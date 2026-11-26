"""TAREL Hub discovery, project suggestion, and explicit installation facade."""

from __future__ import annotations

from pathlib import Path

from tarel.hub.application import (
    install_hub_extension_use_case,
    list_hub_extensions_use_case,
    search_hub_extensions_use_case,
    show_hub_extension_use_case,
    suggest_hub_extensions_use_case,
)
from tarel.hub.contracts import HubExtension, HubInstallResult, HubSuggestion


class HubAPI:
    """Discover, inspect, suggest, and explicitly install TAREL Hub extensions."""

    __slots__ = ()

    def list(
        self,
        *,
        kind: str | None = None,
        installed: bool | None = None,
        include_planned: bool = False,
        hub_url: str | None = None,
        offline: bool = False,
    ) -> tuple[HubExtension, ...]:
        return list_hub_extensions_use_case(
            kind=kind,
            installed=installed,
            include_planned=include_planned,
            hub_url=hub_url,
            offline=offline,
        )

    def show(
        self,
        name: str,
        *,
        hub_url: str | None = None,
        offline: bool = False,
    ) -> HubExtension:
        return show_hub_extension_use_case(
            name,
            hub_url=hub_url,
            offline=offline,
        )

    def search(
        self,
        query: str,
        *,
        kind: str | None = None,
        include_planned: bool = False,
        hub_url: str | None = None,
        offline: bool = False,
    ) -> tuple[HubExtension, ...]:
        return search_hub_extensions_use_case(
            query,
            kind=kind,
            include_planned=include_planned,
            hub_url=hub_url,
            offline=offline,
        )

    def suggest(
        self,
        path: str | Path | None = None,
        *,
        hub_url: str | None = None,
        offline: bool = True,
    ) -> tuple[HubSuggestion, ...]:
        return suggest_hub_extensions_use_case(
            Path(path) if path is not None else None,
            hub_url=hub_url,
            offline=offline,
        )

    def install(
        self,
        name: str,
        *,
        extra: str | None = None,
        dry_run: bool = False,
        yes: bool = False,
        hub_url: str | None = None,
        offline: bool = False,
    ) -> HubInstallResult:
        return install_hub_extension_use_case(
            name,
            extra=extra,
            dry_run=dry_run,
            yes=yes,
            hub_url=hub_url,
            offline=offline,
        )
