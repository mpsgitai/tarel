"""Embedding vectors on disk: packing, validation and nearest-neighbour ranking."""

from __future__ import annotations

import json
import math
import sqlite3
import sys
from array import array

from tarel.retrieval.contracts import RankedDocument, RetrievalDocument, RetrievalFailure


def rank_vectors(
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


def read_vector_rows(
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
    validate_vector_rows(
        tuple(rows.values()),
        dimensions=dimensions,
        code="invalid_index",
    )
    return rows


def merge_vector_dimensions(
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


def validate_vector_rows(
    rows: tuple[tuple[str, int, bytes], ...],
    *,
    dimensions: int | None,
    code: str = "embedding_failed",
) -> int:
    if not rows:
        raise RetrievalFailure(code, "Embedding count does not match documents.")
    selected_dimensions = dimensions
    for _document_id, row_dimensions, value in rows:
        validated_vector_array(value, row_dimensions, code=code)
        selected_dimensions = merge_vector_dimensions(
            selected_dimensions,
            row_dimensions,
            code=code,
        )
    if selected_dimensions is None:
        raise RetrievalFailure(code, "Retrieval index contains no vectors.")
    return selected_dimensions


def validate_vectors(
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


def pack_vector(vector: tuple[float, ...]) -> bytes:
    values = array("f", vector)
    if sys.byteorder != "little":
        values.byteswap()
    return values.tobytes()


def unpack_vector(value: bytes, dimensions: int) -> tuple[float, ...]:
    return tuple(validated_vector_array(value, dimensions, code="invalid_index"))


def validated_vector_array(value: bytes, dimensions: int, *, code: str) -> array:
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
