"""Actual HA native-to-existing-For-you flow; Spotify/STT/hardware inputs are declared fixtures."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch

import verify_requested_moments_http as harness
import verify_session_for_you_http as for_you


async def native_flow(hass, manager, history, request, state):
    from homeassistant.config_entries import ConfigEntries, ConfigEntryState
    from homeassistant.components.conversation import ConversationInput
    from homeassistant.core import Context
    from homeassistant.helpers import device_registry
    from custom_components.djconnect import DJConnectRuntime
    from custom_components.djconnect.native_voice import exchange
    from custom_components.djconnect.profile_context import profile_storage
    entry = harness.owning_harness.entry('native-for-you-entry', {
        'device_id': 'djconnect-conversation-agent', 'client_type': 'conversation_agent',
        'music_backend': 'source-spotify', 'assist_pipeline_id': 'history-fixture-pipeline',
    })
    with patch.object(ConfigEntries, 'async_setup', return_value=True):
        await hass.config_entries.async_add(entry)
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    runtime = DJConnectRuntime(entry, device_token=None)
    runtime.memory = hass.data['djconnect']['owner-entry'].memory
    hass.data['djconnect'][entry.entry_id] = runtime
    device = device_registry.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id,
        identifiers={('native_voice_fixture', 'for_you_satellite')}, name='Synthetic voice endpoint')
    await profile_storage(hass).async_set_profile_mapping('personal_voice_endpoint', device.id, 'profile-a')
    def user(text, conversation):
        return ConversationInput(text=text, context=Context(), conversation_id=conversation,
            language='nl', device_id=device.id, satellite_id=None, agent_id='conversation.djconnect_dj')
    cases = {}
    for known in (True, False):
        active = manager.current_active('profile-a')
        if active:
            await manager.async_end(owner_profile_id='profile-a', session_id=active.session_id)
        state.update(active=known, playing=False, track=None, effects=[], reads=[], tracks={}, missing='')
        started, code = await request('POST', '/api/djconnect/v1/session/start', {'mood': 'groove', 'language': 'nl'})
        assert code == 201, started
        offer = started['for_you']
        assert offer['state'] == 'available', offer
        original_searches = state['reads'].count('/search')
        conversation = 'native-For-you-known-' + str(known)
        result, _, pending = await exchange(hass, runtime, user('Voor jou', conversation))
        assert result['result_set']['result_set_id'] == offer['offer_id'], result
        assert [item['action_id'] for item in result['result_set']['items']] == [item['action_id'] for item in offer['result_set']['items']]
        assert state['reads'].count('/search') == original_searches
        assert not state['effects'] and pending
        chosen = user('Speel de tweede', conversation)
        result, _, pending = await exchange(hass, runtime, chosen)
        assert result['success'], result
        if not known:
            assert result['first_play']['state'] == 'output' and pending, result
            assert not state['effects']
            result, _, pending = await exchange(hass, runtime, user('Speel de eerste', conversation))
            assert result['success'], result
        plays = [item for item in state['effects'] if item['kind'] == 'play']
        assert len(plays) == 1, state['effects']
        assert plays[0]['uris'] == offer['result_set']['items'][1]['uris']
        owner, code = await request('GET', '/api/djconnect/v1/session/active')
        assert code == 200 and not owner['for_you']['visible'], owner
        assert state['reads'].count('/search') == original_searches
        cases['native_exact_same_offer_known_output' if known else 'native_same_mix_one_output_question'] = 'PASS'
    active = manager.current_active('profile-a')
    if active:
        await manager.async_end(owner_profile_id='profile-a', session_id=active.session_id)
    state.update(active=True, playing=False, track=None, effects=[], reads=[], tracks={}, missing='')
    start_input = user('Start een DJ-sessie', 'native-start')
    result, _, pending = await exchange(hass, runtime, start_input)
    assert result['success'] and len(result['result_set']['items']) == 3 and pending, result
    searches = state['reads'].count('/search')
    assert searches == 3 and not state['effects'], state
    repeated, _, _ = await exchange(hass, runtime, start_input)
    assert repeated['success'] and state['reads'].count('/search') == searches
    assert not state['effects']
    original_session = manager.current_active('profile-a').session_id
    # Force persistent-history retry instead of the original RAM admission.
    frames = history.dialogue.owners['profile:profile-a']
    for key in list(frames):
        if key.startswith('ha-'):
            del frames[key]
    saved_replay, _, _ = await exchange(hass, runtime, start_input)
    assert saved_replay['success'] and manager.current_active('profile-a').session_id == original_session
    from custom_components.djconnect import api_handlers
    from custom_components.djconnect.playback_observation import playback_observation_manager
    # The parent For-you lab stubs background observation startup. Exercise the
    # real stop coordinator here rather than awaiting its parent's sync Mock.
    with patch.object(api_handlers, 'playback_observation_manager', playback_observation_manager):
        await exchange(hass, runtime, user('Beëindig de DJ-sessie', 'native-end'))
    from custom_components.djconnect.session_conversation import SessionConversationError
    try:
        await exchange(hass, runtime, start_input)
    except SessionConversationError as exc:
        assert exc.code == 'session_context_changed', exc.code
    else:
        raise AssertionError('Ended original start must not replay a false active-Session success')
    assert manager.current_active('profile-a') is None and not state['effects']
    cases['native_saved_lifecycle_replay_retains_original_target_after_disposal'] = 'PASS'
    cases['native_session_start_same_three_offers_no_playback_no_retry_regeneration'] = 'PASS'
    return cases


async def qualify(hass, manager, history, request, client):
    result = await for_you.qualify(hass, manager, history, request, client, after=native_flow, pair_receivers=True)
    return {**result, 'requests': [{'scenario': key, 'status': value} for key, value in result['cases'].items()],
            'native_HA_entity_input': True, 'physical_satellite': 'NOT_RUN'}


async def main():
    harness.qualify = qualify
    await harness.run()
    path = Path(os.environ['DJC_LAB_ROOT'])/'http-requested-moments-receipt.json'
    receipt = json.loads(path.read_text())
    path.with_name('native-voice-for-you-actual-ha.json').write_text(json.dumps(receipt, indent=2)+'\n')


if __name__ == '__main__':
    asyncio.run(main())
