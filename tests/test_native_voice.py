"""Causal native-admission/service regressions; HA registry/model boundary is synthetic here."""
from __future__ import annotations

from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from tests import test_ask_dj_contextual_dialogue as fixtures


class NativeVoiceTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SharedDialogueTest.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.SharedDialogueTest.tearDownClass()

    async def asyncSetUp(self):
        self.app = fixtures.SharedDialogueTest()
        await self.app.asyncSetUp()
        self.entry, self.storage = await self.app.native_service_fixture()
        self.hass, self.runtime = self.app.hass, self.app.runtime
        import importlib
        self.native = importlib.import_module("custom_components.djconnect.native_voice")
        self.devices = {key: SimpleNamespace(id=key) for key in ('kitchen', 'study')}
        self.registry = SimpleNamespace(async_get=self.devices.get)
        self.patches = [patch.dict(sys.modules, {
            'custom_components.djconnect.conversation': SimpleNamespace(DJConnectConversationAgent=type('NativeAgentFixture', (), {})),
            'homeassistant.helpers.device_registry': SimpleNamespace(async_get=lambda _: self.registry),
            'homeassistant.components.conversation': SimpleNamespace(ConversationEntity=object,
                async_get_agent=lambda *a: object()),
        }), patch.object(self.app.pipeline, '_get_default_assist_pipeline', return_value=SimpleNamespace(id='fixture-pipeline', conversation_engine='conversation.fixture', language='en')),
            patch.object(self.app.pipeline, '_get_assist_pipeline', return_value=SimpleNamespace(id='fixture-pipeline', conversation_engine='conversation.fixture', language='en'))]
        # Import-from-package can retain an earlier registry module even when
        # sys.modules is patched; isolate both Python import routes causally.
        self.patches.append(patch.object(sys.modules['homeassistant.helpers'], 'device_registry',
            SimpleNamespace(async_get=lambda _: self.registry), create=True))
        self.patches.append(patch.object(sys.modules['homeassistant.components'], 'conversation',
            SimpleNamespace(ConversationEntity=object, async_get_agent=lambda *a: object()), create=True))
        for value in self.patches:
            value.start()
        await self.storage.async_set_profile_mapping('personal_voice_endpoint', 'kitchen', 'profile-a')
        await self.storage.async_set_profile_mapping('personal_voice_endpoint', 'study', 'profile-a')
        await self.storage.async_set_profile_mapping('ha_user', 'ha-owner', 'profile-a')

    async def asyncTearDown(self):
        for value in reversed(self.patches):
            value.stop()
        await self.app.asyncTearDown()

    def input(self, text='What is an ostinato?', device='kitchen', conversation='conversation-1', request='request-1'):
        return SimpleNamespace(text=text, language='en', device_id=device,
            conversation_id=conversation, agent_id='conversation.djconnect',
            context=SimpleNamespace(id=request, user_id='ha-owner'))

    async def test_native_and_app_use_same_service_no_session_or_playback_for_question(self):
        import importlib
        service = importlib.import_module("custom_components.djconnect.ask_dj.service")
        with patch.object(service, 'async_exchange', wraps=service.async_exchange) as common:
            answer, conversation, pending = await self.native.exchange(self.hass, self.runtime, self.input())
        self.assertEqual(common.await_count, 1)
        self.assertTrue(answer['success'], answer)
        self.assertEqual(conversation, 'conversation-1')
        self.assertFalse(pending)
        self.assertIsNone(await self.app.fixture.manager.async_get_active('profile-a'))
        self.assertEqual(self.app.effects, [])
        payload = common.call_args.args[2]
        self.assertNotIn('session_id', payload['conversation_context'])
        self.assertNotIn('assist_pipeline_id', payload)
        self.assertEqual(payload['audio_response'], 'never')
        self.assertIsNone(self.native.current_admission.get())

    async def test_ha_retry_reuses_original_turn_without_new_model_call(self):
        first = await self.native.exchange(self.hass, self.runtime, self.input())
        count = len(self.app.prompts)
        second = await self.native.exchange(self.hass, self.runtime, self.input())
        self.assertEqual(len(self.app.prompts), count)
        self.assertEqual(first[0]['text'], second[0]['text'])
        self.assertEqual(self.app.effects, [])

    async def test_first_delivery_without_ha_conversation_id_retries_original_reference(self):
        value = self.input(conversation=None)
        first = await self.native.exchange(self.hass, self.runtime, value)
        count = len(self.app.prompts)
        second = await self.native.exchange(self.hass, self.runtime, value)
        self.assertEqual(first[1], second[1])
        self.assertEqual(first[0]['text'], second[0]['text'])
        self.assertEqual(len(self.app.prompts), count)
        self.assertEqual(self.app.effects, [])

    async def test_same_ha_conversation_on_two_satellites_has_separate_core_threads(self):
        await self.native.exchange(self.hass, self.runtime, self.input())
        await self.native.exchange(self.hass, self.runtime, self.input(device='study'))
        threads = self.app.history.dialogue.owners['profile:profile-a']
        self.assertEqual(len([k for k in threads if k.startswith('ha-')]), 2)
        self.assertNotIn('default', threads)

    async def test_untrusted_room_user_fallback_and_synthetic_device_never_grant_personal_access(self):
        await self.storage.async_set_profile_mapping('personal_voice_endpoint', 'kitchen', '')
        await self.storage.async_set_profile_mapping('ha_device', 'kitchen', 'profile-a')
        await self.storage.async_set_profile_mapping('ha_user', 'ha-owner', 'profile-a')
        for device in ('kitchen', 'missing', None):
            with self.subTest(device=device), self.assertRaises(self.native.SessionConversationError):
                await self.native.exchange(self.hass, self.runtime, self.input(device=device))
        self.assertEqual(self.app.prompts, [])
        self.assertEqual(self.app.effects, [])

    async def test_withdrawal_after_model_await_rejects_result_and_clears_context(self):
        original = self.app.pipeline._call_conversation_process_transport
        async def withdrawn(*args, **kwargs):
            result = await original(*args, **kwargs)
            await self.storage.async_set_profile_mapping('personal_voice_endpoint', 'kitchen', '')
            return result
        with patch.object(self.app.pipeline, '_call_conversation_process_transport', withdrawn):
            with self.assertRaises(self.native.SessionConversationError):
                await self.native.exchange(self.hass, self.runtime, self.input())
        self.assertIsNone(self.native.current_admission.get())
        self.assertEqual(self.app.effects, [])

    async def test_two_profiles_have_per_turn_context_without_mutating_agent_defaults(self):
        import asyncio
        import importlib
        await self.storage.async_create_profile('Other personal owner', profile_id='profile-b', default_backend_id='later_manual')
        await self.storage.async_set_profile_mapping('personal_voice_endpoint', 'study', 'profile-b')
        service = importlib.import_module('custom_components.djconnect.ask_dj.service')
        one, two = self.input(request='one'), self.input(device='study', request='two')
        one.context.user_id = two.context.user_id = None
        before = getattr(self.runtime, 'profile_context_profile_id', None)
        with patch.object(service, 'async_exchange', wraps=service.async_exchange) as common:
            a, b = await asyncio.gather(self.native.exchange(self.hass, self.runtime, one),
                                       self.native.exchange(self.hass, self.runtime, two))
        self.assertEqual((a[0]['owner_profile_id'], b[0]['owner_profile_id']), ('profile-a', 'profile-b'))
        self.assertEqual(getattr(self.runtime, 'profile_context_profile_id', None), before)
        views = [call.args[1] for call in common.call_args_list]
        self.assertIsNot(views[0], views[1])
        self.assertEqual({view.config['profile_id'] for view in views}, {'profile-a', 'profile-b'})
        self.assertEqual(self.app.effects, [])

    async def test_repeat_original_answer_is_not_music_repeat_or_new_model_work(self):
        first, _, _ = await self.native.exchange(self.hass, self.runtime, self.input())
        count = len(self.app.prompts)
        repeated, _, _ = await self.native.exchange(self.hass, self.runtime,
            self.input(text='Repeat that', request='repeat-answer'))
        self.assertIn(first['text'], repeated['text'])
        self.assertEqual(repeated['intent']['intent'], 'conversation_recall')
        self.assertEqual(len(self.app.prompts), count)
        self.assertEqual(self.app.effects, [])
        self.assertFalse(repeated.get('history_persisted'))

    async def test_stop_talking_ends_pending_input_without_pausing_music_or_model_call(self):
        await self.native.exchange(self.hass, self.runtime, self.input())
        before = len(self.app.prompts)
        result, _, pending = await self.native.exchange(self.hass, self.runtime,
            self.input(text='Stop talking', request='stop-speaking'))
        self.assertTrue(result['success'])
        self.assertEqual(result['intent']['intent'], 'conversation_stop')
        self.assertFalse(pending)
        self.assertEqual(len(self.app.prompts), before)
        self.assertEqual(self.app.effects, [])

    async def test_five_turn_subject_survives_live_track_change(self):
        active = await self.app.fixture.manager.async_start(owner_profile_id='profile-a', locale='en')
        questions = ['Who is Brian Eno?', 'Tell me more about him', 'What about his earlier work?',
                     'Has he worked solo?', 'Tell me more about that artist']
        thread = None
        for index, question in enumerate(questions):
            if index == 2:
                await self.app.fixture.manager.async_update_playback_projection(owner_profile_id='profile-a',
                    session_id=active.session_id, state='playing', media_identity='spotify:track:'+'Z'*22,
                    title='Synthetic changed recording', artist='Different synthetic artist')
            result, _, _ = await self.native.exchange(self.hass, self.runtime,
                self.input(text=question, request='topic-'+str(index)))
            actual = result['conversation']['thread_id']
            if thread is None:
                thread = actual
            self.assertEqual(actual, thread)
            frame = self.app.history.dialogue.owners['profile:profile-a'][thread]
            self.assertTrue(any(subject['name'] == 'Brian Eno' for subject in frame.subjects), frame.subjects)
        self.assertEqual(self.app.effects, [])

    async def test_ended_session_does_not_supply_an_unrelated_latest_spoken_story(self):
        active = await self.app.fixture.manager.async_start(owner_profile_id='profile-a', locale='en')
        await self.native.exchange(self.hass, self.runtime, self.input())
        await self.app.fixture.manager.async_end(owner_profile_id='profile-a', session_id=active.session_id)
        result, _, _ = await self.native.exchange(self.hass, self.runtime,
            self.input(text='What did you just say?', request='after-session-end'))
        self.assertIn('cannot establish what you just heard', result['text'])
        self.assertIsNone(self.app.fixture.manager.current_active('profile-a'))
        self.assertEqual(self.app.effects, [])

    async def test_other_ha_user_cannot_impersonate_trusted_device(self):
        user = self.input()
        user.context.user_id = 'other-user'
        with self.assertRaises(self.native.SessionConversationError):
            await self.native.exchange(self.hass, self.runtime, user)
        self.assertEqual(self.app.effects, [])
        self.assertEqual(self.app.prompts, [])

    async def test_consent_remove_regrant_cannot_replay_original_request(self):
        await self.native.exchange(self.hass, self.runtime, self.input())
        await self.storage.async_set_profile_mapping('personal_voice_endpoint', 'kitchen', '')
        await self.storage.async_set_profile_mapping('personal_voice_endpoint', 'kitchen', 'profile-a')
        with self.assertRaises(self.native.SessionConversationError):
            await self.native.exchange(self.hass, self.runtime, self.input())
        self.assertEqual(self.app.effects, [])

    async def test_changed_registry_device_and_profile_mapping_close_original_admission(self):
        admission = await self.native.admit(self.hass, self.runtime, self.input())
        self.devices['kitchen'] = SimpleNamespace(id='kitchen')
        with self.assertRaises(self.native.SessionConversationError):
            admission.validate()

    async def test_explicit_lifecycle_uses_existing_owner_without_music_effect(self):
        from unittest.mock import AsyncMock
        from custom_components.djconnect.playback_observation import PlaybackObservationManager
        with patch.object(self.app.handlers, '_async_generate_initial_session_moment', AsyncMock()), patch.object(
                PlaybackObservationManager, 'async_start_spotify', AsyncMock()):
            started, _, _ = await self.native.exchange(self.hass, self.runtime,
                self.input(text='Start a DJ session', request='start-1'))
        self.assertTrue(started['success'], started)
        active = self.app.fixture.manager.current_active('profile-a')
        self.assertIsNotNone(active)
        replay, _, _ = await self.native.exchange(self.hass, self.runtime,
            self.input(text='Start a DJ session', request='start-1'))
        self.assertTrue(replay['success'], replay)
        self.assertEqual(self.app.fixture.manager.current_active('profile-a').session_id, active.session_id)
        ended, _, _ = await self.native.exchange(self.hass, self.runtime,
            self.input(text='End the DJ session', request='end-1'))
        self.assertTrue(ended['success'], ended)
        self.assertIsNone(self.app.fixture.manager.current_active('profile-a'))
        self.assertEqual(self.app.effects, [])

    async def test_saved_lifecycle_replay_keeps_original_target_after_frame_disposal(self):
        from unittest.mock import AsyncMock
        from custom_components.djconnect.playback_observation import PlaybackObservationManager
        with patch.object(self.app.handlers, '_async_generate_initial_session_moment', AsyncMock()), patch.object(
                PlaybackObservationManager, 'async_start_spotify', AsyncMock()):
            start = self.input(text='Start a DJ session', request='saved-start')
            await self.native.exchange(self.hass, self.runtime, start)
            original = self.app.fixture.manager.current_active('profile-a').session_id
            frames = self.app.history.dialogue.owners['profile:profile-a']
            for key in list(frames):
                if key.startswith('ha-'):
                    del frames[key]
            replay, _, _ = await self.native.exchange(self.hass, self.runtime, start)
            self.assertTrue(replay['success'])
            self.assertEqual(self.app.fixture.manager.current_active('profile-a').session_id, original)
            end = self.input(text='End the DJ session', request='saved-end')
            await self.native.exchange(self.hass, self.runtime, end)
            with self.assertRaisesRegex(self.native.SessionConversationError, 'session_context_changed'):
                await self.native.exchange(self.hass, self.runtime, start)
            self.assertIsNone(self.app.fixture.manager.current_active('profile-a'))
            ended_replay, _, _ = await self.native.exchange(self.hass, self.runtime, end)
            self.assertTrue(ended_replay['success'])
            await self.native.exchange(self.hass, self.runtime,
                self.input(text='Start a DJ session', request='replacement-start'))
            with self.assertRaisesRegex(self.native.SessionConversationError, 'session_context_changed'):
                await self.native.exchange(self.hass, self.runtime, end)
            self.assertNotEqual(self.app.fixture.manager.current_active('profile-a').session_id, original)
            with self.assertRaisesRegex(self.native.SessionConversationError, 'session_context_changed'):
                await self.native.exchange(self.hass, self.runtime, start)
        self.assertEqual(self.app.effects, [])

    async def test_import_does_not_restore_personal_trust_and_profile_delete_does_not_transfer_it(self):
        from custom_components.djconnect.domain.storage import household_to_storage, household_from_storage
        saved = household_to_storage(self.storage.household)
        self.assertTrue(household_from_storage(saved).shared.personal_voice_endpoint_profile_ids)
        self.assertFalse(household_from_storage(saved, trusted_bindings=False).shared.personal_voice_endpoint_profile_ids)
        from custom_components.djconnect.domain.storage import _reassign_shared_profile_references
        shared = _reassign_shared_profile_references(self.storage.household.shared, 'profile-a', 'profile-b')
        self.assertEqual(shared.personal_voice_endpoint_profile_ids, {})


