"""When existing retrieval indexes may be reused, and how their limits are reported."""

from __future__ import annotations

import json
import os
import sqlite3
from array import array
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.cli import main
from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
from tarel.graph.build import build_graph_from_catalog
from tarel.retrieval.contracts import RetrievalFailure
from tarel.retrieval.documents import build_retrieval_documents
from tarel.retrieval.index import embedding_input_warning, vector_reuse_rule
LOCAL_EMBEDDING_INPUT = "llama.cpp:max_tokens=2048:overflow=recorded_document_cut"
from tarel.retrieval.remote import HTTP_EMBEDDING_INPUT
from tarel.sdk import Tarel
from tarel.workspaces.core import create_workspace, define_system

LOCAL_EMBEDDING = "tarel.retrieval.application._create_local_embedder"
_OLD_FORMATS = ("tarel.retrieval.v0.1", "tarel.retrieval.v0.2", "tarel.retrieval.v0.3")


class VectorReuseRuleTests(TestCase):
    def test_decision_table(self) -> None:
        for stored, current, countable, expected in (
            (LOCAL_EMBEDDING_INPUT, LOCAL_EMBEDDING_INPUT, True, "all"),
            ("", LOCAL_EMBEDDING_INPUT, True, "whole_only"),
            ("llama.cpp:max_tokens=512:overflow=reject", LOCAL_EMBEDDING_INPUT, True, "none"),
            ("", HTTP_EMBEDDING_INPUT, False, "all"),
            (HTTP_EMBEDDING_INPUT, HTTP_EMBEDDING_INPUT, False, "all"),
            (HTTP_EMBEDDING_INPUT, LOCAL_EMBEDDING_INPUT, True, "none"),
            ("", None, False, "all"),
        ):
            with self.subTest(stored=stored, current=current):
                self.assertEqual(
                    vector_reuse_rule(stored, current, countable=countable), expected,
                )


