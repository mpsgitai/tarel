"""Small promoted logical-join sidecars with existing aggregate Discovery evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, NoReturn

from tarel.discovery.contracts import DiscoveryFailure, DiscoveryObservation
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.topology.endpoint_contracts import LogicalEndpointFailure

LOGICAL_JOIN_CONTRACT = "tarel.logical-join.v0.1.experimental"
LOGICAL_JOIN_MODES = frozenset(
    {"confirmed_only", "confirmed_then_candidates", "include_candidates"}
)


class LogicalJoinFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        _invalid("Logical join identifiers must be bounded safe metadata IDs.")
    return value


def sha256(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        _invalid("Logical join revisions must be SHA-256 values.")
    return value


@dataclass(frozen=True, slots=True)
class LogicalJoin:
    id: str
    graph_name: str
    graph_revision: str
    program: LogicalJoinProgram
    observations: tuple[DiscoveryObservation, ...]
    run_id: str
    run_revision: str
    discovery_candidate_id: str
    producer: str
    promotion_reason: str
    state: str = "candidate"
    review_reason: str | None = None

    @property
    def revision(self) -> str:
        raw = json.dumps(
            self.to_dict(include_revision=False),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    @property
    def usage(self) -> str:
        return "confirmed" if self.state == "reviewed" else "exploratory_only"

    def to_dict(self, *, include_revision: bool = True) -> dict[str, object]:
        data: dict[str, object] = {
            "contract_version": LOGICAL_JOIN_CONTRACT,
            "id": self.id,
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "program": self.program.to_dict(),
            "observations": [item.to_dict() for item in self.observations],
            "provenance": {
                "run_id": self.run_id,
                "run_revision": self.run_revision,
                "discovery_candidate_id": self.discovery_candidate_id,
                "producer": self.producer,
                "promotion_reason": self.promotion_reason,
            },
            "state": self.state,
            "review": (
                {
                    "source": "human",
                    "reason": self.review_reason,
                    "decision": "approve" if self.state == "reviewed" else "reject",
                }
                if self.review_reason is not None
                else None
            ),
        }
        if include_revision:
            data["revision"] = self.revision
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogicalJoin:
        required = {
            "contract_version",
            "id",
            "graph",
            "program",
            "observations",
            "provenance",
            "state",
            "review",
        }
        if not isinstance(data, dict) or set(data) not in (required, required | {"revision"}):
            _invalid("Logical join fields do not match the strict contract.")
        if data["contract_version"] != LOGICAL_JOIN_CONTRACT:
            _invalid("Unsupported logical join contract.")
        graph, provenance, review = data["graph"], data["provenance"], data["review"]
        if not isinstance(graph, dict) or set(graph) != {"name", "revision"}:
            _invalid("Logical join requires a physical graph revision.")
        if not isinstance(provenance, dict) or set(provenance) != {
            "run_id",
            "run_revision",
            "discovery_candidate_id",
            "producer",
            "promotion_reason",
        }:
            _invalid("Logical join requires exact Discovery provenance.")
        if not isinstance(data["state"], str) or data["state"] not in {
            "candidate",
            "reviewed",
            "rejected",
        }:
            _invalid("Unsupported logical join review state.")
        reason = _text(provenance["promotion_reason"])
        if not isinstance(provenance["producer"], str) or provenance["producer"] not in {
            "coding_agent",
            "provider",
            "human",
        }:
            _invalid("Logical join producer must identify its Discovery actor type.")
        review_reason = None
        if data["state"] == "candidate":
            if review is not None:
                _invalid("Candidates cannot claim a human review.")
        else:
            if not isinstance(review, dict) or set(review) != {"source", "reason", "decision"}:
                _invalid("A reviewed logical join requires an explicit human decision.")
            expected = "approve" if data["state"] == "reviewed" else "reject"
            if review["source"] != "human" or review["decision"] != expected:
                _invalid("Logical join review source or decision does not match its state.")
            review_reason = _text(review["reason"])
        if (
            not isinstance(data["observations"], list)
            or not 2 <= len(data["observations"]) <= 2_000
        ):
            _invalid("Logical joins require bounded support and challenge observations.")
        try:
            program = LogicalJoinProgram.from_dict(data["program"])
            observations = tuple(
                DiscoveryObservation.from_dict(item) for item in data["observations"]
            )
        except (DiscoveryFailure, LogicalEndpointFailure) as exc:
            raise LogicalJoinFailure("invalid_logical_join", str(exc)) from exc
        if len({item.id for item in observations}) != len(observations):
            _invalid("Logical join observation IDs must be unique.")
        successful = tuple(item for item in observations if item.status == "succeeded")
        support = tuple(item for item in successful if item.phase == "support")
        challenge = tuple(item for item in successful if item.phase == "challenge")
        if (
            not support
            or not challenge
            or not any(
                first.query_hash != second.query_hash for first in support for second in challenge
            )
        ):
            _invalid("Logical joins require independent successful support and challenge queries.")
        for observation in successful:
            metrics = observation.metrics
            if (
                observation.execution is None
                or metrics is None
                or not metrics.evaluated_count
                or metrics.collision_count is None
                or metrics.counterexample_count is None
            ):
                _invalid("Logical join evidence needs execution provenance and measured risks.")
        result = cls(
            identifier(data["id"]),
            identifier(graph["name"]),
            sha256(graph["revision"]),
            program,
            observations,
            identifier(provenance["run_id"]),
            sha256(provenance["run_revision"]),
            identifier(provenance["discovery_candidate_id"]),
            identifier(provenance["producer"]),
            reason,
            data["state"],
            review_reason,
        )
        if "revision" in data and data["revision"] != result.revision:
            _invalid("Logical join content revision does not match.")
        return result


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1_000:
        _invalid(
            "Reasons must be nonempty bounded metadata descriptions, never source rows or SQL."
        )
    return value


def _invalid(message: str) -> NoReturn:
    raise LogicalJoinFailure("invalid_logical_join", message)
