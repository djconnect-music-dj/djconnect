"""Reconcile proven source delivery while retaining the original acceptance gates."""

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FREEZE = "history/20261122/music-origin-source-freeze-maintenance-v21.json"
READBACK = "docs/verification/music-origin-source-publication-readback-20261122.json"
READBACK_SHA = "bfa53124c4ecb369b763c0014349d4734a3a8516933449121038e96010986737"
SOURCES = {
    "core": ("djconnect-music-dj/djconnect", "5f4b8be750891869ac6b8ea3a5474473f1aac5dd", "9758cbea19e2af153f192cd53480e11a3f9c482b", "d9739df30d6d46273288b9cdfce54b1cb3e582b0"),
    "apple": ("djconnect-music-dj/djconnect-app", "f489aa2cf8b66fe5bb8972f9cc7def5eca57f63c", "e0fa68b870893343f4660f42786e3697d0c8e35d", "cd072ef748cfa4a77967b8c17383e28a6aef902c"),
}
POLICY = "3fba299f26c75e47804e66218cabea8fd50627bd2a84a1dd294d59009714466f"
POLICY_ORIGINS = {"core": ("evidence-ebbb", "ebbb35f038a7a3c7d46c12660968bcd50eb67580"),
                  "apple": ("evidence-4877", "4877403ba6fc69881439e70d3048da13ecb5576b")}



def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(plan, previous_validator):
    d = plan["planning_maintenance"]
    receipt = d.get("music_origin_finalization_receipt", {})
    frozen_raw = (Path(__file__).parent / FREEZE).read_bytes()
    frozen = json.loads(frozen_raw)
    errors = []

    def check(ok, reason):
        if not ok:
            errors.append("maintenance: Music Origin Finalization " + reason)

    check(receipt.get("assignment_id") == "DJC-MUSIC-ORIGIN-MOMENT-V1-20261113"
          and receipt.get("predecessor_path") == FREEZE
          and receipt.get("predecessor_sha256") == digest(frozen_raw), "source freeze")
    check(receipt.get("source_delivery") == "PROTECTED_MERGED"
          and receipt.get("automatic_dispatch") is False
          and receipt.get("consumer_writes") is False, "bounded source authority")
    check(receipt.get("overall_acceptance") == "OPEN"
          and receipt.get("native") == "SOURCE_SOFTWARE_ONLY_PHYSICAL_OPEN"
          and all(receipt.get(k) == "NOT_RUN" for k in ("installed", "deployment", "live_model")),
          "open real-provider/editorial/device acceptance")
    documents = receipt.get("documents", [])
    check(isinstance(documents, list) and len(documents) == 2
          and {row.get("path") for row in documents} == {
              "docs/technical/MUSIC_ORIGIN_SOURCE_FINALIZATION_20261122.md",
              "docs/history/prompts/2026-11-22-music-origin-source-finalization.md"}
          and all(digest((ROOT / row["path"]).read_bytes()) == row.get("sha256") for row in documents),
          "exact separate Finalization documents")
    restored = deepcopy(d)
    restored["schema_version"] = "djconnect-federated-planning-delta/21"
    restored.pop("music_origin_finalization_receipt", None)
    originals = {n["id"]: n for n in frozen["nodes"]}
    for n in restored["nodes"]:
        if n["id"].startswith("MUSIC-ORIGIN::") and not n["id"].endswith("ACCEPTANCE"):
            check(n.get("status") == "Completed" and n.get("source_delivery") == "SOURCE_DELIVERED",
                  "source leaves only")
            n["status"] = originals[n["id"]]["status"]
            if "source_delivery" in originals[n["id"]]:
                n["source_delivery"] = originals[n["id"]]["source_delivery"]
            else:
                n.pop("source_delivery", None)
    check(restored == frozen, "unchanged predecessor and joint Planned gate")
    path = ROOT / READBACK
    if not path.is_file():
        check(False, "missing actual publication readback")
    else:
        raw = path.read_bytes()
        check(receipt.get("source_readback_path") == READBACK
              and receipt.get("source_readback_sha256") == digest(raw) == READBACK_SHA,
              "immutable actual publication readback")
        evidence = json.loads(raw)
        policy = ROOT / "tools/trusted_delivery/evidence_preservation.py"
        check(digest(policy.read_bytes()) == POLICY, "original canonical validator")
        spec = importlib.util.spec_from_file_location("music_origin_durable_policy", policy)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name, (repository, head, merge, tree) in SOURCES.items():
            snapshot, original = POLICY_ORIGINS[name]
            expected_policy = {"repository": "djconnect-music-dj/.github", "repository_id": 1461539726,
                               "revision": "89a2a8b4c7571965249bed745bf7c5c37a1221f1", "snapshot": snapshot,
                               "original_repository_id": 1258575431, "original_revision": original}
            row = evidence.get(name, {})
            durable = row.get("durable_qualification", {})
            encoded = (json.dumps(durable, sort_keys=True, indent=2) + "\n").encode()
            check((row.get("repository"), row.get("qualified_head"), row.get("main_sha"), row.get("tree"))
                  == (repository, head, merge, tree)
                  and row.get("source_tree_equal") is True and row.get("main_validation") == "PASS",
                  name + " exact merged source and own main")
            check(durable.get("commit_sha") == merge
                  and row.get("durable_sha256") == digest(encoded)
                  and module.validate_record(durable, expected_policy_source=expected_policy) == [], name + " canonical durable qualification")
        product = evidence.get("core", {}).get("archive_product_files", {})
        actual = {str(p.relative_to(ROOT)): digest(p.read_bytes())
                  for p in (ROOT / "custom_components/djconnect").rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
        check(len(product) == 322 and product == actual, "published product identity")
    previous = deepcopy(plan)
    previous["planning_maintenance"] = restored
    return errors + previous_validator(previous)
