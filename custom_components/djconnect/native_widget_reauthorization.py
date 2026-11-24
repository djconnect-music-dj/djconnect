"""Paired, current SQLite consent -> original assertion challenge -> winning role.

RAM operations are not permission. Only an exact actual API winning ACK crosses
this module's private, once-only handoff. No status or imported receipt does so.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import re
import uuid
from weakref import WeakKeyDictionary

from .surface_push_contract import require
from .surface_push_wire import canonical

_ERROR = "native_widget_reauthorization_unavailable"
_DOMAIN = "djc-installation-widget-reauthorization/1"
_PREFIX = "/v1/push/native/installation/issuer/reauthorize/"
_WINNERS = WeakKeyDictionary()


class _Winner:
    def __new__(cls):
        raise TypeError("Only an actual reauthorization ACK creates a winner")

    def __reduce_ex__(self, protocol):
        raise TypeError("Reauthorization winners cannot be serialized")

    def __copy__(self):
        raise TypeError("Reauthorization winners cannot be copied")

    def __deepcopy__(self, memo):
        raise TypeError("Reauthorization winners cannot be copied")


def take_winner(winner):
    record = _WINNERS.pop(winner, None)
    require(record is not None and record.winner is winner, _ERROR, 403)
    record.guard()
    return record


@dataclass(repr=False)
class _Record:
    controller: object
    operation: str
    request: str
    pair: object
    authority: object
    consent_current: object
    spki: bytes
    credential: tuple
    statement: bytes
    digest: str
    challenge: dict
    bindings: dict
    receipt: dict
    delegation: dict
    capture: object
    paired: object
    source: dict
    source_current: object
    deadline: float
    signer: object
    wall: object
    monotonic: object
    guard: object = None
    winner: object = None
    owner: object = None
    attempted: bool = False
    failed: bool = False


class NativeWidgetReauthorization:
    """Bounded operation coordinator owned by the selected native service."""

    def __init__(self, service):
        self.service = service
        self.operations = {}
        self.deadlines = {}

    def _selected(self):
        from .native_installation_runtime import InstallationHTTPS
        from .native_installation_key_custody import InstallationWidgetKeyCustodian
        from .native_pair_enrollment import KEY
        service = self.service
        require(service.hass.data.get("djconnect", {}).get(KEY) is service
                and getattr(service, "_widget_reauthorization", None) is self
                and not service.hass.is_stopping and service.api_audience == "djc-native-push/1"
                and type(service.transport) is InstallationHTTPS
                and type(service.selection) is InstallationWidgetKeyCustodian
                and service._installation is not None, _ERROR, 503)
        service._installation.selected()

    def _caller(self, payload, headers):
        from .direct_rich_pair import capture_pair
        from .transport_operations import operation_created_ms
        require(type(payload) is dict and payload.get("client_type") == "ios", _ERROR, 400)
        operation_created_ms(payload["operation_id"])
        self._selected()
        return capture_pair(self.service.hass, headers, device_id=payload["device_id"], client_type="ios")

    def _original(self, payload, headers):
        pair = self._caller(payload, headers)
        record = self.operations.get(payload["operation_id"])
        require(record is not None and record.pair.registration is pair.registration
                and record.pair.acknowledgement is pair.acknowledgement
                and pair.current() and not record.failed, _ERROR, 409)
        return record

    async def challenge(self, payload, headers):
        from .native_pair_enrollment import ConsentFence, _durable_pair
        from .native_widget_consent import read_widget_consent
        from .native_pair_retirement import NativePairRetirementJournal
        from .hybrid_service import PairedAuthority
        from .reply_artwork import source_admission
        from .native_widget_issuer import _jwk, _hash, _operation, _POLICY_EXPIRY
        from .surface_issuer_wire import DOMAIN, public_key_thumbprint
        from .surface_issuer_owner import IssuerOwnerCapture
        from .surface_issuer_responses import ExpectedIssuerReply
        from .transport_operations import operation_created_ms

        pair = self._caller(payload, headers)
        operation, request = payload["operation_id"], canonical(payload)
        if operation in self.operations:
            record = self._original(payload, headers)
            require(record.request == request and not record.attempted, _ERROR, 409)
            record.guard()
            return self._public_challenge(record)
        service = self.service
        wall, monotonic = service.wall, service.monotonic
        now, mono = int(wall() * 1000), monotonic()
        require(service.wall is wall and service.monotonic is monotonic, _ERROR, 403)
        # Keep successful current owners, never promote historical status. Failed
        # and superseded operations release only RAM capacity after their window.
        for previous, expiry_mono in tuple(self.deadlines.items()):
            if mono < expiry_mono:
                continue
            retained = self.operations.get(previous)
            if retained is not None and retained.owner is not None:
                try:
                    retained.owner._live()
                    continue
                except Exception:
                    pass
            self.operations.pop(previous, None)
            self.deadlines.pop(previous, None)
        require(now - 300_000 < operation_created_ms(operation) <= now + 30_000
                and len(self.operations) < 32, _ERROR, 409)
        # Reserve the identity before any await. Unknown outcomes cannot retry.
        self.operations[operation] = None
        self.deadlines[operation] = mono + 120
        try:
            await _durable_pair(pair)
            token, credential_id = await service.credential(pair)
            binding = pair.registration.binding
            fence = service.consent_fences.setdefault(binding, ConsentFence())
            def consent_current():
                return binding not in service.consent_writes and service.consent_fences.get(binding) is fence
            consent = await read_widget_consent(pair)
            require(consent.enabled and consent_current(), _ERROR, 403)
            authority = await service.selection.capture(pair, channel="widgetkit", existing_only=True)
            spki, signer = authority.public_key_spki, authority.sign
            bindings = {**authority.bindings, "core_key_thumbprint": hashlib.sha256(spki).hexdigest()}
            receipt = payload["first_key_receipt"]
            fields = {"contract_version", "operation_id", "api_installation_id", "install_credential_id",
                "expires_at_ms", "pairing_generation", "core_key_thumbprint", "key_revision",
                "transcript_sha256", "state", "registry_generation",
                "apple_evidence_expires_at_ms", "apple_status_expires_at_ms"}
            require(type(receipt) is dict and set(receipt) == fields
                and type(receipt["contract_version"]) is int and receipt["contract_version"] == 1
                and type(receipt["key_revision"]) is int and receipt["key_revision"] == 1
                and receipt["state"] == "registered" and receipt["install_credential_id"] == credential_id
                and all(receipt[k] == bindings[k] for k in ("pairing_generation", "core_key_thumbprint"))
                and all(type(receipt[k]) is int and 0 < receipt[k] < 2**53 for k in
                    ("expires_at_ms", "apple_evidence_expires_at_ms", "apple_status_expires_at_ms")), _ERROR, 400)
            receipt = dict(receipt)
            paired = await PairedAuthority.resolve(service.hass,
                {"device_id": payload["device_id"], "client_type": "ios"}, dict(headers))
            require(paired.runtime is pair.runtime, _ERROR, 403)
            source, source_current = source_admission(service.hass, paired.runtime, paired.context.profile_id)
            require(source and callable(source_current), _ERROR, 403)
            expiry = min(now + 28_800_000, _POLICY_EXPIRY,
                receipt["apple_evidence_expires_at_ms"], receipt["apple_status_expires_at_ms"])
            require(now < expiry, _ERROR, 403)
            key = _jwk(spki)
            thumbprint = public_key_thumbprint(key)
            policy = {"token_role": "widget", "platform": "ios", "apns_environment": "sandbox",
                "target": {"app_bundle_id": "dev.djconnect.ios",
                    "extension_bundle_id": "dev.djconnect.ios.track-insight-widget",
                    "widget_kind": "DJConnectSessionWidget"}, "activity_profile": None,
                "external_content_allowed": False, "original_grant_expires_at_ms": expiry,
                "max_operations": 10000, "max_events": 1000, "max_challenges": 100}
            delegation_id, enrol_operation = str(uuid.uuid4()), _operation(now)
            grant = _hash([_DOMAIN, "grant", paired.binding, consent.revision, operation])
            source_binding = _hash([_DOMAIN, "source", source])
            scope = _hash([DOMAIN, "delegation", delegation_id, 1, receipt["api_installation_id"],
                paired.device, paired.owner, grant, source_binding, paired.binding, thumbprint, policy])
            expected = ExpectedIssuerReply(delegation_id, enrol_operation, thumbprint, scope, expiry, now, mono)
            capture = IssuerOwnerCapture(expected, service.transport.origin, receipt["api_installation_id"],
                canonical(key), canonical(policy), paired.binding, paired.device, paired.owner,
                grant, source_binding, object())
            capture.comparisons()
            delegation = {"contract_version": 1, "purpose": "surface_push", "action": "enrol",
                "operation_id": enrol_operation, "delegation_id": delegation_id, "expected_revision": 0,
                "approval_reference": receipt["registry_generation"], "install_id": capture.install_id,
                "binding_id": paired.binding, "device_binding": paired.device, "owner_binding": paired.owner,
                "grant_binding": grant, "source_binding": source_binding, "public_key": key, "policy": policy}
            transport, publisher, selection = service.transport, service.publisher, service.selection
            deadline = min(mono + 120, mono + (expiry - now) / 1000)
            credential = (hashlib.sha256(token.encode("ascii")).digest(), credential_id)
            record = _Record(self, operation, request, pair, authority, consent_current, spki, credential,
                b"", "", {}, bindings, receipt, delegation, capture, paired, dict(source), source_current,
                deadline, signer, wall, monotonic)
            last_clock = [now, mono]
            def check_current():
                require(service.wall is wall and service.monotonic is monotonic, _ERROR, 403)
                actual_wall, actual_mono = int(wall() * 1000), monotonic()
                require(service.wall is wall and service.monotonic is monotonic, _ERROR, 403)
                require(last_clock[0] <= actual_wall < min(now + 120_000, expiry)
                    and last_clock[1] <= actual_mono, _ERROR, 403)
                last_clock[:] = [actual_wall, actual_mono]
                self._selected()
                require(self.operations.get(operation) is record and not record.failed
                    and service.transport is transport and service.publisher is publisher
                    and service.selection is selection and authority.sign is signer, _ERROR, 403)
                service.guard(pair, authority, record.deadline, consent_current)
                paired.validate_now()
                require(source_current() and source_admission(service.hass, paired.runtime,
                    paired.context.profile_id)[0] == source, _ERROR, 403)
                self._selected()
                require(service.transport is transport and service.publisher is publisher
                    and service.selection is selection and authority.sign is signer
                    and service.wall is wall and service.monotonic is monotonic
                    and pair.current(), _ERROR, 403)
            def guard():
                try:
                    check_current()
                except BaseException:
                    record.failed = True
                    raise
            record.guard = guard
            self.operations[operation] = record
            async def recheck():
                guard()
                require(await read_widget_consent(pair) == consent, _ERROR, 403)
                await service.original_credential(record)
                guard()
            await recheck()
            publication = {"contract_version": 1, "operation_id": operation, **bindings,
                "install_credential_id": credential_id, "request_expires_at_ms": now + 120_000}
            def current():
                try:
                    guard()
                    return True
                except Exception:
                    return False
            await NativePairRetirementJournal(pair.persistence).stage(pair, transport.origin,
                {**publication, "api_audience": service.api_audience, "event_id": operation},
                consent, publisher.origin, current)
            await recheck()
            await publisher.publish("operation", {**publication, "consent_revision": consent.revision},
                guard=guard, deadline=record.deadline)
            await recheck()
            statement = canonical([_DOMAIN, "POST", _PREFIX + "challenge", receipt, operation, delegation]).encode()
            guard()
            signature = base64.urlsafe_b64encode(signer(statement)).decode().rstrip("=")
            guard()
            record.statement, record.digest = statement, hashlib.sha256(statement).hexdigest()
            reply = await transport._post(transport.origin, _PREFIX + "challenge",
                {"contract_version": 1, "first_key_receipt": receipt,
                 "publication_operation_id": operation, "delegation": delegation, "signature": signature},
                {"Authorization": "Bearer " + token}, guard=guard, deadline=record.deadline)
            await recheck()
            challenge = reply.body
            require(reply.status == 200 and type(challenge) is dict and set(challenge) == {
                "contract_version", "api_audience", "challenge_id", "challenge_nonce", "expires_at_ms",
                "publication_operation_id", "first_key_receipt_sha256", "delegation_sha256"}
                and type(challenge["contract_version"]) is int and challenge["contract_version"] == 1
                and challenge["api_audience"] == service.api_audience
                and challenge["publication_operation_id"] == operation
                and challenge["first_key_receipt_sha256"] == _hash(receipt)
                and challenge["delegation_sha256"] == _hash(delegation)
                and type(challenge["challenge_id"]) is str
                and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", challenge["challenge_id"])
                and type(challenge["challenge_nonce"]) is str
                and re.fullmatch(r"[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]", challenge["challenge_nonce"])
                and type(challenge["expires_at_ms"]) is int
                and int(wall() * 1000) < challenge["expires_at_ms"] <= min(now + 120_000, expiry),
                _ERROR, 502)
            record.challenge = dict(challenge)
            record.deadline = min(record.deadline, monotonic() +
                (challenge["expires_at_ms"] - int(wall() * 1000)) / 1000)
            guard()
            return self._public_challenge(record)
        except BaseException:
            record = self.operations.get(operation)
            if record is not None:
                record.failed = True
            raise

    def _public_challenge(self, record):
        # Round-trip copies prevent a renderer mutating retained signing inputs.
        import json
        transcript = canonical([_DOMAIN, "POST", _PREFIX + "register", record.challenge,
            record.receipt, record.delegation]).encode()
        return json.loads(canonical({"contract_version": 1, "api_audience": "djc-native-push/1",
            "operation_id": record.operation, "challenge": record.challenge,
            "first_key_receipt": record.receipt, "delegation": record.delegation,
            "client_data_hash_b64": base64.b64encode(hashlib.sha256(transcript).digest()).decode()}))

    async def register(self, payload, headers):
        record = self._original(payload, headers)
        require(not record.attempted and record.owner is None, _ERROR, 409)
        proof = payload["apple_proof"]
        require(type(proof) is dict and set(proof) == {"kind", "key_id_b64", "proof_b64"}
            and proof["kind"] == "assertion", _ERROR, 400)
        for name, minimum, maximum in (("key_id_b64", 32, 32), ("proof_b64", 1, 9216)):
            require(type(proof[name]) is str, _ERROR, 400)
            raw = base64.b64decode(proof[name], validate=True)
            require(minimum <= len(raw) <= maximum and base64.b64encode(raw).decode() == proof[name], _ERROR, 400)
        record.guard()
        record.attempted = True
        try:
            service = self.service
            token = await service.original_credential(record)
            record.guard()
            reply = await service.transport._post(service.transport.origin, _PREFIX + "register",
                {"contract_version": 1, "challenge": record.challenge, "first_key_receipt": record.receipt,
                 "delegation": record.delegation, "apple_proof": dict(proof)},
                {"Authorization": "Bearer " + token}, guard=record.guard, deadline=record.deadline)
            record.guard()
            expected = record.capture.expected
            ack = {"contract_version": 1, "success": True, "state": "enrolled", "replayed": False,
                "delegation_id": expected.delegation_id, "delegation_revision": 1,
                "key_thumbprint": expected.key_thumbprint, "scope_digest": expected.scope_digest,
                "expires_at_ms": expected.original_grant_expires_ms,
                "enrol_operation_id": expected.operation_id,
                "install_credential_id": record.receipt["install_credential_id"],
                "native_operation_id": record.receipt["operation_id"],
                "native_api_installation_id": record.receipt["api_installation_id"],
                "native_registry_generation": record.receipt["registry_generation"],
                "enrolment_sha256": record.digest, "publication_operation_id": record.operation,
                "reauthorization_challenge_id": record.challenge["challenge_id"]}
            require(reply.status == 200 and canonical(reply.body) == canonical(ack), _ERROR, 502)
            winner = object.__new__(_Winner)
            record.winner = winner
            _WINNERS[winner] = record
            from .native_widget_issuer import CoreWidgetIssuerOwner
            from .native_widget_preparation import accept_reauthorized_winner
            owner = CoreWidgetIssuerOwner.from_reauthorization(winner)
            accept_reauthorized_winner(service, owner)
            record.owner = owner
            return self._ready(record)
        except BaseException:
            record.failed = True
            if record.winner is not None:
                _WINNERS.pop(record.winner, None)
            if record.owner is not None:
                record.owner.fence_live()
            raise

    def _ready(self, record):
        self._selected()
        require(record.owner is not None and not record.failed, _ERROR, 409)
        record.owner._live()
        return {"contract_version": 1, "operation_id": record.operation, "state": "ready"}

    async def status(self, payload, headers):
        return self._ready(self._original(payload, headers))
