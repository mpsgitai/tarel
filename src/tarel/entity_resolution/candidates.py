"""Entity resolution candidates, their validation and review, and resolved matches."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any

from tarel.discovery.coverage import QueryLinkedEntityCoverage
from tarel.discovery.identity import EntityAliasGroup, IdentityFailure
from tarel.discovery.programs import DiscoveryProgram
from tarel.discovery.runs import DiscoveryExecution
from tarel.entity_resolution._parse import (
    require_choice,
    require_fields,
    require_identifier,
    require_object,
    require_sha256,
    require_text,
)
from tarel.entity_resolution.contracts import (
    ENTITY_RESOLUTION_CONTRACT_VERSIONS,
    ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION,
    ENTITY_RESOLUTION_STATES,
    EntityResolutionFailure,
)
from tarel.entity_resolution.evidence import (
    EntityResolutionEvidence,
    EntityResolutionProvenance,
    EntityResolutionQuality,
    EntityResolutionReview,
    EntityResolutionRule,
    SelfEntityMatch,
)


@dataclass(frozen=True, slots=True)
class EntityResolutionCandidate:
    id: str
    graph_name: str
    graph_revision: str
    source_field_id: str
    target_field_id: str
    rule: EntityResolutionRule | None
    evidence: EntityResolutionEvidence
    provenance: EntityResolutionProvenance
    program: DiscoveryProgram | None = None
    execution: DiscoveryExecution | None = None
    quality: EntityResolutionQuality | None = None
    self_match: SelfEntityMatch | None = None
    identity_group: EntityAliasGroup | None = None
    state: str = "candidate"
    review: EntityResolutionReview | None = None
    contract_version: str = ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION

    @property
    def revision(self) -> str:
        payload = json.dumps(
            self.to_dict(include_revision=False),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def human_reviewed(self) -> bool:
        return self.review is not None

    def to_dict(
        self,
        *,
        include_revision: bool = True,
        include_identity_values: bool = True,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": self.contract_version,
            "evidence": self.evidence.to_dict(),
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "id": self.id,
            "provenance": self.provenance.to_dict(),
            "review": self.review.to_dict() if self.review else None,
            "source_field_id": self.source_field_id,
            "state": self.state,
            "target_field_id": self.target_field_id,
        }
        if self.contract_version == ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION:
            payload["rule"] = self.rule.to_dict() if self.rule else None
        else:
            payload["execution"] = self.execution.to_dict() if self.execution else None
            payload["program"] = self.program.to_dict() if self.program else None
            payload["quality"] = self.quality.to_dict() if self.quality else None
            if self.self_match is not None:
                payload["self_match"] = self.self_match.to_dict()
            if self.identity_group is not None:
                payload["identity_group"] = self.identity_group.to_dict(
                    include_members=include_identity_values
                )
        if include_revision:
            payload["revision"] = self.revision
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityResolutionCandidate:
        contract_version = data.get("contract_version")
        if contract_version not in ENTITY_RESOLUTION_CONTRACT_VERSIONS:
            raise EntityResolutionFailure(
                "unsupported_entity_resolution",
                "Unsupported TAREL entity-resolution candidate contract.",
            )
        common_fields = {
                "contract_version",
                "evidence",
                "graph",
                "id",
                "provenance",
                "review",
                "source_field_id",
                "state",
                "target_field_id",
        }
        version_fields = (
            {"rule"}
            if contract_version == ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION
            else {"execution", "program", "quality"}
        )
        require_fields(
            data,
            common_fields | version_fields,
            "entity-resolution candidate",
            optional={"identity_group", "revision", "self_match"},
        )
        graph = require_object(data.get("graph"), "candidate graph")
        require_fields(graph, {"name", "revision"}, "candidate graph")
        review_value = data.get("review")
        if review_value is not None and not isinstance(review_value, dict):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution review must be an object or null.",
            )
        program_value = data.get("program")
        execution_value = data.get("execution")
        quality_value = data.get("quality")
        self_match_value = data.get("self_match")
        if self_match_value is not None and not isinstance(self_match_value, dict):
            raise EntityResolutionFailure(
                "invalid_entity_resolution", "self_match must be an object or null."
            )
        identity_group_value = data.get("identity_group")
        if identity_group_value is not None and not isinstance(identity_group_value, dict):
            raise EntityResolutionFailure(
                "invalid_entity_resolution", "identity_group must be an object or null."
            )
        try:
            identity_group = (
                EntityAliasGroup.from_dict(identity_group_value)
                if isinstance(identity_group_value, dict)
                else None
            )
        except IdentityFailure as exc:
            raise EntityResolutionFailure("invalid_entity_resolution", str(exc)) from exc
        candidate = cls(
            id=require_identifier(data.get("id"), "candidate id"),
            graph_name=require_text(graph.get("name"), "graph name"),
            graph_revision=require_sha256(graph.get("revision"), "graph revision"),
            source_field_id=require_text(data.get("source_field_id"), "source_field_id"),
            target_field_id=require_text(data.get("target_field_id"), "target_field_id"),
            rule=(
                EntityResolutionRule.from_dict(require_object(data.get("rule"), "rule"))
                if contract_version == ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION
                else None
            ),
            evidence=EntityResolutionEvidence.from_dict(
                require_object(data.get("evidence"), "evidence")
            ),
            provenance=EntityResolutionProvenance.from_dict(
                require_object(data.get("provenance"), "provenance")
            ),
            program=(
                DiscoveryProgram.from_dict(require_object(program_value, "program"))
                if program_value is not None
                else None
            ),
            execution=(
                DiscoveryExecution.from_dict(require_object(execution_value, "execution"))
                if execution_value is not None
                else None
            ),
            quality=(
                EntityResolutionQuality.from_dict(require_object(quality_value, "quality"))
                if quality_value is not None
                else None
            ),
            self_match=(
                SelfEntityMatch.from_dict(self_match_value)
                if isinstance(self_match_value, dict)
                else None
            ),
            identity_group=identity_group,
            state=require_choice(data.get("state"), "candidate state", ENTITY_RESOLUTION_STATES),
            review=EntityResolutionReview.from_dict(review_value) if review_value else None,
            contract_version=str(contract_version),
        )
        validate_entity_resolution_candidate(candidate)
        expected_revision = data.get("revision")
        if expected_revision is not None and expected_revision != candidate.revision:
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution candidate revision does not match its content.",
            )
        return candidate


@dataclass(frozen=True, slots=True)
class EntityResolutionMatch:
    candidate: EntityResolutionCandidate
    source_reference: str
    target_reference: str
    query_linked_coverage: QueryLinkedEntityCoverage | None = None

    @property
    def usage(self) -> str:
        return "confirmed" if self.candidate.state == "reviewed" else "exploratory_only"

    @property
    def requires_runtime_validation(self) -> bool:
        return self.candidate.state != "reviewed"

    def to_dict(self) -> dict[str, object]:
        coverage_summary = (
            self.query_linked_coverage.to_summary_dict()
            if self.query_linked_coverage is not None
            else None
        )
        if coverage_summary is not None:
            coverage_summary["candidate_usage"] = self.usage
        return {
            "candidate": self.candidate.to_dict(include_identity_values=False),
            "requires_runtime_validation": self.requires_runtime_validation,
            "scope": "self_object" if self.candidate.self_match else "cross_object",
            "source": self.source_reference,
            "target": self.target_reference,
            "usage": self.usage,
            "query_linked_coverage": coverage_summary,
            "warning": (
                None
                if self.candidate.state == "reviewed"
                else "Unreviewed hypothesis; probe it at runtime before presenting a result."
            ),
        }


@dataclass(frozen=True, slots=True)
class EntityAliasMatch:
    candidate_id: str
    group: EntityAliasGroup
    state: str
    object_reference: str
    record_key_field: str

    @property
    def usage(self) -> str:
        return "confirmed" if self.state == "reviewed" else "exploratory_only"

    @property
    def requires_runtime_validation(self) -> bool:
        return self.state != "reviewed"

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "group": self.group.to_dict(),
            "object": self.object_reference,
            "record_key_field": self.record_key_field,
            "requires_runtime_validation": self.requires_runtime_validation,
            "state": self.state,
            "usage": self.usage,
            "warning": (
                None
                if self.state == "reviewed"
                else "Unreviewed alias group; validate it before presenting a result."
            ),
        }


def validate_entity_resolution_candidate(candidate: EntityResolutionCandidate) -> None:
    """Raise ``EntityResolutionFailure`` unless identity, program and review are consistent."""
    _validate_identity(candidate)
    _validate_legacy_contract(candidate)
    _validate_review(candidate)


def _validate_identity(candidate: EntityResolutionCandidate) -> None:
    """Contract version, identity, graph binding and the self-match rule."""
    if candidate.contract_version not in ENTITY_RESOLUTION_CONTRACT_VERSIONS:
        raise EntityResolutionFailure(
            "unsupported_entity_resolution",
            "Unsupported TAREL entity-resolution candidate contract.",
        )
    require_identifier(candidate.id, "candidate id")
    require_text(candidate.graph_name, "graph name")
    require_sha256(candidate.graph_revision, "graph revision")
    if candidate.source_field_id == candidate.target_field_id and candidate.self_match is None:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "Equal entity-resolution endpoints require explicit self-entity semantics.",
        )


def _validate_legacy_contract(candidate: EntityResolutionCandidate) -> None:
    """Rules that only the legacy contract version allowed or required."""
    if candidate.contract_version == ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION:
        if (
            candidate.rule is None
            or candidate.program is not None
            or candidate.execution is not None
            or candidate.quality is not None
            or candidate.self_match is not None
            or candidate.identity_group is not None
        ):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Legacy candidates require only the normalized-exact rule.",
            )
        EntityResolutionRule.from_dict(candidate.rule.to_dict())
    else:
        if (
            candidate.rule is not None
            or candidate.program is None
            or candidate.execution is None
            or candidate.quality is None
        ):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Discovery-derived candidates require program, execution, and quality.",
            )
        DiscoveryProgram.from_dict(candidate.program.to_dict())
        DiscoveryExecution.from_dict(candidate.execution.to_dict())
        EntityResolutionQuality.from_dict(candidate.quality.to_dict())
        if candidate.program.kind != "entity_matching":
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Entity-resolution programs must use entity-matching semantics.",
            )
        if (
            candidate.program.source_fields[0] != candidate.source_field_id
            or candidate.program.target_fields[0] != candidate.target_field_id
        ):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Primary entity-resolution endpoints must match the first program field pair.",
            )
        if (candidate.program.self_match is None) != (candidate.self_match is None):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Discovery and entity-resolution self-match semantics must agree.",
            )
        # The check above guarantees both self-match sides are present together.
        if candidate.self_match is not None and candidate.program.self_match is not None:
            SelfEntityMatch.from_dict(candidate.self_match.to_dict())
            comparison_indexes = tuple(
                index
                for index in range(len(candidate.program.source_fields))
                if index not in candidate.program.contradiction_field_indexes
            )
            expected_comparison = tuple(
                candidate.program.source_fields[index]
                for index in comparison_indexes
            )
            expected_contradictions = tuple(
                candidate.program.source_fields[index]
                for index in candidate.program.contradiction_field_indexes
            )
            if (
                candidate.source_field_id != candidate.target_field_id
                or candidate.self_match.record_key_field_id
                != candidate.program.self_match.record_key_field
                or candidate.self_match.comparison_field_ids != expected_comparison
                or candidate.self_match.contradiction_field_ids
                != expected_contradictions
                or candidate.self_match.pair_policy
                != candidate.program.self_match.pair_policy
            ):
                raise EntityResolutionFailure(
                    "invalid_entity_resolution",
                    "Self-entity projection does not match its discovery program.",
                )
        if candidate.identity_group is not None:
            try:
                EntityAliasGroup.from_dict(candidate.identity_group.to_dict())
            except IdentityFailure as exc:
                raise EntityResolutionFailure(
                    "invalid_entity_resolution", str(exc)
                ) from exc
            if (
                candidate.self_match is None
                or candidate.program.comparison != "llm_assessed"
                or candidate.identity_group.candidate_id
                != candidate.provenance.discovery_candidate_id
                or not candidate.provenance.source_names
            ):
                raise EntityResolutionFailure(
                    "invalid_entity_resolution",
                    "Persisted alias groups require their LLM-assessed Self-Entity candidate "
                    "and explicit source provenance.",
                )
        elif candidate.program.comparison == "llm_assessed":
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "LLM-assessed Self-Entity candidates require one concrete alias group.",
            )
        provenance = candidate.provenance
        if (
            provenance.discovery_candidate_id is None
            or provenance.discovery_run_revision is None
            or not provenance.observation_ids
            or provenance.promotion_reason is None
        ):
            raise EntityResolutionFailure(
                "invalid_entity_resolution",
                "Discovery-derived provenance is incomplete.",
            )


def _validate_review(candidate: EntityResolutionCandidate) -> None:
    """Evidence, provenance and the review decision agree with the candidate state."""
    EntityResolutionEvidence.from_dict(candidate.evidence.to_dict())
    EntityResolutionProvenance.from_dict(candidate.provenance.to_dict())
    if candidate.provenance.supersedes_candidate_id is not None and (
        candidate.self_match is None
        or candidate.provenance.supersedes_candidate_id == candidate.id
    ):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "Only Self-Entity evidence may supersede a different candidate.",
        )
    if candidate.state == "candidate" and candidate.review is not None:
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            "An unreviewed candidate cannot contain a human review.",
        )
    expected_decision = {"reviewed": "approve", "rejected": "reject"}.get(candidate.state)
    if expected_decision is not None and (
        candidate.review is None or candidate.review.decision != expected_decision
    ):
        raise EntityResolutionFailure(
            "invalid_entity_resolution",
            f"State {candidate.state} requires a matching human review.",
        )
    if candidate.review is not None:
        EntityResolutionReview.from_dict(candidate.review.to_dict())


def review_candidate(
    candidate: EntityResolutionCandidate,
    *,
    decision: str,
    reason: str,
) -> EntityResolutionCandidate:
    if candidate.state != "candidate":
        raise EntityResolutionFailure(
            "entity_resolution_already_reviewed",
            f"Entity-resolution candidate is already {candidate.state}: {candidate.id}",
        )
    review = EntityResolutionReview.from_dict(
        {"decision": decision, "reason": reason, "source": "human"}
    )
    changed = replace(
        candidate,
        state="reviewed" if decision == "approve" else "rejected",
        review=review,
    )
    validate_entity_resolution_candidate(changed)
    return changed
