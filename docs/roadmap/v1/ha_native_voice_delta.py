"""Selected native adopter; exact preserved predecessor and separate physical/shared work."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FREEZE = 'history/20261122/ha-native-voice-predecessor-maintenance-v24.json'
FREEZE_SHA = 'd3e13077388ab998cd423e04e765689e1d5e4ee192d50660b770043f6347de0e'
DOCS = {'docs/product/ASK_DJ_CONVERSATIONAL_EXPERIENCE_V1.md',
        'docs/product/ASK_DJ_CONTEXTUAL_DIALOGUE_CONTRACT_V1.md',
        'docs/technical/VOICE_TRANSPORT.md', 'docs/technical/AUDIO_RENDERER_HOST_ARCHITECTURE.md',
        'docs/technical/ROOM_PRESENTATION_ROUTING_ARCHITECTURE.md',
        'CLIENT_CAPABILITY_MATRIX.md', 'DJCONNECT_CAPABILITY_MODEL.md'}
DESIGN = 'docs/technical/HA_NATIVE_VOICE_DJCONNECT_CORE_V1.md'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(plan, previous_validator):
    from experience_reconciliation_delta import HISTORICAL_DOCUMENT_SOURCES
    from music_canvas_finalization_delta import validate as canvas_final
    from music_canvas_delta import validate as canvas_source
    delta = plan['planning_maintenance']
    receipt = delta.get('ha_native_voice_receipt', {})
    errors = []
    def check(value, reason):
        if not value:
            errors.append('maintenance: HA-native voice ' + reason)
    if not isinstance(receipt, dict):
        return ['maintenance: HA-native voice receipt object required']
    raw = (Path(__file__).parent/FREEZE).read_bytes()
    prior = json.loads(raw)
    check(sha(raw) == FREEZE_SHA == receipt.get('predecessor_sha256')
          and receipt.get('predecessor_path') == FREEZE, 'immutable predecessor')
    check(receipt.get('assignment_id') == 'DJC-HA-VOICE-CORE-CONVERGENCE-V1-20261107'
          and receipt.get('base_sha') == 'd987f79f8c281dab3cbcc1dc4bc5981d129f5d23'
          and receipt.get('source_delivery') == 'LOCAL_IMPLEMENTATION_NOT_MERGED'
          and receipt.get('stage1') == receipt.get('stage2') == 'LOCAL_IMPLEMENTED_VALIDATING'
          and receipt.get('stage3') == 'DEPENDENT_SHARED_CONTRACTS_NOT_IMPLEMENTED'
          and receipt.get('overall_acceptance') == 'OPEN'
          and all(receipt.get(k) == 'NOT_RUN' for k in ('installed','deployment','real_provider','physical_satellite'))
          and receipt.get('automatic_dispatch') is False and receipt.get('consumer_writes') is False,
          'source, shared and acceptance boundaries')
    restored = deepcopy(delta)
    restored.pop('ha_native_voice_receipt', None)
    restored['schema_version'] = prior['schema_version']
    restored['nodes'] = [n for n in restored['nodes'] if not n['id'].startswith('HA-NATIVE-VOICE::')]
    restored['edges'] = [e for e in restored['edges'] if not e['id'].startswith('HA-NATIVE-VOICE-')]
    restored['document_references'] = prior['document_references']
    check(restored == prior, 'all inherited nodes, receipts and dependencies unchanged')
    added = [n for n in delta['nodes'] if n['id'].startswith('HA-NATIVE-VOICE::')]
    check({n['id'] for n in added} == {'HA-NATIVE-VOICE::ADOPTION','HA-NATIVE-VOICE::ACCEPTANCE'}
          and all(n['lane'] == 'DJC-CORE' and n['contract_binding'] == DESIGN
              and n['status'] == ('In progress' if n['id'].endswith('ADOPTION') else 'Planned') for n in added),
          'one existing-service adopter and open acceptance')
    links = [e for e in delta['edges'] if e['id'].startswith('HA-NATIVE-VOICE-')]
    expected = {('CONVERSATION::CORE::SHARED-DIALOGUE','HA-NATIVE-VOICE::ADOPTION'),
                ('HA-NATIVE-VOICE::ADOPTION','HA-NATIVE-VOICE::ACCEPTANCE')} | {
        (name, 'HA-NATIVE-VOICE::ACCEPTANCE') for name in ('ENTRY::CORE::LIFECYCLE','ENTRY::CORE::ASK-LIFECYCLE',
            'WEB::CHAT','WEB::REQUEST','WEB::EFFECT-POLICY','WEB::ENQUEUE','WEB::SHARED')}
    check(len(links) == len(expected) and {(e['producer'],e['consumer']) for e in links} == expected
          and all(e['hard_precedence'] is True and e['logical_mode'] == 'AND' for e in links),
          'actual existing functional dependencies, not a parallel guest queue')
    docs = receipt.get('documents', [])
    check({d.get('path') for d in docs} == DOCS | {DESIGN, 'SYNC_PROMPTS.md'}
          and all(sha((ROOT/d['path']).read_bytes()) == d.get('sha256') for d in docs), 'current canonical documents')
    references = {r['path']:r['sha256'] for r in delta['document_references']}
    previous_refs = {r['path']:r['sha256'] for r in prior['document_references']}
    check(set(references) == {r['path'] for r in prior['document_references']} | DOCS | {DESIGN, 'SYNC_PROMPTS.md'}
          and all(references.get(d['path']) == d.get('sha256') for d in docs)
          and all(references.get(path) == digest for path, digest in previous_refs.items() if path not in DOCS),
          'current source reference completeness')
    snapshots = receipt.get('predecessor_documents', [])
    old_refs = {r['path']:r['sha256'] for r in prior['document_references']}
    check({d.get('path') for d in snapshots} == DOCS and all(
        d.get('snapshot') == 'docs/roadmap/v1/history/20261122/ha-native-voice-predecessor-documents/'+d['path']
        and sha((ROOT/d['snapshot']).read_bytes()) == d.get('sha256')
        and (d['path'] not in old_refs or old_refs[d['path']] == d['sha256']) for d in snapshots),
        'byte-preserved predecessor documents')
    manifest_path = 'docs/verification/ha-native-voice-product-manifest.json'
    manifest_raw = (ROOT/manifest_path).read_bytes()
    actual = {str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in (ROOT/'custom_components/djconnect').rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    check(receipt.get('product_manifest_path') == manifest_path
          and receipt.get('product_manifest_sha256') == sha(manifest_raw)
          and json.loads(manifest_raw) == actual and len(actual) == 331, 'exact full current product inventory')
    previous = dict(plan)
    previous['planning_maintenance'] = restored
    token = HISTORICAL_DOCUMENT_SOURCES.set({r['path']:ROOT/r['snapshot'] for r in snapshots})
    try:
        # Old 328-file publication is checked against its immutable published
        # package manifest; the new exact 331-file candidate is checked above.
        return errors + canvas_final(previous,
            lambda p: canvas_source(p, previous_validator, historical_product=True), historical_product=True)
    finally:
        HISTORICAL_DOCUMENT_SOURCES.reset(token)
