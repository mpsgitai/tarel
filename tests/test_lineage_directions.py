import json
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from test_focus import _fixture, _run_cli

from tarel.lineage import directions
from tarel.lineage.contracts import LineageFailure, LineageWriteSource, LineageWriteUnit
from tarel.lineage.directions import trace_lineage, trace_lineage_batch
from tarel.lineage.projection import compact_batch_dict
from tarel.lineage.trace_application import resolve_lineage_sources_use_case
from tarel.lineage.traversal import trace_upstream
from tarel.runtime import TarelRuntime


class DirectionTests(TestCase):
    def test_downstream_reaches_what_a_source_feeds(self) -> None:
        graph, lineage = _fixture()

        trace = trace_lineage((lineage,), (graph,), "Demo.raw.Sales", direction="down")

        self.assertEqual(trace.upstream, ())
        self.assertEqual(
            [(hop.depth, hop.source.reference, hop.target.reference) for hop in trace.downstream],
            [(1, "Demo.raw.Sales", "dbt.model.sales"), (2, "dbt.model.sales", "Demo.mart.Sales")],
        )
        self.assertEqual([item.reference for item in trace.impacts], ["Demo.mart.Sales"])

    def test_downstream_skips_fields_that_feed_nothing(self) -> None:
        graph, lineage = _fixture()

        trace = trace_lineage((lineage,), (graph,), "Demo.mart.Sales", direction="down")

        self.assertEqual(trace.downstream, ())
        self.assertEqual(trace.impacts, ())
        self.assertIn("No downstream lineage was found for the selected reference.", trace.warnings)

    def test_a_self_merge_is_not_downstream_lineage(self) -> None:
        graph, lineage = _fixture()
        evidence = lineage.claims[0].evidence
        merge = LineageWriteUnit(
            id="merge-into-itself",
            definition_id=lineage.definitions[0].id,
            operation="merge",
            target="Demo.mart.Sales",
            state="draft",
            evidence=evidence,
            sources=(LineageWriteSource("Demo.mart.Sales", "business_data", (), evidence),),
        )

        trace = trace_lineage(
            (replace(lineage, write_units=(merge,)),), (graph,), "Demo.mart.Sales",
            direction="down",
        )

        self.assertTrue(all(hop.source.id == hop.target.id for hop in trace.downstream))
        self.assertIn("No downstream lineage was found for the selected reference.", trace.warnings)
        self.assertFalse([item for item in trace.warnings if "cycle" in item])

    def test_a_terminal_table_that_merges_into_itself_is_still_an_impact(self) -> None:
        graph, lineage = _fixture()
        evidence = lineage.claims[0].evidence
        merge = LineageWriteUnit(
            id="merge-raw-and-self",
            definition_id=lineage.definitions[0].id,
            operation="merge",
            target="Demo.mart.Sales",
            state="draft",
            evidence=evidence,
            sources=(
                LineageWriteSource("Demo.raw.Sales", "business_data", (), evidence),
                LineageWriteSource("Demo.mart.Sales", "business_data", (), evidence),
            ),
        )

        trace = trace_lineage(
            (replace(lineage, write_units=(merge,)),), (graph,), "Demo.raw.Sales",
            direction="down",
        )

        self.assertEqual([item.reference for item in trace.impacts], ["Demo.mart.Sales"])

    def test_an_ambiguous_write_target_is_reported_downstream(self) -> None:
        graph, lineage = _fixture()

        trace = trace_lineage(
            (lineage,), (graph, replace(graph, name="demo-copy")), "dbt.model.sales",
            direction="down",
        )

        self.assertEqual(trace.downstream, ())
        self.assertTrue(
            any("writes to Demo.mart.Sales" in item and "matches 2 objects" in item
                for item in trace.warnings),
            trace.warnings,
        )

    def test_an_ambiguous_field_consumer_is_reported_for_its_table(self) -> None:
        graph, lineage = _fixture()
        claim = replace(lineage.claims[0], id="read-field", target="Demo.raw.Sales.SaleId")
        documents = (replace(lineage, claims=(claim,)),)
        graphs = (graph, replace(graph, name="demo-copy"))

        trace = trace_lineage(
            documents, graphs, "graph:demo:object:Demo/raw/Sales", direction="down",
        )

        self.assertTrue(
            any(item.startswith("Downstream may be incomplete: Demo.raw.Sales.SaleId")
                for item in trace.warnings),
            trace.warnings,
        )

    def test_up_matches_the_existing_upstream_trace(self) -> None:
        graph, lineage = _fixture()

        trace = trace_lineage((lineage,), (graph,), "Demo.mart.Sales", direction="up")
        upstream = trace_upstream((lineage,), (graph,), "Demo.mart.Sales")

        self.assertEqual(trace.upstream, upstream.hops)
        self.assertEqual(trace.origins, upstream.origins)

    def test_both_marks_downstream_rows_in_the_compact_view(self) -> None:
        graph, lineage = _fixture()

        compact = trace_lineage(
            (lineage,), (graph,), "dbt.model.sales", direction="both",
        ).to_compact_dict()

        self.assertEqual(compact["direction"], "both")
        self.assertEqual(
            [(item.get("dir"), item["from"], item["to"]) for item in compact["edges"]],
            [(None, "Demo.raw.Sales", "dbt.model.sales"),
             ("down", "dbt.model.sales", "Demo.mart.Sales")],
        )
        self.assertEqual(compact["origins"], ["Demo.raw.Sales"])
        self.assertEqual(compact["impacts"], ["Demo.mart.Sales"])

    def test_unknown_direction_is_retryable(self) -> None:
        graph, lineage = _fixture()

        with self.assertRaises(LineageFailure) as raised:
            trace_lineage((lineage,), (graph,), "Demo.raw.Sales", direction="sideways")

        self.assertEqual(raised.exception.code, "invalid_lineage_direction")
        self.assertTrue(raised.exception.retryable)


