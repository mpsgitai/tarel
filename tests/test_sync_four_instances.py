"""Runs the four-instance proof as part of the suite; see the tool for what it covers."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from unittest import TestCase

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "sync_four_instances.py"


class FourInstanceTests(TestCase):
    def test_every_check_of_the_four_instance_run_passes(self) -> None:
        if shutil.which("ssh-keygen") is None:
            self.skipTest("ssh-keygen is not installed.")

        result = subprocess.run(
            [sys.executable, str(_TOOL)], capture_output=True, text=True, check=False, timeout=300,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(" 0 failed", result.stdout)
        self.assertNotIn("FAIL", result.stdout)
