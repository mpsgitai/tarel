"""Pure rules: how a publication relates to history, and how it meets central knowledge."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from tarel.graph.contracts import (
    SYNC_ORIGIN_KEY,
    AnnotationProvenance,
    GraphAnnotation,
    GraphDocument,
    GraphNode,
)
from tarel.graph.refresh import GraphRefreshReport, refresh_graph
from tarel.graph.revision import graph_revision
from tarel.sync.contracts import (
    RECENT_PUBLICATIONS,
    Publication,
    StreamHead,
    SyncFailure,
)

ACTION_FIRST = "first_activation"
ACTION_NONE = "already_active"
ACTION_FRESHNESS = "confirm_freshness"
ACTION_UPDATE = "update_content"
PUBLISHED_ANNOTATION_KEY = "published_annotation"
_KEEPS_STATE = frozenset({"deferred", "draft", "rejected"})


def classify(
    publication: Publication,
    publication_id: str,
    head: StreamHead | None,
    *,
    accept_history_gap: bool = False,
) -> tuple[str, tuple[str, ...]]:
    """Decide from sequence and history alone; a clock never settles which publication wins."""
    if head is not None and publication_id == head.publication_id:
        return ACTION_NONE, ()
    if publication.completeness != "complete":
        raise SyncFailure(
            "incomplete_snapshot",
            f"Publication {publication.sequence} is {publication.completeness}; "
            "it proves no deletion, so the active state stays.",
        )
    if head is None:
        return ACTION_FIRST, ()
    if publication.sequence < head.sequence:
        raise SyncFailure(
            "stale_publication",
            f"Publication {publication.sequence} is older than active {head.sequence}.",
        )
    if publication.sequence == head.sequence:
        raise SyncFailure(
            "publication_conflict",
            f"Two different publications claim sequence {head.sequence} of this stream.",
        )
    warnings: list[str] = []
    _check_profile_history(publication, head)
    if head.publication_id not in publication.recent_publications:
        if not accept_history_gap:
            if len(publication.recent_publications) < RECENT_PUBLICATIONS:
                raise SyncFailure(
                    "publication_conflict",
                    f"Publication {publication.sequence} does not descend from active "
                    f"{head.sequence}; two writers may share this stream identity. If this writer "
                    "is the right one, for example after restoring a backup, accept it explicitly.",
                )
            raise SyncFailure(
                "history_gap",
                f"Active {head.sequence} is older than the history publication "
                f"{publication.sequence} can vouch for; accept the gap explicitly to continue.",
            )
        warnings.append(f"Accepted without history from {head.sequence}.")
    elif publication.sequence > head.sequence + 1:
        warnings.append(
            f"Skipped publications {head.sequence + 1}..{publication.sequence - 1}; "
            "this complete snapshot replaces them."
        )
    if publication.content_revision == head.content_revision:
        return ACTION_FRESHNESS, tuple(warnings)
    return ACTION_UPDATE, tuple(warnings)


def _check_profile_history(publication: Publication, head: StreamHead) -> None:
    """A scope may only change under a new profile version, so no change can pass unnoticed."""
    if publication.profile_version < head.profile_version:
        raise SyncFailure(
            "publication_conflict",
            f"Profile version {publication.profile_version} is older than active "
            f"{head.profile_version}.",
        )
    if (
        publication.profile_version == head.profile_version
        and publication.scope.digest != head.scope.digest
    ):
        raise SyncFailure(
            "publication_conflict",
            "Scope changed without a new profile version.",
        )


def base_materialization(
    published: GraphDocument, publication: Publication, local_graph: str,
) -> GraphDocument:
    """A publication as central state shows it when nothing central was added to it.

    A site's review state is its own: the claim keeps it word for word in metadata, while the
    visible annotation is at most a draft until someone here decides otherwise.
    """
    origin = {"graph_id": publication.graph_id, "publisher_id": publication.publisher_id}
    stream = {**origin, "stream_id": publication.stream_id}
    nodes = tuple(_materialize_node(node, origin, stream) for node in published.nodes)
    return replace(published, name=local_graph, nodes=nodes)


@dataclass(frozen=True, slots=True)
class Merged:
    graph: GraphDocument
    report: GraphRefreshReport | None
    restored: tuple[str, ...] = ()


def merge(
    current: GraphDocument | None,
    previous_base: GraphDocument | None,
    incoming_base: GraphDocument,
    retired: Mapping[str, Mapping[str, Any]] | None = None,
) -> Merged:
    """Adopt the site's observations and keep whatever central state changed itself.

    An annotation counts as central when it differs from what the last activation wrote, so a human
    decision on an imported claim survives, while an untouched imported claim simply follows the
    site. A central statement whose object left comes back with the object, flagged for review if
    it had been validated, because the source may have changed in between.
    """
    if current is None:
        return Merged(incoming_base, None)
    known = previous_base.node_by_id() if previous_base is not None else {}
    central_only = replace(
        current,
        nodes=tuple(_central_annotation_only(node, known.get(node.id)) for node in current.nodes),
    )
    observed = replace(
        incoming_base,
        nodes=tuple(replace(node, annotation=None) for node in incoming_base.nodes),
    )
    refreshed, report = refresh_graph(central_only, observed)
    published = incoming_base.node_by_id()
    returning = retired or {}
    restored: list[str] = []
    nodes: list[GraphNode] = []
    for node in refreshed.nodes:
        if node.annotation is not None:
            nodes.append(node)
        elif node.id in returning:
            nodes.append(_restore(node, returning[node.id]))
            restored.append(node.id)
        else:
            nodes.append(replace(node, annotation=published[node.id].annotation))
    graph = replace(refreshed, nodes=tuple(nodes))
    return Merged(
        graph,
        replace(
            report,
            before_revision=graph_revision(current),
            after_revision=graph_revision(graph),
        ),
        tuple(restored),
    )


def _restore(node: GraphNode, claim: Mapping[str, Any]) -> GraphNode:
    annotation = GraphAnnotation.from_dict(claim["claim"]["annotation"])
    if annotation.state != "validated":
        return replace(node, annotation=annotation)
    return replace(
        node,
        annotation=replace(annotation, state="review_required"),
        metadata={**node.metadata, "change_review": {"reasons": ["object_returned"]}},
    )


def _central_annotation_only(node: GraphNode, known: GraphNode | None) -> GraphNode:
    if known is not None and node.annotation == known.annotation:
        return replace(node, annotation=None)
    return node


def _materialize_node(
    node: GraphNode, origin: dict[str, str], stream: dict[str, str],
) -> GraphNode:
    if node.type == "catalog":
        node = replace(node, metadata={**node.metadata, SYNC_ORIGIN_KEY: stream})
    if node.annotation is None:
        return node
    metadata = {
        **node.metadata,
        PUBLISHED_ANNOTATION_KEY: {"annotation": node.annotation.to_dict(), "origin": origin},
    }
    return replace(node, metadata=metadata, annotation=_imported(node.annotation, origin))


def _imported(annotation: GraphAnnotation, origin: dict[str, str]) -> GraphAnnotation:
    state = annotation.state if annotation.state in _KEEPS_STATE else "draft"
    return replace(
        annotation,
        state=state,
        provenance=AnnotationProvenance(
            source=f"sync:{origin['publisher_id']}",
            provider=annotation.provenance.provider,
            model=annotation.provenance.model,
        ),
    )
