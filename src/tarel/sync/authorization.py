"""Who sent a publication, and what that sender may publish. Local trust decides both."""

from __future__ import annotations

from datetime import UTC, datetime

from tarel.sync.contracts import Publication, SyncFailure, TrustEntry, instant
from tarel.sync.envelope import SignedStatement
from tarel.sync.signing import verify_statement
from tarel.sync.store import FileSyncStore


def trusted_entry(store: FileSyncStore, publication: Publication) -> TrustEntry:
    entries = store.trust_entries()
    if not any(item.publisher_id == publication.publisher_id for item in entries):
        raise SyncFailure("untrusted_publisher", f"Unknown publisher: {publication.publisher_id}")
    entry = next(
        (
            item
            for item in entries
            if item.publisher_id == publication.publisher_id
            and item.stream_id == publication.stream_id
        ),
        None,
    )
    if entry is None or entry.graph_id != publication.graph_id:
        raise SyncFailure(
            "unauthorized_scope",
            f"Publisher {publication.publisher_id} may not write stream {publication.stream_id} "
            f"of graph {publication.graph_id}.",
        )
    return entry


def check_sender(
    store: FileSyncStore,
    statement: SignedStatement,
    entry: TrustEntry,
    *,
    allow_unsigned_dev: bool,
) -> None:
    """Who sent this, then whether they may say it. A good signature grants no permission."""
    _check_signature(store, statement, allow_unsigned_dev=allow_unsigned_dev)
    scope = statement.publication.scope
    if set(scope.namespaces) - set(entry.namespaces):
        raise SyncFailure(
            "unauthorized_scope",
            f"Stream {entry.stream_id} declares namespaces outside what it may publish.",
        )
    if scope.annotations and not entry.annotations:
        raise SyncFailure(
            "unauthorized_scope", f"Stream {entry.stream_id} may not publish annotations.",
        )
    if scope.technical_descriptions and not entry.technical_descriptions:
        raise SyncFailure(
            "unauthorized_scope", f"Stream {entry.stream_id} may not publish descriptions.",
        )


def _check_signature(
    store: FileSyncStore, statement: SignedStatement, *, allow_unsigned_dev: bool,
) -> None:
    publication = statement.publication
    named = publication.signing_key
    if (statement.signature is None) != (named is None):
        # Either a removed signature or one the statement never agreed to; no flag excuses this.
        raise SyncFailure("invalid_signature", "Statement and signature do not belong together.")
    if statement.signature is None or named is None:
        if not allow_unsigned_dev:
            raise SyncFailure(
                "unsigned_publication",
                "Unsigned publications are accepted only with the development flag.",
            )
        return
    publisher = next(
        (
            item
            for item in store.trusted_publishers()
            if item.publisher_id == publication.publisher_id
        ),
        None,
    )
    key = next(
        (item for item in (publisher.keys if publisher else ()) if item.fingerprint == named),
        None,
    )
    if key is None:
        raise SyncFailure("unknown_signing_key", f"Key is not trusted for this publisher: {named}")
    if key.revoked:
        raise SyncFailure("revoked_signing_key", f"Key is revoked here: {named}")
    if key.not_after is not None and datetime.now(UTC) > instant(key.not_after):
        raise SyncFailure("expired_signing_key", f"Key expired at {key.not_after}: {named}")
    verify_statement(statement.statement, statement.signature, key.public_key)
