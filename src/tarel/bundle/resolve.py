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

_MAX_ROUNDS = 10
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


def marker_environment(target: Target) -> dict[str, str]:
    sys_platform, system, os_name = _SYSTEMS[target.os]
    return {
        "sys_platform": sys_platform,
        "platform_system": system,
        "os_name": os_name,
        "platform_machine": _MACHINES[(target.os, target.arch)],
        "python_version": target.python,
        # The patch level is unknown; .0 is the conservative reading of "3.12".
        "python_full_version": f"{target.python}.0",
        "implementation_name": "cpython",
        "platform_python_implementation": "CPython",
        "implementation_version": f"{target.python}.0",
        "platform_release": "",
        "platform_version": "",
        "extra": "",
    }


@dataclass(frozen=True)
class _Wheel:
    path: Path
    version: str
    requires: tuple[str, ...]


def complete_for_target(
    wheels: Path,
    roots: Iterable[str],
    target: Target,
    download: Callable[[list[str]], None],
) -> None:
    """Download until the closure of ``roots`` is complete, then delete unused wheels."""
    packaging = _packaging()
    environment = marker_environment(target)
    roots = tuple(roots)
    for _ in range(_MAX_ROUNDS):
        index = _index(wheels, packaging)
        needed, missing = _closure(index, roots, environment, packaging)
        if not missing:
            for name, wheel in index.items():
                if name not in needed:
                    wheel.path.unlink()
            return
        download(missing)
    raise BundleFailure(
        "bundle_resolve_incomplete", f"Dependencies still missing after downloading: {missing}."
    )


def _closure(
    index: dict[str, _Wheel],
    roots: tuple[str, ...],
    environment: dict[str, str],
    packaging: Any,
) -> tuple[dict[str, set[str]], list[str]]:
    requirement_type = packaging.requirements.Requirement
    needed: dict[str, set[str]] = {}
    missing: list[str] = []
    queue = [requirement_type(text) for text in roots]
    while queue:
        requirement = queue.pop()
        name = _normalize(requirement.name)
        known = needed.get(name)
        extras = set(requirement.extras)
        if known is not None and extras <= known:
            continue
        needed.setdefault(name, set()).update(extras)
        wheel = index.get(name)
        if wheel is None:
            missing.append(_without_marker(requirement))
            continue
        if not requirement.specifier.contains(wheel.version, prereleases=True):
            raise BundleFailure(
                "bundle_resolve_conflict",
                f"{wheel.path.name} does not satisfy {requirement} on the target.",
            )
        active_extras = needed[name] or {""}
        for text in wheel.requires:
            dependency = requirement_type(text)
            marker = dependency.marker
            if marker is None or any(
                marker.evaluate({**environment, "extra": extra}) for extra in active_extras
            ):
                queue.append(dependency)
    return needed, sorted(set(missing))


def _without_marker(requirement: Any) -> str:
    extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
    return f"{requirement.name}{extras}{requirement.specifier}"


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
        from pip._vendor.packaging import requirements, version  # noqa: F401
    except ImportError as exc:
        raise BundleFailure(
            "bundle_pip_unavailable", "pip is not importable from this Python."
        ) from exc
    return packaging
