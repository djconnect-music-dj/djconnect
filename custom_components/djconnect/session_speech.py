"""Private accepted-reference speech presentation in existing contribution owners.

Text is never supplied by a caller. The dialogue window owns ephemeral replies;
this module neither archives a body nor repeats semantic Ask DJ execution.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from dataclasses import dataclass
import hashlib
import json
import time

PATH = "/api/djconnect/v1/speech/prepare"
TTL = 300
MAX_TEXT = 4000
MAX_SEGMENT = 1200
MAX_SEGMENTS = 8
MAX_REFERENCES = 8
LITERAL_PROCESSING_BASES = frozenset({
    "qualified_dialogue_v1", "cc0_normalized_fields_v1", "runtime_authored_direction_v1",
    "spotify_owner_local_read_v1", "retained_owner_local_read_v1", "accepted_local_reply",
    "core_owned_voice_preview_v1",
    "core_owned_persona_reaction_v1",
    "runtime_accepted_settings_v1",
    "public_news_bulletin_v1",
    "private_headline_manual_ha_v1",
})


def accepted_processing_basis(result):
    """Server-established processing provenance, never inferred from history text."""
    basis = result.get("speech_processing_basis") or result.get("model_processing_basis")
    return basis if basis in {"qualified_dialogue_v1", "cc0_normalized_fields_v1",
        "runtime_authored_direction_v1", "spotify_owner_local_read_v1"} else "accepted_local_reply"


def capability():
    from .session_runtime import DJMomentType
    result = {"available": True, "version": 1, "path": PATH, "method": "POST",
            "supported_moment_types": [kind.value for kind in DJMomentType if kind is not DJMomentType.SILENCE],
            "excluded_moment_types": [DJMomentType.SILENCE.value],
            "supported_prepare_versions": [1, 2, 3],
            "shared_profile_settings": {"version": 3, "prepare_version": 3,
                "path": "/api/djconnect/v1/profile/settings",
                "scope": "profile_and_active_session", "storage_owner": "core",
                "voice_processor": "ha_configured", "caller_voice_override": False,
                "activated_profile_requires_version": 3},
            "authentication": "paired_device_bearer", "owner_only": True,
            "supported_reference_kinds": ["turn_id", "moment_id", "entry_id"],
            "source_kinds": ["accepted_ask_dj", "published_dj_moment", "retained_dj_contribution"],
            "processors": ["local_on_device", "ha_configured"],
            "processor_qualification_required": True,
            "provider_feedback": {"version": 1, "voice_options_path": "/api/djconnect/v1/speech/voice-options",
                                  "audio_configuration_error_status": 409,
                                  "languages": ["en", "nl", "de", "fr", "es"]},
            "voice_preference_context": {"scope": "owner_session_device", "storage_owner": "client",
                                         "runtime_mutable": True, "session_end": "discard"},
            "session_voice_selection": {"optional_voice_id": True, "authority": "configured_ha_assist_pipeline_provider"},
            "gender_preference": {"optional": True, "authority": "configured_ha_assist_pipeline_provider",
                                  "options_path": "/api/djconnect/v1/speech/voice-options"}, "voice_selection": "renderer_owned_or_exact_configured",
            "autoplay_scope": "per_device_new_publication_only", "manual_after_never": True,
            "ask_dj_request_version_field": "speech_contract_version",
            "voice_request_version_header": "X-DJConnect-Speech-Contract-Version",
            "legacy_private_audio_disposition": "client_protocol_upgrade_required",
            "history_mints_reference": False, "maximum_seconds": TTL,
            "maximum_text_characters": MAX_TEXT, "maximum_segments": MAX_SEGMENTS,
            "cache_policy": "private,no-store"}
    # Keep the published v1 envelope intact, but make those old local options
    # unambiguously version1-only. Consumers negotiating prepare2 must use its
    # descriptor; old top-level fields never grant a shared-settings override.
    result['legacy_voice_option_prepare_versions'] = [1]
    result['music_announcement'] = {
        'version': 1, 'moment_type': 'music_announcement',
        'text_at_every_presence': True, 'manual_after_text_only': True,
        'manual_text_only_target': 'local', 'automatic_start_window_seconds': 12,
        'manual_retention': 'original_committed_entry', 'new_publication_on_replay': False}
    result['prepare_contracts'] = {
        '1': {key: result[key] for key in (
            'processors', 'voice_preference_context', 'session_voice_selection',
            'gender_preference', 'voice_selection')},
        '2': {'processors': ['local_on_device', 'ha_configured'], 'settings_contract_version': 2,
              'settings_path': '/api/djconnect/v1/profile/settings',
              'caller_voice_override': False,
              'voice_preference_context': {'scope': 'profile_and_active_session',
                  'storage_owner': 'core', 'runtime_mutable': True,
                  'session_end': 'retain_profile_defaults'}},
        '3': {'processors': ['local_on_device', 'ha_configured'], 'settings_contract_version': 3,
              'settings_path': '/api/djconnect/v1/profile/settings',
              'caller_voice_override': False, 'intent': ['manual', 'automatic'],
              'targets': {'local': True, 'ha_speaker': True, 'both': True},
              'speaker_delivery': 'existing_operation_journal',
              'play_operation': 'session/speech/play',
              'play_path': '/api/djconnect/v1/transport/operation',
              'play_reference': 'live_moment_only',
              'retained_speaker_replay': {'available': True, 'version': 1,
                  'operation': 'session/speech/play', 'reference_kind': 'entry_id',
                  'entry_kinds': ['dj_moment'], 'intent': 'manual',
                  'voice_settings': 'active_session_else_confirmed_profile',
                  'automatic_history_playback': False},
              'automatic_speaker': 'core_publication_only',
              'speaker_media_maximum_seconds': 30,
              'speaker_media_maximum_reads': 4,
              'text_only_all_speech_forbidden': False,
              'text_only_automatic_speech_forbidden': True,
              'text_only_manual_local': ['music_announcement','live_impression','source_admitted_user_requested_moment']},
    }
    for version in ('2', '3'):
        result['prepare_contracts'][version]['local_on_device'] = {
            'target': 'local', 'voice_settings_scope': 'device_local',
            'ha_voice_availability_required': False, 'audio_state': 'renderer_pending',
            'effective_voice_authority': 'native_renderer',
            'original_publication_and_device_autoplay_required': True,
        }
    from .voice_preview import capability as voice_preview_capability
    result['voice_preview'] = voice_preview_capability()
    return result


def unavailable(reference, reason):
    return {"schema_version": 1, "reference": reference, "state": "unavailable",
            "reason": reason, "manual_allowed": False, "autoplay_eligible": False,
            "segments": [], "processors": [], "cache_policy": "private,no-store"}


def exact_segments(text):
    """Keep every accepted character; split only at natural whitespace boundaries."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        return None
    from .presentation_composer import SpeechSegment, SpeakerRole
    remaining, result = text, []
    while remaining and len(result) < MAX_SEGMENTS:
        end = min(MAX_SEGMENT, len(remaining))
        if len(remaining) > end:
            end = max(remaining.rfind("\n", 0, end) + 1,
                      remaining.rfind(" ", 0, end) + 1)
            if end <= 0:
                return None
        result.append(SpeechSegment(len(result) + 1, SpeakerRole.DJ, remaining[:end]).as_dict())
        remaining = remaining[end:]
    return result if not remaining else None


