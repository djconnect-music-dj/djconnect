"""Real P256, SQLite pair/consent and private atomic files; fake API only.

The file store below models HA private atomic Store semantics for unit tests.
It is not an actual HA SDK, API enrollment or provider/device acceptance proof.
"""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests import test_native_pair_enrollment as pair_fixture
from tests.test_profile_storage import ProfilePlatformStorage
from custom_components.djconnect import profile_observation as observation
from custom_components.djconnect.direct_rich_pair import capture_pair
from custom_components.djconnect.domain.storage import STORE_KEY, STORE_VERSION
from custom_components.djconnect.native_pair_enrollment import NativePairEnrollment
from custom_components.djconnect import native_installation_key_custody as custody
from custom_components.djconnect.surface_push_contract import SurfacePushError


class PrivateStore:
    def __init__(self, path, key, version=1):
        self.path, self.key, self.version = os.fspath(path), key, version

    async def async_load(self):
        try:
            return json.loads(Path(self.path).read_text())["data"]
        except FileNotFoundError:
            return None

    async def async_save(self, data):
        staged = self.path + ".staging"
        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"key": self.key, "version": self.version, "data": data}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, self.path)


class HassFixture(SimpleNamespace):
    # HA's real HomeAssistant is hashable/weak-referenceable; SimpleNamespace
    # in the older pair-only fixture is not suitable for profile observations.
    __hash__ = object.__hash__


