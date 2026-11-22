"""Owner-selected Music Origin delta; preserve every prior planning byte."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path


def validate(plan, previous_validator):
    d = plan["planning_maintenance"]
    receipt = d.get("music_origin_receipt", {})
    path = Path(__file__).parent / "history/20261122/music-origin-predecessor-maintenance-v20.json"
    raw = path.read_bytes()
    prior = json.loads(raw)
    restored = deepcopy(d)
    restored["schema_version"] = "djconnect-federated-planning-delta/20"
    restored.pop("music_origin_receipt", None)
    restored["nodes"] = [n for n in restored["nodes"] if not n["id"].startswith("MUSIC-ORIGIN::")]
    restored["edges"] = [e for e in restored["edges"] if not e["id"].startswith("MUSIC-ORIGIN-")]
    nodes = [n for n in d["nodes"] if n["id"].startswith("MUSIC-ORIGIN::")]
    edges = [e for e in d["edges"] if e["id"].startswith("MUSIC-ORIGIN-")]
    expected_edges = {
        ("MUSIC-ORIGIN::" + a, "MUSIC-ORIGIN::" + b)
        for a, b in [
            ("CONTRACT", "PRODUCER"),
            ("CONTRACT", "APPLE"),
            ("PRODUCER", "ACCEPTANCE"),
            ("APPLE", "ACCEPTANCE"),
        ]
    }
    documents = receipt.get("documents", [])
    root = Path(__file__).resolve().parents[3]
    valid = (
        restored == prior
        and receipt.get("predecessor_sha256") == hashlib.sha256(raw).hexdigest()
        and receipt.get("assignment_id") == "DJC-MUSIC-ORIGIN-MOMENT-V1-20261113"
        and receipt.get("automatic_dispatch") is False
        and receipt.get("overall_acceptance") == "OPEN"
        and receipt.get("source_delivery") == "LOCAL_IMPLEMENTATION_NOT_MERGED"
        and receipt.get("installed") == receipt.get("live_model") == "NOT_RUN"
        and receipt.get("native") == "OPEN_APPLE"
        and receipt.get("owner_issue")
        == "https://github.com/djconnect-music-dj/djconnect/issues/1581"
        and len(documents) == 1
        and documents[0].get("path") == "docs/product/MUSIC_ORIGIN_MOMENT_V1.md"
        and hashlib.sha256((root / documents[0]["path"]).read_bytes()).hexdigest()
        == documents[0].get("sha256")
        and all(
            n["lane"] == ("DJC-APPLE" if n["id"].endswith("::APPLE") else "DJC-CORE") for n in nodes
        )
        and {(e["producer"], e["consumer"]) for e in edges} == expected_edges
        and all(e["hard_precedence"] is True and e["logical_mode"] == "AND" for e in edges)
        and {n["id"] for n in nodes}
        == {"MUSIC-ORIGIN::" + x for x in ("CONTRACT", "PRODUCER", "APPLE", "ACCEPTANCE")}
        and len(edges) == 4
        and all(
            n["status"] == ("Planned" if n["id"].endswith("ACCEPTANCE") else "In progress")
            for n in nodes
        )
    )
    previous = deepcopy(plan)
    previous["planning_maintenance"] = restored
    return (
        [] if valid else ["maintenance: invalid Music Origin scope or altered predecessor"]
    ) + previous_validator(previous)
