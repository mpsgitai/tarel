"""Complete a wheel folder for the target's environment markers.

``pip download --platform`` selects wheel tags for the target but evaluates environment markers
(``sys_platform == "win32"`` and friends) for *this* machine. A bundle built on Linux for Windows
would silently lack Windows-only dependencies, and pip's own dry run cannot notice, because it
makes the same substitution. This module walks the dependency closure with the target's markers,
downloads what is missing, and drops what the target never installs.

Marker and requirement parsing use the ``packaging`` copy that pip vendors: bundles already need
pip, so this adds no dependency, and hand-written marker evaluation would be a second truth.
"""

from __future__ import annotations

import email.parser
import re
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tarel.bundle.contracts import BundleFailure, Target

# Downloads use --no-deps, so each round adds one level of the dependency tree.
_MAX_ROUNDS = 30
_SYSTEMS = {
    "windows": ("win32", "Windows", "nt"),
    "linux": ("linux", "Linux", "posix"),
    "macos": ("darwin", "Darwin", "posix"),
}
_MACHINES = {
    ("windows", "x86_64"): "AMD64",
    ("windows", "arm64"): "ARM64",
    ("linux", "x86_64"): "x86_64",
    ("linux", "arm64"): "aarch64",
    ("macos", "x86_64"): "x86_64",
    ("macos", "arm64"): "arm64",
}


# A target is known as "3.12", not its patch release. Markers are evaluated for the first and
# for a late patch release, and a dependency counts if either needs it: an extra wheel is
# harmless, a missing one breaks the offline install.
_PATCHES = ("0", "99")


def marker_environments(target: Target) -> tuple[dict[str, str], ...]:
    return tuple(marker_environment(target, patch) for patch in _PATCHES)


def marker_environment(target: Target, patch: str = "0") -> dict[str, str]:
    sys_platform, system, os_name = _SYSTEMS[target.os]
    return {
        "sys_platform": sys_platform,
        "platform_system": system,
        "os_name": os_name,
        "platform_machine": _MACHINES[(target.os, target.arch)],
        "python_version": target.python,
        "python_full_version": f"{target.python}.{patch}",
        "implementation_name": "cpython",
        "platform_python_implementation": "CPython",
        "implementation_version": f"{target.python}.{patch}",
        "platform_release": "",
        "platform_version": "",
        "extra": "",
    }


@dataclass(frozen=True)
class _Wheel:
    path: Path
    version: str
    requires: tuple[str, ...]


@dataclass(frozen=True)
class _Walk:
    needed: dict[str, set[str]]  # project -> selected extras
    missing: dict[str, str]  # project -> requirement to download, without markers
    stale: dict[str, list[str]]  # project whose wheel fails a constraint -> who asks what
    asks: dict[str, list[str]]  # project -> "parent needs requirement", for every edge


def complete_for_target(
    wheels: Path,
    roots: Iterable[str],
    target: Target,
    download: Callable[[list[str]], None],
    *,
    local: Iterable[str] = (),
) -> None:
    """Download until the closure of ``roots`` is complete, then delete unused wheels.

    ``download`` must fetch exactly the requirements it is given, without their dependencies:
    pip would resolve those for this machine. ``local`` names projects built from local sources;
    they are never swapped for a download.

    The walk takes the newest version that satisfies every constraint seen so far; unlike pip it
    does not backtrack to older versions of a parent. A conflict therefore stops the build with
    every constraint named, instead of producing a bundle that cannot install.
    """
    packaging = _packaging()
    environments = marker_environments(target)
    roots = tuple(roots)
    protected = {_normalize(name) for name in local}
    walk: _Walk | None = None
    for _ in range(_MAX_ROUNDS):
        index = _index(wheels, packaging)
        walk = _closure(index, roots, environments, packaging)
        if not walk.missing:
            for name, wheel in index.items():
                if name not in walk.needed:
                    wheel.path.unlink()
            return
        for name, asks in walk.stale.items():
            if name in protected:
                raise BundleFailure(
                    "bundle_resolve_conflict",
                    f"The locally built {index[name].path.name} does not satisfy every "
                    f"constraint on the target: {'; '.join(asks)}.",
                )
            # A newer download replaces it; two wheels of one project would be ambiguous.
            index[name].path.unlink()
        try:
            download(sorted(walk.missing.values()))
        except BundleFailure as exc:
            raise BundleFailure(exc.code, f"{exc}{_explain(walk)}") from exc
    missing = sorted(walk.missing.values()) if walk is not None else []
    raise BundleFailure(
        "bundle_resolve_incomplete", f"Dependencies still missing after downloading: {missing}."
    )


