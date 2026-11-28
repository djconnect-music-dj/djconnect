"""Actual shared HA adapters qualify source, never provider or device acceptance."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SharedGuestActualHAEvidenceTests(unittest.TestCase):
    def test_full_current_manifest_and_all_executed_adapters_are_bound(self):
        proof = json.loads((ROOT/'docs/verification/music-canvas-parallel-shared-qualification-20261128.json').read_text())
        actual = {str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'custom_components/djconnect').rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
        self.assertEqual(len(actual), 361)
        self.assertEqual(proof['source_pins'], actual)
        self.assertIs(proof['source_before_after_equal'], True)
        matrix_path = ROOT/proof['matrix_path']
        self.assertEqual(sha(matrix_path), proof['matrix_sha256'])
        matrix = json.loads(matrix_path.read_text())
        self.assertEqual(matrix['source_pins'], actual)
        self.assertTrue(matrix['source_before_after_equal'])
        self.assertEqual(len(matrix['results']), 54)
        self.assertEqual(len({r['harness'] for r in matrix['results']}), 54)
        for row in matrix['results']:
            self.assertEqual(row['exit_code'], 0, row['harness'])
            self.assertEqual(sha(ROOT/row['harness']), row['harness_sha256'])
            self.assertIn('--network', row['command'])
            self.assertEqual(row['command'][row['command'].index('--network')+1], 'none')
        execution = proof['shared_execution']
        self.assertEqual(execution['harness'], 'scripts/verification/verify_shared_guest_actual_ha.py')
        raw = execution['receipt']
        self.assertTrue(raw['source_unchanged'])
        for path, digest in raw['source_files_sha256'].items():
            self.assertEqual(sha(ROOT/path), digest)
        extension = raw['extension']
        self.assertEqual(len(extension['requests']), 14)
        self.assertEqual({r['status'] for r in extension['requests']}, {'PASS'})
        self.assertEqual(len({r['scenario'] for r in extension['requests']}), 14)
        self.assertEqual(extension['queue_posts'], 3)
        for field in ('installed', 'real_provider', 'physical_satellite'):
            self.assertEqual(extension[field], 'NOT_RUN')
        for field in ('installed', 'deployment', 'real_provider', 'physical_satellite'):
            self.assertEqual(proof[field], 'NOT_RUN')
        self.assertEqual(proof['editorial_acceptance'], 'OPEN')
