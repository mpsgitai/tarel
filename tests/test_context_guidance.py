from __future__ import annotations

import json
from contextlib import redirect_stdout
from copy import deepcopy
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from test_context import _context_graph

from tarel.cli import main
from tarel.context import (
    ContextFailure,
    compile_context,
    compile_context_from_objects,
    compile_context_prefix,
)
from tarel.context_guidance import context_brief, context_delta
from tarel.context_output import ContextScope, canonical_hash
from tarel.context_packets import context_packet_from_dict, load_context_packet
from tarel.graph.contracts import GraphAnnotation
from tarel.graph.store import FileGraphStore
from tarel.sdk import Tarel


class ContextGuidanceTests(TestCase):
    def test_brief_reports_scope_size_coverage_gaps_and_continuity(self) -> None:
        packet = compile_context(
            _context_graph(include_geography_fk=True),
            "sales city",
            namespace="sales",
            seed_limit=1,
            max_objects=3,
            max_fields_per_object=1,
        )

        brief = context_brief(packet)
        payload = brief.to_dict()

        self.assertEqual(payload["view_version"], "tarel.context-brief.v0.1")
        self.assertEqual(brief.graphs, ("context_demo",))
        self.assertIn("schema=sales", brief.scope)
        self.assertEqual(brief.object_count, 3)
        self.assertEqual(brief.field_count, 3)
        self.assertEqual(brief.focus, ("city", "sale"))
        self.assertEqual(payload["continuity"]["packet_hash"], packet.packet_hash)
        self.assertEqual(brief.continuity.object_ids, brief.object_ids)
        self.assertTrue(any(gap.code == "missing_object_semantics" for gap in brief.gaps))
        self.assertTrue(any(gap.code == "context_budget_omissions" for gap in brief.gaps))
        self.assertEqual(brief.gaps[0].code, "context_budget_omissions")
        self.assertEqual(len(brief.text().splitlines()), 6)
        self.assertIn("object semantics", brief.text())

    def test_brief_uses_workspace_scope_and_preserves_warnings(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)
        packet = replace(
            packet,
            scope=ContextScope(
                mode="workspace_retrieval",
                workspace="enterprise",
                systems=("adventure", "worldwide"),
                graphs=("context_demo",),
                objects=("context_demo:sales.FactSales",),
                warnings=("Focus traversal reached its boundary.",),
            ),
        )

        brief = context_brief(packet)

        self.assertIn("enterprise", brief.scope)
        self.assertIn("graphs=context_demo", brief.scope)
        self.assertIn("systems=adventure, worldwide", brief.scope)
        self.assertIn("objects=context_demo:sales.FactSales", brief.scope)
        warning = next(gap for gap in brief.gaps if gap.code == "scope_warnings")
        self.assertEqual(warning.category, "scope")
        self.assertEqual(warning.references, ("Focus traversal reached its boundary.",))

    def test_query_independent_prefix_does_not_invent_a_focus(self) -> None:
        packet = compile_context_prefix(_context_graph(), max_objects=10)

        brief = context_brief(packet)

        self.assertEqual(brief.focus, ())
        self.assertIn("Focus: query-independent", brief.text())

    def test_prefix_uses_explicit_focus_selectors_for_orientation(self) -> None:
        packet = replace(
            compile_context_prefix(_context_graph(), max_objects=10),
            scope=ContextScope(mode="graph_scope_prefix", focuses=("revenue",)),
        )

        brief = context_brief(packet)

        self.assertEqual(brief.focus, ("revenue",))

    def test_missing_field_references_include_the_owning_object(self) -> None:
        packet = compile_context(
            _context_graph(include_geography_fk=True),
            "sales city",
            seed_limit=1,
            max_objects=3,
            max_fields_per_object=2,
        )

        gap = next(
            item for item in context_brief(packet).gaps
            if item.code == "missing_field_semantics"
        )

        self.assertIn("sales.FactSales.CustomerKey", gap.references)
        self.assertIn("sales.DimCustomer.CustomerKey", gap.references)

        previous = packet.to_dict()
        current = deepcopy(previous)
        _describe_field(previous, "sales.FactSales", "CustomerKey")
        _describe_field(current, "sales.DimCustomer", "CustomerKey")
        _refresh_identity(previous)
        _refresh_identity(current)
        change = next(
            item for item in context_delta(previous, current).gaps_changed
            if item.code == "missing_field_semantics"
        )
        self.assertEqual(change.before, change.after)
        self.assertTrue(change.evidence_changed)

    def test_parallel_join_deltas_include_their_field_pairs(self) -> None:
        packet = compile_context(
            _context_graph(include_geography_fk=True),
            "sales city",
            seed_limit=1,
            max_objects=3,
        )
        previous = packet.to_dict()
        current = deepcopy(previous)
        join = current["stable"]["joins"][0]
        previous_from_field = join["from_fields"][0]
        join["id"] = f"{join['id']}::parallel"
        join["from_fields"] = ["SalesAmount"]
        join["to_fields"] = ["CustomerName"]
        _refresh_identity(current)

        delta = context_delta(previous, current)

        self.assertEqual(len(delta.joins_added), 1)
        self.assertEqual(len(delta.joins_removed), 1)
        self.assertNotEqual(delta.joins_added, delta.joins_removed)
        self.assertIn("(SalesAmount)", delta.joins_added[0])
        self.assertIn(f"({previous_from_field})", delta.joins_removed[0])

    def test_delta_reports_added_fields_gap_improvement_and_cache_change(self) -> None:
        graph = _context_graph()
        previous = compile_context(
            graph, "sales", seed_limit=1, max_objects=1, max_fields_per_object=1,
        )
        current = compile_context(
            graph, "sales amount", seed_limit=1, max_objects=1, max_fields_per_object=3,
        )

        delta = context_delta(previous, current)

        self.assertEqual(delta.to_dict()["view_version"], "tarel.context-delta.v0.1")
        self.assertEqual(delta.objects_preserved, 1)
        self.assertEqual(delta.objects_added, ())
        self.assertGreaterEqual(len(delta.fields_added), 1)
        self.assertTrue(delta.query_changed)
        self.assertFalse(delta.stable_prefix_reusable)
        self.assertTrue(any(item.code == "missing_field_semantics" for item in delta.gaps_changed))
        self.assertIn("Kept: 1 object", delta.text())

    def test_delta_reports_changed_gap_evidence_when_count_is_unchanged(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)
        previous = replace(
            packet,
            scope=ContextScope(
                mode="retrieval",
                workspace="enterprise",
                scope_hash="a" * 64,
                warnings=("Old boundary warning.",),
            ),
        )
        current = replace(
            packet,
            scope=ContextScope(
                mode="retrieval",
                workspace="enterprise",
                scope_hash="b" * 64,
                warnings=("New boundary warning.",),
            ),
        )

        delta = context_delta(previous, current)
        change = next(item for item in delta.gaps_changed if item.code == "scope_warnings")

        self.assertEqual((change.before, change.after), (1, 1))
        self.assertTrue(change.evidence_changed)
        self.assertFalse(delta.scope_changed)
        self.assertIn("scope_warnings evidence changed", delta.text())

    def test_delta_reports_logical_hint_changes_without_physical_changes(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)
        previous = packet.to_dict()
        previous["stable"]["logical_hints"] = {"mode": "confirmed", "items": ["metric_a"]}
        _refresh_identity(previous)
        current = deepcopy(previous)
        current["stable"]["logical_hints"]["items"] = ["metric_b"]
        _refresh_identity(current)

        delta = context_delta(previous, current)

        self.assertTrue(delta.logical_hints_changed)
        self.assertTrue(delta.to_dict()["logical_hints_changed"])
        self.assertEqual(delta.objects_changed, ())
        self.assertIn("Changed: logical hints", delta.text())

    def test_logical_omission_reasons_distinguish_equal_counts(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)
        previous = packet.to_dict()
        previous["dynamic"]["logical_hints"] = {
            "omissions": {"review_policy": 1},
            "warnings": [],
        }
        _refresh_identity(previous)
        current = deepcopy(previous)
        current["dynamic"]["logical_hints"]["omissions"] = {"character_budget": 1}
        _refresh_identity(current)

        delta = context_delta(previous, current)
        change = next(item for item in delta.gaps_changed if item.code == "logical_hint_limits")
        current_gap = next(
            item for item in context_brief(current).gaps
            if item.code == "logical_hint_limits"
        )

        self.assertEqual((change.before, change.after), (1, 1))
        self.assertTrue(change.evidence_changed)
        self.assertEqual(current_gap.references, ("character_budget: 1",))

    def test_delta_reports_retrieval_and_selection_evidence_changes(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)
        previous = packet.to_dict()
        current = deepcopy(previous)
        current["dynamic"]["retrieval"]["mode"] = "hybrid"
        current["dynamic"]["selection"][0]["search_score"] += 1
        _refresh_identity(current)

        delta = context_delta(previous, current)

        self.assertTrue(delta.retrieval_changed)
        self.assertTrue(delta.selection_changed)
        self.assertFalse(delta.query_changed)
        self.assertTrue(delta.stable_prefix_reusable)
        self.assertIn("Changed: retrieval · selection evidence", delta.text())

    def test_delta_reports_graph_revision_changes(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)
        previous = packet.to_dict()
        current = deepcopy(previous)
        current["stable"]["graph"]["revision"] = "f" * 64
        _refresh_identity(current)

        delta = context_delta(previous, current)

        self.assertTrue(delta.graph_revision_changed)
        self.assertTrue(delta.to_dict()["graph_revision_changed"])
        self.assertEqual(delta.objects_changed, ())
        self.assertIn("Changed: graph revision", delta.text())

    def test_snapshot_hashes_are_revalidated_before_use(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)
        snapshot = context_packet_from_dict(packet.to_dict())
        snapshot.stable["scope"]["namespace"] = "tampered"

        with self.assertRaisesRegex(ContextFailure, "identity hashes"):
            context_brief(snapshot)

    def test_identical_delta_keeps_stable_prefix_reusable(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)

        delta = context_delta(packet, packet.to_dict())

        self.assertTrue(delta.identical)
        self.assertTrue(delta.stable_prefix_reusable)
        self.assertEqual(delta.character_delta, 0)
        self.assertEqual(delta.gaps_changed, ())
        self.assertEqual(delta.joins_changed, ())

    def test_contract_change_does_not_claim_exact_prefix_reuse(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)
        legacy = packet.to_dict()
        legacy["contract_version"] = "tarel.context.v0.1"
        legacy.pop("identity")

        delta = context_delta(legacy, packet)

        self.assertFalse(delta.stable_prefix_reusable)
        self.assertFalse(delta.identical)

    def test_query_change_with_exact_anchors_reuses_the_stable_prefix(self) -> None:
        graph = _context_graph()
        object_id = next(node.id for node in graph.nodes if node.label == "sales.FactSales")
        previous = compile_context_from_objects(graph, (object_id,), query="revenue", max_hops=0)
        current = compile_context_from_objects(
            graph, (object_id,), query="revenue by year", max_hops=0,
        )

        delta = context_delta(previous, current)

        self.assertTrue(delta.query_changed)
        self.assertTrue(delta.stable_prefix_reusable)
        self.assertEqual(delta.objects_preserved, 1)
        self.assertEqual(delta.objects_added, ())
        self.assertEqual(delta.fields_added, ())

    def test_added_semantics_resolve_reported_gaps(self) -> None:
        graph = _context_graph()
        object_id = next(node.id for node in graph.nodes if node.label == "sales.FactSales")
        previous = compile_context_from_objects(graph, (object_id,), max_hops=0)
        annotated = replace(
            graph,
            nodes=tuple(
                replace(
                    node,
                    annotation=GraphAnnotation(
                        description=f"Documented {node.label}.", state="draft"
                    ),
                )
                if node.id == object_id or node.metadata.get("object_id") == object_id
                else node
                for node in graph.nodes
            ),
        )
        current = compile_context_from_objects(annotated, (object_id,), max_hops=0)

        delta = context_delta(previous, current)

        self.assertEqual(
            {gap.code for gap in delta.gaps_resolved},
            {"missing_field_semantics", "missing_object_semantics"},
        )
        self.assertEqual(context_brief(current).gaps, ())

    def test_sdk_accepts_packets_and_saved_packet_paths(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)
        sdk = Tarel(Path("unused"))

        direct = sdk.context.brief(packet)
        compared = sdk.context.compare(packet, packet)
        with TemporaryDirectory() as temporary_directory:
            left = Path(temporary_directory) / "left.json"
            right = Path(temporary_directory) / "right.json"
            rendered = json.dumps(packet.to_dict())
            left.write_text(rendered, encoding="utf-8")
            right.write_text(rendered, encoding="utf-8")
            loaded = sdk.context.brief(left)
            loaded_comparison = sdk.context.compare(left, right)
            mixed_comparison = sdk.context.compare(left, packet)

        self.assertEqual(direct.packet_hash, loaded.packet_hash)
        self.assertTrue(compared.identical)
        self.assertTrue(loaded_comparison.identical)
        self.assertTrue(mixed_comparison.identical)

    def test_cli_brief_and_diff_render_human_and_json_guidance(self) -> None:
        packet = compile_context(_context_graph(), "sales", seed_limit=1, max_objects=1)
        with TemporaryDirectory() as temporary_directory:
            left = Path(temporary_directory) / "left.json"
            right = Path(temporary_directory) / "right.json"
            rendered = json.dumps(packet.to_dict())
            left.write_text(rendered, encoding="utf-8")
            right.write_text(rendered, encoding="utf-8")

            text_output = StringIO()
            with redirect_stdout(text_output):
                brief_exit = main(["context", "brief", str(left)])
            json_output = StringIO()
            with (
                patch(
                    "tarel.application.load_context_packet",
                    wraps=load_context_packet,
                ) as packet_loader,
                redirect_stdout(json_output),
            ):
                diff_exit = main([
                    "context", "diff", str(left), str(right), "--format", "json",
                ])

        self.assertEqual(brief_exit, 0)
        self.assertIn("Area: context_demo", text_output.getvalue())
        self.assertIn("Next:", text_output.getvalue())
        self.assertEqual(diff_exit, 0)
        self.assertEqual(packet_loader.call_count, 2)
        self.assertTrue(json.loads(json_output.getvalue())["guidance"]["identity"]["identical"])

    def test_context_build_can_return_only_the_compact_brief(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            store = FileGraphStore(Path(temporary_directory))
            store.save(_context_graph())
            output = StringIO()
            with (
                patch("tarel.application.FileGraphStore", return_value=store),
                redirect_stdout(output),
            ):
                exit_code = main([
                    "context", "build", "context_demo", "sales",
                    "--seed-limit", "1", "--max-objects", "1", "--brief",
                ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Loaded: 1 object", output.getvalue())
        self.assertIn("1 selected object has no included description", output.getvalue())
        self.assertNotIn("## Stable objects", output.getvalue())


def _refresh_identity(packet: dict[str, object]) -> None:
    stable_hash = canonical_hash(packet["stable"])
    dynamic_hash = canonical_hash(packet["dynamic"])
    packet["identity"] = {
        "dynamic_hash": dynamic_hash,
        "packet_hash": canonical_hash({
            "contract_version": packet["contract_version"],
            "dynamic_hash": dynamic_hash,
            "stable_hash": stable_hash,
        }),
        "stable_hash": stable_hash,
    }


def _describe_field(packet: dict[str, object], object_label: str, field_name: str) -> None:
    objects = packet["stable"]["objects"]
    target = next(item for item in objects if item["label"] == object_label)
    field = next(item for item in target["fields"] if item["name"] == field_name)
    field["description"] = "Documented for this packet."
