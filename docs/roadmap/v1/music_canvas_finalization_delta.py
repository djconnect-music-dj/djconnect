"""Reconcile qualified Canvas source only; preserve every acceptance boundary."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FREEZE = "history/20261122/music-canvas-source-freeze-maintenance-v23.json"
READBACK = "docs/verification/music-canvas-source-publication-readback-20261122.json"
READBACK_SHA = "bb233f110aa8b5dfea7afa6ad5a3a04b4c179ff71e28997ebce62ef1310b403b"
POLICY_SHA = "3fba299f26c75e47804e66218cabea8fd50627bd2a84a1dd294d59009714466f"
SOURCES = {
    "core": ("djconnect-music-dj/djconnect", "8b215bb7a1050bc47e2f85da317d3b4a27abb0f5", "fa3f9b755eba1b94f559a3d6881c7c60e7f89df1", "bb24e1bb8a6076b5e783e1560b2d98627944c6f8"),
    "apple": ("djconnect-music-dj/djconnect-app", "c63b34b6db8644e0f36365863e4e25cc8d3005ae", "c61a4c62595342e21faca3b945790f6f4a06c149", "b34f66bc0043669fbae6d945d1fe8382220a725a"),
}
ORIGINS = {"core": ("evidence-ebbb", "ebbb35f038a7a3c7d46c12660968bcd50eb67580"),
           "apple": ("evidence-4877", "4877403ba6fc69881439e70d3048da13ecb5576b")}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(plan, previous_validator):
    delta = plan["planning_maintenance"]
    receipt = delta.get("music_canvas_finalization_receipt", {})
    raw = (Path(__file__).parent/FREEZE).read_bytes()
    prior = json.loads(raw)
    errors = []

    def check(ok, reason):
        if not ok:
            errors.append("maintenance: Music Canvas Finalization " + reason)

    check(receipt.get("assignment_id") == "DJC-MUSIC-CANVAS-V1-20261115"
          and receipt.get("predecessor_path") == FREEZE
          and receipt.get("predecessor_sha256") == sha(raw), "immutable source freeze")
    check(receipt.get("source_delivery") == "PROTECTED_MERGED"
          and receipt.get("overall_acceptance") == receipt.get("physical_acceptance") == "OPEN"
          and receipt.get("installed") == receipt.get("live_model") == receipt.get("deployment") == "NOT_RUN"
          and receipt.get("native") == "SOURCE_SOFTWARE_ONLY_PHYSICAL_OPEN"
          and receipt.get("automatic_dispatch") is False and receipt.get("consumer_writes") is False,
          "source-only authority and open acceptance")
    restored = deepcopy(delta)
    restored["schema_version"] = "djconnect-federated-planning-delta/23"
    restored.pop("music_canvas_finalization_receipt", None)
    originals = {n["id"]: n for n in prior["nodes"]}
    for node in restored["nodes"]:
        if node["id"].startswith("MUSIC-CANVAS::") and not node["id"].endswith("ACCEPTANCE"):
            check(node.get("status") == "Completed" and node.get("source_delivery") == "SOURCE_DELIVERED",
                  "delivered source leaves")
            original = originals.get(node["id"], {})
            node["status"] = original.get("status")
            if "source_delivery" in original:
                node["source_delivery"] = original["source_delivery"]
            else:
                node.pop("source_delivery", None)
    check(restored == prior, "unchanged predecessor and Planned acceptance")
    documents = receipt.get("documents", [])
    check({x.get("path") for x in documents} == {
        "docs/technical/MUSIC_CANVAS_SOURCE_FINALIZATION_20261122.md",
        "docs/history/prompts/2026-11-22-music-canvas-source-finalization.md"}
        and len(documents) == 2
        and all(sha((ROOT/x["path"]).read_bytes()) == x.get("sha256") for x in documents),
        "exact Finalization documents")
    path = ROOT/READBACK
    if not path.is_file():
        check(False, "missing actual source publication")
    else:
        raw = path.read_bytes()
        check(receipt.get("source_readback_path") == READBACK
              and receipt.get("source_readback_sha256") == sha(raw) == READBACK_SHA,
              "immutable source publication")
        readback = json.loads(raw)
        policy = ROOT/"tools/trusted_delivery/evidence_preservation.py"
        check(sha(policy.read_bytes()) == POLICY_SHA, "original canonical validator")
        spec = importlib.util.spec_from_file_location("canvas_durable_policy", policy)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name, identity in SOURCES.items():
            row = readback.get(name, {})
            check(tuple(row.get(k) for k in ("repository", "qualified_head", "main_sha", "tree")) == identity
                  and row.get("source_tree_equal") is True and row.get("main_validation") == "PASS",
                  name + " actual exact-main provenance")
            snapshot, original = ORIGINS[name]
            expected = {"repository": "djconnect-music-dj/.github", "repository_id": 1461539726,
                        "revision": "89a2a8b4c7571965249bed745bf7c5c37a1221f1", "snapshot": snapshot,
                        "original_repository_id": 1258575431, "original_revision": original}
            durable = row.get("durable_qualification", {})
            encoded = (json.dumps(durable, sort_keys=True, indent=2)+"\n").encode()
            check(durable.get("commit_sha") == identity[2] and row.get("durable_sha256") == sha(encoded)
                  and module.validate_record(durable, expected_policy_source=expected) == [],
                  name + " original twelve-check qualification")
        actual = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (ROOT/"custom_components/djconnect").rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
        check(len(actual) == 328 and readback.get("core", {}).get("archive_product_files") == actual,
              "actual published product identity")
    previous = deepcopy(plan)
    previous["planning_maintenance"] = restored
    return errors + previous_validator(previous)
