"""Real request/dialogue boundaries with declared synthetic evidence and planner.

These regressions qualify clarification routing, not biographies/model quality.
"""

import json
import asyncio
import unittest
from copy import deepcopy
from datetime import date
from unittest.mock import patch
from tests import test_ask_dj_contextual_dialogue as shared

GOLDEN = (
    (
        "nl",
        "Hoe oud is Example Band?",
        ("Band Example Band", "Ik bedoel de band zelf", "Hoe lang bestaat die band?"),
        ("Leeftijd", "De leeftijd van de muzikant"),
        "Welke muzikant bedoel je?",
    ),
    (
        "en",
        "How old is Example Band?",
        ("the band itself", "I mean the band Example Band", "How long has the band existed?"),
        ("age", "the musician’s age"),
        "Which musician do you mean?",
    ),
    (
        "de",
        "Wie alt ist Example Band?",
        ("die Band selbst", "Ich meine die Band Example Band", "Wie lange gibt es die Band?"),
        ("das Alter", "das Alter des Musikers"),
        "Welchen Musiker meinst du?",
    ),
    (
        "fr",
        "Quel âge a Example Band ?",
        (
            "le groupe lui-même",
            "Je parle du groupe Example Band",
            "Depuis quand ce groupe existe-t-il ?",
        ),
        ("l’âge", "l’âge du musicien"),
        "De quel musicien parles-tu ?",
    ),
    (
        "es",
        "¿Qué edad tiene Example Band?",
        ("la banda en sí", "Me refiero a la banda Example Band", "¿Desde cuándo existe la banda?"),
        ("la edad", "la edad del músico"),
        "¿A qué músico te refieres?",
    ),
)


class AgeClarificationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        shared.SharedDialogueTest.setUpClass()

    @classmethod
    def tearDownClass(cls):
        shared.SharedDialogueTest.tearDownClass()

    @staticmethod
    def sources(person=False):
        from custom_components.djconnect.ask_dj import public_research as r
        from custom_components.djconnect.ask_dj.person_age import entity_url

        name, qid, kind = ("Ada Reed", "Q123", 5) if person else ("Example Band", "Q1", 215380)

        def statement(prop, value, typed="time"):
            return {
                "rank": "normal",
                "mainsnak": {
                    "property": prop,
                    "snaktype": "value",
                    "datatype": "time" if typed == "time" else "wikibase-item",
                    "datavalue": {"type": typed, "value": value},
                },
            }

        birthday = {
            "time": "+1980-11-24T00:00:00Z" if person else "+1996-00-00T00:00:00Z",
            "precision": 11 if person else 9,
            "before": 0,
            "after": 0,
            "timezone": 0,
            "calendarmodel": "http://www.wikidata.org/entity/Q1985727",
        }
        document = {
            "entities": {
                qid: {
                    "id": qid,
                    "type": "item",
                    "sitelinks": {"enwiki": {"title": name}},
                    "claims": {
                        "P31": [
                            statement(
                                "P31",
                                {"entity-type": "item", "numeric-id": kind, "id": "Q" + str(kind)},
                                "wikibase-entityid",
                            )
                        ],
                        "P569" if person else "P571": [
                            statement("P569" if person else "P571", birthday)
                        ],
                    },
                }
            }
        }
        wiki = r._source(
            "Wikipedia",
            name,
            "https://en.wikipedia.org/wiki/" + name.replace(" ", "_"),
            name + " is a singer."
            if person
            else "Example Band is a rock band. Example Band was formed in 1996.",
            "en",
            entity_id=qid,
        )
        data = r._source(
            "Wikidata",
            name,
            entity_url(qid, "en"),
            json.dumps(document),
            "en",
            entity_id=qid,
            current=True,
        )
        return [wiki, data]

    async def test_five_language_natural_choices_progress_without_new_facts_or_effects(self):
        from custom_components.djconnect.ask_dj import public_research as r, person_age

        original_age = person_age.age_answer
        for language, initial, bands, people, directed in GOLDEN:
            for branch, replies in [("band_duration", bands), ("person_age", people)]:
                for reply in replies:
                    with self.subTest(language=language, branch=branch, reply=reply):
                        f = shared.SharedDialogueTest()
                        await f.asyncSetUp()
                        calls = []
                        lookups = []

                        async def research(subject, question, locale, guard, **kwargs):
                            await guard()
                            lookups.append((subject, question, kwargs.get("research_angle")))
                            self.assertIn(subject, {"Example Band", "Ada Reed"})
                            return self.sources(subject == "Ada Reed"), {
                                "state": "available",
                                "synthetic_source": True,
                            }

                        async def agent(hass, data, **kwargs):
                            p = json.loads(data["text"].split("\nData:\n", 1)[1])
                            calls.append(p)
                            self.assertIn(
                                "available",
                                p,
                                "No factual generation/review call is needed for these exact date receipts",
                            )
                            self.assertEqual(p["pending_age"]["subject"], "Example Band")
                            self.assertIn(
                                p["question"],
                                {reply, "Ada Reed"},
                                "Do not synthesize a corrected question",
                            )
                            if p["question"] == "Ada Reed":
                                self.assertEqual(p["pending_age"]["stage"], "choose_person")
                                proposal = {
                                    "read": "research",
                                    "reference": "named",
                                    "exclude_current": False,
                                    "subject": "Ada Reed",
                                    "angle": "age",
                                }
                            else:
                                self.assertEqual(p["pending_age"]["stage"], "choose_scope")
                                proposal = {
                                    "read": "research",
                                    "reference": "recent",
                                    "exclude_current": False,
                                    "angle": "age",
                                    "age_target": branch,
                                }
                            return {
                                "response": {"speech": {"plain": {"speech": json.dumps(proposal)}}}
                            }

                        try:
                            with (
                                patch.object(r, "research", research),
                                patch.object(
                                    f.pipeline, "_call_conversation_process_transport", agent
                                ),
                                patch.object(
                                    person_age,
                                    "age_answer",
                                    lambda sources, subject, locale: original_age(
                                        sources, subject, locale, today=date(2026, 11, 23)
                                    ),
                                ),
                            ):
                                first, status = await f.request(
                                    initial, identifier="age-first", language=language
                                )
                                self.assertEqual(status, 200, first)
                                self.assertTrue(first.get("clarification_required"), first)
                                self.assertEqual(calls, [])
                                frame = next(
                                    iter(f.history.dialogue.owners["profile:profile-a"].values())
                                )
                                original_deadline = frame.pending["deadline"]
                                second, status = await f.request(
                                    reply, identifier="age-choice", language=language
                                )
                                self.assertEqual(status, 200, second)
                                self.assertFalse(second.get("playback_actions"))
                                self.assertEqual(f.effects, [])
                                if branch == "band_duration":
                                    self.assertIn(
                                        "1996",
                                        second["text"],
                                        {
                                            "reply": second,
                                            "planner_calls": calls,
                                            "lookups": lookups,
                                        },
                                    )
                                    self.assertFalse(second.get("clarification_required"))
                                    self.assertIsNone(frame.pending)
                                else:
                                    self.assertEqual(second["text"], directed)
                                    self.assertTrue(second.get("clarification_required"))
                                    self.assertEqual(frame.pending["stage"], "choose_person")
                                    self.assertEqual(
                                        frame.pending["deadline"],
                                        original_deadline,
                                        "No renewed purpose lease",
                                    )
                                    self.assertEqual(len(calls), 1)
                                    third, status = await f.request(
                                        "Ada Reed", identifier="age-person", language=language
                                    )
                                    self.assertEqual(status, 200, third)
                                    self.assertIn("45", third["text"])
                                    self.assertEqual(
                                        third.get("knowledge_basis"), "public_person_age_v1"
                                    )
                                    self.assertIsNone(frame.pending)
                                    self.assertEqual(lookups[-1], ("Ada Reed", "Ada Reed", "age"))
                                    self.assertEqual(len(calls), 2)
                                self.assertEqual(f.effects, [])
                        finally:
                            await f.asyncTearDown()

    def test_age_plan_is_closed_and_old_plans_remain_valid(self):
        from custom_components.djconnect.ask_dj.semantic_reads import parse_plan

        old = {"read": "research", "reference": "recent", "exclude_current": False, "angle": "age"}
        self.assertEqual(parse_plan(json.dumps(old)).age_target, "")
        for target in ("band_duration", "person_age"):
            self.assertEqual(
                parse_plan(json.dumps({**old, "age_target": target})).age_target, target
            )
        for extra in (
            {"age_target": ""},
            {"age_target": True},
            {"age_target": None},
            {"age_target": "oldest_member"},
            {"age_target": "person_age", "angle": "biography"},
            {"age_target": "person_age", "read": "artist"},
            {"age_target": "person_age", "reference": "named", "subject": "Ada Reed"},
            {"age_target": "person_age", "exclude_current": True},
            {"age_target": "person_age", "command": "play"},
        ):
            self.assertIsNone(parse_plan(json.dumps({**old, **extra})), extra)
        self.assertIsNone(
            parse_plan(
                json.dumps(old)[:-1] + ',"age_target":"person_age","age_target":"band_duration"}'
            )
        )

    async def test_scope_revision_aba_and_withdrawal_fence_each_owner_await(self):
        from custom_components.djconnect.ask_dj import public_research as r
        from custom_components.djconnect.ask_dj.dialogue import current_turn

        for boundary in ("planner", "research"):
            for mutation in (
                "pending_aba",
                "thread",
                "scope",
                "generation",
                "read_revision",
                "reference_aba",
                "withdraw",
            ):
                with self.subTest(boundary=boundary, mutation=mutation):
                    f = shared.SharedDialogueTest()
                    await f.asyncSetUp()
                    choice = [False]
                    lookups = []

                    def invalidate():
                        turn = current_turn.get()
                        frame = turn.frame
                        if mutation == "pending_aba":
                            frame.set_pending(deepcopy(frame.pending))
                        elif mutation == "thread":
                            frame.pending["thread_id"] = "other"
                        elif mutation == "scope":
                            frame.pending["scope"] = "profile:other"
                        elif mutation == "generation":
                            frame.generation += "-changed"
                        elif mutation == "read_revision":
                            frame.read_context_revision += 1
                        elif mutation == "reference_aba":
                            frame.public_query_revision += 1
                        else:
                            f.history.dialogue.withdraw_content(
                                turn.scope,
                                request_hashes={frame.pending["public_request_hash"]},
                                turn_ids=set(),
                            )

                    async def research(subject, question, language, guard, **kwargs):
                        await guard()
                        lookups.append(subject)
                        if choice[0] and boundary == "research":
                            await asyncio.sleep(0)
                            invalidate()
                            await guard()
                        return self.sources(), {"state": "available", "synthetic_source": True}

                    async def agent(hass, data, **kwargs):
                        p = json.loads(data["text"].split("\nData:\n", 1)[1])
                        self.assertIn("pending_age", p)
                        await asyncio.sleep(0)
                        if boundary == "planner":
                            invalidate()
                        return {
                            "response": {
                                "speech": {
                                    "plain": {
                                        "speech": json.dumps(
                                            {
                                                "read": "research",
                                                "reference": "recent",
                                                "exclude_current": False,
                                                "angle": "age",
                                                "age_target": "person_age",
                                            }
                                        )
                                    }
                                }
                            }
                        }

                    try:
                        with (
                            patch.object(r, "research", research),
                            patch.object(f.pipeline, "_call_conversation_process_transport", agent),
                        ):
                            first, status = await f.request(
                                "Hoe oud is Example Band?", identifier="race-first", language="nl"
                            )
                            self.assertEqual(status, 200, first)
                            self.assertTrue(first.get("clarification_required"))
                            choice[0] = True
                            second, status = await f.request(
                                "Leeftijd", identifier="race-choice", language="nl"
                            )
                            self.assertIn(status, {403, 409}, second)
                            self.assertFalse(second.get("success"))
                            self.assertEqual(f.effects, [])
                            self.assertEqual(
                                lookups,
                                ["Example Band"]
                                if boundary == "planner"
                                else ["Example Band", "Example Band"],
                            )
                    finally:
                        await f.asyncTearDown()

    async def test_same_message_replay_preserves_progress_without_another_lookup(self):
        from custom_components.djconnect.ask_dj import public_research as r

        f = shared.SharedDialogueTest()
        await f.asyncSetUp()
        calls = []
        lookups = []

        async def research(subject, question, language, guard, **kwargs):
            await guard()
            lookups.append(subject)
            return self.sources(), {"state": "available", "synthetic_source": True}

        async def agent(hass, data, **kwargs):
            calls.append(data)
            return {
                "response": {
                    "speech": {
                        "plain": {
                            "speech": json.dumps(
                                {
                                    "read": "research",
                                    "reference": "recent",
                                    "exclude_current": False,
                                    "angle": "age",
                                    "age_target": "person_age",
                                }
                            )
                        }
                    }
                }
            }

        try:
            with (
                patch.object(r, "research", research),
                patch.object(f.pipeline, "_call_conversation_process_transport", agent),
            ):
                first, status = await f.request(
                    "Hoe oud is Example Band?", identifier="replay-first", language="nl"
                )
                self.assertEqual(status, 200, first)
                chosen, status = await f.request(
                    "Leeftijd", identifier="replay-choice", language="nl"
                )
                self.assertEqual(status, 200, chosen)
                frame = next(iter(f.history.dialogue.owners["profile:profile-a"].values()))
                pending, revision = frame.pending, frame.pending_revision
                replay, status = await f.request(
                    "Leeftijd", identifier="replay-choice", language="nl"
                )
                self.assertEqual(status, 200, replay)
                self.assertEqual(replay["text"], chosen["text"])
                self.assertIs(frame.pending, pending)
                self.assertEqual(frame.pending_revision, revision)
                self.assertEqual(len(calls), 1)
                self.assertEqual(lookups, ["Example Band", "Example Band"])
                self.assertEqual(f.effects, [])
        finally:
            await f.asyncTearDown()

    async def test_completion_guards_reject_later_replacement_expiry_and_source_withdrawal(self):
        from types import SimpleNamespace
        from custom_components.djconnect.ask_dj import public_research as r
        from custom_components.djconnect.ask_dj.dialogue import DialogueTurn, DialogueError
        from custom_components.djconnect.ask_dj.exploration import bind_age_pending

        for change in ("replacement", "expiry", "withdraw"):
            with self.subTest(change=change):
                f = shared.SharedDialogueTest()
                await f.asyncSetUp()

                async def research(subject, question, language, guard, **kwargs):
                    await guard()
                    return self.sources(), {"state": "available", "synthetic_source": True}

                async def valid():
                    pass

                try:
                    with patch.object(r, "research", research):
                        first, status = await f.request(
                            "Hoe oud is Example Band?", identifier="complete-first", language="nl"
                        )
                        self.assertEqual(status, 200, first)
                    state = f.history.dialogue
                    frame = next(iter(state.owners["profile:profile-a"].values()))
                    original = deepcopy(frame.pending)
                    turn = DialogueTurn(
                        frame,
                        "profile:profile-a",
                        "default",
                        "manual-choice",
                        "digest",
                        frame.generation,
                        valid,
                        SimpleNamespace(dialogue=state),
                        style={"language": "nl"},
                    )
                    turn.source_request_hashes = set()
                    bind_age_pending(turn)
                    state.complete(
                        turn,
                        {
                            "success": True,
                            "text": "A qualified local reply",
                            "_dialogue_question": "Leeftijd",
                        },
                    )
                    self.assertIsNone(frame.pending)
                    for check in turn.delivery_validators:
                        check()
                    if change == "replacement":
                        frame.set_pending(None)
                    elif change == "expiry":
                        state.clock = lambda: original["deadline"] + 1
                    else:
                        state.withdraw_content(
                            turn.scope,
                            request_hashes={original["public_request_hash"]},
                            turn_ids=set(),
                        )
                    with self.assertRaises(DialogueError):
                        for check in turn.delivery_validators:
                            check()
                finally:
                    await f.asyncTearDown()

    async def test_current_recording_and_new_named_topic_do_not_borrow_age_scope(self):
        from custom_components.djconnect.ask_dj import public_research as r

        for topic in ("current", "new_named"):
            with self.subTest(topic=topic):
                f = shared.SharedDialogueTest()
                await f.asyncSetUp()
                lookups = []

                async def research(subject, question, language, guard, **kwargs):
                    await guard()
                    lookups.append(subject)
                    return self.sources(subject == "Ada Reed"), {
                        "state": "available",
                        "synthetic_source": True,
                    }

                async def agent(hass, data, **kwargs):
                    p = json.loads(data["text"].split("\nData:\n", 1)[1])
                    self.assertIn("pending_age", p)
                    self.assertEqual(
                        topic, "current", "New explicit public age question needs no model route"
                    )
                    return {
                        "response": {
                            "speech": {
                                "plain": {
                                    "speech": json.dumps(
                                        {
                                            "read": "recording",
                                            "reference": "current",
                                            "exclude_current": False,
                                        }
                                    )
                                }
                            }
                        }
                    }

                async def status(hass, runtime, command, *args, **kwargs):
                    self.assertEqual(command, "status")
                    return {
                        "success": True,
                        "playback": {
                            "uri": "spotify:track:0123456789abcdefghijkL",
                            "artist": "Actual current performer",
                            "title": "Actual current recording",
                        },
                    }

                try:
                    with (
                        patch.object(r, "research", research),
                        patch.object(f.pipeline, "_call_conversation_process_transport", agent),
                        patch.object(f.core, "run_music_command", status),
                    ):
                        first, code = await f.request(
                            "Hoe oud is Example Band?", identifier="topic-first", language="nl"
                        )
                        self.assertEqual(code, 200, first)
                        frame = next(iter(f.history.dialogue.owners["profile:profile-a"].values()))
                        if topic == "current":
                            result, code = await f.request(
                                "welk nummer hoor ik nu eigenlijk?",
                                identifier="topic-current",
                                language="nl",
                            )
                            self.assertEqual(code, 200, result)
                            self.assertIn("Actual current recording", result["text"])
                            self.assertNotIn("Example Band", result["text"])
                            self.assertEqual(lookups, ["Example Band"])
                            self.assertIsNone(
                                frame.pending
                            )  # Existing current-context reset discards the old purpose.
                        else:
                            result, code = await f.request(
                                "Hoe oud is Ada Reed?", identifier="topic-new", language="nl"
                            )
                            self.assertEqual(code, 200, result)
                            self.assertEqual(result.get("knowledge_basis"), "public_person_age_v1")
                            self.assertEqual(lookups, ["Example Band", "Ada Reed"])
                            self.assertIsNone(frame.pending)
                            self.assertEqual(frame.public_query_reference.subject, "Ada Reed")
                        self.assertEqual(f.effects, [])
                finally:
                    await f.asyncTearDown()

    async def test_interpreter_cannot_substitute_an_unnamed_band_member(self):
        from custom_components.djconnect.ask_dj import public_research as r

        f = shared.SharedDialogueTest()
        await f.asyncSetUp()
        lookups = []
        phase = ["choose"]

        async def research(subject, question, language, guard, **kwargs):
            await guard()
            lookups.append(subject)
            self.assertEqual(subject, "Example Band")
            return self.sources(), {"state": "available", "synthetic_source": True}

        async def agent(hass, data, **kwargs):
            p = json.loads(data["text"].split("\nData:\n", 1)[1])
            self.assertIn("available", p)
            proposal = (
                {
                    "read": "research",
                    "reference": "recent",
                    "exclude_current": False,
                    "angle": "age",
                    "age_target": "person_age",
                }
                if phase[0] == "choose"
                else {
                    "read": "research",
                    "reference": "named",
                    "exclude_current": False,
                    "angle": "age",
                    "subject": "Ada Reed",
                }
            )
            return {"response": {"speech": {"plain": {"speech": json.dumps(proposal)}}}}

        try:
            with (
                patch.object(r, "research", research),
                patch.object(f.pipeline, "_call_conversation_process_transport", agent),
            ):
                first, code = await f.request(
                    "Hoe oud is Example Band?", identifier="unnamed-first", language="nl"
                )
                self.assertEqual(code, 200, first)
                chosen, code = await f.request(
                    "Leeftijd", identifier="unnamed-choice", language="nl"
                )
                self.assertEqual(code, 200, chosen)
                phase[0] = "invent"
                result, code = await f.request(
                    "Leeftijd", identifier="unnamed-member", language="nl"
                )
                self.assertEqual(code, 200, result)
                self.assertNotIn("Ada Reed", result["text"])
                self.assertEqual(lookups, ["Example Band", "Example Band"])
                self.assertEqual(f.effects, [])
        finally:
            await f.asyncTearDown()

    def test_directed_choice_still_requires_current_positive_group_source(self):
        from dataclasses import replace
        from datetime import UTC, datetime, timedelta
        from custom_components.djconnect.ask_dj import public_research as r
        from custom_components.djconnect.ask_dj.exploration import band_age_question

        valid = self.sources()[0]
        projection = r.research_projection("Example Band", [valid], {"state": "available"})
        self.assertEqual(
            band_age_question(projection, "nl", age_target="person_age"),
            "Welke muzikant bedoel je?",
        )
        for source in (
            replace(valid, expires_at=(datetime.now(UTC) - timedelta(seconds=1)).isoformat()),
            replace(valid, text="Example Band is a film about a rock band."),
            self.sources(True)[0],
        ):
            p = r.research_projection("Example Band", [source], {"state": "available"})
            self.assertIsNone(band_age_question(p, "nl", age_target="person_age"))
        self.assertNotEqual(
            band_age_question(projection, "nl", age_target="invented"), "Welke muzikant bedoel je?"
        )

    async def test_legacy_plan_cannot_undo_person_choice_but_explicit_band_choice_can(self):
        from custom_components.djconnect.ask_dj import public_research as r

        f = shared.SharedDialogueTest()
        await f.asyncSetUp()
        target = ["person_age"]
        calls = []

        async def research(subject, question, language, guard, **kwargs):
            await guard()
            self.assertEqual(subject, "Example Band")
            return self.sources(), {"state": "available", "synthetic_source": True}

        async def agent(hass, data, **kwargs):
            p = json.loads(data["text"].split("\nData:\n", 1)[1])
            calls.append(p)
            proposal = {
                "read": "research",
                "reference": "recent",
                "exclude_current": False,
                "angle": "age",
            }
            if target[0]:
                proposal["age_target"] = target[0]
            return {"response": {"speech": {"plain": {"speech": json.dumps(proposal)}}}}

        try:
            with (
                patch.object(r, "research", research),
                patch.object(f.pipeline, "_call_conversation_process_transport", agent),
            ):
                first, code = await f.request(
                    "Hoe oud is Example Band?", identifier="stage-first", language="nl"
                )
                self.assertEqual(code, 200, first)
                chosen, code = await f.request("Leeftijd", identifier="stage-person", language="nl")
                self.assertEqual(code, 200, chosen)
                self.assertEqual(chosen["text"], "Welke muzikant bedoel je?")
                frame = next(iter(f.history.dialogue.owners["profile:profile-a"].values()))
                deadline = frame.pending["deadline"]
                target[0] = ""
                again, code = await f.request(
                    "De muzikant", identifier="stage-name-unspecified", language="nl"
                )
                self.assertEqual(code, 200, again)
                self.assertEqual(again["text"], chosen["text"])
                self.assertEqual(frame.pending["stage"], "choose_person")
                self.assertEqual(frame.pending["deadline"], deadline)
                target[0] = "band_duration"
                band, code = await f.request(
                    "Ik bedoel de band zelf", identifier="stage-explicit-switch", language="nl"
                )
                self.assertEqual(code, 200, band)
                self.assertIn("1996", band["text"])
                self.assertIsNone(frame.pending)
                self.assertEqual(len(calls), 3)
                self.assertEqual(f.effects, [])
        finally:
            await f.asyncTearDown()
