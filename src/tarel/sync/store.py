"""Files under ``<state>/sync``. Packages never select this directory, so it never leaves a site.

``streams/<id>/head.json`` is the only authority on what is active. ``status.json`` beside it only
reports attempts, so losing it cannot change the active state.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tarel.atomic import sync_directory, write_atomic
from tarel.file_lock import file_lock
from tarel.graph.contracts import GraphDocument
from tarel.sync.contracts import (
    SYNC_STATE_VERSION,
    PublisherStream,
    StreamHead,
    SyncFailure,
    TrustedPublisher,
    TrustEntry,
    require_identity,
    require_name,
    sha256_hex,
)

if TYPE_CHECKING:
    from tarel.sync.impacts import ActiveImpacts


class FileSyncStore:
    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root
        self.root = state_root / "sync"

    @contextmanager
    def stream_lock(self, stream_id: str) -> Iterator[None]:
        """Serialize work on one stream. Other streams and central writers continue meanwhile."""
        try:
            with file_lock(self._central(stream_id) / ".lock"):
                yield
        except TimeoutError as exc:
            raise SyncFailure("sync_busy", f"Stream is busy; retry: {stream_id}") from exc

    @contextmanager
    def configuration_lock(self) -> Iterator[None]:
        """Serialize a site's counter and identities, and changes to central trust."""
        try:
            with file_lock(self.root / ".configuration.lock"):
                yield
        except TimeoutError as exc:
            raise SyncFailure("sync_busy", "Another sync operation is running; retry.") from exc

    def publisher_id(self) -> str | None:
        data = self._read(self.root / "publisher.json")
        return None if data is None else require_identity(data["publisher_id"], "pub", "publisher")

    def save_publisher_id(self, publisher_id: str) -> None:
        self._write(
            self.root / "publisher.json",
            {"contract_version": SYNC_STATE_VERSION, "publisher_id": publisher_id},
        )

    def graph_ids(self) -> dict[str, str]:
        data = self._read(self.root / "graph-ids.json")
        return {} if data is None else dict(data["graphs"])

    def save_graph_ids(self, graph_ids: dict[str, str]) -> None:
        self._write(
            self.root / "graph-ids.json",
            {"contract_version": SYNC_STATE_VERSION, "graphs": graph_ids},
        )

    def publisher_streams(self) -> tuple[PublisherStream, ...]:
        directory = self.root / "published"
        if not directory.is_dir():
            return ()
        return tuple(
            PublisherStream.from_dict(self._require(path))
            for path in sorted(directory.glob("*.json"))
        )

    def publisher_stream(self, name: str) -> PublisherStream:
        data = self._read(self._publisher_stream(name))
        if data is None:
            raise SyncFailure("stream_not_found", f"Stream not found: {name}")
        return PublisherStream.from_dict(data)

    def save_publisher_stream(self, stream: PublisherStream) -> None:
        self._write(self._publisher_stream(stream.name), stream.to_dict())

    def trust_entries(self) -> tuple[TrustEntry, ...]:
        data = self._read(self.root / "trust.json")
        if data is None:
            return ()
        return tuple(TrustEntry.from_dict(item) for item in data["entries"])

    def trusted_publishers(self) -> tuple[TrustedPublisher, ...]:
        data = self._read(self.root / "trust.json")
        if data is None:
            return ()
        return tuple(TrustedPublisher.from_dict(item) for item in data.get("publishers", ()))

    def save_trust_entries(self, entries: tuple[TrustEntry, ...]) -> None:
        self._save_trust(self.trusted_publishers(), entries)

    def save_trusted_publishers(self, publishers: tuple[TrustedPublisher, ...]) -> None:
        self._save_trust(publishers, self.trust_entries())

    def _save_trust(
        self, publishers: tuple[TrustedPublisher, ...], entries: tuple[TrustEntry, ...],
    ) -> None:
        self._write(
            self.root / "trust.json",
            {
                "contract_version": SYNC_STATE_VERSION,
                "entries": [
                    item.to_dict() for item in sorted(entries, key=lambda item: item.stream_id)
                ],
                "publishers": [
                    item.to_dict()
                    for item in sorted(publishers, key=lambda item: item.publisher_id)
                ],
            },
        )

    def trust_digest(self) -> str:
        try:
            return sha256_hex((self.root / "trust.json").read_bytes())
        except FileNotFoundError:
            return sha256_hex(b"")

    def head(self, stream_id: str) -> StreamHead | None:
        data = self._read(self._central(stream_id) / "head.json")
        return None if data is None else StreamHead.from_dict(data)

    def save_head(self, head: StreamHead) -> None:
        self._write(self._central(head.stream_id) / "head.json", head.to_dict())

    def status(self, stream_id: str) -> dict[str, Any]:
        return self._read(self._central(stream_id) / "status.json") or {}

    def save_status(self, stream_id: str, status: dict[str, Any]) -> None:
        self._write(self._central(stream_id) / "status.json", status)

    def incoming_directory(self) -> Path:
        return self.root / "incoming"

    def clear_abandoned_incoming(self, older_than_seconds: float = 3600) -> int:
        """A killed process leaves its private copy behind. It was never active, so it can go."""
        directory = self.incoming_directory()
        if not directory.is_dir():
            return 0
        limit = time.time() - older_than_seconds
        abandoned = [
            path
            for path in directory.glob(".incoming-*.tmp")
            if path.stat().st_mtime < limit
        ]
        for path in abandoned:
            path.unlink(missing_ok=True)
        return len(abandoned)

    def artifact_path(self, stream_id: str, publication_id: str) -> Path:
        return self._revision(stream_id, publication_id) / "artifact.tarelpub"

    def retain_artifact(self, frozen: Path, stream_id: str, publication_id: str) -> None:
        target = self.artifact_path(stream_id, publication_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            frozen.replace(target)
            sync_directory(target.parent)
        except OSError as exc:
            raise SyncFailure("sync_save_failed", f"Could not retain {target}") from exc

    def save_activation(self, stream_id: str, publication_id: str, graph: GraphDocument) -> None:
        """Keep the exact graph a head promises, so a crash can finish without recomputing it."""
        self._write(self._revision(stream_id, publication_id) / "activation.json", graph.to_dict())

    def load_activation(self, stream_id: str, publication_id: str) -> GraphDocument:
        data = self._require(self._revision(stream_id, publication_id) / "activation.json")
        return GraphDocument.from_dict(data)

    def impacts(self, stream_id: str, publication_id: str) -> ActiveImpacts | None:
        from tarel.sync.impacts import ActiveImpacts

        data = self._read(self._revision(stream_id, publication_id) / "impacts.json")
        return None if data is None else ActiveImpacts.from_dict(data)

    def save_impacts(
        self, stream_id: str, publication_id: str, impacts: ActiveImpacts,
    ) -> None:
        self._write(self._revision(stream_id, publication_id) / "impacts.json", impacts.to_dict())

    def revisions(self, stream_id: str) -> tuple[str, ...]:
        directory = self._central(stream_id) / "revisions"
        if not directory.is_dir():
            return ()
        return tuple(sorted(path.name for path in directory.iterdir() if path.is_dir()))

    def revision_directory(self, stream_id: str, publication_id: str) -> Path:
        return self._revision(stream_id, publication_id)

    def _central(self, stream_id: str) -> Path:
        return self.root / "streams" / require_identity(stream_id, "str", "stream ID")

    def _revision(self, stream_id: str, publication_id: str) -> Path:
        if len(publication_id) != 64 or not publication_id.isalnum():
            raise SyncFailure("invalid_sync_identity", f"Invalid publication: {publication_id!r}")
        return self._central(stream_id) / "revisions" / publication_id

    def _publisher_stream(self, name: str) -> Path:
        return self.root / "published" / f"{require_name(name, 'stream name')}.json"

    def _require(self, path: Path) -> dict[str, Any]:
        data = self._read(path)
        if data is None:
            raise SyncFailure("invalid_sync_state", f"Sync state is missing: {path}")
        return data

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncFailure("invalid_sync_state", f"Could not read sync state: {path}") from exc
        if not isinstance(data, dict):
            raise SyncFailure("invalid_sync_state", f"Sync state must be an object: {path}")
        return data

    def _write(self, path: Path, data: dict[str, Any]) -> None:
        text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            write_atomic(path, text, prefix=".sync-", durable=True, lock_root=self.state_root)
        except OSError as exc:
            raise SyncFailure("sync_save_failed", f"Could not save sync state: {path}") from exc
