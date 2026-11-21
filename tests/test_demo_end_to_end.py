"""End-to-end behavior against the built-in retail demo warehouse."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.retrieval.settings import RetrievalSettings
from tarel.sdk import Tarel
from tarel.sdk.setup import create_demo


class RetailDemoTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / ".tarel"
        create_demo("retail-dwh", path=root / "demos" / "retail-dwh.sqlite")
        self.tarel = Tarel(root)
        self.tarel.source.configure(
            "retail", connector="sqlite", config_reference="state:demos/retail-dwh.toml",
            namespace="main",
        )
        self.tarel.source.build_graph("retail", "retail")

    def test_unqualified_script_tables_resolve_to_graph_objects(self) -> None:
        lineage = self.tarel.lineage
        lineage.add_job(
            "manual", kind="script", job_name="stage", qualified_name="TarelRetailDW.main.stage",
            language="sqlite", source_reference="scripts/stage.sql",
            description="Stages internet sales.",
        )
        lineage.add_hop(
            "manual", job="TarelRetailDW.main.stage", source="F_SLS_01", target="MART_STAGE",
            operation="insert", evidence_reference="scripts/stage.sql", reason="INSERT ... SELECT",
        )

        trace = lineage.upstream("MART_STAGE", lineages=("manual",), graphs=("retail",))

        sources = {origin.reference: origin.source for origin in trace.origins}
        self.assertEqual(sources, {"TarelRetailDW.main.F_SLS_01": "graph:retail"})

    def test_ambiguous_short_names_stay_external(self) -> None:
        # The same object name in a second graph makes "F_SLS_01" ambiguous: keep it unresolved.
        self.tarel.source.build_graph("retail", "retail-copy")
        lineage = self.tarel.lineage
        lineage.add_job(
            "manual", kind="script", job_name="stage", qualified_name="TarelRetailDW.main.stage",
            language="sqlite", source_reference="scripts/stage.sql",
            description="Stages internet sales.",
        )
        lineage.add_hop(
            "manual", job="TarelRetailDW.main.stage", source="F_SLS_01", target="MART_STAGE",
            operation="insert", evidence_reference="scripts/stage.sql", reason="INSERT ... SELECT",
        )

        trace = lineage.upstream(
            "MART_STAGE", lineages=("manual",), graphs=("retail", "retail-copy"),
        )

        self.assertEqual([origin.source for origin in trace.origins], ["external"])

    def test_index_status_reports_a_missing_model_instead_of_failing(self) -> None:
        self.tarel.retrieval.configure(RetrievalSettings(rerank_depth=5))

        graph_status = self.tarel.index.status("retail", model_path=Path("missing.gguf"))

        self.assertEqual(graph_status["state"], "missing")
        self.assertFalse(graph_status["ready"])
