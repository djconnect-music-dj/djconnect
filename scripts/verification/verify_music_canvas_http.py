"""Real HA2026.11 TLS/pairing/SQLite Canvas proof; no provider or hardware calls."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch
import uuid

import verify_requested_moments_http as harness


async def qualify(hass, manager, history, request, client):
    from custom_components.djconnect.music_canvas_runtime import setup
    from custom_components.djconnect.music_canvas import CanvasError
    runtime = await setup(hass)
    # No independent discovery/hardware worker is needed in this controlled lab.
    runtime.unsubscribe()
    base = "/api/djconnect/v1/music_canvas/"
    calls = []
    async def call(kind, payload=None, authorized=True):
        body, code = await request("POST", base+kind,
            {"contract_version": 1, **(payload or {})}, authorized=authorized)
        calls.append({"route": kind, "status": code, "success": body.get("success")})
        return body, code
    import sys
    trace_rows = []
    def trace(frame, event, arg):
        if event == "exception" and "music_canvas" in frame.f_code.co_filename:
            trace_rows.append({"function": frame.f_code.co_name, "line": frame.f_lineno,
                               "type": arg[0].__name__})
        return trace
    sys.settrace(trace)
    try:
        first, code = await call("read")
    finally:
        sys.settrace(None)
    if code != 200:
        print(json.dumps({"canvas_exception_frames": trace_rows}))
    assert code == 200, first
    assert first["preferences"]["enabled"] is False and first["revision"] == 0
    assert first["can_manage_devices"] is False
    denied, code = await call("read", authorized=False)
    assert code == 401, denied
    binding = first["binding"]
    update = dict(binding=binding, operation_id=str(uuid.uuid4()),
                  expected_revision=0, patch={"enabled": True})
    accepted, code = await call("update", update)
    assert code == 200 and accepted["revision"] == 1, accepted
    replayed, code = await call("update", update)
    assert code == 200 and replayed["revision"] == 1, replayed
    altered, code = await call("update", {**update, "patch": {"enabled": False}})
    assert code == 409, altered
    stale, code = await call("update", {**update, "operation_id": str(uuid.uuid4())})
    assert code == 409, stale
    operation, code = await call("operation", {k: update[k] for k in ("binding", "operation_id")})
    assert code == 200 and operation["revision"] == 1, operation
    foreign, code = await call("update", {**update, "profile_id": "profile-other"})
    assert code == 400, foreign
    management, code = await call("forget", dict(binding=binding, operation_id=str(uuid.uuid4()),
        target_id="switchbot:fixture", cleanup_remote=False, allow_remaining_art=False))
    assert code == 403, management
    state = await runtime.repository.read()
    assert state["profiles"]["profile-a"]["preferences"]["enabled"] is True
    assert "profile-other" not in state["profiles"]

    # A real SQLite round trip with two simultaneous clients on the same revision.
    outcomes = await asyncio.gather(*(call("update", dict(binding=binding,
        operation_id=str(uuid.uuid4()), expected_revision=1, patch={"cadence": value}))
        for value in ("900", "3600")))
    assert sorted(x[1] for x in outcomes) == [200, 409], outcomes
    before = await runtime.repository.read()
    try:
        await runtime.repository.mutate(lambda s: s["profiles"].clear(), lambda: False)
        raise AssertionError("withdrawn authority accepted")
    except PermissionError:
        pass
    assert await runtime.repository.read() == before
    readback, code = await call("read")
    assert code == 200 and readback["revision"] == 2
    assert readback["preferences"]["cadence"] in ("900", "3600")

    # Real protocol adapter and native service schema, simulated physical boundary.
    from custom_components.djconnect import music_canvas_adapters as adapters
    from homeassistant.components.switchbot_cloud.services import UPLOAD_IMAGE_SCHEMA
    schema = UPLOAD_IMAGE_SCHEMA({"device_id": ["fixture-ha-registry-id"], "image_url": "https://fixture.invalid/one"})
    assert schema["device_id"] == ["fixture-ha-registry-id"]
    try:
        UPLOAD_IMAGE_SCHEMA({"device_id": [], "image_url": "https://fixture.invalid/one"})
        raise AssertionError("empty target list accepted")
    except Exception as exc:
        assert not isinstance(exc, AssertionError)
    events = []
    class Art:
        token = "synthetic-tv-token"
        mode = "off"
        def get_artmode(self):
            events.append("mode")
            return self.mode
        def upload(self, *args, **kwargs):
            events.append("upload")
            return "owned-art"
        def get_current(self):
            events.append("readback")
            return {"content_id": "owned-art"}
        def select_image(self, content_id, show): events.append("select")
        def close(self): events.append("close")
    art = Art()
    class Remote:
        def __init__(self, *args, **kwargs): pass
        def art(self): return art
    device = dict(host="fixture.invalid", token="synthetic-tv-token", owned_content=[])
    with patch("samsungtvws.SamsungTVWS", Remote):
        try:
            adapters.samsung_action(device, "upload", content=b"synthetic")
            raise AssertionError("off television received an upload")
        except CanvasError as exc:
            assert exc.code == "canvas_manual_takeover"
        assert "upload" not in events and events[-1] == "close"
        art.mode = "on"
        uploaded = adapters.samsung_action(device, "upload", content=b"synthetic")
        assert uploaded["content_id"] == "owned-art" and "select" not in events
        result = adapters.samsung_action(device, "select", content_id="owned-art")
        assert result["displayed"] and events.index("select") < events.index("readback")

    # Actual Session owner + lifecycle scheduler, with declared image/hardware seams.
    import io
    from PIL import Image
    from custom_components.djconnect import music_canvas_render as render
    fixture_image = io.BytesIO()
    Image.new("RGB", (640, 640), (150, 90, 35)).save(fixture_image, "PNG")
    targets = {
        "samsung:fixture-a": ("samsung", 640, 360),
        "samsung:fixture-b": ("samsung", 640, 360),
        "switchbot:fixture-p": ("switchbot", 320, 480),
    }
    def seed(state):
        for key, (adapter, width, height) in targets.items():
            state["devices"][key] = dict(id=key, name=key, adapter=adapter, state="ready", epoch=0,
                screen=dict(width=width, height=height, orientation="portrait" if height > width else "landscape"),
                owned_content=[], token="synthetic", host="fixture.invalid", ha_device_id="fixture-ha-device")
    await runtime.repository.mutate(seed, lambda: True)
    latest, code = await call("read")
    selected, code = await call("update", dict(binding=binding, operation_id=str(uuid.uuid4()),
        expected_revision=latest["revision"], patch={"selected_targets": list(targets), "cadence": "1800"}))
    assert code == 200, selected
    session = await manager.async_start(owner_profile_id="profile-a", selected_mood="chill", locale="nl")
    await manager.async_update_playback_projection(owner_profile_id="profile-a", session_id=session.session_id,
        state="playing", media_identity="fixture-recording", title="Synthetic liquid shapes", artist="Fixture",
        duration_ms=240000, position_ms=1000)
    generations, deliveries = [], []
    failing = set()
    async def generate(_hass, prompt):
        generations.append(prompt)
        return fixture_image.getvalue()
    def hardware(device, action, **kwargs):
        deliveries.append((device["id"], action))
        if device["id"] in failing:
            raise CanvasError("canvas_device_offline", 503)
        return {"content_id": "owned-"+device["id"], "displayed": True, "deleted": True}
    async def cloud(_hass, device, image_url, authorize):
        assert authorize() and image_url.startswith("https://canvas.fixture.invalid/")
        deliveries.append((device["id"], "cloud_upload"))
        return {"state": "delivered_unknown", "displayed": False}
    hass.data["djconnect"]["music_canvas_asset_origin"] = "https://canvas.fixture.invalid"
    # Native action registration is an explicit fixture; its actual SDK schema
    # was exercised above, and physical cloud execution remains substituted.
    hass.services.async_register("switchbot_cloud", "upload_art_frame_image", lambda call: None)
    with patch.object(render, "generation_available", lambda _hass: True), \
         patch.object(render, "generate", generate), patch.object(adapters, "samsung_action", hardware), \
         patch.object(adapters, "deliver_switchbot", cloud):
        await runtime.tick()
        await runtime.jobs["profile-a"]
        assert not generations, "debounce skipped"
        await asyncio.sleep(5.1)
        await runtime.tick()
        await runtime.jobs["profile-a"]
        assert len(generations) == 2, "identical Samsung targets must share one generation"
        assert runtime.states["samsung:fixture-a"] == "displayed"
        assert runtime.states["switchbot:fixture-p"] == "delivered_unknown"
        rendered = await runtime.repository.read()
        assert rendered["devices"]["samsung:fixture-a"]["preview"] == rendered["devices"]["samsung:fixture-b"]["preview"]
        await runtime.tick()
        await runtime.jobs["profile-a"]
        assert len(generations) == 2, "interval generated on an ordinary tick"
        # Selecting a shared physical screen is not a grant to another Profile's preview.
        def select_other(state):
            state["profiles"]["profile-other"] = {"revision": 1, "preferences": {
                **state["profiles"]["profile-a"]["preferences"], "selected_targets": ["samsung:fixture-a"]}}
        await runtime.repository.mutate(select_other, lambda: True)
        try:
            await runtime.preview("profile-other", "samsung:fixture-a", lambda: True)
            raise AssertionError("cross-Profile preview exposed")
        except CanvasError as exc:
            assert exc.status == 404
        # A presentation change deterministically reuses current source bytes.
        failing.add("samsung:fixture-a")
        latest, code = await call("read")
        changed, code = await call("update", dict(binding=binding, operation_id=str(uuid.uuid4()),
            expected_revision=latest["revision"], patch={"matte": "contrast"}))
        assert code == 200
        await runtime.tick()
        await runtime.jobs["profile-a"]
        assert len(generations) == 2, "matte change regenerated instead of composing"
        assert runtime.states["samsung:fixture-a"] == "canvas_device_offline"
        assert runtime.states["samsung:fixture-b"] == "displayed", "one offline screen blocked another"
        failing.clear()
        # Genuine Session end fences an already pending model completion.
        begun, release = asyncio.Event(), asyncio.Event()
        async def delayed(_hass, prompt):
            begun.set()
            await release.wait()
            return fixture_image.getvalue()
        runtime.cadence.completed = {k: (v[0], 0) for k, v in runtime.cadence.completed.items()}
        with patch.object(render, "generate", delayed):
            await runtime.tick()
            await asyncio.wait_for(begun.wait(), timeout=5)
            before_end = len(deliveries)
            await manager.async_end(owner_profile_id="profile-a", session_id=session.session_id)
            release.set()
            await runtime.jobs["profile-a"]
            assert len(deliveries) == before_end, "late model completion delivered after Session end"
        before_end = len(deliveries)
        await runtime.tick()
        assert len(deliveries) == before_end
        ended, code = await call("read")
        assert code == 200 and ended["preferences"]["enabled"] is True
        assert ended["preferences"]["selected_targets"] == list(targets)
        # Actual HA admin account + actual existing shared Profile association.
        from homeassistant.auth.const import GROUP_ID_ADMIN
        from custom_components.djconnect.profile_context import profile_storage
        storage = profile_storage(hass)
        await hass.auth.async_create_user("Synthetic lab owner", group_ids=[GROUP_ID_ADMIN])
        admin = await hass.auth.async_create_user("Synthetic Canvas admin", group_ids=[GROUP_ID_ADMIN])
        await storage.async_set_profile_mapping("ha_user", admin.id, "profile-a")
        privileged, code = await call("read")
        assert code == 200 and privileged["can_manage_devices"]
        # Explicit simulated hardware capability for the cleanup-failure cases;
        # this is not a qualification of any installed Samsung model.
        await runtime.repository.mutate(
            lambda state: state["devices"]["samsung:fixture-a"].update(cleanup_supported=True),
            lambda: True)
        cleanup_attempts = []
        def cleanup_failure(device, action, **kwargs):
            cleanup_attempts.append(action)
            return {"deleted": False}
        forget = dict(binding=binding, operation_id=str(uuid.uuid4()), target_id="samsung:fixture-a",
                      cleanup_remote=True, allow_remaining_art=False)
        with patch.object(adapters, "samsung_action", cleanup_failure):
            failed, code = await call("forget", forget)
            assert code == 200 and failed["state"] == "cleanup_failed", failed
            replay, code = await call("forget", forget)
            assert code == 200 and len(cleanup_attempts) == 1
            remaining, code = await call("forget", {**forget, "operation_id": str(uuid.uuid4()),
                                                   "allow_remaining_art": True})
            assert code == 200 and remaining["state"] == "confirmed" and remaining["remaining_art"]
        state = await runtime.repository.read()
        assert "samsung:fixture-a" not in state["devices"]
        assert state["profiles"]["profile-a"]["preferences"]["enabled"]
        assert state["profiles"]["profile-a"]["preferences"]["selected_targets"] == list(targets)[1:]
        assert state["devices"]["samsung:fixture-b"]["token"] == "synthetic"
        # Interrupted hardware outcome: reserve/fence durably, cancel the work,
        # then close the actual SQLite provider and construct a new Canvas runtime.
        begun_unknown = asyncio.Event()
        async def interrupted_protocol(action):
            begun_unknown.set()
            await asyncio.Future()
        unknown = dict(binding=binding, operation_id=str(uuid.uuid4()), target_id="samsung:fixture-b",
                       cleanup_remote=False, allow_remaining_art=False)
        # Force an await inside the deliberate cleanup branch without claiming
        # any real device request was made by this simulated hardware seam.
        await runtime.repository.mutate(
            lambda state: state["devices"]["samsung:fixture-b"].update(cleanup_supported=True),
            lambda: True)
        unknown["cleanup_remote"] = True
        from custom_components.djconnect.music_canvas_http import current_admin
        with patch.object(runtime, "protocol", interrupted_protocol):
            pending = asyncio.create_task(runtime.manage("forget", "profile-a", binding, unknown,
                lambda: current_admin(hass, admin)))
            await asyncio.wait_for(begun_unknown.wait(), timeout=5)
            pending.cancel()
            try:
                await pending
                raise AssertionError("interrupted management did not cancel")
            except asyncio.CancelledError:
                pass
        orphaned, code = await call("operation", {k: unknown[k] for k in ("binding", "operation_id")})
        assert code == 200 and orphaned["state"] == "unknown"
        runtime.stop()
        from custom_components.djconnect.persistence import async_shutdown_persistence, async_initialize_persistence
        await async_shutdown_persistence(hass)
        hass.data["djconnect"].pop("music_canvas")
        await async_initialize_persistence(hass)
        runtime = await setup(hass)
        runtime.unsubscribe()
        restarted, code = await call("read")
        assert code == 200 and restarted["preferences"]["enabled"]
        assert next(t for t in restarted["targets"] if t["id"] == unknown["target_id"])["forgetting"]
        orphaned, code = await call("operation", {k: unknown[k] for k in ("binding", "operation_id")})
        assert code == 200 and orphaned["state"] == "unknown", orphaned
        resolved, code = await call("forget", {**unknown, "operation_id": str(uuid.uuid4()),
            "cleanup_remote": False, "allow_remaining_art": True})
        assert code == 200 and resolved["state"] == "confirmed" and resolved["remaining_art"], resolved
        state = await runtime.repository.read()
        assert unknown["target_id"] not in state["devices"]
        assert state["profiles"]["profile-a"]["preferences"]["enabled"]
        await hass.auth.async_remove_user(admin)
        unprivileged, code = await call("read")
        assert code == 200 and not unprivileged["can_manage_devices"]
    runtime.stop()
    return {"requests": calls, "actual_sqlite": True, "paired_tls": True,
            "native_switchbot_schema": True, "samsung_upload_select_separate": True,
            "samsung_off_no_upload": True, "synthetic_image_generations": len(generations),
            "shared_samsung_generation": True, "matte_reuses_source": True,
            "cross_profile_preview_denied": True, "offline_target_isolated": True,
            "late_model_after_session_end_denied": True, "admin_deletion_withdraws_management": True,
            "failed_cleanup_and_explicit_forget_anyway": True,
            "unknown_forget_survives_actual_sqlite_and_runtime_restart": True,
            "unknown_forget_requires_new_explicit_admin_decision": True,
            "session_end_preserves_enabled_and_targets": True,
            "real_model_calls": 0, "physical_hardware": "NOT_RUN"}


async def main():
    harness.qualify = qualify
    await harness.run()
    path = Path(os.environ["DJC_LAB_ROOT"])/"http-requested-moments-receipt.json"
    receipt = json.loads(path.read_text())
    receipt["qualification"] = "Music Canvas actual HA/TLS/pairing/SQLite; simulated model/hardware boundaries"
    target = path.with_name("music-canvas-actual-ha.json")
    target.write_text(json.dumps(receipt, indent=2)+"\n")
    print(json.dumps({"result": "PASS", "canvas_receipt": str(target)}))


if __name__ == "__main__":
    asyncio.run(main())
