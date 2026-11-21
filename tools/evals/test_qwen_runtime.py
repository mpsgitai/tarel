"""Real llama.cpp checks of the pinned Qwen GGUF; mocks cannot prove what the runtime keeps.

Skipped with a stated reason when the optional runtime or the local model file is missing. Set
TAREL_EMBEDDING_MODEL to use a copy outside the default cache; nothing is ever downloaded.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import ClassVar
from unittest import SkipTest, TestCase

from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.retrieval.contracts import RetrievalFailure
from tarel.retrieval.documents import build_retrieval_documents
from tarel.retrieval.local import (
    DEFAULT_MODEL_NAME,
    EMBEDDING_TOKEN_CAPACITY,
    LlamaCppEmbedding,
    default_model_path,
    model_spec,
    qwen_embedding_query,
    sha256_file,
)
from tarel.sdk import Tarel

_UNIT = "order"
_LEGACY_TOKEN_LIMIT = 256


def real_model_or_skip() -> Path:
    if importlib.util.find_spec("llama_cpp") is None:
        raise SkipTest("llama-cpp-python is not installed; install tarel[local-rag].")
    configured = os.getenv("TAREL_EMBEDDING_MODEL")
    path = Path(configured) if configured else default_model_path()
    if not path.is_file():
        raise SkipTest(f"Pinned Qwen GGUF not found at {path}; run `tarel model download`.")
    if sha256_file(path) != model_spec(DEFAULT_MODEL_NAME).sha256:
        raise SkipTest(f"{path} is not the pinned Qwen GGUF; its SHA-256 differs.")
    return path


class QwenRuntimeTests(TestCase):
    embedder: ClassVar[LlamaCppEmbedding]
    model_path: ClassVar[Path]

    @classmethod
    def setUpClass(cls) -> None:
        cls.model_path = real_model_or_skip()
        cls.embedder = LlamaCppEmbedding(cls.model_path, n_threads=4)

    def _text(self, tokens: int, suffix: str = "") -> str:
        """Build a text of exactly this many real tokens, counting what the tokenizer adds."""
        overhead = self.embedder.token_count(_UNIT) - 1
        tail = f" {suffix}" if suffix else ""
        used = self.embedder.token_count(_UNIT + tail) - overhead
        text = _UNIT + f" {_UNIT}" * (tokens - overhead - used) + tail
        self.assertEqual(self.embedder.token_count(text), tokens)
        return text

    def _embed(self, text: str) -> tuple[float, ...]:
        return self.embedder.embed_documents((text,), batch_size=1)[0]

    def test_tokenizer_adds_a_special_token_that_counts_against_the_limit(self) -> None:
        tokens = self.embedder._model.tokenize(_UNIT.encode())

        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[-1], self.embedder._model.token_eos())
        self.assertEqual(self.embedder.token_count(_UNIT), 2)

    def test_lengths_around_the_old_limit_are_embedded_whole(self) -> None:
        for tokens in (255, 256, 257):
            with self.subTest(tokens=tokens):
                self.assertEqual(len(self._embed(self._text(tokens))), 1024)

    def test_text_at_the_limit_is_embedded_and_one_token_more_is_refused(self) -> None:
        self.assertEqual(len(self._embed(self._text(EMBEDDING_TOKEN_CAPACITY))), 1024)

        with self.assertRaises(RetrievalFailure) as raised:
            self._embed(self._text(EMBEDDING_TOKEN_CAPACITY + 1))

        self.assertEqual(raised.exception.code, "embedding_input_too_long")
        self.assertIn(str(EMBEDDING_TOKEN_CAPACITY + 1), str(raised.exception))

    def test_only_a_marked_document_is_cut_and_only_after_the_limit(self) -> None:
        length = EMBEDDING_TOKEN_CAPACITY + 20
        first = self.embedder.embed_cut_document(self._text(length, "diagnosis"))
        second = self.embedder.embed_cut_document(self._text(length, "stock"))

        # The difference sits past the limit, so an identical result proves this really cuts.
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1024)
        # The same text still reaches the refusal unless a caller chose to record the cut.
        with self.assertRaises(RetrievalFailure):
            self._embed(self._text(length, "diagnosis"))

    def test_difference_after_token_256_reaches_the_vector(self) -> None:
        for length in (300, 1000):
            with self.subTest(tokens=length):
                first = self._embed(self._text(length, "diagnosis"))
                second = self._embed(self._text(length, "stock"))
                self.assertNotEqual(first, second)

    def test_old_settings_really_lose_the_difference_this_guards_against(self) -> None:
        # Negative control: if these vectors stop being equal, the test above no longer proves
        # anything about truncation, and neither does the old index compatibility reasoning.
        legacy = self._legacy_runtime()
        first = legacy.embed(self._text(300, "diagnosis"), normalize=True, truncate=True)
        second = legacy.embed(self._text(300, "stock"), normalize=True, truncate=True)

        self.assertEqual(first, second)

    def test_short_text_vectors_do_not_depend_on_token_capacity(self) -> None:
        # Only token capacity is compared here. Stored vectors of an old index can still differ
        # from these through decode batching and library version, so they count as unverified.
        legacy = self._legacy_runtime()
        for text in (self._text(40), self._text(_LEGACY_TOKEN_LIMIT)):
            with self.subTest(tokens=self.embedder.token_count(text)):
                current = self._embed(text)
                self.assertEqual(
                    current,
                    self._renormalized(legacy.embed(text, normalize=True, truncate=False)),
                )
        query = "Customer revenue by country"
        self.assertEqual(
            self.embedder.embed_query(query),
            self._renormalized(
                legacy.embed(qwen_embedding_query(query), normalize=True, truncate=False)
            ),
        )

    def test_physical_batch_size_does_not_change_a_long_vector(self) -> None:
        from llama_cpp import Llama

        whole = Llama(
            model_path=str(self.model_path), n_ctx=2048, n_batch=2048, n_ubatch=2048,
            n_threads=4, n_gpu_layers=0, embedding=True, verbose=False,
        )
        text = self._text(600)

        self.assertEqual(
            self._embed(text),
            self._renormalized(whole.embed(text, normalize=True, truncate=False)),
        )

    def test_query_limit_includes_the_retrieval_instruction(self) -> None:
        instruction = self.embedder.token_count(qwen_embedding_query("")) - 1
        self.assertGreater(instruction, 10)
        # "Query: " alone tokenizes its space separately; before a word the space merges into it.
        question = self._text(EMBEDDING_TOKEN_CAPACITY - instruction + 1)
        self.assertEqual(
            self.embedder.token_count(qwen_embedding_query(question)), EMBEDDING_TOKEN_CAPACITY,
        )

        with self.assertRaises(RetrievalFailure) as raised:
            self.embedder.embed_query(question + f" {_UNIT}")

        self.assertEqual(raised.exception.code, "embedding_input_too_long")
        self.assertIn("Query", str(raised.exception))

    def test_query_difference_after_token_256_reaches_the_vector(self) -> None:
        first = self.embedder.embed_query(self._text(300, "diagnosis"))
        second = self.embedder.embed_query(self._text(300, "stock"))

        self.assertNotEqual(first, second)

    def _legacy_runtime(self):
        from llama_cpp import Llama

        return Llama(
            model_path=str(self.model_path), n_ctx=2048, n_batch=256, n_ubatch=256,
            n_threads=4, n_gpu_layers=0, embedding=True, verbose=False,
        )

    @staticmethod
    def _renormalized(vector: list[float]) -> tuple[float, ...]:
        from tarel.retrieval.local import _normalized_vector

        return _normalized_vector(vector)


class OldIndexRuntimeTests(TestCase):
    """An index as the old settings stored it, reused by the current code with the real model."""

    model_path: ClassVar[Path]

    @classmethod
    def setUpClass(cls) -> None:
        cls.model_path = real_model_or_skip()

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.sdk = Tarel(Path(temporary.name) / ".tarel")
        self.graph = _long_object_graph()
        self.sdk.runtime.graph_store().save(self.graph)
        self.store = self.sdk.runtime.retrieval_index()
        self.store.build(
            self.graph, embedder=_OldSettingsQwen(self.model_path), model_path=self.model_path,
        )
        self.path = self.store.path(self.graph.name)
        with sqlite3.connect(self.path) as connection:
            connection.execute("DELETE FROM metadata WHERE key='embedding_input'")
            connection.execute("DELETE FROM metadata WHERE key='unverified_documents'")
            connection.execute("DELETE FROM metadata WHERE key='truncated_documents'")
            connection.execute("DELETE FROM metadata WHERE key='embedding_runtime'")
            connection.execute(
                "UPDATE metadata SET value=? WHERE key='contract_version'",
                (json.dumps("tarel.retrieval.v0.3"),),
            )

    def _vectors(self) -> dict[str, bytes]:
        with sqlite3.connect(self.path) as connection:
            return dict(connection.execute("SELECT document_id, value FROM vectors"))

    def test_real_query_search_and_selective_update_of_an_old_index(self) -> None:
        status = self.sdk.index.status(self.graph.name, model_path=self.model_path)
        self.assertEqual(status["state"], "ready")
        self.assertEqual(status["embedding_input"]["state"], "unverified")

        results = self.sdk.search.graph(
            self.graph.name, "Which table holds customer revenue?",
            mode="hybrid", model_path=self.model_path, n_threads=4,
        )
        self.assertEqual(results.hits[0].label, "dbo.Customer")
        self.assertIn("256 tokens", results.warnings[0])

        embedder = LlamaCppEmbedding(self.model_path, n_threads=4)
        long_ids = {
            item.id for item in build_retrieval_documents(self.graph)
            if embedder.token_count(item.text) > 256
        }
        self.assertTrue(long_ids)
        before = self._vectors()

        built = self.sdk.index.build(self.graph.name, model_path=self.model_path, n_threads=4)

        after = self._vectors()
        self.assertEqual(built.embedded_documents, len(long_ids))
        self.assertEqual(built.reused_documents, len(before) - len(long_ids))
        self.assertEqual(built.metadata.unverified_documents, built.reused_documents)
        self.assertRegex(built.metadata.embedding_runtime, r"^llama-cpp-python \d")
        self.assertEqual(
            {identifier for identifier in before if before[identifier] != after[identifier]},
            long_ids,
        )
        self.assertEqual(
            self.sdk.index.status(self.graph.name, model_path=self.model_path)["embedding_input"][
                "state"
            ],
            "partially_verified",
        )
        rerun = self.sdk.search.graph(
            self.graph.name, "Which table holds customer revenue?",
            mode="hybrid", model_path=self.model_path, n_threads=4,
        )
        self.assertEqual(rerun.warnings, ())


class ExistingStateRuntimeTests(TestCase):
    """Optional: an index a real earlier TAREL wrote; the state is copied, never used in place."""

    def test_native_old_index_serves_real_queries(self) -> None:
        model = real_model_or_skip()
        configured = os.getenv("TAREL_LEGACY_STATE")
        if not configured:
            self.skipTest("Set TAREL_LEGACY_STATE to a state holding an index of lab-chinook.")
        with TemporaryDirectory() as temporary:
            state = Path(temporary) / ".tarel"
            shutil.copytree(Path(configured), state)
            sdk = Tarel(state)
            status = sdk.index.status("lab-chinook", model_path=model)
            results = sdk.search.graph(
                "lab-chinook",
                "Welche Künstler und Musikgenres erzeugen Umsatz nach Kundenland?",
                mode="hybrid", model_path=model, n_threads=4, limit=12,
            )

        self.assertEqual(status["state"], "ready")
        self.assertEqual(status["index"]["contract_version"], "tarel.retrieval.v0.1")
        self.assertEqual(status["embedding_input"]["state"], "unverified")
        labels = " ".join(hit.label for hit in results.hits)
        for expected in ("Customer", "Genre", "Artist", "Track", "Invoice"):
            self.assertIn(expected, labels)


class _OldSettingsQwen:
    """Embeds as every earlier release did: n_batch=256 with silent truncation."""

    model_id = "qwen3-embedding-0.6b-q4-k-m.gguf"
    input_strategy = ""
    max_input_tokens = None
    runtime_version = ""

    def __init__(self, model_path: Path) -> None:
        from llama_cpp import Llama

        self.model = Llama(
            model_path=str(model_path), n_ctx=2048, n_batch=256, n_ubatch=256,
            n_threads=4, n_gpu_layers=0, embedding=True, verbose=False,
        )

    def token_count(self, text: str) -> None:
        del text

    def embed_documents(self, texts, *, batch_size):
        del batch_size
        return tuple(
            tuple(self.model.embed(text, normalize=True, truncate=True)) for text in texts
        )

    def embed_query(self, text):
        return self.embed_documents((text,), batch_size=1)[0]


def _long_object_graph():
    measures = tuple(
        CatalogField(f"Quarterly Revenue Measure {number} For Region", number, "decimal", False)
        for number in range(1, 26)
    )
    return build_graph_from_catalog(
        "old-index",
        CatalogResult(
            connector="test",
            source_type="database",
            catalog="ShopDW",
            dialect="tsql",
            objects=(
                CatalogObject(namespace="dbo", name="Customer", kind="table", fields=measures),
                CatalogObject(
                    namespace="dbo",
                    name="Calendar",
                    kind="table",
                    fields=(CatalogField("DateKey", 1, "integer", False),),
                ),
            ),
        ),
    )