class IndexCompatibilityCase(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.model = self.root / "qwen.gguf"
        self.model.write_bytes(b"test model")
        self.sdk = Tarel(self.root / ".tarel")
        self.graph = _graph("sales", "SalesDW", long_fields=40)
        self.sdk.runtime.graph_store().save(self.graph)
        self.documents = build_retrieval_documents(self.graph)
        self.long_ids = {item.id for item in self.documents if _words(item.text) > 256}
        self.assertTrue(self.long_ids)
        self.assertLess(len(self.long_ids), len(self.documents))
        self.store = self.sdk.runtime.retrieval_index()

    def _built_old_index(self, graph=None, *, version: str = "tarel.retrieval.v0.3") -> Path:
        graph = graph or self.graph
        self.store.build(graph, embedder=_TokenEmbedding(), model_path=self.model)
        path = self.store.path(graph.name)
        _downgrade(path, version)
        return path

    def _build(self, embedder=None):
        embedder = embedder or _TokenEmbedding()
        # A fresh client, because a runtime keeps its loaded embedding backend.
        with patch(LOCAL_EMBEDDING, return_value=embedder):
            built = Tarel(self.root / ".tarel").index.build("sales", model_path=self.model)
        return built, embedder


class ExistingFormatTests(IndexCompatibilityCase):
    def test_old_formats_stay_usable_but_are_not_reported_as_verified(self) -> None:
        for version in _OLD_FORMATS:
            with self.subTest(version=version):
                self._built_old_index(version=version)
                status = self.sdk.index.status("sales", model_path=self.model)

                self.assertEqual(status["state"], "ready")
                self.assertEqual(status["index"]["contract_version"], version)
                self.assertEqual(status["embedding_input"]["state"], "unverified")
                self.assertIsNone(status["embedding_input"]["strategy"])
                self.assertEqual(
                    status["embedding_input"]["unverified_documents"], len(self.documents),
                )

    def test_vector_search_on_an_old_index_warns_and_names_the_graph(self) -> None:
        self._built_old_index()

        with patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding()):
            results = self.sdk.search.graph(
                "sales", "revenue", mode="hybrid", model_path=self.model,
            )

        self.assertTrue(results.hits)
        self.assertEqual(len(results.warnings), 1)
        self.assertIn("sales", results.warnings[0])
        self.assertIn("256 tokens", results.warnings[0])
        self.assertEqual(results.to_dict()["warnings"], list(results.warnings))

    def test_bm25_does_not_warn_about_vectors_it_does_not_use(self) -> None:
        self._built_old_index()

        results = self.sdk.search.graph("sales", "revenue", mode="bm25")

        self.assertEqual(results.warnings, ())

    def test_update_re_embeds_only_documents_the_old_limit_could_have_cut(self) -> None:
        for version in _OLD_FORMATS:
            with self.subTest(version=version):
                path = self._built_old_index(version=version)
                short_id = next(
                    item.id for item in self.documents if item.id not in self.long_ids
                )
                before = _vector(path, short_id)

                result, embedder = self._build()

                self.assertEqual(result.embedded_documents, len(self.long_ids))
                self.assertEqual(
                    result.reused_documents, len(self.documents) - len(self.long_ids),
                )
                self.assertEqual(set(embedder.embedded), {
                    item.text for item in self.documents if item.id in self.long_ids
                })
                self.assertEqual(_vector(path, short_id), before)
                metadata = result.metadata
                self.assertEqual(metadata.embedding_input, LOCAL_EMBEDDING_INPUT)
                self.assertEqual(metadata.unverified_documents, result.reused_documents)

    def test_carried_vectors_stay_reported_as_unverified_after_the_update(self) -> None:
        self._built_old_index()
        self._build()

        status = self.sdk.index.status("sales", model_path=self.model)
        repeat, embedder = self._build()
        with patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding()):
            results = self.sdk.search.graph(
                "sales", "revenue", mode="hybrid", model_path=self.model,
            )

        self.assertEqual(status["state"], "ready")
        self.assertEqual(status["embedding_input"]["state"], "partially_verified")
        self.assertIn("not because they were re-embedded", status["embedding_input"]["detail"])
        self.assertEqual(repeat.embedded_documents, 0)
        self.assertEqual(embedder.embedded, [])
        self.assertEqual(repeat.metadata.unverified_documents, status["embedding_input"][
            "unverified_documents"
        ])
        self.assertEqual(results.warnings, ())

    def test_a_fresh_build_is_verified_and_needs_no_model_when_unchanged(self) -> None:
        result, _embedder = self._build()

        self.assertEqual(result.embedded_documents, len(self.documents))
        self.assertEqual(result.metadata.unverified_documents, 0)
        status = self.sdk.index.status("sales", model_path=self.model)
        self.assertEqual(status["embedding_input"]["state"], "verified")

        with patch(LOCAL_EMBEDDING, side_effect=AssertionError("model must not load")):
            repeat = self.sdk.index.build("sales", model_path=self.model)

        self.assertEqual(repeat.embedded_documents, 0)
        self.assertEqual(repeat.reused_documents, len(self.documents))

    def test_a_different_recorded_strategy_keeps_no_vectors(self) -> None:
        self.store.build(self.graph, embedder=_TokenEmbedding(), model_path=self.model)
        _set_metadata(
            self.store.path("sales"),
            embedding_input="llama.cpp:max_tokens=512:overflow=reject",
        )

        with patch(
            "tarel.retrieval.application.local_embedding_input_strategy",
            return_value=LOCAL_EMBEDDING_INPUT,
        ):
            result, _embedder = self._build()

        self.assertEqual(result.reused_documents, 0)
        self.assertEqual(result.embedded_documents, len(self.documents))
        self.assertEqual(result.metadata.unverified_documents, 0)

    def test_changed_document_in_an_old_index_is_embedded_again(self) -> None:
        self._built_old_index()
        changed = _graph("sales", "SalesDW", long_fields=40, extra_field="ChangedField")
        self.sdk.runtime.graph_store().save(changed)

        result, embedder = self._build()

        self.assertTrue(any("ChangedField" in text for text in embedder.embedded))
        self.assertLess(result.reused_documents, len(self.documents))

    def test_remote_old_index_keeps_vectors_because_its_path_did_not_change(self) -> None:
        embedder = _RemoteEmbedding()
        self.store.build(
            self.graph, embedder=embedder, model_path=None, model_sha256="remote-identity",
        )
        path = self.store.path("sales")
        _downgrade(path, "tarel.retrieval.v0.3")
        embedder.embedded.clear()

        result = self.store.build(
            self.graph, embedder=embedder, model_path=None, model_sha256="remote-identity",
        )

        self.assertEqual(embedder.embedded, [])
        self.assertEqual(result.metadata.embedding_input, HTTP_EMBEDDING_INPUT)
        self.assertEqual(result.metadata.unverified_documents, 0)
        self.assertIsNone(embedding_input_warning(result.metadata))


