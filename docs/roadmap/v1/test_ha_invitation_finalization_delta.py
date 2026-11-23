"""Merge reconciliation preserves the narrow browser repair and broader open gates."""
from copy import deepcopy
from pathlib import Path
import unittest
from validate_snapshot import load, validate


class InvitationFinalizationTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name('djconnect-platform-v1.json'))

    def test_source_repair_delivered_without_claiming_broader_acceptance(self):
        self.assertEqual(validate(self.plan), [])
        receipt = self.plan['planning_maintenance']['ha_invitation_finalization_receipt']
        self.assertEqual(receipt['repair_delivery'], 'SOURCE_DELIVERED')
        self.assertEqual(receipt['source_delivery'], 'PROTECTED_MERGED')
        nodes = {n['id']:n for n in self.plan['planning_maintenance']['nodes']}
        self.assertEqual(nodes['WEB::BROWSER']['status'], 'In progress')
        self.assertEqual(nodes['HA-NATIVE-VOICE::ACCEPTANCE']['status'], 'Planned')

    def test_readback_identity_and_no_install_or_completion_overclaim(self):
        for field, value in (('source_delivery','UNPUBLISHED'), ('repair_delivery','COMPLETE'),
                ('broader_browser_receiver_acceptance','PASS'), ('overall_acceptance','PASS'),
                ('installed','PASS'), ('deployment','PASS'), ('real_provider','PASS'),
                ('physical_satellite','PASS'), ('automatic_dispatch',True), ('consumer_writes',True),
                ('predecessor_sha256','0'*64), ('source_readback_sha256','0'*64), ('documents',[])):
            with self.subTest(field=field):
                plan = deepcopy(self.plan)
                plan['planning_maintenance']['ha_invitation_finalization_receipt'][field] = value
                self.assertTrue(validate(plan))

    def test_historical_repair_authority_and_product_gates_stay_immutable(self):
        for field, value in (('source_delivery','PROTECTED_MERGED'), ('workspace_exception','DELETE_BRANCH')):
            plan = deepcopy(self.plan)
            plan['planning_maintenance']['ha_guest_invitation_receipt'][field] = value
            self.assertTrue(validate(plan))
        plan = deepcopy(self.plan)
        next(n for n in plan['planning_maintenance']['nodes'] if n['id'] == 'WEB::BROWSER')['status'] = 'Completed'
        self.assertTrue(validate(plan))
