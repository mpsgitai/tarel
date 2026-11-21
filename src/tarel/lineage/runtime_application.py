"""Runtime lineage use cases: import reported executions, load them and trace one call."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.graph.revision import graph_revision
from tarel.lineage.contracts import LineageFailure
from tarel.lineage.runtime import runtime_lineage_document_version, validate_runtime_lineage_input
from tarel.lineage.runtime_inputs import (
    RuntimeFederatedQueryInput,
    RuntimeMongoAttemptInput,
    RuntimePythonAnalysisInput,
)
from tarel.lineage.runtime_logical import RuntimeLogicalOperation
from tarel.lineage.runtime_records import (
    RuntimeDependency,
    RuntimeEvent,
    RuntimeEventInput,
    RuntimeFederatedQuery,
    RuntimeInputReference,
    RuntimeLineageDocument,
    RuntimeLineageInput,
    RuntimeLineageTrace,
    RuntimeMongoAttempt,
    RuntimePythonAnalysis,
    RuntimeSQLAttempt,
    RuntimeTraceCall,
)
from tarel.runtime import TarelRuntime, resolve_runtime


@dataclass(frozen=True, slots=True)
class RuntimeLineageImportResult:
    document: RuntimeLineageDocument
    path: Path


def import_runtime_lineage_use_case(
    name: str,
    observed: RuntimeLineageInput,
    *,
    runtime: TarelRuntime | None = None,
) -> RuntimeLineageImportResult:
    validate_runtime_lineage_input(observed)
    graph = resolve_runtime(runtime).graph_store().load(observed.graph_name)
    current_revision = graph_revision(graph)
    if observed.graph_revision != current_revision:
        raise LineageFailure(
            "runtime_graph_revision_mismatch",
            "Runtime lineage graph revision does not match the persisted graph.",
        )
    events = tuple(_runtime_event(graph, event) for event in observed.events)
    document = RuntimeLineageDocument(
        name=name,
        run_id=observed.run_id,
        graph_name=graph.name,
        graph_revision=current_revision,
        events=events,
        contract_version=runtime_lineage_document_version(observed.contract_version),
    )
    return RuntimeLineageImportResult(
        document, resolve_runtime(runtime).runtime_lineage_store().create(document)
    )


def load_runtime_lineage_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> RuntimeLineageDocument:
    return resolve_runtime(runtime).runtime_lineage_store().load(name)


def list_runtime_lineages_use_case(*, runtime: TarelRuntime | None = None) -> tuple[str, ...]:
    return resolve_runtime(runtime).runtime_lineage_store().list()


def trace_runtime_lineage_use_case(
    name: str,
    call_id: str,
    *,
    runtime: TarelRuntime | None = None,
) -> RuntimeLineageTrace:
    document = resolve_runtime(runtime).runtime_lineage_store().load(name)
    events = {item.call_id: item for item in document.events}
    start = events.get(call_id)
    if start is None:
        raise LineageFailure(
            "runtime_call_not_found",
            f"Runtime call not found in {name}: {call_id}",
        )
    if start.status not in {"accepted", "succeeded"}:
        raise LineageFailure(
            "runtime_call_not_evidence",
            "A failed runtime call cannot be used as an evidence trace endpoint.",
        )
    reached: set[str] = set()
    dependencies: set[tuple[str, str]] = set()

    def visit(event: RuntimeEvent) -> None:
        if event.call_id in reached:
            return
        reached.add(event.call_id)
        if isinstance(
            event, (RuntimeFederatedQuery, RuntimePythonAnalysis, RuntimeLogicalOperation)
        ):
            for source_call_id in event.consumes:
                dependencies.add((source_call_id, event.call_id))
                visit(events[source_call_id])

    visit(start)
    selected = tuple(sorted((events[item] for item in reached), key=lambda item: item.sequence))
    origins = {
        reference.node_id: reference
        for event in selected
        if isinstance(event, (RuntimeSQLAttempt, RuntimeMongoAttempt))
        for reference in event.inputs
    }
    return RuntimeLineageTrace(
        runtime_lineage=document.name,
        start_call_id=start.call_id,
        graph_name=document.graph_name,
        graph_revision=document.graph_revision,
        calls=tuple(
            RuntimeTraceCall(
                call_id=event.call_id,
                sequence=event.sequence,
                kind=(
                    "logical_operation"
                    if isinstance(event, RuntimeLogicalOperation)
                    else "python_analysis"
                    if isinstance(event, RuntimePythonAnalysis)
                    else "federated_query"
                    if isinstance(event, RuntimeFederatedQuery)
                    else "mongo_query"
                    if isinstance(event, RuntimeMongoAttempt)
                    else "sql_query"
                ),
                status=event.status,
                operation=event.operation if isinstance(event, RuntimeLogicalOperation) else None,
            )
            for event in selected
        ),
        dependencies=tuple(
            RuntimeDependency(source_call_id=source, target_call_id=target)
            for source, target in sorted(
                dependencies,
                key=lambda item: (
                    events[item[0]].sequence,
                    events[item[1]].sequence,
                    item,
                ),
            )
        ),
        origins=tuple(sorted(origins.values(), key=lambda item: item.reference.casefold())),
    )


def _runtime_event(graph: GraphDocument, event: RuntimeEventInput) -> RuntimeEvent:
    if isinstance(event, RuntimeLogicalOperation):
        return event
    if isinstance(event, RuntimePythonAnalysisInput):
        return RuntimePythonAnalysis(
            sequence=event.sequence,
            call_id=event.call_id,
            status=event.status,
            code_sha256=event.code_sha256,
            consumes=event.consumes,
            executor=event.executor,
            input_frames=event.input_frames,
            analysis=event.analysis,
            result=event.result,
            error_code=event.error_code,
        )
    if isinstance(event, RuntimeFederatedQueryInput):
        return RuntimeFederatedQuery(
            sequence=event.sequence,
            call_id=event.call_id,
            status=event.status,
            statement_sha256=event.statement_sha256,
            consumes=event.consumes,
            result=event.result,
            error_code=event.error_code,
            executor=event.executor,
            input_frames=event.input_frames,
            analysis=event.analysis,
        )
    if isinstance(event, RuntimeMongoAttemptInput):
        return RuntimeMongoAttempt(
            sequence=event.sequence,
            call_id=event.call_id,
            status=event.status,
            source=event.source,
            operation=event.operation,
            request_sha256=event.request_sha256,
            inputs=tuple(_runtime_input_reference(graph, node_id) for node_id in event.inputs),
            result=event.result,
            error_code=event.error_code,
        )
    return RuntimeSQLAttempt(
        sequence=event.sequence,
        call_id=event.call_id,
        status=event.status,
        source=event.source,
        dialect=event.dialect,
        statement_sha256=event.statement_sha256,
        inputs=tuple(_runtime_input_reference(graph, node_id) for node_id in event.inputs),
        duration_ms=event.duration_ms,
        result=event.result,
        error_code=event.error_code,
    )


def _runtime_input_reference(graph: GraphDocument, node_id: str) -> RuntimeInputReference:
    nodes = graph.node_by_id()
    node = nodes.get(node_id)
    if node is None or node.type not in {"field", "table", "view"}:
        raise LineageFailure(
            "runtime_input_not_found",
            f"Runtime input is not a table, view, or field in graph {graph.name}: {node_id}",
        )
    return RuntimeInputReference(
        node_id=node.id,
        reference=_runtime_graph_reference(graph, node, nodes),
        kind=node.type,
    )


def _runtime_graph_reference(
    graph: GraphDocument,
    node: GraphNode,
    nodes: dict[str, GraphNode],
) -> str:
    if node.type != "field":
        return f"{graph.catalog}.{node.label}"
    parent_id = node.metadata.get("object_id")
    parent = nodes.get(parent_id) if isinstance(parent_id, str) else None
    if parent is None or parent.type not in {"table", "view"}:
        raise LineageFailure(
            "invalid_runtime_lineage_graph",
            f"Runtime field input has no table or view parent: {node.id}",
        )
    return f"{graph.catalog}.{parent.label}.{node.label}"
