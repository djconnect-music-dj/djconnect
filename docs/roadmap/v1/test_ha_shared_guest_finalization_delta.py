"""Source publication reconciliation cannot close independent acceptance gates."""
from copy import deepcopy
from pathlib import Path
import unittest
from validate_snapshot import load, validate


class SharedGuestFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name('djconnect-platform-v1.json'))

    def test_current_shared_source_is_delivered_but_all_broader_owners_stay_open(self):
        self.assertEqual(validate(self.plan), [])
        receipt = self.plan['planning_maintenance']['ha_shared_guest_finalization_receipt']
        self.assertEqual(receipt['source_delivery'], 'PROTECTED_MERGED')
        self.assertEqual(receipt['stage3'], 'SOURCE_DELIVERED_WITH_OPEN_ACCEPTANCE')
        nodes = {n['id']:n for n in self.plan['planning_maintenance']['nodes']}
        self.assertEqual(nodes['HA-NATIVE-VOICE::ACCEPTANCE']['status'], 'Planned')
        for name in self.plan['planning_maintenance']['ha_shared_guest_receipt']['selected_nodes']:
            self.assertEqual(nodes[name]['status'], 'In progress')

    def test_publication_identity_and_all_acceptance_boundaries_are_enforced(self):
        for field, value in (('source_delivery', 'UNPUBLISHED'), ('stage3', 'COMPLETED'),
                ('overall_acceptance', 'PASS'), ('browser_receiver_acceptance', 'PASS'),
                ('installed', 'PASS'), ('deployment', 'PASS'), ('physical_satellite', 'PASS'),
                ('real_provider', 'PASS'), ('automatic_dispatch', True), ('consumer_writes', True),
                ('predecessor_sha256', '0'*64), ('source_readback_sha256', '0'*64), ('documents', [])):
            with self.subTest(field=field):
                plan = deepcopy(self.plan)
                plan['planning_maintenance']['ha_shared_guest_finalization_receipt'][field] = value
                self.assertTrue(validate(plan))

    def test_historical_local_source_receipt_and_selected_nodes_cannot_be_rewritten(self):
        plan = deepcopy(self.plan)
        plan['planning_maintenance']['ha_shared_guest_receipt']['source_delivery'] = 'PROTECTED_MERGED'
        self.assertTrue(validate(plan))
        for name in ('WEB::CHAT', 'WEB::ENQUEUE', 'WEB::MEDIA', 'HA-NATIVE-VOICE::ACCEPTANCE'):
            plan = deepcopy(self.plan)
            next(n for n in plan['planning_maintenance']['nodes'] if n['id'] == name)['status'] = 'Completed'
            self.assertTrue(validate(plan))
