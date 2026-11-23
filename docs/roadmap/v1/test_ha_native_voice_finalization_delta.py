"""Partial source delivery cannot close shared work or borrow publication authority."""
from copy import deepcopy
from pathlib import Path
import unittest
from validate_snapshot import load, validate


class NativeVoiceFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name('djconnect-platform-v1.json'))

    def test_first_two_stages_delivered_without_completing_existing_nodes(self):
        self.assertEqual(validate(self.plan), [])
        receipt = self.plan['planning_maintenance']['ha_native_voice_finalization_receipt']
        self.assertEqual(receipt['stage1'], 'SOURCE_DELIVERED')
        self.assertEqual(receipt['stage2'], 'SOURCE_DELIVERED')
        nodes = {n['id']:n for n in self.plan['planning_maintenance']['nodes']}
        self.assertEqual(nodes['HA-NATIVE-VOICE::ADOPTION']['status'], 'In progress')
        self.assertEqual(nodes['HA-NATIVE-VOICE::ACCEPTANCE']['status'], 'Planned')
        self.assertEqual(nodes['WEB::ENQUEUE']['status'], 'Planned')

    def test_false_shared_install_dispatch_or_publication_claim_is_rejected(self):
        for key, value in (('stage3', 'SOURCE_DELIVERED'), ('overall_acceptance', 'PASS'),
                           ('installed', 'PASS'), ('deployment', 'PASS'), ('real_provider', 'PASS'),
                           ('physical_satellite', 'PASS'), ('automatic_dispatch', True),
                           ('consumer_writes', True), ('source_delivery', 'UNPUBLISHED'),
                           ('predecessor_sha256', '0'*64), ('source_readback_sha256', '0'*64),
                           ('documents', [])):
            with self.subTest(key=key):
                plan = deepcopy(self.plan)
                plan['planning_maintenance']['ha_native_voice_finalization_receipt'][key] = value
                self.assertTrue(validate(plan))

    def test_inherited_source_evidence_and_open_work_cannot_be_rewritten(self):
        for target in ('HA-NATIVE-VOICE::ADOPTION', 'HA-NATIVE-VOICE::ACCEPTANCE', 'WEB::ENQUEUE'):
            plan = deepcopy(self.plan)
            next(n for n in plan['planning_maintenance']['nodes'] if n['id'] == target)['status'] = 'Completed'
            self.assertTrue(validate(plan), target)
        plan = deepcopy(self.plan)
        plan['planning_maintenance']['ha_native_voice_receipt']['source_delivery'] = 'PROTECTED_MERGED'
        self.assertTrue(validate(plan))
