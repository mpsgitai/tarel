"""Strict experimental contracts for graph-bound logical topology."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any, TypeAlias

LOGICAL_TOPOLOGY_CONTRACT_VERSION = "tarel.logical-topology.v0.1.experimental"
ENDPOINT_KINDS = frozenset({"graph_field", "graph_object", "step_output"})
STEP_KINDS = frozenset({"explode", "extract"})
OUTPUT_FIELD_KINDS = frozenset({"derived", "passthrough"})
EVIDENCE_LEVELS = frozenset({"population_tested", "proposed", "sample_tested"})
DERIVED_RELATION_STATES = frozenset({"candidate", "rejected", "reviewed"})

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DATA_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_. (),\[\]-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_STEPS = 64
_MAX_OUTPUT_FIELDS = 256
_MAX_EVIDENCE = 64


class LogicalTopologyFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class EndpointRef:
    """A graph node or a prior step output, identified without executable syntax."""

    kind: str
    id: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "kind": self.kind}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EndpointRef:
        _fields(data, {"id", "kind"}, "endpoint reference")
        return cls(
            kind=_choice(data.get("kind"), "endpoint kind", ENDPOINT_KINDS),
            id=_reference(data.get("id"), "endpoint id"),
        )


@dataclass(frozen=True, slots=True)
class StepOutput:
    id: str
    data_type: str
    nullable: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "data_type": self.data_type,
            "id": self.id,
            "nullable": self.nullable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepOutput:
        _fields(data, {"data_type", "id", "nullable"}, "step output")
        return cls(
            id=_identifier(data.get("id"), "step output id"),
            data_type=_data_type(data.get("data_type"), "step output data_type"),
            nullable=_boolean(data.get("nullable"), "step output nullable"),
        )


@dataclass(frozen=True, slots=True)
class ExtractStep:
    id: str
    input: EndpointRef
    pointer: str
    output: StepOutput
    kind: str = "extract"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "input": self.input.to_dict(),
            "kind": self.kind,
            "output": self.output.to_dict(),
            "pointer": self.pointer,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractStep:
        _fields(data, {"id", "input", "kind", "output", "pointer"}, "extract step")
        _choice(data.get("kind"), "step kind", frozenset({"extract"}))
        return cls(
            id=_identifier(data.get("id"), "step id"),
            input=EndpointRef.from_dict(_object(data.get("input"), "step input")),
            pointer=_json_pointer(data.get("pointer")),
            output=StepOutput.from_dict(_object(data.get("output"), "step output")),
        )


@dataclass(frozen=True, slots=True)
class ExplodeStep:
    id: str
    input: EndpointRef
    pointer: str
    output: StepOutput
    ordinal_output: StepOutput | None = None
    kind: str = "explode"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "input": self.input.to_dict(),
            "kind": self.kind,
            "ordinal_output": (
                self.ordinal_output.to_dict() if self.ordinal_output is not None else None
            ),
            "output": self.output.to_dict(),
            "pointer": self.pointer,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExplodeStep:
        _fields(
            data,
            {"id", "input", "kind", "ordinal_output", "output", "pointer"},
            "explode step",
        )
        _choice(data.get("kind"), "step kind", frozenset({"explode"}))
        ordinal = data.get("ordinal_output")
        if ordinal is not None and not isinstance(ordinal, dict):
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "explode ordinal_output must be an object or null.",
            )
        return cls(
            id=_identifier(data.get("id"), "step id"),
            input=EndpointRef.from_dict(_object(data.get("input"), "step input")),
            pointer=_json_pointer(data.get("pointer")),
            output=StepOutput.from_dict(_object(data.get("output"), "step output")),
            ordinal_output=(StepOutput.from_dict(ordinal) if isinstance(ordinal, dict) else None),
        )


DerivedStep: TypeAlias = ExtractStep | ExplodeStep


def step_from_dict(data: dict[str, Any]) -> DerivedStep:
    kind = data.get("kind")
    if kind == "extract":
        return ExtractStep.from_dict(data)
    if kind == "explode":
        return ExplodeStep.from_dict(data)
    raise LogicalTopologyFailure(
        "invalid_logical_topology",
        f"Unsupported step kind: {kind}",
    )


@dataclass(frozen=True, slots=True)
class OutputField:
    id: str
    name: str
    data_type: str
    nullable: bool
    kind: str
    source: EndpointRef

    def to_dict(self) -> dict[str, object]:
        return {
            "data_type": self.data_type,
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "nullable": self.nullable,
            "source": self.source.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OutputField:
        _fields(
            data,
            {"data_type", "id", "kind", "name", "nullable", "source"},
            "output field",
        )
        field = cls(
            id=_identifier(data.get("id"), "output field id"),
            name=_identifier(data.get("name"), "output field name"),
            data_type=_data_type(data.get("data_type"), "output field data_type"),
            nullable=_boolean(data.get("nullable"), "output field nullable"),
            kind=_choice(data.get("kind"), "output field kind", OUTPUT_FIELD_KINDS),
            source=EndpointRef.from_dict(_object(data.get("source"), "output source")),
        )
        expected_source_kind = "graph_field" if field.kind == "passthrough" else "step_output"
        if field.source.kind != expected_source_kind:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                f"{field.kind} output fields require a {expected_source_kind} source.",
            )
        return field


@dataclass(frozen=True, slots=True)
class Grain:
    field_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {"field_ids": list(self.field_ids)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Grain:
        _fields(data, {"field_ids"}, "grain")
        field_ids = _identifier_array(data.get("field_ids"), "grain field_ids")
        if not field_ids:
            raise LogicalTopologyFailure(
                "invalid_logical_topology", "A derived relation requires a non-empty grain."
            )
        return cls(field_ids=field_ids)


@dataclass(frozen=True, slots=True)
class ExecutorProvenance:
    name: str
    version: str
    implementation_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "implementation_sha256": self.implementation_sha256,
            "name": self.name,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutorProvenance:
        _fields(
            data,
            {"implementation_sha256", "name", "version"},
            "executor provenance",
        )
        return cls(
            name=_identifier(data.get("name"), "executor name"),
            version=_text(data.get("version"), "executor version", limit=64),
            implementation_sha256=_sha256(
                data.get("implementation_sha256"), "executor implementation_sha256"
            ),
        )


@dataclass(frozen=True, slots=True)
class DerivationEvidence:
    id: str
    level: str
    plan_revision: str
    input_count: int
    output_count: int
    error_count: int
    input_manifest_sha256: str | None
    output_manifest_sha256: str | None
    truncated: bool
    executor: ExecutorProvenance

    def to_dict(self) -> dict[str, object]:
        return {
            "error_count": self.error_count,
            "executor": self.executor.to_dict(),
            "id": self.id,
            "input_count": self.input_count,
            "input_manifest_sha256": self.input_manifest_sha256,
            "level": self.level,
            "output_count": self.output_count,
            "output_manifest_sha256": self.output_manifest_sha256,
            "plan_revision": self.plan_revision,
            "truncated": self.truncated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DerivationEvidence:
        _fields(
            data,
            {
                "error_count",
                "executor",
                "id",
                "input_count",
                "input_manifest_sha256",
                "level",
                "output_count",
                "output_manifest_sha256",
                "plan_revision",
                "truncated",
            },
            "derivation evidence",
        )
        evidence = cls(
            id=_identifier(data.get("id"), "evidence id"),
            level=_choice(data.get("level"), "evidence level", EVIDENCE_LEVELS),
            plan_revision=_sha256(data.get("plan_revision"), "evidence plan_revision"),
            input_count=_integer(data.get("input_count"), "evidence input_count"),
            output_count=_integer(data.get("output_count"), "evidence output_count"),
            error_count=_integer(data.get("error_count"), "evidence error_count"),
            input_manifest_sha256=_optional_sha256(
                data.get("input_manifest_sha256"), "evidence input_manifest_sha256"
            ),
            output_manifest_sha256=_optional_sha256(
                data.get("output_manifest_sha256"), "evidence output_manifest_sha256"
            ),
            truncated=_boolean(data.get("truncated"), "evidence truncated"),
            executor=ExecutorProvenance.from_dict(
                _object(data.get("executor"), "evidence executor")
            ),
        )
        if evidence.error_count > evidence.input_count:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "Evidence error_count cannot exceed input_count.",
            )
        measured = evidence.input_count or evidence.output_count or evidence.error_count
        if evidence.level == "proposed" and (
            measured
            or evidence.input_manifest_sha256 is not None
            or evidence.output_manifest_sha256 is not None
            or evidence.truncated
        ):
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "Proposed evidence cannot claim measured rows.",
            )
        if evidence.level != "proposed":
            if evidence.input_count == 0 or evidence.error_count == evidence.input_count:
                raise LogicalTopologyFailure(
                    "invalid_logical_topology",
                    "Tested evidence requires at least one successfully evaluated input row.",
                )
            if (
                evidence.input_manifest_sha256 is None
                or evidence.output_manifest_sha256 is None
            ):
                raise LogicalTopologyFailure(
                    "invalid_logical_topology",
                    "Tested evidence requires input and output manifest hashes.",
                )
        if evidence.level == "population_tested" and evidence.truncated:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "Population-tested evidence cannot be truncated.",
            )
        return evidence


@dataclass(frozen=True, slots=True)
class DerivedRelationReview:
    decision: str
    reason: str
    source: str = "human"

    def to_dict(self) -> dict[str, str]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DerivedRelationReview:
        _fields(data, {"decision", "reason", "source"}, "derived relation review")
        if data.get("source") != "human":
            raise LogicalTopologyFailure(
                "invalid_logical_topology", "Derived-relation review source must be human."
            )
        return cls(
            decision=_choice(
                data.get("decision"), "review decision", frozenset({"approve", "reject"})
            ),
            reason=_text(data.get("reason"), "review reason", limit=1_000),
        )


@dataclass(frozen=True, slots=True)
class DerivedRelation:
    id: str
    name: str
    source: EndpointRef
    steps: tuple[DerivedStep, ...]
    output_schema: tuple[OutputField, ...]
    grain: Grain
    evidence: tuple[DerivationEvidence, ...]
    state: str = "candidate"
    review: DerivedRelationReview | None = None

    @property
    def plan_revision(self) -> str:
        return _revision(self._plan_dict())

    def _plan_dict(self) -> dict[str, object]:
        return {
            "grain": self.grain.to_dict(),
            "id": self.id,
            "name": self.name,
            "output_schema": [field.to_dict() for field in self.output_schema],
            "source": self.source.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._plan_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "plan_revision": self.plan_revision,
            "review": self.review.to_dict() if self.review is not None else None,
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DerivedRelation:
        _fields(
            data,
            {
                "evidence",
                "grain",
                "id",
                "name",
                "output_schema",
                "plan_revision",
                "review",
                "source",
                "state",
                "steps",
            },
            "derived relation",
        )
        steps = _object_array(data.get("steps"), "derived relation steps")
        output_schema = _object_array(
            data.get("output_schema"), "derived relation output_schema"
        )
        evidence = _object_array(data.get("evidence"), "derived relation evidence")
        review = data.get("review")
        if review is not None and not isinstance(review, dict):
            raise LogicalTopologyFailure(
                "invalid_logical_topology", "Derived relation review must be an object or null."
            )
        relation = cls(
            id=_identifier(data.get("id"), "derived relation id"),
            name=_identifier(data.get("name"), "derived relation name"),
            source=EndpointRef.from_dict(_object(data.get("source"), "relation source")),
            steps=tuple(step_from_dict(item) for item in steps),
            output_schema=tuple(OutputField.from_dict(item) for item in output_schema),
            grain=Grain.from_dict(_object(data.get("grain"), "relation grain")),
            evidence=tuple(DerivationEvidence.from_dict(item) for item in evidence),
            state=_choice(
                data.get("state"), "derived relation state", DERIVED_RELATION_STATES
            ),
            review=(
                DerivedRelationReview.from_dict(review) if isinstance(review, dict) else None
            ),
        )
        validate_derived_relation(relation)
        if data.get("plan_revision") != relation.plan_revision:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "Derived relation plan_revision does not match its plan.",
            )
        return relation


@dataclass(frozen=True, slots=True)
class LogicalTopologyDocument:
    graph_name: str
    graph_revision: str
    derived_relations: tuple[DerivedRelation, ...]
    contract_version: str = LOGICAL_TOPOLOGY_CONTRACT_VERSION

    @property
    def revision(self) -> str:
        return _revision(self.to_dict(include_revision=False))

    def to_dict(self, *, include_revision: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": self.contract_version,
            "derived_relations": [item.to_dict() for item in self.derived_relations],
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
        }
        if include_revision:
            payload["revision"] = self.revision
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogicalTopologyDocument:
        _fields(
            data,
            {"contract_version", "derived_relations", "graph"},
            "logical topology document",
            optional={"revision"},
        )
        if data.get("contract_version") != LOGICAL_TOPOLOGY_CONTRACT_VERSION:
            raise LogicalTopologyFailure(
                "unsupported_logical_topology",
                "Unsupported TAREL logical-topology contract.",
            )
        graph = _object(data.get("graph"), "logical topology graph")
        _fields(graph, {"name", "revision"}, "logical topology graph")
        relations = _object_array(data.get("derived_relations"), "derived_relations")
        document = cls(
            graph_name=_identifier(graph.get("name"), "graph name"),
            graph_revision=_sha256(graph.get("revision"), "graph revision"),
            derived_relations=tuple(DerivedRelation.from_dict(item) for item in relations),
        )
        validate_logical_topology(document)
        expected_revision = data.get("revision")
        if expected_revision is not None and expected_revision != document.revision:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "Logical-topology revision does not match its content.",
            )
        return document


def validate_derived_relation(relation: DerivedRelation) -> None:
    _identifier(relation.id, "derived relation id")
    _identifier(relation.name, "derived relation name")
    source = EndpointRef.from_dict(relation.source.to_dict())
    if source.kind != "graph_object":
        raise LogicalTopologyFailure(
            "invalid_logical_topology", "A derived relation source must be a graph_object."
        )
    if not relation.steps or len(relation.steps) > _MAX_STEPS:
        raise LogicalTopologyFailure(
            "invalid_logical_topology",
            f"A derived relation requires between 1 and {_MAX_STEPS} steps.",
        )
    if not relation.output_schema or len(relation.output_schema) > _MAX_OUTPUT_FIELDS:
        raise LogicalTopologyFailure(
            "invalid_logical_topology",
            f"A derived relation requires between 1 and {_MAX_OUTPUT_FIELDS} output fields.",
        )
    if not relation.evidence or len(relation.evidence) > _MAX_EVIDENCE:
        raise LogicalTopologyFailure(
            "invalid_logical_topology",
            f"A derived relation requires between 1 and {_MAX_EVIDENCE} evidence records.",
        )

    step_ids: set[str] = set()
    available_outputs: dict[str, StepOutput] = {}
    for step in relation.steps:
        parsed = step_from_dict(step.to_dict())
        if parsed.id in step_ids:
            raise LogicalTopologyFailure(
                "invalid_logical_topology", "Derived relation step IDs must be unique."
            )
        step_ids.add(parsed.id)
        if parsed.input.kind == "step_output" and parsed.input.id not in available_outputs:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "A step may reference only a prior step output.",
            )
        if parsed.input.kind not in {"graph_field", "step_output"}:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "Steps may read only graph fields or prior step outputs.",
            )
        for output in _step_outputs(parsed):
            if output.id in available_outputs:
                raise LogicalTopologyFailure(
                    "invalid_logical_topology", "Step output IDs must be unique."
                )
            available_outputs[output.id] = output

    fields = tuple(OutputField.from_dict(item.to_dict()) for item in relation.output_schema)
    field_ids = [item.id for item in fields]
    field_names = [item.name for item in fields]
    if len(field_ids) != len(set(field_ids)) or len(field_names) != len(set(field_names)):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", "Output field IDs and names must be unique."
        )
    for field in fields:
        if field.kind == "derived":
            step_output = available_outputs.get(field.source.id)
            if step_output is None:
                raise LogicalTopologyFailure(
                    "invalid_logical_topology",
                    "A derived output field must reference a known step output.",
                )
            if (field.data_type, field.nullable) != (
                step_output.data_type,
                step_output.nullable,
            ):
                raise LogicalTopologyFailure(
                    "invalid_logical_topology",
                    "A derived output field must preserve its step output schema.",
                )
    if not any(field.kind == "derived" for field in fields):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", "A derived relation requires a derived output field."
        )

    grain = Grain.from_dict(relation.grain.to_dict())
    if not set(grain.field_ids).issubset(field_ids):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", "Grain keys must reference output field IDs."
        )
    evidence_ids: set[str] = set()
    for evidence in relation.evidence:
        parsed_evidence = DerivationEvidence.from_dict(evidence.to_dict())
        if parsed_evidence.id in evidence_ids:
            raise LogicalTopologyFailure(
                "invalid_logical_topology", "Evidence IDs must be unique per relation."
            )
        evidence_ids.add(parsed_evidence.id)
        if parsed_evidence.plan_revision != relation.plan_revision:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "Evidence plan_revision must match the derived relation plan.",
            )
    expected_decision = {"reviewed": "approve", "rejected": "reject"}.get(relation.state)
    if relation.state == "candidate" and relation.review is not None:
        raise LogicalTopologyFailure(
            "invalid_logical_topology", "A candidate derived relation cannot contain a review."
        )
    if expected_decision is not None and (
        relation.review is None or relation.review.decision != expected_decision
    ):
        raise LogicalTopologyFailure(
            "invalid_logical_topology",
            f"Derived relation state {relation.state} requires a matching human review.",
        )
    if relation.review is not None:
        DerivedRelationReview.from_dict(relation.review.to_dict())


def review_derived_relation(
    relation: DerivedRelation,
    *,
    decision: str,
    reason: str,
) -> DerivedRelation:
    if relation.state != "candidate":
        raise LogicalTopologyFailure(
            "derived_relation_already_reviewed",
            f"Derived relation is already {relation.state}: {relation.id}",
        )
    review = DerivedRelationReview.from_dict(
        {"decision": decision, "reason": reason, "source": "human"}
    )
    changed = replace(
        relation,
        state="reviewed" if review.decision == "approve" else "rejected",
        review=review,
    )
    validate_derived_relation(changed)
    return changed


def validate_logical_topology(document: LogicalTopologyDocument) -> None:
    if document.contract_version != LOGICAL_TOPOLOGY_CONTRACT_VERSION:
        raise LogicalTopologyFailure(
            "unsupported_logical_topology", "Unsupported TAREL logical-topology contract."
        )
    _identifier(document.graph_name, "graph name")
    _sha256(document.graph_revision, "graph revision")
    relation_ids: set[str] = set()
    relation_names: set[str] = set()
    for relation in document.derived_relations:
        validate_derived_relation(relation)
        if relation.id in relation_ids or relation.name in relation_names:
            raise LogicalTopologyFailure(
                "invalid_logical_topology",
                "Derived relation IDs and names must be unique per document.",
            )
        relation_ids.add(relation.id)
        relation_names.add(relation.name)


def _step_outputs(step: DerivedStep) -> tuple[StepOutput, ...]:
    if isinstance(step, ExplodeStep) and step.ordinal_output is not None:
        return (step.output, step.ordinal_output)
    return (step.output,)


def _revision(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _fields(
    data: dict[str, Any],
    required: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    if set(data) - allowed or required - set(data):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"{label} has unexpected or missing fields."
        )


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"{label} must be an object."
        )
    return value


def _object_array(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"{label} must be an array of objects."
        )
    return tuple(value)


def _text(value: object, label: str, *, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise LogicalTopologyFailure(
            "invalid_logical_topology",
            f"{label} must be a non-empty string of at most {limit} characters.",
        )
    if any(ord(character) < 32 for character in value):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"{label} may not contain control characters."
        )
    return value.strip()


def _identifier(value: object, label: str) -> str:
    clean = _text(value, label, limit=128)
    if not _IDENTIFIER.fullmatch(clean):
        raise LogicalTopologyFailure(
            "invalid_logical_topology",
            f"{label} may contain letters, numbers, dots, underscores, and hyphens.",
        )
    return clean


def _reference(value: object, label: str) -> str:
    return _text(value, label, limit=1_000)


def _data_type(value: object, label: str) -> str:
    clean = _text(value, label, limit=128)
    if not _DATA_TYPE.fullmatch(clean):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"{label} contains unsupported characters."
        )
    return clean


def _choice(value: object, label: str, choices: frozenset[str]) -> str:
    clean = _text(value, label)
    if clean not in choices:
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"Unsupported {label}: {clean}"
        )
    return clean


def _sha256(value: object, label: str) -> str:
    clean = _text(value, label, limit=64)
    if not _SHA256.fullmatch(clean):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"{label} must be a lowercase SHA-256 value."
        )
    return clean


def _optional_sha256(value: object, label: str) -> str | None:
    return None if value is None else _sha256(value, label)


def _identifier_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"{label} must be an array of identifiers."
        )
    identifiers = tuple(_identifier(item, label) for item in value)
    if len(identifiers) != len(set(identifiers)):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"{label} must contain unique identifiers."
        )
    return identifiers


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"{label} must be a boolean."
        )
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LogicalTopologyFailure(
            "invalid_logical_topology", f"{label} must be a non-negative integer."
        )
    return value


def _json_pointer(value: object) -> str:
    if not isinstance(value, str) or len(value) > 1_000:
        raise LogicalTopologyFailure(
            "invalid_logical_topology",
            "JSON pointer must be a string of at most 1000 characters.",
        )
    if value and not value.startswith("/"):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", "JSON pointer must be empty or start with '/'."
        )
    index = 0
    while index < len(value):
        if value[index] == "~" and (index + 1 == len(value) or value[index + 1] not in "01"):
            raise LogicalTopologyFailure(
                "invalid_logical_topology", "JSON pointer contains an invalid escape."
            )
        index += 1
    if any(ord(character) < 32 for character in value):
        raise LogicalTopologyFailure(
            "invalid_logical_topology", "JSON pointer may not contain control characters."
        )
    return value
