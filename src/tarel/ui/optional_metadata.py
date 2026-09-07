"""Bounded on-demand browser metadata; no rows, execution, or persistent cache."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace

from tarel.discovery.application import list_query_linked_coverages_use_case
from tarel.entity_resolution.application import (
    find_entity_resolution_candidates_for_graph_use_case,
)
from tarel.entity_resolution.contracts import EntityResolutionCandidate, EntityResolutionMatch
from tarel.entity_resolution.projection import project_entity_resolution_edges
from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.graph.revision import graph_revision
from tarel.reference_mapping.application import (
    find_reference_mapping_candidates_for_graph_use_case,
)
from tarel.runtime import TarelRuntime
from tarel.semantics.application import list_semantic_imports_use_case
from tarel.semantics.projection import semantic_node_bindings
from tarel.ui.presentation import (
    _edge_payload,
    _query_linked_coverage_summary,
    _reference_mapping_edge_payloads,
)

_MAX_LIMIT = 20
_MAX_PAYLOAD_BYTES = 128 * 1024


class OptionalMetadataFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def optional_object_metadata(
    graph: GraphDocument,
    object_id: str,
    *,
    allowed_object_ids: frozenset[str],
    kind: str,
    limit: int = _MAX_LIMIT,
    runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    """Project current optional claims for one authorized physical object.

    Existing find use cases remain authoritative for rejected, superseded and stale
    candidate policies. Their stores may scan local artifacts on this explicit call;
    limits bound the response, not the underlying storage scan.
    """
    if not isinstance(kind, str) or kind not in {"identity", "mappings", "coverage", "imports"} or (
        type(limit) is not int or not 1 <= limit <= _MAX_LIMIT
    ) or not isinstance(allowed_object_ids, frozenset) or (
        not isinstance(object_id, str)
        or any(not isinstance(item, str) for item in allowed_object_ids)
    ):
        raise OptionalMetadataFailure(
            "invalid_optional_metadata_request", "Invalid metadata request.",
        )
    nodes = graph.node_by_id()
    selected = nodes.get(object_id)
    if (selected is None or selected.type not in {"table", "view"}
            or object_id not in allowed_object_ids):
        raise OptionalMetadataFailure(
            "optional_object_outside_scope", "Object is outside this scope.",
        )
    allowed = allowed_object_ids & frozenset(
        node.id for node in graph.nodes if node.type in {"table", "view"}
    )
    omissions: Counter[str] = Counter()
    records: list[dict[str, object]] = []
    revisions: dict[str, str] = {}
    if kind in {"identity", "coverage"}:
        matches = find_entity_resolution_candidates_for_graph_use_case(graph, runtime=runtime)
        scoped = tuple(match for match in matches if _in_scope(
            _entity_fields(match.candidate), nodes, object_id, allowed,
        ))
        if kind == "identity":
            for match in scoped:
                # Run-level coverage has its own stricter same-object attribution
                # path below; candidate presence alone cannot justify those counts.
                edge = project_entity_resolution_edges(
                    graph, (replace(match, query_linked_coverage=None),),
                )[0]
                record = _edge_payload(edge, nodes, graph.name)
                if record is None:
                    raise OptionalMetadataFailure(
                        "invalid_optional_edge", "Cannot project this edge.",
                    )
                record["metadata"]["revision"] = match.candidate.revision
                records.append(record)
                revisions[match.candidate.id] = match.candidate.revision
        else:
            records, revisions = _coverage_records(
                graph, object_id, nodes, scoped, omissions, runtime,
            )
    elif kind == "mappings":
        matches = find_reference_mapping_candidates_for_graph_use_case(graph, runtime=runtime)
        scoped = tuple(match for match in matches if _in_scope(
            (match.candidate.source_field_id, match.candidate.target_field_id),
            nodes, object_id, allowed,
        ))
        records = _reference_mapping_edge_payloads(graph, scoped, visible_object_ids=set(allowed))
        revisions = {match.candidate.id: match.candidate.revision for match in scoped}
    else:
        documents = list_semantic_imports_use_case(graph_name=graph.name, runtime=runtime)
        bindings = semantic_node_bindings(documents)
        fields = tuple(node for node in graph.nodes if node.type == "field"
                       and node.metadata.get("object_id") == object_id)
        for node in (selected, *fields):
            for entry in bindings.get((graph.name, node.id), ()):
                # No source snapshot, expressions, original values or local source references.
                record = {key: entry[key] for key in (
                    "import_name", "import_revision", "target_id", "kind", "name",
                    "description", "synonyms", "patch_count",
                )}
                record.update(
                    object_id=object_id, field_id=node.id if node.type == "field" else None,
                    field_label=node.label if node.type == "field" else None,
                )
                records.append(record)
                revisions[str(entry["import_name"])] = str(entry["import_revision"])
        if documents:
            omissions["model_wide_metadata_not_projected"] = sum(
                len(doc.models) for doc in documents
            )
            omissions["semantic_import_incomplete"] = sum(not doc.complete for doc in documents)
    bounded, more_available = _bounded(records, limit, omissions)
    is_edge = kind in {"identity", "mappings"}
    returned_refs = {
        str(record["metadata"]["candidate_id"] if is_edge else
            record["run_id"] if kind == "coverage" else record["import_name"])
        for record in bounded
    }
    payload = {
        "graph": graph.name,
        "object_id": object_id,
        "kind": kind,
        "state": "loaded",
        "items": [] if is_edge else bounded,
        "edges": bounded if is_edge else [],
        "omissions": [{"code": code, "count": count}
                      for code, count in sorted(omissions.items()) if count],
        "more_available": more_available,
        "limit": limit,
        "artifact_revisions": [
            {"id": key, "revision": revisions[key]} for key in sorted(returned_refs)
        ],
        "notice": "Current in-scope metadata only; retrieval policy excludes stale, rejected "
        "and superseded candidates. Optional hints do not establish confirmed joins.",
    }
    # Reserve the small graph/scope revision envelope added by the HTTP adapter.
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > _MAX_PAYLOAD_BYTES - 512:
        raise OptionalMetadataFailure(
            "optional_metadata_too_large", "Metadata envelope exceeds the response limit.",
        )
    return payload


def _entity_fields(candidate: EntityResolutionCandidate) -> tuple[str, ...]:
    fields = [candidate.source_field_id, candidate.target_field_id]
    if candidate.program is not None:
        fields.extend((*candidate.program.source_fields, *candidate.program.target_fields))
    if candidate.self_match is not None:
        fields.extend((candidate.self_match.record_key_field_id,
                       *candidate.self_match.comparison_field_ids,
                       *candidate.self_match.contradiction_field_ids))
    return tuple(sorted(set(fields)))


def _owners(fields: tuple[str, ...], nodes: dict[str, GraphNode]) -> frozenset[str]:
    owners: set[str] = set()
    for field_id in fields:
        field = nodes.get(field_id)
        owner = nodes.get(str(field.metadata.get("object_id") or "")) if field else None
        if (field is None or field.type != "field" or owner is None
                or owner.type not in {"table", "view"}):
            raise OptionalMetadataFailure("invalid_optional_endpoint", "Invalid metadata endpoint.")
        owners.add(owner.id)
    return frozenset(owners)


def _in_scope(
    fields: tuple[str, ...], nodes: dict[str, GraphNode],
    selected: str, allowed: frozenset[str],
) -> bool:
    owners = _owners(fields, nodes)
    return selected in owners and owners <= allowed


def _coverage_records(
    graph: GraphDocument, object_id: str, nodes: dict[str, GraphNode],
    matches: tuple[EntityResolutionMatch, ...], omissions: Counter[str],
    runtime: TarelRuntime | None,
) -> tuple[list[dict[str, object]], dict[str, str]]:
    by_run: dict[str, set[str]] = {}
    revision = graph_revision(graph)
    for match in matches:
        candidate = match.candidate
        if _owners(_entity_fields(candidate), nodes) != frozenset({object_id}):
            continue
        refs = by_run.setdefault(candidate.provenance.run_id, set())
        refs.add(candidate.id)
        if candidate.provenance.discovery_candidate_id:
            refs.add(candidate.provenance.discovery_candidate_id)
    records, revisions = [], {}
    for coverage in list_query_linked_coverages_use_case(graph_name=graph.name, runtime=runtime):
        if coverage.graph_revision != revision:
            omissions["stale_query_linked_coverage"] += 1
        elif not coverage.candidate_refs or not set(coverage.candidate_refs) <= by_run.get(
            coverage.run_id, set()
        ):
            omissions["coverage_object_scope_unverified"] += 1
        else:
            summary = _query_linked_coverage_summary(coverage, ())
            usages = {
                match.usage for match in matches
                if match.candidate.provenance.run_id == coverage.run_id
                and {match.candidate.id, match.candidate.provenance.discovery_candidate_id}
                & set(coverage.candidate_refs)
            }
            summary["candidate_usage"] = (
                "confirmed" if usages == {"confirmed"} else "exploratory_only"
            )
            records.append(summary)
            revisions[coverage.run_id] = coverage.revision
    return sorted(records, key=lambda item: item["run_id"]), revisions


def _bounded(
    records: list[dict[str, object]], limit: int, omissions: Counter[str],
) -> tuple[list[dict[str, object]], bool]:
    selected = []
    # Leave space for bounded revisions and the envelope rather than truncating a
    # claim's evidence or uncertainty text halfway through.
    budget = _MAX_PAYLOAD_BYTES - 8192
    for record in records[:limit]:
        size = len(json.dumps(record, ensure_ascii=False).encode("utf-8"))
        if size > budget:
            omissions["metadata_response_budget"] += 1
            continue
        selected.append(record)
        budget -= size
    if len(records) > limit:
        omissions["metadata_result_limit"] += len(records) - limit
    return selected, len(selected) < len(records)
