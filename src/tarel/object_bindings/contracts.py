"""Exact value-to-family-attribute declarations; no values or executable rules."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from tarel.object_families.contracts import FamilyReview
from tarel.reference_mapping.contracts import ReferenceMappingEvidence
from tarel.topology.endpoint_contracts import LogicalEndpoint

CONTRACT_VERSION = "tarel.object-value-binding.v0.1.experimental"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ObjectBindingFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ObjectValueBinding:
    id: str
    graph_name: str
    source: LogicalEndpoint
    target: LogicalEndpoint
    producer: str
    run_id: str
    evidence: tuple[ReferenceMappingEvidence, ...] = ()
    state: str = "candidate"
    review: FamilyReview | None = None
    rule: str = "exact_string"
    contract_version: str = CONTRACT_VERSION

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
        result: dict[str, object] = {
            "id": self.id,
            "graph": self.graph_name,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "producer": self.producer,
            "run_id": self.run_id,
            "evidence": [item.to_dict() for item in self.evidence],
            "state": self.state,
            "review": self.review.to_dict() if self.review else None,
            "rule": self.rule,
            "contract_version": self.contract_version,
        }
        if include_revision:
            result["revision"] = self.revision
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObjectValueBinding:
        required = {
            "id",
            "graph",
            "source",
            "target",
            "producer",
            "run_id",
            "evidence",
            "state",
            "review",
            "rule",
            "contract_version",
        }
        if not isinstance(data, dict) or not required <= set(data) <= required | {"revision"}:
            invalid(
                "Unexpected object-binding fields; values, paths and executable code are forbidden."
            )
        for key in ("id", "graph", "producer", "run_id"):
            identifier(data[key])
        if data["contract_version"] != CONTRACT_VERSION or data["rule"] != "exact_string":
            invalid("Only the experimental exact_string object-binding contract is supported.")
        if not isinstance(data["evidence"], list) or len(data["evidence"]) > 64:
            invalid("Evidence must be a bounded array.")
        source = LogicalEndpoint.from_dict(data["source"])
        target = LogicalEndpoint.from_dict(data["target"])
        if source.kind != "graph_field" or target.kind != "family_attribute":
            invalid("Object binding connects a physical field to a family metadata attribute.")
        review = FamilyReview.from_dict(data["review"]) if data["review"] is not None else None
        state = data["state"]
        if not isinstance(state, str) or state not in {"candidate", "reviewed", "rejected"}:
            invalid("Unknown binding review state.")
        if (state == "candidate") != (review is None) or (
            review is not None
            and review.decision != ("approve" if state == "reviewed" else "reject")
        ):
            invalid("Binding state does not match its human review.")
        evidence = tuple(ReferenceMappingEvidence.from_dict(item) for item in data["evidence"])
        if len({item.observation_id for item in evidence}) != len(evidence):
            invalid("Evidence observation IDs must be unique.")
        if state == "reviewed" and {item.phase for item in evidence} != {"support", "challenge"}:
            invalid("Approval requires both measured support and challenge evidence.")
        result = cls(
            data["id"],
            data["graph"],
            source,
            target,
            data["producer"],
            data["run_id"],
            evidence,
            state,
            review,
        )
        if "revision" in data and data["revision"] != result.revision:
            invalid("Binding revision does not match its content.")
        return result


def identifier(value: object) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        invalid("Binding graph and identifiers must be bounded metadata identifiers.")


def invalid(message: str) -> None:
    raise ObjectBindingFailure("invalid_object_binding", message)