def _explain(walk: _Walk) -> str:
    """Name who asks for what when several packages constrain one dependency."""
    shared = {name: walk.asks[name] for name in walk.missing if len(walk.asks[name]) > 1}
    if not shared:
        return ""
    lines = [f"  {name}: {'; '.join(asks)}" for name, asks in sorted(shared.items())]
    return (
        "\n\nThese packages constrain the same dependency:\n"
        + "\n".join(lines)
        + "\nThe bundle takes the newest version of each package and does not try older ones. "
        "If the constraints exclude each other, pin a compatible version in the package that "
        "needs it."
    )


def _closure(
    index: dict[str, _Wheel],
    roots: tuple[str, ...],
    environments: tuple[dict[str, str], ...],
    packaging: Any,
) -> _Walk:
    """Walk the closure of ``roots`` with the target's markers."""
    requirement_type = packaging.requirements.Requirement
    needed: dict[str, set[str]] = {}
    constraints: dict[str, list[tuple[Any, str]]] = {}
    queue = [(requirement_type(text), "the bundle") for text in roots]
    while queue:
        requirement, parent = queue.pop()
        name = _normalize(requirement.name)
        if requirement.url:
            # Collection and the offline install both go through wheels/; a URL would be
            # silently swapped for an index package of the same name.
            raise BundleFailure(
                "bundle_direct_reference",
                f"{parent} depends on {requirement.name} by URL ({requirement.url}). Offline "
                "bundles take every package from an index or a local build; publish it there.",
            )
        # Record every edge's constraint, also for a project whose dependencies were walked.
        constraints.setdefault(name, []).append((requirement, parent))
        known = needed.get(name)
        extras = set(requirement.extras)
        if known is not None and extras <= known:
            continue
        needed.setdefault(name, set()).update(extras)
        wheel = index.get(name)
        if wheel is None or not _satisfies(wheel, constraints[name]):
            continue
        # Extras add to the base dependencies; pip always installs the base set as well.
        active_extras = {"", *needed[name]}
        label = f"{wheel.path.name.split('-')[0]} {wheel.version}"
        for text in wheel.requires:
            dependency = requirement_type(text)
            marker = dependency.marker
            if marker is None or any(
                marker.evaluate({**environment, "extra": extra})
                for environment in environments
                for extra in active_extras
            ):
                queue.append((dependency, label))
    missing: dict[str, str] = {}
    stale: dict[str, list[str]] = {}
    asks = {
        name: [f"{parent} needs {_without_marker(r)}" for r, parent in edges]
        for name, edges in constraints.items()
    }
    for name, edges in constraints.items():
        wheel = index.get(name)
        if wheel is not None and _satisfies(wheel, edges):
            continue
        if wheel is not None:
            stale[name] = asks[name]
        missing[name] = _combined(name, needed[name], [r for r, _ in edges], packaging)
    return _Walk(needed=needed, missing=missing, stale=stale, asks=asks)


def _satisfies(wheel: _Wheel, edges: list[tuple[Any, str]]) -> bool:
    return all(r.specifier.contains(wheel.version, prereleases=True) for r, _ in edges)


def _without_marker(requirement: Any) -> str:
    extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
    return f"{requirement.name}{extras}{requirement.specifier}"


def _combined(name: str, extras: set[str], requirements: list[Any], packaging: Any) -> str:
    """One requirement without markers that satisfies every edge to ``name`` at once."""
    specifiers = packaging.specifiers.SpecifierSet(
        ",".join(str(r.specifier) for r in requirements if str(r.specifier))
    )
    extra = f"[{','.join(sorted(extras))}]" if extras else ""
    return f"{name}{extra}{specifiers}"


def _index(wheels: Path, packaging: Any) -> dict[str, _Wheel]:
    index: dict[str, _Wheel] = {}
    for path in sorted(wheels.glob("*.whl")):
        metadata = wheel_metadata(path)
        name = _normalize(str(metadata.get("Name", "")))
        if not name:
            raise BundleFailure("bundle_wheel_metadata", f"{path.name} has no package name.")
        if name in index:
            raise BundleFailure(
                "bundle_wheel_duplicate",
                f"Two wheels for {name}: {index[name].path.name} and {path.name}.",
            )
        index[name] = _Wheel(
            path=path,
            version=str(packaging.version.Version(str(metadata.get("Version")))),
            requires=tuple(str(value) for value in metadata.get_all("Requires-Dist", [])),
        )
    return index


def wheel_metadata(wheel: Path) -> Any:
    with zipfile.ZipFile(wheel) as archive:
        name = next((n for n in archive.namelist() if n.endswith(".dist-info/METADATA")), None)
        if name is None:
            raise BundleFailure("bundle_wheel_metadata", f"{wheel.name} has no METADATA.")
        return email.parser.BytesHeaderParser().parsebytes(archive.read(name))


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _packaging() -> Any:
    try:
        from pip._vendor import packaging  # type: ignore[attr-defined,unused-ignore]
        from pip._vendor.packaging import requirements, specifiers, version  # noqa: F401
    except ImportError as exc:
        raise BundleFailure(
            "bundle_pip_unavailable", "pip is not importable from this Python."
        ) from exc
    return packaging
