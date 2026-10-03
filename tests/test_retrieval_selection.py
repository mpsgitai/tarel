"""Model selection, isolation and cloud failure boundaries without paid calls."""

import json
import os
import urllib.error
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from tarel.cli import main
from tarel.graph.contracts import GraphAnnotation
from tarel.providers.config import HTTPProviderConfig
from tarel.retrieval.catalog import list_models
from tarel.retrieval.contracts import RetrievalFailure
from tarel.retrieval.local import DEFAULT_MODEL_NAME, sha256_file
from tarel.retrieval.remote import HTTPEmbedding, HTTPRetrievalClient, indexed_rows, rerank_remote
from tarel.retrieval.rerank import LocalQwenReranker, rerank_results
from tarel.retrieval.settings import index_namespace, load_settings, snapshot_runtime
from tarel.sdk import ModelChoice, RetrievalSettings, Tarel
from tarel.ui.server import TarelUIBackend, UIConfig
from tarel.workspaces.contracts import SchemaReference
from tarel.workspaces.core import create_workspace, define_area, define_system, define_zone
from tests.test_retrieval import _FakeEmbedding, _retrieval_graph
from tests.test_retrieval_workflow import _focus


def _profile():
    return HTTPProviderConfig(
        "openrouter",
        "openrouter",
        "test-key",
        "unused-chat-default",
        "https://openrouter.ai/api/v1",
    )