class EmbeddingRuntimeTests(IndexCompatibilityCase):
    def test_runtime_names_the_build_that_embedded_and_triggers_nothing(self) -> None:
        first, _embedder = self._build()
        self.assertEqual(first.metadata.embedding_runtime, "llama-cpp-python 9.9.9")
        status = self.sdk.index.status("sales", model_path=self.model)
        self.assertEqual(status["embedding_input"]["runtime"], "llama-cpp-python 9.9.9")

        class Newer(_TokenEmbedding):
            runtime_version = "llama-cpp-python 10.0.0"

        repeat, embedder = self._build(Newer())

        self.assertEqual(embedder.embedded, [])
        self.assertEqual(repeat.reused_documents, len(self.documents))
        self.assertEqual(repeat.metadata.embedding_runtime, "llama-cpp-python 9.9.9")

    def test_old_index_has_no_runtime_until_something_is_embedded(self) -> None:
        self._built_old_index()
        status = self.sdk.index.status("sales", model_path=self.model)
        self.assertIsNone(status["embedding_input"]["runtime"])

        updated, _embedder = self._build()

        self.assertGreater(updated.embedded_documents, 0)
        self.assertEqual(updated.metadata.embedding_runtime, "llama-cpp-python 9.9.9")


class ContextWarningTests(IndexCompatibilityCase):
    def _context(self, mode: str):
        with patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding()):
            return self.sdk.context.graph("sales", "revenue", mode=mode, model_path=self.model)

    def test_limits_reach_the_packet_outside_its_stable_part(self) -> None:
        self._cut_index()
        cut = self._context("hybrid")
        warnings = cut.to_dict()["dynamic"]["retrieval"]["warnings"]

        self.assertEqual(warnings, list(cut.retrieval_warnings))
        self.assertIn("shortened", warnings[0])
        self.assertNotIn("shortened", json.dumps(cut.stable_dict()))
        clean = replace(cut, retrieval_warnings=())
        self.assertEqual(clean.stable_hash, cut.stable_hash)
        self.assertNotEqual(clean.packet_hash, cut.packet_hash)
        self.assertNotIn("warnings", clean.to_dict()["dynamic"]["retrieval"])

    def test_old_index_warning_reaches_the_packet_and_its_brief(self) -> None:
        self._built_old_index()

        packet = self._context("hybrid")
        brief = self.sdk.context.brief(packet)

        self.assertIn("256 tokens", packet.retrieval_warnings[0])
        gaps = {gap.code: gap for gap in brief.gaps}
        self.assertEqual(gaps["retrieval_warnings"].references, packet.retrieval_warnings)

    def test_modes_without_vectors_and_clean_indexes_add_nothing(self) -> None:
        self._built_old_index()
        lexical = self.sdk.context.graph("sales", "revenue", mode="bm25")
        self.assertEqual(lexical.retrieval_warnings, ())
        self.assertEqual(lexical.to_dict()["dynamic"]["retrieval"].keys(), {"mode", "terms"})

        self.store.path("sales").unlink()
        self.store.build(self.graph, embedder=_TokenEmbedding(), model_path=self.model)
        self.assertEqual(self._context("hybrid").retrieval_warnings, ())

    def _cut_index(self) -> None:
        self.store.build(self.graph, embedder=_TokenEmbedding(limit=100), model_path=self.model)


