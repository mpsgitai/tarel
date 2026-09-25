import builtins
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.cli import main
from tarel.lineage.application import (
    build_lineage_use_case,
    run_lineage_analysis_use_case,
)
from tarel.lineage.contracts import LineageDocument, LineageFailure
from tarel.lineage.source import LineageInput, SourceDefinition, SourceStep
from tarel.lineage.sqlglot_adapter import analyze_with_sqlglot
from tarel.lineage.status import lineage_status
from tarel.sdk import Tarel
from tarel.ui.presentation import browser_lineages


class SqlglotLineageTests(TestCase):
    def test_tsql_fixture_uses_static_analysis_without_provider(self) -> None:
        fixture = (
            Path(__file__).parent / "fixtures" / "lineage" / "adventureworks" / "sales_refresh.json"
        )
        previous = Path.cwd()
        with TemporaryDirectory() as temporary_directory:
            os.chdir(temporary_directory)
            try:
                build_lineage_use_case("aw", source_path=fixture)
                result = run_lineage_analysis_use_case(
                    "aw",
                    source_path=fixture,
                    analyzer="sqlglot",
                )
            finally:
                os.chdir(previous)

        self.assertEqual(result.applied, 2)
        self.assertEqual(result.sqlglot_applied, 2)
        self.assertEqual(result.provider_requests, 0)
        self.assertEqual(result.unresolved_definitions, ())
        self.assertEqual({item.analyzer for item in result.document.analyses}, {"sqlglot"})
        self.assertEqual({item.dialect for item in result.document.analyses}, {"tsql"})
        self.assertEqual(
            {item.evidence.source for item in result.document.write_units},
            {"sqlglot"},
        )
        self.assertEqual(
            LineageDocument.from_dict(result.document.to_dict()),
            result.document,
        )
        status = lineage_status(result.document).definitions[0].to_dict()
        self.assertEqual(status["analysis"]["analyzer"], "sqlglot")
        projected = browser_lineages((result.document,))[0]["jobs"][0]["analysis"]
        self.assertEqual(projected["analyzer"], "sqlglot")
        self.assertEqual(projected["dialect"], "tsql")

    def test_temp_table_is_excluded_and_traced_to_physical_sources(self) -> None:
        definition = _definition(
            "tsql",
            "SELECT o.id\n"
            "INTO #Stage\n"
            "FROM raw.Orders o;\n"
            "INSERT INTO mart.Fact\n"
            "SELECT s.id FROM #Stage s JOIN dim.Customer c ON c.id = s.id;",
        )

        result = analyze_with_sqlglot(definition)

        self.assertTrue(result.complete)
        assert result.analysis is not None
        self.assertEqual(result.analysis["excluded_writes"][0]["target"], "#Stage")
        sources = result.analysis["writes"][0]["sources"]
        self.assertEqual(
            {(item["target"], tuple(item["via"])) for item in sources},
            {("raw.Orders", ("#Stage",)), ("dim.Customer", ())},
        )

    def test_supported_dialects_and_cte_are_explicit(self) -> None:
        cases = {
            "duckdb": "INSERT INTO mart.orders SELECT * FROM raw.orders;",
            "postgresql": (
                "WITH staged AS (SELECT * FROM raw.orders)\n"
                "INSERT INTO mart.orders SELECT * FROM staged;"
            ),
            "sqlite": "INSERT INTO target SELECT * FROM source;",
        }

        results = {
            language: analyze_with_sqlglot(_definition(language, sql))
            for language, sql in cases.items()
        }

        self.assertTrue(all(item.complete for item in results.values()))
        self.assertEqual(results["postgresql"].dialect, "postgres")
        postgres_sources = results["postgresql"].analysis["writes"][0]["sources"]
        self.assertEqual(postgres_sources[0]["target"], "raw.orders")
        self.assertEqual(postgres_sources[0]["via"], ["staged"])

    def test_update_and_delete_aliases_do_not_become_physical_sources(self) -> None:
        definition = _definition(
            "tsql",
            "UPDATE target_alias\n"
            "SET value = source_alias.value\n"
            "FROM dbo.Target AS target_alias\n"
            "JOIN dbo.Source AS source_alias ON source_alias.id = target_alias.id;\n"
            "DELETE target_alias\n"
            "FROM dbo.Target AS target_alias\n"
            "JOIN dbo.Obsolete AS old ON old.id = target_alias.id;",
        )

        result = analyze_with_sqlglot(definition)

        self.assertTrue(result.complete)
        assert result.analysis is not None
        self.assertEqual(
            [item["target"] for item in result.analysis["writes"]],
            ["dbo.Target", "dbo.Target"],
        )
        self.assertEqual(
            [
                [source["target"] for source in item["sources"]]
                for item in result.analysis["writes"]
            ],
            [["dbo.Source"], ["dbo.Obsolete"]],
        )

    def test_dynamic_sql_is_sent_as_one_definition_to_provider_fallback(self) -> None:
        source = _source("EXEC('INSERT INTO dbo.Target SELECT * FROM dbo.Source');")
        provider = _Provider(
            [
                {
                    "excluded_writes": [],
                    "observations": [],
                    "summary": "Provider reviewed the complete dynamic definition.",
                    "warnings": ["Dynamic SQL could not be resolved statically."],
                    "writes": [],
                }
            ]
        )
        previous = Path.cwd()
        with TemporaryDirectory() as temporary_directory:
            os.chdir(temporary_directory)
            try:
                source_path = Path("source.json")
                _write_source(source_path, source)
                build_lineage_use_case("dynamic", source_path=source_path)
                with patch("tarel.lineage.application.load_provider", return_value=provider):
                    result = run_lineage_analysis_use_case(
                        "dynamic",
                        source_path=source_path,
                        analyzer="auto",
                        provider_name="openrouter",
                        retry=0,
                        review_passes=0,
                    )
            finally:
                os.chdir(previous)

        self.assertEqual(result.applied, 1)
        self.assertEqual(result.sqlglot_applied, 0)
        self.assertEqual(result.provider_requests, 1)
        self.assertEqual(result.fallback_definitions, ("etl.Load",))
        self.assertEqual(result.document.analyses[0].analyzer, "provider:openrouter")
        self.assertEqual(len(provider.requests), 1)

    def test_static_only_keeps_unsupported_definition_visible_and_retryable(self) -> None:
        source = _source("EXEC('SELECT * FROM dbo.Source');")
        previous = Path.cwd()
        with TemporaryDirectory() as temporary_directory:
            os.chdir(temporary_directory)
            try:
                source_path = Path("source.json")
                _write_source(source_path, source)
                build_lineage_use_case("dynamic", source_path=source_path)
                result = run_lineage_analysis_use_case(
                    "dynamic",
                    source_path=source_path,
                    analyzer="sqlglot",
                )
                second = run_lineage_analysis_use_case(
                    "dynamic",
                    source_path=source_path,
                    analyzer="sqlglot",
                )
            finally:
                os.chdir(previous)

        self.assertEqual(result.applied, 0)
        self.assertEqual(result.unresolved_definitions, ("etl.Load",))
        self.assertEqual(result.document.analysis_failures[0].provider, "sqlglot")
        self.assertEqual(second.planned, 1)

    def test_missing_extra_has_a_precise_error(self) -> None:
        original_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):
            if name == "sqlglot" or name.startswith("sqlglot."):
                raise ImportError("blocked for contract test")
            return original_import(name, *args, **kwargs)

        with (
            patch.object(builtins, "__import__", side_effect=blocked_import),
            self.assertRaisesRegex(LineageFailure, r"tarel\[sql-lineage\]"),
        ):
            analyze_with_sqlglot(_definition("sqlite", "SELECT * FROM source;"))

    def test_cli_and_sdk_share_the_static_application_path(self) -> None:
        fixture = (
            Path(__file__).parent / "fixtures" / "lineage" / "adventureworks" / "sales_refresh.json"
        )
        previous = Path.cwd()
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            sdk = Tarel(root / "sdk-state")
            sdk.lineage.build("aw", source=fixture)
            sdk_result = sdk.lineage.analyze(
                "aw",
                source=fixture,
                analyzer="sqlglot",
            )
            cli_root = root / "cli"
            cli_root.mkdir()
            os.chdir(cli_root)
            try:
                build_code, _, _ = _run_cli(
                    ["lineage", "build", "aw", "--source", str(fixture), "--format", "json"]
                )
                code, output, _ = _run_cli(
                    [
                        "lineage",
                        "analyze",
                        "aw",
                        "--source",
                        str(fixture),
                        "--analyzer",
                        "sqlglot",
                        "--format",
                        "json",
                    ]
                )
            finally:
                os.chdir(previous)

        payload = json.loads(output)
        self.assertEqual(build_code, 0)
        self.assertEqual(code, 0)
        self.assertEqual(payload["analyzer"], "sqlglot")
        self.assertEqual(payload["provider_requests"], 0)
        self.assertEqual(payload["sqlglot_applied"], sdk_result.sqlglot_applied)


