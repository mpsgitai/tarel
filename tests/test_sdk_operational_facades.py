import json
import os
import stat
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from tarel.agents import AgentSetupFailure
from tarel.cli import main
from tarel.connectors.contracts import ConnectorFailure
from tarel.providers.contracts import ProviderFailure
from tarel.sdk import (
    Tarel,
    create_demo,
    install_agent_skill,
    scaffold_connector,
    scaffold_provider,
)


class SDKOperationalFacadeTests(TestCase):
    def test_provider_facade_shares_redacted_cli_results(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            sdk = Tarel(root / "state")
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(root / "config")}):
                path = sdk.provider.configure(
                    "local",
                    model="fixture-model",
                    base_url="http://127.0.0.1:18080/v1",
                    allow_no_api_key=True,
                )
                checked = sdk.provider.check("local")
                names = sdk.provider.list()
                cli_check = _cli_json(["provider", "check", "local", "--format", "json"])
                cli_list = _cli_json(["provider", "list", "--format", "json"])

            self.assertEqual(cli_check, [checked.to_dict()])
            self.assertEqual(
                [item["name"] for item in cli_list],
                list(names),
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertNotIn("api_key", json.dumps(checked.to_dict()))
            self.assertFalse((root / "state").exists())

    def test_provider_test_is_explicit_and_uses_the_cli_application_path(self) -> None:
        sdk = Tarel("unused-state")
        provider = _Provider()
        with patch("tarel.application.load_provider", return_value=provider):
            sdk_result = sdk.provider.test("fixture", timeout=3.5)
            cli_result = _cli_json(
                ["provider", "test", "fixture", "--timeout", "3.5", "--format", "json"]
            )
        self.assertEqual(sdk_result, cli_result)
        self.assertEqual(len(provider.requests), 2)

    def test_connector_facade_matches_cli_and_does_not_persist_samples(self) -> None:
        previous = Path.cwd()
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            demo = create_demo("retail-dwh", path=root / "retail.sqlite")
            sdk = Tarel(root / "state")
            try:
                os.chdir(root)
                checked = sdk.connector.check("sqlite")
                probe = sdk.connector.probe("sqlite", config=demo.config_path)
                catalog = sdk.connector.discover(
                    "sqlite", config=demo.config_path, namespace="main"
                )
                sample = sdk.connector.sample(
                    "sqlite",
                    config=demo.config_path,
                    namespace="main",
                    object="D_CUST",
                    limit=3,
                )
                profile = sdk.connector.profile(
                    "sqlite",
                    config=demo.config_path,
                    namespace="main",
                    object="D_CUST",
                    row_limit=100,
                    include_values=False,
                )
                cli_results = (
                    _cli_json(["connector", "check", "sqlite", "--format", "json"]),
                    _cli_json([
                        "connector", "probe", "sqlite", "--config", str(demo.config_path),
                        "--format", "json",
                    ]),
                    _cli_json([
                        "connector", "discover", "sqlite", "--config",
                        str(demo.config_path), "--namespace", "main", "--format", "json",
                    ]),
                    _cli_json([
                        "connector", "sample", "sqlite", "--config", str(demo.config_path),
                        "--namespace", "main", "--object", "D_CUST", "--limit", "3",
                        "--format", "json",
                    ]),
                    _cli_json([
                        "connector", "profile", "sqlite", "--config", str(demo.config_path),
                        "--namespace", "main", "--object", "D_CUST", "--row-limit", "100",
                        "--format", "json",
                    ]),
                )
            finally:
                os.chdir(previous)

            self.assertEqual(
                cli_results,
                (
                    checked.to_dict(),
                    probe.to_dict(),
                    catalog.to_dict(),
                    sample.to_dict(),
                    profile.to_dict(),
                ),
            )
            self.assertEqual(sdk.graph.list(), ())
            self.assertFalse((root / "state").exists())

    def test_connector_facade_requires_an_explicit_config(self) -> None:
        sdk = Tarel("unused-state")
        with self.assertRaises(TypeError):
            sdk.connector.probe("sqlite")

    def test_setup_helpers_require_explicit_targets_and_remain_outside_client(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connector = scaffold_connector("fixture", output=root / "connector")
            provider = scaffold_provider("fixture", output=root / "provider")
            skill = install_agent_skill("codex", target=root / "project")
            sdk = Tarel(root / "state")

            self.assertTrue((connector.path / "CONNECTOR_TASK.md").is_file())
            self.assertTrue((provider.path / "PROVIDER_TASK.md").is_file())
            self.assertTrue((skill.path / "SKILL.md").is_file())
            self.assertFalse(hasattr(sdk, "architecture"))
            with self.assertRaises(ConnectorFailure):
                scaffold_connector("fixture", output=root / "connector")
            with self.assertRaises(ProviderFailure):
                scaffold_provider("fixture", output=root / "provider")
            with self.assertRaises(AgentSetupFailure):
                install_agent_skill("codex", target=root / "project")


class _Provider:
    name = "fixture"
    default_model = "fixture"

    def __init__(self) -> None:
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        return {"status": "ok"}


def _cli_json(arguments: list[str]):
    output = StringIO()
    with redirect_stdout(output):
        exit_code = main(arguments)
    if exit_code != 0:
        raise AssertionError(f"CLI failed with exit code {exit_code}: {arguments}")
    return json.loads(output.getvalue())
