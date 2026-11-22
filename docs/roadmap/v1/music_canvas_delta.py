"""One selected Canvas increment, preserving the complete delivered predecessor."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FREEZE = "history/20261122/music-canvas-predecessor-maintenance-v22.json"
EXPECTED = {"CONTRACT", "PROFILE", "PRODUCER", "SAMSUNG", "SWITCHBOT", "APPLE", "ACCEPTANCE"}
LINKS = {("CONTRACT", x) for x in ("PROFILE", "PRODUCER", "SAMSUNG", "SWITCHBOT", "APPLE")} | {
    (x, "ACCEPTANCE") for x in ("PROFILE", "PRODUCER", "SAMSUNG", "SWITCHBOT", "APPLE")}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate(plan, previous_validator):
    from music_origin_finalization_delta import validate as validate_previous
    from experience_reconciliation_delta import HISTORICAL_DOCUMENT_SOURCES
    d = plan["planning_maintenance"]
    receipt = d.get("music_canvas_receipt", {})
    raw = (Path(__file__).parent/FREEZE).read_bytes()
    prior = json.loads(raw)
    restored = deepcopy(d)
    restored["schema_version"] = "djconnect-federated-planning-delta/22"
    restored.pop("music_canvas_receipt", None)
    restored["nodes"] = [x for x in restored["nodes"] if not x["id"].startswith("MUSIC-CANVAS::")]
    restored["edges"] = [x for x in restored["edges"] if not x["id"].startswith("MUSIC-CANVAS-")]
    errors = []
    def check(ok, reason):
        if not ok:
            errors.append("maintenance: Music Canvas " + reason)
    old_references = {r["path"]: r["sha256"] for r in prior["document_references"]}
    for ref in restored["document_references"]:
        if ref["path"] in {"API_CONTRACT.md", "PRODUCT_BACKLOG.md"}:
            check(ref["sha256"] == sha((ROOT/ref["path"]).read_bytes()), "current canonical document reference")
            ref["sha256"] = old_references[ref["path"]]
    check(restored == prior and receipt.get("predecessor_sha256") == sha(raw), "predecessor changed")
    check(receipt.get("assignment_id") == "DJC-MUSIC-CANVAS-V1-20261115"
          and receipt.get("automatic_dispatch") is False
          and receipt.get("source_delivery") == "LOCAL_IMPLEMENTATION_NOT_MERGED"
          and receipt.get("overall_acceptance") == "OPEN"
          and receipt.get("installed") == receipt.get("live_model") == "NOT_RUN", "source/acceptance boundary")
    nodes = [x for x in d["nodes"] if x["id"].startswith("MUSIC-CANVAS::")]
    check({x["id"] for x in nodes} == {"MUSIC-CANVAS::"+x for x in EXPECTED}, "bounded node set")
    check(all(x["status"] == ("Planned" if x["id"].endswith("ACCEPTANCE") else "In progress")
        and x["lane"] == ("DJC-APPLE" if x["id"].endswith("APPLE") else "DJC-CORE") for x in nodes),
        "owning lanes/status")
    edges = [x for x in d["edges"] if x["id"].startswith("MUSIC-CANVAS-")]
    check({(x["producer"], x["consumer"]) for x in edges}
          == {("MUSIC-CANVAS::"+a, "MUSIC-CANVAS::"+b) for a, b in LINKS}
          and len(edges) == len(LINKS)
          and all(x["hard_precedence"] and x["logical_mode"] == "AND" for x in edges), "actual dependencies")
    documents = receipt.get("documents", [])
    check({x.get("path") for x in documents} == {
        "docs/product/MUSIC_CANVAS_V1.md", "docs/technical/MUSIC_CANVAS_V1_CONTRACT.md",
        "API_CONTRACT.md", "PRODUCT_BACKLOG.md"}
        and all(sha((ROOT/x["path"]).read_bytes()) == x.get("sha256") for x in documents),
        "canonical design/contract")
    manifest_path = ROOT/"docs/verification/music-canvas-product-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    actual = {str(p.relative_to(ROOT)): sha(p.read_bytes())
        for p in (ROOT/"custom_components/djconnect").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    check(manifest == actual and receipt.get("product_manifest_sha256") == sha(manifest_path.read_bytes()),
          "current candidate product manifest")
    previous = dict(plan)
    previous["planning_maintenance"] = restored
    # The original exact source proof remains verified against its immutable
    # readback. Current candidate bytes are independently checked above; they
    # must not be passed off as the previously published Music Origin product.
    archived = receipt.get("predecessor_documents", [])
    pins = {r["path"]: r["sha256"] for r in prior["document_references"]}
    check({r.get("path") for r in archived} == {"API_CONTRACT.md", "PRODUCT_BACKLOG.md"}
          and all(r.get("sha256") == pins.get(r["path"])
              and r.get("snapshot") == "docs/roadmap/v1/history/20261122/music-canvas-predecessor-documents/"+r["path"]
              and sha((ROOT/r["snapshot"]).read_bytes()) == r["sha256"] for r in archived),
          "immutable predecessor document source")
    token = HISTORICAL_DOCUMENT_SOURCES.set({r["path"]: ROOT/r["snapshot"] for r in archived})
    try:
        return errors + validate_previous(previous, previous_validator, historical_product=True)
    finally:
        HISTORICAL_DOCUMENT_SOURCES.reset(token)
