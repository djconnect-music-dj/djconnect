"""Cast-only transport admission into real B owners; no replacement principal."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re
import secrets
import weakref

from .display_admission import DisplayAdmissionError
from .display_service import DisplayAdmissionService, _shape, _KEEP_DEFAULT
from .cast_sender import CastSender, receiver_id

RECEIVER_ORIGIN = "https://receiver.djconnect.dev"
OWNER_ACTIONS = ("owner/bootstrap", "owner/launch")
BOOTSTRAP_TTL = 30
MAX_BOOTSTRAPS = 32
MAX_OWNER_BOOTSTRAPS = 2
BROWSER_ACTIONS = frozenset({"claim", "collect", "cancel", "renew", "leave", "snapshot", "artwork"})
PARTICIPATION_ACTIONS = frozenset({"invitation", "focus", "return", "focus-photo", "presentation"})


def _token(headers, prefix):
    raw = headers.get("Authorization", "")
    if (
        not isinstance(raw, str)
        or re.fullmatch("Bearer " + prefix + r"[A-Za-z0-9_-]{43}", raw) is None
    ):
        raise DisplayAdmissionError("cast_bootstrap_unavailable", 401)
    return raw[7:]


@dataclass(slots=True, repr=False)
class _Binding:
    owner: object
    broadcast_ref: object
    origin: str
    epoch: str
    deadline: float
    claim: object = None
    display: object = None
    withdrawn: bool = False

    def current(self, service):
        if self.withdrawn:
            return False
        state = service.manager._display_admission
        try:
            service._origin(self.origin)
            active = service.manager.current_active(self.owner.profile_id)
            valid = (
                state.issuer_epoch == self.epoch
                and self.owner.valid()
                and active is not None
                and active.session_id == self.owner.session_id
                and self.broadcast_ref() is not None
                and active.broadcast is self.broadcast_ref()
            )
        except DisplayAdmissionError:
            valid = False
        self.withdrawn = not valid
        return valid

    def approved_owner(self):
        actual = (
            self.display.owner if self.display is not None else getattr(self.claim, "owner", None)
        )
        return actual is None or (
            actual.stamp == self.owner.stamp
            and actual.entry_id == self.owner.entry_id
            and actual.profile_id == self.owner.profile_id
            and actual.session_id == self.owner.session_id
            and actual.valid()
        )


class _Registry:
    def __init__(self):
        self.tokens = {}
        self.claims = {}
        self.displays = {}
        self.launches = set()

    def prune(self, service):
        state = service.manager._display_admission
        state.prune()
        self.tokens = {
            key: row
            for key, row in self.tokens.items()
            if row.deadline > state._clock() and row.current(service)
        }
        self.claims = {
            key: row
            for key, row in self.claims.items()
            if state._claims.get(key) is row.claim and row.current(service)
        }
        self.displays = {
            key: row
            for key, row in self.displays.items()
            if state._displays.get(key) is row.display and row.current(service)
        }


def registry(manager):
    value = getattr(manager, "_cast_display_registry", None)
    if value is None:
        value = manager._cast_display_registry = _Registry()
    return value


def require_cast_display(hass, manager, display):
    service = DisplayAdmissionService(hass, manager)
    row = registry(manager).displays.get(display.display_id)
    if (
        row is None
        or row.display is not display
        or not row.current(service)
        or not row.approved_owner()
    ):
        raise DisplayAdmissionError("display_grant_invalid", 401)
    return row


class CastDisplayService:
    def __init__(self, hass, manager):
        self.hass, self.manager = hass, manager
        self.display = DisplayAdmissionService(hass, manager)

    def _require(self, row):
        if row is None or not row.current(self.display) or not row.approved_owner():
            raise DisplayAdmissionError("display_context_changed", 409)
        return row

    def _guard_result(self, result, row):
        original = result.release

        def release():
            self._require(row)
            original()
            self._require(row)

        return replace(result, release=release)

    async def _bootstrap(self, payload, headers, origins):
        if (
            not isinstance(payload, dict)
            or set(payload) != {"contract_version", "identity", "session_id"}
            or type(payload.get("contract_version")) is not int
            or payload["contract_version"] != 1
            or not isinstance(payload["session_id"], str)
            or not 0 < len(payload["session_id"]) <= 256
        ):
            raise DisplayAdmissionError("display_code_invalid", 400)
        selected, _ = await self.display._initial_origin("owner/context", origins)
        owner = await self.display._request_owner(
            "owner/bootstrap", payload, headers, selected, owner_action=True
        )
        async with self.manager._lock:
            self.display._sync_origin(self.display._origin(selected))
            state = self.manager._display_admission
            active = self.manager.current_active(owner.profile_id)
            if not owner.valid() or active is None or active.session_id != payload["session_id"]:
                raise DisplayAdmissionError("display_context_changed", 409)
            records = registry(self.manager)
            records.prune(self.display)
            if (
                len(records.tokens) >= MAX_BOOTSTRAPS
                or sum(row.owner.profile_id == owner.profile_id for row in records.tokens.values())
                >= MAX_OWNER_BOOTSTRAPS
            ):
                raise DisplayAdmissionError("display_capacity", 429)
            row = _Binding(
                owner,
                weakref.ref(active.broadcast),
                selected,
                state.issuer_epoch,
                state._clock() + BOOTSTRAP_TTL,
            )
            token = "djccb_" + secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).hexdigest()
            records.tokens[digest] = row

            def current():
                return (
                    row.current(self.display)
                    and row.deadline > state._clock()
                    and records.tokens.get(digest) is row
                )

            return self.display._release_result(
                {
                    "bootstrap_token": token,
                    "bootstrap_expires_in": BOOTSTRAP_TTL,
                    "ha_origin": selected,
                    "receiver_origin": RECEIVER_ORIGIN,
                    "issuer_epoch": state.issuer_epoch,
                    "session_id": active.session_id,
                },
                current,
                lambda: None,
                None,
                state,
                selected,
            )

    async def _launch(self, payload, headers, origins):
        if not isinstance(payload, dict) or set(payload) != {
            "contract_version", "identity", "session_id", "receiver_id"
        }:
            raise DisplayAdmissionError("display_code_invalid", 400)
        target = receiver_id(payload["receiver_id"])
        identity = payload["identity"]
        if origins or not isinstance(identity, dict) or identity.get("client_type") != "macos":
            raise DisplayAdmissionError("display_origin_denied", 403)
        bootstrap = await self._bootstrap(
            {key: value for key, value in payload.items() if key != "receiver_id"}, headers, origins
        )
        wire = bootstrap.payload
        state = self.manager._display_admission
        records = registry(self.manager)
        digest = hashlib.sha256(wire["bootstrap_token"].encode()).hexdigest()
        row = records.tokens.get(digest)
        self._require(row)
        if target in records.launches or len(records.launches) >= MAX_OWNER_BOOTSTRAPS:
            records.tokens.pop(digest, None)
            raise DisplayAdmissionError("display_capacity", 429)
        records.launches.add(target)
        known_hosts = [
            host
            for entry in self.hass.config_entries.async_entries("cast")
            for host in entry.data.get("known_hosts", [])
        ]
        sender = CastSender(target, known_hosts)
        handoff = secrets.token_hex(16)
        try:
            await self.hass.async_add_executor_job(sender.connect)
            bootstrap.release()
            await self.hass.async_add_executor_job(sender.launch)
            bootstrap.release()
            reply = await self.hass.async_add_executor_job(sender.claim, {
                "kind": "vibecast_display_bootstrap",
                "version": 1,
                "handoff_id": handoff,
                "ha_origin": wire["ha_origin"],
                "bootstrap_token": wire["bootstrap_token"],
                "expires_in": row.deadline - state._clock(),
            })
            async with self.manager._lock:
                self._require(row)
                claim = row.claim
                if not isinstance(reply, dict) or claim is None or (
                    reply.get("kind") != "vibecast_display_claim"
                    or type(reply.get("version")) is not int or reply["version"] != 1
                    or reply.get("handoff_id") != handoff
                    or reply.get("issuer_epoch") != row.epoch
                    or reply.get("claim_id") != claim.claim_id
                    or reply.get("browser_generation") != claim.generation
                    or reply.get("code") != claim.code
                ):
                    raise DisplayAdmissionError("cast_receiver_unavailable", 503)

                def current():
                    return (
                        row.current(self.display)
                        and state._claims.get(claim.claim_id) is claim
                        and claim.deadline > state._clock()
                    )

                return self.display._release_result({
                    "issuer_epoch": row.epoch, "claim_id": claim.claim_id,
                    "browser_generation": claim.generation, "code": claim.code,
                }, current, lambda: None, None, state, row.origin)
        finally:
            records.tokens.pop(digest, None)
            try:
                await self.hass.async_add_executor_job(sender.close)
            finally:
                records.launches.discard(target)

    def _claim(self, payload, headers, source, selected):
        _shape("claim", payload)
        if set(payload) != {"contract_version", "browser_nonce"}:
            raise DisplayAdmissionError("display_code_invalid", 400)
        token = _token(headers, "djccb_")
        records = registry(self.manager)
        state = self.manager._display_admission
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = records.tokens.get(digest)
        if row is None or row.deadline <= state._clock():
            raise DisplayAdmissionError("cast_bootstrap_unavailable", 404)
        self._require(row)
        outcome = self.display._claim(state, {"browser_nonce": payload["browser_nonce"]}, source)
        row.claim = state._claims[outcome.payload["claim_id"]]
        row.claim.cast_owner = row.owner
        records.claims[row.claim.claim_id] = row
        del records.tokens[digest]
        result = self.display._release_result(
            outcome.payload, outcome.guard, lambda: None, None, state, selected
        )
        return self._guard_result(result, row)

    async def _participation(self, action, payload, headers, selected):
        from .guest_service import GuestParticipationService, shape

        actual = action.removeprefix("participation/")
        shape(actual, payload)
        async with self.manager._lock:
            display = self.manager._display_admission.authorize(
                token=_token(headers, "djcd_"),
                display_id=payload["display_id"],
                issuer_epoch=payload["issuer_epoch"],
            )
            row = require_cast_display(self.hass, self.manager, display)
        service = GuestParticipationService(self.hass, self.manager)
        if actual == "display/focus-photo":
            from .guest_focus_media import prepare

            result = await prepare(service, payload, headers, selected)
        else:
            def cast_authority(current):
                if require_cast_display(self.hass, self.manager, current) is not row:
                    raise DisplayAdmissionError("display_context_changed", 403)

            result = await service._display_action(actual, payload, headers, selected, cast_authority=cast_authority)
        return self._guard_result(result, row)

    async def post(self, action, payload, *, headers, origins, source):
        if action == "owner/bootstrap":
            return await self._bootstrap(payload, headers, origins)
        if action == "owner/launch":
            return await self._launch(payload, headers, origins)
        if tuple(origins) != (RECEIVER_ORIGIN,):
            raise DisplayAdmissionError("display_origin_denied", 403)
        if action not in BROWSER_ACTIONS and action not in {
            "participation/display/" + name for name in PARTICIPATION_ACTIONS
        }:
            raise DisplayAdmissionError("display_code_invalid", 400)
        selected = self.display._origin()
        async with self.manager._lock:
            self.display._sync_origin(self.display._origin(selected))
            records = registry(self.manager)
            records.prune(self.display)
            if action == "claim":
                return self._claim(payload, headers, source, selected)
            if not action.startswith("participation/"):
                return self._browser_action(action, payload, headers, source, selected)
        return await self._participation(action, payload, headers, selected)

    def _browser_action(self, action, payload, headers, source, selected):
        _shape(action, payload)
        state = self.manager._display_admission
        records = registry(self.manager)
        if action in {"collect", "cancel"}:
            row = records.claims.get(payload["claim_id"])
            if row is None or state._claims.get(payload["claim_id"]) is not row.claim:
                raise DisplayAdmissionError("display_claim_unavailable", 404)
        else:
            actual = state.authorize(
                token=_token(headers, "djcd_"),
                display_id=payload["display_id"],
                issuer_epoch=payload["issuer_epoch"],
            )
            row = require_cast_display(self.hass, self.manager, actual)
        self._require(row)
        args = {key: value for key, value in payload.items() if key != "contract_version"}
        outcome = self.display._dispatch_action(
            action, state, None, selected, args, headers, source, payload
        )
        if action == "collect" and outcome.payload.get("state") == "admitted":
            row.display = state._displays[outcome.payload["display_id"]]
            records.displays[row.display.display_id] = row
            records.claims.pop(row.claim.claim_id, None)
            row.claim = None
        elif action == "cancel":
            records.claims.pop(payload["claim_id"], None)
        elif action == "leave":
            records.displays.pop(payload["display_id"], None)
        guard = outcome.guard if outcome.guard is not _KEEP_DEFAULT else lambda: True
        complete = outcome.complete if outcome.complete is not _KEEP_DEFAULT else lambda: None
        result = self.display._release_result(
            outcome.payload, guard, complete, outcome.media, state, selected
        )
        return self._guard_result(result, row)
