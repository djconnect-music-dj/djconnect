"""Automatic Core source join: real pair/consent/crypto, declared fake TLS API.

API replies here are fixtures, never native/provider admission evidence.
"""
import asyncio
import base64
import hashlib
from pathlib import Path
from unittest.mock import patch

from tests import test_native_installation_key_custody as fixture
from tests import test_native_pair_enrollment as pair_fixture
from custom_components.djconnect.native_pair_enrollment import KEY
from custom_components.djconnect.native_pair_retirement import NativePairRetirementJournal
from custom_components.djconnect.native_installation_runtime import create_installation_service
from custom_components.djconnect.surface_push_contract import SurfacePushError
from custom_components.djconnect.surface_push_wire import canonical

TOKEN = "djci_" + "A" * 43  # Synthetic ordinary credential, never an actual token.


class ConfiguredHass(fixture.HassFixture):
    def __init__(self, **kwargs):
        if kwargs.get("entry_id") == "synthetic-entry":
            kwargs["options"] = {**kwargs["options"], "djconnect_install_token": TOKEN}
        super().__init__(**kwargs)


class NativeInstallationRuntimeTests(fixture.NativeInstallationCustodyTests):
    async def asyncSetUp(self):
        maintenance = patch("custom_components.djconnect.session_history_maintenance.schedule_history_maintenance")
        maintenance.start()
        self.addCleanup(maintenance.stop)
        with patch.object(pair_fixture, "SimpleNamespace", ConfiguredHass):
            await pair_fixture.NativePairEnrollmentTests.asyncSetUp(self)

    async def production(self):
        await self.prepare_custodian()
        self.service = create_installation_service(self.hass)
        self.domain[KEY] = self.service
        self.negative_store = fixture.PrivateStore(Path(self.temp.name) / "negative", "synthetic-negative", 2)
        self.service._installation.store = lambda: self.negative_store
        self.production_calls = []
        self.resolve_override = None
        self.service.transport._post = self.production_api
        return self.service

    async def production_api(self, origin, path, body, headers, *, guard, deadline):
        guard()
        self.assertEqual(origin, "https://api.djconnect.dev")
        self.assertEqual(headers.get("Authorization"), "Bearer " + TOKEN)
        self.assertNotIn("CF-Access-Client-Secret", headers)
        self.production_calls.append((path, dict(body)))
        if path.endswith("/resolve"):
            result = self.resolve_override or {"contract_version": 1, "install_credential_id": "ordinary-credential",
                                             "ha_install_id": "synthetic-ha"}
        elif "/publisher/" in path:
            result = {"ok": True}
        elif path.endswith("/challenge"):
            result = {"contract_version": 1, "api_audience": "djc-native-push/1", "operation_id": body["operation_id"],
                "api_installation_id": "synthetic-api-installation", "install_credential_id": "ordinary-credential",
                "challenge_id": "synthetic-challenge", "challenge_nonce": "A" * 43,
                "expected_key_revision": 0, "expires_at_ms": int(self.service.wall() * 1000) + 60_000}
        elif path.endswith("/register"):
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
            from cryptography.hazmat.primitives.serialization import load_der_public_key
            challenge_fields = ("operation_id", "api_installation_id", "install_credential_id", "challenge_id",
                                "challenge_nonce", "expires_at_ms", "expected_key_revision")
            binding_fields = ("pairing_generation", "pair_binding", "owner_binding", "device_binding", "core_key_thumbprint")
            statement = canonical(["djc-native-pair-witness/1", "djc-native-push/1", "POST",
                "/v1/push/native/key/register", "widget-first-key", *(body[k] for k in challenge_fields),
                *(body[k] for k in binding_fields)]).encode()
            raw = base64.urlsafe_b64decode(body["core_signature_b64url"] + "==")
            load_der_public_key(base64.b64decode(body["core_public_key_spki_b64"])).verify(
                encode_dss_signature(int.from_bytes(raw[:32]), int.from_bytes(raw[32:])), statement, ec.ECDSA(hashes.SHA256()))
            result = {k: body[k] for k in ("contract_version", "operation_id", "api_installation_id",
                                          "install_credential_id", "expires_at_ms", "pairing_generation", "core_key_thumbprint")}
            result.update(registry_generation="synthetic-fixture-ACK", key_revision=1, state="registered",
                          transcript_sha256=hashlib.sha256(statement).hexdigest())
        elif path.endswith("/retire"):
            result = {"contract_version": 1, "api_audience": "djc-native-push/1", "event_id": body["event_id"],
                      "pair_binding": body["pair_binding"], "event_sha256": hashlib.sha256(canonical(body).encode()).hexdigest(),
                      "state": "retired"}
        else:
            raise AssertionError("Unexpected fixture API route")
        guard()
        return pair_fixture.SimpleNamespace(status=200, body=result)

    async def test_automatic_construction_has_no_network_key_or_store_effect(self):
        with patch("custom_components.djconnect.native_installation_runtime.InstallationHTTPS.resolve",
                   side_effect=AssertionError("No startup network")):
            service = create_installation_service(self.hass)
            self.assertEqual(service.api_audience, "djc-native-push/1")
            self.assertEqual(list(service._installation.tasks), [])

    async def test_ordinary_original_pair_and_optin_use_new_audience_real_key_and_ack(self):
        await self.production()
        self.install_path.unlink()  # The old HA-dev credential store is irrelevant.
        self.assertEqual((await self.post("bootstrap"))[0], 200)
        self.assertFalse(Path(self.key_store.path).exists())
        operation, receipt = await self.registered_winner()
        self.assertEqual(receipt["install_credential_id"], "ordinary-credential")
        self.assertTrue(Path(self.negative_store.path).exists())
        self.assertTrue(Path(self.key_store.path).exists())
        self.assertTrue(any(path.endswith("/publisher/operation") for path, _ in self.production_calls))
        witness = await self.service.take_registered_enrollment(operation)
        self.assertEqual(dict(witness.receipt), receipt)
        self.assertTrue(await witness.sign(b"synthetic retained production-key custody"))

    async def test_unknown_or_mismatched_resolve_cannot_create_key_or_publish(self):
        await self.production()
        self.resolve_override = {"contract_version": 1, "install_credential_id": "other", "ha_install_id": "wrong"}
        self.assertEqual((await self.post("challenge"))[0], 502)
        self.assertFalse(Path(self.key_store.path + ".claim").exists())
        self.assertTrue(all(path.endswith("/resolve") for path, _ in self.production_calls))

    async def test_disabled_channel_does_not_generate_or_publish_from_existing_token(self):
        await self.production()
        await self.widget_consent(enabled=False, expected_revision=1)
        self.assertEqual((await self.post("challenge"))[0], 403)
        self.assertFalse(Path(self.key_store.path + ".claim").exists())
        self.assertTrue(all(path.endswith("/resolve") for path, _ in self.production_calls))

    async def test_original_negative_journal_can_retire_after_restart_without_positive_restore(self):
        await self.production()
        await self.registered_winner()
        self.registration.retire()
        await self.settle()
        journal = NativePairRetirementJournal(self.persistence)
        pending = await journal.pending(self.service.transport.origin)
        self.assertEqual(len(pending), 1)
        self.entry.options.pop("djconnect_install_token")
        restarted = create_installation_service(self.hass)
        restarted._installation.store = lambda: self.negative_store
        restarted.transport._post = self.production_api
        self.domain[KEY] = restarted
        self.assertEqual(list(restarted._installation.tasks), [])
        with self.assertRaises(SurfacePushError):
            await restarted.credential(self.pair)
        reply = await restarted.transport.post_retirement(pending[0].body(), guard=lambda: None,
                                                         deadline=restarted.monotonic() + 10)
        self.assertEqual(reply.body["state"], "retired")
        self.assertEqual(list(restarted._installation.tasks), [])

    async def test_ordinary_credential_change_during_resolve_creates_no_key_or_publication(self):
        await self.production()
        original = self.service.transport._post
        async def rotated(origin, path, body, headers, **kwargs):
            reply = await original(origin, path, body, headers, **kwargs)
            if path.endswith("/resolve"):
                self.entry.options["djconnect_install_token"] = "djci_" + "B" * 43
            return reply
        self.service.transport._post = rotated
        self.assertEqual((await self.post("challenge"))[0], 403)
        self.assertFalse(Path(self.key_store.path + ".claim").exists())
        self.assertTrue(all(path.endswith("/resolve") for path, _ in self.production_calls))

    async def test_failed_negative_custody_prevents_publication_and_native_challenge(self):
        await self.production()
        async def failed(_records):
            raise OSError("synthetic private store unavailable")
        self.negative_store.async_save = failed
        self.assertEqual((await self.post("challenge"))[0], 503)
        self.assertFalse(any(path.endswith("/publisher/operation") for path, _ in self.production_calls))
        self.assertFalse(any(path.endswith("/key/challenge") for path, _ in self.production_calls))

    async def test_withdrawal_during_publication_ack_never_returns_native_challenge(self):
        await self.production()
        original = self.service.transport._post
        async def withdrawn(origin, path, body, headers, **kwargs):
            reply = await original(origin, path, body, headers, **kwargs)
            if path.endswith("/publisher/operation"):
                await self.widget_consent(enabled=False, expected_revision=1)
            return reply
        self.service.transport._post = withdrawn
        self.assertEqual((await self.post("challenge"))[0], 403)
        self.assertFalse(any(path.endswith("/key/challenge") for path, _ in self.production_calls))

    async def test_restart_negative_custody_cannot_retire_another_original_event(self):
        await self.production()
        await self.registered_winner()
        self.registration.retire()
        await self.settle()
        event = (await NativePairRetirementJournal(self.persistence).pending(self.service.transport.origin))[0].body()
        event["owner_binding"] = "0" * 64
        with self.assertRaises(SurfacePushError):
            await self.service._installation.negative(event, guard=lambda: None)

    async def test_actual_different_pair_same_ha_id_uses_distinct_key_partition(self):
        await self.production()
        import json
        import uuid
        from types import SimpleNamespace
        from custom_components.djconnect.direct_rich_pair import capture_pair
        from custom_components.djconnect import native_installation_key_custody as key_custody
        entry = ConfiguredHass(entry_id="second-entry", disabled_by=None,
            state=SimpleNamespace(value="loaded"), data={"device_id":"djconnect-ios-SECOND123456", "client_type":"ios",
            "device_token":"SYNTHETIC-SECOND-PAIR"}, options={"ha_install_id":"synthetic-ha",
            "djconnect_install_token":"djci_" + "B" * 43})
        runtime = pair_fixture.fixtures.Runtime()
        runtime.entry, runtime.device_token, runtime.pairing_device_id = entry, entry.data["device_token"], entry.data["device_id"]
        runtime.surface_registration_retirement = pair_fixture.fixtures.PairingRetirement()
        self.domain[entry.entry_id] = runtime
        self.hass.config_entries.async_entries = lambda _: [self.entry, entry]
        self.path.write_text(json.dumps({"data":{"entries":[{"entry_id":e.entry_id,"domain":"djconnect",
            "data":dict(e.data),"options":dict(e.options)} for e in (self.entry,entry)]}}))
        pair_fixture.fixtures.schedule_pair_registration(self.hass, runtime)
        while runtime.surface_pair_registration.tasks:
            await asyncio.gather(*tuple(runtime.surface_pair_registration.tasks))
        await self.profiles.async_upsert_device(entry.data["device_id"], "ios", linked_profile_id="synthetic-owner")
        headers = pair_fixture.fixtures.Headers({"Authorization":"Bearer " + entry.data["device_token"],
            "X-DJConnect-Device-ID":entry.data["device_id"], "X-DJConnect-Client-Type":"ios"})
        await self.service.consent(headers, enabled=True, operation_id=str(uuid.uuid4()), expected_revision=0)
        second = capture_pair(self.hass, headers, device_id=entry.data["device_id"], client_type="ios")
        transport = self.service.transport._post
        async def resolve_second(origin,path,body,auth,**kwargs):
            if auth.get("Authorization") == "Bearer djci_" + "B" * 43:
                self.assertTrue(path.endswith("/resolve"))
                return SimpleNamespace(status=200,body={"contract_version":1,"install_credential_id":"second-credential",
                                                       "ha_install_id":"synthetic-ha"})
            return await transport(origin,path,body,auth,**kwargs)
        self.service.transport._post = resolve_second
        def partition(pair, identity):
            return fixture.PrivateStore(Path(self.temp.name) / ("partition-" + identity), "key." + identity)
        with patch.object(key_custody,"_store",side_effect=partition):
            first_authority = await self.service.selection.capture(self.pair,channel="widgetkit")
            second_authority = await self.service.selection.capture(second,channel="widgetkit")
        self.assertNotEqual(self.pair.registration.binding, second.registration.binding)
        self.assertNotEqual(first_authority.public_key_spki, second_authority.public_key_spki)
        self.assertEqual(len(list(Path(self.temp.name).glob("partition-*.claim"))),2)

    async def test_actual_sqlite_optout_uses_original_wire_revision_and_real_withdraw_ack(self):
        await self.production()
        await self.registered_winner()
        await self.widget_consent(enabled=False, expected_revision=1)
        journal = NativePairRetirementJournal(self.persistence)
        await journal.deliver_withdrawals(self.service.publisher, self.service.transport.origin,
            guard=lambda: None, deadline=self.service.monotonic() + 10)
        sent = [body for path, body in self.production_calls if path.endswith("/publisher/withdraw")]
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["consent_revision"], 1)  # Existing original publication wire.
        row = await self.persistence.async_in_transaction(lambda tx: tx.fetchone(
            "SELECT delivered,withdrawn FROM djconnect_native_pair_retirements"))
        self.assertEqual(tuple(row), (0, 1))
        await self.service._installation.prune(guard=lambda: None)
        self.assertEqual(len(await self.service._installation.records(self.negative_store)), 1)

    async def test_real_unpair_withdraw_and_retire_acks_prune_only_original_private_record(self):
        await self.production()
        await self.registered_winner()
        self.registration.retire()
        await self.settle()
        journal = NativePairRetirementJournal(self.persistence)
        await journal.deliver_withdrawals(self.service.publisher, self.service.transport.origin,
            guard=lambda: None, deadline=self.service.monotonic() + 10)
        await self.service._installation.prune(guard=lambda: None)
        self.assertEqual(len(await self.service._installation.records(self.negative_store)), 1)
        await journal.deliver(self.service.transport, guard=lambda: None, deadline=self.service.monotonic() + 10)
        await self.service._installation.prune(guard=lambda: None)
        self.assertEqual(await self.service._installation.records(self.negative_store), {})
        row = await self.persistence.async_in_transaction(lambda tx: tx.fetchone(
            "SELECT delivered,withdrawn FROM djconnect_native_pair_retirements"))
        self.assertEqual(tuple(row), (1, 1))

    async def test_wrong_retirement_ack_never_releases_pending_private_credential(self):
        await self.production()
        await self.registered_winner()
        self.registration.retire()
        await self.settle()
        journal = NativePairRetirementJournal(self.persistence)
        await journal.deliver_withdrawals(self.service.publisher, self.service.transport.origin,
            guard=lambda: None, deadline=self.service.monotonic() + 10)
        original = self.service.transport._post
        async def wrong_ack(origin, path, body, headers, **kwargs):
            reply = await original(origin, path, body, headers, **kwargs)
            if path.endswith("/retire"):
                reply.body["event_sha256"] = "0" * 64
            return reply
        self.service.transport._post = wrong_ack
        with self.assertRaises(SurfacePushError):
            await journal.deliver(self.service.transport, guard=lambda: None, deadline=self.service.monotonic() + 10)
        await self.service._installation.prune(guard=lambda: None)
        self.assertEqual(len(await self.service._installation.records(self.negative_store)), 1)
        row = await self.persistence.async_in_transaction(lambda tx: tx.fetchone(
            "SELECT delivered,withdrawn FROM djconnect_native_pair_retirements"))
        self.assertEqual(tuple(row), (0, 1))

    async def test_lost_publication_ack_retains_only_negative_credential_before_rpc(self):
        await self.production()
        original = self.service.transport._post
        async def lost(origin, path, body, headers, **kwargs):
            reply = await original(origin, path, body, headers, **kwargs)
            if path.endswith("/publisher/operation"):
                raise SurfacePushError("surface_issuer_outcome_unknown", 502)
            return reply
        self.service.transport._post = lost
        self.assertEqual((await self.post("challenge"))[0], 502)
        self.assertFalse(any(path.endswith("/key/challenge") for path, _ in self.production_calls))
        records = await self.service._installation.records(self.negative_store)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(next(iter(records.values()))["operations"]), 1)
        self.registration.retire()
        await self.settle()
        journal = NativePairRetirementJournal(self.persistence)
        await journal.deliver_withdrawals(self.service.publisher, self.service.transport.origin,
            guard=lambda: None, deadline=self.service.monotonic() + 10)
        await journal.deliver(self.service.transport, guard=lambda: None, deadline=self.service.monotonic() + 10)
        await self.service._installation.prune(guard=lambda: None)
        self.assertEqual(await self.service._installation.records(self.negative_store), {})

    async def test_65_expired_preparations_share_one_original_pair_credential(self):
        await self.production()
        clock = [self.service.monotonic()]
        self.service.monotonic = lambda: clock[0]  # Declared unit monotonic expiry, no native-clock claim.
        for _ in range(65):
            status, challenge = await self.post("challenge")
            self.assertEqual(status, 200, challenge)
            clock[0] += 121  # The original pending lease expires; never manually cleared/renewed.
        records = await self.service._installation.records(self.negative_store)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(next(iter(records.values()))["operations"]), 65)
        await self.service._installation.prune(guard=lambda: None)
        self.assertEqual(len(await self.service._installation.records(self.negative_store)), 1)
        self.assertFalse(any(path.endswith("/key/register") for path, _ in self.production_calls))

    async def test_missing_sql_original_preserves_pending_credential_and_denies_negative_use(self):
        await self.production()
        await self.registered_winner()
        records = await self.service._installation.records(self.negative_store)
        publication = next(iter(records.values()))["publication"]
        event = self.service._installation.original_event(publication)
        await self.persistence.async_in_transaction(lambda tx: tx.execute(
            "DELETE FROM djconnect_native_pair_retirements"))  # Explicit missing-original corruption fixture.
        await self.service._installation.prune(guard=lambda: None)
        self.assertEqual(await self.service._installation.records(self.negative_store), records)
        with self.assertRaises(SurfacePushError):
            await self.service._installation.negative(event, guard=lambda: None)
