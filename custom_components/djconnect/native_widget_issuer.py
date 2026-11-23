"""Original native register winner -> independently enrolled Widget key owner.

No config/JSON/status constructor and no first-key lifetime extension. Native
clock and SDK target admission remain separate from this backend role custody.
"""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import secrets
import uuid
from weakref import WeakKeyDictionary

from .surface_issuer_owner import IssuerOwnerCapture, WidgetIssuerOwner
from .surface_issuer_responses import ExpectedIssuerReply
from .surface_issuer_wire import DOMAIN, PREFIX, public_key_thumbprint, signing_bytes
from .surface_push_contract import require
from .surface_push_wire import canonical

_ERROR = "native_widget_issuer_unavailable"
_ENROL = "/v1/push/native/installation/issuer/enrol"
_ROLE_DOMAIN = "djc-installation-surface-delegation/1"
_POLICY_EXPIRY = int(datetime.fromisoformat("2026-12-23T10:00:00+00:00").timestamp() * 1000)
_OWNERS = WeakKeyDictionary()


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _operation(now):
    # UUIDv7 operation identity, not a bearer, owner, key or grant witness.
    return str(uuid.UUID(int=(now << 80) | (7 << 76) | (secrets.randbits(12) << 64)
                         | (2 << 62) | secrets.randbits(62)))


def _jwk(spki):
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    from cryptography.hazmat.primitives.asymmetric import ec
    public = load_der_public_key(spki)
    require(isinstance(public, ec.EllipticCurvePublicKey)
            and isinstance(public.curve, ec.SECP256R1), _ERROR, 503)
    point = public.public_numbers()
    def encoded(number):
        return base64.urlsafe_b64encode(number.to_bytes(32, "big")).decode().rstrip("=")
    return {"kty": "EC", "crv": "P-256", "x": encoded(point.x), "y": encoded(point.y)}


@dataclass(repr=False)
class _Role:
    service: object
    first: object
    authority: object
    source: dict = field(repr=False)
    source_current: object = field(repr=False)
    broker: object
    service_generation: object
    installation: object
    transport: object
    publisher: object
    selection: object
    signer: object = field(repr=False)
    spki: bytes = field(repr=False)
    base: IssuerOwnerCapture
    wall: object
    monotonic: object
    last_wall: int
    last_mono: float
    deadline: float
    captures: dict = field(default_factory=dict, repr=False)
    closed: bool = False
    quarantined: bool = False