class OverlongDocumentTests(IndexCompatibilityCase):
    def _cut_build(self, graph=None, *, limit: int = 100):
        embedder = _TokenEmbedding(limit=limit)
        result = self.store.build(graph or self.graph, embedder=embedder, model_path=self.model)
        return result, embedder

    def test_overlong_documents_are_cut_named_and_their_fields_stay_whole(self) -> None:
        result, embedder = self._cut_build()

        self.assertEqual(set(result.metadata.truncated_documents), self.long_ids)
        self.assertEqual(len(embedder.cut), len(self.long_ids))
        self.assertEqual(
            len(embedder.embedded), len(self.documents) - len(self.long_ids),
        )
        self.assertTrue(all(_words(text) > 100 for text in embedder.cut))
        self.assertTrue(all(_words(text) <= 100 for text in embedder.embedded))

    def test_vectors_stay_in_document_order_when_some_are_cut(self) -> None:
        class Distinct(_TokenEmbedding):
            def embed_documents(self, texts, *, batch_size):
                del batch_size
                return tuple((0.0, 1.0) for _text in texts)

        self.store.build(self.graph, embedder=Distinct(limit=100), model_path=self.model)
        path = self.store.path("sales")

        cut = _unpack(_vector(path, next(iter(self.long_ids))))
        whole = _unpack(_vector(
            path, next(item.id for item in self.documents if item.id not in self.long_ids),
        ))

        self.assertEqual((cut, whole), ((1.0, 0.0), (0.0, 1.0)))

    def test_status_and_search_report_the_cut(self) -> None:
        self._cut_build()

        status = self.sdk.index.status("sales", model_path=self.model)
        with patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding()):
            results = self.sdk.search.graph(
                "sales", "revenue", mode="hybrid", model_path=self.model,
            )

        self.assertEqual(status["state"], "ready")
        self.assertEqual(status["embedding_input"]["state"], "verified_with_truncation")
        self.assertEqual(set(status["embedding_input"]["truncated_documents"]), self.long_ids)
        self.assertIn("beginning", status["embedding_input"]["detail"])
        self.assertEqual(len(results.warnings), 1)
        self.assertIn("sales", results.warnings[0])
        self.assertIn("shortened", results.warnings[0])

    def test_record_survives_reuse_and_ends_when_the_document_is_gone(self) -> None:
        self._cut_build()
        repeat, embedder = self._cut_build()
        self.assertEqual(embedder.cut, [])
        self.assertEqual(set(repeat.metadata.truncated_documents), self.long_ids)

        narrow = _graph("sales", "SalesDW", long_fields=2)
        self.sdk.runtime.graph_store().save(narrow)
        changed, _embedder = self._cut_build(narrow)

        self.assertEqual(changed.metadata.truncated_documents, ())

    def test_record_is_kept_when_nothing_needs_a_model(self) -> None:
        self._cut_build()

        with patch(LOCAL_EMBEDDING, side_effect=AssertionError("model must not load")):
            repeat = self.sdk.index.build("sales", model_path=self.model)

        self.assertEqual(set(repeat.metadata.truncated_documents), self.long_ids)

    def test_old_index_update_records_cuts_next_to_kept_vectors(self) -> None:
        self._built_old_index()
        short = len(self.documents) - len(self.long_ids)

        result, embedder = self._cut_build(limit=100)

        self.assertEqual(result.metadata.unverified_documents, short)
        self.assertEqual(set(result.metadata.truncated_documents), self.long_ids)
        self.assertEqual(embedder.embedded, [])
        state = self.sdk.index.status("sales", model_path=self.model)["embedding_input"]
        self.assertEqual(state["state"], "partially_verified")
        self.assertIn("not because they were re-embedded", state["detail"])
        self.assertIn("beginning", state["detail"])

    def test_cli_build_reports_the_cut_in_text_and_json(self) -> None:
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        outputs = {}
        for form in ("text", "json"):
            self.store.path("sales").unlink(missing_ok=True)
            output = StringIO()
            with (
                patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding(limit=100)),
                redirect_stdout(output),
                redirect_stderr(StringIO()),
            ):
                code = main([
                    "index", "build", "sales", "--model", str(self.model), "--format", form,
                ])
            self.assertEqual(code, 0)
            outputs[form] = output.getvalue()

        self.assertIn(f"Shortened documents: {len(self.long_ids)}", outputs["text"])
        self.assertEqual(
            set(json.loads(outputs["json"])["index"]["truncated_documents"]), self.long_ids,
        )