class RetrievalSelectionTests(TestCase):
    def setUp(self) -> None:
        configuration = TemporaryDirectory()
        self.addCleanup(configuration.cleanup)
        environment = {key: value for key, value in os.environ.items() if not (
            key.startswith(("TAREL_PROVIDER_", "TAREL_OPENROUTER_"))
            or key in {"OPENROUTER_API_KEY", "OPENAI_API_KEY"}
        )}
        environment["XDG_CONFIG_HOME"] = configuration.name
        self.enterContext(patch.dict(os.environ, environment, clear=True))
        # Index namespacing imports this loader independently from the HTTP adapter.
        self.enterContext(patch("tarel.providers.config.load_http_provider_config",
                               return_value=_profile()))

    def test_local_model_override_keeps_configured_indexes_and_settings_intact(self):
        for saved in (True, False):
            with (
                self.subTest(saved=saved), TemporaryDirectory() as temporary,
                patch("tarel.application.LlamaCppEmbedding", return_value=_FakeEmbedding()),
            ):
                root = Path(temporary)
                original_model, override = root / "original.gguf", root / "override.gguf"
                original_model.write_bytes(b"original model")
                override.write_bytes(b"override model")
                settings = RetrievalSettings(embedding=ModelChoice(model_path=str(original_model)))
                sdk = Tarel(root / ".tarel", retrieval=None if saved else settings)
                if saved:
                    sdk.retrieval.configure(settings)
                graphs = (_retrieval_graph(), replace(_retrieval_graph(), name="second"))
                for graph in graphs:
                    sdk.runtime.graph_store().save(graph)
                sdk.runtime.workspace_store().save(define_system(
                    create_workspace("estate"), "analytics",
                    graph_names=tuple(graph.name for graph in graphs),
                    graphs={graph.name: graph for graph in graphs},
                ))
                sdk.index.build_workspace("estate", max_graphs=2)
                originals = {graph.name: sdk.runtime.retrieval_index().path(graph.name)
                             for graph in graphs}
                content = {name: path.read_bytes() for name, path in originals.items()}
                self.assertEqual(sdk.index.status_workspace("estate", model_path=override)
                                 ["state"], "missing")
                built = sdk.index.build(graphs[0].name, model_path=override)
                self.assertNotEqual(built.path, originals[graphs[0].name])
                workspace_build = sdk.index.build_workspace("estate", model_path=override)
                self.assertEqual(workspace_build["built_graphs"], 1)
                for graph in graphs:
                    for path in (None, override):
                        self.assertTrue(sdk.index.status(graph.name, model_path=path)["ready"])
                        self.assertTrue(sdk.search.graph(graph.name, "internet revenue",
                                                        mode="hybrid", model_path=path).hits)
                    self.assertEqual(originals[graph.name].read_bytes(), content[graph.name])
                for path in (None, override):
                    self.assertTrue(sdk.index.status_workspace("estate", model_path=path)["ready"])
                    self.assertTrue(sdk.search.workspace("estate", "internet revenue",
                                                        mode="hybrid", model_path=path).hits)
                self.assertEqual(sdk.retrieval.settings(), settings)
                selected_override = Tarel(sdk.root, retrieval=RetrievalSettings(
                    embedding=ModelChoice(model_path=str(override)),
                ))
                self.assertEqual(selected_override.runtime.retrieval_index().path(graphs[0].name),
                                 built.path)
                if saved:
                    previous, output = Path.cwd(), StringIO()
                    os.chdir(root)
                    try:
                        with redirect_stdout(output):
                            code = main(["index", "build", graphs[0].name,
                                         "--model", str(override), "--format", "json"])
                        self.assertEqual(code, 0)
                        self.assertEqual(json.loads(output.getvalue())["path"], str(built.path))
                    finally:
                        os.chdir(previous)

    def test_gui_cannot_persist_or_change_a_pinned_sdk_override(self):
        for project_configured in (False, True):
            with self.subTest(project_configured=project_configured), TemporaryDirectory() as root:
                regular = Tarel(root)
                if project_configured:
                    regular.retrieval.configure(RetrievalSettings(rerank_depth=25))
                path = regular.root / "retrieval.json"
                before = path.read_bytes() if path.is_file() else None
                settings = RetrievalSettings(ModelChoice("openrouter", "embedding"))
                pinned = Tarel(root, retrieval=settings)
                backend = TarelUIBackend(UIConfig(graph="sales", search_mode="bm25"),
                                         runtime=pinned.runtime)
                with self.assertRaises(RetrievalFailure) as error:
                    backend.mutate("/api/retrieval/settings", {
                        "settings": RetrievalSettings().to_dict(), "search_mode": "hybrid",
                    })
                self.assertEqual(error.exception.code, "retrieval_settings_override")
                self.assertEqual(path.read_bytes() if path.is_file() else None, before)
                self.assertIs(backend.runtime, pinned.runtime)
                self.assertEqual(backend.config.search_mode, "bm25")
                self.assertEqual(pinned.retrieval.settings(), settings)
                self.assertEqual(backend.read("/api/retrieval/settings")["settings"],
                                 settings.to_dict())

    def test_default_snapshot_stays_local_when_first_configuration_appears(self):
        with TemporaryDirectory() as temporary:
            previous = Path.cwd()
            os.chdir(temporary)
            try:
                sdk = Tarel(Path(temporary) / ".tarel")
                captured = (snapshot_runtime(None), snapshot_runtime(sdk.runtime))
                sdk.retrieval.configure(RetrievalSettings(
                    ModelChoice("openrouter", "embedding"),
                    ModelChoice("openrouter", "typesafe/jev-1.13"),
                ))
                for snapshot in captured:
                    self.assertEqual(load_settings(snapshot), RetrievalSettings())
                    self.assertIsNone(index_namespace(snapshot))
                    self.assertIs(snapshot_runtime(snapshot), snapshot)
                self.assertEqual(sdk.retrieval.settings().embedding.provider, "openrouter")
            finally:
                os.chdir(previous)

    def test_search_cannot_call_cloud_after_concurrent_first_configuration(self):
        with (
            TemporaryDirectory() as temporary,
            patch("tarel.application.LlamaCppEmbedding", return_value=_FakeEmbedding()),
            patch("tarel.application.HTTPEmbedding") as cloud_embedding,
            patch("tarel.retrieval.rerank.rerank_remote") as cloud_reranker,
        ):
            sdk = Tarel(temporary)
            model = Path(temporary) / "local.gguf"
            model.write_bytes(b"local model")
            graph = _retrieval_graph()
            sdk.runtime.graph_store().save(graph)
            built = sdk.index.build(graph.name, model_path=model)

            def configure_and_load(name):
                sdk.retrieval.configure(RetrievalSettings(
                    ModelChoice("openrouter", "embedding"),
                    ModelChoice("openrouter", "typesafe/jev-1.13"),
                ))
                return graph

            with patch("tarel.application._graph_store") as store:
                store.return_value.load.side_effect = configure_and_load
                hits = sdk.search.graph(graph.name, "internet revenue", mode="hybrid",
                                        model_path=model)
            self.assertTrue(hits.hits)
            self.assertTrue(built.path.is_file())
            self.assertEqual(sdk.retrieval.settings().embedding.provider, "openrouter")
            cloud_embedding.assert_not_called()
            cloud_reranker.assert_not_called()

    def test_workspace_build_keeps_one_selection_during_first_configuration(self):
        with (
            TemporaryDirectory() as temporary,
            patch("tarel.application.LlamaCppEmbedding", return_value=_FakeEmbedding()),
            patch("tarel.application.HTTPEmbedding") as cloud,
        ):
            sdk = Tarel(temporary)
            model = Path(temporary) / "local.gguf"
            model.write_bytes(b"local model")
            graphs = (_retrieval_graph(), replace(_retrieval_graph(), name="second"))
            for graph in graphs:
                sdk.runtime.graph_store().save(graph)
            sdk.runtime.workspace_store().save(define_system(
                create_workspace("estate"), "analytics",
                graph_names=tuple(graph.name for graph in graphs),
                graphs={graph.name: graph for graph in graphs},
            ))

            def configure(determined, total, stage):
                sdk.retrieval.configure(RetrievalSettings(ModelChoice("openrouter", "embedding")))

            result = sdk.index.build_workspace("estate", model_path=model, progress=configure)
            self.assertEqual(result["built_graphs"], 2)
            self.assertTrue(result["status"]["ready"])
            for built in result["built"]:
                self.assertEqual(Path(built["path"]), sdk.root / "indexes"
                                 / built["graph"] / "index.sqlite")
            self.assertEqual(sdk.retrieval.settings().embedding.provider, "openrouter")
            cloud.assert_not_called()

    def test_cli_respects_text_and_json_for_settings_configure_and_catalog(self):
        with TemporaryDirectory() as temporary:
            previous = Path.cwd()
            os.chdir(temporary)
            try:
                for command in ("settings", "configure", "models"):
                    arguments = ["retrieval", command]
                    if command == "configure":
                        arguments += ["--reranker-provider", "local"]
                    with self.subTest(command=command):
                        text, explicit_text, machine = StringIO(), StringIO(), StringIO()
                        with redirect_stdout(text):
                            self.assertEqual(main(arguments), 0)
                        with redirect_stdout(explicit_text):
                            self.assertEqual(main(arguments + ["--format", "text"]), 0)
                        with redirect_stdout(machine):
                            self.assertEqual(main(arguments + ["--format", "json"]), 0)
                        self.assertEqual(text.getvalue(), explicit_text.getvalue())
                        self.assertFalse(text.getvalue().startswith("{"))
                        payload = json.loads(machine.getvalue())
                        if command == "models":
                            self.assertEqual(payload["provider"], "local")
                            self.assertIn(DEFAULT_MODEL_NAME, text.getvalue())
                        else:
                            self.assertEqual(payload, Tarel(Path(temporary) / ".tarel")
                                             .retrieval.settings().to_dict())
                            self.assertIn("Embedding: local /", text.getvalue())
                            if command == "configure":
                                self.assertIn("Reranker: local /", text.getvalue())
                            else:
                                self.assertIn("Reranker: off", text.getvalue())
            finally:
                os.chdir(previous)

    def test_scoped_workspace_search_ignores_excluded_broken_indexes(self):
        for failure in ("index_not_found", "stale_index", "model_index_mismatch"):
            with (
                self.subTest(failure=failure),
                TemporaryDirectory() as temporary,
                patch("tarel.retrieval.remote.load_http_provider_config", return_value=_profile()),
                patch("tarel.application.HTTPEmbedding", return_value=_FakeEmbedding()),
            ):
                sdk = Tarel(temporary, retrieval=RetrievalSettings(
                    ModelChoice("openrouter", "embedding"),
                    ModelChoice("openrouter", "typesafe/jev-1.13"), rerank_depth=2,
                ))
                selected = _retrieval_graph()
                excluded = replace(selected, name="excluded")
                graph_map = {graph.name: graph for graph in (selected, excluded)}
                for graph in graph_map.values():
                    sdk.runtime.graph_store().save(graph)
                sdk.index.build(selected.name)
                if failure == "stale_index":
                    sdk.index.build(excluded.name)
                    changed = replace(excluded, nodes=excluded.nodes[:-1] + (
                        replace(excluded.nodes[-1], annotation=GraphAnnotation(
                            description="Changed excluded metadata.")),
                    ))
                    sdk.runtime.graph_store().save(changed)
                elif failure == "model_index_mismatch":
                    sdk.runtime.retrieval_index().build(
                        excluded, embedder=_FakeEmbedding(), model_path=None,
                        model_sha256="f" * 64, model_id="unrelated-model",
                    )
                fact_id = next(node.id for node in selected.nodes
                               if node.label == "dbo.FactInternetSales")
                reference = f"{selected.name}:{fact_id}"
                workspace = define_system(create_workspace("estate"), "analytics",
                    graph_names=tuple(graph_map), graphs=graph_map)
                workspace = define_area(workspace, "analytics", "sales",
                    schemas=(SchemaReference(selected.name, "dbo"),), graphs=graph_map)
                workspace = define_zone(workspace, "analytics", "sales-slice",
                    object_references=(f"{selected.name}:dbo.FactInternetSales",), graphs=graph_map)
                sdk.runtime.workspace_store().save(workspace)
                sdk.runtime.focus_store().save(_focus("sales-focus", selected, fact_id))
                backend = _FakeEmbedding()
                with (
                    patch("tarel.application.HTTPEmbedding", return_value=backend),
                    patch.object(backend, "embed_query", wraps=backend.embed_query) as embedding,
                    patch("tarel.retrieval.rerank.rerank_remote",
                          side_effect=lambda choice, query, texts: (0.9,) * len(texts)) as reranker,
                ):
                    scopes = (
                        {"graphs": (selected.name,)}, {"areas": ("sales",)},
                        {"schemas": (f"{selected.name}:dbo",)},
                        {"zones": ("sales-slice",)},
                        {"focuses": ("sales-focus",)}, {"scope_objects": (reference,)},
                    )
                    for mode in ("vector", "hybrid"):
                        for scope in scopes:
                            with self.subTest(mode=mode, scope=scope):
                                embedding.reset_mock()
                                hits = sdk.search.workspace("estate", "internet revenue",
                                                            mode=mode, **scope)
                                self.assertTrue(hits.hits)
                                self.assertEqual(hits.graphs, (selected.name,))
                                self.assertTrue(all(hit.source_graph == selected.name
                                                    for hit in hits.hits))
                                embedding.assert_called_once()
                                self.assertTrue(all(text.startswith(
                                    f"System/graph: {selected.name}\n")
                                    for text in reranker.call_args.args[2]))
                    embedding.reset_mock()
                    with self.assertRaises(RetrievalFailure) as error:
                        sdk.search.workspace("estate", "internet revenue", mode="hybrid")
                    self.assertEqual(error.exception.code, failure)
                    embedding.assert_not_called()

    def test_local_reranker_reuses_hash_and_backend_until_model_file_changes(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "ranker.gguf"
            path.write_bytes(b"original model")
            sdk = Tarel(temporary, retrieval=RetrievalSettings(
                reranker=ModelChoice("local", "qwen3-reranker-0.6b-q4-k-m", str(path)),
                rerank_depth=2,
            ))
            graph = _retrieval_graph()
            sdk.runtime.graph_store().save(graph)
            with (
                patch("tarel.retrieval.local.sha256_file", wraps=sha256_file) as hashed,
                patch("tarel.retrieval.rerank.LocalQwenReranker") as factory,
            ):
                factory.return_value.score.return_value = (0.9, 0.1)
                for _ in range(2):
                    self.assertTrue(sdk.search.graph(graph.name, "dbo", mode="bm25").hits)
                self.assertEqual(hashed.call_count, 1)
                factory.assert_called_once()
                replacement = path.with_suffix(".replacement")
                replacement.write_bytes(b"replacement model")
                replacement.replace(path)
                self.assertTrue(sdk.search.graph(graph.name, "dbo", mode="bm25").hits)
                self.assertEqual(hashed.call_count, 2)
                self.assertEqual(factory.call_count, 2)
                self.assertEqual(len(sdk.runtime._rerank_backends), 1)

    def test_explicit_local_choice_does_not_reuse_an_unrelated_recorded_model(self):
        with TemporaryDirectory() as temporary:
            sdk = Tarel(temporary)
            old_model, selected_model = Path(temporary) / "old.gguf", Path(temporary) / "new.gguf"
            old_model.write_bytes(b"old model")
            selected_model.write_bytes(b"selected Qwen model")
            graph = _retrieval_graph()
            sdk.runtime.graph_store().save(graph)
            with patch("tarel.application.LlamaCppEmbedding", return_value=_FakeEmbedding()):
                sdk.index.build(graph.name, model_path=old_model)
                sdk.retrieval.configure(RetrievalSettings())
                with patch("tarel.application.resolve_model_path", return_value=selected_model):
                    self.assertFalse(sdk.index.status(graph.name)["ready"])
                    rebuilt = sdk.index.build(graph.name)
                    self.assertEqual(rebuilt.metadata.model_path, str(selected_model))
                    self.assertEqual(rebuilt.embedded_documents, rebuilt.metadata.document_count)
                    self.assertTrue(sdk.index.status(graph.name)["ready"])

    def test_client_override_cannot_silently_save_unused_settings(self):
        with TemporaryDirectory() as temporary:
            sdk = Tarel(temporary, retrieval=RetrievalSettings())
            with self.assertRaises(RetrievalFailure) as error:
                sdk.retrieval.configure(RetrievalSettings(rerank_depth=20))
            self.assertEqual(error.exception.code, "retrieval_settings_override")
            self.assertFalse((sdk.root / "retrieval.json").exists())

    def test_missing_cloud_index_does_not_call_embedding_provider(self):
        with (
            TemporaryDirectory() as temporary,
            patch("tarel.retrieval.remote.load_http_provider_config", return_value=_profile()),
            patch("tarel.application.HTTPEmbedding") as factory,
        ):
            sdk = Tarel(temporary, retrieval=RetrievalSettings(ModelChoice("openrouter", "model")))
            graph = _retrieval_graph()
            sdk.runtime.graph_store().save(graph)
            with self.assertRaises(RetrievalFailure) as error:
                sdk.search.graph(graph.name, "internet", mode="hybrid")
            self.assertEqual(error.exception.code, "index_not_found")
            factory.return_value.embed_query.assert_not_called()

    def test_local_catalog_separates_embedding_and_reranker(self):
        embedding = list_models()
        reranker = list_models(task="reranker")
        self.assertEqual([row["id"] for row in embedding["models"]], [DEFAULT_MODEL_NAME])
        self.assertEqual(len(reranker["models"]), 1)
        self.assertTrue(reranker["models"][0]["downloadable"])
        with self.assertRaises(RetrievalFailure):
            RetrievalSettings(embedding=ModelChoice(model=reranker["models"][0]["id"]))

    def test_invalid_settings_fail_before_persistence(self):
        for payload in (
            {"api_key": "not-allowed"},
            {"rerank_depth": True},
            {"rerank_depth": 101},
            {"embedding": []},
            {"embedding": {"provider": "../remote", "model": "model"}},
            {"embedding": {"provider": "openrouter", "model": "m", "model_path": "/tmp/m"}},
        ):
            with self.subTest(payload=payload), self.assertRaises(RetrievalFailure):
                RetrievalSettings.from_dict(payload)

    def test_cli_sdk_gui_share_settings_and_do_not_call_models_on_selection(self):
        with (
            TemporaryDirectory() as temporary,
            patch(
                "tarel.retrieval.remote.load_http_provider_config",
                return_value=_profile(),
            ),
            patch("tarel.retrieval.remote.HTTPRetrievalClient.request") as request,
        ):
            previous = Path.cwd()
            os.chdir(temporary)
            try:
                output = StringIO()
                with redirect_stdout(output):
                    code = main(
                        [
                            "retrieval",
                            "configure",
                            "--embedding-provider",
                            "openrouter",
                            "--embedding-model",
                            "perplexity/pplx-embed-v1-4b",
                            "--reranker-provider",
                            "openrouter",
                            "--reranker-model",
                            "typesafe/jev-1.13",
                            "--format",
                            "json",
                        ]
                    )
                sdk = Tarel(Path(temporary) / ".tarel")
                backend = TarelUIBackend(UIConfig(graph="sales"), runtime=sdk.runtime)
                selected = sdk.retrieval.settings()
                gui = backend.read("/api/retrieval/settings")
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output.getvalue()), selected.to_dict())
                self.assertEqual(gui["settings"], selected.to_dict())
                self.assertNotIn("test-key", (sdk.root / "retrieval.json").read_text())
                sdk.retrieval.configure(RetrievalSettings())
                self.assertIsNone(sdk.retrieval.settings().reranker)
                request.assert_not_called()
            finally:
                os.chdir(previous)

    def test_cloud_models_coexist_and_switching_back_reuses_the_local_index(self):
        with (
            TemporaryDirectory() as temporary,
            patch(
                "tarel.retrieval.remote.load_http_provider_config",
                return_value=_profile(),
            ),
            patch("tarel.application.HTTPEmbedding", return_value=_FakeEmbedding()),
        ):
            root = Path(temporary)
            model = root / "model.gguf"
            model.write_bytes(b"test model")
            local = Tarel(root / "state")
            local.retrieval.configure(RetrievalSettings(
                embedding=ModelChoice(model_path=str(model)),
            ))
            graph = _retrieval_graph()
            local.runtime.graph_store().save(graph)
            with patch("tarel.application.LlamaCppEmbedding", return_value=_FakeEmbedding()):
                original = local.index.build(graph.name, model_path=model)
            before = original.path.read_bytes()
            paths = []
            for name in ("perplexity/pplx-embed-v1-4b", "qwen/qwen3-embedding-8b"):
                remote = Tarel(
                    local.root, retrieval=RetrievalSettings(ModelChoice("openrouter", name))
                )
                indexed = remote.index.build(graph.name)
                paths.append(indexed.path)
                self.assertTrue(remote.index.status(graph.name)["ready"])
                again = remote.index.build(graph.name)
                self.assertEqual(again.embedded_documents, 0)
                self.assertEqual(again.reused_documents, indexed.metadata.document_count)
                hits = remote.search.graph(graph.name, "internet revenue", mode="hybrid")
                self.assertTrue(hits.hits)
            self.assertEqual(len(set(paths + [original.path])), 3)
            self.assertEqual(original.path.read_bytes(), before)
            local.retrieval.configure(
                replace(local.retrieval.settings(),
                        reranker=ModelChoice("openrouter", "typesafe/jev-1.13"))
            )
            self.assertEqual(local.runtime.retrieval_index().path(graph.name), original.path)
            self.assertTrue(local.index.status(graph.name, model_path=model)["ready"])

    def test_cloud_updates_embed_only_changed_documents_and_detect_stale_metadata(self):
        with (
            TemporaryDirectory() as temporary,
            patch(
                "tarel.retrieval.remote.load_http_provider_config",
                return_value=_profile(),
            ),
            patch("tarel.application.HTTPEmbedding", return_value=_FakeEmbedding()),
        ):
            sdk = Tarel(
                temporary,
                retrieval=RetrievalSettings(
                    ModelChoice("openrouter", "perplexity/pplx-embed-v1-4b")
                ),
            )
            graph = _retrieval_graph()
            sdk.runtime.graph_store().save(graph)
            sdk.index.build(graph.name)
            changed = replace(
                graph,
                nodes=graph.nodes[:-1]
                + (
                    replace(
                        graph.nodes[-1],
                        annotation=GraphAnnotation(description="Updated helper field."),
                    ),
                ),
            )
            sdk.runtime.graph_store().save(changed)
            self.assertFalse(sdk.index.status(graph.name)["ready"])
            with self.assertRaises(RetrievalFailure) as error:
                sdk.search.graph(graph.name, "internet", mode="hybrid")
            self.assertEqual(error.exception.code, "stale_index")
            result = sdk.index.build(graph.name)
            self.assertGreater(result.embedded_documents, 0)
            self.assertLess(result.embedded_documents, result.metadata.document_count)
            self.assertTrue(sdk.index.status(graph.name)["ready"])

    def test_reranker_orders_only_selected_candidates_and_does_not_change_index_identity(self):
        with TemporaryDirectory() as temporary:
            sdk = Tarel(temporary)
            graph = _retrieval_graph()
            sdk.runtime.graph_store().save(graph)
            original = sdk.search.graph(graph.name, "dbo", mode="bm25", limit=10)
            self.assertGreaterEqual(len(original.hits), 2)
            selected = Tarel(
                temporary,
                retrieval=RetrievalSettings(
                    reranker=ModelChoice("openrouter", "typesafe/jev-1.13"), rerank_depth=2
                ),
            )
            with patch("tarel.retrieval.rerank.rerank_remote", return_value=(0.1, 0.9)) as ranker:
                reranked = rerank_results(original, (graph,), runtime=selected.runtime, limit=10)
                self.assertEqual(reranked.hits[0].id, original.hits[1].id)
                self.assertEqual(reranked.hits[2:], original.hits[2:])
                texts = ranker.call_args.args[2]
                self.assertEqual(len(texts), 2)
                self.assertTrue(all(text.startswith("System/graph:") for text in texts))
            self.assertIsNone(index_namespace(selected.runtime))

    def test_workspace_cloud_query_embedding_is_shared_and_reranking_is_global(self):
        with (
            TemporaryDirectory() as temporary,
            patch(
                "tarel.retrieval.remote.load_http_provider_config",
                return_value=_profile(),
            ),
            patch("tarel.application.HTTPEmbedding", return_value=_FakeEmbedding()) as factory,
        ):
            sdk = Tarel(
                temporary,
                retrieval=RetrievalSettings(
                    ModelChoice("openrouter", "perplexity/pplx-embed-v1-4b"),
                    ModelChoice("openrouter", "typesafe/jev-1.13"),
                    rerank_depth=2,
                ),
            )
            first = _retrieval_graph()
            second = replace(first, name="second")
            for graph in (first, second):
                sdk.runtime.graph_store().save(graph)
                sdk.index.build(graph.name)
            sdk.runtime.workspace_store().save(
                define_system(
                    create_workspace("estate"),
                    "sales",
                    graph_names=(first.name, second.name),
                    graphs={first.name: first, second.name: second},
                )
            )
            backend = _FakeEmbedding()
            with (
                patch("tarel.application.HTTPEmbedding", return_value=backend) as search_factory,
                patch.object(backend, "embed_query", wraps=backend.embed_query) as query_embedding,
                patch("tarel.retrieval.rerank.rerank_remote", return_value=(0.1, 0.9)) as reranker,
            ):
                response = sdk.search.workspace("estate", "internet revenue", mode="hybrid")
                self.assertEqual(query_embedding.call_count, 1)
                self.assertEqual(reranker.call_count, 1)
            self.assertTrue(response.hits)
            self.assertEqual(search_factory.call_count, 1)
            self.assertGreaterEqual(factory.call_count, 2)

    def test_gui_selection_and_update_use_the_selected_cloud_index(self):
        with (
            TemporaryDirectory() as temporary,
            patch(
                "tarel.retrieval.remote.load_http_provider_config",
                return_value=_profile(),
            ),
            patch("tarel.application.HTTPEmbedding", return_value=_FakeEmbedding()),
        ):
            sdk = Tarel(temporary)
            graph = _retrieval_graph()
            sdk.runtime.graph_store().save(graph)
            backend = TarelUIBackend(
                UIConfig(graph=graph.name, model_path=Path("/old/local.gguf")), runtime=sdk.runtime
            )
            settings = RetrievalSettings(ModelChoice("openrouter", "perplexity/pplx-embed-v1-4b"))
            reply = backend.mutate(
                "/api/retrieval/settings", {"settings": settings.to_dict(), "search_mode": "hybrid"}
            )
            self.assertEqual(reply["search_mode"], "hybrid")
            self.assertEqual(backend.read("/api/index/status")["state"], "missing")
            updated = backend.mutate("/api/index/build", {})
            self.assertTrue(updated["status"]["ready"])
            self.assertTrue(backend.mutate("/api/search", {"query": "internet"})["results"]["hits"])

    def test_snapshot_keeps_a_running_request_on_its_original_model(self):
        with TemporaryDirectory() as temporary:
            sdk = Tarel(temporary)
            first = RetrievalSettings(ModelChoice("openrouter", "perplexity/pplx-embed-v1-4b"))
            sdk.retrieval.configure(first)
            captured = snapshot_runtime(sdk.runtime)
            sdk.retrieval.configure(RetrievalSettings())
            self.assertEqual(captured.retrieval_settings, first)
            self.assertEqual(sdk.retrieval.settings(), RetrievalSettings())


