from __future__ import annotations

import json
import zipfile
import zlib
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from tarel.cli import main
from tarel.packages.application import (
    PACKAGE_CONTRACT_VERSION,
    PackageFailure,
    inspect_package,
    pack_workspace,
    unpack_package,
    verify_package,
)
from tarel.packages.archive import read_member
from tarel.packages.contracts import canonical_json, sha256, validate_portable_path


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

    def test_portable_paths_reject_windows_illegal_characters(self) -> None:
        for character in ':*?"<>|\x00\x1f':
            with (
                self.subTest(character=repr(character)),
                self.assertRaisesRegex(PackageFailure, "Non-portable package path"),
            ):
                validate_portable_path(f"graphs/sales{character}west/graph.json")

    def test_pack_translates_output_setup_io_errors(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            _write_json(state / "graphs/sales/graph.json", _graph_payload())
            _write_json(state / "workspaces/team/workspace.json", _workspace_payload())
            blocked_parent = root / "blocked"
            blocked_parent.write_text("regular file", encoding="utf-8")
            errors = StringIO()

            with redirect_stderr(errors):
                exit_code = main(
                    [
                        "package",
                        "pack",
                        "--state",
                        str(state),
                        "--workspace",
                        "team",
                        "--output",
                        str(blocked_parent / "team.tarel"),
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("error [package_write_failed]", errors.getvalue())

    def test_pack_rejects_oversized_source_before_reading_it(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            graph = state / "graphs/sales/graph.json"
            _write_json(graph, _graph_payload())
            graph.write_bytes(graph.read_bytes() + (b" " * 2_000))
            _write_json(state / "workspaces/team/workspace.json", _workspace_payload())

            with (
                patch("tarel.packages.application.MAX_MEMBER_BYTES", 1_024),
                self.assertRaisesRegex(PackageFailure, "Package source is too large"),
            ):
                pack_workspace(state, "team", root / "team.tarel")

    def test_read_member_translates_decompressor_errors(self) -> None:
        archive = MagicMock()
        archive.open.side_effect = zlib.error("invalid compressed data")

        with self.assertRaisesRegex(PackageFailure, "Could not read package entry"):
            read_member(archive, "graphs/sales/graph.json", 10)

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

    def test_verify_rejects_graphs_outside_the_selected_workspace(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            _write_json(state / "graphs/sales/graph.json", _graph_payload())
            _write_json(state / "workspaces/team/workspace.json", _workspace_payload())
            package = root / "team.tarel"
            pack_workspace(state, "team", package)
            members = _read_package_members(package)
            other_payload = _graph_payload()
            other_payload["name"] = "other"
            other_path = "graphs/other/graph.json"
            members[other_path] = _json_bytes(other_payload)
            _refresh_manifest(
                members,
                new_entries=(
                    {
                        "contract_version": "tarel.graph.v0.1",
                        "kind": "graph",
                        "name": "other",
                        "path": other_path,
                        "sha256": sha256(members[other_path]),
                        "size": len(members[other_path]),
                    },
                ),
            )
            independent = root / "independent-extra-graph.tarel"
            _write_package_members(independent, members)

            with self.assertRaisesRegex(PackageFailure, "extra=\\['other'\\]"):
                verify_package(independent)

    def test_verify_translates_non_object_graph_members(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            _write_json(state / "graphs/sales/graph.json", _graph_payload())
            _write_json(state / "workspaces/team/workspace.json", _workspace_payload())
            package = root / "team.tarel"
            pack_workspace(state, "team", package)
            members = _read_package_members(package)
            graph_path = "graphs/sales/graph.json"
            graph = json.loads(members[graph_path])
            graph["nodes"] = [1]
            members[graph_path] = _json_bytes(graph)
            _refresh_manifest(members)
            malformed = root / "malformed-graph.tarel"
            _write_package_members(malformed, members)

            with self.assertRaisesRegex(PackageFailure, "Invalid graph document"):
                verify_package(malformed)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(payload))


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _read_package_members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _write_package_members(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def _refresh_manifest(
    members: dict[str, bytes], *, new_entries: tuple[dict[str, object], ...] = ()
) -> None:
    manifest = json.loads(members["manifest.json"])
    manifest["entries"].extend(new_entries)
    for entry in manifest["entries"]:
        data = members[entry["path"]]
        entry["sha256"] = sha256(data)
        entry["size"] = len(data)
    manifest["entries"].sort(key=lambda entry: entry["path"])
    unsigned = {key: value for key, value in manifest.items() if key != "package_revision"}
    manifest["package_revision"] = sha256(canonical_json(unsigned))
    members["manifest.json"] = _json_bytes(manifest)


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