def _definition(language: str, content: str) -> SourceDefinition:
    return SourceDefinition(
        external_id="load",
        kind="script",
        name="Load",
        qualified_name="etl.Load",
        language=language,
        content=content,
        source_reference="test:load",
    )


def _source(content: str) -> LineageInput:
    definition = _definition("tsql", content)
    return LineageInput(
        source_kind="test",
        source_name="SQLGlot test",
        source_reference="test:sqlglot",
        workflow_external_id="sqlglot",
        workflow_name="SQLGlot",
        definitions=(definition,),
        steps=(SourceStep("load", "Load", definition.external_id, ()),),
    )


def _write_source(path: Path, source: LineageInput) -> None:
    payload = {
        "definitions": [
            {
                "content": item.content,
                "external_id": item.external_id,
                "kind": item.kind,
                "language": item.language,
                "name": item.name,
                "qualified_name": item.qualified_name,
                "source_reference": item.source_reference,
            }
            for item in source.definitions
        ],
        "format_version": "tarel.lineage-input.v0.2",
        "materializations": [],
        "observations": [],
        "source": {
            "kind": source.source_kind,
            "name": source.source_name,
            "reference": source.source_reference,
        },
        "workflow": {
            "external_id": source.workflow_external_id,
            "name": source.workflow_name,
            "steps": [
                {
                    "definition_id": item.definition_external_id,
                    "depends_on": list(item.depends_on_external_ids),
                    "external_id": item.external_id,
                    "name": item.name,
                }
                for item in source.steps
            ],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class _Provider:
    name = "openrouter"
    default_model = "test/model"

    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


def _run_cli(arguments: list[str]) -> tuple[int, str, str]:
    output = StringIO()
    errors = StringIO()
    with redirect_stdout(output), redirect_stderr(errors):
        code = main(arguments)
    return code, output.getvalue(), errors.getvalue()
