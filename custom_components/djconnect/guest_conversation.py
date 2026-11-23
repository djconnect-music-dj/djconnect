"""Sealed guest actor for the one Ask DJ service, never a personal Profile grant."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import re
import time
from urllib.parse import urlsplit

from .display_admission import DisplayAdmissionError
from .session_conversation import SessionConversationError

current_guest = ContextVar('djconnect_guest_actor', default=None)

PUBLIC_INTENTS = frozenset({
    'guest_request_status', 'guest_screen_focus', 'ask_music_info', 'current_track_reference', 'current_artist_information',
    'current_release_information', 'album_tracks_information', 'current_track_versions',
    'track_versions_search', 'track_artist_album_lookup', 'track_title_choices',
    'artist_item_list', 'artist_concerts', 'similar_artists',
    'conversation_recall', 'conversation_stop', 'conversational_followup', 'clarification_needed',
})
PUBLIC_COMMANDS = frozenset({'search_tracks', 'search_albums', 'search_media', 'album_tracks',
                            'track_metadata', 'artist_albums', 'related_artists',
                            'artist_collections', 'artist_profile'})


def actor_for(hass):
    actor = current_guest.get()
    return actor if actor is not None and actor.hass is hass else None


class GuestServiceResult(dict):
    """RAM-only original Core delivery fence, never part of JSON or storage."""
    def __init__(self, body, validate_now):
        super().__init__(body)
        self.validate_now = validate_now


class GuestPrivateQuery:
    """No underlying repository is exposed, including to a mistaken read helper."""
    def __getattr__(self, name):
        raise SessionConversationError('guest_private_context_unavailable', 403)


class GuestRuntimeView:
    memory = None
    device_token = None

    def __init__(self, actor):
        self.actor = actor
        playback = actor.shared_status()['playback']
        source = playback.get('source_url') or ''
        uri = ('spotify:track:' + source.rsplit('/', 1)[1]
               if re.fullmatch(r'https://open\.spotify\.com/track/[A-Za-z0-9]{22}', source) else '')
        self.device_status = {}
        self.last_playback = {**playback, 'uri':uri, 'track_name':playback.get('title', ''),
                              'artist_name':playback.get('artist', ''), 'is_playing':playback.get('state') == 'playing'}
        self.ask_dj_history = None
        self.listeners = []
        self.last_text = self.last_dj_text = self.last_stt_text = self.last_corrected_text = None
        self.last_intent = self.last_spotify_search = self.last_resolved_media = None

    def update(self, **changes):
        # Only this temporary consumer's runtime cache. Never replace the
        # paired host's transcript/debug/cache state with a room interaction.
        for key, value in changes.items():
            if key.startswith('last_'):
                setattr(self, key, value)

    @property
    def config(self):
        from .profile_backend import PROFILE_BACKEND_ENTRY_ID, profile_backend_entry_id
        self.actor.validate()
        source = self.actor.transport or self.actor.runtime
        # Carry routing only, never device names, response-style prose or any
        # other personal entry option into this public consumer view.
        conf = {key:source.config[key] for key in ("assist_pipeline_id",) if key in source.config}
        prefs = self.actor.profile.preferences
        conf.update(profile_id=self.actor.profile.profile_id, music_backend=prefs.default_backend_id,
                    music_account_id=prefs.default_music_account_id)
        provider = profile_backend_entry_id(self.actor.hass, self.actor.profile.profile_id)
        if provider:
            conf[PROFILE_BACKEND_ENTRY_ID] = provider
        return conf

    def __getattr__(self, name):
        if name.startswith('profile_context_') or name in {'device_id', 'device_name', 'user_id', 'music_dna_key'}:
            raise AttributeError(name)
        if name == 'entry':
            return self.actor.runtime.entry
        raise AttributeError(name)


@dataclass(frozen=True, repr=False)
class GuestConversationActor:
    hass: object
    manager: object
    grant: object
    share: object
    active: object
    profile: object
    runtime: object
    transport: object = None
    transport_digest: str = ''

    @property
    def scope(self):
        return 'guest:' + self.grant.principal_id

    @property
    def revision(self):
        self.validate()
        return self.grant.generation

    def validate(self):
        try:
            state = self.manager._display_admission
            share, _policy = state.participation.validate(self.grant)
            if (share is not self.share or self.manager.current_active(self.profile.profile_id) is not self.active
                    or self.active.session_id != share.owner.session_id
                    or self.hass.data.get('djconnect', {}).get(share.owner.entry_id) is not self.runtime):
                raise DisplayAdmissionError('guest_context_changed', 403)
            from .profile_context import profile_storage
            if profile_storage(self.hass).household.profiles.get(self.profile.profile_id) is not self.profile:
                raise DisplayAdmissionError('guest_context_changed', 403)
            if self.transport is not None:
                from .api_handlers import _ha_native_service_identity
                from .native_voice import _configuration_digest
                _ha_native_service_identity(self.hass, self.transport)
                if _configuration_digest(self.transport) != self.transport_digest:
                    raise DisplayAdmissionError('guest_context_changed', 403)
        except DisplayAdmissionError as exc:
            raise SessionConversationError(exc.code, exc.status) from exc

    def require_shared_dependencies(self, dependencies):
        self.validate()
        if not dependencies:
            return
        from .guest_presentation import selected_shared_moment
        for dependency in dependencies:
            if set(dependency) != {'session_id','moment_id'}:
                raise SessionConversationError('guest_private_context_unavailable', 403)
            selected_shared_moment(self, dependency)

    def authorize_intent(self, intent, *, text="", request=False):
        self.validate()
        from .mood_music_steering import first_play_requested
        from .ask_dj.spotify_collection_offers import collection_request
        if first_play_requested(text) or collection_request(text) is not None:
            raise SessionConversationError('guest_private_context_unavailable', 403)
        if request:
            _, policy = self.manager._display_admission.participation.validate(self.grant)
            if policy.requests == 'disabled':
                raise SessionConversationError('guest_requests_disabled', 403)
            return
        if intent.intent not in PUBLIC_INTENTS or (
                intent.category in {'action', 'hybrid'} and intent.intent != 'conversation_stop'):
            raise SessionConversationError('guest_action_not_permitted', 403)

    def shared_status(self):
        self.validate()
        from .display_projection import _public_playback
        # No output-status consent: a guest cannot inspect a host's device IDs.
        class PublicAudience:
            include_output_status = False
        playback = _public_playback(self.active.broadcast.state.playback, PublicAudience())
        playback['has_playback'] = bool(playback.get('item_id'))
        playback['is_playing'] = playback.get('state') == 'playing'
        return {'success':True, 'playback':playback}

    def allow_command(self, command):
        self.validate()
        from .guest_requests import admission_for
        admission = admission_for(self)
        if admission is not None and admission.allows_command(command):
            return
        if command not in PUBLIC_COMMANDS:
            raise SessionConversationError('guest_action_not_permitted', 403)

    async def before_turn(self):
        async with self.manager._lock:
            self.validate()
            try:
                self.manager._display_admission.participation.charge_turn(self.grant)
            except DisplayAdmissionError as exc:
                raise SessionConversationError(exc.code, exc.status) from exc

    async def before_model(self):
        from .guest_requests import current_request
        if current_request.get() is not None:
            raise SessionConversationError('guest_action_not_permitted', 403)
        async with self.manager._lock:
            self.validate()
            try:
                self.manager._display_admission.participation.charge_model(self.grant)
            except DisplayAdmissionError as exc:
                raise SessionConversationError(exc.code, exc.status) from exc

    def present(self, response):
        self.validate()
        # Never return a personal history/speech/media envelope or owner fields.
        return {'success':bool(response.get('success')), 'text':str(response.get('dj_text') or response.get('text') or ''),
                'guest_id':self.grant.principal_id, 'history_persisted':False,
                **({'guest_request':dict(response['guest_request'])} if isinstance(response.get('guest_request'), dict) else {}),
                **({'request_choices':{'result_set_id':response['result_set']['result_set_id'],
                    'items':[{k:item[k] for k in ('title','artist','action_id') if k in item}
                             for item in response['result_set']['items']]}}
                   if isinstance(response.get('result_set'), dict) and response['result_set'].get('result_set_id')
                   and all(i.get('command') == 'guest_request_recording' for i in response['result_set'].get('items', [])) else {})}


def capture_actor(hass, manager, grant, *, transport=None):
    """Called under the sole Runtime lock after genuine guest/native admission."""
    state = manager._display_admission
    share, _ = state.participation.validate(grant)
    active = manager.current_active(share.owner.profile_id)
    from .profile_context import profile_storage
    storage = profile_storage(hass)
    profile = storage.household.profiles.get(share.owner.profile_id)
    runtime = hass.data.get('djconnect', {}).get(share.owner.entry_id)
    if active is None or profile is None or runtime is None:
        raise SessionConversationError('guest_context_changed', 403)
    digest = ''
    if transport is not None:
        from .native_voice import _configuration_digest
        digest = _configuration_digest(transport)
    actor = GuestConversationActor(hass, manager, grant, share, active, profile, runtime, transport, digest)
    actor.validate()
    return actor


def guard_spotify(method, path):
    actor = current_guest.get()
    if actor is None:
        return
    actor.validate()
    from .guest_requests import admission_for
    admission = admission_for(actor)
    if admission is not None:
        admission.guard(method.upper(), path)
        return
    route = urlsplit(path).path
    public = (route in {'/search','/tracks','/albums','/artists'} or re.fullmatch(
        r'/(?:tracks/[A-Za-z0-9]+|albums/[A-Za-z0-9]+(?:/tracks)?|artists/[A-Za-z0-9]+(?:/(?:albums|top-tracks|related-artists))?)', route))
    if method.upper() != 'GET' or not public:
        raise SessionConversationError('guest_action_not_permitted', 403)


async def exchange(actor, payload, *, request=None):
    """Translate a principal once; the existing application service owns the turn."""
    actor.validate()
    if current_guest.get() is not None:
        raise SessionConversationError('guest_recursive_exchange', 403)
    from .http import _history_manager, async_handle_ask_dj
    from .ask_dj import service
    history = _history_manager(actor.hass, actor.runtime)
    context = payload.get('conversation_context') or {}
    if set(context) - {'thread_id', 'result_set_id', 'selected_moment'}:
        raise SessionConversationError('guest_private_context_unavailable', 403)
    original_moment = None
    if context.get('selected_moment') is not None:
        from .guest_presentation import selected_shared_moment
        original_moment = selected_shared_moment(actor, context['selected_moment'])
    language = payload.get('language') or actor.active.locale
    if language not in {'nl', 'en', 'de', 'fr', 'es'}:
        raise SessionConversationError('guest_request_invalid', 400)
    data = {key:payload[key] for key in ('text', 'client_message_id', 'choice_action') if key in payload}
    data.update(conversation_context=context, language=language, audio_response='never',
                privacy_mode='private', speech_contract_version=3)
    view = GuestRuntimeView(actor)
    if request is None:
        from .ask_dj import classify_ask_dj
        intent = classify_ask_dj(str(data.get('text') or ''))
        frame = history.dialogue.owners.get(actor.scope, {}).get(context.get('thread_id') or 'default')
        pending = frame.pending if frame else None
        request = intent.intent == 'play_music' or (
            isinstance(pending, dict) and pending.get('type') == 'guest_request'
            and intent.intent not in {'conversation_stop', 'session_lifecycle'}
            and not (intent.category == 'action' and intent.intent != 'play_music'))
        # Original common-owner replay carries the routing mode. Consuming a
        # choice must not change the digest of the same delivered HA turn.
        from .guest_requests import status_action
        from .guest_presentation import presentation_action
        if status_action(data.get('text')) or presentation_action(data.get('text')):
            request = False
        previous = (frame.inflight.get(data.get('client_message_id'))
                    or frame.catalogue_replays.get(data.get('client_message_id'))) if frame else None
        future = previous[1] if previous else None
        if future is not None and future.done() and not future.cancelled() and future.exception() is None:
            original_response, _ = future.result()
            if type(original_response.get('_guest_request_mode')) is bool:
                request = original_response['_guest_request_mode']

    def dispose():
        frames = history.dialogue.owners.pop(actor.scope, {})
        for frame in frames.values():
            frame.reset('guest_authority_withdrawn')

    actor.grant.invalidated = dispose

    def validate_selected():
        actor.validate()
        if original_moment is not None:
            from .guest_presentation import selected_shared_moment
            if selected_shared_moment(actor, context['selected_moment']) is not original_moment:
                raise SessionConversationError('guest_shared_moment_unavailable', 404)

    async def validate():
        validate_selected()

    async def delegate(confirmed, scope, selected, playback):
        from .guest_presentation import presentation_action, presentation_response
        action = presentation_action(confirmed.get('text'))
        if action and not request:
            return await presentation_response(actor, confirmed, action)
        from .guest_requests import status_action, respond_status
        if status_action(confirmed.get('text')) and not request:
            return await respond_status(actor, confirmed)
        if request:
            from .guest_requests import respond
            return await respond(actor, view, confirmed)
        return await async_handle_ask_dj(actor.hass, view, confirmed,
            conversation_history_scope=scope, ephemeral_conversation=True,
            confirmed_entry=selected, saved_playback_result=playback)

    token = current_guest.set(actor)
    try:
        response = await service.async_exchange(actor.hass, view, data,
            profile_id=actor.profile.profile_id, profile=actor.profile, history_manager=history,
            delegate=delegate, validate_owner=validate, validate_immediate=validate_selected,
            persist_history=False, actor=actor, participant_request=request)
        original_now = getattr(response, "validate_now", validate_selected)
        original_now()
        result = GuestServiceResult(actor.present(response), original_now)
        frame = history.dialogue.owners.get(actor.scope, {}).get(context.get('thread_id') or 'default')
        result['continue_conversation'] = bool(frame and frame.pending)
        return result
    finally:
        current_guest.reset(token)


async def voice_exchange(hass, runtime, user_input):
    """Actual mapped HA endpoint -> the same guest actor/service as the browser."""
    from .session_runtime import session_runtime_manager
    manager = session_runtime_manager(hass)
    state = manager._display_admission
    endpoint_id = getattr(user_input, 'device_id', None)
    # No shared mapping means the existing personal admission still decides.
    if not isinstance(endpoint_id, str) or endpoint_id not in state.participation._voice:
        return None
    from .native_voice import _configuration_digest, require_native_backend, conversation_reference
    from .api_handlers import _ha_native_service_identity
    from .pipeline import _assist_context
    from homeassistant.helpers import device_registry as dr
    _ha_native_service_identity(hass, runtime)
    if dr.async_get(hass).async_get(endpoint_id) is None:
        raise SessionConversationError('guest_voice_endpoint_invalid', 403)
    require_native_backend(hass, _assist_context(hass, runtime.config))
    from homeassistant.core import Context
    from homeassistant.util.ulid import ulid_to_bytes_or_none
    request_context = getattr(user_input, 'context', None)
    if not isinstance(request_context, Context):
        raise SessionConversationError('guest_voice_context_required', 403)
    try:
        raw_context = ulid_to_bytes_or_none(request_context.id)
    except (TypeError, ValueError, AttributeError):
        raw_context = None
    if raw_context is None:
        raise SessionConversationError('guest_voice_context_required', 403)
    created_ms = int.from_bytes(raw_context[:6], 'big')
    async with manager._lock:
        endpoint = state.participation._voice.get(endpoint_id)
        # HA's actual Context timestamp is a negative stale-input fence, not a
        # speaker identity, fabricated input epoch or proof of physical capture.
        if (endpoint is None or created_ms <= endpoint.admitted_ms
                or created_ms > time.time_ns() // 1_000_000 + 30000):
            raise SessionConversationError('guest_voice_context_changed', 403)
        try:
            grant = state.participation.voice(endpoint_id)
        except DisplayAdmissionError as exc:
            raise SessionConversationError(exc.code, exc.status) from exc
        actor = capture_actor(hass, manager, grant, transport=runtime)
    conversation_id = conversation_reference(user_input, runtime.entry.entry_id, endpoint_id)
    if not isinstance(conversation_id, str) or not conversation_id or len(conversation_id) > 128:
        raise SessionConversationError('invalid_conversation_context', 400)
    context_id = request_context.id
    identifier = 'ha-guest-' + hashlib.sha256(json.dumps([
        runtime.entry.entry_id, endpoint_id, conversation_id, context_id, user_input.text,
    ]).encode()).hexdigest()
    thread = 'voice-' + hashlib.sha256(json.dumps([endpoint_id, conversation_id]).encode()).hexdigest()
    before = _configuration_digest(runtime)
    result = await exchange(actor, {'text':user_input.text, 'language':user_input.language,
        'client_message_id':identifier, 'conversation_context':{'thread_id':thread}})
    result.validate_now()
    if _configuration_digest(runtime) != before:
        raise SessionConversationError('guest_context_changed', 403)
    return result, conversation_id, result['continue_conversation']