def projection(record, *, autoplay=False):
    return {"schema_version": 1, "reference": {"turn_id": record["turn_id"]},
            "source_kind": "accepted_ask_dj", "source_id": record["turn_id"],
            "session_id": record["session_id"] or None,
            "text_revision": record["text_revision"],
            "presentation_revision": record["text_revision"],
            "persona": record["persona"], "persona_revision": record["persona_revision"],
            "locale": record["locale"], "segments": exact_segments(record["text"]),
            "state": "available", "reason": None, "manual_allowed": True,
            "autoplay_eligible": autoplay, "processors": ["local_on_device", "ha_configured"],
            "processor_qualification_required": True,
            "expires_at": record["expires_at"], "cache_policy": "private,no-store",
            "attribution": deepcopy(record["attribution"])}


def _observation_speech_deadline(result, now, deadline):
    for name in ("queue_observation", "session_forecast"):
        stamp = (result.get(name) or {}).get("valid_until")
        if stamp:
            try:
                expiry = datetime.fromisoformat(stamp)
                if expiry.tzinfo is None:
                    return None
                deadline = min(deadline, now + expiry.timestamp() - time.time())
            except (TypeError, ValueError, OverflowError):
                return None
    return deadline


def _remember_speech_deadline(turn, frame, result, now, admissions):
    deadline = min([now + TTL, *(getattr(validate, "speech_deadline", now + TTL) for validate in admissions)])
    if turn.speech_deadline is not None:
        deadline = min(deadline, turn.speech_deadline)
    if frame.result_set:
        deadline = min(deadline, frame.result_set["deadline"])
    return _observation_speech_deadline(result, now, deadline)


def _existing_speech_reference(frame, turn_id, now):
    """Expire original references before returning a cached reply without renewing it."""
    for key, item in list(frame.speech_references.items()):
        if now >= item["deadline"]:
            old = frame.speech_references.pop(key)
            old["dispose"]()
    if turn_id in frame.speech_references:
        return projection(frame.speech_references[turn_id])
    return None


def _remember_source_qualification(admissions, result, deadline, now):
    """Revalidate original sources before admitting bounded attribution and expiry."""
    try:
        for validate in admissions:
            validate()
    except Exception:
        return None, "original_source_withdrawn"
    attribution = result.get("sources") or []
    if not isinstance(attribution, list) or len(attribution) > 8 or len(json.dumps(attribution)) > 4096:
        return None, "unsupported_attribution_extent"
    if deadline <= now:
        return None, "original_source_expired"
    return attribution, None


def remember(state, turn, result, *, turn_id, session_id, persona_revision,
             scope_revision, grant_revision, profile_source, playback_item_id="", deduplicated=False,
             autoplay_eligible=False, announcement_output='client_device'):
    """Attach an immutable reference only after the common semantic commit.

    Exactly eight bounded replies per already bounded frame, original five-minute
    deadlines. Deleting a frame deletes its references. A saved/deduplicated turn
    never opens a new grant or renews the first one.
    """
    if announcement_output == 'text_only':
        return unavailable({'turn_id': turn_id}, 'announcement_text_only')
    frame = turn.frame
    now = state.clock()
    existing = _existing_speech_reference(frame, turn_id, now)
    if existing is not None:
        return existing
    reference = {"turn_id": turn_id}
    text = result.get("text") or result.get("dj_text")
    if deduplicated:
        return unavailable(reference, "original_reference_not_retained")
    if exact_segments(text) is None:
        return unavailable(reference, "unsupported_text_extent")
    if len(frame.speech_references) >= MAX_REFERENCES:
        old = frame.speech_references.pop(next(iter(frame.speech_references)))
        old["dispose"]()
    revision = hashlib.sha256(text.encode()).hexdigest()[:24]
    admissions = tuple(turn.delivery_validators)
    deadline = _remember_speech_deadline(turn, frame, result, now, admissions)
    if deadline is None:
        return unavailable(reference, "original_source_expired")
    attribution, reason = _remember_source_qualification(admissions, result, deadline, now)
    if reason is not None:
        return unavailable(reference, reason)
    record = {"turn_id": turn_id, "text": text, "text_revision": revision,
              "persona": turn.style["persona"], "persona_revision": persona_revision,
              "locale": turn.style["language"], "session_id": session_id,
              "playback_item_id": playback_item_id, "generation": frame.generation,
              "scope_revision": scope_revision, "grant_revision": grant_revision,
              "profile_source": deepcopy(profile_source), "dependencies": deepcopy(turn.dependencies),
              "deadline": deadline, "admissions": admissions,
              "expires_at": datetime.fromtimestamp(time.time() + deadline - now, UTC).isoformat(),
              "attribution": deepcopy(attribution),
              "processor_basis": accepted_processing_basis(result)}
    record["disposals"] = []
    def expire():
        if frame.speech_references.get(turn_id) is record:
            frame.speech_references.pop(turn_id, None)
        handle = record.pop("expiry_handle", None)
        if handle is not None:
            handle.cancel()
        record["withdrawn"] = True
        record.pop("text", None)
        record["admissions"] = ()
        for dispose in record.pop("disposals", []):
            dispose()
    record["dispose"] = expire
    record["expiry_handle"] = asyncio.get_running_loop().call_later(deadline - now, expire)
    frame.speech_references[turn_id] = record
    return projection(record, autoplay=autoplay_eligible)


def _validate_dialogue_frame(history, scope, frame, record):
    """Revalidate the original RAM frame identity and its unrenewed lifetime."""
    if (record.get("withdrawn") or record["generation"] != frame.generation
        or not any(current is frame for current in history.dialogue.owners.get(scope, {}).values())
        or frame.speech_references.get(record["turn_id"]) is not record
        or history.dialogue.clock() >= record["deadline"]):
        raise PermissionError("speech_reference_withdrawn")


