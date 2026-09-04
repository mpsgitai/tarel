from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.graph.contracts import GraphAnnotation, GraphDocument, GraphEdge, GraphFailure, GraphNode
from tarel.graph.revision import graph_revision, physical_graph_revision, physical_schema_revision
from tarel.graph.store import FileGraphStore


class LazyGraphStoreTests(TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = FileGraphStore(Path(self.temporary.name) / "graphs")
        self.graph = _graph()
        self.source = self.store.save(self.graph)

    def _assert_failure(self, code: str, action) -> None:
        with self.assertRaises(GraphFailure) as failure:
            action()
        self.assertEqual(failure.exception.code, code)

    def test_legacy_json_bootstrap_reports_full_read_and_preserves_source_bytes(self) -> None:
        before = self.source.read_bytes()
        with patch.object(self.store, "load", wraps=self.store.load) as load:
            header = self.store.header("demo")
        self.assertEqual(load.call_count, 1)
        self.assertEqual(header.revision, graph_revision(self.graph))
        self.assertEqual(header.physical_revision, physical_graph_revision(self.graph))
        self.assertEqual(header.object_count, 3)
        self.assertEqual(header.read_stats.mode, "cache_built")
        self.assertTrue(header.read_stats.full_document_read)
        self.assertEqual(header.read_stats.loaded_node_count, len(self.graph.nodes))
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.store.list(), ("demo",))
        self.assertEqual(self.store.load("demo"), self.graph)

    def test_warm_reads_never_read_json_or_deserialize_a_complete_graph(self) -> None:
        self.store.header("demo")
        original_read = Path.read_text

        def guarded_read(path, *args, **kwargs):
            self.assertNotEqual(path, self.source)
            return original_read(path, *args, **kwargs)

        with (
            patch.object(Path, "read_text", guarded_read),
            patch.object(self.store, "load", side_effect=AssertionError("whole graph load")),
            patch.object(
                GraphDocument, "from_dict", side_effect=AssertionError("whole graph parse")
            ),
        ):
            header = self.store.header("demo")
            page = self.store.list_objects("demo", limit=1)
            selected = self.store.read_slice("demo", ("a",), expected_revision=header.revision)
        self.assertEqual(header.read_stats.mode, "warm")
        self.assertFalse(selected.header.read_stats.full_document_read)
        self.assertEqual(page.header.read_stats.loaded_node_count, 1)
        self.assertEqual(selected.header.read_stats.loaded_node_count, 5)

    def test_slice_has_real_endpoint_closure_no_neighbours_or_fabricated_edges(self) -> None:
        selected = self.store.read_slice("demo", ("a",))
        self.assertEqual(
            {node.id for node in selected.graph.nodes}, {"catalog", "sales", "a", "aid", "av"}
        )
        self.assertEqual(
            {edge.id for edge in selected.graph.edges},
            {"c-sales", "sales-a", "a-id", "a-v"},
        )
        known = selected.graph.node_by_id()
        self.assertTrue(
            all(
                edge.source_id in known and edge.target_id in known for edge in selected.graph.edges
            )
        )
        self.assertNotEqual(graph_revision(selected.graph), selected.header.revision)
        self.assertEqual(selected.header.revision, graph_revision(self.graph))
        self.assertEqual(GraphDocument.from_dict(selected.graph.to_dict()), selected.graph)
        self.assertEqual(selected.to_dict()["source"]["revision"], graph_revision(self.graph))

    def test_selected_join_endpoints_preserve_actual_foreign_key_edges(self) -> None:
        selected = self.store.read_slice("demo", ("a", "b"))
        self.assertIn("fk", {edge.id for edge in selected.graph.edges})
        self.assertIn("fk-field", {edge.id for edge in selected.graph.edges})
        self.assertNotIn("z", selected.graph.node_by_id())

    def test_namespace_and_exact_id_selection_are_enforced_before_projection(self) -> None:
        for ids, namespace in ((("z",), "sales"), (("missing",), None), (("aid",), None)):
            with self.subTest(ids=ids, namespace=namespace):
                self._assert_failure(
                    "graph_object_not_found",
                    lambda ids=ids, namespace=namespace: self.store.read_slice(
                        "demo",
                        ids,
                        namespace=namespace,
                    ),
                )
        page = self.store.list_objects("demo", namespace="sales", object_ids=("a", "z"))
        self.assertEqual(tuple(node.id for node in page.objects), ("a",))
        self.assertEqual(page.total_objects, 1)
        self.assertEqual(self.store.read_slice("demo", ()).graph.nodes, ())

    def test_pagination_is_deterministic_revision_bound_and_bounded(self) -> None:
        header = self.store.header("demo")
        first = self.store.list_objects("demo", limit=1, expected_revision=header.revision)
        second = self.store.list_objects("demo", offset=first.next_offset, limit=2)
        self.assertEqual(tuple(node.id for node in first.objects + second.objects), ("a", "b", "z"))
        self.assertIsNone(second.next_offset)
        self.assertEqual(first.total_objects, 3)
        self.assertEqual(self.store.list_objects("demo", offset=9).objects, ())
        for kwargs in ({"limit": 1001}, {"limit": True}, {"offset": -1}, {"offset": "0"}):
            self._assert_failure(
                "invalid_graph_page",
                lambda kwargs=kwargs: self.store.list_objects("demo", **kwargs),
            )
        for ids in (("a", "a"), ["a"], (None,), ([],), None):
            self._assert_failure(
                "invalid_graph_selection", lambda ids=ids: self.store.read_slice("demo", ids)
            )
        self._assert_failure(
            "invalid_graph_selection", lambda: self.store.list_objects("demo", namespace=1)
        )
        self._assert_failure(
            "graph_revision_mismatch",
            lambda: self.store.list_objects(
                "demo",
                expected_revision="0" * 64,
            ),
        )

    def test_annotations_invalidate_full_revision_but_not_physical_revision(self) -> None:
        before = self.store.header("demo")
        changed = replace(
            self.graph,
            nodes=tuple(
                replace(node, annotation=GraphAnnotation("Reviewed table.", state="validated"))
                if node.id == "a"
                else node
                for node in self.graph.nodes
            ),
        )
        self.store.save(changed)
        after = self.store.header("demo")
        self.assertEqual(after.read_stats.mode, "cache_rebuilt")
        self.assertNotEqual(after.revision, before.revision)
        self.assertEqual(after.physical_revision, before.physical_revision)
        selected = self.store.read_slice("demo", ("a",), expected_revision=after.revision)
        self.assertEqual(selected.graph.node_by_id()["a"].annotation.description, "Reviewed table.")
        self._assert_failure(
            "graph_revision_mismatch",
            lambda: self.store.read_slice(
                "demo",
                ("a",),
                expected_revision=before.revision,
            ),
        )

    def test_schema_hashes_validate_every_member_without_hydrating_fields(self) -> None:
        graph = replace(
            self.graph,
            nodes=tuple(
                replace(node, metadata={**node.metadata, "nullable": False})
                if node.type == "field"
                else node
                for node in self.graph.nodes
            ),
        )
        self.store.save(graph)
        header = self.store.header("demo")
        with (
            patch.object(self.store, "load", side_effect=AssertionError("whole graph")),
            patch.object(GraphNode, "from_dict", side_effect=AssertionError("field hydration")),
        ):
            result = self.store.object_schema_hashes(
                "demo",
                ("a", "b", "z"),
                expected_revision=header.revision,
            )
        hashes = dict(result.hashes)
        self.assertEqual(
            hashes["a"], physical_schema_revision((("id", "int", False), ("amount", "int", False)))
        )
        self.assertNotEqual(hashes["a"], hashes["b"])
        self.assertIsNone(hashes["z"])
        self.assertEqual(result.header.read_stats.loaded_node_count, 0)
        self.assertEqual(result.header.read_stats.mode, "warm")
        self._assert_failure(
            "graph_object_not_found", lambda: self.store.object_schema_hashes("demo", ("missing",))
        )
        self._assert_failure(
            "graph_revision_mismatch",
            lambda: self.store.object_schema_hashes(
                "demo",
                ("a",),
                expected_revision="0" * 64,
            ),
        )

    def test_out_of_band_same_size_source_edit_with_restored_mtime_cannot_serve_stale_rows(
        self,
    ) -> None:
        old = self.store.header("demo")
        stamp = self.source.stat()
        payload = self.source.read_text(encoding="utf-8")
        self.source.write_text(payload.replace("sales.a", "sales.x"), encoding="utf-8")
        os.utime(self.source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        current = self.store.header("demo")
        self.assertNotEqual(current.revision, old.revision)
        self.assertEqual(current.read_stats.mode, "cache_rebuilt")
        self.assertEqual(
            self.store.list_objects("demo", object_ids=("a",)).objects[0].label, "sales.x"
        )

    def test_modified_sqlite_cache_fails_closed_and_explicit_rebuild_recovers(self) -> None:
        expected = self.store.header("demo")
        cache = self.source.with_name("graph.selective.sqlite")
        with sqlite3.connect(cache) as connection:
            connection.execute("DELETE FROM nodes WHERE id='a'")
        self._assert_failure("invalid_graph_cache", lambda: self.store.header("demo"))
        rebuilt = self.store.rebuild_index("demo")
        self.assertEqual(rebuilt.revision, expected.revision)
        self.assertEqual(rebuilt.read_stats.mode, "cache_rebuilt")
        self.assertEqual(self.store.list_objects("demo").total_objects, 3)

    def test_corrupt_or_missing_cache_never_silently_becomes_empty_success(self) -> None:
        self.store.header("demo")
        cache = self.source.with_name("graph.selective.sqlite")
        cache.write_bytes(b"not sqlite")
        self._assert_failure("invalid_graph_cache", lambda: self.store.list_objects("demo"))
        self.store.rebuild_index("demo")
        cache.unlink()
        self._assert_failure("invalid_graph_cache", lambda: self.store.header("demo"))
        self.store.rebuild_index("demo")
        descriptor = self.source.with_name("graph.selective.json")
        descriptor.write_text("{}", encoding="utf-8")
        self._assert_failure("invalid_graph_cache", lambda: self.store.header("demo"))

    def test_source_corruption_or_deletion_never_falls_back_to_existing_cache(self) -> None:
        self.store.header("demo")
        self.source.write_text("invalid json", encoding="utf-8")
        self._assert_failure("invalid_graph", lambda: self.store.header("demo"))
        self.source.unlink()
        self._assert_failure("graph_not_found", lambda: self.store.header("demo"))

    def test_concurrent_source_save_during_warm_read_is_visible_not_a_mixed_snapshot(self) -> None:
        self.store.header("demo")
        original = GraphNode.from_dict
        mutated = False

        def during_read(data):
            nonlocal mutated
            if not mutated:
                mutated = True
                self.store.save(replace(self.graph, catalog="changed"))
            return original(data)

        with patch.object(GraphNode, "from_dict", side_effect=during_read):
            self._assert_failure(
                "graph_changed_during_read", lambda: self.store.read_slice("demo", ("a",))
            )

    def test_concurrent_source_save_during_bootstrap_does_not_publish_old_cache(self) -> None:
        original = self.store.load

        def during_load(name):
            graph = original(name)
            self.store.save(replace(graph, catalog="changed"))
            return graph

        with patch.object(self.store, "load", side_effect=during_load):
            self._assert_failure("graph_changed_during_read", lambda: self.store.header("demo"))
        self.assertFalse(self.source.with_name("graph.selective.sqlite").exists())

    def test_concurrent_cache_replacement_fails_closed(self) -> None:
        self.store.header("demo")
        original = GraphNode.from_dict
        mutated = False

        def during_read(data):
            nonlocal mutated
            if not mutated:
                mutated = True
                cache = self.source.with_name("graph.selective.sqlite")
                stamp = cache.stat()
                os.utime(cache, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000_000))
            return original(data)

        with patch.object(GraphNode, "from_dict", side_effect=during_read):
            self._assert_failure(
                "graph_cache_changed_during_read", lambda: self.store.list_objects("demo")
            )

    def test_thousands_of_members_only_hydrate_requested_metadata(self) -> None:
        graph = _large_graph(2000)
        self.store.save(graph)
        self.store.header("large")
        with (
            patch.object(self.store, "load", side_effect=AssertionError("whole graph")),
            patch.object(GraphNode, "from_dict", wraps=GraphNode.from_dict) as nodes,
        ):
            page = self.store.list_objects("large", offset=100, limit=10)
            selected = self.store.read_slice("large", (page.objects[0].id,))
        self.assertEqual(page.total_objects, 2000)
        self.assertEqual(nodes.call_count, 18)
        self.assertEqual(selected.header.read_stats.loaded_node_count, 8)
        self.assertLess(len(json.dumps(page.to_dict())), 8000)
        self.assertLess(len(json.dumps(selected.to_dict())), 10000)


