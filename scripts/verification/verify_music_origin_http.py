"""Real HA/TLS/paired-operation/SQLite origin gate; public/model inputs synthetic."""
from urllib.parse import urlsplit

import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import uuid

ROOT = Path(os.environ["DJC_SOURCE_ROOT"])
sys.path[:0] = [str(ROOT), str(ROOT / "scripts/verification")]
owner = importlib.import_module("verify_requested_moments_http")
BASELINE = owner.qualify


async def qualify(hass, manager, history, request, client):
    baseline = await BASELINE(hass, manager, history, request, client)
    from custom_components.djconnect import pipeline
    from custom_components.djconnect.ask_dj import public_research
    from custom_components.djconnect.hybrid_service import operations

    active = manager.current_active("profile-a")
    runtime = hass.data["djconnect"]["owner-entry"]
    identity = {"device_id": runtime.entry.data["device_id"], "client_type": "ios"}
    headers = {
        "Authorization": "Bearer " + runtime.entry.data["device_token"],
        "X-DJConnect-Device-ID": identity["device_id"],
    }
    requests, calls, urls = [], [], []

    async def http(path, body):
        response = await client.post(path, json={"identity": identity, **body}, headers=headers)
        data = await response.json()
        requests.append({"path": path, "status": response.status, "scheme": response.url.scheme})
        assert (
            response.url.scheme == "https" and response.headers.get("Cache-Control") == "no-store"
        )
        return data, response.status

    async def fetch(self, url, **kwargs):
        await self.guard()
        self.requests += 1
        urls.append(url)
        if url.endswith("/robots.txt"):
            return 200, "User-agent: *\nAllow: /\n", url
        if urlsplit(url).hostname == "html.duckduckgo.com":
            return (
                200,
                '<a class="result__a" href="https://example.org/origin">Synthetic origin interview</a><a class="result__snippet">A possible interpolation of Original Light by Source Artist.</a>',
                url,
            )
        return (
            200,
            "<html><p>The musician described a possible interpolation of Original Light by Source Artist.</p></html>",
            url,
        )

    async def model(hass, data, **kwargs):
        calls.append(data["text"])
        value = {
            "found": True,
            "title": "Een bekende melodie",
            "summary": "Een mogelijke muzikale verbinding.",
            "text": "Misschien herken je de melodie uit Original Light van Source Artist. Volgens het interview is een interpolatie mogelijk, al is de exacte opname niet bevestigd. Dat geeft een interessant aanknopingspunt voor het luisteren.",
            "relation": {
                "kind": "interpolation",
                "direction": "current_to_related",
                "uncertainty": "possible",
                "target": {
                    "kind": "recording",
                    "title": "Original Light",
                    "artist": "Source Artist",
                },
            },
            "source_indices": [0],
        }
        return {"response": {"speech": {"plain": {"speech": json.dumps(value)}}}}

    with (
        patch.object(public_research.PublicFetch, "request", fetch),
        patch.object(pipeline, "_call_conversation_process_transport", model),
    ):
        inventory, code = await http(
            "/api/djconnect/v1/transport/read",
            {
                "contract_version": 1,
                "operation": "ask_dj/moments",
                "payload": {"contract_version": 1, "session_id": active.session_id},
            },
        )
        assert code == 200 and not calls and not urls
        item = next(x for x in inventory["types"] if x["type_id"] == "music_origin")
        assert item["available"]
        envelope = {
            "contract_version": 1,
            "operation_id": str(uuid.uuid7()),
            "operation_epoch": operations(hass).journal.epoch,
            "operation": "ask_dj/moments/request",
            "payload": {
                "contract_version": 1,
                "session_id": active.session_id,
                "type_id": "music_origin",
                "subject_ref": item["subject"]["subject_ref"],
            },
        }
        result, code = await http("/api/djconnect/v1/transport/operation", envelope)
        assert code == 200 and result["state"] == "accepted", result
        rich = result["result"]
        moment = rich["moment"]
        assert (
            moment["type"] == "music_origin"
            and moment["music_origin"]["relation"]["uncertainty"] == "possible"
        )
        assert rich["retention"] == "retained" and rich["presentation_admission"]["display_allowed"]
        rows = await manager._historical_projections.async_entry_records(
            "profile-a", active.session_id
        )
        assert len([r for r in rows if r["reference_id"] == moment["moment_id"]]) == 1
        duplicate, code = await http("/api/djconnect/v1/transport/operation", envelope)
        assert (
            code == 200
            and duplicate["operation_receipt"]["phase"] == "confirmed"
            and len(calls) == 1
        )
    with (
        patch.object(public_research.PublicFetch, "request", fetch),
        patch.object(pipeline, "_call_conversation_process_transport", model),
    ):
        freeform, code = await http(
            "/api/djconnect/v1/ask_dj/message",
            {
                "client_message_id": "origin-freeform-original-subject",
                "text": "Waar ken ik dit nummer van?",
                "language": "nl",
                "conversation_context": {
                    "session_id": active.session_id,
                    "selected_entry": {
                        "session_id": active.session_id,
                        "entry_id": rich["entry_id"],
                    },
                },
            },
        )
        assert code == 200 and "Original Light" in freeform.get("text", ""), freeform
        assert len(calls) == 2, calls
    baseline["music_origin"] = {
        "requests": requests,
        "model_fixture_calls": len(calls),
        "public_fixture_reads": len(urls),
        "native_type": "music_origin",
        "uncertainty": "possible",
        "direct_sqlite_commit": True,
        "duplicate_did_not_regenerate": True,
        "freeform_same_producer": True,
        "real_model_calls": 0,
        "real_provider_calls": 0,
        "native_installed_acceptance": "NOT_RUN",
    }
    return baseline


if __name__ == "__main__":
    owner.qualify = qualify
    asyncio.run(owner.run())
