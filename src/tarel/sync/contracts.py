"""Versioned contracts of a publication, its stream and the central record of it.

Three things stay apart on purpose: ``content_revision`` names what was observed, ``publication_id``
and ``sequence`` name one act of publishing it, and ``observed_at`` says when the source was read.
None of them decides a conflict by comparing clocks.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from tarel.errors import TarelError

PUBLICATION_CONTRACT_VERSION = "tarel.publication.v0.1"
SYNC_STATE_VERSION = "tarel.sync-state.v0.1"
RECENT_PUBLICATIONS = 64
COMPLETENESS_VALUES = frozenset({"complete", "partial"})
OBSERVATION_RECORDED = "recorded"
OBSERVATION_STATED = "stated"

_IDENTITY = re.compile(r"^(pub|gph|str)_[A-Za-z0-9]{8,64}$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_KEY_FINGERPRINT = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
_PUBLICATION_FIELDS = frozenset(
    {
        "completeness",
        "content_revision",
        "contract_version",
        "graph_id",
        "observation_source",
        "observed_at",
        "package_sha256",
        "profile",
        "publisher_id",
        "recent_publications",
        "scope",
        "sequence",
        "signing_key",
        "stream_id",
    }
)


class SyncFailure(TarelError):
    """Raised when a publication or central update is rejected."""


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_digest(value: object) -> str:
    """Digest of a value this process built itself; received documents are hashed as raw bytes."""
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256_hex(payload.encode("utf-8"))


def require_identity(value: object, prefix: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not _IDENTITY.fullmatch(value)
        or not value.startswith(f"{prefix}_")
    ):
        raise SyncFailure("invalid_sync_identity", f"Invalid {label}.")
    return value


def require_name(value: object, label: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise SyncFailure("invalid_sync_name", f"Invalid {label}.")
    return value


def require_timestamp(value: object, label: str) -> str:
    """Accept UTC only, so two sites can never state one instant in two spellings."""
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SyncFailure("invalid_timestamp", f"{label} must be UTC, ending in Z.")
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise SyncFailure("invalid_timestamp", f"Invalid {label}.") from exc
    return value


@dataclass(frozen=True, slots=True)
class ExportScope:
    """The approved part of a graph. Only what is listed here may leave the site."""

    namespaces: tuple[str, ...]
    annotations: bool = False
    technical_descriptions: bool = False

    @property
    def digest(self) -> str:
        return stable_digest(self._body())

    def _body(self) -> dict[str, object]:
        return {
            "annotations": self.annotations,
            "namespaces": sorted(self.namespaces),
            "technical_descriptions": self.technical_descriptions,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "digest": self.digest}

    @classmethod
    def from_dict(cls, data: object) -> ExportScope:
        if not isinstance(data, dict) or set(data) != {
            "annotations",
            "digest",
            "namespaces",
            "technical_descriptions",
        }:
            raise SyncFailure("invalid_publication", "Publication scope has the wrong fields.")
        namespaces = data["namespaces"]
        annotations = data["annotations"]
        descriptions = data["technical_descriptions"]
        if (
            not isinstance(namespaces, list)
            or not namespaces
            or not all(isinstance(item, str) and item for item in namespaces)
            or len(set(namespaces)) != len(namespaces)
            or not isinstance(annotations, bool)
            or not isinstance(descriptions, bool)
        ):
            raise SyncFailure("invalid_publication", "Publication scope is invalid.")
        scope = cls(tuple(sorted(namespaces)), annotations, descriptions)
        if data["digest"] != scope.digest:
            raise SyncFailure("invalid_publication", "Publication scope digest does not match.")
        return scope


@dataclass(frozen=True, slots=True)
class Publication:
    """The signed statement about one package. Parsed from exact bytes, never re-serialized."""

    publisher_id: str
    graph_id: str
    stream_id: str
    sequence: int
    recent_publications: tuple[str, ...]
    content_revision: str
    profile_id: str
    profile_version: int
    scope: ExportScope
    completeness: str
    observed_at: str
    package_sha256: str
    observation_source: str = OBSERVATION_RECORDED
    signing_key: str | None = None
    contract_version: str = PUBLICATION_CONTRACT_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "completeness": self.completeness,
            "content_revision": self.content_revision,
            "contract_version": self.contract_version,
            "graph_id": self.graph_id,
            "observation_source": self.observation_source,
            "observed_at": self.observed_at,
            "package_sha256": self.package_sha256,
            "profile": {"id": self.profile_id, "version": self.profile_version},
            "publisher_id": self.publisher_id,
            "recent_publications": list(self.recent_publications),
            "scope": self.scope.to_dict(),
            "sequence": self.sequence,
            "signing_key": self.signing_key,
            "stream_id": self.stream_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Publication:
        # The version comes first: fields of an unknown contract mean nothing yet.
        if data.get("contract_version") != PUBLICATION_CONTRACT_VERSION:
            raise SyncFailure("unsupported_contract", "Unsupported publication contract.")
        if set(data) != _PUBLICATION_FIELDS:
            raise SyncFailure("invalid_publication", "Publication has the wrong fields.")
        sequence = data["sequence"]
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise SyncFailure("invalid_publication", "Publication sequence must be positive.")
        recent = data["recent_publications"]
        if (
            not isinstance(recent, list)
            or len(recent) > RECENT_PUBLICATIONS
            or not all(_is_sha256(item) for item in recent)
        ):
            raise SyncFailure("invalid_publication", "Publication history is invalid.")
        profile = data["profile"]
        if (
            not isinstance(profile, dict)
            or set(profile) != {"id", "version"}
            or not isinstance(profile["version"], int)
            or isinstance(profile["version"], bool)
            or profile["version"] < 1
        ):
            raise SyncFailure("invalid_publication", "Publication profile is invalid.")
        completeness = data["completeness"]
        # A JSON list cannot even be looked up in a set, and nobody has checked this sender yet.
        if not isinstance(completeness, str) or completeness not in COMPLETENESS_VALUES:
            raise SyncFailure("invalid_publication", "Publication completeness is invalid.")
        signing_key = data["signing_key"]
        if signing_key is not None and not (
            isinstance(signing_key, str) and _KEY_FINGERPRINT.fullmatch(signing_key)
        ):
            raise SyncFailure("invalid_publication", "Signing key must be a SHA256 fingerprint.")
        source = data["observation_source"]
        if not isinstance(source, str) or source not in {OBSERVATION_RECORDED, OBSERVATION_STATED}:
            raise SyncFailure("invalid_publication", "Publication observation source is invalid.")
        for key in ("content_revision", "package_sha256"):
            if not _is_sha256(data[key]):
                raise SyncFailure("invalid_publication", f"Publication {key} is not SHA-256.")
        return cls(
            publisher_id=require_identity(data["publisher_id"], "pub", "publisher ID"),
            graph_id=require_identity(data["graph_id"], "gph", "graph ID"),
            stream_id=require_identity(data["stream_id"], "str", "stream ID"),
            sequence=sequence,
            recent_publications=tuple(recent),
            content_revision=data["content_revision"],
            profile_id=require_name(profile["id"], "profile ID"),
            profile_version=profile["version"],
            scope=ExportScope.from_dict(data["scope"]),
            completeness=completeness,
            observed_at=require_timestamp(data["observed_at"], "observed_at"),
            package_sha256=data["package_sha256"],
            observation_source=source,
            signing_key=signing_key,
        )


@dataclass(frozen=True, slots=True)
class PublisherStream:
    """A site's own record of one stream. Its counter never moves backwards."""

    name: str
    stream_id: str
    graph: str
    graph_id: str
    scope: ExportScope
    profile_version: int = 1
    sequence: int = 0
    recent_publications: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": SYNC_STATE_VERSION,
            "graph": self.graph,
            "graph_id": self.graph_id,
            "name": self.name,
            "profile_version": self.profile_version,
            "recent_publications": list(self.recent_publications),
            "scope": self.scope.to_dict(),
            "sequence": self.sequence,
            "stream_id": self.stream_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PublisherStream:
        _require_state_version(data)
        return cls(
            name=require_name(data["name"], "stream name"),
            stream_id=require_identity(data["stream_id"], "str", "stream ID"),
            graph=require_name(data["graph"], "graph name"),
            graph_id=require_identity(data["graph_id"], "gph", "graph ID"),
            scope=ExportScope.from_dict(data["scope"]),
            profile_version=int(data["profile_version"]),
            sequence=int(data["sequence"]),
            recent_publications=tuple(data["recent_publications"]),
        )


