"""One Core dialogue with separate ephemeral guest rights and deny-by-default reads."""
from copy import deepcopy
import importlib
import unittest
from unittest.mock import AsyncMock, patch
from tests import test_guest_service as fixtures


class GuestConversationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.GuestServiceTests.setUpClass()
        cls.guest = importlib.import_module('custom_components.djconnect.guest_conversation')
        cls.core = importlib.import_module('custom_components.djconnect.ask_dj.service')
        cls.http = importlib.import_module('custom_components.djconnect.http')

    @classmethod
    def tearDownClass(cls):
        fixtures.GuestServiceTests.tearDownClass()

    async def asyncSetUp(self):
        self.fixture = fixtures.GuestServiceTests()
        await self.fixture.asyncSetUp()
        self.joined = (await self.fixture.join()).payload
        self.purpose = self.fixture.fixture.fixture
        self.hass, self.manager = self.purpose.hass, self.purpose.manager
        self.state = self.manager._display_admission
        self.grant = self.state.participation.authorize(guest_id=self.joined['guest_id'],
            token=self.joined['guest_token'], issuer_epoch=self.joined['issuer_epoch'])
        self.actor = self.guest.capture_actor(self.hass, self.manager, self.grant)
        self.history = self.http._history_manager(self.hass, self.actor.runtime)
        await self.history.async_load()

    async def asyncTearDown(self):
        await self.fixture.asyncTearDown()

    def payload(self, text='Tell me about David Bowie', client='guest-turn'):
        return {'text':text, 'client_message_id':client, 'language':'en',
                'conversation_context':{'thread_id':'guest-thread'}}

    async def test_same_application_service_separate_scope_and_no_private_archive(self):
        from custom_components.djconnect.ask_dj.dialogue import current_turn
        before = deepcopy(self.history.data)
        scopes = []

        async def reply(_hass, runtime, payload, **kwargs):
            self.assertTrue(kwargs['ephemeral_conversation'])
            self.assertIsNone(runtime.memory)
            self.assertNotIn('device_token', runtime.config)
            self.assertNotIn('device_name', runtime.config)
            scopes.append(current_turn.get().scope)
            return {'success':True,'text':'A public reply.','owner_profile_id':'must-not-leak',
                    'audio_url':'private-owner-audio','images':[{'url':'private-owner-image'}]}

        with patch.object(self.http, 'async_handle_ask_dj', reply), patch.object(
                self.core, 'async_history_grant_revision', side_effect=AssertionError('private grant read')):
            result = await self.guest.exchange(self.actor, self.payload())
        self.assertEqual(scopes, [self.actor.scope])
        self.assertEqual(self.history.data, before)
        self.assertNotIn('owner_profile_id', result)
        self.assertNotIn('audio_url', result)
        self.assertNotIn('images', result)
        self.assertFalse(result['history_persisted'])
        self.assertTrue(result['success'])
        self.assertIsNone(self.guest.current_guest.get())

    async def test_guest_retry_deduplicates_on_its_own_original_frame(self):
        reply = AsyncMock(return_value={'success':True,'text':'Public reply.'})
        with patch.object(self.http, 'async_handle_ask_dj', reply):
            first = await self.guest.exchange(self.actor, self.payload())
            second = await self.guest.exchange(self.actor, self.payload())
        self.assertEqual(first['text'], second['text'])
        self.assertEqual(reply.await_count, 1)

    async def test_owner_actions_dna_and_private_history_references_never_reach_delegate(self):
        reply = AsyncMock(return_value={'success':True,'text':'Must not be delegated.'})
        with patch.object(self.http, 'async_handle_ask_dj', reply):
            for text in ('pause', 'End the DJ session', 'wat is mijn music dna', 'For you'):
                with self.subTest(text=text), self.assertRaises(self.guest.SessionConversationError):
                    await self.guest.exchange(self.actor, self.payload(text, text))
            body = self.payload()
            body['conversation_context']['selected_entry'] = {'session_id':'private','entry_id':'private'}
            with self.assertRaises(self.guest.SessionConversationError):
                await self.guest.exchange(self.actor, body)
        reply.assert_not_awaited()

    async def test_withdrawal_during_await_rejects_reply_and_discards_operational_scope(self):
        async def reply(*args, **kwargs):
            self.state.revoke_session(self.actor.active.session_id)
            return {'success':True,'text':'Must not escape.'}
        with patch.object(self.http, 'async_handle_ask_dj', reply), self.assertRaises(self.guest.SessionConversationError):
            await self.guest.exchange(self.actor, self.payload())
        self.assertNotIn(self.actor.scope, self.history.dialogue.owners)

    async def test_private_queries_effects_and_spotify_reads_are_denied_at_boundaries(self):
        from custom_components.djconnect.session_conversation import query_service
        from custom_components.djconnect.ask_dj.dialogue import guard_effect_dispatch, DialogueError
        token = self.guest.current_guest.set(self.actor)
        try:
            with self.assertRaises(self.guest.SessionConversationError):
                _ = query_service(self.hass)._repository
            for method, path in (('GET','/me/top/tracks'),('GET','/me/player/queue'),
                                 ('POST','/me/player/play'),('GET','/artists/../me')):
                with self.subTest(path=path), self.assertRaises(self.guest.SessionConversationError):
                    self.guest.guard_spotify(method, path)
            self.guest.guard_spotify('GET', '/search?q=public')
            with self.assertRaises(DialogueError):
                await guard_effect_dispatch(method='POST',path='/me/player/queue?uri=spotify:track:abc')
        finally:
            self.guest.current_guest.reset(token)

    async def test_actual_lower_current_track_reply_uses_shared_status_without_private_memory(self):
        from custom_components.djconnect.use_cases import run_music_command
        token = self.guest.current_guest.set(self.actor)
        try:
            status = await run_music_command(self.hass, self.guest.GuestRuntimeView(self.actor), 'status')
            self.assertNotIn('output_label', status['playback'])
            self.assertNotIn('device_id', status['playback'])
        finally:
            self.guest.current_guest.reset(token)
        result = await self.guest.exchange(self.actor, self.payload('What is playing now?'))
        self.assertIsInstance(result['text'], str)
        self.assertFalse(result['history_persisted'])

    async def test_original_common_delivery_fence_survives_dto_mapping_and_rejects_late_frame_reset(self):
        reply = AsyncMock(return_value={'success':True,'text':'Public answer.'})
        with patch.object(self.http, 'async_handle_ask_dj', reply):
            result = await self.guest.exchange(self.actor, self.payload())
        result.validate_now()
        self.history.dialogue.invalidate(self.actor.scope)
        with self.assertRaises(self.guest.SessionConversationError):
            result.validate_now()
        self.actor.validate()  # Guest authority alone would still pass.

    async def test_native_presentation_route_enters_common_service_without_model_or_publication(self):
        from custom_components.djconnect import guest_presentation
        reply = AsyncMock(return_value={'success':True,'text':'Shared presentation selected.'})
        original = self.actor.active.broadcast.state
        with patch.object(guest_presentation, 'presentation_response', reply), patch.object(
                self.core, 'async_exchange', wraps=self.core.async_exchange) as common:
            result = await self.guest.exchange(self.actor, self.payload('show that on the screen'))
        self.assertTrue(result['success'])
        self.assertEqual(common.await_count, 1)
        self.assertEqual(reply.await_count, 1)
        self.assertIs(self.actor.active.broadcast.state, original)

    async def test_guest_request_status_uses_common_service_without_model_or_private_queries(self):
        reply = AsyncMock(side_effect=AssertionError('status is not model work'))
        with patch.object(self.http, 'async_handle_ask_dj', reply), patch.object(
                self.core, 'async_history_grant_revision', side_effect=AssertionError('private grant read')):
            result = await self.guest.exchange(self.actor, self.payload('What is the status of my request?'))
        self.assertTrue(result['success'])
        self.assertIn('no request', result['text'])
        reply.assert_not_awaited()

    async def test_guest_runtime_view_cannot_read_or_overwrite_host_private_runtime_cache(self):
        host = self.actor.runtime
        host.last_text = 'A private host question'
        host.device_status = {'queue':['private queue'], 'owner_profile_id':'private'}
        host.last_playback = {'device':{'id':'private-output'},'uri':'private-recording'}
        view = self.guest.GuestRuntimeView(self.actor)
        self.assertIsNone(view.last_text)
        self.assertEqual(view.device_status, {})
        self.assertNotIn('device', view.last_playback)
        view.update(last_text='Public guest question')
        view.device_status['queue'] = []
        self.assertEqual(host.last_text, 'A private host question')
        self.assertEqual(host.device_status['queue'], ['private queue'])
        with self.assertRaises(AttributeError):
            _ = view.profile_context_profile_id
