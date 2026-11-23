"""Original event pixels for an independent, genuinely admitted shared display.

No personal image registry/grant, owner credential, historical read or new photo
selection. Four bounded transient reads; all bytes keep the original live fence.
"""
from __future__ import annotations

import asyncio
import hashlib
import json

from .display_admission import DisplayAdmissionError
from .display_service import DisplayResult
from .guest_presentation import shared_items
from .live_impression import admitted, MAX_IMAGE_BYTES


class SharedFocusMediaResult(DisplayResult):
    """In-process purpose marker; never caller-selected response limits."""


def original_photo(manager, display, revision):
    state = manager._display_admission
    guests = state.participation
    row = guests._focus.get(display.share_id)
    active = manager.current_active(display.owner.profile_id)
    if (row is None or row[3] != revision or active is None
            or active.session_id != display.owner.session_id or row[1] <= state._clock()
            or state._displays.get(display.display_id) is not display
            or not display.owner.valid() or display.lease_deadline <= state._clock()):
        raise DisplayAdmissionError('guest_shared_photo_unavailable', 404)
    guests.validate(row[2])
    if row[0] not in shared_items(active, now=state._clock()):
        raise DisplayAdmissionError('guest_shared_photo_unavailable', 404)
    moment = next((m for m in active.broadcast.state.dj_moments if m.moment_id == row[0]), None)
    if not admitted(moment):
        raise DisplayAdmissionError('guest_shared_photo_unavailable', 404)
    reference = json.loads(moment.live_impression.reference_json)
    payload = json.loads(moment.live_impression.payload_json)
    photo = next((p for p in payload['photos'] if p['photo_id'] == reference.get('photo_id')), None)
    if (photo is None or any(reference.get(key) != photo.get(key) for key in (
            'photo_id','revision','source_url','license','license_url'))):
        raise DisplayAdmissionError('guest_shared_photo_unavailable', 404)
    return row, active, moment, reference, photo


def public_photo(manager, display, revision):
    try:
        photo = original_photo(manager, display, revision)[4]
    except DisplayAdmissionError:
        return None
    return {key:photo[key] for key in ('photo_id','revision','caption','alt_text','author',
                                      'credit','source_url','license','license_url')}


async def prepare(service, payload, headers, selected):
    manager = service.manager
    token = headers.get('Authorization', '')
    if not isinstance(token, str) or not token.startswith('Bearer djcd_') or len(token) > 256:
        raise DisplayAdmissionError('display_grant_invalid', 401)
    async with manager._lock:
        service.display._sync_origin(service.display._origin(selected))
        state = manager._display_admission
        display = state.authorize(token=token.removeprefix('Bearer '), display_id=payload['display_id'],
                                  issuer_epoch=payload['issuer_epoch'])
        original = original_photo(manager, display, payload['focus_revision'])
        guests = state.participation
        reads = guests._focus_media_reads
        guests.prune()
        attempt = (display.display_id, payload['focus_revision'])
        if (display.display_id in reads or len(reads) >= 4
                or attempt in guests._focus_media_attempts or len(guests._focus_media_attempts) >= 64):
            raise DisplayAdmissionError('guest_shared_photo_capacity', 429)
        marker = object()
        reads[display.display_id] = marker
        guests._focus_media_attempts.add(attempt)

    def complete():
        if reads.get(display.display_id) is marker:
            del reads[display.display_id]

    def current():
        try:
            service.display._origin(selected)
            actual = state.authorize(token=token.removeprefix('Bearer '), display_id=payload['display_id'],
                                     issuer_epoch=payload['issuer_epoch'])
            found = original_photo(manager, display, payload['focus_revision'])
            return (actual is display and reads.get(display.display_id) is marker
                    and all(found[i] is original[i] for i in (0,1,2)) and found[3:] == original[3:])
        except DisplayAdmissionError:
            return False

    async def guard():
        if not current():
            raise PermissionError('shared_photo_withdrawn')

    try:
        from .live_impression_media import refetch
        async with asyncio.timeout(20):
            body, mime = await refetch(original[3], guard)
        await guard()
        if (not isinstance(body, bytes) or len(body) > MAX_IMAGE_BYTES or mime not in {'image/jpeg','image/png'}
                or hashlib.sha256(body).hexdigest() != original[4]['revision']):
            raise DisplayAdmissionError('guest_shared_photo_unavailable', 404)
        result = service.display._release_result({}, current, complete, (body,mime), state, selected)
        return SharedFocusMediaResult(result.payload, result.release, result.complete, result.media)
    except asyncio.CancelledError:
        complete()
        raise
    except Exception as exc:
        complete()
        if isinstance(exc, DisplayAdmissionError):
            raise
        raise DisplayAdmissionError('guest_shared_photo_unavailable', 404) from None