async def resolve_dialogue(hass, history, profile_id, reference, *, profile_source):
    """Read an accepted RAM reference without touching idle or source deadlines."""
    from .ask_dj.service import _live_reference
    from .session_conversation import async_history_grant_revision, history_grant_revision, query_service
    from .session_runtime import session_runtime_manager

    threads = history.dialogue.owners.get("profile:" + profile_id, {})
    found = next(((f, f.speech_references[reference["turn_id"]]) for f in threads.values()
                  if reference["turn_id"] in f.speech_references), None)
    if found is None:
        raise PermissionError("speech_reference_unavailable")
    frame, record = found
    manager = session_runtime_manager(hass)
    scope = "profile:" + profile_id
    # Read durable invalidation epochs before checking the synchronous final fence.
    await history.async_scope_revision(scope)
    await async_history_grant_revision(hass, profile_id)

    def guard():
        _validate_dialogue_frame(history, scope, frame, record)
        if (record["scope_revision"] != history.scope_revision(scope)
            or record["grant_revision"] != history_grant_revision(hass, profile_id)
            or record["profile_source"] != profile_source):
            raise PermissionError("speech_reference_withdrawn")
        for validate in record["admissions"]:
            validate()
        if record["session_id"]:
            active = manager.current_active(profile_id)
            if (active is None or active.session_id != record["session_id"]
                or (record["playback_item_id"] and active.broadcast.state.playback.item_id != record["playback_item_id"])):
                raise PermissionError("speech_reference_withdrawn")
    guard()
    for dependency in record["dependencies"]:
        if "moment_id" in dependency:
            await _live_reference(manager, profile_id, dependency)
        else:
            await query_service(hass, history).async_open_source_entry(profile_id, dependency["session_id"], dependency["entry_id"])
        guard()
    def on_withdraw(callback):
        if record.get("withdrawn"):
            callback()
            return lambda: None
        record["disposals"].append(callback)
        def remove():
            callbacks = record.get("disposals", [])
            if callback in callbacks:
                callbacks.remove(callback)
        return remove
    guard.on_withdraw = on_withdraw
    guard.processor_basis = record["processor_basis"]
    if record["session_id"]:
        from .dj_response import PrivateSpeechSource, invalidate_private_speech_sources, collect_private_speech_sources
        source = PrivateSpeechSource(hass, guard,
            expires_at=datetime.fromisoformat(record["expires_at"]).timestamp(), session_id=record["session_id"])
        original_watch = source.on_withdraw
        def watch(callback):
            remove = original_watch(callback)
            try:
                remove_record = guard.on_withdraw(source.withdraw)
            except BaseException:
                remove()
                raise
            def unsubscribe():
                remove()
                remove_record()
            return unsubscribe
        source.on_withdraw = watch
        source.processor_basis = guard.processor_basis
        active = manager.current_active(profile_id)
        active.broadcast.speech_cleanup = lambda: invalidate_private_speech_sources(hass, session_id=record["session_id"])
        active.broadcast.speech_refresh = lambda: collect_private_speech_sources(hass, session_id=record["session_id"])
        return projection(record), source
    return projection(record), guard


def _contribution_metadata_reason(locale, attribution):
    """Bound original locale and attribution before constructing any speech descriptor."""
    if not isinstance(locale, str) or locale not in {"en", "nl", "de", "fr", "es"}:
        return "original_locale_unknown"
    try:
        if not isinstance(attribution, list) or len(attribution) > 8 or len(json.dumps(attribution, allow_nan=False)) > 4096:
            return "unsupported_attribution_extent"
    except (TypeError, ValueError):
        return "unsupported_attribution_extent"
    return None


def _contribution_descriptor(reference, *, text, locale, persona, persona_revision,
                             expires_at, source_kind, attribution, autoplay=False, mood=None):
    reason = _contribution_metadata_reason(locale, attribution)
    if reason is not None:
        return unavailable(reference, reason)
    if persona not in ("home_dj", "radio_dj", "club_dj", "festival_dj"):
        persona = None
    if type(persona_revision) is not int or persona_revision < 0:
        persona_revision = None
    segments = exact_segments(text)
    if segments is None:
        return unavailable(reference, "unsupported_text_extent")
    revision = hashlib.sha256(text.encode()).hexdigest()[:24]
    mood = mood if mood in {"chill", "groove", "energy", "party"} else None
    presentation = hashlib.sha256(json.dumps([reference, revision, locale, persona,
        persona_revision, attribution, mood], sort_keys=True).encode()).hexdigest()[:24]
    return {"schema_version": 1, "reference": reference, "source_kind": source_kind,
            "source_id": reference.get("moment_id") or reference.get("entry_id"),
            "session_id": reference["session_id"], "text_revision": revision,
            "presentation_revision": presentation, "persona": persona,
            "persona_revision": persona_revision, "mood": mood, "locale": locale, "segments": segments,
            "style_basis": "accepted_contribution" if persona is not None else "legacy_unknown",
            "state": "available", "reason": None, "manual_allowed": True,
            "autoplay_eligible": autoplay, "processors": ["local_on_device", "ha_configured"],
            "processor_qualification_required": True,
            "expires_at": expires_at, "source_expires_at": expires_at,
            "attribution": attribution, "cache_policy": "private,no-store"}


def _published_moment(broadcast, moment_id):
    return next((moment for moment in broadcast.state.dj_moments
                 if moment.moment_id == moment_id), None)


def _native_admission(broadcast, moment_id, default=None):
    """Read the original published admission without manufacturing fallback rights."""
    return next((item for item in broadcast.native_delivery()['admissions']
                 if item['moment_id'] == moment_id), default)


def _presence_suppresses_speech(broadcast, opening, *, requested, announcement, confirmation):
    return not requested and not announcement and confirmation is None and (
        broadcast.state.selected_presence == 'music_only'
        or (opening is not None and opening.presence == 'music_only'))


def _published_source_qualified(admission, boundary, confirmation):
    """A confirmation needs current display; other sources may retain active Flow rights."""
    if confirmation is not None and (not admission or not admission['current_display_allowed']):
        return False
    return (boundary is not None and admission and admission['qualification'] == 'qualified'
            and (admission['current_display_allowed'] or admission['active_flow_display_allowed']))


def _published_moment_output(broadcast, opening, *, requested, requested_initiator,
                             announcement, confirmation, live, autoplay):
    """Apply the existing contribution-specific output policy before source lookup."""
    if requested and not requested_initiator:
        autoplay = False  # Recovery never starts a competing narrator.
    if _presence_suppresses_speech(broadcast, opening, requested=requested,
                                  announcement=announcement, confirmation=confirmation):
        autoplay = False
    output = getattr(broadcast, 'owner_speech_output', None)
    if callable(output) and output() == 'text_only':
        if not announcement and not live and not requested:
            return autoplay, 'announcement_text_only'
        autoplay = False
    return autoplay, None


def _published_moment_expiry(admission, boundary, *, confirmation, live, retained_expiry):
    """Keep original display/source/retained deadlines; a read never renews one."""
    if not _published_source_qualified(admission, boundary, confirmation):
        return None, 'original_source_unavailable'
    expiry = (admission['display_expires_at'] if confirmation is not None else
              admission["source_expires_at"] or boundary.utc_at(boundary.published_monotonic + 1800)
              if admission["active_flow_display_allowed"] else admission["display_expires_at"])
    if live and retained_expiry is not None:
        expiry = retained_expiry  # Only the original-row read supplies this authority.
    if not expiry or datetime.fromisoformat(expiry).timestamp() <= time.time():
        return None, 'original_source_expired'
    return expiry, None


def _published_moment_source_details(descriptor, moment, boundary, *, requested, live, announcement):
    """Preserve original processor rights and the initiator-only automatic window."""
    from .bulletin_runtime import private_bulletin, manual_ha_speech_admitted
    if descriptor["manual_allowed"] and private_bulletin(moment):
        descriptor["processors"] = (["local_on_device", "ha_configured"]
            if manual_ha_speech_admitted(moment) else ["local_on_device"])
        # The new source use is manual only, never a new autoplay opportunity.
        if manual_ha_speech_admitted(moment):
            descriptor["autoplay_eligible"] = False
    if requested:
        descriptor['automatic_start_expires_at'] = boundary.utc_at(boundary.published_monotonic+12)
        descriptor['autoplay_eligible'] = (descriptor['autoplay_eligible']
            and not moment.user_requested.automatic_cancelled and time.monotonic()<boundary.published_monotonic+12)
        descriptor['user_requested'] = True
        descriptor['moment_type'] = moment.moment_type.value
    if live:
        descriptor['moment_type'] = 'live_impression'
    if announcement:
        descriptor['moment_type'] = 'music_announcement'
    return descriptor


