"""Negative controls for Canvas ownership, predecessor preservation and claims."""
from copy import deepcopy
from pathlib import Path
import unittest
from validate_snapshot import load, validate


class MusicCanvasPlanningTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).parent/"djconnect-platform-v1.json")

    def test_valid_current_delta_retains_joint_open(self):
        self.assertEqual(validate(self.plan), [])
        nodes = self.plan["planning_maintenance"]["nodes"]
        self.assertEqual(next(n for n in nodes if n["id"] == "MUSIC-CANVAS::ACCEPTANCE")["status"], "Planned")

    def test_prior_delivery_cannot_be_relabelled_or_new_scope_silently_added(self):
        for mutation in ("prior", "new_scope", "claimed_installed", "source_manifest"):
            plan = deepcopy(self.plan)
            d = plan["planning_maintenance"]
            if mutation == "prior":
                next(n for n in d["nodes"] if n["id"] == "MUSIC-ORIGIN::PRODUCER")["status"] = "Planned"
            elif mutation == "new_scope":
                d["nodes"].append({**d["nodes"][-1], "id": "MUSIC-CANVAS::CAST"})
            elif mutation == "claimed_installed":
                d["music_canvas_receipt"]["installed"] = "PASS"
            else:
                d["music_canvas_receipt"]["product_manifest_sha256"] = "0"*64
            self.assertTrue(validate(plan), mutation)

    def test_independent_adapters_cannot_be_made_serial_or_apple_owned(self):
        for mutation in ("edge", "owner"):
            plan = deepcopy(self.plan)
            d = plan["planning_maintenance"]
            if mutation == "edge":
                edge = next(e for e in d["edges"] if e["id"].startswith("MUSIC-CANVAS-"))
                edge["producer"] = "MUSIC-CANVAS::SAMSUNG"
            else:
                next(n for n in d["nodes"] if n["id"] == "MUSIC-CANVAS::PRODUCER")["lane"] = "DJC-APPLE"
            self.assertTrue(validate(plan), mutation)
