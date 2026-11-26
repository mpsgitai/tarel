"""Discovery, inspection, project suggestion, and explicit installation for TAREL Hub."""

from tarel.hub.application import (
    install_hub_extension_use_case,
    list_hub_extensions_use_case,
    search_hub_extensions_use_case,
    show_hub_extension_use_case,
    suggest_hub_extensions_use_case,
)
from tarel.hub.contracts import (
    HubEntryPoint,
    HubExtension,
    HubFailure,
    HubInstallResult,
    HubSuggestion,
)

__all__ = [
    "HubEntryPoint",
    "HubExtension",
    "HubFailure",
    "HubInstallResult",
    "HubSuggestion",
    "install_hub_extension_use_case",
    "list_hub_extensions_use_case",
    "search_hub_extensions_use_case",
    "show_hub_extension_use_case",
    "suggest_hub_extensions_use_case",
]
