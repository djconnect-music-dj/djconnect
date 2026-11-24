"""Current UI source proof, with exact immutable delivered predecessor validation."""
from copy import deepcopy
import hashlib

from experience_reconciliation_delta import historical_verification_source
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FREEZE = 'history/20261123/vibecast-ui-predecessor-maintenance-v30.json'
FREEZE_SHA = '4043ce5cfecdc51b384e3044b778e4fd61c06e69cd30f87edc9a57bc8a2aa964'
BASE_SHA = '20b9caa92dbcaec9faf3deda8166022f684ba4f4'
BASE_PROOF_SHA = 'c018fe065de286b61da5a9a48a3ee9524761ff99682e23e8d8e4513953e158cd'
PREFIX = 'docs/verification/'
PATHS = {
    'product_manifest': PREFIX+'vibecast-ui-product-manifest-20261124.json',
    'qualification': PREFIX+'vibecast-ui-qualification-20261124.json',
    'live_ui': PREFIX+'vibecast-live-ui-actual-ha-20261124.json',
    'browser': PREFIX+'vibecast-ui-browser-20261124.json',
    'base_publication': PREFIX+'vibecast-ui-base-publication-20261123.json',
}


EXPECTED_LIVE_CASES = {'actual_typed_emoji_and_direct_emotion_same_receipt_wrong_track_changed_retry_denied_zero_model_budget', 'actual_share_end_scrubs_original_public_object_and_guest_state_preserving_owner_history', 'actual_guest_count_only_admitted_redeemed_principals_not_display_or_invitation', 'actual_guest_scoped_prepared_png_binary_and_wrong_guest_reference_denial', 'actual_observer_source_withdrawal_removes_art_observation_and_owner_preview', 'actual_paired_owner_history_seeded_via_local_help_no_model_for_retention_counterproof', 'actual_owner_runtime_http_near_end_preview_from_original_queue_not_shared_moment', 'actual_paired_share_create_default_four_hours_app_locale_and_live_off', 'actual_host_only_mode_dynamics_reaches_guest_and_screen_without_playback_or_guest_write', 'actual_normal_provider_observer_original_sample_public_metadata_no_read_renewal', 'actual_live_off_revokes_guests_and_reactions_but_preserves_host_session_and_screen'}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(plan, previous_validator):
    from ha_invitation_finalization_delta import validate as delivered
    from experience_reconciliation_delta import HISTORICAL_DOCUMENT_SOURCES
    delta = plan['planning_maintenance']
    receipt = delta.get('vibecast_ui_receipt')
    if not isinstance(receipt, dict):
        return ['maintenance: UI qualification receipt object required']
    errors = []

    def check(ok, reason):
        if not ok:
            errors.append('maintenance: UI qualification '+reason)

    raw = (Path(__file__).parent/FREEZE).read_bytes()
    prior = json.loads(raw)
    check(receipt.get('predecessor_path') == FREEZE
          and receipt.get('predecessor_sha256') == sha(raw) == FREEZE_SHA,
          'immutable delivered maintenance30')
    restored = deepcopy(delta)
    restored.pop('vibecast_ui_receipt', None)
    restored['schema_version'] = prior['schema_version']
    restored['document_references'] = prior['document_references']
    check(restored == prior, 'unchanged historical nodes, receipts and references')
    check(receipt.get('base_sha') == BASE_SHA
          and receipt.get('source_delivery') == 'LOCAL_IMPLEMENTATION_NOT_MERGED'
          and all(receipt.get(k) == 'OPEN' for k in ('overall_acceptance','editorial_acceptance'))
          and all(receipt.get(k) == 'NOT_RUN' for k in
                  ('installed','deployment','real_provider','physical_satellite'))
          and receipt.get('automatic_dispatch') is False
          and receipt.get('consumer_writes') is False,
          'bounded local source and independent acceptance')
    document = PREFIX+'VIBECAST_UI_CORE_QUALIFICATION_20261124.md'
    check(receipt.get('document') == document
          and receipt.get('document_sha256') == sha((ROOT/document).read_bytes()),
          'current qualification document')
    loaded = {}
    for name, path in PATHS.items():
        raw = (ROOT/path).read_bytes()
        check(receipt.get(name+'_path') == path
              and receipt.get(name+'_sha256') == sha(raw), 'exact '+name+' binding')
        loaded[name] = json.loads(raw)
    sources = HISTORICAL_DOCUMENT_SOURCES.get()
    browser_harness = 'tests/browser/vibecast_display_flow.cjs'
    historical = browser_harness in sources
    actual = loaded['product_manifest'] if historical else {str(p.relative_to(ROOT)):sha(p.read_bytes())
              for p in (ROOT/'custom_components/djconnect').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    check(actual == loaded['product_manifest'] and len(actual) == 356,
          'complete current product bytes')
    base = loaded['base_publication']
    old = json.loads((ROOT/'docs/verification/ha-guest-invitation-product-manifest.json').read_bytes())
    check(receipt.get('base_publication_sha256') == BASE_PROOF_SHA
          and base.get('main_sha') == BASE_SHA and base.get('main_validation') == 'PASS'
          and base.get('source_tree_equal') is True
          and base.get('archive_product_files') == old and base.get('archive_exact_product_count') == 343,
          'independently downloaded actual published predecessor inventory')
    policy = ROOT/'tools/trusted_delivery/evidence_preservation.py'
    check(sha(policy.read_bytes()) == base.get('canonical_validator_sha256')
          == '3fba299f26c75e47804e66218cabea8fd50627bd2a84a1dd294d59009714466f',
          'original canonical qualification policy')
    spec = importlib.util.spec_from_file_location('ui_base_policy', policy)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    durable = base.get('durable_qualification', {})
    check(durable.get('commit_sha') == BASE_SHA
          and module.validate_record(durable, expected_policy_source=base['expected_policy_source']) == [],
          'actual predecessor twelve-check qualification')
    proof = loaded['qualification']
    raw = (ROOT/'docs/verification/vibecast-ui-actual-ha-matrix-20261124.json').read_bytes()
    matrix = json.loads(raw)
    rows = matrix['results']
    old_matrix = json.loads((ROOT/'docs/verification/ha-guest-invitation-actual-ha-matrix-20261123.json').read_bytes())
    check({r['harness'] for r in rows} == {r['harness'] for r in old_matrix['results']},
          'same complete owning HA harness set')
    check(proof.get('matrix_path') == 'docs/verification/vibecast-ui-actual-ha-matrix-20261124.json'
          and proof.get('matrix_sha256') == sha(raw)
          and proof.get('source_pins') == matrix.get('source_pins') == actual
          and proof.get('source_before_after_equal') is matrix.get('source_before_after_equal') is True
          and proof.get('execution_count') == len(rows) == len({r['harness'] for r in rows}) == 54
          and all(r.get('exit_code') == 0 and r.get('harness_sha256') == sha(historical_verification_source(ROOT, r['harness']).read_bytes())
                  for r in rows), 'fresh full54 actual HA matrix')
    native = proof.get('additional_native_execution', {})
    native_raw = native.get('receipt', {})
    native_cases = native_raw.get('extension', {}).get('cases', [])
    extra = matrix.get('additional_executions', [])
    check(len(extra) == 1 and extra[0].get('exit_code') == 0
          and native.get('harness') == extra[0].get('harness')
          == 'scripts/verification/verify_native_widget_winner_actual_ha.py'
          and native.get('harness_sha256') == extra[0].get('harness_sha256')
          == sha((ROOT/native['harness']).read_bytes())
          and native_raw.get('product_source_pins') == actual
          and native_raw.get('product_source_before_after_equal') is True
          and len(native_cases) == 10 and all(c.get('status') == 'PASS' for c in native_cases),
          'additional genuine HA Widget winner and withdrawal software cases')
    live = loaded['live_ui']
    extension = live['extension']
    cases = extension['requests']
    check(live.get('product_source_pins') == actual and live.get('product_source_count') == 356
          and live.get('product_source_before_after_equal') is True
          and live.get('live_ui_harness_sha256') == sha((ROOT/'scripts/verification/verify_vibecast_live_ui_actual_ha.py').read_bytes())
          and all(sha((ROOT/'scripts/verification'/n).read_bytes()) == v
                  for n,v in live['reused_harnesses'].items())
          and len(cases) == 11 and {r['scenario'] for r in cases} == EXPECTED_LIVE_CASES
          and all(r['status'] == 'PASS' for r in cases)
          and extension.get('actual_ha') is extension.get('actual_verified_tls') is True
          and extension.get('live_ui_model_calls') == 0
          and extension.get('physical_native_app_TV_and_real_provider') == 'NOT_RUN',
          'additional actual Live HTTP cases with explicit provider/native boundary')
    browser = loaded['browser']
    check(browser.get('scope') == 'REAL_BROWSER_DECLARED_HTTP_WEBSOCKET_FIXTURE_NOT_INSTALLED_PROVIDER'
          and browser.get('source_pins') == actual and browser.get('product_file_count') == 356
          and browser.get('engines') == ['chromium','webkit'] and browser.get('result') == 'PASS'
          and browser.get('harness') == browser_harness
          and browser.get('harness_sha256') == sha(sources.get(browser_harness, ROOT/browser_harness).read_bytes()),
          'actual maintained two-engine renderer proof')
    evolved = receipt.get('evolved_documents', [])
    old_refs = {r['path']:r['sha256'] for r in prior['document_references']}
    check(len(evolved) == 2 and {r.get('path') for r in evolved} == {'API_CONTRACT.md','SYNC_PROMPTS.md'}
          and all(r.get('sha256') == sha(sources.get(r['path'], ROOT/r['path']).read_bytes())
                  and r.get('predecessor_sha256') == old_refs.get(r['path'])
                  and r.get('snapshot') == 'docs/roadmap/v1/history/20261123/vibecast-ui-predecessor-documents/'+r['path']
                  and sha((ROOT/r['snapshot']).read_bytes()) == r['predecessor_sha256']
                  for r in evolved), 'independently bound current and immutable predecessor documents')
    expected_refs = {r['path']:r['sha256'] for r in prior['document_references']}
    expected_refs.update({r['path']:r['sha256'] for r in evolved})
    check({r['path']:r['sha256'] for r in delta['document_references']} == expected_refs
          and len(delta['document_references']) == len(expected_refs), 'exact current document references')
    for obj in (proof, browser):
        check(all(obj.get(k) == 'NOT_RUN' for k in ('installed','real_provider','physical_satellite'))
              and obj.get('editorial_acceptance') == 'OPEN', 'no software-to-provider/native promotion')
    previous = dict(plan)
    previous['planning_maintenance'] = restored
    # Historical validation retains the actual downloaded343-file package;
    # only the new outer layer qualifies current356 product bytes.
    token = HISTORICAL_DOCUMENT_SOURCES.set({**HISTORICAL_DOCUMENT_SOURCES.get(),
        **{r['path']:ROOT/r['snapshot'] for r in evolved
           if r.get('path') in {'API_CONTRACT.md','SYNC_PROMPTS.md'}
           and r.get('snapshot') == 'docs/roadmap/v1/history/20261123/vibecast-ui-predecessor-documents/'+r['path']
           and (ROOT/r['snapshot']).is_file()
           and sha((ROOT/r['snapshot']).read_bytes()) == old_refs[r['path']]}})
    try:
        return errors + delivered(previous, previous_validator, historical_product=True)
    finally:
        HISTORICAL_DOCUMENT_SOURCES.reset(token)
