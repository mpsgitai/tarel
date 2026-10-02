from __future__ import annotations

import errno
import json
import os
import shutil
import stat
import zlib
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

from test_packages import (
    _graph_payload,
    _read_package_members,
    _refresh_manifest,
    _workspace_payload,
    _write_json,
    _write_package_members,
)

from tarel.cli import main
from tarel.packages.application import (
    PackageFailure,
    pack_workspace,
    unpack_package,
)
from tarel.packages.contracts import OMISSIONS, SNAPSHOT_OMISSIONS


class PackageImportTests(TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "state"
        _write_json(self.state / "graphs/sales/graph.json", _graph_payload())
        _write_json(self.state / "workspaces/team/workspace.json", _workspace_payload())
        self.package = self.root / "team.tarel"
        pack_workspace(self.state, "team", self.package)
        self.destination = self.root / "imported"

    def assert_cli_failure(self, arguments: list[str], code: str, detail: str) -> None:
        errors = StringIO()
        with redirect_stderr(errors), redirect_stdout(StringIO()):
            self.assertEqual(main(["package", *arguments]), 2)
        self.assertIn(f"error [{code}]", errors.getvalue())
        self.assertIn(detail, errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())

    def assert_import_removed(self) -> None:
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.root.glob(".imported-*")), [])

    def test_verify_rejects_normalized_aliases_even_with_valid_manifest_hashes(self) -> None:
        for alias in (
            "graphs//sales/graph.json",
            "graphs/./sales/graph.json",
            "./graphs/sales/graph.json",
        ):
            with self.subTest(alias=alias):
                members = _read_package_members(self.package)
                path = "graphs/sales/graph.json"
                members[alias] = members[path]
                entry = next(
                    entry
                    for entry in json.loads(members["manifest.json"])["entries"]
                    if entry["path"] == path
                )
                entry["path"] = alias
                _refresh_manifest(members, new_entries=(entry,))
                bad = self.root / "aliased.tarel"
                _write_package_members(bad, members)
                self.assert_cli_failure(
                    ["verify", str(bad)], "invalid_package_path", "Unsafe package path"
                )

    def test_verify_rejects_case_and_unicode_collisions_before_document_parsing(self) -> None:
        for first, second in (
            ("graphs/Sales/graph.json", "graphs/sales/graph.json"),
            ("graphs/caf\u00e9/graph.json", "graphs/cafe\u0301/graph.json"),
        ):
            with self.subTest(paths=(first, second)):
                bad = self.root / "colliding.tarel"
                _write_package_members(bad, {first: b"{}", second: b"{}"})
                self.assert_cli_failure(["verify", str(bad)], "invalid_package", "colliding")

    def test_verify_rejects_raw_zip_names_that_truncate_at_a_null_byte(self) -> None:
        members = _read_package_members(self.package)
        path = "graphs/sales/graph.json"
        disguised = path + "xxxxx"
        members[disguised] = members.pop(path)
        bad = self.root / "null-alias.tarel"
        _write_package_members(bad, members)
        raw = bad.read_bytes()
        self.assertEqual(raw.count(disguised.encode()), 2)
        # ZipInfo.filename silently truncates at NUL. Keep the original member
        # length and checksums so verification must inspect the raw name.
        bad.write_bytes(raw.replace(disguised.encode(), (path + "\x00xxxx").encode()))
        self.assert_cli_failure(
            ["verify", str(bad)], "invalid_package_path", "Non-portable package path"
        )

    def test_verify_translates_malformed_json_with_matching_checksums(self) -> None:
        for data, detail in (
            (b'{"name":', "line 1, column"),
            (b'{"name":"\xff"}', "must be UTF-8"),
            (b'{"name":1,"name":2}', "duplicate object keys"),
            (b'{"number":NaN}', "non-finite"),
            (b'{"number":Infinity}', "non-finite"),
            (b'{"number":-Infinity}', "non-finite"),
            (b'{"number":1e9999}', "non-finite"),
            (b'{"nested":' + b"[" * 10000 + b"0" + b"]" * 10000 + b"}", "too deeply"),
        ):
            with self.subTest(detail=detail, size=len(data)):
                members = _read_package_members(self.package)
                members["graphs/sales/graph.json"] = data
                _refresh_manifest(members)
                bad = self.root / "malformed.tarel"
                _write_package_members(bad, members)
                self.assert_cli_failure(["verify", str(bad)], "invalid_package_json", detail)
                with self.assertRaises(PackageFailure):
                    unpack_package(bad, self.destination)
                self.assert_import_removed()

    def test_verify_translates_excessively_nested_manifest_json(self) -> None:
        members = _read_package_members(self.package)
        members["manifest.json"] = b'{"nested":' + b"[" * 10000 + b"0" + b"]" * 10000 + b"}"
        bad = self.root / "nested-manifest.tarel"
        _write_package_members(bad, members)
        self.assert_cli_failure(["verify", str(bad)], "invalid_package_json", "too deeply")

    def test_unpack_translates_a_parent_that_is_a_file(self) -> None:
        blocked = self.root / "blocked"
        blocked.write_bytes(b"preserve me")
        self.assert_cli_failure(
            ["unpack", str(self.package), "--destination", str(blocked / "imported")],
            "package_extract_failed",
            "Could not unpack",
        )
        self.assertEqual(blocked.read_bytes(), b"preserve me")

    def test_unpack_translates_staging_setup_permission_errors(self) -> None:
        with patch(
            "tarel.packages.application.tempfile.mkdtemp",
            side_effect=PermissionError(errno.EACCES, "Permission denied"),
        ):
            self.assert_cli_failure(
                ["unpack", str(self.package), "--destination", str(self.destination)],
                "package_extract_failed",
                "Permission denied",
            )
        self.assert_import_removed()

    def test_unpack_cleans_up_after_partial_write_or_publication_failure(self) -> None:
        for operation in ("shutil.copyfileobj", "os.replace"):
            with (
                self.subTest(operation=operation),
                patch(
                    f"tarel.packages.application.{operation}",
                    side_effect=OSError(errno.ENOSPC, "No space left on device"),
                ),
            ):
                self.assert_cli_failure(
                    ["unpack", str(self.package), "--destination", str(self.destination)],
                    "package_extract_failed",
                    "No space left on device",
                )
            self.assert_import_removed()

    def test_unpack_translates_decompression_failure_after_verification(self) -> None:
        with patch(
            "tarel.packages.application.shutil.copyfileobj",
            side_effect=zlib.error("invalid compressed data"),
        ):
            self.assert_cli_failure(
                ["unpack", str(self.package), "--destination", str(self.destination)],
                "invalid_package",
                "Could not extract",
            )
        self.assert_import_removed()

    def test_unpack_preserves_a_destination_created_during_extraction(self) -> None:
        copy = shutil.copyfileobj

        def concurrent_destination(source, sink, *, length):
            self.destination.mkdir(exist_ok=True)
            (self.destination / "existing.txt").write_bytes(b"other writer")
            copy(source, sink, length=length)

        with patch("tarel.packages.application.shutil.copyfileobj", concurrent_destination):
            self.assert_cli_failure(
                ["unpack", str(self.package), "--destination", str(self.destination)],
                "package_destination_exists",
                "appeared during unpacking",
            )
        self.assertEqual((self.destination / "existing.txt").read_bytes(), b"other writer")
        self.assertEqual(list(self.root.glob(".imported-*")), [])

    def test_verify_translates_package_open_and_size_io_errors(self) -> None:
        with patch(
            "tarel.packages.archive.zipfile.ZipFile",
            side_effect=PermissionError(errno.EACCES, "Permission denied"),
        ):
            self.assert_cli_failure(
                ["verify", str(self.package)], "package_read_failed", "Permission denied"
            )
        # A vanished file after successful archive verification must not report
        # a fabricated zero-byte package as successful.
        with patch(
            "tarel.packages.contracts.Path.stat",
            side_effect=FileNotFoundError(errno.ENOENT, "No such file or directory"),
        ):
            self.assert_cli_failure(
                ["verify", str(self.package)], "package_read_failed", "Could not read package size"
            )

    @skipUnless(os.name == "posix", "POSIX symlink and mode semantics")
    def test_unpack_rejects_dangling_destination_symlink_without_following_it(self) -> None:
        absent = self.root / "absent"
        self.destination.symlink_to(absent, target_is_directory=True)
        self.assert_cli_failure(
            ["unpack", str(self.package), "--destination", str(self.destination)],
            "package_destination_exists",
            "never merges",
        )
        self.assertTrue(self.destination.is_symlink())
        self.assertFalse(absent.exists())

    @skipUnless(os.name == "posix", "POSIX symlink semantics")
    def test_verify_translates_symlink_loop_as_a_read_error(self) -> None:
        loop = self.root / "loop.tarel"
        loop.symlink_to(loop)
        self.assert_cli_failure(["verify", str(loop)], "package_read_failed", "Could not read")

    @skipUnless(os.name == "posix", "POSIX permission bits")
    def test_unpack_reports_a_real_unwritable_destination_parent(self) -> None:
        if os.geteuid() == 0:
            self.skipTest("root bypasses mode permissions")
        parent = self.root / "read-only"
        parent.mkdir(mode=0o500)
        try:
            self.assert_cli_failure(
                ["unpack", str(self.package), "--destination", str(parent / "imported")],
                "package_extract_failed",
                "Permission denied",
            )
            self.assertEqual(list(parent.iterdir()), [])
        finally:
            parent.chmod(0o700)

    @skipUnless(os.name == "posix", "POSIX permission bits")
    def test_unpack_keeps_owner_only_modes_under_permissive_umask(self) -> None:
        old_umask = os.umask(0)
        try:
            unpack_package(self.package, self.destination)
        finally:
            os.umask(old_umask)
        for path in (self.destination, *self.destination.rglob("*")):
            with self.subTest(path=path.relative_to(self.destination)):
                expected = 0o700 if path.is_dir() else 0o600
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), expected)
        self.assertEqual(
            (self.destination / "graphs/sales/graph.json").read_bytes(),
            (self.state / "graphs/sales/graph.json").read_bytes(),
        )

    def test_all_package_commands_disclose_snapshot_omissions_without_changing_manifest(self):
        _write_json(self.state / "logical-topology/sales/topology.json", {"fixture": True})
        _write_json(self.state / "graphs/sales/changes/fixture.json", {"fixture": True})
        commands = (
            ["plan", "--state", str(self.state), "--workspace", "team"],
            [
                "pack",
                "--state",
                str(self.state),
                "--workspace",
                "team",
                "--output",
                str(self.root / "disclosed.tarel"),
                "--replace",
            ],
            ["inspect", str(self.package)],
            ["verify", str(self.package)],
            ["unpack", str(self.package), "--destination", str(self.destination)],
        )
        for command in commands:
            for output_format in ("text", "json"):
                with self.subTest(command=command[0], output_format=output_format):
                    output = StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(main(["package", *command, "--format", output_format]), 0)
                    if output_format == "json":
                        self.assertEqual(
                            json.loads(output.getvalue())["omissions"],
                            list(OMISSIONS + SNAPSHOT_OMISSIONS),
                        )
                    else:
                        for omission in SNAPSHOT_OMISSIONS:
                            self.assertIn(omission, output.getvalue())
                    if command[0] == "unpack":
                        shutil.rmtree(self.destination)
        manifest = json.loads(_read_package_members(self.root / "disclosed.tarel")["manifest.json"])
        self.assertEqual(manifest["omissions"], list(OMISSIONS))
        self.assertEqual(manifest["contract_version"], "tarel.package.v0.2")
