"""Purpose-qualified passive Session delivery, never a second content producer.

Only original accepted evidence and already prepared cover bytes are projected.
Reads do not renew clocks, fetch content, mutate grants or publish events.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
import re
import secrets
import time
from typing import Callable

from .passive_contribution import contribution, retained_latest, status

VERSION = 1
MAX_GRANTS = 32
SURFACES = {'widget', 'live_activity', 'watch_widget'}
TRACK = re.compile(r'https://open\.spotify\.com/track/([A-Za-z0-9]{22})\Z')
BASE = '/api/djconnect/v1/session/surface'


def stamp(value):
    return datetime.fromtimestamp(value, UTC).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:32]


def capability():
    return {'version': VERSION, 'owner_only': True, 'authentication': 'paired_device_bearer',
            'authorize_path': BASE + '/authorize', 'read_path': BASE + '/read',
            'surfaces': sorted(SURFACES), 'explicit_consent_required': True,
            'max_cache_seconds': 120, 'read_side_effects': False,
            'live_invalidation': 'existing_owner_broadcast_events',
            'projection_versions': [1, 2, 3, 4], 'default_projection_version': 1,
            'background_delivery': False, 'watch_replication': False,
            'retained_latest': {'surface': 'widget', 'projection_version': 4,
                'consent_field': 'retained_latest', 'maximum_publication_seconds': 1800},
            'watch_widget': {'scope': 'paired_watch_widget_v1', 'surface': 'watch_widget',
                'client_type': 'watchos', 'contract_version': 1, 'projection_version': 1,
                'explicit_consent_required': True, 'locked_display_required': True,
                'background_delivery': False}}


@dataclass(frozen=True)
class SurfaceGrant:
    grant_id: str
    binding_id: str
    generation: str
    entry_id: str
    surface: str
    locked_display: bool
    authority: Callable[[], bool]
    projection_version: int = 1


def _text(broadcast, now):
    """Legacy representation never receives an unknown provenance vocabulary."""
    return contribution(broadcast, now, projection_version=1)[0]


def _observed_track_reference(original):
    match = TRACK.fullmatch(original.source_url)
    if not match or digest_identity('spotify:track:' + match[1]) != original.item_id or not original.title:
        return None
    return match


def _music(broadcast, now, *, projection_version=1):
    observed = broadcast.passive_observation
    if not observed:
        return None, status('no_observation')
    if not 0 <= now - observed[0] < 120 or time.time() >= observed[1] + 120:
        return None, status('original_deadline_expired')
    _, wall, original = observed
    current = broadcast.state.playback
    match = _observed_track_reference(original)
    if match is None:
        return None, status('source_not_qualified')
    if current.item_id != original.item_id:
        return None, status('subject_changed')
    if current.state not in {'playing', 'paused'}:
        return None, status('playback_inactive')
    music = {'item_id': original.item_id, 'subject_uri': 'spotify:track:' + match[1],
            'track': original.title, 'artist': original.artist, 'album': original.album,
            'observed_at': stamp(wall), 'expires_at': stamp(wall + 120),
            'source_url': original.source_url,
            'attribution': {'provider': 'Spotify', 'mark': 'spotify', 'url': original.source_url},
            'usage_basis': 'spotify_temporary_passive_metadata'}
    if projection_version in (3, 4):
        progress = _progress(broadcast, now)
        if progress is not None:
            music['progress'] = progress
    return music, status('qualified', 'available')


def _accepted_progress_source(original, current, position, duration):
    if (original.state not in {'playing', 'paused'} or current.state != original.state
            or current.item_id != original.item_id
            or type(position) is not int or type(duration) is not int
            or not 0 <= position <= duration <= 9007199254740991 or duration == 0):
        return False
    return True


def _progress(broadcast, now):
    """Original accepted data only; never the renderer's extrapolated position."""
    observed_mono, observed_wall, original = broadcast.passive_observation
    snapshot_mono, snapshot_wall = broadcast.passive_state_observed
    current = broadcast.state.playback
    position, duration = original.position_ms, original.duration_ms
    wall = time.time()
    if not _accepted_progress_source(original, current, position, duration):
        return None
    clocks = (now, wall, observed_mono, observed_wall, snapshot_mono, snapshot_wall)
    if (not all(type(v) in (int, float) and math.isfinite(v) for v in clocks)
            or not observed_mono <= now < observed_mono + 120
            or not snapshot_mono <= now < snapshot_mono + 120
            or not 0 < observed_wall <= wall < observed_wall + 120
            or not 0 < snapshot_wall <= wall < snapshot_wall + 120):
        return None
    try:
        return {'schema_version': 1, 'position_ms': position, 'duration_ms': duration,
                'playback_state': original.state, 'observed_at': stamp(observed_wall),
                'expires_at': stamp(min(observed_wall + 120, snapshot_wall + 120))}
    except (ValueError, OverflowError, OSError):
        return None


