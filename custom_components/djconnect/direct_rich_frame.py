"""Pure Direct rich projection from one actual, still-current Session attempt.

No producer, provider fetch, registry creation, timestamp renewal or native
clock qualification. Prepared bytes remain owned by the existing image registry.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import math
import time
import zlib

from .direct_rich_wire import canonical, digest, require, safe_integer
from .passive_contribution import contribution, status
from .passive_session import _covers, _music
from .direct_rich_output import valid

_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _date_us(value):
    parsed = datetime.fromisoformat(value)
    require(parsed.tzinfo is not None, "rich_frame_unavailable", 503)
    delta = parsed - _UTC_EPOCH
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def _cap(field, expires_ms):
    field = dict(field)
    if _date_us(field["expires_at"]) > expires_ms * 1000:
        field["expires_at"] = (_UTC_EPOCH + timedelta(milliseconds=expires_ms)).isoformat()
    return field


def utc_ms(seconds, *, upper=False):
    require(type(seconds) in (int, float, Fraction) and math.isfinite(seconds), "rich_unavailable", 503)
    value = Fraction(seconds) * 1000
    result = math.ceil(value) if upper else math.floor(value)
    require(safe_integer(result, 1), "rich_unavailable", 503)
    return result


def _png_chunk(body, offset):
    size = int.from_bytes(body[offset:offset + 4], "big")
    end = offset + 8 + size
    if end + 4 > len(body):
        return None
    kind = body[offset + 4:offset + 8]
    if not all(65 <= c <= 90 or 97 <= c <= 122 for c in kind):
        return None
    if zlib.crc32(body[offset + 4:end]) != int.from_bytes(body[end:end + 4], "big"):
        return None
    return kind, size, end


@dataclass
class _PngContainer:
    header: bool = False
    data: bool = False

    def consume(self, kind, size, end, length):
        if not self.header:
            if kind != b"IHDR" or size != 13:
                return False
            self.header = True
        elif kind == b"IHDR":
            return False
        if kind in {b"acTL", b"fcTL", b"fdAT"}:
            return False
        if kind == b"IDAT":
            self.data = True
        if kind == b"IEND":
            return self.finished(size, end, length)
        return None

    def finished(self, size, end, length):
        return self.data and size == 0 and end + 4 == length


def _complete_png(body):
    if not body.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset, state = 8, _PngContainer()
    while offset <= len(body) - 12:
        chunk = _png_chunk(body, offset)
        if chunk is None:
            return False
        kind, size, end = chunk
        complete = state.consume(kind, size, end, len(body))
        if complete is not None:
            return complete
        offset = end + 4
    return False


def _jpeg_marker(body, offset):
    if body[offset] != 255:
        return None
    while offset < len(body) and body[offset] == 255:
        offset += 1
    if offset >= len(body):
        return None
    return body[offset], offset + 1


def _jpeg_segment(body, offset):
    if offset > len(body) - 2:
        return None
    size = int.from_bytes(body[offset:offset + 2], "big")
    if size < 2 or offset + size > len(body):
        return None
    return size


def _jpeg_scan_end(body, offset):
    while offset < len(body):
        if body[offset] != 255:
            offset += 1
            continue
        start = offset
        parsed = _jpeg_marker(body, offset)
        if parsed is None:
            return None
        marker, following = parsed
        if marker == 0 or 208 <= marker <= 215:
            offset = following
        else:
            return start
    return offset


@dataclass
class _JpegContainer:
    frame: bool = False
    scan: bool = False

    def finished(self, offset, length):
        return self.frame and self.scan and offset == length

    def consume(self, body, marker, offset):
        if marker in {0, 216} or 208 <= marker <= 215:
            return None
        if marker == 1:
            return offset
        size = _jpeg_segment(body, offset)
        if size is None:
            return None
        if marker in {192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207}:
            if self.frame:
                return None
            self.frame = True
        offset += size
        if marker == 218:
            self.scan = True
            return _jpeg_scan_end(body, offset)
        return offset


def _complete_jpeg(body):
    offset, state = 2, _JpegContainer()
    while offset < len(body):
        parsed = _jpeg_marker(body, offset)
        if parsed is None:
            return False
        marker, offset = parsed
        if marker == 217:
            return state.finished(offset, len(body))
        offset = state.consume(body, marker, offset)
        if offset is None:
            return False
    return False


def complete_image(body, mime):
    """Reject trailing/animated/concatenated containers before actual decoding."""
    if mime == "image/png":
        return _complete_png(body)
    if mime != "image/jpeg" or not body.startswith(b"\xff\xd8"):
        return False
    return _complete_jpeg(body)

def _original_bytes(registry, descriptor):
    """Only an existing unique prepared asset, never an image URL lookup."""
    from .session_artwork import _PreparedBytes
    matches = [a for a in registry.assets.values() if a.get("asset_id") == descriptor["asset_id"]]
    require(len(matches) == 1, "rich_asset_unavailable", 404)
    asset = matches[0]
    body, mime = asset["body"], asset["mime"]
    witness = asset.get("_direct_rich_bytes")
    require(type(witness) is _PreparedBytes and witness.body is body
        and witness.mime == mime and type(body) is bytes and 0 < len(body) <= 256000
        and witness.sha256 == hashlib.sha256(body).hexdigest()
        and (witness.width, witness.height) == (descriptor["width"], descriptor["height"]),
        "rich_asset_unavailable", 404)
    return body, mime


def _qualified_rich_fields(broadcast, now, expiry):
    """Bound the original independent text and music projections before art reads."""
    text, text_status = contribution(broadcast, now, projection_version=2)
    music, music_status = _music(broadcast, now)
    if text is not None and len(text["text"].encode("utf-8")) > 2560:
        text, text_status = None, status("copy_too_long")
    if text is not None and not valid("contribution", text):
        text, text_status = None, status("source_not_qualified")
    if music is not None and not valid("now_playing", music):
        music, music_status = None, status("source_not_qualified")
    if text is not None:
        text = _cap(text, expiry)
    if music is not None:
        music = _cap(music, expiry)
    return text, text_status, music, music_status


def _qualified_rich_artwork(context, active, text, music, now, expiry):
    """Reuse only existing original prepared bytes; keep unsupported slots independent."""
    registry = context.pair.domain.get("session_images")
    covers, art_status = _covers(registry, context.owner, active.session_id, text, music, now)
    artwork, assets = [], {}
    for cover in covers:
        try:
            body, mime = _original_bytes(registry, cover)
            descriptor = {k: v for k, v in cover.items() if k != "image_path"}
            descriptor.update(bytes_sha256=hashlib.sha256(body).hexdigest(), byte_length=len(body), mime_type=mime)
            descriptor = _cap(descriptor, expiry)
            require(valid("artwork_item", descriptor), "rich_asset_unavailable", 404)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            # Observe the unsupported slot without hiding independent text or
            # silently swallowing an unrelated implementation/runtime failure.
            art_status = status("asset_not_supported")
        else:
            artwork.append(descriptor)
            assets[cover["asset_id"]] = (body, mime)
    if artwork:
        art_status = status("qualified", "available")
    if covers and not artwork:
        art_status = status("source_not_qualified")
    return artwork, assets, art_status


def project(attempt, *, purpose_id, generation, expires_ms):
    """Fresh fields may change; original purpose and observation never renew."""
    require(attempt.current(), "rich_frame_unavailable", 503)
    context, active = attempt.context, attempt.active
    broadcast = active.broadcast
    now, wall = time.monotonic(), time.time()
    observed_mono, observed_wall = broadcast.passive_state_observed
    observed = utc_ms(observed_wall, upper=True)
    expiry = min(utc_ms(Fraction(observed_wall) + 120), expires_ms)
    require(observed < expiry, "rich_frame_unavailable", 503)
    text, text_status, music, music_status = _qualified_rich_fields(broadcast, now, expiry)
    artwork, assets, art_status = _qualified_rich_artwork(context, active, text, music, now, expiry)
    stale = (not 0 <= now - observed_mono < 120
        or Fraction(wall) >= Fraction(observed_wall) + 120
        or Fraction(wall) * 1000 >= expires_ms)
    if stale:
        text, music, artwork, assets = None, None, [], {}
        text_status = music_status = art_status = status("original_snapshot_expired", "stale")
    frame = {"schema_version": 1, "binding_id": purpose_id, "generation": generation,
        "session_id": active.session_id, "delivery_sequence": broadcast.delivery_sequence,
        "state": "stale" if stale else "active", "observed_at_ms": observed, "expires_at_ms": expiry,
        "playback_state": broadcast.state.playback.state if broadcast.state.playback.state
            in {"playing", "paused", "stopped", "unknown"} else "unknown",
        "mood": {"value": active.selected_mood if active.selected_mood in {"chill", "groove", "energy", "party"}
            else None, "revision": active.mood_revision},
        "presence": active.selected_presence, "persona": active.dj_persona.value,
        "contribution": text, "now_playing": music, "artwork": artwork,
        "contribution_status": text_status, "now_playing_status": music_status, "artwork_status": art_status}
    frame["frame_id"] = digest(frame)
    require(valid("frame", frame) and len(canonical(frame)) <= 15000, "rich_frame_unavailable", 503)
    require(attempt.current(), "rich_frame_unavailable", 503)
    return frame, assets


def _rich_fields_unexpired(attempt, frame, wall, mono):
    """Recheck original snapshot and individual field deadlines without renewal."""
    if frame["state"] == "active":
        observed_mono = attempt.active.broadcast.passive_state_observed[0]
        if not 0 <= mono - observed_mono < 120 or Fraction(wall) * 1000 >= frame["expires_at_ms"]:
            return False
    for field in (frame["contribution"], frame["now_playing"], *frame["artwork"]):
        if field is not None and Fraction(wall) * 1000000 >= _date_us(field["expires_at"]):
            return False
    return True


def _rich_artwork_current(context, frame, mono):
    if frame["artwork"]:
        registry = context.pair.domain.get("session_images")
        covers, _ = _covers(registry, context.owner, context.session_id,
            frame["contribution"], frame["now_playing"], mono)
        if not {a["asset_id"] for a in frame["artwork"]} <= {a["asset_id"] for a in covers}:
            return False
        for descriptor in frame["artwork"]:
            try:
                _original_bytes(registry, descriptor)
            except Exception:
                return False
    return True


def final_current(attempt, frame):
    """Final no-await original-deadline checks, also after serialization work."""
    if not attempt.current():
        return False
    wall, mono = time.time(), time.monotonic()
    if not _rich_fields_unexpired(attempt, frame, wall, mono):
        return False
    context, broadcast = attempt.context, attempt.active.broadcast
    if frame["contribution"] is not None and contribution(broadcast, mono, projection_version=2)[0] is None:
        return False
    if frame["now_playing"] is not None and _music(broadcast, mono)[0] is None:
        return False
    if not _rich_artwork_current(context, frame, mono):
        return False
    return attempt.current()
