"""Offline bundles: targets, recipes, hub catalog, marker-aware resolution, files, and the dialog.

Nothing here downloads; pip is only used for its vendored ``packaging``.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tarel import __version__
from tarel.bundle import builder
from tarel.bundle.application import plan_bundle_use_case
from tarel.bundle.contracts import BundleFailure, BundleReport, Recipe, Target
from tarel.bundle.resolve import complete_for_target
from tarel.bundle.targets import (
    PROFILE_COMMAND,
    can_test_install,
    host_profile,
    parse_profile,
    parse_target,
    pip_platforms,
)
from tarel.cli import main
from tarel.cli._bundle_dialog import Cancelled, Dialog
from tarel.cli._terminal import Style

WINDOWS = Target(os="windows", arch="x86_64", python="3.12")


def write_wheel(folder: Path, name: str, version: str, requires: tuple[str, ...] = ()) -> Path:
    path = folder / f"{name}-{version}-py3-none-any.whl"
    metadata = ["Metadata-Version: 2.1", f"Name: {name}", f"Version: {version}"]
    metadata += [f"Requires-Dist: {requirement}" for requirement in requires]
    metadata.append("License-Expression: MIT")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}-{version}.dist-info/METADATA", "\n".join(metadata) + "\n")
        archive.writestr(f"{name}-{version}.dist-info/licenses/LICENSE", "MIT terms\n")
    return path


def write_hub(root: Path) -> Path:
    (root / "catalog").mkdir(parents=True)
    (root / "catalog" / "catalog.toml").write_text(
        """
contract_version = 1
[[extension]]
id = "connector-postgres"
capabilities = ["connector"]
status = "experimental"
package = "tarel-connector-postgres"
import_name = "tarel_connector_postgres"
path = "packages/connector-postgres"

[[extension]]
id = "importer-documents"
capabilities = ["importer"]
status = "planned"

