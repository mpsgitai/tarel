"""Tests for the 4 usability & security findings from the fresh E2E walkthrough."""

from __future__ import annotations

import json
import os
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.cli import main
from tarel.connectors.application import read_config
from tarel.connectors.contracts import ConnectorFailure
from tarel.sdk import Tarel
from tarel.sources.application import configure_source_use_case, probe_source_use_case
from tarel.sources.contracts import SourceFailure


class UsabilityAndSecurityFindingsTests(TestCase):
    def test_env_config_ref_with_connection_url_never_leaks_secret(self) -> None:
        secret_pw = "SuperSecret_Pass_9981!"
        fake_url = f"postgresql://reader:{secret_pw}@localhost:5432/dwh"
        previous = Path.cwd()
        with (
            TemporaryDirectory() as temporary_directory,
            patch.dict(os.environ, {"TAREL_TEST_BAD_REF": fake_url}),
        ):
            os.chdir(temporary_directory)
            try:
                configure_source_use_case(
                    "pg_bad",
                    connector="sqlite",
                    config_reference="env:TAREL_TEST_BAD_REF",
                )
                with self.assertRaises(SourceFailure) as raised:
                    probe_source_use_case("pg_bad")
            finally:
                os.chdir(previous)

        self.assertEqual(raised.exception.code, "invalid_config_reference")
        self.assertNotIn(secret_pw, str(raised.exception))
        self.assertIn("env:TAREL_TEST_BAD_REF", str(raised.exception))

    def test_read_config_with_url_path_redacts_secret(self) -> None:
        secret_pw = "AnotherSecret_7766!"
        with self.assertRaises(ConnectorFailure) as raised:
            read_config(Path(f"postgresql://reader:{secret_pw}@localhost:5432/dwh"))
        self.assertEqual(raised.exception.code, "config_not_found")
        self.assertNotIn(secret_pw, str(raised.exception))

    def test_connector_list_cli_and_sdk_parity(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            sdk_items = Tarel(temporary_directory).connector.list()
        sdk_names = [item.name for item in sdk_items]
        self.assertIn("sqlite", sdk_names)
        self.assertIn("sqlserver", sdk_names)

        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(["connector", "list", "--format", "json"])
        self.assertEqual(code, 0, stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        cli_names = [item["name"] for item in payload["connectors"]]
        self.assertEqual(cli_names, sdk_names)

        text_out = StringIO()
        with redirect_stdout(text_out):
            code_text = main(["connector", "list"])
        self.assertEqual(code_text, 0)
        self.assertIn("sqlite", text_out.getvalue())

    def test_lazy_cli_version_fast_path(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            code = main(["version"])
        self.assertEqual(code, 0)
        self.assertTrue(stdout.getvalue().strip())

    def test_check_and_list_connectors_never_import_plugin_code(self) -> None:
        import sys
        from importlib.metadata import EntryPoint

        from tarel.connectors.host import check_connector, list_connectors

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            pkg = root / "no_import_plugin"
            pkg.mkdir()
            (pkg / "__init__.py").write_text(
                'raise RuntimeError("plugin __init__ must not run during check/list")\n',
                encoding="utf-8",
            )
            (pkg / "manifest.toml").write_text(
                '[connector]\n'
                'contract_version = 1\n'
                'name = "noimport"\n'
                'version = "0.1.0"\n'
                'source_type = "database"\n'
                'dialect = "sqlite"\n'
                'entrypoint = "no_import_plugin.connector:create"\n'
                'extra = "noimport"\n'
                'capabilities = ["probe", "discover_catalog"]\n'
                'permissions = ["read"]\n'
                'dependencies = []\n',
                encoding="utf-8",
            )
            ep = EntryPoint(
                name="noimport",
                value="no_import_plugin.connector:create",
                group="tarel.connectors",
            )
            sys.path.insert(0, str(root))
            try:
                with patch("tarel.connectors.host.entry_points") as eps:
                    eps.return_value.select.side_effect = (
                        lambda *, group, name=None: (ep,)
                        if group == "tarel.connectors" and name in (None, "noimport")
                        else ()
                    )
                    checked = check_connector("noimport")
                    listed = list_connectors()
            finally:
                sys.path.remove(str(root))
                sys.modules.pop("no_import_plugin", None)

        self.assertTrue(checked.available)
        self.assertIn("noimport", [item.name for item in listed])
