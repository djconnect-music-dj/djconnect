"""Original winning first-key custody, not an issuer grant or native permission.

Only NativePairEnrollment's successful register continuation publishes a handle.
It retains the same original pair, consent fence, signer and API ACK in RAM under
both ORIGINAL deadlines. Status, replay, restart and client JSON cannot create
one. Taking is once-only; withdrawal/unload/cancellation closes it before use.
A future WidgetIssuerOwner still needs its own genuinely enrolled widget policy.
No first-key binding is converted into a surface binding or a new clock/lease.
The producer remains its existing iOS/widgetkit path; this grants no other channel.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import MappingProxyType
from weakref import WeakKeyDictionary, WeakSet

from .surface_push_contract import SurfacePushError, require
from .surface_push_wire import canonical

_STATES = WeakKeyDictionary()
_ERROR = "native_enrollment_handoff_unavailable"


class RegisteredEnrollmentWitness:
    """Opaque server-private custody. There is no affirmative public constructor."""
    __slots__ = ("__weakref__",)

    def __new__(cls, *args, **kwargs):
        raise TypeError("Registered enrollment witnesses are server-owned")

    def __repr__(self):
        return "<RegisteredEnrollmentWitness>"

    def __reduce_ex__(self, protocol):
        raise TypeError("Registered enrollment witnesses cannot be serialized")

    def __copy__(self):
        raise TypeError("Registered enrollment witnesses cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("Registered enrollment witnesses cannot be copied")

    async def validate(self):
        """Recheck actual credential custody as well as original RAM currentness."""
        state = _current(self)
        try:
            await state.owner.original_credential(state.original)
            _current(self)
        except BaseException:
            state.broker.discard(self)
            raise

    @property
    def receipt(self):
        """Read-only original ACK DATA; never a replacement authority object."""
        return MappingProxyType(dict(_current(self).receipt))

    @property
    def original_pair(self):
        return _current(self).pair

    @property
    def public_key_spki(self):
        return _current(self).spki

    async def sign(self, statement):
        """Guard the retained signer; no issuer policy or operation budget is supplied."""
        require(type(statement) is bytes and 0 < len(statement) <= 16384, _ERROR, 403)
        await self.validate()
        state = _current(self)
        try:
            signed = state.original.sign(statement)
            _current(self)
            return signed
        except BaseException:
            state.broker.discard(self)
            raise


@dataclass(eq=False, repr=False)
class _Attempt:
    owner: object
    original: object
    deadline: float
    reservation: object
    task: object
    generation: object
    custody: object


@dataclass(repr=False)
class _Custody:
    broker: object
    owner: object
    original: object
    deadline: float
    task: object
    pair: object
    authority: object
    consent_current: object
    signer: object
    spki: bytes
    credential: tuple
    challenge: str
    bindings: str
    statement: bytes
    digest: str
    receipt: tuple
    wall: object
    monotonic: object
    service: tuple
    last_wall_ms: int
    last_monotonic: float
    claimed: bool = False


def _current(witness):
    state = _STATES.get(witness)
    require(state is not None, _ERROR, 403)
    try:
        task = asyncio.current_task()
        require(task is not None and not task.cancelling() and not state.task.cancelling(), _ERROR, 403)
        require(state.owner._registered_handoffs is state.broker
                and state.owner.wall is state.wall and state.owner.monotonic is state.monotonic, _ERROR, 403)
        wall_ms, mono = int(state.wall() * 1000), state.monotonic()
        require(wall_ms >= state.last_wall_ms and mono >= state.last_monotonic, _ERROR, 403)
        state.last_wall_ms, state.last_monotonic = wall_ms, mono
        require(state.owner.transport is state.service[0] and state.owner.publisher is state.service[1]
                and state.owner.selection is state.service[2]
                and state.owner.transport.origin == state.service[3], _ERROR, 403)
        original = state.original
        require(original.pair is state.pair and original.authority is state.authority
                and original.consent_current is state.consent_current
                and original.authority.sign is state.signer and original.spki == state.spki
                and original.credential == state.credential and original.statement == state.statement
                and original.digest == state.digest and canonical(original.challenge) == state.challenge
                and canonical(original.bindings) == state.bindings, _ERROR, 403)
        state.owner.guard(state.pair, state.authority, state.deadline, state.consent_current)
        wall_ms, mono = int(state.wall() * 1000), state.monotonic()
        require(state.last_wall_ms <= wall_ms < original.challenge["expires_at_ms"]
                and state.last_monotonic <= mono < state.deadline, _ERROR, 403)
        state.last_wall_ms, state.last_monotonic = wall_ms, mono
        original.receipt(dict(state.receipt))
        require(_STATES.get(witness) is state and not task.cancelling()
                and not state.task.cancelling(), _ERROR, 403)
        return state
    except BaseException:
        state.broker.discard(witness)
        raise


class _RegisteredEnrollmentHandoffs:
    """One service lifetime; no Store, HTTP lookup or positive restoration path."""
    def __init__(self, owner):
        self.owner = owner
        self._available = {}
        self._issued = WeakSet()
        self._attempts = set()
        self._generation = object()

    def begin(self, original, deadline, reservation):
        for witness in tuple(self._issued):
            try:
                _current(witness)
            except SurfacePushError:
                pass
        require(len(self._issued) + len(self._attempts) < 32, _ERROR, 503)
        task = asyncio.current_task()
        require(task is not None and not task.cancelling(), _ERROR, 403)
        # Capture BEFORE the register request can yield: its continuation may
        # validate only this original custody, never a late replacement signer.
        custody = _Custody(self, self.owner, original, deadline, task,
            original.pair, original.authority, original.consent_current, original.authority.sign,
            bytes(original.spki), original.credential, canonical(original.challenge), canonical(original.bindings),
            bytes(original.statement), original.digest, (), self.owner.wall, self.owner.monotonic,
            (self.owner.transport, self.owner.publisher, self.owner.selection, self.owner.transport.origin),
            int(self.owner.wall() * 1000), self.owner.monotonic())
        attempt = _Attempt(self.owner, original, deadline, reservation, task, self._generation, custody)
        self._attempts.add(attempt)
        return attempt

    def abort(self, attempt):
        self._attempts.discard(attempt)

    def publish(self, attempt, receipt):
        original = attempt.original
        require(attempt in self._attempts and attempt.owner is self.owner and attempt.generation is self._generation
                and asyncio.current_task() is attempt.task and not attempt.task.cancelling()
                and self.owner.pending.get(original.pair.device_id) is attempt.reservation, _ERROR, 403)
        self.owner.guard(original.pair, original.authority, attempt.deadline, original.consent_current)
        original.receipt(receipt)
        operation = original.challenge["operation_id"]
        require(operation not in self._available, _ERROR, 403)
        witness = object.__new__(RegisteredEnrollmentWitness)
        attempt.custody.receipt = tuple(receipt.items())
        _STATES[witness] = attempt.custody
        self._issued.add(witness)
        try:
            _current(witness)
            self._available[operation] = witness
        except BaseException:
            self.discard(witness)
            raise

    async def take(self, operation):
        witness = self._available.pop(operation, None)
        require(witness is not None, _ERROR, 403)
        state = _current(witness)
        require(not state.claimed, _ERROR, 403)
        state.claimed = True  # Consume BEFORE the credential-read await.
        await witness.validate()
        return witness

    def discard(self, witness):
        state = _STATES.pop(witness, None)
        self._issued.discard(witness)
        if state is not None:
            operation = state.original.challenge.get("operation_id")
            if self._available.get(operation) is witness:
                self._available.pop(operation, None)

    def withdraw_pair(self, registration):
        for attempt in tuple(self._attempts):
            if attempt.original.pair.registration is registration:
                self._attempts.discard(attempt)
        for witness in tuple(self._issued):
            if _STATES[witness].pair.registration is registration:
                self.discard(witness)

    def invalidate(self):
        self._generation = object()
        self._attempts.clear()
        for witness in tuple(self._issued):
            self.discard(witness)
