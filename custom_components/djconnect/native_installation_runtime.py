"""Automatic genuine installation publisher; no CF or native admission fallback.

Positive operations use only a current ordinary loaded/persisted pairing and
its actual API bearer. Persisted publication credentials are negative-only:
they can withdraw/retire their exact original request after unpair/restart,
never supply a positive key, pairing, first-key ACK or issuer policy.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from weakref import WeakKeyDictionary

from .const import CONF_API_BASE_URL, CONF_DJCONNECT_INSTALL_TOKEN, CONF_HA_INSTALL_ID, DEFAULT_API_BASE_URL
from .native_pair_enrollment import KEY, NativePairEnrollment, _durable_pair
from .native_installation_key_custody import _private_read
from .surface_issuer_transport import IssuerHTTPS
from .surface_push_contract import require
from .surface_push_wire import canonical

_ERROR = "native_installation_unavailable"
_PREFIX = "/v1/push/native/installation/"


def _loaded(entry):
    config = {**entry.data, **entry.options}
    token = config.get(CONF_DJCONNECT_INSTALL_TOKEN)
    install = config.get(CONF_HA_INSTALL_ID)
    origin = config.get(CONF_API_BASE_URL, DEFAULT_API_BASE_URL)
    require(type(token) is str and re.fullmatch(r"djci_[A-Za-z0-9_-]{43}", token)
            and type(install) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", install)
            and origin == DEFAULT_API_BASE_URL, _ERROR, 503)
    return origin, token, install


def _persisted(path, entry_id, expected):
    try:
        saved = json.loads(Path(path).read_bytes())
        rows = [row for row in saved["data"]["entries"] if row.get("entry_id") == entry_id
                and row.get("domain") == "djconnect"]
        if len(rows) != 1:
            return False
        row = rows[0]
        return _loaded(type("SavedEntry", (), {"data": row["data"], "options": row["options"]})) == expected
    except (OSError, ValueError, KeyError, TypeError):
        return False


@dataclass(frozen=True, repr=False)
class _OriginalCredential:
    pair: object
    original: tuple
    credential_id: str


class InstallationHTTPS(IssuerHTTPS):
    origin = DEFAULT_API_BASE_URL

    async def resolve(self, token, *, guard, deadline):
        return await self._post(self.origin, _PREFIX + "resolve", {"contract_version": 1},
            {"Authorization": "Bearer " + token}, guard=guard, deadline=deadline)

    async def post_first_key(self, action, body, install_token, *, currentness, guard, deadline):
        require(action in ("challenge", "register", "status/challenge", "status"), _ERROR, 403)
        return await self._post(self.origin, "/v1/push/native/key/" + action, body,
            {"Authorization": "Bearer " + install_token,
             "X-DJC-First-Key-Currentness": canonical(currentness)}, guard=guard, deadline=deadline)

    async def post_retirement(self, body, *, guard, deadline):
        token = await self.custody.negative(body, guard=guard)
        return await self._post(self.origin, "/v1/push/native/key/retire", body,
            {"Authorization": "Bearer " + token}, guard=guard, deadline=deadline)


class _InstallationPublisher:
    origin = DEFAULT_API_BASE_URL

    def __init__(self, custody, transport):
        self.custody, self.transport = custody, transport

    async def publish(self, action, body, *, guard, deadline):
        require(action in ("operation", "withdraw"), _ERROR, 403)
        guard()
        original_body = canonical(body)
        if action == "operation":
            record = self.custody.tasks.get(asyncio.current_task())
            require(record is not None and body.get("install_credential_id") == record.credential_id, _ERROR, 403)
            await self.custody.current(record)
            token = record.original[1]
        else:
            token = await self.custody.negative(body, guard=guard)
        guard()
        reply = await self.transport._post(self.origin, _PREFIX + "publisher/" + action, body,
            {"Authorization": "Bearer " + token}, guard=guard, deadline=deadline)
        require(reply.status == 200 and canonical(reply.body) == '{"ok":true}'
                and canonical(body) == original_body, _ERROR, 502)
        if action == "operation":
            await self.custody.current(record)
            guard()
            # Persist/read back negative-only original custody before any key
            # challenge can be returned to the native client.
            await self.custody.retain(record, body, guard=guard)
        guard()


class InstallationCredentialCustody:
    def __init__(self, service):
        self.service = service
        self.transport = service.transport
        self.publisher = None  # Bound once by the concrete composition below.
        self.tasks = WeakKeyDictionary()
        self.lock = service.hass.data.setdefault("_djconnect_native_negative_writer", asyncio.Lock())

    def selected(self):
        require(self.service.hass.data.get("djconnect", {}).get(KEY) is self.service
                and self.service._installation is self
                and self.service.transport is self.transport
                and self.service.publisher is self.publisher
                and self.transport.custody is self, _ERROR, 403)

    async def current(self, record):
        service, pair = self.service, record.pair
        self.selected()
        require(pair.hass.data.get("djconnect", {}).get(KEY) is service
                and service._installation is self and pair.current()
                and _loaded(pair.entry) == record.original, _ERROR, 403)
        await _durable_pair(pair)
        saved = await pair.hass.async_add_executor_job(_persisted,
            pair.hass.config.path(".storage", "core.config_entries"), pair.entry.entry_id, record.original)
        self.selected()
        require(saved and pair.current() and _loaded(pair.entry) == record.original
                and pair.hass.data.get("djconnect", {}).get(KEY) is service, _ERROR, 403)

    async def credential(self, pair):
        original = _loaded(pair.entry)
        record = _OriginalCredential(pair, original, "")
        await self.current(record)
        deadline = self.service.monotonic() + 10

        def guard():
            self.selected()
            require(pair.current() and _loaded(pair.entry) == original
                    and pair.hass.data.get("djconnect", {}).get(KEY) is self.service
                    and self.service._installation is self and self.service.monotonic() < deadline, _ERROR, 403)

        reply = await self.service.transport.resolve(original[1], guard=guard, deadline=deadline)
        guard()
        body = reply.body
        require(set(body) == {"contract_version", "install_credential_id", "ha_install_id"}
                and type(body["contract_version"]) is int and body["contract_version"] == 1
                and body["ha_install_id"] == original[2]
                and type(body["install_credential_id"]) is str
                and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", body["install_credential_id"]), _ERROR, 502)
        record = _OriginalCredential(pair, original, body["install_credential_id"])
        await self.current(record)
        guard()
        self.tasks[asyncio.current_task()] = record
        return original[1], record.credential_id

    def store(self):
        from homeassistant.helpers.storage import Store
        return Store(self.service.hass, 1, "djconnect_native_installation_negative", private=True, atomic_writes=True)

    async def records(self, store):
        document = await self.service.hass.async_add_executor_job(_private_read, store.path, 131072)
        if document is None:
            return {}
        require(type(document) is dict and type(document.get("version")) is int and document["version"] == 1
                and document.get("key") == store.key
                and type(document.get("data")) is dict and len(document["data"]) <= 64, _ERROR, 503)
        records = document["data"]
        fields = {"contract_version", "install_credential_id", "operation_id", "pairing_generation", "pair_binding",
                  "owner_binding", "device_binding", "core_key_thumbprint", "request_expires_at_ms", "consent_revision"}
        for key, record in records.items():
            require(type(record) is dict and set(record) == {"credential_id", "origin", "install_token", "publication"}, _ERROR, 503)
            publication = record["publication"]
            require(type(publication) is dict and set(publication) == fields
                    and type(publication["contract_version"]) is int and publication["contract_version"] == 1
                    and record["origin"] == DEFAULT_API_BASE_URL
                    and type(record["install_token"]) is str and re.fullmatch(r"djci_[A-Za-z0-9_-]{43}", record["install_token"])
                    and record["credential_id"] == publication["install_credential_id"]
                    and all(type(publication[name]) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", publication[name])
                            for name in ("install_credential_id", "operation_id", "pairing_generation"))
                    and all(type(publication[name]) is str and re.fullmatch(r"[a-f0-9]{64}", publication[name])
                            for name in ("pair_binding", "owner_binding", "device_binding", "core_key_thumbprint"))
                    and all(type(publication[name]) is int and 0 < publication[name] < 2**53
                            for name in ("request_expires_at_ms", "consent_revision"))
                    and key == hashlib.sha256(canonical([record["credential_id"], publication["operation_id"]]).encode()).hexdigest(),
                    _ERROR, 503)
        return records

    async def retain(self, record, publication, *, guard):
        # The worker owns the lock until the atomic file operation has actually
        # finished, even if the requesting HTTP task is cancelled mid-write.
        task = asyncio.create_task(self._retain(record, publication, guard=guard))
        task.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)
        await asyncio.shield(task)

    async def _retain(self, record, publication, *, guard):
        async with self.lock:
            store = self.store()
            records = await self.records(store)
            await self.current(record)
            guard()
            operation = publication["operation_id"]
            key = hashlib.sha256(canonical([record.credential_id, operation]).encode()).hexdigest()
            retained = {"credential_id": record.credential_id, "origin": record.original[0],
                        "install_token": record.original[1], "publication": dict(publication)}
            require((key in records and records[key] == retained) or (key not in records and len(records) < 64), _ERROR, 503)
            records[key] = retained
            await store.async_save(records)
            actual = await self.records(store)
            await self.current(record)
            guard()
            require(actual == records, _ERROR, 503)

    async def negative(self, event, *, guard):
        """Only a genuine pending journal event calls this private negative port."""
        guard()
        records = await self.records(self.store())
        guard()
        candidates = []
        for record in records.values():
            require(type(record) is dict and set(record) == {"credential_id", "origin", "install_token", "publication"}, _ERROR, 503)
            publication = record["publication"]
            require(type(publication) is dict and record["origin"] == DEFAULT_API_BASE_URL
                    and type(record["install_token"]) is str
                    and re.fullmatch(r"djci_[A-Za-z0-9_-]{43}", record["install_token"]), _ERROR, 503)
            if event.get("pair_binding") != publication.get("pair_binding"):
                continue
            if "install_credential_id" in event:
                expected = {**publication, "api_audience": "djc-native-push/1", "event_id": publication.get("operation_id")}
                expected.pop("consent_revision", None)
                if event != expected or record["credential_id"] != event["install_credential_id"]:
                    continue
            else:
                require(set(event) == {"contract_version", "pair_binding", "consent_revision"}
                        and type(event["consent_revision"]) is int, _ERROR, 403)
                if event["consent_revision"] <= publication.get("consent_revision", -1):
                    continue
            candidates.append(record["install_token"])
        require(len(set(candidates)) == 1, _ERROR, 403)
        return candidates[0]


def create_installation_service(hass):
    """Dormant construction only; original entry/pair/opt-in later supplies custody."""
    transport = InstallationHTTPS()
    service = NativePairEnrollment(hass, transport, api_audience="djc-native-push/1")
    custody = InstallationCredentialCustody(service)
    service._installation = transport.custody = custody
    service.publisher = custody.publisher = _InstallationPublisher(custody, transport)
    return service