[[extension]]
id = "lineage-sqlglot"
capabilities = ["lineage-analysis"]
status = "experimental"
package = "tarel-lineage-sqlglot"
path = "packages/lineage-sqlglot"
""",
        encoding="utf-8",
    )
    for name, extras in (
        ("connector-postgres", '\n[project.optional-dependencies]\nbinary = ["x"]'),
        ("lineage-sqlglot", ""),
    ):
        package = root / "packages" / name
        package.mkdir(parents=True)
        (package / "pyproject.toml").write_text(
            f'[project]\nname = "tarel-{name}"\n'
            f'description = "Read-only {name} metadata connector for TAREL."\n{extras}\n',
            encoding="utf-8",
        )
    return root


class TargetTests(unittest.TestCase):
    def test_profiles_from_each_system(self) -> None:
        self.assertEqual(parse_profile("tarel-target:1 cpython win-amd64 3.12 AMD64 - -"), WINDOWS)
        linux = parse_profile("tarel-target:1 cpython linux-aarch64 3.13 aarch64 glibc-2.31.1 -")
        self.assertEqual((linux.arch, linux.glibc, linux.slug), ("arm64", "2.31", linux.slug))
        mac = parse_profile("tarel-target:1 cpython macosx-11.0-arm64 3.12 arm64 - 14.5")
        self.assertEqual(mac.macos, "14.0")

    def test_profile_rejections_are_explained(self) -> None:
        cases = {
            "hello": "bundle_profile_invalid",
            "tarel-target:1 pypy win-amd64 3.12 AMD64 - -": "bundle_profile_python",
            "tarel-target:1 cpython linux-x86_64 3.12 x86_64 - -": "bundle_profile_libc",
            "tarel-target:1 cpython win-amd64 3.10 AMD64 - -": "bundle_target_python",
        }
        for line, code in cases.items():
            with self.subTest(line=line), self.assertRaises(BundleFailure) as caught:
                parse_profile(line)
            self.assertEqual(caught.exception.code, code)

    def test_host_profile_round_trips(self) -> None:
        self.assertEqual(parse_target("host"), parse_profile(host_profile()))

    def test_profile_command_survives_every_shell(self) -> None:
        # cmd.exe expands %VAR%, PowerShell and POSIX expand $; one outer pair of double quotes.
        self.assertNotIn("%", PROFILE_COMMAND)
        self.assertNotIn("$", PROFILE_COMMAND)
        self.assertEqual(PROFILE_COMMAND.count('"'), 2)

    def test_slugs_and_platform_tags(self) -> None:
        self.assertEqual(parse_target("windows-x86_64-py3.12"), WINDOWS)
        linux = parse_target("linux-x86_64-py3.11")
        self.assertEqual(linux.glibc, "2.28")
        tags = pip_platforms(parse_target("linux-x86_64-py3.12-glibc2.19"))
        self.assertEqual(
            tags,
            (
                "manylinux_2_19_x86_64",
                "manylinux_2_18_x86_64",
                "manylinux_2_17_x86_64",
                "manylinux2014_x86_64",
            ),
        )
        self.assertEqual(pip_platforms(parse_target("macos-arm64-py3.12")), ("macosx_11_0_arm64",))
        with self.assertRaises(BundleFailure):
            parse_target("solaris-sparc-py3.12")

    def test_install_test_needs_a_compatible_host(self) -> None:
        old = Target(os="linux", arch="x86_64", python="3.12", glibc="2.28")
        new = Target(os="linux", arch="x86_64", python="3.12", glibc="2.39")
        self.assertTrue(can_test_install(old, new))
        self.assertFalse(can_test_install(new, old))
        self.assertFalse(can_test_install(WINDOWS, new))


class RecipeAndPlanTests(unittest.TestCase):
    def test_recipe_round_trips_through_toml(self) -> None:
        recipe = Recipe(
            target=Target(os="linux", arch="arm64", python="3.13", glibc="2.31"),
            components=("sqlserver", "postgres"),
            tarel_version=__version__,
            hub=Path('C:\\hub "x"'),
        )
        self.assertEqual(Recipe.from_toml(recipe.to_toml()), recipe)

    def test_plan_resolves_core_extras_and_hub_packages(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            hub = write_hub(Path(folder))
            recipe = Recipe(WINDOWS, ("postgres", "semantic", "sqlserver"), __version__, hub)
            plan = plan_bundle_use_case(recipe)
        self.assertEqual(
            plan.requirements,
            (f"tarel[semantic,sqlserver]=={__version__}", "tarel-connector-postgres[binary]"),
        )
        self.assertEqual(next(c.id for c in plan.components), "sqlite")
        self.assertNotIn("importer-documents", [c.id for c in plan.components])

    def test_plan_refuses_unknown_parts_and_other_versions(self) -> None:
        with self.assertRaises(BundleFailure) as caught:
            plan_bundle_use_case(Recipe(WINDOWS, ("postgres",), __version__))
        self.assertIn("--hub", str(caught.exception))
        with self.assertRaises(BundleFailure) as caught:
            plan_bundle_use_case(Recipe(WINDOWS, (), "0.0.1"))
        self.assertEqual(caught.exception.code, "bundle_version_mismatch")

    def test_cli_plan_json(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(
                [
                    "bundle",
                    "plan",
                    "--target",
                    "windows-x86_64-py3.12",
                    "--with",
                    "sqlserver",
                    "--format",
                    "json",
                ]
            )
        self.assertEqual(code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["pip_platforms"], ["win_amd64"])
        self.assertEqual(data["requirements"], [f"tarel[sqlserver]=={__version__}"])


class ResolveTests(unittest.TestCase):
    def test_closure_follows_target_markers_not_this_machine(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            wheels = Path(folder)
            write_wheel(
                wheels,
                "app",
                "1.0",
                (
                    'tzdata; sys_platform == "win32"',
                    'linuxonly; sys_platform == "linux"',
                    "lib[fast]>=2",
                ),
            )
            write_wheel(wheels, "lib", "2.1", ('speedup; extra == "fast"', 'slow; extra == "slow"'))
            write_wheel(wheels, "linuxonly", "1.0")
            fetched: list[list[str]] = []

            def download(requirements: list[str]) -> None:
                fetched.append(requirements)
                for requirement in requirements:
                    write_wheel(wheels, requirement.split("[")[0], "1.0")

            complete_for_target(wheels, ["app"], WINDOWS, download)
            names = sorted(path.name.split("-")[0] for path in wheels.glob("*.whl"))
        self.assertEqual(fetched, [["speedup", "tzdata"]])
        self.assertEqual(names, ["app", "lib", "speedup", "tzdata"])

    def test_version_conflict_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            wheels = Path(folder)
            write_wheel(wheels, "app", "1.0", ("lib>=3",))
            write_wheel(wheels, "lib", "2.0")
            with self.assertRaises(BundleFailure) as caught:
                complete_for_target(wheels, ["app"], WINDOWS, lambda _: None)
        self.assertEqual(caught.exception.code, "bundle_resolve_conflict")


class BundleFileTests(unittest.TestCase):
    def test_lock_licenses_and_zip_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bundle = root / "bundle"
            wheels = bundle / "wheels"
            wheels.mkdir(parents=True)
            wheel = write_wheel(wheels, "Some_Pkg", "1.0")
            packages = builder._write_lock(wheels, bundle / "requirements.lock")
            builder._write_licenses(wheels, bundle)
            lock = (bundle / "requirements.lock").read_text(encoding="utf-8")
            digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
            self.assertIn(f"some-pkg==1.0 \\\n    --hash=sha256:{digest}", lock)
            self.assertEqual(packages[0].license, "MIT")
            self.assertTrue((bundle / "licenses" / "Some_Pkg" / "LICENSE").is_file())

            first, second = root / "a" / "b.zip", root / "c" / "b.zip"
            for output in (first, second):
                output.parent.mkdir()
                builder._write_zip(bundle, output)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertIn("b/requirements.lock", archive.namelist())
            self.assertFalse((first.parent / "b.zip.partial").exists())

    def test_install_guide_names_the_offline_flags(self) -> None:
        guide = builder._install_guide(WINDOWS)
        self.assertIn("py -3.12 -m venv .venv", guide)
        self.assertIn("--no-index --find-links wheels --require-hashes", guide)


class DialogTests(unittest.TestCase):
    def run_dialog(self, answers: list[str], folder: Path) -> tuple[list[str], mock.MagicMock]:
        transcript: list[str] = []
        replies = iter(answers)

        def ask(prompt: str) -> str:
            transcript.append(prompt)
            return next(replies)

        report = BundleReport(
            path=folder / "bundle.zip",
            size_bytes=2_500_000,
            target=WINDOWS,
            packages=(),
            install_check="resolved",
            notes=("Resolved only.",),
        )
        dialog = Dialog(
            style=Style(color=False, unicode=True, live=False),
            ask=ask,
            say=transcript.append,
            folder=folder,
        )
        with (
            mock.patch.dict("os.environ", {}, clear=True),
            mock.patch(
                "tarel.cli._bundle_dialog.build_bundle_use_case", return_value=report
            ) as build,
        ):
            dialog.run()
        return transcript, build

    def test_choosing_the_target_by_hand(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            # manual target, Windows, x86-64, 3.12, core only, SQL Server, semantic, confirm.
            answers = ["2", "1", "1", "1", "", "", "1", ""]
            transcript, build = self.run_dialog(answers, Path(folder))
            recipe = build.call_args.args[0]
            saved = Recipe.from_toml(
                (Path(folder) / f"{build.call_args.args[1].stem}.toml").read_text(encoding="utf-8")
            )
        self.assertEqual(recipe.target, WINDOWS)
        self.assertEqual(recipe.components, ("sqlserver", "semantic"))
        self.assertEqual(saved, recipe)
        text = "\n".join(transcript)
        self.assertIn("✓ Windows · x86-64 · Python 3.12", text)
        self.assertIn("Done.", text)

    def test_invalid_answers_are_asked_again_and_no_declines(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            answers = [
                "9",
                "1",
                "nonsense",
                "tarel-target:1 cpython win-amd64 3.12 AMD64 - -",
                "",
                "7",
                "none",
                "none",
                "n",
            ]
            with self.assertRaises(Cancelled):
                self.run_dialog(answers, Path(folder))

    def test_ascii_consoles_get_ascii_symbols(self) -> None:
        stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        style = Style.for_stream(stream)
        self.assertFalse(style.unicode)
        self.assertEqual(style.text("a · b"), "a - b")


if __name__ == "__main__":
    unittest.main()
