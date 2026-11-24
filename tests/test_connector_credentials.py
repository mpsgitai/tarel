import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.connectors.application import configured_connector
from tarel.connectors.contracts import (
    ConnectorFailure,
    ConnectorManifest,
    Credential,
    ProbeRequest,
)
from tarel.connectors.credentials import resolve_credential
from tarel.connectors.host import load_manifest
from tarel.connectors.sqlserver.connector import _login, _parse_target

SQLSERVER = load_manifest("sqlserver")
SQLITE = load_manifest("sqlite")


class CredentialResolutionTests(TestCase):
    def test_no_auth_keeps_the_url_login(self) -> None:
        self.assertIsNone(resolve_credential("sqlserver", {}, SQLSERVER, config_dir=None))

    def test_integrated_login_carries_no_secret(self) -> None:
        credential = resolve_credential(
            "sqlserver", {"auth": "integrated"}, SQLSERVER, config_dir=None
        )
        self.assertEqual(credential, Credential("integrated"))

    def test_env_secret_is_resolved_and_hidden_from_repr(self) -> None:
        with patch.dict(os.environ, {"TAREL_TEST_SECRET": "s3cr3t"}):
            credential = resolve_credential(
                "sqlserver",
                {"auth": "password", "username": "reader", "secret": "env:TAREL_TEST_SECRET"},
                SQLSERVER,
                config_dir=None,
            )
        assert credential is not None
        self.assertEqual((credential.username, credential.secret), ("reader", "s3cr3t"))
        self.assertNotIn("s3cr3t", repr(credential))

    def test_relative_file_secret_is_read_next_to_the_config(self) -> None:
        with TemporaryDirectory() as directory:
            Path(directory, "sql.secret").write_text("s3cr3t\n", encoding="utf-8")
            credential = resolve_credential(
                "sqlserver",
                {"auth": "password", "secret": "file:sql.secret"},
                SQLSERVER,
                config_dir=Path(directory),
            )
        assert credential is not None
        self.assertEqual(credential.secret, "s3cr3t")

    def test_failures_name_the_reference_but_never_a_value(self) -> None:
        cases = [
            ({"auth": "token"}, SQLSERVER, "unsupported_auth"),
            ({"auth": "integrated"}, SQLITE, "unsupported_auth"),
            ({"username": "reader"}, SQLSERVER, "invalid_config"),
            ({"auth": "password"}, SQLSERVER, "invalid_config"),
            ({"auth": "integrated", "secret": "env:X"}, SQLSERVER, "invalid_config"),
            ({"auth": "password", "secret": "cmd:az account"}, SQLSERVER, "invalid_config"),
            ({"auth": "password", "secret": "s3cr3t"}, SQLSERVER, "invalid_config"),
            (
                {"auth": "password", "secret": "env:TAREL_TEST_UNSET"},
                SQLSERVER,
                "secret_not_resolved",
            ),
            (
                {"auth": "password", "secret": "file:/missing/sql.secret"},
                SQLSERVER,
                "secret_not_resolved",
            ),
        ]
        for section, manifest, code in cases:
            with self.subTest(section=section), patch.dict(os.environ, {}, clear=False):
                os.environ.pop("TAREL_TEST_UNSET", None)
                with self.assertRaises(ConnectorFailure) as raised:
                    resolve_credential("sqlserver", section, manifest, config_dir=None)
                self.assertEqual(raised.exception.code, code)

    def test_manifest_rejects_unknown_auth_methods(self) -> None:
        data = {
            "connector": {
                "contract_version": 1,
                "name": "vendor",
                "version": "0.0.1",
                "source_type": "vendor",
                "entrypoint": "vendor.connector:create_connector",
                "extra": "vendor",
                "capabilities": ["probe", "discover_catalog"],
                "dependencies": [],
                "permissions": ["read"],
                "auth": ["cmd"],
            }
        }
        with self.assertRaises(ConnectorFailure) as raised:
            ConnectorManifest.from_mapping(data)
        self.assertEqual(raised.exception.code, "invalid_manifest")

    def test_configured_connector_resolves_the_login_from_the_config_file(self) -> None:
        with TemporaryDirectory() as directory:
            config = Path(directory, "sources.toml")
            config.write_text(
                '[sqlserver]\nurl = "mssql+pymssql://localhost/Contoso"\nauth = "integrated"\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("TAREL_SQLSERVER_URL", None)
                with patch("tarel.connectors.application.load_connector") as load:
                    load.return_value.manifest = SQLSERVER
                    source = configured_connector("sqlserver", config_path=config)
        self.assertEqual(source.credential, Credential("integrated"))
        self.assertNotIn("localhost", repr(source))


class SqlServerLoginTests(TestCase):
    def test_url_login_is_unchanged(self) -> None:
        target = _parse_target(ProbeRequest("mssql+pymssql://reader:s3cr3t@db:1433/Contoso"))
        self.assertEqual(_login(target), {"user": "reader", "password": "s3cr3t"})
        self.assertNotIn("s3cr3t", repr(target))

    def test_integrated_login_passes_no_user_to_the_driver(self) -> None:
        target = _parse_target(
            ProbeRequest("mssql+pymssql://localhost/Contoso", credential=Credential("integrated"))
        )
        self.assertEqual(_login(target), {})

    def test_password_credential_uses_the_url_user_or_its_own(self) -> None:
        credential = Credential("password", secret="s3cr3t")
        target = _parse_target(
            ProbeRequest("mssql+pymssql://reader@db/Contoso", credential=credential)
        )
        self.assertEqual(_login(target), {"user": "reader", "password": "s3cr3t"})
        own = Credential("password", username="other", secret="s3cr3t")
        target = _parse_target(ProbeRequest("mssql+pymssql://reader@db/Contoso", credential=own))
        self.assertEqual(_login(target)["user"], "other")

    def test_one_login_source_only(self) -> None:
        cases = [
            ("mssql+pymssql://db/Contoso", None, "invalid_url"),
            (
                "mssql+pymssql://reader:s3cr3t@db/Contoso",
                Credential("integrated"),
                "invalid_config",
            ),
            ("mssql+pymssql://reader@db/Contoso", Credential("integrated"), "invalid_config"),
            (
                "mssql+pymssql://db/Contoso",
                Credential("password", secret="s3cr3t"),
                "invalid_config",
            ),
        ]
        for url, credential, code in cases:
            with self.subTest(url=url, credential=credential):
                with self.assertRaises(ConnectorFailure) as raised:
                    _parse_target(ProbeRequest(url, credential=credential))
                self.assertEqual(raised.exception.code, code)
