"""Host tests for the static SQL lineage analyzer extension point (`tarel.lineage_analyzers`)."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.lineage.analysis_application import run_lineage_analysis_use_case
from tarel.lineage.analyzers import StaticLineageAnalysisResult, load_lineage_analyzer
from tarel.lineage.application import build_lineage_use_case
from tarel.lineage.contracts import LineageDocument, LineageFailure
from tarel.lineage.coverage import write_markers
from tarel.lineage.source import SourceDefinition
from tarel.lineage.status import lineage_status
from tarel.ui.payloads.lineage import browser_lineages


class _FakeSqlglotAnalyzer:
    name = "sqlglot"

    def analyze(
        self,
        definition: SourceDefinition,
        *,
        dialect: str | None = None,
    ) -> StaticLineageAnalysisResult:
        markers = write_markers(definition.content)
        writes = [
            {
                "line_end": marker.line,
                "line_start": marker.line,
                "operation": marker.operation,
                "reason": "Fake static write.",
                "sources": [
                    {
                        "line_end": marker.line,
                        "line_start": marker.line,
                        "reason": "Fake source.",
                        "role": "unknown",
                        "target": "raw.Orders",
                        "via": [],
                    }
                ],
                "target": "mart.Fact",
                "warnings": [],
            }
            for marker in markers
        ]
        return StaticLineageAnalysisResult(
            status="complete",
            dialect=dialect or "tsql",
            engine_version="30.19.0",
            adapter_version="tarel.sqlglot-lineage.v0.2",
            analysis={
                "excluded_writes": [],
                "observations": [],
                "summary": "Fake static analysis.",
                "warnings": [],
                "writes": writes,
            },
        )


class LineageAnalyzerPluginTests(TestCase):
    def test_missing_sqlglot_hub_plugin_raises_clear_error(self) -> None:
        with (
            patch("tarel.lineage.analyzers.entry_points") as eps,
            self.assertRaises(LineageFailure) as raised,
        ):
            eps.return_value.select.return_value = ()
            load_lineage_analyzer("sqlglot")
        self.assertEqual(raised.exception.code, "sqlglot_not_installed")
        self.assertIn("tarel-lineage-sqlglot", str(raised.exception))

    def test_installed_analyzer_plugin_runs_through_host_use_case(self) -> None:
        import json

        previous = Path.cwd()
        with (
            TemporaryDirectory() as temporary_directory,
            patch(
                "tarel.lineage.analyzers.entry_points",
            ) as eps,
        ):
            eps.return_value.select.return_value = (
                type(
                    "_EP",
                    (),
                    {
                        "name": "sqlglot",
                        "load": staticmethod(lambda: _FakeSqlglotAnalyzer),
                    },
                )(),
            )
            source_file = Path(temporary_directory) / "input.json"
            source_file.write_text(
                json.dumps(
                    {
                        "format_version": "tarel.lineage-input.v0.2",
                        "materializations": [],
                        "observations": [],
                        "source": {
                            "kind": "json",
                            "name": "Fake static lineage fixture",
                            "reference": "input.json",
                        },
                        "definitions": [
                            {
                                "content": "INSERT INTO mart.Fact SELECT id FROM raw.Orders;",
                                "external_id": "proc:refresh_fact",
                                "kind": "procedure",
                                "language": "tsql",
                                "name": "usp_refresh_fact",
                                "qualified_name": "dbo.usp_refresh_fact",
                                "source_reference": "sql/usp_refresh_fact.sql",
                            }
                        ],
                        "workflow": {
                            "external_id": "job:daily_sales",
                            "name": "Daily Sales",
                            "steps": [
                                {
                                    "definition_id": "proc:refresh_fact",
                                    "depends_on": [],
                                    "external_id": "step:1",
                                    "name": "Load Fact",
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            os.chdir(temporary_directory)
            try:
                build_lineage_use_case("aw", source_path=source_file)
                result = run_lineage_analysis_use_case(
                    "aw",
                    source_path=source_file,
                    analyzer="sqlglot",
                )
            finally:
                os.chdir(previous)

        self.assertEqual(result.applied, 1)
        self.assertEqual(result.sqlglot_applied, 1)
        self.assertEqual(result.provider_requests, 0)
        self.assertEqual({item.analyzer for item in result.document.analyses}, {"sqlglot"})
        self.assertEqual(
            LineageDocument.from_dict(result.document.to_dict()),
            result.document,
        )
        status = lineage_status(result.document).definitions[0].to_dict()
        self.assertEqual(status["analysis"]["analyzer"], "sqlglot")
        projected = browser_lineages((result.document,))[0]["jobs"][0]["analysis"]
        self.assertEqual(projected["analyzer"], "sqlglot")