class BatchTests(TestCase):
    def test_batch_builds_the_network_once_and_keeps_failures_separate(self) -> None:
        graph, lineage = _fixture()

        with mock.patch.object(
            directions, "build_network", wraps=directions.build_network,
        ) as built:
            batch = trace_lineage_batch(
                (lineage,), (graph,), ("Demo.mart.Sales", "Demo.raw.Sales", "Demo.nope"),
            )

        self.assertEqual(built.call_count, 1)
        compact = compact_batch_dict(batch)
        self.assertEqual(
            compact["chains"],
            {"Demo.mart.Sales": "Demo.mart.Sales <- Demo.raw.Sales",
             "Demo.raw.Sales": "Demo.raw.Sales"},
        )
        self.assertEqual(compact["errors"]["Demo.nope"]["code"], "lineage_reference_not_found")
        self.assertEqual(
            compact["summary"],
            {"failed": 1, "jobs": 1, "max_depth": 2, "references": 3, "with_lineage": 1,
             "without_lineage": 1},
        )

    def test_batch_keeps_warnings_that_belong_to_one_reference(self) -> None:
        graph, lineage = _fixture()
        batch = trace_lineage_batch(
            (lineage,), (graph,), ("Demo.mart.Sales", "Demo.raw.Sales"), direction="down",
        )
        hidden = "Downstream may be incomplete: x in lineage y is ambiguous and may refer to z."
        first, second = batch.traces
        batch = replace(
            batch, traces=(first, replace(second, warnings=(*second.warnings, hidden))),
        )

        compact = compact_batch_dict(batch)

        self.assertEqual(compact["warnings"][hidden], ["Demo.raw.Sales"])

    def test_duplicate_references_are_rejected(self) -> None:
        graph, lineage = _fixture()

        with self.assertRaises(LineageFailure) as raised:
            trace_lineage_batch((lineage,), (graph,), ("Demo.raw.Sales", "Demo.raw.Sales"))

        self.assertEqual(raised.exception.code, "invalid_lineage_batch")