@dataclass(frozen=True, slots=True)
class TrustedKey:
    """One signing key of a publisher, as far as this state has been told about it.

    An offline state only knows what reached it, so a revocation takes effect here when it is
    entered here, not when it was decided elsewhere.
    """

    public_key: str
    fingerprint: str
    revoked: bool = False
    not_after: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "fingerprint": self.fingerprint,
            "not_after": self.not_after,
            "public_key": self.public_key,
            "revoked": self.revoked,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrustedKey:
        not_after = data.get("not_after")
        return cls(
            public_key=str(data["public_key"]),
            fingerprint=str(data["fingerprint"]),
            revoked=bool(data.get("revoked", False)),
            not_after=None if not_after is None else require_timestamp(not_after, "not_after"),
        )


@dataclass(frozen=True, slots=True)
class TrustedPublisher:
    publisher_id: str
    keys: tuple[TrustedKey, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "keys": [item.to_dict() for item in sorted(self.keys, key=lambda k: k.fingerprint)],
            "publisher_id": self.publisher_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrustedPublisher:
        return cls(
            publisher_id=require_identity(data.get("publisher_id"), "pub", "publisher ID"),
            keys=tuple(TrustedKey.from_dict(item) for item in data["keys"]),
        )


@dataclass(frozen=True, slots=True)
class TrustEntry:
    """Central permission for one stream. Written locally; a package can never add or widen one."""

    publisher_id: str
    stream_id: str
    graph_id: str
    local_graph: str
    workspace: str
    system: str
    namespaces: tuple[str, ...]
    annotations: bool = False
    technical_descriptions: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "annotations": self.annotations,
            "graph_id": self.graph_id,
            "local_graph": self.local_graph,
            "namespaces": sorted(self.namespaces),
            "publisher_id": self.publisher_id,
            "stream_id": self.stream_id,
            "system": self.system,
            "technical_descriptions": self.technical_descriptions,
            "workspace": self.workspace,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrustEntry:
        return cls(
            publisher_id=require_identity(data.get("publisher_id"), "pub", "publisher ID"),
            stream_id=require_identity(data.get("stream_id"), "str", "stream ID"),
            graph_id=require_identity(data.get("graph_id"), "gph", "graph ID"),
            local_graph=require_name(data.get("local_graph"), "local graph"),
            workspace=require_name(data.get("workspace"), "workspace"),
            system=require_name(data.get("system"), "system"),
            namespaces=_namespaces(data.get("namespaces")),
            annotations=data.get("annotations") is True,
            technical_descriptions=data.get("technical_descriptions") is True,
        )


@dataclass(frozen=True, slots=True)
class PendingActivation:
    """The graph write a committed head still owes. A later run finishes it after a crash."""

    graph_before: str | None
    graph_after: str
    first_activation: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "first_activation": self.first_activation,
            "graph_after": self.graph_after,
            "graph_before": self.graph_before,
        }


