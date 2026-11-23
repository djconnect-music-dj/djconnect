"""Synthetic public-audience event vector and genuine pure-state display grants.

The existing production Live-impressie producer is owner-only; this conditional
purpose test does not promote that producer or claim physical/public delivery.
"""
import asyncio
from dataclasses import replace
import hashlib
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_guest_presentation as fixtures
from tests import test_guest_service as ha_fixtures
from tests.test_live_impression import accepted_text


class GuestFocusMediaTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        ha_fixtures.GuestServiceTests.setUpClass()
        fixtures.GuestPresentationTests.setUpClass()
        cls.media = importlib.import_module('custom_components.djconnect.guest_focus_media')
        cls.source = importlib.import_module('custom_components.djconnect.live_impression_media')
        cls.service = importlib.import_module('custom_components.djconnect.guest_service')

    @classmethod
    def tearDownClass(cls):
        fixtures.GuestPresentationTests.tearDownClass()
        ha_fixtures.GuestServiceTests.tearDownClass()

    def setUp(self):
        self.fixture = fixtures.GuestPresentationTests()
        self.fixture.setUp()

    async def asyncSetUp(self):
        base = self.fixture.fixture
        original = self.fixture.moment
        runtime = base.runtime
        presentation = original.presentation_intent
        self.vector = accepted_text(original.source_fact, locale=base.session.locale,
            persona=presentation.dj_persona.value, mood=presentation.source_session_mood)
        accepted = self.vector.accepted
        # Explicitly declared public source vector, retaining the original
        # source/presentation clocks; never an owner-image URL or wire grant.
        self.moment = replace(original,moment_type=runtime.DJMomentType.LIVE_IMPRESSION,
            knowledge_intent=replace(original.knowledge_intent,intent_type=runtime.KnowledgeIntentType.LIVE_IMPRESSION),
            live_impression=accepted,title=accepted.title,summary=accepted.lead,content=accepted.text)
        broadcast = base.session.broadcast
        broadcast.state = replace(broadcast.state,dj_moments=tuple(
            self.moment if m.moment_id == original.moment_id else m for m in broadcast.state.dj_moments))
        actor = self.fixture.actor
        actor.manager._lock = asyncio.Lock()
        self.origin = 'https://ha.unit-source.djconnect.dev'
        self.fixture.state.selected_origin = self.origin
        self.wrapper = self.service.GuestParticipationService(SimpleNamespace(),actor.manager)
        self.wrapper.display._origin = lambda expected=None:self.origin
        self.fixture.module.focus(actor,self.moment.moment_id)
        row = self.fixture.admission._focus[actor.share.share_id]
        self.payload = {'issuer_epoch':self.fixture.state.issuer_epoch,
                        'display_id':base.display.display_id,'focus_revision':row[3]}
        self.headers = {'Authorization':'Bearer '+base.collected['grant_token']}

    async def asyncTearDown(self):
        self.fixture.tearDown()

    async def prepare(self):
        return await self.media.prepare(self.wrapper,self.payload,self.headers,self.origin)

    async def test_independent_display_purpose_original_pixels_and_licensing_no_owner_registry(self):
        with patch.object(self.source,'refetch',AsyncMock(return_value=(self.vector.pixels,self.vector.mime))) as fetch, \
             patch.object(self.source,'authority',side_effect=AssertionError('personal owner image permission borrowed')), \
             patch.object(self.source,'resolve',side_effect=AssertionError('personal owner image registry borrowed')):
            result = await self.prepare()
        result.release()
        self.assertEqual(result.media,(self.vector.pixels,self.vector.mime))
        self.assertEqual(hashlib.sha256(result.media[0]).hexdigest(),
            self.media.public_photo(self.fixture.actor.manager,self.fixture.fixture.display,self.payload['focus_revision'])['revision'])
        fetch.assert_awaited_once()
        self.assertEqual(type(result),self.media.SharedFocusMediaResult)
        result.complete()
        self.assertFalse(self.fixture.admission._focus_media_reads)
        # A response loss cannot cause an unbounded refetch loop for one focus.
        with self.assertRaises(self.media.DisplayAdmissionError):
            await self.prepare()

    async def test_owner_only_moment_cannot_be_promoted_by_guest_or_display(self):
        broadcast = self.fixture.fixture.session.broadcast
        private = replace(self.moment,presentation_intent=replace(self.moment.presentation_intent,
            visibility=type(self.moment.presentation_intent.visibility)('owner_only')))
        broadcast.state = replace(broadcast.state,dj_moments=(private,))
        with patch.object(self.source,'refetch',AsyncMock()) as fetch, self.assertRaises(self.media.DisplayAdmissionError):
            await self.prepare()
        fetch.assert_not_awaited()

    async def test_foreign_focus_and_guest_bearer_never_fetch_event_pixels(self):
        with patch.object(self.source,'refetch',AsyncMock()) as fetch:
            original = dict(self.payload)
            self.payload['focus_revision'] = 'foreign-focus'
            with self.assertRaises(self.media.DisplayAdmissionError):
                await self.prepare()
            self.payload = original
            self.headers = {'Authorization':'Bearer djcg_not_a_display_grant'}
            with self.assertRaises(self.media.DisplayAdmissionError):
                await self.prepare()
        fetch.assert_not_awaited()

    async def test_revocation_after_fetch_or_before_body_release_closes_original_scope(self):
        with patch.object(self.source,'refetch',AsyncMock(return_value=(self.vector.pixels,self.vector.mime))):
            result = await self.prepare()
        self.fixture.fixture.owner_live = False
        with self.assertRaises(self.media.DisplayAdmissionError):
            result.release()
        result.complete()
        self.assertFalse(self.fixture.admission._focus_media_reads)

    async def test_different_pixels_cannot_replace_original_event_image(self):
        with patch.object(self.source,'refetch',AsyncMock(return_value=(b'changed original pixels','image/png'))), \
             self.assertRaises(self.media.DisplayAdmissionError):
            await self.prepare()
        self.assertFalse(self.fixture.admission._focus_media_reads)
