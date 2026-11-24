"""Single cancellable HA-owner service, real Runtime plus synthetic HTTP/model."""
import asyncio
import unittest

from tests import test_bulletin_runtime as runtime_fixture
from tests.test_bulletin_builder import Store
from tests.test_bulletin_intake import HTTP, Response, rss
from custom_components.djconnect.bulletin_intake import PRIVATE_SOURCES, SOURCES
from custom_components.djconnect.bulletin_service import BulletinService


class BulletinServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        runtime_fixture.BulletinRuntimeTests.setUpClass()
        self.fixture = runtime_fixture.BulletinRuntimeTests()
        await self.fixture.asyncSetUp()
        self.fixture.calls.clear()
        self.http = HTTP()
        self.http.closed = 0
        async def close():
            self.http.closed += 1
        self.http.close = close
        from datetime import datetime, timezone
        from email.utils import format_datetime
        self.http.reply = lambda source: Response(200, rss(source,
            date=format_datetime(datetime.fromtimestamp(self.fixture.items[0].published_at, timezone.utc)),
            title=self.fixture.items[0 if source == SOURCES[0] else 1].title,
            suffix="one" if source == SOURCES[0] else "two")) if source in SOURCES[:2] else Response(503)
        self.unsubscribed = 0
        self.callbacks = []
        self.tasks = []
        def subscribe(callback):
            self.callbacks.append(callback)
            def unsubscribe():
                self.unsubscribed += 1
            return unsubscribe
        def create(coro):
            task = asyncio.create_task(coro)
            self.tasks.append(task)
            return task
        self.store = Store()
        self.service = BulletinService(self.fixture.manager, self.store, self.http,
            create_task=create, subscribe=subscribe)

    async def asyncTearDown(self):
        await self.service.close()
        await self.fixture.asyncTearDown()
        runtime_fixture.BulletinRuntimeTests.tearDownClass()

    async def start_ready(self):
        await self.service.start()
        await self.service._task
        self.assertIsNotNone(self.service.ready(self.fixture.work.owner, self.fixture.sid))

    async def test_inventory_reads_current_pair_without_io_model_or_reservation_writes(self):
        from copy import deepcopy
        self.service.collector.sources = SOURCES[:2]
        await self.service.builder.initialize()
        self.assertEqual(self.service.availability(self.fixture.work.owner),
                         (False, "bulletin_sources_pending"))
        await self.service.collector.collect(now=self.service.wall())
        before = (deepcopy(self.store.data), list(self.http.calls), list(self.fixture.calls))
        self.assertEqual(self.service.availability(self.fixture.work.owner), (True, None))
        self.assertEqual((self.store.data, self.http.calls, self.fixture.calls), before)
        self.assertEqual(self.tasks, [])

    async def test_consumed_pair_stays_reserved_and_inventory_explains_no_new_stories(self):
        from copy import deepcopy
        self.service.collector.sources = SOURCES[:2]
        await self.start_ready()
        candidate, work = self.service.builder._candidate, self.service._work
        self.assertEqual(self.service.availability(work.owner), (True, None))
        await self.service.builder.take(candidate, session=work.session, guard=work.guard)
        before = deepcopy(self.store.data)
        self.assertEqual(self.service.availability(work.owner), (False, "bulletin_no_new_stories"))
        self.assertEqual(self.store.data, before)
        self.assertEqual(len(before["reservations"]), 4)
        self.assertEqual(len(self.fixture.calls), 2)

    async def test_missing_fresh_pair_is_distinct_from_actual_feed_failure(self):
        self.service.collector.sources = SOURCES[:2]
        await self.service.builder.initialize()
        actual = self.http.reply
        self.http.reply = lambda source: actual(source) if source == SOURCES[0] else Response(503)
        await self.service.collector.collect(now=self.service.wall())
        self.assertEqual(self.service.availability(self.fixture.work.owner),
                         (False, "bulletin_sources_temporarily_unavailable"))
        # A successful, empty original source has no transport failure.
        state = self.service.collector._state[SOURCES[1].source_id]
        state["failures"] = 0
        self.assertEqual(self.service.availability(self.fixture.work.owner),
                         (False, "bulletin_not_enough_fresh_sources"))
        self.assertEqual(self.fixture.calls, [])

    async def test_explicit_private_request_reuses_the_original_prepared_headlines(self):
        from datetime import datetime, timezone
        from email.utils import format_datetime

        self.service.collector.sources = PRIVATE_SOURCES
        stamp = format_datetime(datetime.fromtimestamp(self.fixture.items[0].published_at, timezone.utc))
        titles = ("Tech publisher announces new processor", "Parliament discusses transport funding")
        self.http.reply = lambda source: Response(200, rss(
            source, date=stamp, title=titles[PRIVATE_SOURCES.index(source)]))
        await self.start_ready()
        original, original_work = self.service.builder._candidate, self.service._work
        session_id, generate, authorize, _ = self.fixture.manager._bulletin_providers[original_work.owner]
        provider = (session_id, generate, authorize, lambda: lambda: None)
        self.assertNotEqual(str(id(provider)), original.session.source_generation)
        before = list(self.http.calls)
        self.assertEqual(self.service.availability(original_work.owner, provider=provider), (True, None))
        attempt = iter((True, False))

        def withdrawing_request():
            if not next(attempt):
                raise PermissionError("fixture_request_withdrawn")

        with self.assertRaises(PermissionError):
            await self.service.requested(original_work.owner, withdrawing_request, provider=provider)
        self.assertIs(self.service.builder._candidate, original)
        self.assertIs(self.service._work, original_work)
        taken, work = await self.service.requested(original_work.owner, lambda: None, provider=provider)
        self.assertEqual((taken.candidate_id, taken.text, taken.monotonic_deadline),
                         (original.candidate_id, original.text, original.monotonic_deadline))
        self.assertEqual(self.http.calls, before)
        self.assertEqual(self.fixture.calls, [])
        self.assertIsNone(self.service.builder._candidate)
        self.fixture.authorized = False
        with self.assertRaises(PermissionError):
            work.guard()

    async def test_single_poll_owner_prepares_without_publishing_or_duplicate_background_work(self):
        with self.assertLogs(BulletinService.__module__, level="DEBUG") as logs:
            await self.service.start()
            self.service.tick()
            self.service.tick()
            await self.service._task
        self.assertIn("candidate prepared, awaiting Planner", logs.output[0])
        self.assertEqual(len(self.tasks), 1)
        self.assertEqual(len(self.http.calls), 5)
        self.assertEqual(len(self.fixture.calls), 2)
        self.assertEqual(self.fixture.active.presence_ledger.total_published, 0)
        self.assertFalse(self.fixture.active.broadcast.state.dj_moments)
        self.assertIsNotNone(self.service.ready(self.fixture.work.owner, self.fixture.sid))
        self.assertIsNone(self.service.ready("other-owner", self.fixture.sid))
        self.assertIsNone(self.service.ready(self.fixture.work.owner, "other-session"))
        await self.service.poll()
        self.assertEqual(len(self.http.calls), 5)
        self.assertEqual(len(self.fixture.calls), 2)

    async def test_private_feeds_publish_headlines_only_to_owner_without_model(self):
        from datetime import datetime, timezone
        from email.utils import format_datetime
        from custom_components.djconnect.session_speech import moment_projection

        self.service.collector.sources = PRIVATE_SOURCES
        notices = ("Copyright 1998 - 2026 DPG Media B.V.", "Copyright © 2026, NU")
        titles = ("Tech publisher announces new processor", "Parliament discusses transport funding")
        date = format_datetime(datetime.fromtimestamp(self.fixture.items[0].published_at, timezone.utc))

        def reply(source):
            index = PRIVATE_SOURCES.index(source)
            body = rss(source, date=date, title=titles[index], description="Must never leave intake")
            body = body.replace(b"<item>", f"<copyright>{notices[index]}</copyright><item>".encode())
            if index == 1:
                body = body.replace(b"</item>", b'<dc:rights xmlns:dc="http://purl.org/dc/elements/1.1/">'
                    b'copyright photo: ANP</dc:rights></item>')
            return Response(200, body)

        self.http.reply = reply
        await self.start_ready()
        self.assertEqual(len(self.http.calls), 2)
        self.assertEqual(self.fixture.calls, [])
        moment = await self.fixture.publish()
        self.assertIsNotNone(moment)
        self.assertEqual(moment.content, f"Tweakers: {titles[0]}\n\nNU.nl: {titles[1]}")
        self.assertEqual(moment.presentation_intent.visibility.value, "owner_only")
        broadcast = self.fixture.active.broadcast
        self.assertIn(titles[0], str(broadcast.as_dict()))
        self.assertNotIn(titles[0], str(broadcast.as_dict(include_owner_only=False)))
        from dataclasses import replace
        from custom_components.djconnect.bulletin_runtime import (
            BulletinManualSpeechUse, manual_ha_speech_admitted,
        )
        speech = moment_projection(broadcast, moment, autoplay=True)
        self.assertEqual(speech["processors"], ["local_on_device", "ha_configured"])
        self.assertFalse(speech["autoplay_eligible"])
        self.assertTrue(manual_ha_speech_admitted(moment))
        self.assertNotIn("manual_speech_use", str(moment.as_dict()))
        proof = moment.bulletin
        old = replace(moment, bulletin=replace(proof, manual_speech_use=None))
        self.assertFalse(manual_ha_speech_admitted(old))
        self.assertEqual(moment_projection(broadcast, old)["processors"], ["local_on_device"])
        for forged in ({"candidate": proof.candidate},
                       BulletinManualSpeechUse(replace(proof.candidate), proof.original_guard),
                       BulletinManualSpeechUse(proof.candidate, lambda: None)):
            self.assertFalse(manual_ha_speech_admitted(
                replace(moment, bulletin=replace(proof, manual_speech_use=forged))))
        from unittest.mock import patch
        with patch("custom_components.djconnect.bulletin_runtime.time.time",
                   return_value=proof.candidate.expires_at + 1):
            self.assertFalse(manual_ha_speech_admitted(moment))
        self.fixture.authorized = False
        self.assertFalse(manual_ha_speech_admitted(moment))

    async def test_existing_planner_consumes_ready_service_once_and_stop_withdraws_further_access(self):
        await self.start_ready()
        self.assertIsNotNone(await self.fixture.publish())
        self.assertEqual(self.fixture.active.presence_ledger.total_published, 1)
        self.assertIsNone(await self.fixture.publish())
        await self.service.close()
        self.assertEqual(self.unsubscribed, 1)
        self.assertIsNone(self.fixture.manager._bulletin_service)
        self.assertIsNone(self.service.ready(self.fixture.work.owner, self.fixture.sid))
        self.service.tick()
        self.assertEqual(len(self.tasks), 1)

    async def test_close_cancels_inflight_generation_without_late_candidate_or_released_reservations(self):
        entered = asyncio.Event()
        async def wait():
            entered.set()
            await asyncio.Event().wait()
        self.fixture.hook = wait
        await self.service.start()
        await entered.wait()
        self.assertEqual(len(self.store.data["reservations"]), 4)
        await self.service.close()
        self.assertTrue(self.tasks[0].cancelled())
        self.assertIsNone(self.service.builder._candidate)
        self.assertFalse(self.fixture.active.broadcast.state.dj_moments)
        self.assertEqual(self.http.closed, 1)

    async def test_original_owner_loss_during_generation_is_silent_without_model_retry(self):
        async def withdraw():
            self.fixture.authorized = False
        self.fixture.hook = withdraw
        await self.service.start()
        await self.service._task
        self.assertIsNone(self.service.ready(self.fixture.work.owner, self.fixture.sid))
        self.assertEqual(len(self.fixture.calls), 1)
        self.fixture.authorized, self.fixture.hook = True, None
        await self.service.poll()
        self.assertEqual(len(self.fixture.calls), 1)
        self.assertFalse(self.fixture.active.broadcast.state.dj_moments)

    async def test_technical_collection_failure_drops_original_candidate_not_rebinds_it_to_fresh_authority(self):
        await self.start_ready()
        original = self.service.collector.collect
        async def unavailable(**kwargs):
            raise ValueError("synthetic-clock-failure")
        self.service.collector.collect = unavailable
        with self.assertLogs(BulletinService.__module__, level="DEBUG") as logs:
            await self.service.poll()
        self.assertIn("DJ Bulletin poll: technical failure", logs.output[0])
        self.assertNotIn("synthetic-clock-failure", "".join(logs.output))
        self.assertIsNone(self.service.builder._candidate)
        self.assertIsNone(self.service._work)
        self.fixture.revision[0] += 1
        self.service.collector.collect = original
        await self.service.poll()
        self.assertIsNone(self.service.ready(self.fixture.work.owner, self.fixture.sid))
        self.assertEqual(len(self.fixture.calls), 2)
