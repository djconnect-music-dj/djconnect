"""Snapshot validation and predecessor projection must never alter caller data."""
from copy import deepcopy
from pathlib import Path
import unittest
from validate_snapshot import load, validate
from web_first_delta import strip


class SnapshotImmutabilityTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name("djconnect-platform-v1.json"))

    def test_accepted_current_snapshot_is_not_mutated(self):
        before = deepcopy(self.plan)
        self.assertEqual(validate(self.plan), [])
        self.assertEqual(self.plan, before)

    def test_rejected_current_and_predecessor_claims_are_not_mutated(self):
        for mode in ("installation", "prior_owner", "cycle"):
            with self.subTest(mode=mode):
                plan = deepcopy(self.plan)
                delta = plan["planning_maintenance"]
                if mode == "installation":
                    delta["music_canvas_finalization_receipt"]["installed"] = "PASS"
                elif mode == "prior_owner":
                    next(n for n in delta["nodes"] if n["id"] == "MUSIC-CANVAS::PRODUCER")["lane"] = "DJC-APPLE"
                else:
                    edge = deepcopy(delta["edges"][0])
                    edge.update(id="IMMUTABILITY-CYCLE", producer=edge["consumer"], consumer=edge["producer"])
                    delta["edges"].append(edge)
                before = deepcopy(plan)
                self.assertTrue(validate(plan))
                self.assertEqual(plan, before)

    def test_web_predecessor_projection_can_be_changed_without_touching_caller(self):
        before = deepcopy(self.plan)
        result = strip(self.plan)
        result["planning_maintenance"]["schema_version"] = "probe"
        result["planning_maintenance"]["nodes"].append({"id": "probe"})
        self.assertEqual(self.plan, before)
