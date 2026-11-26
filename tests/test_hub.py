from __future__ import annotations

import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tarel.cli import main
from tarel.connectors.contracts import ConnectorFailure
from tarel.connectors.host import check_connector
from tarel.hub.catalog import is_compatible_with_host
from tarel.hub.contracts import HubFailure
from tarel.lineage.analyzers import load_lineage_analyzer
from tarel.lineage.contracts import LineageFailure
from tarel.retrieval.contracts import RetrievalFailure
from tarel.retrieval.plugins import load_local_embedding_plugin, load_local_reranker_plugin
from tarel.sdk import Tarel


class HubCatalogAndCliTests(unittest.TestCase):
    def test_hub_list_cli_and_sdk_parity_offline(self) -> None:
        with TemporaryDirectory() as tmp:
            sdk_all = Tarel(tmp).hub.list(offline=True)
            sdk_connectors = Tarel(tmp).hub.list(kind="connector", offline=True)
            sdk_with_planned = Tarel(tmp).hub.list(include_planned=True, offline=True)

        self.assertGreaterEqual(len(sdk_all), 8)
        self.assertTrue(all(item.status != "planned" for item in sdk_all))
        self.assertGreater(len(sdk_with_planned), len(sdk_all))
        self.assertTrue(all(item.kind == "connector" for item in sdk_connectors))

        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["hub", "list", "--offline", "--format", "json"])
        self.assertEqual(code, 0, stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            [item["id"] for item in payload["extensions"]],
            [item.id for item in sdk_all],
        )

        text_out = StringIO()
        with redirect_stdout(text_out):
            self.assertEqual(main(["hub", "list", "--offline", "--kind", "connector"]), 0)
        self.assertIn("connector-postgres", text_out.getvalue())

    def test_hub_show_resolves_id_package_and_entrypoint_and_config_template(self) -> None:
        with TemporaryDirectory() as tmp:
            client = Tarel(tmp)
            by_id = client.hub.show("connector-postgres", offline=True)
            by_pkg = client.hub.show("tarel-connector-postgres", offline=True)
            by_ep = client.hub.show("postgres", offline=True)
            sqlglot = client.hub.show("sqlglot", offline=True)

        self.assertEqual(by_id.id, "connector-postgres")
        self.assertEqual(by_pkg.id, "connector-postgres")
        self.assertEqual(by_ep.id, "connector-postgres")
        self.assertEqual(sqlglot.id, "lineage-sqlglot")
        self.assertIn("binary", by_id.extras)
        self.assertEqual(by_id.recommended_extra, "binary")
        self.assertEqual(
            by_id.recommended_cli_install,
            "tarel hub install connector-postgres --extra binary --yes",
        )
        self.assertIsNotNone(by_id.config_template)
        assert by_id.config_template is not None
        self.assertIn("TAREL_POSTGRES_URL", by_id.config_template)

        # CLI --config-template in text and JSON modes
        text_out = StringIO()
        with redirect_stdout(text_out):
            self.assertEqual(
                main(["hub", "show", "postgres", "--config-template", "--offline"]),
                0,
            )
        self.assertIn("[source]", text_out.getvalue())
        self.assertIn("TAREL_POSTGRES_URL", text_out.getvalue())

        json_out = StringIO()
        with redirect_stdout(json_out):
            code = main(
                ["hub", "show", "duckdb", "--config-template", "--offline", "--format", "json"]
            )
            self.assertEqual(code, 0)
        tpl_payload = json.loads(json_out.getvalue())
        self.assertEqual(tpl_payload["extension_id"], "connector-duckdb")
        self.assertIn("warehouse.duckdb", tpl_payload["config_template"])

    def test_hub_search_matches_capabilities_and_dialects(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = main(["hub", "search", "lineage", "--offline", "--format", "json"])
        self.assertEqual(code, 0)
        ids = [item["id"] for item in json.loads(stdout.getvalue())["extensions"]]
        self.assertEqual(ids, ["lineage-sqlglot"])

        with TemporaryDirectory() as tmp:
            matches = Tarel(tmp).hub.search("mariadb", offline=True)
        self.assertEqual([item.id for item in matches], ["connector-mysql"])

    def test_hub_install_dry_run_validation_and_execution(self) -> None:
        with TemporaryDirectory() as tmp:
            client = Tarel(tmp)

            # Without --yes: plans without executing subprocess
            with patch("tarel.hub.application.subprocess.run") as run_mock:
                plan = client.hub.install("postgres", extra="binary", offline=True)
            run_mock.assert_not_called()
            self.assertFalse(plan.executed)
            self.assertTrue(plan.dry_run)
            self.assertEqual(plan.extra, "binary")
            self.assertTrue(plan.install_spec.endswith("packages/connector-postgres[binary]"))

            # Invalid extra is rejected
            with self.assertRaises(HubFailure) as invalid_extra:
                client.hub.install("postgres", extra="nonexistent", offline=True)
            self.assertEqual(invalid_extra.exception.code, "invalid_hub_extra")

            # Planned and builtin entries cannot be installed via hub install
            with self.assertRaises(HubFailure) as planned_err:
                client.hub.install("importer-documents", offline=True)
            self.assertEqual(planned_err.exception.code, "hub_extension_not_installable")

            with self.assertRaises(HubFailure) as builtin_err:
                client.hub.install("connector-sqlserver", offline=True)
            self.assertEqual(builtin_err.exception.code, "hub_extension_not_installable")

            # With --yes: runs installer subprocess and handles failure cleanly
            failed_proc = subprocess.CompletedProcess(
                args=["pip"],
                returncode=1,
                stdout="",
                stderr="network unavailable",
            )
            with (
                patch("tarel.hub.application.subprocess.run", return_value=failed_proc),
                self.assertRaises(HubFailure) as fail_err,
            ):
                client.hub.install("duckdb", yes=True, offline=True)
            self.assertEqual(fail_err.exception.code, "hub_install_failed")

            # With --yes and success: verifies installed extension
            ok_proc = subprocess.CompletedProcess(
                args=["pip"],
                returncode=0,
                stdout="Successfully installed tarel-connector-duckdb",
                stderr="",
            )
            with (
                patch("tarel.hub.application.subprocess.run", return_value=ok_proc) as run_mock,
                patch("tarel.hub.application._verify_installed", return_value=True),
            ):
                installed = client.hub.install("duckdb", yes=True, offline=True)
            run_mock.assert_called_once()
            self.assertTrue(installed.executed)
            self.assertFalse(installed.dry_run)
            self.assertTrue(installed.verified)

        # CLI dry-run output
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = main(["hub", "install", "connector-duckdb", "--offline", "--format", "json"])
        self.assertEqual(code, 0)
        cli_plan = json.loads(stdout.getvalue())
        self.assertTrue(cli_plan["dry_run"])
        self.assertFalse(cli_plan["executed"])

    def test_hub_url_override_and_error_handling(self) -> None:
        with TemporaryDirectory() as tmp:
            custom_catalog = Path(tmp) / "custom_catalog.json"
            custom_catalog.write_text(
                json.dumps(
                    {
                        "contract_version": 1,
                        "extensions": [
                            {
                                "id": "connector-custom",
                                "kind": "connector",
                                "capabilities": ["connector"],
                                "status": "experimental",
                                "package": "tarel-connector-custom",
                                "import_name": "tarel_connector_custom",
                                "path": "packages/connector-custom",
                                "entry_points": [
                                    {"group": "tarel.connectors", "name": "custom"}
                                ],
                                "host_contract": "connector.v1",
                                "host_versions": "tarel>=0.0.6,<0.1",
                                "dependencies": [],
                                "native_requirements": [],
                                "extras": [],
                                "recommended_extra": None,
                                "license": "MIT",
                                "origin": "internal",
                                "install": "pip install tarel-connector-custom",
                                "install_spec": "git+https://example.invalid/hub.git#subdirectory=packages/connector-custom",
                                "real_source_evidence": "custom",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            client = Tarel(tmp)
            items = client.hub.list(hub_url=str(custom_catalog))
            self.assertEqual([item.id for item in items], ["connector-custom"])
            self.assertEqual(items[0].catalog_source, str(custom_catalog))

            # Explicit bad hub_url must raise HubFailure (never silently swallow)
            with self.assertRaises(HubFailure) as missing_err:
                client.hub.list(hub_url=str(Path(tmp) / "missing.json"))
            self.assertEqual(missing_err.exception.code, "hub_fetch_failed")

            # Unsupported scheme raises HubFailure
            with self.assertRaises(HubFailure) as scheme_err:
                client.hub.list(hub_url="ftp://example.invalid/catalog.json")
            self.assertEqual(scheme_err.exception.code, "hub_fetch_failed")

            # Default URL falls back to bundled snapshot when offline/unreachable
            with patch(
                "tarel.hub.catalog._fetch_catalog_json",
                side_effect=HubFailure("hub_fetch_failed", "offline"),
            ):
                fallback = client.hub.list()
            self.assertGreaterEqual(len(fallback), 8)
            self.assertEqual(fallback[0].catalog_source, "bundled_snapshot")

    def test_host_version_compatibility_ranges(self) -> None:
        self.assertTrue(is_compatible_with_host("tarel>=0.0.6,<0.1", "0.0.6"))
        self.assertTrue(is_compatible_with_host("tarel>=0.0.3,<0.1", "0.0.6"))
        self.assertFalse(is_compatible_with_host("tarel>=0.0.7,<0.1", "0.0.6"))
        self.assertFalse(is_compatible_with_host("tarel>=0.0.3,<0.0.6", "0.0.6"))
        self.assertTrue(is_compatible_with_host("part of the host", "0.0.6"))

    def test_hub_suggest_detects_project_signals_without_reading_secrets(self) -> None:
        with TemporaryDirectory() as tmp:
            project = Path(tmp) / "analytics_repo"
            (project / "models").mkdir(parents=True)
            (project / "data").mkdir()
            (project / ".venv" / "ignored").mkdir(parents=True)

            (project / "data" / "local.duckdb").write_bytes(b"")
            (project / "dbt_project.yml").write_text("name: retail\n", encoding="utf-8")
            (project / "models" / "orders.sql").write_text("SELECT 1;\n", encoding="utf-8")
            (project / "docker-compose.yml").write_text(
                "services:\n  db:\n    image: postgres:17\n"
                "  ch:\n    image: clickhouse/clickhouse-server\n",
                encoding="utf-8",
            )
            # Files inside .venv must be ignored
            (project / ".venv" / "ignored" / "requirements.txt").write_text(
                "pymongo==4.19.0\n",
                encoding="utf-8",
            )

            secret_value = "SUPER_SECRET_PASSWORD_DO_NOT_LEAK"
            with patch.dict(os.environ, {"MYSQL_HOST": secret_value}, clear=False):
                stdout = StringIO()
                with redirect_stdout(stdout):
                    code = main(["hub", "suggest", "--path", str(project), "--format", "json"])
            self.assertEqual(code, 0)
            raw_json = stdout.getvalue()
            self.assertNotIn(secret_value, raw_json)

            suggestions = json.loads(raw_json)["suggestions"]
            ids = {item["extension_id"] for item in suggestions}
            self.assertIn("connector-duckdb", ids)
            self.assertIn("connector-postgres", ids)
            self.assertIn("connector-clickhouse", ids)
            self.assertIn("connector-mysql", ids)
            self.assertIn("lineage-sqlglot", ids)
            self.assertNotIn("connector-mongodb", ids)

    def test_self_healing_hub_hints_on_missing_plugins(self) -> None:
        with (
            patch("tarel.connectors.host.entry_points") as connector_eps,
            self.assertRaises(ConnectorFailure) as conn_err,
        ):
            connector_eps.return_value.select.return_value = ()
            check_connector("postgres")
        self.assertEqual(conn_err.exception.code, "unknown_connector")
        self.assertEqual(
            conn_err.exception.hint,
            "tarel hub install connector-postgres --extra binary --yes",
        )
        self.assertEqual(conn_err.exception.details["hub_package"], "connector-postgres")
        self.assertIn("tarel hub install connector-postgres", str(conn_err.exception))

        # CLI stderr exposes the self-healing hint
        stderr = StringIO()
        with (
            patch("tarel.connectors.host.entry_points") as connector_eps,
            redirect_stderr(stderr),
        ):
            connector_eps.return_value.select.return_value = ()
            exit_code = main(["connector", "check", "duckdb"])
        self.assertEqual(exit_code, 2)
        self.assertIn("tarel hub install connector-duckdb --yes", stderr.getvalue())

        with (
            patch("tarel.lineage.analyzers.entry_points") as lineage_eps,
            self.assertRaises(LineageFailure) as lineage_err,
        ):
            lineage_eps.return_value.select.return_value = ()
            load_lineage_analyzer("sqlglot")
        self.assertEqual(lineage_err.exception.code, "sqlglot_not_installed")
        self.assertEqual(lineage_err.exception.hint, "tarel hub install lineage-sqlglot --yes")
        self.assertEqual(lineage_err.exception.details["hub_package"], "lineage-sqlglot")

        with (
            patch("tarel.retrieval.plugins.entry_points") as retrieval_eps,
            self.assertRaises(RetrievalFailure) as emb_err,
        ):
            retrieval_eps.return_value.select.return_value = ()
            load_local_embedding_plugin()
        self.assertEqual(emb_err.exception.code, "missing_local_rag_dependency")
        self.assertEqual(emb_err.exception.hint, "tarel hub install retrieval-llamacpp --yes")
        self.assertEqual(emb_err.exception.details["hub_package"], "retrieval-llamacpp")

        with (
            patch("tarel.retrieval.plugins.entry_points") as retrieval_eps,
            self.assertRaises(RetrievalFailure) as rerank_err,
        ):
            retrieval_eps.return_value.select.return_value = ()
            load_local_reranker_plugin()
        self.assertEqual(rerank_err.exception.code, "missing_local_rag_dependency")
        self.assertEqual(rerank_err.exception.hint, "tarel hub install retrieval-llamacpp --yes")


if __name__ == "__main__":
    unittest.main()
