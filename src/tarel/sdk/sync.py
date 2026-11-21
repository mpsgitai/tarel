"""``tarel.sync``: publish approved metadata from a site and take it over centrally."""

from __future__ import annotations

from pathlib import Path

from tarel.sdk._base import RuntimeAPI, optional_path
from tarel.sync.admin_application import (
    add_trust_use_case,
    inspect_publication_use_case,
    prune_revisions_use_case,
    revoke_key_use_case,
    set_trust_scope_use_case,
    sync_status_use_case,
    trust_key_use_case,
)
from tarel.sync.application import (
    apply_publication_use_case,
    plan_publication_use_case,
    recover_activations_use_case,
)
from tarel.sync.contracts import PublisherStream, TrustedKey, TrustEntry
from tarel.sync.inbox import process_inbox_use_case
from tarel.sync.publish_application import (
    create_stream_use_case,
    init_publisher_use_case,
    publish_use_case,
    update_stream_use_case,
)
from tarel.sync.results import (
    ApplyResult,
    InboxResult,
    PruneResult,
    PublicationReport,
    PublishResult,
    StreamStatus,
    SyncPlan,
)


class SyncAPI(RuntimeAPI):
    """The same use cases and failures as ``tarel sync``, with typed results."""

    def init_publisher(self) -> str:
        return init_publisher_use_case(runtime=self._runtime)

    def create_stream(
        self,
        name: str,
        *,
        graph: str,
        namespaces: tuple[str, ...],
        annotations: bool = False,
        technical_descriptions: bool = False,
    ) -> PublisherStream:
        return create_stream_use_case(
            name,
            graph=graph,
            namespaces=namespaces,
            annotations=annotations,
            technical_descriptions=technical_descriptions,
            runtime=self._runtime,
        )

    def update_stream(
        self,
        name: str,
        *,
        namespaces: tuple[str, ...],
        annotations: bool = False,
        technical_descriptions: bool = False,
    ) -> PublisherStream:
        return update_stream_use_case(
            name,
            namespaces=namespaces,
            annotations=annotations,
            technical_descriptions=technical_descriptions,
            runtime=self._runtime,
        )

    def publish(
        self,
        stream: str,
        *,
        output: str | Path,
        observed_at: str | None = None,
        completeness: str | None = None,
        signing_key: str | Path | None = None,
        unsigned_dev: bool = False,
    ) -> PublishResult:
        return publish_use_case(
            stream,
            output=Path(output),
            observed_at=observed_at,
            completeness=completeness,
            signing_key=optional_path(signing_key),
            unsigned_dev=unsigned_dev,
            runtime=self._runtime,
        )

    def inspect(self, path: str | Path) -> PublicationReport:
        return inspect_publication_use_case(Path(path))

    def trust(
        self,
        *,
        publisher_id: str,
        stream_id: str,
        graph_id: str,
        local_graph: str,
        workspace: str,
        system: str,
        namespaces: tuple[str, ...],
        annotations: bool = False,
        technical_descriptions: bool = False,
    ) -> TrustEntry:
        return add_trust_use_case(
            publisher_id=publisher_id,
            stream_id=stream_id,
            graph_id=graph_id,
            local_graph=local_graph,
            workspace=workspace,
            system=system,
            namespaces=namespaces,
            annotations=annotations,
            technical_descriptions=technical_descriptions,
            runtime=self._runtime,
        )

    def set_trust_scope(
        self,
        stream_id: str,
        *,
        namespaces: tuple[str, ...],
        annotations: bool = False,
        technical_descriptions: bool = False,
    ) -> TrustEntry:
        return set_trust_scope_use_case(
            stream_id,
            namespaces=namespaces,
            annotations=annotations,
            technical_descriptions=technical_descriptions,
            runtime=self._runtime,
        )

    def trust_key(
        self, publisher_id: str, *, public_key: str, not_after: str | None = None,
    ) -> TrustedKey:
        return trust_key_use_case(
            publisher_id, public_key=public_key, not_after=not_after, runtime=self._runtime,
        )

    def revoke_key(self, publisher_id: str, fingerprint: str) -> TrustedKey:
        return revoke_key_use_case(publisher_id, fingerprint, runtime=self._runtime)

    def plan(
        self,
        path: str | Path,
        *,
        allow_unsigned_dev: bool = False,
        accept_history_gap: bool = False,
    ) -> SyncPlan:
        return plan_publication_use_case(
            Path(path),
            allow_unsigned_dev=allow_unsigned_dev,
            accept_history_gap=accept_history_gap,
            runtime=self._runtime,
        )

    def apply(
        self,
        path: str | Path,
        *,
        plan_id: str | None = None,
        allow_unsigned_dev: bool = False,
        accept_history_gap: bool = False,
    ) -> ApplyResult:
        return apply_publication_use_case(
            Path(path),
            plan_id=plan_id,
            allow_unsigned_dev=allow_unsigned_dev,
            accept_history_gap=accept_history_gap,
            runtime=self._runtime,
        )

    def recover(self) -> tuple[str, ...]:
        return recover_activations_use_case(runtime=self._runtime)

    def process_inbox(
        self,
        directory: str | Path,
        *,
        min_age_seconds: float = 0,
        allow_unsigned_dev: bool = False,
    ) -> InboxResult:
        return process_inbox_use_case(
            Path(directory),
            min_age_seconds=min_age_seconds,
            allow_unsigned_dev=allow_unsigned_dev,
            runtime=self._runtime,
        )

    def status(self, *, max_age_hours: float | None = None) -> tuple[StreamStatus, ...]:
        return sync_status_use_case(max_age_hours=max_age_hours, runtime=self._runtime)

    def prune(self, stream_id: str) -> PruneResult:
        return prune_revisions_use_case(stream_id, runtime=self._runtime)
