"""Original shared Moment references, without private images or publication."""
from __future__ import annotations

import re
import secrets

from .display_admission import DisplayAdmissionError
from .session_conversation import SessionConversationError


def shared_items(active, *, now):
    from .display_projection import _qualified_shared_moments
    broadcast = active.broadcast
    current = broadcast.state
    flow_ids = {item.moment_id for item in current.session_flow.items if item.moment_id}
    moments, flow = _qualified_shared_moments(active, broadcast, current, current.playback, flow_ids, now)
    return {item['moment_id']:item for item in [*moments, *(item for _,item in flow)]}


def public_context(actor):
    actor.validate()
    items = shared_items(actor.active, now=actor.manager._display_admission._clock())
    return {'playback':actor.shared_status()['playback'], 'moments':[
        {key:item[key] for key in ('moment_id', 'title', 'summary', 'moment_type') if key in item}
        for item in list(items.values())[-12:]]}


def focus(actor, moment_id):
    actor.validate()
    guests = actor.manager._display_admission.participation
    _, policy = guests.validate(actor.grant)
    if not policy.screen_focus:
        raise SessionConversationError('guest_screen_focus_disabled', 403)
    now = guests.display._clock()
    if not any(display.share_id == actor.share.share_id and display.lease_deadline > now
               and display.owner.valid() for display in guests.display._displays.values()):
        raise SessionConversationError('guest_screen_unavailable', 409)
    if moment_id is None:
        guests._focus.pop(actor.share.share_id, None)
        return {'focused_moment_id':None}
    if moment_id not in shared_items(actor.active, now=now):
        raise SessionConversationError('guest_shared_moment_unavailable', 404)
    guests._focus[actor.share.share_id] = (moment_id, min(actor.share.deadline, now + 30), actor.grant, secrets.token_urlsafe(18))
    return {'focused_moment_id':moment_id}


def display_focus(hass, manager, display):
    state = manager._display_admission
    guests = state.participation
    row = guests._focus.get(display.share_id)
    if row is None:
        return {'focused_moment_id':None, 'expires_in':0}
    identifier, deadline, guest, revision = row
    active = manager.current_active(display.owner.profile_id)
    try:
        guests.validate(guest)
        if (active is None or active.session_id != display.owner.session_id
                or deadline <= state._clock() or identifier not in shared_items(active, now=state._clock())):
            raise DisplayAdmissionError('guest_shared_moment_unavailable', 404)
    except DisplayAdmissionError:
        guests._focus.pop(display.share_id, None)
        return {'focused_moment_id':None, 'expires_in':0}
    return {'focused_moment_id':identifier, 'focus_revision':revision, 'expires_in':deadline - state._clock()}


FOCUS_TEXT = {
    'en':('This shared Moment is selected for the screen.', 'The screen is returning to live.'),
    'nl':('Deze gedeelde Moment is geselecteerd voor het scherm.', 'Het scherm keert terug naar live.'),
    'de':('Dieser geteilte Moment ist für den Bildschirm ausgewählt.', 'Der Bildschirm kehrt zu Live zurück.'),
    'fr':('Ce Moment partagé est sélectionné pour l’écran.', 'L’écran revient au direct.'),
    'es':('Este Moment compartido está seleccionado para la pantalla.', 'La pantalla vuelve al directo.'),
}


def presentation_action(text):
    value = ' '.join(str(text).casefold().strip(' .!?').split())
    if re.fullmatch(r'(?:toon|laat|show|zeig(?:e)?|affiche|montre|muestra)(?: (?:dit|deze|dat|die|this|that|das|diesen|ce|ceci|ça|este|eso|ese))?(?: moment)?(?: (?:op het scherm|op tv|zien|on (?:the )?screen|auf dem bildschirm|à l’écran|sur l’écran|en (?:la )?pantalla))?', value):
        return 'focus'
    if value in {'terug naar live','terug naar het live scherm','back to live','return to live',
                 'zurück zu live','revenir au direct','retour au direct','volver al directo'}:
        return 'return'
    return None


def selected_shared_moment(actor, target):
    actor.validate()
    if (not isinstance(target, dict) or set(target) != {'session_id','moment_id'}
            or target['session_id'] != actor.active.session_id
            or target['moment_id'] not in shared_items(actor.active, now=actor.manager._display_admission._clock())):
        raise SessionConversationError('guest_shared_moment_unavailable', 404)
    moment = next((m for m in actor.active.broadcast.state.dj_moments if m.moment_id == target['moment_id']), None)
    if moment is None:
        raise SessionConversationError('guest_shared_moment_unavailable', 404)
    return moment


async def presentation_response(actor, payload, action):
    from .ask_dj.dialogue import current_turn
    turn = current_turn.get()
    target = None
    if action == 'focus':
        explicit = (payload.get('conversation_context') or {}).get('selected_moment')
        previous = next((d for d in reversed(turn.frame.dependencies) if 'moment_id' in d), None)
        target = explicit or previous
        if target is None:
            target = {'session_id':actor.active.session_id,
                      'moment_id':actor.active.broadcast.current_delivery_candidate_id()}
        selected_shared_moment(actor, target)
    async with actor.manager._lock:
        result = focus(actor, target['moment_id'] if target else None)
    if target:
        turn.dependencies = [target]
    return {'success':True, 'text':FOCUS_TEXT.get(payload.get('language'), FOCUS_TEXT['en'])[action == 'return'],
            'shared_presentation':result}
