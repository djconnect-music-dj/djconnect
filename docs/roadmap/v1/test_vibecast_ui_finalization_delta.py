"""Publication closeout preserves the exact source and cannot grant device acceptance."""
import copy
import unittest
from pathlib import Path
from validate_snapshot import load, validate

ROOT = Path(__file__).resolve().parent


class VibeCastUIFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(ROOT/'djconnect-platform-v1.json')

    def test_actual_publication_preserves_complete_source_predecessor(self):
        self.assertEqual(validate(self.plan), [])
        restored = copy.deepcopy(self.plan['planning_maintenance'])
        restored.pop('vibecast_baseline_receipt')
        restored.pop('vibecast_ui_finalization_receipt')
        restored['schema_version'] = 'djconnect-federated-planning-delta/31'
        self.assertEqual(restored, load(ROOT/'history/20261124/vibecast-ui-source-freeze-maintenance-v31.json'))

    def test_publication_cannot_grant_install_or_device_acceptance(self):
        for key, value in [('installed', 'PASS'), ('deployment', 'PASS'),
                           ('physical_satellite', 'PASS'), ('real_provider', 'PASS'),
                           ('overall_acceptance', 'PASS'), ('automatic_dispatch', True),
                           ('consumer_writes', True), ('source_delivery', 'LOCAL'),
                           ('source_readback_sha256', '0'*64), ('predecessor_sha256', '0'*64)]:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.plan)
                changed['planning_maintenance']['vibecast_ui_finalization_receipt'][key] = value
                self.assertTrue(validate(changed))

    def test_prior_source_and_original_dependency_tampering_rejected(self):
        changed = copy.deepcopy(self.plan)
        changed['planning_maintenance']['vibecast_ui_receipt']['overall_acceptance'] = 'PASS'
        self.assertTrue(validate(changed))
        changed = copy.deepcopy(self.plan)
        changed['planning_maintenance']['edges'].pop()
        self.assertTrue(validate(changed))
