"""Real P256/SQLite first-key custody with explicit synthetic owner/HTTP seams.

These seams do not prove native enrollment, clock or provider/device delivery.
"""
import base64
import asyncio
import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from tests import test_native_installation_runtime as fixtures
from custom_components.djconnect import native_widget_issuer as issuer
from custom_components.djconnect.surface_issuer_transport import IssuerHTTPReply
from custom_components.djconnect.surface_issuer_wire import PREFIX, signing_bytes, verify_envelope
from custom_components.djconnect.surface_push_contract import SurfacePushError
from custom_components.djconnect.surface_push_wire import canonical


class NativeWidgetIssuerTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.f = fixtures.NativeInstallationRuntimeTests()
        await self.f.asyncSetUp()
        await self.f.production()
        # Explicit virtual clocks inside the selected bounded development policy.
        # A later CI date must not pretend to qualify a new production policy.
        self.clock = [datetime(2026, 11, 24, tzinfo=UTC).timestamp(), 1000.0]
        self.f.service.wall = lambda: self.clock[0]
        self.f.service.monotonic = lambda: self.clock[1]
        self.valid = True
        self.source = {"backend_id": "synthetic-backend", "music_account_id": "synthetic-account",
            "provider_entry_id": "synthetic-provider", "provider_account_id": "synthetic-provider-account"}
        def validate():
            if not self.valid:
                raise SurfacePushError("synthetic_owner_withdrawn", 403)
        self.authority = SimpleNamespace(runtime=self.f.runtime,
            context=SimpleNamespace(profile_id="synthetic-owner"), binding="b" * 64,
            device=hashlib.sha256(self.f.runtime.pairing_device_id.encode()).hexdigest(),
            owner=hashlib.sha256(b"synthetic-owner").hexdigest(), validate_now=validate)
        async def resolve(*args):
            validate()
            return self.authority
        self.patches = [patch("custom_components.djconnect.hybrid_service.PairedAuthority.resolve", resolve),
            patch("custom_components.djconnect.reply_artwork.source_admission",
                side_effect=lambda *_: (dict(self.source), lambda: self.valid))]
        for item in self.patches:
            item.start()
        self.original_http = self.f.service.transport._post
        self.f.service.transport._post = self.http
        self.role_calls = []
        self.corrupt = False
        self.reply_hook = None

    async def asyncTearDown(self):
        for item in reversed(self.patches):
            item.stop()
        await self.f.asyncTearDown()
        self.f.doCleanups()

    async def http(self, origin, path, body, headers, *, guard, deadline):
        if path != issuer._ENROL:
            return await self.original_http(origin, path, body, headers, guard=guard, deadline=deadline)
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        guard()
        self.assertEqual(headers, {"Authorization": "Bearer " + fixtures.TOKEN})
        self.assertEqual(origin, "https://api.djconnect.dev")
        receipt, delegation = body["first_key_receipt"], body["delegation"]
        statement = canonical([issuer._ROLE_DOMAIN, "POST", path, receipt, delegation]).encode()
        original = next(original for _, original in self.f.service.pending.values()
            if original is not None and original.challenge["operation_id"] == receipt["operation_id"])
        public = load_der_public_key(original.spki)
        raw = base64.urlsafe_b64decode(body["signature"] + "==")
        public.verify(utils.encode_dss_signature(int.from_bytes(raw[:32]), int.from_bytes(raw[32:])),
            statement, ec.ECDSA(hashes.SHA256()))
        self.assertEqual(delegation["public_key"], issuer._jwk(original.spki))
        self.role_calls.append(body)
        key, policy = delegation["public_key"], delegation["policy"]
        scope = issuer._hash([issuer.DOMAIN, "delegation", delegation["delegation_id"], 1,
            delegation["install_id"], delegation["device_binding"], delegation["owner_binding"],
            delegation["grant_binding"], delegation["source_binding"], delegation["binding_id"],
            issuer.public_key_thumbprint(key), policy])
        ack = {"contract_version": 1, "success": True, "state": "enrolled", "replayed": self.corrupt,
            "delegation_id": delegation["delegation_id"], "delegation_revision": 1,
            "key_thumbprint": issuer.public_key_thumbprint(key), "scope_digest": scope,
            "expires_at_ms": policy["original_grant_expires_at_ms"],
            "enrol_operation_id": delegation["operation_id"],
            "install_credential_id": receipt["install_credential_id"],
            "native_operation_id": receipt["operation_id"],
            "native_api_installation_id": receipt["api_installation_id"],
            "native_registry_generation": receipt["registry_generation"],
            "enrolment_sha256": hashlib.sha256(statement).hexdigest()}
        if self.reply_hook is not None:
            await self.reply_hook()
        guard()
        return IssuerHTTPReply(200, ack)

    async def enrol(self):
        operation, receipt = await self.f.registered_winner()
        owner = await issuer.CoreWidgetIssuerOwner.enrol(self.f.service, operation, self.f.headers)
        return owner, operation, receipt

    def capture(self, owner):
        return owner.capture_live(issuer._operation(int(self.clock[0] * 1000)))

    async def test_winning_role_is_distinct_and_original_firstkey_is_consumed(self):
        with self.assertRaises(TypeError):
            issuer.CoreWidgetIssuerOwner()
        owner, operation, receipt = await self.enrol()
        capture = self.capture(owner)
        self.assertNotEqual(capture.expected.key_thumbprint, receipt["core_key_thumbprint"])
        self.assertEqual(capture.binding_id, self.authority.binding)
        self.assertEqual(capture.owner_binding, self.authority.owner)
        self.assertEqual(len(self.role_calls), 1)
        with self.assertRaises(SurfacePushError):
            await self.f.service.take_registered_enrollment(operation)
        payload = {"contract_version": 1, "purpose": "surface_push", "action": "challenge",
            "operation_id": capture.expected.operation_id, "delegation_id": capture.expected.delegation_id,
            "delegation_revision": 1, "key_thumbprint": capture.expected.key_thumbprint}
        message = signing_bytes(PREFIX + "challenge", payload)
        signature = await owner.sign(capture, PREFIX + "challenge", message, action="challenge")
        self.assertTrue(verify_envelope(PREFIX + "challenge", {"payload": payload, "signature": signature},
            self.role_calls[0]["delegation"]["public_key"]))
        self.clock[0] += 61
        self.clock[1] += 61
        owner.validate_live(capture)

    async def test_replayed_role_ack_consumes_attempt_without_owner(self):
        self.corrupt = True
        operation, _ = await self.f.registered_winner()
        for _ in range(2):
            with self.assertRaises(SurfacePushError):
                await issuer.CoreWidgetIssuerOwner.enrol(self.f.service, operation, self.f.headers)
        self.assertEqual(len(self.role_calls), 1)

    async def test_unknown_reply_never_retries_or_adopts_old_registered_key(self):
        async def lost():
            raise SurfacePushError("synthetic_lost_reply", 502)
        self.reply_hook = lost
        operation, _ = await self.f.registered_winner()
        for _ in range(2):
            with self.assertRaises(SurfacePushError):
                await issuer.CoreWidgetIssuerOwner.enrol(self.f.service, operation, self.f.headers)
        self.assertEqual(len(self.role_calls), 1)

    async def test_actual_consent_withdrawal_during_enrol_reply_adopts_nothing(self):
        async def withdraw():
            await self.f.widget_consent(enabled=False, expected_revision=1)
        self.reply_hook = withdraw
        with self.assertRaises(SurfacePushError):
            await self.enrol()
        self.assertEqual(len(self.role_calls), 1)

    async def test_source_aba_never_reopens_role(self):
        owner, _, _ = await self.enrol()
        capture = self.capture(owner)
        self.valid = False
        with self.assertRaises(SurfacePushError):
            owner.validate_live(capture)
        self.valid = True
        with self.assertRaises(SurfacePushError):
            owner.validate_live(capture)
        owner.validate_withdrawal(capture)

    async def test_actual_consent_off_closes_live_but_retains_original_management(self):
        owner, _, _ = await self.enrol()
        capture = self.capture(owner)
        await self.f.widget_consent(enabled=False, expected_revision=1)
        with self.assertRaises(SurfacePushError):
            owner.validate_live(capture)
        owner.validate_status(capture)
        owner.validate_withdrawal(capture)

    async def test_original_role_expiry_never_renews(self):
        owner, _, _ = await self.enrol()
        capture = self.capture(owner)
        self.clock[0] += 28800
        self.clock[1] += 28800
        with self.assertRaises(SurfacePushError):
            owner.validate_live(capture)
        owner.validate_withdrawal(capture)

    async def test_role_policy_uses_original_server_bounds_before_its_real_signature(self):
        owner, _, receipt = await self.enrol()
        role = owner._live()
        policy = self.role_calls[0]["delegation"]["policy"]
        self.assertEqual(policy["original_grant_expires_at_ms"], receipt["apple_status_expires_at_ms"])
        self.assertEqual(role.base.expected.original_grant_expires_ms, receipt["apple_status_expires_at_ms"])
        self.assertLess(receipt["expires_at_ms"], receipt["apple_status_expires_at_ms"])
        self.clock[0] += 14400
        self.clock[1] += 14400
        with self.assertRaises(SurfacePushError):
            owner._live()

    async def test_unload_cannot_restore_role_from_same_service_or_old_ack(self):
        owner, _, _ = await self.enrol()
        capture = self.capture(owner)
        self.f.service.stop_retirement_delivery()
        with self.assertRaises(SurfacePushError):
            owner.validate_live(capture)
        with self.assertRaises(SurfacePushError):
            owner.validate_withdrawal(capture)

    async def test_clock_rollback_quarantines_original_role(self):
        owner, _, _ = await self.enrol()
        capture = self.capture(owner)
        self.clock[0] -= 1
        with self.assertRaises(SurfacePushError):
            owner.validate_live(capture)
        self.clock[0] += 1
        with self.assertRaises(SurfacePushError):
            owner.validate_live(capture)

    async def test_production_transport_uses_original_role_without_cf_or_install_auth(self):
        from custom_components.djconnect.native_widget_transport import ProductionWidgetHTTPS
        with self.assertRaises(SurfacePushError):
            ProductionWidgetHTTPS(object.__new__(issuer.CoreWidgetIssuerOwner))
        owner, _, _ = await self.enrol()
        capture = self.capture(owner)
        transport = ProductionWidgetHTTPS(owner)
        calls = []
        async def post(origin, path, body, headers, *, guard, deadline):
            guard()
            calls.append((origin, path, headers))
            return IssuerHTTPReply(200, {"synthetic": "transport-only"})
        transport._post = post
        payload = {"contract_version": 1, "purpose": "surface_push", "action": "challenge",
            "operation_id": capture.expected.operation_id, "delegation_id": capture.expected.delegation_id,
            "delegation_revision": 1, "key_thumbprint": capture.expected.key_thumbprint}
        message = signing_bytes(PREFIX + "challenge", payload)
        signature = await owner.sign(capture, PREFIX + "challenge", message, action="challenge")
        await transport.post_once(capture, "challenge", {"payload": payload, "signature": signature},
            guard=lambda: owner.validate_live(capture), deadline=self.clock[1] + 10)
        self.assertEqual(calls, [("https://api.djconnect.dev", PREFIX + "challenge", {})])
        with self.assertRaises(SurfacePushError):
            transport.validate_origin("https://operator.example.com")

    async def test_original_role_validates_in_real_ha_style_synchronous_callback(self):
        owner, _, _ = await self.enrol()
        capture = self.capture(owner)
        loop = asyncio.get_running_loop()
        completed = loop.create_future()
        def callback():
            self.assertIsNone(asyncio.current_task())
            try:
                owner.validate_live(capture)
                completed.set_result(True)
            except BaseException as error:
                completed.set_exception(error)
        loop.call_soon(callback)
        self.assertTrue(await completed)

    async def test_same_value_consent_callback_replacement_cannot_replace_original_custody(self):
        owner, _, _ = await self.enrol()
        capture = self.capture(owner)
        first = self.f.service.pending[self.f.runtime.pairing_device_id][1]
        original = first.consent_current
        first.consent_current = lambda: original()
        with self.assertRaises(SurfacePushError):
            owner.validate_live(capture)
        first.consent_current = original
        with self.assertRaises(SurfacePushError):
            owner.validate_live(capture)

    async def test_actual_sqlite_off_cannot_be_overridden_by_new_callback(self):
        owner, _, _ = await self.enrol()
        capture = self.capture(owner)
        first = self.f.service.pending[self.f.runtime.pairing_device_id][1]
        original = first.consent_current
        first.consent_current = lambda: True
        await self.f.widget_consent(enabled=False, expected_revision=1)
        self.assertFalse(original())
        self.assertTrue(first.consent_current())
        with self.assertRaises(SurfacePushError):
            owner.validate_live(capture)

    async def test_cancelled_caller_cannot_sign_or_destroy_independent_role_custody(self):
        owner, _, _ = await self.enrol()
        capture = self.capture(owner)
        async def cancelled():
            asyncio.current_task().cancel()
            owner.validate_live(capture)
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.create_task(cancelled())
        owner.validate_live(capture)
