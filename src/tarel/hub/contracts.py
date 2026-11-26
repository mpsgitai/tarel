"""Typed contracts for TAREL Hub catalog discovery, suggestions, and installation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tarel.errors import TarelError


class HubFailure(TarelError):
    """Raised when a TAREL Hub discovery or installation operation fails."""


@dataclass(frozen=True, slots=True)
class HubEntryPoint:
    """One Python entry point declared by a TAREL Hub extension."""

    group: str
    name: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> HubEntryPoint:
        group = str(payload.get("group", "")).strip()
        name = str(payload.get("name", "")).strip()
        if not group or not name:
            raise HubFailure("invalid_hub_catalog", "Hub entry point requires group and name.")
        return cls(group=group, name=name)

    def to_dict(self) -> dict[str, str]:
        return {"group": self.group, "name": self.name}


@dataclass(frozen=True, slots=True)
class HubExtension:
    """One extension entry from the TAREL Hub catalog, enriched with local host status."""

    id: str
    kind: str
    capabilities: tuple[str, ...]
    status: str
    package: str | None
    import_name: str | None
    path: str | None
    entry_points: tuple[HubEntryPoint, ...]
    host_contract: str
    host_versions: str | None
    dependencies: tuple[str, ...]
    native_requirements: tuple[str, ...]
    extras: tuple[str, ...]
    recommended_extra: str | None
    license: str
    origin: str
    install: str
    install_spec: str | None
    real_source_evidence: str
    installed: bool = False
    compatible: bool = True
    config_template: str | None = None
    catalog_source: str = "bundled_snapshot"

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        installed: bool = False,
        compatible: bool = True,
        config_template: str | None = None,
        catalog_source: str = "bundled_snapshot",
    ) -> HubExtension:
        ext_id = str(payload.get("id", "")).strip()
        if not ext_id:
            raise HubFailure("invalid_hub_catalog", "Hub extension entry is missing an id.")
        raw_eps = payload.get("entry_points")
        eps: list[HubEntryPoint] = []
        if isinstance(raw_eps, list):
            eps = [HubEntryPoint.from_dict(item) for item in raw_eps if isinstance(item, Mapping)]
        elif isinstance(payload.get("entry_point"), Mapping):
            eps = [HubEntryPoint.from_dict(payload["entry_point"])]
        return cls(
            id=ext_id,
            kind=str(payload.get("kind", "extension")).strip() or "extension",
            capabilities=tuple(str(item) for item in payload.get("capabilities", ())),
            status=str(payload.get("status", "")).strip(),
            package=_opt_str(payload.get("package")),
            import_name=_opt_str(payload.get("import_name")),
            path=_opt_str(payload.get("path")),
            entry_points=tuple(eps),
            host_contract=str(payload.get("host_contract", "")).strip(),
            host_versions=_opt_str(payload.get("host_versions")),
            dependencies=tuple(str(item) for item in payload.get("dependencies", ())),
            native_requirements=tuple(
                str(item) for item in payload.get("native_requirements", ())
            ),
            extras=tuple(str(item) for item in payload.get("extras", ())),
            recommended_extra=_opt_str(payload.get("recommended_extra")),
            license=str(payload.get("license", "")).strip(),
            origin=str(payload.get("origin", "")).strip(),
            install=str(payload.get("install", "")).strip(),
            install_spec=_opt_str(payload.get("install_spec")),
            real_source_evidence=str(payload.get("real_source_evidence", "")).strip(),
            installed=installed,
            compatible=compatible,
            config_template=config_template,
            catalog_source=catalog_source,
        )

    @property
    def recommended_cli_install(self) -> str | None:
        if self.status == "planned":
            return None
        if self.status == "builtin":
            return self.install or None
        extra_flag = f" --extra {self.recommended_extra}" if self.recommended_extra else ""
        return f"tarel hub install {self.id}{extra_flag} --yes"

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilities": list(self.capabilities),
            "catalog_source": self.catalog_source,
            "compatible": self.compatible,
            "config_template": self.config_template,
            "dependencies": list(self.dependencies),
            "entry_points": [ep.to_dict() for ep in self.entry_points],
            "extras": list(self.extras),
            "host_contract": self.host_contract,
            "host_versions": self.host_versions,
            "id": self.id,
            "import_name": self.import_name,
            "install": self.install,
            "install_spec": self.install_spec,
            "installed": self.installed,
            "kind": self.kind,
            "license": self.license,
            "native_requirements": list(self.native_requirements),
            "origin": self.origin,
            "package": self.package,
            "path": self.path,
            "real_source_evidence": self.real_source_evidence,
            "recommended_cli_install": self.recommended_cli_install,
            "recommended_extra": self.recommended_extra,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class HubInstallResult:
    """Result of planning or executing a TAREL Hub package installation."""

    extension_id: str
    package: str | None
    extra: str | None
    install_spec: str
    command: tuple[str, ...]
    executed: bool
    dry_run: bool
    verified: bool
    dependencies: tuple[str, ...]
    license: str
    output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "dependencies": list(self.dependencies),
            "dry_run": self.dry_run,
            "executed": self.executed,
            "extension_id": self.extension_id,
            "extra": self.extra,
            "install_spec": self.install_spec,
            "license": self.license,
            "output": self.output,
            "package": self.package,
            "verified": self.verified,
        }


@dataclass(frozen=True, slots=True)
class HubSuggestion:
    """A static, read-only project recommendation for a TAREL Hub extension."""

    extension_id: str
    kind: str
    package: str | None
    installed: bool
    confidence: str
    reasons: tuple[str, ...]
    install_command: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "extension_id": self.extension_id,
            "install_command": self.install_command,
            "installed": self.installed,
            "kind": self.kind,
            "package": self.package,
            "reasons": list(self.reasons),
        }


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
