from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from unittest import TestCase
from unittest.mock import patch

from test_packages import (
    _graph_payload,
    _read_package_members,
    _workspace_payload,
    _write_json,
    _write_package_members,
)

from tarel.cli import main
from tarel.knowledge.contracts import KnowledgeDocument, KnowledgeScope
from tarel.lineage.contracts import LineageDocument
from tarel.packages.application import (
    PackageFailure,
    pack_workspace,
    plan_workspace,
    unpack_package,
    verify_package,
)
from tarel.packages.contracts import canonical_json, sha256
from tarel.runtime import TarelRuntime


class PackageSelectionTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.runtime = TarelRuntime.local(self.state)
        _write_json(self.state / "graphs/sales/graph.json", _graph_payload())
        other = {**_graph_payload(), "name": "inventory"}
        _write_json(self.state / "graphs/inventory/graph.json", other)
        _write_json(self.state / "workspaces/team/workspace.json", _workspace_payload())
        for name, scope in (
            ("sales-terms", KnowledgeScope.parse("graph:sales")),
            ("inventory-terms", KnowledgeScope.parse("graph:inventory")),
            ("global-terms", KnowledgeScope.parse("global")),
        ):
            self.runtime.knowledge_store().save(
                KnowledgeDocument(name, name, scope, "Synthetic terms.", "fixture.txt")
            )
        self.runtime.lineage_store().save(
            LineageDocument(
                name="sales-job",
                source_kind="json",
                source_name="fixture",
                source_reference="synthetic",
                source_revision="1" * 64,
                workflow_id="workflow",
                workflow_name="Fixture",
                definitions=(),
                steps=(),
            )
        )

    def test_default_scope_excludes_foreign_and_global_knowledge_and_unassigned_lineage(self):
        output = self.root / "team.tarel"
        pack_workspace(self.state, "team", output)
        members = _read_package_members(output)
        self.assertIn("knowledge/sales-terms/document.json", members)
        self.assertNotIn("knowledge/inventory-terms/document.json", members)
        self.assertNotIn("knowledge/global-terms/document.json", members)
        self.assertNotIn("lineage/sales-job/lineage.json", members)

    def test_explicit_auxiliaries_and_plan_match_export_bytes_and_round_trip(self):
        options = dict(lineage_names=("sales-job",), knowledge_ids=("global-terms",))
        plan = plan_workspace(self.state, "team", **options)
        output = self.root / "team.tarel"
        pack_workspace(self.state, "team", output, **options)
        members = _read_package_members(output)
        manifest = json.loads(members["manifest.json"])
        self.assertEqual(manifest["entries"], [entry.to_dict() for entry in plan.entries])
        self.assertIn("knowledge/global-terms/document.json", members)
        self.assertIn("lineage/sales-job/lineage.json", members)
        imported = self.root / "imported"
        unpack_package(output, imported)
        for entry in plan.entries:
            self.assertEqual(
                (imported / entry.path).read_bytes(), (self.state / entry.path).read_bytes()
            )

    def test_cli_plan_and_pack_share_explicit_selection(self):
        output = self.root / "team.tarel"
        options = [
            "--state",
            str(self.state),
            "--workspace",
            "team",
            "--lineage",
            "sales-job",
            "--knowledge",
            "global-terms",
            "--format",
            "json",
        ]
        stdout = StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(main(["package", "plan", *options]), 0)
        plan = json.loads(stdout.getvalue())
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["package", "pack", *options, "--output", str(output)]), 0)
        self.assertEqual(
            json.loads(_read_package_members(output)["manifest.json"])["entries"], plan["entries"]
        )

    def test_schema_object_and_system_knowledge_are_scoped_to_actual_workspace_members(self):
        from tarel.connectors.contracts import CatalogField, CatalogObject, CatalogResult
        from tarel.graph.build import build_graph_from_catalog

        graph = build_graph_from_catalog(
            "sales",
            CatalogResult(
                connector="fixture",
                source_type="database",
                catalog="Demo",
                dialect="ansi",
                objects=(
                    CatalogObject(
                        namespace="main",
                        name="Orders",
                        kind="table",
                        fields=(CatalogField("id", 1, "integer", False),),
                    ),
                ),
            ),
        )
        self.runtime.graph_store().save(graph)
        scopes = {
            "schema-match": KnowledgeScope.parse("schema:sales:main"),
            "schema-other": KnowledgeScope.parse("schema:sales:private"),
            "object-match": KnowledgeScope.parse("object:sales:main.Orders"),
            "object-other": KnowledgeScope.parse("object:sales:main.Missing"),
            "system-match": KnowledgeScope("system", "sales-system", workspace="team"),
            "system-other-workspace": KnowledgeScope("system", "sales-system", workspace="other"),
            "system-other-name": KnowledgeScope("system", "other", workspace="team"),
        }
        for name, scope in scopes.items():
            self.runtime.knowledge_store().save(
                KnowledgeDocument(name, name, scope, "Synthetic scoped terms.", "fixture.txt")
            )
        names = {
            entry.name
            for entry in plan_workspace(self.state, "team").entries
            if entry.kind == "knowledge"
        }
        self.assertEqual(names, {"sales-terms", "schema-match", "object-match", "system-match"})

    def test_repeated_explicit_names_are_deduplicated(self):
        plan = plan_workspace(
            self.state,
            "team",
            lineage_names=("sales-job", "sales-job"),
            knowledge_ids=("global-terms", "global-terms"),
        )
        paths = [entry.path for entry in plan.entries]
        self.assertEqual(len(paths), len(set(paths)))

    def test_explicit_foreign_document_is_an_intentional_override(self):
        plan = plan_workspace(self.state, "team", knowledge_ids=("inventory-terms",))
        self.assertIn("knowledge/inventory-terms/document.json", [e.path for e in plan.entries])

    def test_missing_explicit_auxiliary_fails_without_creating_package(self):
        for options in (dict(lineage_names=("missing",)), dict(knowledge_ids=("missing",))):
            with self.subTest(options=options), self.assertRaises(PackageFailure):
                pack_workspace(self.state, "team", self.root / "absent.tarel", **options)
            self.assertFalse((self.root / "absent.tarel").exists())
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_auxiliary_paths_cannot_escape_state(self):
        for options in (dict(lineage_names=("../outside",)), dict(knowledge_ids=("../outside",))):
            with self.subTest(options=options), self.assertRaises(PackageFailure):
                plan_workspace(self.state, "team", **options)

    def test_legacy_v01_packages_remain_verifiable_and_unpackable(self):
        output = self.root / "current.tarel"
        pack_workspace(self.state, "team", output)
        members = _read_package_members(output)
        manifest = json.loads(members["manifest.json"])
        manifest["contract_version"] = "tarel.package.v0.1"
        manifest["selection"]["auxiliary_scope"] = "all lineage and knowledge; compatible focuses"
        unsigned = {k: v for k, v in manifest.items() if k != "package_revision"}
        manifest["package_revision"] = sha256(canonical_json(unsigned))
        members["manifest.json"] = json.dumps(manifest).encode()
        legacy = self.root / "legacy.tarel"
        _write_package_members(legacy, members)
        self.assertTrue(verify_package(legacy).verified)
        unpack_package(legacy, self.root / "legacy-imported")

    def test_competing_no_replace_exports_have_one_winner(self):
        output = self.root / "team.tarel"
        ready = Barrier(2)
        original_verify = verify_package

        def verify_then_wait(path):
            result = original_verify(path)
            ready.wait(timeout=5)
            return result

        def publish():
            try:
                return pack_workspace(self.state, "team", output)
            except PackageFailure as failure:
                return failure

        with (
            patch("tarel.packages.application.verify_package", side_effect=verify_then_wait),
            ThreadPoolExecutor(2) as pool,
        ):
            outcomes = list(pool.map(lambda _n: publish(), range(2)))
        failures = [x for x in outcomes if isinstance(x, PackageFailure)]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].code, "package_exists")
        self.assertTrue(verify_package(output).verified)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_existing_output_is_untouched_and_failed_replace_preserves_previous_package(self):
        output = self.root / "team.tarel"
        pack_workspace(self.state, "team", output)
        before = output.read_bytes()
        with self.assertRaises(PackageFailure):
            pack_workspace(self.state, "team", output)
        graph = self.state / "graphs/sales/graph.json"
        graph.write_text("not json")
        with self.assertRaises(PackageFailure):
            pack_workspace(self.state, "team", output, replace=True)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_graph_and_knowledge_changes_during_compression_do_not_mix_snapshot(self):
        output = self.root / "team.tarel"
        graph_path = self.state / "graphs/sales/graph.json"
        knowledge_path = self.state / "knowledge/sales-terms/document.json"
        before_graph, before_knowledge = graph_path.read_bytes(), knowledge_path.read_bytes()
        from tarel.packages.application import write_document

        changed = False

        def write_after_change(archive, name, data):
            nonlocal changed
            if not changed:
                changed = True
                store = self.runtime.graph_store()
                store.save(replace(store.load("sales"), catalog="changed"))
                store = self.runtime.knowledge_store()
                store.save(
                    replace(store.load("sales-terms"), content="Changed during compression.")
                )
            return write_document(archive, name, data)

        with patch("tarel.packages.application.write_document", side_effect=write_after_change):
            pack_workspace(self.state, "team", output)
        members = _read_package_members(output)
        self.assertEqual(members["graphs/sales/graph.json"], before_graph)
        self.assertEqual(members["knowledge/sales-terms/document.json"], before_knowledge)
        self.assertNotEqual(graph_path.read_bytes(), before_graph)
        self.assertNotEqual(knowledge_path.read_bytes(), before_knowledge)

    def test_snapshot_blocks_publication_until_all_bytes_are_captured(self):
        output = self.root / "team.tarel"
        path = self.state / "knowledge/sales-terms/document.json"
        before = path.read_bytes()
        started, finished = Event(), Event()
        from tarel.packages.application import _read_source_document

        scheduled = False

        def publish():
            started.set()
            store = self.runtime.knowledge_store()
            store.save(replace(store.load("sales-terms"), content="Updated concurrently."))
            finished.set()

        with ThreadPoolExecutor(1) as pool:
            future = None

            def read_during_write(source):
                nonlocal scheduled, future
                if not scheduled:
                    scheduled = True
                    future = pool.submit(publish)
                    self.assertTrue(started.wait(5))
                    self.assertFalse(finished.wait(0.05))
                return _read_source_document(source)

            with patch(
                "tarel.packages.application._read_source_document", side_effect=read_during_write
            ):
                pack_workspace(self.state, "team", output)
            future.result(timeout=5)
        self.assertEqual(
            _read_package_members(output)["knowledge/sales-terms/document.json"], before
        )
        self.assertNotEqual(path.read_bytes(), before)

    def test_failed_pack_cleans_temporary_snapshot_and_unpublished_archive(self):
        snapshots = self.root / "snapshots"
        snapshots.mkdir()
        (self.state / "graphs/sales/graph.json").write_text("invalid JSON")
        original_directory = TemporaryDirectory

        def snapshot_directory(*args, **kwargs):
            return original_directory(*args, dir=snapshots, **kwargs)

        with (
            patch("tarel.packages.application.tempfile.TemporaryDirectory", snapshot_directory),
            self.assertRaises(PackageFailure),
        ):
            pack_workspace(self.state, "team", self.root / "failed.tarel")
        self.assertEqual(list(snapshots.iterdir()), [])
        self.assertFalse((self.root / "failed.tarel").exists())
        self.assertEqual(list(self.root.glob("*.tmp")), [])
