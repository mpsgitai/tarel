"""Static, read-only project scanner that suggests relevant TAREL Hub extensions."""

from __future__ import annotations

import os
import re
from pathlib import Path

from tarel.hub.contracts import HubExtension, HubSuggestion

_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tarel",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)
_MAX_DEPTH = 4
_MAX_FILES = 500
_MAX_FILE_BYTES = 65_536

_TEXT_INSPECT_NAMES = frozenset(
    {
        ".env.example",
        ".env.sample",
        ".env.template",
        "compose.yaml",
        "compose.yml",
        "dbt_project.yml",
        "docker-compose.yaml",
        "docker-compose.yml",
        "profiles.yml",
        "pyproject.toml",
        "requirements.txt",
    }
)

_ENV_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("connector-postgres", ("PGHOST", "PGDATABASE", "POSTGRES_URL", "TAREL_POSTGRES_URL")),
    ("connector-mysql", ("MYSQL_HOST", "MYSQL_URL", "TAREL_MYSQL_URL")),
    ("connector-clickhouse", ("CLICKHOUSE_HOST", "CLICKHOUSE_URL", "TAREL_CLICKHOUSE_URL")),
    ("connector-oracle", ("ORACLE_DSN", "ORACLE_URL", "TAREL_ORACLE_URL")),
    ("connector-mongodb", ("MONGODB_URI", "MONGODB_URL", "TAREL_MONGODB_URL")),
)

_CONTENT_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "connector-postgres",
        re.compile(
            r"(?:postgres(?:ql)?://|\bpsycopg\b|\btype:\s*postgres\b|\bpostgres:)",
            re.IGNORECASE,
        ),
        "PostgreSQL reference",
    ),
    (
        "connector-mysql",
        re.compile(
            r"\b(mysql://|mariadb://|pymysql|type:\s*mysql|mysql:|mariadb:)\b",
            re.IGNORECASE,
        ),
        "MySQL/MariaDB reference",
    ),
    (
        "connector-clickhouse",
        re.compile(
            r"\b(clickhouse(\+https?)?://|clickhouse-connect|type:\s*clickhouse|clickhouse/)\b",
            re.IGNORECASE,
        ),
        "ClickHouse reference",
    ),
    (
        "connector-oracle",
        re.compile(r"\b(oracle://|oracledb|type:\s*oracle|gvenzl/oracle)\b", re.IGNORECASE),
        "Oracle reference",
    ),
    (
        "connector-mongodb",
        re.compile(r"\b(mongodb(\+srv)?://|pymongo|image:\s*mongo)\b", re.IGNORECASE),
        "MongoDB reference",
    ),
    (
        "connector-duckdb",
        re.compile(r"\b(duckdb|type:\s*duckdb)\b", re.IGNORECASE),
        "DuckDB reference",
    ),
)


def suggest_hub_extensions(
    root: Path,
    extensions: tuple[HubExtension, ...],
) -> tuple[HubSuggestion, ...]:
    """Inspect a workspace directory and env variable names without executing code."""
    resolved = root.resolve()
    reasons_by_id: dict[str, list[str]] = {}
    confidence_by_id: dict[str, str] = {}

    def record(ext_id: str, reason: str, confidence: str) -> None:
        bucket = reasons_by_id.setdefault(ext_id, [])
        if reason not in bucket and len(bucket) < 5:
            bucket.append(reason)
        if confidence == "high" or ext_id not in confidence_by_id:
            confidence_by_id[ext_id] = confidence

    sql_files = 0
    for file_path in _iter_bounded_files(resolved):
        rel = file_path.relative_to(resolved).as_posix()
        suffix = file_path.suffix.lower()
        name_lower = file_path.name.lower()
        if suffix in (".duckdb", ".ddb"):
            record("connector-duckdb", f"Found DuckDB database file: {rel}", "high")
        if suffix == ".sql":
            sql_files += 1
            if sql_files == 1:
                record("lineage-sqlglot", f"Found SQL files (for example {rel})", "medium")
        if name_lower == "dbt_project.yml":
            record("lineage-sqlglot", f"Found dbt project file: {rel}", "high")
        if name_lower in _TEXT_INSPECT_NAMES or (
            name_lower.startswith("requirements") and suffix == ".txt"
        ):
            text = _read_bounded_text(file_path)
            if not text:
                continue
            for ext_id, pattern, label in _CONTENT_PATTERNS:
                if pattern.search(text):
                    record(ext_id, f"{label} in {rel}", "high")

    # Inspect only environment variable NAMES, never values.
    env_names = set(os.environ)
    for ext_id, var_names in _ENV_HINTS:
        present = [var for var in var_names if var in env_names]
        if present:
            record(ext_id, f"Environment variable set: {', '.join(present)}", "high")

    by_id = {ext.id: ext for ext in extensions}
    suggestions: list[HubSuggestion] = []
    for ext_id, reasons in reasons_by_id.items():
        ext = by_id.get(ext_id)
        if ext is None or ext.status == "planned":
            continue
        suggestions.append(
            HubSuggestion(
                extension_id=ext.id,
                kind=ext.kind,
                package=ext.package,
                installed=ext.installed,
                confidence=confidence_by_id.get(ext_id, "medium"),
                reasons=tuple(reasons),
                install_command=ext.recommended_cli_install,
            )
        )
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(
        key=lambda item: (
            item.installed,
            confidence_rank.get(item.confidence, 9),
            item.extension_id,
        )
    )
    return tuple(suggestions)


def _iter_bounded_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    found: list[Path] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack and len(found) < _MAX_FILES:
        current, depth = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        for entry in entries:
            if len(found) >= _MAX_FILES:
                break
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in _SKIP_DIRS or depth >= _MAX_DEPTH:
                    continue
                stack.append((entry, depth + 1))
            elif entry.is_file():
                found.append(entry)
    return found


def _read_bounded_text(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_FILE_BYTES)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="ignore")
