"""Build one offline bundle: collect wheels, pin them by hash, prove they install, and zip them."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from tarel.bundle.contracts import (
    BUNDLE_FORMAT,
    BundledPackage,
    BundleFailure,
    BundlePlan,
    BundleReport,
    InstallCheck,
    Target,
)
from tarel.bundle.pip import ensure_pip, run_pip, target_arguments
from tarel.bundle.resolve import complete_for_target, wheel_metadata
from tarel.bundle.targets import can_test_install, host_target

StepCallback = Callable[[str], None]

_WHEEL_NAME = re.compile(r"(?P<name>[^-]+)-(?P<version>[^-]+)(?:-\d[^-]*)?-[^-]+-[^-]+-[^-]+\.whl")
_LICENSE_FILE = re.compile(r"(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.IGNORECASE)
# 1980-01-01 is the earliest ZIP timestamp; a fixed one keeps bundles byte-identical.
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def build_bundle(
    plan: BundlePlan,
    output: Path,
    *,
    tarel_from: Path | None,
    on_step: StepCallback,
) -> BundleReport:
    ensure_pip()
    with tempfile.TemporaryDirectory(prefix="tarel-bundle-") as scratch:
        root = Path(scratch)
        local = root / "local"
        wheels = root / "bundle" / "wheels"
        local.mkdir()
        wheels.mkdir(parents=True)

        hub = [c for c in plan.components if c.hub_path is not None]
        if hub or tarel_from is not None:
            on_step("Building local packages")
            if tarel_from is not None:
                _build_local(tarel_from, local)
            for component in hub:
                assert component.hub_path is not None
                _build_local(component.hub_path, local)

        def download(requirements: list[str]) -> None:
            try:
                _download(requirements)
            except BundleFailure as exc:
                if "No matching distribution" not in str(exc):
                    raise
                raise BundleFailure(
                    exc.code,
                    f"{exc}\n\nA package above publishes no wheel for {plan.target.label}. "
                    "Choose a newer target (for macOS, its real version from the profile) "
                    "or leave out that component.",
                ) from exc

        def _download(requirements: list[str]) -> None:
            run_pip(
                [
                    "download",
                    "--dest",
                    str(wheels),
                    "--find-links",
                    str(local),
                    *target_arguments(plan.target),
                    *requirements,
                ],
                code="bundle_download_failed",
            )

        on_step(f"Downloading packages for {plan.target.label}")
        download(list(plan.requirements))
        complete_for_target(wheels, plan.requirements, plan.target, download)

        on_step("Pinning every file by its SHA-256 hash")
        packages = _write_lock(wheels, root / "bundle" / "requirements.lock")
        _write_licenses(wheels, root / "bundle")
        _write_text(root / "bundle" / "INSTALL.md", _install_guide(plan.target))
        _write_text(root / "bundle" / "bundle.json", _manifest(plan, packages))

        install_check = _check_install(plan, root, on_step)

        on_step("Writing the bundle")
        _write_zip(root / "bundle", output)
    return BundleReport(
        path=output,
        size_bytes=output.stat().st_size,
        target=plan.target,
        packages=packages,
        install_check=install_check,
        notes=_notes(install_check),
    )


def _build_local(source: Path, destination: Path) -> None:
    if source.is_file() and source.suffix == ".whl":
        destination.joinpath(source.name).write_bytes(source.read_bytes())
        return
    if not (source / "pyproject.toml").is_file():
        raise BundleFailure("bundle_local_source", f"Not a wheel or a Python project: {source}.")
    run_pip(
        ["wheel", "--no-deps", "--wheel-dir", str(destination), str(source)],
        code="bundle_local_build_failed",
    )


def _wheel_files(wheels: Path) -> list[Path]:
    files = sorted(wheels.iterdir())
    foreign = [path.name for path in files if path.suffix != ".whl"]
    if foreign:
        # --only-binary should make this impossible; refuse rather than ship a source build.
        raise BundleFailure("bundle_not_a_wheel", f"Not a wheel: {', '.join(foreign)}.")
    return files


def _write_lock(wheels: Path, lock: Path) -> tuple[BundledPackage, ...]:
    lines = [
        "# Every file in wheels/, pinned by hash. Install with:",
        "#   pip install --no-index --find-links wheels --require-hashes -r requirements.lock",
    ]
    packages = []
    for path in _wheel_files(wheels):
        match = _WHEEL_NAME.fullmatch(path.name)
        if match is None:
            raise BundleFailure("bundle_wheel_name", f"Unreadable wheel file name: {path.name}.")
        name = re.sub(r"[-_.]+", "-", match.group("name")).lower()
        version = match.group("version")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{name}=={version} \\\n    --hash=sha256:{digest}")
        packages.append(BundledPackage(name=name, version=version, license=_license_of(path)))
    _write_text(lock, "\n".join(lines) + "\n")
    return tuple(packages)


def _license_of(wheel: Path) -> str:
    metadata = wheel_metadata(wheel)
    expression = metadata.get("License-Expression")
    if expression:
        return str(expression)
    classifiers = [
        str(value).rsplit(" :: ", 1)[-1]
        for value in metadata.get_all("Classifier", [])
        if str(value).startswith("License :: ")
    ]
    if classifiers:
        return " / ".join(classifiers)
    declared = str(metadata.get("License", "")).strip()
    return declared if declared and "\n" not in declared and len(declared) < 60 else "unknown"


def _write_licenses(wheels: Path, bundle: Path) -> None:
    """Copy every license file the wheels carry; LGPL drivers require shipping their terms."""
    for path in _wheel_files(wheels):
        name = path.name.split("-", 1)[0]
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                parts = PurePosixPath(member).parts
                if not parts or not parts[0].endswith(".dist-info") or member.endswith("/"):
                    continue
                if "licenses" in parts[1:-1] or _LICENSE_FILE.match(parts[-1]):
                    inner = parts[2:] if parts[1] == "licenses" else parts[1:]
                    target = bundle / "licenses" / name / Path(*inner)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(member))


def _check_install(plan: BundlePlan, root: Path, on_step: StepCallback) -> InstallCheck:
    bundle = root / "bundle"
    install = [
        "install",
        "--no-index",
        "--find-links",
        str(bundle / "wheels"),
        "--require-hashes",
        "-r",
        str(bundle / "requirements.lock"),
    ]
    if not can_test_install(plan.target, host_target()):
        on_step("Checking that the bundle resolves offline for the target")
        # pip evaluates markers for this Python even here, so dependencies stay with
        # complete_for_target; the dry run proves tags, Requires-Python and hashes per file.
        dry_run = ["--dry-run", "--no-deps", "--ignore-installed", "--target", str(root / "dry")]
        run_pip([*install, *dry_run, *target_arguments(plan.target)], code="bundle_check_failed")
        return "resolved"

    on_step("Installing into a clean environment, without internet")
    venv = root / "venv"
    _run([sys.executable, "-m", "venv", str(venv)], "bundle_venv_failed")
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run_pip(install, python=python, code="bundle_check_failed")
    imports = ["tarel", *(c.import_name for c in plan.components if c.import_name)]
    _run(
        [str(python), "-I", "-c", "import " + ", ".join(imports)],
        "bundle_import_failed",
        lead="The bundle installed, but a package does not import:",
    )
    return "installed"


def _run(command: list[str], code: str, *, lead: str = "Command failed:") -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout).strip().splitlines()[-8:]
        raise BundleFailure(code, "\n".join([lead, *tail]))


def _notes(install_check: InstallCheck) -> tuple[str, ...]:
    if install_check == "installed":
        return ()
    return (
        "This machine is a different platform, so the bundle was resolved for the target "
        "but not installed. Install it once on a matching test machine before rollout.",
    )


def _manifest(plan: BundlePlan, packages: tuple[BundledPackage, ...]) -> str:
    # No timestamps, host names, or paths: the bundle may cross into a restricted network.
    data = {
        "format": BUNDLE_FORMAT,
        "tarel": plan.tarel_version,
        "target": plan.target.to_dict(),
        "components": [c.id for c in plan.components],
        "packages": [
            {"name": p.name, "version": p.version, "license": p.license} for p in packages
        ],
    }
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def _install_guide(target: Target) -> str:
    if target.os == "windows":
        python = f"py -{target.python}"
        venv_python, tarel = r".venv\Scripts\python", r".venv\Scripts\tarel"
    else:
        python = f"python{target.python}"
        venv_python, tarel = ".venv/bin/python", ".venv/bin/tarel"
    return f"""# Install TAREL offline

Target: {target.label}

No internet connection is needed. Run these commands inside this folder:

```
{python} -m venv .venv
{venv_python} -m pip install --no-index --find-links wheels --require-hashes -r requirements.lock
{tarel} --version
```

`--no-index` stops pip from contacting any server. `--require-hashes` makes pip refuse any file
whose SHA-256 differs from `requirements.lock`, so a damaged or swapped file stops the install.

Contents: `wheels/` (unmodified wheels as published upstream, plus locally built TAREL hub
packages), `requirements.lock`, `bundle.json` (what is inside), and `licenses/`.
"""


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_zip(source: Path, output: Path) -> None:
    folder = output.stem
    partial = output.with_name(output.name + ".partial")
    try:
        _zip_folder(source, partial, folder)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(output)


def _zip_folder(source: Path, destination: Path, folder: str) -> None:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(f"{folder}/{relative}", date_time=_ZIP_TIME)
            info.external_attr = 0o644 << 16
            # Wheels are already compressed; storing them keeps the build fast.
            stored = path.suffix == ".whl"
            info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
