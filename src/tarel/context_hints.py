"""Value-free logical hints projected into an optional context section."""

from __future__ import annotations

from dataclasses import dataclass, replace

from tarel.discovery.contracts import DiscoveryMetrics

LOGICAL_HINT_MODES = ("confirmed_only", "confirmed_then_candidates", "include_candidates")
_USAGE_NOTICE = (
    "Hints are metadata, not executable plans or joins. Load the referenced current artifact "
    "and use an authorized harness; runtime-validate exploratory hints."
)


@dataclass(frozen=True, slots=True)
class LogicalHintField:
    name: str
    data_type: str
    nullable: bool

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "data_type": self.data_type, "nullable": self.nullable}


@dataclass(frozen=True, slots=True)
class DerivationHintEvidence:
    level: str
    input_count: int
    output_count: int
    error_count: int
    truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "error_count": self.error_count,
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class DerivedRelationHint:
    graph: str
    relation_id: str
    document_revision: str
    source_object_id: str
    name: str
    state: str
    operations: tuple[str, ...]
    output_fields: tuple[LogicalHintField, ...]
    grain: tuple[str, ...]
    evidence: DerivationHintEvidence

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "derived_relation",
            "artifact": {
                "kind": "logical_topology",
                "graph": self.graph,
                "id": self.relation_id,
                "revision": self.document_revision,
            },
            "source_object_id": self.source_object_id,
            "name": self.name,
            "state": self.state,
            "usage": "confirmed" if self.state == "reviewed" else "exploratory_only",
            "requires_runtime_validation": self.state != "reviewed",
            "operations": list(self.operations),
            "output_fields": [field.to_dict() for field in self.output_fields],
            "grain": list(self.grain),
            "evidence": self.evidence.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class MappingHintEndpoint:
    object_id: str
    field_id: str
    reference: str

    def to_dict(self) -> dict[str, str]:
        return {
            "object_id": self.object_id,
            "field_id": self.field_id,
            "reference": self.reference,
        }


@dataclass(frozen=True, slots=True)
class MappingHintEvidence:
    level: str
    metrics: DiscoveryMetrics

    def to_dict(self) -> dict[str, object]:
        return {"level": self.level, "metrics": self.metrics.to_dict()}


@dataclass(frozen=True, slots=True)
class ReferenceMappingHint:
    graph: str
    candidate_id: str
    candidate_revision: str
    state: str
    source: MappingHintEndpoint
    target: MappingHintEndpoint
    cardinality: str
    mapping_count: int
    support: MappingHintEvidence
    challenge: MappingHintEvidence

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "reference_mapping",
            "artifact": {
                "kind": "reference_mapping",
                "graph": self.graph,
                "id": self.candidate_id,
                "revision": self.candidate_revision,
            },
            "state": self.state,
            "usage": "confirmed" if self.state == "reviewed" else "exploratory_only",
            "requires_runtime_validation": self.state != "reviewed",
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "cardinality": self.cardinality,
            "mapping_count": self.mapping_count,
            "support": self.support.to_dict(),
            "challenge": self.challenge.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ObjectFamilyHint:
    graph: str
    family_id: str
    revision: str
    name: str
    state: str
    member_count: int
    source_object_ids: tuple[str, ...]
    schema: tuple[LogicalHintField, ...]
    grain: tuple[str, ...]
    attributes: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "object_family",
            "artifact": {
                "kind": "object_family",
                "graph": self.graph,
                "id": self.family_id,
                "revision": self.revision,
            },
            "name": self.name,
            "state": self.state,
            "usage": "confirmed" if self.state == "reviewed" else "exploratory_only",
            "requires_runtime_validation": self.state != "reviewed",
            "member_count": self.member_count,
            "source_object_ids": list(self.source_object_ids),
            "schema": [field.to_dict() for field in self.schema],
            "grain": list(self.grain),
            "attributes": [
                {"name": name, "source": source, "data_type": "string"}
                for name, source in self.attributes
            ],
            "evidence": {"level": "schema_only"},
            "notice": (
                "Resolve a bounded member page explicitly. Grain is declared; "
                "schema compatibility does not prove row disjointness, uniqueness "
                "or semantic equivalence. No executable UNION or family-wide join."
            ),
        }


LogicalHint = DerivedRelationHint | ReferenceMappingHint | ObjectFamilyHint


@dataclass(frozen=True, slots=True)
class LogicalContextHints:
    mode: str
    items: tuple[LogicalHint, ...] = ()
    omissions: tuple[tuple[str, int], ...] = ()

    def stable_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "notice": _USAGE_NOTICE,
            "items": [item.to_dict() for item in self.items],
        }

    def dynamic_dict(self) -> dict[str, object]:
        return {
            "omissions": dict(self.omissions),
            "warnings": [
                "Stale logical hints were omitted; rebuild or re-evidence their artifacts."
            ]
            if dict(self.omissions).get("stale", 0)
            else [],
        }

    def trim_last(self) -> LogicalContextHints:
        return self.keep_first(len(self.items) - 1)

    def keep_first(self, count: int) -> LogicalContextHints:
        omissions = dict(self.omissions)
        removed = len(self.items) - count
        if removed:
            omissions["character_budget"] = omissions.get("character_budget", 0) + removed
        return replace(
            self,
            items=self.items[:count],
            omissions=tuple(sorted(omissions.items())),
        )
