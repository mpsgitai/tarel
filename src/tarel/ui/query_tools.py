"""Bounded read-only browser adapters for the existing search/context use cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tarel.application import (
    compile_context_use_case,
    compile_workspace_context_use_case,
    load_workspace_use_case,
    resolve_workspace_scope_use_case,
    search_graph_use_case,
    search_workspace_use_case,
)
from tarel.context_output import canonical_hash
from tarel.graph.store import FileGraphStore
from tarel.runtime import TarelRuntime

_SCOPE_NOTICE = (
    "Project scope only. Graph display filters, selected objects and report/cube "
    "filters do not constrain this search or context. No source queries or LLM calls."
)
_EXPECTED_KEYS = frozenset({"expected_revisions", "expected_scope_identity"})
_BUDGETS = {
    "seed_limit": (3, 1, 20),
    "max_objects": (10, 1, 50),
    "max_joins": (12, 0, 100),
    "max_hops": (2, 0, 4),
    "max_fields_per_object": (12, 1, 100),
    "max_characters": (24_000, 1_000, 100_000),
}


class UIQueryFailure(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class UIQueryScope:
    """Server-owned launch selection, never constructed from a browser request."""

    graph: str | None = None
    workspace: str | None = None
    systems: tuple[str, ...] = ()
    graphs: tuple[str, ...] = ()
    areas: tuple[str, ...] = ()
    schemas: tuple[str, ...] = ()
    zones: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if bool(self.graph) == bool(self.workspace):
            raise UIQueryFailure("invalid_query_scope", "Choose one project query scope.")
        if any(
            value is not None and (not isinstance(value, str) or not value.strip())
            for value in (self.graph, self.workspace)
        ):
            raise UIQueryFailure("invalid_query_scope", "Invalid project query scope.")
        for values in self.selectors().values():
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise UIQueryFailure("invalid_query_scope", "Invalid project query selectors.")
            if self.graph and values:
                raise UIQueryFailure(
                    "invalid_query_scope", "Query selectors require a workspace launch scope."
                )

    def selectors(self) -> dict[str, tuple[str, ...]]:
        return {
            "systems": self.systems, "graphs": self.graphs, "areas": self.areas,
            "schemas": self.schemas, "zones": self.zones,
        }


def query_scope_snapshot(
    scope: UIQueryScope, *, runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    """Expose exact source revisions without inventing a viewport selection contract."""
    if scope.workspace:
        resolved = resolve_workspace_scope_use_case(
            scope.workspace, **scope.selectors(), runtime=runtime,
        )
        names = resolved.graph_names
        selection: dict[str, object] = {
            "mode": "workspace", "workspace": scope.workspace,
            "selection": resolved.selection.to_dict(),
            "graphs": list(names), "scope_hash": resolved.scope_hash,
            "workspace_revision": canonical_hash(
                load_workspace_use_case(scope.workspace, runtime=runtime).to_dict()
            ),
        }
    else:
        assert scope.graph is not None
        names = (scope.graph,)
        selection = {"mode": "graph", "graph": scope.graph}
    store = runtime.graph_store() if runtime else FileGraphStore()
    revisions = {name: store.header(name).revision for name in names}
    return {
        "scope": selection,
        "revisions": revisions,
        "scope_identity": canonical_hash({"scope": selection, "revisions": revisions}),
        "notice": _SCOPE_NOTICE,
    }


def search_metadata(
    scope: UIQueryScope, payload: dict[str, Any], *, runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    _request_keys(payload, {"query", "limit", "family_mode"} | _EXPECTED_KEYS)
    query = _query(payload)
    limit = _integer(payload, "limit", default=20, minimum=1, maximum=100)
    family_mode = payload.get("family_mode", "confirmed_only")
    if family_mode not in ("confirmed_only", "include_candidates"):
        raise UIQueryFailure("invalid_query_policy", "Unsupported family search policy.")
    before = query_scope_snapshot(scope, runtime=runtime)
    _check_expected(payload, before, required=False)
    if scope.workspace:
        result = search_workspace_use_case(
            scope.workspace, query, **scope.selectors(),
            limit=limit, mode="lexical", family_mode=family_mode, runtime=runtime,
        )
    else:
        assert scope.graph is not None
        result = search_graph_use_case(
            scope.graph, query, limit=limit, mode="lexical", family_mode=family_mode,
            runtime=runtime,
        )
    _check_unchanged(scope, before, runtime)
    return {**before, "results": result.to_dict()}


def preview_context(
    scope: UIQueryScope, payload: dict[str, Any], *, runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    _request_keys(
        payload,
        {"query", "reviewed_annotations_only", "logical_hints"} | _EXPECTED_KEYS | _BUDGETS.keys(),
    )
    query = _query(payload)
    reviewed = payload.get("reviewed_annotations_only", True)
    if not isinstance(reviewed, bool):
        raise UIQueryFailure("invalid_query_policy", "Reviewed annotations must be a boolean.")
    logical_hints = payload.get("logical_hints")
    if logical_hints == "off":
        logical_hints = None
    if logical_hints not in (None, "confirmed_only", "include_candidates"):
        raise UIQueryFailure("invalid_query_policy", "Unsupported logical hint policy.")
    budgets = {
        name: _integer(payload, name, default=default, minimum=minimum, maximum=maximum)
        for name, (default, minimum, maximum) in _BUDGETS.items()
    }
    if budgets["seed_limit"] > budgets["max_objects"]:
        raise UIQueryFailure("invalid_query_budget", "Seed limit cannot exceed object budget.")
    before = query_scope_snapshot(scope, runtime=runtime)
    _check_expected(payload, before, required=True)
    if scope.workspace:
        result = compile_workspace_context_use_case(
            scope.workspace, query, **scope.selectors(), **budgets, mode="lexical",
            validated_only=reviewed, logical_hints=logical_hints, runtime=runtime,
        )
    else:
        assert scope.graph is not None
        result = compile_context_use_case(
            scope.graph, query, **budgets, mode="lexical", validated_only=reviewed,
            logical_hints=logical_hints, runtime=runtime,
        )
    _check_unchanged(scope, before, runtime)
    return {**before, "packet": result.to_dict()}


def _request_keys(payload: dict[str, Any], allowed: set[str] | frozenset[str]) -> None:
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise UIQueryFailure(
            "invalid_query_request",
            "Unsupported query parameters. Project scope and execution mode are server-owned.",
        )


def _query(payload: dict[str, Any]) -> str:
    value = payload.get("query")
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 2_000:
        raise UIQueryFailure("invalid_query", "Query must contain between 1 and 2000 characters.")
    return value.strip()


def _integer(
    payload: dict[str, Any], key: str, *, default: int, minimum: int, maximum: int,
) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise UIQueryFailure("invalid_query_budget", "Query limit is outside its allowed range.")
    return value


def _check_expected(
    payload: dict[str, Any], snapshot: dict[str, object], *, required: bool,
) -> None:
    if not required and not (_EXPECTED_KEYS & payload.keys()):
        return
    revisions = payload.get("expected_revisions")
    identity = payload.get("expected_scope_identity")
    if (
        not isinstance(revisions, dict)
        or any(not isinstance(key, str) or not isinstance(value, str)
               for key, value in revisions.items())
        or not isinstance(identity, str) or not identity
    ):
        raise UIQueryFailure(
            "query_revision_required", "Reload the project scope before requesting context."
        )
    if revisions != snapshot["revisions"] or identity != snapshot["scope_identity"]:
        _stale()


def _check_unchanged(
    scope: UIQueryScope, before: dict[str, object], runtime: TarelRuntime | None,
) -> None:
    if query_scope_snapshot(scope, runtime=runtime)["scope_identity"] != before["scope_identity"]:
        _stale()


def _stale() -> None:
    raise UIQueryFailure(
        "stale_query_scope", "The project scope changed. Reload before building context.",
        status=409,
    )
