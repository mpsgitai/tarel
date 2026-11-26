"""Explicit loading and checking of trusted connector manifests."""

from __future__ import annotations

import importlib
import importlib.util
import tomllib
from collections.abc import Callable
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any, cast

from tarel.connectors.contracts import (
    Connector,
    ConnectorCheck,
    ConnectorFailure,
    ConnectorManifest,
)

_CONNECTOR_ROOT = Path(__file__).resolve().parent
_BUILTIN_MANIFESTS = {
    "sqlite": _CONNECTOR_ROOT / "sqlite" / "manifest.toml",
    "sqlserver": _CONNECTOR_ROOT / "sqlserver" / "manifest.toml",
}


def list_connectors() -> tuple[ConnectorCheck, ...]:
    """Return checks for built-in and installed connectors without importing drivers."""
    names = set(_BUILTIN_MANIFESTS)
    names.update(ep.name for ep in entry_points().select(group="tarel.connectors"))
    return tuple(check_connector(name) for name in sorted(names))


def check_connector(name: str) -> ConnectorCheck:
    manifest = load_manifest(name)
    missing = tuple(
        dependency
        for dependency in manifest.dependencies
        if importlib.util.find_spec(dependency) is None
    )
    return ConnectorCheck(
        name=manifest.name,
        version=manifest.version,
        source_type=manifest.source_type,
        available=not missing,
        capabilities=manifest.capabilities,
        permissions=manifest.permissions,
        missing_dependencies=missing,
        extra=manifest.extra,
        dialect=manifest.dialect,
        references=manifest.references,
        auth=manifest.auth,
    )


def load_manifest(name: str) -> ConnectorManifest:
    manifest_path = _BUILTIN_MANIFESTS.get(name)
    if manifest_path is not None and tuple(
        entry_points().select(group="tarel.connectors", name=name)
    ):
        raise ConnectorFailure(
            "ambiguous_connector",
            f"An installed package also provides the built-in connector {name}. "
            "Uninstall it or give it another name.",
        )
    if manifest_path is None:
        entry_point = _installed_entry_point(name)
        module_name, separator, _factory_name = entry_point.value.partition(":")
        if not separator or not module_name:
            raise ConnectorFailure(
                "invalid_entrypoint",
                f"Connector entry point is invalid: {name}",
            )
        manifest_path = _manifest_path_for_entry_point(name, entry_point, module_name)
    try:
        with manifest_path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConnectorFailure(
            "invalid_manifest",
            f"Could not read connector manifest: {name}",
        ) from exc
    manifest = ConnectorManifest.from_mapping(data)
    if manifest.name != name:
        raise ConnectorFailure(
            "invalid_manifest",
            "Connector name does not match its manifest path.",
        )
    if name not in _BUILTIN_MANIFESTS:
        entry_point = _installed_entry_point(name)
        if manifest.entrypoint != entry_point.value:
            raise ConnectorFailure(
                "invalid_manifest",
                "Connector manifest entrypoint does not match its installed entry point.",
            )
    return manifest


def load_connector(name: str) -> Connector:
    manifest = load_manifest(name)
    check = check_connector(name)
    if not check.available:
        missing = ", ".join(check.missing_dependencies)
        hint = (
            f"Install with `pip install tarel[{manifest.extra}]`."
            if name in _BUILTIN_MANIFESTS
            else "Reinstall the package that provides this connector."
        )
        raise ConnectorFailure("missing_dependency", f"Connector {name} requires {missing}. {hint}")

    try:
        if name in _BUILTIN_MANIFESTS:
            module_name, separator, factory_name = manifest.entrypoint.partition(":")
            if not separator or not module_name or not factory_name:
                raise ConnectorFailure(
                    "invalid_manifest", "Connector entrypoint must be module:function."
                )
            module = importlib.import_module(module_name)
            factory = cast(Callable[[ConnectorManifest], Any], getattr(module, factory_name))
        else:
            factory = cast(
                Callable[[ConnectorManifest], Any],
                _installed_entry_point(name).load(),
            )
        connector = factory(manifest)
    except ConnectorFailure:
        raise
    except (AttributeError, ImportError, TypeError) as exc:
        raise ConnectorFailure("invalid_entrypoint", f"Could not load connector: {name}") from exc
    return cast(Connector, connector)