def moment_projection(broadcast, moment, *, autoplay=False, admission=None, retained_expiry=None, requested_initiator=False):
    """Pure owner speech admission over already published immutable content."""
    reference = {"session_id": broadcast.state.session_id, "moment_id": moment.moment_id}
    from .session_runtime import DJMomentType
    if moment.moment_type is DJMomentType.SILENCE:
        return unavailable(reference, "silence_has_no_speech")
    from .session_opening import opening_context
    opening = opening_context(moment)
    from .settings_confirmation import context as settings_context
    confirmation = settings_context(moment)
    from .track_start_announcement import accepted as announcement_accepted
    announcement = announcement_accepted(moment)
    from .live_impression import admitted as admitted_live
    live = admitted_live(moment)
    from .requested_moment_proof import admitted as requested_admitted
    requested = requested_admitted(moment, committed=True)
    autoplay, reason = _published_moment_output(
        broadcast, opening, requested=requested, requested_initiator=requested_initiator,
        announcement=announcement, confirmation=confirmation, live=live, autoplay=autoplay)
    if reason is not None:
        return unavailable(reference, reason)
    if admission is None:
        admission = _native_admission(broadcast, moment.moment_id)
    boundary = broadcast._moment_delivery_boundaries.get(moment.moment_id)
    if announcement and (not admission or not admission['current_display_allowed']):
        autoplay = False
    expiry, reason = _published_moment_expiry(admission, boundary, confirmation=confirmation,
                                            live=live, retained_expiry=retained_expiry)
    if reason is not None:
        return unavailable(reference, reason)
    descriptor = _contribution_descriptor(reference, text=moment.content, locale=broadcast.state.locale,
        persona=moment.presentation_intent.dj_persona.value, persona_revision=boundary.persona_revision,
        mood=moment.presentation_intent.source_session_mood,
        expires_at=expiry, source_kind="published_dj_moment",
        attribution=moment.as_dict().get('sources') or ([dict(moment.source_attribution)] if moment.source_attribution else []), autoplay=autoplay)
    return _published_moment_source_details(descriptor, moment, boundary,
                                            requested=requested, live=live, announcement=announcement)


async def _resolve_moment_archive(hass, history, profile_id, manager, active, moment):
    """Keep a RAM seal subordinate to the admitted original retained row."""
    from .track_start_announcement import retained as retained_announcement
    archive_guard = None
    archive_expiry = None
    from .live_impression import admitted as admitted_live
    live=admitted_live(moment)
    from .requested_moment_proof import proof as request_proof
    requested = request_proof(moment)
    retained_request = requested is not None and requested.retained
    if retained_announcement(moment) or retained_request or (live and requested is None):
        # A RAM seal must not outlive the actual retained row's current
        # deletion/retention/source rights. Reuse the existing archive owner.
        if history is None or manager._historical_projections is None:
            raise PermissionError('speech_reference_unavailable')
        row = await manager._historical_projections.async_entry_record(
            profile_id, active.session_id, '', moment_id=moment.moment_id)
        if row is None:
            raise PermissionError('speech_reference_unavailable')
        retained_descriptor, archive_guard = await resolve_retained(hass, history, profile_id,
            {'session_id':active.session_id, 'entry_id':row['entry_id']}, moment_only=True)
        if not retained_descriptor['manual_allowed']:
            raise PermissionError('speech_reference_unavailable')
        archive_expiry = datetime.fromisoformat(retained_descriptor['expires_at']).timestamp()
    return archive_guard, archive_expiry, live


def _spotify_moment_source(source, moment):
    """Existing Spotify/observed/transition/announcement owners share literal processing."""
    return ((source is not None and source.provider == "Spotify")
            or moment.observed_playback is not None or moment.genre_transition is not None
            or getattr(moment, 'track_announcement', None) is not None)


def _moment_processor_basis(moment):
    source = moment.source_fact
    from .public_artist_narration import ResearchMomentAcceptance
    from .live_impression import admitted as admitted_live
    from .settings_confirmation import context as settings_context
    from .bulletin_runtime import admitted as bulletin_admitted
    return ("public_news_bulletin_v1" if bulletin_admitted(moment)
        else "runtime_accepted_settings_v1" if settings_context(moment) is not None
        else "qualified_dialogue_v1" if type(moment.narration_acceptance) is ResearchMomentAcceptance or admitted_live(moment)
        else "spotify_owner_local_read_v1" if _spotify_moment_source(source, moment)
        else "cc0_normalized_fields_v1" if source is not None else "runtime_authored_direction_v1")


async def resolve_moment(hass, profile_id, reference, *, history=None):
    from .session_runtime import session_runtime_manager
    from .dj_response import PrivateSpeechSource, invalidate_private_speech_sources, collect_private_speech_sources
    manager = session_runtime_manager(hass)
    active = manager.current_active(profile_id)
    if active is None or active.session_id != reference["session_id"]:
        raise PermissionError("speech_reference_unavailable")
    broadcast = active.broadcast
    if getattr(broadcast, 'content_pending', False):
        raise PermissionError('content_delete_outcome_unknown')
    moment = _published_moment(broadcast, reference["moment_id"])
    if moment is None:
        raise PermissionError("speech_reference_unavailable")
    archive_guard, archive_expiry, live = await _resolve_moment_archive(
        hass, history, profile_id, manager, active, moment)
    retained_until=datetime.fromtimestamp(archive_expiry,UTC).isoformat() if live and archive_expiry is not None else None
    descriptor = moment_projection(broadcast, moment,retained_expiry=retained_until)
    if not descriptor["manual_allowed"]:
        raise PermissionError("speech_reference_unavailable")
    descriptor["expires_at"] = datetime.fromtimestamp(min(time.time()+TTL,
        datetime.fromisoformat(descriptor["source_expires_at"]).timestamp(),
        archive_expiry if archive_expiry is not None else float('inf')), UTC).isoformat()
    def validate():
        if archive_guard is not None:
            archive_guard()
        current = manager.current_active(profile_id)
        if (current is None or current.broadcast is not broadcast
                or moment.moment_id in broadcast.content_pending_moment_ids
                or not moment_projection(broadcast, moment,retained_expiry=retained_until)["manual_allowed"]):
            raise PermissionError("speech_reference_withdrawn")
    guard = PrivateSpeechSource(hass, validate,
        expires_at=datetime.fromisoformat(descriptor["expires_at"]).timestamp(), session_id=active.session_id,
        moment_id=moment.moment_id)
    from .bulletin_runtime import private_bulletin, manual_ha_speech_admitted
    if private_bulletin(moment):
        guard.private_bulletin_ha_use = lambda: manual_ha_speech_admitted(moment)
    guard.processor_basis = _moment_processor_basis(moment)
    broadcast.speech_cleanup = lambda: invalidate_private_speech_sources(hass, session_id=active.session_id)
    broadcast.speech_refresh = lambda: collect_private_speech_sources(hass, session_id=active.session_id)
    guard()
    return descriptor, guard


def _retained_speech_style(entry):
    """Use only the admitted stored owner's original style and attribution fields."""
    if entry["kind"] == "dj_moment" and entry.get("archive_basis") in {
            "cc0_normalized_fields_v1", "runtime_authored_direction_v1", "runtime_accepted_settings_v1", "owner_metadata_narration_v1", "public_artist_narration_v1", "public_live_impression_v1"}:
        style = {"language": entry.get("locale"), "persona": entry.get("persona"),
                 "mood": entry.get("mood"),
                 "persona_revision": entry.get("persona_revision")}
        attribution = entry.get('sources') or ([entry["source_attribution"]] if entry.get("source_attribution") else [])
    elif entry["kind"] == "conversation_dj" and entry.get("role") == "assistant":
        style = entry.get("effective_style") or {}
        if not isinstance(style, dict):
            style = {}
        attribution = entry.get("sources") or []
    else:
        return None
    return style, attribution