class SourceResolutionTests(TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.runtime = TarelRuntime(self.root / ".tarel")
        graph, lineage = _fixture()
        self.runtime.graph_store().save(graph)
        self.runtime.lineage_store().save(lineage)

    def test_without_sources_all_lineages_and_their_catalog_graphs_are_used(self) -> None:
        resolved = resolve_lineage_sources_use_case(runtime=self.runtime)

        self.assertEqual(
            resolved.to_dict(),
            {"auto": True, "graphs": ["demo"], "graphs_from": "declared_catalogs",
             "lineages": ["dbt-sales"], "lineages_from": "all_local"},
        )

    def test_explicit_lineage_alone_keeps_its_old_meaning(self) -> None:
        resolved = resolve_lineage_sources_use_case(
            lineage_names=("dbt-sales",), runtime=self.runtime,
        )

        self.assertEqual((resolved.lineage_names, resolved.graph_names), (("dbt-sales",), ()))
        self.assertFalse(resolved.auto)

    def test_sources_are_classified_by_name_or_prefix(self) -> None:
        resolved = resolve_lineage_sources_use_case(
            sources=("demo", "lineage:dbt-sales"), runtime=self.runtime,
        )

        self.assertEqual(resolved.lineage_names, ("dbt-sales",))
        self.assertEqual(resolved.graph_names, ("demo",))

    def test_no_auto_catalog_reads_no_graph(self) -> None:
        resolved = resolve_lineage_sources_use_case(auto_catalog=False, runtime=self.runtime)

        self.assertEqual(resolved.graph_names, ())

    def test_unknown_source_previews_accepted_names(self) -> None:
        with self.assertRaises(LineageFailure) as raised:
            resolve_lineage_sources_use_case(sources=("dmo",), runtime=self.runtime)

        self.assertEqual(raised.exception.code, "unknown_lineage_source")
        self.assertEqual(raised.exception.details["accepted_preview"][0], "demo")

    def test_role_error_suggests_the_catalog_graphs(self) -> None:
        with self.assertRaises(LineageFailure) as raised:
            resolve_lineage_sources_use_case(graph_names=("dbt-sales",), runtime=self.runtime)

        self.assertEqual(
            raised.exception.details["suggestion"],
            {"graphs": ["demo"], "graphs_from": "declared_catalogs", "lineages": ["dbt-sales"]},
        )

    def test_name_in_both_roles_must_be_prefixed(self) -> None:
        graph, _lineage = _fixture()
        self.runtime.graph_store().save(replace(graph, name="dbt-sales"))

        with self.assertRaises(LineageFailure) as raised:
            resolve_lineage_sources_use_case(sources=("dbt-sales",), runtime=self.runtime)

        self.assertEqual(raised.exception.code, "ambiguous_source")


class LineageTraceCliTests(TestCase):
    def test_trace_downstream_and_batch_default_to_compact_json(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = TarelRuntime(Path(directory) / ".tarel")
            graph, lineage = _fixture()
            runtime.graph_store().save(graph)
            runtime.lineage_store().save(lineage)
            previous = Path.cwd()
            os.chdir(directory)
            try:
                trace = _run_cli(["lineage", "trace", "Demo.mart.Sales", "--format", "json"])
                down = _run_cli(["lineage", "downstream", "Demo.raw.Sales", "--format", "json"])
                batch = _run_cli(["lineage", "batch", "Demo.mart.Sales", "Demo.raw.Sales",
                                  "--format", "json"])
                upstream = _run_cli(["lineage", "upstream", "Demo.mart.Sales", "--format", "json"])
            finally:
                os.chdir(previous)

        trace_payload = json.loads(trace[1])
        self.assertEqual(trace_payload["view"], "compact")
        self.assertEqual(trace_payload["resolution"]["graphs"], ["demo"])
        self.assertEqual(trace_payload["freshness"], {"missing": ["demo"], "stale": "unverified"})
        self.assertEqual(json.loads(down[1])["impacts"], ["Demo.mart.Sales"])
        self.assertEqual(len(batch[1].splitlines()), 1)
        self.assertEqual(json.loads(batch[1])["summary"]["references"], 2)
        upstream_payload = json.loads(upstream[1])
        self.assertEqual(upstream_payload["resolution"]["lineages_from"], "all_local")
        self.assertIn("hops", upstream_payload)