@dataclass(frozen=True, slots=True)
class StreamHead:
    """The authoritative answer to which publication of a stream is active."""

    stream_id: str
    publisher_id: str
    graph_id: str
    local_graph: str
    publication_id: str
    sequence: int
    content_revision: str
    observed_at: str
    accepted_at: str
    content_activated_by: str
    scope: ExportScope
    profile_version: int
    pending: PendingActivation | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted_at": self.accepted_at,
            "content_activated_by": self.content_activated_by,
            "content_revision": self.content_revision,
            "contract_version": SYNC_STATE_VERSION,
            "graph_id": self.graph_id,
            "local_graph": self.local_graph,
            "observed_at": self.observed_at,
            "pending": self.pending.to_dict() if self.pending else None,
            "profile_version": self.profile_version,
            "publication_id": self.publication_id,
            "publisher_id": self.publisher_id,
            "scope": self.scope.to_dict(),
            "sequence": self.sequence,
            "stream_id": self.stream_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StreamHead:
        _require_state_version(data)
        pending = data["pending"]
        return cls(
            stream_id=data["stream_id"],
            publisher_id=data["publisher_id"],
            graph_id=data["graph_id"],
            local_graph=data["local_graph"],
            publication_id=data["publication_id"],
            sequence=data["sequence"],
            content_revision=data["content_revision"],
            observed_at=data["observed_at"],
            accepted_at=data["accepted_at"],
            content_activated_by=data["content_activated_by"],
            scope=ExportScope.from_dict(data["scope"]),
            profile_version=data["profile_version"],
            pending=None if pending is None else PendingActivation(
                graph_before=pending["graph_before"],
                graph_after=pending["graph_after"],
                first_activation=pending["first_activation"],
            ),
        )


def _namespaces(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, (list, tuple))
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise SyncFailure("invalid_scope", "A trust entry must allow at least one namespace.")
    return tuple(sorted(set(value)))


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _require_state_version(data: dict[str, Any]) -> None:
    if data.get("contract_version") != SYNC_STATE_VERSION:
        raise SyncFailure(
            "unsupported_sync_state",
            f"Unsupported sync state: {data.get('contract_version')!r}",
        )
