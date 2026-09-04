"""Optional bounded inspector metadata; no graph expansion, rows, or execution."""

from __future__ import annotations

from collections import Counter

from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import physical_graph_revision
from tarel.graph.store import FileGraphStore
from tarel.logical_joins.application import (
    find_logical_joins_use_case,
    list_logical_joins_use_case,
)
from tarel.object_bindings.application import (
    find_object_bindings_use_case,
    load_object_binding_use_case,
)
from tarel.object_families.application import (
    load_object_family_use_case,
    validate_object_family_against_graph,
)
from tarel.runtime import TarelRuntime
from tarel.semantic_concepts.application import find_semantic_concepts_use_case
from tarel.topology.application import load_logical_topology_use_case
from tarel.topology.endpoint_contracts import LogicalEndpoint, ResolvedLogicalEndpoint
from tarel.topology.endpoints import resolve_logical_endpoint_for_graph_use_case

_LIMIT = 20


class LogicalMetadataFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def logical_metadata_use_case(
    graph_name: str,
    object_ids: tuple[str, ...],
    *,
    allowed_object_ids: frozenset[str] | None = None,
    mode: str = "include_candidates",
    runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    if (
        not isinstance(object_ids, tuple)
        or not 1 <= len(object_ids) <= 100
        or any(not isinstance(identifier, str) or not identifier for identifier in object_ids)
        or not isinstance(mode, str)
        or mode not in {"confirmed_only", "include_candidates"}
        or (
            allowed_object_ids is not None
            and (
                not isinstance(allowed_object_ids, frozenset)
                or any(not isinstance(identifier, str) for identifier in allowed_object_ids)
            )
        )
    ):
        raise LogicalMetadataFailure("invalid_logical_metadata_scope", "Invalid inspector scope.")
    graph = (runtime.graph_store() if runtime else FileGraphStore()).load(graph_name)
    allowed = frozenset(node.id for node in graph.nodes if node.type in {"table", "view"})
    if allowed_object_ids is not None:
        allowed &= allowed_object_ids
    selected = _selected_objects(graph, object_ids, allowed, mode, runtime)
    omissions: Counter[tuple[str, str]] = Counter()
    concepts: list[dict[str, object]] = []
    try:
        concepts = [
            item.to_dict()
            for item in find_semantic_concepts_use_case(
                graph_name,
                object_ids=selected,
                allowed_object_ids=allowed,
                mode=mode,
                limit=_LIMIT + 1,
                runtime=runtime,
            )
        ]
    except RuntimeError as exc:
        _omit_or_raise(omissions, "semantic_concepts", exc)
    cache: dict[LogicalEndpoint, ResolvedLogicalEndpoint] = {}
    joins: list[dict[str, object]] = []
    for join in list_logical_joins_use_case(graph_name=graph_name, runtime=runtime):
        if join.state == "rejected" or (mode == "confirmed_only" and join.state != "reviewed"):
            continue
        if join.graph_revision != physical_graph_revision(graph):
            omissions[("logical_joins", "stale_logical_join")] += 1
            continue
        try:
            endpoints = _resolve(
                graph,
                (
                    *join.program.source_endpoints,
                    *join.program.target_endpoints,
                ),
                runtime,
                cache,
            )
            if not _in_scope(endpoints, selected, allowed):
                continue
            matches = find_logical_joins_use_case(
                graph_name, join_id=join.id, mode=mode, runtime=runtime
            )
            if not matches:
                omissions[("logical_joins", "policy_excluded")] += 1
                continue
            joins.append(matches[0].to_dict())
        except RuntimeError as exc:
            _omit_or_raise(omissions, "logical_joins", exc)
        if len(joins) > _LIMIT:
            break
    bindings: list[dict[str, object]] = []
    for item in find_object_bindings_use_case(graph_name, mode=mode, runtime=runtime):
        if not item["usable"]:
            omissions[("object_bindings", str(item["error_code"]))] += 1
            continue
        try:
            endpoints = _resolve(
                graph,
                (
                    LogicalEndpoint.from_dict(item["source"]),
                    LogicalEndpoint.from_dict(item["target"]),
                ),
                runtime,
                cache,
            )
            if not _in_scope(endpoints, selected, allowed):
                continue
            binding = load_object_binding_use_case(graph_name, str(item["id"]), runtime=runtime)
            bindings.append(
                {
                    **item,
                    "provenance": {
                        "producer": binding.producer,
                        "run_id": binding.run_id,
                    },
                }
            )
        except RuntimeError as exc:
            _omit_or_raise(omissions, "object_bindings", exc)
        if len(bindings) > _LIMIT:
            break
    return {
        "graph": graph_name,
        "mode": mode,
        "limit_per_kind": _LIMIT,
        "concepts": concepts[:_LIMIT],
        "logical_joins": joins[:_LIMIT],
        "object_bindings": bindings[:_LIMIT],
        "more_available": {
            "concepts": len(concepts) > _LIMIT,
            "logical_joins": len(joins) > _LIMIT,
            "object_bindings": len(bindings) > _LIMIT,
        },
        "omissions": [
            {"kind": kind, "code": code, "count": count}
            for (kind, code), count in sorted(omissions.items())
        ],
        "notice": "Optional metadata only. Exploratory hints require runtime validation; "
        "no source values, member lists, joins or analysis code are executed here.",
    }


def _selected_objects(
    graph: GraphDocument,
    identifiers: tuple[str, ...],
    allowed: frozenset[str],
    mode: str,
    runtime: TarelRuntime | None,
) -> frozenset[str]:
    selected: set[str] = set()
    for identifier in identifiers:
        if identifier.startswith("object_family:"):
            family = load_object_family_use_case(
                graph.name,
                identifier.removeprefix("object_family:"),
                runtime=runtime,
            )
            validate_object_family_against_graph(family, graph)
            _state(family.state, mode)
            matching = set(family.member_ids) & allowed
        elif identifier.startswith(("logical_relation:", "derived_relation:")):
            document = load_logical_topology_use_case(graph.name, runtime=runtime)
            relation_id = identifier.split(":", 1)[1]
            relation = next(
                (item for item in document.derived_relations if item.id == relation_id), None
            )
            if relation is None:
                raise LogicalMetadataFailure(
                    "logical_metadata_object_not_found", "Unknown relation."
                )
            _state(relation.state, mode)
            matching = {relation.source.id} & allowed
        else:
            matching = {identifier} & allowed
        if not matching:
            raise LogicalMetadataFailure(
                "logical_metadata_object_outside_scope",
                "Selected object is outside the UI scope.",
            )
        selected.update(matching)
    return frozenset(selected)


def _state(state: str, mode: str) -> None:
    if state == "rejected" or (mode == "confirmed_only" and state != "reviewed"):
        raise LogicalMetadataFailure("logical_metadata_policy_excluded", "Object is not confirmed.")


def _resolve(
    graph: GraphDocument,
    endpoints: tuple[LogicalEndpoint, ...],
    runtime: TarelRuntime | None,
    cache: dict[LogicalEndpoint, ResolvedLogicalEndpoint],
) -> tuple[ResolvedLogicalEndpoint, ...]:
    for endpoint in endpoints:
        if endpoint not in cache:
            cache[endpoint] = resolve_logical_endpoint_for_graph_use_case(
                graph,
                endpoint,
                mode="include_candidates",
                runtime=runtime,
            )
    return tuple(cache[endpoint] for endpoint in endpoints)


def _in_scope(
    endpoints: tuple[ResolvedLogicalEndpoint, ...],
    selected: frozenset[str],
    allowed: frozenset[str],
) -> bool:
    physical_ids = {identifier for item in endpoints for identifier in item.physical_object_ids}
    return bool(physical_ids & selected) and physical_ids <= allowed


def _omit_or_raise(counts: Counter[tuple[str, str]], kind: str, error: RuntimeError) -> None:
    code = str(getattr(error, "code", ""))
    if (
        code.startswith("stale_")
        or code.endswith(("_graph_revision_mismatch", "_not_found"))
        or code == "logical_endpoint_policy_excluded"
    ):
        counts[(kind, code)] += 1
        return
    raise error
