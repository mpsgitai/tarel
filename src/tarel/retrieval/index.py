"""The local SQLite retrieval index: one per graph and embedding model."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tarel.annotations.states import DEFAULT_CONTEXT_ANNOTATION_STATES
from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import graph_revision
from tarel.retrieval.checkpoint import (
    copy_index_checkpoint_vectors,
    prepare_index_checkpoint,
    save_index_checkpoint_batch,
)
from tarel.retrieval.contracts import (
    EmbeddingBackend,
    EmbeddingInputStatus,
    IndexBuildResult,
    IndexChanges,
    IndexMetadata,
    RankedDocument,
    RetrievalDocument,
    RetrievalFailure,
)
from tarel.retrieval.documents import build_retrieval_documents
from tarel.retrieval.local import sha256_file
from tarel.retrieval.remote import HTTP_EMBEDDING_INPUT
from tarel.retrieval.vectors import (
    merge_vector_dimensions,
    pack_vector,
    rank_vectors,
    read_vector_rows,
    unpack_vector,
    validate_vector_rows,
    validate_vectors,
)

_CONTRACT_VERSION = "tarel.retrieval.v0.4"


_UNRECORDED_INPUT_CONTRACT_VERSION = "tarel.retrieval.v0.3"


_PREVIOUS_CONTRACT_VERSION = "tarel.retrieval.v0.2"


_LEGACY_CONTRACT_VERSION = "tarel.retrieval.v0.1"


# Every released index builder gave llama.cpp n_batch=256, which cut each text there. Texts within
# this limit were embedded whole, whatever else about those builds is no longer known.
_UNRECORDED_INPUT_WHOLE_TOKENS = 256


_SUPPORTED_CONTRACT_VERSIONS = frozenset({
    _CONTRACT_VERSION,
    _UNRECORDED_INPUT_CONTRACT_VERSION,
    _PREVIOUS_CONTRACT_VERSION,
    _LEGACY_CONTRACT_VERSION,
})


_GRAPH_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _model_identity(path: Path | None, identity: str | None) -> str:
    if identity is not None:
        return identity
    if path is None:
        raise RetrievalFailure("missing_embedding_backend", "An embedding identity is required.")
    return sha256_file(path)


def _annotation_policy_suffix(annotation_states: frozenset[str]) -> str:
    if annotation_states == DEFAULT_CONTEXT_ANNOTATION_STATES:
        return ""
    payload = json.dumps(sorted(annotation_states), separators=(",", ":")).encode("utf-8")
    return f"-{hashlib.sha256(payload).hexdigest()[:12]}"


@dataclass(frozen=True, slots=True)
class _Reuse:
    """What a new build may keep from the index it replaces."""

    document_ids: set[str] = field(default_factory=set)
    previous_ids: set[str] = field(default_factory=set)
    dimensions: int | None = None
    unverified_documents: int = 0
    stored_input: str = ""
    truncated_documents: frozenset[str] = frozenset()
    stored_runtime: str = ""


def vector_reuse_rule(stored_input: str, current_input: str | None, *, countable: bool) -> str:
    """Decide which stored vectors a build keeps when the text itself is unchanged.

    Returns ``all``, ``whole_only`` (texts that provably fitted the old limit) or ``none``.
    """
    if current_input is None or stored_input == current_input:
        return "all"
    if stored_input:
        return "none"
    # Remote embedding did not change with this fix and cannot be counted locally.
    return "whole_only" if countable else "all"


def embedding_input_status(metadata: IndexMetadata) -> EmbeddingInputStatus:
    """Report what the index can show about its vectors, without implying more."""
    state, detail = _embedding_input_state(metadata)
    truncated = metadata.truncated_documents
    if truncated:
        detail += (
            f" {len(truncated)} documents exceeded the token limit, so their vectors cover only "
            f"their beginning, starting with {truncated[0]}."
        )
    return {
        "state": state,
        "strategy": metadata.embedding_input or None,
        "unverified_documents": (
            metadata.unverified_documents if metadata.embedding_input else metadata.document_count
        ),
        "truncated_documents": list(truncated),
        "runtime": metadata.embedding_runtime or None,
        "detail": detail,
    }


def _embedding_input_state(metadata: IndexMetadata) -> tuple[str, str]:
    if not metadata.embedding_input:
        return "unverified", (
            "This index format did not record its embedding settings. Documents over "
            f"{_UNRECORDED_INPUT_WHOLE_TOKENS} tokens may have been embedded only in part."
        )
    if metadata.embedding_input == HTTP_EMBEDDING_INPUT:
        return "provider_defined", "The embedding provider decides how long texts are handled."
    if metadata.unverified_documents:
        return "partially_verified", (
            f"{metadata.unverified_documents} vectors come from an index without recorded "
            f"settings. They were kept because their documents fit within "
            f"{_UNRECORDED_INPUT_WHOLE_TOKENS} tokens, not because they were re-embedded."
        )
    if metadata.truncated_documents:
        return "verified_with_truncation", "All other vectors cover their whole document."
    return "verified", "Every vector was embedded from its whole document."


def embedding_input_warning(metadata: IndexMetadata) -> str | None:
    """A search warning, only when vectors may not represent their whole document."""
    if metadata.truncated_documents:
        return (
            f"Retrieval index for graph {metadata.graph} shortened "
            f"{len(metadata.truncated_documents)} documents over the embedding limit, starting "
            f"with {metadata.truncated_documents[0]}. Their fields keep their own vectors."
        )
    if metadata.embedding_input:
        return None
    return (
        f"Retrieval index for graph {metadata.graph} has no recorded embedding settings; "
        f"documents over {_UNRECORDED_INPUT_WHOLE_TOKENS} tokens may have been embedded only in "
        "part. Run "
        f"`tarel index build {metadata.graph}` to re-embed only those."
    )


class FileRetrievalIndex:
    def __init__(self, root: Path | None = None, *, namespace: str | None = None) -> None:
        self.root = root or Path.cwd() / ".tarel" / "indexes"
        if namespace is not None and not re.fullmatch(r"[a-f0-9]{24}", namespace):
            raise RetrievalFailure("invalid_index_namespace", "Invalid model index namespace.")
        self.namespace = namespace

    def build(
        self,
        graph: GraphDocument,
        *,
        embedder: EmbeddingBackend | None,
        model_path: Path | None,
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
        selected_model_sha256 = _model_identity(model_path, model_sha256)
        reuse = self._reusable_documents(
            graph.name,
            documents=documents,
            model_sha256=selected_model_sha256,
            annotation_states=annotation_states,
            embedder=embedder,
        )
        reusable, previous_ids = reuse.document_ids, reuse.previous_ids
        reusable_dimensions = reuse.dimensions
        selected_input = embedder.input_strategy if embedder is not None else reuse.stored_input
        overlong = (
            _overlong_documents(documents, reusable, embedder) if embedder is not None
            else frozenset()
        )
        checkpoint = self.checkpoint_path(graph.name, annotation_states=annotation_states)
        resumed_documents = 0
        reused_documents = 0
        embedded_documents = 0
        dimensions = reusable_dimensions
        if resume:
            resumed_documents, checkpoint_dimensions = prepare_index_checkpoint(
                checkpoint,
                graph=graph,
                documents=documents,
                model_id=selected_model_id,
                model_sha256=selected_model_sha256,
                annotation_states=annotation_states,
                embedding_input=selected_input,
            )
            dimensions = merge_vector_dimensions(
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
                    copy_index_checkpoint_vectors(checkpoint, destination)
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
                                read_vector_rows(
                                    source,
                                    reusable_batch,
                                    dimensions=dimensions,
                                )
                            )
                        if missing and embedder is not None:
                            embedded = _embed_missing(
                                embedder, missing, overlong, batch_size=batch_size,
                            )
                            embedded_dimensions = validate_vectors(
                                embedded, expected_count=len(missing),
                            )
                            dimensions = merge_vector_dimensions(
                                dimensions, embedded_dimensions, code="embedding_failed",
                            )
                            rows_by_id.update(
                                (
                                    document.id,
                                    (
                                        document.id,
                                        embedded_dimensions,
                                        pack_vector(vector),
                                    ),
                                )
                                for document, vector in zip(missing, embedded, strict=True)
                            )
                        rows = tuple(rows_by_id[document.id] for document in batch)
                        dimensions = validate_vector_rows(rows, dimensions=dimensions)
                        destination.executemany(
                            "INSERT INTO vectors(document_id, dimensions, value) VALUES (?, ?, ?)",
                            rows,
                        )
                        reused_documents += len(reusable_batch)
                        embedded_documents += len(missing)
                        if resume:
                            save_index_checkpoint_batch(
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
                    model_path=str(model_path.resolve()) if model_path is not None else "",
                    model_sha256=selected_model_sha256,
                    normalized=True,
                    annotation_states=tuple(sorted(annotation_states)),
                    documents_sha256=_documents_sha256(documents),
                    embedding_input=selected_input,
                    unverified_documents=reuse.unverified_documents,
                    truncated_documents=tuple(sorted(
                        overlong | (reuse.truncated_documents & reusable)
                    )),
                    embedding_runtime=(
                        embedder.runtime_version if embedder is not None and embedded_documents
                        else reuse.stored_runtime
                    ),
                )
                destination.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    ((key, json.dumps(value)) for key, value in metadata.to_dict().items()),
                )
                if progress is not None:
                    progress(total, total, "writing")
                destination.commit()
            temporary_path.replace(path)
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
        # Report a file that is not a usable index as that, not as a problem with its documents.
        self.metadata(graph.name, annotation_states=annotation_states)
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

    def _reusable_documents(
        self,
        name: str,
        *,
        documents: tuple[RetrievalDocument, ...],
        model_sha256: str,
        annotation_states: frozenset[str],
        embedder: EmbeddingBackend | None,
    ) -> _Reuse:
        path = self.path(name, annotation_states=annotation_states)
        if not path.is_file():
            return _Reuse()
        previous_ids: set[str] = set()
        try:
            metadata = self.metadata(name, annotation_states=annotation_states)
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                previous_ids = {
                    str(row[0]) for row in connection.execute("SELECT id FROM documents")
                }
                _validate_index_storage(connection, metadata)
                if metadata.model_sha256 != model_sha256:
                    return _Reuse(previous_ids=previous_ids)
                rule = vector_reuse_rule(
                    metadata.embedding_input,
                    embedder.input_strategy if embedder is not None else None,
                    countable=embedder is not None and embedder.max_input_tokens is not None,
                )
                if rule == "none":
                    return _Reuse(previous_ids=previous_ids)
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
                if rule == "whole_only":
                    assert embedder is not None
                    reusable = {
                        document.id for document in documents
                        if document.id in reusable
                        and (embedder.token_count(document.text) or 0)
                        <= _UNRECORDED_INPUT_WHOLE_TOKENS
                    }
                return _Reuse(
                    reusable,
                    previous_ids,
                    metadata.dimensions if reusable else None,
                    (
                        len(reusable) if rule == "whole_only"
                        else min(metadata.unverified_documents, len(reusable))
                    ),
                    metadata.embedding_input,
                    frozenset(metadata.truncated_documents),
                    metadata.embedding_runtime,
                )
        except RetrievalFailure as exc:
            if exc.code in {"invalid_index", "unsupported_index"}:
                return _Reuse(previous_ids=previous_ids)
            raise
        except sqlite3.Error:
            return _Reuse(previous_ids=previous_ids)

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
                f"Could not read retrieval index: {name}. It is not a TAREL index, or it is "
                "damaged.",
            ) from exc
        contract_version = values.get("contract_version")
        if contract_version not in _SUPPORTED_CONTRACT_VERSIONS:
            raise RetrievalFailure(
                "unsupported_index",
                f"Retrieval index for graph {name} has unsupported format {contract_version!r}. "
                "TAREL does not convert other formats; `tarel index build` needs this file "
                "removed first.",
            )
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
            if isinstance(values.get("truncated_documents"), list):
                values["truncated_documents"] = tuple(values["truncated_documents"])
            metadata = IndexMetadata(**values)
        except (TypeError, ValueError) as exc:
            raise RetrievalFailure(
                "invalid_index", f"Retrieval index metadata is invalid for graph {name}.",
            ) from exc
        if frozenset(metadata.annotation_states) != annotation_states:
            raise RetrievalFailure(
                "index_policy_mismatch", "Retrieval index annotation policy differs."
            )
        return metadata

    def storage_complete(
        self,
        name: str,
        *,
        metadata: IndexMetadata,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> bool:
        path = self.path(name, annotation_states=annotation_states)
        try:
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                _validate_index_storage(connection, metadata)
        except (sqlite3.Error, RetrievalFailure):
            return False
        return True

    def validate_selection(
        self,
        graph: GraphDocument,
        *,
        model_path: Path | None,
        model_sha256: str | None = None,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> IndexMetadata:
        metadata = self.metadata(graph.name, annotation_states=annotation_states)
        if not _retrieval_projection_current(
            metadata, graph, annotation_states=annotation_states,
        ):
            raise RetrievalFailure(
                "stale_index",
                f"Graph {graph.name} changed after indexing. Run `tarel index build {graph.name}`.",
            )
        if metadata.model_sha256 != _model_identity(model_path, model_sha256):
            raise RetrievalFailure(
                "model_index_mismatch",
                "The selected embedding model differs from the one indexed for graph "
                f"{graph.name}. Rebuild that index.",
            )
        return metadata

    def load(
        self,
        graph: GraphDocument,
        *,
        model_path: Path | None,
        model_sha256: str | None = None,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> tuple[IndexMetadata, tuple[RetrievalDocument, ...], tuple[tuple[float, ...], ...]]:
        metadata = self.validate_selection(
            graph, model_path=model_path, model_sha256=model_sha256,
            annotation_states=annotation_states,
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
        vectors = tuple(unpack_vector(row[7], int(row[6])) for row in rows)
        if len(documents) != metadata.document_count:
            raise RetrievalFailure("invalid_index", "Retrieval index document count is invalid.")
        return metadata, documents, vectors

    def rank(
        self,
        graph: GraphDocument,
        *,
        model_path: Path | None,
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
            return rank_vectors(indexed, query_vector, limit=limit)
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
        model_path: Path | None,
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
        if metadata.model_sha256 != _model_identity(model_path, model_sha256):
            raise RetrievalFailure(
                "model_index_mismatch",
                "The selected embedding model differs from the one indexed for graph "
                f"{graph.name}. Rebuild that index.",
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
            "query": pack_vector(query_vector), "limit": limit,
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
        directory = self.root / name
        if self.namespace is not None:
            directory = directory / "models" / self.namespace
        return directory / f"index{suffix}.sqlite"

    def checkpoint_path(
        self, name: str, *,
        annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    ) -> Path:
        return self.path(name, annotation_states=annotation_states).with_suffix(
            ".checkpoint.sqlite",
        )

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
            set(identity) - {"embedding_input"} != required
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
            "embedding_input": identity.get("embedding_input"),
            "path": str(path),
        }


def _overlong_documents(
    documents: tuple[RetrievalDocument, ...],
    reusable: set[str],
    embedder: EmbeddingBackend,
) -> frozenset[str]:
    """The documents this build must shorten, known before any embedding work starts."""
    limit = embedder.max_input_tokens
    if limit is None:
        return frozenset()
    return frozenset(
        document.id
        for document in documents if document.id not in reusable
        if (tokens := embedder.token_count(document.text)) is not None and tokens > limit
    )


def _embed_missing(
    embedder: EmbeddingBackend,
    missing: tuple[RetrievalDocument, ...],
    overlong: frozenset[str],
    *,
    batch_size: int,
) -> tuple[tuple[float, ...], ...]:
    whole = tuple(document for document in missing if document.id not in overlong)
    embedded = (
        embedder.embed_documents(tuple(item.text for item in whole), batch_size=batch_size)
        if whole else ()
    )
    if len(whole) == len(missing):
        return embedded
    if len(embedded) != len(whole):
        raise RetrievalFailure("embedding_failed", "Embedding count does not match documents.")
    remaining = iter(embedded)
    return tuple(
        embedder.embed_cut_document(document.text) if document.id in overlong else next(remaining)
        for document in missing
    )


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
