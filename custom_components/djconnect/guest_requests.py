"""Temporary request proposals; the existing Core journal owns queue dispatch.

No recommendation, queue replacement, durable preference or independent Session.
The privileged scope exists only around a sealed, host-admitted exact recording.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import json
import re
import secrets
import unicodedata
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from .session_conversation import SessionConversationError

current_request = ContextVar('djconnect_host_request_admission', default=None)
MAX_REQUESTS = 128
MAX_SHARE_PENDING = 12
ACTIVE = frozenset({'received', 'considering', 'planned', 'effect_uncertain', 'queue_confirmed'})

TEXT = {
    'choose': {'en':'Which recording would you like to request?', 'nl':'Welke opname wil je aanvragen?', 'de':'Welche Aufnahme möchtest du wünschen?', 'fr':'Quel enregistrement souhaites-tu demander ?', 'es':'¿Qué grabación quieres pedir?'},
    'missing': {'en':'Name the song and artist you would like to request.', 'nl':'Noem het nummer en de artiest die je wilt aanvragen.', 'de':'Nenne das Lied und den Künstler für deinen Wunsch.', 'fr':'Indique le titre et l’artiste que tu souhaites demander.', 'es':'Indica la canción y el artista que quieres pedir.'},
    'received': {'en':'Your request has been received for host review.', 'nl':'Je verzoek is ontvangen voor beoordeling door de host.', 'de':'Dein Wunsch ist zur Prüfung beim Gastgeber eingegangen.', 'fr':'Ta demande a été reçue pour examen par l’hôte.', 'es':'Tu petición se ha recibido para que el anfitrión la revise.'},
    'queue_confirmed': {'en':'The recording is confirmed in the music queue.', 'nl':'De opname staat bevestigd in de muziekwachtrij.', 'de':'Die Aufnahme ist in der Musikwarteschlange bestätigt.', 'fr':'L’enregistrement est confirmé dans la file musicale.', 'es':'La grabación está confirmada en la cola de música.'},
    'effect_uncertain': {'en':'Queue placement is uncertain. I will check the existing request without adding it again.', 'nl':'Plaatsing in de wachtrij is onzeker. Ik controleer het bestaande verzoek zonder het opnieuw toe te voegen.', 'de':'Die Einreihung ist ungewiss. Ich prüfe den bestehenden Wunsch, ohne ihn erneut hinzuzufügen.', 'fr':'La mise en file est incertaine. Je vérifierai la demande existante sans l’ajouter de nouveau.', 'es':'La incorporación a la cola es incierta. Comprobaré la petición existente sin añadirla otra vez.'},
}


def message(key, language):
    return TEXT[key].get(language, TEXT[key]['en'])


def _key(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(text)).casefold() if c.isalnum())


_REQUEST_WRAPPERS = tuple(re.compile(pattern, re.I) for pattern in (
    r'(?:kun|kan|wil|zou) je (?:alsjeblieft )?(?P<subject>.+?) (?:draaien|spelen|opzetten)',
    r'doe maar (?P<subject>.+)',
    r'ik wil (?:graag )?(?P<subject>.+?) aanvragen',
    r'zet (?P<subject>.+?) in de wachtrij',
))
_TITLE_AND_ARTIST = re.compile(r'(?P<title>.+?)\s+(?:van|by)\s+(?P<artist>.+)', re.I)
_BARE_SENTENCE = re.compile(
    r'^(?:ik|we|je|kun|kan|mag|is|zijn|was|heb|heeft|vertel|leg|vraag|noem|toon|over|'
    r'i|you|are|can|could|would|tell|show|explain|about)\b', re.I,
)
_MISSING_SUBJECT = re.compile(r'(?:(?:een|het|dit|dat) )?(?:verzoeknummer|verzoekje|verzoek)', re.I)


def request_subject(text):
    """Recognize guest-only request phrasing. Bare credits require a choice."""
    from .ask_dj import _looks_like_prompt_or_sandbox_attack, _nonexecuting_speech_act
    from .music_intent import music_command_subject, negated_music_command

    subject = ' '.join(text.strip().split()).rstrip('.!?').strip()
    if (not subject or _nonexecuting_speech_act(text)
            or _looks_like_prompt_or_sandbox_attack(text)
            or re.search(r'[{}<>]|https?://|spotify:', text, re.I)):
        return None
    for wrapper in _REQUEST_WRAPPERS:
        if match := wrapper.fullmatch(subject):
            value = match['subject']
            if negated_music_command('speel ' + value):
                return None
            return ('' if _MISSING_SUBJECT.fullmatch(value) else value, True)
    if ('?' not in text and not music_command_subject(text) and not _BARE_SENTENCE.match(subject)
            and _TITLE_AND_ARTIST.fullmatch(subject)
            and not negated_music_command('speel ' + subject)):
        return subject, False
    return None


@dataclass(slots=True, repr=False)
class SongRequest:
    request_id: str
    actor: object
    client_key: str
    uri: str
    title: str
    artist: str
    operation_id: str
    policy_mode: str
    deadline: float
    state: str = 'received'
    basis: str = 'guest_selected_recording'
    output_id: str = ''
    journal_key: str = ''
    started: bool = False
    sent: bool = False
    acknowledged: bool = False
    host: object = None
    participants: set[str] = field(default_factory=set)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def public(self):
        return {'request_id':self.request_id, 'title':self.title, 'artist':self.artist,
                'state':self.state, 'basis':self.basis}


class GuestRequestState:
    def __init__(self, admission):
        self.admission = admission
        self.records: dict[str, SongRequest] = {}
        self.clients: dict[str, str] = {}

    def propose(self, actor, client_id, item):
        actor.validate()
        _, policy = self.admission.validate(actor.grant)
        if policy.requests == 'disabled':
            raise SessionConversationError('guest_requests_disabled', 403)
        uri = item.get('uri')
        if not isinstance(uri, str) or not re.fullmatch(r'spotify:track:[A-Za-z0-9]{22}', uri):
            raise SessionConversationError('guest_recording_unavailable', 409)
        # The physical room endpoint survives principal renewal/reconfiguration;
        # the same delivered HA turn must not become a fresh queue intent.
        identity = actor.grant.endpoint_id if actor.grant.kind == 'voice' else actor.grant.principal_id
        client_key = hashlib.sha256(json.dumps([
            'ha-voice' if actor.grant.kind == 'voice' else actor.share.share_id, identity, client_id]).encode()).hexdigest()
        old = self.records.get(self.clients.get(client_key))
        if old is not None:
            if old.uri != uri:
                raise SessionConversationError('guest_request_conflict', 409)
            old.actor.validate()  # Regrant cannot revive withdrawn intent.
            return old
        now = self.admission.display._clock()
        # Never evict a still-live receipt in order to dispatch another effect.
        if len(self.records) >= MAX_REQUESTS or len(self.clients) >= 256:
            raise SessionConversationError('guest_request_capacity', 429)
        pending = []
        for record in self.records.values():
            if record.actor.share is not actor.share or record.state not in ACTIVE or record.deadline <= now:
                continue
            try:
                record.actor.validate()
            except SessionConversationError:
                continue  # No fresh caller inherits an expired guest's status/approval.
            pending.append(record)
        # Coalesce exact active recordings for this share, without another write.
        existing = next((r for r in pending if r.uri == uri), None)
        if existing is not None:
            if len(self.clients) >= 256:
                raise SessionConversationError('guest_request_capacity', 429)
            self.clients[client_key] = existing.request_id
            existing.participants.add(actor.grant.principal_id)
            return existing
        if len(pending) >= MAX_SHARE_PENDING or sum(r.actor.grant is actor.grant for r in pending) >= policy.max_pending:
            raise SessionConversationError('guest_request_capacity', 429)
        from .hybrid_service import operations
        journal = operations(actor.hass).journal
        ms = journal.now_ms()
        operation_id = str(UUID(int=(ms << 80) | (7 << 76) | (secrets.randbits(12) << 64)
                                | (2 << 62) | secrets.randbits(62)))
        request = SongRequest(secrets.token_urlsafe(24), actor, client_key, uri,
            str(item.get('title') or item.get('name') or '')[:200],
            str(item.get('artist') or item.get('artist_name') or item.get('subtitle') or '')[:200],
            operation_id, policy.requests, min(actor.share.deadline, now + 300))
        request.participants.add(actor.grant.principal_id)
        self.records[request.request_id] = request
        self.clients[client_key] = request.request_id
        return request

    def owned(self, actor, request_id):
        actor.validate()
        record = self.records.get(request_id)
        if record is None or record.actor.share is not actor.share:
            raise SessionConversationError('guest_request_unavailable', 404)
        # Coalesced guests see only public recording/status, never another dialog.
        if actor.grant.principal_id not in record.participants:
            raise SessionConversationError('guest_request_unavailable', 404)
        return record

    def prune_guest(self, grant):
        for record in self.records.values():
            if record.actor.grant is grant and not record.sent and record.state in {'received','considering','planned'}:
                record.state = 'expired'

    def prune_share(self, share_id):
        # Retain opaque retry binding until Runtime ends. Withdrawing a share
        # invalidates actors; it cannot turn an old input into a fresh dispatch.
        for record in self.records.values():
            if record.actor.grant.share_id == share_id and record.state in {'received','considering','planned'} and not record.sent:
                record.state = 'expired'


@dataclass(repr=False)
class HostRequestAdmission:
    record: SongRequest
    state: GuestRequestState

    def validate(self):
        record = self.record
        actor = record.actor
        actor.validate()
        _, policy = self.state.admission.validate(actor.grant)
        if (self.state.records.get(record.request_id) is not record
                or policy.requests != record.policy_mode
                or self.state.admission.display._clock() >= record.deadline
                or (record.policy_mode == 'review' and (record.host is None or not record.host.valid()))):
            raise SessionConversationError('guest_request_authority_changed', 403)

    def allows_command(self, command):
        self.validate()
        return command in {'enqueue_track', 'queue'}

    def guard(self, method, path, body=None, *, dispatch=False):
        self.validate()
        route = urlsplit(path)
        if method == 'GET' and route.path in {'/me/player','/me/player/queue'} and not route.query:
            return
        if (method != 'POST' or route.path != '/me/player/queue' or body is not None
                or parse_qs(route.query) != {'uri':[self.record.uri], 'device_id':[self.record.output_id]}
                or not self.record.output_id):
            raise SessionConversationError('guest_action_not_permitted', 403)
        if dispatch:
            from .hybrid_service import operations
            journal = operations(self.record.actor.hass).journal
            stored = (journal._state or {}).get('records', {}).get(self.record.journal_key)
            if (not self.record.started or self.record.journal_key not in journal._active
                    or stored is None or stored.get('phase') != 'sent_unknown'
                    or stored.get('operation_id') != self.record.operation_id
                    or stored.get('operation') != 'guest/request/enqueue' or stored.get('epoch') != journal.epoch):
                raise SessionConversationError('guest_request_not_reserved', 403)
            journal._validate_time(self.record.operation_id)
            if self.record.sent:
                raise SessionConversationError('guest_request_outcome_unknown', 409)
            self.record.sent = True  # No 401/internal transport retry may resend.


def admission_for(actor=None):
    admission = current_request.get()
    if type(admission) is not HostRequestAdmission:
        return None
    if actor is not None and admission.record.actor is not actor:
        return None
    admission.validate()
    return admission


async def fulfil(state, record, *, host=None):
    """One reservation, one POST; retries only observe the original queue."""
    from .hybrid_service import operations
    from .profile_backend import profile_backend_runtime
    from .spotify_backend import SpotifyBackend
    from .guest_conversation import GuestRuntimeView, current_guest
    async with record.lock:
        if host is not None:
            state.admission._owner(host, record.actor.share.share_id)
            record.host = host
        admission = HostRequestAdmission(record, state)
        admission.validate()
        guest_token = current_guest.set(record.actor)
        scope_token = current_request.set(admission)
        journal, key = operations(record.actor.hass).journal, record.journal_key
        try:
            view = GuestRuntimeView(record.actor)
            from .profile_context import profile_storage
            from .domain.backend import BackendProvider
            backend_registration = profile_storage(record.actor.hass).household.music_backends.get(
                record.actor.profile.preferences.default_backend_id)
            if backend_registration is None or backend_registration.provider != BackendProvider.SPOTIFY_DIRECT:
                raise SessionConversationError('guest_queue_backend_unavailable', 409)
            backend = SpotifyBackend(record.actor.hass, profile_backend_runtime(record.actor.hass, view))
            from .session_runtime import RendererSafePlaybackProjection
            requested_item_id = RendererSafePlaybackProjection.from_observation(
                state='playing', media_identity=record.uri).item_id
            if record.started:
                if record.state not in {'queue_confirmed', 'effect_uncertain', 'planned'}:
                    return record.public()
                output = await backend._request('GET', '/me/player')
                admission.validate()
                if (not isinstance(output, dict) or not isinstance(output.get('device'), dict)
                        or output['device'].get('id') != record.output_id):
                    record.state, record.basis = 'effect_uncertain', 'original_output_no_longer_current'
                    return record.public()
                queue = await backend.queue()
                admission.validate()
                if any(item.get('uri') == record.uri for item in queue.get('queue', [])):
                    record.state, record.basis = 'queue_confirmed', 'observed_exact_recording_in_queue'
                playback = record.actor.active.broadcast.state.playback
                if record.state == 'queue_confirmed' and playback.item_id == requested_item_id and playback.state == 'playing':
                    record.state, record.basis = 'actually_playing', 'observed_shared_playback'
                return record.public()
            record.started = True  # All failure paths retain the original intent.
            key, receipt, fresh = await journal.reserve(owner=record.actor.profile.profile_id,
                device=record.actor.share.owner.entry_id, binding=record.actor.grant.generation,
                identifier=record.operation_id, epoch=journal.epoch, operation='guest/request/enqueue',
                digest=hashlib.sha256(json.dumps([record.uri, record.client_key]).encode()).hexdigest())
            record.journal_key = key
            if not fresh:
                record.state = 'effect_uncertain'
                return record.public()
            # Read actual output, not Profile/device names or a caller-selected ID.
            playback = await backend._request('GET', '/me/player')
            admission.validate()
            device = playback.get('device') if isinstance(playback, dict) else None
            current = playback.get('item') if isinstance(playback, dict) else None
            expected = record.actor.active.broadcast.state.playback.item_id
            observed_uri = current.get('uri') if isinstance(current, dict) else None
            observed_item_id = (RendererSafePlaybackProjection.from_observation(
                state='playing', media_identity=observed_uri).item_id
                if isinstance(observed_uri, str) and re.fullmatch(r'spotify:track:[A-Za-z0-9]{22}', observed_uri) else None)
            if (not isinstance(device, dict) or not isinstance(device.get('id'), str) or not device['id']
                    or device.get('is_restricted') is not False or not isinstance(current, dict)
                    or observed_item_id is None or observed_item_id != expected):
                record.state = 'expired'
                await journal.transition(key, 'rejected', error='guest_output_unavailable')
                return record.public()
            if expected == requested_item_id and record.actor.active.broadcast.state.playback.state == 'playing':
                record.state, record.basis = 'actually_playing', 'observed_shared_playback'
                await journal.transition(key, 'confirmed')
                return record.public()
            record.output_id = device['id']
            queue = await backend.queue()
            admission.validate()
            if any(item.get('uri') == record.uri for item in queue.get('queue', [])):
                record.state, record.basis = 'queue_confirmed', 'observed_exact_recording_in_queue'
                await journal.transition(key, 'confirmed')
                return record.public()
            record.state = 'planned'
            await journal.transition(key, 'sent_unknown')
            admission.validate()
            from .use_cases import run_music_command
            await run_music_command(record.actor.hass, view, 'enqueue_track',
                                    {'uri':record.uri, 'device_id':record.output_id})
            admission.validate()
            record.acknowledged = True
            output = await backend._request('GET', '/me/player')
            admission.validate()
            if (not isinstance(output, dict) or not isinstance(output.get('device'), dict)
                    or output['device'].get('id') != record.output_id):
                record.state, record.basis = 'effect_uncertain', 'original_output_no_longer_current'
                await journal.transition(key, 'unknown', error='guest_output_changed')
                return record.public()
            record.state, record.basis = 'queue_confirmed', 'backend_enqueue_acknowledged'
            await journal.transition(key, 'confirmed')
            return record.public()
        except asyncio.CancelledError:
            record.state = 'effect_uncertain' if record.sent else 'expired'
            raise
        except Exception as exc:
            record.state = 'effect_uncertain' if record.sent else 'expired'
            if key:
                await journal.transition(key, 'unknown' if record.sent else 'rejected', error='guest_request_unconfirmed')
            if isinstance(exc, SessionConversationError):
                raise
            if record.sent:
                return record.public()
            raise SessionConversationError('guest_request_unavailable', 503) from None
        finally:
            if key:
                journal.release(key)
            current_request.reset(scope_token)
            current_guest.reset(guest_token)


async def respond(actor, runtime, payload):
    """The common Core dialogue owns choices, deadlines and pending continuation."""
    from .ask_dj.dialogue import current_turn, choice_index
    from .music_intent import music_command_subject, parse_spoken_music_request
    from .use_cases import run_music_command
    turn = current_turn.get()
    actor.validate()
    _, policy = actor.manager._display_admission.participation.validate(actor.grant)
    if policy.requests == 'disabled':
        raise SessionConversationError('guest_requests_disabled', 403)
    text = payload.get('text') or ''
    language = payload.get('language') or 'en'
    selected = None
    choice = payload.get('choice_action')
    original = turn.frame.result_set
    if original is not None:
        if original['deadline'] <= turn.history.dialogue.clock():
            raise SessionConversationError('choice_expired', 409)
        index = choice_index(text)
        if isinstance(choice, dict):
            if choice.get('result_set_id') != original['result_set_id']:
                raise SessionConversationError('choice_expired', 409)
            selected = next((item for item in original['items'] if item['action_id'] == choice.get('action_id')), None)
            if selected is None:
                raise SessionConversationError('choice_expired', 409)
        elif index is not None and index < len(original['items']):
            selected = original['items'][index]
        if selected and selected.get('command') != 'guest_request_recording':
            raise SessionConversationError('guest_action_not_permitted', 403)
    if selected is None:
        subject = request_subject(text)
        if subject == ('', True):
            turn.pending = {'type':'guest_request', 'query':'', 'deadline':turn.history.dialogue.clock() + 120}
            turn.clear_result_set = True
            return {'success':True, 'text':message('missing', language)}
        command = 'speel ' + subject[0] if subject else text
        parsed = parse_spoken_music_request(command)
        if parsed.get('type') in {'liked','playlist','album'}:
            return {'success':True, 'text':message('missing', language)}
        if not parsed.get('title'):
            credit = _TITLE_AND_ARTIST.fullmatch(music_command_subject(command))
            if credit:
                parsed.update(title=credit['title'], artist=credit['artist'],
                              query=credit['title'] + ' ' + credit['artist'])
        query = parsed.get('query') or text
        pending = turn.pending_at_start
        continuing = isinstance(pending, dict) and pending.get('type') == 'guest_request'
        if continuing and pending.get('query') and not parsed.get('title'):
            query = str(pending['query']) + ' ' + text
        result = await run_music_command(actor.hass, runtime, 'search_tracks', {'query':query, 'limit':5})
        await turn.guard()
        items = result.get('tracks') or result.get('items') or []
        items = [item for item in items if isinstance(item, dict)
                 and re.fullmatch(r'spotify:track:[A-Za-z0-9]{22}', str(item.get('uri') or ''))][:5]
        # Only one exact title+artist match may avoid another confirmation.
        exact = [item for item in items if parsed.get('title') and parsed.get('artist')
                 and _key(item.get('title') or item.get('name')) == _key(parsed['title'])
                 and _key(item.get('artist') or item.get('artist_name')) == _key(parsed['artist'])]
        completing_request = (continuing and pending.get('query') == ''
                              and turn.frame.pending is pending
                              and turn.frame.pending_revision == turn.pending_revision_at_start
                              and turn.history.dialogue.clock() < pending['deadline'])
        if len(items) == 1 and len(exact) == 1 and (subject is None or subject[1] or completing_request):
            selected = exact[0]
        else:
            turn.pending = {'type':'guest_request', 'query':query[:800], 'deadline':turn.history.dialogue.clock() + 120}
            return {'success':True, 'text':message('choose' if items else 'missing', language),
                    'playback_actions':[{'kind':'track','uri':i['uri'],
                        'title':str(i.get('title') or i.get('name') or '')[:200],
                        'artist':str(i.get('artist') or i.get('artist_name') or '')[:200],
                        'command':'guest_request_recording'} for i in items]}
    async with actor.manager._lock:
        request = actor.manager._display_admission.participation.requests.propose(actor, turn.client_id, selected)
    turn.clear_pending = True
    turn.clear_result_set = True
    if request.policy_mode == 'auto_queue':
        await fulfil(actor.manager._display_admission.participation.requests, request)
    return {'success':True, 'text':message(request.state if request.state in TEXT else 'received', language),
            'guest_request':request.public()}

STATUS_TEXT = {
    'considering':{'en':'The host is considering your request.','nl':'De host overweegt je verzoek.','de':'Der Gastgeber erwägt deinen Wunsch.','fr':'L’hôte examine ta demande.','es':'El anfitrión está considerando tu petición.'},
    'planned':{'en':'Queue placement is being prepared.','nl':'Plaatsing in de wachtrij wordt voorbereid.','de':'Die Einreihung wird vorbereitet.','fr':'La mise en file est en préparation.','es':'Se está preparando la incorporación a la cola.'},
    'actually_playing':{'en':'The requested recording is now playing.','nl':'De aangevraagde opname wordt nu afgespeeld.','de':'Die gewünschte Aufnahme wird jetzt gespielt.','fr':'L’enregistrement demandé est en cours de lecture.','es':'La grabación solicitada se está reproduciendo.'},
    'rejected':{'en':'The host declined this request.','nl':'De host heeft dit verzoek afgewezen.','de':'Der Gastgeber hat diesen Wunsch abgelehnt.','fr':'L’hôte a refusé cette demande.','es':'El anfitrión ha rechazado esta petición.'},
    'expired':{'en':'This request has expired. It has not been added again.','nl':'Dit verzoek is verlopen. Het is niet opnieuw toegevoegd.','de':'Dieser Wunsch ist abgelaufen. Er wurde nicht erneut hinzugefügt.','fr':'Cette demande a expiré. Elle n’a pas été ajoutée de nouveau.','es':'Esta petición ha caducado. No se ha añadido otra vez.'},
    'missing_request':{'en':'You have no request in this temporary conversation.','nl':'Je hebt geen verzoek in dit tijdelijke gesprek.','de':'In diesem vorübergehenden Gespräch hast du keinen Wunsch.','fr':'Tu n’as aucune demande dans cette conversation temporaire.','es':'No tienes ninguna petición en esta conversación temporal.'},
}
TEXT.update(STATUS_TEXT)


def status_action(text):
    value = ' '.join(str(text).casefold().strip(' .!?¿¡').split())
    return value in {'what is the status of my request','is my request in the queue','my request status',
        'wat is de status van mijn verzoek','staat mijn verzoek in de wachtrij','status van mijn verzoek',
        'wie ist der status meines wunsches','ist mein wunsch in der warteschlange',
        'quel est le statut de ma demande','ma demande est-elle dans la file',
        'cuál es el estado de mi petición','está mi petición en la cola'}


async def respond_status(actor, payload):
    actor.validate()
    requests = actor.manager._display_admission.participation.requests
    records = [r for r in requests.records.values() if r.actor.share is actor.share
               and actor.grant.principal_id in r.participants]
    if not records:
        return {'success':True,'text':message('missing_request',payload.get('language'))}
    record = records[-1]
    if record.started and record.state in {'queue_confirmed','planned','effect_uncertain'}:
        await fulfil(requests, record)
    return {'success':True,'text':message(record.state,payload.get('language')),'guest_request':record.public()}