class HTTPRetrievalTests(TestCase):
    def test_qwen_cloud_queries_share_the_local_retrieval_instruction(self):
        with patch("tarel.retrieval.remote.load_http_provider_config", return_value=_profile()):
            embedding = HTTPEmbedding(ModelChoice("openrouter", "qwen/qwen3-embedding-8b"))
        with patch.object(embedding.client, "request", return_value={
            "data": [{"index": 0, "embedding": [1, 0]}]
        }) as request:
            embedding.embed_query(" revenue ")
            self.assertTrue(request.call_args.args[1]["input"][0].startswith("Instruct:"))
            self.assertTrue(request.call_args.args[1]["input"][0].endswith("Query: revenue"))
            embedding.embed_documents(("metadata",), batch_size=1)
            self.assertEqual(request.call_args.args[1]["input"], ["metadata"])

    def test_http_errors_are_sanitized_and_redirects_are_disabled(self):
        with patch("tarel.retrieval.remote.load_http_provider_config", return_value=_profile()):
            client = HTTPRetrievalClient("openrouter")
        for status in (302, 401, 429, 503):
            with (
                self.subTest(status=status),
                patch("urllib.request.build_opener") as opener,
                self.assertRaises(RetrievalFailure) as error,
            ):
                opener.return_value.open.side_effect = urllib.error.HTTPError(
                    "https://example.invalid/secret", status, "secret", {}, StringIO("secret")
                )
                client.request("/embeddings", {"model": "model", "input": ["metadata"]})
            self.assertEqual(error.exception.code, "retrieval_provider_failed")
            self.assertNotIn("secret", str(error.exception))
            handler = opener.call_args.args[0]
            self.assertIsNone(handler.redirect_request(None, None, 302, "", {}, "new-url"))

    def test_native_rerank_restores_provider_indexes(self):
        with (
            patch("tarel.retrieval.remote.load_http_provider_config", return_value=_profile()),
            patch("tarel.retrieval.remote.HTTPRetrievalClient.request", return_value={
                "results": [{"index": 1, "relevance_score": 0.9},
                            {"index": 0, "relevance_score": 0.1}]
            }) as request,
        ):
            self.assertEqual(rerank_remote(ModelChoice("openrouter", "native-ranker"),
                                          "revenue", ("cpu", "sales")), (0.1, 0.9))
            self.assertEqual(request.call_args.args[0], "/rerank")
    def test_embedding_restores_row_order_normalizes_and_checks_dimension(self):
        with patch("tarel.retrieval.remote.load_http_provider_config", return_value=_profile()):
            embedding = HTTPEmbedding(ModelChoice("openrouter", "perplexity/pplx-embed-v1-4b"))
        with patch.object(
            embedding.client,
            "request",
            return_value={
                "data": [{"index": 1, "embedding": [0, 2]}, {"index": 0, "embedding": [3, 0]}]
            },
        ) as request:
            self.assertEqual(
                embedding.embed_documents(("first", "second"), batch_size=16),
                ((1.0, 0.0), (0.0, 1.0)),
            )
            self.assertEqual(request.call_args.args[1]["input"], ["first", "second"])
        with patch.object(
            embedding.client,
            "request",
            return_value={"data": [{"index": 0, "embedding": [1, 0, 0]}]},
        ), self.assertRaises(RetrievalFailure):
            embedding.embed_query("query")

    def test_duplicate_indexes_and_invalid_vectors_fail(self):
        with self.assertRaises(RetrievalFailure):
            indexed_rows({"data": [{"index": 0}, {"index": 0}]}, "data", 2)
        with patch("tarel.retrieval.remote.load_http_provider_config", return_value=_profile()):
            embedding = HTTPEmbedding(ModelChoice("openrouter", "perplexity/pplx-embed-v1-4b"))
        for vector in ([0, 0], [float("nan"), 1], [True, 1], [10**400, 1]):
            with (
                self.subTest(vector=vector),
                patch.object(
                    embedding.client,
                    "request",
                    return_value={"data": [{"index": 0, "embedding": vector}]},
                ),
                self.assertRaises(RetrievalFailure),
            ):
                embedding.embed_query("query")

    def test_jev_uses_typed_decisions_and_rejects_generated_or_invalid_answers(self):
        choice = ModelChoice("openrouter", "typesafe/jev-1.13")
        with patch("tarel.retrieval.remote.load_http_provider_config", return_value=_profile()):
            with patch(
                "tarel.retrieval.remote.HTTPRetrievalClient.request",
                return_value={"answers": {"relevance": {"type": "noul", "noul": 0.9}}},
            ) as request:
                self.assertEqual(rerank_remote(choice, "revenue", ("sales",)), (0.9,))
                self.assertEqual(request.call_args.args[0], "/alpha/decisions")
                self.assertNotIn("messages", request.call_args.args[1])
            for answer in (
                {"type": "text", "noul": 0.9},
                {"type": "noul", "noul": True},
                {"type": "noul", "noul": float("inf")},
                {"type": "noul", "noul": 1.2},
            ):
                with (
                    patch(
                        "tarel.retrieval.remote.HTTPRetrievalClient.request",
                        return_value={"answers": {"relevance": answer}},
                    ),
                    self.assertRaises(RetrievalFailure),
                ):
                    rerank_remote(choice, "revenue", ("sales",))


