"""Regression coverage for the read-only macOS host verifier."""
from pathlib import Path
import subprocess
import unittest

HOST_BOOTSTRAP_PACKAGE = Path(__file__).resolve().parents[1] / "scripts/runner/macos_host_bootstrap"


class HostBootstrapProbeClassificationTest(unittest.TestCase):
    def test_crontab_and_tailscale_distinguish_unavailable_from_drift(self) -> None:
        command = r"""
source "$1"
VERIFY_DRIFT_COUNT=0
VERIFY_UNVERIFIED_COUNT=0
verify_cron_entry cron 'expected' 126 'Operation not permitted'
verify_cron_entry cron 'expected' 0 'some other entry'
verify_cron_entry cron 'expected' 0 'expected'
verify_tailscale_preference tailscale disabled 'not JSON' '.RunSSH'
verify_tailscale_preference tailscale disabled '{}' '.RunSSH'
verify_tailscale_preference tailscale disabled '{"RunSSH":true}' '.RunSSH'
verify_tailscale_preference tailscale disabled '{"RunSSH":false}' '.RunSSH'
printf '%s %s\n' "$VERIFY_DRIFT_COUNT" "$VERIFY_UNVERIFIED_COUNT"
"""
        result = subprocess.run(
            ["/bin/bash", "-c", command, "probe-test", str(HOST_BOOTSTRAP_PACKAGE / "core.sh")],
            text=True,
            capture_output=True,
            check=True,
        )
        rows = result.stdout.splitlines()
        self.assertEqual(
            [row.split("|")[-2].strip() for row in rows[:-1]],
            ["UNVERIFIED", "DRIFT", "MATCH", "UNVERIFIED", "UNVERIFIED", "DRIFT", "MATCH"],
        )
        self.assertEqual(rows[-1], "2 3")
