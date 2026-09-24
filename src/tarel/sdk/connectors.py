"""Low-level read-only connector operations for embedded harnesses."""

from __future__ import annotations

from pathlib import Path

from tarel.application import (
    check_connector_use_case,
    discover_catalog_use_case,
    probe_connector_use_case,
    profile_connector_use_case,
    sample_connector_use_case,
)
from tarel.connectors.contracts import (
    CatalogResult,
    ConnectorCheck,
    ObjectProfileResult,
    ProbeResult,
    SampleResult,
)


class ConnectorAPI:
    """Call connectors directly without applying a named source permission policy."""

    __slots__ = ()

    def check(self, name: str) -> ConnectorCheck:
        return check_connector_use_case(name)

    def probe(
        self,
        name: str,
        *,
        config: str | Path,
        database: str | None = None,
    ) -> ProbeResult:
        return probe_connector_use_case(
            name,
            config_path=Path(config),
            database=database,
        )

    def discover(
        self,
        name: str,
        *,
        config: str | Path,
        database: str | None = None,
        namespace: str | None = None,
    ) -> CatalogResult:
        return discover_catalog_use_case(
            name,
            config_path=Path(config),
            database=database,
            namespace=namespace,
        )

    def sample(
        self,
        name: str,
        *,
        config: str | Path,
        namespace: str,
        object: str,
        limit: int,
        database: str | None = None,
    ) -> SampleResult:
        """Return an ephemeral bounded sample; the SDK never persists its row values."""
        return sample_connector_use_case(
            name,
            config_path=Path(config),
            database=database,
            namespace=namespace,
            object_name=object,
            limit=limit,
        )

    def profile(
        self,
        name: str,
        *,
        config: str | Path,
        namespace: str,
        object: str,
        row_limit: int,
        database: str | None = None,
        small_domain_limit: int = 20,
        include_values: bool = False,
    ) -> ObjectProfileResult:
        return profile_connector_use_case(
            name,
            config_path=Path(config),
            database=database,
            namespace=namespace,
            object_name=object,
            row_limit=row_limit,
            small_domain_limit=small_domain_limit,
            include_values=include_values,
        )