def retained_projection(entry):
    """Pure owner-entry speech state; no resources or new read-time deadline."""
    reference = {"session_id": entry["session_id"], "entry_id": entry["entry_id"]}
    original = _retained_speech_style(entry)
    if original is None:
        return unavailable(reference, "original_source_unqualified")
    style, attribution = original
    if entry.get("archive_basis") == "public_live_impression_v1":
        from .live_impression import checked
        if checked(entry.get("live_impression")) is None:
            return unavailable(reference,"original_source_unqualified")
    descriptor = _contribution_descriptor(reference, text=entry.get("text"), locale=style.get("language"),
        persona=style.get("persona"), persona_revision=style.get("persona_revision"),
        mood=style.get("mood"),
        expires_at=entry["retained_until"], source_kind="retained_dj_contribution", attribution=attribution)
    from .requested_moment_proof import retained_provenance
    if retained_provenance(entry):
        descriptor['user_requested']=True
        descriptor['moment_type']=entry.get('moment_type')
    if entry.get('archive_basis') == 'public_live_impression_v1':
        descriptor['moment_type']='live_impression'
    if (entry.get('moment_type') == 'music_announcement'
            and entry.get('archive_basis') == 'owner_metadata_narration_v1'):
        descriptor['moment_type'] = 'music_announcement'
    return descriptor


async def resolve_retained(hass, history, profile_id, reference, *, moment_only=False):
    from .session_conversation import (query_service, async_history_grant_revision, history_grant_revision)
    from .persistence import persistence_service
    from .dj_response import PrivateSpeechSource, invalidate_private_speech_sources
    domain = hass.data.setdefault("djconnect", {})
    epoch = domain.setdefault("tts_audio_authority_revision", 0)
    service = persistence_service(hass)
    service.session_speech_invalidator = lambda: invalidate_private_speech_sources(hass)
    retention_fence = (getattr(service, 'history_retention_epoch', 0),
                       getattr(service, 'history_retention_writes', 0))
    grant = await async_history_grant_revision(hass, profile_id)
    revision = await history.async_scope_revision("profile:" + profile_id)
    opened = await query_service(hass, history).async_open_source_entry(profile_id, reference["session_id"], reference["entry_id"])
    entry = opened["entry"]
    if entry["kind"] not in {"dj_moment", "conversation_dj"} or (moment_only and entry["kind"] != "dj_moment"):
        raise PermissionError("speech_reference_unqualified")
    descriptor = retained_projection(entry)
    basis = (entry.get("archive_basis") if entry["kind"] == "dj_moment"
             else entry.get("speech_processing_basis") or "retained_owner_local_read_v1")
    if basis == 'owner_metadata_narration_v1':
        basis = 'spotify_owner_local_read_v1'
    elif basis in {'public_artist_narration_v1','public_live_impression_v1'}:
        basis = 'qualified_dialogue_v1'
    expires = min(time.time() + TTL, datetime.fromisoformat(entry["retained_until"]).timestamp())
    if descriptor["manual_allowed"]:
        descriptor["expires_at"] = datetime.fromtimestamp(expires, UTC).isoformat()
    def validate():
        if (retention_fence[1] or retention_fence != (
                getattr(service, 'history_retention_epoch', 0), getattr(service, 'history_retention_writes', 0))
                or history_grant_revision(hass, profile_id) != grant
                or history.scope_revision("profile:" + profile_id) != revision):
            raise PermissionError("speech_reference_withdrawn")
    guard = PrivateSpeechSource(hass, validate, expires_at=expires,
                                session_id=reference["session_id"], entry_id=reference["entry_id"])
    guard.epoch = epoch  # Also fence a destructive transaction during entry reads.
    guard.processor_basis = basis
    guard()
    return descriptor, guard


def _valid_prepare_voice(data):
    """Validate the optional legacy HA voice identifier without resolving a provider."""
    if "voice_id" not in data:
        return True
    return (data.get("processor") == "ha_configured"
            and isinstance(data["voice_id"], str) and 0 < len(data["voice_id"]) <= 128
            and data["voice_id"] == data["voice_id"].strip() and data["voice_id"].isprintable())


def _valid_prepare_reference(reference):
    return (isinstance(reference, dict)
            and set(reference) in ({"turn_id"}, {"session_id", "moment_id"}, {"session_id", "entry_id"})
            and all(isinstance(value, str) and 0 < len(value) <= 128 and value == value.strip()
                    for value in reference.values()))


def _valid_prepare_shape(data, fields, shared_settings):
    return (isinstance(data, dict) and fields <= set(data)
            and not (set(data) - fields - {"voice_id"})
            and not (shared_settings and 'voice_id' in data))


def _valid_prepare_options(data, *, target_aware, shared_settings):
    return (type(data["contract_version"]) is int and data["contract_version"] in (1, 2, 3)
            and (not target_aware or (data['intent'] in ('manual', 'automatic')
                                     and data['target'] in ('local', 'ha_speaker', 'both')))
            and data["processor"] in ("local_on_device", "ha_configured")
            and (shared_settings or data["voice_preference"] in ("default", "male", "female")))


def _prepare_contract(data):
    """Validate wire shape before authentication or any owner/provider lookup."""
    version = data.get('contract_version') if type(data) is dict else None
    target_aware = type(version) is int and version == 3
    shared_settings = type(version) is int and version in (2, 3)
    fields = {"contract_version", "device_id", "client_type", "reference", "processor"}
    if target_aware:
        fields.update({'intent', 'target'})
    if not shared_settings:
        fields.add('voice_preference')
    if (not _valid_prepare_shape(data, fields, shared_settings)
        or not _valid_prepare_voice(data)
        or not _valid_prepare_options(data, target_aware=target_aware, shared_settings=shared_settings)
        or not _valid_prepare_reference(data["reference"])):
        return None
    return target_aware, shared_settings


@dataclass
class _PrepareSettings:
    """One settings read and its immutable fence carried through preparation."""
    data: dict
    selected: object = None
    token: object = None
    migration: dict | None = None
    snapshot: dict | None = None
    response: object = None


def _manual_local_prepare(data, target_aware):
    return target_aware and data['intent'] == 'manual' and data['target'] == 'local'


def _prepare_target_reason(selected, data, *, target_aware, speaker_operation):
    manual_text_only = _manual_local_prepare(data, target_aware)
    if selected.announcement_output == 'text_only' and not manual_text_only:
        return 'announcement_text_only'
    if target_aware:
        allowed = ({'client_device': {'local'}, 'both': {'local', 'ha_speaker', 'both'},
                    'ha_speaker': {'ha_speaker'}} if data['intent'] == 'automatic' else
                   {'text_only': {'local'}, 'client_device': {'local'}, 'both': {'local', 'ha_speaker', 'both'},
                    'ha_speaker': {'local', 'ha_speaker', 'both'}})
        if data['target'] not in allowed[selected.announcement_output]:
            return ('automatic_target_not_allowed' if data['intent'] == 'automatic'
                    else 'speech_target_not_allowed')
        if data['target'] != 'local' and not speaker_operation:
            # Speaker delivery requires its qualified grant, never an anonymous URL.
            return 'use_speech_play_operation'
    return None


