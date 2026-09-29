# /// script
# requires-python = ">=3.11"
# dependencies = ["sqlite-vec==0.1.9"]
# ///
"""Compare scalar sqlite-vec and Python directly on a read-only benchmark cache.

Benchmark caches identify documents only by position. Results therefore deliberately
contain positions, never unverified labels from a graph that has since changed.
Use query fixtures made with the exact recorded embedding model/runtime identity.
"""

import argparse
import hashlib
import json
import math
import sqlite3
import statistics
import struct
import time
from pathlib import Path

from sqlite_vec_trial import load_extension, read_index


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("queries", type=Path)
    parser.add_argument("--backend", choices=("python", "scalar"), default="scalar")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    fixtures = json.loads(args.queries.read_text())
    before = args.index.stat()
    with read_index(args.index) as connection:
        metadata = dict(connection.execute("SELECT name,value FROM metadata"))
        if metadata.get("format") != "trb.vector-index.v1":
            raise ValueError("Unsupported benchmark index")
        if metadata["model_id"] != fixtures["model_id"] or metadata["key"] != fixtures["index_key"]:
            raise ValueError("Query model/runtime or index identity mismatch")
        dimensions = int(metadata["dimension"])
        if not 1 <= dimensions <= 8192:
            raise ValueError("Unsupported dimensions")
        digest = hashlib.sha256()
        count = 0
        for position, blob in connection.execute(
            "SELECT position,vector FROM vectors ORDER BY position"
        ):
            if position != count or len(blob) != dimensions * 4:
                raise ValueError("Corrupt index positions or dimensions")
            digest.update(blob)
            count += 1
        if count != int(metadata["count"]) or digest.hexdigest() != metadata["vectors_hash"]:
            raise ValueError("Vector count or checksum mismatch")
        started = time.perf_counter()
        if args.backend == "python":
            rows = connection.execute(
                "SELECT position,vector FROM vectors ORDER BY position"
            ).fetchall()
            vectors = tuple(struct.unpack(f"<{dimensions}f", blob) for _, blob in rows)
            del rows
        else:
            load_extension(connection)
        preparation_seconds = time.perf_counter() - started
        measurements = []
        for fixture in fixtures["fixtures"]:
            query = tuple(fixture["vector"])
            if len(query) != dimensions or not all(math.isfinite(value) for value in query):
                raise ValueError("Invalid query vector")
            norm = math.sqrt(sum(value * value for value in query))
            if norm <= 0:
                raise ValueError("Zero query vector")
            query = tuple(value / norm for value in query)
            blob = struct.pack(f"<{dimensions}f", *query)
            elapsed = []
            for _ in range(3):
                started = time.perf_counter()
                if args.backend == "python":
                    hits = [
                        (position, sum(a * b for a, b in zip(vector, query, strict=True)))
                        for position, vector in enumerate(vectors)
                    ]
                    hits.sort(key=lambda row: (-row[1], row[0]))
                    hits = hits[:50]
                else:
                    hits = connection.execute(
                        "SELECT position,1.0-vec_distance_cosine(vector,?) AS score FROM vectors "
                        "ORDER BY score DESC,position LIMIT 50",
                        (blob,),
                    ).fetchall()
                elapsed.append((time.perf_counter() - started) * 1000)
            measurements.append(
                {
                    "id": fixture["id"],
                    "text": fixture["text"],
                    "median_ms": statistics.median(elapsed),
                    "samples_ms": elapsed,
                    "positions": [position for position, _ in hits],
                    "scores": [score for _, score in hits],
                }
            )
    after = args.index.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Index changed during experiment")
    result = {
        "backend": args.backend,
        "documents": count,
        "dimensions": dimensions,
        "index_key": metadata["key"],
        "model_identity_verified": True,
        "vector_checksum_verified": True,
        "document_mapping_verified": False,
        "source_open_mode": "ro",
        "preparation_seconds": preparation_seconds,
        "sqlite": sqlite3.sqlite_version,
        "queries": measurements,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "backend": args.backend,
                "queries": len(measurements),
                "median_ms": statistics.median(m["median_ms"] for m in measurements),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
