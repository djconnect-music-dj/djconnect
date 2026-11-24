"""Isolate genuine local TLS/WS from the legacy suite's synthetic HTTP modules."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class CastDisplayTransportTests(unittest.TestCase):
    def test_real_tls_CORS_claim_collect_B_writer_renew_and_withdrawal(self):
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            [sys.executable, "-B", "-m", "tests.cast_display_transport_runner", "-q"],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Ran 3 tests", result.stderr)
        self.assertIn("OK", result.stderr)
