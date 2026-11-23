"""Preparation spends no visible choice time; original issued leases never renew.

Clock/provider/narration boundaries are explicit unit seams. Original Runtime,
loaded DNA, source/grant and ordinary dialogue/result owner are reused.
"""

from copy import deepcopy
from dataclasses import replace
import importlib
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from tests import test_session_for_you as fixtures


class VisibleAdmissionTests(IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.ForYouTests.asyncSetUp
    new_session = fixtures.ForYouTests.new_session
    new_turn = fixtures.ForYouTests.new_turn
    offer = fixtures.ForYouTests.offer
    choose = fixtures.ForYouTests.choose

    async def prepared(self, duration=45, mutate=None, final=None):
        from tests.test_music_dna import FakeStore
        from custom_components.djconnect.ask_dj_history import AskDJHistoryManager
        from custom_components.djconnect.domain.storage import STORE_KEY

        self.now, self.wall = 1000.0, 2000000000.0
        fake_time = SimpleNamespace(time=lambda: self.wall, monotonic=lambda: self.now)
        self.service = importlib.import_module("custom_components.djconnect.ask_dj.service")
        for module in (self.steering, self.service):
            clock = patch.object(module, "time", fake_time)
            clock.start()
            self.addCleanup(clock.stop)
        self.for_you_history = AskDJHistoryManager(store=FakeStore())
        self.for_you_history.dialogue.clock = lambda: self.now
        storage = self.hass.data["djconnect"][STORE_KEY]
        self.context = SimpleNamespace(
            profile_id="synthetic-owner", profile=storage.household.profiles["synthetic-owner"]
        )
        source = patch(
            "custom_components.djconnect.reply_artwork.source_admission",
            return_value=(self.source, lambda: self.allowed),
        )
        source.start()
        self.addCleanup(source.stop)

        async def intro(hass, runtime, admission, directions):
            self.preparation = admission
            self.producer_turn = self.dialogue.current_turn.get()
            self.independent_calls = []
            self.independent_effect = lambda: self.independent_calls.append("effect")
            self.independent_delivery = lambda: self.independent_calls.append("delivery")
            self.producer_turn.effect_validators.append(self.independent_effect)
            self.producer_turn.delivery_validators.append(self.independent_delivery)
            self.now += duration
            self.wall += duration
            if mutate is not None:
                await mutate()
            return self.steering.FOR_YOU_INTRO[admission.locale], False

        narration = patch.object(self.steering, "_for_you_intro", intro)
        narration.start()
        self.addCleanup(narration.stop)
        self.response = None
        project = self.service._for_you_offer_projection

        def projection(active, thread, response):
            self.response = deepcopy(response)
            return project(active, thread, response)

        projection_seam = patch.object(self.service, "_for_you_offer_projection", projection)
        projection_seam.start()
        self.addCleanup(projection_seam.stop)

        def current():
            if final is not None:
                final()
            if not self.allowed:
                raise PermissionError("original owner withdrawn")

        await self.steering.prepare_for_you_once(
            self.hass, self.runtime, self.context, self.active, self.for_you_history, current
        )
        return self.project()

    def project(self):
        return self.steering.for_you_projection(
            self.hass, self.runtime, "synthetic-owner", self.active
        )

    def advance(self, seconds):
        self.now += seconds
        self.wall += seconds

    async def test_45_second_preparation_leaves_original_full_visible_choice_period(self):
        initial = await self.prepared()
        self.assertEqual(initial["state"], "available")
        self.assertEqual(initial["expires_in"], 60)
        self.assertTrue(initial["actions_available"])
        for elapsed, delta in ((14, 14), (16, 2), (40, 24), (60, 20)):
            self.advance(delta)
            shown = self.project()
            self.assertEqual(shown["expires_in"], max(0, 60 - elapsed))
            self.assertEqual(shown["actions_available"], elapsed < 60)
            self.assertEqual(shown["offer_id"], initial["offer_id"])
        self.assertEqual(len([r for r in self.reads if r.startswith("/search")]), 3)
        self.assertEqual(self.effects, [])
        self.assertEqual(self.reservations, [])

    async def test_distinct_private_actor_one_seal_and_no_old_dto_or_read_mint(self):
        initial = await self.prepared()
        admission = self.active.broadcast.first_play_offer["_admission"]
        self.assertIs(type(admission), self.steering.FirstPlayAdmission)
        self.assertIs(type(self.preparation), self.steering.FirstPlayPreparationAdmission)
        self.assertIsNot(admission, self.preparation)
        self.assertEqual(self.preparation.deadline, 1060)
        self.assertEqual(admission.deadline, 1105)
        self.assertTrue(self.preparation.withdrawn)
        self.assertTrue(self.preparation.sealed)
        token = self.dialogue.current_turn.set(self.producer_turn)
        try:
            with self.assertRaises(self.dialogue.DialogueError):
                self.preparation.seal()
            self.advance(16)
            # Re-converting an old in-memory DTO is not a second issuer.
            replay = self.service._for_you_offer_projection(
                self.active, initial["conversation_context"]["thread_id"], self.response
            )
            self.assertEqual(replay["_action_monotonic_deadline"], 1105)
            self.assertEqual(replay["_action_wall_deadline"], 2000000105)
            self.assertIs(replay["_admission"], admission)
            for _ in range(5):
                self.project()
            self.assertEqual(admission.deadline, 1105)
        finally:
            self.dialogue.current_turn.reset(token)
        self.assertEqual(len([r for r in self.reads if r.startswith("/search")]), 3)
        self.assertEqual(self.effects, [])

    async def test_preparation_cannot_dispatch_or_seal_after_its_original_60_seconds(self):
        shown = await self.prepared(duration=60)
        self.assertNotEqual(shown["state"], "available")
        self.assertFalse(shown["actions_available"])
        self.assertFalse(self.preparation.sealed)
        with self.assertRaises(self.dialogue.DialogueError):
            self.preparation.before_dispatch("play", (), "")
        self.assertEqual(self.preparation.deadline, 1060)
        self.assertEqual(self.effects, [])

    async def test_original_source_dna_epoch_mood_end_and_frame_changes_during_preparation_deny(
        self,
    ):
        # Each case uses a fresh genuine fixture; do not revive withdrawn authority.
        for name in ("source", "dna", "epoch", "mood", "end", "frame", "owner"):
            with self.subTest(change=name):
                child = VisibleAdmissionTests()
                await child.asyncSetUp()
                try:
                    # Bind the chosen mutation to that fixture's original owner.
                    async def mutation(child=child, name=name):
                        if name == "source":
                            child.manager._history_source_contexts[child.active.session_id] = dict(
                                child.source
                            )
                        elif name == "dna":
                            await child.runtime.memory.async_clear("profile:synthetic-owner")
                        elif name == "epoch":
                            child.grant = "changed-original-grant"
                        elif name == "mood":
                            child.manager._active_by_profile["synthetic-owner"] = replace(
                                child.active,
                                selected_mood="party",
                                mood_revision=child.active.mood_revision + 1,
                            )
                        elif name == "end":
                            await child.manager.async_end(
                                owner_profile_id="synthetic-owner",
                                session_id=child.active.session_id,
                            )
                        elif name == "frame":
                            child.producer_turn.frame.reset("new-generation")
                        else:
                            child.allowed = False

                    shown = await child.prepared(mutate=mutation)
                    self.assertNotEqual(shown["state"], "available")
                    self.assertFalse(child.preparation.sealed)
                    self.assertEqual(child.effects, [])
                finally:
                    await child.asyncTearDown()
                    child.doCleanups()

    async def test_last_real_owner_guard_failure_publishes_no_selection(self):
        def fail_after_preparation():
            if hasattr(self, "preparation"):
                raise PermissionError("last original owner validation denied")

        shown = await self.prepared(final=fail_after_preparation)
        self.assertNotEqual(shown["state"], "available")
        self.assertFalse(self.preparation.sealed)
        self.assertEqual(self.effects, [])

    async def test_explicit_choice_40_seconds_after_publication_dispatches_original_mix(self):
        initial = await self.prepared()
        exact = initial["result_set"]["items"][1]["uris"]
        self.advance(40)
        self.frame = self.for_you_history.dialogue.owners["profile:synthetic-owner"][
            initial["conversation_context"]["thread_id"]
        ]
        self.for_you_history.async_reserve_dialogue_effect = (
            self.history.async_reserve_dialogue_effect
        )
        self.history = self.for_you_history
        result = await self.choose(1, "explicit-after-forty-visible-seconds")
        self.assertTrue(result["action_outcome"]["readback_confirmed"])
        self.assertEqual(self.effects, [("play_uris", exact, True)])
        self.assertEqual(self.turn.first_play_admission.deadline, 1105)

    async def test_explicit_choice_at_exact_60_seconds_denies_without_lookup_or_effect(self):
        initial = await self.prepared()
        self.advance(60)
        self.frame = self.for_you_history.dialogue.owners["profile:synthetic-owner"][
            initial["conversation_context"]["thread_id"]
        ]
        self.for_you_history.async_reserve_dialogue_effect = (
            self.history.async_reserve_dialogue_effect
        )
        self.history = self.for_you_history
        before = list(self.reads)
        with self.assertRaises(self.dialogue.DialogueError):
            await self.choose(1, "expired-after-sixty-visible-seconds")
        self.assertEqual(self.reads, before)
        self.assertEqual(self.effects, [])
        self.assertEqual(self.reservations, [])

    async def test_seal_preserves_independent_validators_and_old_selection_expiry(self):
        await self.prepared()
        turn = self.producer_turn
        self.assertFalse(
            any(v is self.preparation.preparation_effect_guard for v in turn.effect_validators)
        )
        self.assertFalse(
            any(v is self.preparation.preparation_delivery_guard for v in turn.delivery_validators)
        )
        admission = turn.first_play_admission
        self.assertTrue(any(v is self.independent_effect for v in turn.effect_validators))
        self.assertTrue(any(v is self.independent_delivery for v in turn.delivery_validators))
        self.assertIn("effect", self.independent_calls)
        self.assertTrue(
            any(getattr(v, "__self__", None) is admission for v in turn.effect_validators)
        )
        self.advance(60)
        token = self.dialogue.current_turn.set(turn)
        try:
            with self.assertRaises(self.dialogue.DialogueError):
                admission.guard()
        finally:
            self.dialogue.current_turn.reset(token)
        self.assertEqual(admission.deadline, 1105)
        self.assertFalse(self.project()["actions_available"])
