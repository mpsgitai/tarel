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
