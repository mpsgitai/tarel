"""Connector use cases: check, probe, discover, sample and profile a configured source."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from tarel.connectors.authoring import ScaffoldResult, scaffold_connector
from tarel.connectors.contracts import (
    CatalogRequest,
    CatalogResult,
    Connector,
    ConnectorCheck,
    ConnectorFailure,
    Credential,
    ObjectProfileConnector,
    ObjectProfileRequest,
    ObjectProfileResult,
    ProbeRequest,
    ProbeResult,
    SampleRequest,
    SampleResult,
)
from tarel.connectors.credentials import resolve_credential
from tarel.connectors.host import check_connector, list_connectors, load_connector


def list_connectors_use_case() -> tuple[ConnectorCheck, ...]:
    return list_connectors()


def check_connector_use_case(name: str) -> ConnectorCheck:
    return check_connector(name)


@dataclass(frozen=True, slots=True)
class ConfiguredConnector:
    """A loaded connector with its resolved target; URL and login never appear in repr."""

    connector: Connector
    url: str = field(repr=False)
    database: str | None
    credential: Credential | None = field(repr=False)


def configured_connector(
    name: str,
    *,
    config_path: Path | None,
    database: str | None = None,
) -> ConfiguredConnector:
    config = read_config(config_path)
    section = config.get(name, {})
    if not isinstance(section, dict):
        raise ConnectorFailure("invalid_config", f"Configuration section [{name}] must be a table.")
    url = connection_url(name, section)
    selected_database = database or _optional_string(section.get("default_database"))
    connector = load_connector(name)
    config_dir = config_path.expanduser().resolve().parent if config_path is not None else None
    credential = resolve_credential(name, section, connector.manifest, config_dir=config_dir)
    return ConfiguredConnector(connector, url, selected_database, credential)


def probe_connector_use_case(
    name: str,
    *,
    config_path: Path | None = None,
    database: str | None = None,
) -> ProbeResult:
    source = configured_connector(name, config_path=config_path, database=database)
    return source.connector.probe(
        ProbeRequest(url=source.url, database=source.database, credential=source.credential)
    )


def discover_catalog_use_case(
    name: str,
    *,
    config_path: Path | None = None,
    database: str | None = None,
    namespace: str | None = None,
) -> CatalogResult:
    source = configured_connector(name, config_path=config_path, database=database)
    return source.connector.discover_catalog(
        CatalogRequest(
            url=source.url,
            database=source.database,
            namespace=namespace,
            credential=source.credential,
        )
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
    source = configured_connector(name, config_path=config_path, database=database)
    return source.connector.sample_rows(
        SampleRequest(
            url=source.url,
            database=source.database,
            namespace=namespace,
            object_name=object_name,
            limit=limit,
            credential=source.credential,
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
    source = configured_connector(name, config_path=config_path, database=database)
    connector = source.connector
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
            url=source.url,
            database=source.database,
            namespace=namespace,
            object_name=object_name,
            row_limit=row_limit,
            small_domain_limit=small_domain_limit,
            include_values=include_values,
            credential=source.credential,
        )
    )


def scaffold_connector_use_case(name: str, *, output: Path | None = None) -> ScaffoldResult:
    return scaffold_connector(name, output=output)


def _looks_like_url_or_secret_path(raw: str) -> bool:
    return "://" in raw or (":/" in raw and "@" in raw)


def read_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    raw = str(path)
    if _looks_like_url_or_secret_path(raw):
        raise ConnectorFailure(
            "config_not_found",
            "Configuration file not found: value looks like a connection URL, "
            "expected a TOML file path.",
        )
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
