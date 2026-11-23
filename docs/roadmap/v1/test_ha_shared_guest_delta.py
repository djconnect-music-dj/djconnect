"""Shared source must retain exact predecessors and independent acceptance gates."""
from copy import deepcopy
from pathlib import Path
import unittest
from validate_snapshot import load, validate


class SharedGuestPlanningTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name('djconnect-platform-v1.json'))

    def test_current_source_and_existing_web_owners_remain_in_progress(self):
        self.assertEqual(validate(self.plan), [])
        nodes = {n['id']:n for n in self.plan['planning_maintenance']['nodes']}
        receipt = self.plan['planning_maintenance']['ha_shared_guest_receipt']
        self.assertEqual(receipt['product_file_count'], 343)
        for name in receipt['selected_nodes']:
            self.assertEqual(nodes[name]['status'], 'In progress')
        self.assertEqual(nodes['HA-NATIVE-VOICE::ACCEPTANCE']['status'], 'Planned')

    def test_no_merge_install_provider_or_completion_claim_can_be_borrowed(self):
        for field, value in (('source_delivery', 'PROTECTED_MERGED'), ('stage3', 'SOURCE_DELIVERED'),
                ('installed', 'PASS'), ('deployment', 'PASS'), ('physical_satellite', 'PASS'),
                ('real_provider', 'PASS'), ('overall_acceptance', 'PASS'), ('editorial_acceptance', 'PASS'),
                ('automatic_dispatch', True), ('consumer_writes', True), ('product_file_count', 331),
                ('product_manifest_sha256', '0'*64), ('qualification_sha256', '0'*64), ('predecessor_sha256', '0'*64),
                ('documents', []), ('predecessor_documents', []), ('selected_nodes', [])):
            with self.subTest(field=field):
                plan = deepcopy(self.plan)
                plan['planning_maintenance']['ha_shared_guest_receipt'][field] = value
                self.assertTrue(validate(plan))

    def test_inherited_scopes_edges_and_old_delivery_receipts_are_immutable(self):
        for name in ('WEB::CHAT', 'WEB::BROWSER', 'WEB::MEDIA', 'HA-NATIVE-VOICE::ACCEPTANCE'):
            with self.subTest(node=name):
                plan = deepcopy(self.plan)
                next(n for n in plan['planning_maintenance']['nodes'] if n['id'] == name)['status'] = 'Completed'
                self.assertTrue(validate(plan))
        plan = deepcopy(self.plan)
        plan['planning_maintenance']['edges'].pop()
        self.assertTrue(validate(plan))
        plan = deepcopy(self.plan)
        plan['planning_maintenance']['ha_native_voice_finalization_receipt']['stage3'] = 'SOURCE_DELIVERED'
        self.assertTrue(validate(plan))
