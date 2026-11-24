"""Installation-owned private first-key custody, not API/issuer enrollment.

Construction is dormant. Only the selected NativePairEnrollment service may
request a WidgetKit key after its actual durable pair, stored installation
credential, explicit SQLite consent and persisted profile/source qualify.
A synced exclusive claim precedes generation. Unknown/malformed/mismatched
state is never a new installation and never permits replacement key material.
No private material leaves this service/HA private atomic store. Restoring the
same private key does not restore a registration winner or issuer permission.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

from .native_widget_consent import read_widget_consent
from .native_widget_selection import WidgetEnrollmentSelection, capture_widget_owner
from .surface_push_contract import require
from .surface_push_wire import canonical

_ERROR = "native_installation_key_unavailable"
_MAX_FILE = 16384


def _unique(items):
    result = dict(items)
    require(len(result) == len(items), _ERROR, 503)
    return result


def _private_read(path, maximum=_MAX_FILE):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None  # Only actual absence is a fresh state.
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600
                and 0 < info.st_size <= maximum, _ERROR, 503)
        raw = stream.read(maximum + 1)
        require(len(raw) == info.st_size, _ERROR, 503)
        return json.loads(raw, object_pairs_hook=_unique)


def _read_claim(path, binding):
    existing = _private_read(path)
    require(type(existing) is dict and set(existing) == {"binding", "claim_id"}
            and existing["binding"] == binding
            and str(uuid.UUID(existing["claim_id"])) == existing["claim_id"]
            and uuid.UUID(existing["claim_id"]).version == 4, _ERROR, 503)
    return existing


def _claim(path, binding, allow_create=True):
    """No unlink/retry/reset path: an uncertain write consumes the claim."""
    if not allow_create:
        return _read_claim(path, binding), False
    body = {"binding": binding, "claim_id": str(uuid.uuid4())}
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return _read_claim(path, binding), False
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(body).encode())
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return body, True


def _generate():
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
    key = ec.generate_private_key(ec.SECP256R1())
    return {"binding_key_b64": base64.b64encode(os.urandom(32)).decode("ascii"),
            "signing_key_der_b64": base64.b64encode(key.private_bytes(
                Encoding.DER, PrivateFormat.PKCS8, NoEncryption())).decode("ascii")}


def _selection(document, store, claim):
    from cryptography.hazmat.primitives.serialization import load_der_private_key
    require(type(document) is dict and document.get("key") == store.key
            and type(document.get("version")) is int and document["version"] == 1
            and type(document.get("data")) is dict, _ERROR, 503)
    data = document["data"]
    require(set(data) == {"claim", "binding_key_b64", "signing_key_der_b64"}
            and data["claim"] == claim, _ERROR, 503)
    return WidgetEnrollmentSelection(base64.b64decode(data["binding_key_b64"], validate=True),
        load_der_private_key(base64.b64decode(data["signing_key_der_b64"], validate=True), None))


def _store(pair, identity):
    from homeassistant.helpers.storage import Store
    return Store(pair.hass, 1, "djconnect_native_key." + identity,
                 private=True, atomic_writes=True)


class InstallationWidgetKeyCustodian:
    """Actual selected service adapter; no caller JSON or startup key effects."""
    def __init__(self, service):
        self._service = service
        self._lock = asyncio.Lock()

    async def capture(self, pair, *, channel, existing_only=False):
        from cryptography.exceptions import UnsupportedAlgorithm
        from .surface_push_contract import SurfacePushError
        try:
            return await self._capture(pair, channel=channel, existing_only=existing_only)
        except SurfacePushError:
            raise
        except (OSError, ValueError, TypeError, KeyError, UnsupportedAlgorithm):
            # Do not put decoder/key/store contents into HA exception logs.
            require(False, _ERROR, 503)

    async def _capture(self, pair, *, channel, existing_only=False):
        from .native_pair_enrollment import KEY
        service = self._service
        require(channel == "widgetkit", _ERROR, 503)
        snapshot, _, _ = await capture_widget_owner(pair, channel=channel)
        consent = await read_widget_consent(pair)
        require(consent.enabled, "native_widget_consent_required", 403)
        token, credential_id = await service.credential(pair)
        transport, publisher = service.transport, service.publisher
        binding = {**service.install_binding(pair), "credential_id": credential_id,
                   "credential_sha256": hashlib.sha256(token.encode("ascii")).hexdigest()}
        identity = hashlib.sha256(canonical([binding["origin"], binding["installation"], pair.registration.binding]).encode()).hexdigest()
        store = _store(pair, identity)

        def current():
            require(pair.hass.data.get("djconnect", {}).get(KEY) is service
                    and service.selection is self and service.transport is transport
                    and service.publisher is publisher and pair.current() and snapshot.current()
                    and service.install_binding(pair) == {key: value for key, value in binding.items()
                        if key not in ("credential_id", "credential_sha256")}, _ERROR, 403)

        async def recheck():
            current()
            require(await read_widget_consent(pair) == consent, _ERROR, 403)
            actual_token, actual_id = await service.credential(pair)
            current()
            require(actual_id == credential_id and hashlib.sha256(actual_token.encode("ascii")).hexdigest()
                    == binding["credential_sha256"], _ERROR, 403)

        async with self._lock:
            await recheck()
            # Both are private local custody; neither is an API acknowledgement.
            document = await pair.hass.async_add_executor_job(_private_read, store.path)
            await recheck()
            require(not existing_only or document is not None, _ERROR, 503)
            claim, fresh = await pair.hass.async_add_executor_job(_claim, os.fspath(store.path) + ".claim", binding, document is None and not existing_only)
            await recheck()
            if document is None:
                require(fresh, _ERROR, 503)  # Unknown generation/write outcome: no retry.
                material = await pair.hass.async_add_executor_job(_generate)
                await recheck()
                await store.async_save({"claim": claim, **material})
                await recheck()
                document = await pair.hass.async_add_executor_job(_private_read, store.path)
                await recheck()
            else:
                require(not fresh, _ERROR, 503)  # Orphaned original key is not new custody.
            selection = _selection(document, store, claim)
            authority = await selection.capture(pair, channel=channel)
            await recheck()
            return authority
