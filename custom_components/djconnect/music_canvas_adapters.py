"""Two explicit output families. No playback, Cast or SwitchBot credential copy."""
from __future__ import annotations
from urllib.parse import urlsplit

from .music_canvas import CanvasError, need


async def discover(hass):
    """Read shared HA registries/SSDP cache only, never perform a LAN scan."""
    from homeassistant.helpers import device_registry as dr
    from homeassistant.components.ssdp import async_get_discovery_info_by_st
    targets = {}
    registry = dr.async_get(hass)
    cloud_devices = {}
    for entry in hass.config_entries.async_entries("switchbot_cloud"):
        if entry.state.value == "loaded":
            for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
                cloud_devices[device.id] = device
    for device in cloud_devices.values():
        entries = [hass.config_entries.async_get_entry(x) for x in device.config_entries]
        loaded = any(x and x.domain == "switchbot_cloud" and x.state.value == "loaded" for x in entries)
        if loaded and device.model == "AI Art Frame" and any(x[0] == "switchbot_cloud" for x in device.identifiers):
            key = "switchbot:" + device.id
            targets[key] = dict(id=key, name=device.name_by_user or device.name or "SwitchBot",
                                adapter="switchbot", ha_device_id=device.id,
                                state="needs_setup", screen={}, epoch=0, owned_content=[])
    for info in await async_get_discovery_info_by_st(hass, "urn:schemas-upnp-org:device:MediaRenderer:1"):
        description = info.upnp or {}
        manufacturer = str(description.get("manufacturer") or "").lower()
        udn = description.get("UDN") or info.ssdp_usn
        if "samsung" not in manufacturer or not udn:
            continue
        host = urlsplit(info.ssdp_location).hostname
        if not host:
            continue
        from .music_canvas import digest
        key = "samsung:" + digest(str(udn))[:32]
        targets[key] = dict(id=key, name=str(description.get("friendlyName") or "Samsung")[:128],
                            adapter="samsung", host=host, stable_identity=str(udn),
                            state="discovered", screen={}, epoch=0, owned_content=[])
    return targets


def samsung_action(device, action, *, content=None, content_id=None):
    """Blocking protocol library is confined to an executor and one connection."""
    from samsungtvws import SamsungTVWS
    remote = SamsungTVWS(device["host"], port=8002, token=device.get("token"),
                         timeout=10, name="DJConnect Music Canvas")
    art = remote.art()
    try:
        if action == "pair":
            version = art.get_api_version()
            need(type(version) is str and bool(version), "canvas_samsung_unsupported", 409)
            token = art.token
            need(type(token) is str and bool(token), "canvas_pairing_denied", 409)
            return {"token": token, "api_version": version}
        need(device.get("token"), "canvas_pairing_required", 409)
        # Never call set_artmode, power, remote keys, HDMI, volume or sound APIs.
        need(art.get_artmode() == "on", "canvas_manual_takeover", 409)
        if action == "upload":
            uploaded = art.upload(content, matte="none", portrait_matte="none", file_type="jpg")
            need(type(uploaded) is str and bool(uploaded), "canvas_upload_unknown", 503)
            return {"content_id": uploaded}
        if action == "select":
            art.select_image(content_id, show=True)
            observed = art.get_current()
            return {"displayed": isinstance(observed, dict) and observed.get("content_id") == content_id}
        if action == "cleanup":
            need(content_id in device.get("owned_content", []), "canvas_content_not_owned", 403)
            return {"deleted": art.delete(content_id) is True}
        if action == "observe":
            return {"current": art.get_current()}
        raise CanvasError("canvas_adapter_action_invalid")
    finally:
        art.close()


async def deliver_switchbot(hass, device, image_url, authorize):
    need(authorize(), "canvas_context_changed", 409)
    need(hass.services.has_service("switchbot_cloud", "upload_art_frame_image"),
         "canvas_switchbot_setup_required", 503)
    parts = urlsplit(image_url)
    need(parts.scheme == "https" and bool(parts.hostname) and not parts.username
         and not parts.password and not parts.fragment, "canvas_public_asset_required", 503)
    need(authorize(), "canvas_context_changed", 409)
    await hass.services.async_call("switchbot_cloud", "upload_art_frame_image",
        {"device_id": [device["ha_device_id"]], "image_url": image_url}, blocking=True)
    # Irrevocable submitted cloud action can still complete after withdrawal.
    return {"state": "delivered_unknown", "displayed": False}
