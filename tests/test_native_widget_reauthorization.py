"""Actual Core P256/SQLite coordinator; explicitly MODEL API/Apple proof seams."""
import base64
import hashlib
import json
import os
import uuid
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from tests import test_native_widget_preparation as fixture
from custom_components.djconnect import native_widget_reauthorization as reauth
from custom_components.djconnect import native_widget_issuer as issuer
from custom_components.djconnect.surface_issuer_transport import IssuerHTTPReply
from custom_components.djconnect.surface_push_contract import SurfacePushError
from custom_components.djconnect.surface_push_wire import canonical


class NativeWidgetReauthorizationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.f = fixture.NativeWidgetPreparationTests()
        await self.f.asyncSetUp()
        self.native = self.f.unit.f.service
        self.headers = self.f.unit.f.headers
        self.old_owner = self.f.record.owner
        # Initial owner retains the exact acknowledged receipt only as test data.
        self.receipt = dict(self.f.unit.role_calls[0]["first_key_receipt"])
        await self.native.consent(self.headers, enabled=False, operation_id=str(uuid.uuid4()), expected_revision=1)
        await self.native.consent(self.headers, enabled=True, operation_id=str(uuid.uuid4()), expected_revision=2)
        self.controller = reauth.NativeWidgetReauthorization(self.native)
        self.native._widget_reauthorization = self.controller
        self.original_http = self.native.transport._post
        self.native.transport._post = self.http
        self.calls = []
        self.hook = None
        self.corrupt = False
        self.consent_revision = 3
        self.payload = {"device_id": self.f.unit.f.runtime.pairing_device_id, "client_type": "ios",
            "operation_id": issuer._operation(int(self.native.wall() * 1000)),
            "first_key_receipt": self.receipt}
        self.proof = {"kind": "assertion", "key_id_b64": base64.b64encode(b"M" * 32).decode(),
            "proof_b64": base64.b64encode(b"MODEL-only-not-Apple-proof").decode()}

    async def asyncTearDown(self):
        await self.f.asyncTearDown()

    async def http(self, origin, path, body, headers, *, guard, deadline):
        if not path.startswith(reauth._PREFIX):
            return await self.original_http(origin, path, body, headers, guard=guard, deadline=deadline)
        guard()
        self.calls.append((path, body))
        record = self.controller.operations[self.payload["operation_id"]]
        if path.endswith("challenge"):
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec, utils
            from cryptography.hazmat.primitives.serialization import load_der_public_key
            raw = base64.urlsafe_b64decode(body["signature"] + "==")
            statement = canonical([reauth._DOMAIN, "POST", path, body["first_key_receipt"],
                body["publication_operation_id"], body["delegation"]]).encode()
            load_der_public_key(record.spki).verify(utils.encode_dss_signature(
                int.from_bytes(raw[:32]), int.from_bytes(raw[32:])), statement, ec.ECDSA(hashes.SHA256()))
            # Confirm the durable SQL original exists before the network effect.
            rows = await record.pair.persistence.async_in_transaction(lambda tx: tx.fetchone(
                "SELECT consent_revision FROM djconnect_native_pair_retirements WHERE event_id=?",
                (record.operation,)))
            self.assertEqual(rows[0], self.consent_revision)
            response = {"contract_version": 1, "api_audience": "djc-native-push/1",
                "challenge_id": "MODEL-challenge", "challenge_nonce": "A" * 43,
                "expires_at_ms": int(self.native.wall() * 1000) + 60000,
                "publication_operation_id": record.operation,
                "first_key_receipt_sha256": issuer._hash(record.receipt),
                "delegation_sha256": issuer._hash(record.delegation)}
        else:
            expected = record.capture.expected
            response = {"contract_version": 1, "success": True, "state": "enrolled", "replayed": self.corrupt,
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
        if self.hook:
            await self.hook()
        guard()
        return IssuerHTTPReply(200, response)

    def register_body(self):
        return {key: value for key, value in self.payload.items() if key != "first_key_receipt"} | {
            "apple_proof": self.proof}

    async def test_actual_winning_ack_replaces_fenced_owner_and_status_retains_original(self):
        challenge = await self.controller.challenge(self.payload, self.headers)
        transcript = canonical([reauth._DOMAIN, "POST", reauth._PREFIX + "register", challenge["challenge"],
            challenge["first_key_receipt"], challenge["delegation"]]).encode()
        self.assertEqual(challenge["client_data_hash_b64"], base64.b64encode(hashlib.sha256(transcript).digest()).decode())
        self.assertEqual(await self.controller.challenge(self.payload, self.headers), challenge)
        self.assertEqual(len(self.calls), 1)
        result = await self.controller.register(self.register_body(), self.headers)
        self.assertEqual(result, {"contract_version": 1, "operation_id": self.payload["operation_id"], "state": "ready"})
        owner = self.controller.operations[self.payload["operation_id"]].owner
        self.assertIsNot(owner, self.old_owner)
        owner._live()
        with self.assertRaises(SurfacePushError):
            self.old_owner._live()
        self.assertIs(self.f.pool.roles[id(self.f.record.registration)].owner, owner)
        body = {k: v for k, v in self.payload.items() if k != "first_key_receipt"}
        self.assertEqual(await self.controller.status(body, self.headers), result)
        with self.assertRaises(SurfacePushError):
            await self.controller.register(self.register_body(), self.headers)
        if os.environ.get("DJCONNECT_REAUTH_FIXTURE"):
            Path(os.environ["DJCONNECT_REAUTH_FIXTURE"]).write_text(json.dumps({
                "boundary": "MODEL API/Apple proof; actual Core P256 and SQLite producer",
                "challenge_response": challenge, "canonical_client_data_utf8": transcript.decode(),
                "client_data_sha256_hex": hashlib.sha256(transcript).hexdigest(),
                "register_ready_response": result, "status_ready_response": result}, indent=2) + "\n")

    async def test_unknown_status_cannot_restore_or_create(self):
        with self.assertRaises(SurfacePushError):
            await self.controller.status(self.payload, self.headers)
        self.assertEqual(self.calls, [])

    async def test_replayed_ack_cannot_create_owner(self):
        await self.controller.challenge(self.payload, self.headers)
        self.corrupt = True
        with self.assertRaises(SurfacePushError):
            await self.controller.register(self.register_body(), self.headers)
        self.assertIsNone(self.controller.operations[self.payload["operation_id"]].owner)

    async def test_consent_withdrawn_during_await_cannot_create_owner(self):
        await self.controller.challenge(self.payload, self.headers)
        async def withdraw():
            await self.native.consent(self.headers, enabled=False, operation_id=str(uuid.uuid4()), expected_revision=3)
        self.hook = withdraw
        with self.assertRaises(SurfacePushError):
            await self.controller.register(self.register_body(), self.headers)
        self.assertIsNone(self.controller.operations[self.payload["operation_id"]].owner)

    async def test_restart_has_no_positive_status(self):
        await self.controller.challenge(self.payload, self.headers)
        await self.controller.register(self.register_body(), self.headers)
        replacement = reauth.NativeWidgetReauthorization(self.native)
        self.native._widget_reauthorization = replacement
        with self.assertRaises(SurfacePushError):
            await replacement.status(self.payload, self.headers)

    async def test_caller_cannot_replace_retained_challenge_data(self):
        challenge = await self.controller.challenge(self.payload, self.headers)
        challenge["delegation"]["policy"]["original_grant_expires_at_ms"] += 1000
        record = self.controller.operations[self.payload["operation_id"]]
        self.assertNotEqual(challenge["delegation"], record.delegation)
        changed = dict(self.payload, first_key_receipt=dict(self.receipt, core_key_thumbprint="f" * 64))
        with self.assertRaises(SurfacePushError):
            await self.controller.challenge(changed, self.headers)

    async def test_missing_original_key_does_not_generate_or_claim(self):
        with patch("custom_components.djconnect.native_installation_key_custody._private_read", return_value=None), \
             patch("custom_components.djconnect.native_installation_key_custody._generate") as generate, \
             patch("custom_components.djconnect.native_installation_key_custody._claim") as claim:
            with self.assertRaises(SurfacePushError):
                await self.controller.challenge(self.payload, self.headers)
            generate.assert_not_called()
            claim.assert_not_called()
        self.assertEqual(self.calls, [])

    async def test_clock_rollback_blocks_register_before_network_effect(self):
        await self.controller.challenge(self.payload, self.headers)
        self.f.unit.clock[0] -= 1
        with self.assertRaises(SurfacePushError):
            await self.controller.register(self.register_body(), self.headers)
        self.assertEqual(len(self.calls), 1)

    async def test_expired_challenge_cannot_mint_owner(self):
        await self.controller.challenge(self.payload, self.headers)
        self.f.unit.clock[0] += 60
        self.f.unit.clock[1] += 60
        with self.assertRaises(SurfacePushError):
            await self.controller.register(self.register_body(), self.headers)
        self.assertEqual(len(self.calls), 1)

    async def test_http_closed_body_and_no_cookie_boundary(self):
        from types import SimpleNamespace
        from tests.test_native_pair_enrollment import Body, fixtures as pair_fixture
        from custom_components.djconnect.native_pair_enrollment_http import NativeWidgetReauthorizationView
        view = NativeWidgetReauthorizationView(self.native.hass, "challenge")
        for extra, cookie in (({"profile_id": "caller-cannot-select"}, False), ({}, True)):
            headers = pair_fixture.Headers({**self.headers, "Content-Type": "application/json"})
            if cookie:
                headers["Cookie"] = "closed"
            raw = json.dumps({"contract_version": 1, **self.payload, **extra}).encode()
            result = await view.post(SimpleNamespace(raw_path=view.url, headers=headers,
                content=Body(raw), content_length=len(raw)))
            self.assertEqual(result.status, 400)
        self.assertEqual(self.calls, [])

    async def test_signer_replacement_in_final_guard_never_invokes_replacement(self):
        await self.controller.challenge(self.payload, self.headers)
        record = self.controller.operations[self.payload["operation_id"]]
        original_validate = record.paired.validate_now
        calls = []
        def validate():
            original_validate()
            object.__setattr__(record.authority, "sign", lambda _: calls.append(True))
        record.paired.validate_now = validate
        with self.assertRaises(SurfacePushError):
            await self.controller.register(self.register_body(), self.headers)
        self.assertEqual(calls, [])

    async def test_subsequent_winner_does_not_redirect_old_operation_to_latest(self):
        await self.controller.challenge(self.payload, self.headers)
        await self.controller.register(self.register_body(), self.headers)
        old_payload = dict(self.payload)
        old_record = self.controller.operations[old_payload["operation_id"]]
        old_owner = old_record.owner
        await self.native.consent(self.headers, enabled=False, operation_id=str(uuid.uuid4()), expected_revision=3)
        await self.native.consent(self.headers, enabled=True, operation_id=str(uuid.uuid4()), expected_revision=4)
        self.consent_revision = 5
        self.payload = dict(self.payload, operation_id=issuer._operation(int(self.native.wall() * 1000)))
        await self.controller.challenge(self.payload, self.headers)
        await self.controller.register(self.register_body(), self.headers)
        latest = self.controller.operations[self.payload["operation_id"]].owner
        self.assertIsNot(latest, old_owner)
        self.assertIs(old_record.owner, old_owner)
        with self.assertRaises(SurfacePushError):
            await self.controller.status(old_payload, self.headers)
        latest._live()

    async def test_http_actual_challenge_and_register_ready_are_closed_data(self):
        from types import SimpleNamespace
        from tests.test_native_pair_enrollment import Body, fixtures as pair_fixture
        from custom_components.djconnect.native_pair_enrollment_http import NativeWidgetReauthorizationView
        async def post(action, body):
            view = NativeWidgetReauthorizationView(self.native.hass, action)
            headers = pair_fixture.Headers({**self.headers, "Content-Type": "application/json"})
            raw = json.dumps({"contract_version": 1, **body}).encode()
            result = await view.post(SimpleNamespace(raw_path=view.url, headers=headers,
                content=Body(raw), content_length=len(raw)))
            self.assertEqual(result.status, 200, result.body)
            self.assertEqual(result.headers["Cache-Control"], "no-store")
            return json.loads(result.body)
        challenge = await post("challenge", self.payload)
        self.assertEqual(set(challenge), {"contract_version", "api_audience", "operation_id", "challenge",
            "first_key_receipt", "delegation", "client_data_hash_b64"})
        ready = await post("register", self.register_body())
        self.assertEqual(set(ready), {"contract_version", "operation_id", "state"})
        self.assertEqual(await post("status", {k: v for k, v in self.payload.items() if k != "first_key_receipt"}), ready)

    async def test_role_ready_uses_real_role_grant_not_expired_assertion_challenge(self):
        await self.controller.challenge(self.payload, self.headers)
        await self.controller.register(self.register_body(), self.headers)
        self.f.unit.clock[0] += 121
        self.f.unit.clock[1] += 121
        ready = await self.controller.status(self.payload, self.headers)
        self.assertEqual(ready["state"], "ready")
        record = self.controller.operations[self.payload["operation_id"]]
        self.assertLess(record.deadline, self.native.monotonic())
        self.f.unit.clock[0] += 14_400
        self.f.unit.clock[1] += 14_400
        with self.assertRaises(SurfacePushError):
            await self.controller.status(self.payload, self.headers)

    async def test_original_clock_expiry_cannot_be_hidden_by_replacement_producers(self):
        await self.controller.challenge(self.payload, self.headers)
        original_wall, original_mono = self.native.wall(), self.native.monotonic()
        self.f.unit.clock[0] += 121
        self.f.unit.clock[1] += 121
        self.native.wall = lambda: original_wall
        self.native.monotonic = lambda: original_mono
        with self.assertRaises(SurfacePushError):
            await self.controller.register(self.register_body(), self.headers)
        self.assertEqual(len(self.calls), 1)
        self.assertIsNone(self.controller.operations[self.payload["operation_id"]].owner)

    async def test_clock_replacement_during_ack_await_cannot_be_adopted_by_role(self):
        await self.controller.challenge(self.payload, self.headers)
        original_wall, original_mono = self.native.wall(), self.native.monotonic()
        async def replace():
            self.native.wall = lambda: original_wall
            self.native.monotonic = lambda: original_mono
        self.hook = replace
        with self.assertRaises(SurfacePushError):
            await self.controller.register(self.register_body(), self.headers)
        self.assertIsNone(self.controller.operations[self.payload["operation_id"]].owner)
