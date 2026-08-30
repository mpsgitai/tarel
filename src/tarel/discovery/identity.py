"""Private, bounded contracts for optional Self-Entity discovery."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Any

IDENTITY_ACTIONS = frozenset(
    {
        "record_entity_group",
        "record_entity_reflection",
        "record_inventory_page",
        "register_identity_inventory",
    }
)
IDENTITY_REFLECTION_DECISIONS = frozenset(
    {
        "accept_as_exploratory",
        "recommend_promotion",
        "reject_group",
        "request_more_evidence",
    }
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@-]{0,255}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 2_000
_MAX_PAGES = 10_000
_MAX_PAGE_ATTEMPTS = 20_000
_MAX_GROUPS = 2_000
_MAX_GROUP_MEMBERS = 1_000
_MAX_REFLECTIONS = 4_000


class IdentityFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class IdentityInventoryManifest:
    """Hash-bound description of an ephemeral key/label identity inventory."""

    graph_name: str
    graph_revision: str
    source_name: str
    object_reference: str
    record_key_field: str
    label_field: str
    row_count: int
    identity_count: int
    inventory_hash: str
    estimated_tokens: int
    token_budget: int
    page_count: int

    @property
    def projected_fields(self) -> tuple[str, ...]:
        return self.record_key_field, self.label_field

    def to_dict(self) -> dict[str, object]:
        return {
            "estimated_tokens": self.estimated_tokens,
            "graph_name": self.graph_name,
            "graph_revision": self.graph_revision,
            "identity_count": self.identity_count,
            "inventory_hash": self.inventory_hash,
            "label_field": self.label_field,
            "object_reference": self.object_reference,
            "order": "label_then_key",
            "page_count": self.page_count,
            "record_key_field": self.record_key_field,
            "row_count": self.row_count,
            "source_name": self.source_name,
            "token_budget": self.token_budget,
            "truncated": False,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IdentityInventoryManifest:
        _fields(
            data,
            {
                "estimated_tokens",
                "graph_name",
                "graph_revision",
                "identity_count",
                "inventory_hash",
                "label_field",
                "object_reference",
                "order",
                "page_count",
                "record_key_field",
                "row_count",
                "source_name",
                "token_budget",
                "truncated",
            },
            "identity inventory manifest",
        )
        if data.get("order") != "label_then_key" or data.get("truncated") is not False:
            raise IdentityFailure(
                "invalid_identity_inventory",
                "Identity inventories require label_then_key ordering and truncated=false.",
            )
        manifest = cls(
            graph_name=_identifier(data.get("graph_name"), "graph_name"),
            graph_revision=_sha256(data.get("graph_revision"), "graph_revision"),
            source_name=_identifier(data.get("source_name"), "source_name"),
            object_reference=_text(data.get("object_reference"), "object_reference"),
            record_key_field=_text(data.get("record_key_field"), "record_key_field"),
            label_field=_text(data.get("label_field"), "label_field"),
            row_count=_integer(data.get("row_count"), "row_count"),
            identity_count=_integer(
                data.get("identity_count"), "identity_count"
            ),
            inventory_hash=_sha256(data.get("inventory_hash"), "inventory_hash"),
            estimated_tokens=_integer(
                data.get("estimated_tokens"), "estimated_tokens"
            ),
            token_budget=_integer(data.get("token_budget"), "token_budget", minimum=1),
            page_count=_bounded_integer(
                data.get("page_count"), "page_count", minimum=1, maximum=_MAX_PAGES
            ),
        )
        if len(manifest.projected_fields) != len(set(manifest.projected_fields)):
            raise IdentityFailure(
                "invalid_identity_inventory",
                "Record key and label field must be distinct.",
            )
        if manifest.identity_count > manifest.row_count:
            raise IdentityFailure(
                "invalid_identity_inventory",
                "Distinct key/label rows cannot exceed the source row count.",
            )
        if manifest.page_count == 1 and manifest.estimated_tokens > manifest.token_budget:
            raise IdentityFailure(
                "identity_token_budget_exceeded",
                "An over-budget identity inventory must be split into stable pages.",
            )
        return manifest


@dataclass(frozen=True, slots=True)
class IdentityInventoryPage:
    id: str
    index: int
    identity_count: int
    content_hash: str
    status: str
    error_category: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "content_hash": self.content_hash,
            "error_category": self.error_category,
            "id": self.id,
            "identity_count": self.identity_count,
            "index": self.index,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IdentityInventoryPage:
        _fields(
            data,
            {"content_hash", "error_category", "id", "identity_count", "index", "status"},
            "identity inventory page",
        )
        page = cls(
            id=_identifier(data.get("id"), "page id"),
            index=_integer(data.get("index"), "page index"),
            identity_count=_integer(data.get("identity_count"), "identity_count"),
            content_hash=_sha256(data.get("content_hash"), "content_hash"),
            status=_choice(
                data.get("status"), "page status", frozenset({"failed", "succeeded"})
            ),
            error_category=_optional_identifier(
                data.get("error_category"), "error_category"
            ),
        )
        if (page.status == "failed") != (page.error_category is not None):
            raise IdentityFailure(
                "invalid_identity_inventory_page",
                "Only failed inventory pages require a sanitized error category.",
            )
        if page.status == "failed" and page.identity_count != 0:
            raise IdentityFailure(
                "invalid_identity_inventory_page",
                "Failed inventory pages cannot claim inspected identities.",
            )
        return page


@dataclass(frozen=True, slots=True)
class EntityAliasGroup:
    """One concrete same-entity hypothesis over record keys from one object."""

    id: str
    candidate_id: str
    member_keys: tuple[str, ...]
    confidence: float
    rationale: str
    evidence_refs: tuple[str, ...]
    producer: str
    model: str | None = None

    def to_dict(self, *, include_members: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "candidate_id": self.candidate_id,
            "confidence": self.confidence,
            "evidence_refs": list(self.evidence_refs),
            "id": self.id,
            "member_count": len(self.member_keys),
            "model": self.model,
            "producer": self.producer,
        }
        if include_members:
            payload["member_keys"] = list(self.member_keys)
            payload["rationale"] = self.rationale
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityAliasGroup:
        _fields(
            data,
            {
                "candidate_id",
                "confidence",
                "evidence_refs",
                "id",
                "member_keys",
                "model",
                "producer",
                "rationale",
            },
            "entity alias group",
            optional={"member_count"},
        )
        members = _string_array(
            data.get("member_keys"),
            "member_keys",
            maximum=_MAX_GROUP_MEMBERS,
            text_limit=512,
        )
        if len(members) < 2:
            raise IdentityFailure(
                "invalid_entity_alias_group",
                "Entity alias groups require at least two distinct record keys.",
            )
        declared_count = data.get("member_count")
        if declared_count is not None and declared_count != len(members):
            raise IdentityFailure(
                "invalid_entity_alias_group",
                "Entity alias group member_count does not match member_keys.",
            )
        return cls(
            id=_identifier(data.get("id"), "group id"),
            candidate_id=_identifier(data.get("candidate_id"), "candidate_id"),
            member_keys=tuple(sorted(members)),
            confidence=_rate(data.get("confidence"), "confidence"),
            rationale=_text(data.get("rationale"), "rationale"),
            evidence_refs=_identifier_array(data.get("evidence_refs"), "evidence_refs"),
            producer=_identifier(data.get("producer"), "producer"),
            model=_optional_model(data.get("model"), "model"),
        )


@dataclass(frozen=True, slots=True)
class EntityGroupReflection:
    id: str
    candidate_id: str
    observation_id: str
    decision: str
    confidence: float
    summary: str
    evidence_refs: tuple[str, ...]
    producer: str
    model: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "confidence": self.confidence,
            "decision": self.decision,
            "evidence_refs": list(self.evidence_refs),
            "id": self.id,
            "model": self.model,
            "observation_id": self.observation_id,
            "producer": self.producer,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityGroupReflection:
        _fields(
            data,
            {
                "candidate_id",
                "confidence",
                "decision",
                "evidence_refs",
                "id",
                "model",
                "observation_id",
                "producer",
                "summary",
            },
            "entity group reflection",
        )
        return cls(
            id=_identifier(data.get("id"), "reflection id"),
            candidate_id=_identifier(data.get("candidate_id"), "candidate_id"),
            observation_id=_identifier(data.get("observation_id"), "observation_id"),
            decision=_choice(
                data.get("decision"),
                "reflection decision",
                IDENTITY_REFLECTION_DECISIONS,
            ),
            confidence=_rate(data.get("confidence"), "confidence"),
            summary=_text(data.get("summary"), "summary"),
            evidence_refs=_identifier_array(data.get("evidence_refs"), "evidence_refs"),
            producer=_identifier(data.get("producer"), "producer"),
            model=_optional_model(data.get("model"), "model"),
        )


@dataclass(frozen=True, slots=True)
class IdentityInspection:
    manifest: IdentityInventoryManifest | None = None
    pages: tuple[IdentityInventoryPage, ...] = ()
    groups: tuple[EntityAliasGroup, ...] = ()
    reflections: tuple[EntityGroupReflection, ...] = ()

    @property
    def covered_identities(self) -> int:
        successful: dict[int, IdentityInventoryPage] = {}
        for page in self.pages:
            if page.status == "succeeded":
                successful.setdefault(page.index, page)
        return sum(page.identity_count for page in successful.values())

    @property
    def coverage_complete(self) -> bool:
        if self.manifest is None:
            return False
        indexes = {page.index for page in self.pages if page.status == "succeeded"}
        return (
            indexes == set(range(self.manifest.page_count))
            and self.covered_identities == self.manifest.identity_count
        )

    @property
    def phase(self) -> str:
        if self.manifest is None:
            return "started"
        if not self.coverage_complete:
            return "inventory_running"
        if not self.groups:
            return "inventory_ready"
        return "group_validation"

    def group_for_candidate(self, candidate_id: str) -> EntityAliasGroup | None:
        return next((item for item in self.groups if item.candidate_id == candidate_id), None)

    def to_dict(self, *, include_values: bool = True) -> dict[str, object]:
        return {
            "groups": [
                item.to_dict(include_members=include_values) for item in self.groups
            ],
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "pages": [item.to_dict() for item in self.pages],
            "reflections": [item.to_dict() for item in self.reflections],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IdentityInspection:
        _fields(data, {"groups", "manifest", "pages", "reflections"}, "identity inspection")
        manifest = data.get("manifest")
        if manifest is not None and not isinstance(manifest, dict):
            raise IdentityFailure(
                "invalid_identity_inspection", "manifest must be an object or null."
            )
        inspection = cls()
        if isinstance(manifest, dict):
            inspection = add_manifest(inspection, manifest)
        for page in _object_array(data.get("pages"), "pages"):
            inspection = add_page(inspection, page)
        for group in _object_array(data.get("groups"), "groups"):
            inspection = add_group(inspection, group)
        for reflection in _object_array(data.get("reflections"), "reflections"):
            inspection = add_reflection(inspection, reflection)
        return inspection


def add_manifest(
    inspection: IdentityInspection, payload: dict[str, Any]
) -> IdentityInspection:
    if inspection.manifest is not None:
        raise IdentityFailure(
            "identity_inventory_exists", "Identity inventory manifests are create-only."
        )
    return replace(inspection, manifest=IdentityInventoryManifest.from_dict(payload))


def add_page(inspection: IdentityInspection, payload: dict[str, Any]) -> IdentityInspection:
    if inspection.manifest is None:
        raise IdentityFailure(
            "identity_inventory_required", "Register the identity inventory before its pages."
        )
    if len(inspection.pages) >= _MAX_PAGE_ATTEMPTS:
        raise IdentityFailure(
            "identity_inspection_budget_exceeded", "Inventory page-attempt budget was exhausted."
        )
    page = IdentityInventoryPage.from_dict(payload)
    if page.index >= inspection.manifest.page_count:
        raise IdentityFailure(
            "invalid_identity_inventory_page", "Page index exceeds the inventory manifest."
        )
    if page.id in _artifact_ids(inspection):
        raise IdentityFailure(
            "identity_artifact_exists", "Identity artifact IDs are create-only."
        )
    successful = next(
        (
            item
            for item in inspection.pages
            if item.index == page.index and item.status == "succeeded"
        ),
        None,
    )
    if successful is not None and page.status == "succeeded" and (
        page.content_hash != successful.content_hash
        or page.identity_count != successful.identity_count
    ):
        raise IdentityFailure(
            "invalid_identity_inventory_page",
            "Repeated successful pages must preserve their hash and identity count.",
        )
    newly_covered = 0 if successful is not None else page.identity_count
    if inspection.covered_identities + newly_covered > inspection.manifest.identity_count:
        raise IdentityFailure(
            "invalid_identity_inventory_page",
            "Inventory pages exceed the declared distinct identity count.",
        )
    return replace(inspection, pages=(*inspection.pages, page))


def add_group(inspection: IdentityInspection, payload: dict[str, Any]) -> IdentityInspection:
    if not inspection.coverage_complete:
        raise IdentityFailure(
            "identity_inventory_incomplete",
            "Entity groups require a complete, non-truncated identity inventory.",
        )
    if len(inspection.groups) >= _MAX_GROUPS:
        raise IdentityFailure(
            "identity_inspection_budget_exceeded", "Entity group budget was exhausted."
        )
    group = EntityAliasGroup.from_dict(payload)
    if group.id in _artifact_ids(inspection) or any(
        item.candidate_id == group.candidate_id for item in inspection.groups
    ):
        raise IdentityFailure(
            "entity_alias_group_exists",
            "Identity artifact IDs are create-only and each candidate accepts one group.",
        )
    page_ids = {item.id for item in inspection.pages if item.status == "succeeded"}
    if not group.evidence_refs or not set(group.evidence_refs).issubset(page_ids):
        raise IdentityFailure(
            "invalid_entity_alias_evidence",
            "Entity group evidence must reference successful identity inventory pages.",
        )
    return replace(inspection, groups=(*inspection.groups, group))


def add_reflection(
    inspection: IdentityInspection, payload: dict[str, Any]
) -> IdentityInspection:
    if len(inspection.reflections) >= _MAX_REFLECTIONS:
        raise IdentityFailure(
            "identity_inspection_budget_exceeded", "Entity reflection budget was exhausted."
        )
    reflection = EntityGroupReflection.from_dict(payload)
    if reflection.id in _artifact_ids(inspection):
        raise IdentityFailure(
            "identity_artifact_exists", "Identity artifact IDs are create-only."
        )
    group = inspection.group_for_candidate(reflection.candidate_id)
    if group is None:
        raise IdentityFailure(
            "entity_alias_group_required", "Reflect only on a registered entity alias group."
        )
    evidence_ids = {
        *(item.id for item in inspection.pages if item.status == "succeeded"),
        group.id,
    }
    if not reflection.evidence_refs or not set(reflection.evidence_refs).issubset(evidence_ids):
        raise IdentityFailure(
            "invalid_entity_alias_evidence",
            "Entity reflection evidence must reference the group or inventory pages.",
        )
    return replace(inspection, reflections=(*inspection.reflections, reflection))


def _artifact_ids(inspection: IdentityInspection) -> set[str]:
    return {
        *(item.id for item in inspection.pages),
        *(item.id for item in inspection.groups),
        *(item.id for item in inspection.reflections),
    }


def _fields(
    data: dict[str, Any],
    required: set[str],
    label: str,
    *,
    optional: set[str] = frozenset(),
) -> None:
    if set(data) - optional != required or not set(data).issubset(required | optional):
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} has unexpected or missing fields."
        )


def _text(value: object, label: str, *, limit: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be bounded non-empty text."
        )
    return value.strip()


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be a bounded identifier."
        )
    return value


def _optional_identifier(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, label)


def _optional_model(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _MODEL.fullmatch(value):
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be a bounded model identifier."
        )
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be a lowercase SHA-256."
        )
    return value


def _choice(value: object, label: str, choices: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} has an unsupported value."
        )
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be an integer >= {minimum}."
        )
    return value


def _bounded_integer(
    value: object, label: str, *, minimum: int, maximum: int
) -> int:
    parsed = _integer(value, label, minimum=minimum)
    if parsed > maximum:
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be <= {maximum}."
        )
    return parsed


def _rate(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be between zero and one."
        )
    parsed = float(value)
    if not math.isfinite(parsed) or not 0 <= parsed <= 1:
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be between zero and one."
        )
    return parsed


def _string_array(
    value: object,
    label: str,
    *,
    maximum: int,
    allow_empty: bool = False,
    text_limit: int = _MAX_TEXT,
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or len(value) > maximum
        or any(
            not isinstance(item, str)
            or not item.strip()
            or len(item.strip()) > text_limit
            for item in value
        )
    ):
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be a bounded string array."
        )
    items = tuple(item.strip() for item in value)
    if len(items) != len(set(items)):
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must contain unique values."
        )
    return items


def _identifier_array(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > 100:
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be a bounded identifier array."
        )
    items = tuple(_identifier(item, label) for item in value)
    if len(items) != len(set(items)):
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must contain unique values."
        )
    return items


def _object_array(value: object, label: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise IdentityFailure(
            "invalid_identity_inspection", f"{label} must be an array of objects."
        )
    return tuple(value)
