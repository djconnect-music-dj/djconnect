"""Closed paired-native Music Canvas routes and file-scoped opt-in cloud lease."""
from __future__ import annotations
import asyncio
import json
import time
from urllib.parse import urlsplit
from uuid import uuid4
from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .music_canvas import CanvasError, IDENTITY, digest, need, validate_request, validate_screen
from .music_canvas_runtime import KEY

HEADERS = {"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer",
           "X-Content-Type-Options": "nosniff"}

def current_admin(hass, user):
    """Pinned HA AuthStore adapter; missing synchronous readback fails closed.

    async_get_user establishes the original object. The actual live store map
    then fences deletion/replacement without an await inside SQLite commit.
    """
    users = getattr(getattr(hass.auth, "_store", None), "_users", None)
    return (type(users) is dict and users.get(user.id) is user and user.is_active
            and user.is_admin and not user.system_generated)


async def admission(hass, data, headers):
    from .api_handlers import _session_profile_context, _conversation_profile_fence
    from .profile_context import profile_storage
    from .request_auth import resolve_runtime, authorize_runtime_device_request, request_token
    from .profile_settings import binding_digest
    identity = {k: data[k] for k in IDENTITY}
    original = resolve_runtime(hass, data["device_id"], headers)
    need(original and authorize_runtime_device_request(
        original, headers, data["device_id"], data["client_type"]), "unauthorized", 401)
    entry = original.entry
    entry_data, entry_options = entry.data, entry.options
    runtime, context, failure, status = await _session_profile_context(
        hass, identity, headers=headers, user_id=None, source="music_canvas_v1")
    need(failure is None and original is runtime, "unauthorized", status if failure else 401)
    need(context.profile.profile_type.value == "personal", "canvas_profile_not_allowed", 403)
    storage = profile_storage(hass)
    device = storage.household.devices.get(data["device_id"])
    need(device and device.binding_generation, "canvas_binding_unavailable", 503)
    generation = device.binding_generation
    revision = storage.authority_revision

    def authorized():
        try:
            _conversation_profile_fence(hass, runtime, identity, headers, context)
            current = storage.household.devices.get(data["device_id"])
            return (storage.authority_revision == revision and current is device
                and current.binding_generation == generation and current.pairing_state.value == "paired"
                and hass.data.get("djconnect", {}).get(entry.entry_id) is runtime
                and hass.config_entries.async_get_entry(entry.entry_id) is entry
                and entry.disabled_by is None and entry.state.value == "loaded"
                and entry.data is entry_data and entry.options is entry_options
                and authorize_runtime_device_request(runtime, headers, data["device_id"], data["client_type"]))
        except Exception:
            return False
    need(authorized(), "unauthorized", 401)
    binding = binding_digest(entry_id=entry.entry_id, device_id=data["device_id"],
        profile_id=context.profile_id, generation=generation, token=request_token(headers))
    # A paired Profile is not an administrator by name/type. Only an actual
    # persisted HA-user/Profile association and live HA admin account delegate
    # installation-wide Canvas device management to this bound native identity.
    users = []
    for user_id, profile_id in storage.household.shared.ha_user_profile_ids.items():
        if profile_id == context.profile_id:
            user = await hass.auth.async_get_user(user_id)
            if user and current_admin(hass, user):
                users.append(user)
    need(authorized(), "unauthorized", 401)

    def management():
        return authorized() and any(current_admin(hass, u)
            and storage.household.shared.ha_user_profile_ids.get(u.id) == context.profile_id for u in users)
    return context.profile_id, binding, authorized, management