class IncompatibleIndexTests(IndexCompatibilityCase):
    def test_changed_graph_is_stale_and_named(self) -> None:
        self._built_old_index()
        self.sdk.runtime.graph_store().save(
            _graph("sales", "SalesDW", long_fields=40, extra_field="NewField")
        )

        status = self.sdk.index.status("sales", model_path=self.model)
        self.assertEqual(status["state"], "update_required")
        self.assertFalse(status["ready"])
        self.assertGreater(status["changes"]["requires_embedding"], 0)
        with (
            patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding()),
            self.assertRaises(RetrievalFailure) as raised,
        ):
            self.sdk.search.graph("sales", "revenue", mode="vector", model_path=self.model)

        self.assertEqual(raised.exception.code, "stale_index")
        self.assertIn("sales", str(raised.exception))

    def test_other_model_is_a_named_mismatch(self) -> None:
        self._built_old_index()
        other = self.root / "other.gguf"
        other.write_bytes(b"other model")

        status = self.sdk.index.status("sales", model_path=other)
        self.assertEqual(status["state"], "model_mismatch")
        self.assertFalse(status["model_matches"])
        with (
            patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding()),
            self.assertRaises(RetrievalFailure) as raised,
        ):
            self.sdk.search.graph("sales", "revenue", mode="vector", model_path=other)

        self.assertEqual(raised.exception.code, "model_index_mismatch")
        self.assertIn("sales", str(raised.exception))

    def test_other_model_keeps_no_vectors_on_update(self) -> None:
        self._built_old_index()
        other = self.root / "other.gguf"
        other.write_bytes(b"other model")

        with patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding()):
            result = self.sdk.index.build("sales", model_path=other)

        self.assertEqual(result.reused_documents, 0)
        self.assertEqual(result.metadata.unverified_documents, 0)

    def test_foreign_formats_are_named_and_never_overwritten(self) -> None:
        path = self.store.path("sales")
        path.parent.mkdir(parents=True, exist_ok=True)
        for name, create, code, expected in (
            ("foreign manifest", _foreign_manifest, "unsupported_index", "trb.vector-index.v1"),
            ("positional vectors", _foreign_vectors, "invalid_index", "not a TAREL index"),
        ):
            with self.subTest(name=name):
                path.unlink(missing_ok=True)
                create(path)
                before = path.read_bytes()

                for operation in (
                    lambda: self.sdk.index.status("sales", model_path=self.model),
                    lambda: self.sdk.index.build("sales", model_path=self.model),
                ):
                    with (
                        patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding()),
                        self.assertRaises(RetrievalFailure) as raised,
                    ):
                        operation()
                    self.assertEqual(raised.exception.code, code)
                    self.assertIn(expected, str(raised.exception))
                    self.assertIn("sales", str(raised.exception))

                self.assertEqual(path.read_bytes(), before)

    def test_checkpoint_from_older_settings_is_not_resumed(self) -> None:
        self.store.checkpoint_path("sales").parent.mkdir(parents=True, exist_ok=True)
        embedder = _TokenEmbedding(fail_after=1)
        with self.assertRaises(RetrievalFailure):
            self.store.build(
                self.graph, embedder=embedder, model_path=self.model, batch_size=2, resume=True,
            )
        checkpoint = self.store.checkpoint_path("sales")
        with sqlite3.connect(checkpoint) as connection:
            connection.execute("DELETE FROM metadata WHERE key='embedding_input'")
            connection.execute(
                "UPDATE metadata SET value=? WHERE key='checkpoint_version'",
                (json.dumps("tarel.retrieval-checkpoint.v0.2"),),
            )

        status = self.store.checkpoint_status("sales")
        with self.assertRaises(RetrievalFailure) as raised:
            self.store.build(
                self.graph, embedder=_TokenEmbedding(), model_path=self.model, resume=True,
            )

        self.assertIsNone(status["embedding_input"])
        self.assertEqual(raised.exception.code, "stale_index_checkpoint")
        self.assertIn("embedding settings", str(raised.exception))
        self.store.build(self.graph, embedder=_TokenEmbedding(), model_path=self.model)
        self.assertFalse(checkpoint.exists())


