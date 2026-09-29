"""Storage-only probes from a checksum-verified benchmark vector cache.

The old graph corpus may have changed, so do not guess document labels or attach
old vectors to current metadata. Use explicit synthetic identifiers and scopes.
This tests storage performance and ranking parity, never business relevance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import struct
from contextlib import closing
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("queries", type=Path)
    args = parser.parse_args(argv)
    if args.target.exists() or args.queries.exists():
        parser.error("Use new output paths")
    with closing(
        sqlite3.connect(args.source.resolve().as_uri() + "?mode=ro", uri=True)
    ) as original:
        metadata = dict(original.execute("SELECT * FROM metadata"))
        if metadata.get("format") != "trb.vector-index.v1":
            raise ValueError("Unsupported benchmark vector format")
        dimensions, expected = int(metadata["dimension"]), int(metadata["count"])
        if not 1 <= dimensions <= 8192 or expected < 20:
            raise ValueError("Invalid dimensions or insufficient probe documents")
        args.target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(sqlite3.connect(args.target)) as destination:
                destination.executescript(
                    "CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);"
                    "CREATE TABLE documents(id TEXT PRIMARY KEY,object_id TEXT,field_id TEXT,"
                    "namespace TEXT,label TEXT,text TEXT);"
                    "CREATE TABLE vectors(document_id TEXT PRIMARY KEY,dimensions INT,value BLOB);"
                )
                copied_metadata = {
                    "contract_version": "sqlite-vec-storage-probes-synthetic-scopes",
                    "dimensions": dimensions,
                    "document_count": expected,
                    "source_key": metadata["key"],
                }
                destination.executemany(
                    "INSERT INTO metadata VALUES (?,?)",
                    ((key, json.dumps(value)) for key, value in copied_metadata.items()),
                )
                digest = hashlib.sha256()
                count = 0
                for position, blob in original.execute("SELECT * FROM vectors ORDER BY position"):
                    if position != count or len(blob) != dimensions * 4:
                        raise ValueError("Corrupt vector positions/dimensions")
                    identifier = f"probe:{position:06}"
                    destination.execute(
                        "INSERT INTO documents VALUES (?,?,?,?,?,?)",
                        (
                            identifier,
                            f"object:{position // 10}",
                            None,
                            f"scope:{position // 1000}",
                            identifier,
                            "Storage probe, synthetic metadata",
                        ),
                    )
                    destination.execute(
                        "INSERT INTO vectors VALUES (?,?,?)", (identifier, dimensions, blob)
                    )
                    digest.update(blob)
                    count += 1
                if count != expected or digest.hexdigest() != metadata["vectors_hash"]:
                    raise ValueError("Corrupt vector count/checksum")
                destination.commit()
        except Exception:
            args.target.unlink(missing_ok=True)
            raise
        fixtures = []
        for number, position in enumerate((0, expected // 3, 2 * expected // 3)):
            vectors = []
            for offset in (0, 17):
                blob = original.execute(
                    "SELECT vector FROM vectors WHERE position=?", ((position + offset) % expected,)
                ).fetchone()[0]
                vectors.append(struct.unpack(f"<{dimensions}f", blob))
            mixed = tuple(0.65 * a + 0.35 * b for a, b in zip(*vectors, strict=True))
            norm = math.sqrt(sum(value * value for value in mixed))
            vector = [value / norm for value in mixed]
            scopes = {
                "global": {},
                "namespace": {"namespace": f"scope:{position // 1000}"},
                "object": {"object_ids": [f"object:{position // 10}"]},
            }
            for name, scope in scopes.items():
                fixtures.append(
                    {"id": f"probe-{number}-{name}", "vector": vector, "limit": 50, **scope}
                )
        fixtures.append(
            {"id": "empty-scope", "vector": fixtures[0]["vector"], "object_ids": [], "limit": 50}
        )
        args.queries.write_text(json.dumps(fixtures) + "\n")
    print(
        json.dumps(
            {
                "documents": expected,
                "dimensions": dimensions,
                "fixtures": len(fixtures),
                "bytes": args.target.stat().st_size,
                "scope_metadata": "synthetic",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
