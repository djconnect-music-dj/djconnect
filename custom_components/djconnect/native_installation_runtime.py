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
from .persistence import PERSISTENCE_SERVICE_KEY, PersistenceService
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
            await self.custody.retain(record, body, guard=guard)
        else:
            token = await self.custody.negative(body, guard=guard)
        guard()
        require(canonical(body) == original_body, _ERROR, 403)
        reply = await self.transport._post(self.origin, _PREFIX + "publisher/" + action, body,
            {"Authorization": "Bearer " + token}, guard=guard, deadline=deadline)
        require(reply.status == 200 and canonical(reply.body) == '{"ok":true}'
                and canonical(body) == original_body, _ERROR, 502)
        if action == "operation":
            await self.custody.current(record)
            guard()
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
        return Store(self.service.hass, 2, "djconnect_native_installation_negative", private=True, atomic_writes=True)

    @staticmethod
    def pair_context(publication):
        return {name: publication[name] for name in
                ("pairing_generation", "pair_binding", "owner_binding", "device_binding", "core_key_thumbprint")}

    @classmethod
    def record_key(cls, record):
        return hashlib.sha256(canonical([record["origin"], record["ha_install_id"], record["credential_id"],
            record["local_binding"], cls.pair_context(record["publication"])]).encode()).hexdigest()

    @staticmethod
    def original_event(publication):
        event = {**publication, "api_audience": "djc-native-push/1", "event_id": publication["operation_id"]}
        event.pop("consent_revision")
        return event

    @classmethod
    def operation_digest(cls, publication):
        return hashlib.sha256(canonical([cls.original_event(publication), publication["consent_revision"]]).encode()).hexdigest()

    async def records(self, store):
        document = await self.service.hass.async_add_executor_job(_private_read, store.path, 131072)
        if document is None:
            return {}
        require(type(document) is dict and type(document.get("version")) is int and document["version"] == 2
                and document.get("key") == store.key
                and type(document.get("data")) is dict and len(document["data"]) <= 64, _ERROR, 503)
        records = document["data"]
        fields = {"contract_version", "install_credential_id", "operation_id", "pairing_generation", "pair_binding",
                  "owner_binding", "device_binding", "core_key_thumbprint", "request_expires_at_ms", "consent_revision"}
        for key, record in records.items():
            require(type(record) is dict and set(record) == {"credential_id", "origin", "ha_install_id", "local_binding",
                    "install_token", "publication", "operations"}, _ERROR, 503)
            publication = record["publication"]
            require(type(publication) is dict and set(publication) == fields
                    and type(publication["contract_version"]) is int and publication["contract_version"] == 1
                    and record["origin"] == DEFAULT_API_BASE_URL
                    and type(record["ha_install_id"]) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", record["ha_install_id"])
                    and type(record["local_binding"]) is str and re.fullmatch(r"[a-f0-9]{64}", record["local_binding"])
                    and type(record["install_token"]) is str and re.fullmatch(r"djci_[A-Za-z0-9_-]{43}", record["install_token"])
                    and record["credential_id"] == publication["install_credential_id"]
                    and all(type(publication[name]) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", publication[name])
                            for name in ("install_credential_id", "operation_id", "pairing_generation"))
                    and all(type(publication[name]) is str and re.fullmatch(r"[a-f0-9]{64}", publication[name])
                            for name in ("pair_binding", "owner_binding", "device_binding", "core_key_thumbprint"))
                    and all(type(publication[name]) is int and 0 < publication[name] < 2**53
                            for name in ("request_expires_at_ms", "consent_revision"))
                    and type(record["operations"]) is dict and 0 < len(record["operations"]) <= 1024
                    and all(type(op) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", op)
                            and type(digest) is str and re.fullmatch(r"[a-f0-9]{64}", digest)
                            for op, digest in record["operations"].items())
                    and record["operations"].get(publication["operation_id"]) == self.operation_digest(publication)
                    and key == self.record_key(record), _ERROR, 503)
        return records

    async def journal_originals(self, record, *, guard):
        """Only real staged SQL originals of this original pair/context qualify."""
        persistence = self.service.hass.data.get("djconnect", {}).get(PERSISTENCE_SERVICE_KEY)
        require(isinstance(persistence, PersistenceService) and persistence.readiness.ready, _ERROR, 503)
        guard()
        self.selected()
        context = self.pair_context(record["publication"])
        def read(tx):
            return [tuple(row) for row in tx.fetchall(
                "SELECT event.original,event.consent_revision,event.delivered,event.withdrawn,pair.state,EXISTS ("
                "SELECT 1 FROM djconnect_native_widget_consent choice "
                "WHERE choice.local_binding=event.local_binding AND choice.enabled=0 "
                "AND choice.revision>event.consent_revision) "
                "FROM djconnect_native_pair_retirements event "
                "JOIN djconnect_surface_pairs pair ON pair.binding=event.local_binding "
                "WHERE event.local_binding=? AND event.origin=? AND event.publisher_origin=? "
                "AND json_extract(event.original,'$.api_audience')='djc-native-push/1' "
                "AND json_extract(event.original,'$.install_credential_id')=? "
                "AND json_extract(event.original,'$.pairing_generation')=? "
                "AND json_extract(event.original,'$.pair_binding')=? "
                "AND json_extract(event.original,'$.owner_binding')=? "
                "AND json_extract(event.original,'$.device_binding')=? "
                "AND json_extract(event.original,'$.core_key_thumbprint')=?",
                (record["local_binding"], DEFAULT_API_BASE_URL, DEFAULT_API_BASE_URL, record["credential_id"],
                 *context.values()))]
        rows = await persistence.async_in_transaction(read)
        guard()
        self.selected()
        require(self.service.hass.data.get("djconnect", {}).get(PERSISTENCE_SERVICE_KEY) is persistence
                and persistence.readiness.ready, _ERROR, 503)
        result = []
        for row in rows:
            event = json.loads(row[0])
            require(type(event) is dict and event.get("event_id") == event.get("operation_id")
                    and canonical(event) == row[0], _ERROR, 503)
            publication = {key: value for key, value in event.items() if key not in ("api_audience", "event_id")}
            publication["consent_revision"] = row[1]
            digest = self.operation_digest(publication)
            known = record["operations"].get(event["operation_id"])
            require(known is None or known == digest, _ERROR, 503)
            result.append((event, row[1], row[2], row[3], row[4], row[5], digest))
        return result

    async def closed_records(self, records, *, guard):
        retained = {}
        for key, record in records.items():
            rows = await self.journal_originals(record, guard=guard)
            actual = {row[0]["operation_id"]: row[6] for row in rows}
            complete = (bool(rows) and all(actual.get(op) == digest for op, digest in record["operations"].items())
                        and all(row[2:5] == (1, 1, "retired") for row in rows))
            if not complete:
                retained[key] = record
        return retained

    async def save_records(self, store, records, *, guard):
        # Check the real HA private Store envelope bound before writing; never
        # turn our own capacity limit into an unreadable, oversized credential file.
        envelope = {"version": 2, "minor_version": 1, "key": store.key, "data": records}
        require(len(json.dumps(envelope, indent=2, ensure_ascii=False).encode()) <= 131072, _ERROR, 503)
        guard()
        await store.async_save(records)
        actual = await self.records(store)
        guard()
        require(actual == records, _ERROR, 503)

    async def prune(self, *, guard):
        task = asyncio.create_task(self._prune(guard=guard))
        task.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)
        await asyncio.shield(task)

    async def _prune(self, *, guard):
        async with self.lock:
            store = self.store()
            records = await self.records(store)
            retained = await self.closed_records(records, guard=guard)
            if retained != records:
                await self.save_records(store, retained, guard=guard)

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
            records = await self.closed_records(records, guard=guard)
            await self.current(record)
            guard()
            retained = {"credential_id": record.credential_id, "origin": record.original[0],
                        "ha_install_id": record.original[2], "local_binding": record.pair.registration.binding,
                        "install_token": record.original[1], "publication": dict(publication),
                        "operations": {publication["operation_id"]: self.operation_digest(publication)}}
            staged = await self.journal_originals(retained, guard=guard)
            expected = canonical(self.original_event(publication))
            require(any(canonical(row[0]) == expected and row[1] == publication["consent_revision"]
                        for row in staged), _ERROR, 403)
            key = self.record_key(retained)
            if key in records:
                existing = records[key]
                require(existing["install_token"] == retained["install_token"]
                        and self.pair_context(existing["publication"]) == self.pair_context(publication), _ERROR, 503)
                op = publication["operation_id"]
                digest = self.operation_digest(publication)
                require(op not in existing["operations"] or existing["operations"][op] == digest, _ERROR, 503)
                existing["operations"][op] = digest
                require(len(existing["operations"]) <= 1024, _ERROR, 503)
            else:
                require(len(records) < 64, _ERROR, 503)
                records[key] = retained
            await self.save_records(store, records, guard=guard)
            await self.current(record)
            guard()

    async def negative(self, event, *, guard):
        """Private records supply only credentials; actual SQL supplies the original."""
        guard()
        records = await self.records(self.store())
        guard()
        candidates = []
        retirement = "install_credential_id" in event
        if not retirement:
            require(set(event) == {"contract_version", "pair_binding", "consent_revision"}
                    and type(event["contract_version"]) is int and event["contract_version"] == 1
                    and type(event["consent_revision"]) is int, _ERROR, 403)
        for record in records.values():
            if event.get("pair_binding") != record["publication"]["pair_binding"]:
                continue
            for row in await self.journal_originals(record, guard=guard):
                if retirement:
                    if canonical(event) != canonical(row[0]) or row[4] != "retired":
                        continue
                elif event["consent_revision"] != row[1] or not (row[4] == "retired" or row[5]):
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
