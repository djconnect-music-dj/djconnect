"""Actual register hook/SQLite/P256/adoption; declared owner/provider/TLS seams."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import uuid
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from tests import test_native_widget_issuer as fixture
from tests import test_native_pair_enrollment as pair_fixture
from tests import test_native_installation_key_custody as custody_fixture
from custom_components.djconnect.native_widget_issuer import _operation
from custom_components.djconnect.surface_issuer_transport import IssuerHTTPReply
from custom_components.djconnect.surface_issuer_wire import PREFIX, verify_envelope
from custom_components.djconnect.surface_push_contract import SurfacePushError
from custom_components.djconnect.surface_push_service import SurfacePushService


class NativeWidgetPreparationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.unit = fixture.NativeWidgetIssuerTests()
        await self.unit.asyncSetUp()
        f = self.unit.f
        f.entry.modified_at = 1
        # The pair-only Runtime fixture lacks the ordinary request-auth method.
        # Supply exact synthetic bearer/device/type matching, not a blanket grant.
        f.runtime.authorize_device_request = lambda headers, device, client: (
            headers.get("Authorization") == "Bearer " + f.runtime.device_token
            and device == f.runtime.pairing_device_id and client == "ios")
        await self.second_pair_before_enrollment()
        f.hass.async_create_background_task = lambda coro, name: asyncio.create_task(coro, name=name)
        self.active = SimpleNamespace(owner_profile_id="synthetic-owner", session_id="synthetic-session",
            broadcast=object(), runtime_state=SimpleNamespace(value="active"))
        self.manager = SimpleNamespace(current_active=lambda _: self.active,
            _history_source_contexts={self.active.session_id: dict(self.unit.source)})
        f.domain["session_runtime_manager"] = self.manager
        self.surface = SurfacePushService(f.hass, self.manager, f.persistence)
        f.domain["surface_push_service"] = self.surface
        self.source_patch = patch("custom_components.djconnect.forecast_imagery.artist_authority",
            side_effect=lambda *args, **kwargs: lambda: self.unit.valid)
        self.source_patch.start()
        self.key_operation, _ = await f.registered_winner()
        self.pool = self.surface._native_widget_preparation
        self.record = next(iter(self.pool.roles.values()))
        self.calls = []
        self.hook = None
        self.record.lifecycle.transport._post = self.issuer_http

    async def second_pair_before_enrollment(self):
        f = self.unit.f
        self.second_entry = SimpleNamespace(entry_id="second-entry", modified_at=2, disabled_by=None,
            state=SimpleNamespace(value="loaded"), data={"device_id": "djconnect-ios-SECOND123456",
            "client_type": "ios", "device_token": "SYNTHETIC-SECOND-PAIR"},
            options={"ha_install_id": "synthetic-ha", "djconnect_install_token": fixture.fixtures.TOKEN})
        runtime = pair_fixture.fixtures.Runtime()
        runtime.entry = self.second_entry
        runtime.pairing_device_id = self.second_entry.data["device_id"]
        runtime.device_token = self.second_entry.data["device_token"]
        runtime.surface_registration_retirement = pair_fixture.fixtures.PairingRetirement()
        runtime.authorize_device_request = lambda headers, device, client: (
            headers.get("Authorization") == "Bearer " + runtime.device_token
            and device == runtime.pairing_device_id and client == "ios")
        self.second_runtime = runtime
        f.domain[self.second_entry.entry_id] = runtime
        entries = (f.entry, self.second_entry)
        f.hass.config_entries.async_entries = lambda _: list(entries)
        f.path.write_text(json.dumps({"data": {"entries": [{"entry_id": entry.entry_id,
            "domain": "djconnect", "data": dict(entry.data), "options": dict(entry.options)}
            for entry in entries]}}))
        pair_fixture.fixtures.schedule_pair_registration(f.hass, runtime)
        while runtime.surface_pair_registration.tasks:
            await asyncio.gather(*tuple(runtime.surface_pair_registration.tasks))
        await f.profiles.async_upsert_device(runtime.pairing_device_id, "ios", linked_profile_id="synthetic-owner")
        self.second_headers = pair_fixture.fixtures.Headers({"Authorization": "Bearer " + runtime.device_token,
            "X-DJConnect-Device-ID": runtime.pairing_device_id, "X-DJConnect-Client-Type": "ios"})
        await f.service.consent(self.second_headers, enabled=True, operation_id=str(uuid.uuid4()), expected_revision=0)
        second_authority = SimpleNamespace(runtime=runtime, context=self.unit.authority.context,
            binding="c" * 64, device=hashlib.sha256(runtime.pairing_device_id.encode()).hexdigest(),
            owner=self.unit.authority.owner, validate_now=self.unit.authority.validate_now)
        authorities = {f.runtime.pairing_device_id: self.unit.authority,
                       runtime.pairing_device_id: second_authority}
        async def resolve(hass, identity, headers):
            authority = authorities[identity["device_id"]]
            self.assertTrue(authority.runtime.authorize_device_request(headers, **{
                "device": identity["device_id"], "client": identity["client_type"]}))
            authority.validate_now()
            return authority
        self.extra_patches = [patch("custom_components.djconnect.hybrid_service.PairedAuthority.resolve", resolve),
            patch("custom_components.djconnect.native_installation_key_custody._store",
                side_effect=lambda pair, identity: custody_fixture.PrivateStore(
                    Path(f.temp.name) / ("partition-" + identity), "synthetic-key." + identity))]
        for item in self.extra_patches:
            item.start()

    async def asyncTearDown(self):
        await self.surface.close()
        for item in reversed(self.extra_patches):
            item.stop()
        self.source_patch.stop()
        await self.unit.asyncTearDown()

    def payload(self):
        return {"contract_version": 1, "operation_id": _operation(int(self.unit.clock[0] * 1000)),
            "device_id": self.unit.f.runtime.pairing_device_id, "client_type": "ios",
            "session_id": self.active.session_id}

    async def issuer_http(self, origin, path, envelope, headers, *, guard, deadline):
        guard()
        self.assertEqual(origin, "https://api.djconnect.dev")
        self.assertEqual(headers, {})
        payload = envelope["payload"]
        action = path.removeprefix(PREFIX)
        record = next(record for record in self.pool.roles.values()
            if record.owner._live().base.expected.delegation_id == payload["delegation_id"])
        original = record.owner._live().captures[payload["operation_id"]]
        key, _ = original.comparisons()
        self.assertTrue(verify_envelope(path, envelope, key))
        self.calls.append(action)
        expected = original.expected
        reply = {"contract_version": 1, "success": True, "operation_id": payload["operation_id"],
            "delegation_id": expected.delegation_id, "delegation_revision": 1,
            "expires_at_ms": expected.original_grant_expires_ms, "state": action, "replayed": False,
            "scope_digest": expected.scope_digest}
        if action == "challenge":
            reply.update(key_thumbprint=expected.key_thumbprint, challenge_id="synthetic-challenge",
                nonce="A" * 43, expires_at_ms=int(self.unit.clock[0] * 1000) + 120000)
        elif action == "issue":
            reply.update(state="issued", capability_id=expected.delegation_id + "-cap",
                credential="djcs_" + base64.urlsafe_b64encode(
                    hashlib.sha256(expected.delegation_id.encode()).digest()).decode().rstrip("="))
        else:
            raise AssertionError("Unexpected fixture issuer action")
        if self.hook:
            await self.hook(action)
        guard()
        return IssuerHTTPReply(200, reply)

    async def test_actual_register_winner_prepares_once_and_exact_replay_preserves_purpose(self):
        self.assertEqual(len(self.unit.role_calls), 1)
        data = self.payload()
        response = await self.pool.prepare(data, self.unit.f.headers)
        self.assertEqual(response, {"contract_version": 1, "state": "prepared",
            "operation_id": data["operation_id"], "session_id": self.active.session_id})
        purpose = self.record.handle.purpose
        self.assertIs(next(iter(self.surface._purposes.values())), purpose)
        self.assertEqual(await self.pool.prepare(dict(data), self.unit.f.headers), response)
        self.assertIs(self.record.handle.purpose, purpose)
        self.assertEqual(self.calls, ["challenge", "issue"])
        with self.assertRaises(SurfacePushError):
            await self.unit.f.service.take_registered_enrollment(self.key_operation)

    async def test_wrong_session_allocates_no_handle_or_remote_effect(self):
        data = self.payload()
        data["session_id"] = "wrong-session"
        with self.assertRaises(SurfacePushError):
            await self.pool.prepare(data, self.unit.f.headers)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.surface._widget_adoptions._handles), 0)
        self.assertIsNone(self.record.operation)

    async def test_real_consent_off_during_issue_denies_late_adoption(self):
        async def off(action):
            if action == "issue":
                await self.unit.f.widget_consent(enabled=False, expected_revision=1)
        self.hook = off
        data = self.payload()
        with self.assertRaises(SurfacePushError):
            await self.pool.prepare(data, self.unit.f.headers)
        self.assertEqual(self.surface._purposes, {})
        self.assertTrue(self.record.handle.closed)
        calls = list(self.calls)
        with self.assertRaises(SurfacePushError):
            await self.pool.prepare(data, self.unit.f.headers)
        self.assertEqual(self.calls, calls)

    async def test_prepare_route_accepts_only_closed_ios_request(self):
        from custom_components.djconnect.surface_push_http import validate, surface_views
        data = self.payload()
        validate("widget/prepare", data)
        self.assertIn("/api/djconnect/v1/push/surface/widget/prepare",
            [view.url for view in surface_views(self.unit.f.hass)])
        data["client_type"] = "watchos"
        with self.assertRaises(SurfacePushError):
            validate("widget/prepare", data)

    async def test_two_original_pairs_share_journal_without_owner_or_consent_alias(self):
        f = self.unit.f
        identity = {"device_id": self.second_runtime.pairing_device_id, "client_type": "ios"}
        challenge = await f.service.challenge(self.second_headers, **identity)
        await f.service.register(self.second_headers, **identity,
            operation_id=challenge["operation_id"], apple_proof=f.proof())
        self.assertEqual(len(self.pool.roles), 2)
        second = next(record for record in self.pool.roles.values() if record is not self.record)
        self.assertIs(second.lifecycle.journal, self.record.lifecycle.journal)
        self.assertIsNot(second.lifecycle, self.record.lifecycle)
        self.assertNotEqual(second.owner._live().spki, self.record.owner._live().spki)
        second.lifecycle.transport._post = self.issuer_http
        first_payload = self.payload()
        await self.pool.prepare(first_payload, f.headers)
        second_payload = {**self.payload(), "device_id": self.second_runtime.pairing_device_id}
        await self.pool.prepare(second_payload, self.second_headers)
        self.assertEqual(len(self.surface._purposes), 2)
        self.assertEqual(self.calls, ["challenge", "issue", "challenge", "issue"])
        with self.assertRaises(SurfacePushError):
            await self.pool.prepare(first_payload, self.second_headers)
        await f.widget_consent(enabled=False, expected_revision=1)
        self.assertTrue(self.record.handle.closed)
        self.assertTrue(second.handle.purpose.is_current())
        self.assertFalse(second.handle.closed)
