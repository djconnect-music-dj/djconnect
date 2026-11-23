"""Literal recording constraints are checked before any Spotify playback write."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlencode


def _identity(value):
    return ' '.join(re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', value).casefold()).split())


async def resolve_recording(backend, constraints, media_type):
    from .spotify_backend import SpotifyBackendError, DEFAULT_SPOTIFY_MARKET

    def deny():
        raise SpotifyBackendError('The requested recording could not be uniquely verified')

    if media_type != 'track' or type(constraints) is not dict or set(constraints) != {'title', 'artist', 'album'}:
        deny()
    if any(type(v) is not str or not v.strip() or len(v) > 300
           or re.search(r'["\\\x00-\x1f]', v) or not _identity(v) for v in constraints.values()):
        deny()
    query = ' '.join(f'{field}:"{constraints[key]}"' for field, key in
                     (('track', 'title'), ('artist', 'artist'), ('album', 'album')))
    params = urlencode({'q':query, 'type':'track', 'limit':10,
                        'market':str(backend.conf.get('spotify_market') or DEFAULT_SPOTIFY_MARKET)})
    data = await backend._request('GET', '/search?' + params)
    section = data.get('tracks') if isinstance(data, dict) else None
    items = section.get('items') if isinstance(section, dict) else None
    if not isinstance(items, list) or len(items) > 10:
        deny()
    matches = {}
    for item in items:
        if not isinstance(item, dict) or item.get('is_local') or item.get('is_playable') is False:
            continue
        album = item.get('album')
        credits = item.get('artists')
        if (not isinstance(album, dict) or not isinstance(credits, list)
                or not re.fullmatch(r'spotify:track:[A-Za-z0-9]{22}', str(item.get('uri') or ''))):
            continue
        title, album_name = item.get('name'), album.get('name')
        if (type(title) is str and type(album_name) is str
                and _identity(title) == _identity(constraints['title'])
                and _identity(album_name) == _identity(constraints['album'])
                and any(isinstance(artist, dict) and type(artist.get('name')) is str
                        and _identity(artist['name']) == _identity(constraints['artist']) for artist in credits)):
            matches[item['uri']] = item
    if len(matches) != 1:
        deny()
    return next(iter(matches.values())), data
