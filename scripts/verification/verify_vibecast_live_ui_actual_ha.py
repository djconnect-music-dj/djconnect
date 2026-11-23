"""Actual isolated HA/TLS/paired VibeCast Live UI contracts; offline provider inputs.

Reuse the unchanged shared-guest qualification and original paired/TLS setup.
No installed HA configuration, real Spotify/CDN/model, native app or physical TV
acceptance is claimed. Prepared image bytes below are an explicit fixture at the
existing media-preparation boundary, not proof of external CDN qualification.
"""
from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import hashlib
import inspect
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from unittest.mock import patch

import verify_requested_moments_http as harness
import verify_shared_guest_actual_ha as shared

ROOT = Path(os.environ['DJC_SOURCE_ROOT'])
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAANUlEQVR4nO3QsQ0AMAzDsLT//9yeoCkbeYAN6LzZdZf3x0GSKEmUJEoSJYmSREmiJFGSaMoHo8QBPwYSAhsAAAAASUVORK5CYII=')


def product_pins():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'custom_components/djconnect').rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


async def qualify(hass, manager, history, request, client):
    legacy = await shared.qualify(hass, manager, history, request, client)
    from custom_components.djconnect import api_handlers, pipeline, spotify_backend, DJConnectRuntime
    from custom_components.djconnect.domain.backend import BackendProvider
    from custom_components.djconnect.domain.music_account import MusicAccountKind
    from custom_components.djconnect.domain.profile.dj_settings import DJSettings
    from custom_components.djconnect.persistence import persistence_service
    from custom_components.djconnect.persistence.dj_settings import ProfileDJSettingsRepository
    from custom_components.djconnect.playback_observation import playback_observation_manager, PlaybackObservationManager
    from custom_components.djconnect.profile_context import profile_storage
    from custom_components.djconnect.display_delivery import DisplayArtwork, display_live_hub
    from custom_components.djconnect.surface_status_samples import OriginalSample, SourceWitness
    from custom_components.djconnect import surface_status_samples
    from custom_components.djconnect.const import API_SESSION_BROADCAST

    active = manager.current_active('profile-a')
    if active:
        await manager.async_end(owner_profile_id='profile-a', session_id=active.session_id)
    observer = playback_observation_manager(hass)
    await observer.async_stop('profile-a')
    captured = inspect.getclosurevars(request).nonlocals
    identity, owner_headers = captured['identity'], captured['headers']
    selected = 'https://ha.shared-guest.djconnect.dev'
    assert hass.config.external_url == selected
    storage = profile_storage(hass)
    await storage.async_upsert_music_backend('spotify_direct', BackendProvider.SPOTIFY_DIRECT,
        display_name='Declared Live provider fixture')
    await storage.async_upsert_music_account('live-source-account', 'spotify_direct',
        kind=MusicAccountKind.PERSONAL, display_name='Declared Live account fixture',
        provider_account_id='synthetic-live-provider', linked_profile_ids=frozenset({'profile-a'}))
    await storage.async_update_profile('profile-a', preferences=replace(
        storage.household.profiles['profile-a'].preferences,
        default_backend_id='spotify_direct', default_music_account_id='live-source-account'))
    source_entry = hass.config_entries.async_get_entry('source-entry')
    hass.config_entries.async_update_entry(source_entry, data={**source_entry.data,
        'profile_id':'profile-a','music_backend':'spotify_direct','music_account_id':'live-source-account',
        'spotify_client_id':'synthetic-live-provider'})
    hass.data['djconnect']['source-entry'] = DJConnectRuntime(source_entry)
    owner_entry = hass.config_entries.async_get_entry('owner-entry')
    hass.config_entries.async_update_entry(owner_entry, data={**owner_entry.data,
        'profile_backend_entry_id':'source-entry','music_backend':'spotify_direct','music_account_id':'live-source-account'})
    owner_runtime = hass.data['djconnect']['owner-entry']
    from custom_components.djconnect.profile_backend import profile_backend_runtime
    assert profile_backend_runtime(hass,owner_runtime,provider_only=True) is hass.data['djconnect']['source-entry']
    manager._settings_repository = ProfileDJSettingsRepository(persistence_service(hass))
    current, code = await request('GET','/api/djconnect/v1/profile/settings',{'contract_version':3})
    assert code == 200
    configured, code = await request('PATCH','/api/djconnect/v1/profile/settings',{
        'contract_version':3,'binding':current['binding'],'operation_id':str(__import__('uuid').uuid7()),
        'patch':DJSettings(presence='music_only').as_dict(),
        'expected_defaults_revision':current['snapshot']['defaults_revision'],'expected_session':None})
    assert code == 200
    cases, provider_reads, models = [], [], []

    def case(name):
        cases.append({'scenario':name,'status':'PASS'})
        (Path(os.environ['DJC_LAB_ROOT'])/'live-ui-progress.json').write_text(
            json.dumps({'status':'WIP_NOT_QUALIFIED','completed_cases':cases},indent=2)+'\n')

    async def post(namespace, action, body, *, token=None, owner=False, expected=200):
        headers = dict(owner_headers) if owner else ({'Authorization':'Bearer '+token} if token else {})
        headers['Origin'] = selected
        data = {'contract_version':1, **body}
        if owner:
            data['identity'] = identity
        response = await client.post('/api/djconnect/v1/'+namespace+'/'+action,headers=headers,json=data)
        value = await response.json()
        assert response.status == expected, (namespace, action, response.status, value.get('error'))
        assert response.headers['Cache-Control'] == 'no-store'
        return value

    async def no_external(*args, **kwargs):
        return None

    async def no_model(*args, **kwargs):
        models.append('unexpected')
        raise AssertionError('Live typed reactions and presentation require no model')

    def track(letter, name):
        return {'id':letter*22,'uri':'spotify:track:'+letter*22,'type':'track','name':name,
            'is_playable':True,'is_local':False,'duration_ms':300000,
            'artists':[{'id':'D'*22,'name':'Declared Live artist'}],
            'album':{'name':'Declared Live album','uri':'spotify:album:'+'E'*22,'images':[]}}
    current_track, next_track = track('A','Declared current track'), track('B','Declared next track')
    provider = {'position':270000,'playing':True}
    class Response:
        status = 200
        headers = {}
        def __init__(self, value): self.value = value
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def json(self, **kwargs): return deepcopy(self.value)
        async def text(self): return json.dumps(self.value)
    class Wire:
        def request(self, method, url, **kwargs):
            parsed = urlsplit(url)
            assert parsed.scheme == 'https' and parsed.hostname == 'api.spotify.com'
            route = parsed.path.removeprefix('/v1')
            assert method == 'GET', 'No provider effect is admitted in the Live UI fixture'
            provider_reads.append(route)
            if route == '/me/player':
                return Response({'is_playing':provider['playing'],'progress_ms':provider['position'],
                    'item':current_track,'device':{'id':'declared-live-output','name':'Declared Live speaker','volume_percent':35}})
            if route == '/me/player/queue':
                return Response({'currently_playing':current_track,'queue':[next_track]})
            if route == '/me/player/devices':
                return Response({'devices':[{'id':'declared-live-output','name':'Declared Live speaker','is_active':True,'is_restricted':False}]})
            if route == '/artists':
                return Response({'artists':[]})
            if route.startswith('/artists/'):
                return Response({'id':'D'*22,'name':'Declared Live artist','images':[],'genres':[]})
            raise AssertionError('Unexpected declared provider read: '+route)
    async def token(*args, **kwargs): return 'declared-synthetic-provider-token'
    async def insight(): return {}
    samples = []
    original_seal = surface_status_samples.seal
    def seal(*args, **kwargs):
        value = original_seal(*args, **kwargs)
        if value is not None:
            samples.append(value)
        return value

    with patch.object(api_handlers,'_async_generate_initial_session_moment',no_external), \
         patch.object(PlaybackObservationManager,'async_start_spotify',no_external):
        started, code = await request('POST','/api/djconnect/v1/session/start',{'mood':'groove','locale':'fr'})
    assert code == 201
    active = manager.current_active('profile-a')
    sid = active.session_id
    assert active.locale == 'fr'

    with patch.object(pipeline,'_call_conversation_process_transport',no_model):
        owner_reply, code = await request('POST','/api/djconnect/v1/ask_dj/message',{
            'client_message_id':'live-ui-owner-history','text':'help','language':'en','audio_response':'never'})
    assert code == 200 and owner_reply.get('success') and not models
    owner_history, code = await request('GET','/api/djconnect/v1/ask_dj/history')
    assert code == 200 and len(owner_history['messages']) >= 2
    history_baseline = json.dumps(history.data,sort_keys=True)
    case('actual_paired_owner_history_seeded_via_local_help_no_model_for_retention_counterproof')

    async def screen(live=None):
        nonce = secrets.token_urlsafe(32)
        claim = await post('display','claim',{'browser_nonce':nonce})
        options = {'mode':'create','consent':True,'language':'fr'}
        if live is not None:
            options['live'] = live
        await post('display','owner/approve',{
            **{k:claim[k] for k in ('issuer_epoch','claim_id','browser_generation','code')},
            'session_id':sid,'share':options},owner=True)
        display = await post('display','collect',{
            **{k:claim[k] for k in ('issuer_epoch','claim_id','browser_generation','claim_secret')},'browser_nonce':nonce})
        assert 14380 < display['share_expires_in'] <= 14400
        assert display['session_locale'] == 'fr'
        return display

    default_display = await screen()
    default_host = {'session_id':sid,'share_id':default_display['share_id']}
    disabled = await post('display','owner/context',{'session_id':sid},owner=True)
    assert disabled['live'] is False
    await post('display','owner/revoke',default_host,owner=True)
    case('actual_paired_share_create_default_four_hours_app_locale_and_live_off')
    display = await screen(True)
    host = {'session_id':sid,'share_id':display['share_id']}
    display_binding = {k:display[k] for k in ('issuer_epoch','display_id')}
    display_token = display['grant_token']
    state = manager._display_admission
    share = state._shares[display['share_id']]
    async def display_status():
        return await post('participation','display/focus',display_binding,token=display_token)
    async def join():
        invite = await post('participation','owner/invite',host,owner=True)
        joined = await post('participation','redeem',{k:invite[k] for k in ('issuer_epoch','invitation_id','invitation_secret')})
        return {k:joined[k] for k in ('issuer_epoch','guest_id')}, joined['guest_token']
    async def context(binding, token):
        return await post('participation','context',binding,token=token)
    assert (await display_status())['guest_count'] == 0
    await post('participation','display/invitation',display_binding,token=display_token)
    assert (await display_status())['guest_count'] == 0
    first, first_token = await join()
    second, second_token = await join()
    assert (await display_status())['guest_count'] == 2
    await post('participation','owner/invite',host,owner=True)
    assert (await display_status())['guest_count'] == 2
    case('actual_guest_count_only_admitted_redeemed_principals_not_display_or_invitation')

    with patch.object(pipeline,'_call_conversation_process_transport',no_model), \
         patch.object(spotify_backend,'async_get_clientsession',lambda *args,**kwargs:Wire()), \
         patch.object(spotify_backend.SpotifyBackend,'_access_token',token), \
         patch.object(manager,'async_prepare_forecast_art',no_external), \
         patch.object(surface_status_samples,'seal',seal):
        await observer.async_start_spotify(integration_runtime=owner_runtime,session=active,insight_provider=insight)
        observed = observer._spotify_sessions.get('profile-a')
        assert observed is not None
        assert samples and type(samples[-1]) is OriginalSample and type(samples[-1].witness) is SourceWitness
        sample = samples[-1]
        assert sample.current()
        snapshot = await post('display','snapshot',display_binding,token=display_token)
        assert snapshot['snapshot']['session']['locale'] == 'fr'
        rows = snapshot['snapshot']['observed_playback']
        assert len(rows) == 1 and rows[0]['title'] == 'Declared current track'
        assert 'moment_id' not in rows[0]
        original_rows = share.observed_playback
        for _ in range(3):
            assert (await context(first,first_token))['observed_playback'] == rows
        assert share.observed_playback is original_rows
        case('actual_normal_provider_observer_original_sample_public_metadata_no_read_renewal')
        owner, code = await request('GET',API_SESSION_BROADCAST.format(session_id=sid))
        assert code == 200
        preview = owner['snapshot']['horizon_moment']
        assert preview and preview['track']['title'] == 'Declared next track'
        assert 'moment_id' not in preview
        assert 'horizon_moment' not in snapshot['snapshot']
        assert 'horizon_moment' not in await context(first,first_token)
        case('actual_owner_runtime_http_near_end_preview_from_original_queue_not_shared_moment')
        before_state = active.broadcast.state
        before_models = (deepcopy(state.participation._model_guests),deepcopy(state.participation._model_shares))
        item = active.broadcast.state.playback.item_id
        reaction_body = {**first,'client_message_id':'live-ui-heart','playback_item_id':item}
        typed = await post('participation','ask',{**reaction_body,'text':'❤️'},token=first_token)
        direct = await post('participation','emotion',{**reaction_body,'emotion':'heart'},token=first_token)
        assert typed['reaction']['event_id'] == direct['reaction']['event_id']
        assert len((await display_status())['reactions']) == 1
        await post('participation','emotion',{**reaction_body,'emotion':'fire'},token=first_token,expected=409)
        await post('participation','emotion',{**reaction_body,'playback_item_id':'wrong','emotion':'heart'},token=first_token,expected=409)
        assert not models
        assert before_models == (state.participation._model_guests,state.participation._model_shares)
        assert active.broadcast.state is before_state
        case('actual_typed_emoji_and_direct_emotion_same_receipt_wrong_track_changed_retry_denied_zero_model_budget')
        changed = await post('participation','owner/presentation',{**host,'mode':'vibescape','dynamics':.8},owner=True)
        assert changed['view'] == {'mode':'vibescape','dynamics':.8}
        public = await context(first,first_token)
        assert public['view']['mode'] == 'vibescape' and public['view']['dynamics'] == .8
        assert public['session']['locale'] == 'fr'
        assert (await display_status())['view']['dynamics'] == .8
        await post('participation','owner/presentation',{**host,'identity':identity,'mode':'flow','dynamics':.1},token=first_token,expected=401)
        assert active.broadcast.state is before_state
        case('actual_host_only_mode_dynamics_reaches_guest_and_screen_without_playback_or_guest_write')
        now = state._clock()
        expiry = (datetime.now(UTC)+timedelta(seconds=40)).isoformat()
        asset = DisplayArtwork('declared-prepared-pixels',item,active.broadcast.state.playback.source_url,
            PNG,'image/png',now+40,expiry,now+1000,expiry,
            lambda:sample.witness.current(historical=True),frozenset({(share.share_id,share.generation)}),
            lambda:sample.witness.current(historical=True))
        active.broadcast.display_artwork = asset
        first_art = (await context(first,first_token))['playback']['artwork']
        second_art = (await context(second,second_token))['playback']['artwork']
        assert first_art['reference'] != second_art['reference']
        async def artwork(binding, bearer, reference, expected):
            response = await client.post('/api/djconnect/v1/participation/artwork',
                headers={'Origin':selected,'Authorization':'Bearer '+bearer},
                json={'contract_version':1,**binding,'reference':reference})
            assert response.status == expected, ('artwork',response.status)
            assert response.headers['Cache-Control'] == 'no-store'
            body = await response.read()
            if expected == 200:
                assert response.content_type == 'image/png' and body == PNG
        await artwork(first,first_token,first_art['reference'],200)
        await artwork(second,second_token,first_art['reference'],404)
        assert not display_live_hub(manager).artwork_reads
        case('actual_guest_scoped_prepared_png_binary_and_wrong_guest_reference_denial')
        assert json.dumps(history.data,sort_keys=True) == history_baseline
        await observer.async_stop('profile-a',sid)
        assert not sample.current()
        withdrawn = await context(first,first_token)
        assert 'artwork' not in withdrawn['playback'] and withdrawn['observed_playback'] == []
        await artwork(first,first_token,first_art['reference'],404)
        owner, code = await request('GET',API_SESSION_BROADCAST.format(session_id=sid))
        assert code == 200 and owner['snapshot']['horizon_moment'] is None
        case('actual_observer_source_withdrawal_removes_art_observation_and_owner_preview')
        await post('participation','owner/configure',{**host,'policy':{
            'information':False,'requests':'disabled','max_pending':3}},owner=True)
        await post('participation','context',first,token=first_token,expected=401)
        status = await display_status()
        assert status['guest_count'] == 0 and status['reactions'] == [] and not status['live_enabled']
        assert manager.current_active('profile-a') is active
        ordinary = await post('display','snapshot',display_binding,token=display_token)
        assert ordinary['snapshot']['playback']['title'] == 'Declared current track'
        case('actual_live_off_revokes_guests_and_reactions_but_preserves_host_session_and_screen')
        # Counterproof: share stop must scrub live state itself, not merely
        # observe the empty maps already produced by the separate Live-off case.
        await post('participation','owner/configure',{**host,'policy':{
            'information':True,'requests':'review','max_pending':3}},owner=True)
        final_guest, final_token = await join()
        await post('participation','emotion',{**final_guest,'client_message_id':'before-share-end',
            'playback_item_id':item,'emotion':'heart'},token=final_token)
        await post('participation','owner/invite',host,owner=True)
        ending_status = await display_status()
        assert ending_status['guest_count'] == 1 and len(ending_status['reactions']) == 1
        assert share.observed_playback, 'Retain original observation object until actual share stop'
        history_before = json.dumps(history.data,sort_keys=True)
        await post('display','owner/revoke',host,owner=True)
        await post('participation','context',final_guest,token=final_token,expected=401)
        assert not any(inv.share_id == share.share_id for inv in state.participation._invitations.values())
        assert share.share_id not in state.participation._policies
        assert share.observed_playback == () and share.observed_key == ''
        assert share.share_id not in state._shares
        assert state.participation._guests == {} and state.participation._emotion_receipts == {}
        assert json.dumps(history.data,sort_keys=True) == history_before
        assert manager.current_active('profile-a') is active
        case('actual_share_end_scrubs_original_public_object_and_guest_state_preserving_owner_history')
    assert models == []
    return {'requests':cases,'legacy_shared_guest':legacy,'actual_ha':True,'actual_verified_tls':True,
        'actual_paired_host':True,'actual_admitted_guest_principals':True,
        'provider_io':'DECLARED_SYNTHETIC_SPOTIFY_GET_RESPONSES','prepared_image':'DECLARED_SYNTHETIC_PNG_AT_EXISTING_PREPARATION_BOUNDARY',
        'live_ui_model_calls':len(models),'provider_reads':provider_reads,
        'physical_native_app_TV_and_real_provider':'NOT_RUN'}


async def main():
    lab = Path(os.environ['DJC_LAB_ROOT'])
    if not lab.is_dir() or any(lab.iterdir()):
        raise RuntimeError('A new empty private lab is required')
    before = product_pins()
    harness.qualify = qualify
    await harness.run()
    after = product_pins()
    assert before == after, 'Readonly product source changed during qualification'
    path = lab/'http-requested-moments-receipt.json'
    result = json.loads(path.read_text())
    result.update(product_source_pins=before,product_source_count=len(before),
        product_source_before_after_equal=True,
        live_ui_harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        reused_harnesses={name:hashlib.sha256((ROOT/'scripts/verification'/name).read_bytes()).hexdigest()
            for name in ('verify_requested_moments_http.py','verify_shared_guest_actual_ha.py','verify_session_conversation_history_http.py')})
    output = lab/'vibecast-live-ui-actual-ha.json'
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'vibecast_live_ui':'PASS','cases':len(result['extension']['requests']),
        'product_sources':len(before),'receipt_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    asyncio.run(main())
