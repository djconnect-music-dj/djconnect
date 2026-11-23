"""Guest media purpose over real paired/share actors; prepared pixels synthetic."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib
import json
import unittest
from unittest.mock import patch

from tests import test_guest_service as fixtures


class GuestArtworkTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.GuestServiceTests.setUpClass()
        cls.delivery = importlib.import_module('custom_components.djconnect.display_delivery')

    @classmethod
    def tearDownClass(cls):
        fixtures.GuestServiceTests.tearDownClass()

    async def asyncSetUp(self):
        self.fixture = fixtures.GuestServiceTests()
        await self.fixture.asyncSetUp()
        self.manager = self.fixture.fixture.manager
        self.state = self.manager._display_admission
        self.active = self.fixture.fixture.fixture.active
        self.share = self.state._shares[self.fixture.share_id]
        self.source_live = True
        self.binding, self.headers = await self.join()
        current = self.active.broadcast.state
        self.active.broadcast.state = replace(current, playback=replace(
            current.playback, state='playing', item_id='original-item',
            source_url='https://open.spotify.com/track/' + 'a' * 22))
        now = self.state._clock()
        expiry = (datetime.now(timezone.utc) + timedelta(seconds=100)).isoformat()
        self.asset = self.delivery.DisplayArtwork(
            'prepared-original', 'original-item', self.active.broadcast.state.playback.source_url,
            b'synthetic-prepared-png', 'image/png', now + 100, expiry,
            now + 1000, expiry, lambda: self.source_live,
            frozenset({(self.share.share_id, self.share.generation)}), lambda: self.source_live)
        self.active.broadcast.display_artwork = self.asset

    async def asyncTearDown(self):
        await self.fixture.asyncTearDown()

    async def join(self):
        guest = (await self.fixture.join()).payload
        return ({key:guest[key] for key in ('issuer_epoch', 'guest_id')},
                {'Authorization':'Bearer ' + guest['guest_token']})

    async def context(self, binding=None, headers=None):
        return await self.fixture.call('context', binding or self.binding, headers=headers or self.headers)

    async def read(self, reference, binding=None, headers=None):
        return await self.fixture.call('artwork', {**(binding or self.binding), 'reference':reference},
                                       headers=headers or self.headers)

    async def test_guest_descriptor_and_binary_are_scoped_without_private_urls(self):
        result = await self.context()
        art = result.payload['playback']['artwork']
        self.assertEqual(set(art), {'reference', 'item_id', 'expires_at'})
        self.assertEqual(art['expires_at'], self.asset.expires_at)
        self.assertNotIn('artwork_url', json.dumps(result.payload))
        media = await self.read(art['reference'])
        try:
            media.release()
            self.assertEqual(media.media, (self.asset.body, 'image/png'))
            self.assertEqual(len(self.delivery.display_live_hub(self.manager).artwork_reads), 1)
        finally:
            media.complete()
        self.assertFalse(self.delivery.display_live_hub(self.manager).artwork_reads)

    async def test_reference_is_not_transferable_between_guests_or_display(self):
        reference = (await self.context()).payload['playback']['artwork']['reference']
        other, headers = await self.join()
        other_reference = (await self.context(other, headers)).payload['playback']['artwork']['reference']
        self.assertNotEqual(reference, other_reference)
        with self.assertRaises(self.fixture.module.DisplayAdmissionError):
            await self.read(reference, other, headers)
        display = self.state._displays[self.fixture.admitted.payload['display_id']]
        display_reference = self.delivery.qualified_artwork(self.active, display, self.state)[0]
        with self.assertRaises(self.fixture.module.DisplayAdmissionError):
            await self.read(display_reference)

    async def test_source_withdrawal_and_track_change_fence_pending_bytes(self):
        reference = (await self.context()).payload['playback']['artwork']['reference']
        media = await self.read(reference)
        try:
            self.source_live = False
            with self.assertRaises(self.fixture.module.DisplayAdmissionError):
                media.release()
            self.assertNotIn('artwork', (await self.context()).payload['playback'])
        finally:
            media.complete()
        self.source_live = True  # Independent branch of this synthetic source case.
        state = self.active.broadcast.state
        self.active.broadcast.state = replace(state, playback=replace(state.playback, item_id='different'))
        with self.assertRaises(self.fixture.module.DisplayAdmissionError):
            await self.read(reference)

    async def test_leave_and_live_off_fence_media_without_capacity_leak(self):
        reference = (await self.context()).payload['playback']['artwork']['reference']
        media = await self.read(reference)
        await self.fixture.call('leave', self.binding, headers=self.headers)
        try:
            with self.assertRaises(self.fixture.module.DisplayAdmissionError):
                media.release()
        finally:
            media.complete()
        self.binding, self.headers = await self.join()
        reference = (await self.context()).payload['playback']['artwork']['reference']
        media = await self.read(reference)
        await self.fixture.call('owner/configure', {'policy': {
            'information':False, 'requests':'disabled', 'max_pending':3}})
        try:
            with self.assertRaises(self.fixture.module.DisplayAdmissionError):
                media.release()
        finally:
            media.complete()
        self.assertFalse(self.delivery.display_live_hub(self.manager).artwork_reads)

    async def test_expiry_wrong_share_and_replaced_pixels_withdraw_original_reference(self):
        reference = (await self.context()).payload['playback']['artwork']['reference']
        media = await self.read(reference)
        self.active.broadcast.display_artwork = replace(self.asset, body=b'new-pixels', nonce='new')
        try:
            with self.assertRaises(self.fixture.module.DisplayAdmissionError):
                media.release()
        finally:
            media.complete()
        self.active.broadcast.display_artwork = replace(self.asset, shares=frozenset())
        self.assertNotIn('artwork', (await self.context()).payload['playback'])
        self.active.broadcast.display_artwork = self.asset
        self.active.broadcast.display_artwork = replace(self.asset, expires_at='2099-01-01T00:00:00+00:00')
        self.assertNotEqual(reference, (await self.context()).payload['playback']['artwork']['reference'])
        self.active.broadcast.display_artwork = self.asset
        with patch.object(self.state, '_clock', return_value=self.asset.deadline):
            with self.assertRaises(self.fixture.module.DisplayAdmissionError):
                await self.read(reference)

    async def test_flow_requires_public_membership_and_uses_distinct_purpose(self):
        presentation = importlib.import_module('custom_components.djconnect.guest_presentation')
        self.active.broadcast.display_flow_artwork = {'original-item':self.asset}
        shared = {'public-moment':{'moment_id':'public-moment', 'playback_item_id':'original-item'}}
        with patch.object(presentation, 'shared_items', return_value=shared):
            context = (await self.context()).payload
            reference = context['shared_flow'][0]['artwork']['reference']
            self.assertNotEqual(reference, context['playback']['artwork']['reference'])
            media = await self.read(reference)
        try:
            with self.assertRaises(self.fixture.module.DisplayAdmissionError):
                media.release()
        finally:
            media.complete()
