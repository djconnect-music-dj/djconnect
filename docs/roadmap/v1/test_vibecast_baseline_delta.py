"""Combining validated source preserves earlier evidence and acceptance scope."""

from copy import deepcopy
from pathlib import Path
import unittest

from validate_snapshot import load, validate
from vibecast_baseline_delta import FREEZE


class VibeCastBaselineTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name("djconnect-platform-v1.json"))

    def test_preserves_delivered_predecessor(self):
        self.assertEqual(validate(self.plan), [])
        previous = deepcopy(self.plan["planning_maintenance"])
        previous.pop("vibecast_baseline_receipt")
        frozen = load(FREEZE)
        previous["schema_version"] = frozen["schema_version"]
        self.assertEqual(previous, frozen)

    def test_refuses_forged_proof_or_installed_acceptance(self):
        for key, value in (
            ("installed", "PASS"),
            ("physical_satellite", "PASS"),
            ("overall_acceptance", "PASS"),
            ("predecessor_sha256", "0" * 64),
            ("evidence", {}),
        ):
            with self.subTest(key=key):
                changed = deepcopy(self.plan)
                changed["planning_maintenance"]["vibecast_baseline_receipt"][key] = value
                self.assertTrue(validate(changed), key)
