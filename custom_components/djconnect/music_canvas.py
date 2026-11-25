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
                matte="off", cadence="1800", cadence_overrides={}, show_track_title=False)
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
    need(type(result["enabled"]) is bool and type(result["show_track_title"]) is bool)
    targets = result["selected_targets"]
    need(type(targets) is list and len(targets) <= 16 and len(set(targets)) == len(targets)
         and all(identifier(x) for x in targets))
    need(result["composition"] in COMPOSITIONS and result["matte"] in MATTES
         and result["cadence"] in CADENCES)
    overrides = result["cadence_overrides"]
    need(type(overrides) is dict and set(overrides) <= set(targets)
         and all(x in CADENCES for x in overrides.values()))
    return result


def fresh_state():
    return {"profiles": {}, "devices": {}, "operations": {}, "asset_origin": None}


def profile(state, owner):
    result = deepcopy(state["profiles"].get(owner, {"revision": 0, "preferences": DEFAULTS}))
    result["preferences"].setdefault("show_track_title", False)
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
    result = {"revision": current["revision"] + 1, "preferences": prefs}
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
        if target in prefs["selected_targets"]:
            prefs["selected_targets"].remove(target)
            prefs["cadence_overrides"].pop(target, None)
            item["revision"] += 1


class Cadence:
    """No catch-up; changes restart a bounded stable-track debounce."""
    def __init__(self):
        self.observed = {}
        self.completed = {}

    def due(self, key, occurrence, cadence, now):
        before = self.observed.get(key)
        if before is None or before[0] != occurrence:
            self.observed[key] = (occurrence, now)
            return False
        if now-before[1] < 5:
            return False
        last = self.completed.get(key)
        return last is None or (last[0] != occurrence if cadence == "track"
                                else now-last[1] >= int(cadence))

    def mark(self, key, occurrence, now):
        self.completed[key] = (occurrence, now)
