"""Small, value-free semantic concept declarations; not an ontology engine."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from tarel.topology.endpoint_contracts import LogicalEndpoint

SEMANTIC_CONCEPT_CONTRACT_VERSION = "tarel.semantic-concepts.v0.1.experimental"
CONCEPT_REPRESENTATIONS = frozenset({"code", "label", "description", "hierarchy_level"})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SemanticConceptFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ConceptBinding:
    endpoint: LogicalEndpoint
    representation: str

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, LogicalEndpoint):
            _invalid("Concept bindings require a logical endpoint.")
        if not isinstance(self.representation, str) or self.representation not in (
            CONCEPT_REPRESENTATIONS
        ):
            _invalid("Unknown concept representation.")

    def to_dict(self) -> dict[str, object]:
        return {"endpoint": self.endpoint.to_dict(), "representation": self.representation}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConceptBinding:
        _fields(data, {"endpoint", "representation"})
        return cls(LogicalEndpoint.from_dict(data["endpoint"]), data["representation"])


@dataclass(frozen=True, slots=True)
class ConceptReview:
    decision: str
    reason: str
    source: str = "human"

    def __post_init__(self) -> None:
        if self.decision not in ("approve", "reject") or self.source != "human":
            _invalid("A concept review requires an explicit human approval or rejection.")
        _text(self.reason, 1000)

    def to_dict(self) -> dict[str, str]:
        return {"decision": self.decision, "reason": self.reason, "source": self.source}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConceptReview:
        _fields(data, {"decision", "reason", "source"})
        return cls(**data)


@dataclass(frozen=True, slots=True)
class SemanticConcept:
    id: str
    name: str
    description: str
    parent_ids: tuple[str, ...] = ()
    bindings: tuple[ConceptBinding, ...] = ()
    evidence_hashes: tuple[str, ...] = ()
    producer: str = "coding_agent"
    state: str = "candidate"
    review: ConceptReview | None = None

    def __post_init__(self) -> None:
        _identifier(self.id)
        _text(self.name, 200)
        _text(self.description, 2000)
        _tuple(self.parent_ids, 32)
        for parent in self.parent_ids:
            _identifier(parent)
        if self.id in self.parent_ids or len(set(self.parent_ids)) != len(self.parent_ids):
            _invalid("Concept parents must be distinct and cannot include the concept itself.")
        _tuple(self.bindings, 256)
        if any(not isinstance(item, ConceptBinding) for item in self.bindings):
            _invalid("Concept bindings must use the typed binding contract.")
        if len(set(self.bindings)) != len(self.bindings):
            _invalid("Concept bindings must be distinct.")
        _tuple(self.evidence_hashes, 64)
        for evidence_hash in self.evidence_hashes:
            _hash(evidence_hash)
        if len(set(self.evidence_hashes)) != len(self.evidence_hashes):
            _invalid("Concept evidence hashes must be distinct.")
        if self.producer not in ("coding_agent", "provider", "human"):
            _invalid("Unknown concept producer.")
        if self.state not in ("candidate", "reviewed", "rejected"):
            _invalid("Unknown concept review state.")
        if self.state == "candidate":
            if self.review is not None:
                _invalid("Candidate concepts must not carry a human decision.")
        elif not isinstance(self.review, ConceptReview) or self.review.decision != (
            "approve" if self.state == "reviewed" else "reject"
        ):
            _invalid("Concept state and human review decision disagree.")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_ids": sorted(self.parent_ids),
            "bindings": [item.to_dict() for item in self.bindings],
            "evidence_hashes": sorted(self.evidence_hashes),
            "producer": self.producer,
            "state": self.state,
            "review": self.review.to_dict() if self.review else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticConcept:
        _fields(
            data,
            {
                "id",
                "name",
                "description",
                "parent_ids",
                "bindings",
                "evidence_hashes",
                "producer",
                "state",
                "review",
            },
        )
        for name in ("parent_ids", "bindings", "evidence_hashes"):
            if not isinstance(data[name], list):
                _invalid(f"Concept {name} must be an array.")
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            parent_ids=tuple(data["parent_ids"]),
            bindings=tuple(ConceptBinding.from_dict(item) for item in data["bindings"]),
            evidence_hashes=tuple(data["evidence_hashes"]),
            producer=data["producer"],
            state=data["state"],
            review=ConceptReview.from_dict(data["review"]) if data["review"] is not None else None,
        )


@dataclass(frozen=True, slots=True)
class SemanticConceptDocument:
    graph_name: str
    graph_revision: str
    concepts: tuple[SemanticConcept, ...]
    contract_version: str = SEMANTIC_CONCEPT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _identifier(self.graph_name)
        _hash(self.graph_revision)
        if self.contract_version != SEMANTIC_CONCEPT_CONTRACT_VERSION:
            _invalid("Unsupported semantic concept contract.")
        _tuple(self.concepts, 10000)
        if any(not isinstance(item, SemanticConcept) for item in self.concepts):
            _invalid("Concept documents require typed concept declarations.")
        by_id = {item.id: item for item in self.concepts}
        if len(by_id) != len(self.concepts):
            _invalid("Concept IDs must be unique within a graph.")
        pending = {item.id: set(item.parent_ids) for item in self.concepts}
        for parents in pending.values():
            if not parents <= by_id.keys():
                _invalid("Concept parent references must exist in the same document.")
        children: dict[str, list[str]] = {identifier: [] for identifier in by_id}
        for child, parents in pending.items():
            for parent in parents:
                children[parent].append(child)
        ready = [identifier for identifier, parents in pending.items() if not parents]
        visited = 0
        while ready:
            identifier = ready.pop()
            visited += 1
            for child in children[identifier]:
                pending[child].remove(identifier)
                if not pending[child]:
                    ready.append(child)
        if visited != len(by_id):
            _invalid("Concept parent declarations must form an acyclic hierarchy.")

    @property
    def revision(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_dict(include_revision=False),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def to_dict(self, *, include_revision: bool = True) -> dict[str, object]:
        payload = {
            "graph_name": self.graph_name,
            "graph_revision": self.graph_revision,
            "concepts": [
                item.to_dict() for item in sorted(self.concepts, key=lambda concept: concept.id)
            ],
            "contract_version": self.contract_version,
        }
        if include_revision:
            payload["revision"] = self.revision
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticConceptDocument:
        if not isinstance(data, dict):
            _invalid("Semantic concepts require a JSON object.")
        _fields(
            data,
            {"graph_name", "graph_revision", "concepts", "contract_version"},
            optional={"revision"},
        )
        if not isinstance(data["concepts"], list):
            _invalid("Concepts must be an array.")
        result = cls(
            graph_name=data["graph_name"],
            graph_revision=data["graph_revision"],
            concepts=tuple(SemanticConcept.from_dict(item) for item in data["concepts"]),
            contract_version=data["contract_version"],
        )
        if "revision" in data and data["revision"] != result.revision:
            _invalid("Semantic concept revision does not match its content.")
        return result


def _invalid(message: str) -> None:
    raise SemanticConceptFailure("invalid_semantic_concepts", message)


def _fields(data: object, expected: set[str], optional: set[str] | None = None) -> None:
    if (
        not isinstance(data, dict)
        or not expected <= data.keys()
        or set(data) - (expected | (optional or set()))
    ):
        _invalid("Missing or unsupported semantic concept fields.")


def _identifier(value: object) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _invalid("Concept IDs and graph names must be bounded safe identifiers.")


def _hash(value: object) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _invalid("Concept revisions and evidence must be SHA-256 hashes.")


def _text(value: object, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 and character not in "\n\t" for character in value)
    ):
        _invalid("Concept metadata must be bounded nonempty text.")


def _tuple(value: object, maximum: int) -> None:
    if not isinstance(value, tuple) or len(value) > maximum:
        _invalid("Concept collections must be bounded tuples.")
