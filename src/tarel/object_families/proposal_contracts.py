"""Experimental checkpoints for bounded metadata-only provider family proposals."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import NoReturn

from tarel.object_families.contracts import ObjectFamilyFailure

CONTRACT = "tarel.family-proposals.v0.1.experimental"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        invalid("Expected a safe run, graph or provider identifier.")
    return value


def invalid(message: str) -> NoReturn:
    raise ObjectFamilyFailure("invalid_family_proposals", message)


def fields(value: object, names: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != names:
        invalid("Proposal fields do not match the strict contract.")
    return value


def strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item or len(item) > 1_000 for item in value
    ):
        invalid("Expected a bounded array of nonempty strings.")
    return tuple(value)


def count(value: object) -> int:
    if type(value) is not int or value < 0:
        invalid("Counts must be nonnegative integers.")
    return value


@dataclass(frozen=True, slots=True)
class ProposalOutcome:
    family_id: str
    status: str
    member_count: int
    error_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "family_id": self.family_id,
            "status": self.status,
            "member_count": self.member_count,
            "error_code": self.error_code,
        }

    @classmethod
    def from_dict(cls, value: object) -> ProposalOutcome:
        data = fields(value, {"family_id", "status", "member_count", "error_code"})
        if not isinstance(data["status"], str) or data["status"] not in {
            "saved_candidate",
            "failed",
        }:
            invalid("Unsupported proposal outcome.")
        error = data["error_code"]
        if (data["status"] == "failed") != (error is not None):
            invalid("Failed proposals require an error code.")
        members = count(data["member_count"])
        if members > 200 or (data["status"] == "saved_candidate" and members < 2):
            invalid("Invalid proposal member count.")
        return cls(
            identifier(data["family_id"]),
            data["status"],
            members,
            identifier(error) if error else None,
        )


@dataclass(frozen=True, slots=True)
class ProposalBatch:
    object_ids: tuple[str, ...]
    request_hash: str
    status: str = "planned"
    attempts: int = 0
    outcomes: tuple[ProposalOutcome, ...] = ()
    unassigned_count: int = 0
    error_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "object_ids": list(self.object_ids),
            "request_hash": self.request_hash,
            "status": self.status,
            "attempts": self.attempts,
            "outcomes": [outcome.to_dict() for outcome in self.outcomes],
            "unassigned_count": self.unassigned_count,
            "error_code": self.error_code,
        }

    @classmethod
    def from_dict(cls, value: object) -> ProposalBatch:
        data = fields(
            value,
            {
                "object_ids",
                "request_hash",
                "status",
                "attempts",
                "outcomes",
                "unassigned_count",
                "error_code",
            },
        )
        ids = strings(data["object_ids"])
        if len(ids) < 2 or len(set(ids)) != len(ids) or len(ids) > 200:
            invalid("A proposal batch requires 2 to 200 distinct objects.")
        if not isinstance(data["request_hash"], str) or not _HASH.fullmatch(data["request_hash"]):
            invalid("Invalid proposal request hash.")
        if not isinstance(data["status"], str) or data["status"] not in {
            "planned",
            "running",
            "completed",
            "partial",
            "failed",
        }:
            invalid("Invalid proposal batch status.")
        if not isinstance(data["outcomes"], list):
            invalid("Expected proposal outcomes.")
        outcomes = tuple(ProposalOutcome.from_dict(item) for item in data["outcomes"])
        error = data["error_code"]
        if error is not None:
            identifier(error)
        attempts, unassigned = count(data["attempts"]), count(data["unassigned_count"])
        if (data["status"] == "planned") != (attempts == 0):
            invalid("Started proposal batches require a positive attempt count.")
        if (data["status"] == "failed") != (error is not None):
            invalid("Failed proposal batches require an error code.")
        terminal = data["status"] in {"completed", "partial"}
        if terminal:
            if unassigned + sum(item.member_count for item in outcomes) != len(ids):
                invalid("Terminal proposal counts must account for every batch object.")
            if (data["status"] == "partial") != any(item.status == "failed" for item in outcomes):
                invalid("Partial batches must record individual proposal failures.")
        elif outcomes or unassigned:
            invalid("Unfinished batches cannot contain terminal proposal outcomes.")
        return cls(
            ids,
            data["request_hash"],
            data["status"],
            attempts,
            outcomes,
            unassigned,
            error,
        )


@dataclass(frozen=True, slots=True)
class FamilyProposalRun:
    id: str
    graph_name: str
    graph_revision: str
    provider: str
    model: str
    objects_per_batch: int
    max_input_chars: int
    max_objects: int
    total_objects: int
    batches: tuple[ProposalBatch, ...]
    omissions: tuple[tuple[str, int], ...] = ()

    @property
    def status(self) -> str:
        states = {batch.status for batch in self.batches}
        if states.intersection({"running", "planned"}):
            return "planned" if states <= {"planned"} else "incomplete"
        if states.intersection({"failed", "partial"}):
            return "partial"
        return "completed"

    def to_dict(self, *, include_revision: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "contract_version": CONTRACT,
            "id": self.id,
            "graph": {"name": self.graph_name, "revision": self.graph_revision},
            "provider": self.provider,
            "model": self.model,
            "limits": {
                "objects_per_batch": self.objects_per_batch,
                "max_input_chars": self.max_input_chars,
                "max_objects": self.max_objects,
            },
            "total_objects": self.total_objects,
            "planned_objects": sum(len(batch.object_ids) for batch in self.batches),
            "status": self.status,
            "omissions": dict(self.omissions),
            "batches": [batch.to_dict() for batch in self.batches],
            "saved_candidates": sum(
                outcome.status == "saved_candidate"
                for batch in self.batches
                for outcome in batch.outcomes
            ),
        }
        if include_revision:
            payload["revision"] = digest(payload)
        return payload

    @classmethod
    def from_dict(cls, value: object) -> FamilyProposalRun:
        data = fields(
            value,
            {
                "contract_version",
                "id",
                "graph",
                "provider",
                "model",
                "limits",
                "total_objects",
                "planned_objects",
                "status",
                "omissions",
                "batches",
                "saved_candidates",
                "revision",
            },
        )
        if data["contract_version"] != CONTRACT:
            invalid("Unsupported family-proposal contract.")
        graph = fields(data["graph"], {"name", "revision"})
        if not isinstance(graph["revision"], str) or not _HASH.fullmatch(graph["revision"]):
            invalid("Invalid physical graph revision.")
        limits = fields(data["limits"], {"objects_per_batch", "max_input_chars", "max_objects"})
        model = data["model"]
        if not isinstance(model, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,255}", model
        ):
            invalid("Model must be an explicit bounded provider model identifier.")
        if not isinstance(data["batches"], list) or not isinstance(data["omissions"], dict):
            invalid("Expected batches and aggregate omissions.")
        batches = tuple(ProposalBatch.from_dict(item) for item in data["batches"])
        ids = tuple(item for batch in batches for item in batch.object_ids)
        if len(ids) != len(set(ids)):
            invalid("An object may be planned only once in one run.")
        run = cls(
            identifier(data["id"]),
            identifier(graph["name"]),
            graph["revision"],
            identifier(data["provider"]),
            model,
            count(limits["objects_per_batch"]),
            count(limits["max_input_chars"]),
            count(limits["max_objects"]),
            count(data["total_objects"]),
            batches,
            tuple(sorted((identifier(key), count(val)) for key, val in data["omissions"].items())),
        )
        if not 2 <= run.objects_per_batch <= 200 or not 2 <= run.max_objects <= 100_000:
            invalid("Invalid family-proposal object limits.")
        if not 2_000 <= run.max_input_chars <= 2_000_000:
            invalid("Invalid family-proposal input limit.")
        if (
            len(ids) > run.max_objects
            or len(ids) + sum(dict(run.omissions).values()) != run.total_objects
        ):
            invalid("Planned and omitted object counts must account for the physical population.")
        if any(len(batch.object_ids) > run.objects_per_batch for batch in batches):
            invalid("A proposal batch exceeds the declared object limit.")
        if run.to_dict() != data:
            invalid("Family-proposal content or revision is inconsistent.")
        return run
