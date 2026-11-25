"""Real HA2026.11 TLS/pairing/SQLite Canvas proof; no provider or hardware calls."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
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
    assert first["preferences"]["show_track_title"] is False
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
    observed_content = {}
    upload_serial = [0]
    failing = set()
    async def generate(_hass, prompt):
        generations.append(prompt)
        return fixture_image.getvalue()
    def hardware(device, action, **kwargs):
        deliveries.append((device["id"], action))
        if device["id"] in failing:
            raise CanvasError("canvas_device_offline", 503)
        if action == "observe":
            return {"current": {"content_id": observed_content.get(device["id"])}}
        if action == "upload":
            upload_serial[0] += 1
            return {"content_id": "owned-" + str(upload_serial[0])}
        if action == "select":
            observed_content[device["id"]] = kwargs["content_id"]
        return {"displayed": True, "deleted": True}
    async def cloud(_hass, device, image_url, authorize):
        assert authorize() and image_url.startswith("https://canvas.fixture.invalid/")
        deliveries.append((device["id"], "cloud_upload"))
        return {"state": "delivered_unknown", "displayed": False}
    hass.data["djconnect"]["music_canvas_asset_origin"] = "https://canvas.fixture.invalid"
    # Native action registration is an explicit fixture; its actual SDK schema
    # was exercised above, and physical cloud execution remains substituted.
    hass.services.async_register("switchbot_cloud", "upload_art_frame_image", lambda call: None)
    real_samsung_action = adapters.samsung_action
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
            expected_revision=latest["revision"], patch={"matte": "contrast", "show_track_title": True}))
        assert code == 200 and changed["preferences"]["show_track_title"] is True
        await runtime.tick()
        await runtime.jobs["profile-a"]
        assert len(generations) == 2, "matte change regenerated instead of composing"
        assert runtime.states["samsung:fixture-a"] == "canvas_device_offline"
        assert runtime.states["samsung:fixture-b"] == "displayed", "one offline screen blocked another"
        titled = (await runtime.repository.read())["devices"]["samsung:fixture-b"]
        untitled = rendered["devices"]["samsung:fixture-b"]
        assert titled["presentation"] == ["central", "contrast", True]
        assert titled["preview"] != untitled["preview"] and titled["source_image"] == untitled["source_image"]
        failing.clear()
        runtime.next_probe.clear()  # Isolate later cases from the deliberate offline backoff.
        # A physically running executor retains its effect slot through repeated cancellation.
        import threading
        from copy import deepcopy
        started_thread, finish_thread = threading.Event(), threading.Event()
        def blocking_hardware():
            started_thread.set()
            assert finish_thread.wait(5)
        async def effect():
            async with runtime.effect_lock:
                await runtime.protocol(blocking_hardware)
        job = asyncio.create_task(effect())
        while not started_thread.is_set():
            await asyncio.sleep(0.001)
        try:
            for _ in range(3):
                job.cancel()
                await asyncio.sleep(0.01)
                assert runtime.effect_lock.locked() and not job.done()
        finally:
            finish_thread.set()
        try:
            await job
        except asyncio.CancelledError:
            pass
        assert not runtime.effect_lock.locked()
        # A manual art selection suspends Canvas durably, without paid generation.
        current = await runtime.repository.read()
        device = current["devices"]["samsung:fixture-a"]
        observed_content[device["id"]] = "manually-selected-art"
        try:
            async with runtime.effect_lock:
                await runtime.observe_samsung(device, lambda: True)
            raise AssertionError("manual takeover ignored")
        except CanvasError as exc:
            assert exc.code == "canvas_manual_takeover"
        before_manual = len(generations)
        await runtime.tick()
        await runtime.jobs["profile-a"]
        assert runtime.states[device["id"]] == "canvas_manual_takeover"
        assert len(generations) == before_manual
        # Explicit lab reset, not a claim that user art is automatically overridden.
        await runtime.repository.mutate(lambda state: state["devices"][device["id"]].update(manual_takeover=False), lambda: True)
        observed_content[device["id"]] = device["last_selected_content"]
        # A settings-independent track change can complete an interval render;
        # the same late track is rejected in per-track mode. Force only due-time.
        for mode in ("1800", "track"):
            state = await runtime.repository.read()
            config = deepcopy(state["profiles"]["profile-a"])
            config["preferences"].update(selected_targets=["samsung:fixture-a"], cadence=mode, cadence_overrides={})
            before_select = sum(action == "select" for _, action in deliveries)
            async def transition(_hass, prompt, mode=mode):
                await manager.async_update_playback_projection(owner_profile_id="profile-a", session_id=session.session_id,
                    state="playing", media_identity="transition-"+mode, title="Next track "+mode,
                    artist="Fixture", duration_ms=240000, position_ms=1000)
                return await generate(_hass, prompt)
            with patch.object(render, "generate", transition), patch.object(runtime.cadence, "due", lambda *args: True):
                await runtime.run("profile-a", manager.current_active("profile-a"), config, state)
            after_select = sum(action == "select" for _, action in deliveries)
            assert after_select-before_select == (1 if mode == "1800" else 0), (mode, runtime.states)
        # Withdrawal during select cannot start a subsequent cleanup effect.
        state = await runtime.repository.read()
        device = deepcopy(state["devices"]["samsung:fixture-a"])
        config = state["profiles"]["profile-a"]
        allowed = [True]

        def withdraw_during_upload(device, action, **kwargs):
            result = hardware(device, action, **kwargs)
            if action == "upload":
                allowed[0] = False
            return result

        before_select = sum(action == "select" for _, action in deliveries)
        with patch.object(adapters, "samsung_action", withdraw_during_upload):
            try:
                await runtime.deliver("profile-a", config, manager.current_active("profile-a"), device["id"],
                    device, device["preview"], fixture_image.getvalue(), lambda: allowed[0], device["source_image"])
                raise AssertionError("withdrawn upload selected")
            except CanvasError as exc:
                assert exc.code == "canvas_context_changed"
        acknowledged = (await runtime.repository.read())["devices"][device["id"]]
        assert not acknowledged["upload_pending"]
        assert len(acknowledged["owned_content"]) == len(device["owned_content"]) + 1
        assert sum(action == "select" for _, action in deliveries) == before_select
        # Retain the original fixture for the independent withdrawal during select.
        await runtime.repository.mutate(lambda current: current["devices"].update({device["id"]: device}), lambda: True)
        allowed[0] = True

        def withdraw_during_select(device, action, **kwargs):
            result = hardware(device, action, **kwargs)
            if action == "select":
                allowed[0] = False
            return result
        before_cleanup = sum(action == "cleanup" for _, action in deliveries)
        with patch.object(adapters, "samsung_action", withdraw_during_select):
            try:
                await runtime.deliver("profile-a", config, manager.current_active("profile-a"), device["id"],
                    device, device["preview"], fixture_image.getvalue(), lambda: allowed[0], device["source_image"])
                raise AssertionError("withdrawn select committed")
            except CanvasError as exc:
                assert exc.code == "canvas_context_changed"
        assert sum(action == "cleanup" for _, action in deliveries) == before_cleanup
        # Restore this declared synthetic hardware scenario for unrelated end tests.
        await runtime.repository.mutate(lambda current: current["devices"].update({device["id"]: device}), lambda: True)
        observed_content[device["id"]] = device["last_selected_content"]
        # Cancellation during an actual private file save cannot strand references.
        await runtime.cleanup_assets()
        files_before_cancel = set(runtime.asset_root.glob("*.jpg"))
        save_started, save_release = threading.Event(), threading.Event()
        original_protocol = runtime.protocol
        async def stalled_save_protocol(action):
            if getattr(action, "__name__", None) == "save":
                def save_after_release():
                    save_started.set()
                    assert save_release.wait(5)
                    action()
                return await original_protocol(save_after_release)
            return await original_protocol(action)
        state = await runtime.repository.read()
        config = deepcopy(state["profiles"]["profile-a"])
        config["preferences"].update(selected_targets=["samsung:fixture-a"], composition="free", matte="off")
        with patch.object(runtime, "protocol", stalled_save_protocol), patch.object(runtime.cadence, "due", lambda *args: True):
            cancelled_save = asyncio.create_task(runtime.safe_run("profile-a", manager.current_active("profile-a"), config, state))
            while not save_started.is_set():
                assert not cancelled_save.done(), runtime.states
                await asyncio.sleep(0.001)
            try:
                for _ in range(3):
                    cancelled_save.cancel()
                    await asyncio.sleep(0.01)
                    assert not cancelled_save.done() and runtime.inflight_files and runtime.asset_lock.locked()
            finally:
                save_release.set()
            try:
                await cancelled_save
            except asyncio.CancelledError:
                pass
        assert not runtime.inflight_files and not runtime.asset_lock.locked()
        await runtime.cleanup_assets()
        assert set(runtime.asset_root.glob("*.jpg")) == files_before_cancel
        # Genuine Session end fences an already pending model completion.
        begun, release = asyncio.Event(), asyncio.Event()
        async def delayed(_hass, prompt):
            begun.set()
            await release.wait()
            return fixture_image.getvalue()
        await runtime.tick()
        await runtime.jobs["profile-a"]
        await asyncio.sleep(5.1)  # Stable new track after the transition scenarios.
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
        owner = await hass.auth.async_create_user("Synthetic lab owner", group_ids=[GROUP_ID_ADMIN])
        admin = await hass.auth.async_create_user("Synthetic Canvas admin", group_ids=[GROUP_ID_ADMIN])
        from homeassistant.core import Context
        from homeassistant.exceptions import ServiceValidationError
        from homeassistant.helpers import device_registry as dr
        from custom_components.djconnect.music_canvas_http import register_samsung_setup
        register_samsung_setup(hass)
        fixture_entry = SimpleNamespace(entry_id="synthetic-ha-tv", domain="samsungtv", title="TV fixture",
            data={"host": "192.0.2.55", "token": "separate-ha-remote-token"}, unique_id=str(uuid.uuid4()),
            state=SimpleNamespace(value="loaded"))
        fixture_device = SimpleNamespace(id="tv-fixture", name_by_user=None,
                                         config_entries={fixture_entry.entry_id})
        setup_target = adapters.samsung_entry_target(fixture_entry)
        await runtime.repository.mutate(lambda s: s["devices"].update({setup_target["id"]: setup_target}), lambda: True)
        setup_calls = []
        class RegistryArt:
            token = None
            connection = SimpleNamespace(sock=SimpleNamespace(getpeercert=lambda **_: b"fixture-tv-tls-peer"))

            def get_api_version(self):
                setup_calls.append("pair")
                return "6.0.0.0"

            def get_artmode(self): return "on"
            def get_current(self): return {"content_id": "fixture-current-art"}
            def open(self): pass
            def close(self): pass

        def registry_remote(host, **kwargs):
            assert host == setup_target["host"] and kwargs["port"] == 8002 and kwargs["token"] is None
            return SimpleNamespace(art=RegistryArt)
        setup_data = {"device_id": "tv-fixture", "width": 3840, "height": 2160, "orientation": "landscape"}
        entry_lookup = hass.config_entries.async_get_entry
        entry_list = hass.config_entries.async_entries
        with patch.object(dr, "async_get", return_value=SimpleNamespace(
                   async_get=lambda key: fixture_device if key == "tv-fixture" else None)), \
             patch.object(type(hass.config_entries), "async_get_entry", lambda self, key:
                   fixture_entry if key == fixture_entry.entry_id else entry_lookup(key)), \
             patch.object(type(hass.config_entries), "async_entries", lambda self, domain=None, **kw:
                   [fixture_entry] if domain == "samsungtv" else entry_list(domain, **kw)), \
             patch.object(dr, "async_entries_for_config_entry", return_value=[fixture_device]), \
             patch.object(adapters, "samsung_action", real_samsung_action), \
             patch("samsungtvws.SamsungTVWS", registry_remote):
            for fields, context, expected in (
                (setup_data, Context(), "canvas_admin_required"),
                ({**setup_data, "device_id": "unknown"}, Context(user_id=owner.id), "canvas_ha_samsung_target_unavailable"),
            ):
                try:
                    await hass.services.async_call("djconnect", "music_canvas_samsung_setup", fields,
                        blocking=True, context=context)
                    raise AssertionError("invalid Samsung setup accepted")
                except ServiceValidationError as exc:
                    assert exc.translation_domain == "djconnect" and exc.translation_key == expected
            assert not setup_calls
            from custom_components.djconnect.config_flow import DJConnectOptionsFlow
            from homeassistant.auth.const import GROUP_ID_USER
            from homeassistant.components.http import KEY_HASS_USER
            from homeassistant.helpers.http import current_request

            flow = DJConnectOptionsFlow(fixture_entry)
            flow.hass, flow.handler, flow.flow_id = hass, "djconnect", "canvas-samsung-fixture-flow"
            non_admin = await hass.auth.async_create_user("Synthetic non-admin", group_ids=[GROUP_ID_USER])
            for requester in (None, non_admin):
                request_token = current_request.set({KEY_HASS_USER: requester})
                try:
                    denied = await flow.async_step_music_canvas_samsung(setup_data)
                    assert denied["reason"] == "canvas_samsung_admin_required"
                finally:
                    current_request.reset(request_token)

            request_token = current_request.set({KEY_HASS_USER: owner})
            try:
                shown = await flow.async_step_music_canvas_samsung()
                assert shown["type"] == "form"
                assert shown["step_id"] == "music_canvas_samsung"
                assert shown["data_schema"](setup_data) == setup_data
                rejected = await flow.async_step_music_canvas_samsung({**setup_data, "device_id": "unknown"})
                assert rejected["errors"]["base"] == "canvas_samsung_setup_failed" and not setup_calls
                result = await flow.async_step_music_canvas_samsung(setup_data)
                assert result["reason"] == "canvas_samsung_setup_complete"
                await runtime.repository.mutate(
                    lambda canvas: canvas["devices"][setup_target["id"]].update(
                        upload_pending=True, owned_content=["fixture-prior-owned-art"]),
                    lambda: True,
                )
                recover = {"device_id": "tv-fixture", "recover_pending_upload": True}
                rejected = await flow.async_step_music_canvas_samsung({**recover, "width": 3840})
                assert rejected["errors"]["base"] == "canvas_samsung_setup_failed"
                before_recovery = await runtime.repository.read()
                assert before_recovery["devices"][setup_target["id"]]["upload_pending"]
                result = await flow.async_step_music_canvas_samsung(recover)
                assert result["reason"] == "canvas_samsung_setup_complete"
                after_recovery = await runtime.repository.read()
                assert not after_recovery["devices"][setup_target["id"]]["upload_pending"]
                assert after_recovery["devices"][setup_target["id"]]["owned_content"] == ["fixture-prior-owned-art"]
                assert after_recovery["profiles"] == before_recovery["profiles"]
                assert any(item["result"].get("previous_upload_unverified")
                           for item in after_recovery["operations"].values())
            finally:
                current_request.reset(request_token)
        assert setup_calls == ["pair"] and owner.id not in storage.household.shared.ha_user_profile_ids
        paired = (await runtime.repository.read())["devices"][setup_target["id"]]
        assert paired["state"] == "ready" and "token" not in paired
        assert paired["art_registry_entry_id"] == fixture_entry.entry_id and len(paired["art_tls_peer_sha256"]) == 64
        assert not runtime.registry_art_current(paired), "Unloaded registry authority must withdraw access"
        unbound, code = await call("read")
        assert code == 200 and not unbound["can_manage_devices"] and any(
            item["id"] == setup_target["id"] and item["state"] == "ready" for item in unbound["targets"])
        await storage.async_set_profile_mapping("ha_user", admin.id, "profile-a")
        privileged, code = await call("read")
        assert code == 200 and privileged["can_manage_devices"]
        # A delayed private preview cannot survive global target forgetting.
        image_started, image_release = asyncio.Event(), asyncio.Event()
        original_executor = hass.async_add_executor_job
        snapshot = await runtime.repository.read()
        portrait = snapshot["devices"]["switchbot:fixture-p"]
        async def delayed_preview_io(action, *args):
            if getattr(action, "__name__", None) == "read_bytes" and getattr(action, "__self__", None) == runtime.asset_root/portrait["preview"]:
                data = await original_executor(action, *args)
                image_started.set()
                await image_release.wait()
                return data
            return await original_executor(action, *args)
        with patch.object(hass, "async_add_executor_job", delayed_preview_io):
            pending_preview = asyncio.create_task(call("preview", {"target_id": "switchbot:fixture-p"}))
            await asyncio.wait_for(image_started.wait(), timeout=5)
            forgotten, code = await call("forget", dict(binding=binding, operation_id=str(uuid.uuid4()),
                target_id="switchbot:fixture-p", cleanup_remote=False, allow_remaining_art=False))
            assert code == 200 and forgotten["state"] == "confirmed"
            image_release.set()
            late_preview, code = await pending_preview
            assert code == 404 and not late_preview["success"], late_preview
        # Real HA action errors carry translation keys rather than English copy.
        from custom_components.djconnect.music_canvas_http import register_asset_configuration
        register_asset_configuration(hass)
        for origin, context, expected in (
            ("https://canvas.fixture.invalid", Context(), "canvas_admin_required"),
            ("http://invalid.fixture.invalid/path", Context(user_id=admin.id), "canvas_https_origin_required"),
            ("https://invalid.fixture.invalid:bad", Context(user_id=admin.id), "canvas_https_origin_required"),
            ("https://[invalid", Context(user_id=admin.id), "canvas_https_origin_required"),
        ):
            try:
                await hass.services.async_call("djconnect", "music_canvas_asset_access",
                    {"https_origin": origin}, blocking=True, context=context)
                raise AssertionError("invalid asset setup accepted")
            except ServiceValidationError as exc:
                assert exc.translation_domain == "djconnect" and exc.translation_key == expected
        with patch.object(runtime, "stopped", True):
            try:
                await hass.services.async_call("djconnect", "music_canvas_asset_access",
                    {"https_origin": "https://canvas.fixture.invalid"}, blocking=True, context=Context(user_id=admin.id))
                raise AssertionError("stopped runtime accepted setup")
            except ServiceValidationError as exc:
                assert exc.translation_key == "canvas_unavailable"
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
        assert state["profiles"]["profile-a"]["preferences"]["selected_targets"] == ["samsung:fixture-b"]
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
        from custom_components.djconnect.persistence import async_shutdown_persistence, async_initialize_persistence
        old_runtime = runtime
        await async_shutdown_persistence(hass, preserve_for_reload=True)
        assert await setup(hass) is old_runtime and not old_runtime.stopped
        await async_shutdown_persistence(hass)
        assert old_runtime.stopped and "music_canvas" not in hass.data["djconnect"]
        await async_initialize_persistence(hass)
        runtime = await setup(hass)
        assert runtime is not old_runtime
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
    return {"executor_drains_through_repeated_cancellation": True,
            "manual_artwork_takeover_suspends_without_generation": True,
            "interval_survives_track_transition_but_per_track_does_not": True,
            "withdrawal_during_select_prevents_cleanup": True,
            "withdrawal_records_acknowledged_upload_without_selecting_it": True,
            "requests": calls, "actual_sqlite": True, "paired_tls": True,
            "native_switchbot_schema": True, "samsung_upload_select_separate": True,
            "samsung_off_no_upload": True, "synthetic_image_generations": len(generations),
            "shared_samsung_generation": True, "matte_reuses_source": True, "track_title_reuses_source": True,
            "cross_profile_preview_denied": True, "offline_target_isolated": True,
            "late_model_after_session_end_denied": True, "admin_deletion_withdraws_management": True,
            "failed_cleanup_and_explicit_forget_anyway": True,
            "unknown_forget_survives_actual_sqlite_and_runtime_restart": True,
            "unknown_forget_requires_new_explicit_admin_decision": True,
            "preserve_reload_retains_runtime_final_unload_recreates_it": True,
            "asset_configuration_uses_localized_ha_errors": True,
            "ha_admin_pairs_exact_registered_samsung_without_profile_authority_change": True,
            "tokenless_art_registration_pins_tls_and_requires_loaded_entry": True,
            "ha_options_flow_pairs_registered_samsung_with_live_admin": True,
            "ha_admin_recovers_unverified_samsung_upload_without_touching_art_or_profiles": True,
            "late_private_preview_after_forget_is_denied": True,
            "cancelled_private_save_drains_and_releases_all_references": True,
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