def digest_identity(uri):
    return hashlib.sha256(uri.encode()).hexdigest()[:24]


def _passive_cover_source_reason(asset, now):
    captured = asset.get('captured_monotonic')
    if not asset['authority']() or type(captured) not in (int, float) or not math.isfinite(captured):
        return 'source_not_qualified'
    if not captured <= now < captured + 120 or asset['deadline'] <= now:
        return 'original_deadline_expired'
    return None


def _passive_cover_shape(scope, art, subject):
    if (scope is None or art.get('state') != 'ready' or subject.get('type') not in {'track', 'album'}
            or art.get('role') not in {'cover', 'playback_thumbnail'}
            or art.get('usage_basis') != 'spotify_temporary_owner_display'
            or art.get('attribution') != {'provider': 'Spotify', 'mark': 'spotify', 'url': art.get('source_url')}
            or not re.fullmatch(r'https://open\.spotify\.com/(track|album)/[A-Za-z0-9]{22}', art.get('source_url', ''))):
        return False
    return True


def _passive_cover_slot(contribution, music, target, scope, subject):
    slot, expires = None, None
    if contribution and target.get('moment_id') == contribution['moment_id']:
        slot, expires = 'contribution', contribution['expires_at']
    elif music and scope[0] and subject.get('uri') == music['subject_uri']:
        slot, expires = 'now_playing', music['expires_at']
    return slot, expires


def _passive_cover_descriptor(slot, asset, subject, expiry, art, session_id):
    return {'slot': slot, 'asset_id': asset['asset_id'], 'subject': dict(subject),
                  'role': 'contextual_cover' if slot == 'contribution' else 'current_cover',
                  'media_revision': art['media_revision'], 'captured_at': art['captured_at'],
                  'expires_at': stamp(expiry), 'source_url': art['source_url'],
                  'attribution': dict(art['attribution']), 'alt_text': dict(art['alt_text']),
                  'width': art['width'], 'height': art['height'], 'crop_allowed': False,
                  'usage_basis': 'spotify_temporary_passive_cover',
                  'image_path': BASE + '/image/' + session_id + '/' + asset['asset_id'],
                  'rights': {'passive_cache': True, 'os_snapshot': True,
                             'external_relay': False, 'watch_replication': False}}


def _project_passive_cover(key, asset, slots, contribution, music, now, session_id):
    unavailable_reason = _passive_cover_source_reason(asset, now)
    if unavailable_reason is not None:
        return None, unavailable_reason
    scope = asset['delivery_scope']()
    art = asset['projection']['artwork']
    target = dict(key[2])
    subject = art.get('subject', {})
    if not _passive_cover_shape(scope, art, subject):
        return None, 'source_not_qualified'
    slot, expires = _passive_cover_slot(contribution, music, target, scope, subject)
    if slot is None or any(v['slot'] == slot for v in slots):
        return None, 'no_matching_subject'
    expiry = min(datetime.fromisoformat(expires).timestamp(),
                 datetime.fromisoformat(art['expires_at']).timestamp(),
                 datetime.fromisoformat(art['captured_at']).timestamp() + 120)
    # Monotonic and UTC must both permit; clock uncertainty fails closed.
    if time.time() >= expiry:
        return None, 'original_deadline_expired'
    return _passive_cover_descriptor(slot, asset, subject, expiry, art, session_id), None


def _covers(registry, owner, session_id, contribution, music, now):
    """Independent cover-only qualification; no private URL/grant reuse."""
    if not contribution and not music:
        return [], status('no_eligible_context')
    if registry is None or registry.closed:
        return [], status('not_prepared')
    slots, reason = [], 'not_prepared'
    for key, asset in registry.assets.items():
        if key[:2] != (owner, session_id) or asset['historical']:
            continue
        reason = 'no_matching_subject'
        projected, unavailable_reason = _project_passive_cover(
            key, asset, slots, contribution, music, now, session_id)
        if projected is not None:
            slots.append(projected)
        else:
            reason = unavailable_reason
    return slots, status('qualified', 'available') if slots else status(reason)


def _passive_frame_current(active, broadcast, grant, *, watch=False):
    if not grant.authority():
        return False
    if watch and not grant.locked_display:
        return False
    return (active.runtime_state.value == 'active'
            and broadcast.state.runtime_state.value == 'active')


