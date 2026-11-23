"""Guest proposals exercise common dialogue and the real bounded effect journal."""
from copy import deepcopy
from dataclasses import replace
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from tests import test_guest_conversation as fixtures


class GuestRequestTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.GuestConversationTests.setUpClass()
        cls.module = importlib.import_module('custom_components.djconnect.guest_requests')
        cls.hybrid = importlib.import_module('custom_components.djconnect.hybrid_service')
        cls.spotify = importlib.import_module('custom_components.djconnect.spotify_backend')
        cls.use_cases = importlib.import_module('custom_components.djconnect.use_cases')

    @classmethod
    def tearDownClass(cls):
        fixtures.GuestConversationTests.tearDownClass()

    async def asyncSetUp(self):
        self.fixture = fixtures.GuestConversationTests()
        await self.fixture.asyncSetUp()
        # Configure a synthetic but genuinely registered original provider before
        # issuing a fresh share. Do not retrofit an old owner/source stamp.
        host = self.fixture.purpose
        self.fixture.state.revoke_session(host.active.session_id)
        from custom_components.djconnect.domain.backend import BackendProvider
        from custom_components.djconnect.domain.music_account import MusicAccountKind
        await host.storage.async_upsert_music_backend('spotify_direct', BackendProvider.SPOTIFY_DIRECT,
            display_name='Synthetic Spotify')
        await host.storage.async_upsert_music_account('guest-test-account', 'spotify_direct',
            kind=MusicAccountKind.PERSONAL, display_name='Synthetic Spotify account',
            linked_profile_ids=frozenset({'profile-a'}), provider_account_id='synthetic-provider')
        await host.storage.async_update_profile('profile-a', preferences=replace(
            host.storage.household.profiles['profile-a'].preferences,
            default_backend_id='spotify_direct', default_music_account_id='guest-test-account'))
        host.runtime.config.update(music_backend='spotify_direct', music_account_id='guest-test-account',
            spotify_client_id='synthetic-provider', spotify_refresh_token='synthetic-refresh')
        host.runtime.last_playback = {}
        host.runtime.device_status = {}
        host.runtime.update = lambda **changes: vars(host.runtime).update(changes)
        host.entry.data.update(host.runtime.config)
        host.hass.config_entries.async_entries = lambda domain: [host.entry]
        display = self.fixture.fixture.fixture
        admitted = await display.admitted()
        self.fixture.fixture.share_id = admitted.payload['share_id']
        joined = (await self.fixture.fixture.join()).payload
        self.fixture.grant = self.fixture.state.participation.authorize(guest_id=joined['guest_id'],
            token=joined['guest_token'], issuer_epoch=joined['issuer_epoch'])
        self.fixture.actor = self.fixture.guest.capture_actor(host.hass, host.manager, self.fixture.grant)
        from custom_components.djconnect.transport_operations import OperationJournal
        self.store = SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
        self.journal = OperationJournal(self.store)
        self.ops = patch.object(self.hybrid, 'operations', return_value=SimpleNamespace(journal=self.journal))
        self.ops.start()
        # The repository's stub fixtures can retain an earlier function module;
        # bind this provider seam to the exact adapter used by this fixture.
        self.provider_adapter = patch.object(self.use_cases, '_handle_spotify_command', self.spotify.handle_spotify_command)
        self.provider_adapter.start()
        self.actor, self.guest = self.fixture.actor, self.fixture.guest
        self.current_uri = 'spotify:track:'+'a'*22
        await self.actor.manager.async_update_playback_projection(owner_profile_id=self.actor.profile.profile_id,
            session_id=self.actor.active.session_id, state='playing', media_identity=self.current_uri,
            title='Synthetic current recording', artist='Synthetic current artist')
        self.requests = self.fixture.state.participation.requests
        self.item = {'uri':'spotify:track:'+'b'*22, 'title':'Heroes', 'artist':'David Bowie'}

    async def asyncTearDown(self):
        self.provider_adapter.stop()
        self.ops.stop()
        await self.fixture.asyncTearDown()

    async def test_ambiguous_recordings_offer_original_core_choices_and_selection_proposes_once(self):
        search = AsyncMock(return_value={'tracks':[self.item, {**self.item,
            'uri':'spotify:track:'+'c'*22, 'title':'Heroes (Live)'}]})
        with patch.object(self.use_cases, 'run_music_command', search):
            first = await self.guest.exchange(self.actor, self.fixture.payload('Play Heroes by David Bowie'), request=True)
            self.assertEqual(len(first['request_choices']['items']), 2)
            self.assertEqual(self.requests.records, {})
            second = await self.guest.exchange(self.actor, self.fixture.payload('the second', 'choose-second'))
            third = await self.guest.exchange(self.actor, self.fixture.payload('the second', 'choose-second'))
        self.assertEqual(search.await_count, 1)
        self.assertEqual(second['guest_request'], third['guest_request'])
        self.assertEqual(second['guest_request']['state'], 'received')
        record = next(iter(self.requests.records.values()))
        self.assertEqual(record.uri, 'spotify:track:'+'c'*22)
        self.assertFalse(record.started)
        self.assertFalse(record.sent)

    async def test_disabled_policy_cannot_become_request_authority(self):
        from custom_components.djconnect.guest_admission import ParticipationPolicy
        self.fixture.state.participation._policies[self.actor.share.share_id].policy = ParticipationPolicy(True)
        with self.assertRaises(self.guest.SessionConversationError):
            await self.guest.exchange(self.actor, self.fixture.payload('Play Heroes by David Bowie'), request=True)
        self.assertEqual(self.requests.records, {})

    def propose(self):
        return self.requests.propose(self.actor, 'original-intent', self.item)

    async def test_actual_adapter_one_post_durable_receipt_and_readonly_retry_without_host_dna(self):
        record = self.propose()
        before = deepcopy(self.fixture.history.data)
        calls = []
        backend = self.spotify.SpotifyBackend
        async def request(_backend, method, path, **kwargs):
            # Keep the real synchronous permission gate and dispatch hook while
            # replacing only provider I/O with a deterministic synthetic seam.
            self.guest.guard_spotify(method, path)
            calls.append((method, path))
            if method == 'POST':
                from custom_components.djconnect.ask_dj.dialogue import guard_effect_dispatch
                await guard_effect_dispatch(method=method, path=path)
                self.assertEqual(self.journal._state['records'][record.journal_key]['phase'], 'sent_unknown')
                return {}
            if path == '/me/player':
                return {'device':{'id':'actual-output','is_restricted':False},
                        'item':{'uri':self.current_uri}}
            return {'queue':[]}
        with patch.object(backend, '_request', request):
            first = await self.module.fulfil(self.requests, record, host=self.actor.share.owner)
            second = await self.module.fulfil(self.requests, record, host=self.actor.share.owner)
        self.assertEqual(first['state'], 'queue_confirmed')
        self.assertEqual(second['state'], 'queue_confirmed')
        self.assertEqual(sum(m == 'POST' for m,p in calls), 1)
        self.assertEqual(self.fixture.history.data, before)
        self.assertEqual(self.journal._state['records'][record.journal_key]['phase'], 'confirmed')
        self.assertNotIn('Heroes', str(self.store.async_save.call_args))
        self.assertNotIn(self.item['uri'], str(self.store.async_save.call_args))
        self.assertIsNone(self.module.current_request.get())
        self.assertIsNone(self.guest.current_guest.get())

    async def test_uncertain_post_is_never_repeated_and_matching_queue_can_confirm(self):
        record = self.propose()
        posts = []
        present = False
        async def request(_backend, method, path, **kwargs):
            self.guest.guard_spotify(method, path)
            if method == 'POST':
                from custom_components.djconnect.ask_dj.dialogue import guard_effect_dispatch
                await guard_effect_dispatch(method=method, path=path)
                posts.append(path)
                raise TimeoutError('synthetic lost acknowledgement')
            if path == '/me/player':
                return {'device':{'id':'actual-output','is_restricted':False},
                        'item':{'uri':self.current_uri}}
            return {'queue':[{'uri':record.uri, 'name':record.title}] if present else []}
        with patch.object(self.spotify.SpotifyBackend, '_request', request):
            uncertain = await self.module.fulfil(self.requests, record, host=self.actor.share.owner)
            self.assertEqual(uncertain['state'], 'effect_uncertain')
            self.assertEqual(record.state, 'effect_uncertain')
            present = True
            result = await self.module.fulfil(self.requests, record)
        self.assertEqual(len(posts), 1)
        self.assertEqual(result['state'], 'queue_confirmed')
        self.assertEqual(result['basis'], 'observed_exact_recording_in_queue')

    async def test_withdrawn_host_or_policy_denies_before_any_backend_read(self):
        record = self.propose()
        with patch.object(self.spotify.SpotifyBackend, '_request', AsyncMock()) as io:
            with self.assertRaises(self.guest.SessionConversationError):
                await self.module.fulfil(self.requests, record)
            self.fixture.state.participation.revoke_share(self.actor.share.share_id)
            with self.assertRaises(self.guest.SessionConversationError):
                await self.module.fulfil(self.requests, record, host=self.actor.share.owner)
        io.assert_not_awaited()

    async def test_other_guest_cannot_read_an_unrelated_request(self):
        record = self.propose()
        from dataclasses import replace
        alien = replace(self.actor.grant, principal_id='other-principal')
        self.fixture.state.participation._guests[alien.principal_id] = alien
        actor = self.guest.capture_actor(self.actor.hass, self.actor.manager, alien)
        with self.assertRaises(self.guest.SessionConversationError):
            self.requests.owned(actor, record.request_id)

    async def test_output_change_after_ack_cannot_claim_current_queue_or_resend(self):
        record = self.propose()
        changed = False
        posts = []
        async def request(_backend, method, path, **kwargs):
            nonlocal changed
            self.guest.guard_spotify(method,path)
            if method == 'POST':
                from custom_components.djconnect.ask_dj.dialogue import guard_effect_dispatch
                await guard_effect_dispatch(method=method,path=path)
                posts.append(path)
                changed = True
                return {}
            if path == '/me/player':
                return {'device':{'id':'other-output' if changed else 'actual-output','is_restricted':False},
                        'item':{'uri':self.current_uri}}
            return {'queue':[]}
        with patch.object(self.spotify.SpotifyBackend,'_request',request):
            first = await self.module.fulfil(self.requests,record,host=self.actor.share.owner)
            retry = await self.module.fulfil(self.requests,record)
        self.assertEqual(first['state'],'effect_uncertain')
        self.assertEqual(retry['state'],'effect_uncertain')
        self.assertEqual(len(posts),1)
        self.assertEqual(self.journal._state['records'][record.journal_key]['phase'],'unknown')
