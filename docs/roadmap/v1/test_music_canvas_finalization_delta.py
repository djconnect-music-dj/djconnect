"""Source reconciliation cannot grant physical/provider/installation authority."""
from copy import deepcopy
from pathlib import Path
import unittest
import hashlib
import json
from unittest.mock import patch
from validate_snapshot import load, validate


class CanvasFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name("djconnect-platform-v1.json"))

    def test_only_source_leaves_complete_and_acceptance_stays_planned(self):
        self.assertEqual(validate(self.plan), [])
        nodes = [n for n in self.plan["planning_maintenance"]["nodes"] if n["id"].startswith("MUSIC-CANVAS::")]
        self.assertEqual({n["id"] for n in nodes if n["status"] == "Planned"}, {"MUSIC-CANVAS::ACCEPTANCE"})

    def test_false_install_dispatch_readback_or_document_claim_is_rejected(self):
        for key, value in (("installed", "PASS"), ("deployment", "PASS"), ("native", "PASS"), ("live_model", "PASS"), ("physical_acceptance", "PASS"),
                           ("overall_acceptance", "PASS"), ("automatic_dispatch", True),
                           ("automatic_dispatch", 0), ("consumer_writes", True),
                           ("source_readback_sha256", "0"*64), ("predecessor_sha256", "0"*64), ("documents", [])):
            with self.subTest(key=key):
                plan = deepcopy(self.plan)
                plan["planning_maintenance"]["music_canvas_finalization_receipt"][key] = value
                self.assertTrue(validate(plan))

    def test_original_predecessor_and_acceptance_cannot_be_modified(self):
        for target in ("MUSIC-CANVAS::ACCEPTANCE", "MUSIC-ORIGIN::PRODUCER"):
            plan = deepcopy(self.plan)
            next(n for n in plan["planning_maintenance"]["nodes"] if n["id"] == target)["status"] = "Completed" if target.endswith("ACCEPTANCE") else "Planned"
            self.assertTrue(validate(plan), target)

    def test_rehashed_wrong_main_cannot_become_publication_authority(self):
        from music_canvas_finalization_delta import READBACK, ROOT
        path = ROOT/READBACK
        original = Path.read_bytes
        value = json.loads(original(path))
        value["apple"]["main_sha"] = "0"*40
        raw = json.dumps(value,indent=2).encode()
        plan = deepcopy(self.plan)
        plan["planning_maintenance"]["music_canvas_finalization_receipt"]["source_readback_sha256"] = hashlib.sha256(raw).hexdigest()
        with patch.object(Path, "read_bytes", lambda current: raw if current == path else original(current)):
            self.assertTrue(validate(plan))
