"""Genuine fixture pairing and B factories; no SDK/TV acceptance claim."""

import importlib
import secrets
import sys
import unittest
from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import Mock, patch
from uuid import UUID

from tests import test_display_service as existing


class CastDisplayTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        existing.DisplayServiceTests.setUpClass()
        cls.module = importlib.import_module("custom_components.djconnect.cast_display")

    @classmethod
    def tearDownClass(cls):
        existing.DisplayServiceTests.tearDownClass()

    async def asyncSetUp(self):
        self.base = existing.DisplayServiceTests()
        await self.base.asyncSetUp()
        self.fixture = self.base.fixture
        self.manager = self.base.manager
        self.service = self.module.CastDisplayService(self.fixture.hass, self.manager)

    async def asyncTearDown(self):
        await self.base.asyncTearDown()

    async def call(self, action, body, *, headers=None, origins=None):
        return await self.service.post(
            action,
            {"contract_version": 1, **body},
            headers={} if headers is None else headers,
            origins=[self.module.RECEIVER_ORIGIN] if origins is None else origins,
            source="unit-cast-peer",
        )

    async def bootstrap(self, *, headers=None):
        return await self.call(
            "owner/bootstrap",
            {"identity": self.fixture.identity, "session_id": self.fixture.active.session_id},
            headers=self.fixture.headers if headers is None else headers,
            origins=[],
        )

    async def claim(self):
        bootstrap = await self.bootstrap()
        bootstrap.release()
        nonce = secrets.token_urlsafe(32)
        claim = await self.call(
            "claim",
            {"browser_nonce": nonce},
            headers={"Authorization": "Bearer " + bootstrap.payload["bootstrap_token"]},
        )
        claim.release()
        return claim.payload, nonce, bootstrap.payload

    async def test_mac_launch_only_returns_the_claim_created_by_its_receiver(self):
        identity = {"device_id": "djconnect-macos-ABCDEF123457", "client_type": "macos"}
        headers = {"Authorization": "Bearer synthetic-mac-fixture-token"}
        await self.fixture.storage.async_upsert_device(
            identity["device_id"], "macos", linked_profile_id="profile-a"
        )
        entry = SimpleNamespace(
            entry_id="mac-owner", data={**identity, "device_token": "synthetic-mac-fixture-token"},
            options={}, disabled_by=None, state="loaded",
        )
        self.fixture.hass.data["djconnect"][entry.entry_id] = SimpleNamespace(
            config={**identity, "music_backend": "later_manual"}, device_status=identity,
            device_token=entry.data["device_token"], entry=entry, _receiver_end_generation=0,
            authorize_device_request=lambda given, device_id=None, client_type=None: (
                given.get("Authorization") == headers["Authorization"]
                and device_id == identity["device_id"] and client_type == "macos"
            ),
        )
        entries = {self.fixture.entry.entry_id: self.fixture.entry, entry.entry_id: entry}
        self.fixture.hass.config_entries.async_get_entry = entries.get
        self.fixture.hass.config_entries.async_entries = lambda domain: [
            SimpleNamespace(data={"known_hosts": ["test-tv.example.test"]})
        ] if domain == "cast" else []
        receiver = Mock()
        reply_handoff = None

        async def executor(job, *args):
            if job is not receiver.claim:
                return job(*args)
            envelope, = args
            claim = await self.call(
                "claim", {"browser_nonce": secrets.token_urlsafe(32)},
                headers={"Authorization": "Bearer " + envelope["bootstrap_token"]},
            )
            claim.release()
            return {**claim.payload, "kind": "vibecast_display_claim", "version": 1,
                    "handoff_id": reply_handoff or envelope["handoff_id"]}

        self.fixture.hass.async_add_executor_job = executor
        body = {"identity": identity, "session_id": self.fixture.active.session_id,
                "receiver_id": "88f78d37ee02414fa9430a4dce6407f6"}
        with patch.object(self.module, "CastSender", return_value=receiver) as sender:
            with self.assertRaises(self.module.DisplayAdmissionError):
                await self.call("owner/launch", body, headers=headers)
            with self.assertRaises(self.module.DisplayAdmissionError):
                await self.call("owner/launch", body | {"receiver_id": "192.0.2.10"}, headers=headers, origins=[])
            with self.assertRaises(self.module.DisplayAdmissionError):
                await self.call("owner/launch", body, origins=[])
            sender.assert_not_called()

            reply_handoff = "wrong"
            with self.assertRaises(self.module.DisplayAdmissionError):
                await self.call("owner/launch", body, headers=headers, origins=[])
            self.assertFalse(self.module.registry(self.manager).launches)

            reply_handoff = None
            result = await self.call("owner/launch", body, headers=headers, origins=[])
            result.release()
            sender.assert_called_with(UUID(hex=body["receiver_id"]), ["test-tv.example.test"])
        self.assertEqual(set(result.payload), {
            "success", "contract_version", "issuer_epoch", "claim_id", "browser_generation", "code",
        })
        resolved = await self.base.call("owner/resolve", {"code": result.payload["code"]},
                                        identity=identity, headers=headers)
        self.assertEqual(resolved.payload["claim_id"], result.payload["claim_id"])
        self.assertEqual(receiver.close.call_count, 2)
        self.assertFalse(self.manager._display_admission._shares)
        self.assertFalse(self.manager._display_admission._displays)

    async def test_mac_sender_sends_only_to_the_selected_receiver_transport(self):
        adapter = importlib.import_module("custom_components.djconnect.cast_sender")
        target = UUID("88f78d37-ee02-414f-a943-0a4dce6407f6")
        browser = Mock()
        device = Mock()
        device.cast_info = SimpleNamespace(uuid=target, cast_type="cast")
        device.status = SimpleNamespace(app_id=adapter.APP_ID, transport_id="web-42",
                                        namespaces=[adapter.NAMESPACE])
        handoff = "a" * 32
        envelope = {"kind": "vibecast_display_bootstrap", "handoff_id": handoff}
        expected = {"kind": "vibecast_display_claim", "handoff_id": handoff}

        class Controller:
            def __init__(self, namespace):
                self.namespace = namespace

        def on_send(*args, **kwargs):
            controller = device.register_handler.call_args.args[0]
            message = SimpleNamespace(source_id="web-other", destination_id=device.socket_client.source_id)
            controller.receive_message(message, expected | {"code": "wrong"})
            message.source_id = "web-42"
            controller.receive_message(message, expected)

        device.socket_client.send_message.side_effect = on_send
        sdk = Mock()
        sdk.get_listed_chromecasts.return_value = ([device], browser)
        with patch.dict(sys.modules, {
            "pychromecast": sdk, "pychromecast.controllers": SimpleNamespace(BaseController=Controller)
        }):
            sender = adapter.CastSender(target, ["test-tv.example.test"])
            try:
                sender.connect()
                sender.launch()
                self.assertEqual(sender.claim(envelope), expected)
            finally:
                sender.close()
        self.assertEqual(sdk.get_listed_chromecasts.call_args.kwargs["uuids"], [target])
        self.assertEqual(sdk.get_listed_chromecasts.call_args.kwargs["known_hosts"], ["test-tv.example.test"])
        self.assertTrue(device.socket_client.logger.disabled)
        device.start_app.assert_called_once_with(adapter.APP_ID, timeout=7)
        device.socket_client.send_message.assert_called_once_with(
            "web-42", adapter.NAMESPACE, envelope, no_add_request_id=True
        )
        device.disconnect.assert_called_once_with(timeout=3)
        browser.stop_discovery.assert_called_once()

    async def admitted(self):
        claim, nonce, bootstrap = await self.claim()
        resolved = await self.base.call("owner/resolve", {"code": claim["code"]})
        self.assertEqual(resolved.payload["claim_id"], claim["claim_id"])
        await self.base.call(
            "owner/approve",
            {
                **{k: claim[k] for k in ("issuer_epoch", "claim_id", "browser_generation", "code")},
                "session_id": self.fixture.active.session_id,
                "share": {
                    "mode": "create",
                    "consent": True,
                    "lifetime_seconds": 14400,
                    "live": True,
                },
            },
        )
        binding = {
            k: claim[k] for k in ("issuer_epoch", "claim_id", "claim_secret", "browser_generation")
        }
        result = await self.call("collect", {**binding, "browser_nonce": nonce})
        result.release()
        return result

    async def test_real_factories_and_ordinary_owner_admission_create_readonly_live_display(self):
        result = await self.admitted()
        p = result.payload
        self.assertEqual(p["state"], "admitted")
        self.assertEqual(p["session_id"], self.fixture.active.session_id)
        self.assertFalse(p["capabilities"]["owner_controls"])
        actual = self.manager._display_admission._displays[p["display_id"]]
        self.assertIs(self.module.registry(self.manager).displays[p["display_id"]].display, actual)
        self.assertTrue(
            self.manager._display_admission.participation._policies[
                p["share_id"]
            ].policy.information
        )
        self.assertNotIn("bootstrap_token", p)
        self.assertNotIn("claim_secret", p)

    async def test_presentation_is_bound_to_the_admitted_cast_display(self):
        receipt = (await self.admitted()).payload
        body = {key: receipt[key] for key in ("issuer_epoch", "display_id")}
        headers = {"Authorization": "Bearer " + receipt["grant_token"]}
        before = self.fixture.active.broadcast.state
        result = await self.call(
            "participation/display/presentation", {**body, "mode": "vibescape"}, headers=headers
        )
        result.release()
        self.assertEqual(result.payload["view"]["mode"], "vibescape")
        self.assertEqual(result.payload["view"]["revision"], 1)
        self.assertIs(self.fixture.active.broadcast.state, before)
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call(
                "participation/display/presentation", {**body, "mode": "flow"},
                headers=headers, origins=[self.base.origin],
            )
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call(
                "participation/display/presentation", {**body, "mode": "flow", "dynamics": 1},
                headers=headers,
            )
        self.module.registry(self.manager).displays.pop(receipt["display_id"])
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call("participation/display/presentation", {**body, "mode": "flow"}, headers=headers)
        self.assertEqual(self.manager._display_admission._shares[receipt["share_id"]].view_mode, "vibescape")

    async def test_withdrawn_cast_association_cannot_create_a_guest_invitation(self):
        receipt = (await self.admitted()).payload
        scope = {key: receipt[key] for key in ("issuer_epoch", "display_id")}
        headers = {"Authorization": "Bearer " + receipt["grant_token"]}
        invitations = self.manager._display_admission.participation._invitations
        original = self.module.require_cast_display

        def withdraw_after_preflight(hass, manager, display):
            verified = original(hass, manager, display)
            self.module.registry(manager).displays.pop(display.display_id)
            return verified

        before = invitations.copy()
        with patch.object(self.module, "require_cast_display", side_effect=withdraw_after_preflight):
            with self.assertRaises(self.module.DisplayAdmissionError):
                await self.call("participation/display/invitation", scope, headers=headers)
        self.assertEqual(invitations, before)

    async def test_pairing_required_and_bootstrap_creates_no_share_or_display(self):
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.bootstrap(headers={})
        b = await self.bootstrap()
        self.assertEqual(b.payload["ha_origin"], self.base.origin)
        self.assertEqual(b.payload["bootstrap_expires_in"], 30)
        self.assertFalse(self.manager._display_admission._claims)
        self.assertFalse(self.manager._display_admission._shares)
        self.assertFalse(self.manager._display_admission._displays)

    async def test_successful_claim_consumes_bootstrap_once_and_secret_is_browser_only(self):
        claim, nonce, b = await self.claim()
        self.assertIn("claim_secret", claim)
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call(
                "claim",
                {"browser_nonce": nonce},
                headers={"Authorization": "Bearer " + b["bootstrap_token"]},
            )
        self.assertEqual(len(self.manager._display_admission._claims), 1)
        self.assertFalse(self.manager._display_admission._shares)

    async def test_expired_bootstrap_cannot_mint_claim_or_release_saved_response(self):
        b = await self.bootstrap()
        state = self.manager._display_admission
        clock = state._clock
        state._clock = lambda: clock() + 31
        with self.assertRaises(self.module.DisplayAdmissionError):
            b.release()
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call(
                "claim",
                {"browser_nonce": secrets.token_urlsafe(32)},
                headers={"Authorization": "Bearer " + b.payload["bootstrap_token"]},
            )
        self.assertFalse(state._claims)

    async def test_foreign_missing_duplicate_origins_and_legacy_bearer_cannot_mint(self):
        b = await self.bootstrap()
        for origins in ([], ["null"], [self.base.origin], [self.module.RECEIVER_ORIGIN] * 2):
            with (
                self.subTest(origins=origins),
                self.assertRaises(self.module.DisplayAdmissionError),
            ):
                await self.call(
                    "claim",
                    {"browser_nonce": secrets.token_urlsafe(32)},
                    headers={"Authorization": "Bearer " + b.payload["bootstrap_token"]},
                    origins=origins,
                )
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call(
                "claim",
                {"browser_nonce": secrets.token_urlsafe(32)},
                headers={"Authorization": "Bearer " + "x" * 43},
            )
        self.assertFalse(self.manager._display_admission._claims)

    async def test_original_B_route_still_denies_receiver_origin(self):
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.base.call(
                "claim",
                {"browser_nonce": secrets.token_urlsafe(32)},
                origins=[self.module.RECEIVER_ORIGIN],
            )

    async def test_ordinary_B_grant_cannot_be_adopted_by_cast_transport(self):
        p = (await self.base.admitted()).payload
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call(
                "snapshot",
                {k: p[k] for k in ("issuer_epoch", "display_id")},
                headers={"Authorization": "Bearer " + p["grant_token"]},
            )

    async def test_genuine_B_factory_rejects_other_owner_before_any_approval_mutation(self):
        claim, _, _ = await self.claim()
        state = self.manager._display_admission
        actual = state._claims[claim["claim_id"]]
        original = actual.cast_owner
        # A second live authority differs in private stamp; never an HTTP-selected owner.
        other = replace(original, stamp="different-real-owner-stamp")
        with self.assertRaises(self.module.DisplayAdmissionError):
            state.resolve(code=claim["code"], owner=other)
        with self.assertRaises(self.module.DisplayAdmissionError):
            state.approve(
                owner=other,
                **{k: claim[k] for k in ("issuer_epoch", "claim_id", "browser_generation", "code")},
                share={"mode": "create", "consent": True},
            )
        self.assertIsNone(actual.owner)
        self.assertFalse(state._shares)
        self.assertEqual(
            state.resolve(code=claim["code"], owner=original)["claim_id"], claim["claim_id"]
        )

    async def test_live_grant_renew_without_writer_never_extends_original_lease(self):
        p = (await self.admitted()).payload
        state = self.manager._display_admission
        deadline = state._displays[p["display_id"]].lease_deadline
        result = await self.call(
            "renew",
            {**{k: p[k] for k in ("issuer_epoch", "display_id")}, "renew_sequence": 1},
            headers={"Authorization": "Bearer " + p["grant_token"]},
        )
        result.release()
        self.assertEqual(state._displays[p["display_id"]].lease_deadline, deadline)

    async def test_display_only_QR_focus_paths_work_but_owner_and_guest_effects_are_closed(self):
        p = (await self.admitted()).payload
        headers = {"Authorization": "Bearer " + p["grant_token"]}
        body = {k: p[k] for k in ("issuer_epoch", "display_id")}
        invitation = await self.call("participation/display/invitation", body, headers=headers)
        invitation.release()
        self.assertTrue(invitation.payload["qr_data_uri"].startswith("data:image/svg+xml;base64,"))
        focus = await self.call("participation/display/focus", body, headers=headers)
        focus.release()
        self.assertIn("focused_moment_id", focus.payload)
        for action in ("owner/approve", "participation/ask", "participation/owner/configure"):
            with self.subTest(action=action), self.assertRaises(self.module.DisplayAdmissionError):
                await self.call(action, body, headers=headers)

    async def test_session_or_origin_change_invalidates_issued_bootstrap(self):
        b = await self.bootstrap()
        self.base.origin = "https://changed.example.net"
        with self.assertRaises(self.module.DisplayAdmissionError):
            b.release()
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call(
                "claim",
                {"browser_nonce": secrets.token_urlsafe(32)},
                headers={"Authorization": "Bearer " + b.payload["bootstrap_token"]},
            )

    async def test_two_actual_paired_owners_cannot_adopt_each_others_cast_claim(self):
        second = {"device_id": "djconnect-ios-ABCDEF123457", "client_type": "ios"}
        headers = {"Authorization": "Bearer synthetic-second-fixture-token"}
        await self.fixture.storage.async_upsert_device(
            second["device_id"], "ios", linked_profile_id="profile-a"
        )
        entry = SimpleNamespace(
            entry_id="second-owner-entry",
            data={**second, "device_token": "synthetic-second-fixture-token"},
            options={},
            disabled_by=None,
            state="loaded",
        )
        runtime = SimpleNamespace(
            config={**second, "music_backend": "later_manual"},
            device_status=second,
            device_token="synthetic-second-fixture-token",
            entry=entry,
            _receiver_end_generation=0,
            authorize_device_request=lambda given, device_id=None, client_type=None: (
                given.get("Authorization") == headers["Authorization"]
                and device_id == second["device_id"]
                and client_type == "ios"
            ),
        )
        self.fixture.hass.data["djconnect"][entry.entry_id] = runtime
        entries = {self.fixture.entry.entry_id: self.fixture.entry, entry.entry_id: entry}
        self.fixture.hass.config_entries.async_get_entry = entries.get
        context = await self.base.call("owner/context", identity=second, headers=headers)
        self.assertEqual(context.payload["session_id"], self.fixture.active.session_id)
        claim, _, _ = await self.claim()
        actual = self.manager._display_admission._claims[claim["claim_id"]]
        self.assertTrue(actual.cast_owner.valid())
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.base.call(
                "owner/resolve", {"code": claim["code"]}, identity=second, headers=headers
            )
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.base.call(
                "owner/approve",
                {
                    **{
                        k: claim[k]
                        for k in ("issuer_epoch", "claim_id", "browser_generation", "code")
                    },
                    "session_id": self.fixture.active.session_id,
                    "share": {"mode": "create", "consent": True},
                },
                identity=second,
                headers=headers,
            )
        self.assertIsNone(actual.owner)
        self.assertFalse(self.manager._display_admission._shares)
        original = await self.base.call("owner/resolve", {"code": claim["code"]})
        self.assertEqual(original.payload["claim_id"], claim["claim_id"])

    async def test_owner_repair_cannot_revive_bootstrap_or_claim_and_final_response_is_fenced(self):
        claim, nonce, _ = await self.claim()
        self.fixture.runtime.device_token = "synthetic-repaired-fixture-token"
        self.fixture.entry.data["device_token"] = self.fixture.runtime.device_token
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.call(
                "collect",
                {
                    **{
                        k: claim[k]
                        for k in ("issuer_epoch", "claim_id", "claim_secret", "browser_generation")
                    },
                    "browser_nonce": nonce,
                },
            )
        self.assertFalse(self.manager._display_admission._displays)

    async def test_bootstrap_capacity_denies_without_evicting_live_pending_authority(self):
        first = await self.bootstrap()
        second = await self.bootstrap()
        with self.assertRaises(self.module.DisplayAdmissionError):
            await self.bootstrap()
        first.release()
        second.release()
        self.assertEqual(len(self.module.registry(self.manager).tokens), 2)

    async def test_real_performance_memory_value_replacement_preserves_current_Cast_authority(self):
        b = await self.bootstrap()
        original = self.manager.current_active("profile-a")
        updated = self.manager._record_performance_memory("profile-a", original)
        self.assertIsNot(updated, original)
        self.assertIs(updated.broadcast, original.broadcast)
        self.assertEqual(updated.session_id, original.session_id)
        b.release()
        nonce = secrets.token_urlsafe(32)
        c = await self.call(
            "claim",
            {"browser_nonce": nonce},
            headers={"Authorization": "Bearer " + b.payload["bootstrap_token"]},
        )
        c.release()
        again = self.manager._record_performance_memory("profile-a", updated)
        self.assertIs(again.broadcast, original.broadcast)
        c.release()

    async def test_new_Broadcast_or_session_cannot_inherit_bootstrap(self):
        for field in ("broadcast", "session_id"):
            with self.subTest(field=field):
                b = await self.bootstrap()
                original = self.manager.current_active("profile-a")
                changed = replace(
                    original, **{field: object() if field == "broadcast" else "other-real-session"}
                )
                self.manager._active_by_profile["profile-a"] = changed
                with self.assertRaises(self.module.DisplayAdmissionError):
                    b.release()
                self.manager._active_by_profile["profile-a"] = original
                with self.assertRaises(self.module.DisplayAdmissionError):
                    b.release()