class CanvasView(HomeAssistantView):
    url = "/api/djconnect/v1/music_canvas/{kind}"
    name = "api:djconnect:music_canvas"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def post(self, request, kind):
        try:
            need(not request.query_string and request.content_type == "application/json")
            need(request.headers.get("Content-Encoding", "identity") == "identity")
            need(request.content_length is None or request.content_length <= 8192)
            async with asyncio.timeout(5):
                raw = b""
                while len(raw) <= 8192:
                    chunk = await request.content.read(min(2048, 8193-len(raw)))
                    if not chunk:
                        break
                    raw += chunk
            need(len(raw) <= 8192)
            def pairs(items):
                value = {}
                for key, item in items:
                    need(key not in value)
                    value[key] = item
                return value
            data = json.loads(raw, object_pairs_hook=pairs)
            validate_request(kind, data)
            owner, binding, authorized, management = await admission(self.hass, data, request.headers)
            runtime = self.hass.data["djconnect"].get(KEY)
            need(runtime is not None and not runtime.stopped, "canvas_unavailable", 503)
            if "binding" in data:
                need(data["binding"] == binding, "canvas_binding_changed", 409)
            if kind == "preview":
                content = await runtime.preview(owner, data["target_id"], authorized)
                return web.Response(body=content, content_type="image/jpeg", headers=HEADERS)
            if kind == "read":
                result = await runtime.snapshot(owner, authorized)
                result["can_manage_devices"] = management()
            elif kind == "update":
                result = await runtime.update(owner, binding, data, authorized)
            elif kind == "operation":
                result = await runtime.operation(owner, binding, data["operation_id"], authorized)
            else:
                need(management(), "canvas_admin_required", 403)
                result = await runtime.manage(kind, owner, binding, data, management)
            need(authorized(), "unauthorized", 401)
            operation = {"operation_id": data["operation_id"]} if "operation_id" in data else {}
            return web.json_response({"success": True, "contract_version": 1, "binding": binding,
                                      **operation, **result}, headers=HEADERS)
        except CanvasError as exc:
            return web.json_response({"success": False, "error": exc.code}, status=exc.status, headers=HEADERS)
        except (ValueError, TypeError, KeyError, asyncio.IncompleteReadError):
            return web.json_response({"success": False, "error": "invalid_canvas_request"}, status=400, headers=HEADERS)
        except Exception:
            return web.json_response({"success": False, "error": "canvas_unavailable"}, status=503, headers=HEADERS)


class CanvasAssetView(HomeAssistantView):
    url = "/api/djconnect/music_canvas/asset/{lease}"
    name = "api:djconnect:music_canvas:asset"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request, lease):
        runtime = self.hass.data.get("djconnect", {}).get(KEY)
        row = runtime.leases.get(lease) if runtime and not runtime.stopped else None
        if not request.secure or request.query_string or not row or row["expires"] <= time.time():
            return web.Response(status=404, headers=HEADERS)
        state = await runtime.repository.read()
        device = state["devices"].get(row["target"])
        from .music_canvas import profile
        from .profile_context import profile_storage
        prefs = profile(state, row["owner"])
        manager = self.hass.data["djconnect"].get("session_runtime_manager")
        active = manager.current_active(row["owner"]) if manager else None
        person = profile_storage(self.hass).household.profiles.get(row["owner"])
        from .profile_privacy import resolve_profile_privacy_policy
        authority_revision = profile_storage(self.hass).authority_revision
        if (not device or device.get("forgetting") or device["epoch"] != row["epoch"]
                or not person or str(person.state) != "active"
                or resolve_profile_privacy_policy(person).suppresses_personal_persistence
                or prefs["revision"] != row["revision"] or not prefs["preferences"]["enabled"]
                or row["target"] not in prefs["preferences"]["selected_targets"]
                or not active or active.session_id != row["session_id"]):
            return web.Response(status=404, headers=HEADERS)
        content = await self.hass.async_add_executor_job((runtime.asset_root/row["file"]).read_bytes)
        if (runtime.leases.get(lease) is not row or row["expires"] <= time.time()
                or profile_storage(self.hass).authority_revision != authority_revision
                or runtime.revisions.get(row["owner"]) != row["revision"]
                or manager.current_active(row["owner"]) is not active):
            return web.Response(status=404, headers=HEADERS)
        return web.Response(body=content, content_type="image/jpeg", headers=HEADERS)


