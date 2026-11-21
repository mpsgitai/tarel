"""Same-named objects across catalogs: only ambiguity on the traced path may stop a trace."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from json import loads
from os import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.cli import main
from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.lineage.contracts import (
    LineageClaim,
    LineageDefinition,
    LineageDocument,
    LineageEvidence,
    LineageFailure,
    LineageWriteSource,
    LineageWriteUnit,
    validate_lineage_document,
)
from tarel.lineage.traversal import find_lineage_references, trace_upstream
from tarel.sdk import Tarel


class IrrelevantAmbiguityTests(TestCase):
    def test_trace_ignores_ambiguity_it_never_depends_on(self) -> None:
        trace = trace_upstream(_documents(), _graphs(), "reports.Finance.Card")

        self.assertEqual(
            {hop.source.reference for hop in trace.hops}, {"Finance.finance.Ledger"},
        )
        self.assertFalse(trace.truncated)
        self.assertNotIn("DimGeography", " ".join(trace.warnings))

    def test_find_works_with_an_irrelevant_ambiguity_loaded(self) -> None:
        found = find_lineage_references(_documents(), _graphs(), "Finance Card")

        self.assertEqual(found[0].reference, "reports.Finance.Card")

    def test_ambiguous_definition_read_stops_only_the_traces_that_reach_it(self) -> None:
        with self.assertRaises(LineageFailure) as raised:
            trace_upstream(_documents(), _graphs(), "reports.Geo.Card")

        self.assertEqual(raised.exception.code, "ambiguous_lineage_reference")
        message = str(raised.exception)
        self.assertIn("dbo.DimGeography", message)
        self.assertIn("Adventure.dbo.DimGeography", message)
        self.assertIn("Contoso.dbo.DimGeography", message)
        self.assertIn("reports.Geo.Card", message)

    def test_ambiguous_start_is_rejected_without_choosing(self) -> None:
        with self.assertRaises(LineageFailure) as raised:
            trace_upstream(_documents(), _graphs(), "dbo.DimGeography")

        self.assertEqual(raised.exception.code, "ambiguous_lineage_reference")
        self.assertIn("Adventure.dbo.DimGeography", str(raised.exception))
        self.assertIn("Contoso.dbo.DimGeography", str(raised.exception))

    def test_fully_qualified_reference_is_exact(self) -> None:
        document = _document(
            "qualified",
            _definition("card", "Card", "reports.Qualified.Card"),
            claims=(_claim("read", "card", "Contoso.dbo.DimGeography"),),
        )

        trace = trace_upstream((document,), _graphs(), "reports.Qualified.Card")

        self.assertEqual(
            [hop.source.reference for hop in trace.hops], ["Contoso.dbo.DimGeography"],
        )

    def test_write_with_an_ambiguous_target_blocks_every_candidate(self) -> None:
        # The load may fill either table, so neither may present itself as a complete origin.
        document = _document(
            "unknown-target",
            _definition("load", "Load", "jobs.Load"),
            write_units=(_unit("load", "dbo.DimGeography", "staging.Geo"),),
        )

        for start in ("Adventure.dbo.DimGeography", "Contoso.dbo.DimGeography"):
            with self.subTest(start=start), self.assertRaises(LineageFailure) as raised:
                trace_upstream((document,), _graphs(), start)
            self.assertEqual(raised.exception.code, "ambiguous_lineage_reference")

    def test_ambiguity_beyond_the_hop_limit_reports_truncation_not_completeness(self) -> None:
        trace = trace_upstream(_documents(), _graphs(), "reports.Chain.Card", max_hops=1)

        self.assertTrue(trace.truncated)
        self.assertIn("Trace stopped at the configured max_hops=1 boundary.", trace.warnings)
        with self.assertRaises(LineageFailure):
            trace_upstream(_documents(), _graphs(), "reports.Chain.Card", max_hops=2)


class DeclaredIdentityTests(TestCase):
    def test_definition_catalog_settles_a_two_part_name_and_says_so(self) -> None:
        document = _document(
            "adventure-etl",
            _definition("load", "Load", "Adventure.dbo.LoadCustomer"),
            write_units=(_unit("load", "dbo.DimCustomer", "dbo.DimGeography"),),
        )

        trace = trace_upstream((document,), _graphs(), "Adventure.dbo.DimCustomer")

        self.assertEqual(
            {hop.source.reference for hop in trace.hops}, {"Adventure.dbo.DimGeography"},
        )
        self.assertIn(
            "Same-named reference dbo.DimGeography resolved to Adventure.dbo.DimGeography "
            "by the catalog of Adventure.dbo.LoadCustomer.",
            trace.warnings,
        )

    def test_same_named_definitions_are_read_inside_their_own_document(self) -> None:
        old = _document(
            "etl-old",
            _definition("extract", "Extract", "src.dbo.Extract"),
            _definition("load", "Load", "jobs.Load"),
            claims=(
                _claim("old-a", "load", "src.dbo.Extract"),
                _claim("old-b", "extract", "finance.Ledger"),
            ),
        )
        fixed = _document(
            "etl-fixed",
            _definition("extract", "Extract", "src.dbo.Extract"),
            _definition("load", "Load fixed", "jobs.LoadFixed"),
            claims=(
                _claim("fixed-a", "load", "src.dbo.Extract"),
                _claim("fixed-b", "extract", "staging.Geo"),
            ),
        )

        trace = trace_upstream((old, fixed), _graphs(), "jobs.LoadFixed")

        self.assertEqual(
            {hop.source.reference for hop in trace.hops},
            {"src.dbo.Extract", "Finance.staging.Geo"},
        )
        self.assertEqual({hop.lineage for hop in trace.hops}, {"etl-fixed"})

    def test_catalog_named_elsewhere_in_the_document_settles_a_bare_name(self) -> None:
        document = _document(
            "pipeline",
            _definition("load", "Load", "jobs.pipeline.load"),
            claims=(
                _claim("exact", "load", "Portable.main.stg_sale"),
                _claim("bare", "load", "dim_customer"),
            ),
        )

        trace = trace_upstream((document,), _name_clash_graphs(), "jobs.pipeline.load")

        self.assertIn(
            "Portable.main.dim_customer", {hop.source.reference for hop in trace.hops},
        )

    def test_bare_name_matching_a_foreign_definition_is_not_taken_on_trust(self) -> None:
        # dim_customer also names a definition of an unrelated pipeline; adopting it because it is
        # the only exact alias would invent lineage from that pipeline.
        foreign = _document(
            "foreign", _definition("model", "dim_customer", "dbt.lakehouse.dim_customer"),
        )
        document = _document(
            "report",
            _definition("card", "Card", "reports.Portable.Card"),
            claims=(_claim("bare", "card", "dim_customer"),),
        )

        with self.assertRaises(LineageFailure) as raised:
            trace_upstream((document, foreign), _name_clash_graphs(), "reports.Portable.Card")

        self.assertEqual(raised.exception.code, "ambiguous_lineage_reference")
        self.assertIn("dbt.lakehouse.dim_customer", str(raised.exception))
        self.assertIn("Portable.main.dim_customer", str(raised.exception))


class NameCoincidenceTests(TestCase):
    def test_only_object_of_a_name_in_an_unmentioned_system_is_not_an_upstream(self) -> None:
        # A large selection makes such a match likely; it must not become a false origin.
        document = _document(
            "report",
            _definition("card", "Card", "powerbi.Portable.Card"),
            claims=(
                _claim("exact", "card", "Portable.main.stg_sale"),
                _claim("bare", "card", "Sales"),
            ),
        )
        unrelated = _graph(
            "music", "Music", (GraphNode("music-sales", "table", "main.Sales", {}),),
        )

        trace = trace_upstream(
            (document,), (*_name_clash_graphs(), unrelated), "powerbi.Portable.Card",
        )

        self.assertNotIn("Music.main.Sales", {hop.source.reference for hop in trace.hops})
        self.assertIn("Sales", {origin.reference for origin in trace.origins})
        self.assertIn("Unresolved upstream reference: Sales", trace.warnings)

    def test_foreign_definition_matching_a_bare_name_is_not_an_upstream(self) -> None:
        foreign = _document(
            "foreign", _definition("model", "ledger", "dbt.finance.ledger"),
        )
        document = _document(
            "report",
            _definition("card", "Card", "powerbi.Portable.Card"),
            claims=(
                _claim("exact", "card", "Portable.main.stg_sale"),
                _claim("bare", "card", "ledger"),
            ),
        )

        trace = trace_upstream((document, foreign), _name_clash_graphs(), "powerbi.Portable.Card")

        self.assertNotIn("dbt.finance.ledger", {hop.source.reference for hop in trace.hops})
        self.assertIn("Unresolved upstream reference: ledger", trace.warnings)

    def test_document_without_a_catalog_keeps_the_match_and_flags_it(self) -> None:
        document = _document(
            "script",
            _definition("job", "Job", "jobs.Script"),
            claims=(_claim("bare", "job", "Sales"),),
        )
        only = _graph("music", "Music", (GraphNode("music-sales", "table", "main.Sales", {}),))

        trace = trace_upstream((document,), (only,), "jobs.Script")

        self.assertEqual({hop.source.reference for hop in trace.hops}, {"Music.main.Sales"})
        self.assertIn(
            "Reference Sales matched Music.main.Sales by name alone; "
            "lineage script names no catalog to confirm it.",
            trace.warnings,
        )

    def test_bare_name_in_a_catalog_the_document_names_still_resolves(self) -> None:
        document = _document(
            "pipeline",
            _definition("load", "Load", "jobs.pipeline.load"),
            claims=(
                _claim("exact", "load", "Portable.main.stg_sale"),
                _claim("bare", "load", "dim_customer"),
            ),
        )
        only_portable = (_name_clash_graphs()[0],)

        trace = trace_upstream((document,), only_portable, "jobs.pipeline.load")

        self.assertIn(
            "Portable.main.dim_customer", {hop.source.reference for hop in trace.hops},
        )
        self.assertNotIn("name alone", " ".join(trace.warnings))


class ExistingBehaviorTests(TestCase):
    def test_missing_reference_stays_a_visible_unresolved_origin(self) -> None:
        document = _document(
            "missing",
            _definition("card", "Card", "reports.Missing.Card"),
            claims=(_claim("read", "card", "nowhere.Table"),),
        )

        trace = trace_upstream((document,), _graphs(), "reports.Missing.Card")

        self.assertEqual(trace.origins[0].kind, "unresolved")
        self.assertIn("Unresolved upstream reference: nowhere.Table", trace.warnings)

    def test_unknown_start_is_not_found(self) -> None:
        with self.assertRaises(LineageFailure) as raised:
            trace_upstream(_documents(), _graphs(), "reports.Nope")

        self.assertEqual(raised.exception.code, "lineage_reference_not_found")

    def test_cycles_terminate_with_a_warning_next_to_an_irrelevant_ambiguity(self) -> None:
        document = _document(
            "cycle",
            _definition("a", "A", "jobs.A"),
            _definition("b", "B", "jobs.B"),
            claims=(_claim("ab", "a", "jobs.B"), _claim("ba", "b", "jobs.A")),
        )

        trace = trace_upstream((*_documents(), document), _graphs(), "jobs.A")

        self.assertIn("Lineage cycle detected at: jobs.A", trace.warnings)

    def test_results_do_not_depend_on_loading_order(self) -> None:
        documents, graphs = _documents(), _graphs()

        first = trace_upstream(documents, graphs, "reports.Finance.Card")
        second = trace_upstream(documents[::-1], graphs[::-1], "reports.Finance.Card")

        self.assertEqual(first.to_dict(), second.to_dict())


class SurfaceParityTests(TestCase):
    def test_cli_and_sdk_report_the_same_trace_and_the_same_failure(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory() as directory:
            chdir(directory)
            self.addCleanup(chdir, previous)
            sdk = Tarel(Path(directory) / ".tarel")
            for graph in _graphs():
                sdk.runtime.graph_store().save(graph)
            for document in _documents():
                sdk.runtime.lineage_store().save(document)
            sources = (
                "--lineage", "north", "--lineage", "south",
                "--graph", "adventure", "--graph", "contoso", "--graph", "finance",
            )
            scope = {
                "lineages": ("north", "south"),
                "graphs": ("adventure", "contoso", "finance"),
            }

            output = StringIO()
            with redirect_stdout(output):
                code = main([
                    "lineage", "upstream", "reports.Finance.Card", *sources, "--format", "json",
                ])
            self.assertEqual(code, 0)
            self.assertEqual(
                loads(output.getvalue()),
                sdk.lineage.upstream("reports.Finance.Card", **scope).to_dict(),
            )

            errors = StringIO()
            with redirect_stderr(errors):
                code = main([
                    "lineage", "upstream", "reports.Geo.Card", *sources, "--format", "json",
                ])
            self.assertEqual(code, 2)
            self.assertIn("ambiguous_lineage_reference", errors.getvalue())
            with self.assertRaises(LineageFailure) as raised:
                sdk.lineage.upstream("reports.Geo.Card", **scope)
            self.assertIn(str(raised.exception), errors.getvalue())


def _documents() -> tuple[LineageDocument, ...]:
    north = _document(
        "north",
        _definition("finance", "Finance card", "reports.Finance.Card"),
        claims=(_claim("finance-read", "finance", "finance.Ledger"),),
    )
    south = _document(
        "south",
        _definition("geo", "Geo card", "reports.Geo.Card"),
        _definition("chain", "Chain card", "reports.Chain.Card"),
        _definition("middle", "Chain middle", "reports.Chain.Middle"),
        claims=(
            _claim("geo-read", "geo", "dbo.DimGeography"),
            _claim("chain-read", "chain", "reports.Chain.Middle"),
            _claim("middle-read", "middle", "dbo.DimGeography"),
        ),
    )
    return north, south


def _graphs() -> tuple[GraphDocument, ...]:
    table = GraphNode
    return (
        _graph("adventure", "Adventure", (
            table("geo", "table", "dbo.DimGeography", {}),
            table("customer", "table", "dbo.DimCustomer", {}),
        )),
        _graph("contoso", "Contoso", (
            table("geo", "table", "dbo.DimGeography", {}),
            table("customer", "table", "dbo.DimCustomer", {}),
        )),
        _graph("finance", "Finance", (
            table("ledger", "table", "finance.Ledger", {}),
            table("geo-stage", "table", "staging.Geo", {}),
        )),
    )


def _name_clash_graphs() -> tuple[GraphDocument, ...]:
    return (
        _graph("portable", "Portable", (
            GraphNode("customer", "table", "main.dim_customer", {}),
            GraphNode("sale", "table", "main.stg_sale", {}),
        )),
        _graph("lakehouse", "Lakehouse", (
            GraphNode("customer", "table", "silver.dim_customer", {}),
        )),
    )


def _document(
    name: str,
    *definitions: LineageDefinition,
    claims: tuple[LineageClaim, ...] = (),
    write_units: tuple[LineageWriteUnit, ...] = (),
) -> LineageDocument:
    document = LineageDocument(
        name=name,
        source_kind="test",
        source_name=name,
        source_reference=f"test:{name}",
        source_revision="2" * 64,
        workflow_id=f"workflow-{name}",
        workflow_name=name,
        definitions=definitions,
        steps=(),
        claims=claims,
        write_units=write_units,
    )
    validate_lineage_document(document)
    return document


def _definition(identifier: str, name: str, qualified_name: str) -> LineageDefinition:
    return LineageDefinition(
        id=identifier,
        external_id=f"external-{qualified_name}",
        kind="query",
        name=name,
        qualified_name=qualified_name,
        language="tsql",
        source_reference=f"fixture:{identifier}",
        content_hash="0" * 64,
        revision="1" * 64,
    )


def _claim(identifier: str, definition_id: str, target: str) -> LineageClaim:
    return LineageClaim(
        id=identifier,
        definition_id=definition_id,
        operation="read",
        target=target,
        state="draft",
        evidence=_evidence(definition_id),
    )


def _unit(definition_id: str, target: str, source: str) -> LineageWriteUnit:
    return LineageWriteUnit(
        id=f"{definition_id}-{target}",
        definition_id=definition_id,
        operation="insert",
        target=target,
        state="draft",
        sources=(
            LineageWriteSource(
                target=source, role="business_data", via=(), evidence=_evidence(definition_id),
            ),
        ),
        evidence=_evidence(definition_id),
    )


def _evidence(reference: str) -> LineageEvidence:
    return LineageEvidence(
        source="fixture",
        reference=f"fixture:{reference}",
        reason="The fixture declares this reference.",
        line_start=1,
        line_end=1,
    )


def _graph(name: str, catalog: str, nodes: tuple[GraphNode, ...]) -> GraphDocument:
    return GraphDocument(
        name=name,
        connector="fixture",
        source_type="sql",
        catalog=catalog,
        dialect="tsql",
        nodes=nodes,
        edges=(),
    )
