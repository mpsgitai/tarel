"""Connector use cases: check, probe, discover, sample and profile a configured source."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, cast

from tarel.connectors.authoring import ScaffoldResult, scaffold_connector
from tarel.connectors.contracts import (
    CatalogRequest,
    CatalogResult,
    ConnectorCheck,
    ConnectorFailure,
    ObjectProfileConnector,
    ObjectProfileRequest,
    ObjectProfileResult,
    ProbeRequest,
    ProbeResult,
    SampleRequest,
    SampleResult,
)
from tarel.connectors.host import check_connector, load_connector


def check_connector_use_case(name: str) -> ConnectorCheck:
    return check_connector(name)


def probe_connector_use_case(
    name: str,
    *,
    config_path: Path | None = None,
    database: str | None = None,
) -> ProbeResult:
    config = read_config(config_path)
    section = config.get(name, {})
    if not isinstance(section, dict):
        raise ConnectorFailure("invalid_config", f"Configuration section [{name}] must be a table.")

    url = connection_url(name, section)
    selected_database = database or _optional_string(section.get("default_database"))
    connector = load_connector(name)
    return connector.probe(ProbeRequest(url=url, database=selected_database))


def discover_catalog_use_case(
    name: str,
    *,
    config_path: Path | None = None,
    database: str | None = None,
    namespace: str | None = None,
) -> CatalogResult:
    config = read_config(config_path)
    section = config.get(name, {})
    if not isinstance(section, dict):
        raise ConnectorFailure("invalid_config", f"Configuration section [{name}] must be a table.")

    url = connection_url(name, section)
    selected_database = database or _optional_string(section.get("default_database"))
    connector = load_connector(name)
    return connector.discover_catalog(
        CatalogRequest(url=url, database=selected_database, namespace=namespace)
    )


def sample_connector_use_case(
    name: str,
    *,
    config_path: Path | None,
    database: str | None,
    namespace: str,
    object_name: str,
    limit: int,
) -> SampleResult:
    config = read_config(config_path)
    section = config.get(name, {})
    if not isinstance(section, dict):
        raise ConnectorFailure("invalid_config", f"Configuration section [{name}] must be a table.")
    url = connection_url(name, section)
    selected_database = database or _optional_string(section.get("default_database"))
    connector = load_connector(name)
    return connector.sample_rows(
        SampleRequest(
            url=url,
            database=selected_database,
            namespace=namespace,
            object_name=object_name,
            limit=limit,
        )
    )


def profile_connector_use_case(
    name: str,
    *,
    config_path: Path | None,
    database: str | None,
    namespace: str,
    object_name: str,
    row_limit: int,
    small_domain_limit: int = 20,
    include_values: bool = False,
) -> ObjectProfileResult:
    config = read_config(config_path)
    section = config.get(name, {})
    if not isinstance(section, dict):
        raise ConnectorFailure("invalid_config", f"Configuration section [{name}] must be a table.")
    url = connection_url(name, section)
    selected_database = database or _optional_string(section.get("default_database"))
    connector = load_connector(name)
    if "profile_object" not in connector.manifest.capabilities or not hasattr(
        connector, "profile_object"
    ):
        raise ConnectorFailure(
            "unsupported_capability",
            f"Connector {name} does not support object profiles.",
        )
    profiler = cast(ObjectProfileConnector, connector)
    return profiler.profile_object(
        ObjectProfileRequest(
            url=url,
            database=selected_database,
            namespace=namespace,
            object_name=object_name,
            row_limit=row_limit,
            small_domain_limit=small_domain_limit,
            include_values=include_values,
        )
    )


def scaffold_connector_use_case(name: str, *, output: Path | None = None) -> ScaffoldResult:
    return scaffold_connector(name, output=output)


def read_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        with path.expanduser().open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConnectorFailure("config_not_found", f"Configuration file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConnectorFailure(
            "invalid_config",
            f"Configuration file is not valid TOML: {path}",
        ) from exc
    return data


def connection_url(name: str, section: dict[str, Any]) -> str:
    env_name = f"TAREL_{name.upper()}_URL"
    value = os.getenv(env_name) or section.get("url")
    if not isinstance(value, str) or not value.strip():
        raise ConnectorFailure(
            "missing_config",
            f"No connection URL configured. Set {env_name} or [{name}].url in --config.",
        )
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConnectorFailure("invalid_config", "default_database must be a string.")
    return value.strip() or None
