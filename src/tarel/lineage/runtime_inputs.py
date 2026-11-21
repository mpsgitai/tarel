"""Runtime lineage attempts: what a harness reports about one executed query or analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tarel.lineage._runtime_parse import (
    DIALECTS,
    FEDERATED_STATUSES,
    INPUT_VERSION,
    INPUT_VERSION_V2,
    INPUT_VERSION_V3,
    MAX_COLUMNS,
    MAX_INPUTS,
    MONGO_OPERATIONS,
    MONGO_STATUSES,
    RECONCILIATION_STATUSES,
    SQL_STATUSES,
    require_boolean,
    require_choice,
    require_fields,
    require_integer,
    require_object,
    require_objects,
    require_rate,
    require_safe_code,
    require_sha256,
    require_strings,
    require_text,
)
from tarel.lineage.contracts import LineageFailure


@dataclass(frozen=True, slots=True)
class RuntimeResultEvidence:
    columns: tuple[str, ...]
    row_count: int
    sha256: str
    truncated: bool | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "columns": list(self.columns),
            "row_count": self.row_count,
            "sha256": self.sha256,
        }
        if self.truncated is not None:
            result["truncated"] = self.truncated
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeResultEvidence:
        require_fields(
            data,
            {"columns", "row_count", "sha256"},
            "result",
            optional={"truncated"},
        )
        columns = require_strings(data.get("columns"), "result columns", limit=MAX_COLUMNS)
        if not columns or len(columns) != len({item.casefold() for item in columns}):
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Runtime result columns must be non-empty and unique.",
            )
        row_count = require_integer(data.get("row_count"), "result row_count", minimum=0)
        return cls(
            columns=columns,
            row_count=row_count,
            sha256=require_sha256(data.get("sha256"), "result sha256"),
            truncated=(
                require_boolean(data.get("truncated"), "result truncated")
                if "truncated" in data
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class RuntimeSQLAttemptInput:
    sequence: int
    call_id: str
    status: str
    source: str
    dialect: str
    statement_sha256: str
    inputs: tuple[str, ...]
    result: RuntimeResultEvidence | None = None
    error_code: str | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "call_id": self.call_id,
            "dialect": self.dialect,
            "error_code": self.error_code,
            "inputs": list(self.inputs),
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
    def from_dict(cls, data: dict[str, Any]) -> RuntimeSQLAttemptInput:
        require_fields(
            data,
            {
                "call_id",
                "dialect",
                "error_code",
                "inputs",
                "kind",
                "operation",
                "result",
                "sequence",
                "source",
                "statement_sha256",
                "status",
            },
            "SQL event",
            optional={"duration_ms"},
        )
        if data.get("kind") != "sql_query":
            raise LineageFailure(
                "invalid_runtime_lineage",
                "This runtime-lineage version supports only sql_query events.",
            )
        if data.get("operation") != "select":
            raise LineageFailure(
                "invalid_runtime_lineage",
                "This runtime-lineage version accepts only declared read-only SELECT attempts.",
            )
        status = require_choice(data.get("status"), "SQL event status", SQL_STATUSES)
        result_value = data.get("result")
        error_value = data.get("error_code")
        if status == "succeeded":
            if not isinstance(result_value, dict) or error_value is not None:
                raise LineageFailure(
                    "invalid_runtime_lineage",
                    "A succeeded SQL event requires result evidence and no error code.",
                )
            result = RuntimeResultEvidence.from_dict(result_value)
            error_code = None
        else:
            if result_value is not None or error_value is None:
                raise LineageFailure(
                    "invalid_runtime_lineage",
                    "A failed SQL event requires an error code and no result evidence.",
                )
            result = None
            error_code = require_safe_code(error_value, "SQL event error_code")
        inputs = require_strings(data.get("inputs"), "SQL event inputs", limit=MAX_INPUTS)
        if not inputs or len(inputs) != len(set(inputs)):
            raise LineageFailure(
                "invalid_runtime_lineage",
                "SQL event inputs must contain unique graph node IDs.",
            )
        return cls(
            sequence=require_integer(data.get("sequence"), "SQL event sequence", minimum=1),
            call_id=require_text(data.get("call_id"), "SQL event call_id"),
            status=status,
            source=require_safe_code(data.get("source"), "SQL event source"),
            dialect=require_choice(data.get("dialect"), "SQL event dialect", DIALECTS),
            statement_sha256=require_sha256(data.get("statement_sha256"), "statement_sha256"),
            inputs=inputs,
            duration_ms=(
                require_integer(data.get("duration_ms"), "SQL event duration_ms", minimum=0)
                if "duration_ms" in data
                else None
            ),
            result=result,
            error_code=error_code,
        )


@dataclass(frozen=True, slots=True)
class RuntimeMongoAttemptInput:
    sequence: int
    call_id: str
    status: str
    source: str
    operation: str
    request_sha256: str
    inputs: tuple[str, ...]
    result: RuntimeResultEvidence | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "call_id": self.call_id,
            "error_code": self.error_code,
            "inputs": list(self.inputs),
            "kind": "mongo_query",
            "operation": self.operation,
            "request_sha256": self.request_sha256,
            "result": self.result.to_dict() if self.result else None,
            "sequence": self.sequence,
            "source": self.source,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeMongoAttemptInput:
        require_fields(
            data,
            {
                "call_id",
                "error_code",
                "inputs",
                "kind",
                "operation",
                "request_sha256",
                "result",
                "sequence",
                "source",
                "status",
            },
            "MongoDB event",
        )
        if data.get("kind") != "mongo_query":
            raise LineageFailure(
                "invalid_runtime_lineage",
                "This runtime-lineage version supports only mongo_query events here.",
            )
        operation = require_choice(
            data.get("operation"),
            "MongoDB event operation",
            MONGO_OPERATIONS,
        )
        status = require_choice(data.get("status"), "MongoDB event status", MONGO_STATUSES)
        result_value = data.get("result")
        error_value = data.get("error_code")
        if status == "succeeded":
            if not isinstance(result_value, dict) or error_value is not None:
                raise LineageFailure(
                    "invalid_runtime_lineage",
                    "A succeeded MongoDB event requires result evidence and no error code.",
                )
            result = RuntimeResultEvidence.from_dict(result_value)
            error_code = None
        else:
            if result_value is not None or error_value is None:
                raise LineageFailure(
                    "invalid_runtime_lineage",
                    "A failed MongoDB event requires an error code and no result evidence.",
                )
            result = None
            error_code = require_safe_code(error_value, "MongoDB event error_code")
        inputs = require_strings(data.get("inputs"), "MongoDB event inputs", limit=MAX_INPUTS)
        if not inputs or len(inputs) != len(set(inputs)):
            raise LineageFailure(
                "invalid_runtime_lineage",
                "MongoDB event inputs must contain unique graph node IDs.",
            )
        return cls(
            sequence=require_integer(data.get("sequence"), "MongoDB event sequence", minimum=1),
            call_id=require_text(data.get("call_id"), "MongoDB event call_id"),
            status=status,
            source=require_safe_code(data.get("source"), "MongoDB event source"),
            operation=operation,
            request_sha256=require_sha256(data.get("request_sha256"), "request_sha256"),
            inputs=inputs,
            result=result,
            error_code=error_code,
        )


@dataclass(frozen=True, slots=True)
class RuntimeExecutor:
    plugin_id: str
    plugin_version: str

    def to_dict(self) -> dict[str, str]:
        return {"plugin_id": self.plugin_id, "plugin_version": self.plugin_version}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeExecutor:
        require_fields(data, {"plugin_id", "plugin_version"}, "analysis executor")
        return cls(
            plugin_id=require_safe_code(data.get("plugin_id"), "executor plugin_id"),
            plugin_version=require_safe_code(
                data.get("plugin_version"),
                "executor plugin_version",
            ),
        )


@dataclass(frozen=True, slots=True)
class RuntimeAnalysisInputFrame:
    call_id: str
    alias: str
    source: str
    frame_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "alias": self.alias,
            "call_id": self.call_id,
            "frame_sha256": self.frame_sha256,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeAnalysisInputFrame:
        require_fields(
            data,
            {"alias", "call_id", "frame_sha256", "source"},
            "analysis input frame",
        )
        return cls(
            call_id=require_text(data.get("call_id"), "analysis input call_id"),
            alias=require_safe_code(data.get("alias"), "analysis input alias"),
            source=require_safe_code(data.get("source"), "analysis input source"),
            frame_sha256=require_sha256(data.get("frame_sha256"), "frame_sha256"),
        )


@dataclass(frozen=True, slots=True)
class RuntimeAnalysisLimits:
    input_row_limit: int
    output_row_limit: int
    timeout_ms: int

    def to_dict(self) -> dict[str, int]:
        return {
            "input_row_limit": self.input_row_limit,
            "output_row_limit": self.output_row_limit,
            "timeout_ms": self.timeout_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeAnalysisLimits:
        require_fields(
            data,
            {"input_row_limit", "output_row_limit", "timeout_ms"},
            "analysis limits",
        )
        return cls(
            input_row_limit=require_integer(
                data.get("input_row_limit"),
                "analysis input_row_limit",
                minimum=1,
            ),
            output_row_limit=require_integer(
                data.get("output_row_limit"),
                "analysis output_row_limit",
                minimum=1,
            ),
            timeout_ms=require_integer(
                data.get("timeout_ms"),
                "analysis timeout_ms",
                minimum=1,
            ),
        )


@dataclass(frozen=True, slots=True)
class RuntimeAnalysisEvidence:
    grain: tuple[str, ...]
    join_coverage: float | None
    unmatched_counts: tuple[tuple[str, int], ...]
    reconciliation_status: str
    duration_ms: int
    limits: RuntimeAnalysisLimits

    def to_dict(self) -> dict[str, object]:
        return {
            "duration_ms": self.duration_ms,
            "grain": list(self.grain),
            "join_coverage": self.join_coverage,
            "limits": self.limits.to_dict(),
            "reconciliation_status": self.reconciliation_status,
            "unmatched_counts": dict(self.unmatched_counts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimeAnalysisEvidence:
        require_fields(
            data,
            {
                "duration_ms",
                "grain",
                "join_coverage",
                "limits",
                "reconciliation_status",
                "unmatched_counts",
            },
            "analysis evidence",
        )
        unmatched_value = data.get("unmatched_counts")
        if not isinstance(unmatched_value, dict):
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Analysis unmatched_counts must be an object.",
            )
        unmatched_counts = tuple(
            sorted(
                (
                    require_safe_code(alias, "unmatched-count alias"),
                    require_integer(count, "unmatched count", minimum=0),
                )
                for alias, count in unmatched_value.items()
            )
        )
        join_coverage_value = data.get("join_coverage")
        grain = require_strings(data.get("grain"), "analysis grain", limit=MAX_COLUMNS)
        if len(grain) != len({item.casefold() for item in grain}):
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Analysis grain fields must be unique.",
            )
        return cls(
            grain=grain,
            join_coverage=(
                require_rate(join_coverage_value, "analysis join_coverage")
                if join_coverage_value is not None
                else None
            ),
            unmatched_counts=unmatched_counts,
            reconciliation_status=require_choice(
                data.get("reconciliation_status"),
                "analysis reconciliation_status",
                RECONCILIATION_STATUSES,
            ),
            duration_ms=require_integer(
                data.get("duration_ms"),
                "analysis duration_ms",
                minimum=0,
            ),
            limits=RuntimeAnalysisLimits.from_dict(
                require_object(data.get("limits"), "analysis limits")
            ),
        )


@dataclass(frozen=True, slots=True)
class RuntimeFederatedQueryInput:
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
        payload: dict[str, object] = {
            "call_id": self.call_id,
            "consumes": list(self.consumes),
            "engine": "duckdb",
            "error_code": self.error_code,
            "kind": "federated_query",
            "operation": "select",
            "result": self.result.to_dict() if self.result else None,
            "sequence": self.sequence,
            "statement_sha256": self.statement_sha256,
            "status": self.status,
        }
        if self.executor is not None and self.analysis is not None:
            payload["analysis"] = self.analysis.to_dict()
            payload["executor"] = self.executor.to_dict()
            payload["inputs"] = [item.to_dict() for item in self.input_frames]
        return payload

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        contract_version: str = INPUT_VERSION,
    ) -> RuntimeFederatedQueryInput:
        version_two = contract_version in {INPUT_VERSION_V2, INPUT_VERSION_V3}
        analysis_fields = {"analysis", "executor", "inputs"}
        require_fields(
            data,
            {
                "call_id",
                "consumes",
                "engine",
                "error_code",
                "kind",
                "operation",
                "result",
                "sequence",
                "statement_sha256",
                "status",
            }
            | (analysis_fields if version_two else set()),
            "federated event",
        )
        if data.get("kind") != "federated_query" or data.get("engine") != "duckdb":
            raise LineageFailure(
                "invalid_runtime_lineage",
                "This runtime-lineage version supports only DuckDB federated_query events.",
            )
        if data.get("operation") != "select":
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Federated runtime lineage accepts only declared read-only SELECT attempts.",
            )
        status = require_choice(
            data.get("status"),
            "federated event status",
            FEDERATED_STATUSES,
        )
        result_value = data.get("result")
        error_value = data.get("error_code")
        if status in {"accepted", "succeeded"}:
            if not isinstance(result_value, dict) or error_value is not None:
                raise LineageFailure(
                    "invalid_runtime_lineage",
                    "A successful federated event requires result evidence and no error code.",
                )
            result = RuntimeResultEvidence.from_dict(result_value)
            error_code = None
        else:
            if result_value is not None or error_value is None:
                raise LineageFailure(
                    "invalid_runtime_lineage",
                    "A failed federated event requires an error code and no result evidence.",
                )
            result = None
            error_code = require_safe_code(error_value, "federated event error_code")
        consumes = require_strings(
            data.get("consumes"),
            "federated event consumes",
            limit=MAX_INPUTS,
        )
        if not consumes or len(consumes) != len(set(consumes)):
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Federated events must consume unique prior call IDs.",
            )
        executor, input_frames, analysis = analysis_metadata(
            data,
            consumes=consumes,
            status=status,
            required=version_two,
        )
        return cls(
            sequence=require_integer(data.get("sequence"), "federated event sequence", minimum=1),
            call_id=require_text(data.get("call_id"), "federated event call_id"),
            status=status,
            statement_sha256=require_sha256(data.get("statement_sha256"), "statement_sha256"),
            consumes=consumes,
            result=result,
            error_code=error_code,
            executor=executor,
            input_frames=input_frames,
            analysis=analysis,
        )


@dataclass(frozen=True, slots=True)
class RuntimePythonAnalysisInput:
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
        return {
            "analysis": self.analysis.to_dict(),
            "call_id": self.call_id,
            "code_sha256": self.code_sha256,
            "consumes": list(self.consumes),
            "error_code": self.error_code,
            "executor": self.executor.to_dict(),
            "inputs": [item.to_dict() for item in self.input_frames],
            "kind": "python_analysis",
            "operation": "analyze",
            "result": self.result.to_dict() if self.result else None,
            "sequence": self.sequence,
            "status": self.status,
            "tool_type": "python",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuntimePythonAnalysisInput:
        require_fields(
            data,
            {
                "analysis",
                "call_id",
                "code_sha256",
                "consumes",
                "error_code",
                "executor",
                "inputs",
                "kind",
                "operation",
                "result",
                "sequence",
                "status",
                "tool_type",
            },
            "Python analysis event",
        )
        if data.get("kind") != "python_analysis" or data.get("tool_type") != "python":
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Python analysis events require kind python_analysis and tool_type python.",
            )
        if data.get("operation") != "analyze":
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Python analysis events require operation analyze.",
            )
        status = require_choice(data.get("status"), "Python analysis status", FEDERATED_STATUSES)
        result, error_code = analysis_result(data, status=status, label="Python analysis")
        consumes = require_strings(
            data.get("consumes"),
            "Python analysis consumes",
            limit=MAX_INPUTS,
        )
        if not consumes or len(consumes) != len(set(consumes)):
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Python analysis events must consume unique prior call IDs.",
            )
        executor, input_frames, analysis = analysis_metadata(
            data,
            consumes=consumes,
            status=status,
            required=True,
        )
        if executor is None or analysis is None:
            raise LineageFailure(
                "invalid_runtime_lineage",
                "Python analysis metadata is required.",
            )
        return cls(
            sequence=require_integer(data.get("sequence"), "Python event sequence", minimum=1),
            call_id=require_text(data.get("call_id"), "Python event call_id"),
            status=status,
            code_sha256=require_sha256(data.get("code_sha256"), "code_sha256"),
            consumes=consumes,
            executor=executor,
            input_frames=input_frames,
            analysis=analysis,
            result=result,
            error_code=error_code,
        )


def analysis_result(
    data: dict[str, Any],
    *,
    status: str,
    label: str,
) -> tuple[RuntimeResultEvidence | None, str | None]:
    result_value = data.get("result")
    error_value = data.get("error_code")
    if status in {"accepted", "succeeded"}:
        if not isinstance(result_value, dict) or error_value is not None:
            raise LineageFailure(
                "invalid_runtime_lineage",
                f"A successful {label} event requires result evidence and no error code.",
            )
        return RuntimeResultEvidence.from_dict(result_value), None
    if result_value is not None or error_value is None:
        raise LineageFailure(
            "invalid_runtime_lineage",
            f"A failed {label} event requires an error code and no result evidence.",
        )
    return None, require_safe_code(error_value, f"{label} error_code")


def analysis_metadata(
    data: dict[str, Any],
    *,
    consumes: tuple[str, ...],
    status: str,
    required: bool,
) -> tuple[
    RuntimeExecutor | None,
    tuple[RuntimeAnalysisInputFrame, ...],
    RuntimeAnalysisEvidence | None,
]:
    if not required:
        return None, (), None
    executor = RuntimeExecutor.from_dict(require_object(data.get("executor"), "analysis executor"))
    frames = tuple(
        RuntimeAnalysisInputFrame.from_dict(item)
        for item in require_objects(data.get("inputs"), "analysis inputs")
    )
    if tuple(item.call_id for item in frames) != consumes:
        raise LineageFailure(
            "invalid_runtime_lineage",
            "Analysis input call IDs must exactly match consumes in order.",
        )
    aliases = tuple(item.alias for item in frames)
    if len(aliases) != len(set(aliases)):
        raise LineageFailure(
            "invalid_runtime_lineage",
            "Analysis input aliases must be unique.",
        )
    analysis = RuntimeAnalysisEvidence.from_dict(
        require_object(data.get("analysis"), "analysis evidence")
    )
    unmatched_aliases = {alias for alias, _count in analysis.unmatched_counts}
    if not unmatched_aliases <= set(aliases):
        raise LineageFailure(
            "invalid_runtime_lineage",
            "Analysis unmatched-count aliases must identify declared input frames.",
        )
    if status in {"accepted", "succeeded"} and not analysis.grain:
        raise LineageFailure(
            "invalid_runtime_lineage",
            "Successful analysis events require a declared output grain.",
        )
    return executor, frames, analysis
