"""Load, enrich, and query the TAREL Hub catalog without importing plugin code."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

from tarel import __version__
from tarel.hub.contracts import HubEntryPoint, HubExtension, HubFailure

DEFAULT_HUB_CATALOG_URL = (
    "https://raw.githubusercontent.com/mpsgitai/tarel-hub/main/catalog/catalog.json"
)
HUB_URL_ENV_VAR = "TAREL_HUB_URL"
_SNAPSHOT_PATH = Path(__file__).resolve().parent / "catalog_snapshot.json"
_MAX_CATALOG_BYTES = 1_048_576
_FETCH_TIMEOUT_SECONDS = 5.0
_BUILTIN_CONNECTORS = frozenset({"sqlite", "sqlserver"})

_CONFIG_TEMPLATES: dict[str, str] = {
    "connector-postgres": (
        '[source]\n'
        'url = "${TAREL_POSTGRES_URL}"\n'
        '# Or omit url and rely on libpq environment variables / pgpass / SSPI / GSSAPI.\n'
        '# Optional: schema = "public"\n'
    ),
    "connector-mysql": (
        '[source]\n'
        'url = "${TAREL_MYSQL_URL}"\n'
        '# Example: mysql://readonly_user:password@127.0.0.1:3306/analytics\n'
    ),
    "connector-clickhouse": (
        '[source]\n'
        'url = "${TAREL_CLICKHOUSE_URL}"\n'
        '# Example: clickhouse+http://readonly_user:password@127.0.0.1:8123/default\n'
    ),
    "connector-oracle": (
        '[source]\n'
        'url = "${TAREL_ORACLE_URL}"\n'
        '# Example: oracle://readonly_user:password@127.0.0.1:1521/FREEPDB1\n'
    ),
    "connector-duckdb": (
        '[source]\n'
        'path = "./warehouse.duckdb"\n'
        '# Opened read-only with external access disabled (trusted local files only).\n'
    ),
    "connector-mongodb": (
        '[source]\n'
        'url = "${TAREL_MONGODB_URL}"\n'
        '# Example: mongodb://readonly_user:password@127.0.0.1:27017/analytics\n'
    ),
    "connector-sqlserver": (
        '[source]\n'
        'server = "127.0.0.1"\n'
        'port = 1433\n'
        'database = "analytics"\n'
        '# Provide user/password or use Windows integrated auth where supported.\n'
    ),
    "lineage-sqlglot": (
        "# No source.toml required. Once installed, TAREL discovers `sqlglot` automatically:\n"
        "#   tarel lineage analyze --sql-dir ./models --dialect postgres --format json\n"
    ),
    "retrieval-llamacpp": (
        "# No source.toml required. Download pinned GGUF models explicitly after install:\n"
        "#   tarel model list\n"
        "#   tarel model download <model-name>\n"
    ),
}


def config_template_for_extension(extension_id: str) -> str | None:
    """Return a minimal safe configuration or usage template for one Hub extension."""
    return _CONFIG_TEMPLATES.get(extension_id)


def load_hub_catalog(
    *,
    hub_url: str | None = None,
    offline: bool = False,
) -> tuple[HubExtension, ...]:
    """Load the TAREL Hub catalog and enrich each entry with local host status."""
    raw_payload, source = _load_raw_catalog(hub_url=hub_url, offline=offline)
    raw_extensions = raw_payload.get("extensions")
    if not isinstance(raw_extensions, list):
        raise HubFailure("invalid_hub_catalog", "Hub catalog JSON must contain an extensions list.")
    installed_eps = _installed_entry_point_keys()
    extensions: list[HubExtension] = []
    for item in raw_extensions:
        if not isinstance(item, dict):
            raise HubFailure(
                "invalid_hub_catalog",
                "Hub catalog extension entry must be an object.",
            )
        ext_id = str(item.get("id", "")).strip()
        parsed_eps = _extract_entry_points(item)
        status = str(item.get("status", "")).strip()
        installed = _is_installed(
            status=status,
            entry_points_list=parsed_eps,
            installed=installed_eps,
        )
        compatible = is_compatible_with_host(
            str(item["host_versions"]) if item.get("host_versions") is not None else None,
            __version__,
        )
        extensions.append(
            HubExtension.from_dict(
                item,
                installed=installed,
                compatible=compatible,
                config_template=config_template_for_extension(ext_id),
                catalog_source=source,
            )
        )
    return tuple(extensions)


def load_bundled_hub_catalog() -> tuple[HubExtension, ...]:
    """Load the bundled offline Hub snapshot without touching the network."""
    return load_hub_catalog(offline=True)


def resolve_hub_extension(
    identifier: str,
    extensions: tuple[HubExtension, ...],
) -> HubExtension:
    """Resolve an extension by id, package name, or entry-point name."""
    needle = identifier.strip().lower()
    if not needle:
        raise HubFailure("unknown_hub_extension", "Hub extension name must not be empty.")
    for ext in extensions:
        if ext.id.lower() == needle:
            return ext
    for ext in extensions:
        if ext.package and ext.package.lower() == needle:
            return ext
    ep_matches = [
        ext for ext in extensions if any(ep.name.lower() == needle for ep in ext.entry_points)
    ]
    if len(ep_matches) == 1:
        return ep_matches[0]
    if len(ep_matches) > 1:
        names = ", ".join(ext.id for ext in ep_matches)
        raise HubFailure(
            "unknown_hub_extension",
            f"Ambiguous Hub extension {identifier!r}; specify one of: {names}.",
        )
    raise HubFailure(
        "unknown_hub_extension",
        f"Unknown TAREL Hub extension: {identifier}. "
        "Run `tarel hub list` to see available packages.",
    )


def hub_hint_for_entry_point(group: str, name: str) -> tuple[str, str] | None:
    """Return ``(extension_id, install_command)`` from the bundled snapshot, or ``None``."""
    needle = name.strip().lower()
    if not needle:
        return None
    for ext in load_bundled_hub_catalog():
        if ext.status == "planned":
            continue
        if any(ep.group == group and ep.name.lower() == needle for ep in ext.entry_points):
            cmd = ext.recommended_cli_install
            if cmd:
                return (ext.id, cmd)
    return None


def is_compatible_with_host(host_versions: str | None, host_version: str) -> bool:
    """Check simple PEP 440 range specifiers such as ``tarel>=0.0.6,<0.1``."""
    if not host_versions:
        return True
    cleaned = host_versions.strip()
    if cleaned.lower().startswith("part of"):
        return True
    if cleaned.lower().startswith("tarel"):
        cleaned = cleaned[len("tarel") :].strip()
    current = _parse_version_tuple(host_version)
    if current is None:
        return True
    for clause in cleaned.split(","):
        spec = clause.strip()
        if not spec:
            continue
        match = re.match(r"^(>=|<=|==|!=|>|<)\s*([0-9]+(?:\.[0-9]+)*)$", spec)
        if match is None:
            continue
        operator, raw_target = match.groups()
        target = _parse_version_tuple(raw_target)
        if target is None:
            continue
        if not _compare_versions(current, operator, target):
            return False
    return True


def _load_raw_catalog(
    *,
    hub_url: str | None,
    offline: bool,
) -> tuple[dict[str, Any], str]:
    if offline:
        return _read_bundled_snapshot(), "bundled_snapshot"
    explicit_url = hub_url or os.environ.get(HUB_URL_ENV_VAR)
    target_url = explicit_url.strip() if explicit_url else DEFAULT_HUB_CATALOG_URL
    try:
        payload = _fetch_catalog_json(target_url)
    except HubFailure:
        if explicit_url:
            raise
        return _read_bundled_snapshot(), "bundled_snapshot"
    return payload, target_url


def _read_bundled_snapshot() -> dict[str, Any]:
    try:
        data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HubFailure(
            "invalid_hub_catalog",
            "Bundled Hub catalog snapshot is unreadable.",
        ) from exc
    if not isinstance(data, dict):
        raise HubFailure(
            "invalid_hub_catalog",
            "Bundled Hub catalog snapshot must be a JSON object.",
        )
    return data


def _fetch_catalog_json(target: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme in ("", "file"):
        local_path = (
            Path(urllib.parse.unquote(parsed.path))
            if parsed.scheme == "file"
            else Path(target)
        )
        try:
            raw = local_path.read_bytes()
        except OSError as exc:
            raise HubFailure(
                "hub_fetch_failed",
                f"Could not read Hub catalog file: {target}",
            ) from exc
    elif parsed.scheme in ("https", "http"):
        request = urllib.request.Request(
            target,
            headers={"Accept": "application/json", "User-Agent": f"tarel/{__version__}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
                raw = response.read(_MAX_CATALOG_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HubFailure(
                "hub_fetch_failed",
                f"Could not fetch TAREL Hub catalog from {target}. "
                "Use --offline for the bundled snapshot.",
            ) from exc
        if len(raw) > _MAX_CATALOG_BYTES:
            raise HubFailure("invalid_hub_catalog", "Hub catalog response exceeds maximum size.")
    else:
        raise HubFailure(
            "hub_fetch_failed",
            f"Unsupported Hub catalog URL scheme: {parsed.scheme!r}.",
        )
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HubFailure(
            "invalid_hub_catalog",
            f"Hub catalog at {target} is not valid JSON.",
        ) from exc
    if not isinstance(data, dict):
        raise HubFailure("invalid_hub_catalog", "Hub catalog JSON must be an object.")
    return data


def _installed_entry_point_keys() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for group in (
        "tarel.connectors",
        "tarel.lineage_analyzers",
        "tarel.embeddings",
        "tarel.rerankers",
    ):
        for ep in entry_points().select(group=group):
            found.add((group, ep.name))
    return found


def _extract_entry_points(item: dict[str, Any]) -> tuple[HubEntryPoint, ...]:
    raw_eps = item.get("entry_points")
    if isinstance(raw_eps, list):
        return tuple(HubEntryPoint.from_dict(ep) for ep in raw_eps if isinstance(ep, dict))
    if isinstance(item.get("entry_point"), dict):
        return (HubEntryPoint.from_dict(item["entry_point"]),)
    return ()


def _is_installed(
    *,
    status: str,
    entry_points_list: tuple[HubEntryPoint, ...],
    installed: set[tuple[str, str]],
) -> bool:
    if status == "planned" or not entry_points_list:
        return False
    if status == "builtin":
        return all(ep.name in _BUILTIN_CONNECTORS for ep in entry_points_list)
    return all((ep.group, ep.name) in installed for ep in entry_points_list)


def _parse_version_tuple(raw: str) -> tuple[int, ...] | None:
    match = re.match(r"^([0-9]+(?:\.[0-9]+)*)", raw.strip())
    if match is None:
        return None
    parts = [int(piece) for piece in match.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _compare_versions(left: tuple[int, ...], operator: str, right: tuple[int, ...]) -> bool:
    if operator == ">=":
        return left >= right
    if operator == "<=":
        return left <= right
    if operator == ">":
        return left > right
    if operator == "<":
        return left < right
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    return True
