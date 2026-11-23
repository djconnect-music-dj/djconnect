"""No voice selection may rewrite predecessor proof or claim shared/physical delivery."""
from copy import deepcopy
from pathlib import Path
import unittest
from validate_snapshot import load, validate


class NativeVoicePlanningTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(Path(__file__).with_name('djconnect-platform-v1.json'))

    def test_selected_source_and_separate_shared_acceptance(self):
        self.assertEqual(validate(self.plan), [])
        nodes = {n['id']:n for n in self.plan['planning_maintenance']['nodes']}
        self.assertEqual(nodes['HA-NATIVE-VOICE::ADOPTION']['status'], 'In progress')
        self.assertEqual(nodes['HA-NATIVE-VOICE::ACCEPTANCE']['status'], 'Planned')
        for name in ('WEB::CHAT','WEB::REQUEST','WEB::ENQUEUE'):
            self.assertEqual(nodes[name]['status'], 'In progress')

    def test_no_publication_install_guest_or_predecessor_overclaim(self):
        for field, value in (('source_delivery','PROTECTED_MERGED'),('installed','PASS'),
                ('deployment','PASS'),('real_provider','PASS'),('physical_satellite','PASS'),
                ('overall_acceptance','PASS'),('stage3','IMPLEMENTED'),('automatic_dispatch',True),
                ('consumer_writes',True),('predecessor_sha256','0'*64),
                ('product_manifest_sha256','0'*64)):
            with self.subTest(field=field):
                plan = deepcopy(self.plan)
                plan['planning_maintenance']['ha_native_voice_receipt'][field] = value
                self.assertTrue(validate(plan))
        plan = deepcopy(self.plan)
        plan['planning_maintenance']['music_canvas_finalization_receipt']['overall_acceptance'] = 'PASS'
        self.assertTrue(validate(plan))

    def test_required_guest_effect_and_source_dependencies_cannot_be_removed(self):
        plan = deepcopy(self.plan)
        plan['planning_maintenance']['edges'] = [e for e in plan['planning_maintenance']['edges']
            if not (e['producer'] == 'WEB::ENQUEUE' and e['consumer'] == 'HA-NATIVE-VOICE::ACCEPTANCE')]
        self.assertTrue(validate(plan))
