"""Provider use cases: list, check, configure, scaffold and test generation providers."""

from __future__ import annotations

from pathlib import Path

from tarel.providers.authoring import ProviderScaffoldResult, scaffold_provider
from tarel.providers.config import (
    BUILTIN_PROVIDER_ADAPTERS,
    HTTP_PROVIDER_ADAPTERS,
    check_provider,
    configure_http_provider,
    configure_installed_provider,
    configure_openrouter,
    list_provider_names,
)
from tarel.providers.contracts import (
    Message,
    ProviderCheck,
    ProviderFailure,
    ProviderTestResult,
    StructuredRequest,
)
from tarel.providers.host import load_provider


def check_provider_use_case(name: str) -> ProviderCheck:
    return check_provider(name)


def list_provider_names_use_case() -> tuple[str, ...]:
    return list_provider_names()


def scaffold_provider_use_case(
    name: str,
    *,
    output: Path | None = None,
) -> ProviderScaffoldResult:
    return scaffold_provider(name, output=output)


def configure_provider_use_case(
    name: str,
    *,
    adapter: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    reasoning_effort: str | None = None,
    structured_mode: str | None = None,
    allow_no_api_key: bool = False,
) -> Path:
    selected_adapter = adapter or BUILTIN_PROVIDER_ADAPTERS.get(name)
    if selected_adapter is None:
        raise ProviderFailure(
            "missing_provider_adapter",
            "Custom provider profiles require --adapter.",
        )
    expected_adapter = BUILTIN_PROVIDER_ADAPTERS.get(name)
    if expected_adapter is not None and selected_adapter != expected_adapter:
        raise ProviderFailure(
            "invalid_provider_adapter",
            f"Provider profile {name} uses the reserved {expected_adapter} adapter.",
        )
    if allow_no_api_key and selected_adapter == "openrouter":
        raise ProviderFailure(
            "missing_api_key",
            f"Provider profile {name} requires an API key.",
        )
    if name == "openrouter" and selected_adapter == "openrouter":
        return configure_openrouter(
            api_key=api_key,
            model=model,
            base_url=base_url,
            reasoning_effort=reasoning_effort,
        )
    if selected_adapter in HTTP_PROVIDER_ADAPTERS:
        return configure_http_provider(
            name,
            adapter=selected_adapter,
            api_key=api_key,
            model=model,
            base_url=base_url,
            reasoning_effort=reasoning_effort,
            structured_mode=structured_mode,
            allow_no_api_key=allow_no_api_key,
        )
    if reasoning_effort is not None or structured_mode is not None:
        raise ProviderFailure(
            "invalid_provider_config",
            "Installed adapters own provider-specific reasoning and structured-output settings.",
        )
    return configure_installed_provider(
        name,
        adapter=selected_adapter,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )


def test_provider_use_case(name: str, *, timeout: float = 120.0) -> ProviderTestResult:
    provider = load_provider(name, timeout=timeout)
    result = provider.generate_structured(
        StructuredRequest(
            messages=(
                Message(
                    role="user",
                    content='Return exactly {"status":"ok"} as structured JSON.',
                ),
            ),
            schema_name="TarelProviderCheck",
            schema={
                "additionalProperties": False,
                "properties": {"status": {"const": "ok", "type": "string"}},
                "required": ["status"],
                "type": "object",
            },
        )
    )
    if result != {"status": "ok"}:
        raise ProviderFailure(
            "invalid_provider_response",
            "Provider check returned an unexpected structured response.",
        )
    return {"name": name, "status": "ok"}
