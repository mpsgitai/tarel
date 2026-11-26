"""Application use cases for TAREL Hub discovery, suggestions, and installation."""

from __future__ import annotations

import importlib
import importlib.util
import shutil
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

from tarel.connectors.host import check_connector
from tarel.hub.catalog import load_hub_catalog, resolve_hub_extension
from tarel.hub.contracts import HubExtension, HubFailure, HubInstallResult, HubSuggestion
from tarel.hub.suggest import suggest_hub_extensions


def list_hub_extensions_use_case(
    *,
    kind: str | None = None,
    installed: bool | None = None,
    include_planned: bool = False,
    hub_url: str | None = None,
    offline: bool = False,
) -> tuple[HubExtension, ...]:
    """List TAREL Hub extensions with optional filters."""
    extensions = load_hub_catalog(hub_url=hub_url, offline=offline)
    results: list[HubExtension] = []
    for ext in extensions:
        if not include_planned and ext.status == "planned":
            continue
        if kind is not None and ext.kind != kind:
            continue
        if installed is not None and ext.installed != installed:
            continue
        results.append(ext)
    return tuple(results)


def show_hub_extension_use_case(
    identifier: str,
    *,
    hub_url: str | None = None,
    offline: bool = False,
) -> HubExtension:
    """Inspect one TAREL Hub extension by id, package name, or entry-point name."""
    extensions = load_hub_catalog(hub_url=hub_url, offline=offline)
    return resolve_hub_extension(identifier, extensions)


def search_hub_extensions_use_case(
    query: str,
    *,
    kind: str | None = None,
    include_planned: bool = False,
    hub_url: str | None = None,
    offline: bool = False,
) -> tuple[HubExtension, ...]:
    """Search TAREL Hub extensions by id, kind, capability, package, entry point, or evidence."""
    needle = query.strip().lower()
    if not needle:
        return list_hub_extensions_use_case(
            kind=kind,
            include_planned=include_planned,
            hub_url=hub_url,
            offline=offline,
        )
    candidates = list_hub_extensions_use_case(
        kind=kind,
        include_planned=include_planned,
        hub_url=hub_url,
        offline=offline,
    )
    matches: list[HubExtension] = []
    for ext in candidates:
        haystack = " ".join(
            [
                ext.id,
                ext.kind,
                ext.package or "",
                " ".join(ext.capabilities),
                " ".join(ep.name for ep in ext.entry_points),
                ext.real_source_evidence,
            ]
        ).lower()
        if needle in haystack:
            matches.append(ext)
    return tuple(matches)


def suggest_hub_extensions_use_case(
    path: Path | None = None,
    *,
    hub_url: str | None = None,
    offline: bool = True,
) -> tuple[HubSuggestion, ...]:
    """Suggest TAREL Hub extensions for a local project directory without executing code."""
    target = (path or Path.cwd()).resolve()
    extensions = load_hub_catalog(hub_url=hub_url, offline=offline)
    return suggest_hub_extensions(target, extensions)


def install_hub_extension_use_case(
    identifier: str,
    *,
    extra: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    hub_url: str | None = None,
    offline: bool = False,
) -> HubInstallResult:
    """Plan or execute installation of one verified TAREL Hub extension.

    Installation is never executed unless ``yes=True`` and ``dry_run=False``.
    """
    ext = show_hub_extension_use_case(identifier, hub_url=hub_url, offline=offline)
    if ext.status == "planned":
        raise HubFailure(
            "hub_extension_not_installable",
            f"Extension {ext.id} is planned and not available for installation yet.",
        )
    if ext.status == "builtin":
        raise HubFailure(
            "hub_extension_not_installable",
            f"Extension {ext.id} is built into TAREL. {ext.install}",
        )
    if not ext.install_spec:
        raise HubFailure(
            "hub_extension_not_installable",
            f"Extension {ext.id} has no installable specification in the Hub catalog.",
        )
    selected_extra = extra.strip() if extra is not None else None
    if selected_extra == "":
        selected_extra = None
    if selected_extra is not None and selected_extra not in ext.extras:
        available = ", ".join(ext.extras) if ext.extras else "none"
        raise HubFailure(
            "invalid_hub_extra",
            f"Unknown extra {selected_extra!r} for {ext.id}. Available extras: {available}.",
        )
    install_spec = (
        f"{ext.install_spec}[{selected_extra}]" if selected_extra else ext.install_spec
    )
    command = _build_install_command(install_spec)
    should_execute = yes and not dry_run
    if not should_execute:
        return HubInstallResult(
            extension_id=ext.id,
            package=ext.package,
            extra=selected_extra,
            install_spec=install_spec,
            command=command,
            executed=False,
            dry_run=True,
            verified=ext.installed,
            dependencies=ext.dependencies,
            license=ext.license,
        )

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    combined_output = "\n".join(
        part for part in (completed.stdout.strip(), completed.stderr.strip()) if part
    )
    if completed.returncode != 0:
        raise HubFailure(
            "hub_install_failed",
            f"Failed to install {ext.id} (exit {completed.returncode}).\n{combined_output}".strip(),
        )
    importlib.invalidate_caches()
    verified = _verify_installed(ext)
    return HubInstallResult(
        extension_id=ext.id,
        package=ext.package,
        extra=selected_extra,
        install_spec=install_spec,
        command=command,
        executed=True,
        dry_run=False,
        verified=verified,
        dependencies=ext.dependencies,
        license=ext.license,
        output=combined_output,
    )


def _build_install_command(install_spec: str) -> tuple[str, ...]:
    if importlib.util.find_spec("pip") is not None:
        return (sys.executable, "-m", "pip", "install", install_spec)
    uv_bin = shutil.which("uv")
    if uv_bin is not None:
        return (uv_bin, "pip", "install", "--python", sys.executable, install_spec)
    return (sys.executable, "-m", "pip", "install", install_spec)


def _verify_installed(ext: HubExtension) -> bool:
    if not ext.entry_points:
        return False
    if ext.kind == "connector":
        try:
            return all(check_connector(ep.name).available for ep in ext.entry_points)
        except Exception:
            return False
    for ep in ext.entry_points:
        if not tuple(entry_points().select(group=ep.group, name=ep.name)):
            return False
    return True
