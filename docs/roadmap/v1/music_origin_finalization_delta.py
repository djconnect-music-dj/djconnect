"""Reconcile proven source delivery while retaining the original acceptance gates."""

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FREEZE = "history/20261122/music-origin-source-freeze-maintenance-v21.json"
READBACK = "docs/verification/music-origin-corrected-source-publication-readback-20261122.json"
READBACK_SHA = "22ac24df11e7ce0a8aa4dbc4864e479c6b3c87eb03feced9bc9e0df8bcd7688e"
SOURCES = {
    "core": ("djconnect-music-dj/djconnect", "e1697270dd71f87831f280158b5086fcd29e1d8b", "0cfff07002dc13d05d768212d09c71e894da3282", "38fbb906afb1865ada1ccb12b5e8efb53d576b38"),
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
          and receipt.get("live_model") == "NOT_RUN"
          and receipt.get("installed") == "SEPARATE_AUTHORIZED_OPERATION"
          and receipt.get("deployment") == "SEPARATE_AUTHORIZED_HA_DEV_OPERATION"
          and receipt.get("physical_acceptance") == "OPEN",
          "open real-provider/editorial/device acceptance")
    documents = receipt.get("documents", [])
    check(isinstance(documents, list) and len(documents) == 2
          and {row.get("path") for row in documents} == {
              "docs/technical/MUSIC_ORIGIN_CORRECTED_SOURCE_FINALIZATION_20261122.md",
              "docs/history/prompts/2026-11-22-music-origin-corrected-source-finalization.md"}
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
        installation = evidence.get("separate_authorized_installation", {})
        encoded_installation = (json.dumps(installation, indent=2) + "\n").encode()
        check(receipt.get("installation_receipt_sha256") == digest(encoded_installation)
              and installation.get("installed_targets") == ["iphone", "macbook", "ha-dev"]
              and installation.get("core_source") == SOURCES["core"][2]
              and installation.get("apple_source") == SOURCES["apple"][2]
              and installation.get("apple_build") == "40532"
              and installation.get("ha_dev", {}).get("exact_actual_runtime_files") == 322
              and installation.get("ha_dev", {}).get("existing_principals_preserved") == 13
              and installation.get("ha_dev", {}).get("music_origin_advertised") is True,
              "separate authorized installation identity and scope")
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
