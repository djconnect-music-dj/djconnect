"""RAM-only public metadata observations captured at accepted playback, not GET."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import re
from uuid import uuid4


@dataclass(frozen=True, repr=False)
class SharedObservation:
    entry_id: str
    playback_item_id: str
    title: str
    artist: str
    album: str
    source_url: str
    observed_at: str
    expires_at: str
    deadline: float
    source_current: object


def capture(state, active, source_sample, media_identity, *, occurrence=None):
    """Only the normal accepted provider observation calls this private helper."""
    from .surface_status_samples import OriginalSample
    if (type(source_sample) is not OriginalSample or not source_sample.current()
            or source_sample.state != 'playing'
            or type(media_identity) is not str
            or not re.fullmatch(r'spotify:track:[A-Za-z0-9]{22}', media_identity)):
        return
    playback = active.broadcast.state.playback
    expected = hashlib.sha256(media_identity.encode()).hexdigest()[:24]
    if (playback.state != 'playing' or playback.item_id != expected
            or playback.source_url != 'https://open.spotify.com/track/' + media_identity.rsplit(':', 1)[-1]
            or any(type(value) is not str or len(value) > 512
                   for value in (playback.title, playback.artist, playback.album))):
        return
    from .track_start_announcement import Occurrence
    if type(occurrence) is not Occurrence or occurrence.item_id != playback.item_id:
        occurrence = None
    key = occurrence.occurrence_id if occurrence is not None else None
    now = state._clock()
    def current():
        return source_sample.witness.current(historical=True)
    for share in state._shares.values():
        if (share.owner.session_id != active.session_id or not share.owner.valid()
                or share.deadline <= now):
            continue
        # The announcement occurrence is sent only on its start sample. Later
        # polls of that recording belong to the same row unless playback repeats.
        if (share.observed_item_id == playback.item_id
                and (occurrence is None or not occurrence.repeated or share.observed_key == key)):
            continue
        deadline = min(share.deadline, source_sample.observed_monotonic + 1800)
        if deadline <= now or not current():
            continue
        observed_at = datetime.fromtimestamp(source_sample.observed_ms / 1000, UTC)
        entry_id = key or 'observed-' + uuid4().hex
        row = SharedObservation(entry_id, playback.item_id, playback.title, playback.artist, playback.album,
            playback.source_url, observed_at.isoformat(),
            (observed_at + timedelta(seconds=deadline-source_sample.observed_monotonic)).isoformat(),
            deadline, current)
        share.observed_playback = tuple(item for item in share.observed_playback
            if item.deadline > now and item.source_current())[-11:] + (row,)
        share.observed_item_id = playback.item_id
        share.observed_key = entry_id


def public(share, state):
    now = state._clock()
    if state._shares.get(share.share_id) is not share or share.deadline <= now or not share.owner.valid():
        return []
    fields = ('entry_id', 'playback_item_id', 'title', 'artist', 'album', 'source_url',
              'observed_at', 'expires_at')
    return [{key:getattr(row, key) for key in fields} for row in share.observed_playback
            if row.deadline > now and row.source_current()]