class LocalRerankerTests(TestCase):
    def test_reads_only_final_native_logits_and_bounds_long_documents(self):
        class FakeLlama:
            ctx = object()

            def __init__(self, **kwargs):
                self.arguments = kwargs
                self.evaluations = []

            def tokenize(self, value, **kwargs):
                if value == b"no":
                    return [0]
                if value == b"yes":
                    return [1]
                return [2] * len(value)

            def reset(self):
                pass

            def eval(self, tokens):
                self.evaluations.append(tokens)

            @property
            def scores(self):
                raise AssertionError("The unused Python scores buffer must not be read.")

        calls = []

        def logits(context, row):
            calls.append((context, row))
            return [0.0, 2.0]

        module = SimpleNamespace(Llama=FakeLlama, llama_get_logits_ith=logits)
        with patch.dict("sys.modules", {"llama_cpp": module}):
            ranker = LocalQwenReranker(Path("model.gguf"), n_threads=4)
            scores = ranker.score("revenue", ("x" * 10_000,))
        self.assertGreater(scores[0], 0.8)
        self.assertEqual(calls, [(ranker.model.ctx, -1)])
        self.assertEqual(len(ranker.model.evaluations[0]), 4096)
        self.assertFalse(ranker.model.arguments["logits_all"])
        self.assertEqual(ranker.model.arguments["n_gpu_layers"], 0)
