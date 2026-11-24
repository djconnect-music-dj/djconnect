"""Bound invitation repair to new full-source proof and immutable delivered history."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FREEZE = 'history/20261123/ha-guest-invitation-predecessor-maintenance-v28.json'
FREEZE_SHA = 'df43ea540ab120614e8a722405df01b1c5c3fac752f865f86321f6104d4c9d18'
BASE = '48c25f820fbfa39270137e3c7a4f01823511875f'
BASE_READBACK_SHA = 'eb4e4f5ee920264da71862a30d556dd402698dc4409b5382483c937478d6080e'
DOCS = {'docs/verification/HA_GUEST_INVITATION_REPAIR_20261123.md',
        'docs/history/prompts/2026-11-23-ha-guest-invitation-repair.md'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(plan, previous_validator, *, historical_product=False):
    from ha_shared_guest_delta import validate as shared_source
    from ha_shared_guest_finalization_delta import validate as shared_final
    delta = plan['planning_maintenance']
    receipt = delta.get('ha_guest_invitation_receipt', {})
    errors = []

    def check(ok, reason):
        if not ok:
            errors.append('maintenance: invitation repair ' + reason)

    if not isinstance(receipt, dict):
        return ['maintenance: invitation repair receipt object required']
    raw = (Path(__file__).parent/FREEZE).read_bytes()
    prior = json.loads(raw)
    check(receipt.get('predecessor_path') == FREEZE
          and receipt.get('predecessor_sha256') == sha(raw) == FREEZE_SHA,
          'immutable delivered predecessor')
    restored = deepcopy(delta)
    restored.pop('ha_guest_invitation_receipt', None)
    restored['schema_version'] = prior['schema_version']
    restored['document_references'] = prior['document_references']
    check(restored == prior, 'unchanged nodes, scopes, dependencies and historical receipts')
    check(receipt.get('base_sha') == BASE
          and receipt.get('branch') == 'codex/ha-guest-invitation-repair-20261123'
          and receipt.get('finding_id') == 'HA-GUEST-SAME-TAB-INVITATION'
          and receipt.get('source_delivery') == 'LOCAL_IMPLEMENTATION_NOT_MERGED'
          and receipt.get('overall_acceptance') == receipt.get('editorial_acceptance') == 'OPEN'
          and all(receipt.get(k) == 'NOT_RUN' for k in
                  ('installed', 'deployment', 'real_provider', 'physical_satellite'))
          and receipt.get('automatic_dispatch') is False and receipt.get('consumer_writes') is False,
          'bounded source and independent acceptance')
    check(receipt.get('retained_source_branch') == 'codex/ha-native-shared-participation-20261123'
          and receipt.get('retained_source_head') == 'bf0494f6d5756b1756c526c46d04a9631e6b81b3'
          and receipt.get('workspace_exception') == 'OWNER_APPROVED_BOUNDED_REPAIR_WITH_SOURCE_BRANCH_RETENTION',
          'explicit retention without deletion or broader authority')
    docs = receipt.get('documents', [])
    check(len(docs) == 2 and {d.get('path') for d in docs} == DOCS
          and all(sha((ROOT/d['path']).read_bytes()) == d.get('sha256') for d in docs),
          'current correction and prompt documents')
    refs = {r['path']:r['sha256'] for r in delta['document_references']}
    check(len(refs) == len(delta['document_references']) and refs == {
        **{r['path']:r['sha256'] for r in prior['document_references']},
        **{r['path']:r['sha256'] for r in docs}}, 'unchanged predecessor references and exact new sources')
    loaded = {}
    for name, path in (
            ('product_manifest', 'docs/verification/ha-guest-invitation-product-manifest.json'),
            ('qualification', 'docs/verification/ha-guest-invitation-qualification-20261123.json'),
            ('browser_receipt', 'docs/verification/ha-guest-invitation-browser-receipt-20261123.json'),
            ('base_readback', 'docs/verification/ha-guest-invitation-predecessor-publication-20261123.json')):
        raw = (ROOT/path).read_bytes()
        check(receipt.get(name+'_path') == path and receipt.get(name+'_sha256') == sha(raw),
              'exact ' + name + ' binding')
        loaded[name] = json.loads(raw)
    actual = loaded['product_manifest'] if historical_product else {str(p.relative_to(ROOT)):sha(p.read_bytes())
              for p in (ROOT/'custom_components/djconnect').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    check(loaded['product_manifest'] == actual and len(actual) == 343, 'all current product bytes')
    base = loaded['base_readback']
    old = json.loads((ROOT/'docs/verification/ha-shared-guest-product-manifest.json').read_text())
    check(receipt.get('base_readback_sha256') == BASE_READBACK_SHA
          and base.get('main_sha') == BASE and base.get('qualified_head') == '1c033dac697e240bfee0ec056a9b5ba83784f6dd'
          and base.get('tree') == '464bd2d6b1a187d9b8848b8c25c395bc7f5816a1'
          and base.get('source_tree_equal') is True and base.get('main_validation') == 'PASS'
          and base.get('archive_product_files') == old and base.get('archive_exact_product_count') == 343,
          'independently qualified actual predecessor package')
    check(old.keys() == actual.keys() and {n for n in actual if old.get(n) != actual[n]} == {
        'custom_components/djconnect/vibecast_renderer/guest.js',
        'custom_components/djconnect/vibecast_guest.html'}, 'only maintained guest script and generated artifact changed')
    policy = ROOT/'tools/trusted_delivery/evidence_preservation.py'
    check(sha(policy.read_bytes()) == '3fba299f26c75e47804e66218cabea8fd50627bd2a84a1dd294d59009714466f',
          'unchanged original canonical policy')
    spec = importlib.util.spec_from_file_location('invitation_base_policy', policy)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = {'repository':'djconnect-music-dj/.github', 'repository_id':1461539726,
        'revision':'89a2a8b4c7571965249bed745bf7c5c37a1221f1', 'snapshot':'evidence-ebbb',
        'original_repository_id':1258575431, 'original_revision':'ebbb35f038a7a3c7d46c12660968bcd50eb67580'}
    durable = base.get('durable_qualification', {})
    check(durable.get('commit_sha') == BASE
          and module.validate_record(durable, expected_policy_source=expected) == [], 'original twelve-check base proof')
    proof = loaded['qualification']
    matrix_raw = (ROOT/proof['matrix_path']).read_bytes()
    matrix = json.loads(matrix_raw)
    rows = matrix['results']
    check(proof.get('source_pins') == matrix.get('source_pins') == actual
          and proof.get('source_before_after_equal') is matrix.get('source_before_after_equal') is True
          and proof.get('matrix_sha256') == sha(matrix_raw)
          and proof.get('execution_count') == len(rows) == len({r['harness'] for r in rows}) == 54
          and all(r.get('exit_code') == 0 and r.get('harness_sha256') == sha((ROOT/r['harness']).read_bytes())
              for r in rows), 'fresh all54 actual HA executions on unchanged full source')
    browser = loaded['browser_receipt']
    check(browser.get('scope') == 'REAL_BROWSER_WITH_DECLARED_SYNTHETIC_HTTP_NOT_HA_PROVIDER_PHYSICAL'
          and browser.get('base_sha') == BASE and browser.get('source_before_after_equal') is True
          and browser.get('product_manifest_sha256') == receipt.get('product_manifest_sha256')
          and browser.get('product_file_count') == 343 and browser.get('distinct_fixture_guest_count') == 2
          and len(browser.get('checks', {})) == 5 and set(browser['checks'].values()) == {'PASS'}
          and browser.get('node_before_exit_code') == 1
          and browser.get('node_harness_sha256') == sha((ROOT/'scripts/verification/guest_browser_contract.mjs').read_bytes())
          and browser.get('predecessor_guest_source_sha256') == old['custom_components/djconnect/vibecast_renderer/guest.js']
          and browser.get('current_guest_source_sha256') == actual['custom_components/djconnect/vibecast_renderer/guest.js'],
          'causal predecessor failure and actual browser navigation repair')
    for obj in (proof, browser):
        check(all(obj.get(k) == 'NOT_RUN' for k in ('installed','deployment','real_provider','physical_satellite'))
              and obj.get('editorial_acceptance') == 'OPEN', 'no fixture-to-physical/provider promotion')
    previous = dict(plan)
    previous['planning_maintenance'] = restored
    # Old343 bytes are checked against independently downloaded published
    # packages above and in v28; this candidate must match all current343 bytes.
    return errors + shared_final(previous,
        lambda p: shared_source(p, previous_validator, historical_product=True))