def _watch_snapshot_current(broadcast, now, wall):
    return not (not 0 <= now - broadcast.passive_state_observed[0] < 120
                or not 0 < broadcast.passive_state_observed[1] <= wall < broadcast.passive_state_observed[1] + 120)


def _surface_snapshot_current(broadcast, now, wall):
    return not (not 0 <= now - broadcast.passive_state_observed[0] < 120
                or wall >= broadcast.passive_state_observed[1] + 120)


def _watch_projection(active, grant, *, registry=None, owner=''):
    """Own paired Watch consent and minimal DTO; never a replicated phone view."""
    broadcast = active.broadcast
    now, wall = time.monotonic(), time.time()
    result = {'schema_version': 1, 'scope': 'paired_watch_widget_v1',
              'surface': 'watch_widget', 'binding_id': grant.binding_id,
              'generation': grant.generation, 'session_id': active.session_id,
              'delivery_sequence': broadcast.delivery_sequence, 'as_of': stamp(wall),
              'observed_at': stamp(broadcast.passive_state_observed[1]),
              'expires_at': stamp(broadcast.passive_state_observed[1] + 120),
              'state': 'active',
              'cache_policy': {'scope': 'current_watch_widget_only', 'maximum_seconds': 120,
                  'renew_on_read': False, 'locked_display': grant.locked_display,
                  'os_pixel_erasure': 'best_effort_when_learned'},
              'mood': {'value': active.selected_mood if active.selected_mood in
                  {'chill', 'groove', 'energy', 'party'} else None, 'revision': active.mood_revision},
              'now_playing': None, 'artwork': []}
    if not _passive_frame_current(active, broadcast, grant, watch=True):
        result['state'], reason = 'withdrawn', 'authority_withdrawn'
        result['mood'] = {'value': None, 'revision': 0}
        result['expires_at'] = stamp(wall)
        result['now_playing_status'] = status(reason, 'withdrawn')
        result['artwork_status'] = status(reason, 'withdrawn')
    elif not _watch_snapshot_current(broadcast, now, wall):
        result['state'] = 'stale'
        result['mood'] = {'value': None, 'revision': 0}
        result['now_playing_status'] = status('original_snapshot_expired', 'stale')
        result['artwork_status'] = status('original_snapshot_expired', 'stale')
    else:
        music, result['now_playing_status'] = _music(broadcast, now)
        if music is not None:
            allowed = {'item_id', 'subject_uri', 'track', 'observed_at', 'expires_at',
                       'source_url', 'attribution', 'usage_basis'}
            result['now_playing'] = {key: value for key, value in music.items() if key in allowed}
        covers, result['artwork_status'] = _covers(registry, owner, active.session_id, None, music, now)
        result['artwork'] = covers[:1]
        for cover in result['artwork']:
            cover['rights']['paired_watch_cache'] = True
    result['revision'] = digest({k: v for k, v in result.items() if k != 'as_of'})
    return result


def _withdrawn_surface_projection(active, broadcast, grant, wall):
    return {'schema_version': grant.projection_version, 'state': 'withdrawn', 'surface': grant.surface,
            'binding_id': grant.binding_id, 'generation': grant.generation,
            'session_id': active.session_id, 'delivery_sequence': broadcast.delivery_sequence,
            'as_of': stamp(wall), 'expires_at': stamp(wall), 'artwork': [],
            **({'latest_contribution': None, 'latest_contribution_status': status('authority_withdrawn', 'withdrawn')}
               if grant.projection_version == 4 else {}),
            **({name: status('authority_withdrawn', 'withdrawn')
                for name in ('contribution_status', 'now_playing_status', 'artwork_status')}
               if grant.projection_version in (2, 3, 4) else {})}


def _expire_surface_projection(result, grant):
    result['state'] = 'stale'
    result['contribution'], result['now_playing'], result['artwork'] = None, None, []
    if grant.projection_version == 4:
        result['latest_contribution'] = None
        result['latest_contribution_status'] = status('original_snapshot_expired', 'stale')
    if grant.projection_version in (2, 3, 4):
        for name in ('contribution_status', 'now_playing_status', 'artwork_status'):
            result[name] = status('original_snapshot_expired', 'stale')


