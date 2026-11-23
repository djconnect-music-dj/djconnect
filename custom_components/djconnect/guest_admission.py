"""Temporary guest principals subordinate to the existing live B share.

All transitions run under SessionRuntimeManager's existing lock. This is not
a Profile, pairing registry, Session, conversation engine or effect grant.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import secrets
import time
from typing import Callable

from .display_admission import DisplayAdmissionError, DisplayOwnerBinding

INVITATION_SECONDS = 120
GUEST_LEASE_SECONDS = 60
MAX_GUESTS = 64
MAX_INVITATIONS = 32
MAX_VOICE_ENDPOINTS = 32
MODEL_CALLS_PER_GUEST = 8
MODEL_CALLS_PER_SHARE = 32


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ParticipationPolicy:
    information: bool = False
    requests: str = 'disabled'
    max_pending: int = 3
    screen_focus: bool = False

    def __post_init__(self):
        if (type(self.screen_focus) is not bool or type(self.information) is not bool or not isinstance(self.requests, str) or self.requests not in {'disabled', 'review', 'auto_queue'}
                or type(self.max_pending) is not int or not 1 <= self.max_pending <= 10):
            raise DisplayAdmissionError('guest_policy_invalid', 400)
        if not self.information and (self.requests != 'disabled' or self.screen_focus):
            raise DisplayAdmissionError('guest_policy_invalid', 400)


@dataclass(slots=True, repr=False)
class GuestGrant:
    principal_id: str
    share_id: str
    generation: str
    kind: str
    secret_hash: str
    lease_deadline: float
    endpoint_id: str = ''
    invalidated: Callable[[], None] | None = None
    renew_sequence: int = 0


@dataclass(slots=True, repr=False)
class _Invitation:
    invitation_id: str
    secret_hash: str
    share_id: str
    generation: str
    deadline: float


@dataclass(slots=True, repr=False)
class _Participation:
    owner: DisplayOwnerBinding
    generation: str
    policy: ParticipationPolicy


@dataclass(slots=True, repr=False)
class _VoiceEndpoint:
    endpoint_id: str
    share_id: str
    generation: str
    current: Callable[[], bool]
    admitted_ms: int


class GuestAdmissionState:
    """One child of DisplayAdmissionState; its original share owns every right."""

    def __init__(self, display_state):
        self.display = display_state
        self._policies: dict[str, _Participation] = {}
        self._invitations: dict[str, _Invitation] = {}
        self._guests: dict[str, GuestGrant] = {}
        self._voice: dict[str, _VoiceEndpoint] = {}
        self._attempts: dict[str, tuple[int, float]] = {}
        self._model_guests: dict[str, list[float]] = {}
        self._model_shares: dict[str, list[float]] = {}
        self._requests = None
        self._qr_invites = {}
        self._focus = {}
        self._focus_media_reads = {}
        self._focus_media_attempts = set()
        self._turn_guests = {}
        self._turn_shares = {}

    @property
    def requests(self):
        if self._requests is None:
            from .guest_requests import GuestRequestState
            self._requests = GuestRequestState(self)
        return self._requests

    def _share(self, share_id):
        share = self.display._shares.get(share_id)
        participation = self._policies.get(share_id)
        if (share is None or participation is None or not share.owner.valid()
                or not participation.owner.valid() or share.deadline <= self.display._clock()
                or not participation.policy.information):
            raise DisplayAdmissionError('guest_share_unavailable', 403)
        return share, participation

    def _owner(self, owner, share_id):
        from .guest_host import InstallationAdminConsent
        if type(owner) is InstallationAdminConsent:
            if owner.manager._display_admission is not self.display or not owner.valid():
                raise DisplayAdmissionError('guest_host_unavailable', 403)
        else:
            self.display._owner(owner)
        share = self.display._shares.get(share_id)
        if (share is None or not share.owner.valid() or share.deadline <= self.display._clock()
                or (owner.profile_id, owner.session_id) != (share.owner.profile_id, share.owner.session_id)):
            raise DisplayAdmissionError('guest_share_unavailable', 403)
        return share

    def _drop_guest(self, principal_id):
        grant = self._guests.pop(principal_id, None)
        if grant is not None and self._requests is not None:
            self._requests.prune_guest(grant)
        self._model_guests.pop(principal_id, None)
        self._turn_guests.pop(principal_id, None)
        if grant is not None and grant.invalidated is not None:
            try:
                grant.invalidated()
            except Exception:
                pass  # Withdrawal cannot be rolled back by a transport callback.

    def revoke_share(self, share_id):
        self._focus.pop(share_id, None)
        if self._requests is not None:
            self._requests.prune_share(share_id)
        self._policies.pop(share_id, None)
        self._model_shares.pop(share_id, None)
        self._turn_shares.pop(share_id, None)
        for key, grant in tuple(self._guests.items()):
            if grant.share_id == share_id:
                self._drop_guest(key)
        self.rotate_invitations(share_id)
        for key, endpoint in tuple(self._voice.items()):
            if endpoint.share_id == share_id:
                del self._voice[key]

    def clear(self):
        for share_id in tuple(self._policies):
            self.revoke_share(share_id)
        self._attempts.clear()
        self._focus_media_attempts.clear()

    def prune(self):
        now = self.display._clock()
        for share_id in tuple(self._policies):
            try:
                self._share(share_id)
            except DisplayAdmissionError:
                self.revoke_share(share_id)
        for key, invite in tuple(self._invitations.items()):
            if invite.deadline <= now:
                del self._invitations[key]
        for key, grant in tuple(self._guests.items()):
            try:
                self.validate(grant)
            except DisplayAdmissionError:
                self._drop_guest(key)
        self._attempts = {key: row for key, row in self._attempts.items() if row[1] > now}
        revisions = {row[3] for row in self._focus.values() if row[1] > now}
        self._focus_media_attempts = {key for key in self._focus_media_attempts if key[1] in revisions}

    def configure(self, *, owner, share_id, policy):
        self.prune()
        self._owner(owner, share_id)
        if type(policy) is not ParticipationPolicy:
            raise DisplayAdmissionError('guest_policy_invalid', 400)
        existing = self._policies.get(share_id)
        if existing is None or existing.policy != policy:
            self.revoke_share(share_id)
            if policy.information:
                self._policies[share_id] = _Participation(owner, secrets.token_urlsafe(24), policy)
        return {'information': policy.information, 'requests': policy.requests,
                'max_pending': policy.max_pending, 'screen_focus':policy.screen_focus}

    def rotate_invitations(self, share_id):
        self._qr_invites.pop(share_id, None)
        for key, invite in tuple(self._invitations.items()):
            if invite.share_id == share_id:
                del self._invitations[key]

    def invite(self, *, owner, share_id):
        self.prune()
        self._owner(owner, share_id)
        result = self._issue_invitation(share_id)
        self._qr_invites[share_id] = result
        return dict(result)

    def _issue_invitation(self, share_id):
        share, participation = self._share(share_id)
        self.rotate_invitations(share_id)
        if len(self._invitations) >= MAX_INVITATIONS:
            raise DisplayAdmissionError('guest_capacity', 429)
        identifier, secret = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
        deadline = min(share.deadline, self.display._clock() + INVITATION_SECONDS)
        self._invitations[identifier] = _Invitation(identifier, _hash(secret), share_id,
                                                  participation.generation, deadline)
        return {'invitation_id': identifier, 'invitation_secret': secret,
                'issuer_epoch': self.display.issuer_epoch,
                'expires_in': max(0, deadline - self.display._clock())}

    def display_invitation(self, share_id):
        self.prune()
        self._share(share_id)
        result = self._qr_invites.get(share_id)
        if result is not None and result['invitation_id'] in self._invitations:
            return {**result, 'expires_in':self._invitations[result['invitation_id']].deadline - self.display._clock()}
        result = self._issue_invitation(share_id)
        self._qr_invites[share_id] = result
        return dict(result)

    def redeem(self, *, invitation_id, invitation_secret, issuer_epoch, source):
        self.prune()
        source_key = _hash(str(source)[:128])
        count, deadline = self._attempts.get(source_key, (0, self.display._clock() + 60))
        if count >= 10 or (source_key not in self._attempts and len(self._attempts) >= 256):
            raise DisplayAdmissionError('guest_rate_limited', 429)
        self._attempts[source_key] = count + 1, deadline
        invite = self._invitations.get(invitation_id)
        if (not isinstance(issuer_epoch, str) or not secrets.compare_digest(issuer_epoch, self.display.issuer_epoch)
                or invite is None or not isinstance(invitation_secret, str)
                or not secrets.compare_digest(invite.secret_hash, _hash(invitation_secret))):
            raise DisplayAdmissionError('guest_invitation_invalid', 401)
        share, participation = self._share(invite.share_id)
        if invite.generation != participation.generation:
            raise DisplayAdmissionError('guest_invitation_invalid', 401)
        if len(self._guests) >= MAX_GUESTS:
            raise DisplayAdmissionError('guest_capacity', 429)
        identifier, secret = secrets.token_urlsafe(24), 'djcg_' + secrets.token_urlsafe(32)
        grant = GuestGrant(identifier, share.share_id, participation.generation, 'browser', _hash(secret),
                           min(share.deadline, self.display._clock() + GUEST_LEASE_SECONDS))
        del self._invitations[invitation_id]  # A lost response never issues another grant.
        self._qr_invites.pop(invite.share_id, None)
        self._guests[identifier] = grant
        return {**self.public(grant), 'guest_token': secret, 'issuer_epoch': self.display.issuer_epoch}

    def validate(self, grant):
        if type(grant) is not GuestGrant or self._guests.get(grant.principal_id) is not grant:
            raise DisplayAdmissionError('guest_grant_invalid', 401)
        share, participation = self._share(grant.share_id)
        if (grant.generation != participation.generation or grant.lease_deadline <= self.display._clock()
                or (grant.kind == 'voice' and not self._voice_current(grant))):
            raise DisplayAdmissionError('guest_grant_invalid', 401)
        return share, participation.policy

    def authorize(self, *, guest_id, token, issuer_epoch):
        self.prune()
        grant = self._guests.get(guest_id)
        if (grant is None or grant.kind != 'browser' or not isinstance(token, str)
                or not isinstance(issuer_epoch, str) or not secrets.compare_digest(issuer_epoch, self.display.issuer_epoch)
                or not secrets.compare_digest(grant.secret_hash, _hash(token))):
            raise DisplayAdmissionError('guest_grant_invalid', 401)
        self.validate(grant)
        return grant

    def renew(self, grant, sequence):
        share, _ = self.validate(grant)
        if type(sequence) is not int or sequence < 1:
            raise DisplayAdmissionError('guest_context_changed', 409)
        if sequence == grant.renew_sequence + 1:
            grant.renew_sequence = sequence
            grant.lease_deadline = min(share.deadline, self.display._clock() + GUEST_LEASE_SECONDS)
        elif sequence != grant.renew_sequence:
            raise DisplayAdmissionError('guest_context_changed', 409)
        return self.public(grant)

    def remove(self, *, owner, share_id, guest_id):
        self._owner(owner, share_id)
        grant = self._guests.get(guest_id)
        if grant is not None and grant.share_id == share_id:
            self._drop_guest(guest_id)

    def bind_voice(self, *, owner, share_id, endpoint_id, current):
        self.prune()
        self._owner(owner, share_id)
        _, participation = self._share(share_id)
        def live(callback):
            try:
                return callable(callback) and callback() is True
            except Exception:
                return False
        if (not isinstance(endpoint_id, str) or not endpoint_id or len(endpoint_id) > 128 or not live(current)):
            raise DisplayAdmissionError('guest_voice_endpoint_invalid', 400)
        old = self._voice.get(endpoint_id)
        if old is not None and old.share_id != share_id:
            raise DisplayAdmissionError('guest_voice_endpoint_in_use', 409)
        if old is not None and old.generation == participation.generation and live(old.current):
            return  # Lost host response cannot revoke/recreate an admitted room.
        if endpoint_id not in self._voice and len(self._voice) >= MAX_VOICE_ENDPOINTS:
            raise DisplayAdmissionError('guest_capacity', 429)
        self.unbind_voice(endpoint_id)
        self._voice[endpoint_id] = _VoiceEndpoint(endpoint_id, share_id, participation.generation, current, time.time_ns() // 1_000_000)

    def unbind_voice(self, endpoint_id):
        self._voice.pop(endpoint_id, None)
        for key, grant in tuple(self._guests.items()):
            if grant.kind == 'voice' and grant.endpoint_id == endpoint_id:
                self._drop_guest(key)

    def _voice_current(self, grant):
        endpoint = self._voice.get(grant.endpoint_id)
        try:
            return (endpoint is not None and endpoint.share_id == grant.share_id
                    and endpoint.generation == grant.generation and endpoint.current() is True)
        except Exception:
            return False

    def voice(self, endpoint_id):
        self.prune()
        endpoint = self._voice.get(endpoint_id)
        if endpoint is None:
            raise DisplayAdmissionError('guest_voice_endpoint_invalid', 403)
        share, participation = self._share(endpoint.share_id)
        for grant in self._guests.values():
            if grant.kind == 'voice' and grant.endpoint_id == endpoint_id:
                self.validate(grant)
                grant.lease_deadline = min(share.deadline, self.display._clock() + GUEST_LEASE_SECONDS)
                return grant
        if len(self._guests) >= MAX_GUESTS:
            raise DisplayAdmissionError('guest_capacity', 429)
        grant = GuestGrant(secrets.token_urlsafe(24), endpoint.share_id, participation.generation, 'voice', '',
                           min(share.deadline, self.display._clock() + GUEST_LEASE_SECONDS), endpoint_id)
        if not self._voice_current(grant):
            raise DisplayAdmissionError('guest_voice_endpoint_invalid', 403)
        self._guests[grant.principal_id] = grant
        return grant

    def charge_turn(self, grant):
        self.validate(grant)
        now = self.display._clock()
        guest = [s for s in self._turn_guests.get(grant.principal_id, ()) if s > now - 60]
        share = [s for s in self._turn_shares.get(grant.share_id, ()) if s > now - 60]
        if len(guest) >= 12 or len(share) >= 48:
            raise DisplayAdmissionError('guest_turn_budget', 429)
        self._turn_guests[grant.principal_id] = [*guest, now]
        self._turn_shares[grant.share_id] = [*share, now]

    def charge_model(self, grant):
        self.validate(grant)
        now = self.display._clock()
        guest = [stamp for stamp in self._model_guests.get(grant.principal_id, ()) if stamp > now - 60]
        share = [stamp for stamp in self._model_shares.get(grant.share_id, ()) if stamp > now - 60]
        if len(guest) >= MODEL_CALLS_PER_GUEST or len(share) >= MODEL_CALLS_PER_SHARE:
            raise DisplayAdmissionError('guest_model_budget', 429)
        self._model_guests[grant.principal_id] = [*guest, now]
        self._model_shares[grant.share_id] = [*share, now]

    def public(self, grant):
        _, policy = self.validate(grant)
        return {'guest_id': grant.principal_id,
                'lease_expires_in': max(0, grant.lease_deadline - self.display._clock()),
                'capabilities': {'shared_information': True, 'request_song': policy.requests != 'disabled',
                                 'owner_controls': False, 'profile_history': False, 'music_dna': False, 'screen_focus':policy.screen_focus}}
