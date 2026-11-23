"""The bounded UI correction may not rewrite source/publication or acceptance."""
from copy import deepcopy
from pathlib import Path
import unittest
from validate_snapshot import load, validate


class InvitationRepairPlanningTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name('djconnect-platform-v1.json'))

    def test_current_repair_preserves_existing_nodes_and_open_acceptance(self):
        self.assertEqual(validate(self.plan), [])
        nodes = {n['id']:n for n in self.plan['planning_maintenance']['nodes']}
        self.assertEqual(nodes['WEB::BROWSER']['status'], 'In progress')
        self.assertEqual(nodes['HA-NATIVE-VOICE::ACCEPTANCE']['status'], 'Planned')

    def test_wrong_source_proof_or_authority_expansion_is_rejected(self):
        for field, value in (('source_delivery', 'PROTECTED_MERGED'), ('overall_acceptance', 'PASS'),
                ('editorial_acceptance', 'PASS'), ('installed', 'PASS'), ('deployment', 'PASS'),
                ('real_provider', 'PASS'), ('physical_satellite', 'PASS'), ('automatic_dispatch', True),
                ('consumer_writes', True), ('workspace_exception', 'DELETE_BRANCH'),
                ('retained_source_branch', 'other-branch'), ('retained_source_head', '0'*40),
                ('predecessor_sha256', '0'*64), ('base_readback_sha256', '0'*64),
                ('product_manifest_sha256', '0'*64), ('qualification_sha256', '0'*64),
                ('browser_receipt_sha256', '0'*64), ('documents', [])):
            with self.subTest(field=field):
                plan = deepcopy(self.plan)
                plan['planning_maintenance']['ha_guest_invitation_receipt'][field] = value
                self.assertTrue(validate(plan))

    def test_old_publication_and_source_receipts_cannot_be_borrowed_or_rewritten(self):
        for key in ('ha_shared_guest_receipt', 'ha_shared_guest_finalization_receipt'):
            plan = deepcopy(self.plan)
            plan['planning_maintenance'][key]['overall_acceptance'] = 'PASS'
            self.assertTrue(validate(plan))
        plan = deepcopy(self.plan)
        plan['planning_maintenance']['edges'].pop()
        self.assertTrue(validate(plan))
        plan = deepcopy(self.plan)
        next(n for n in plan['planning_maintenance']['nodes'] if n['id'] == 'WEB::BROWSER')['status'] = 'Completed'
        self.assertTrue(validate(plan))
