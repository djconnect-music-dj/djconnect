"""Prepared public track art under an original guest, never display authority."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
import re

from .display_admission import DisplayAdmissionError
from .session_conversation import SessionConversationError



@dataclass(frozen=True, slots=True)
class RequestArtwork:
    nonce: str
    item_id: str
    body: bytes
    mime: str
    expires_at: str


def prepare_request(state, record, url):
    from .display_delivery import fetch_display_artwork, safe_cdn_url
    if not isinstance(url, str) or not safe_cdn_url(url):
        return

    def current():
        return (record.actor.share.owner.valid() and
                state.admission.display._shares.get(record.actor.share.share_id) is record.actor.share
                and any(candidate is record for candidate in state.pending(record.actor.share)))

    async def prepare():
        from aiohttp import ClientError
        try:
            if not current():
                return
            witness = await fetch_display_artwork(record.actor.hass, url, current)
            remaining = record.deadline - state.admission.display._clock()
            if witness is not None and current() and remaining > 0:
                record.artwork = RequestArtwork(secrets.token_hex(16), record.request_id, witness.body,
                    witness.mime, (datetime.now(UTC) + timedelta(seconds=remaining)).isoformat())
        except (ClientError, OSError, ValueError, TimeoutError):
            return

    record.actor.hass.async_create_task(prepare())


def _request_reference(actor, asset):
    state = actor.manager._display_admission
    binding = (state.issuer_epoch, 'guest-request', actor.grant.principal_id, actor.grant.generation,
               actor.share.share_id, str(actor.share.generation), asset.item_id, asset.nonce, asset.expires_at)
    return hashlib.sha256(':'.join(binding).encode()).hexdigest()


def request_queue(actor):
    actor.validate()
    rows = []
    for record in actor.manager._display_admission.participation.requests.pending(actor.share):
        row = {'request_id': record.request_id, 'title': record.title, 'artist': record.artist}
        if (asset := record.artwork) is not None:
            row['artwork'] = {'reference': _request_reference(actor, asset),
                              'item_id': asset.item_id, 'expires_at': asset.expires_at}
        rows.append(row)
    return rows


def _request_asset(actor, reference):
    actor.validate()
    if actor.share.party_requests:
        for record in actor.manager._display_admission.participation.requests.pending(actor.share):
            if (asset := record.artwork) is not None and _request_reference(actor, asset) == reference:
                return asset
    return None


def qualified(actor, *, flow_item_id=None):
    actor.validate()
    state = actor.manager._display_admission
    now = state._clock()
    broadcast = actor.active.broadcast
    if broadcast.state.runtime_state != 'active':
        return None
    if flow_item_id is None:
        asset = getattr(broadcast, 'display_artwork', None)
        if asset is None or not asset.current(actor.active, now) or not asset.source_current():
            return None
    else:
        from .guest_presentation import shared_items
        from .display_observed import public as public_observations
        asset = getattr(broadcast, 'display_flow_artwork', {}).get(flow_item_id)
        if (asset is None or now >= asset.flow_deadline or not asset.source_current()
                or not any(item.get('playback_item_id') == flow_item_id
                           for item in [*shared_items(actor.active, now=now).values(),
                                        *public_observations(actor.share, state)])):
            return None
    if (actor.share.share_id, actor.share.generation) not in asset.shares:
        return None
    binding = (state.issuer_epoch, 'guest', actor.grant.principal_id,
               actor.grant.generation, actor.share.share_id, str(actor.share.generation),
               actor.active.session_id, asset.item_id, asset.nonce,
               'flow' if flow_item_id is not None else 'current',
               asset.flow_expires_at if flow_item_id is not None else asset.expires_at)
    return hashlib.sha256(':'.join(binding).encode()).hexdigest(), asset


def descriptor(actor, *, flow_item_id=None):
    found = qualified(actor, flow_item_id=flow_item_id)
    if found is None:
        return None
    reference, asset = found
    return {'reference': reference, 'item_id': asset.item_id,
            'expires_at': asset.flow_expires_at if flow_item_id is not None else asset.expires_at}


def read(service, actor, reference, selected):
    if not re.fullmatch(r'[a-f0-9]{64}', reference):
        raise DisplayAdmissionError('guest_artwork_unavailable', 404)
    found, flow_item_id = qualified(actor), None
    if found is None or found[0] != reference:
        found = None
        for item_id in getattr(actor.active.broadcast, 'display_flow_artwork', {}):
            match = qualified(actor, flow_item_id=item_id)
            if match is not None and match[0] == reference:
                found, flow_item_id = match, item_id
                break
    request_art = _request_asset(actor, reference) if found is None else None
    if found is None and request_art is None:
        raise DisplayAdmissionError('guest_artwork_unavailable', 404)
    asset = request_art if request_art is not None else found[1]
    from .display_delivery import MAX_DISPLAY_ARTWORK_BYTES, display_live_hub
    if (type(asset.body) is not bytes or len(asset.body) > MAX_DISPLAY_ARTWORK_BYTES
            or asset.mime not in {'image/jpeg', 'image/png', 'image/webp'}):
        raise DisplayAdmissionError('guest_artwork_unavailable', 404)

    def guard():
        try:
            if request_art is not None:
                return _request_asset(actor, reference) is request_art
            match = qualified(actor, flow_item_id=flow_item_id)
            return match is not None and match[0] == reference and match[1] is asset
        except (SessionConversationError, DisplayAdmissionError):
            return False

    complete = display_live_hub(actor.manager).reserve_artwork('guest:' + actor.grant.principal_id)
    return service.display._release_result({}, guard, complete, (asset.body, asset.mime),
                                           actor.manager._display_admission, selected)
