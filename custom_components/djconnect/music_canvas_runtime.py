"""Installation-owned Canvas lifecycle, original operations and bounded assets."""
from __future__ import annotations
import asyncio
from collections import deque
from copy import deepcopy
from datetime import timedelta
import hashlib
from pathlib import Path
import secrets
import time

from .music_canvas import (
    Cadence, CanvasError, apply_update, digest, finish_forget, need, profile, reserve_forget, screen_cadence,
    DEFAULT_MATTE_SIZE, screen_matte_size, screen_presentation,
)
from .persistence import persistence_service
from .persistence.music_canvas import CanvasRepository
from . import music_canvas_adapters as adapters
from . import music_canvas_render as render

KEY = "music_canvas"


class CanvasRuntime:
    def __init__(self, hass):
        self.hass = hass
        self.repository = CanvasRepository(persistence_service(hass))
        self.lock = asyncio.Lock()
        self.effect_lock = asyncio.Lock()
        self.asset_lock = asyncio.Lock()
        self.cadence = Cadence()
        self.jobs = {}
        self.states = {}
        self.leases = {}
        self.claims = {}
        self.revisions = {}
        self.generation_lock = asyncio.Lock()
        self.inflight_files = set()
        self.next_probe = {}
        self.generation_attempts = deque()
        self.management_operations = set()
        self.stopped = False
        self.unsubscribe = lambda: None
        self.last_discovery = 0
        self.asset_root = Path(hass.config.path(".storage", "djconnect_music_canvas"))

    async def start(self):
        from homeassistant.helpers.event import async_track_time_interval
        from homeassistant.const import EVENT_HOMEASSISTANT_STOP
        state = await self.repository.read()
        if state.get("asset_origin"):
            self.hass.data["djconnect"]["music_canvas_asset_origin"] = state["asset_origin"]
        self.unsubscribe = async_track_time_interval(self.hass, self.tick, timedelta(seconds=5))
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.stop)

    def stop(self, _event=None):
        self.stopped = True
        self.unsubscribe()
        for task in self.jobs.values():
            task.cancel()
        self.leases.clear()

    async def shutdown(self):
        """Drain work before its persistence owner is closed on final unload."""
        self.stop()
        await asyncio.gather(*self.jobs.values(), return_exceptions=True)
        async with self.lock, self.effect_lock:
            pass

    async def snapshot(self, owner, authorize):
        state = await self.repository.read(authorize)
        need(authorize(), "unauthorized", 401)
        result = profile(state, owner)
        selected = set(result["preferences"]["selected_targets"])
        devices = []
        manager = self.hass.data.get("djconnect", {}).get("session_runtime_manager")
        active = manager.current_active(owner) if manager else None
        for key, device in state["devices"].items():
            observed = device["state"]
            if key in selected:
                if not result["preferences"]["enabled"]:
                    observed = "disabled"
                elif active is None:
                    observed = "waiting_music"
                elif self.claims.get(key, owner) != owner:
                    observed = "busy"
                else:
                    observed = self.states.get(key, device["state"])
            preview = device.get("preview") if key in selected and device.get("preview_owner") == owner \
                and not device.get("forgetting") else None
            devices.append({
                "id": key, "name": device["name"], "adapter": device["adapter"],
                "state": observed,
                "screen": device["screen"], "remote_cleanup": device["adapter"] == "samsung"
                    and device.get("cleanup_supported") is True,
                "preview_available": bool(preview),
                "preview_revision": digest(preview) if preview else None,
                "shared_profiles": sum(key in x["preferences"]["selected_targets"] for x in state["profiles"].values()),
                "forgetting": device.get("forgetting") is True,
            })
        return {**result, "targets": devices, "image_generation_available": render.generation_available(self.hass),
                "per_screen_composition_and_cadence": True, "per_screen_matte_size": True}

    async def update(self, owner, binding, data, authorize):
        async with self.lock, self.effect_lock:
            def apply(state):
                revision = profile(state, owner)["revision"]
                result = apply_update(state, owner, binding, data, time.time())
                return result, profile(state, owner)["revision"] != revision

            result, changed = await self.repository.mutate(apply, authorize)
            if not changed:
                return result
            self.revisions[owner] = result["revision"]
            for target, claimant in tuple(self.claims.items()):
                if claimant == owner:
                    self.revoke(target)
            # Revisions fence in-flight work immediately; no execute retry.
            task = self.jobs.get(owner)
            if task:
                task.cancel()
            return result

    async def operation(self, owner, binding, operation, authorize):
        state = await self.repository.read(authorize)
        row = state["operations"].get(digest([owner, binding, operation]))
        need(row is not None and row["expires"] > time.time(), "canvas_operation_not_found", 404)
        result = deepcopy(row["result"])
        if result.get("state") == "pending" and digest([owner, binding, operation]) not in self.management_operations:
            result["state"] = "unknown"
        return result

    async def manage(self, kind, owner, binding, data, authorize):
        """Reserve durably before a physical effect; unknown is never replayed."""
        key = digest([owner, binding, data["operation_id"]])
        fingerprint = digest([kind, data])
        async with self.effect_lock:
            def reserve(state):
                state["operations"] = {k: v for k, v in state["operations"].items() if v["expires"] > time.time()}
                prior = state["operations"].get(key)
                if prior:
                    need(prior["digest"] == fingerprint, "canvas_operation_conflict", 409)
                    return (False, prior["result"], None)
                need(len(state["operations"]) < 256, "canvas_receipts_full", 503)
                device = state["devices"].get(data["target_id"])
                need(device is not None, "canvas_target_unavailable", 404)
                need(not device.get("forgetting") or (
                    kind == "forget" and data["allow_remaining_art"]), "canvas_target_forgetting", 409)
                if kind == "forget":
                    reserve_forget(state, data["target_id"])
                else:
                    device["epoch"] += 1
                receipt = {"state": "pending", "operation_id": data["operation_id"]}
                state["operations"][key] = dict(owner=owner, digest=fingerprint, result=receipt, expires=time.time()+86400)
                return (True, receipt, deepcopy(device))
            reserved, receipt, device = await self.repository.mutate(reserve, authorize)
            if not reserved:
                return receipt
            self.management_operations.add(key)
            try:
                target = data["target_id"]
                self.revoke(target)
                outcome = {"state": "confirmed", "operation_id": data["operation_id"]}
                updates = {}
                try:
                    need(authorize(), "unauthorized", 401)
                    if kind == "setup" and data.get("recover_pending_upload") is True:
                        need(device["state"] == "ready" and device.get("upload_pending")
                             and not device.get("manual_takeover"), "canvas_ha_samsung_setup_incomplete", 409)
                        pairing = {**device, "art_registry_entry_id": data["art_registry_entry_id"]}
                        need(self.registry_art_current(pairing), "canvas_target_unavailable", 404)
                        import functools
                        async with asyncio.timeout(20):
                            observation = await self.protocol(
                                functools.partial(adapters.samsung_action, pairing, "observe"))
                        need(isinstance(observation["current"], dict), "canvas_ha_samsung_setup_incomplete", 409)
                        updates["upload_pending"] = False
                        outcome["previous_upload_unverified"] = True
                    elif kind == "setup":
                        screen = data["screen"]
                        # The setup only supplies unknown fields, never overwrites observed hardware.
                        need(not (set(screen) & set(device["screen"])), "canvas_screen_already_known", 409)
                        updates["screen"] = {**device["screen"], **screen}
                        need({"width", "height", "orientation"} <= set(updates["screen"]),
                             "canvas_screen_setup_required", 409)
                        updates["screen"]["provenance"] = "explicit_setup"
                        width, height = updates["screen"]["width"], updates["screen"]["height"]
                        need(width*height <= 34_000_000, "canvas_screen_invalid", 409)
                        if ((updates["screen"]["orientation"] == "portrait") != (height >= width)):
                            updates["screen"]["width"], updates["screen"]["height"] = height, width
                        if device["adapter"] == "samsung" and not device.get("token"):
                            pairing = {**device}
                            if entry_id := data.get("art_registry_entry_id"):
                                pairing["art_registry_entry_id"] = entry_id
                            need(self.registry_art_current(pairing), "canvas_target_unavailable", 404)
                            async with asyncio.timeout(20):
                                import functools
                                updates.update(await self.protocol(functools.partial(adapters.samsung_action, pairing, "pair")))
                        updates["state"] = "ready"
                        updates["manual_takeover"] = False
                        updates["last_selected_content"] = None
                        if device["adapter"] == "switchbot" and "switchbot_replace_oldest" in data:
                            updates["switchbot_replace_oldest"] = data["switchbot_replace_oldest"]
                    else:
                        remaining = False
                        if data["cleanup_remote"]:
                            need(device["adapter"] == "samsung" and device.get("cleanup_supported") is True,
                                 "canvas_cleanup_unsupported", 409)
                            for content_id in device["owned_content"]:
                                need(authorize(), "unauthorized", 401)
                                need(self.registry_art_current(device), "canvas_target_unavailable", 404)
                                import functools
                                try:
                                    async with asyncio.timeout(20):
                                        result = await self.protocol(functools.partial(
                                            adapters.samsung_action, device, "cleanup", content_id=content_id))
                                    remaining |= not result["deleted"]
                                except Exception:
                                    remaining = True
                        if remaining and not data["allow_remaining_art"]:
                            outcome = {**outcome, "state": "cleanup_failed", "remaining_art": True}
                        else:
                            outcome["remaining_art"] = (remaining or bool(device.get("upload_pending"))
                                or bool(device["owned_content"]) and not data["cleanup_remote"])
                            outcome["tv_authorization_revoked"] = False
                except Exception as exc:
                    outcome = {**outcome, "state": "unknown" if not isinstance(exc, CanvasError) else "rejected",
                               "error": exc.code if isinstance(exc, CanvasError) else "canvas_device_unavailable"}

                def commit(state):
                    current = state["devices"].get(target)
                    if not current or current["epoch"] != device["epoch"]:
                        raise CanvasError("canvas_context_changed", 409)
                    if kind == "forget" and outcome["state"] == "confirmed":
                        finish_forget(state, target)
                    elif kind == "forget":
                        current["forgetting"] = False
                    elif outcome["state"] == "confirmed":
                        current.update(updates)
                    state["operations"][key]["result"] = outcome
                    return outcome
                result = await self.repository.mutate(commit, authorize)
                await self.cleanup_assets()
                return result
            finally:
                self.management_operations.discard(key)

    def revoke(self, target):
        self.states.pop(target, None)
        self.claims.pop(target, None)
        self.leases = {k: v for k, v in self.leases.items() if v["target"] != target}

    def registry_art_current(self, device):
        entry_id = device.get("art_registry_entry_id")
        if not entry_id:
            return True
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != "samsungtv":
            return False
        target = adapters.samsung_entry_target(entry)
        return target is not None and all(target[key] == device.get(key) for key in ("id", "host", "stable_identity"))

    async def purge_owner(self, owner):
        async with self.lock, self.effect_lock:
            self.revisions[owner] = -1
            task = self.jobs.get(owner)
            if task:
                task.cancel()
            self.jobs.pop(owner, None)
            for target, claimant in tuple(self.claims.items()):
                if claimant == owner:
                    self.revoke(target)
            def purge(state):
                state["profiles"].pop(owner, None)
                state["operations"] = {k: v for k, v in state["operations"].items() if v.get("owner") != owner}
                for device in state["devices"].values():
                    if device.get("preview_owner") == owner:
                        for key in ("preview", "preview_owner", "source_image", "presentation", "preview_matte_size", "provenance"):
                            device.pop(key, None)
            await self.repository.mutate(purge, lambda: not self.stopped)
            await self.cleanup_assets()

    async def preview(self, owner, target, authorize):
        state = await self.repository.read(authorize)
        need(target in profile(state, owner)["preferences"]["selected_targets"], "canvas_preview_unavailable", 404)
        device = state["devices"].get(target)
        need(device and device.get("preview") and device.get("preview_owner") == owner
             and not device.get("forgetting"), "canvas_preview_unavailable", 404)
        data = await self.hass.async_add_executor_job((self.asset_root/device["preview"]).read_bytes)
        current = await self.repository.read(authorize)
        after = current["devices"].get(target)
        need(after and not after.get("forgetting") and after["epoch"] == device["epoch"]
             and after.get("preview") == device["preview"] and after.get("preview_owner") == owner
             and target in profile(current, owner)["preferences"]["selected_targets"],
             "canvas_preview_unavailable", 404)
        need(authorize(), "unauthorized", 401)
        return data

    async def cleanup_assets(self):
        async with self.asset_lock:
            state = await self.repository.read()
            live = {x["preview"] for x in state["devices"].values() if x.get("preview")}
            live |= {x["source_image"] for x in state["devices"].values() if x.get("source_image")}
            now = time.time()
            self.leases = {k: v for k, v in self.leases.items() if v["expires"] > now}
            live |= {v["file"] for v in self.leases.values()}
            live |= self.inflight_files
            def clean():
                if self.asset_root.is_dir():
                    for path in self.asset_root.glob("*.jpg"):
                        if path.name not in live:
                            path.unlink(missing_ok=True)
            await self.protocol(clean)

    async def tick(self, _now=None):
        if self.stopped or self.lock.locked():
            return
        async with self.lock:
            state = await self.repository.read()
            if time.monotonic()-self.last_discovery >= 60:
                self.last_discovery = time.monotonic()
                try:
                    discovered = await adapters.discover(self.hass)
                    def merge(current):
                        changed = []
                        for key, item in discovered.items():
                            if key in current["devices"]:
                                if any(item.get(k) != current["devices"][key].get(k)
                                       for k in ("host", "ha_device_id") if k in item):
                                    current["devices"][key]["epoch"] += 1
                                    changed.append(key)
                                current["devices"][key].update({k: item[k] for k in ("host", "ha_device_id", "name") if k in item})
                            elif len(current["devices"]) < 64:
                                current["devices"][key] = item
                        return changed
                    async with self.effect_lock:
                        changed = await self.repository.mutate(merge, lambda: not self.stopped)
                        for target in changed:
                            self.revoke(target)
                except Exception:
                    pass  # No device contact or false ready state on registry failure.
            from .domain.profile.models import ProfileState
            from .profile_context import profile_storage
            manager = self.hass.data.get("djconnect", {}).get("session_runtime_manager")
            storage = profile_storage(self.hass)
            for owner, config in state["profiles"].items():
                self.revisions[owner] = config["revision"]
                active = manager.current_active(owner) if manager else None
                person = storage.household.profiles.get(owner)
                from .profile_privacy import resolve_profile_privacy_policy
                enabled = (config["preferences"]["enabled"] and person is not None
                    and person.state == ProfileState.ACTIVE
                    and not resolve_profile_privacy_policy(person).suppresses_personal_persistence)
                task = self.jobs.get(owner)
                if not enabled or active is None:
                    if task:
                        task.cancel()
                    self.claims = {k: v for k, v in self.claims.items() if v != owner}
                    self.leases = {k: v for k, v in self.leases.items() if v.get("owner") != owner}
                    for target in config["preferences"]["selected_targets"]:
                        if self.claims.get(target, owner) == owner:
                            self.states[target] = "waiting_music" if enabled else "disabled"
                    continue
                if not task or task.done():
                    self.jobs[owner] = self.hass.async_create_task(self.safe_run(owner, active, config, state))
            await self.cleanup_assets()

    async def safe_run(self, owner, active, config, state):
        try:
            async with self.generation_lock:
                await self.run(owner, active, config, state)
        except asyncio.CancelledError:
            raise
        except Exception:
            for target in config["preferences"]["selected_targets"]:
                self.states[target] = "unavailable"

    async def protocol(self, action):
        task = asyncio.ensure_future(self.hass.async_add_executor_job(action))
        return await self.await_effect_completion(task)

    @staticmethod
    async def await_effect_completion(task):
        """Cancellation cannot release an effect slot while its effect is unresolved."""
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Every cancellation (including repeated tick cancellation) must leave
            # the executor future shielded until the physical action has ended.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not task.cancelled():
                task.exception()
            raise

    async def run(self, owner, active, config, state):
        """Use accepted, fresh playing samples; keep last good work on any error."""
        from .profile_context import profile_storage
        manager = self.hass.data["djconnect"].get("session_runtime_manager")
        storage = profile_storage(self.hass)
        authority_revision = storage.authority_revision
        prefs = config["preferences"]
        sample = active.broadcast.passive_observation
        if not sample or time.monotonic()-sample[0] > 30 or sample[2].state != "playing":
            return
        playback = sample[2]
        announcements = getattr(active.broadcast, "track_announcements", None)
        started = getattr(announcements, "current_occurrence", None)
        if started is not None and started.item_id != playback.item_id:
            started = None
        occurrence = digest([active.session_id,
            started.occurrence_id if started is not None else playback.item_id])
        source_track = digest([occurrence, playback.title])
        source_context = deepcopy(manager._history_source_contexts.get(active.session_id))
        def scope_current(per_track=False):
            return (not self.stopped and storage.authority_revision == authority_revision
                    and self.revisions.get(owner) == config["revision"]
                    and str(active.runtime_state) == "active"
                    and (owner, active.session_id) not in manager._visual_ending
                    and manager._history_source_contexts.get(active.session_id) == source_context
                    and (not per_track or started is None or announcements.current_occurrence is started)
                    and manager.current_active(owner) is active and active.broadcast.passive_observation
                    and active.broadcast.passive_observation[2].state == "playing"
                    and (not per_track or active.broadcast.passive_observation[2].item_id == playback.item_id)
                    and time.monotonic()-active.broadcast.passive_observation[0] <= 30)
        groups = {}
        for target in prefs["selected_targets"]:
            device = state["devices"].get(target)
            if not device or device.get("forgetting"):
                continue
            if device.get("manual_takeover"):
                self.claims[target] = owner
                self.states[target] = "canvas_manual_takeover"
                continue
            if device.get("upload_pending"):
                self.states[target] = "canvas_upload_unknown"
                continue
            if self.claims.get(target, owner) != owner:
                self.states[target] = "busy"
                continue
            screen = device["screen"]
            if device["state"] != "ready" or not {"width", "height", "orientation"} <= screen.keys():
                self.states[target] = "needs_setup"
                continue
            if device["adapter"] == "switchbot":
                if not self.hass.data["djconnect"].get("music_canvas_asset_origin"):
                    self.states[target] = "canvas_public_asset_required"
                    continue
                if not self.hass.services.has_service("switchbot_cloud", "upload_art_frame_image"):
                    self.states[target] = "canvas_switchbot_setup_required"
                    continue
                if sum(v["target"] == target for v in self.leases.values()) >= 2 or len(self.leases) >= 32:
                    self.states[target] = "waiting_screen"
                    continue
            key = (owner, active.session_id, target)
            presentation = screen_presentation(prefs, target, device)
            matte_size = screen_matte_size(prefs, target, presentation[1])
            cadence = screen_cadence(prefs, target)
            previous_presentation = device.get("presentation")
            if isinstance(previous_presentation, list) and len(previous_presentation) == 2:
                previous_presentation = [*previous_presentation, False]
            cached = device.get("source_image") if (device.get("preview_owner") == owner
                and (device.get("provenance") or {}).get("source_track") == source_track
                and (previous_presentation != list(presentation)
                     or device.get("preview_matte_size", DEFAULT_MATTE_SIZE) != matte_size)) else None
            if not cached and not self.cadence.due(key, occurrence, cadence, time.monotonic()):
                continue
            if device["adapter"] == "samsung":
                if self.next_probe.get(target, 0) > time.monotonic():
                    continue
                try:
                    async with self.effect_lock:
                        current = await self.repository.read()
                        row = current["devices"].get(target)
                        need(scope_current(cadence == "track") and row and row["epoch"] == device["epoch"]
                             and not row.get("forgetting"), "canvas_context_changed", 409)
                        def authorized():
                            return scope_current(cadence == "track") and self.registry_art_current(row)

                        if len(row["owned_content"]) == 2:
                            device = await self.reconcile_samsung_uploads(row, authorized)
                        else:
                            await self.observe_samsung(row, authorized)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.next_probe[target] = time.monotonic()+30
                    self.states[target] = exc.code if isinstance(exc, CanvasError) else "unavailable"
                    continue
            self.claims[target] = owner
            groups.setdefault((screen["width"], screen["height"], cached, cadence == "track", presentation, matte_size),
                              []).append((target, device, key))
        if not groups:
            return

        pending_attempts = {}
        generated = {}
        try:
            for (width, height, cached, per_track, presentation, matte_size), targets in groups.items():
                composition, matte, show_title = presentation
                def current_scope():
                    return scope_current(per_track)
                need(current_scope(), "canvas_context_changed", 409)
                if not cached and not render.generation_available(self.hass):
                    for target, _, _ in targets:
                        self.states[target] = "image_provider_required"
                    continue
                for target, _, key in targets:
                    self.states[target] = "preparing"
                    # At most one attempt per cadence, including unknown provider outcome.
                    if not cached:
                        attempt = (occurrence, time.monotonic())
                        pending_attempts[key] = attempt
                        self.cadence.mark(key, *attempt)
                generation_key = (width, height, per_track, composition)
                if cached:
                    raw = await self.hass.async_add_executor_job((self.asset_root/cached).read_bytes)
                elif generation_key in generated:
                    raw = generated[generation_key]
                else:
                    now = time.monotonic()
                    while self.generation_attempts and now-self.generation_attempts[0] >= 3600:
                        self.generation_attempts.popleft()
                    need(len(self.generation_attempts) < 48, "canvas_generation_budget_wait", 429)
                    self.generation_attempts.append(now)
                    prompt = render.art_prompt(playback.title, active.selected_mood, composition,
                        width, height, latitude=getattr(self.hass.config, "latitude", None),
                        month=__import__("datetime").datetime.now().month)
                    async with asyncio.timeout(120):
                        raw = await render.generate(self.hass, prompt)
                    generated[generation_key] = raw
                need(current_scope(), "canvas_context_changed", 409)
                art = await self.hass.async_add_executor_job(
                    render.compose, raw, width, height, composition, matte,
                    playback.title if show_title else None, matte_size)
                filename = hashlib.sha256(art).hexdigest()+".jpg"
                source_file = cached or hashlib.sha256(raw).hexdigest()+".jpg"
                self.inflight_files.add(filename)
                self.inflight_files.add(source_file)
                def save():
                    self.asset_root.mkdir(parents=True, exist_ok=True, mode=0o700)
                    path = self.asset_root/filename
                    if not path.exists():
                        path.write_bytes(art)
                        path.chmod(0o600)
                    source = self.asset_root/source_file
                    if not source.exists():
                        source.write_bytes(raw)
                        source.chmod(0o600)
                try:
                    async with self.asset_lock:
                        await self.protocol(save)
                    for target, device, key in targets:
                        # Once delivery starts it may have had a physical effect,
                        # even if the acknowledgement or profile is withdrawn.
                        pending_attempts.pop(key, None)
                        try:
                            await self.deliver(owner, config, active, target, device, filename, art, current_scope,
                                               source_file, source_track=source_track)
                        except CanvasError as exc:
                            self.states[target] = exc.code
                        except Exception:
                            self.states[target] = "unavailable"
                finally:
                    # No cancellable await may strand these bounded references.
                    # Added durable references commit under asset_lock first.
                    self.inflight_files.discard(filename)
                    self.inflight_files.discard(source_file)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            for targets in groups.values():
                for target, _, _ in targets:
                    self.states[target] = exc.code if isinstance(exc, CanvasError) else "unavailable"
        finally:
            if self.revisions.get(owner) != config["revision"]:
                for key, attempt in pending_attempts.items():
                    self.cadence.release(key, attempt)

    async def observe_samsung(self, device, authorize):
        """Respect manual artwork until an admin explicitly reconnects Canvas."""
        import functools
        need(authorize() and self.registry_art_current(device), "canvas_context_changed", 409)
        observed = await self.protocol(functools.partial(adapters.samsung_action, device, "observe"))
        need(authorize() and self.registry_art_current(device), "canvas_context_changed", 409)
        expected = device.get("last_selected_content")
        current = observed.get("current")
        if expected and (not isinstance(current, dict) or current.get("content_id") != expected):
            await self.repository.mutate(
                lambda state: state["devices"][device["id"]].update(manual_takeover=True), authorize)
            raise CanvasError("canvas_manual_takeover", 409)

    async def reconcile_samsung_uploads(self, device, authorize):
        """Retire an older owned upload after the TV confirms the latest one."""
        import functools
        previous, latest = device["owned_content"]
        need(authorize(), "canvas_context_changed", 409)

        async def cleanup_and_record():
            need(authorize(), "canvas_context_changed", 409)
            result = await self.protocol(functools.partial(
                adapters.samsung_action, device, "cleanup", content_id=previous, displayed_content_id=latest))
            need(result["deleted"], "canvas_cleanup_required", 409)

            def record(state):
                row = state["devices"].get(device["id"])
                need(row and row["epoch"] == device["epoch"] and row["owned_content"] == [previous, latest]
                     and not row.get("forgetting"), "canvas_context_changed", 409)
                row["owned_content"].remove(previous)
                row["last_selected_content"] = latest
                row["cleanup_supported"] = True
                return deepcopy(row)

            return await self.repository.mutate(record, self.effect_lock.locked)

        return await self.await_effect_completion(asyncio.create_task(cleanup_and_record()))

    async def deliver(self, owner, config, active, target, device, filename, art, scope_current, source_file,
                      *, source_track=None):
        async with self.effect_lock:
            current = await self.repository.read()
            def authorized():
                row = current["devices"].get(target)
                return (scope_current() and profile(current, owner)["revision"] == config["revision"]
                        and row and row["epoch"] == device["epoch"] and not row.get("forgetting")
                        and self.registry_art_current(device))
            need(authorized(), "canvas_context_changed", 409)
            self.states[target] = "delivering"
            if device["adapter"] == "samsung":
                import functools
                await self.observe_samsung(device, authorized)
                need(len(device["owned_content"]) < 2, "canvas_cleanup_required", 409)
                def reserve_upload(state):
                    state["devices"][target]["upload_pending"] = True
                await self.repository.mutate(reserve_upload, authorized)
                async def upload_and_record():
                    result = await self.protocol(
                        functools.partial(adapters.samsung_action, device, "upload", content=art))
                    uploaded = result["content_id"]

                    def own(state):
                        row = state["devices"].get(target)
                        need(row and row["epoch"] == device["epoch"] and row.get("upload_pending") is True
                             and not row.get("forgetting")
                             and all(row.get(field) == device.get(field) for field in
                                     ("stable_identity", "host", "art_registry_entry_id", "art_tls_peer_sha256")),
                             "canvas_context_changed", 409)
                        if uploaded not in row["owned_content"]:
                            row["owned_content"].append(uploaded)
                        row["upload_pending"] = False

                    # Attribute the acknowledged effect to its original target even
                    # if the Session withdrew. Only a current Session may select it.
                    await self.repository.mutate(own, self.effect_lock.locked)
                    return uploaded

                content_id = await self.await_effect_completion(asyncio.create_task(upload_and_record()))
                need(authorized(), "canvas_context_changed", 409)
                result = await self.protocol(
                    functools.partial(adapters.samsung_action, device, "select", content_id=content_id))
                need(authorized(), "canvas_context_changed", 409)
                observed = "displayed" if result["displayed"] else "delivered_unknown"
            else:
                origin = self.hass.data["djconnect"].get("music_canvas_asset_origin")
                need(type(origin) is str and origin.startswith("https://"), "canvas_public_asset_required", 503)
                lease = secrets.token_urlsafe(32)
                self.leases[lease] = dict(target=target, file=filename, expires=time.time()+900,
                    epoch=device["epoch"], owner=owner, revision=config["revision"], session_id=active.session_id)
                delivery = adapters.deliver_switchbot(self.hass, current["devices"][target],
                    origin.rstrip("/")+"/api/djconnect/music_canvas/asset/"+lease, authorized)
                result = await self.await_effect_completion(asyncio.create_task(delivery))
                observed = result["state"]
            def commit(state):
                need(authorized(), "canvas_context_changed", 409)
                row = state["devices"][target]
                if device["adapter"] == "samsung" and observed == "displayed":
                    row["last_selected_content"] = content_id
                row["preview"] = filename
                row["preview_owner"] = owner
                row["source_image"] = source_file
                presentation = screen_presentation(config["preferences"], target, device)
                row["presentation"] = list(presentation)
                row["preview_matte_size"] = screen_matte_size(config["preferences"], target, presentation[1])
                row["provenance"] = {
                    "input": "bounded_confirmed_title_only", "external_attachments": False,
                    "generated": True, "native_model_resolution_qualified": False,
                    "source_track": source_track}
                return row
            async with self.asset_lock:
                saved = await self.repository.mutate(commit, authorized)
            self.states[target] = observed
            if (device["adapter"] == "samsung" and observed == "displayed"
                    and len(saved["owned_content"]) == 2 and authorized()):
                try:
                    await self.reconcile_samsung_uploads(saved, authorized)
                except Exception:
                    # Keep the verified selection. The next eligible run
                    # reconciles these two owned uploads before adding another.
                    self.next_probe[target] = time.monotonic() + 30


async def setup(hass):
    domain = hass.data.setdefault("djconnect", {})
    lock = domain.setdefault("music_canvas_setup_lock", asyncio.Lock())
    async with lock:
        existing = domain.get(KEY)
        if existing is not None and (existing.stopped or
                existing.repository._persistence is not persistence_service(hass)):
            await existing.shutdown()
            domain.pop(KEY, None)
        if KEY not in domain:
            runtime = CanvasRuntime(hass)
            await runtime.start()
            domain[KEY] = runtime
        return domain[KEY]
