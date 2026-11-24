"""Prepared public track art under an original guest, never display authority."""
from __future__ import annotations

import hashlib
import re

from .display_admission import DisplayAdmissionError
from .session_conversation import SessionConversationError


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
    if found is None:
        raise DisplayAdmissionError('guest_artwork_unavailable', 404)
    asset = found[1]
    from .display_delivery import MAX_DISPLAY_ARTWORK_BYTES, display_live_hub
    if (type(asset.body) is not bytes or len(asset.body) > MAX_DISPLAY_ARTWORK_BYTES
            or asset.mime not in {'image/jpeg', 'image/png', 'image/webp'}):
        raise DisplayAdmissionError('guest_artwork_unavailable', 404)

    def guard():
        try:
            match = qualified(actor, flow_item_id=flow_item_id)
            return match is not None and match[0] == reference and match[1] is asset
        except (SessionConversationError, DisplayAdmissionError):
            return False

    complete = display_live_hub(actor.manager).reserve_artwork('guest:' + actor.grant.principal_id)
    return service.display._release_result({}, guard, complete, (asset.body, asset.mime),
                                           actor.manager._display_admission, selected)
