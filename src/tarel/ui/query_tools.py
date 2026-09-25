"""Bounded read-only browser adapters for the existing search/context use cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tarel.application import (
    compile_context_prefix_use_case,
    compile_context_use_case,
    compile_workspace_context_prefix_use_case,
    compile_workspace_context_use_case,
    load_focus_use_case,
    load_workspace_use_case,
    resolve_graph_object_scope_use_case,
    resolve_workspace_scope_use_case,
    search_graph_use_case,
    search_workspace_use_case,
)
from tarel.context_output import canonical_hash
from tarel.expansion.application import expand_context_use_case
from tarel.expansion.contracts import ExpansionTarget
from tarel.graph.store import FileGraphStore
from tarel.runtime import TarelRuntime
from tarel.search import SearchFilters

_SCOPE_NOTICE = (
    "The server launch scope is the outer boundary. An explicit working scope can narrow "
    "search and context; display filters do not constrain it until applied. "
    "No source queries or LLM calls."
)
_EXPECTED_KEYS = frozenset({"expected_revisions", "expected_scope_identity"})
_MAX_SCOPE_OBJECTS = 5_000
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
    focuses: tuple[str, ...] = ()
    search_mode: str = "lexical"
    model_path: Path | None = None
    n_threads: int | None = None

    def __post_init__(self) -> None:
        if bool(self.graph) == bool(self.workspace):
            raise UIQueryFailure("invalid_query_scope", "Choose one project query scope.")
        if any(
            value is not None and (not isinstance(value, str) or not value.strip())
            for value in (self.graph, self.workspace)
        ):
            raise UIQueryFailure("invalid_query_scope", "Invalid project query scope.")
        if self.search_mode not in {"lexical", "bm25", "vector", "hybrid"}:
            raise UIQueryFailure("invalid_query_scope", "Unsupported project search mode.")
        for key, values in self.selectors().items():
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise UIQueryFailure("invalid_query_scope", "Invalid project query selectors.")
            if self.graph and values and key != "focuses":
                raise UIQueryFailure(
                    "invalid_query_scope", "Query selectors require a workspace launch scope."
                )

    def selectors(self) -> dict[str, tuple[str, ...]]:
        return {
            "systems": self.systems, "graphs": self.graphs, "areas": self.areas,
            "schemas": self.schemas, "zones": self.zones, "focuses": self.focuses,
        }


def query_scope_snapshot(
    scope: UIQueryScope, *, scope_objects: tuple[str, ...] = (),
    runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    """Expose exact source revisions without inventing a viewport selection contract."""
    if scope.workspace:
        resolved = resolve_workspace_scope_use_case(
            scope.workspace, **scope.selectors(), objects=scope_objects, runtime=runtime,
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
        if scope.focuses:
            selection["focuses"] = list(scope.focuses)
        if scope_objects:
            _graph_scope_ids(scope.graph, scope_objects, runtime=runtime)
            selection["objects"] = list(scope_objects)
    store = runtime.graph_store() if runtime else FileGraphStore()
    revisions = {name: store.header(name).revision for name in names}
    for name in scope.focuses:
        revisions[f"focus:{name}"] = load_focus_use_case(name, runtime=runtime).revision
    return {
        "scope": selection,
        "revisions": revisions,
        "scope_identity": canonical_hash({"scope": selection, "revisions": revisions}),
        "notice": _SCOPE_NOTICE,
        "search": {"local": True, "mode": scope.search_mode},
    }


def search_metadata(
    scope: UIQueryScope, payload: dict[str, Any], *, runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    _request_keys(
        payload,
        {
            "query", "limit", "family_mode", "types", "roles", "required_fields",
            "scope_objects", "reviewed_annotations_only",
        }
        | _EXPECTED_KEYS,
    )
    query = _query(payload)
    limit = _integer(payload, "limit", default=20, minimum=1, maximum=100)
    family_mode = payload.get("family_mode", "confirmed_only")
    if family_mode not in ("confirmed_only", "include_candidates"):
        raise UIQueryFailure("invalid_query_policy", "Unsupported family search policy.")
    filters = SearchFilters(
        types=_strings(payload, "types"),
        roles=_strings(payload, "roles"),
        required_fields=_strings(payload, "required_fields"),
    )
    reviewed = payload.get("reviewed_annotations_only", False)
    if not isinstance(reviewed, bool):
        raise UIQueryFailure("invalid_query_policy", "Reviewed annotations must be a boolean.")
    scope_objects = _scope_objects(payload)
    before = query_scope_snapshot(scope, scope_objects=scope_objects, runtime=runtime)
    _check_expected(payload, before, required=False)
    if scope.workspace:
        result = search_workspace_use_case(
            scope.workspace, query, **scope.selectors(),
            limit=limit, mode=scope.search_mode, model_path=scope.model_path,
            n_threads=scope.n_threads, family_mode=family_mode, filters=filters,
            scope_objects=scope_objects,
            validated_only=reviewed,
            runtime=runtime,
        )
    else:
        assert scope.graph is not None
        result = search_graph_use_case(
            scope.graph, query, limit=limit, mode=scope.search_mode,
            model_path=scope.model_path, n_threads=scope.n_threads,
            family_mode=family_mode, filters=filters, focuses=scope.focuses,
            validated_only=reviewed,
            scope_object_ids=_graph_scope_ids(
                scope.graph, scope_objects, runtime=runtime,
            ),
            runtime=runtime,
        )
    _check_unchanged(scope, before, runtime, scope_objects=scope_objects)
    return {**before, "results": result.to_dict()}


def preview_context(
    scope: UIQueryScope, payload: dict[str, Any], *, runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    _request_keys(
        payload,
        {
            "query", "kind", "object_ids", "scope_objects",
            "reviewed_annotations_only", "logical_hints",
        }
        | _EXPECTED_KEYS | _BUDGETS.keys(),
    )
    kind = payload.get("kind", "question")
    if kind not in {"question", "prefix", "selected"}:
        raise UIQueryFailure("invalid_context_kind", "Unsupported context kind.")
    query = "" if kind == "prefix" else _query(payload)
    if "object_ids" in payload and kind != "selected":
        raise UIQueryFailure(
            "invalid_query_request", "Object IDs require explicit selected context mode."
        )
    object_ids = _strings(payload, "object_ids")
    scope_objects = _scope_objects(payload)
    if kind == "selected" and not object_ids:
        raise UIQueryFailure("invalid_context_selection", "Select at least one object.")
    if kind != "selected" and object_ids:
        raise UIQueryFailure(
            "invalid_context_selection", "Object selection requires selected context mode."
        )
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
    before = query_scope_snapshot(scope, scope_objects=scope_objects, runtime=runtime)
    _check_expected(payload, before, required=True)
    if kind == "prefix" and scope.workspace:
        result = compile_workspace_context_prefix_use_case(
            scope.workspace, **scope.selectors(),
            scope_objects=scope_objects,
            max_objects=budgets["max_objects"], max_joins=budgets["max_joins"],
            max_fields_per_object=budgets["max_fields_per_object"],
            max_characters=budgets["max_characters"], validated_only=reviewed,
            logical_hints=logical_hints, runtime=runtime,
        )
    elif kind == "prefix":
        assert scope.graph is not None
        result = compile_context_prefix_use_case(
            scope.graph, max_objects=budgets["max_objects"],
            max_joins=budgets["max_joins"],
            max_fields_per_object=budgets["max_fields_per_object"],
            max_characters=budgets["max_characters"], validated_only=reviewed,
            logical_hints=logical_hints, focuses=scope.focuses, runtime=runtime,
            scope_object_ids=_graph_scope_ids(
                scope.graph, scope_objects, runtime=runtime,
            ),
        )
    elif scope.workspace:
        result = compile_workspace_context_use_case(
            scope.workspace, query, **scope.selectors(), **budgets, mode=scope.search_mode,
            scope_objects=scope_objects,
            model_path=scope.model_path, n_threads=scope.n_threads,
            validated_only=reviewed, logical_hints=logical_hints,
            object_ids=object_ids, runtime=runtime,
        )
    else:
        assert scope.graph is not None
        result = compile_context_use_case(
            scope.graph, query, **budgets, mode=scope.search_mode,
            model_path=scope.model_path, n_threads=scope.n_threads,
            validated_only=reviewed,
            logical_hints=logical_hints, object_ids=object_ids,
            focuses=scope.focuses, runtime=runtime,
            scope_object_ids=_graph_scope_ids(
                scope.graph, scope_objects, runtime=runtime,
            ),
        )
    _check_unchanged(scope, before, runtime, scope_objects=scope_objects)
    return {**before, "packet": result.to_dict()}


def preview_expansion(
    scope: UIQueryScope, payload: dict[str, Any], *, runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    """Expand fields for physical objects already present in a validated context packet."""
    _request_keys(
        payload,
        {"packet", "object_ids", "scope_objects", "max_characters"} | _EXPECTED_KEYS,
    )
    packet = payload.get("packet")
    if not isinstance(packet, dict):
        raise UIQueryFailure("invalid_context_expansion", "A context packet is required.")
    object_ids = _strings(payload, "object_ids")
    if not object_ids:
        raise UIQueryFailure("invalid_context_expansion", "Select at least one packet object.")
    scope_objects = _scope_objects(payload)
    max_characters = _integer(
        payload, "max_characters", default=24_000, minimum=1_000, maximum=100_000,
    )
    before = query_scope_snapshot(scope, scope_objects=scope_objects, runtime=runtime)
    _check_expected(payload, before, required=True)
    stable = packet.get("stable")
    if not isinstance(stable, dict):
        raise UIQueryFailure("invalid_context_expansion", "The context packet is invalid.")
    graph_identity = stable.get("graph")
    packet_scope = stable.get("scope")
    objects = stable.get("objects")
    if (
        not isinstance(graph_identity, dict)
        or not isinstance(packet_scope, dict)
        or not isinstance(objects, list)
    ):
        raise UIQueryFailure("invalid_context_expansion", "The context packet is invalid.")
    if scope.graph and graph_identity.get("name") != scope.graph:
        raise UIQueryFailure("invalid_context_expansion", "Packet belongs to another graph.")
    if scope.workspace and packet_scope.get("workspace") != scope.workspace:
        raise UIQueryFailure("invalid_context_expansion", "Packet belongs to another workspace.")
    available = {
        item.get("id") for item in objects
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if set(object_ids) - available:
        raise UIQueryFailure(
            "invalid_context_expansion", "Expansion object is not present in the packet."
        )
    revisions = before["revisions"]
    assert isinstance(revisions, dict)
    targets: list[ExpansionTarget] = []
    for reference in object_ids:
        if reference.startswith("scope::"):
            prefix, graph_name, object_id = reference.split("::", 2)
            if prefix != "scope" or not graph_name or not object_id:
                raise UIQueryFailure("invalid_context_expansion", "Invalid workspace object ID.")
        else:
            if scope.graph is None:
                raise UIQueryFailure("invalid_context_expansion", "Invalid workspace object ID.")
            graph_name, object_id = scope.graph, reference
        revision = revisions.get(graph_name)
        if not isinstance(revision, str):
            raise UIQueryFailure("stale_query_scope", "Object graph is outside the working scope.")
        targets.append(ExpansionTarget("object", graph_name, object_id, revision))
    if scope.workspace:
        resolved = resolve_workspace_scope_use_case(
            scope.workspace, **scope.selectors(), objects=scope_objects, runtime=runtime,
        )
        allowed = {(item.graph, item.object_id) for item in resolved.objects}
    else:
        assert scope.graph is not None
        allowed = {
            (scope.graph, object_id) for object_id in resolve_graph_object_scope_use_case(
                scope.graph, focuses=scope.focuses,
                object_ids=_graph_scope_ids(scope.graph, scope_objects, runtime=runtime),
                runtime=runtime,
            )
        }
    if any((target.graph, target.id) not in allowed for target in targets):
        raise UIQueryFailure(
            "invalid_context_expansion", "Expansion object is outside the working scope."
        )
    result = expand_context_use_case(
        packet, tuple(targets), max_characters=max_characters, runtime=runtime,
    )
    _check_unchanged(scope, before, runtime, scope_objects=scope_objects)
    return {**before, "expansion": result.to_dict()}


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


def _strings(
    payload: dict[str, Any], key: str, *, maximum: int = 100,
) -> tuple[str, ...]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise UIQueryFailure("invalid_query_request", f"Invalid {key} selection.")
    if len(value) > maximum:
        raise UIQueryFailure("invalid_query_request", f"Too many {key} values.")
    return tuple(value)


def _scope_objects(payload: dict[str, Any]) -> tuple[str, ...]:
    return _strings(payload, "scope_objects", maximum=_MAX_SCOPE_OBJECTS)


def _graph_scope_ids(
    graph_name: str,
    references: tuple[str, ...],
    *,
    runtime: TarelRuntime | None,
) -> tuple[str, ...]:
    if not references:
        return ()
    object_ids: list[str] = []
    for reference in references:
        selected_graph, separator, object_id = reference.partition(":")
        if not separator or selected_graph != graph_name or not object_id:
            raise UIQueryFailure(
                "invalid_query_scope", "Working-scope object belongs to another graph."
            )
        object_ids.append(object_id)
    store = runtime.graph_store() if runtime else FileGraphStore()
    graph = store.load(graph_name)
    known = {node.id for node in graph.nodes if node.type in {"table", "view"}}
    if set(object_ids) - known:
        raise UIQueryFailure("invalid_query_scope", "Working-scope object no longer exists.")
    return tuple(object_ids)


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
    *, scope_objects: tuple[str, ...] = (),
) -> None:
    if query_scope_snapshot(
        scope, scope_objects=scope_objects, runtime=runtime,
    )["scope_identity"] != before["scope_identity"]:
        _stale()


def _stale() -> None:
    raise UIQueryFailure(
        "stale_query_scope", "The project scope changed. Reload before building context.",
        status=409,
    )
