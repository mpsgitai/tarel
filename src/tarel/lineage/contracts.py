"""Dependency-free persisted contracts for reviewed static lineage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tarel.errors import TarelError

_CONTRACT_VERSION = "tarel.lineage.v0.5"
_READABLE_CONTRACT_VERSIONS = frozenset(
    {_CONTRACT_VERSION, "tarel.lineage.v0.4", "tarel.lineage.v0.3", "tarel.lineage.v0.2"}
)
_DEFINITION_KINDS = frozenset({"procedure", "query", "script"})
_OPERATIONS = frozenset({"call", "read"})
_WRITE_OPERATIONS = frozenset({"delete", "insert", "merge", "select_into", "truncate", "update"})
_SOURCE_ROLES = frozenset(
    {"audit", "business_data", "control", "deduplication", "filter", "lookup", "unknown"}
)
_EXCLUSION_KINDS = frozenset({"dynamic_sql", "local_intermediate", "unresolved"})
_STATES = frozenset({"draft", "rejected", "review_required", "validated"})
_MATERIALIZATION_MODES = frozenset({"incremental", "table", "view"})


class LineageFailure(TarelError):
    """Raised when a lineage operation is rejected."""


@dataclass(frozen=True, slots=True)
class LineageEvidence:
    source: str
    reference: str
    reason: str
    line_start: int
    line_end: int

    def to_dict(self) -> dict[str, object]:
        return {
            "line_end": self.line_end,
            "line_start": self.line_start,
            "reason": self.reason,
            "reference": self.reference,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class LineageWriteSource:
    target: str
    role: str
    via: tuple[str, ...]
    evidence: LineageEvidence

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence": self.evidence.to_dict(),
            "role": self.role,
            "target": self.target,
            "via": list(self.via),
        }


@dataclass(frozen=True, slots=True)
class LineageExcludedWrite:
    operation: str
    target: str
    disposition: str
    evidence: LineageEvidence

    def to_dict(self) -> dict[str, object]:
        return {
            "disposition": self.disposition,
            "evidence": self.evidence.to_dict(),
            "operation": self.operation,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class LineageReview:
    decision: str
    reason: str
    source: str = "human"

    def to_dict(self) -> dict[str, str]:
        return {"decision": self.decision, "reason": self.reason, "source": self.source}


@dataclass(frozen=True, slots=True)
class LineageDefinition:
    id: str
    external_id: str
    kind: str
    name: str
    qualified_name: str
    language: str
    source_reference: str
    content_hash: str
    revision: str

    def to_dict(self) -> dict[str, str]:
        return {
            "content_hash": self.content_hash,
            "external_id": self.external_id,
            "id": self.id,
            "kind": self.kind,
            "language": self.language,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "revision": self.revision,
            "source_reference": self.source_reference,
        }


@dataclass(frozen=True, slots=True)
class LineageStep:
    id: str
    external_id: str
    name: str
    definition_id: str
    depends_on: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "definition_id": self.definition_id,
            "depends_on": list(self.depends_on),
            "external_id": self.external_id,
            "id": self.id,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class LineageAnalysis:
    definition_id: str
    definition_revision: str
    summary: str
    warnings: tuple[str, ...]
    excluded_writes: tuple[LineageExcludedWrite, ...] = ()
    analyzer: str = "coding_agent"
    analyzer_version: str | None = None
    dialect: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "analyzer": self.analyzer,
            "analyzer_version": self.analyzer_version,
            "definition_id": self.definition_id,
            "definition_revision": self.definition_revision,
            "dialect": self.dialect,
            "excluded_writes": [item.to_dict() for item in self.excluded_writes],
            "summary": self.summary,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class LineageAnalysisFailure:
    definition_id: str
    definition_revision: str
    code: str
    provider: str
    model: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "definition_id": self.definition_id,
            "definition_revision": self.definition_revision,
            "model": self.model,
            "provider": self.provider,
        }


@dataclass(frozen=True, slots=True)
class LineageClaim:
    id: str
    definition_id: str
    operation: str
    target: str
    state: str
    evidence: LineageEvidence
    reviews: tuple[LineageReview, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "definition_id": self.definition_id,
            "evidence": self.evidence.to_dict(),
            "id": self.id,
            "operation": self.operation,
            "reviews": [item.to_dict() for item in self.reviews],
            "state": self.state,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class LineageWriteUnit:
    id: str
    definition_id: str
    operation: str
    target: str
    state: str
    evidence: LineageEvidence
    sources: tuple[LineageWriteSource, ...]
    warnings: tuple[str, ...] = ()
    reviews: tuple[LineageReview, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "definition_id": self.definition_id,
            "evidence": self.evidence.to_dict(),
            "id": self.id,
            "operation": self.operation,
            "reviews": [item.to_dict() for item in self.reviews],
            "sources": [item.to_dict() for item in self.sources],
            "state": self.state,
            "target": self.target,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class LineageMaterialization:
    id: str
    definition_id: str
    target: str
    mode: str
    state: str
    evidence: LineageEvidence
    reviews: tuple[LineageReview, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "definition_id": self.definition_id,
            "evidence": self.evidence.to_dict(),
            "id": self.id,
            "mode": self.mode,
            "reviews": [item.to_dict() for item in self.reviews],
            "state": self.state,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class LineageDocument:
    name: str
    source_kind: str
    source_name: str
    source_reference: str
    source_revision: str
    workflow_id: str
    workflow_name: str
    definitions: tuple[LineageDefinition, ...]
    steps: tuple[LineageStep, ...]
    analyses: tuple[LineageAnalysis, ...] = ()
    analysis_failures: tuple[LineageAnalysisFailure, ...] = ()
    claims: tuple[LineageClaim, ...] = ()
    write_units: tuple[LineageWriteUnit, ...] = ()
    materializations: tuple[LineageMaterialization, ...] = ()
    contract_version: str = _CONTRACT_VERSION

    def definition_by_id(self) -> dict[str, LineageDefinition]:
        return {item.id: item for item in self.definitions}

    def claim_by_id(self) -> dict[str, LineageClaim]:
        return {item.id: item for item in self.claims}

    def to_dict(self) -> dict[str, object]:
        return {
            "analysis_failures": [item.to_dict() for item in self.analysis_failures],
            "analyses": [item.to_dict() for item in self.analyses],
            "claims": [item.to_dict() for item in self.claims],
            "contract_version": self.contract_version,
            "definitions": [item.to_dict() for item in self.definitions],
            "materializations": [item.to_dict() for item in self.materializations],
            "name": self.name,
            "source_kind": self.source_kind,
            "source_name": self.source_name,
            "source_reference": self.source_reference,
            "source_revision": self.source_revision,
            "steps": [item.to_dict() for item in self.steps],
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "write_units": [item.to_dict() for item in self.write_units],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineageDocument:
        contract_version = data.get("contract_version")
        if contract_version not in _READABLE_CONTRACT_VERSIONS:
            raise LineageFailure("unsupported_lineage", "Unsupported TAREL lineage contract.")
        if contract_version == "tarel.lineage.v0.2":
            data = {**data, "analysis_failures": []}
        if contract_version in {"tarel.lineage.v0.2", "tarel.lineage.v0.3"}:
            data = {**data, "materializations": []}
        if contract_version in {
            "tarel.lineage.v0.2",
            "tarel.lineage.v0.3",
            "tarel.lineage.v0.4",
        }:
            data = {
                **data,
                "analyses": [
                    {
                        **item,
                        "analyzer": "coding_agent",
                        "analyzer_version": None,
                        "dialect": None,
                    }
                    for item in _objects(data.get("analyses"), "analyses")
                ],
            }
        _fields(
            data,
            {
                "analysis_failures",
                "analyses",
                "claims",
                "contract_version",
                "definitions",
                "materializations",
                "name",
                "source_kind",
                "source_name",
                "source_reference",
                "source_revision",
                "steps",
                "workflow_id",
                "workflow_name",
                "write_units",
            },
            "document",
        )
        try:
            document = cls(
                name=_text_value(data.get("name"), "name"),
                source_kind=_text_value(data.get("source_kind"), "source_kind"),
                source_name=_text_value(data.get("source_name"), "source_name"),
                source_reference=_text_value(data.get("source_reference"), "source_reference"),
                source_revision=_text_value(data.get("source_revision"), "source_revision"),
                workflow_id=_text_value(data.get("workflow_id"), "workflow_id"),
                workflow_name=_text_value(data.get("workflow_name"), "workflow_name"),
                definitions=tuple(
                    _definition(item) for item in _objects(data.get("definitions"), "definitions")
                ),
                materializations=tuple(
                    _materialization(item)
                    for item in _objects(data.get("materializations"), "materializations")
                ),
                steps=tuple(_step(item) for item in _objects(data.get("steps"), "steps")),
                analyses=tuple(
                    _analysis(item) for item in _objects(data.get("analyses"), "analyses")
                ),
                analysis_failures=tuple(
                    _analysis_failure(item)
                    for item in _objects(data.get("analysis_failures"), "analysis failures")
                ),
                claims=tuple(_claim(item) for item in _objects(data.get("claims"), "claims")),
                write_units=tuple(
                    _write_unit(item) for item in _objects(data.get("write_units"), "write_units")
                ),
            )
        except LineageFailure:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise LineageFailure("invalid_lineage", "Malformed lineage document.") from exc
        validate_lineage_document(document)
        return document


def validate_lineage_document(document: LineageDocument) -> None:
    """Raise ``LineageFailure`` unless every section of ``document`` is internally consistent."""
    _validate_header(document)
    _validate_definitions(document)
    definitions = document.definition_by_id()
    _validate_steps(document, definitions)
    _validate_analyses(document, definitions)
    _validate_claims(document, definitions)
    _validate_materializations(document, definitions)
    _validate_write_units(document, definitions)


def _validate_header(document: LineageDocument) -> None:
    """Workflow identity: names, references and the source revision."""
    for value, label in (
        (document.name, "name"),
        (document.source_kind, "source_kind"),
        (document.source_name, "source_name"),
        (document.source_reference, "source_reference"),
        (document.workflow_id, "workflow_id"),
        (document.workflow_name, "workflow_name"),
    ):
        _text_value(value, label)
    _sha256(document.source_revision, "source_revision")


def _validate_definitions(document: LineageDocument) -> None:
    """Definitions carry text identity, a supported kind and content hashes, all unique."""
    definition_ids: list[str] = []
    definition_external_ids: list[str] = []
    for definition in document.definitions:
        for value, label in (
            (definition.id, "definition id"),
            (definition.external_id, "definition external_id"),
            (definition.kind, "definition kind"),
            (definition.name, "definition name"),
            (definition.qualified_name, "definition qualified_name"),
            (definition.language, "definition language"),
            (definition.source_reference, "definition source_reference"),
        ):
            _text_value(value, label)
        if definition.kind not in _DEFINITION_KINDS:
            raise LineageFailure(
                "invalid_lineage", f"Unsupported definition kind: {definition.kind}"
            )
        _sha256(definition.content_hash, "definition content_hash")
        _sha256(definition.revision, "definition revision")
        definition_ids.append(definition.id)
        definition_external_ids.append(definition.external_id)
    _unique(definition_ids, "definition IDs")
    _unique(definition_external_ids, "definition external IDs")


def _validate_steps(document: LineageDocument, definitions: dict[str, LineageDefinition]) -> None:
    """Workflow steps reference known definitions and form an acyclic dependency graph."""
    step_ids: list[str] = []
    step_external_ids: list[str] = []
    for step in document.steps:
        for value, label in (
            (step.id, "step id"),
            (step.external_id, "step external_id"),
            (step.name, "step name"),
            (step.definition_id, "step definition_id"),
        ):
            _text_value(value, label)
        if step.definition_id not in definitions:
            raise LineageFailure(
                "invalid_lineage",
                "Workflow step references an unknown definition.",
            )
        if not all(isinstance(value, str) and value for value in step.depends_on):
            raise LineageFailure("invalid_lineage", "Step dependencies must be strings.")
        step_ids.append(step.id)
        step_external_ids.append(step.external_id)
    _unique(step_ids, "step IDs")
    _unique(step_external_ids, "step external IDs")
    _validate_step_graph(document.steps)


def _validate_analyses(
    document: LineageDocument, definitions: dict[str, LineageDefinition]
) -> None:
    """Each definition is analyzed or failed at its current revision, never both."""
    analysis_ids: list[str] = []
    for analysis in document.analyses:
        _text_value(analysis.definition_id, "analysis definition_id")
        if analysis.definition_id not in definitions:
            raise LineageFailure("invalid_lineage", "Analysis references an unknown definition.")
        _sha256(analysis.definition_revision, "analysis definition_revision")
        if analysis.definition_revision != definitions[analysis.definition_id].revision:
            raise LineageFailure(
                "invalid_lineage",
                "Analysis revision does not match its lineage definition.",
            )
        _text_value(analysis.summary, "analysis summary")
        _text_value(analysis.analyzer, "analysis analyzer")
        for optional_value, label in (
            (analysis.analyzer_version, "analysis analyzer_version"),
            (analysis.dialect, "analysis dialect"),
        ):
            if optional_value is not None:
                _text_value(optional_value, label)
        if not all(isinstance(value, str) for value in analysis.warnings):
            raise LineageFailure("invalid_lineage", "Analysis warnings must be strings.")
        for excluded in analysis.excluded_writes:
            if excluded.operation not in _WRITE_OPERATIONS:
                raise LineageFailure("invalid_lineage", "Invalid excluded-write operation.")
            if excluded.disposition not in _EXCLUSION_KINDS:
                raise LineageFailure("invalid_lineage", "Invalid excluded-write disposition.")
            _text_value(excluded.target, "excluded-write target")
            _validate_evidence(excluded.evidence)
        analysis_ids.append(analysis.definition_id)
    _unique(analysis_ids, "analysis definition IDs")

    failure_ids: list[str] = []
    for failure in document.analysis_failures:
        _text_value(failure.definition_id, "analysis failure definition_id")
        if failure.definition_id not in definitions:
            raise LineageFailure(
                "invalid_lineage",
                "Analysis failure references an unknown definition.",
            )
        _sha256(failure.definition_revision, "analysis failure definition_revision")
        if failure.definition_revision != definitions[failure.definition_id].revision:
            raise LineageFailure(
                "invalid_lineage",
                "Analysis failure revision does not match its lineage definition.",
            )
        _text_value(failure.code, "analysis failure code")
        _text_value(failure.provider, "analysis failure provider")
        if failure.model is not None:
            _text_value(failure.model, "analysis failure model")
        failure_ids.append(failure.definition_id)
    _unique(failure_ids, "analysis failure definition IDs")
    if set(failure_ids) & set(analysis_ids):
        raise LineageFailure(
            "invalid_lineage",
            "A definition cannot be both analyzed and failed.",
        )


def _validate_claims(document: LineageDocument, definitions: dict[str, LineageDefinition]) -> None:
    """Declared claims reference known definitions and carry evidence and reviews."""
    claim_ids: list[str] = []
    for claim in document.claims:
        for value, label in (
            (claim.id, "claim id"),
            (claim.definition_id, "claim definition_id"),
            (claim.operation, "claim operation"),
            (claim.target, "claim target"),
            (claim.state, "claim state"),
        ):
            _text_value(value, label)
        if claim.definition_id not in definitions:
            raise LineageFailure("invalid_lineage", "Claim references an unknown definition.")
        if claim.operation not in _OPERATIONS or claim.state not in _STATES:
            raise LineageFailure("invalid_lineage", "Unsupported claim operation or state.")
        _validate_evidence(claim.evidence)
        for review in claim.reviews:
            _text_value(review.decision, "review decision")
            _text_value(review.reason, "review reason")
            _text_value(review.source, "review source")
            if review.decision not in {"reject", "validate"} or review.source != "human":
                raise LineageFailure("invalid_lineage", "Invalid lineage review.")
        if claim.state == "draft" and claim.reviews:
            raise LineageFailure("invalid_lineage", "Draft claims cannot contain reviews.")
        if claim.state in {"rejected", "validated"}:
            expected = "reject" if claim.state == "rejected" else "validate"
            if not claim.reviews or claim.reviews[-1].decision != expected:
                raise LineageFailure("invalid_lineage", "Claim state requires a matching review.")
        claim_ids.append(claim.id)
    _unique(claim_ids, "claim IDs")


def _validate_materializations(
    document: LineageDocument, definitions: dict[str, LineageDefinition]
) -> None:
    """Materializations describe how a definition persists its target."""
    materialization_ids: list[str] = []
    materialized_definitions: list[str] = []
    for materialization in document.materializations:
        for value, label in (
            (materialization.id, "materialization id"),
            (materialization.definition_id, "materialization definition_id"),
            (materialization.target, "materialization target"),
            (materialization.mode, "materialization mode"),
            (materialization.state, "materialization state"),
        ):
            _text_value(value, label)
        if materialization.definition_id not in definitions:
            raise LineageFailure(
                "invalid_lineage",
                "Materialization references an unknown definition.",
            )
        if (
            materialization.mode not in _MATERIALIZATION_MODES
            or materialization.state not in _STATES
        ):
            raise LineageFailure(
                "invalid_lineage",
                "Unsupported materialization mode or state.",
            )
        _validate_evidence(materialization.evidence)
        _validate_reviews(materialization.state, materialization.reviews, "materialization")
        materialization_ids.append(materialization.id)
        materialized_definitions.append(materialization.definition_id)
    _unique(materialization_ids, "materialization IDs")
    _unique(materialized_definitions, "materialized definition IDs")


def _validate_write_units(
    document: LineageDocument, definitions: dict[str, LineageDefinition]
) -> None:
    """Write units describe persistent writes with their sources and exclusions."""
    write_unit_ids: list[str] = []
    for unit in document.write_units:
        for value, label in (
            (unit.id, "write-unit id"),
            (unit.definition_id, "write-unit definition_id"),
            (unit.operation, "write-unit operation"),
            (unit.target, "write-unit target"),
            (unit.state, "write-unit state"),
        ):
            _text_value(value, label)
        if unit.definition_id not in definitions:
            raise LineageFailure("invalid_lineage", "Write unit references an unknown definition.")
        if unit.operation not in _WRITE_OPERATIONS or unit.state not in _STATES:
            raise LineageFailure("invalid_lineage", "Unsupported write-unit operation or state.")
        _validate_evidence(unit.evidence)
        if not all(isinstance(value, str) for value in unit.warnings):
            raise LineageFailure("invalid_lineage", "Write-unit warnings must be strings.")
        source_keys = []
        for source in unit.sources:
            _text_value(source.target, "write source target")
            if source.role not in _SOURCE_ROLES:
                raise LineageFailure("invalid_lineage", "Unsupported write-source role.")
            if not all(isinstance(value, str) and value.strip() for value in source.via):
                raise LineageFailure("invalid_lineage", "Write-source via values must be strings.")
            _unique(list(source.via), "write-source via values")
            _validate_evidence(source.evidence)
            source_keys.append(
                (
                    source.target.casefold(),
                    source.evidence.line_start,
                    source.evidence.line_end,
                )
            )
        if len(source_keys) != len(set(source_keys)):
            raise LineageFailure("invalid_lineage", "Write unit contains duplicate sources.")
        _validate_reviews(unit.state, unit.reviews, "write unit")
        write_unit_ids.append(unit.id)
    _unique(write_unit_ids, "write-unit IDs")


def _definition(data: dict[str, Any]) -> LineageDefinition:
    _fields(
        data,
        {
            "content_hash",
            "external_id",
            "id",
            "kind",
            "language",
            "name",
            "qualified_name",
            "revision",
            "source_reference",
        },
        "definition",
    )
    return LineageDefinition(**data)


def _step(data: dict[str, Any]) -> LineageStep:
    _fields(data, {"definition_id", "depends_on", "external_id", "id", "name"}, "step")
    values = {key: value for key, value in data.items() if key != "depends_on"}
    return LineageStep(**values, depends_on=_strings(data.get("depends_on"), "step depends_on"))


def _analysis(data: dict[str, Any]) -> LineageAnalysis:
    _fields(
        data,
        {
            "analyzer",
            "analyzer_version",
            "definition_id",
            "definition_revision",
            "dialect",
            "excluded_writes",
            "summary",
            "warnings",
        },
        "analysis",
    )
    values = {
        key: value for key, value in data.items() if key not in {"excluded_writes", "warnings"}
    }
    for field in ("analyzer_version", "dialect"):
        value = values.get(field)
        if value is not None and not isinstance(value, str):
            raise LineageFailure(
                "invalid_lineage",
                f"Analysis {field} must be a string or null.",
            )
    return LineageAnalysis(
        **values,
        warnings=_strings(data.get("warnings"), "analysis warnings"),
        excluded_writes=tuple(
            _excluded_write(item)
            for item in _objects(data.get("excluded_writes"), "excluded_writes")
        ),
    )


def _analysis_failure(data: dict[str, Any]) -> LineageAnalysisFailure:
    _fields(
        data,
        {"code", "definition_id", "definition_revision", "model", "provider"},
        "analysis failure",
    )
    model = data.get("model")
    if model is not None and not isinstance(model, str):
        raise LineageFailure("invalid_lineage", "Analysis failure model must be a string or null.")
    return LineageAnalysisFailure(
        definition_id=data["definition_id"],
        definition_revision=data["definition_revision"],
        code=data["code"],
        provider=data["provider"],
        model=model,
    )


def _claim(data: dict[str, Any]) -> LineageClaim:
    _fields(
        data,
        {"definition_id", "evidence", "id", "operation", "reviews", "state", "target"},
        "claim",
    )
    reviews = tuple(_review(item) for item in _objects(data.get("reviews"), "claim reviews"))
    values = {key: value for key, value in data.items() if key not in {"evidence", "reviews"}}
    return LineageClaim(
        **values,
        evidence=_evidence(data.get("evidence"), "claim evidence"),
        reviews=reviews,
    )


def _materialization(data: dict[str, Any]) -> LineageMaterialization:
    _fields(
        data,
        {"definition_id", "evidence", "id", "mode", "reviews", "state", "target"},
        "materialization",
    )
    values = {key: value for key, value in data.items() if key not in {"evidence", "reviews"}}
    return LineageMaterialization(
        **values,
        evidence=_evidence(data.get("evidence"), "materialization evidence"),
        reviews=tuple(
            _review(item) for item in _objects(data.get("reviews"), "materialization reviews")
        ),
    )


def _write_unit(data: dict[str, Any]) -> LineageWriteUnit:
    _fields(
        data,
        {
            "definition_id",
            "evidence",
            "id",
            "operation",
            "reviews",
            "sources",
            "state",
            "target",
            "warnings",
        },
        "write unit",
    )
    evidence = _evidence(data.get("evidence"), "write-unit evidence")
    reviews = tuple(_review(item) for item in _objects(data.get("reviews"), "write-unit reviews"))
    values = {
        key: value
        for key, value in data.items()
        if key not in {"evidence", "reviews", "sources", "warnings"}
    }
    return LineageWriteUnit(
        **values,
        evidence=evidence,
        reviews=reviews,
        sources=tuple(
            _write_source(item) for item in _objects(data.get("sources"), "write-unit sources")
        ),
        warnings=_strings(data.get("warnings"), "write-unit warnings"),
    )


def _write_source(data: dict[str, Any]) -> LineageWriteSource:
    _fields(data, {"evidence", "role", "target", "via"}, "write source")
    return LineageWriteSource(
        target=data["target"],
        role=data["role"],
        via=_strings(data.get("via"), "write-source via"),
        evidence=_evidence(data.get("evidence"), "write-source evidence"),
    )


def _excluded_write(data: dict[str, Any]) -> LineageExcludedWrite:
    _fields(data, {"disposition", "evidence", "operation", "target"}, "excluded write")
    return LineageExcludedWrite(
        disposition=data["disposition"],
        operation=data["operation"],
        target=data["target"],
        evidence=_evidence(data.get("evidence"), "excluded-write evidence"),
    )


def _evidence(value: Any, label: str) -> LineageEvidence:
    if not isinstance(value, dict):
        raise LineageFailure("invalid_lineage", f"Lineage {label} must be an object.")
    _fields(value, {"line_end", "line_start", "reason", "reference", "source"}, label)
    return LineageEvidence(**value)


def _review(data: dict[str, Any]) -> LineageReview:
    _fields(data, {"decision", "reason", "source"}, "review")
    return LineageReview(**data)


def _validate_evidence(item: LineageEvidence) -> None:
    for value, label in (
        (item.source, "evidence source"),
        (item.reference, "evidence reference"),
        (item.reason, "evidence reason"),
    ):
        _text_value(value, label)
    if not _positive(item.line_start) or not _positive(item.line_end):
        raise LineageFailure("invalid_lineage", "Evidence lines must be positive integers.")
    if item.line_end < item.line_start:
        raise LineageFailure("invalid_lineage", "Evidence line range is invalid.")


def _validate_reviews(
    state: str,
    reviews: tuple[LineageReview, ...],
    label: str,
) -> None:
    for review in reviews:
        _text_value(review.decision, f"{label} review decision")
        _text_value(review.reason, f"{label} review reason")
        _text_value(review.source, f"{label} review source")
        if review.decision not in {"reject", "validate"} or review.source != "human":
            raise LineageFailure("invalid_lineage", f"Invalid {label} review.")
    if state == "draft" and reviews:
        raise LineageFailure("invalid_lineage", f"Draft {label} cannot contain reviews.")
    if state in {"rejected", "validated"}:
        expected = "reject" if state == "rejected" else "validate"
        if not reviews or reviews[-1].decision != expected:
            raise LineageFailure("invalid_lineage", f"{label.capitalize()} state requires review.")


def _validate_step_graph(steps: tuple[LineageStep, ...]) -> None:
    known = {item.id for item in steps}
    remaining: dict[str, set[str]] = {}
    for item in steps:
        dependencies = set(item.depends_on)
        if len(dependencies) != len(item.depends_on) or item.id in dependencies:
            raise LineageFailure("invalid_lineage", "Invalid workflow step dependencies.")
        if not dependencies <= known:
            raise LineageFailure("invalid_lineage", "Workflow step has unknown dependencies.")
        remaining[item.id] = dependencies
    while remaining:
        ready = {key for key, values in remaining.items() if not values}
        if not ready:
            raise LineageFailure("invalid_lineage", "Workflow dependencies contain a cycle.")
        remaining = {key: values - ready for key, values in remaining.items() if key not in ready}


def _objects(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise LineageFailure("invalid_lineage", f"Lineage {label} must contain objects.")
    return value


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LineageFailure("invalid_lineage", f"Lineage {label} must contain strings.")
    return tuple(value)


def _fields(data: dict[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - set(data))
    unexpected = sorted(set(data) - expected)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unsupported: {', '.join(unexpected)}")
        raise LineageFailure(
            "invalid_lineage",
            f"Invalid lineage {label} fields ({'; '.join(details)}).",
        )


def _text_value(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LineageFailure("invalid_lineage", f"Lineage {label} must be a non-empty string.")
    return value


def _sha256(value: Any, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise LineageFailure("invalid_lineage", f"Lineage {label} must be a SHA-256 value.")


def _positive(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value > 0


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise LineageFailure("invalid_lineage", f"Lineage contains duplicate {label}.")
