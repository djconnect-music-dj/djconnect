"""Bounded best-effort producer semantics; public/model responses are synthetic."""
from urllib.parse import urlsplit

import json
import unittest
from unittest.mock import patch
from tests import test_requested_moments as fixtures


class MusicOriginResearchTest(unittest.IsolatedAsyncioTestCase):
    setUpClass = fixtures.RequestedMomentsTest.__dict__["setUpClass"]
    tearDownClass = fixtures.RequestedMomentsTest.__dict__["tearDownClass"]

    def test_all_canonical_menu_questions_share_freeform_origin_routing(self):
        from custom_components.djconnect.music_origin import is_origin_question
        from custom_components.djconnect.requested_moment_inventory import FAMILIES
        labels = next(labels for kind, _, labels in FAMILIES if kind == "music_origin")
        self.assertEqual(len(labels), 5)
        for label in labels:
            with self.subTest(label=label):
                self.assertTrue(is_origin_question(label))
                self.assertTrue(is_origin_question(label.casefold().replace("’", "'").strip("¿? ")))
                self.assertFalse(is_origin_question("Speel iets anders en " + label))
                self.assertFalse(is_origin_question("Niet: " + label))

    async def test_websearch_first_page_or_labelled_excerpt_one_model_call(self):
        from custom_components.djconnect.ask_dj import public_research as research
        from custom_components.djconnect import music_origin as origin

        for page_status in (200, 403):
            seen, calls = [], []

            class Fetch:
                maximum_requests = 8
                requests = 0

                def __init__(self, guard):
                    self.guard = guard

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

                async def robots(self, url):
                    await self.guard()
                    return True

                async def request(self, url, **kwargs):
                    await self.guard()
                    self.requests += 1
                    seen.append(url)
                    if urlsplit(url).hostname == "html.duckduckgo.com":
                        return (
                            200,
                            '<a class="result__a" href="https://example.org/interview">Artist interview</a><a class="result__snippet">The song may cover Original Light by Source Artist.</a>',
                            url,
                        )
                    return (
                        page_status,
                        "<html><p>The song may cover Original Light by Source Artist.</p></html>",
                        url,
                    )

            async def ask(prompt):
                calls.append(prompt)
                return json.dumps(
                    {
                        "found": True,
                        "title": "A familiar tune",
                        "summary": "A possible connection.",
                        "text": "You may recognise this melody from Original Light. The interview suggests a connection, but the exact recording is uncertain.",
                        "relation": {
                            "kind": "cover",
                            "direction": "current_to_related",
                            "uncertainty": "possible",
                            "target": {
                                "kind": "recording",
                                "title": "Original Light",
                                "artist": "Source Artist",
                            },
                        },
                        "source_indices": [0],
                    }
                )

            async def guard():
                pass

            with (
                patch.object(research, "PublicFetch", Fetch),
                patch.object(
                    research,
                    "wikipedia",
                    side_effect=AssertionError("Wikipedia is not a prerequisite"),
                ),
            ):
                result = await origin.realize(
                    origin.OriginBrief("Current Light", "Current Artist", "en", "home_dj", "chill"),
                    ask=ask,
                    admission=lambda: None,
                    async_guard=guard,
                )
            self.assertIs(type(result), origin.MusicOriginText)
            self.assertEqual(len(calls), 1)
            self.assertIn("html.duckduckgo.com", seen[0])
            self.assertEqual(len(seen), 2)
            sources = json.loads(result.accepted.sources_json)
            self.assertEqual(
                sources[0]["consultation"], "page_read" if page_status == 200 else "search_excerpt"
            )
            self.assertNotIn("Wikipedia", str(seen))
            self.assertTrue(result.accepted.valid())

    async def test_no_sources_no_model_and_revocation_is_not_a_fallback(self):
        from custom_components.djconnect import music_origin as origin
        from custom_components.djconnect.ask_dj import public_research as research

        async def none(*args):
            return []

        async def never(prompt):
            raise AssertionError("No model without usable sources")

        with patch.object(research, "music_origin_sources", none):
            self.assertIsNone(
                await origin.realize(
                    origin.OriginBrief("Title", "Artist", "nl", "home_dj", "chill"),
                    ask=never,
                    admission=lambda: None,
                )
            )

        async def revoked():
            raise PermissionError("original owner withdrawn")

        with self.assertRaises(PermissionError):
            await research.music_origin_sources("Title", "Artist", "nl", revoked)

    def test_direction_media_and_uncertainty_are_bounded_without_exact_master_ids(self):
        from custom_components.djconnect.music_origin import checked, is_origin_question

        for direction in ["current_to_related", "related_to_current"]:
            value = {
                "schema_version": 1,
                "subject": {"title": "Song", "artist": "Artist"},
                "relation": {
                    "kind": "sample",
                    "direction": direction,
                    "uncertainty": "likely",
                    "target": {"kind": "recording", "title": "Other song", "artist": ""},
                },
            }
            self.assertIs(checked(value), value)
        value["relation"].update(
            kind="media_use",
            direction="current_to_related",
            target={"kind": "media", "title": "Film", "artist": ""},
        )
        self.assertIs(checked(value), value)
        value["relation"]["direction"] = "related_to_current"
        self.assertIsNone(checked(value))
        self.assertTrue(is_origin_question("Waar ken ik dit nummer van?"))
        self.assertTrue(is_origin_question("Where have I heard this song?"))
        self.assertFalse(is_origin_question("Speel iets anders en waar ken ik dit nummer van?"))
        self.assertFalse(is_origin_question("Ik vraag niet waar ken ik dit nummer van"))


class MusicOriginActualHAProofTest(unittest.TestCase):
    def test_actual_origin_and_freeform_receipt_bind_current_source(self):
        from pathlib import Path
        import hashlib

        root = Path(__file__).resolve().parents[1]
        proof = json.loads(
            (
                root / 'examples/client_contracts/music_origin_v1/canvas-confirmed-slot-20261128-15edebf2.json'
            ).read_text()
        )
        self.assertEqual(len(proof["source_pins"]), 361)
        for name, digest in {**proof["source_pins"], **proof["harness_pins"]}.items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), digest, name)
        raw = proof["receipt"]
        self.assertEqual(
            hashlib.sha256(json.dumps(raw, indent=2, ensure_ascii=False).encode()).hexdigest(),
            proof["raw_receipt_sha256"],
        )
        origin = raw["extension"]["music_origin"]
        self.assertTrue(proof["source_before_after_equal"])
        self.assertTrue(origin["direct_sqlite_commit"])
        self.assertTrue(origin["duplicate_did_not_regenerate"])
        self.assertTrue(origin["freeform_same_producer"])
        self.assertEqual(origin["native_type"], "music_origin")
        self.assertEqual(origin["uncertainty"], "possible")
        self.assertEqual(origin["model_fixture_calls"], 6)
        self.assertEqual(origin["canonical_freeform_languages"], ["en", "nl", "de", "fr", "es"])
        self.assertEqual({x["scheme"] for x in origin["requests"]}, {"https"})
        self.assertEqual((origin["real_model_calls"], origin["real_provider_calls"]), (0, 0))
        self.assertEqual(
            (proof["installed"], proof["real_provider"], proof["editorial"]),
            ("NOT_RUN", "NOT_RUN", "OPEN"),
        )
