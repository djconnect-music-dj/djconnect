"""Bound stage3 source to its actual HA qualification without rewriting delivered history."""
from copy import deepcopy
import hashlib

from experience_reconciliation_delta import HISTORICAL_DOCUMENT_SOURCES, historical_verification_source
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FREEZE = 'history/20261123/ha-shared-guest-predecessor-maintenance-v26.json'
FREEZE_SHA = '735f7eb1567cf4c70e1f69990f01acbbbaac5b4529cdbb187bab966f80403286'
SELECTED = {'WEB::GUEST', 'WEB::SHARED', 'WEB::CHAT', 'WEB::REQUEST',
            'WEB::EFFECT-POLICY', 'WEB::ENQUEUE', 'WEB::BROWSER', 'WEB::MEDIA'}
PARTIAL = {'WEB::BROWSER', 'WEB::MEDIA'}
MANIFEST = 'docs/verification/ha-shared-guest-product-manifest.json'
QUALIFICATION = 'docs/verification/ha-shared-guest-qualification-20261123.json'
ADDED_DOCS = {'docs/technical/VIBECAST_GUEST_PARTICIPATION_V1.md',
              'docs/history/prompts/2026-11-23-ha-shared-guest-participation.md'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(plan, previous_validator, *, historical_product=False):
    from ha_native_voice_delta import validate as native_source
    from ha_native_voice_finalization_delta import validate as native_final
    delta = plan['planning_maintenance']
    receipt = delta.get('ha_shared_guest_receipt', {})
    errors = []

    def check(ok, reason):
        if not ok:
            errors.append('maintenance: shared guest ' + reason)

    if not isinstance(receipt, dict):
        return ['maintenance: shared guest receipt object required']
    raw = (Path(__file__).parent/FREEZE).read_bytes()
    prior = json.loads(raw)
    check(receipt.get('predecessor_path') == FREEZE
          and receipt.get('predecessor_sha256') == sha(raw) == FREEZE_SHA,
          'immutable delivered predecessor')
    check(receipt.get('assignment_id') == 'DJC-HA-VOICE-CORE-CONVERGENCE-V1-20261107'
          and receipt.get('base_sha') == 'bbf56161c4b920ce43f701d3e951e721bba9d6df'
          and receipt.get('branch') == 'codex/ha-native-shared-participation-20261123'
          and receipt.get('source_delivery') == 'LOCAL_IMPLEMENTATION_NOT_MERGED'
          and receipt.get('stage3') == 'LOCAL_SHARED_PARTICIPATION_VALIDATING'
          and receipt.get('overall_acceptance') == receipt.get('editorial_acceptance') == 'OPEN'
          and all(receipt.get(k) == 'NOT_RUN' for k in
                  ('installed', 'deployment', 'real_provider', 'physical_satellite'))
          and receipt.get('automatic_dispatch') is False and receipt.get('consumer_writes') is False,
          'source and independent acceptance boundaries')
    old_nodes = {n['id']:n for n in prior['nodes']}
    selected = [n for n in delta['nodes'] if n['id'] in SELECTED]
    check(set(receipt.get('selected_nodes', [])) == SELECTED and len(selected) == 8
          and all(n['status'] == 'In progress' and n.get('assignment_status') ==
              ('SELECTED_CORE_SOURCE_PARTIAL' if n['id'] in PARTIAL else 'SELECTED_IN_PROGRESS')
              for n in selected), 'bounded existing owners without family completion')
    restored = deepcopy(delta)
    restored.pop('ha_shared_guest_receipt', None)
    restored['schema_version'] = prior['schema_version']
    for node in restored['nodes']:
        if node['id'] in SELECTED:
            original = old_nodes[node['id']]
            node['status'] = original['status']
            if 'assignment_status' in original:
                node['assignment_status'] = original['assignment_status']
            else:
                node.pop('assignment_status', None)
    restored['document_references'] = prior['document_references']
    check(restored == prior, 'all other nodes, scopes, edges and receipts unchanged')
    original_docs = {d['path']:d['sha256'] for d in prior['ha_native_voice_receipt']['documents']}
    docs = receipt.get('documents', [])
    check(len(docs) == 11 and {d.get('path') for d in docs} == original_docs.keys() | ADDED_DOCS
          and all(sha(historical_verification_source(ROOT, d['path'], d['sha256']).read_bytes()) == d.get('sha256') for d in docs),
          'current canonical contracts and prompt history')
    refs = {d['path']:d['sha256'] for d in delta['document_references']}
    old_refs = {d['path']:d['sha256'] for d in prior['document_references']}
    expected_refs = {**old_refs, **{d['path']:d['sha256'] for d in docs}}
    check(refs == expected_refs and len(refs) == len(delta['document_references']),
          'exact current document references')
    snapshots = receipt.get('predecessor_documents', [])
    check(len(snapshots) == 9 and {d.get('path') for d in snapshots} == original_docs.keys()
          and all(d.get('snapshot') ==
              'docs/roadmap/v1/history/20261123/ha-shared-guest-predecessor-documents/'+d['path']
              and sha((ROOT/d['snapshot']).read_bytes()) == d.get('sha256') == original_docs[d['path']]
              for d in snapshots), 'byte-preserved delivered source documents')
    raw = (ROOT/MANIFEST).read_bytes()
    actual = json.loads(raw) if historical_product else {str(p.relative_to(ROOT)):sha(p.read_bytes())
              for p in (ROOT/'custom_components/djconnect').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    check(receipt.get('product_manifest_path') == MANIFEST
          and receipt.get('product_manifest_sha256') == sha(raw)
          and receipt.get('product_file_count') == len(actual) == 343
          and json.loads(raw) == actual, 'full exact current product manifest')
    check(receipt.get('qualification_path') == QUALIFICATION, 'qualification path')
    qualification_raw = (ROOT/QUALIFICATION).read_bytes()
    check(receipt.get('qualification_sha256') == sha(qualification_raw), 'exact qualification receipt')
    proof = json.loads(qualification_raw)
    matrix_raw = (ROOT/proof['matrix_path']).read_bytes()
    matrix = json.loads(matrix_raw)
    rows = matrix['results']
    shared = proof['shared_execution']
    check(proof.get('source_pins') == matrix.get('source_pins') == actual
          and proof.get('source_before_after_equal') is matrix.get('source_before_after_equal') is True
          and proof.get('matrix_sha256') == sha(matrix_raw)
          and proof.get('execution_count') == len(rows) == len({r['harness'] for r in rows}) == 54
          and all(r.get('image') in {
              'sha256:6785d1eca68747a524c156faae1b139ed415c07357386ae6fe17291986e59e82',
              'sha256:1b64d38f38d922bf9d59336451fd6453e1d614f934456af4ee3d2a51061be3a4'}
              and r.get('exit_code') == 0
              and r.get('harness_sha256') == sha(historical_verification_source(ROOT, r['harness'], r['harness_sha256']).read_bytes()) for r in rows),
          '54 actual isolated HA executions bound to unchanged current source')
    check(shared.get('harness') == 'scripts/verification/verify_shared_guest_actual_ha.py'
          and shared.get('exit_code') == 0
          and any(all(row.get(k) == shared.get(k) for k in
              ('harness', 'harness_sha256', 'image', 'exit_code', 'run_log_sha256'))
              for row in ({**r, 'run_log_sha256':r['log_sha256']} for r in rows))
          and shared['receipt'].get('source_unchanged') is True,
          'actual shared adapter execution and raw result')
    check(all(proof.get(k) == 'NOT_RUN' for k in
              ('installed', 'deployment', 'real_provider', 'physical_satellite'))
          and proof.get('editorial_acceptance') == 'OPEN', 'no fixture-to-device/provider promotion')
    previous = dict(plan)
    previous['planning_maintenance'] = restored
    token = HISTORICAL_DOCUMENT_SOURCES.set({**HISTORICAL_DOCUMENT_SOURCES.get(),
        **{d['path']:ROOT/d['snapshot'] for d in snapshots}})
    try:
        # The v26 canonical publication readback independently checks all 331
        # historical bytes. Only this current candidate must match all 343.
        return errors + native_final(previous,
            lambda p: native_source(p, previous_validator, historical_product=True))
    finally:
        HISTORICAL_DOCUMENT_SOURCES.reset(token)
