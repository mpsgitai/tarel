"""Optional experiment tests: run with sqlite-vec installed in an isolated uv environment."""

import hashlib
import importlib.util
import math
import sqlite3
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

from tarel.retrieval.bm25 import rank_bm25
from tarel.retrieval.contracts import RetrievalFailure
from tarel.retrieval.index import FileRetrievalIndex, _reciprocal_rank_fusion
from tests.test_retrieval import _FakeEmbedding, _retrieval_graph
from tools.sqlite_vec_trial import (
    load_python,
    prepare_vec0,
    rank_native,
    rank_python,
    read_index,
)


@skipUnless(importlib.util.find_spec("sqlite_vec"), "optional sqlite-vec experiment")
class SqliteVecTrialTests(TestCase):
    def test_production_index_backend_matches_python_with_filters(self):
        graph = _retrieval_graph()
        model = Path(self.temporary.name) / "model.gguf"
        model.write_bytes(b"test model")
        store = FileRetrievalIndex(Path(self.temporary.name) / "production")
        embedder = _FakeEmbedding()
        built = store.build(graph, embedder=embedder, model_path=model)
        query = embedder.embed_query("Internet Umsatz pro Jahr")
        object_id = "object:AdventureWorksDW/dbo/FactInternetSales"
        for scope in (
            {}, {"namespace": "DBO"}, {"object_ids": frozenset({object_id})},
            {"namespace": "dbo", "object_ids": frozenset({object_id})},
        ):
            with self.subTest(scope=scope):
                expected = store.rank(
                    graph, model_path=model, model_sha256=built.metadata.model_sha256,
                    query_vector=query, limit=10, backend="python", **scope,
                )
                actual = store.rank(
                    graph, model_path=model, model_sha256=built.metadata.model_sha256,
                    query_vector=query, limit=10, backend="sqlite-vec", **scope,
                )
                self.assertEqual(
                    [item.document.id for item in actual],
                    [item.document.id for item in expected],
                )

    def test_production_native_backend_rejects_incomplete_index(self):
        graph = _retrieval_graph()
        model = Path(self.temporary.name) / "model.gguf"
        model.write_bytes(b"test model")
        store = FileRetrievalIndex(Path(self.temporary.name) / "production-corrupt")
        built = store.build(graph, embedder=_FakeEmbedding(), model_path=model)
        with sqlite3.connect(built.path) as connection:
            connection.execute(
                "DELETE FROM vectors WHERE document_id=(SELECT document_id FROM vectors LIMIT 1)"
            )
        query = (1.0, 0.0)

        for backend in ("python", "sqlite-vec"):
            with self.subTest(backend=backend), self.assertRaises(RetrievalFailure) as raised:
                store.rank(
                    graph,
                    model_path=model,
                    model_sha256=built.metadata.model_sha256,
                    query_vector=query,
                    limit=10,
                    backend=backend,
                )
            self.assertEqual(raised.exception.code, "invalid_index")

    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.source = Path(self.temporary.name) / "source.sqlite"
        self.vec0 = Path(self.temporary.name) / "vec0.sqlite"
        with sqlite3.connect(self.source) as connection:
            connection.executescript(
                "CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);"
                "CREATE TABLE documents(id TEXT PRIMARY KEY,object_id TEXT,field_id TEXT,"
                "namespace TEXT,label TEXT,text TEXT);"
                "CREATE TABLE vectors(document_id TEXT PRIMARY KEY,dimensions INT,value BLOB);"
            )
            connection.executemany(
                "INSERT INTO metadata VALUES (?,?)", [("dimensions", "3"), ("document_count", "30")]
            )
            for i in range(30):
                vector = (i + 1.0, 30.0 - i, (i % 3) + 0.5)
                norm = math.sqrt(sum(value * value for value in vector))
                blob = struct.pack("<3f", *(value / norm for value in vector))
                connection.execute(
                    "INSERT INTO documents VALUES (?,?,?,?,?,?)",
                    (
                        f"doc:{i}",
                        f"object:{i // 3}",
                        None,
                        "Straße" if i < 15 else "Sales",
                        f"label {i:02}",
                        "monthly revenue" if i % 2 else "customer addresses",
                    ),
                )
                connection.execute("INSERT INTO vectors VALUES (?,?,?)", (f"doc:{i}", 3, blob))
        self.digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        prepare_vec0(self.source, self.vec0)

    def test_rank_and_hybrid_parity_with_filters(self):
        query = (0.3, 0.8, 0.1)
        norm = math.sqrt(sum(value * value for value in query))
        query = tuple(value / norm for value in query)
        cases = (
            {},
            {"namespace": "STRASSE"},
            {"object_ids": {"object:8"}},
            {"namespace": "sales", "object_ids": {"object:8", "object:9"}},
            {"namespace": "missing"},
            {"object_ids": set()},
            {"object_ids": {"object:0", "' OR 1=1 --"}},
        )
        with read_index(self.source) as connection:
            indexed = load_python(connection)
        for scope in cases:
            expected = rank_python(indexed, query, limit=10, **scope)
            documents = tuple(
                document
                for document, _ in indexed
                if "namespace" not in scope
                or document.namespace.casefold() == scope["namespace"].casefold()
            )
            documents = tuple(
                document
                for document in documents
                if "object_ids" not in scope or document.object_id in scope["object_ids"]
            )
            lexical = rank_bm25(documents, "monthly revenue", limit=10)
            for backend, path in (("scalar", self.source), ("vec0", self.vec0)):
                with self.subTest(backend=backend, scope=scope):
                    with read_index(path, native=True) as connection:
                        actual = rank_native(
                            connection, query, dimensions=3, limit=10, backend=backend, **scope
                        )
                    self.assertEqual(
                        [x.document.id for x in expected], [x.document.id for x in actual]
                    )
                    for left, right in zip(expected, actual, strict=True):
                        self.assertAlmostEqual(left.score, right.score, places=6)
                    for weight in (0.0, 0.08, 1.0):
                        self.assertEqual(
                            _reciprocal_rank_fusion(
                                lexical, expected, limit=10, bm25_weight=weight
                            ),
                            _reciprocal_rank_fusion(lexical, actual, limit=10, bm25_weight=weight),
                        )

    def test_invalid_queries_fail(self):
        for path, backend in ((self.source, "scalar"), (self.vec0, "vec0")):
            with read_index(path, native=True) as connection:
                for query in ((1.0, 0.0), (float("nan"), 0.0, 0.0), (0.0, 0.0, 0.0)):
                    with self.assertRaises(ValueError):
                        rank_native(connection, query, dimensions=3, limit=5, backend=backend)

    def test_source_is_unchanged_and_readonly(self):
        with (
            read_index(self.source, native=True) as connection,
            self.assertRaises(sqlite3.OperationalError),
        ):
            connection.execute("DELETE FROM vectors")
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.digest)
        with self.assertRaises(ValueError):
            prepare_vec0(self.source, self.source)
        with self.assertRaises(ValueError):
            prepare_vec0(self.source, self.vec0)

    def test_failed_conversion_leaves_no_index(self):
        target = self.vec0.with_name("failed.sqlite")
        with (
            patch("tools.sqlite_vec_trial.load_extension", side_effect=RuntimeError("missing")),
            self.assertRaises(RuntimeError),
        ):
            prepare_vec0(self.source, target)
        self.assertFalse(target.exists())
        self.assertEqual(set(target.parent.glob("*.sqlite")), {self.source, self.vec0})

    def test_vec0_insert_update_delete_and_rollback(self):
        from tools.sqlite_vec_trial import load_extension

        connection = sqlite3.connect(self.vec0)
        self.addCleanup(connection.close)
        load_extension(connection)
        original = connection.execute("SELECT embedding FROM knn WHERE rowid=1").fetchone()[0]
        replacement = struct.pack("<3f", 1.0, 0.0, 0.0)
        connection.execute("UPDATE knn SET embedding=? WHERE rowid=1", (replacement,))
        connection.rollback()
        self.assertEqual(
            connection.execute("SELECT embedding FROM knn WHERE rowid=1").fetchone()[0], original
        )
        connection.execute("UPDATE knn SET embedding=? WHERE rowid=1", (replacement,))
        connection.execute("DELETE FROM knn WHERE rowid=2")
        connection.execute(
            "INSERT INTO knn(rowid,embedding,namespace,object_id) VALUES(?,?,?,?)",
            (31, replacement, "sales", "new"),
        )
        connection.commit()
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM knn").fetchone()[0], 30)
        self.assertIsNone(connection.execute("SELECT rowid FROM knn WHERE rowid=2").fetchone())
        self.assertEqual(
            connection.execute("SELECT embedding FROM knn WHERE rowid=1").fetchone()[0], replacement
        )

    def test_large_scope_uses_one_json_parameter(self):
        with read_index(self.source, native=True) as connection:
            results = rank_native(
                connection,
                (1.0, 0.0, 0.0),
                dimensions=3,
                limit=5,
                object_ids={f"object:{i}" for i in range(40000)},
            )
        self.assertEqual(len(results), 5)

    def test_scalar_tie_break_matches_python(self):
        with sqlite3.connect(self.source) as connection:
            blob = struct.pack("<3f", 1.0, 0.0, 0.0)
            connection.execute("UPDATE vectors SET value=?", (blob,))
        with read_index(self.source, native=True) as connection:
            expected = rank_python(load_python(connection), (1.0, 0.0, 0.0), limit=5)
            actual = rank_native(connection, (1.0, 0.0, 0.0), dimensions=3, limit=5)
        self.assertEqual(actual, expected)

    def test_no_extension_imported_by_tarel(self):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-c", "import tarel,sys; assert 'sqlite_vec' not in sys.modules"],
            check=False,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
