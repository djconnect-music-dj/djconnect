"""Pure temporary up-next presentation under the original observed queue."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re

COPY = {
    'nl': ('Hierna staat “{title}” van {artist} voor je klaar.',
           'Een korte blik vooruit: “{title}” van {artist}.',
           'Straks in de mix: “{title}” van {artist}.',
           'Hierna op het programma: “{title}” van {artist}.'),
    'en': ('Up next for you: “{title}” by {artist}.',
           'A quick look ahead: “{title}” by {artist}.',
           'Next in the mix: “{title}” by {artist}.',
           'Coming up: “{title}” by {artist}.'),
    'de': ('Als Nächstes liegt „{title}“ von {artist} für dich bereit.',
           'Ein kurzer Blick nach vorn: „{title}“ von {artist}.',
           'Als Nächstes im Mix: „{title}“ von {artist}.',
           'Gleich im Programm: „{title}“ von {artist}.'),
    'fr': ('Ensuite pour toi : « {title} » de {artist}.',
           'Un bref regard sur la suite : « {title} » de {artist}.',
           'La suite du mix : « {title} » de {artist}.',
           'À suivre : « {title} » de {artist}.'),
    'es': ('A continuación para ti: «{title}» de {artist}.',
           'Un vistazo a lo que viene: «{title}» de {artist}.',
           'Lo siguiente en la mezcla: «{title}» de {artist}.',
           'A continuación en el programa: «{title}» de {artist}.'),
}
PERSONAS = ('home_dj', 'radio_dj', 'club_dj', 'festival_dj')


def project(broadcast, *, locale=None):
    state, forecast = broadcast.state, broadcast.forecast
    playback = state.playback
    if (getattr(state.runtime_state, 'value', state.runtime_state) != 'active'
            or playback.state != 'playing' or not playback.item_id
            or type(playback.duration_ms) is not int or type(playback.position_ms) is not int
            or not 0 < playback.duration_ms - playback.position_ms <= 45000
            or not 0 <= playback.position_ms < playback.duration_ms
            or not forecast.authority()):
        return None
    queue = forecast.queue_context(playback.item_id)
    upcoming = dict(playback.up_next)
    first = queue.get('items', [{}])[0] if queue else {}
    source_url = upcoming.get('source_url', '')
    if (not queue or upcoming.get('current_item_id') != playback.item_id
            or re.fullmatch(r'https://open\.spotify\.com/track/[A-Za-z0-9]{22}', source_url) is None
            or not all(upcoming.get(key) and upcoming.get(key) == first.get(key)
                       for key in ('title', 'artist'))):
        return None
    try:
        expiry = min(datetime.fromisoformat(upcoming['expires_at']).timestamp(), queue['wall_deadline'])
        if expiry <= forecast.wall_clock():
            return None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    from .session_forecast import timestamp
    uri = 'spotify:track:' + source_url.rsplit('/', 1)[-1]
    identifier = hashlib.sha256(json.dumps([state.session_id, playback.item_id, uri,
        upcoming['title'], upcoming['artist']], ensure_ascii=False).encode()).hexdigest()
    persona = getattr(state.dj_persona, 'value', state.dj_persona)
    forms = COPY.get(locale or state.locale, COPY['en'])
    text = forms[PERSONAS.index(persona) if persona in PERSONAS else 0].format(**upcoming)
    track = {'item_id':hashlib.sha256(uri.encode()).hexdigest()[:24],
             'title':upcoming['title'], 'artist':upcoming['artist'], 'source_url':source_url}
    if upcoming.get('artwork_url'):
        track['artwork_url'] = upcoming['artwork_url']
    return {'contract_version':1, 'type':'horizon', 'preview_id':identifier,
            'session_id':state.session_id, 'current_item_id':playback.item_id,
            'text':text, 'expires_at':timestamp(expiry), 'track':track}
