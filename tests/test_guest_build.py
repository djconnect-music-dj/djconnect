"""Deterministic maintained guest artifact and causal source UI retry/withdrawal."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GuestBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('guest_build_unit',ROOT/'scripts/build_vibecast.py')
        cls.build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.build)

    def test_generated_guest_is_exact_and_its_artifact_contains_no_runtime_credentials(self):
        self.assertEqual((ROOT/'custom_components/djconnect/vibecast_guest.html').read_text(),self.build.render_guest(ROOT))
        with TemporaryDirectory() as directory:
            output = Path(directory)
            manifest = self.build.build_guest(ROOT, output, source_revision='a'*40)
            self.assertEqual(manifest['sources'].keys(),{'guest.html','guest.css','guest.js'})
            self.assertFalse(manifest['private_runtime_data_in_build'])
            self.assertEqual(manifest['files']['index.html'], self.build.digest((output/'index.html').read_bytes()))
            self.assertEqual(json.loads((output/'manifest.json').read_text()),manifest)
        code = (ROOT/'custom_components/djconnect/vibecast_renderer/guest.js').read_text()
        for forbidden in ('localStorage','sessionStorage','document.cookie','djcd_','/session/history','/api/djconnect/v1/command'):
            self.assertNotIn(forbidden,code)
        page = self.build.render_guest(ROOT)
        self.assertNotIn('<script src=',page)
        self.assertNotIn('@@GUEST_',page)

    def test_actual_guest_script_preserves_retry_identity_and_withdraws_dom_and_dispatch(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node is required for the source UI contract')
        result = subprocess.run([node,str(ROOT/'scripts/verification/guest_browser_contract.mjs')],
            text=True,capture_output=True,timeout=20,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt['status'],'PASS')
        self.assertEqual(receipt['scope'],'SOURCE_DOM_AND_HTTP_FIXTURES_NOT_REAL_BROWSER')
        self.assertEqual(len(receipt['checks']),5)
