"""Shared allowlist qualification over actual unit Runtime/Moment publications."""
from dataclasses import replace
from datetime import datetime, timezone
import importlib
import json
import secrets
import unittest
from unittest.mock import patch

from tests import test_expressive_dj_persona as source_tests


class DisplayProjectionTests(unittest.TestCase):
    setUpClass = source_tests.ExpressiveDJPersonaTest.__dict__["setUpClass"]
    tearDownClass = source_tests.ExpressiveDJPersonaTest.__dict__["tearDownClass"]
    source_pair = source_tests.ExpressiveDJPersonaTest.source_pair
    run_sequence = source_tests.ExpressiveDJPersonaTest.run_sequence

    def prepared(self, *, include_output_status=False):
        self.moments = self.run_sequence(self.runtime.DJPersona.RADIO_DJ, count=1)
        module = importlib.import_module("custom_components.djconnect.display_admission")
        self.projection = importlib.import_module("custom_components.djconnect.display_projection")
        self.state = module.DisplayAdmissionState(lambda: 101)
        self.owner_live = True
        self.owner = module.DisplayOwnerBinding("owner", self.session.session_id, "entry", "stamp", lambda: self.owner_live)
        nonce = secrets.token_urlsafe(32)
        claim = self.state.create_claim(source="unit", browser_nonce=nonce)
        self.state.approve(owner=self.owner, **{key: claim[key] for key in (
            "issuer_epoch", "claim_id", "browser_generation", "code")}, share={"mode": "create", "consent": True, **({"include_output_status": True} if include_output_status else {})})
        collected = self.state.collect(**{key: claim[key] for key in (
            "issuer_epoch", "claim_id", "browser_generation", "claim_secret")}, browser_nonce=nonce)
        self.collected = collected  # Original synthetic grant, retained only by this disposable fixture.
        self.display = self.state._displays[collected["display_id"]]
        return self.moments[0]

    def snapshot(self, now=101):
        return self.projection.shared_snapshot(self.session, self.display, self.state, now=now)

    def test_public_reference_citation_exports_required_attribution_without_corpus_or_owner(self):
        self.prepared()
        base={'provider':'Public web','title':'Artist account','url':'https://artist.example/',
            'language':'en','license':'public_page_short_reference','revision_url':'',
            'usage_basis':'public_page_short_reference','attributed_author':'Nora Vale',
            'author_status':'publication_byline_not_independent_identity',
            'work_reference':{'title':'Paper Lanterns','artist':'Nora Vale',
                'url':'https://musicbrainz.org/release-group/'+'a'*36,'private':'forbidden'},
            'untrusted_excerpt':'never export the source body','owner_id':'private-owner'}
        result=self.projection.public_citation(base)
        self.assertEqual(result['attributed_author'],'Nora Vale')
        self.assertEqual(set(result['work_reference']),{'title','artist','url'})
        self.assertNotIn('untrusted_excerpt',result)
        self.assertNotIn('owner_id',result)

    def test_shared_horizon_uses_current_forecast_text_and_rechecks_expiry(self):
        self.prepared()
        broadcast = self.session.broadcast
        forecast = broadcast.forecast
        forecast.clock = lambda: 101
        forecast.wall_clock = lambda: 1_800_000_000
        forecast.accept_observation()
        playback = broadcast.state.playback
        self.assertTrue(forecast.update({
            "has_current": True, "supported": True, "title": playback.title,
            "artist": playback.artist, "album": playback.album or playback.title,
            "source_url": "https://owner.invalid/private",
            "guidance": "quiet",
        }, locale="nl", persona="radio_dj", current_item_id=playback.item_id,
            imagery=({"url": "https://owner.invalid/image"},)))
        snapshot = self.snapshot()
        card = snapshot["horizon"]
        self.assertEqual(set(card), {"valid_until", "sections"})
        self.assertEqual(card["valid_until"], forecast.value["valid_until"])
        self.assertTrue(all(set(section) == {"title", "text"} for section in card["sections"]))
        # The track already has its own now-playing surface. Horizon is the
        # forward-looking guidance, never another copy of that same track.
        self.assertEqual(len(card["sections"]), 1)
        self.assertNotEqual(card["sections"][0]["text"], forecast.value["sections"][0]["text"])
        self.assertNotIn("owner.invalid", json.dumps(card))
        guard = self.projection.projection_release_guard(self.session, self.display, self.state, snapshot)
        with patch("time.monotonic", return_value=101):
            self.assertTrue(guard())
            broadcast.state = replace(broadcast.state, playback=replace(playback, item_id="next-item"))
            self.assertFalse(guard())
            self.assertNotIn("horizon", self.snapshot())
            broadcast.state = replace(broadcast.state, playback=playback)
            forecast.clock = lambda: forecast.deadline
            self.assertFalse(guard())
        self.assertNotIn("horizon", self.snapshot())

    def test_approved_display_horizon_uses_the_same_authorized_queue_text_as_owner(self):
        self.prepared()
        broadcast = self.session.broadcast
        forecast = broadcast.forecast
        forecast.clock = lambda: 101
        forecast.wall_clock = lambda: 1_800_000_000
        queue_allowed = True
        playback = broadcast.state.playback
        forecast.accept_observation()
        forecast.accept_queue({
            "items": [{"title": "Upcoming recording", "artist": "Upcoming artist", "genres": ["choral"],
                       "private_id": "provider-internal-id"}],
            "deadline": 120, "wall_deadline": 1_800_000_015,
        }, playback.item_id, lambda: queue_allowed)
        forecast.update({
            "has_current": True, "supported": True, "title": playback.title,
            "artist": playback.artist, "album": playback.album or playback.title,
            "source_url": "https://owner.invalid/private", "guidance": "quiet",
            "queue_preview": forecast.queue_context(playback.item_id),
        }, locale="nl", persona="radio_dj", current_item_id=playback.item_id)

        snapshot = self.snapshot()
        card = snapshot["horizon"]
        locale = snapshot["session"]["locale"]
        owner = forecast.as_dict(locale=locale)
        owner_guidance = next(section["text"] for section in owner["sections"] if section["id"] == "guidance")
        self.assertEqual(card["sections"][0]["text"], owner_guidance)
        self.assertIn("Upcoming recording", owner_guidance)
        self.assertIn("Upcoming artist", owner_guidance)
        self.assertEqual(card["valid_until"], owner["valid_until"])
        self.assertNotIn("provider-internal-id", json.dumps(card))
        self.assertNotIn("owner.invalid", json.dumps(card))
        guest = self.projection._shared_horizon(broadcast, locale=locale)
        self.assertNotIn("Upcoming recording", json.dumps(guest))

        guard = self.projection.projection_release_guard(self.session, self.display, self.state, snapshot)
        with patch("time.monotonic", return_value=101):
            self.assertTrue(guard())
            forecast.wall_clock = lambda: 1_800_000_015
            self.assertFalse(guard())
            self.assertNotIn("horizon", self.snapshot())
            forecast.wall_clock = lambda: 1_800_000_000
            queue_allowed = False
            self.assertFalse(guard())
            self.assertNotIn("horizon", self.snapshot())

    def test_pending_content_erasure_withdraws_cached_guard_and_shared_text(self):
        moment = self.prepared()
        snapshot = self.snapshot()
        self.assertTrue(snapshot['dj_moments'])
        guard = self.projection.projection_release_guard(self.session, self.display, self.state, snapshot)
        self.session.broadcast.content_epoch += 1
        self.session.broadcast.content_pending = True
        self.session.broadcast.content_pending_moment_ids.add(moment.moment_id)
        self.assertFalse(guard())
        self.assertEqual(self.snapshot()['dj_moments'], [])

    def test_shared_upcoming_card_follows_queue_deadline_and_current_playback(self):
        self.prepared()
        broadcast = self.session.broadcast
        forecast = broadcast.forecast
        forecast.clock = lambda: 101
        forecast.wall_clock = lambda: 1_800_000_000
        playback = broadcast.state.playback
        next_url = "https://open.spotify.com/track/" + "N" * 22
        upcoming = {"title": "Next recording", "artist": "Next artist", "source_url": next_url,
                    "artwork_url": "/api/djconnect/v1/image_proxy/owner-asset",
                    "current_item_id": playback.item_id, "expires_at": "2027-01-15T08:00:20+00:00"}
        forecast.accept_queue({"items": [{"title": upcoming["title"], "artist": upcoming["artist"],
                                         "genres": []}, {"title": "Another song", "artist": "Private", "genres": []}],
                               "deadline": 120, "wall_deadline": 1_800_000_015}, playback.item_id, lambda: True)
        playing = replace(playback, state="playing", duration_ms=180_000, position_ms=160_000,
                          up_next=tuple(upcoming.items()))
        broadcast.state = replace(broadcast.state, playback=playing)
        snapshot = self.snapshot()
        preview = snapshot["horizon_preview"]
        self.assertEqual(preview["track"]["title"], "Next recording")
        self.assertEqual(preview["track"]["source_url"], next_url)
        self.assertEqual(preview["current_item_id"], playback.item_id)
        self.assertEqual(datetime.fromisoformat(preview["expires_at"]).timestamp(), 1_800_000_015)
        self.assertNotIn("owner-asset", json.dumps(preview))
        self.assertNotIn("Another song", json.dumps(preview))
        guard = self.projection.projection_release_guard(self.session, self.display, self.state, snapshot)
        with patch("time.monotonic", return_value=101):
            self.assertTrue(guard())
            for changed in (replace(playing, state="paused"), replace(playing, position_ms=1),
                            replace(playing, item_id="new-recording")):
                broadcast.state = replace(broadcast.state, playback=changed)
                self.assertNotIn("horizon_preview", self.snapshot())
                self.assertFalse(guard())
            broadcast.state = replace(broadcast.state, playback=playing)
            forecast.wall_clock = lambda: 1_800_000_015
            self.assertFalse(guard())
            self.assertNotIn("horizon_preview", self.snapshot())

    def test_published_shared_fact_text_and_attribution_unchanged_no_private_fields(self):
        moment = self.prepared()
        before = moment.as_dict()
        snapshot = self.snapshot()
        self.assertEqual(len(snapshot["dj_moments"]), 1)
        card = snapshot["dj_moments"][0]
        self.assertEqual(card["content"], moment.content)
        self.assertEqual(card["source_attribution"], dict(moment.source_attribution))
        self.assertEqual(card["presentation_intent"]["dj_persona"], "radio_dj")
        self.assertEqual(before, moment.as_dict())
        wire = json.dumps(snapshot)
        for field in ("planner", "session_flow", "session_direction", "native_delivery", "source_fact",
                      "generation_metadata", "actions", "voice_style", "up_next", "target_name", "artwork_url",
                      "profile_id", "account_id", "device_id", "session_forecast"):
            self.assertNotIn('"' + field + '"', wire)

    def test_output_status_is_optional_and_bound_to_the_approved_display(self):
        for allowed in (False, True):
            with self.subTest(allowed=allowed):
                self.prepared(include_output_status=allowed)
                broadcast = self.session.broadcast
                playback = replace(broadcast.state.playback, target_name="Living room", volume_percent=0)
                broadcast.state = replace(broadcast.state, playback=playback)
                status = self.snapshot()["playback"]
                self.assertEqual(status.get("output_label"), "Living room" if allowed else None)
                self.assertEqual(status.get("volume_percent"), 0 if allowed else None)
                self.assertNotIn("target_name", status)
                self.assertNotIn("target_id", status)
                broadcast.state = replace(broadcast.state, playback=replace(playback, state="idle"))
                self.assertNotIn("volume_percent", self.snapshot()["playback"])

    def test_shared_flow_retains_only_qualified_publication_until_original_expiry(self):
        moment = self.prepared()
        broadcast = self.session.broadcast
        initial = self.snapshot()
        self.assertEqual([row["moment_id"] for row in initial["shared_flow"]], [moment.moment_id])
        broadcast.invalidate_current_delivery()
        broadcast.state = replace(broadcast.state, playback=replace(broadcast.state.playback, item_id="other"))
        updated = self.snapshot()
        self.assertEqual(updated["dj_moments"], [])
        self.assertEqual(updated["shared_flow"], initial["shared_flow"])
        guard = self.projection.projection_release_guard(self.session, self.display, self.state, updated)
        with patch("time.monotonic", return_value=101):
            self.assertTrue(guard())
            broadcast.deleted_moment_ids.add(moment.moment_id)
            self.assertFalse(guard())
        self.assertEqual(self.snapshot()["shared_flow"], [])
        broadcast.deleted_moment_ids.remove(moment.moment_id)
        self.assertEqual(self.snapshot(now=1901)["shared_flow"], [])

    def test_shared_flow_cover_follows_original_track_and_source_authority(self):
        moment = self.prepared()
        delivery = importlib.import_module("custom_components.djconnect.display_delivery")
        broadcast = self.session.broadcast
        item_id = broadcast._moment_delivery_boundaries[moment.moment_id].playback_item_id
        share = self.state._shares[self.display.share_id]
        source_live = True
        asset = delivery.DisplayArtwork(
            "original", item_id, "https://open.spotify.com/track/" + "a" * 22,
            b"original cover", "image/png", 102, datetime.now(timezone.utc).isoformat(),
            400, "2026-11-09T20:00:00+00:00", lambda: source_live,
            frozenset({(share.share_id, share.generation)}), lambda: False)
        broadcast.display_flow_artwork = {item_id: asset}
        broadcast.invalidate_current_delivery()
        broadcast.state = replace(broadcast.state, playback=replace(broadcast.state.playback, item_id="next"))

        snapshot = self.snapshot()
        cover = snapshot["shared_flow"][0]["artwork"]
        self.assertEqual(cover["item_id"], item_id)
        self.assertEqual(cover["source_url"], asset.source_url)
        self.assertNotIn("artwork", snapshot)
        guard = self.projection.projection_release_guard(self.session, self.display, self.state, snapshot)
        with patch("time.monotonic", return_value=101):
            self.assertTrue(guard())
            source_live = False
            self.assertFalse(guard())
        self.assertNotIn("artwork", self.snapshot()["shared_flow"][0])
        source_live = True
        share.generation += 1
        self.assertNotIn("artwork", self.snapshot()["shared_flow"][0])
        share.generation -= 1
        with patch.object(self.state, "_clock", return_value=asset.flow_deadline):
            self.assertIsNone(delivery.qualified_artwork(
                self.session, self.display, self.state, flow_item_id=item_id))

    def test_shared_album_outlives_the_spotlight_but_not_its_original_source(self):
        moment = self.prepared()
        source = replace(moment.source_fact, key="album_release", intent="album_story",
                         provider="Spotify", license="Spotify metadata display",
                         source_url="https://open.spotify.com/album/" + "a" * 22,
                         source_expires_at=400)
        moment = replace(moment, moment_type=self.runtime.DJMomentType.ALBUM, source_fact=source,
                         source_attribution=(("provider", source.provider), ("url", source.source_url),
                                             ("license", source.license)))
        broadcast = self.session.broadcast
        broadcast.state = replace(broadcast.state, dj_moments=(moment,))
        initial = self.snapshot()
        self.assertEqual(initial["dj_moments"][0]["moment_id"], moment.moment_id)
        self.assertNotEqual(initial["shared_flow"][0]["flow_expires_at"],
                            initial["dj_moments"][0]["display_expires_at"])
        broadcast.invalidate_current_delivery()
        broadcast.state = replace(broadcast.state, playback=replace(broadcast.state.playback, item_id="other"))
        retained = self.snapshot(now=191)
        self.assertEqual(retained["dj_moments"], [])
        self.assertEqual(retained["shared_flow"], initial["shared_flow"])
        guard = self.projection.projection_release_guard(self.session, self.display, self.state, retained)
        with patch("time.monotonic", return_value=399):
            self.assertTrue(guard())
        with patch("time.monotonic", return_value=400):
            self.assertFalse(guard())
        self.assertEqual(self.snapshot(now=400)["shared_flow"], [])

    def test_owner_visibility_or_owner_channel_never_becomes_shared_from_valid_source(self):
        moment = self.prepared()
        broadcast = self.session.broadcast
        for presentation in (replace(moment.presentation_intent, visibility=self.runtime.DJMomentVisibility.OWNER_ONLY),
                             replace(moment.presentation_intent, delivery_channels=(self.runtime.DeliveryChannel.OWNER,))):
            broadcast.state = replace(broadcast.state, dj_moments=(replace(moment, presentation_intent=presentation),))
            self.assertEqual(self.snapshot()["dj_moments"], [])
            self.assertEqual(self.snapshot()["shared_flow"], [])

    def test_shared_label_without_field_proof_attribution_or_flow_is_insufficient(self):
        moment = self.prepared()
        broadcast = self.session.broadcast
        for malformed in (replace(moment, source_fact=None), replace(moment, source_attribution=()),
                          replace(moment, source_fact=replace(moment.source_fact, license="unknown"))):
            broadcast.state = replace(broadcast.state, dj_moments=(malformed,))
            self.assertEqual(self.snapshot()["dj_moments"], [])
        broadcast.state = replace(broadcast.state, dj_moments=(moment,),
            session_flow=replace(broadcast.state.session_flow, items=()))
        self.assertEqual(self.snapshot()["dj_moments"], [])

    def test_spotlight_uses_native_selection_and_never_reveals_owner_only_selection(self):
        moment = self.prepared()
        broadcast = self.session.broadcast
        initial = self.snapshot()
        self.assertEqual(initial["current_moment_id"], moment.moment_id)
        with patch("time.monotonic", return_value=101):
            native = broadcast.native_delivery()
        self.assertEqual(initial["current_moment_id"], native["current_moment_id"])
        self.assertEqual(initial["dj_moments"][0]["display_expires_at"], native["admissions"][0]["display_expires_at"])
        self.assertIsNone(self.snapshot(now=191)["current_moment_id"])
        self.assertEqual(self.snapshot(now=191)["shared_flow"][0]["moment_id"], moment.moment_id)
        owner_only = replace(moment, presentation_intent=replace(
            moment.presentation_intent, visibility=self.runtime.DJMomentVisibility.OWNER_ONLY))
        broadcast.state = replace(broadcast.state, dj_moments=(owner_only,))
        with patch("time.monotonic", return_value=101):
            self.assertEqual(broadcast.native_delivery()["current_moment_id"], moment.moment_id)
        self.assertIsNone(self.snapshot()["current_moment_id"])
        silence = replace(moment, moment_id="silence", moment_type=self.runtime.DJMomentType.SILENCE,
                          knowledge_intent=replace(moment.knowledge_intent, intent_type=self.runtime.KnowledgeIntentType.SILENCE),
                          content="", artwork_url=None, actions=(), source_references=(), source_attribution=(), source_fact=None)
        flow = broadcast.state.session_flow
        flow_item = next(item for item in flow.items if item.moment_id == moment.moment_id)
        broadcast.state = replace(broadcast.state, dj_moments=(moment, silence),
                                  session_flow=replace(flow, items=flow.items+(replace(flow_item, moment_id="silence"),)))
        boundary = broadcast._moment_delivery_boundaries[moment.moment_id]
        broadcast._moment_delivery_boundaries["silence"] = boundary
        broadcast._moment_playback_item_ids["silence"] = boundary.playback_item_id
        with patch("time.monotonic", return_value=101):
            self.assertEqual(broadcast.native_delivery()["current_silence_moment_id"], "silence")
        self.assertIsNone(self.snapshot()["current_moment_id"])
        self.assertEqual(self.snapshot()["shared_flow"][0]["moment_id"], moment.moment_id)
        broadcast.state = replace(broadcast.state, dj_moments=(moment,))
        broadcast.invalidate_current_delivery()
        self.assertIsNone(self.snapshot()["current_moment_id"])

    def test_original_deadlines_expiry_pause_invalidation_and_revision(self):
        self.prepared()
        first, repeated = self.snapshot(), self.snapshot(now=102)
        self.assertEqual(first["projection_revision"], repeated["projection_revision"])
        self.assertEqual(first["dj_moments"][0]["display_expires_at"], repeated["dj_moments"][0]["display_expires_at"])
        self.assertEqual(self.snapshot(now=1901)["dj_moments"], [])
        self.session.broadcast.invalidate_current_delivery()
        after = self.snapshot()
        self.assertEqual(after["dj_moments"], [])
        self.assertNotEqual(first["projection_revision"], after["projection_revision"])

    def test_withdrawal_and_oversized_full_fact_fail_closed_without_truncation(self):
        moment = self.prepared()
        self.session.broadcast.state = replace(self.session.broadcast.state,
            dj_moments=(replace(moment, content="x" * (129 * 1024)),))
        with self.assertRaises(self.projection.DisplayAdmissionError) as failure:
            self.snapshot()
        self.assertEqual(failure.exception.code, "display_capacity")
        self.owner_live = False
        with self.assertRaises(self.projection.DisplayAdmissionError):
            self.snapshot()

    def test_final_content_release_uses_original_source_clock_after_serialization(self):
        moment = self.prepared()
        moment = replace(moment, source_fact=replace(moment.source_fact, source_expires_at=101.5))
        self.session.broadcast.state = replace(self.session.broadcast.state, dj_moments=(moment,))
        snapshot = self.snapshot(now=101)
        self.assertEqual(len(snapshot["dj_moments"]), 1)
        guard = self.projection.projection_release_guard(self.session, self.display, self.state, snapshot)
        with patch("time.monotonic", return_value=101):
            self.assertTrue(guard())
        # Causal gap: same serialized frame, unchanged owner/share/lease and
        # generation; ONLY the original source clock reaches equality.
        with patch("time.monotonic", return_value=101.5):
            self.assertFalse(guard())
