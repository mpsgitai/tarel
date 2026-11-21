"""Hybrid ranking over a retrieval index: BM25, vectors and reciprocal rank fusion."""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from tarel.annotations.states import DEFAULT_CONTEXT_ANNOTATION_STATES
from tarel.graph.contracts import GraphDocument
from tarel.retrieval.bm25 import rank_bm25, tokenize
from tarel.retrieval.contracts import (
    EmbeddingBackend,
    RankedDocument,
    RetrievalDocument,
    RetrievalFailure,
)
from tarel.retrieval.documents import build_retrieval_documents
from tarel.retrieval.index import FileRetrievalIndex, embedding_input_warning
from tarel.search import FieldSearchHit, SearchHit, SearchResults

_RRF_K = 60


_RESULT_SCORE_SCALE = 1_000_000


_MAX_SAFE_BM25_WEIGHT = sys.float_info.max / _RESULT_SCORE_SCALE


DEFAULT_BM25_WEIGHT = 1.0


_MAX_FIELDS = 8


def search_retrieval(
    graph: GraphDocument,
    query: str,
    *,
    mode: str,
    limit: int,
    namespace: str | None = None,
    object_ids: frozenset[str] | None = None,
    embedder: EmbeddingBackend | None = None,
    model_path: Path | None = None,
    store: FileRetrievalIndex | None = None,
    annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    bm25_weight: float | None = None,
    query_vector: tuple[float, ...] | None = None,
    vector_backend: str = "auto",
    model_sha256: str | None = None,
) -> SearchResults:
    if mode not in {"bm25", "vector", "hybrid"}:
        raise RetrievalFailure("invalid_retrieval_mode", "Mode must be bm25, vector, or hybrid.")
    if not 1 <= limit <= 100:
        raise RetrievalFailure("invalid_limit", "Search limit must be between 1 and 100.")
    weight = validate_bm25_weight(mode, bm25_weight)
    all_documents = build_retrieval_documents(graph, annotation_states=annotation_states)
    documents = tuple(
        document
        for document in all_documents
        if namespace is None or document.namespace.casefold() == namespace.casefold()
        if object_ids is None or document.object_id in object_ids
    )
    candidate_limit = max(20, min(len(documents), limit * 5))
    bm25_results = (
        rank_bm25(documents, query, limit=candidate_limit) if mode in {"bm25", "hybrid"} else ()
    )
    vector_results: tuple[RankedDocument, ...] = ()
    warnings: tuple[str, ...] = ()
    if mode in {"vector", "hybrid"}:
        if embedder is None or (model_path is None and model_sha256 is None):
            raise RetrievalFailure("missing_embedding_backend", "Vector retrieval needs a model.")
        if query_vector is None:
            # Reject missing/stale indexes before a potentially paid embedding request.
            (store or FileRetrievalIndex()).validate_selection(
                graph, model_path=model_path, model_sha256=model_sha256,
                annotation_states=annotation_states,
            )
        selected_query_vector = query_vector or embedder.embed_query(query)
        vector_results = (store or FileRetrievalIndex()).rank(
            graph,
            model_path=model_path,
            model_sha256=model_sha256,
            query_vector=selected_query_vector,
            limit=candidate_limit,
            namespace=namespace,
            object_ids=object_ids,
            annotation_states=annotation_states,
            backend=vector_backend,
        )
        warning = embedding_input_warning(
            (store or FileRetrievalIndex()).metadata(
                graph.name, annotation_states=annotation_states,
            )
        )
        warnings = (warning,) if warning else ()

    if mode == "bm25":
        ranked = bm25_results
    elif mode == "vector":
        ranked = vector_results
    else:
        ranked = _reciprocal_rank_fusion(
            bm25_results, vector_results, limit=candidate_limit, bm25_weight=weight,
        )
    return replace(
        _object_results(graph, query, mode=mode, ranked=ranked, limit=limit),
        warnings=warnings,
    )


def validate_bm25_weight(mode: str, weight: float | None) -> float:
    if weight is None:
        return DEFAULT_BM25_WEIGHT
    if mode != "hybrid":
        raise RetrievalFailure(
            "invalid_bm25_weight", "BM25 weight is only available in hybrid mode."
        )
    if (
        isinstance(weight, bool)
        or not isinstance(weight, (int, float))
        or weight < 0
        or weight > _MAX_SAFE_BM25_WEIGHT
        or not math.isfinite(weight)
    ):
        raise RetrievalFailure(
            "invalid_bm25_weight",
            "BM25 weight must be a finite nonnegative number within the supported score range.",
        )
    return float(weight)


def _reciprocal_rank_fusion(
    left: tuple[RankedDocument, ...],
    right: tuple[RankedDocument, ...],
    *,
    limit: int,
    bm25_weight: float = DEFAULT_BM25_WEIGHT,
) -> tuple[RankedDocument, ...]:
    scores: defaultdict[str, float] = defaultdict(float)
    sources: defaultdict[str, set[str]] = defaultdict(set)
    documents: dict[str, RetrievalDocument] = {}
    for results, weight in ((left, bm25_weight), (right, 1.0)):
        if weight == 0:
            continue
        for rank, result in enumerate(results, start=1):
            document_id = result.document.id
            documents[document_id] = result.document
            scores[document_id] += weight / (_RRF_K + rank)
            sources[document_id].update(result.sources)
    return tuple(
        sorted(
            (
                RankedDocument(
                    document=documents[document_id],
                    score=score,
                    sources=tuple(sorted(sources[document_id])),
                )
                for document_id, score in scores.items()
            ),
            key=lambda item: (-item.score, item.document.label.casefold(), item.document.id),
        )[:limit]
    )


def _object_results(
    graph: GraphDocument,
    query: str,
    *,
    mode: str,
    ranked: tuple[RankedDocument, ...],
    limit: int,
) -> SearchResults:
    node_by_id = graph.node_by_id()
    by_object: defaultdict[str, list[RankedDocument]] = defaultdict(list)
    for result in ranked:
        by_object[result.document.object_id].append(result)
    query_terms = tuple(sorted(set(tokenize(query))))
    hits: list[SearchHit] = []
    for object_id, results in by_object.items():
        node = node_by_id.get(object_id)
        if node is None or node.type not in {"table", "view"}:
            continue
        ordered = sorted(results, key=lambda item: (-item.score, item.document.id))
        best = ordered[0]
        fields = tuple(
            FieldSearchHit(
                id=result.document.field_id or "",
                label=result.document.label.rsplit(".", 1)[-1],
                score=max(1, round(result.score * _RESULT_SCORE_SCALE)),
                reasons=tuple(f"retrieval:{source}" for source in result.sources),
            )
            for result in ordered
            if result.document.field_id is not None
        )[:_MAX_FIELDS]
        document_terms = set().union(*(set(tokenize(result.document.text)) for result in ordered))
        matched_terms = tuple(term for term in query_terms if term in document_terms)
        source_names = tuple(sorted(set().union(*(set(result.sources) for result in ordered))))
        hits.append(
            SearchHit(
                id=object_id,
                label=node.label,
                type=node.type,
                score=max(1, round(best.score * _RESULT_SCORE_SCALE)),
                matched_terms=matched_terms,
                reasons=tuple(f"retrieval:{source}" for source in source_names),
                fields=fields,
            )
        )
    ordered_hits = tuple(
        sorted(hits, key=lambda hit: (-hit.score, hit.label.casefold(), hit.id))[:limit]
    )
    return SearchResults(
        graph=graph.name,
        query=query,
        terms=query_terms,
        hits=ordered_hits,
        mode=mode,
    )