class WorkspaceCoverageTests(IndexCompatibilityCase):
    def setUp(self) -> None:
        super().setUp()
        self.other = _graph("crm", "CrmDB", long_fields=2)
        self.sdk.runtime.graph_store().save(self.other)
        graphs = {"sales": self.graph, "crm": self.other}
        self.sdk.runtime.workspace_store().save(define_system(
            define_system(
                create_workspace("estate"), "sales", graph_names=("sales",), graphs=graphs,
            ),
            "crm", graph_names=("crm",), graphs=graphs,
        ))

    def test_partial_index_is_not_reported_as_workspace_coverage(self) -> None:
        self._built_old_index()

        status = self.sdk.index.status_workspace("estate", model_path=self.model)

        self.assertEqual(status["state"], "update_required")
        self.assertFalse(status["ready"])
        self.assertEqual((status["ready_graphs"], status["missing_graphs"]), (1, 1))
        self.assertEqual(status["unverified_embedding_graphs"], ["sales"])
        by_graph = {item["graph"]: item for item in status["graphs"]}
        self.assertEqual(by_graph["crm"]["state"], "missing")
        self.assertIsNone(by_graph["crm"]["embedding_input"])

    def test_search_over_a_partial_index_names_the_missing_graph(self) -> None:
        self._built_old_index()

        with (
            patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding()),
            self.assertRaises(RetrievalFailure) as raised,
        ):
            self.sdk.search.workspace("estate", "revenue", mode="hybrid", model_path=self.model)

        self.assertEqual(raised.exception.code, "index_not_found")
        self.assertIn("crm", str(raised.exception))

    def test_the_indexed_system_can_be_searched_and_warns_only_for_itself(self) -> None:
        self._built_old_index()

        with patch(LOCAL_EMBEDDING, return_value=_TokenEmbedding()):
            results = self.sdk.search.workspace(
                "estate", "revenue", systems=("sales",), mode="hybrid", model_path=self.model,
            )

        self.assertEqual(results.graphs, ("sales",))
        self.assertTrue(all(hit.source_graph == "sales" for hit in results.hits))
        self.assertEqual(len(results.warnings), 1)
        self.assertIn("sales", results.warnings[0])

    def test_workspace_update_settles_old_graphs_and_then_has_nothing_left(self) -> None:
        self._built_old_index()
        embedder = _TokenEmbedding()

        with patch(LOCAL_EMBEDDING, return_value=embedder):
            first = self.sdk.index.build_workspace("estate", model_path=self.model)
            second = self.sdk.index.build_workspace("estate", model_path=self.model)

        built = {item["graph"]: item for item in first["built"]}
        self.assertEqual(built["sales"]["embedded_documents"], len(self.long_ids))
        self.assertEqual(
            built["sales"]["unverified_documents"], len(self.documents) - len(self.long_ids),
        )
        self.assertEqual(built["crm"]["unverified_documents"], 0)
        self.assertEqual(first["remaining_graphs"], 0)
        self.assertEqual(second["built"], [])

    def test_cli_status_shows_the_same_limits_in_json_and_text(self) -> None:
        self._built_old_index()
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)

        for arguments, parse in (
            (["index", "status", "--workspace", "estate", "--format", "json"], json.loads),
            (["index", "status", "--workspace", "estate", "--format", "text"], str),
        ):
            output = StringIO()
            with redirect_stdout(output), redirect_stderr(StringIO()):
                code = main(arguments)
            self.assertEqual(code, 1)
            payload = parse(output.getvalue())
            if isinstance(payload, dict):
                self.assertEqual(payload, self.sdk.index.status_workspace("estate"))
            else:
                self.assertIn("Unverified embedding settings: sales", payload)
                self.assertIn("crm: missing", payload)

        output = StringIO()
        with redirect_stdout(output):
            main(["index", "status", "sales", "--format", "text"])
        self.assertIn("Embedding input: unverified.", output.getvalue())


