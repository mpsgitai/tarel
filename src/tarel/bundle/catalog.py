"""The parts a bundle can contain: core extras and the packages listed in a hub checkout.

Hub packages are read from the hub's ``catalog/catalog.toml``; reading it imports nothing and
builds nothing. Entries without a package path (built-in or planned) are not offered.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from tarel.bundle.contracts import BundleFailure, Component, ComponentKind

CORE_COMPONENTS: tuple[Component, ...] = (
    Component(
        id="sqlite",
        kind="source",
        origin="core",
        summary="SQLite (always included)",
        status="builtin",
        requirement=None,
        always=True,
    ),
    Component(
        id="sqlserver",
        kind="source",
        origin="core",
        summary="Microsoft SQL Server",
        status="builtin",
        requirement="sqlserver",
    ),
    Component(
        id="semantic",
        kind="extra",
        origin="core",
        summary="Semantic models from YAML",
        status="builtin",
        requirement="semantic",
    ),
    Component(
        id="vector",
        kind="extra",
        origin="core",
        summary="Vector search inside SQLite",
        status="builtin",
        requirement="vector",
    ),
)

# A hub package extra that ships native client libraries inside the wheel. An offline target
# cannot install system libraries later, so a bundle always takes it when the package offers it.
_SELF_CONTAINED_EXTRA = "binary"
_OFFERED_STATUSES = ("experimental", "stable")
_CONNECTOR_PREFIX = "connector-"


def hub_components(hub_root: Path) -> tuple[Component, ...]:
    """Read the installable packages of one hub checkout."""
    catalog_path = hub_root / "catalog" / "catalog.toml"
    try:
        catalog = tomllib.loads(catalog_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BundleFailure(
            "bundle_hub_missing", f"No TAREL hub catalog at {catalog_path}."
        ) from exc
    except tomllib.TOMLDecodeError as exc:
        raise BundleFailure("bundle_hub_invalid", f"{catalog_path} is not valid TOML.") from exc
    components = []
    for entry in catalog.get("extension", []):
        if entry.get("status") not in _OFFERED_STATUSES or not entry.get("path"):
            continue
        package_dir = (hub_root / entry["path"]).resolve()
        project = _read_project(package_dir)
        extras = project.get("optional-dependencies", {})
        requirement = entry["package"]
        if _SELF_CONTAINED_EXTRA in extras:
            requirement += f"[{_SELF_CONTAINED_EXTRA}]"
        kind: ComponentKind = "source" if "connector" in entry.get("capabilities", []) else "extra"
        components.append(
            Component(
                id=entry["id"].removeprefix(_CONNECTOR_PREFIX),
                kind=kind,
                origin="hub",
                summary=str(project.get("description", entry["id"])).rstrip("."),
                status=entry["status"],
                requirement=requirement,
                hub_path=package_dir,
                import_name=entry.get("import_name"),
            )
        )
    return tuple(components)


def _read_project(package_dir: Path) -> dict[str, Any]:
    pyproject = package_dir / "pyproject.toml"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError) as exc:
        raise BundleFailure(
            "bundle_hub_package", f"Hub package has no readable pyproject.toml: {pyproject}."
        ) from exc
    project = data.get("project")
    if not isinstance(project, dict):
        raise BundleFailure("bundle_hub_package", f"{pyproject} has no [project] table.")
    return project


def available_components(hub_root: Path | None) -> tuple[Component, ...]:
    hub = hub_components(hub_root) if hub_root is not None else ()
    taken = {component.id for component in CORE_COMPONENTS}
    clashes = sorted(component.id for component in hub if component.id in taken)
    if clashes:
        raise BundleFailure(
            "bundle_hub_clash", f"Hub packages reuse core component names: {', '.join(clashes)}."
        )
    return CORE_COMPONENTS + hub


def select_components(
    available: tuple[Component, ...], chosen: tuple[str, ...]
) -> tuple[Component, ...]:
    """The chosen components plus the ones that are always included, in catalog order."""
    by_id = {component.id: component for component in available}
    unknown = sorted(set(chosen) - set(by_id))
    if unknown:
        hint = "" if any(c.origin == "hub" for c in available) else " Pass --hub for hub packages."
        raise BundleFailure(
            "bundle_component_unknown", f"Unknown component(s): {', '.join(unknown)}.{hint}"
        )
    return tuple(c for c in available if c.always or c.id in chosen)