def _select_prepare_settings(result, hass, runtime, data, *, shared_settings, target_aware,
                             speaker_operation):
    """Select from the admitted snapshot; this stage performs no new settings read."""
    from .profile_settings import VoicePolicy
    from .domain.profile.dj_settings import DJSettings
    from .speech_processor import voice_options

    snapshot = result.snapshot
    if not shared_settings:
        return result
    if snapshot['session'] and snapshot['session'].get('selection_required'):
        result.response = {'success': True, 'session_speech': unavailable(
            data['reference'], 'settings_migration_choice_required')}, 200
        return result
    selected = DJSettings.from_dict(snapshot['session']['settings'] if snapshot['session'] else snapshot['defaults'])
    result.selected = selected
    reason = _prepare_target_reason(selected, data, target_aware=target_aware,
                                    speaker_operation=speaker_operation)
    if reason is not None:
        result.response = {'success': True, 'session_speech': unavailable(data['reference'], reason)}, 200
        return result
    if data['processor'] == 'ha_configured':
        policy = VoicePolicy.from_options(voice_options(hass, runtime.config))
        availability = policy.selection_state(selected)
        if not availability['available']:
            result.response = {'success': True, 'session_speech': unavailable(
                data['reference'], availability['reason'])}, 200
            return result
        result.data = {**data, 'voice_preference': selected.gender.value}
        if selected.voice.kind == 'provider_voice':
            result.data['voice_id'] = selected.voice.voice_id
    return result


async def _resolve_prepare_settings(hass, runtime, identity, headers, context, manager, data,
                                    *, shared_settings, target_aware, speaker_operation):
    from .settings_migration import assessment
    from .profile_context import profile_storage

    result = _PrepareSettings(data)
    if not (shared_settings or manager._settings_repository is not None):
        return result
    snapshot = await manager.async_read_dj_settings(owner_profile_id=context.profile_id,
        authorize=lambda: _speech_settings_authority(hass, runtime, identity, headers, context))
    result.snapshot = snapshot
    result.token = manager.dj_settings_fence_token(context.profile_id)
    result.migration = {key: snapshot[key] for key in ('activated', 'accepted_contract_version')}
    if assessment(hass, profile_storage(hass).household, context.profile,
                  **result.migration)['requires_review']:
        result.response = {'success': True, 'session_speech': unavailable(
            data['reference'], 'settings_migration_choice_required')}, 200
        return result
    if not target_aware and (snapshot['activated'] or (
            snapshot['session'] is not None and manager.current_active(context.profile_id).settings_contract_version >= 2)):
        result.response = {'success': False, 'error': 'settings_contract_upgrade_required',
                           'settings_contract_version': 3}, 426
        return result
    return _select_prepare_settings(result, hass, runtime, data, shared_settings=shared_settings,
        target_aware=target_aware, speaker_operation=speaker_operation)


def _requested_automatic_admission(manager, profile_id, identity, reference):
    """Bind automatic playback to the initiating device and original twelve-second window."""
    from .requested_moment_proof import admitted as requested_admitted
    active = manager.current_active(profile_id)
    original = _published_moment(active.broadcast, reference.get('moment_id')) if active else None
    boundary = active.broadcast._moment_delivery_boundaries.get(reference.get('moment_id')) if active else None
    device = hashlib.sha256(identity.get('device_id','').encode()).hexdigest()
    def requested_auto_guard():
        if (original is None or boundary is None or not requested_admitted(original,committed=True)
                or original.user_requested.device != device or original.user_requested.automatic_cancelled
                or not boundary.published_monotonic <= time.monotonic() < boundary.published_monotonic+12):
            raise PermissionError('automatic_requested_moment_unavailable')
    requested_auto_guard()
    return requested_auto_guard


def _announcement_start_deadline(manager, profile_id, reference):
    """Automatic announcements require the actual current original publication."""
    active = manager.current_active(profile_id)
    if 'moment_id' not in reference or active is None or active.session_id != reference.get('session_id'):
        raise PermissionError('automatic_announcement_requires_live_publication')
    admitted = _native_admission(active.broadcast, reference['moment_id'], {})
    if not admitted.get('current_display_allowed'):
        raise PermissionError('automatic_announcement_start_window_elapsed')
    return datetime.fromisoformat(admitted['display_expires_at']).timestamp()


def _recheck_announcement_window(manager, profile_id, reference, automatic_announcement_deadline):
    if automatic_announcement_deadline is not None:
        live = manager.current_active(profile_id)
        admission = _native_admission(live.broadcast, reference['moment_id'], {}) if live is not None else {}
        if (time.time() >= automatic_announcement_deadline
                or not admission.get('current_display_allowed')):
            raise PermissionError('automatic_announcement_start_window_elapsed')


def _recheck_prepare_settings(hass, manager, profile_id, settings):
    from .settings_migration import assessment
    from .profile_context import profile_storage

    settings_token, migration_acceptance = settings.token, settings.migration
    if settings_token is not None and manager.dj_settings_fence_token(profile_id) != settings_token:
        raise PermissionError('speech_settings_changed')
    if migration_acceptance is not None and assessment(
            hass, profile_storage(hass).household,
            profile_storage(hass).household.profiles[profile_id],
            **migration_acceptance)['requires_review']:
        raise PermissionError('settings_migration_choice_required')


def _prepare_admission(hass, runtime, identity, headers, context, manager, data,
                       descriptor, source_guard, settings, private_ha_use, *, target_aware):
    """Bind the source, device, time, profile and settings fences before synthesis."""
    from .api_handlers import _conversation_profile_fence

    reference = data['reference']
    requested_auto_guard = None
    if target_aware and data['intent']=='automatic' and descriptor.get('user_requested') is True:
        requested_auto_guard = _requested_automatic_admission(
            manager, context.profile_id, identity, reference)
    grant_deadline = None
    automatic_announcement_deadline = None
    if (target_aware and data['intent'] == 'automatic'
            and descriptor.get('moment_type') == 'music_announcement'):
        automatic_announcement_deadline = _announcement_start_deadline(
            manager, context.profile_id, reference)
    if descriptor['manual_allowed']:
        try:
            grant_deadline = datetime.fromisoformat(descriptor['expires_at']).timestamp()
        except (KeyError, TypeError, ValueError):
            raise PermissionError('speech_reference_unavailable') from None
    def guard():
        if requested_auto_guard is not None:
            requested_auto_guard()
        _conversation_profile_fence(hass, runtime, identity, headers, context)
        if grant_deadline is not None and time.time() >= grant_deadline:
            raise PermissionError('speech_reference_expired')
        _recheck_announcement_window(manager, context.profile_id, reference, automatic_announcement_deadline)
        _recheck_prepare_settings(hass, manager, context.profile_id, settings)
        source_guard()
        if private_ha_use is not None and not private_ha_use():
            raise PermissionError('bulletin_manual_speech_use_withdrawn')
    guard.on_withdraw = source_guard.on_withdraw
    guard.processor_basis = ('private_headline_manual_ha_v1'
                             if private_ha_use is not None else source_guard.processor_basis)
    guard()
    return guard


