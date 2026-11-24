"""Real isolated HA SDK/TLS Cast→ordinary owner→B chain; synthetic providers.

No host configuration, installed endpoint, public certificate, actual CAF/native
SDK or physical display is qualified. Run network-none from captured RO source.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import replace
from contextvars import ContextVar
from collections import Counter
import hashlib
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(os.environ.get("DJC_SOURCE_ROOT", "/candidate"))
sys.path[:0] = [str(ROOT), str(ROOT / "scripts/verification")]
import verify_display_admission_http as base  # noqa: E402
from custom_components.djconnect.cast_display import RECEIVER_ORIGIN  # noqa: E402


def source_pins():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "custom_components/djconnect").rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def public_fixture(examples):
    """Producer shapes/clocks with explicitly nonfunctional test credentials."""
    opaque = {
        "bootstrap_token",
        "grant_token",
        "claim_secret",
        "browser_nonce",
        "connection_nonce",
        "issuer_epoch",
        "claim_id",
        "browser_generation",
        "display_id",
        "share_id",
    }
    replacements = {}

    def clean(value, key=""):
        if isinstance(value, dict):
            return {name: clean(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [clean(item) for item in value]
        if key in opaque and isinstance(value, str):
            if value not in replacements:
                random = (
                    base64.urlsafe_b64encode(
                        hashlib.sha256(
                            ("NONFUNCTIONAL_CAST_FIXTURE_" + str(len(replacements))).encode()
                        ).digest()
                    )
                    .decode()
                    .rstrip("=")
                )
                prefix = (
                    "djccb_"
                    if value.startswith("djccb_")
                    else "djcd_"
                    if value.startswith("djcd_")
                    else ""
                )
                replacements[value] = prefix + random
            return replacements[value]
        if key == "code":
            return "999999" if value == "000000" else "000000"
        return value

    result = {
        "schema": "cast-b-producer-fixture.v1",
        "scope": "ACTUAL_ISOLATED_HA_HTTP_WS_PRODUCER",
        "credentials": "REPLACED_NONFUNCTIONAL_TEST_VALUES_CANNOT_AUTHENTICATE",
        "clock_policy": "Original request/response UTC+monotonic and producer expires_at/in retained; never renewed",
        "examples": clean(examples),
    }
    encoded = json.dumps(result, indent=2) + "\n"
    assert not any(original in encoded for original in replacements)
    return encoded


async def main():
    before = source_pins()
    lab = Path(os.environ.get("DJC_LAB_ROOT", "/lab"))
    directory = lab / "cast-ha-config"
    directory.mkdir(parents=True)
    hass = base.HomeAssistant(str(directory))
    hass.state = base.CoreState.running
    hass.config.language = "en"
    selected = "https://ha.cast-lab.djconnect.dev"
    hass.config.external_url = selected
    base.device_registry.async_setup(hass)
    await base.device_registry.async_load(hass, load_empty=True)
    hass.config_entries = base.ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    await base.entity_registry.async_load(hass, load_empty=True)
    await base.area_registry.async_load(hass, load_empty=True)
    hass.auth = await base.auth.auth_manager_from_config(hass, [{"type": "homeassistant"}], [])
    hass.http = base.HomeAssistantHTTP(hass, None, None, None, ["127.0.0.1"], 0, [], "modern")
    await hass.http.async_initialize(
        cors_origins=["https://receiver.djconnect.dev", "https://unrelated.example.test"],
        use_x_forwarded_for=False,
        login_threshold=-1,
        is_ban_enabled=False,
        use_x_frame_options=True,
    )
    first = {"device_id": "djconnect-ios-ABCDEF123456", "client_type": "ios"}
    second = {"device_id": "djconnect-ios-ABCDEF123457", "client_type": "ios"}
    one = base.entry(
        "cast-owner-one",
        {
            **first,
            "pair_code": "123456",
            "profile_id": "profile-a",
            "music_backend": "spotify_direct",
            "music_account_id": "fixture-account",
            "spotify_client_id": "fixture-client",
            "spotify_refresh_token": "fixture-never-sent",
        },
    )
    two = base.entry(
        "cast-owner-two",
        {
            **second,
            "pair_code": "654321",
            "profile_id": "profile-a",
            "music_backend": "spotify_direct",
            "music_account_id": "fixture-account",
            "profile_backend_entry_id": "cast-owner-one",
        },
    )
    await base.ConfigEntryStore(hass).async_save(
        {"entries": [one.as_storage_fragment, two.as_storage_fragment]}
    )
    hass.config_entries = base.ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    one = hass.config_entries.async_get_entry("cast-owner-one")
    two = hass.config_entries.async_get_entry("cast-owner-two")
    for item in (one, two):
        item._async_set_state(hass, base.ConfigEntryState.LOADED, None)
    runtime = base.DJConnectRuntime(one)
    hass.data["djconnect"] = {
        one.entry_id: runtime,
        two.entry_id: base.DJConnectRuntime(two),
        "runtime": runtime,
    }
    storage = base.ProfilePlatformStorage(hass)
    hass.data["djconnect"]["djconnect_profile_platform"] = storage
    await storage.async_upsert_music_backend(
        "spotify_direct",
        base.BackendProvider.SPOTIFY_DIRECT,
        display_name="Isolated synthetic provider",
    )
    await storage.async_create_profile(
        "Synthetic owner", profile_id="profile-a", default_backend_id="spotify_direct"
    )
    await storage.async_upsert_music_account(
        "fixture-account",
        "spotify_direct",
        kind=base.MusicAccountKind.PERSONAL,
        display_name="Synthetic account",
        linked_profile_ids=frozenset({"profile-a"}),
        provider_account_id="fixture-client",
    )
    profile = storage.household.profiles["profile-a"]
    await storage.async_update_profile(
        "profile-a",
        preferences=replace(profile.preferences, default_music_account_id="fixture-account"),
    )
    for identity in (first, second):
        await storage.async_upsert_device(
            identity["device_id"], "ios", linked_profile_id="profile-a"
        )
    persistence = await base.async_initialize_persistence(hass)
    manager = base.SessionRuntimeManager(
        base.PersistentSessionRepository(persistence),
        base.HistoricalProjectionRepository(persistence),
    )
    hass.data["djconnect"]["session_runtime_manager"] = manager
    calls = []
    request_path = ContextVar("cast_http_qualification_request", default="background")
    active_requests = {}

    def is_B_path(path):
        return path.startswith(("/api/djconnect/v1/cast/", "/api/djconnect/v1/display/"))

    def trace_call(path):
        origin = request_path.get()
        active_B = sorted(path for path in active_requests if is_B_path(path))
        calls.append(
            {
                "provider_path": path,
                "request_path": origin,
                "active_B_requests": active_B,
                "ambiguous_unattributed_B_window": origin == "background" and bool(active_B),
                "injected_control": path.startswith("/__CAST_TRACE_SENTINEL_"),
            }
        )

    @base.web.middleware
    async def trace_origin(request, handler):
        token = request_path.set(request.path)
        active_requests[request.path] = active_requests.get(request.path, 0) + 1
        try:
            return await handler(request)
        finally:
            request_path.reset(token)
            active_requests[request.path] -= 1
            if not active_requests[request.path]:
                del active_requests[request.path]

    hass.http.app.middlewares.append(trace_origin)

    async def provider(_self, method, path, **kwargs):
        assert method.upper() == "GET", "No provider mutation allowed"
        trace_call(path)
        if path == "/me/player":
            return {
                "is_playing": True,
                "progress_ms": 1000,
                "device": {"id": "fixture", "name": "Synthetic output"},
                "item": {
                    "id": "A" * 22,
                    "uri": "spotify:track:" + "A" * 22,
                    "type": "track",
                    "name": "Synthetic recording",
                    "artists": [{"id": "B" * 22, "name": "Synthetic performer"}],
                    "duration_ms": 300000,
                    "album": {"id": "C" * 22, "name": "Synthetic album", "images": []},
                },
            }
        if path == "/me/player/queue":
            return {"queue": []}
        if path.startswith("/me/tracks/contains"):
            return [False]
        return {}

    async def facts(_self, path, *_args, **_kwargs):
        trace_call("knowledge:" + str(path))
        return {}

    base.SpotifyBackend._request = provider
    base.SessionFactsResolver._get = facts
    provider_session = base.ClientSession()
    key = base.aiohttp_client._make_key(
        True, base.socket.AF_UNSPEC, base.aiohttp_client.ssl_util.SSLCipherList.PYTHON_DEFAULT
    )
    hass.data.setdefault(base.aiohttp_client.DATA_CLIENTSESSION, {})[key] = provider_session
    base.register_http_views(hass)
    server_ssl, client_ssl = base.local_tls(directory)
    server = base.TestServer(hass.http.app, scheme="https", host="127.0.0.1")
    await server.start_server(ssl=server_ssl)
    checks = []
    examples = []
    boundary_receipt = None
    try:
        async with base.TestClient(server, connector=base.TCPConnector(ssl=client_ssl)) as client:

            async def post(
                prefix, action, data, *, headers=None, origin=RECEIVER_ORIGIN, expected=200
            ):
                actual = dict(headers or {})
                if origin is not None:
                    actual["Origin"] = origin
                requested_at = base.datetime.now(base.timezone.utc).isoformat()
                requested_uptime = base.time.monotonic()
                response = await client.post(
                    "/api/djconnect/v1/" + prefix + "/" + action,
                    json={"contract_version": 1, **data},
                    headers=actual,
                )
                payload = await response.json()
                assert response.status == expected, (
                    prefix,
                    action,
                    response.status,
                    payload.get("error"),
                )
                if (
                    prefix == "cast"
                    and origin == RECEIVER_ORIGIN
                    and not action.startswith("owner/")
                ):
                    assert response.headers.get("Access-Control-Allow-Origin") == RECEIVER_ORIGIN
                    assert "Access-Control-Allow-Credentials" not in response.headers
                examples.append(
                    {
                        "transport": "HTTP",
                        "path": "/api/djconnect/v1/" + prefix + "/" + action,
                        "requested_at": requested_at,
                        "requested_uptime": requested_uptime,
                        "responded_at": base.datetime.now(base.timezone.utc).isoformat(),
                        "responded_uptime": base.time.monotonic(),
                        "request": {"contract_version": 1, **data},
                        "status": response.status,
                        "response": payload,
                    }
                )
                return payload

            owners = []
            for identity, code, selected_entry in (
                (first, "123456", one.entry_id),
                (second, "654321", two.entry_id),
            ):
                # Ordinary pairing follows the HA-selected setup slot, not a
                # caller device-id router. Select each actual fixture slot.
                hass.data["djconnect"]["runtime"] = hass.data["djconnect"][selected_entry]
                response = await client.post(
                    "/api/djconnect/v1/pair", json={**identity, "pair_code": code}
                )
                body = await response.json()
                assert response.status == 200 and body.get("device_token")
                owners.append({"Authorization": "Bearer " + body["device_token"]})
            hass.data["djconnect"]["runtime"] = runtime
            checks.append(
                "two_normal_HA_pairings_on_actual_selected_slots_persist_real_device_tokens"
            )
            response = await client.post(
                "/api/djconnect/v1/session/start",
                headers=owners[0],
                json={**first, "mood": "groove", "locale": "en"},
            )
            started = await response.json()
            assert response.status == 201, (response.status, started.get("error"))
            sid = started["session"]["session_id"]
            for identity, headers in zip((first, second), owners):
                context = await post(
                    "display", "owner/context", {"identity": identity}, headers=headers, origin=None
                )
                assert context["session_id"] == sid
            checks.append("both_owners_are_current_same_Profile_Session_shared_provider")
            native = {"identity": first, "session_id": sid}
            await post("cast", "owner/bootstrap", native, origin=None, expected=401)
            b = await post("cast", "owner/bootstrap", native, headers=owners[0], origin=None)
            assert b["ha_origin"] == selected and b["bootstrap_expires_in"] <= 30
            assert not manager._display_admission._claims and not manager._display_admission._shares
            checks.append("paired_one_use_claim_bootstrap_is_not_display_or_share")
            active = manager.current_active("profile-a")
            updated = manager._record_performance_memory("profile-a", active)
            assert updated is not active and updated.broadcast is active.broadcast
            nonce = secrets.token_urlsafe(32)
            bh = {"Authorization": "Bearer " + b["bootstrap_token"]}
            await post(
                "cast",
                "claim",
                {"browser_nonce": nonce},
                headers=bh,
                origin="https://foreign.example.net",
                expected=403,
            )
            preflight = await client.options(
                "/api/djconnect/v1/cast/claim",
                headers={
                    "Origin": RECEIVER_ORIGIN,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization,content-type",
                },
            )
            assert (
                preflight.status == 204
                and preflight.headers.get("Access-Control-Allow-Origin") == RECEIVER_ORIGIN
            )
            for origin, action in (
                ("https://unrelated.example.test", "claim"),
                (RECEIVER_ORIGIN, "owner/bootstrap"),
                ("https://unrelated.example.test", "owner/bootstrap"),
            ):
                denied = await client.options(
                    "/api/djconnect/v1/cast/" + action,
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "authorization,content-type",
                    },
                )
                assert denied.status == 403
                assert "Access-Control-Allow-Origin" not in denied.headers
            await post(
                "cast", "claim", {"browser_nonce": nonce}, headers=bh,
                origin="https://unrelated.example.test", expected=403,
            )
            checks.append("configured_HA_origins_never_expand_Cast_or_owner_preflight")
            # Positive instrumentation control: inject a provider call into
            # the real Cast HTTP actor, including child-task and HA executor.
            # It fails before claim creation, then the actual method is restored.
            from custom_components.djconnect.cast_display import CastDisplayService
            from custom_components.djconnect.display_admission import DisplayAdmissionError

            original_post = CastDisplayService.post
            backend = base.SpotifyBackend(hass, runtime)

            async def injected_post(service, action, *args, **kwargs):
                if action == "claim":
                    await backend._request("GET", "/__CAST_TRACE_SENTINEL_DIRECT")
                    await asyncio.create_task(
                        backend._request("GET", "/__CAST_TRACE_SENTINEL_CHILD")
                    )

                    def executor_call():
                        asyncio.run(backend._request("GET", "/__CAST_TRACE_SENTINEL_EXECUTOR"))

                    await hass.async_add_executor_job(executor_call)
                    raise DisplayAdmissionError("cast_trace_sentinel", 409)
                return await original_post(service, action, *args, **kwargs)

            CastDisplayService.post = injected_post
            try:
                await post("cast", "claim", {"browser_nonce": nonce}, headers=bh, expected=409)
            finally:
                CastDisplayService.post = original_post
            sentinel_calls = [row for row in calls if row["injected_control"]]
            assert len(sentinel_calls) == 3
            assert {row["provider_path"] for row in sentinel_calls} == {
                "/__CAST_TRACE_SENTINEL_DIRECT",
                "/__CAST_TRACE_SENTINEL_CHILD",
                "/__CAST_TRACE_SENTINEL_EXECUTOR",
            }
            assert all(
                is_B_path(row["request_path"]) or row["ambiguous_unattributed_B_window"]
                for row in sentinel_calls
            )
            assert all(
                row["request_path"] == "/api/djconnect/v1/cast/claim" for row in sentinel_calls[:2]
            )
            tracer_control = {
                "calls": sentinel_calls,
                "would_fail_zero_B_IO_assertion": True,
                "executor_inherits_context": sentinel_calls[2]["request_path"]
                == "/api/djconnect/v1/cast/claim",
                "unattributed_executor_activity_is_fail_closed_not_counted_as_safe_background": True,
            }
            checks.append("positive_Cast_actor_child_executor_provider_trace_mutant_is_detected")
            c = await post("cast", "claim", {"browser_nonce": nonce}, headers=bh)
            await post("cast", "claim", {"browser_nonce": nonce}, headers=bh, expected=404)
            await post(
                "display", "claim", {"browser_nonce": nonce}, origin=RECEIVER_ORIGIN, expected=403
            )
            checks.append("Cast_origin_real_claim_one_use_and_unchanged_B_origin_policy")
            await post(
                "display",
                "owner/resolve",
                {"identity": second, "code": c["code"]},
                headers=owners[1],
                origin=None,
                expected=404,
            )
            fields = {
                name: c[name] for name in ("issuer_epoch", "claim_id", "browser_generation", "code")
            }
            consent = {
                **fields,
                "session_id": sid,
                "share": {
                    "mode": "create",
                    "consent": True,
                    "lifetime_seconds": 14400,
                    "live": True,
                    "language": "en",
                },
            }
            await post(
                "display",
                "owner/approve",
                {**consent, "identity": second},
                headers=owners[1],
                origin=None,
                expected=404,
            )
            resolved = await post(
                "display",
                "owner/resolve",
                {"identity": first, "code": c["code"]},
                headers=owners[0],
                origin=None,
            )
            assert resolved["claim_id"] == c["claim_id"] and "claim_secret" not in resolved
            approved = await post(
                "display",
                "owner/approve",
                {**consent, "identity": first},
                headers=owners[0],
                origin=None,
            )
            checks.append("ordinary_B_resolve_and_approve_enforce_original_actual_Cast_owner")
            claim_body = {
                key: c[key]
                for key in ("issuer_epoch", "claim_id", "claim_secret", "browser_generation")
            }
            admitted = await post("cast", "collect", {**claim_body, "browser_nonce": nonce})
            assert (
                admitted["display_id"] == approved["display_id"]
                and admitted["capabilities"]["owner_controls"] is False
            )
            grant = {key: admitted[key] for key in ("issuer_epoch", "display_id")}
            gh = {"Authorization": "Bearer " + admitted["grant_token"]}
            provider_count = len(calls)
            async with client.ws_connect(
                "/api/djconnect/v1/cast/live", headers={"Origin": RECEIVER_ORIGIN}
            ) as ws:
                await ws.send_json(
                    {
                        "type": "authenticate",
                        "contract_version": 1,
                        **grant,
                        "grant_token": admitted["grant_token"],
                        "connection_nonce": secrets.token_urlsafe(32),
                    }
                )
                frame = await ws.receive_json(timeout=5)
                assert (
                    frame["type"] == "snapshot"
                    and frame["snapshot"]["display_id"] == grant["display_id"]
                )
                assert frame["connection_generation"] >= 1
                connection = base.display_live_hub(manager).connections[grant["display_id"]]
                from custom_components.djconnect.display_live import _Connection

                assert type(connection) is _Connection and connection.origin == selected
                examples.append(
                    {
                        "transport": "WebSocket",
                        "path": "/api/djconnect/v1/cast/live",
                        "response": frame,
                    }
                )

                def frame_metadata(value):
                    snapshot = value["snapshot"]
                    watermark = snapshot["broadcast"]["snapshot_watermark"]
                    assert type(watermark) is int and watermark >= 0
                    return {
                        "snapshot_watermark": watermark,
                        "projection_revision": snapshot["projection_revision"],
                        "frame_sha256": hashlib.sha256(
                            json.dumps(value, sort_keys=True).encode()
                        ).hexdigest(),
                    }

                received_frames = [frame_metadata(frame)]
                sent_frames = []
                boundary_crossed = False
                original_send = connection.ws.send_str

                async def observe_send(data, *args, **kwargs):
                    value = json.loads(data)
                    sent_frames.append(
                        {
                            **frame_metadata(value),
                            "after_unload_boundary": boundary_crossed,
                            "current_at_send": connection.current(),
                        }
                    )
                    return await original_send(data, *args, **kwargs)

                connection.ws.send_str = observe_send
                original_deadline = connection.display.lease_deadline
                await asyncio.sleep(0.02)
                await post("cast", "renew", {**grant, "renew_sequence": 1}, headers=gh)
                assert connection.display.lease_deadline > original_deadline
                checks.append("same_real_B_Connection_and_current_writer_lease_renewal")
                invitation = await post(
                    "cast", "participation/display/invitation", grant, headers=gh
                )
                assert invitation["qr_data_uri"].startswith("data:image/svg+xml;base64,")
                focus = await post("cast", "participation/display/focus", grant, headers=gh)
                assert focus["live_enabled"] is True
                await post("cast", "participation/display/return", grant, headers=gh)
                await post(
                    "cast",
                    "participation/display/focus-photo",
                    {**grant, "focus_revision": "f" * 64},
                    headers=gh,
                    expected=404,
                )
                checks.append("genuine_Live_policy_QR_invitation_focus_and_photo_scope_denial")
                absent = await client.post(
                    "/api/djconnect/v1/cast/participation/ask",
                    json={"contract_version": 1, **grant},
                    headers={**gh, "Origin": RECEIVER_ORIGIN},
                )
                await absent.read()
                assert absent.status == 404
                denied = await client.post(
                    "/api/djconnect/v1/session/end", json={**first, "session_id": sid}, headers=gh
                )
                await denied.read()
                assert denied.status in {401, 403}
                assert manager.current_active("profile-a").session_id == sid
                checks.append("no_Cast_guest_Ask_or_owner_effect_route")
                # Drain bytes actually delivered before withdrawal. Those
                # cannot be recalled and are not post-boundary publications.
                while True:
                    try:
                        pending = await ws.receive(timeout=0.1)
                    except TimeoutError:
                        break
                    assert pending.type == base.WSMsgType.TEXT
                    value = json.loads(pending.data)
                    assert (
                        value["type"] == "snapshot"
                        and value["snapshot"]["display_id"] == grant["display_id"]
                    )
                    received_frames.append(frame_metadata(value))
                pre_sent = len(sent_frames)
                boundary_crossed = True
                boundary_at = base.time.monotonic()
                one._async_set_state(hass, base.ConfigEntryState.UNLOAD_IN_PROGRESS, None)
                assert not connection.current()
                closed = await ws.receive(timeout=3)
                assert closed.type in {
                    base.WSMsgType.CLOSE,
                    base.WSMsgType.CLOSED,
                    base.WSMsgType.ERROR,
                }
                assert not connection.current()
                assert len(sent_frames) == pre_sent and not any(
                    row["after_unload_boundary"] for row in sent_frames
                )
                boundary_receipt = {
                    "boundary_uptime": boundary_at,
                    "pre_boundary_received": received_frames,
                    "pre_boundary_highest_received_watermark": max(
                        row["snapshot_watermark"] for row in received_frames
                    ),
                    "observed_server_send_frames": sent_frames,
                    "initial_frame_was_received_before_instrumentation": True,
                    "server_send_count_at_boundary": pre_sent,
                    "post_boundary_server_sends": len(sent_frames) - pre_sent,
                    "current_immediately_after_unload": False,
                    "terminal_WS_type": closed.type.name,
                }
                checks.append(
                    "actual_entry_unload_withdraws_real_B_writer_no_post_boundary_publication"
                )
            b_calls = [
                call
                for call in calls
                if not call["injected_control"]
                and (is_B_path(call["request_path"]) or call["ambiguous_unattributed_B_window"])
            ]
            assert not b_calls, ("B actor invoked provider", b_calls)
            checks.append("actor_scoped_provider_trace_zero_all_Cast_and_B_requests")
            assert before == source_pins(), "Source changed during qualification"
            (lab / "cast-producer-fixture.json").write_text(public_fixture(examples))
            receipt = {
                "qualification": "ACTUAL_ISOLATED_HA_TLS_CAST_B_FACTORIES_AND_REAL_B_CONNECTION",
                "candidate": os.environ.get("DJC_CANDIDATE_SHA"),
                "ha_version": version("homeassistant"),
                "aiohttp_version": version("aiohttp"),
                "checks": checks,
                "source_before_after_equal": True,
                "source_files": len(before),
                "source_pins": before,
                "provider_calls_during_B": len(b_calls),
                "total_provider_calls_including_negative_controls": len(calls),
                "provider_calls_by_request_origin": dict(
                    Counter(row["request_path"] for row in calls)
                ),
                "all_provider_call_records": calls,
                "tracer_positive_control": tracer_control,
                "traced_interfaces": ["SpotifyBackend._request", "SessionFactsResolver._get"],
                "background_provider_activity_during_B_window": calls[provider_count:],
                "unload_boundary": boundary_receipt,
                "producer_fixture_sha256": hashlib.sha256(
                    (lab / "cast-producer-fixture.json").read_bytes()
                ).hexdigest(),
                "scope_limits": "Synthetic provider inputs; no real Google CAF/native SDK, public certificate, installed HA or physical TV acceptance",
            }
            (lab / "cast-http-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
            print(json.dumps({k: v for k, v in receipt.items() if k != "source_pins"}), flush=True)
    finally:
        await server.close()
        await provider_session.close()
        await base.async_shutdown_persistence(hass)
        await hass.async_stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
