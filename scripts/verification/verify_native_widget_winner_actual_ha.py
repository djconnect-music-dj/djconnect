"""Actual disposable HA/TLS/native winner/Widget preparation; declared API seams.

Real ConfigEntries, ordinary paired HTTP, Profile, SQLite opt-in, private HA
Store and P256 custody. API/AppAttest/provider inputs are explicitly synthetic;
Core context metadata is not native clock/target/restore or APNs acceptance.
Run with a read-only candidate and a new private lab, never installed HA config.
"""
from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch
import uuid

ROOT = Path(os.environ['DJC_SOURCE_ROOT'])
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts/verification')]
import verify_requested_moments_http as harness  # noqa: E402

TOKEN = 'djci_' + 'A' * 43
SECOND = 'djconnect-ios-SECOND123456'


def product_pins():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'custom_components/djconnect').rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


async def qualify(hass, manager, history, request, client):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    from homeassistant.config_entries import ConfigEntryState, ConfigEntryStore
    from custom_components.djconnect import DJConnectRuntime, api_handlers
    from custom_components.djconnect.native_installation_runtime import create_installation_service, InstallationHTTPS
    from custom_components.djconnect.native_pair_enrollment import KEY
    from custom_components.djconnect.native_widget_issuer import _ENROL, _ROLE_DOMAIN, _hash, _operation
    from custom_components.djconnect.native_widget_transport import ProductionWidgetHTTPS
    from custom_components.djconnect.persistence import persistence_service
    from custom_components.djconnect.playback_observation import PlaybackObservationManager
    from custom_components.djconnect.profile_context import profile_storage
    from custom_components.djconnect.surface_issuer_transport import IssuerHTTPReply
    from custom_components.djconnect.surface_issuer_wire import DOMAIN, PREFIX, public_key_thumbprint, verify_envelope
    from custom_components.djconnect.surface_push_service import start_surface_service, close_surface_service
    from custom_components.djconnect.surface_push_wire import canonical

    captured = inspect.getclosurevars(request).nonlocals
    first_identity = dict(captured['identity'])
    first_headers = {**captured['headers'], 'X-DJConnect-Client-Type': 'ios'}
    storage = profile_storage(hass)
    await storage.async_upsert_music_account('source-account', 'source-spotify',
        provider_account_id='synthetic-provider-account', linked_profile_ids=frozenset({'profile-a'}))
    await storage.async_update_profile('profile-a', preferences=replace(
        storage.household.profiles['profile-a'].preferences,
        default_backend_id='source-spotify', default_music_account_id='source-account'))
    await storage.async_upsert_device(SECOND, 'ios', linked_profile_id='profile-a')
    second_entry = hass.config_entries.async_get_entry('second-entry')
    second_entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    second_runtime = DJConnectRuntime(second_entry)
    hass.data['djconnect']['second-entry'] = second_runtime
    source_entry = hass.config_entries.async_get_entry('source-entry')
    hass.data['djconnect']['source-entry'] = DJConnectRuntime(source_entry)
    # The only ConfigEntry fixture setup occurs before the ordinary pair captures.
    # A real HTTP pair (rather than a forged PairJournal ACK) creates device2.
    response = await client.post('/api/djconnect/v1/pair', json={
        'device_id': SECOND, 'client_type': 'ios', 'pair_code': '654321'})
    paired = await response.json()
    assert response.status == 200 and paired['success']
    second_headers = {'Authorization': 'Bearer ' + paired['device_token'],
        'X-DJConnect-Device-ID': SECOND, 'X-DJConnect-Client-Type': 'ios'}
    identities = (first_identity, {'device_id': SECOND, 'client_type': 'ios'})
    headers = (first_headers, second_headers)
    for entry_id in ('owner-entry', 'second-entry'):
        registration = hass.data['djconnect'][entry_id].surface_pair_registration
        while registration.tasks:
            await asyncio.gather(*tuple(registration.tasks))
        assert registration.phase == 'recorded' and registration.current()
    # Force actual HA's pending ConfigEntry Store writer to complete before
    # the real native factory independently reads disk and its exact pair tuple.
    await ConfigEntryStore(hass).async_save({'entries': [
        entry.as_storage_fragment for entry in hass.config_entries.async_entries()]})
    assert (Path(hass.config.config_dir) / '.storage/core.config_entries').is_file()
    native = create_installation_service(hass)
    hass.data['djconnect'][KEY] = native
    persistence = persistence_service(hass)
    calls, cases, http_evidence = [], [], []
    enrol_keys, role_receipts = {}, {}
    pause_issue_for = [None]
    surface = None

    def case(name):
        cases.append({'scenario': name, 'status': 'PASS'})
        (Path(os.environ['DJC_LAB_ROOT']) / 'native-widget-progress.json').write_text(json.dumps(cases, indent=2))

    async def raw(path, body, index=0, expected=200):
        response = await client.post('/api/djconnect/v1/' + path, headers=headers[index], json=body)
        value = await response.json()
        assert response.status == expected, (path, response.status, value.get('error'))
        assert response.headers['Cache-Control'] == 'no-store'
        http_evidence.append({'path': path, 'status': response.status,
            'error': value.get('error'), 'state': value.get('state')})
        return value

    def verify_spki(spki, encoded_signature, statement):
        signature = base64.urlsafe_b64decode(encoded_signature + '==')
        assert len(signature) == 64
        load_der_public_key(spki).verify(utils.encode_dss_signature(
            int.from_bytes(signature[:32]), int.from_bytes(signature[32:])), statement, ec.ECDSA(hashes.SHA256()))

    async def api(_transport, origin, path, body, auth, *, guard, deadline):
        guard()
        assert origin == 'https://api.djconnect.dev'
        assert auth.get('Authorization') == 'Bearer ' + TOKEN
        assert not any(name.startswith('CF-Access-') for name in auth)
        calls.append(path)
        if path.endswith('/resolve'):
            reply = {'contract_version': 1, 'install_credential_id': 'synthetic-actual-credential',
                'ha_install_id': 'synthetic-actual-ha'}
        elif '/publisher/' in path:
            if path.endswith('/operation'):
                row = await persistence.async_in_transaction(lambda tx: tx.fetchone(
                    'SELECT original,consent_revision FROM djconnect_native_pair_retirements WHERE event_id=?',
                    (body['operation_id'],)))
                assert row and row[1] == body['consent_revision']
                event = json.loads(row[0])
                assert event == {**{k: v for k, v in body.items() if k != 'consent_revision'},
                    'api_audience': 'djc-native-push/1', 'event_id': body['operation_id']}
            reply = {'ok': True}
        elif path == _ENROL:
            receipt, delegation = body['first_key_receipt'], body['delegation']
            statement = canonical([_ROLE_DOMAIN, 'POST', path, receipt, delegation]).encode()
            verify_spki(enrol_keys[receipt['operation_id']], body['signature'], statement)
            key, policy = delegation['public_key'], delegation['policy']
            thumb = public_key_thumbprint(key)
            scope = _hash([DOMAIN, 'delegation', delegation['delegation_id'], 1,
                delegation['install_id'], delegation['device_binding'], delegation['owner_binding'],
                delegation['grant_binding'], delegation['source_binding'], delegation['binding_id'], thumb, policy])
            reply = {'contract_version': 1, 'success': True, 'state': 'enrolled', 'replayed': False,
                'delegation_id': delegation['delegation_id'], 'delegation_revision': 1,
                'key_thumbprint': thumb, 'scope_digest': scope,
                'expires_at_ms': policy['original_grant_expires_at_ms'],
                'enrol_operation_id': delegation['operation_id'],
                'install_credential_id': receipt['install_credential_id'],
                'native_operation_id': receipt['operation_id'],
                'native_api_installation_id': receipt['api_installation_id'],
                'native_registry_generation': receipt['registry_generation'],
                'enrolment_sha256': hashlib.sha256(statement).hexdigest()}
            role_receipts[receipt['operation_id']] = deepcopy(reply)
        elif path == '/v1/push/native/key/challenge':
            reply = {'contract_version': 1, 'api_audience': 'djc-native-push/1',
                'operation_id': body['operation_id'], 'api_installation_id': 'synthetic-api-install',
                'install_credential_id': 'synthetic-actual-credential', 'challenge_id': 'synthetic-challenge',
                'challenge_nonce': 'A' * 43, 'expected_key_revision': 0,
                'expires_at_ms': int(native.wall() * 1000) + 60000}
        elif path == '/v1/push/native/key/register':
            fields = ('operation_id', 'api_installation_id', 'install_credential_id', 'challenge_id',
                'challenge_nonce', 'expires_at_ms', 'expected_key_revision', 'pairing_generation',
                'pair_binding', 'owner_binding', 'device_binding', 'core_key_thumbprint')
            statement = canonical(['djc-native-pair-witness/1', 'djc-native-push/1', 'POST', path,
                'widget-first-key', *(body[key] for key in fields)]).encode()
            spki = base64.b64decode(body['core_public_key_spki_b64'])
            verify_spki(spki, body['core_signature_b64url'], statement)
            enrol_keys[body['operation_id']] = spki
            reply = {key: body[key] for key in ('contract_version', 'operation_id', 'api_installation_id',
                'install_credential_id', 'expires_at_ms', 'pairing_generation', 'core_key_thumbprint')}
            reply.update(registry_generation='synthetic-ACK-' + body['operation_id'], key_revision=1,
                state='registered', transcript_sha256=hashlib.sha256(statement).hexdigest(),
                # Explicit MODEL Apple-kernel metadata at this upstream API seam.
                # These are original synthetic deadlines, never native proof.
                apple_evidence_expires_at_ms=int(native.wall() * 1000) + 7200000,
                apple_status_expires_at_ms=int(native.wall() * 1000) + 3600000)
            assert len(reply) == 13
        else:
            raise AssertionError('Undeclared API boundary: ' + path)
        guard()
        return IssuerHTTPReply(200, reply)

    async def issuer_api(transport, origin, path, envelope, auth, *, guard, deadline):
        guard()
        assert origin == 'https://api.djconnect.dev' and auth == {}
        role = transport._owner._live()
        payload = envelope['payload']
        capture = role.captures[payload['operation_id']]
        assert verify_envelope(path, envelope, capture.comparisons()[0])
        row = await persistence.async_in_transaction(lambda tx: tx.fetchone(
            'SELECT body FROM djconnect_surface_issuer_journal WHERE singleton=1'))
        journal = json.loads(row[0])
        journal_identity, journal_binding, journal_operation = capture.journal_keys()
        original_row = journal['records'][journal_identity]
        assert original_row['binding'] == journal_binding and original_row['operation'] == journal_operation
        assert original_row['phase'] == ('challenge_reserved' if path.endswith('challenge') else 'issue_reserved')
        calls.append(path)
        expected = capture.expected
        reply = {'contract_version': 1, 'success': True, 'operation_id': payload['operation_id'],
            'delegation_id': expected.delegation_id, 'delegation_revision': 1,
            'expires_at_ms': expected.original_grant_expires_ms, 'state': payload['action'],
            'replayed': False, 'scope_digest': expected.scope_digest}
        if path == PREFIX + 'challenge':
            reply.update(challenge_id='synthetic-issuer-challenge', nonce='A' * 43,
                key_thumbprint=expected.key_thumbprint, expires_at_ms=int(time.time() * 1000) + 120000)
        elif path == PREFIX + 'issue':
            reply.update(state='issued', capability_id=expected.delegation_id + '-cap',
                credential='djcs_' + base64.urlsafe_b64encode(hashlib.sha256(expected.delegation_id.encode()).digest()).decode().rstrip('='))
            if pause_issue_for[0] == role.first_original[0].device_id:
                await raw('push/native/consent/widgetkit', {'contract_version': 1, 'enabled': False,
                    'operation_id': str(uuid.uuid4()), 'expected_revision': 1})
        else:
            raise AssertionError('Undeclared issuer action')
        guard()
        return IssuerHTTPReply(200, reply)

    async def no_external(*args, **kwargs):
        return None

    with patch.object(InstallationHTTPS, '_post', api), patch.object(ProductionWidgetHTTPS, '_post', issuer_api), \
         patch.object(api_handlers, '_async_generate_initial_session_moment', no_external), \
         patch.object(PlaybackObservationManager, 'async_start_spotify', no_external):
        active = manager.current_active('profile-a')
        if active:
            await manager.async_end(owner_profile_id='profile-a', session_id=active.session_id)
        _, status = await request('POST', '/api/djconnect/v1/session/start', {'mood': 'groove', 'locale': 'nl'})
        assert status == 201
        active = manager.current_active('profile-a')
        sid = active.session_id
        start_surface_service(hass)
        surface = hass.data['djconnect']['surface_push_service']
        pre_context = {**identities[1], 'contract_version': 3, 'session_id': sid,
            'operation_id': _operation(int(time.time() * 1000))}
        await raw('push/surface/context', pre_context, 1, 503)
        case('real_paired_context_before_prepare_has_no_original_purpose')
        challenges = []
        for index in range(2):
            before = await raw('push/native/consent/widgetkit', {'contract_version': 1,
                'enabled': True, 'operation_id': str(uuid.uuid4()), 'expected_revision': 0}, index)
            assert before['enabled'] and before['revision'] == 1
            challenge = await raw('push/native/pair-witness/challenge', {'contract_version': 1, **identities[index]}, index)
            challenges.append(challenge)
            original = native.pending[identities[index]['device_id']][1]
            original_deadline = native.pending[identities[index]['device_id']][0]
            receipt = await raw('push/native/pair-witness/register', {'contract_version': 1, **identities[index],
                'operation_id': challenge['operation_id'], 'apple_proof': {'kind': 'attestation',
                    'key_id_b64': base64.b64encode(b'K' * 32).decode(),
                    'proof_b64': base64.b64encode(b'DECLARED SYNTHETIC APP ATTEST API INPUT').decode()}}, index)
            assert receipt['state'] == 'registered' and receipt['operation_id'] in role_receipts
            assert native.pending[identities[index]['device_id']][0] == original_deadline
            assert original.challenge['expires_at_ms'] == receipt['expires_at_ms']
        pool = surface._native_widget_preparation
        assert len(pool.roles) == 2 and len(enrol_keys) == 2 and len(set(enrol_keys.values())) == 2
        records = [pool.roles[id(hass.data['djconnect'][entry].surface_pair_registration)]
            for entry in ('owner-entry', 'second-entry')]
        assert records[0].lifecycle.journal is records[1].lifecycle.journal
        case('two_actual_http_optins_firstkey_P256_winners_original_hooks_distinct_roles_shared_SQL_journal')
        count = len(calls)
        await raw('push/native/pair-witness/register', {'contract_version': 1, **identities[1],
            'operation_id': challenges[1]['operation_id'], 'apple_proof': {'kind': 'attestation',
                'key_id_b64': base64.b64encode(b'K' * 32).decode(), 'proof_b64': base64.b64encode(b'SYNTHETIC').decode()}}, 1, 409)
        assert len(calls) == count
        case('register_replay_cannot_mint_another_original_winner_or_role_RPC')
        wrong = {'contract_version': 1, **first_identity, 'operation_id': _operation(int(time.time() * 1000)), 'session_id': 'wrong-session'}
        await raw('push/surface/widget/prepare', wrong, expected=409)
        assert records[0].handle is None and len(calls) == count
        case('wrong_session_creates_no_handle_or_RPC')
        prepared_body = {'contract_version': 1, **identities[1], 'operation_id': _operation(int(time.time() * 1000)), 'session_id': sid}
        prepared = await raw('push/surface/widget/prepare', prepared_body, 1)
        purpose = records[1].handle.purpose
        expiry = json.loads(purpose.policy_json)['original_grant_expires_at_ms']
        count = len(calls)
        assert await raw('push/surface/widget/prepare', prepared_body, 1) == prepared
        assert len(calls) == count and records[1].handle.purpose is purpose
        assert json.loads(purpose.policy_json)['original_grant_expires_at_ms'] == expiry
        case('actual_prepare_and_exact_replay_reuse_same_original_purpose_expiry_zero_RPC')
        context = {**identities[1], 'contract_version': 3, 'session_id': sid, 'operation_id': _operation(int(time.time() * 1000))}
        await raw('push/surface/context', pre_context, 1, 409)
        current = await raw('push/surface/context', context, 1)
        assert current['contract_version'] == 3 and current['expires_at_ms'] == expiry
        assert 0 < current['context_remaining_at_original_start_ms'] <= 30000
        assert current['context_remaining_at_original_start_ms'] <= current['purpose_remaining_at_original_start_ms'] <= 28800000
        assert await raw('push/surface/context', context, 1) == current
        assert len(calls) == count
        case('real_Core_context_after_prepare_is_server_metadata_not_native_clock_or_target_permission')
        pause_issue_for[0] = first_identity['device_id']
        first_prepare = {'contract_version': 1, **first_identity, 'operation_id': _operation(int(time.time() * 1000)), 'session_id': sid}
        await raw('push/surface/widget/prepare', first_prepare, expected=403)
        assert records[0].handle.closed and records[0].handle.purpose is None
        assert records[1].handle.purpose is purpose and purpose.is_current()
        case('actual_HTTP_consent_off_during_issue_fences_late_adoption_and_preserves_other_pair')
        count = len(calls)
        await raw('push/surface/widget/prepare', first_prepare, expected=403)
        assert len(calls) == count
        case('withdrawn_original_prepare_cannot_retry_role_or_issue')
        await raw('push/surface/register', {'contract_version': 1, **identities[1], 'session_id': sid}, 1, 409)
        assert len(calls) == count
        case('native_registration_without_actual_v3_context_target_inputs_remains_closed')
        native.stop_retirement_delivery()
        await close_surface_service(hass)
        assert not surface._purposes and surface.closed
        case('service_close_scrubs_original_RAM_purposes_without_positive_restore')
        await manager.async_end(owner_profile_id='profile-a', session_id=sid)
    from cryptography import __version__ as crypto_version
    return {'requests': http_evidence, 'cases': cases, 'actual_P256_SQLite_HA_Store': True,
        'cryptography_version': crypto_version, 'declared_API_routes': calls,
        'actual_firstkey_winners': len(enrol_keys), 'native_issuer_roles': len(role_receipts),
        'synthetic_boundaries': ['API HTTP replies/AppAttest decision', 'Spotify source metadata',
            'initial DJ narration and observer start suppressed'],
        'external_API_provider_model_calls': 0, 'native_clock_target_restore_APNs_acceptance': 'NOT_RUN',
        'installed_or_physical_acceptance': 'NOT_CLAIMED'}