class _TokenEmbedding:
    """Counts one token per word, so tests can place documents around the old limit."""

    model_id = "qwen.gguf"
    input_strategy = LOCAL_EMBEDDING_INPUT
    runtime_version = "llama-cpp-python 9.9.9"

    def __init__(self, *, limit: int = 2048, fail_after: int | None = None) -> None:
        self.max_input_tokens = limit
        self.fail_after = fail_after
        self.embedded: list[str] = []
        self.cut: list[str] = []

    def token_count(self, text: str) -> int:
        return _words(text)

    def embed_documents(self, texts, *, batch_size):
        del batch_size
        if self.fail_after is not None and len(self.embedded) >= self.fail_after:
            raise RetrievalFailure("embedding_failed", "Synthetic interruption.")
        self.embedded.extend(texts)
        return tuple((1.0, 0.0) for _text in texts)

    def embed_query(self, text):
        del text
        return (1.0, 0.0)

    def embed_cut_document(self, text):
        self.cut.append(text)
        return (1.0, 0.0)


class _RemoteEmbedding(_TokenEmbedding):
    input_strategy = HTTP_EMBEDDING_INPUT

    def __init__(self) -> None:
        super().__init__()
        self.max_input_tokens = None

    def token_count(self, text):
        del text


def _words(text: str) -> int:
    return len(text.split())


def _graph(name: str, catalog: str, *, long_fields: int, extra_field: str | None = None):
    names = [
        f"Revenue Measure Number {number} With A Long Spoken Name"
        for number in range(long_fields)
    ]
    if extra_field:
        names.append(extra_field)
    return build_graph_from_catalog(
        name,
        CatalogResult(
            connector="test",
            source_type="database",
            catalog=catalog,
            dialect="tsql",
            objects=(
                CatalogObject(
                    namespace="dbo",
                    name="Revenue",
                    kind="table",
                    fields=tuple(
                        CatalogField(item, position, "decimal", False)
                        for position, item in enumerate(names, start=1)
                    ),
                ),
            ),
        ),
    )


def _downgrade(path: Path, version: str) -> None:
    """Rewrite a built index into an older persisted format, as those releases stored it."""
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM metadata WHERE key='embedding_input'")
        connection.execute("DELETE FROM metadata WHERE key='unverified_documents'")
        connection.execute("DELETE FROM metadata WHERE key='truncated_documents'")
        connection.execute("DELETE FROM metadata WHERE key='embedding_runtime'")
        connection.execute(
            "UPDATE metadata SET value=? WHERE key='contract_version'", (json.dumps(version),),
        )
        if version != "tarel.retrieval.v0.3":
            connection.execute("DELETE FROM metadata WHERE key='documents_sha256'")
        if version == "tarel.retrieval.v0.1":
            connection.execute("DELETE FROM metadata WHERE key='annotation_states'")
            connection.execute("ALTER TABLE documents DROP COLUMN text_sha256")


def _set_metadata(path: Path, **values: object) -> None:
    with sqlite3.connect(path) as connection:
        for key, value in values.items():
            connection.execute(
                "UPDATE metadata SET value=? WHERE key=?", (json.dumps(value), key),
            )


def _vector(path: Path, document_id: str) -> bytes:
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT value FROM vectors WHERE document_id=?", (document_id,),
        ).fetchone()[0]


def _unpack(blob: bytes) -> tuple[float, ...]:
    values = array("f")
    values.frombytes(blob)
    return tuple(values)


def _foreign_manifest(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO metadata VALUES ('contract_version', ?)",
            (json.dumps("trb.vector-index.v1"),),
        )


def _foreign_vectors(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE vectors (position INTEGER PRIMARY KEY, value BLOB)")
