"""Embedded provider administration over the CLI application paths."""

from __future__ import annotations

from pathlib import Path

from tarel.application import (
    check_provider_use_case,
    configure_provider_use_case,
    list_provider_names_use_case,
    test_provider_use_case,
)
from tarel.providers.contracts import ProviderCheck


class ProviderAPI:
    """Manage private user-level provider profiles from an embedded harness."""

    __slots__ = ()

    def list(self) -> tuple[str, ...]:
        return list_provider_names_use_case()

    def check(self, name: str) -> ProviderCheck:
        return check_provider_use_case(name)

    def configure(
        self,
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
        """Persist one private user profile; the returned path never contains its secret."""
        return configure_provider_use_case(
            name,
            adapter=adapter,
            api_key=api_key,
            model=model,
            base_url=base_url,
            reasoning_effort=reasoning_effort,
            structured_mode=structured_mode,
            allow_no_api_key=allow_no_api_key,
        )

    def test(self, name: str, *, timeout: float = 120.0) -> dict[str, object]:
        """Make the same explicit, potentially billable provider request as the CLI."""
        return test_provider_use_case(name, timeout=timeout)
