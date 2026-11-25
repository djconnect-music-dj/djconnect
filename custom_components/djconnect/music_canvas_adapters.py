"""Two explicit output families. No playback, Cast or SwitchBot credential copy."""
from __future__ import annotations
from hashlib import sha256
from html import unescape
from ipaddress import ip_address
from urllib.parse import urlsplit
from uuid import UUID

from .music_canvas import CanvasError, digest, need


# Prefer the original target to preserve existing Canvas IDs whenever advertised.
SAMSUNG_SSDP_TARGETS = (
    "urn:schemas-upnp-org:device:MediaRenderer:1",
    "urn:samsung.com:device:RemoteControlReceiver:1",
    "urn:samsung.com:service:MainTVAgent2:1",
    "urn:schemas-upnp-org:service:RenderingControl:1",
)


def _samsung_target(udn, host, name):
    key = "samsung:" + digest(udn)[:32]
    return dict(id=key, name=unescape(str(name or "Samsung"))[:128], adapter="samsung",
                host=host, stable_identity=udn, state="discovered", screen={},
                epoch=0, owned_content=[])


def samsung_entry_target(entry):
    """Resolve a loaded HA entry without reading its remote-control credential."""
    host, identifier = entry.data.get("host"), entry.unique_id
    if entry.state.value != "loaded" or not isinstance(host, str) or not isinstance(identifier, str):
        return None
    try:
        address = ip_address(host)
        uid = UUID(identifier.removeprefix("uuid:"))
    except ValueError:
        return None
    if address.is_loopback or address.is_multicast or address.is_unspecified:
        return None
    return _samsung_target("uuid:" + str(uid), str(address), entry.title)


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
    samsung_hosts = set()
    for search_target in SAMSUNG_SSDP_TARGETS:
        for info in await async_get_discovery_info_by_st(hass, search_target):
            description = info.upnp or {}
            manufacturer = str(description.get("manufacturer") or "").lower()
            udn = description.get("UDN") or info.ssdp_usn
            if "samsung" not in manufacturer or not isinstance(udn, str) or not udn:
                continue
            try:
                host = urlsplit(info.ssdp_location or "").hostname
            except ValueError:
                continue
            if not host or host in samsung_hosts:
                continue
            if search_target != SAMSUNG_SSDP_TARGETS[0]:
                udn = udn.partition("::")[0]
                if not udn:
                    continue
            target = _samsung_target(udn, host, description.get("friendlyName"))
            targets[target["id"]] = target
            samsung_hosts.add(host)
    for entry in hass.config_entries.async_entries("samsungtv"):
        target = samsung_entry_target(entry)
        if target is None or target["host"] in samsung_hosts:
            continue
        targets.setdefault(target["id"], target)
        samsung_hosts.add(target["host"])
    return targets


def _art_peer_sha256(art):
    connection = getattr(art, "connection", None)
    socket = getattr(connection, "sock", None)
    certificate = socket.getpeercert(binary_form=True) if socket is not None else None
    need(bool(certificate), "canvas_pairing_denied", 409)
    return sha256(certificate).hexdigest()


def samsung_action(device, action, *, content=None, content_id=None, displayed_content_id=None):
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
            if type(token) is str and token:
                return {"token": token, "api_version": version,
                        "art_registry_entry_id": None, "art_tls_peer_sha256": None}
            # Some Frames intentionally expose Art over TLS without an Art token.
            # Only the explicit HA-admin setup can nominate the loaded registry entry.
            entry_id = device.get("art_registry_entry_id")
            need(entry_id, "canvas_pairing_denied", 409)
            need(art.get_artmode() == "on", "canvas_manual_takeover", 409)
            need(isinstance(art.get_current(), dict), "canvas_pairing_denied", 409)
            return {"api_version": version, "art_registry_entry_id": entry_id,
                    "art_tls_peer_sha256": _art_peer_sha256(art)}
        if not device.get("token"):
            pin = device.get("art_tls_peer_sha256")
            need(device.get("art_registry_entry_id") and pin, "canvas_pairing_required", 409)
            art.open()
            need(_art_peer_sha256(art) == pin, "canvas_pairing_denied", 409)
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
            if displayed_content_id is not None:
                need(displayed_content_id != content_id and displayed_content_id in device["owned_content"],
                     "canvas_content_not_owned", 403)
                shown = art.get_current()
                need(isinstance(shown, dict) and shown.get("content_id") == displayed_content_id,
                     "canvas_cleanup_required", 409)
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
