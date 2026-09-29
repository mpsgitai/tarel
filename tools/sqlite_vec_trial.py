# /// script
# requires-python = ">=3.11"
# dependencies = ["sqlite-vec==0.1.9"]
# ///
"""Local storage experiment; not a production search API or freshness check.

Read a frozen TAREL index, compare the existing Python ranking with native SQLite
cosine search, and optionally prepare a separate vec0 copy. Never embed documents
or mutate the source. Query vectors are supplied explicitly in a JSON fixture.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import resource
import sqlite3
import statistics
import struct
import sys
import tempfile
import time
from contextlib import closing, contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tarel.retrieval.contracts import RankedDocument, RetrievalDocument  # noqa: E402
from tarel.retrieval.index import _rank_vectors, _unpack_vector  # noqa: E402


def load_extension(connection: sqlite3.Connection) -> None:
    try:
        import sqlite_vec
    except ImportError as exc:
        raise RuntimeError(
            "Run this experiment with uv run --script tools/sqlite_vec_trial.py"
        ) from exc
    connection.enable_load_extension(True)
    try:
        sqlite_vec.load(connection)
    finally:
        connection.enable_load_extension(False)


@contextmanager
def read_index(path: Path, *, native: bool = False):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if native:
            load_extension(connection)
        connection.create_function("casefold", 1, str.casefold, deterministic=True)
        connection.execute("PRAGMA query_only=ON")
        yield connection
    finally:
        connection.close()


def metadata(connection: sqlite3.Connection) -> dict:
    return {key: json.loads(value) for key, value in connection.execute("SELECT * FROM metadata")}


def load_python(connection: sqlite3.Connection) -> tuple:
    # Match TAREL's fetchall/unpack behavior, including its transient BLOB memory.
    rows = connection.execute(
        "SELECT d.id,d.object_id,d.field_id,d.namespace,d.label,d.text,v.dimensions,v.value "
        "FROM documents d JOIN vectors v ON v.document_id=d.id ORDER BY d.id"
    ).fetchall()
    return tuple((RetrievalDocument(*row[:6]), _unpack_vector(row[7], row[6])) for row in rows)


def rank_python(indexed: tuple, query: tuple, *, limit: int, namespace=None, object_ids=None):
    selected = tuple(
        (document, vector)
        for document, vector in indexed
        if namespace is None or document.namespace.casefold() == namespace.casefold()
        if object_ids is None or document.object_id in object_ids
    )
    return _rank_vectors(selected, query, limit=limit)


def rank_native(
    connection: sqlite3.Connection,
    query: tuple,
    *,
    dimensions: int,
    limit: int,
    backend: str = "scalar",
    namespace=None,
    object_ids=None,
) -> tuple[RankedDocument, ...]:
    if len(query) != dimensions or not all(math.isfinite(value) for value in query):
        raise ValueError("Invalid query dimensions or nonfinite vector")
    if not any(query):
        raise ValueError("Query vector must be nonzero")
    if backend not in {"scalar", "vec0"} or limit < 1:
        raise ValueError("Invalid backend or limit")
    if object_ids is not None and not object_ids:
        return ()
    parameters = {"q": struct.pack(f"<{dimensions}f", *query), "k": limit}
    clauses = []
    prefix = "d" if backend == "scalar" else "v"
    if namespace is not None:
        column = "casefold(d.namespace)" if backend == "scalar" else "v.namespace"
        clauses.append(f"{column}=:namespace")
        parameters["namespace"] = namespace.casefold()
    if object_ids is not None:
        clauses.append(f"{prefix}.object_id IN (SELECT value FROM json_each(:object_ids))")
        parameters["object_ids"] = json.dumps(sorted(object_ids))
    columns = "d.id,d.object_id,d.field_id,d.namespace,d.label,d.text"
    if backend == "scalar":
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = (
            f"SELECT {columns},1.0-vec_distance_cosine(v.value,:q) AS score "
            "FROM documents d JOIN vectors v ON v.document_id=d.id"
            + where
            + " ORDER BY score DESC,casefold(d.label),d.id LIMIT :k"
        )
    else:
        # This experimental path does not repair ties truncated at vec0's k boundary.
        # The parity report must expose any changed selection, even for equal vectors.
        clauses.extend(["v.embedding MATCH :q", "k=:k"])
        sql = (
            "WITH nearest AS (SELECT rowid,distance FROM knn v WHERE "
            + " AND ".join(clauses)
            + ") "
            f"SELECT {columns},1.0-n.distance AS score "
            "FROM nearest n JOIN documents d ON d.rowid=n.rowid "
            "ORDER BY score DESC,casefold(d.label),d.id"
        )
    return tuple(
        RankedDocument(RetrievalDocument(*row[:6]), row[6], ("vector",))
        for row in connection.execute(sql, parameters)
    )


def prepare_vec0(source: Path, target: Path) -> dict:
    if source.resolve() == target.resolve() or target.exists():
        raise ValueError("vec0 destination must be a new, separate file")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=target.parent, suffix=".sqlite")
    os.close(descriptor)
    temporary = Path(temporary_name)
    started = time.perf_counter()
    try:
        with read_index(source) as original, closing(sqlite3.connect(temporary)) as destination:
            load_extension(destination)
            meta = metadata(original)
            dimensions = int(meta["dimensions"])
            if not 1 <= dimensions <= 8192:
                raise ValueError("Unsupported vector dimensions")
            destination.executescript(
                "CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);"
                "CREATE TABLE documents(id TEXT PRIMARY KEY,object_id TEXT,field_id TEXT,"
                "namespace TEXT,label TEXT,text TEXT);"
            )
            destination.execute(
                f"CREATE VIRTUAL TABLE knn USING vec0(embedding float[{dimensions}] "
                "distance_metric=cosine,namespace text,object_id text)"
            )
            destination.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                ((key, json.dumps(value)) for key, value in meta.items()),
            )
            rows = original.execute(
                "SELECT d.id,d.object_id,d.field_id,d.namespace,d.label,d.text,v.value "
                "FROM documents d JOIN vectors v ON v.document_id=d.id ORDER BY d.id"
            )
            count = 0
            for count, row in enumerate(rows, 1):
                destination.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)", row[:6])
                destination.execute(
                    "INSERT INTO knn(rowid,embedding,namespace,object_id) VALUES (?,?,?,?)",
                    (count, row[6], row[3].casefold(), row[1]),
                )
            if count != meta["document_count"]:
                raise ValueError("Source document count mismatch")
            destination.commit()
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "documents": count,
        "seconds": time.perf_counter() - started,
        "bytes": target.stat().st_size,
    }


def benchmark(path: Path, fixtures: list[dict], *, backend: str, repeats: int) -> dict:
    if repeats < 1 or not fixtures:
        raise ValueError("Need query fixtures and at least one repeat")
    started = time.perf_counter()
    with read_index(path, native=backend != "python") as connection:
        meta = metadata(connection)
        indexed = load_python(connection) if backend == "python" else None
        open_seconds = time.perf_counter() - started
        output = []
        for fixture in fixtures:
            query = tuple(fixture["vector"])
            kwargs = {
                "limit": fixture.get("limit", 50),
                "namespace": fixture.get("namespace"),
                "object_ids": fixture.get("object_ids"),
            }
            elapsed = []
            for _ in range(repeats):
                start_query = time.perf_counter()
                if backend == "python":
                    results = rank_python(indexed, query, **kwargs)
                else:
                    results = rank_native(
                        connection, query, dimensions=meta["dimensions"], backend=backend, **kwargs
                    )
                elapsed.append(time.perf_counter() - start_query)
            output.append(
                {
                    "id": fixture["id"],
                    "first_ms": elapsed[0] * 1000,
                    "median_ms": statistics.median(elapsed) * 1000,
                    "samples_ms": [seconds * 1000 for seconds in elapsed],
                    "hits": [{"id": item.document.id, "score": item.score} for item in results],
                }
            )
    return {
        "backend": backend,
        "dimensions": meta["dimensions"],
        "documents": meta["document_count"],
        "open_seconds": open_seconds,
        "peak_rss_mib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "sqlite_vec": "0.1.9" if backend != "python" else None,
        "queries": output,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--prepare-vec0", type=Path)
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--backend", choices=("python", "scalar", "vec0"), default="scalar")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.prepare_vec0:
        result = prepare_vec0(args.index, args.prepare_vec0)
    elif args.queries:
        result = benchmark(
            args.index,
            json.loads(args.queries.read_text()),
            backend=args.backend,
            repeats=args.repeats,
        )
    else:
        parser.error("Specify --queries or --prepare-vec0")
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload)
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
