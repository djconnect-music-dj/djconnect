"""Real HA/TLS/paired host/browser/native registry/Core/journal; synthetic provider I/O.

Readonly source and empty network-none lab only. No physical mic, installed app,
production Spotify, publication, personal history or editorial acceptance claim.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import inspect
import json
import os
from pathlib import Path
import secrets
from unittest.mock import patch

import verify_requested_moments_http as harness


async def qualify(hass, manager, history, request, client, *, party_request_golden=None):
    from homeassistant.components import conversation
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.core import Context
    from homeassistant.helpers import device_registry
    from custom_components.djconnect import DJConnectRuntime
    from custom_components.djconnect.conversation import DJConnectConversationAgent
    from custom_components.djconnect.guest_conversation import current_guest
    from custom_components.djconnect.guest_requests import current_request
    from custom_components.djconnect.display_admission import DisplayAdmissionError
    from custom_components.djconnect.profile_context import profile_storage
    from custom_components.djconnect.domain.music_account import MusicAccountKind
    from custom_components.djconnect.spotify_backend import SpotifyBackend
    from custom_components.djconnect.ask_dj import service

    from homeassistant.helpers import aiohttp_client
    import socket
    key = aiohttp_client._make_key(True, socket.AF_UNSPEC, aiohttp_client.ssl_util.SSLCipherList.PYTHON_DEFAULT)
    hass.data.setdefault(aiohttp_client.DATA_CLIENTSESSION, {})[key] = client.session
    captured = inspect.getclosurevars(request).nonlocals
    identity, owner_headers = captured['identity'], captured['headers']
    selected = 'https://ha.shared-guest.djconnect.dev'
    hass.config.external_url = selected
    storage = profile_storage(hass)
    provider_entry = hass.config_entries.async_get_entry('source-entry')
    hass.config_entries.async_update_entry(provider_entry, data={**provider_entry.data,
        'profile_id':'profile-a', 'music_backend':'source-spotify', 'music_account_id':'source-account',
        'spotify_client_id':'synthetic-provider'})
    hass.data['djconnect'][provider_entry.entry_id] = DJConnectRuntime(provider_entry)
    await storage.async_upsert_music_account('source-account','source-spotify',
        kind=MusicAccountKind.PERSONAL, display_name='Synthetic guest fixture source',
        provider_account_id='synthetic-provider', linked_profile_ids=frozenset({'profile-a'}))
    await storage.async_update_profile('profile-a', preferences=replace(
        storage.household.profiles['profile-a'].preferences,
        default_backend_id='source-spotify', default_music_account_id='source-account'))
    active = await manager.async_start(owner_profile_id='profile-a', locale='en')
    sid = active.session_id
    current_uri, requested_uri = 'spotify:track:'+'A'*22, 'spotify:track:'+'C'*22
    await manager.async_update_playback_projection(owner_profile_id='profile-a', session_id=sid,
        state='playing', media_identity=current_uri, title='Fixture track', artist='Fixture artist',
        duration_ms=300000, position_ms=1000)
    cases = []

    async def post(namespace, action, body, *, token=None, owner=False, expected=200, origin=selected):
        headers = dict(owner_headers) if owner else ({'Authorization':'Bearer '+token} if token else {})
        if origin is not None:
            headers['Origin'] = origin
        data = {'contract_version':1, **body}
        if owner:
            data['identity'] = identity
        response = await client.post('/api/djconnect/v1/'+namespace+'/'+action, headers=headers, json=data)
        value = await response.json()
        assert response.status == expected, (namespace, action, response.status, value.get('error'))
        assert response.headers['Cache-Control'] == 'no-store'
        return value

    nonce = secrets.token_urlsafe(32)
    claim = await post('display','claim', {'browser_nonce':nonce})
    await post('display','owner/approve', {**{k:claim[k] for k in (
        'issuer_epoch','claim_id','browser_generation','code')}, 'session_id':sid,
        'share':{'mode':'create','consent':True}}, owner=True)
    display = await post('display','collect',{**{k:claim[k] for k in (
        'issuer_epoch','claim_id','browser_generation','claim_secret')},'browser_nonce':nonce})
    host = {'session_id':sid,'share_id':display['share_id']}
    stale_context = Context()
    policy = {'information':True,'requests':'review','max_pending':3,'screen_focus':True}
    await post('participation','owner/configure', {**host,'policy':policy}, owner=True)
    await post('participation','owner/configure', {**host,'policy':policy,'identity':identity}, token=display['grant_token'], expected=401)
    invited = await post('participation','owner/invite', host, owner=True)
    invitation = {k:invited[k] for k in ('issuer_epoch','invitation_id','invitation_secret')}
    joined = await post('participation','redeem', invitation)
    await post('participation','redeem', invitation, expected=401)
    binding = {k:joined[k] for k in ('issuer_epoch','guest_id')}
    token = joined['guest_token']
    await post('participation','context', binding, token=display['grant_token'], expected=401)
    await post('participation','context', binding, token=token, origin='https://foreign.djconnect.dev', expected=403)
    context = await post('participation','context', binding, token=token)
    assert context['capabilities']['music_dna'] is False and 'profile_id' not in json.dumps(context)
    cases.append({'scenario':'actual_paired_host_separate_guest_and_display_tokens_closed_origin_single_use', 'status':'PASS'})
    page = await client.get('/djconnect/vibecast/guest')
    assert page.status == 200 and 'frame-ancestors' in page.headers['Content-Security-Policy']
    assert 'guest_token' not in (await page.text()).split('<script>')[0]
    qr = await post('participation','display/invitation', {k:display[k] for k in ('issuer_epoch','display_id')},
                    token=display['grant_token'])
    assert qr['qr_data_uri'].startswith('data:image/svg+xml;base64,')
    cases.append({'scenario':'registered_generated_guest_shell_and_real_segno_display_invitation','status':'PASS'})

    native_entry = harness.owning_harness.entry('shared-native-entry', {
        'client_type':'conversation_agent','device_id':'djconnect-conversation-agent',
        'assist_pipeline_id':'history-fixture-pipeline','music_backend':'later_manual'})
    hass.config_entries._entries[native_entry.entry_id] = native_entry
    native_entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    runtime = DJConnectRuntime(native_entry)
    hass.data['djconnect'][native_entry.entry_id] = runtime
    agent = DJConnectConversationAgent(runtime)
    agent.hass = hass
    registry = device_registry.async_get(hass)
    devices = [registry.async_get_or_create(config_entry_id=native_entry.entry_id,
        identifiers={('shared_guest_fixture',name)}, name=name) for name in ('Room one','Room two')]
    for device in devices:
        await post('participation','owner/voice', {**host,'ha_device_id':device.id}, owner=True)
    await asyncio.sleep(.003)  # Real HA ULID millisecond boundary after endpoint admission.
    def user(text, device=devices[0], identifier=None):
        return conversation.ConversationInput(text=text, language='en', conversation_id='same-ha-thread',
            context=identifier or Context(), device_id=device.id, satellite_id=None, agent_id='conversation.djconnect_dj')

    from custom_components.djconnect.native_voice import exchange as native_exchange
    from custom_components.djconnect.session_conversation import SessionConversationError
    try:
        await native_exchange(hass, runtime, user('Play Fixture request by Fixture artist', identifier=stale_context))
    except SessionConversationError as exc:
        assert exc.code == 'guest_voice_context_changed'
    else:
        raise AssertionError('An actual old HA Context cannot cross room admission')
    cases.append({'scenario':'actual_HA_context_predating_shared_endpoint_admission_denied_without_fabricated_epoch','status':'PASS'})
    queue, writes, model_calls = [], [], []
    async def provider(backend, method, path, **kwargs):
        from custom_components.djconnect.guest_conversation import guard_spotify
        from custom_components.djconnect.ask_dj.dialogue import guard_effect_dispatch
        guard_spotify(method, path)
        if method == 'POST':
            await guard_effect_dispatch(method=method, path=path)
            writes.append(path)
            queue.append({'uri':requested_uri,'name':'Fixture request','artists':[{'name':'Fixture artist'}]})
            return {}
        if path == '/me/player':
            return {'device':{'id':'synthetic-current-output','is_restricted':False},'item':{'uri':current_uri}}
        if path == '/me/player/queue':
            return {'queue':list(queue)}
        if path.startswith('/search?'):
            return {'tracks':{'items':[{'id':letter*22,'uri':'spotify:track:'+letter*22,
                'name':name,'artists':[{'name':'Fixture artist'}]} for letter,name in (
                ('B','Fixture request (Live)'),('C','Fixture request'))]}}
        raise AssertionError('Undeclared provider read: '+path)

    before = json.dumps(history.data, sort_keys=True)
    with patch.object(SpotifyBackend, '_request', provider), patch.object(service, 'async_exchange', wraps=service.async_exchange) as common:
        first = await agent.async_process(user('What is playing?'))
        assert first.response.as_dict()['speech']['plain']['speech']
        await agent.async_process(user('What is playing?', devices[1]))
        assert common.await_count == 2
        from custom_components.djconnect import pipeline
        async def model(_hass, data, **kwargs):
            assert data['agent_id'] == 'history-fixture-agent'
            assert kwargs.get('allow_agent_fallback') is False
            assert current_guest.get() is not None and current_request.get() is None
            assert not manager._lock.locked()
            model_calls.append('qualified_fixture_transport')
            return {'response':{'speech':{'plain':{'speech':'A synthetic unsupported music explanation.'}}}}
        with patch.object(pipeline, '_call_conversation_process_transport', model):
            general = await agent.async_process(user('What is an ostinato?'))
        speech = general.response.as_dict()['speech']['plain']['speech']
        assert 'couldn’t verify enough source information' in speech, speech
        assert not model_calls  # No evidence must be rejected before model spend.
        assert common.await_count == 3
        cases.append({'scenario':'unqualified_guest_question_refused_before_model_spend','status':'PASS'})
        from custom_components.djconnect import http as core_http
        original_reply = core_http.async_handle_ask_dj
        async def budget_probe(_hass, view, payload, **kwargs):
            if payload['text'] != 'A public guest model budget fixture':
                return await original_reply(_hass, view, payload, **kwargs)
            turn, qualified = await pipeline._reserve_qualified_model_call(hass, {
                'agent_id':'history-fixture-agent','text':'Declared synthetic public model input'}, None)
            assert qualified is not None and turn.scope.startswith('guest:')
            actor = current_guest.get()
            guests = manager._display_admission.participation
            assert guests._model_guests[actor.grant.principal_id]
            assert guests._model_shares[actor.share.share_id]
            return {'success':True,'text':'Declared synthetic public response.'}
        with patch.object(core_http, 'async_handle_ask_dj', budget_probe):
            reserved = await agent.async_process(user('A public guest model budget fixture'))
        assert reserved.response.as_dict()['speech']['plain']['speech'] == 'Declared synthetic public response.'
        cases.append({'scenario':'real_common_frame_supported_HA_model_reservation_charges_guest_and_share_declared_reply_fixture','status':'PASS'})
        no_conversation = replace(user('What is playing?'), conversation_id=None)
        initial = await native_exchange(hass, runtime, no_conversation)
        repeated = await native_exchange(hass, runtime, no_conversation)
        assert initial[1] == repeated[1] and initial[0]['text'] == repeated[0]['text']
        cases.append({'scenario':'same_real_HA_context_without_conversation_id_keeps_original_reference_on_retry','status':'PASS'})
        owner_scopes = [key for key in history.dialogue.owners if key.startswith('guest:')]
        assert len(owner_scopes) == 2
        original = user('Play Fixture request by Fixture artist')
        offer = await agent.async_process(original)
        if not offer.continue_conversation:
            from custom_components.djconnect.native_voice import exchange as native_exchange
            diagnostic = await native_exchange(hass, runtime, original)
            raise AssertionError(('request_not_pending', diagnostic[0].get('text')))
        assert offer.continue_conversation
        assert len(writes) == 0
        chosen_input = user('the second')
        await agent.async_process(chosen_input)
        await agent.async_process(chosen_input)
        requests = manager._display_admission.participation.requests
        assert len(requests.records) == 1
        record = next(iter(requests.records.values()))
        assert record.uri == requested_uri and record.state == 'received' and not record.sent
        await post('participation','owner/decide', {**host,'request_id':record.request_id,'decision':'accept'}, owner=True)
        assert len(writes) == 1 and record.state == 'queue_confirmed', (len(writes),record.public(), record.actor.active.broadcast.state.playback.item_id)
        # Same selected recording from browser joins the existing request; it
        # never creates a new queue entry or a personal history contribution.
        browser_offer = await post('participation','request',{**binding,'text':'Fixture request',
            'client_message_id':'browser-proposal','language':'en'}, token=token)
        choices = browser_offer['request_choices']
        result = await post('participation','request',{**binding,'text':'Fixture request',
            'client_message_id':'browser-selection','language':'en','choice_action':{
                'result_set_id':choices['result_set_id'],'action_id':choices['items'][1]['action_id']}}, token=token)
        assert result['guest_request']['request_id'] == record.request_id
        assert len(writes) == 1
        observed = await post('participation','request/status',{**binding,'request_id':record.request_id}, token=token)
        assert observed['request']['state'] == 'queue_confirmed' and len(writes) == 1
        await manager.async_update_playback_projection(owner_profile_id='profile-a', session_id=sid,
            state='playing', media_identity=requested_uri, title='Fixture request', artist='Fixture artist')
        observed = await post('participation','request/status',{**binding,'request_id':record.request_id}, token=token)
        assert observed['request']['state'] == 'actually_playing' and len(writes) == 1
        await post('participation','ask',{**binding,'text':'wat is mijn music dna',
            'client_message_id':'private-denied'}, token=token, expected=403)
    golden = None
    if party_request_golden is not None:
        golden = await party_request_golden(hass, manager, client, post, host, selected, requested_uri)
    assert json.dumps(history.data, sort_keys=True) == before
    assert current_guest.get() is None and current_request.get() is None
    assert manager.current_active('profile-a').session_id == sid
    cases += [{'scenario':name,'status':'PASS'} for name in (
        'actual_native_entity_two_room_scopes_same_core_no_personal_history',
        'native_version_choices_retry_one_request_original_core_offer',
        'real_owner_decision_existing_durable_journal_one_queue_post',
        'browser_native_same_recording_coalescence_and_readonly_status',
        'independent_playback_observation_required_for_actually_playing')]
    await post('participation','owner/configure', {**host,'policy':{
        'information':False,'requests':'disabled','max_pending':3,'screen_focus':False}}, owner=True)
    await post('participation','context', binding, token=token, expected=401)
    assert not any(scope.startswith('guest:') for scope in history.dialogue.owners)
    cases.append({'scenario':'host_withdrawal_discards_both_native_and_browser_operational_scopes','status':'PASS'})
    from homeassistant import loader
    integration = await loader.async_get_integration(hass, 'djconnect')
    await integration.async_get_platform('config_flow')
    options = hass.config_entries.options
    opened = await options.async_init(native_entry.entry_id)
    assert opened['type'] == 'form', opened.get('type')
    controls = await options.async_configure(opened['flow_id'], {'options_action':'guest_participation'})
    assert controls['type'] == 'form' and controls['step_id'] == 'guest_participation', controls.get('type')
    updated = await options.async_configure(controls['flow_id'], {
        'share_id':display['share_id'], 'participation_mode':'review', 'screen_focus':True,
        'max_pending':3, 'shared_voice_endpoints':[d.id for d in devices],
        'request_id':'', 'decision':'none'})
    assert updated['type'] == 'abort' and updated['reason'] == 'guest_participation_updated', updated.get('reason')
    configured = manager._display_admission.participation
    assert all(device.id in configured._voice for device in devices)
    from custom_components.djconnect.guest_host import InstallationAdminConsent
    assert type(configured._policies[display['share_id']].owner) is InstallationAdminConsent
    try:
        manager._display_admission._owner(configured._policies[display['share_id']].owner)
    except DisplayAdmissionError:
        pass
    else:
        raise AssertionError('HA administration must not become B paired-owner authority')
    cases.append({'scenario':'actual_HA_options_flow_distinct_admin_consent_two_room_endpoints_no_B_owner_promotion','status':'PASS'})
    return {'requests':cases,'actual_ha':True,'actual_tls':True,'common_application_service':True,
            **({'party_request_golden': golden} if golden is not None else {}),
            'provider_io':'DECLARED_SYNTHETIC','fixture_model_calls':len(model_calls),'queue_posts':len(writes),'physical_satellite':'NOT_RUN',
            'installed':'NOT_RUN','real_provider':'NOT_RUN','editorial_acceptance':'OPEN'}


async def main():
    harness.qualify = qualify
    await harness.run()
    path = Path(os.environ['DJC_LAB_ROOT'])/'http-requested-moments-receipt.json'
    raw = path.read_bytes()
    path.with_name('shared-guest-actual-ha.json').write_bytes(raw)
    print(json.dumps({'shared_guest':'PASS','receipt_sha256':hashlib.sha256(raw).hexdigest()}))


if __name__ == '__main__':
    asyncio.run(main())
