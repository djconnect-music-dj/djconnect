"""Versioned Music Canvas domain; no HA, provider, transport or client authority."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import uuid

VERSION = 1
CADENCES = ("track", "900", "1800", "3600")
COMPOSITIONS = ("central", "free", "full")
MATTES = ("off", "matching", "contrast")
DEFAULTS = dict(enabled=False, selected_targets=[], composition="central",
                matte="off", cadence="1800", cadence_overrides={}, show_track_title=False,
                presentation_overrides={})
IDENTITY = {"contract_version", "device_id", "client_type"}
FIELDS = {
    "read": set(),
    "update": {"binding", "operation_id", "expected_revision", "patch"},
    "operation": {"binding", "operation_id"},
    "setup": {"binding", "operation_id", "target_id", "screen"},
    "forget": {"binding", "operation_id", "target_id", "cleanup_remote", "allow_remaining_art"},
    "preview": {"target_id"},
}


class CanvasError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def need(ok, code="invalid_canvas_request", status=400):
    if not ok:
        raise CanvasError(code, status)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def identifier(value, maximum=128):
    return type(value) is str and 0 < len(value) <= maximum and all(
        c.isascii() and (c.isalnum() or c in "-_:") for c in value)


def validate_request(kind, data):
    need(kind in FIELDS and type(data) is dict and set(data) == IDENTITY | FIELDS[kind])
    need(type(data["contract_version"]) is int and data["contract_version"] == VERSION,
         "canvas_contract_upgrade_required", 426)
    need(identifier(data["device_id"]) and data["client_type"] in {"ios", "macos"})
    if "binding" in data:
        need(type(data["binding"]) is str and len(data["binding"]) == 64)
    if "operation_id" in data:
        try:
            need(str(uuid.UUID(data["operation_id"])) == data["operation_id"].lower())
        except (ValueError, TypeError, AttributeError):
            raise CanvasError("invalid_canvas_operation") from None
    if "target_id" in data:
        need(identifier(data["target_id"]))
    if kind == "update":
        need(type(data["expected_revision"]) is int and 0 <= data["expected_revision"] < 2**53)
        patched(DEFAULTS, data["patch"])
    if kind == "setup":
        validate_screen(data["screen"])
    if kind == "forget":
        need(type(data["cleanup_remote"]) is bool and type(data["allow_remaining_art"]) is bool)


def validate_screen(screen):
    need(type(screen) is dict and set(screen) <= {"width", "height", "orientation", "diagonal_inches"})
    for key in ("width", "height"):
        if key in screen:
            need(type(screen[key]) is int and 256 <= screen[key] <= 8192)
    if "orientation" in screen:
        need(screen["orientation"] in {"portrait", "landscape"})
    if "diagonal_inches" in screen:
        need(type(screen["diagonal_inches"]) in {int, float} and 5 <= screen["diagonal_inches"] <= 150)


def patched(current, patch):
    need(type(patch) is dict and bool(patch) and set(patch) <= set(DEFAULTS))
    result = {**deepcopy(current), **deepcopy(patch)}
    result.setdefault("show_track_title", False)
    result.setdefault("presentation_overrides", {})
    need(type(result["enabled"]) is bool and type(result["show_track_title"]) is bool)
    targets = result["selected_targets"]
    need(type(targets) is list and len(targets) <= 16 and len(set(targets)) == len(targets)
         and all(identifier(x) for x in targets))
    need(result["composition"] in COMPOSITIONS and result["matte"] in MATTES
         and result["cadence"] in CADENCES)
    overrides = result["cadence_overrides"]
    need(type(overrides) is dict and set(overrides) <= set(targets)
         and all(x in CADENCES for x in overrides.values()))
    presentation = result["presentation_overrides"]
    need(type(presentation) is dict and len(presentation) <= 64)
    prior_presentation = current.get("presentation_overrides", {})
    for target, style in presentation.items():
        need(identifier(target) and type(style) is dict
             and {"matte", "show_track_title"} <= set(style) <= {"matte", "show_track_title", "composition", "cadence"}
             and style["matte"] in MATTES and type(style["show_track_title"]) is bool)
        need("composition" not in style or style["composition"] in COMPOSITIONS)
        need("cadence" not in style or style["cadence"] in CADENCES)
        presentation[target] = {**prior_presentation.get(target, {}), **style}
    return result


def screen_presentation(prefs, target, device):
    """Keep legacy defaults on TVs and leave photo frames borderless by default."""
    style = prefs.get("presentation_overrides", {}).get(target)
    if style is None:
        style = {"matte": "off", "show_track_title": False} if device["adapter"] == "switchbot" else prefs
    return style.get("composition", prefs["composition"]), style["matte"], style.get("show_track_title", False)


def screen_cadence(prefs, target):
    """Resolve the interval for this screen, including existing saved overrides."""
    style = prefs.get("presentation_overrides", {}).get(target, {})
    return style.get("cadence", prefs["cadence_overrides"].get(target, prefs["cadence"]))


def fresh_state():
    return {"profiles": {}, "devices": {}, "operations": {}, "asset_origin": None}


def profile(state, owner):
    result = deepcopy(state["profiles"].get(owner, {"revision": 0, "preferences": DEFAULTS}))
    result["preferences"].setdefault("show_track_title", False)
    result["preferences"].setdefault("presentation_overrides", {})
    return result


def apply_update(state, owner, binding, data, now):
    """Pure transaction: receipt and preferences change together, bounded replay."""
    state["operations"] = {k: v for k, v in state["operations"].items() if v["expires"] > now}
    key = digest([owner, binding, data["operation_id"]])
    fingerprint = digest(data)
    prior = state["operations"].get(key)
    if prior:
        need(prior["digest"] == fingerprint, "canvas_operation_conflict", 409)
        return deepcopy(prior["result"])
    need(len(state["operations"]) < 256, "canvas_receipts_full", 503)
    current = profile(state, owner)
    need(current["revision"] == data["expected_revision"], "canvas_revision_conflict", 409)
    prefs = patched(current["preferences"], data["patch"])
    need(all(x in state["devices"] and not state["devices"][x].get("forgetting")
             for x in prefs["selected_targets"]), "canvas_target_unavailable", 409)
    need(set(prefs["presentation_overrides"]) <= state["devices"].keys(), "canvas_target_unavailable", 409)
    changed = prefs != current["preferences"]
    result = {"revision": current["revision"] + int(changed), "preferences": prefs}
    if changed:
        state["profiles"][owner] = deepcopy(result)
    state["operations"][key] = dict(owner=owner, digest=fingerprint, result=deepcopy(result), expires=now+86400)
    return result


def reserve_forget(state, target):
    """Fence before yielding to transport; remove only this target's references."""
    device = state["devices"].get(target)
    need(device is not None, "canvas_target_unavailable", 404)
    device["epoch"] = device.get("epoch", 0) + 1
    device["forgetting"] = True


