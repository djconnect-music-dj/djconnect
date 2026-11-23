"""Closed participation boundary over genuine paired host and guest principals."""
from __future__ import annotations

from .display_admission import DisplayAdmissionError
from .display_service import DisplayAdmissionService
from .guest_admission import ParticipationPolicy
from .session_conversation import SessionConversationError

_OWNER = {'identity', 'session_id', 'share_id'}
_GUEST = {'issuer_epoch', 'guest_id'}
SHAPES = {
    'owner/context': (_OWNER, set()),
    'owner/configure': (_OWNER | {'policy'}, set()),
    'owner/invite': (_OWNER, set()),
    'owner/remove': (_OWNER | {'guest_id'}, set()),
    'owner/requests': (_OWNER, set()),
    'owner/decide': (_OWNER | {'request_id', 'decision'}, set()),
    'owner/voice': (_OWNER | {'ha_device_id'}, set()),
    'owner/unbind-voice': (_OWNER | {'ha_device_id'}, set()),
    'redeem': ({'issuer_epoch', 'invitation_id', 'invitation_secret'}, set()),
    'renew': (_GUEST | {'renew_sequence'}, set()),
    'leave': (_GUEST, set()),
    'context': (_GUEST, set()),
    'focus': (_GUEST | {'moment_id'}, set()),
    'return': (_GUEST, set()),
    'display/invitation': ({'issuer_epoch','display_id'}, set()),
    'display/focus': ({'issuer_epoch','display_id'}, set()),
    'display/return': ({'issuer_epoch','display_id'}, set()),
    'display/focus-photo': ({'issuer_epoch','display_id','focus_revision'}, set()),
    'ask': (_GUEST | {'text', 'client_message_id'}, {'language', 'thread_id', 'moment_id'}),
    'request': (_GUEST | {'text', 'client_message_id'}, {'language', 'thread_id', 'choice_action'}),
    'request/status': (_GUEST | {'request_id'}, set()),
}


def shape(action, payload):
    if action not in SHAPES or not isinstance(payload, dict):
        raise DisplayAdmissionError('guest_request_invalid', 400)
    if type(payload.get('contract_version')) is not int or payload['contract_version'] != 1:
        raise DisplayAdmissionError('guest_contract_unsupported', 400)
    required, optional = SHAPES[action]
    fields = set(payload) - {'contract_version'}
    if not required <= fields or fields - required - optional:
        raise DisplayAdmissionError('guest_request_invalid', 400)
    for key, value in payload.items():
        if key == 'policy':
            if (not isinstance(value, dict) or not {'information', 'requests', 'max_pending'} <= set(value)
                    or set(value) - {'information', 'requests', 'max_pending', 'screen_focus'}):
                raise DisplayAdmissionError('guest_policy_invalid', 400)
        elif key == 'choice_action':
            if (not isinstance(value, dict) or set(value) != {'result_set_id', 'action_id'}
                    or not all(isinstance(v, str) and 0 < len(v) <= 128 for v in value.values())):
                raise DisplayAdmissionError('guest_request_invalid', 400)
        elif key == 'identity':
            if not isinstance(value, dict):
                raise DisplayAdmissionError('guest_request_invalid', 400)
        elif key in {'contract_version', 'renew_sequence'}:
            if type(value) is not int or value < 1:
                raise DisplayAdmissionError('guest_request_invalid', 400)
        elif not isinstance(value, str) or not value or len(value) > (1600 if key == 'text' else 128 if key in {'thread_id', 'client_message_id'} else 256):
            raise DisplayAdmissionError('guest_request_invalid', 400)


def bearer(headers):
    value = headers.get('Authorization', '')
    if not isinstance(value, str) or not value.startswith('Bearer djcg_') or len(value) > 256:
        raise DisplayAdmissionError('guest_grant_invalid', 401)
    return value.removeprefix('Bearer ')


