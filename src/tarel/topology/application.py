"""Application boundary for graph-bound logical-topology documents."""

from __future__ import annotations

from dataclasses import dataclass, replace

from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import physical_graph_revision
from tarel.graph.store import FileGraphStore, GraphStore
from tarel.runtime import TarelRuntime
from tarel.topology.contracts import (
    DerivedRelation,
    LogicalTopologyDocument,
    LogicalTopologyFailure,
    review_derived_relation,
    validate_logical_topology,
)
from tarel.topology.store import FileLogicalTopologyStore, LogicalTopologyStore


@dataclass(frozen=True, slots=True)
class LogicalTopologyProjection:
    """Current sidecars plus stale graph names for a fail-soft read projection."""

    documents: tuple[LogicalTopologyDocument, ...]
    stale_graphs: tuple[str, ...]


def new_logical_topology_document(
    graph: GraphDocument,
    derived_relations: tuple[DerivedRelation, ...],
) -> LogicalTopologyDocument:
    document = LogicalTopologyDocument(
        graph_name=graph.name,
        graph_revision=physical_graph_revision(graph),
        derived_relations=derived_relations,
    )
    validate_logical_topology_against_graph(document, graph)
    return document


def save_logical_topology_use_case(
    document: LogicalTopologyDocument,
    *,
    expected_revision: str | None = None,
    graph_store: GraphStore | None = None,
    topology_store: LogicalTopologyStore | None = None,
    runtime: TarelRuntime | None = None,
) -> LogicalTopologyDocument:
    validate_logical_topology(document)
    graphs = _graph_store(runtime, graph_store)
    topologies = _topology_store(runtime, topology_store)
    graph = graphs.load(document.graph_name)
    validate_logical_topology_against_graph(document, graph)

    if topologies.exists(document.graph_name):
        current = topologies.load(document.graph_name)
        if expected_revision is None:
            raise LogicalTopologyFailure(
                "expected_logical_topology_revision_required",
                "Replacing a logical topology requires its current revision.",
            )
        if current.revision != expected_revision:
            raise LogicalTopologyFailure(
                "stale_logical_topology",
                "The logical topology changed after it was loaded. Reload it before saving.",
            )
        if current.graph_revision != document.graph_revision:
            raise LogicalTopologyFailure(
                "logical_topology_graph_rebase_forbidden",
                "A logical-topology document cannot be rebound to another physical graph "
                "revision. Rebuild it under a new graph identity.",
            )
        _validate_import_transition(current, document)
    elif expected_revision is not None:
        raise LogicalTopologyFailure(
            "stale_logical_topology",
            "No logical topology exists for the supplied expected revision.",
        )
    else:
        _require_candidate_imports(document)

    topologies.save(document)
    return document


def decide_derived_relation_use_case(
    graph_name: str,
    relation_id: str,
    *,
    decision: str,
    reason: str,
    expected_revision: str | None,
    graph_store: GraphStore | None = None,
    topology_store: LogicalTopologyStore | None = None,
    runtime: TarelRuntime | None = None,
) -> LogicalTopologyDocument:
    if expected_revision is None:
        raise LogicalTopologyFailure(
            "expected_logical_topology_revision_required",
            "Reviewing a derived relation requires the current document revision.",
        )
    graphs = _graph_store(runtime, graph_store)
    topologies = _topology_store(runtime, topology_store)
    current = load_logical_topology_use_case(
        graph_name,
        graph_store=graphs,
        topology_store=topologies,
    )
    if current.revision != expected_revision:
        raise LogicalTopologyFailure(
            "stale_logical_topology",
            "The logical topology changed after it was loaded. Reload it before reviewing.",
        )
    changed_relations: list[DerivedRelation] = []
    found = False
    for relation in current.derived_relations:
        if relation.id != relation_id:
            changed_relations.append(relation)
            continue
        found = True
        changed_relations.append(
            review_derived_relation(relation, decision=decision, reason=reason)
        )
    if not found:
        raise LogicalTopologyFailure(
            "derived_relation_not_found", f"Derived relation not found: {relation_id}"
        )
    changed = replace(current, derived_relations=tuple(changed_relations))
    validate_logical_topology_against_graph(changed, graphs.load(graph_name))
    topologies.save(changed)
    return changed


def load_logical_topology_use_case(
    graph_name: str,
    *,
    graph_store: GraphStore | None = None,
    topology_store: LogicalTopologyStore | None = None,
    runtime: TarelRuntime | None = None,
) -> LogicalTopologyDocument:
    graphs = _graph_store(runtime, graph_store)
    topologies = _topology_store(runtime, topology_store)
    document = topologies.load(graph_name)
    validate_logical_topology_against_graph(document, graphs.load(graph_name))
    return document


