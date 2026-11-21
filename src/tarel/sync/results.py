"""Typed results of the sync use cases, identical for CLI and SDK."""

from __future__ import annotations

from dataclasses import dataclass, field

from tarel.sync.contracts import Publication, StreamHead


@dataclass(frozen=True, slots=True)
class PublishResult:
    path: str
    publication_id: str
    publication: Publication
    artifact_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "path": self.path,
            "publication": self.publication.to_dict(),
            "publication_id": self.publication_id,
        }


@dataclass(frozen=True, slots=True)
class PublicationReport:
    """What a file claims. Reading it says nothing yet about whether this state trusts it."""

    publication_id: str
    artifact_sha256: str
    signed: bool
    publication: Publication
    graph: str
    objects: int
    signature_verified: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "graph": self.graph,
            "objects": self.objects,
            "publication": self.publication.to_dict(),
            "publication_id": self.publication_id,
            "signature_verified": self.signature_verified,
            "signed": self.signed,
        }


@dataclass(frozen=True, slots=True)
class SyncPlan:
    """What applying one file would do. ``plan_id`` changes whenever a basis of the plan changes.

    A deleted object was gone from a scope the site still approves. A withdrawn one left because
    the site stopped approving its namespace, which says nothing about the source.
    """

    plan_id: str
    action: str
    stream_id: str
    publisher_id: str
    local_graph: str
    publication_id: str
    artifact_sha256: str
    sequence: int
    previous_publication_id: str | None
    previous_sequence: int | None
    content_changed: bool
    objects_added: tuple[str, ...] = ()
    objects_changed: tuple[str, ...] = ()
    objects_deleted: tuple[str, ...] = ()
    objects_withdrawn: tuple[str, ...] = ()
    scope_change: dict[str, object] | None = None
    affected_claims: tuple[dict[str, object], ...] = ()
    restored_claims: tuple[str, ...] = ()
    dangling_references: tuple[dict[str, str], ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "affected_claims": list(self.affected_claims),
            "artifact_sha256": self.artifact_sha256,
            "content_changed": self.content_changed,
            "dangling_references": list(self.dangling_references),
            "local_graph": self.local_graph,
            "objects_added": list(self.objects_added),
            "objects_changed": list(self.objects_changed),
            "objects_deleted": list(self.objects_deleted),
            "objects_withdrawn": list(self.objects_withdrawn),
            "plan_id": self.plan_id,
            "previous_publication_id": self.previous_publication_id,
            "previous_sequence": self.previous_sequence,
            "publication_id": self.publication_id,
            "publisher_id": self.publisher_id,
            "restored_claims": list(self.restored_claims),
            "scope_change": self.scope_change,
            "sequence": self.sequence,
            "stream_id": self.stream_id,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class StreamStatus:
    """One origin's state, with source age, receipt and acceptance kept apart."""

    stream_id: str
    publisher_id: str
    local_graph: str
    active_publication_id: str | None = None
    active_sequence: int | None = None
    active_content_revision: str | None = None
    observed_at: str | None = None
    accepted_at: str | None = None
    observation_age_seconds: int | None = None
    stale: bool | None = None
    activation_pending: bool = False
    last_received: dict[str, object] | None = None
    last_failure: dict[str, object] | None = None
    removals: tuple[dict[str, str], ...] = ()
    retired_claims: tuple[dict[str, object], ...] = ()
    dangling_references: tuple[dict[str, str], ...] = ()
    retained_revisions: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted_at": self.accepted_at,
            "activation_pending": self.activation_pending,
            "active_content_revision": self.active_content_revision,
            "active_publication_id": self.active_publication_id,
            "active_sequence": self.active_sequence,
            "dangling_references": list(self.dangling_references),
            "last_failure": self.last_failure,
            "last_received": self.last_received,
            "local_graph": self.local_graph,
            "observation_age_seconds": self.observation_age_seconds,
            "observed_at": self.observed_at,
            "publisher_id": self.publisher_id,
            "removals": list(self.removals),
            "retained_revisions": self.retained_revisions,
            "retired_claims": list(self.retired_claims),
            "stale": self.stale,
            "stream_id": self.stream_id,
        }


@dataclass(frozen=True, slots=True)
class ApplyResult:
    plan: SyncPlan
    applied: bool
    head: StreamHead | None = field(default=None)

    def to_dict(self) -> dict[str, object]:
        return {
            "applied": self.applied,
            "head": self.head.to_dict() if self.head else None,
            "plan": self.plan.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class InboxItem:
    """What one pass did with one file. ``deferred`` files stay in place for the next pass."""

    name: str
    outcome: str
    action: str | None = None
    code: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "code": self.code,
            "message": self.message,
            "name": self.name,
            "outcome": self.outcome,
        }


@dataclass(frozen=True, slots=True)
class InboxResult:
    items: tuple[InboxItem, ...] = ()

    @property
    def rejected(self) -> int:
        return sum(item.outcome == "rejected" for item in self.items)

    def to_dict(self) -> dict[str, object]:
        return {"items": [item.to_dict() for item in self.items], "rejected": self.rejected}


@dataclass(frozen=True, slots=True)
class PruneResult:
    """Old revisions physically removed. The active view did not change."""

    stream_id: str
    removed: tuple[str, ...]
    kept: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "kept": list(self.kept),
            "removed": list(self.removed),
            "stream_id": self.stream_id,
        }
