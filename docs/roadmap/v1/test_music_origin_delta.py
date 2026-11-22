"""New selection must never rewrite predecessor or claim runtime acceptance."""

from copy import deepcopy
import unittest
from pathlib import Path
from validate_snapshot import load, validate


class MusicOriginDeltaTest(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name("djconnect-platform-v1.json"))
        # Preserve the original source-freeze negative cases after source delivery.
        if self.plan["planning_maintenance"]["schema_version"] in {"djconnect-federated-planning-delta/22", "djconnect-federated-planning-delta/23", "djconnect-federated-planning-delta/24"}:
            from experience_reconciliation_delta import HISTORICAL_DOCUMENT_SOURCES
            refs = self.plan["planning_maintenance"].get("music_canvas_receipt", {}).get("predecessor_documents", [])
            root = Path(__file__).resolve().parents[3]
            token = HISTORICAL_DOCUMENT_SOURCES.set({r["path"]: root/r["snapshot"] for r in refs})
            self.addCleanup(HISTORICAL_DOCUMENT_SOURCES.reset, token)
            self.plan["planning_maintenance"] = load(Path(__file__).parent / "history/20261122/music-origin-source-freeze-maintenance-v21.json")

    def test_selected_contract_producer_and_native_slices_have_open_joint_acceptance(self):
        self.assertEqual(validate(self.plan), [])
        d = self.plan["planning_maintenance"]
        self.assertEqual(len([n for n in d["nodes"] if n["id"].startswith("MUSIC-ORIGIN::")]), 4)
        self.assertEqual(d["music_origin_receipt"]["overall_acceptance"], "OPEN")

    def test_prior_design_dispatch_and_consumer_ownership_cannot_be_silently_changed(self):
        for mutation in [
            "predecessor",
            "dispatch",
            "installed",
            "source",
            "native_owner",
            "dependency",
            "design_digest",
        ]:
            with self.subTest(mutation=mutation):
                plan = deepcopy(self.plan)
                d = plan["planning_maintenance"]
                r = d["music_origin_receipt"]
                if mutation == "predecessor":
                    d["nodes"][0]["title"] = "altered predecessor"
                elif mutation == "dispatch":
                    r["automatic_dispatch"] = True
                elif mutation == "installed":
                    r["installed"] = "PASS"
                elif mutation == "source":
                    r["source_delivery"] = "PROTECTED_MERGED"
                elif mutation == "native_owner":
                    next(n for n in d["nodes"] if n["id"] == "MUSIC-ORIGIN::APPLE")["lane"] = (
                        "DJC-CORE"
                    )
                elif mutation == "dependency":
                    next(e for e in d["edges"] if e["id"].startswith("MUSIC-ORIGIN-"))[
                        "hard_precedence"
                    ] = False
                else:
                    r["documents"][0]["sha256"] = "0" * 64
                self.assertTrue(validate(plan))