class GuestParticipationService:
    def __init__(self, hass, manager):
        self.hass, self.manager = hass, manager
        self.display = DisplayAdmissionService(hass, manager)

    def _owner_action(self, action, payload, owner, state, guests):
        share_id = payload['share_id']
        guests._owner(owner, share_id)
        if action == 'owner/requests':
            return {'requests':[r.public() for r in guests.requests.records.values()
                if r.actor.share is state._shares.get(share_id)]}
        if action == 'owner/context':
            record = guests._policies.get(share_id)
            policy = record.policy if record else ParticipationPolicy()
            return {'policy': {'information': policy.information, 'requests': policy.requests,
                              'max_pending': policy.max_pending, 'screen_focus':policy.screen_focus},
                    'guests': [{'guest_id': g.principal_id, 'kind': g.kind}
                               for g in guests._guests.values() if g.share_id == share_id]}
        if action == 'owner/configure':
            return {'policy': guests.configure(owner=owner, share_id=share_id,
                                               policy=ParticipationPolicy(**payload['policy']))}
        if action == 'owner/invite':
            return guests.invite(owner=owner, share_id=share_id)
        if action == 'owner/remove':
            guests.remove(owner=owner, share_id=share_id, guest_id=payload['guest_id'])
            return {}
        if action == 'owner/unbind-voice':
            endpoint = guests._voice.get(payload['ha_device_id'])
            if endpoint is not None and endpoint.share_id == share_id:
                guests.unbind_voice(endpoint.endpoint_id)
            return {}
        if action == 'owner/voice':
            from homeassistant.helpers import device_registry as dr
            from .profile_context import profile_storage
            device_id = payload['ha_device_id']
            registry = dr.async_get(self.hass)
            device = registry.async_get(device_id)
            storage = profile_storage(self.hass)
            if device is None or device_id in storage.household.shared.personal_voice_endpoint_profile_ids:
                raise DisplayAdmissionError('guest_voice_endpoint_invalid', 403)

            def current():
                return (registry.async_get(device_id) is device
                        and device_id not in storage.household.shared.personal_voice_endpoint_profile_ids)

            guests.bind_voice(owner=owner, share_id=share_id, endpoint_id=device_id, current=current)
            return {}
        raise DisplayAdmissionError('guest_request_invalid', 400)

    async def post(self, action, payload, *, headers, origins, source):
        shape(action, payload)
        selected, owner_action = await self.display._initial_origin(action, origins)
        owner = await self.display._request_owner(action, payload, headers, selected, owner_action=owner_action)
        if action == 'display/focus-photo':
            from .guest_focus_media import prepare
            return await prepare(self, payload, headers, selected)
        if action.startswith('display/'):
            return await self._display_action(action, payload, headers, selected)
        if action in {'ask', 'request'}:
            return await self._ask(payload, headers, selected, request=True if action == 'request' else None)
        if action in {'owner/decide', 'request/status'}:
            return await self._request_action(action, payload, owner, headers, selected)
        async with self.manager._lock:
            self.display._sync_origin(self.display._origin(selected))
            state = self.manager._display_admission
            state.prune()
            guests = state.participation
            if owner_action:
                if owner is None or not owner.valid():
                    raise DisplayAdmissionError('guest_context_changed', 403)
                result = self._owner_action(action, payload, owner, state, guests)
                share = state._shares.get(payload['share_id'])
                participation = guests._policies.get(payload['share_id'])
                issued = guests._invitations.get(result.get('invitation_id')) if action == 'owner/invite' else None

                def guard():
                    return (owner.valid() and state._shares.get(payload['share_id']) is share
                            and share is not None and share.owner.valid() and share.deadline > state._clock()
                            and guests._policies.get(payload['share_id']) is participation
                            and (issued is None or (guests._invitations.get(issued.invitation_id) is issued
                                 and issued.deadline > state._clock())))
            else:
                context_snapshot = None
                if action == 'redeem':
                    result = guests.redeem(invitation_id=payload['invitation_id'],
                        invitation_secret=payload['invitation_secret'], issuer_epoch=payload['issuer_epoch'], source=source)
                    grant = guests.authorize(guest_id=result['guest_id'], token=result['guest_token'],
                                              issuer_epoch=state.issuer_epoch)
                else:
                    grant = guests.authorize(guest_id=payload['guest_id'], token=bearer(headers),
                                              issuer_epoch=payload['issuer_epoch'])
                    if action == 'renew':
                        result = guests.renew(grant, payload['renew_sequence'])
                    elif action == 'leave':
                        guests._drop_guest(grant.principal_id)
                        result = {}
                    else:
                        from .guest_conversation import capture_actor
                        from .guest_presentation import public_context, focus
                        try:
                            actor = capture_actor(self.hass, self.manager, grant)
                            if action in {'focus','return'}:
                                result = focus(actor, payload.get('moment_id'))
                            else:
                                context_snapshot = public_context(actor)
                                result = {**guests.public(grant), **context_snapshot}
                        except SessionConversationError as exc:
                            raise DisplayAdmissionError(exc.code, exc.status) from exc

                def guard():
                    # Leaving removes this principal, but still cannot cross an
                    # origin/Runtime/share change during response preparation.
                    if action == 'leave':
                        try:
                            guests._share(grant.share_id)
                            return grant.principal_id not in guests._guests
                        except DisplayAdmissionError:
                            return False
                    try:
                        guests.validate(grant)
                        if context_snapshot is not None:
                            # Re-read the same public source immediately before
                            # releasing bytes after awaited response headers.
                            return public_context(actor) == context_snapshot
                        return True
                    except (DisplayAdmissionError, SessionConversationError):
                        return False
            return self.display._release_result(result, guard, lambda: None, None, state, selected)

    async def _ask(self, payload, headers, selected, *, request=None):
        from .guest_conversation import capture_actor, exchange
        from .session_conversation import SessionConversationError
        async with self.manager._lock:
            self.display._sync_origin(self.display._origin(selected))
            state = self.manager._display_admission
            grant = state.participation.authorize(guest_id=payload['guest_id'], token=bearer(headers),
                                                  issuer_epoch=payload['issuer_epoch'])
            try:
                actor = capture_actor(self.hass, self.manager, grant)
            except SessionConversationError as exc:
                raise DisplayAdmissionError(exc.code, exc.status) from exc
        data = {key:payload[key] for key in ('text', 'client_message_id', 'language', 'choice_action') if key in payload}
        data['conversation_context'] = {'thread_id':payload.get('thread_id') or 'guest-chat'}
        if payload.get('moment_id') is not None:
            data['conversation_context']['selected_moment'] = {
                'session_id':actor.active.session_id, 'moment_id':payload['moment_id']}
        try:
            result = await exchange(actor, data, request=request)
        except SessionConversationError as exc:
            raise DisplayAdmissionError(exc.code, exc.status) from exc

        def guard():
            from .ask_dj.dialogue import DialogueError
            try:
                result.validate_now()
                actor.validate()
                return True
            except (SessionConversationError, DialogueError):
                return False

        return self.display._release_result(result, guard, lambda:None, None, state, selected)

    async def _request_action(self, action, payload, owner, headers, selected):
        from .guest_conversation import capture_actor
        from .guest_requests import fulfil
        from .session_conversation import SessionConversationError
        try:
            async with self.manager._lock:
                self.display._sync_origin(self.display._origin(selected))
                state = self.manager._display_admission
                guests = state.participation
                request_state = guests.requests
                if action == 'owner/decide':
                    guests._owner(owner, payload['share_id'])
                    record = request_state.records.get(payload['request_id'])
                    if record is None or record.actor.share is not state._shares.get(payload['share_id']):
                        raise DisplayAdmissionError('guest_request_unavailable', 404)
                    if payload['decision'] not in {'accept', 'reject', 'consider'}:
                        raise DisplayAdmissionError('guest_request_invalid', 400)
                    actor = record.actor
                    actor.validate()
                    if payload['decision'] != 'accept':
                        if record.started:
                            raise DisplayAdmissionError('guest_request_already_started', 409)
                        record.state = 'rejected' if payload['decision'] == 'reject' else 'considering'
                else:
                    grant = guests.authorize(guest_id=payload['guest_id'], token=bearer(headers),
                                             issuer_epoch=payload['issuer_epoch'])
                    actor = capture_actor(self.hass, self.manager, grant)
                    record = request_state.owned(actor, payload['request_id'])
                run = ((action == 'owner/decide' and payload['decision'] == 'accept'
                        and record.state in {'received','considering','planned','effect_uncertain','queue_confirmed'})
                       or (action == 'request/status' and record.started
                           and record.state in {'planned','effect_uncertain','queue_confirmed'}))
            if run:
                await fulfil(request_state, record, host=owner if action == 'owner/decide' else None)
            actor.validate()
            result = {'request':record.public()}
        except SessionConversationError as exc:
            raise DisplayAdmissionError(exc.code, exc.status) from exc

        def guard():
            try:
                actor.validate()
                return owner is None or owner.valid()
            except SessionConversationError:
                return False
        return self.display._release_result(result, guard, lambda:None, None, state, selected)

    async def _display_action(self, action, payload, headers, selected):
        def _bearer(headers):
            token = headers.get('Authorization', '')
            if not isinstance(token, str) or not token.startswith('Bearer djcd_') or len(token) > 256:
                raise DisplayAdmissionError('display_grant_invalid', 401)
            return token.removeprefix('Bearer ')
        from .guest_presentation import display_focus
        async with self.manager._lock:
            self.display._sync_origin(self.display._origin(selected))
            state = self.manager._display_admission
            display = state.authorize(token=_bearer(headers), display_id=payload['display_id'],
                                      issuer_epoch=payload['issuer_epoch'])
            guests = state.participation
            if action == 'display/invitation':
                result = guests.display_invitation(display.share_id)
                invitation = guests._invitations[result['invitation_id']]
                from urllib.parse import urlencode
                import base64
                from io import BytesIO
                import segno
                url = selected + '/djconnect/vibecast/guest#' + urlencode({
                    key:result[key] for key in ('issuer_epoch','invitation_id','invitation_secret')})
                buffer = BytesIO()
                segno.make(url, error='m').save(buffer, kind='svg', scale=4, border=4)
                result = {'invitation_id':invitation.invitation_id, 'expires_in':result['expires_in'],
                          'qr_data_uri':'data:image/svg+xml;base64,' + base64.b64encode(buffer.getvalue()).decode()}
            else:
                if action == 'display/return':
                    guests._focus.pop(display.share_id, None)
                result = display_focus(self.hass, self.manager, display)
                if result.get('focus_revision'):
                    from .guest_focus_media import public_photo
                    photo = public_photo(self.manager, display, result['focus_revision'])
                    if photo is not None:
                        result['photo'] = photo
                invitation = None

            def guard():
                try:
                    actual = state.authorize(token=_bearer(headers), display_id=payload['display_id'],
                                             issuer_epoch=payload['issuer_epoch'])
                    if actual is not display:
                        return False
                    if invitation is not None:
                        guests._share(display.share_id)
                        return (guests._invitations.get(invitation.invitation_id) is invitation
                                and invitation.deadline > state._clock())
                    current = display_focus(self.hass, self.manager, display)
                    return (current['focused_moment_id'] == result['focused_moment_id']
                            and current.get('focus_revision') == result.get('focus_revision'))
                except DisplayAdmissionError:
                    return False
            return self.display._release_result(result, guard, lambda:None, None, state, selected)
