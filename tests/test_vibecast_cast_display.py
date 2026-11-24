"""Closed new CAF protocol tests; no actual Google SDK or TV claim."""

from pathlib import Path
import shutil
import subprocess
import unittest


class CastDisplayProtocolTests(unittest.TestCase):
    def test_closed_CAF_display_protocol_and_secret_custody(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js required")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [node, "--test", str(root / "tests/browser/vibecast_cast_display.mjs")],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pass 5", result.stdout)
