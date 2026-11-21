"""Discovery programs: the declarative matching recipes a harness asks TAREL to evaluate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tarel.discovery._parse import (
    MAX_FIELDS,
    MAX_TRANSFORMS,
    bounded_integer,
    integer_array,
    optional_integer,
    optional_rate,
    require_choice,
    require_fields,
    require_sha256,
    require_text,
    string_array,
)
from tarel.discovery.contracts import (
    DISCOVERY_COMPARISONS,
    DISCOVERY_KINDS,
    DISCOVERY_SELF_PAIR_POLICIES,
    DISCOVERY_TRANSFORMS,
    REFERENCE_MAPPING_CARDINALITIES,
    DiscoveryFailure,
)
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.topology.endpoint_contracts import LogicalEndpointFailure


@dataclass(frozen=True, slots=True)
class DiscoveryTransform:
    kind: str
    start: int | None = None
    length: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "length": self.length, "start": self.start}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryTransform:
        require_fields(data, {"kind", "length", "start"}, "discovery transform")
        transform = cls(
            kind=require_choice(data.get("kind"), "transform kind", DISCOVERY_TRANSFORMS),
            start=optional_integer(data.get("start"), "transform start"),
            length=optional_integer(data.get("length"), "transform length"),
        )
        if transform.kind == "fixed_segment":
            if transform.start is None or transform.length is None or transform.length < 1:
                raise DiscoveryFailure(
                    "invalid_discovery",
                    "fixed_segment requires a non-negative start and a positive length.",
                )
        elif transform.start is not None or transform.length is not None:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Only fixed_segment accepts start and length parameters.",
            )
        return transform


@dataclass(frozen=True, slots=True)
class DiscoverySelfMatch:
    """Record identity semantics for comparisons within one graph object."""

    record_key_field: str
    pair_policy: str = "distinct_unordered"

    def to_dict(self) -> dict[str, str]:
        return {
            "pair_policy": self.pair_policy,
            "record_key_field": self.record_key_field,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoverySelfMatch:
        require_fields(data, {"pair_policy", "record_key_field"}, "self-match program")
        return cls(
            record_key_field=require_text(data.get("record_key_field"), "record_key_field"),
            pair_policy=require_choice(
                data.get("pair_policy"),
                "self-match pair policy",
                DISCOVERY_SELF_PAIR_POLICIES,
            ),
        )


@dataclass(frozen=True, slots=True)
class DiscoveryProgram:
    kind: str
    source_fields: tuple[str, ...]
    target_fields: tuple[str, ...]
    source_transforms: tuple[tuple[DiscoveryTransform, ...], ...]
    target_transforms: tuple[tuple[DiscoveryTransform, ...], ...]
    comparison: str
    blocking_field_indexes: tuple[int, ...]
    contradiction_field_indexes: tuple[int, ...]
    threshold: float | None = None
    self_match: DiscoverySelfMatch | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "blocking_field_indexes": list(self.blocking_field_indexes),
            "comparison": self.comparison,
            "contradiction_field_indexes": list(self.contradiction_field_indexes),
            "kind": self.kind,
            "source_fields": list(self.source_fields),
            "source_transforms": [
                [transform.to_dict() for transform in transforms]
                for transforms in self.source_transforms
            ],
            "target_fields": list(self.target_fields),
            "target_transforms": [
                [transform.to_dict() for transform in transforms]
                for transforms in self.target_transforms
            ],
            "threshold": self.threshold,
        }
        if self.self_match is not None:
            payload["self_match"] = self.self_match.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryProgram:
        require_fields(
            data,
            {
                "blocking_field_indexes",
                "comparison",
                "contradiction_field_indexes",
                "kind",
                "source_fields",
                "source_transforms",
                "target_fields",
                "target_transforms",
                "threshold",
            },
            "discovery program",
            optional={"self_match"},
        )
        self_match = data.get("self_match")
        if self_match is not None and not isinstance(self_match, dict):
            raise DiscoveryFailure(
                "invalid_discovery", "self_match must be an object or null."
            )
        program = cls(
            kind=require_choice(data.get("kind"), "discovery kind", DISCOVERY_KINDS),
            source_fields=string_array(data.get("source_fields"), "source_fields"),
            target_fields=string_array(data.get("target_fields"), "target_fields"),
            source_transforms=transform_matrix(
                data.get("source_transforms"), "source_transforms"
            ),
            target_transforms=transform_matrix(
                data.get("target_transforms"), "target_transforms"
            ),
            comparison=require_choice(
                data.get("comparison"), "comparison", DISCOVERY_COMPARISONS
            ),
            blocking_field_indexes=integer_array(
                data.get("blocking_field_indexes"), "blocking_field_indexes"
            ),
            contradiction_field_indexes=integer_array(
                data.get("contradiction_field_indexes"),
                "contradiction_field_indexes",
            ),
            threshold=optional_rate(data.get("threshold"), "threshold"),
            self_match=(
                DiscoverySelfMatch.from_dict(self_match)
                if isinstance(self_match, dict)
                else None
            ),
        )
        validate_discovery_program(program)
        return program


@dataclass(frozen=True, slots=True)
class ReferenceMappingProgram:
    """A directed physical-field mapping hypothesis."""

    source_field: str
    target_field: str
    cardinality: str
    kind: str = "reference_mapping"

    def to_dict(self) -> dict[str, object]:
        return {
            "cardinality": self.cardinality,
            "kind": self.kind,
            "source_field": self.source_field,
            "target_field": self.target_field,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceMappingProgram:
        require_fields(
            data,
            {
                "cardinality",
                "kind",
                "source_field",
                "target_field",
            },
            "reference-mapping program",
        )
        program = cls(
            source_field=require_text(data.get("source_field"), "source_field"),
            target_field=require_text(data.get("target_field"), "target_field"),
            cardinality=require_choice(
                data.get("cardinality"),
                "reference-mapping cardinality",
                REFERENCE_MAPPING_CARDINALITIES,
            ),
            kind=require_choice(
                data.get("kind"),
                "discovery kind",
                frozenset({"reference_mapping"}),
            ),
        )
        if program.source_field == program.target_field:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Reference mappings require different directed source and target fields.",
            )
        return program


@dataclass(frozen=True, slots=True)
class ReferenceMappingManifest:
    """Value-free identity and size of a caller-owned mapping artifact."""

    mapping_manifest_hash: str
    mapping_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "mapping_count": self.mapping_count,
            "mapping_manifest_hash": self.mapping_manifest_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceMappingManifest:
        require_fields(
            data,
            {"mapping_count", "mapping_manifest_hash"},
            "reference-mapping manifest",
        )
        return cls(
            mapping_manifest_hash=require_sha256(
                data.get("mapping_manifest_hash"), "mapping_manifest_hash"
            ),
            mapping_count=bounded_integer(
                data.get("mapping_count"), "mapping_count", 1, 1_000_000_000
            ),
        )


DiscoveryProgramType = DiscoveryProgram | ReferenceMappingProgram | LogicalJoinProgram


def discovery_program_from_dict(data: dict[str, Any]) -> DiscoveryProgramType:
    if "source_endpoints" in data or "target_endpoints" in data:
        try:
            return LogicalJoinProgram.from_dict(data)
        except LogicalEndpointFailure as exc:
            raise DiscoveryFailure(exc.code, str(exc)) from exc
    if data.get("kind") == "reference_mapping":
        return ReferenceMappingProgram.from_dict(data)
    return DiscoveryProgram.from_dict(data)


def validate_discovery_program(program: DiscoveryProgram) -> None:
    if program.kind == "reference_mapping":
        raise DiscoveryFailure(
            "invalid_discovery",
            "Reference mappings require the dedicated reference-mapping program.",
        )
    if not 1 <= len(program.source_fields) <= MAX_FIELDS:
        raise DiscoveryFailure(
            "invalid_discovery", "Discovery programs require between one and three fields."
        )
    if len(program.source_fields) != len(program.target_fields):
        raise DiscoveryFailure(
            "invalid_discovery", "Source and target field counts must match."
        )
    if len(program.source_fields) != len(program.source_transforms) or len(
        program.target_fields
    ) != len(program.target_transforms):
        raise DiscoveryFailure(
            "invalid_discovery", "Each field requires one transform list."
        )
    if len(set(program.source_fields)) != len(program.source_fields) or len(
        set(program.target_fields)
    ) != len(program.target_fields):
        raise DiscoveryFailure("invalid_discovery", "Program field references must be unique.")
    indexes = set(range(len(program.source_fields)))
    blocking = set(program.blocking_field_indexes)
    contradictions = set(program.contradiction_field_indexes)
    if not blocking.issubset(indexes) or not contradictions.issubset(indexes):
        raise DiscoveryFailure(
            "invalid_discovery", "Program field indexes must reference supplied field pairs."
        )
    if blocking & contradictions:
        raise DiscoveryFailure(
            "invalid_discovery", "Blocking and contradiction field indexes must be disjoint."
        )
    if program.kind == "join_discovery" and (blocking or contradictions):
        raise DiscoveryFailure(
            "invalid_discovery", "Join programs do not accept entity blocking or guards."
        )
    if program.kind == "join_discovery" and program.self_match is not None:
        raise DiscoveryFailure(
            "invalid_discovery", "Join programs do not accept self-entity semantics."
        )
    if program.kind == "join_discovery" and program.source_fields == program.target_fields:
        raise DiscoveryFailure(
            "invalid_discovery", "Join programs require different source and target fields."
        )
    if program.kind == "entity_matching":
        comparison_indexes = indexes - contradictions
        if not comparison_indexes:
            raise DiscoveryFailure(
                "invalid_discovery", "Entity programs require at least one comparison field."
            )
        if not blocking or not blocking.issubset(comparison_indexes):
            raise DiscoveryFailure(
                "invalid_discovery",
                "Entity programs require blocking indexes over comparison fields.",
            )
        if program.self_match is None and any(
            source == target
            for source, target in zip(
                program.source_fields, program.target_fields, strict=True
            )
        ):
            raise DiscoveryFailure(
                "invalid_discovery",
                "Equal entity field pairs require an explicit self_match program.",
            )
        if program.self_match is not None:
            if program.source_fields != program.target_fields:
                raise DiscoveryFailure(
                    "invalid_discovery",
                    "Self-entity programs require identical ordered source and target fields.",
                )
            if program.source_transforms != program.target_transforms:
                raise DiscoveryFailure(
                    "invalid_discovery",
                    "Self-entity programs require identical source and target transforms.",
                )
            if program.self_match.record_key_field in program.source_fields:
                raise DiscoveryFailure(
                    "invalid_discovery",
                    "The self-entity record key must be separate from comparison fields.",
                )
    for transforms in (*program.source_transforms, *program.target_transforms):
        if len(transforms) > MAX_TRANSFORMS:
            raise DiscoveryFailure(
                "invalid_discovery", "A field accepts at most eight transforms."
            )
        if len([item.kind for item in transforms]) != len(
            {item.kind for item in transforms}
        ):
            raise DiscoveryFailure(
                "invalid_discovery", "A field cannot repeat a transform kind."
            )
    fuzzy = {"normalized_levenshtein_v1", "token_set_ratio_v1"}
    if program.comparison in fuzzy:
        if program.kind != "entity_matching" or program.threshold is None:
            raise DiscoveryFailure(
                "invalid_discovery",
                "Fuzzy comparisons are entity-matching programs and require a threshold.",
            )
    elif program.threshold is not None:
        raise DiscoveryFailure(
            "invalid_discovery", "Exact comparisons do not accept a threshold."
        )
    if program.comparison == "llm_assessed":
        if program.kind != "entity_matching" or program.self_match is None:
            raise DiscoveryFailure(
                "invalid_discovery",
                "LLM-assessed identity groups require explicit Self-Entity semantics.",
            )
        if any((*program.source_transforms, *program.target_transforms)):
            raise DiscoveryFailure(
                "invalid_discovery",
                "LLM-assessed groups describe concrete keys, not an executable transform rule.",
            )
    if program.kind == "join_discovery" and program.comparison not in {
        "exact",
        "normalized_exact",
    }:
        raise DiscoveryFailure(
            "invalid_discovery", "Join discovery does not accept fuzzy equality semantics."
        )


def transform_matrix(value: object, label: str) -> tuple[tuple[DiscoveryTransform, ...], ...]:
    if not isinstance(value, list) or any(not isinstance(item, list) for item in value):
        raise DiscoveryFailure(
            "invalid_discovery", f"{label} must be an array of transform arrays."
        )
    rows: list[tuple[DiscoveryTransform, ...]] = []
    for row in value:
        if any(not isinstance(item, dict) for item in row):
            raise DiscoveryFailure(
                "invalid_discovery", f"{label} entries must be transform objects."
            )
        rows.append(tuple(DiscoveryTransform.from_dict(item) for item in row))
    return tuple(rows)