def finish_forget(state, target):
    state["devices"].pop(target, None)
    for item in state["profiles"].values():
        prefs = item["preferences"]
        selected = target in prefs["selected_targets"]
        style = prefs.get("presentation_overrides", {}).pop(target, None)
        if selected:
            prefs["selected_targets"].remove(target)
            prefs["cadence_overrides"].pop(target, None)
        if selected or style is not None:
            item["revision"] += 1


class Cadence:
    """No catch-up; changes restart a bounded stable-track debounce."""
    def __init__(self):
        self.observed = {}
        self.completed = {}

    def mood_changed(self, key, mood_revision):
        last = self.completed.get(key)
        return mood_revision != (last[2] if last is not None else 0)

    def due(self, key, occurrence, cadence, now, mood_revision=0):
        before = self.observed.get(key)
        if before is None or before[0] != occurrence:
            before = self.observed[key] = (occurrence, now)
        if self.mood_changed(key, mood_revision):
            return True
        if now-before[1] < 5:
            return False
        last = self.completed.get(key)
        return last is None or (last[0] != occurrence if cadence == "track"
                                else now-last[1] >= int(cadence))

    def mark(self, key, occurrence, now, mood_revision=0):
        self.completed[key] = (occurrence, now, mood_revision)

    def release(self, key, attempt):
        """Allow replacement of this attempt only before sending it to a device."""
        if self.completed.get(key) == attempt:
            self.completed.pop(key)
