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
    parts = module_name.split(".")
    parent_parts = parts[:-1] if len(parts) > 1 else parts
    relative_manifest = Path(*parent_parts) / "manifest.toml"
    dist = getattr(entry_point, "dist", None)
    if dist is not None:
        located = Path(str(dist.locate_file(relative_manifest.as_posix())))
        if located.is_file():
            return located.resolve()
        # Editable installs store a direct_url.json or .pth; fall back to filesystem lookup
        # using sys.path without executing any package __init__.py.
    import sys

    for base in sys.path:
        candidate = Path(base or ".") / relative_manifest
        if candidate.is_file():
            return candidate.resolve()
    raise ConnectorFailure(
        "invalid_entrypoint",
        f"Could not locate connector module: {name}",
    )


def _installed_entry_point(name: str) -> EntryPoint:
    matches = tuple(entry_points().select(group="tarel.connectors", name=name))
    if len(matches) != 1:
        code = "unknown_connector" if not matches else "ambiguous_connector"
        raise ConnectorFailure(code, f"Connector is not uniquely installed: {name}")
    return matches[0]