class CoreWidgetIssuerOwner(WidgetIssuerOwner):
    """Only a genuine register continuation and exact role ACK create an owner."""

    def __new__(cls, *args, **kwargs):
        raise TypeError("Widget issuer owners are created by original enrollment")

    def __repr__(self):
        return "<CoreWidgetIssuerOwner>"

    def __reduce_ex__(self, protocol):
        raise TypeError("Widget issuer owners cannot be serialized")

    def __copy__(self):
        raise TypeError("Widget issuer owners cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("Widget issuer owners cannot be copied")

    @classmethod
    async def enrol(cls, service, operation_id, headers):
        """Internal original-winner port; no endpoint imports a role or key."""
        from .native_enrollment_handoff import _current
        from .native_installation_runtime import InstallationHTTPS
        from .hybrid_service import PairedAuthority
        from .reply_artwork import source_admission

        require(service.api_audience == "djc-native-push/1"
                and type(service.transport) is InstallationHTTPS
                and service._installation is not None, _ERROR, 503)
        witness = await service.take_registered_enrollment(operation_id)
        first_state = _current(witness)
        first = first_state.original
        try:
            identity = {"device_id": first.pair.coordinates[0], "client_type": "ios"}
            authority = await PairedAuthority.resolve(service.hass, identity, dict(headers))
            await witness.validate()
            require(authority.runtime is first.pair.runtime, _ERROR, 403)
            source, source_current = source_admission(service.hass, authority.runtime,
                                                       authority.context.profile_id)
            require(bool(source) and callable(source_current) and source_current(), _ERROR, 403)
            token = await service.original_credential(first)
            await witness.validate()
            now, mono = int(service.wall() * 1000), service.monotonic()
            expiry = min(now + 28_800_000, _POLICY_EXPIRY)
            require(now < expiry, _ERROR, 403)
            receipt = dict(witness.receipt)
            key = _jwk(witness.public_key_spki)
            thumbprint = public_key_thumbprint(key)
            policy = {"token_role": "widget", "platform": "ios", "apns_environment": "sandbox",
                "target": {"app_bundle_id": "dev.djconnect.ios",
                    "extension_bundle_id": "dev.djconnect.ios.track-insight-widget",
                    "widget_kind": "DJConnectSessionWidget"},
                "activity_profile": None, "external_content_allowed": False,
                "original_grant_expires_at_ms": expiry,
                "max_operations": 10000, "max_events": 1000, "max_challenges": 100}
            delegation_id = str(uuid.uuid4())
            binding, device, owner = authority.binding, authority.device, authority.owner
            grant = _hash([_ROLE_DOMAIN, "grant", binding, receipt["registry_generation"]])
            source_binding = _hash([_ROLE_DOMAIN, "source", source])
            scope = _hash([DOMAIN, "delegation", delegation_id, 1,
                receipt["api_installation_id"], device, owner, grant, source_binding,
                binding, thumbprint, policy])
            enrol_operation = _operation(now)
            expected = ExpectedIssuerReply(delegation_id, enrol_operation, thumbprint,
                scope, expiry, now, mono)
            capture = IssuerOwnerCapture(expected, service.transport.origin,
                receipt["api_installation_id"], canonical(key), canonical(policy),
                binding, device, owner, grant, source_binding, object())
            capture.comparisons()
            delegation = {"contract_version": 1, "purpose": "surface_push", "action": "enrol",
                "operation_id": enrol_operation, "delegation_id": delegation_id,
                "expected_revision": 0, "approval_reference": receipt["registry_generation"],
                "install_id": capture.install_id, "binding_id": binding, "device_binding": device,
                "owner_binding": owner, "grant_binding": grant, "source_binding": source_binding,
                "public_key": key, "policy": policy}
            statement = canonical([_ROLE_DOMAIN, "POST", _ENROL, receipt, delegation]).encode()
            signature = await witness.sign(statement)
            # Original checks surround EVERY await and precede the real effect.
            def guard():
                _current(witness)
                authority.validate_now()
                require(source_current() and source_admission(service.hass, authority.runtime,
                    authority.context.profile_id)[0] == source, _ERROR, 403)
                _current(witness)
            guard()
            reply = await service.transport._post(capture.origin, _ENROL,
                {"contract_version": 1, "first_key_receipt": receipt,
                 "delegation": delegation, "signature": signature},
                {"Authorization": "Bearer " + token}, guard=guard, deadline=first_state.deadline)
            guard()
            ack = {"contract_version": 1, "success": True, "state": "enrolled", "replayed": False,
                "delegation_id": delegation_id, "delegation_revision": 1,
                "key_thumbprint": thumbprint, "scope_digest": scope, "expires_at_ms": expiry,
                "enrol_operation_id": enrol_operation,
                "install_credential_id": receipt["install_credential_id"],
                "native_operation_id": receipt["operation_id"],
                "native_api_installation_id": receipt["api_installation_id"],
                "native_registry_generation": receipt["registry_generation"],
                "enrolment_sha256": hashlib.sha256(statement).hexdigest()}
            require(reply.status == 200 and canonical(reply.body) == canonical(ack), _ERROR, 502)
            # This new role is born only from this actual winning HTTP continuation.
            owner_handle = object.__new__(cls)
            _OWNERS[owner_handle] = _Role(service, first, authority, dict(source), source_current,
                first_state.broker, first_state.broker._generation, service._installation,
                service.transport, service.publisher, service.selection, first_state.signer,
                bytes(first_state.spki), capture, service.wall, service.monotonic,
                now, mono, mono + (expiry - now) / 1000)
            owner_handle._live()
            return owner_handle
        finally:
            first_state.broker.discard(witness)

    def _historical(self):
        role = _OWNERS.get(self)
        require(role is not None and not role.quarantined, _ERROR, 403)
        try:
            return self._historical_check(role)
        except BaseException:
            role.quarantined = True
            raise

    def _historical_check(self, role):
        from .native_pair_enrollment import KEY
        service = role.service
        task = asyncio.current_task()
        require(task is not None and not task.cancelling()
                and not service.hass.is_stopping
                and service.hass.data.get("djconnect", {}).get(KEY) is service
                and service._registered_handoffs is role.broker
                and role.broker._generation is role.service_generation
                and service._installation is role.installation
                and service.transport is role.transport and service.publisher is role.publisher
                and service.selection is role.selection and service.wall is role.wall
                and service.monotonic is role.monotonic
                and role.first.authority.sign is role.signer
                and role.first.spki == role.spki, _ERROR, 403)
        role.installation.selected()
        now, mono = int(role.wall() * 1000), role.monotonic()
        require(now >= role.last_wall and mono >= role.last_mono, _ERROR, 403)
        role.last_wall, role.last_mono = now, mono
        return role

    def _live(self):
        role = self._historical()
        try:
            require(not role.closed, _ERROR, 403)
            role.service.guard(role.first.pair, role.first.authority, role.deadline,
                               role.first.consent_current)
            role.authority.validate_now()
            require(role.source_current(), _ERROR, 403)
            role.base.expected.live(int(role.wall() * 1000), role.monotonic())
            self._historical()  # Reentrant owner/source callbacks cannot swap custody.
            return role
        except BaseException:
            role.closed = True
            raise

    def capture_live(self, operation_id):
        role = self._live()
        require(operation_id not in role.captures and len(role.captures) < 100, _ERROR, 503)
        from dataclasses import replace
        capture = replace(role.base, expected=replace(role.base.expected, operation_id=operation_id))
        capture.expected.live_operation(int(role.wall() * 1000))
        capture.comparisons()
        role.captures[operation_id] = capture
        return capture

    def _capture(self, capture, *, live):
        role = self._live() if live else self._historical()
        require(type(capture) is IssuerOwnerCapture
                and role.captures.get(capture.expected.operation_id) is capture, _ERROR, 403)
        return role

    def validate_live(self, capture):
        self._capture(capture, live=True)

    def validate_status(self, capture):
        self._capture(capture, live=False)

    def validate_withdrawal(self, capture):
        self._capture(capture, live=False)

    async def sign(self, capture, path, message, *, action):
        require(action in {"challenge", "issue", "status", "withdraw"}, _ERROR, 403)
        live = action in {"challenge", "issue"}
        role = self._capture(capture, live=live)
        require(type(message) is bytes and 0 < len(message) <= 16384
                and path in {PREFIX + name for name in ("challenge", "issue", "status", "withdraw")},
                _ERROR, 403)
        # Check the existing exact wire, not arbitrary messages through a key oracle.
        payload = json.loads(message)
        require(type(payload) is list and len(payload) == 4 and payload[0] == DOMAIN
                and payload[1] == "POST" and payload[2] == path
                and signing_bytes(path, payload[3]) == message
                and payload[3]["delegation_id"] == capture.expected.delegation_id
                and payload[3]["key_thumbprint"] == capture.expected.key_thumbprint
                and payload[3]["action"] == action, _ERROR, 403)
        require(not live or payload[3]["operation_id"] == capture.expected.operation_id,
                _ERROR, 403)
        require(action != "issue" or payload[3]["scope_digest"] == capture.expected.scope_digest,
                _ERROR, 403)
        if live:
            await role.service.original_credential(role.first)
        self._capture(capture, live=live)
        signature = role.signer(message)
        require(type(signature) is bytes and len(signature) == 64, _ERROR, 503)
        self._capture(capture, live=live)
        return base64.urlsafe_b64encode(signature).decode().rstrip("=")

    def validate_widget_adoption(self, original, service_capture):
        from .surface_widget_adoption import WidgetServiceCapture
        role = self._capture(original, live=True)
        require(type(service_capture) is WidgetServiceCapture
                and service_capture.runtime is role.authority.runtime
                and service_capture.owner_binding == role.authority.owner
                and service_capture.device_binding == role.authority.device
                and service_capture.entry_id == role.first.pair.entry.entry_id
                and service_capture.service.hass is role.service.hass
                and service_capture.source_current(), _ERROR, 403)
        self._live()