def _manifest_path_for_entry_point(
    name: str,
    entry_point: EntryPoint,
    module_name: str,
) -> Path:
    """Locate a connector's manifest.toml without importing any plugin Python code."""
    parts = [part for part in module_name.split(".") if part]
    if not parts:
        raise ConnectorFailure(
            "invalid_entrypoint",
            f"Could not locate connector module: {name}",
        )
    relative_candidates = [Path(*parts) / "manifest.toml"]
    if len(parts) > 1:
        relative_candidates.append(Path(*parts[:-1]) / "manifest.toml")

    dist = getattr(entry_point, "dist", None)
    if dist is not None:
        for relative_manifest in relative_candidates:
            located = Path(str(dist.locate_file(relative_manifest.as_posix())))
            if located.is_file():
                return located.resolve()

    from_meta_path = _manifest_path_from_meta_path(parts)
    if from_meta_path is not None:
        return from_meta_path

    import sys

    for base in sys.path:
        base_path = Path(base or ".")
        for relative_manifest in relative_candidates:
            candidate = base_path / relative_manifest
            if candidate.is_file():
                return candidate.resolve()
    raise ConnectorFailure(
        "invalid_entrypoint",
        f"Could not locate connector module: {name}",
    )


def _manifest_path_from_meta_path(parts: list[str]) -> Path | None:
    """Resolve manifest.toml via sys.meta_path finders without importing packages."""
    candidate_names = [".".join(parts)]
    if len(parts) > 1:
        candidate_names.append(".".join(parts[:-1]))
    for candidate_name in candidate_names:
        spec = _find_spec_without_import(candidate_name)
        if spec is None:
            continue
        if spec.origin and spec.origin != "namespace":
            manifest = Path(spec.origin).resolve().parent / "manifest.toml"
            if manifest.is_file():
                return manifest
        if spec.submodule_search_locations:
            for location in spec.submodule_search_locations:
                manifest = Path(location) / "manifest.toml"
                if manifest.is_file():
                    return manifest.resolve()
    return None


def _find_spec_without_import(module_name: str) -> Any:
    """Walk sys.meta_path finders segment-by-segment without executing __init__.py."""
    import sys

    parts = module_name.split(".")
    search_path: list[str] | None = None
    spec: Any = None
    for index in range(len(parts)):
        fullname = ".".join(parts[: index + 1])
        spec = None
        for finder in sys.meta_path:
            find_spec = getattr(finder, "find_spec", None)
            if find_spec is None:
                continue
            try:
                spec = find_spec(fullname, search_path)
            except Exception:
                continue
            if spec is not None:
                break
        if spec is None:
            return None
        if index < len(parts) - 1:
            locations = getattr(spec, "submodule_search_locations", None)
            if locations is None:
                return None
            search_path = list(locations)
    return spec


def _installed_entry_point(name: str) -> EntryPoint:
    matches = tuple(entry_points().select(group="tarel.connectors", name=name))
    if len(matches) != 1:
        if not matches:
            from tarel.hub.catalog import hub_hint_for_entry_point

            hub_hint = hub_hint_for_entry_point("tarel.connectors", name)
            if hub_hint is not None:
                ext_id, install_cmd = hub_hint
                raise ConnectorFailure(
                    "unknown_connector",
                    f"Connector is not uniquely installed: {name}. "
                    f"Install from TAREL Hub: `{install_cmd}`.",
                    hint=install_cmd,
                    details={"hub_package": ext_id, "install_hint": install_cmd},
                )
            raise ConnectorFailure(
                "unknown_connector",
                f"Connector is not uniquely installed: {name}",
            )
        raise ConnectorFailure(
            "ambiguous_connector",
            f"Connector is not uniquely installed: {name}",
        )
    return matches[0]
