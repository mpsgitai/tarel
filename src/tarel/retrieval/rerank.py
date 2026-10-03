"""Optional relevance ordering of already scoped metadata objects."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING

from tarel.retrieval.contracts import RetrievalFailure
from tarel.retrieval.documents import build_retrieval_documents
from tarel.retrieval.local import default_model_path, resolve_model_path, sha256_file
from tarel.retrieval.remote import rerank_remote
from tarel.retrieval.settings import load_settings

if TYPE_CHECKING:
    from tarel.graph.contracts import GraphDocument
    from tarel.runtime import TarelRuntime
    from tarel.search import SearchResults

_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query "
    'and the Instruct provided. Note that the answer can only be "yes" or "no".'
    "<|im_end|>\n<|im_start|>user\n"
)
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


class LocalQwenReranker:
    def __init__(self, path: Path, *, n_threads: int | None = None) -> None:
        try:
            from llama_cpp import Llama, llama_get_logits_ith
        except ImportError as exc:
            raise RetrievalFailure(
                "missing_local_rag_dependency", "Install `tarel[local-rag]` for local reranking."
            ) from exc
        self.lock = RLock()
        self.next_logits = llama_get_logits_ith
        self.model = Llama(
            model_path=str(path),
            n_gpu_layers=0,
            n_ctx=4096,
            n_batch=256,
            n_threads=n_threads,
            logits_all=False,
            verbose=False,
        )
        labels = [self.model.tokenize(label.encode(), add_bos=False) for label in ("no", "yes")]
        if any(len(tokens) != 1 for tokens in labels):
            raise RetrievalFailure(
                "unsupported_reranker", "Qwen reranking needs single-token yes/no labels."
            )
        self.no, self.yes = (tokens[0] for tokens in labels)

    def score(self, query: str, texts: tuple[str, ...]) -> tuple[float, ...]:
        scores = []
        with self.lock:
            for text in texts:
                prefix = self.model.tokenize(
                    (
                        _PREFIX
                        + "<Instruct>: Retrieve relevant database objects.\n"
                        + f"<Query>: {query}\n<Document>: "
                    ).encode(),
                    add_bos=True,
                    special=True,
                )
                suffix = self.model.tokenize(_SUFFIX.encode(), add_bos=False, special=True)
                document = self.model.tokenize(text.encode(), add_bos=False)
                available = 4096 - len(prefix) - len(suffix)
                if available < 1:
                    raise RetrievalFailure(
                        "rerank_query_too_long", "Query exceeds the local rerank context."
                    )
                self.model.reset()
                self.model.eval(prefix + document[:available] + suffix)
                # With logits_all=False recent bindings do not fill Llama.scores.
                # Read only the final native row; retaining every row is unnecessary.
                logits = self.next_logits(self.model.ctx, -1)
                if not logits:
                    raise RetrievalFailure("reranking_failed", "Local reranker omitted logits.")
                difference = float(logits[self.yes]) - float(logits[self.no])
                if not math.isfinite(difference):
                    raise RetrievalFailure(
                        "reranking_failed", "Local reranker returned invalid logits."
                    )
                scores.append(
                    1 / (1 + math.exp(-difference))
                    if difference >= 0
                    else math.exp(difference) / (1 + math.exp(difference))
                )
        return tuple(scores)


def candidate_limit(runtime: TarelRuntime | None, limit: int) -> int:
    settings = load_settings(runtime)
    return max(limit, settings.rerank_depth) if settings.reranker is not None else limit


def rerank_results(
    results: SearchResults,
    graphs: tuple[GraphDocument, ...],
    *,
    runtime: TarelRuntime | None,
    limit: int,
    n_threads: int | None = None,
) -> SearchResults:
    settings = load_settings(runtime)
    choice = settings.reranker
    if choice is None:
        return replace(results, hits=results.hits[:limit])
    documents = {
        (graph.name, doc.object_id): f"System/graph: {graph.name}\n{doc.text[:4000]}"
        for graph in graphs
        for doc in build_retrieval_documents(graph, annotation_states=results.annotation_states)
        if doc.field_id is None
    }
    # Family hits have their own review boundary; never expand them into model inputs.
    positions = [index for index, hit in enumerate(results.hits) if hit.family is None][
        : settings.rerank_depth
    ]
    texts = []
    for index in positions:
        hit = results.hits[index]
        graph = hit.source_graph or results.graph
        prefix = f"scope::{graph}::"
        identifier = hit.id.removeprefix(prefix)
        try:
            texts.append(documents[(graph, identifier)])
        except KeyError as exc:
            raise RetrievalFailure(
                "invalid_rerank_candidate", "Search candidate is absent from the safe projection."
            ) from exc
    if not texts:
        return replace(results, hits=results.hits[:limit])
    if choice.provider == "local":
        path = resolve_model_path(
            Path(choice.model_path) if choice.model_path else default_model_path(choice.model)
        )
        digest = runtime.model_sha256(path) if runtime is not None else sha256_file(path)
        key = (str(path), digest, n_threads)
        if runtime is None:
            backend = LocalQwenReranker(path, n_threads=n_threads)
        else:
            with runtime._embedding_cache_lock:
                if key not in runtime._rerank_backends:
                    for cached in tuple(runtime._rerank_backends):
                        if cached[0] == key[0] and cached != key:
                            del runtime._rerank_backends[cached]
                    runtime._rerank_backends[key] = LocalQwenReranker(path, n_threads=n_threads)
                backend = runtime._rerank_backends[key]
        scores = backend.score(results.query, tuple(texts))
    else:
        scores = rerank_remote(choice, results.query, tuple(texts))
    if len(scores) != len(positions):
        raise RetrievalFailure("reranking_failed", "Reranker omitted a candidate.")
    ordered = sorted(zip(positions, scores, strict=True), key=lambda row: (-row[1], row[0]))
    hits = list(results.hits)
    for target, (source, score) in zip(positions, ordered, strict=True):
        hit = results.hits[source]
        hits[target] = replace(
            hit,
            score=round(score * 1_000_000),
            reasons=hit.reasons + (f"reranker:{choice.provider}:{choice.model}",),
        )
    return replace(results, hits=tuple(hits[:limit]))
