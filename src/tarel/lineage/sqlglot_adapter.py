"""Optional SQLGlot adapter for conservative, write-centred static lineage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tarel.lineage.contracts import LineageFailure
from tarel.lineage.coverage import WriteMarker, write_markers
from tarel.lineage.source import SourceDefinition

_ADAPTER_VERSION = "tarel.sqlglot-lineage.v0.2"
_DIALECT_ALIASES = {
    "duckdb": "duckdb",
    "postgres": "postgres",
    "postgresql": "postgres",
    "sqlite": "sqlite",
    "sqlserver": "tsql",
    "t-sql": "tsql",
    "tsql": "tsql",
}


@dataclass(frozen=True, slots=True)
class SqlglotAnalysisResult:
    status: str
    dialect: str | None
    sqlglot_version: str
    adapter_version: str
    analysis: dict[str, object] | None = None
    failure_code: str | None = None

    @property
    def complete(self) -> bool:
        return self.status == "complete"


@dataclass(frozen=True, slots=True)
class _Source:
    target: str
    line_start: int
    line_end: int
    via: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Write:
    operation: str
    marker: WriteMarker
    expression: Any
    target_table: Any
    target: str
    target_line_end: int


def analyze_with_sqlglot(
    definition: SourceDefinition,
    *,
    dialect: str | None = None,
) -> SqlglotAnalysisResult:
    """Return a complete TAREL workfile or a sanitized unsupported result."""
    try:
        import sqlglot
        from sqlglot import exp
        from sqlglot.errors import ParseError
    except ImportError as exc:
        raise LineageFailure(
            "sqlglot_not_installed",
            "SQLGlot lineage requires the optional `tarel[sql-lineage]` extra.",
        ) from exc

    resolved = _resolve_dialect(dialect or definition.language)
    if resolved is None:
        return _unsupported(sqlglot.__version__, None, "sqlglot_unsupported_dialect")

    try:
        expressions = tuple(
            item for item in sqlglot.parse(definition.content, dialect=resolved) if item is not None
        )
    except ParseError:
        return _unsupported(sqlglot.__version__, resolved, "sqlglot_parse_error")
    except Exception as exc:  # SQLGlot plugins can expose adapter-specific parser failures.
        if exc.__class__.__module__.startswith("sqlglot"):
            return _unsupported(sqlglot.__version__, resolved, "sqlglot_parse_error")
        raise

    if any(
        isinstance(node, exp.Command) for expression in expressions for node in expression.walk()
    ):
        return _unsupported(sqlglot.__version__, resolved, "sqlglot_unsupported_statement")
    if any(
        _is_dynamic_execute(node, exp)
        for expression in expressions
        for node in expression.walk()
    ):
        return _unsupported(sqlglot.__version__, resolved, "sqlglot_dynamic_sql")
    if any(
        _is_create_as(node, exp)
        for expression in expressions
        for node in expression.walk()
    ):
        return _unsupported(sqlglot.__version__, resolved, "sqlglot_unsupported_create_as")

    markers = write_markers(definition.content)
    candidates = tuple(
        node
        for expression in expressions
        for node in expression.walk()
        if _is_write(node, exp) and not _has_write_ancestor(node, exp)
    )
    writes = _match_writes(candidates, markers, exp)
    if writes is None:
        return _unsupported(sqlglot.__version__, resolved, "sqlglot_incomplete_write_coverage")

    local_sources: dict[str, tuple[_Source, ...]] = {}
    workfile_writes: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for write in writes:
        sources = _write_sources(write, local_sources, exp)
        if sources is None:
            return _unsupported(sqlglot.__version__, resolved, "sqlglot_unresolved_source")
        if _is_local(write.target):
            local_sources[write.target.casefold()] = (
                ()
                if write.operation == "truncate"
                else _merge_sources(
                    (*local_sources.get(write.target.casefold(), ()), *sources)
                )
            )
            excluded.append(
                {
                    "disposition": "local_intermediate",
                    "line_end": write.target_line_end,
                    "line_start": write.marker.line,
                    "operation": write.operation,
                    "reason": "SQLGlot identified a local intermediate write.",
                    "target": write.target,
                }
            )
            continue
        workfile_writes.append(
            {
                "line_end": write.target_line_end,
                "line_start": write.marker.line,
                "operation": write.operation,
                "reason": "SQLGlot identified the persistent write target.",
                "sources": [_source_payload(item) for item in sources],
                "target": write.target,
                "warnings": [],
            }
        )

    observations = _observations(expressions, candidates, local_sources, exp)
    if observations is None:
        return _unsupported(sqlglot.__version__, resolved, "sqlglot_unresolved_source")
    return SqlglotAnalysisResult(
        status="complete",
        dialect=resolved,
        sqlglot_version=sqlglot.__version__,
        adapter_version=_ADAPTER_VERSION,
        analysis={
            "excluded_writes": excluded,
            "observations": observations,
            "summary": (
                f"SQLGlot {sqlglot.__version__} statically analyzed this definition as "
                f"{resolved}; TAREL validated complete write coverage."
            ),
            "warnings": [],
            "writes": workfile_writes,
        },
    )


def _resolve_dialect(value: str) -> str | None:
    return _DIALECT_ALIASES.get(value.strip().casefold())


def _is_dynamic_execute(node: Any, exp: Any) -> bool:
    if not isinstance(node, exp.Execute):
        return False
    if not isinstance(node.this, exp.Table):
        return True
    return _table_name(node.this).casefold().split(".")[-1] == "sp_executesql"


def _is_create_as(node: Any, exp: Any) -> bool:
    return (
        isinstance(node, exp.Create)
        and str(node.args.get("kind", "")).casefold() == "table"
        and node.args.get("expression") is not None
    )


def _unsupported(version: str, dialect: str | None, code: str) -> SqlglotAnalysisResult:
    return SqlglotAnalysisResult(
        status="unsupported",
        dialect=dialect,
        sqlglot_version=version,
        adapter_version=_ADAPTER_VERSION,
        failure_code=code,
    )


def _is_write(node: Any, exp: Any) -> bool:
    if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.TruncateTable)):
        return True
    return isinstance(node, exp.Select) and node.args.get("into") is not None


def _has_write_ancestor(node: Any, exp: Any) -> bool:
    parent = node.parent
    while parent is not None:
        if _is_write(parent, exp):
            return True
        parent = parent.parent
    return False


def _match_writes(
    expressions: tuple[Any, ...],
    markers: tuple[WriteMarker, ...],
    exp: Any,
) -> tuple[_Write, ...] | None:
    remaining = list(markers)
    matched: list[_Write] = []
    for expression in expressions:
        operation = _operation(expression, exp)
        target_table = _target_table(expression, operation, exp)
        if target_table is None:
            return None
        target = _table_name(target_table)
        target_lines = _table_lines(target_table)
        if not target or target_lines is None:
            return None
        candidates = [item for item in remaining if item.operation == operation]
        if not candidates:
            return None
        preceding = [item for item in candidates if item.line <= target_lines[1]]
        marker = max(preceding, key=lambda item: item.line) if preceding else candidates[0]
        remaining.remove(marker)
        matched.append(
            _Write(
                operation=operation,
                marker=marker,
                expression=expression,
                target_table=target_table,
                target=target,
                target_line_end=max(marker.line, target_lines[1]),
            )
        )
    if remaining:
        return None
    return tuple(sorted(matched, key=lambda item: (item.marker.line, item.operation)))


def _operation(expression: Any, exp: Any) -> str:
    if isinstance(expression, exp.Select):
        return "select_into"
    for expression_type, operation in (
        (exp.Delete, "delete"),
        (exp.Insert, "insert"),
        (exp.Merge, "merge"),
        (exp.TruncateTable, "truncate"),
        (exp.Update, "update"),
    ):
        if isinstance(expression, expression_type):
            return operation
    raise AssertionError("unsupported SQLGlot write expression")


def _target_table(expression: Any, operation: str, exp: Any) -> Any | None:
    if operation == "truncate":
        tables = expression.args.get("expressions") or ()
        return tables[0] if len(tables) == 1 and isinstance(tables[0], exp.Table) else None
    if operation == "select_into":
        into = expression.args.get("into")
        return into.this if into is not None and isinstance(into.this, exp.Table) else None
    raw = expression.this
    if isinstance(raw, exp.Schema):
        raw = raw.this
    if operation == "delete" and expression.args.get("tables"):
        raw = expression.args["tables"][0]
    if not isinstance(raw, exp.Table):
        return None
    if _is_qualified(raw) or _is_local(_table_name(raw)):
        return raw
    alias = raw.alias_or_name.casefold()
    matches = [
        table
        for table in expression.find_all(exp.Table)
        if table is not raw
        and table.alias_or_name.casefold() == alias
        and (_is_qualified(table) or _is_local(_table_name(table)))
    ]
    return matches[0] if len(matches) == 1 else raw


def _write_sources(
    write: _Write,
    local_sources: dict[str, tuple[_Source, ...]],
    exp: Any,
) -> tuple[_Source, ...] | None:
    sources: list[_Source] = []
    for table in _reachable_tables(write.expression, exp):
        if _is_write_target_table(write, table, exp):
            continue
        target = _table_name(table)
        if not target:
            return None
        via = _cte_ancestors(table, exp)
        if _is_local(target):
            expanded = local_sources.get(target.casefold())
            if expanded is None:
                return None
            sources.extend(
                _Source(item.target, item.line_start, item.line_end, (*via, target, *item.via))
                for item in expanded
            )
            continue
        lines = _table_lines(table)
        if lines is None:
            return None
        sources.append(_Source(target, lines[0], lines[1], via))
    return _merge_sources(tuple(sources))


def _reachable_tables(expression: Any, exp: Any) -> tuple[Any, ...]:
    ctes = {
        cte.alias_or_name.casefold(): cte
        for cte in expression.find_all(exp.CTE)
        if cte.alias_or_name
    }
    expanded_ctes: set[str] = set()
    tables: list[Any] = []

    def visit(node: Any) -> None:
        if isinstance(node, exp.CTE):
            return
        if isinstance(node, exp.Table):
            target = _table_name(node)
            key = target.casefold()
            cte = ctes.get(key) if not _is_qualified(node) else None
            if cte is not None:
                if key not in expanded_ctes:
                    expanded_ctes.add(key)
                    visit(cte.this)
            else:
                tables.append(node)
            for child in node.iter_expressions():
                visit(child)
            return
        for child in node.iter_expressions():
            visit(child)

    visit(expression)
    return tuple(tables)


def _is_write_target_table(write: _Write, table: Any, exp: Any) -> bool:
    if table is write.target_table:
        return True
    expression = write.expression
    candidates: tuple[Any, ...]
    if write.operation == "truncate":
        candidates = tuple(expression.args.get("expressions") or ())
    elif write.operation == "select_into":
        into = expression.args.get("into")
        candidates = (into.this,) if into is not None else ()
    elif write.operation == "delete" and expression.args.get("tables"):
        candidates = tuple(expression.args["tables"])
    else:
        raw = expression.this
        candidates = (raw.this if isinstance(raw, exp.Schema) else raw,)
    return any(table is candidate for candidate in candidates)


def _observations(
    expressions: tuple[Any, ...],
    writes: tuple[Any, ...],
    local_sources: dict[str, tuple[_Source, ...]],
    exp: Any,
) -> list[dict[str, object]] | None:
    write_ids = {id(item) for item in writes}
    observations: list[dict[str, object]] = []
    seen: set[tuple[str, str, int]] = set()
    for expression in expressions:
        for execute in expression.find_all(exp.Execute):
            if not isinstance(execute.this, exp.Table):
                return None
            target = _table_name(execute.this)
            lines = _table_lines(execute.this)
            if not target or lines is None:
                return None
            _append_observation(observations, seen, "call", target, lines)
        cte_names = {
            cte.alias_or_name.casefold()
            for cte in expression.find_all(exp.CTE)
            if cte.alias_or_name
        }
        for table in expression.find_all(exp.Table):
            if _inside_write(table, write_ids):
                continue
            if _is_definition_target(table, exp):
                continue
            if isinstance(table.parent, exp.Execute):
                continue
            target = _table_name(table)
            if not target:
                return None
            if not _is_qualified(table) and target.casefold() in cte_names:
                continue
            lines = _table_lines(table)
            if lines is None:
                return None
            if _is_local(target):
                expanded = local_sources.get(target.casefold())
                if not expanded:
                    return None
                for source in expanded:
                    _append_observation(
                        observations,
                        seen,
                        "read",
                        source.target,
                        (source.line_start, source.line_end),
                    )
                continue
            _append_observation(observations, seen, "read", target, lines)
    return observations


def _inside_write(node: Any, write_ids: set[int]) -> bool:
    parent = node.parent
    while parent is not None:
        if id(parent) in write_ids:
            return True
        parent = parent.parent
    return False


def _is_definition_target(table: Any, exp: Any) -> bool:
    parent = table.parent
    if isinstance(parent, exp.Create) and parent.this is table:
        return True
    stored_procedure = getattr(exp, "StoredProcedure", None)
    return stored_procedure is not None and isinstance(parent, stored_procedure)


def _append_observation(
    result: list[dict[str, object]],
    seen: set[tuple[str, str, int]],
    operation: str,
    target: str,
    lines: tuple[int, int],
) -> None:
    key = (operation, target.casefold(), lines[0])
    if key in seen:
        return
    seen.add(key)
    result.append(
        {
            "line_end": lines[1],
            "line_start": lines[0],
            "operation": operation,
            "reason": f"SQLGlot identified a physical {operation} reference.",
            "target": target,
        }
    )


def _source_payload(source: _Source) -> dict[str, object]:
    return {
        "line_end": source.line_end,
        "line_start": source.line_start,
        "reason": "SQLGlot identified a physical source dependency.",
        "role": "unknown",
        "target": source.target,
        "via": list(source.via),
    }


def _merge_sources(sources: tuple[_Source, ...]) -> tuple[_Source, ...]:
    unique: dict[tuple[str, tuple[str, ...]], _Source] = {}
    for source in sources:
        unique.setdefault((source.target.casefold(), source.via), source)
    return tuple(
        sorted(
            unique.values(), key=lambda item: (item.target.casefold(), item.via, item.line_start)
        )
    )


def _cte_ancestors(table: Any, exp: Any) -> tuple[str, ...]:
    names: list[str] = []
    parent = table.parent
    while parent is not None:
        if isinstance(parent, exp.CTE) and parent.alias_or_name:
            names.append(parent.alias_or_name)
        parent = parent.parent
    return tuple(reversed(names))


def _table_name(table: Any) -> str:
    parts = [part.name for part in table.parts if getattr(part, "name", "")]
    if not parts:
        return ""
    if table.this.args.get("temporary") and not parts[-1].startswith(("#", "@")):
        parts[-1] = f"#{parts[-1]}"
    return ".".join(parts)


def _is_qualified(table: Any) -> bool:
    return len(table.parts) > 1


def _is_local(target: str) -> bool:
    return target.startswith(("#", "@"))


def _table_lines(table: Any) -> tuple[int, int] | None:
    lines = [part.meta.get("line") for part in table.parts]
    valid = [line for line in lines if isinstance(line, int) and not isinstance(line, bool)]
    return (min(valid), max(valid)) if valid else None
