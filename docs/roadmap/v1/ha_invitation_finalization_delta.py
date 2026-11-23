"""Reconcile shared HA-native source while preserving independent open acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FREEZE = 'history/20261123/ha-invitation-source-freeze-maintenance-v29.json'
FREEZE_SHA = '08070ea0b0346aeb406d8e5a928e4091961c3c2de80919f0eda2f0b6b76de561'
READBACK = 'docs/verification/ha-invitation-source-publication-readback-20261123.json'
READBACK_SHA = 'e71eee951d55e5dacff8b3c84e57ac9e61d4ffc34e979eb44007d87be8558cc5'
POLICY_SHA = '3fba299f26c75e47804e66218cabea8fd50627bd2a84a1dd294d59009714466f'
IDENTITY = ('djconnect-music-dj/djconnect', '8203753bfbd5b0ff7b70620bd6f9377867a4710b',
            '9b91dfd7fe81f35e38768f98984788bde5ad331b', '1e000512e7027ea0d923b07d2b0ca49b792233d0')
DOCUMENTS = {'docs/technical/HA_INVITATION_SOURCE_FINALIZATION_20261123.md',
             'docs/history/prompts/2026-11-23-ha-invitation-source-finalization.md'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(plan, previous_validator):
    delta = plan['planning_maintenance']
    receipt = delta.get('ha_invitation_finalization_receipt', {})
    errors = []
    if not isinstance(receipt, dict):
        return ['maintenance: invitation Finalization receipt object required']

    def check(ok, reason):
        if not ok:
            errors.append('maintenance: invitation Finalization ' + reason)

    raw = (Path(__file__).parent/FREEZE).read_bytes()
    prior = json.loads(raw)
    check(receipt.get('predecessor_path') == FREEZE
          and receipt.get('predecessor_sha256') == sha(raw) == FREEZE_SHA,
          'immutable source predecessor')
    restored = dict(delta)
    restored.pop('ha_invitation_finalization_receipt', None)
    restored['schema_version'] = prior['schema_version']
    check(restored == prior, 'unchanged nodes, dependencies and inherited receipts')
    check(receipt.get('assignment_id') == 'DJC-HA-VOICE-CORE-CONVERGENCE-V1-20261107'
          and receipt.get('scope') == 'SAME_DOCUMENT_GUEST_INVITATION_REPAIR'
          and receipt.get('source_delivery') == 'PROTECTED_MERGED'
          and receipt.get('repair_delivery') == 'SOURCE_DELIVERED'
          and receipt.get('broader_browser_receiver_acceptance') == 'OPEN'
          and receipt.get('overall_acceptance') == 'OPEN'
          and all(receipt.get(k) == 'NOT_RUN' for k in
                  ('installed', 'deployment', 'real_provider', 'physical_satellite'))
          and receipt.get('automatic_dispatch') is False
          and receipt.get('consumer_writes') is False,
          'bounded source delivery and open shared/physical acceptance')
    docs = receipt.get('documents', [])
    check(len(docs) == 2 and {x.get('path') for x in docs} == DOCUMENTS
          and all(sha((ROOT/x['path']).read_bytes()) == x.get('sha256') for x in docs),
          'exact Finalization documents')
    raw = (ROOT/READBACK).read_bytes()
    check(receipt.get('source_readback_path') == READBACK
          and receipt.get('source_readback_sha256') == sha(raw) == READBACK_SHA,
          'immutable actual publication readback')
    readback = json.loads(raw)
    check(tuple(readback.get(k) for k in ('repository', 'qualified_head', 'main_sha', 'tree')) == IDENTITY
          and readback.get('source_tree_equal') is True
          and readback.get('main_validation') == 'PASS', 'exact reviewed and merged source identity')
    policy = ROOT/'tools/trusted_delivery/evidence_preservation.py'
    check(sha(policy.read_bytes()) == POLICY_SHA, 'original canonical validator')
    spec = importlib.util.spec_from_file_location('native_voice_durable_policy', policy)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = {'repository': 'djconnect-music-dj/.github', 'repository_id': 1461539726,
                'revision': '89a2a8b4c7571965249bed745bf7c5c37a1221f1',
                'snapshot': 'evidence-ebbb', 'original_repository_id': 1258575431,
                'original_revision': 'ebbb35f038a7a3c7d46c12660968bcd50eb67580'}
    durable = readback.get('durable_qualification', {})
    encoded = (json.dumps(durable, sort_keys=True, indent=2)+'\n').encode()
    check(durable.get('commit_sha') == IDENTITY[2]
          and readback.get('durable_sha256') == sha(encoded)
          and module.validate_record(durable, expected_policy_source=expected) == [],
          'original twelve-check source qualification')
    manifest = json.loads((ROOT/'docs/verification/ha-guest-invitation-product-manifest.json').read_bytes())
    check(len(manifest) == 343 and readback.get('archive_product_files') == manifest
          and readback.get('archive_exact_product_count') == 343,
          'actual published full product inventory')
    previous = dict(plan)
    previous['planning_maintenance'] = restored
    return errors + previous_validator(previous)
