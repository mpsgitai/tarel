"""Caller-observed logical operations; no executable plans or implied artifact approval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from tarel.lineage.contracts import LineageFailure

if TYPE_CHECKING:
    from tarel.lineage.runtime import (
        RuntimeAnalysisEvidence,
        RuntimeAnalysisInputFrame,
        RuntimeExecutor,
        RuntimeResultEvidence,
    )

_OPERATION_ARTIFACTS = {
    "extract": "logical_topology",
    "explode": "logical_topology",
    "reference_mapping": "reference_mapping",
    "object_binding": "object_binding",
    "family_resolution": "object_family",
    "hierarchy_rollup": "semantic_concept",
    "context_expand": "context_expansion",
}
_OPERATIONS = frozenset(_OPERATION_ARTIFACTS)
_ARTIFACT_KINDS = frozenset(_OPERATION_ARTIFACTS.values())
_METADATA_OPERATIONS = frozenset({"family_resolution", "context_expand"})


@dataclass(frozen=True, slots=True)
class RuntimeLogicalArtifactReference:
    kind: str
    graph: str
    id: str
    revision: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "graph": self.graph, "id": self.id, "revision": self.revision}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeLogicalArtifactReference:
        # Local imports keep the shared event validation in one place without
        # making the legacy runtime contracts depend on an eagerly imported adapter.
        from tarel.lineage.runtime import _choice, _fields, _safe_code, _sha256

        _fields(data, {"kind", "graph", "id", "revision"}, "logical artifact reference")
        return cls(
            kind=_choice(data.get("kind"), "logical artifact kind", _ARTIFACT_KINDS),
            graph=_safe_code(data.get("graph"), "logical artifact graph"),
            id=_safe_code(data.get("id"), "logical artifact id"),
            revision=_sha256(data.get("revision"), "logical artifact revision"),
        )


@dataclass(frozen=True, slots=True)
class RuntimeLogicalOperation:
    """Identical input/stored shape: historical artifact claims need no live graph rewrite."""

    sequence: int
    call_id: str
    status: str
    operation: str
    operation_sha256: str
    consumes: tuple[str, ...]
    dependency_refs: tuple[RuntimeLogicalArtifactReference, ...]
    executor: RuntimeExecutor
    input_frames: tuple[RuntimeAnalysisInputFrame, ...]
    analysis: RuntimeAnalysisEvidence
    result: RuntimeResultEvidence | None = None
    error_code: str | None = None
    artifact_validation: str = "caller_claimed"

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "logical_operation",
            "sequence": self.sequence,
            "call_id": self.call_id,
            "status": self.status,
            "operation": self.operation,
            "operation_sha256": self.operation_sha256,
            "consumes": list(self.consumes),
            "dependency_refs": [item.to_dict() for item in self.dependency_refs],
            "executor": self.executor.to_dict(),
            "inputs": [item.to_dict() for item in self.input_frames],
            "analysis": self.analysis.to_dict(),
            "result": self.result.to_dict() if self.result else None,
            "error_code": self.error_code,
            "artifact_validation": self.artifact_validation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeLogicalOperation:
        from tarel.lineage.runtime import (
            _FEDERATED_STATUSES,
            _MAX_INPUTS,
            _analysis_metadata,
            _analysis_result,
            _choice,
            _fields,
            _integer,
            _objects,
            _sha256,
            _strings,
            _text,
        )

        _fields(
            data,
            {
                "kind",
                "sequence",
                "call_id",
                "status",
                "operation",
                "operation_sha256",
                "consumes",
                "dependency_refs",
                "executor",
                "inputs",
                "analysis",
                "result",
                "error_code",
                "artifact_validation",
            },
            "logical operation",
        )
        if (
            data.get("kind") != "logical_operation"
            or data.get("artifact_validation") != "caller_claimed"
        ):
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Logical operations require kind logical_operation "
                "and caller_claimed artifact validation.",
            )
        operation = _choice(data.get("operation"), "logical operation", _OPERATIONS)
        status = _choice(data.get("status"), "logical operation status", _FEDERATED_STATUSES)
        result, error_code = _analysis_result(data, status=status, label="logical operation")
        consumes = _strings(data.get("consumes"), "logical operation consumes", limit=_MAX_INPUTS)
        if len(consumes) != len(set(consumes)) or (
            not consumes and operation not in _METADATA_OPERATIONS
        ):
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Logical data operations require unique prior calls; "
                "only metadata resolution may start a run.",
            )
        refs = tuple(
            RuntimeLogicalArtifactReference.from_dict(item)
            for item in _objects(data.get("dependency_refs"), "logical dependency references")
        )
        if not 1 <= len(refs) <= 32 or len(refs) != len(set(refs)):
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Logical operations require 1–32 unique artifact references.",
            )
        if _OPERATION_ARTIFACTS[operation] not in {item.kind for item in refs}:
            raise LineageFailure(
                "invalid_runtime_lineage", "Logical operation requires its matching artifact kind."
            )
        executor, inputs, analysis = _analysis_metadata(
            data, consumes=consumes, status=status, required=True
        )
        if executor is None or analysis is None:
            raise LineageFailure(
                "invalid_runtime_lineage", "Logical operation metadata is required."
            )
        return cls(
            sequence=_integer(data.get("sequence"), "logical event sequence", minimum=1),
            call_id=_text(data.get("call_id"), "logical event call_id"),
            status=status,
            operation=operation,
            operation_sha256=_sha256(data.get("operation_sha256"), "operation_sha256"),
            consumes=consumes,
            dependency_refs=refs,
            executor=executor,
            input_frames=inputs,
            analysis=analysis,
            result=result,
            error_code=error_code,
        )