async def main():
    from homeassistant.config_entries import ConfigEntryStore
    lab = Path(os.environ['DJC_LAB_ROOT'])
    if not lab.is_dir() or any(lab.iterdir()):
        raise RuntimeError('A new empty private lab is required')
    before = product_pins()
    original_entry = harness.owning_harness.entry
    original_save = ConfigEntryStore.async_save
    def configured_entry(identifier, data):
        if identifier in {'owner-entry', 'second-entry'}:
            data = {**data, 'ha_install_id': 'synthetic-actual-ha', 'djconnect_install_token': TOKEN,
                'music_backend': 'source-spotify', 'profile_backend_entry_id': 'source-entry',
                'music_account_id': 'source-account'}
        elif identifier == 'source-entry':
            data = {**data, 'music_backend': 'source-spotify', 'profile_id': 'profile-a',
                'spotify_client_id': 'synthetic-source-client'}
        return original_entry(identifier, data)
    async def initial_entries(store, data, *args, **kwargs):
        entries = data.get('entries') if isinstance(data, dict) else None
        if entries and not any(entry['entry_id'] == 'second-entry' for entry in entries):
            second = configured_entry('second-entry', {'device_id': SECOND, 'client_type': 'ios',
                'profile_id': 'profile-a', 'pair_code': '654321'})
            data = {**data, 'entries': [*entries, second.as_storage_fragment]}
        return await original_save(store, data, *args, **kwargs)
    harness.qualify = qualify
    with patch.object(harness.owning_harness, 'entry', configured_entry), patch.object(ConfigEntryStore, 'async_save', initial_entries):
        await harness.run()
    assert product_pins() == before
    result = json.loads((lab / 'http-requested-moments-receipt.json').read_text())
    result.update(product_source_pins=before, product_source_count=len(before),
        product_source_before_after_equal=True,
        owning_harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        reused_harnesses={name: hashlib.sha256((ROOT / 'scripts/verification' / name).read_bytes()).hexdigest()
            for name in ('verify_requested_moments_http.py', 'verify_session_conversation_history_http.py')})
    output = lab / 'native-widget-winner-actual-ha.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'native_widget_actual_HA': 'PASS', 'cases': len(result['extension']['cases']),
        'product_sources': len(before), 'receipt_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    asyncio.run(main())