def register_asset_configuration(hass):
    """Explicit HA-admin action; never automatically expose assets at startup."""
    import voluptuous as vol
    from homeassistant.exceptions import ServiceValidationError
    async def configure(call):
        user = await hass.auth.async_get_user(call.context.user_id) if call.context.user_id else None
        if not user or not current_admin(hass, user):
            raise ServiceValidationError(translation_domain="djconnect", translation_key="canvas_admin_required")
        origin = call.data["https_origin"].rstrip("/")
        try:
            parts = urlsplit(origin)
            parts.port  # Validate a supplied numeric port as part of the origin.
        except ValueError:
            raise ServiceValidationError(translation_domain="djconnect", translation_key="canvas_https_origin_required") from None
        if origin and (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.path or parts.query or parts.fragment):
            raise ServiceValidationError(translation_domain="djconnect", translation_key="canvas_https_origin_required")
        # The operator qualifies cloud reachability; configuration is not a probe
        # or an assertion that a URL can already be fetched by a physical frame.
        runtime = hass.data.get("djconnect", {}).get(KEY)
        if runtime is None or runtime.stopped:
            raise ServiceValidationError(translation_domain="djconnect", translation_key="canvas_unavailable")
        def save(state):
            state["asset_origin"] = origin or None
        await runtime.repository.mutate(save,
            lambda: current_admin(hass, user))
        runtime.leases.clear()
        hass.data["djconnect"]["music_canvas_asset_origin"] = origin or None
    hass.services.async_register("djconnect", "music_canvas_asset_access", configure,
        schema=vol.Schema({vol.Required("https_origin"): str}))


def register_samsung_setup(hass):
    """Let a current HA administrator pair an existing Samsung device explicitly."""
    import voluptuous as vol
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import device_registry as dr
    from .music_canvas_adapters import samsung_entry_target

    async def setup_samsung(call):
        user = await hass.auth.async_get_user(call.context.user_id) if call.context.user_id else None
        try:
            need(user and current_admin(hass, user), "canvas_admin_required", 403)
            runtime = hass.data.get("djconnect", {}).get(KEY)
            need(runtime is not None and not runtime.stopped, "canvas_unavailable", 503)
            registry = dr.async_get(hass)
            device = registry.async_get(call.data["device_id"])
            need(device is not None, "canvas_ha_samsung_target_unavailable", 404)
            entries = [hass.config_entries.async_get_entry(key) for key in device.config_entries]
            entries = [entry for entry in entries if entry is not None and entry.domain == "samsungtv"]
            need(len(entries) == 1, "canvas_ha_samsung_target_unavailable", 404)
            entry = entries[0]
            target = samsung_entry_target(entry)
            need(target is not None, "canvas_ha_samsung_target_unavailable", 404)

            def authorize():
                return (current_admin(hass, user) and not runtime.stopped
                        and hass.data.get("djconnect", {}).get(KEY) is runtime
                        and registry.async_get(call.data["device_id"]) is device
                        and entry.entry_id in device.config_entries
                        and hass.config_entries.async_get_entry(entry.entry_id) is entry
                        and samsung_entry_target(entry) == target)

            state = await runtime.repository.read(authorize)
            registered = state["devices"].get(target["id"])
            need(registered and registered["adapter"] == "samsung"
                 and registered["stable_identity"] == target["stable_identity"]
                 and registered["host"] == target["host"], "canvas_ha_samsung_target_unavailable", 404)
            screen = {key: call.data[key] for key in ("width", "height", "orientation") if key in call.data}
            validate_screen(screen)
            recover_pending_upload = call.data.get("recover_pending_upload", False)
            need(not recover_pending_upload or not screen, "canvas_ha_samsung_setup_incomplete", 409)
            owner = digest(["canvas_ha_admin", user.id])
            result = await runtime.manage("setup", owner, digest([owner, entry.entry_id]), {
                "operation_id": str(uuid4()), "target_id": target["id"], "screen": screen,
                "art_registry_entry_id": entry.entry_id,
                "recover_pending_upload": recover_pending_upload,
            }, authorize)
            need(result["state"] == "confirmed", "canvas_ha_samsung_setup_incomplete", 409)
        except CanvasError as error:
            raise ServiceValidationError(translation_domain="djconnect",
                                         translation_key=error.code) from None

    hass.services.async_register("djconnect", "music_canvas_samsung_setup", setup_samsung,
        schema=vol.Schema({
            vol.Required("device_id"): str,
            vol.Optional("width"): vol.All(int, vol.Range(min=256, max=8192)),
            vol.Optional("height"): vol.All(int, vol.Range(min=256, max=8192)),
            vol.Optional("orientation"): vol.In(("landscape", "portrait")),
            vol.Optional("recover_pending_upload"): bool,
        }))