def _graph() -> GraphDocument:
    nodes = (
        GraphNode("catalog", "catalog", "demo", {}),
        GraphNode("sales", "namespace", "sales", {}),
        GraphNode("private", "namespace", "private", {}),
        GraphNode("a", "table", "sales.a", {"namespace": "sales", "name": "a"}),
        GraphNode("aid", "field", "id", {"object_id": "a", "data_type": "int"}),
        GraphNode("av", "field", "amount", {"object_id": "a", "data_type": "int"}),
        GraphNode("b", "table", "sales.b", {"namespace": "sales", "name": "b"}),
        GraphNode("bid", "field", "id", {"object_id": "b", "data_type": "int"}),
        GraphNode("z", "view", "private.z", {"namespace": "private", "name": "z"}),
    )
    edges = tuple(
        GraphEdge(key, source, target, "contains")
        for key, source, target in (
            ("c-sales", "catalog", "sales"),
            ("c-private", "catalog", "private"),
            ("sales-a", "sales", "a"),
            ("sales-b", "sales", "b"),
            ("a-id", "a", "aid"),
            ("a-v", "a", "av"),
            ("b-id", "b", "bid"),
            ("private-z", "private", "z"),
        )
    ) + (
        GraphEdge("fk", "a", "b", "foreign_key"),
        GraphEdge("fk-field", "aid", "bid", "foreign_key_field"),
    )
    return GraphDocument("demo", "test", "sql", "demo", "sqlite", nodes, edges)


def _large_graph(count: int) -> GraphDocument:
    nodes = [GraphNode("c", "catalog", "large", {}), GraphNode("n", "namespace", "prices", {})]
    edges = [GraphEdge("c-n", "c", "n", "contains")]
    for number in range(count):
        object_id = f"prices_{number:05d}"
        nodes.append(GraphNode(object_id, "table", object_id, {"namespace": "prices"}))
        edges.append(GraphEdge(f"n-{object_id}", "n", object_id, "contains"))
        for index in range(5):
            field_id = f"{object_id}.{index}"
            nodes.append(GraphNode(field_id, "field", f"value_{index}", {"object_id": object_id}))
            edges.append(GraphEdge(f"e-{field_id}", object_id, field_id, "contains"))
    return GraphDocument("large", "test", "sql", "large", "sqlite", tuple(nodes), tuple(edges))