def projection(active, grant, *, registry=None, owner=''):
    """Pure projection over accepted state; grant authority is checked by caller."""
    if grant.surface == 'watch_widget':
        return _watch_projection(active, grant, registry=registry, owner=owner)
    broadcast = active.broadcast
    now, wall = time.monotonic(), time.time()
    result = {'schema_version': grant.projection_version, 'surface': grant.surface,
              'binding_id': grant.binding_id, 'generation': grant.generation,
              'session_id': active.session_id, 'delivery_sequence': broadcast.delivery_sequence,
              'as_of': stamp(wall), 'observed_at': stamp(broadcast.passive_state_observed[1]),
              'expires_at': stamp(broadcast.passive_state_observed[1] + 120),
              'state': 'active', 'playback_state': broadcast.state.playback.state,
              'cache_policy': {'scope': 'current_surface_only', 'maximum_seconds': 120,
                               'renew_on_read': False, 'locked_display': grant.locked_display,
                               'os_pixel_erasure': 'best_effort_when_learned'},
              'mood': {'value': active.selected_mood if active.selected_mood in
                       {'chill', 'groove', 'energy', 'party'} else None, 'revision': active.mood_revision},
              'presence': active.selected_presence, 'persona': active.dj_persona.value,
              'navigation': {'kind': 'open_session', 'session_id': active.session_id}}
    # Revision belongs to the original frame, not read-time field pruning.
    result['revision'] = digest({k: v for k, v in result.items() if k != 'as_of'})
    if not _passive_frame_current(active, broadcast, grant):
        return _withdrawn_surface_projection(active, broadcast, grant, wall)
    if grant.projection_version == 4:
        result['latest_contribution'], result['latest_contribution_status'] = retained_latest(broadcast, now)
    text, text_status = contribution(broadcast, now, projection_version=min(grant.projection_version, 3))
    music, music_status = _music(broadcast, now, projection_version=grant.projection_version)
    result['contribution'], result['now_playing'] = text, music
    result['artwork'], artwork_status = _covers(registry, owner, active.session_id, text, music, now)
    if grant.projection_version in (2, 3, 4):
        result['contribution_status'] = text_status
        result['now_playing_status'] = music_status
        result['artwork_status'] = artwork_status
    if not _surface_snapshot_current(broadcast, now, wall):
        _expire_surface_projection(result, grant)
    return result


def _surface_request_fields(payload, authorize):
    fields = {'contract_version', 'device_id', 'client_type', 'session_id', 'surface'}
    fields |= {'enabled', 'os_snapshot_cache', 'locked_display'} if authorize else {'grant_id'}
    if isinstance(payload, dict) and 'projection_version' in payload:
        fields.add('projection_version')
    if authorize and isinstance(payload, dict) and payload.get('projection_version') == 4:
        fields.add('retained_latest')
    return fields


def _valid_surface_fields(payload, fields):
    return (isinstance(payload, dict) and set(payload) == fields
            and type(payload.get('contract_version')) is int and payload['contract_version'] == VERSION
            and not any(type(payload[k]) is not str or not 0 < len(payload[k]) <= 128
                for k in fields - {'contract_version', 'projection_version', 'enabled',
                                  'os_snapshot_cache', 'locked_display', 'retained_latest'}))


def _valid_surface_version(payload):
    return (type(payload.get('projection_version', 1)) is int
            and payload.get('projection_version', 1) in (1, 2, 3, 4))


def _valid_surface_client(payload):
    return (payload['surface'] in SURFACES
            and (payload.get('projection_version', 1) != 4 or payload['surface'] == 'widget')
            and (payload['surface'] != 'watch_widget' or
                 (payload['client_type'] == 'watchos' and payload.get('projection_version', 1) == 1))
            and (payload['surface'] == 'watch_widget' or payload['client_type'] in {'ios', 'macos'}))


def _valid_surface_consent(payload, authorize):
    if authorize and any(type(payload[k]) is not bool for k in ('enabled', 'os_snapshot_cache', 'locked_display')):
        return False
    if authorize and payload.get('projection_version') == 4 and type(payload.get('retained_latest')) is not bool:
        return False
    return True


def _surface_contract(payload, authorize):
    fields = _surface_request_fields(payload, authorize)
    return (_valid_surface_fields(payload, fields) and _valid_surface_version(payload)
            and _valid_surface_client(payload) and _valid_surface_consent(payload, authorize))