class NativeVoiceActualHAEvidenceTest(unittest.TestCase):
    def test_actual_ha_receipts_bind_all_source_and_keep_physical_and_guest_scope_open(self):
        import hashlib
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        proof = json.loads((root/'examples/client_contracts/ha_native_voice_v1/vibecast-party-20261125-personal-regression.json').read_text())
        self.assertTrue(proof['source_before_after_equal'])
        actual = {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in (root/'custom_components/djconnect').rglob('*')
                  if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'}
        self.assertEqual(proof['source_pins'], actual)
        self.assertEqual(len(actual), 361)
        for path, digest in proof['harness_pins'].items():
            self.assertEqual(hashlib.sha256((root/path).read_bytes()).hexdigest(), digest)
        self.assertEqual(len(proof['executions']), 2)
        for execution in proof['executions']:
            self.assertEqual(execution['exit_code'], 0)
            self.assertEqual(hashlib.sha256((root/execution['harness']).read_bytes()).hexdigest(), execution['harness_sha256'])
            self.assertTrue(execution['receipt']['source_unchanged'])
            self.assertEqual(execution['receipt']['extension']['physical_satellite'], 'NOT_RUN')
            self.assertEqual(execution['receipt']['extension']['real_provider_calls'], 0)
        cases = proof['executions'][1]['receipt']['extension']['cases']
        self.assertEqual({key for key in cases if key.startswith('native_')}, {
            'native_exact_same_offer_known_output', 'native_same_mix_one_output_question',
            'native_session_start_same_three_offers_no_playback_no_retry_regeneration',
            'native_saved_lifecycle_replay_retains_original_target_after_disposal'})
        self.assertEqual(set(cases.values()), {'PASS'})
        self.assertEqual(proof['shared_guest_request_display_delivery'], 'NOT_QUALIFIED_BY_PERSONAL_GATE')
        self.assertEqual(proof['installed'], 'NOT_RUN')


if __name__ == '__main__':
    unittest.main()
