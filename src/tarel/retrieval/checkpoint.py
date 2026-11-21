"""Resumable index builds: embeddings are checkpointed in batches and reused when unchanged."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import graph_revision
from tarel.retrieval.contracts import RetrievalDocument, RetrievalFailure
from tarel.retrieval.vectors import merge_vector_dimensions, validated_vector_array


def prepare_index_checkpoint(
    path: Path,
    *,
    graph: GraphDocument,
    documents: tuple[RetrievalDocument, ...],
    model_id: str,
    model_sha256: str,
    annotation_states: frozenset[str],
    embedding_input: str,
) -> tuple[int, int | None]:
    identity = _checkpoint_identity(
        graph,
        documents,
        model_id=model_id,
        model_sha256=model_sha256,
        annotation_states=annotation_states,
        embedding_input=embedding_input,
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
            temporary_path.replace(path)
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
                    "The retrieval index checkpoint belongs to different graph documents, model "
                    "or embedding settings. Run index build without --resume to rebuild and "
                    "clear it.",
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
                validated_vector_array(
                    value, row_dimensions, code="invalid_index_checkpoint",
                )
                vector_dimensions = merge_vector_dimensions(
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


def copy_index_checkpoint_vectors(
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


def save_index_checkpoint_batch(
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
    embedding_input: str,
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
        "checkpoint_version": "tarel.retrieval-checkpoint.v0.3",
        "annotation_states": sorted(annotation_states),
        "document_count": len(documents),
        "documents_sha256": hashlib.sha256(payload).hexdigest(),
        "embedding_input": embedding_input,
        "graph": graph.name,
        "graph_hash": graph_revision(graph),
        "model_id": model_id,
        "model_sha256": model_sha256,
    }


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
