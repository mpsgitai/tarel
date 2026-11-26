"""Run pip as a subprocess of the current interpreter, with failures turned into BundleFailure."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from tarel.bundle.contracts import BundleFailure, Target
from tarel.bundle.targets import pip_platforms

_CREDENTIALS = re.compile(r"(://)[^/@\s]+@")
_TAIL_LINES = 12


def run_pip(arguments: Sequence[str], *, python: Path | None = None, code: str) -> str:
    """Run ``python -m pip`` and return stdout; raise with pip's last error lines on failure."""
    # -P: never import from the working directory, which may be a shared download folder; a
    # planted pip/ package there would otherwise run before any hash or target check.
    command = [str(python or sys.executable), "-P", "-m", "pip", "--disable-pip-version-check"]
    command += ["--no-input", *arguments]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise BundleFailure("bundle_pip_unavailable", f"Could not start pip: {exc}") from exc
    if completed.returncode != 0:
        raise BundleFailure(code, _pip_error(completed.stderr or completed.stdout))
    return completed.stdout


def ensure_pip() -> None:
    run_pip(["--version"], code="bundle_pip_unavailable")


def _pip_error(output: str) -> str:
    # pip echoes index URLs; never let credentials from a private index reach the terminal.
    lines = [_CREDENTIALS.sub(r"\1***@", line) for line in output.strip().splitlines()]
    return "pip failed:\n" + "\n".join(lines[-_TAIL_LINES:])


def target_arguments(target: Target) -> list[str]:
    """pip options that select wheels for ``target`` instead of for this machine."""
    minor = target.python.split(".")[1]
    arguments = ["--only-binary=:all:", "--implementation", "cp"]
    arguments += ["--python-version", target.python, "--abi", f"cp3{minor}"]
    for tag in pip_platforms(target):
        arguments += ["--platform", tag]
    return arguments
