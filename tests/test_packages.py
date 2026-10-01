from __future__ import annotations

import json
import zipfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tarel.cli import main
from tarel.packages.application import (
    PACKAGE_CONTRACT_VERSION,
    PackageFailure,
    inspect_package,
    pack_workspace,
    unpack_package,
    verify_package,
)
from tarel.packages.contracts import canonical_json, sha256


class PackageTests(TestCase):
    def test_workspace_package_is_deterministic_verified_and_round_trips(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            graph = state / "graphs" / "sales" / "graph.json"
            workspace = state / "workspaces" / "team" / "workspace.json"
            cache = state / "graphs" / "sales" / "graph.selective.sqlite"
            _write_json(graph, _graph_payload())
            _write_json(workspace, _workspace_payload())
            cache.write_bytes(b"rebuildable")

            first = root / "first.tarel"
            second = root / "second.tarel"
            first_report = pack_workspace(state, "team", first)
            pack_workspace(state, "team", second)

            self.assertTrue(first_report.verified)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(inspect_package(first).entries, 2)
            self.assertTrue(verify_package(first).verified)
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main(["package", "inspect", str(first), "--format", "json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.getvalue())["workspace"], "team")
            with zipfile.ZipFile(first) as archive:
                self.assertNotIn("graphs/sales/graph.selective.sqlite", archive.namelist())
                manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["contract_version"], PACKAGE_CONTRACT_VERSION)

            destination = root / "unpacked"
            unpacked = unpack_package(first, destination)
            self.assertEqual(unpacked.destination, destination)
            self.assertEqual(
                (destination / "graphs/sales/graph.json").read_bytes(),
                graph.read_bytes(),
            )
            self.assertFalse((destination / "graphs/sales/graph.selective.sqlite").exists())

    def test_unpack_rejects_existing_destination(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            _write_json(state / "graphs/sales/graph.json", _graph_payload())
            _write_json(state / "workspaces/team/workspace.json", _workspace_payload())
            package = root / "team.tarel"
            pack_workspace(state, "team", package)
            destination = root / "existing"
            destination.mkdir()

            with self.assertRaisesRegex(PackageFailure, "never merges"):
                unpack_package(package, destination)

    def test_inspect_rejects_path_traversal_before_reading_manifest(self) -> None:
        with TemporaryDirectory() as temporary:
            package = Path(temporary) / "unsafe.tarel"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("../outside", b"bad")

            with self.assertRaisesRegex(PackageFailure, "Unsafe package path"):
                inspect_package(package)

    def test_verify_rejects_content_with_a_valid_size_but_wrong_checksum(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            _write_json(state / "graphs/sales/graph.json", _graph_payload())
            _write_json(state / "workspaces/team/workspace.json", _workspace_payload())
            package = root / "team.tarel"
            pack_workspace(state, "team", package)
            with zipfile.ZipFile(package) as source:
                members = {name: source.read(name) for name in source.namelist()}
            graph_path = "graphs/sales/graph.json"
            self.assertIn(b'"catalog": "demo"', members[graph_path])
            members[graph_path] = members[graph_path].replace(
                b'"catalog": "demo"', b'"catalog": "dema"'
            )
            tampered = root / "tampered.tarel"
            with zipfile.ZipFile(tampered, "w") as target:
                for name, data in members.items():
                    target.writestr(name, data)

            with self.assertRaisesRegex(PackageFailure, "Checksum mismatch"):
                verify_package(tampered)

    def test_manifest_revision_accepts_an_independent_producer(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            _write_json(state / "graphs/sales/graph.json", _graph_payload())
            _write_json(state / "workspaces/team/workspace.json", _workspace_payload())
            package = root / "team.tarel"
            pack_workspace(state, "team", package)
            with zipfile.ZipFile(package) as source:
                members = {name: source.read(name) for name in source.namelist()}
            manifest = json.loads(members["manifest.json"])
            manifest["created_by"] = {"name": "independent-writer", "version": "1.0"}
            unsigned = {key: value for key, value in manifest.items() if key != "package_revision"}
            manifest["package_revision"] = sha256(canonical_json(unsigned))
            members["manifest.json"] = (
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode()
            independent = root / "independent.tarel"
            with zipfile.ZipFile(independent, "w") as target:
                for name, data in members.items():
                    target.writestr(name, data)

            self.assertTrue(verify_package(independent).verified)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _graph_payload() -> dict[str, object]:
    return {
        "catalog": "demo",
        "connector": "fixture",
        "contract_version": "tarel.graph.v0.1",
        "dialect": None,
        "edges": [],
        "name": "sales",
        "nodes": [],
        "source_type": "fixture",
    }


def _workspace_payload() -> dict[str, object]:
    return {
        "contract_version": "tarel.workspace.v0.1",
        "description": "Team package fixture",
        "name": "team",
        "relationships": [],
        "systems": [
            {
                "areas": [],
                "description": None,
                "graphs": ["sales"],
                "name": "sales-system",
                "zones": [],
            }
        ],
    }