class NativeInstallationCustodyTests(pair_fixture.NativePairEnrollmentTests):
    async def asyncSetUp(self):
        maintenance = patch("custom_components.djconnect.session_history_maintenance.schedule_history_maintenance")
        maintenance.start()
        self.addCleanup(maintenance.stop)
        with patch.object(pair_fixture, "SimpleNamespace", HassFixture):
            await super().asyncSetUp()

    async def prepare_custodian(self):
        directory = Path(self.temp.name)
        observation.bootstrap_from_integration_setup(self.hass)
        store = PrivateStore(directory / "profiles", STORE_KEY, STORE_VERSION)
        self.profiles = ProfilePlatformStorage(self.hass, store=store)
        observation.publish_manager(self.hass, self.domain, self.profiles)
        await self.profiles.async_create_profile("Synthetic owner", profile_id="synthetic-owner")
        await self.profiles.async_upsert_device(self.runtime.pairing_device_id, "ios",
            linked_profile_id="synthetic-owner")
        self.service.selection = custody.InstallationWidgetKeyCustodian(self.service)
        self.key_store = PrivateStore(directory / "custody", "synthetic-key-store")
        override = patch.object(custody, "_store", return_value=self.key_store)
        override.start()
        self.addCleanup(override.stop)
        self.pair = capture_pair(self.hass, self.headers,
            device_id=self.runtime.pairing_device_id, client_type="ios")
        return self.service.selection

    async def test_constructor_is_dormant_without_key_or_store_effect(self):
        with patch.object(custody, "_store", side_effect=AssertionError("No startup store")), \
                patch.object(custody, "_generate", side_effect=AssertionError("No startup crypto")):
            service = NativePairEnrollment(self.hass, self.service.transport, publisher=self.publisher)
            self.assertIsInstance(service.selection, custody.InstallationWidgetKeyCustodian)

    async def test_actual_pair_consent_profile_generate_once_and_reuse_real_signer(self):
        selected = await self.prepare_custodian()
        generated = custody._generate
        with patch.object(custody, "_generate", wraps=generated) as factory:
            first, second = await asyncio.gather(selected.capture(self.pair, channel="widgetkit"),
                selected.capture(self.pair, channel="widgetkit"))
            self.assertEqual(factory.call_count, 1)
        self.assertEqual(first.public_key_spki, second.public_key_spki)
        self.assertEqual(first.bindings, second.bindings)
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        from cryptography.hazmat.primitives.serialization import load_der_public_key
        message = b"synthetic proof of actual P256 custody"
        signature = first.sign(message)
        load_der_public_key(first.public_key_spki).verify(encode_dss_signature(
            int.from_bytes(signature[:32]), int.from_bytes(signature[32:])), message, ec.ECDSA(hashes.SHA256()))
        self.assertEqual(os.stat(self.key_store.path).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.key_store.path + ".claim").st_mode & 0o777, 0o600)
        # New custodian reads the original key, not a fabricated registration ACK.
        self.service.selection = custody.InstallationWidgetKeyCustodian(self.service)
        with patch.object(custody, "_generate", side_effect=AssertionError("Never regenerate")):
            third = await self.service.selection.capture(self.pair, channel="widgetkit")
        self.assertEqual(first.public_key_spki, third.public_key_spki)

    async def test_disabled_consent_and_wrong_channel_make_no_claim_or_key(self):
        selected = await self.prepare_custodian()
        await self.widget_consent(enabled=False, expected_revision=1)
        with patch.object(custody, "_generate", side_effect=AssertionError("No crypto")):
            for channel in ("widgetkit", "watch_smart_stack", "live_activity"):
                with self.assertRaises(SurfacePushError):
                    await selected.capture(self.pair, channel=channel)
        self.assertFalse(Path(self.key_store.path + ".claim").exists())

    async def test_ambiguous_generation_claim_survives_restart_without_regeneration(self):
        selected = await self.prepare_custodian()
        with patch.object(custody, "_generate", side_effect=OSError("synthetic lost generation result")):
            with self.assertRaises(SurfacePushError):
                await selected.capture(self.pair, channel="widgetkit")
        self.assertTrue(Path(self.key_store.path + ".claim").exists())
        self.service.selection = custody.InstallationWidgetKeyCustodian(self.service)
        with patch.object(custody, "_generate", side_effect=AssertionError("No retry crypto")):
            with self.assertRaises(SurfacePushError):
                await self.service.selection.capture(self.pair, channel="widgetkit")

    async def test_malformed_private_state_never_regenerates(self):
        selected = await self.prepare_custodian()
        Path(self.key_store.path).write_bytes(b"not json")
        os.chmod(self.key_store.path, 0o600)
        with patch.object(custody, "_generate", side_effect=AssertionError("No replacement")):
            with self.assertRaises(SurfacePushError):
                await selected.capture(self.pair, channel="widgetkit")
        self.assertFalse(Path(self.key_store.path + ".claim").exists())

    async def test_actual_credential_rotation_cannot_replace_original_key(self):
        selected = await self.prepare_custodian()
        await selected.capture(self.pair, channel="widgetkit")
        before = Path(self.key_store.path).read_bytes()
        saved = json.loads(self.install_path.read_text())
        saved["data"]["install_token"] = "djci_rotated"
        saved["data"]["credential_id"] = "rotated"
        self.install_path.write_text(json.dumps(saved))
        with patch.object(custody, "_generate", side_effect=AssertionError("No replacement")):
            with self.assertRaises(SurfacePushError):
                await selected.capture(self.pair, channel="widgetkit")
        self.assertEqual(Path(self.key_store.path).read_bytes(), before)

    async def test_late_consent_withdrawal_after_claim_permits_no_generation(self):
        selected = await self.prepare_custodian()
        claim = custody._claim
        generated = []
        # Executor completion is an actual async boundary; withdraw on its return.
        executor = self.hass.async_add_executor_job
        async def after_claim(fn, *args):
            result = await executor(fn, *args)
            if fn is claim:
                await self.widget_consent(enabled=False, expected_revision=1)
            return result
        self.hass.async_add_executor_job = after_claim
        with patch.object(custody, "_generate", side_effect=lambda: generated.append(True)):
            with self.assertRaises(SurfacePushError):
                await selected.capture(self.pair, channel="widgetkit")
        self.assertEqual(generated, [])
        self.assertTrue(Path(self.key_store.path + ".claim").exists())

    async def test_orphaned_original_key_cannot_create_a_replacement_claim(self):
        selected = await self.prepare_custodian()
        await selected.capture(self.pair, channel="widgetkit")
        before = Path(self.key_store.path).read_bytes()
        Path(self.key_store.path + ".claim").unlink()  # Explicit corruption fixture.
        with patch.object(custody, "_generate", side_effect=AssertionError("No replacement")):
            with self.assertRaises(SurfacePushError):
                await selected.capture(self.pair, channel="widgetkit")
        self.assertFalse(Path(self.key_store.path + ".claim").exists())
        self.assertEqual(Path(self.key_store.path).read_bytes(), before)

    async def test_private_file_symlink_or_public_mode_never_supplies_custody(self):
        selected = await self.prepare_custodian()
        await selected.capture(self.pair, channel="widgetkit")
        os.chmod(self.key_store.path, 0o644)
        with self.assertRaises(SurfacePushError):
            await selected.capture(self.pair, channel="widgetkit")
        os.chmod(self.key_store.path, 0o600)
        original = self.key_store.path + ".original"
        os.rename(self.key_store.path, original)
        os.symlink(original, self.key_store.path)
        with self.assertRaises(SurfacePushError):
            await selected.capture(self.pair, channel="widgetkit")

    async def test_private_profile_cannot_create_claim_or_generate_key(self):
        selected = await self.prepare_custodian()
        from custom_components.djconnect.domain import ProfilePrivacyMode
        await self.profiles.async_update_profile("synthetic-owner", privacy_mode=ProfilePrivacyMode.PRIVATE)
        with patch.object(custody, "_generate", side_effect=AssertionError("Private source cannot generate")):
            with self.assertRaises(SurfacePushError):
                await selected.capture(self.pair, channel="widgetkit")
        self.assertFalse(Path(self.key_store.path + ".claim").exists())

    async def test_source_change_after_claim_closes_before_generation(self):
        selected = await self.prepare_custodian()
        claim, executor = custody._claim, self.hass.async_add_executor_job
        async def change_source(fn, *args):
            result = await executor(fn, *args)
            if fn is claim:
                await self.profiles.async_update_profile("synthetic-owner", display_name="Changed source")
            return result
        self.hass.async_add_executor_job = change_source
        with patch.object(custody, "_generate", side_effect=AssertionError("Original source retired")):
            with self.assertRaises(SurfacePushError):
                await selected.capture(self.pair, channel="widgetkit")
        self.assertTrue(Path(self.key_store.path + ".claim").exists())