async def _prepare_processor(hass, runtime, context, data, descriptor, guard, selected, *, shared_settings):
    """Prepare only a processor admitted for the accepted original contribution."""
    from .speech_processor import voice_options

    if data["processor"] == "ha_configured":
        if "ha_configured" not in descriptor.get("processors", ()):
            return unavailable(data["reference"], "source_processor_not_qualified")
        descriptor = await prepare_ha(hass, runtime, context.profile_id, data,
                                      descriptor, guard, expected_provider=(
                                          selected.voice.provider_id if selected is not None
                                          and selected.voice.kind == 'provider_voice' else None))
        guard()
    else:
        if (guard.processor_basis not in LITERAL_PROCESSING_BASES
                or 'local_on_device' not in descriptor.get('processors', ())):
            descriptor = unavailable(data['reference'], 'source_processor_not_qualified')
        elif shared_settings:
            # Exact text admission only. The native renderer qualifies its
            # actual OS voice; saved HA voice availability is independent.
            descriptor.update(processor='local_on_device', audio_state='renderer_pending',
                              effective_voice=None, autoplay_eligible=False)
        elif (data['voice_preference'] != 'default' and data['voice_preference'] not in
                voice_options(hass, runtime.config)['gender_selection']['values']):
            descriptor = unavailable(data["reference"], "voice_gender_unavailable")
        else:
            descriptor.update(audio_state="renderer_pending", effective_voice=None,
                              voice_preference=data["voice_preference"], autoplay_eligible=False)
    return descriptor


def _text_only_source_allowed(data, descriptor, target_aware):
    """Only announcement speech or explicitly manual original Moments retain this use."""
    return (descriptor.get('moment_type') == 'music_announcement'
            or (_manual_local_prepare(data, target_aware)
                and (descriptor.get('user_requested') is True
                     or descriptor.get('moment_type') == 'live_impression')))


def _prepare_source_policy(data, descriptor, source_guard, selected, *, target_aware):
    """Preserve the original contribution's processor and manual text-only rights."""
    private_ha_use = (getattr(source_guard, 'private_bulletin_ha_use', None)
                      if data['processor'] == 'ha_configured' else None)
    if private_ha_use is not None and not (
            _manual_local_prepare(data, target_aware) and private_ha_use()):
        return private_ha_use, 'source_processor_not_qualified'
    if (selected is not None and selected.announcement_output == 'text_only'
            and not _text_only_source_allowed(data, descriptor, target_aware)):
        return private_ha_use, 'announcement_text_only'
    return private_ha_use, None


def _valid_speech_read(data, fields):
    return (isinstance(data, dict) and set(data) == fields
            and type(data["contract_version"]) is int and data["contract_version"] == 1)


async def _speech_private_context(hass, data, headers, *, source):
    """All speech reads authenticate the same original device/profile owner."""
    from .api_handlers import _session_profile_context

    if not str(headers.get("Authorization", "")).startswith("Bearer ") or data["client_type"] == "windows":
        return None, None, None, {"success": False, "error": "unauthorized"}, 401
    identity = {key: data[key] for key in ("device_id", "client_type")}
    runtime, context, error, status = await _session_profile_context(
        hass, identity, headers=headers, user_id=None, source=source)
    return identity, runtime, context, error, status


async def _prepare_owned_contribution(hass, runtime, identity, headers, context, manager, data,
                                      *, shared_settings, target_aware, speaker_operation):
    """Resolve, fence and prepare one existing owner's accepted contribution."""
    from .ask_dj.dialogue import source_scope
    from .http import _history_manager
    from .profile_privacy import resolve_profile_privacy_policy
    from .transport_delivery import register_delivery_admission

    settings = await _resolve_prepare_settings(hass, runtime, identity, headers, context,
        manager, data, shared_settings=shared_settings, target_aware=target_aware,
        speaker_operation=speaker_operation)
    if settings.response is not None:
        return settings.response
    selected, settings_token = settings.selected, settings.token
    snapshot, data = settings.snapshot, settings.data
    if not context.privacy_policy.allow_personal_read or not resolve_profile_privacy_policy(context.profile, {}).allow_personal_read:
        raise PermissionError("speech_not_allowed")
    history = _history_manager(hass, runtime)
    reference = data["reference"]
    if "moment_id" in reference:
        descriptor, source_guard = await resolve_moment(hass, context.profile_id, reference, history=history)
    elif "entry_id" in reference:
        descriptor, source_guard = await resolve_retained(hass, history, context.profile_id,
            reference, moment_only=speaker_operation)
    else:
        descriptor, source_guard = await resolve_dialogue(hass, history,
            context.profile_id, reference, profile_source=source_scope(context.profile))
    private_ha_use, reason = _prepare_source_policy(data, descriptor, source_guard, selected,
                                                    target_aware=target_aware)
    if reason is not None:
        return {'success': True, 'session_speech': unavailable(reference, reason)}, 200
    guard = _prepare_admission(hass, runtime, identity, headers, context, manager, data,
        descriptor, source_guard, settings, private_ha_use, target_aware=target_aware)
    register_delivery_admission(guard)
    if not descriptor["manual_allowed"]:
        return {"success": True, "session_speech": descriptor}, 200
    from .persona_reactions import withdraw_for_interaction
    withdraw_for_interaction(hass, context.profile_id)
    if shared_settings:
        descriptor = {**descriptor, 'settings_contract_version': snapshot['contract_version'],
                      'settings_revision': settings_token}
    descriptor = await _prepare_processor(hass, runtime, context, data, descriptor, guard,
                                          selected, shared_settings=shared_settings)
    guard()
    return {"success": True, "session_speech": descriptor}, 200


async def async_handle_prepare(hass, data, *, headers=None, _speaker_operation=False):
    from .session_conversation import SessionConversationError
    from .ask_dj.dialogue import DialogueError
    from .session_history_projection import HistoryQueryError

    contract = _prepare_contract(data)
    if contract is None:
        return {"success": False, "error": "invalid_request"}, 400
    target_aware, shared_settings = contract
    headers = headers or {}
    identity, runtime, context, error, status = await _speech_private_context(
        hass, data, headers, source="session_speech_prepare")
    if error is not None:
        return error, status
    try:
        from .session_runtime import session_runtime_manager
        from .persistence.dj_settings import SettingsCommitError
        manager = session_runtime_manager(hass)
        return await _prepare_owned_contribution(hass, runtime, identity, headers, context, manager,
            data, shared_settings=shared_settings, target_aware=target_aware,
            speaker_operation=_speaker_operation)
    except SessionConversationError as exc:
        return {"success": False, "error": exc.code}, exc.status
    except DialogueError:
        return {"success": False, "error": "speech_reference_unavailable"}, 404
    except HistoryQueryError:
        return {"success": False, "error": "speech_context_changed"}, 409
    except SettingsCommitError:
        return {'success': False, 'error': 'settings_unavailable'}, 503
    except PermissionError as exc:
        status = 403 if str(exc) == "speech_not_allowed" else 404
        return {"success": False, "error": "speech_reference_unavailable"}, status


def _speech_settings_authority(hass, runtime, identity, headers, context):
    from .api_handlers import _conversation_profile_fence
    try:
        _conversation_profile_fence(hass, runtime, identity, headers, context)
        return True
    except Exception:
        return False


