"""Ephemeral public Live presentation; no Profile archive or model invocation."""
from __future__ import annotations

from datetime import UTC, datetime
import secrets
import time

from .display_admission import DisplayAdmissionError

EMOTIONS = {"heart": "❤️", "fire": "🔥", "applause": "👏", "love": "😍", "dance": "💃"}
EMOJI_CODES = {emoji: code for code, emoji in EMOTIONS.items()}


def _label(value):
    return getattr(value, "value", value)


def view(share, active):
    current = active.broadcast.state
    return {"mode": share.view_mode, "revision": share.view_revision, "dynamics": share.dynamics,
            "mood": _label(current.selected_mood), "persona": _label(current.dj_persona)}


def display_status(guests, share_id):
    guests.prune()
    now = guests.display._clock()
    record = guests._policies.get(share_id)
    enabled = bool(record and record.policy.information)
    result = {"live_enabled": enabled,
            "guest_count": sum(g.share_id == share_id and g.kind == "browser" and
                               g.lease_deadline > now for g in guests._guests.values()) if enabled else 0,
            "reactions": [dict(row["event"]) for row in guests._emotion_receipts.values()
                          if enabled and row["share_id"] == share_id and row["deadline"] > now]}
    share = guests.display._shares.get(share_id)
    if enabled and share is not None and share.party_requests:
        result['requested_tracks'] = {
            'expires_at': share.requested_until,
            'items': [{'title': record.title, 'artist': record.artist}
                      for record in guests.requests.pending(share)],
        }
    return result



def react(actor, *, client_message_id, playback_item_id, emotion):
    actor.validate()
    guests = actor.manager._display_admission.participation
    playback = actor.active.broadcast.state.playback
    code = EMOJI_CODES.get(emotion, emotion)
    if (code not in EMOTIONS or playback.state != "playing" or
            not playback_item_id or playback.item_id != playback_item_id):
        raise DisplayAdmissionError("guest_reaction_invalid", 409)
    key = (actor.grant.principal_id, client_message_id)
    prior = guests._emotion_receipts.get(key)
    if prior is not None:
        if prior["event"]["playback_item_id"] != playback_item_id or prior["event"]["emotion"] != code:
            raise DisplayAdmissionError("guest_reaction_changed", 409)
        return {"reaction": dict(prior["event"])}
    own = [row for (guest, _), row in guests._emotion_receipts.items() if guest == actor.grant.principal_id]
    if len(own) >= 128:
        raise DisplayAdmissionError("guest_reaction_capacity", 429)
    now = guests.display._clock()
    if any(row["created"] > now - 1 for row in own):
        raise DisplayAdmissionError("guest_reaction_rate_limited", 429)
    duration = min(5, actor.share.deadline - now, actor.grant.lease_deadline - now)
    event = {"event_id": secrets.token_urlsafe(18), "playback_item_id": playback_item_id,
             "emotion": code, "expires_at": datetime.fromtimestamp(time.time() + duration, UTC).isoformat()}
    guests._emotion_receipts[key] = {"share_id": actor.share.share_id, "created": now,
                                   "deadline": now + duration, "event": event}
    return {"reaction": dict(event)}