def list_logical_topologies_use_case(
    *,
    graph_names: tuple[str, ...] | None = None,
    graph_store: GraphStore | None = None,
    topology_store: LogicalTopologyStore | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[LogicalTopologyDocument, ...]:
    graphs = _graph_store(runtime, graph_store)
    topologies = _topology_store(runtime, topology_store)
    selected = set(graph_names) if graph_names is not None else None
    graph_documents = tuple(
        graphs.load(name)
        for name in topologies.list()
        if selected is None or name in selected
    )
    return list_logical_topologies_for_graphs_use_case(
        graph_documents,
        topology_store=topologies,
    )


def list_logical_topologies_for_graphs_use_case(
    graphs: tuple[GraphDocument, ...],
    *,
    topology_store: LogicalTopologyStore | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[LogicalTopologyDocument, ...]:
    topologies = _topology_store(runtime, topology_store)
    documents = []
    for graph in graphs:
        if not topologies.exists(graph.name):
            continue
        document = topologies.load(graph.name)
        validate_logical_topology_against_graph(document, graph)
        documents.append(document)
    return tuple(documents)


def project_logical_topologies_for_graphs_use_case(
    graphs: tuple[GraphDocument, ...],
    *,
    topology_store: LogicalTopologyStore | None = None,
    runtime: TarelRuntime | None = None,
) -> LogicalTopologyProjection:
    """Select current optional sidecars without making a stale one break the graph UI."""

    topologies = _topology_store(runtime, topology_store)
    documents = []
    stale_graphs = []
    for graph in graphs:
        if not topologies.exists(graph.name):
            continue
        document = topologies.load(graph.name)
        try:
            validate_logical_topology_against_graph(document, graph)
        except LogicalTopologyFailure as exc:
            if exc.code != "logical_topology_graph_revision_mismatch":
                raise
            stale_graphs.append(graph.name)
            continue
        documents.append(document)
    return LogicalTopologyProjection(
        documents=tuple(documents),
        stale_graphs=tuple(stale_graphs),
    )


def validate_logical_topology_against_graph(
    document: LogicalTopologyDocument,
    graph: GraphDocument,
) -> None:
    validate_logical_topology(document)
    if (
        document.graph_name != graph.name
        or document.graph_revision != physical_graph_revision(graph)
    ):
        raise LogicalTopologyFailure(
            "logical_topology_graph_revision_mismatch",
            "Logical topology targets a different graph revision.",
        )

    nodes = graph.node_by_id()
    for relation in document.derived_relations:
        source = nodes.get(relation.source.id)
        if source is None or source.type not in {"table", "view"}:
            raise LogicalTopologyFailure(
                "logical_topology_endpoint_not_found",
                f"Derived relation source is not a graph table or view: {relation.source.id}",
            )
        graph_field_ids = {
            step.input.id
            for step in relation.steps
            if step.input.kind == "graph_field"
        } | {
            field.source.id
            for field in relation.output_schema
            if field.source.kind == "graph_field"
        }
        for field_id in graph_field_ids:
            field = nodes.get(field_id)
            if field is None or field.type != "field":
                raise LogicalTopologyFailure(
                    "logical_topology_endpoint_not_found",
                    f"Logical-topology endpoint is not a graph field: {field_id}",
                )
            if field.metadata.get("object_id") != source.id:
                raise LogicalTopologyFailure(
                    "logical_topology_cross_object_step",
                    "Derived steps and passthrough fields must belong to the source object.",
                )
        for output in relation.output_schema:
            if output.kind != "passthrough":
                continue
            field = nodes[output.source.id]
            source_data_type = field.metadata.get("data_type")
            source_nullable = field.metadata.get("nullable")
            if source_data_type != output.data_type or source_nullable != output.nullable:
                raise LogicalTopologyFailure(
                    "logical_topology_passthrough_schema_mismatch",
                    "Passthrough output schema must match the graph field schema exactly.",
                )


def _require_candidate_imports(document: LogicalTopologyDocument) -> None:
    if any(
        relation.state != "candidate" or relation.review is not None
        for relation in document.derived_relations
    ):
        raise LogicalTopologyFailure(
            "invalid_logical_topology_import",
            "New derived-relation imports must be unreviewed candidates.",
        )


def _validate_import_transition(
    current: LogicalTopologyDocument,
    incoming: LogicalTopologyDocument,
) -> None:
    current_by_id = {relation.id: relation for relation in current.derived_relations}
    incoming_by_id = {relation.id: relation for relation in incoming.derived_relations}
    for relation in incoming.derived_relations:
        previous = current_by_id.get(relation.id)
        if previous == relation:
            continue
        if previous is not None and previous.state != "candidate":
            raise LogicalTopologyFailure(
                "immutable_derived_relation",
                "Reviewed and rejected derived relations are immutable audit records.",
            )
        if relation.state != "candidate" or relation.review is not None:
            raise LogicalTopologyFailure(
                "invalid_logical_topology_import",
                "Changed derived-relation imports must be unreviewed candidates.",
            )
    if any(
        relation.state != "candidate" and relation_id not in incoming_by_id
        for relation_id, relation in current_by_id.items()
    ):
        raise LogicalTopologyFailure(
            "immutable_derived_relation",
            "A whole-document import cannot remove reviewed audit records.",
        )


def _graph_store(runtime: TarelRuntime | None, store: GraphStore | None) -> GraphStore:
    if store is not None:
        return store
    return runtime.graph_store() if runtime is not None else FileGraphStore()


def _topology_store(
    runtime: TarelRuntime | None,
    store: LogicalTopologyStore | None,
) -> LogicalTopologyStore:
    if store is not None:
        return store
    return runtime.logical_topology_store() if runtime is not None else FileLogicalTopologyStore()
