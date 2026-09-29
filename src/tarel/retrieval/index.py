"""Rebuildable SQLite vector cache and transparent hybrid retrieval."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import sys
import tempfile
from array import array
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from tarel.annotations.states import DEFAULT_CONTEXT_ANNOTATION_STATES
from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import graph_revision
from tarel.retrieval.bm25 import rank_bm25, tokenize
from tarel.retrieval.contracts import (
    EmbeddingBackend,
    IndexBuildResult,
    IndexChanges,
    IndexMetadata,
    RankedDocument,
    RetrievalDocument,
    RetrievalFailure,
)
from tarel.retrieval.documents import build_retrieval_documents
from tarel.retrieval.local import sha256_file
from tarel.search import FieldSearchHit, SearchHit, SearchResults

_CONTRACT_VERSION = "tarel.retrieval.v0.3"
_PREVIOUS_CONTRACT_VERSION = "tarel.retrieval.v0.2"
_LEGACY_CONTRACT_VERSION = "tarel.retrieval.v0.1"
_GRAPH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_RRF_K = 60
_RESULT_SCORE_SCALE = 1_000_000
_MAX_SAFE_BM25_WEIGHT = sys.float_info.max / _RESULT_SCORE_SCALE
DEFAULT_BM25_WEIGHT = 1.0
_MAX_FIELDS = 8


def _annotation_policy_suffix(annotation_states: frozenset[str]) -> str:
    if annotation_states == DEFAULT_CONTEXT_ANNOTATION_STATES:
        return ""
    payload = json.dumps(sorted(annotation_states), separators=(",", ":")).encode("utf-8")
    return f"-{hashlib.sha256(payload).hexdigest()[:12]}"


class FileRetrievalIndex:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".tarel" / "indexes"

    def build(
        self,
        graph: GraphDocument,
        *,
        embedder: EmbeddingBackend | None,
        model_path: Path,
        model_id: str | None = None,
        model_sha256: str | None = None,
        batch_size: int = 16,
        resume: bool = False,
        progress: Callable[[int, int, str], None] | None = None,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> IndexBuildResult:
        if not 1 <= batch_size <= 256:
            raise RetrievalFailure("invalid_batch_size", "Batch size must be between 1 and 256.")
        documents = build_retrieval_documents(graph, annotation_states=annotation_states)
        total = len(documents)
        selected_model_id = model_id or (embedder.model_id if embedder is not None else None)
        if selected_model_id is None:
            raise RetrievalFailure(
                "missing_embedding_backend", "Index build needs a model identity.",
            )
        selected_model_sha256 = model_sha256 or sha256_file(model_path)
        reusable, previous_ids, reusable_dimensions = self._reusable_document_ids(
            graph.name,
            documents=documents,
            model_sha256=selected_model_sha256,
            annotation_states=annotation_states,
        )
        checkpoint = self.checkpoint_path(graph.name, annotation_states=annotation_states)
        resumed_documents = 0
        reused_documents = 0
        embedded_documents = 0
        dimensions = reusable_dimensions
        if resume:
            resumed_documents, checkpoint_dimensions = _prepare_index_checkpoint(
                checkpoint,
                graph=graph,
                documents=documents,
                model_id=selected_model_id,
                model_sha256=selected_model_sha256,
                annotation_states=annotation_states,
            )
            dimensions = _merge_vector_dimensions(
                dimensions, checkpoint_dimensions, code="invalid_index_checkpoint",
            )
            if progress is not None:
                progress(resumed_documents, total, "resuming")
        elif progress is not None:
            progress(0, total, "reusing" if len(reusable) == total else "embedding")
        path = self.path(graph.name, annotation_states=annotation_states)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".index-",
            suffix=".sqlite",
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        installed = False
        metadata: IndexMetadata
        try:
            with sqlite3.connect(temporary_path) as destination:
                _create_schema(destination)
                destination.executemany(
                    """
                    INSERT INTO documents(
                        id, object_id, field_id, namespace, label, text, text_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            document.id,
                            document.object_id,
                            document.field_id,
                            document.namespace,
                            document.label,
                            document.text,
                            _text_sha256(document.text),
                        )
                        for document in documents
                    ),
                )
                if resumed_documents:
                    _copy_index_checkpoint_vectors(checkpoint, destination)
                source = (
                    sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                    if reusable else None
                )
                try:
                    for start in range(resumed_documents, total, batch_size):
                        batch = documents[start : start + batch_size]
                        missing = tuple(
                            document for document in batch if document.id not in reusable
                        )
                        if missing and embedder is None:
                            raise RetrievalFailure(
                                "missing_embedding_backend",
                                "Changed retrieval documents need the selected embedding model.",
                            )
                        rows_by_id: dict[str, tuple[str, int, bytes]] = {}
                        reusable_batch = tuple(
                            document for document in batch if document.id in reusable
                        )
                        if reusable_batch:
                            if source is None:
                                raise RetrievalFailure(
                                    "invalid_index", "Reusable retrieval vectors are unavailable.",
                                )
                            rows_by_id.update(
                                _read_vector_rows(
                                    source,
                                    reusable_batch,
                                    dimensions=dimensions,
                                )
                            )
                        if missing and embedder is not None:
                            embedded = embedder.embed_documents(
                                tuple(document.text for document in missing),
                                batch_size=batch_size,
                            )
                            embedded_dimensions = _validate_vectors(
                                embedded, expected_count=len(missing),
                            )
                            dimensions = _merge_vector_dimensions(
                                dimensions, embedded_dimensions, code="embedding_failed",
                            )
                            rows_by_id.update(
                                (
                                    document.id,
                                    (
                                        document.id,
                                        embedded_dimensions,
                                        _pack_vector(vector),
                                    ),
                                )
                                for document, vector in zip(missing, embedded, strict=True)
                            )
                        rows = tuple(rows_by_id[document.id] for document in batch)
                        dimensions = _validate_vector_rows(rows, dimensions=dimensions)
                        destination.executemany(
                            "INSERT INTO vectors(document_id, dimensions, value) VALUES (?, ?, ?)",
                            rows,
                        )
                        reused_documents += len(reusable_batch)
                        embedded_documents += len(missing)
                        if resume:
                            _save_index_checkpoint_batch(
                                checkpoint, start=start, rows=rows,
                            )
                        if progress is not None and missing:
                            progress(min(start + len(batch), total), total, "embedding")
                finally:
                    if source is not None:
                        source.close()
                if dimensions is None:
                    raise RetrievalFailure(
                        "embedding_failed", "Retrieval index contains no vectors.",
                    )
                stored_count = int(
                    destination.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
                )
                if stored_count != total:
                    raise RetrievalFailure(
                        "embedding_failed", "Embedding count does not match documents.",
                    )
                metadata = IndexMetadata(
                    contract_version=_CONTRACT_VERSION,
                    graph=graph.name,
                    graph_hash=graph_revision(graph),
                    document_count=total,
                    dimensions=dimensions,
                    model_id=selected_model_id,
                    model_path=str(model_path.resolve()),
                    model_sha256=selected_model_sha256,
                    normalized=True,
                    annotation_states=tuple(sorted(annotation_states)),
                    documents_sha256=_documents_sha256(documents),
                )
                destination.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    ((key, json.dumps(value)) for key, value in metadata.to_dict().items()),
                )
                if progress is not None:
                    progress(total, total, "writing")
                destination.commit()
            os.replace(temporary_path, path)
            installed = True
            checkpoint.unlink(missing_ok=True)
            if progress is not None:
                progress(total, total, "ready")
        except RetrievalFailure:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise RetrievalFailure(
                "index_build_failed",
                "Could not persist retrieval index.",
            ) from exc
        finally:
            if not installed:
                temporary_path.unlink(missing_ok=True)
        return IndexBuildResult(
            path=path,
            metadata=metadata,
            resumed_documents=resumed_documents,
            reused_documents=reused_documents,
            embedded_documents=embedded_documents,
            removed_documents=len(previous_ids - {document.id for document in documents}),
        )

    def changes(
        self,
        graph: GraphDocument,
        *,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> IndexChanges:
        documents = build_retrieval_documents(graph, annotation_states=annotation_states)
        path = self.path(graph.name, annotation_states=annotation_states)
        if not path.is_file():
            return IndexChanges(len(documents), 0, 0, 0)
        stored = self._stored_document_hashes(path)
        current = {document.id: _text_sha256(document.text) for document in documents}
        shared = stored.keys() & current.keys()
        return IndexChanges(
            added_documents=len(current.keys() - stored.keys()),
            changed_documents=sum(stored[item] != current[item] for item in shared),
            removed_documents=len(stored.keys() - current.keys()),
            unchanged_documents=sum(stored[item] == current[item] for item in shared),
        )

    def _stored_document_hashes(self, path: Path) -> dict[str, str]:
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(documents)")
                }
                if "text_sha256" in columns:
                    rows = connection.execute("SELECT id, text_sha256 FROM documents")
                else:
                    rows = (
                        (identifier, _text_sha256(text))
                        for identifier, text in connection.execute("SELECT id, text FROM documents")
                    )
                return {str(identifier): str(digest) for identifier, digest in rows}
        except sqlite3.Error as exc:
            raise RetrievalFailure("invalid_index", "Could not read indexed documents.") from exc

    def _reusable_document_ids(
        self,
        name: str,
        *,
        documents: tuple[RetrievalDocument, ...],
        model_sha256: str,
        annotation_states: frozenset[str],
    ) -> tuple[set[str], set[str], int | None]:
        path = self.path(name, annotation_states=annotation_states)
        if not path.is_file():
            return set(), set(), None
        previous_ids: set[str] = set()
        try:
            metadata = self.metadata(name, annotation_states=annotation_states)
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                previous_ids = {
                    str(row[0]) for row in connection.execute("SELECT id FROM documents")
                }
                _validate_index_storage(connection, metadata)
                if metadata.model_sha256 != model_sha256:
                    return set(), previous_ids, None
                columns = {
                    str(row[1]) for row in connection.execute("PRAGMA table_info(documents)")
                }
                digest = "d.text_sha256" if "text_sha256" in columns else "NULL"
                rows = connection.execute(
                    f"SELECT d.id,d.text,{digest} "
                    "FROM documents d JOIN vectors v ON v.document_id=d.id"
                )
                current = {document.id: _text_sha256(document.text) for document in documents}
                reusable = set()
                for identifier, text, stored_digest in rows:
                    identifier = str(identifier)
                    actual_digest = str(stored_digest) if stored_digest else _text_sha256(str(text))
                    if current.get(identifier) == actual_digest:
                        reusable.add(identifier)
                return reusable, previous_ids, metadata.dimensions if reusable else None
        except RetrievalFailure as exc:
            if exc.code in {"invalid_index", "unsupported_index"}:
                return set(), previous_ids, None
            raise
        except sqlite3.Error:
            return set(), previous_ids, None

    def metadata(
        self, name: str, *,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> IndexMetadata:
        path = self.path(name, annotation_states=annotation_states)
        if not path.is_file():
            raise RetrievalFailure("index_not_found", f"Retrieval index not found: {name}")
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                values = {
                    str(key): json.loads(value)
                    for key, value in connection.execute("SELECT key, value FROM metadata")
                }
        except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
            raise RetrievalFailure(
                "invalid_index",
                f"Could not read retrieval index: {name}",
            ) from exc
        try:
            if values.get("contract_version") == _LEGACY_CONTRACT_VERSION:
                if annotation_states != DEFAULT_CONTEXT_ANNOTATION_STATES:
                    raise RetrievalFailure(
                        "index_policy_mismatch", "Retrieval index annotation policy differs."
                    )
                values["annotation_states"] = sorted(DEFAULT_CONTEXT_ANNOTATION_STATES)
            if values.get("contract_version") in {
                _LEGACY_CONTRACT_VERSION, _PREVIOUS_CONTRACT_VERSION,
            }:
                values["documents_sha256"] = ""
            if isinstance(values.get("annotation_states"), list):
                values["annotation_states"] = tuple(values["annotation_states"])
            metadata = IndexMetadata(**values)
        except (TypeError, ValueError) as exc:
            raise RetrievalFailure("invalid_index", "Retrieval index metadata is invalid.") from exc
        if metadata.contract_version not in {
            _CONTRACT_VERSION, _PREVIOUS_CONTRACT_VERSION, _LEGACY_CONTRACT_VERSION,
        }:
            raise RetrievalFailure("unsupported_index", "Retrieval index must be rebuilt.")
        if frozenset(metadata.annotation_states) != annotation_states:
            raise RetrievalFailure(
                "index_policy_mismatch", "Retrieval index annotation policy differs."
            )
        return metadata

    def load(
        self,
        graph: GraphDocument,
        *,
        model_path: Path,
        model_sha256: str | None = None,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> tuple[IndexMetadata, tuple[RetrievalDocument, ...], tuple[tuple[float, ...], ...]]:
        metadata = self.metadata(graph.name, annotation_states=annotation_states)
        if not _retrieval_projection_current(
            metadata, graph, annotation_states=annotation_states,
        ):
            raise RetrievalFailure(
                "stale_index",
                f"Graph {graph.name} changed after indexing. Run `tarel index build {graph.name}`.",
            )
        if metadata.model_sha256 != (model_sha256 or sha256_file(model_path)):
            raise RetrievalFailure(
                "model_index_mismatch",
                "The selected embedding model differs from the indexed model. Rebuild the index.",
            )
        path = self.path(graph.name, annotation_states=annotation_states)
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                _validate_index_storage(connection, metadata)
                rows = connection.execute(
                    """
                    SELECT d.id, d.object_id, d.field_id, d.namespace, d.label, d.text,
                           v.dimensions, v.value
                    FROM documents AS d
                    JOIN vectors AS v ON v.document_id = d.id
                    ORDER BY d.id
                    """
                ).fetchall()
        except sqlite3.Error as exc:
            raise RetrievalFailure("invalid_index", "Could not read retrieval vectors.") from exc
        documents = tuple(
            RetrievalDocument(
                id=str(row[0]),
                object_id=str(row[1]),
                field_id=str(row[2]) if row[2] is not None else None,
                namespace=str(row[3]),
                label=str(row[4]),
                text=str(row[5]),
            )
            for row in rows
        )
        vectors = tuple(_unpack_vector(row[7], int(row[6])) for row in rows)
        if len(documents) != metadata.document_count:
            raise RetrievalFailure("invalid_index", "Retrieval index document count is invalid.")
        return metadata, documents, vectors

    def rank(
        self,
        graph: GraphDocument,
        *,
        model_path: Path,
        model_sha256: str | None = None,
        query_vector: tuple[float, ...],
        limit: int,
        namespace: str | None = None,
        object_ids: frozenset[str] | None = None,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
        backend: str = "auto",
    ) -> tuple[RankedDocument, ...]:
        if backend not in {"auto", "python", "sqlite-vec"}:
            raise RetrievalFailure("invalid_vector_backend", "Unknown local vector backend.")
        use_native = backend == "sqlite-vec" or (
            backend == "auto" and sqlite_vec_available()
        )
        if not use_native:
            metadata, documents, vectors = self.load(
                graph, model_path=model_path, model_sha256=model_sha256,
                annotation_states=annotation_states,
            )
            if len(query_vector) != metadata.dimensions:
                raise RetrievalFailure("model_index_mismatch", "Query and index dimensions differ.")
            indexed = tuple(
                (document, vector)
                for document, vector in zip(documents, vectors, strict=True)
                if namespace is None or document.namespace.casefold() == namespace.casefold()
                if object_ids is None or document.object_id in object_ids
            )
            return _rank_vectors(indexed, query_vector, limit=limit)
        return self._rank_sqlite_vec(
            graph,
            model_path=model_path,
            model_sha256=model_sha256,
            query_vector=query_vector,
            limit=limit,
            namespace=namespace,
            object_ids=object_ids,
            annotation_states=annotation_states,
        )

    def _rank_sqlite_vec(
        self,
        graph: GraphDocument,
        *,
        model_path: Path,
        model_sha256: str | None,
        query_vector: tuple[float, ...],
        limit: int,
        namespace: str | None,
        object_ids: frozenset[str] | None,
        annotation_states: frozenset[str],
    ) -> tuple[RankedDocument, ...]:
        metadata = self.metadata(graph.name, annotation_states=annotation_states)
        if not _retrieval_projection_current(
            metadata, graph, annotation_states=annotation_states,
        ):
            raise RetrievalFailure(
                "stale_index",
                f"Graph {graph.name} changed after indexing. "
                f"Run `tarel index build {graph.name}`.",
            )
        if metadata.model_sha256 != (model_sha256 or sha256_file(model_path)):
            raise RetrievalFailure(
                "model_index_mismatch",
                "The selected embedding model differs from the indexed model. Rebuild the index.",
            )
        if len(query_vector) != metadata.dimensions:
            raise RetrievalFailure("model_index_mismatch", "Query and index dimensions differ.")
        path = self.path(graph.name, annotation_states=annotation_states)
        try:
            import sqlite_vec
        except ImportError as exc:
            raise RetrievalFailure(
                "missing_sqlite_vec_dependency",
                "sqlite-vec is unavailable. Install `tarel[vector]` or use the Python backend.",
            ) from exc
        parameters: dict[str, object] = {
            "query": _pack_vector(query_vector), "limit": limit,
        }
        clauses = []
        if namespace is not None:
            clauses.append("casefold(d.namespace)=:namespace")
            parameters["namespace"] = namespace.casefold()
        if object_ids is not None:
            clauses.append("d.object_id IN (SELECT value FROM json_each(:object_ids))")
            parameters["object_ids"] = json.dumps(sorted(object_ids))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                _validate_index_storage(connection, metadata)
                connection.enable_load_extension(True)
                try:
                    sqlite_vec.load(connection)
                finally:
                    connection.enable_load_extension(False)
                connection.create_function("casefold", 1, str.casefold, deterministic=True)
                rows = connection.execute(
                    "SELECT d.id,d.object_id,d.field_id,d.namespace,d.label,d.text,"
                    "1.0-vec_distance_cosine(v.value,:query) AS score "
                    "FROM documents d JOIN vectors v ON v.document_id=d.id "
                    f"{where} ORDER BY score DESC,casefold(d.label),d.id LIMIT :limit",
                    parameters,
                ).fetchall()
        except sqlite3.Error as exc:
            raise RetrievalFailure("invalid_index", "Could not search retrieval vectors.") from exc
        return tuple(
            RankedDocument(
                document=RetrievalDocument(
                    id=str(row[0]), object_id=str(row[1]),
                    field_id=str(row[2]) if row[2] is not None else None,
                    namespace=str(row[3]), label=str(row[4]), text=str(row[5]),
                ),
                score=float(row[6]), sources=("vector",),
            )
            for row in rows if math.isfinite(float(row[6]))
        )

    def path(
        self, name: str, *,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> Path:
        if not _GRAPH_NAME.fullmatch(name):
            raise RetrievalFailure("invalid_graph_name", "Invalid graph name for retrieval index.")
        suffix = _annotation_policy_suffix(annotation_states)
        return self.root / name / f"index{suffix}.sqlite"

    def checkpoint_path(
        self, name: str, *,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> Path:
        suffix = _annotation_policy_suffix(annotation_states)
        self.path(name, annotation_states=annotation_states)
        return self.root / name / f"index{suffix}.checkpoint.sqlite"

    def checkpoint_status(
        self, name: str, *,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> dict[str, object] | None:
        path = self.checkpoint_path(name, annotation_states=annotation_states)
        if not path.is_file():
            return None
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                identity = {
                    str(key): json.loads(value)
                    for key, value in connection.execute("SELECT key, value FROM metadata")
                }
                completed = int(connection.execute("SELECT COUNT(*) FROM vectors").fetchone()[0])
        except (OSError, sqlite3.Error, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RetrievalFailure(
                "invalid_index_checkpoint",
                f"Could not read retrieval index checkpoint: {name}",
            ) from exc
        required = {
            "checkpoint_version",
            "document_count",
            "documents_sha256",
            "graph",
            "graph_hash",
            "model_id",
            "model_sha256",
            "annotation_states",
        }
        document_count = identity.get("document_count")
        if (
            set(identity) != required
            or not isinstance(document_count, int)
            or not 0 <= completed <= document_count
        ):
            raise RetrievalFailure(
                "invalid_index_checkpoint",
                f"Retrieval index checkpoint metadata is invalid: {name}",
            )
        return {
            "completed_documents": completed,
            "contract_version": identity["checkpoint_version"],
            "document_count": document_count,
            "graph": identity["graph"],
            "graph_hash": identity["graph_hash"],
            "model_id": identity["model_id"],
            "model_sha256": identity["model_sha256"],
            "annotation_states": identity["annotation_states"],
            "path": str(path),
        }


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
    if mode in {"vector", "hybrid"}:
        if embedder is None or model_path is None:
            raise RetrievalFailure("missing_embedding_backend", "Vector retrieval needs a model.")
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

    if mode == "bm25":
        ranked = bm25_results
    elif mode == "vector":
        ranked = vector_results
    else:
        ranked = _reciprocal_rank_fusion(
            bm25_results, vector_results, limit=candidate_limit, bm25_weight=weight,
        )
    return _object_results(graph, query, mode=mode, ranked=ranked, limit=limit)


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


def _rank_vectors(
    indexed: tuple[tuple[RetrievalDocument, tuple[float, ...]], ...],
    query_vector: tuple[float, ...],
    *,
    limit: int,
) -> tuple[RankedDocument, ...]:
    ranked: list[RankedDocument] = []
    for document, vector in indexed:
        if len(vector) != len(query_vector):
            raise RetrievalFailure("model_index_mismatch", "Query and index dimensions differ.")
        score = sum(left * right for left, right in zip(vector, query_vector, strict=True))
        if math.isfinite(score):
            ranked.append(RankedDocument(document=document, score=score, sources=("vector",)))
    return tuple(
        sorted(
            ranked,
            key=lambda item: (-item.score, item.document.label.casefold(), item.document.id),
        )[:limit]
    )


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


def _prepare_index_checkpoint(
    path: Path,
    *,
    graph: GraphDocument,
    documents: tuple[RetrievalDocument, ...],
    model_id: str,
    model_sha256: str,
    annotation_states: frozenset[str],
) -> tuple[int, int | None]:
    identity = _checkpoint_identity(
        graph,
        documents,
        model_id=model_id,
        model_sha256=model_sha256,
        annotation_states=annotation_states,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".index-checkpoint-",
            suffix=".sqlite",
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            with sqlite3.connect(temporary_path) as connection:
                _create_checkpoint_schema(connection)
                connection.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    ((key, json.dumps(value)) for key, value in identity.items()),
                )
                connection.commit()
            os.replace(temporary_path, path)
        except (OSError, sqlite3.Error) as exc:
            temporary_path.unlink(missing_ok=True)
            raise RetrievalFailure(
                "index_checkpoint_failed",
                "Could not create retrieval index checkpoint.",
            ) from exc
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            stored_identity = {
                str(key): json.loads(value)
                for key, value in connection.execute("SELECT key, value FROM metadata")
            }
            if stored_identity != identity:
                raise RetrievalFailure(
                    "stale_index_checkpoint",
                    "The retrieval index checkpoint belongs to different graph documents or "
                    "model. Run index build without --resume to rebuild and clear it.",
                )
            completed = 0
            vector_dimensions: int | None = None
            rows = connection.execute(
                "SELECT position,document_id,dimensions,value "
                "FROM vectors ORDER BY position"
            )
            for expected_position, row in enumerate(rows):
                position, document_id, dimensions, value = row
                if (
                    position != expected_position
                    or expected_position >= len(documents)
                    or document_id != documents[expected_position].id
                ):
                    raise RetrievalFailure(
                        "invalid_index_checkpoint",
                        "Retrieval index checkpoint coverage is not a contiguous document "
                        "prefix.",
                    )
                row_dimensions = int(dimensions)
                _validated_vector_array(
                    value, row_dimensions, code="invalid_index_checkpoint",
                )
                vector_dimensions = _merge_vector_dimensions(
                    vector_dimensions,
                    row_dimensions,
                    code="invalid_index_checkpoint",
                )
                completed += 1
    except RetrievalFailure:
        raise
    except (OSError, sqlite3.Error, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RetrievalFailure(
            "invalid_index_checkpoint",
            "Could not read retrieval index checkpoint.",
        ) from exc
    return completed, vector_dimensions


def _copy_index_checkpoint_vectors(
    path: Path,
    destination: sqlite3.Connection,
) -> None:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as source:
            destination.executemany(
                "INSERT INTO vectors(document_id, dimensions, value) VALUES (?, ?, ?)",
                source.execute(
                    "SELECT document_id,dimensions,value FROM vectors ORDER BY position"
                ),
            )
    except sqlite3.Error as exc:
        raise RetrievalFailure(
            "invalid_index_checkpoint",
            "Could not copy retrieval index checkpoint vectors.",
        ) from exc


def _read_vector_rows(
    connection: sqlite3.Connection,
    documents: tuple[RetrievalDocument, ...],
    *,
    dimensions: int | None,
) -> dict[str, tuple[str, int, bytes]]:
    identifiers = [document.id for document in documents]
    try:
        rows = {
            str(identifier): (str(identifier), int(dimensions), bytes(value))
            for identifier, dimensions, value in connection.execute(
                "SELECT document_id,dimensions,value FROM vectors "
                "WHERE document_id IN (SELECT value FROM json_each(?))",
                (json.dumps(identifiers),),
            )
        }
    except (sqlite3.Error, TypeError, ValueError) as exc:
        raise RetrievalFailure("invalid_index", "Could not reuse retrieval vectors.") from exc
    if set(rows) != set(identifiers):
        raise RetrievalFailure("invalid_index", "Reusable retrieval vectors are incomplete.")
    _validate_vector_rows(
        tuple(rows.values()),
        dimensions=dimensions,
        code="invalid_index",
    )
    return rows


def _merge_vector_dimensions(
    current: int | None,
    candidate: int | None,
    *,
    code: str,
) -> int | None:
    if candidate is None:
        return current
    if current is not None and current != candidate:
        raise RetrievalFailure(code, "Embedding dimensions are inconsistent.")
    return candidate


def _validate_vector_rows(
    rows: tuple[tuple[str, int, bytes], ...],
    *,
    dimensions: int | None,
    code: str = "embedding_failed",
) -> int:
    if not rows:
        raise RetrievalFailure(code, "Embedding count does not match documents.")
    selected_dimensions = dimensions
    for _document_id, row_dimensions, value in rows:
        _validated_vector_array(value, row_dimensions, code=code)
        selected_dimensions = _merge_vector_dimensions(
            selected_dimensions,
            row_dimensions,
            code=code,
        )
    if selected_dimensions is None:
        raise RetrievalFailure(code, "Retrieval index contains no vectors.")
    return selected_dimensions


def _save_index_checkpoint_batch(
    path: Path,
    *,
    start: int,
    rows: tuple[tuple[str, int, bytes], ...],
) -> None:
    try:
        with sqlite3.connect(path) as connection:
            connection.executemany(
                "INSERT INTO vectors(position, document_id, dimensions, value) "
                "VALUES (?, ?, ?, ?)",
                (
                    (start + offset, document_id, dimensions, value)
                    for offset, (document_id, dimensions, value) in enumerate(rows)
                ),
            )
            connection.commit()
    except (OSError, sqlite3.Error) as exc:
        raise RetrievalFailure(
            "index_checkpoint_failed",
            "Could not persist retrieval index checkpoint.",
        ) from exc


def _checkpoint_identity(
    graph: GraphDocument,
    documents: tuple[RetrievalDocument, ...],
    *,
    model_id: str,
    model_sha256: str,
    annotation_states: frozenset[str],
) -> dict[str, object]:
    payload = json.dumps(
        [
            [
                document.id,
                document.object_id,
                document.field_id,
                document.namespace,
                document.label,
                document.text,
            ]
            for document in documents
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "checkpoint_version": "tarel.retrieval-checkpoint.v0.2",
        "annotation_states": sorted(annotation_states),
        "document_count": len(documents),
        "documents_sha256": hashlib.sha256(payload).hexdigest(),
        "graph": graph.name,
        "graph_hash": graph_revision(graph),
        "model_id": model_id,
        "model_sha256": model_sha256,
    }


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            object_id TEXT NOT NULL,
            field_id TEXT,
            namespace TEXT NOT NULL,
            label TEXT NOT NULL,
            text TEXT NOT NULL,
            text_sha256 TEXT NOT NULL
        );
        CREATE INDEX documents_namespace ON documents(namespace);
        CREATE INDEX documents_object_id ON documents(object_id);
        CREATE TABLE vectors (
            document_id TEXT PRIMARY KEY REFERENCES documents(id),
            dimensions INTEGER NOT NULL,
            value BLOB NOT NULL
        );
        """
    )


def _create_checkpoint_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE vectors (
            position INTEGER PRIMARY KEY,
            document_id TEXT NOT NULL UNIQUE,
            dimensions INTEGER NOT NULL,
            value BLOB NOT NULL
        );
        """
    )


def _validate_vectors(
    vectors: tuple[tuple[float, ...], ...],
    *,
    expected_count: int,
) -> int:
    if len(vectors) != expected_count or not vectors:
        raise RetrievalFailure("embedding_failed", "Embedding count does not match documents.")
    dimensions = len(vectors[0])
    if dimensions < 1 or any(len(vector) != dimensions for vector in vectors):
        raise RetrievalFailure("embedding_failed", "Embedding dimensions are inconsistent.")
    if any(not math.isfinite(value) for vector in vectors for value in vector):
        raise RetrievalFailure("embedding_failed", "Embedding contains a non-finite number.")
    return dimensions


def _pack_vector(vector: tuple[float, ...]) -> bytes:
    values = array("f", vector)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def _unpack_vector(value: bytes, dimensions: int) -> tuple[float, ...]:
    return tuple(_validated_vector_array(value, dimensions, code="invalid_index"))


def _validated_vector_array(value: bytes, dimensions: int, *, code: str) -> array:
    if dimensions < 1 or len(value) != dimensions * 4:
        raise RetrievalFailure(code, "Stored vector dimensions are invalid.")
    values = array("f")
    try:
        values.frombytes(value)
    except (TypeError, ValueError) as exc:
        raise RetrievalFailure(code, "Stored vector data is invalid.") from exc
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != dimensions:
        raise RetrievalFailure(code, "Stored vector dimensions are invalid.")
    if any(not math.isfinite(item) for item in values):
        raise RetrievalFailure(code, "Stored vector contains a non-finite number.")
    return values


def _validate_index_storage(
    connection: sqlite3.Connection,
    metadata: IndexMetadata,
) -> None:
    try:
        row = connection.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM documents),"
            "(SELECT COUNT(*) FROM vectors),"
            "(SELECT COUNT(*) FROM documents d JOIN vectors v ON v.document_id=d.id)"
        ).fetchone()
    except sqlite3.Error as exc:
        raise RetrievalFailure("invalid_index", "Could not validate retrieval vectors.") from exc
    if row != (
        metadata.document_count,
        metadata.document_count,
        metadata.document_count,
    ):
        raise RetrievalFailure("invalid_index", "Retrieval index coverage is invalid.")


def sqlite_vec_available() -> bool:
    return importlib.util.find_spec("sqlite_vec") is not None


def _text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _documents_sha256(documents: tuple[RetrievalDocument, ...]) -> str:
    payload = json.dumps(
        [[document.id, _text_sha256(document.text)] for document in documents],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _retrieval_projection_current(
    metadata: IndexMetadata,
    graph: GraphDocument,
    *,
    annotation_states: frozenset[str],
) -> bool:
    if metadata.graph_hash == graph_revision(graph):
        return True
    if not metadata.documents_sha256:
        return False
    documents = build_retrieval_documents(graph, annotation_states=annotation_states)
    return metadata.documents_sha256 == _documents_sha256(documents)
