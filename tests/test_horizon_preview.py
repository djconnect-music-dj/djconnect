"""Original queue/source fences for a pure ephemeral owner preview, not generation."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
import unittest

from tests import test_session_forecast as fixtures


class HorizonPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SessionForecastTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixtures.SessionForecastTests.tearDownClass.__func__(cls)

    async def prepared(self, locale='nl', persona=None):
        manager, active = await fixtures.SessionForecastTests.start(self, locale, persona)
        self.forecast = active.broadcast.forecast
        self.now, self.wall, self.source_live = 101, 1800000000, True
        self.forecast.clock = lambda:self.now
        self.forecast.wall_clock = lambda:self.wall
        self.forecast.authority = lambda:self.source_live
        self.queue = {'items':[{'title':'Observed next title', 'artist':'Observed next artist', 'genres':[]}],
                      'deadline':121, 'wall_deadline':1800000020}
        self.forecast.accept_queue(self.queue, active.broadcast.state.playback.item_id,
                                   lambda:self.source_live)
        playback = active.broadcast.state.playback
        upcoming = {'current_item_id':playback.item_id, 'title':'Observed next title',
                    'artist':'Observed next artist', 'source_url':'https://open.spotify.com/track/' + 'B'*22,
                    'artwork_url':'/api/djconnect/v1/image_proxy/prepared-original',
                    'expires_at':datetime.fromtimestamp(1800000020, UTC).isoformat()}
        active.broadcast.state = replace(active.broadcast.state, playback=replace(
            playback, duration_ms=300000, position_ms=270000))
        self.assertTrue(await manager.async_update_next_item_projection(
            owner_profile_id='owner', session_id=active.session_id,
            media_identity='spotify:track:' + 'A'*22, target_name=playback.target_name,
            up_next=upcoming, authority=lambda:self.source_live))
        return manager, active

    def test_twenty_locale_persona_previews_are_authored_from_same_observation(self):
        async def scenario():
            for language in ('en', 'nl', 'de', 'fr', 'es'):
                variants = []
                for persona in self.runtime.DJPersona:
                    _, active = await self.prepared(language, persona)
                    result = active.broadcast.as_dict()['horizon_moment']
                    self.assertEqual(result['type'], 'horizon')
                    self.assertEqual(result['current_item_id'], active.broadcast.state.playback.item_id)
                    self.assertEqual(result['session_id'], active.session_id)
                    self.assertIn('Observed next title', result['text'])
                    self.assertIn('Observed next artist', result['text'])
                    self.assertNotIn('moment_id', result)
                    self.assertEqual(result['track']['artwork_url'],
                                     '/api/djconnect/v1/image_proxy/prepared-original')
                    variants.append(result['text'])
                self.assertEqual(len(set(variants)), 4)
        asyncio.run(scenario())

    def test_read_never_renews_source_or_changes_publications(self):
        async def scenario():
            _, active = await self.prepared()
            original = active.broadcast.as_dict()['horizon_moment']
            before = (active.broadcast.delivery_sequence, active.moment_engine.moments,
                      active.presence_ledger.total_published, self.forecast.deadline)
            self.now += 10
            self.wall += 10
            for _ in range(20):
                self.assertEqual(active.broadcast.as_dict()['horizon_moment'], original)
            self.assertEqual((active.broadcast.delivery_sequence, active.moment_engine.moments,
                             active.presence_ledger.total_published, self.forecast.deadline), before)
            self.now = 121
            self.assertIsNone(active.broadcast.as_dict()['horizon_moment'])
        asyncio.run(scenario())

    def test_source_pause_wrong_recording_early_and_end_withdraw(self):
        async def scenario():
            _, active = await self.prepared()
            broadcast = active.broadcast
            original = broadcast.state
            self.source_live = False
            self.assertIsNone(broadcast.as_dict()['horizon_moment'])
            self.source_live = True  # Independent synthetic withdrawal branches.
            for changed in (replace(original.playback, state='paused'),
                            replace(original.playback, item_id='wrong-recording'),
                            replace(original.playback, position_ms=200000),
                            replace(original.playback, position_ms=300000)):
                broadcast.state = replace(original, playback=changed)
                self.assertIsNone(broadcast.as_dict()['horizon_moment'])
        asyncio.run(scenario())

    def test_queue_change_and_wall_expiry_never_keep_old_preview(self):
        async def scenario():
            _, active = await self.prepared()
            self.queue['items'][0]['title'] = 'Different next track'
            self.forecast.accept_queue(self.queue, active.broadcast.state.playback.item_id,
                                       lambda:self.source_live)
            self.assertIsNone(active.broadcast.as_dict()['horizon_moment'])
            _, active = await self.prepared()
            self.wall = 1800000020
            self.assertIsNone(active.broadcast.as_dict()['horizon_moment'])
        asyncio.run(scenario())

    def test_history_shared_and_old_playback_frames_cannot_gain_owner_preview(self):
        async def scenario():
            _, active = await self.prepared()
            broadcast = active.broadcast
            self.assertNotIn('horizon_moment', broadcast.as_dict(include_owner_only=False))
            historical = broadcast._safe_delivery_payload({'horizon_moment':{'untrusted':'old'}}, historical=True)
            self.assertNotIn('horizon_moment', historical)
            old = broadcast.state.playback.as_dict()
            old['position_ms'] = 0
            replay = broadcast._safe_delivery_payload({'playback':old})
            self.assertIsNone(replay['horizon_moment'])
        asyncio.run(scenario())