def _synthesis_failure_feedback(hass, runtime, owner, voice, entity, admission, exc):
    """Only a still-admitted contribution may record/explain synthesis failure."""
    from .speech_processor import ProcessorUnavailable
    from .speech_feedback import record

    codes = {"processor_not_qualified", "tts_provider_unavailable", "no_matching_locale", "no_matching_voice", "voice_gender_unavailable",
             "unsupported_audio_extent", "unsupported_audio_type", "speech_retry_backoff", "speech_capacity"}
    reason = str(exc) if isinstance(exc, (ProcessorUnavailable, ValueError)) and str(exc) in codes else (
        "speech_preparation_timeout" if isinstance(exc, TimeoutError) else "speech_preparation_failed")
    admission()
    if voice is not None and reason in {"speech_preparation_failed", "speech_preparation_timeout", "unsupported_audio_type", "unsupported_audio_extent"}:
        record(hass, runtime, owner, voice, provider=entity, reason=reason)
    return reason


async def prepare_ha(hass, runtime, owner, data, descriptor, admission, *, expected_provider=None):
    from .dj_response import prepare_private_tts_audio, get_private_tts_audio
    from .speech_processor import configured_processor, synthesize, mood_prosody, ProcessorUnavailable
    from .speech_feedback import SpeechProviderChanged, notification, record

    def failed(reason):
        result = unavailable(data["reference"], reason)
        notice = notification(reason, descriptor["locale"], retry_after=60 if reason in {
            "speech_retry_backoff", "speech_preparation_failed", "speech_preparation_timeout",
            "unsupported_audio_type", "unsupported_audio_extent"} else 0)
        if notice:
            result["notification"] = notice
        return result

    # Exact accepted-text synthesis is owner-authorized through the configured
    # HA provider, independently of a provider's locality. This admits no new
    # model context, arbitrary text or source/history rights.
    if admission.processor_basis not in LITERAL_PROCESSING_BASES:
        return unavailable(data["reference"], "source_processor_not_qualified")
    def resolve_processor():
        if "voice_id" in data:
            result = configured_processor(hass, runtime.config, descriptor["locale"],
                                          data["voice_preference"], selected_voice=data["voice_id"])
        else:
            result = configured_processor(hass, runtime.config, descriptor["locale"], data["voice_preference"])
        if expected_provider is not None and result[1]['engine'] != expected_provider:
            raise ProcessorUnavailable('no_matching_voice')
        return result

    entity = voice = None
    try:
        entity, voice = resolve_processor()
        expression = mood_prosody(entity, descriptor.get("mood"))
        key = (owner, descriptor["source_id"], descriptor["text_revision"],
               descriptor["presentation_revision"], voice["engine"], voice["voice_id"], voice["locale"], id(entity),
               voice.get("provider_version"), voice.get("voice_version"),
               voice.get("configuration_revision"), json.dumps(expression, sort_keys=True))
        if descriptor.get('settings_contract_version') in (2, 3):
            key += (json.dumps(descriptor['settings_revision'], separators=(',', ':')),)
        def qualified_admission():
            admission()
            try:
                current_entity, current_voice = resolve_processor()
            except ProcessorUnavailable as exc:
                raise SpeechProviderChanged(str(exc), descriptor["locale"]) from None
            if (current_entity is not entity or current_voice != voice
                    or mood_prosody(current_entity, descriptor.get("mood")) != expression):
                raise SpeechProviderChanged("speech_configuration_changed", descriptor["locale"])
        qualified_admission.on_withdraw = admission.on_withdraw
        qualified_admission.on_synthesized = lambda: record(hass, runtime, owner, voice, provider=entity)
        token = await prepare_private_tts_audio(hass, owner_profile_id=owner, cache_key=key,
            expires_at=datetime.fromisoformat(descriptor["expires_at"]).timestamp(), admission=qualified_admission,
            synthesize=lambda: synthesize(entity,
                {**voice, "mood_prosody": expression} if expression["state"] == "applied" else voice,
                "".join(segment["text"] for segment in descriptor["segments"])))
        asset = get_private_tts_audio(hass, token, owner)
        return {**descriptor, "expires_at": datetime.fromtimestamp(asset.expires_at, UTC).isoformat(),
                "audio_state": "ready", "effective_voice": voice, "mood_prosody": expression, "autoplay_eligible": False,
                "audio_reference": {"asset_id": token, "path": "/api/djconnect/v1/speech/audio", "method": "POST"}}
    except PermissionError:
        # Source/owner withdrawal stays opaque. A still-authorized contribution
        # can explain a provider change, even if a joined job masked its reason.
        admission()
        if entity is not None:
            try:
                qualified_admission()
            except SpeechProviderChanged as exc:
                return failed(str(exc))
        raise
    except Exception as exc:
        reason = _synthesis_failure_feedback(hass, runtime, owner, voice, entity, admission, exc)
        return failed(reason)


def _valid_speech_audio(data, fields):
    return (_valid_speech_read(data, fields) and isinstance(data["asset_id"], str)
            and 0 < len(data["asset_id"]) <= 64)


async def async_handle_audio(hass, data, *, headers=None):
    """No bearer-free speech audio URL. Exact source admission on every byte read."""
    from .api_handlers import _conversation_profile_fence
    from .dj_response import get_private_tts_audio
    from .session_conversation import SessionConversationError
    from .speech_feedback import SpeechProviderChanged, notification
    fields = {"contract_version", "device_id", "client_type", "asset_id"}
    if not _valid_speech_audio(data, fields):
        return None, 400
    headers = headers or {}
    identity, runtime, context, error, status = await _speech_private_context(
        hass, data, headers, source="session_speech_audio")
    if error is not None:
        return None, status
    try:
        _conversation_profile_fence(hass, runtime, identity, headers, context)
        item = get_private_tts_audio(hass, data["asset_id"], context.profile_id)
        if item.delivery_device_id is not None and item.delivery_device_id != identity['device_id']:
            raise PermissionError('speech_device_mismatch')
        return item, 200
    except SessionConversationError as exc:
        return None, exc.status
    except SpeechProviderChanged as exc:
        return {"success": False, "error": "speech_configuration_changed",
                "notification": notification(str(exc), exc.locale)}, 409
    except PermissionError:
        return None, 404


async def async_handle_voice_options(hass, data, *, headers=None):
    """Private owner readback for the optional provider-supported client setting."""
    from .api_handlers import _conversation_profile_fence
    from .speech_processor import voice_options
    from .session_conversation import SessionConversationError
    from .speech_feedback import status as provider_status
    fields = {"contract_version", "device_id", "client_type"}
    if not _valid_speech_read(data, fields):
        return {"success": False, "error": "invalid_request"}, 400
    headers = headers or {}
    identity, runtime, context, error, status = await _speech_private_context(
        hass, data, headers, source="session_speech_voice_options")
    if error is not None:
        return error, status
    try:
        result = voice_options(hass, runtime.config)
        result["provider_status"] = provider_status(hass, runtime, context.profile_id, result,
            getattr(hass.config, "language", "en"))
        result["notification"] = result["provider_status"]["notification"]
        result["revision"] = hashlib.sha256(json.dumps(
            {key: value for key, value in result.items() if key != "revision"}, sort_keys=True).encode()).hexdigest()[:24]
        _conversation_profile_fence(hass, runtime, identity, headers, context)
        return {"success": True, "speech_voice_options": result}, 200
    except SessionConversationError as exc:
        return {"success": False, "error": exc.code}, exc.status
