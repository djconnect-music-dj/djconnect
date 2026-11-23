"""Actual HA ConversationInput/entity/registry/SQLite; declared model and physical-device fixtures.

Run only in a network-none container with an empty lab and readonly candidate.
Never loads HA-dev/prod configuration, credentials or a physical microphone.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch

import verify_requested_moments_http as harness


async def qualify(hass, manager, history, request, client):
    from homeassistant.components import conversation
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.core import Context
    from homeassistant.helpers import device_registry
    from custom_components.djconnect import DJConnectRuntime, pipeline
    from custom_components.djconnect.conversation import DJConnectConversationAgent
    from custom_components.djconnect.native_voice import exchange, current_admission
    from custom_components.djconnect.profile_context import profile_storage
    from custom_components.djconnect.ask_dj import service

    # Explicit fixture setup, not physical endpoint admission evidence.
    entry = harness.owning_harness.entry('native-voice-entry', {
        'client_type': 'conversation_agent', 'device_id': 'djconnect-conversation-agent',
        'assist_pipeline_id': 'history-fixture-pipeline', 'music_backend': 'later_manual',
    })
    hass.config_entries._entries[entry.entry_id] = entry
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    runtime = DJConnectRuntime(entry, device_token=None)
    hass.data['djconnect'][entry.entry_id] = runtime
    agent = DJConnectConversationAgent(runtime)
    agent.hass = hass
    registry = device_registry.async_get(hass)
    devices = [registry.async_get_or_create(config_entry_id=entry.entry_id,
        identifiers={('native_voice_fixture', name)}, name=name) for name in ('Kitchen', 'Study')]
    storage = profile_storage(hass)
    for device in devices:
        await storage.async_set_profile_mapping('personal_voice_endpoint', device.id, 'profile-a')
    calls = []
    async def model(_hass, data, **kwargs):
        assert data['agent_id'] == 'history-fixture-agent'
        assert kwargs.get('allow_agent_fallback') is False
        calls.append({'agent': data['agent_id'], 'fallback': False})
        return {'response': {'speech': {'plain': {'speech': 'A synthetic compact music explanation.'}}}}
    def user(device=devices[0], text='What is an ostinato?', conv='native-conversation', context=None):
        return conversation.ConversationInput(text=text, language='en',
            conversation_id=conv, context=context or Context(), device_id=device.id,
            satellite_id=None, agent_id='conversation.djconnect_dj')
    records = []
    with patch.object(pipeline, '_call_conversation_process_transport', model), patch.object(
            service, 'async_exchange', wraps=service.async_exchange) as shared:
        reply = await agent._async_handle_message(user(), object())
        speech = reply.response.as_dict()['speech']['plain']['speech']
        assert speech == 'I couldn’t verify enough source information to answer that reliably.', speech
        # Deliberately unsupported model prose must not become an accepted fact.
        # Positive non-model question uses the same native entity/service next.
        bound = shared.call_args.args[2]
        help_reply = await agent.async_process(user(text='help', conv='native-help'))
        assert help_reply.response.as_dict()['speech']['plain']['speech']
        assert not help_reply.continue_conversation
        assert not reply.continue_conversation
        assert reply.conversation_id == 'native-conversation'
        assert shared.await_count == 2
        assert 'session_id' not in bound['conversation_context']
        assert bound['audio_response'] == 'never'
        assert bound['ha_device_id'] == devices[0].id
        original = user(conv='retry-conversation')
        first = await exchange(hass, runtime, original)
        count = len(calls)
        replay = await exchange(hass, runtime, original)
        assert len(calls) == count
        assert first[0]['text'] == replay[0]['text']
        await exchange(hass, runtime, user(devices[1]))
        threads = history.dialogue.owners['profile:profile-a']
        assert len([key for key in threads if key.startswith('ha-')]) == 4
        assert current_admission.get() is None
        records += [{'scenario': 'actual_native_entity_common_service_help_and_unsupported_fact_rejection', 'status': 'PASS'},
                    {'scenario': 'original_ha_request_no_duplicate_model', 'status': 'PASS'},
                    {'scenario': 'two_registry_endpoints_separate_threads', 'status': 'PASS'}]
        await storage.async_set_profile_mapping('personal_voice_endpoint', devices[0].id, '')
        denied = await agent.async_process(user())
        assert 'personal access' in denied.response.as_dict()['speech']['plain']['speech']
        records.append({'scenario': 'withdrawn_personal_access', 'status': 'PASS'})
        await storage.async_set_profile_mapping('personal_voice_endpoint', devices[0].id, 'profile-a')
        # Real HA agent registry points back to this ingress: no recursion/model call.
        conversation.async_set_agent(hass, entry, agent)
        before = len(calls)
        with patch.object(pipeline, '_assist_context', return_value={'agent_id': entry.entry_id}):
            denied = await agent.async_process(user())
        assert 'separate AI conversation agent' in denied.response.as_dict()['speech']['plain']['speech']
        assert len(calls) == before
        records.append({'scenario': 'actual_ha_agent_self_reference_denied', 'status': 'PASS'})
        conversation.async_unset_agent(hass, entry)
    return {'requests': records, 'actual_ha_conversation_entity': True,
            'actual_ha_input_dataclass': True, 'actual_ha_device_registry': True,
            'common_application_service_spy': True, 'fixture_model_calls': len(calls),
            'physical_satellite': 'NOT_RUN', 'real_provider_calls': 0,
            'audible_turn_taking_and_display': 'OPEN'}


async def main():
    harness.qualify = qualify
    await harness.run()
    path = Path(os.environ['DJC_LAB_ROOT'])/'http-requested-moments-receipt.json'
    result = json.loads(path.read_text())
    path.with_name('native-voice-actual-ha.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    asyncio.run(main())