def _authorize_surface_grant(grants, key, payload, entry, current, error):
    if not payload['enabled']:
        grants.pop(key, None)
        return None, ({'success': True, 'contract_version': VERSION, 'state': 'disabled'}, 200)
    if payload.get('projection_version') == 4 and not payload['retained_latest']:
        return None, error('surface_consent_required', 403)
    if not payload['os_snapshot_cache'] or (payload['surface'] in {'live_activity', 'watch_widget'} and not payload['locked_display']):
        return None, error('surface_consent_required', 403)
    if key not in grants and len(grants) >= MAX_GRANTS:
        return None, error('surface_capacity', 409)
    grant = SurfaceGrant(secrets.token_urlsafe(24), secrets.token_hex(16), secrets.token_hex(16),
                         entry.entry_id, payload['surface'], payload['locked_display'], current,
                         payload.get('projection_version', 1))
    grants[key] = grant
    return grant, None


def _read_surface_grant(grants, key, payload, error):
    grant = grants.get(key)
    if (not grant or grant.projection_version != payload.get('projection_version', 1)
            or not secrets.compare_digest(grant.grant_id, payload['grant_id']) or not grant.authority()):
        return None, error('surface_grant_invalid', 403)
    return grant, None


def _surface_runtime(hass, payload, headers, *, resolve_runtime, authorize_device):
    if not str(headers.get('Authorization', '')).startswith('Bearer '):
        return None
    runtime = resolve_runtime(hass, payload['device_id'], headers)
    if runtime is None or not authorize_device(runtime, headers, payload['device_id'], payload['client_type']):
        return None
    return runtime


def _surface_runtime_epoch(hass, storage, revision, latest, active, source_authority, manager,
                           entry, entry_generation, *, profile_storage):
    return (profile_storage(hass) is storage and storage.authority_revision == revision
            and latest is not None and latest.broadcast is active.broadcast
            and latest.runtime_state.value == 'active' and source_authority()
            and manager.receiver_entry_generation(entry.entry_id) == entry_generation)


def _surface_profile_device(profile, owner, conf, device_id, client_type, *, resolve_privacy):
    return (profile.profile_id == owner and profile.privacy_mode.value == 'normal'
            and resolve_privacy(profile, {}).allow_personal_read
            and conf.get('device_id') == device_id and conf.get('client_type') == client_type)


async def handle(hass, payload, *, headers=None, authorize=False):
    """Ordinary pairing + exact owner/entry/generation/source fences."""
    from .api_handlers import _async_owner_broadcast_session_context
    from .profile_context import profile_storage
    from .profile_privacy import resolve_profile_privacy_policy
    from .forecast_imagery import artist_authority
    from .request_auth import resolve_runtime, authorize_runtime_device_request

    def error(code, status):
        return {'success': False, 'error': code}, status

    if not _surface_contract(payload, authorize):
        return error('invalid_request', 400)
    headers = headers or {}
    runtime = _surface_runtime(hass, payload, headers, resolve_runtime=resolve_runtime,
                               authorize_device=authorize_runtime_device_request)
    if runtime is None:
        return error('unauthorized', 401)
    context, status, manager, owner = await _async_owner_broadcast_session_context(
        hass, dict(payload), headers=headers, source='passive_session')
    if manager is None:
        return context, status
    storage = profile_storage(hass)
    revision = storage.authority_revision
    entry = runtime.entry
    device_id, client_type = payload['device_id'], payload['client_type']
    entry_generation = getattr(runtime, '_receiver_end_generation', 0)
    source_authority = artist_authority(hass, runtime, owner_profile_id=owner,
        expected_source=manager._history_source_contexts.get(payload['session_id'], {}))
    active = manager._active_by_profile.get(owner)
    if active is None or active.session_id != payload['session_id']:
        return error('active_session_not_found', 404)

    def current():
        try:
            profile = storage.resolver().resolve_bound_device(device_id)
            latest = manager._active_by_profile.get(owner)
            conf = {**entry.data, **entry.options}
            return (_surface_runtime_epoch(hass, storage, revision, latest, active, source_authority,
                        manager, entry, entry_generation, profile_storage=profile_storage)
                    and _surface_profile_device(profile, owner, conf, device_id, client_type,
                                               resolve_privacy=resolve_profile_privacy_policy))
        except Exception:
            return False

    if not current():
        return error('surface_not_allowed', 403)
    grants = active.broadcast.passive_grants
    key = (entry.entry_id, payload['surface'])
    if authorize:
        grant, response = _authorize_surface_grant(grants, key, payload, entry, current, error)
    else:
        grant, response = _read_surface_grant(grants, key, payload, error)
    if response is not None:
        return response
    resource = projection(active, grant, registry=hass.data.get('djconnect', {}).get('session_images'), owner=owner)
    return {'success': True, 'contract_version': VERSION, 'grant_id': grant.grant_id,
            'passive_session': resource}, 200
