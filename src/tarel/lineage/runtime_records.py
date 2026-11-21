"""Runtime lineage records: reported events, the stored document and its traces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tarel.lineage._runtime_parse import (
    DOCUMENT_VERSION,
    DOCUMENT_VERSION_V2,
    DOCUMENT_VERSION_V3,
    DOCUMENT_VERSIONS,
    INPUT_VERSION,
    INPUT_VERSION_V2,
    INPUT_VERSION_V3,
    INPUT_VERSIONS,
    MAX_EVENTS,
    require_choice,
    require_fields,
    require_object,
    require_objects,
    require_sha256,
    require_text,
)
from tarel.lineage.contracts import LineageFailure
from tarel.lineage.runtime_inputs import (
    RuntimeAnalysisEvidence,
    RuntimeAnalysisInputFrame,
    RuntimeExecutor,
    RuntimeFederatedQueryInput,
    RuntimeMongoAttemptInput,
    RuntimePythonAnalysisInput,
    RuntimeResultEvidence,
    RuntimeSQLAttemptInput,
)
from tarel.lineage.runtime_logical import RuntimeLogicalOperation

RuntimeEventInput = (
    RuntimeSQLAttemptInput
    | RuntimeMongoAttemptInput
    | RuntimeFederatedQueryInput
    | RuntimePythonAnalysisInput
    | RuntimeLogicalOperation
)


@dataclass(frozen=True, slots=True)
class RuntimeLineageInput:
    run_id: str
    graph_name: str
    graph_revision: str
    events: tuple[RuntimeEventInput, ...]
    contract_version: str = INPUT_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "events": [item.to_dict() for item in self.events],
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "run_id": self.run_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeLineageInput:
        require_fields(data, {"contract_version", "events", "graph", "run_id"}, "runtime input")
        contract_version = data.get("contract_version")
        if not isinstance(contract_version, str) or contract_version not in INPUT_VERSIONS:
            raise LineageFailure(
                "unsupported_runtime_lineage",
                "Unsupported TAREL runtime-lineage input contract.",
            )
        graph = data.get("graph")
        if not isinstance(graph, dict):
            raise LineageFailure("invalid_runtime_lineage", "Runtime graph must be an object.")
        require_fields(graph, {"name", "revision"}, "runtime graph")
        events_value = data.get("events")
        if not isinstance(events_value, list) or not 1 <= len(events_value) <= MAX_EVENTS:
            raise LineageFailure(
                "invalid_runtime_lineage",
                f"Runtime input must contain between 1 and {MAX_EVENTS} events.",
            )
        events = tuple(
            _runtime_input_event(
                require_object(item, "runtime event"),
                contract_version=contract_version,
            )
            for item in events_value
        )
        _validate_event_identity(events)
        return cls(
            run_id=require_text(data.get("run_id"), "run_id"),
            graph_name=require_text(graph.get("name"), "graph name"),
            graph_revision=require_sha256(graph.get("revision"), "graph revision"),
            events=events,
            contract_version=contract_version,
        )


@dataclass(frozen=True, slots=True)
class RuntimeInputReference:
    node_id: str
    reference: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "node_id": self.node_id, "reference": self.reference}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeInputReference:
        require_fields(data, {"kind", "node_id", "reference"}, "runtime input reference")
        kind = require_choice(
            data.get("kind"),
            "runtime input kind",
            frozenset({"field", "table", "view"}),
        )
        return cls(
            node_id=require_text(data.get("node_id"), "runtime input node_id"),
            reference=require_text(data.get("reference"), "runtime input reference"),
            kind=kind,
        )


@dataclass(frozen=True, slots=True)
class RuntimeSQLAttempt:
    sequence: int
    call_id: str
    status: str
    source: str
    dialect: str
    statement_sha256: str
    inputs: tuple[RuntimeInputReference, ...]
    result: RuntimeResultEvidence | None = None
    error_code: str | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "call_id": self.call_id,
            "dialect": self.dialect,
            "error_code": self.error_code,
            "inputs": [item.to_dict() for item in self.inputs],
            "kind": "sql_query",
            "operation": "select",
            "result": self.result.to_dict() if self.result else None,
            "sequence": self.sequence,
            "source": self.source,
            "statement_sha256": self.statement_sha256,
            "status": self.status,
        }
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeSQLAttempt:
        inputs = require_objects(data.get("inputs"), "inputs")
        input_event = RuntimeSQLAttemptInput.from_dict(
            {**data, "inputs": [item.get("node_id") for item in inputs]}
        )
        references = tuple(
            RuntimeInputReference.from_dict(item) for item in inputs
        )
        return cls(
            sequence=input_event.sequence,
            call_id=input_event.call_id,
            status=input_event.status,
            source=input_event.source,
            dialect=input_event.dialect,
            statement_sha256=input_event.statement_sha256,
            inputs=references,
            duration_ms=input_event.duration_ms,
            result=input_event.result,
            error_code=input_event.error_code,
        )


@dataclass(frozen=True, slots=True)
class RuntimeMongoAttempt:
    sequence: int
    call_id: str
    status: str
    source: str
    operation: str
    request_sha256: str
    inputs: tuple[RuntimeInputReference, ...]
    result: RuntimeResultEvidence | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "call_id": self.call_id,
            "error_code": self.error_code,
            "inputs": [item.to_dict() for item in self.inputs],
            "kind": "mongo_query",
            "operation": self.operation,
            "request_sha256": self.request_sha256,
            "result": self.result.to_dict() if self.result else None,
            "sequence": self.sequence,
            "source": self.source,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeMongoAttempt:
        inputs = require_objects(data.get("inputs"), "inputs")
        input_event = RuntimeMongoAttemptInput.from_dict(
            {**data, "inputs": [item.get("node_id") for item in inputs]}
        )
        references = tuple(RuntimeInputReference.from_dict(item) for item in inputs)
        return cls(
            sequence=input_event.sequence,
            call_id=input_event.call_id,
            status=input_event.status,
            source=input_event.source,
            operation=input_event.operation,
            request_sha256=input_event.request_sha256,
            inputs=references,
            result=input_event.result,
            error_code=input_event.error_code,
        )


@dataclass(frozen=True, slots=True)
class RuntimeFederatedQuery:
    sequence: int
    call_id: str
    status: str
    statement_sha256: str
    consumes: tuple[str, ...]
    result: RuntimeResultEvidence | None = None
    error_code: str | None = None
    executor: RuntimeExecutor | None = None
    input_frames: tuple[RuntimeAnalysisInputFrame, ...] = ()
    analysis: RuntimeAnalysisEvidence | None = None

    def to_dict(self) -> dict[str, object]:
        return RuntimeFederatedQueryInput(
            sequence=self.sequence,
            call_id=self.call_id,
            status=self.status,
            statement_sha256=self.statement_sha256,
            consumes=self.consumes,
            result=self.result,
            error_code=self.error_code,
            executor=self.executor,
            input_frames=self.input_frames,
            analysis=self.analysis,
        ).to_dict()

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        contract_version: str = DOCUMENT_VERSION,
    ) -> RuntimeFederatedQuery:
        input_version = (
            INPUT_VERSION_V2
            if contract_version in {DOCUMENT_VERSION_V2, DOCUMENT_VERSION_V3}
            else INPUT_VERSION
        )
        event = RuntimeFederatedQueryInput.from_dict(
            data,
            contract_version=input_version,
        )
        return cls(
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


@dataclass(frozen=True, slots=True)
class RuntimePythonAnalysis:
    sequence: int
    call_id: str
    status: str
    code_sha256: str
    consumes: tuple[str, ...]
    executor: RuntimeExecutor
    input_frames: tuple[RuntimeAnalysisInputFrame, ...]
    analysis: RuntimeAnalysisEvidence
    result: RuntimeResultEvidence | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return RuntimePythonAnalysisInput(
            sequence=self.sequence,
            call_id=self.call_id,
            status=self.status,
            code_sha256=self.code_sha256,
            consumes=self.consumes,
            executor=self.executor,
            input_frames=self.input_frames,
            analysis=self.analysis,
            result=self.result,
            error_code=self.error_code,
        ).to_dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimePythonAnalysis:
        event = RuntimePythonAnalysisInput.from_dict(data)
        return cls(
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


RuntimeEvent = (
    RuntimeSQLAttempt | RuntimeMongoAttempt | RuntimeFederatedQuery | RuntimePythonAnalysis
    | RuntimeLogicalOperation
)


@dataclass(frozen=True, slots=True)
class RuntimeLineageDocument:
    name: str
    run_id: str
    graph_name: str
    graph_revision: str
    events: tuple[RuntimeEvent, ...]
    contract_version: str = DOCUMENT_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "events": [item.to_dict() for item in self.events],
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "name": self.name,
            "run_id": self.run_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeLineageDocument:
        require_fields(
            data,
            {"contract_version", "events", "graph", "name", "run_id"},
            "runtime document",
        )
        contract_version = data.get("contract_version")
        if not isinstance(contract_version, str) or contract_version not in DOCUMENT_VERSIONS:
            raise LineageFailure(
                "unsupported_runtime_lineage",
                "Unsupported TAREL runtime-lineage document contract.",
            )
        graph = require_object(data.get("graph"), "runtime graph")
        require_fields(graph, {"name", "revision"}, "runtime graph")
        events_value = data.get("events")
        if not isinstance(events_value, list) or not 1 <= len(events_value) <= MAX_EVENTS:
            raise LineageFailure(
                "invalid_runtime_lineage",
                f"Runtime document must contain between 1 and {MAX_EVENTS} events.",
            )
        events = tuple(
            _runtime_document_event(
                require_object(item, "runtime event"),
                contract_version=contract_version,
            )
            for item in events_value
        )
        _validate_event_identity(events)
        return cls(
            name=require_text(data.get("name"), "runtime lineage name"),
            run_id=require_text(data.get("run_id"), "run_id"),
            graph_name=require_text(graph.get("name"), "graph name"),
            graph_revision=require_sha256(graph.get("revision"), "graph revision"),
            events=events,
            contract_version=contract_version,
        )


@dataclass(frozen=True, slots=True)
class RuntimeTraceCall:
    call_id: str
    sequence: int
    kind: str
    status: str
    operation: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "call_id": self.call_id,
            "kind": self.kind,
            "sequence": self.sequence,
            "status": self.status,
        }
        if self.operation is not None:
            payload["operation"] = self.operation
            payload["artifact_validation"] = "caller_claimed"
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeDependency:
    source_call_id: str
    target_call_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source_call_id": self.source_call_id,
            "target_call_id": self.target_call_id,
        }


@dataclass(frozen=True, slots=True)
class RuntimeLineageTrace:
    runtime_lineage: str
    start_call_id: str
    graph_name: str
    graph_revision: str
    calls: tuple[RuntimeTraceCall, ...]
    dependencies: tuple[RuntimeDependency, ...]
    origins: tuple[RuntimeInputReference, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "calls": [item.to_dict() for item in self.calls],
            "dependencies": [item.to_dict() for item in self.dependencies],
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "origins": [item.to_dict() for item in self.origins],
            "runtime_lineage": self.runtime_lineage,
            "start_call_id": self.start_call_id,
        }


def _validate_event_identity(
    events: tuple[RuntimeEventInput, ...] | tuple[RuntimeEvent, ...],
) -> None:
    sequences = tuple(item.sequence for item in events)
    if sequences != tuple(range(1, len(events) + 1)):
        raise LineageFailure(
            "invalid_runtime_lineage",
            "Runtime event sequences must be contiguous and start at 1.",
        )
    call_ids = tuple(item.call_id for item in events)
    if len(call_ids) != len(set(call_ids)):
        raise LineageFailure("invalid_runtime_lineage", "Runtime call IDs must be unique.")
    prior: dict[str, RuntimeEventInput | RuntimeEvent] = {}
    for event in events:
        if isinstance(
            event,
            (
                RuntimeFederatedQueryInput,
                RuntimeFederatedQuery,
                RuntimePythonAnalysisInput,
                RuntimePythonAnalysis,
                RuntimeLogicalOperation,
            ),
        ):
            frames = {item.call_id: item for item in event.input_frames}
            for call_id in event.consumes:
                dependency = prior.get(call_id)
                if dependency is None:
                    raise LineageFailure(
                        "invalid_runtime_lineage",
                        "Analysis events may consume only earlier calls in the same document.",
                    )
                if dependency.status not in {"accepted", "succeeded"}:
                    raise LineageFailure(
                        "invalid_runtime_lineage",
                        "Analysis events cannot consume failed runtime calls.",
                    )
                frame = frames.get(call_id)
                source = getattr(dependency, "source", None)
                if source is not None and frame is not None and frame.source != source:
                    raise LineageFailure(
                        "invalid_runtime_lineage",
                        "Analysis input source must match its consumed source call.",
                    )
        prior[event.call_id] = event


def _runtime_input_event(
    data: dict[str, Any],
    *,
    contract_version: str,
) -> RuntimeEventInput:
    kind = data.get("kind")
    if kind == "sql_query":
        return RuntimeSQLAttemptInput.from_dict(data)
    if kind == "mongo_query":
        return RuntimeMongoAttemptInput.from_dict(data)
    if kind == "federated_query":
        return RuntimeFederatedQueryInput.from_dict(
            data,
            contract_version=contract_version,
        )
    if kind == "python_analysis" and contract_version in {INPUT_VERSION_V2, INPUT_VERSION_V3}:
        return RuntimePythonAnalysisInput.from_dict(data)
    if kind == "logical_operation" and contract_version == INPUT_VERSION_V3:
        return RuntimeLogicalOperation.from_dict(data)
    raise LineageFailure("invalid_runtime_lineage", "Unsupported runtime event kind.")


def _runtime_document_event(
    data: dict[str, Any],
    *,
    contract_version: str,
) -> RuntimeEvent:
    kind = data.get("kind")
    if kind == "sql_query":
        return RuntimeSQLAttempt.from_dict(data)
    if kind == "mongo_query":
        return RuntimeMongoAttempt.from_dict(data)
    if kind == "federated_query":
        return RuntimeFederatedQuery.from_dict(
            data,
            contract_version=contract_version,
        )
    if kind == "python_analysis" and contract_version in {
        DOCUMENT_VERSION_V2, DOCUMENT_VERSION_V3,
    }:
        return RuntimePythonAnalysis.from_dict(data)
    if kind == "logical_operation" and contract_version == DOCUMENT_VERSION_V3:
        return RuntimeLogicalOperation.from_dict(data)
    raise LineageFailure("invalid_runtime_lineage", "Unsupported runtime event kind.")
