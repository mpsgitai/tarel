"""Experimental, declarative families of explicitly named physical graph objects."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any, NoReturn

FAMILY_CONTRACT_VERSION = "tarel.object-family.v0.1.experimental"
FAMILY_STATES = frozenset({"candidate", "reviewed", "rejected"})
ATTRIBUTE_SOURCES = frozenset({"object_name", "namespace"})

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DATA_TYPE = re.compile(r"^[A-Za-z][A-Za-z0-9_. (),\[\]-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ObjectFamilyFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class FamilyField:
    """A literal physical field name and schema, never an executable expression."""

    name: str
    data_type: str
    nullable: bool

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "data_type": self.data_type, "nullable": self.nullable}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FamilyField:
        _fields(data, {"name", "data_type", "nullable"}, "family field")
        data_type = _text(data["data_type"], "field data_type", limit=128)
        if not _DATA_TYPE.fullmatch(data_type):
            _invalid("Field data_type contains unsupported characters.")
        if not isinstance(data["nullable"], bool):
            _invalid("Field nullable must be a boolean.")
        return cls(_field_name(data["name"], "field name"), data_type, data["nullable"])


@dataclass(frozen=True, slots=True)
class FamilyAttribute:
    """A string attribute derived only by removing literal metadata affixes."""

    name: str
    source: str
    prefix: str = ""
    suffix: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "source": self.source,
            "prefix": self.prefix,
            "suffix": self.suffix,
            "data_type": "string",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FamilyAttribute:
        _fields(data, {"name", "source", "prefix", "suffix", "data_type"}, "family attribute")
        if data["data_type"] != "string":
            _invalid("Family attributes have fixed string data_type.")
        return cls(
            name=_identifier(data["name"], "attribute name"),
            source=_choice(data["source"], "attribute source", ATTRIBUTE_SOURCES),
            prefix=_affix(data["prefix"], "attribute prefix"),
            suffix=_affix(data["suffix"], "attribute suffix"),
        )


@dataclass(frozen=True, slots=True)
class FamilyReview:
    decision: str
    reason: str
    source: str = "human"

    def to_dict(self) -> dict[str, str]:
        return {"decision": self.decision, "reason": self.reason, "source": self.source}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FamilyReview:
        _fields(data, {"decision", "reason", "source"}, "family review")
        if data["source"] != "human":
            _invalid("Object-family review source must be human.")
        return cls(
            decision=_choice(data["decision"], "review decision", frozenset({"approve", "reject"})),
            reason=_text(data["reason"], "review reason", limit=1_000),
        )


@dataclass(frozen=True, slots=True)
class ObjectFamily:
    graph_name: str
    graph_revision: str
    id: str
    name: str
    member_ids: tuple[str, ...]
    schema: tuple[FamilyField, ...]
    grain: tuple[str, ...]
    attributes: tuple[FamilyAttribute, ...]
    producer: str
    state: str = "candidate"
    review: FamilyReview | None = None
    contract_version: str = FAMILY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.member_ids, tuple) and all(
            isinstance(item, str) for item in self.member_ids
        ):
            object.__setattr__(self, "member_ids", tuple(sorted(self.member_ids)))

    @property
    def revision(self) -> str:
        canonical = json.dumps(
            self.to_dict(include_revision=False),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def to_dict(self, *, include_revision: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": self.contract_version,
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "id": self.id,
            "name": self.name,
            "member_ids": list(self.member_ids),
            "schema": [field.to_dict() for field in self.schema],
            "grain": list(self.grain),
            "attributes": [attribute.to_dict() for attribute in self.attributes],
            "producer": self.producer,
            "state": self.state,
            "review": self.review.to_dict() if self.review is not None else None,
        }
        if include_revision:
            payload["revision"] = self.revision
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectFamily:
        _fields(
            data,
            {
                "contract_version",
                "graph",
                "id",
                "name",
                "member_ids",
                "schema",
                "grain",
                "attributes",
                "producer",
                "state",
                "review",
            },
            "object family",
            optional={"revision"},
        )
        graph = _object(data["graph"], "family graph")
        _fields(graph, {"name", "revision"}, "family graph")
        review = data["review"]
        family = cls(
            graph_name=_identifier(graph["name"], "graph name"),
            graph_revision=_sha256(graph["revision"], "graph revision"),
            id=_identifier(data["id"], "family id"),
            name=_identifier(data["name"], "family name"),
            member_ids=tuple(
                _text(item, "member id", limit=1_000)
                for item in _array(data["member_ids"], "member_ids")
            ),
            schema=tuple(
                FamilyField.from_dict(_object(item, "family field"))
                for item in _array(data["schema"], "schema")
            ),
            grain=tuple(_field_name(item, "grain name") for item in _array(data["grain"], "grain")),
            attributes=tuple(
                FamilyAttribute.from_dict(_object(item, "family attribute"))
                for item in _array(data["attributes"], "attributes")
            ),
            producer=_identifier(data["producer"], "producer"),
            state=_choice(data["state"], "family state", FAMILY_STATES),
            review=FamilyReview.from_dict(_object(review, "family review"))
            if review is not None
            else None,
            contract_version=data["contract_version"],
        )
        validate_family(family)
        if "revision" in data and data["revision"] != family.revision:
            _invalid("Object-family revision does not match its content.")
        return family


def validate_family(family: ObjectFamily) -> None:
    """Validate direct SDK construction as strictly as serialized imports."""
    if not isinstance(family, ObjectFamily):
        _invalid("An object-family document is required.")
    if family.contract_version != FAMILY_CONTRACT_VERSION:
        raise ObjectFamilyFailure(
            "unsupported_object_family", "Unsupported TAREL object-family contract."
        )
    _identifier(family.graph_name, "graph name")
    _sha256(family.graph_revision, "graph revision")
    _identifier(family.id, "family id")
    _identifier(family.name, "family name")
    _identifier(family.producer, "producer")
    _choice(family.state, "family state", FAMILY_STATES)
    _tuple(family.member_ids, "member_ids")
    members = tuple(_text(item, "member id", limit=1_000) for item in family.member_ids)
    if len(members) < 2 or len(set(members)) != len(members):
        _invalid("Object families require at least two unique explicit member IDs.")
    _tuple(family.schema, "schema")
    if not family.schema:
        _invalid("Object families require a non-empty declared schema.")
    for field in family.schema:
        if not isinstance(field, FamilyField):
            _invalid("Family schema entries must be FamilyField values.")
        FamilyField.from_dict(field.to_dict())
    _tuple(family.attributes, "attributes")
    for attribute in family.attributes:
        if not isinstance(attribute, FamilyAttribute):
            _invalid("Family attributes must be FamilyAttribute values.")
        FamilyAttribute.from_dict(attribute.to_dict())
    names = tuple(field.name for field in family.schema) + tuple(
        attribute.name for attribute in family.attributes
    )
    if len(set(names)) != len(names):
        _invalid("Family schema and attribute names must be unique and disjoint.")
    _tuple(family.grain, "grain")
    grain = tuple(_field_name(item, "grain name") for item in family.grain)
    if not grain or len(set(grain)) != len(grain) or not set(grain).issubset(names):
        _invalid("Family grain requires unique declared field or attribute names.")
    if family.review is not None:
        if not isinstance(family.review, FamilyReview):
            _invalid("Family review must be a FamilyReview value or null.")
        FamilyReview.from_dict(family.review.to_dict())
    if family.state == "candidate":
        if family.review is not None:
            _invalid("Candidate object families cannot contain a review.")
    elif (
        family.review is None
        or family.review.decision != {"reviewed": "approve", "rejected": "reject"}[family.state]
    ):
        _invalid("Reviewed or rejected families require a matching human decision.")


def review_family(family: ObjectFamily, *, decision: str, reason: str) -> ObjectFamily:
    validate_family(family)
    if family.state != "candidate":
        raise ObjectFamilyFailure(
            "object_family_already_reviewed", "Object-family review decisions are terminal."
        )
    review = FamilyReview.from_dict({"decision": decision, "reason": reason, "source": "human"})
    changed = replace(
        family, state="reviewed" if decision == "approve" else "rejected", review=review
    )
    validate_family(changed)
    return changed


def _invalid(message: str) -> NoReturn:
    raise ObjectFamilyFailure("invalid_object_family", message)


def _fields(
    data: object, required: set[str], label: str, *, optional: set[str] | None = None
) -> None:
    if (
        not isinstance(data, dict)
        or set(data) - (required | (optional or set()))
        or required - set(data)
    ):
        _invalid(f"{label} has unexpected or missing fields.")


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _invalid(f"{label} must be an object.")
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        _invalid(f"{label} must be an array.")
    return value


def _tuple(value: object, label: str) -> None:
    if not isinstance(value, tuple):
        _invalid(f"{label} must be an immutable tuple.")


def _text(value: object, label: str, *, limit: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > limit:
        _invalid(f"{label} must be a non-empty trimmed string of at most {limit} characters.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        _invalid(f"{label} may not contain control characters.")
    return value


def _identifier(value: object, label: str) -> str:
    clean = _text(value, label, limit=128)
    if not _IDENTIFIER.fullmatch(clean):
        _invalid(f"{label} may contain letters, numbers, dots, underscores, and hyphens.")
    return clean


def _field_name(value: object, label: str) -> str:
    """Preserve literal graph names; grain validation resolves them by exact equality."""
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        _invalid(f"{label} must be a non-empty literal name of at most 256 characters.")
    if any(
        ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF for char in value
    ):
        _invalid(f"{label} may not contain control characters or invalid Unicode.")
    return value


def _sha256(value: object, label: str) -> str:
    clean = _text(value, label, limit=64)
    if not _SHA256.fullmatch(clean):
        _invalid(f"{label} must be a lowercase SHA-256 value.")
    return clean


def _choice(value: object, label: str, choices: frozenset[str]) -> str:
    clean = _text(value, label, limit=128)
    if clean not in choices:
        _invalid(f"Unsupported {label}.")
    return clean


def _affix(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) > 128:
        _invalid(f"{label} must be a literal string of at most 128 characters.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        _invalid(f"{label} may not contain control characters.")
    return value
