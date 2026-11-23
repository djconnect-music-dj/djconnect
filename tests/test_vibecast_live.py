"""Live golden boundaries over the existing paired/share/guest fixture chain."""
from dataclasses import replace
import importlib
import json
import unittest

from tests.test_guest_service import GuestServiceTests


class VibeCastLiveGoldenTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        GuestServiceTests.setUpClass()
        cls.live = importlib.import_module('custom_components.djconnect.guest_live')

    @classmethod
    def tearDownClass(cls):
        GuestServiceTests.tearDownClass()

    async def asyncSetUp(self):
        self.fixture = GuestServiceTests()
        await self.fixture.asyncSetUp()
        self.state = self.fixture.fixture.manager._display_admission
        self.active = self.fixture.fixture.fixture.active
        self.share = self.state._shares[self.fixture.share_id]

    async def asyncTearDown(self):
        await self.fixture.asyncTearDown()

    async def join(self):
        data = (await self.fixture.join()).payload
        return ({key: data[key] for key in ('guest_id', 'issuer_epoch')},
                {'Authorization': 'Bearer ' + data['guest_token']})

    def playing(self, item='recording-one'):
        current = self.active.broadcast.state
        self.active.broadcast.state = replace(current, playback=replace(
            current.playback, state='playing', item_id=item, title='Recording', artist='Artist'))

    async def test_live_toggle_does_not_change_ordinary_session_content(self):
        before = self.active.broadcast.state
        await self.fixture.enable()
        await self.fixture.call('owner/configure', {'policy': {
            'information': False, 'requests': 'disabled', 'max_pending': 3}})
        self.assertIs(self.active.broadcast.state, before)
        self.assertFalse(self.live.display_status(self.state.participation, self.share.share_id)['live_enabled'])

    async def test_guest_count_is_admitted_guests_not_invitations_and_clears_on_leave(self):
        binding, headers = await self.join()
        await self.fixture.call('owner/invite')
        status = self.live.display_status(self.state.participation, self.share.share_id)
        self.assertEqual(status['guest_count'], 1)
        self.assertNotIn(binding['guest_id'], json.dumps(status))
        await self.fixture.call('leave', binding, headers=headers)
        self.assertEqual(self.live.display_status(self.state.participation, self.share.share_id)['guest_count'], 0)

    async def test_prepared_display_status_cannot_release_after_live_off_or_view_change(self):
        await self.join()
        admitted = self.fixture.admitted.payload
        binding = {key:admitted[key] for key in ('issuer_epoch', 'display_id')}
        headers = {'Authorization':'Bearer ' + admitted['grant_token']}
        result = await self.fixture.call('display/focus', binding, headers=headers)
        result.release()
        await self.fixture.call('owner/presentation', {'mode':'vibescape'})
        with self.assertRaises(self.fixture.module.DisplayAdmissionError):
            result.release()
        result = await self.fixture.call('display/focus', binding, headers=headers)
        await self.fixture.call('owner/configure', {'policy': {
            'information':False, 'requests':'disabled', 'max_pending':3}})
        with self.assertRaises(self.fixture.module.DisplayAdmissionError):
            result.release()

    async def test_reaction_retries_once_original_track_only_and_no_public_guest_identity(self):
        binding, headers = await self.join()
        self.playing()
        body = {**binding, 'client_message_id': 'reaction-one',
                'playback_item_id': 'recording-one', 'emotion': 'heart'}
        first = (await self.fixture.call('emotion', body, headers=headers)).payload
        second = (await self.fixture.call('emotion', body, headers=headers)).payload
        self.assertEqual(first['reaction']['event_id'], second['reaction']['event_id'])
        status = self.live.display_status(self.state.participation, self.share.share_id)
        self.assertEqual(len(status['reactions']), 1)
        self.assertNotIn(binding['guest_id'], json.dumps(status))
        self.playing('recording-two')
        with self.assertRaises(self.fixture.module.DisplayAdmissionError):
            await self.fixture.call('emotion', body, headers=headers)
        await self.fixture.call('leave', binding, headers=headers)
        self.assertEqual(self.state.participation._emotion_receipts, {})

    async def test_owner_presentation_changes_only_view_and_guest_cannot_change_it(self):
        binding, headers = await self.join()
        before = self.active.broadcast.state
        changed = await self.fixture.call('owner/presentation', {'mode': 'vibescape', 'dynamics':0.8})
        self.assertEqual(changed.payload['view']['mode'], 'vibescape')
        self.assertEqual(changed.payload['view']['dynamics'], 0.8)
        self.assertIs(self.active.broadcast.state, before)
        context = (await self.fixture.call('context', binding, headers=headers)).payload
        self.assertEqual(context['view']['mode'], 'vibescape')
        self.assertEqual(context['view']['dynamics'], 0.8)
        preserved = await self.fixture.call('owner/presentation', {'mode':'flow'})
        self.assertEqual(preserved.payload['view']['dynamics'], 0.8)
        self.assertEqual(context['session']['session_id'], self.active.session_id)
        self.assertIn('shared_flow', context)
        with self.assertRaises(self.fixture.module.DisplayAdmissionError):
            await self.fixture.call('owner/presentation', {'mode': 'flow'}, headers=headers)

    async def test_dynamics_is_bounded_host_only_and_late_response_keeps_original_value(self):
        for value in (-.1, 1.1, True, '0.5', float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(self.fixture.module.DisplayAdmissionError):
                await self.fixture.call('owner/presentation', {'mode':'flow', 'dynamics':value})
        first = await self.fixture.call('owner/presentation', {'mode':'flow', 'dynamics':0})
        first.release()
        await self.fixture.call('owner/presentation', {'mode':'flow', 'dynamics':1})
        with self.assertRaises(self.fixture.module.DisplayAdmissionError):
            first.release()

    async def test_live_off_revokes_guest_without_ending_host_session(self):
        binding, headers = await self.join()
        await self.fixture.call('owner/configure', {'policy': {
            'information': False, 'requests': 'disabled', 'max_pending': 3}})
        with self.assertRaises(self.fixture.module.DisplayAdmissionError):
            await self.fixture.call('context', binding, headers=headers)
        self.assertIs(self.fixture.fixture.manager.current_active(self.active.owner_profile_id), self.active)
        self.assertEqual(self.state.participation._guests, {})
        self.assertEqual(self.state.participation._emotion_receipts, {})

    async def test_share_stop_erases_live_state_without_stopping_dj_session(self):
        binding, headers = await self.join()
        await self.fixture.fixture.call('owner/revoke', {
            'session_id': self.active.session_id, 'share_id': self.share.share_id})
        with self.assertRaises(self.fixture.module.DisplayAdmissionError):
            await self.fixture.call('context', binding, headers=headers)
        self.assertNotIn(self.share.share_id, self.state._shares)
        self.assertEqual(self.state.participation._guests, {})
        self.assertIs(self.fixture.fixture.manager.current_active(self.active.owner_profile_id), self.active)
