"""Source delivery cannot masquerade as installed or editorial acceptance."""

from copy import deepcopy
from pathlib import Path
import hashlib
import json
from unittest.mock import patch
import unittest
from validate_snapshot import load, validate


class MusicOriginFinalizationTest(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name("djconnect-platform-v1.json"))

    def test_source_only_completion_preserves_joint_acceptance(self):
        self.assertEqual(validate(self.plan), [])
        nodes = [n for n in self.plan["planning_maintenance"]["nodes"] if n["id"].startswith("MUSIC-ORIGIN::")]
        self.assertEqual({n["id"] for n in nodes if n["status"] == "Planned"}, {"MUSIC-ORIGIN::ACCEPTANCE"})

    def test_wrong_source_dispatch_installation_or_rehashed_readback_is_rejected(self):
        for field, value in [("documents", []), ("source_delivery", "LOCAL"), ("automatic_dispatch", True),
                             ("automatic_dispatch", 0), ("consumer_writes", True),
                             ("installed", "PASS"), ("live_model", "PASS"),
                             ("overall_acceptance", "PASS"), ("source_readback_sha256", "0" * 64),
                             ("predecessor_sha256", "0" * 64)]:
            with self.subTest(field=field, value=value):
                p = deepcopy(self.plan)
                p["planning_maintenance"]["music_origin_finalization_receipt"][field] = value
                self.assertTrue(validate(p))

    def test_rehashed_wrong_main_readback_does_not_become_authority(self):
        from music_origin_finalization_delta import READBACK, ROOT
        path = ROOT / READBACK
        original = Path.read_bytes
        readback = json.loads(original(path))
        readback["apple"]["main_sha"] = "0" * 40
        raw = json.dumps(readback, indent=2).encode()
        plan = deepcopy(self.plan)
        plan["planning_maintenance"]["music_origin_finalization_receipt"]["source_readback_sha256"] = hashlib.sha256(raw).hexdigest()
        with patch.object(Path, "read_bytes", lambda current: raw if current == path else original(current)):
            self.assertTrue(validate(plan))
