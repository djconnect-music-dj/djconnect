"""Qualify the combined baseline and retain its delivered predecessor."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

from experience_reconciliation_delta import HISTORICAL_DOCUMENT_SOURCES


ROADMAP = Path(__file__).resolve().parent
ROOT = ROADMAP.parents[2]
HISTORY = ROADMAP / "history/20261124"
FREEZE = HISTORY / "vibecast-baseline-predecessor-maintenance-v32.json"
FREEZE_SHA256 = "f371f0317b7b266001616c8ba60d419314ee81f5943c281f6d4282d7da5659b4"
SNAPSHOTS = HISTORY / "vibecast-baseline-predecessor-files"
BASELINE_ARCHIVE = HISTORY / "vibecast-baseline-main-files"
CHANGED_VERIFICATION_INPUTS = {
    "scripts/verification/verify_music_canvas_http.py",
    "scripts/verification/passive_observation_sequence_lab.py",
}
FILES = {
    "API_CONTRACT.md",
    "ARCHITECTURE_PRINCIPLES.md",
    "SYNC_PROMPTS.md",
    "docs/technical/MUSIC_CANVAS_V1_CONTRACT.md",
    "docs/technical/VIBECAST_GUEST_PARTICIPATION_V1.md",
    "tests/browser/vibecast_display_flow.cjs",
}
EVIDENCE = {
    kind: f"docs/verification/vibecast-baseline-{suffix}-20261124.json"
    for kind, suffix in {
        "product_manifest": "product-manifest",
        "qualification": "qualification",
        "live_ui": "live-actual-ha",
        "browser": "browser",
        "derivation": "receipt-derivation",
    }.items()
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def predecessor_files():
    previous = HISTORICAL_DOCUMENT_SOURCES.get()
    token = HISTORICAL_DOCUMENT_SOURCES.set({**previous, **{name: SNAPSHOTS / name for name in FILES},
        **{name: BASELINE_ARCHIVE / name for name in CHANGED_VERIFICATION_INPUTS}})
    try:
        yield
    finally:
        HISTORICAL_DOCUMENT_SOURCES.reset(token)


def validate(plan, previous_validator):
    delta = plan["planning_maintenance"]
    receipt = delta.get("vibecast_baseline_receipt")
    if not isinstance(receipt, dict):
        return ["maintenance: VibeCast baseline receipt object required"]
    errors = []

    def check(condition, reason):
        if not condition:
            errors.append("maintenance: VibeCast baseline " + reason)

    prior = json.loads(FREEZE.read_bytes())
    restored = dict(delta)
    restored.pop("vibecast_baseline_receipt")
    restored["schema_version"] = prior["schema_version"]
    check(restored == prior and receipt.get("predecessor_sha256") == sha(FREEZE) == FREEZE_SHA256,
          "immutable delivered predecessor")
    check(receipt.get("assignment_id") == "DJC-VIBECAST-UI-IMPROVEMENTS-20261123"
          and receipt.get("source_delivery") == "LOCAL_IMPLEMENTATION_NOT_MERGED"
          and receipt.get("overall_acceptance") == "OPEN"
          and all(receipt.get(key) == "NOT_RUN" for key in
                  ("installed", "deployment", "real_provider", "physical_satellite"))
          and receipt.get("automatic_dispatch") is receipt.get("consumer_writes") is False,
          "software scope and open acceptance")
    retained = receipt.get("retained_files", [])
    archived_document = "docs/technical/MUSIC_CANVAS_V1_CONTRACT.md"
    check(len(retained) == len(FILES) and {row.get("path") for row in retained} == FILES
          and all(sha(SNAPSHOTS / row["path"]) == row.get("previous_sha256")
                  and sha((BASELINE_ARCHIVE if row["path"] == archived_document else ROOT) / row["path"])
                  == row.get("current_sha256") for row in retained),
          "current and historical documents and harness")
    evidence = receipt.get("evidence", {})
    check(set(evidence) == set(EVIDENCE)
          and all(evidence[kind].get("path") == name
                  and evidence[kind].get("sha256") == sha(ROOT / name) for kind, name in EVIDENCE.items()),
          "exact evidence file bindings")
    loaded = {kind: json.loads((ROOT / name).read_bytes()) for kind, name in EVIDENCE.items()}
    actual = loaded["product_manifest"]
    publication = ROOT / "docs/verification/vibecast-baseline-source-publication-20261124.json"
    published = json.loads(publication.read_bytes())
    check(sha(publication) == "b383a7ff21ed2f6a93c5af3ef2b1fa6bb127a6ca8554142ec5cc6aa6a13cf54d"
          and published["archive_exact_product_manifest"] == EVIDENCE["product_manifest"]
          and published["archive_exact_product_manifest_sha256"] == sha(ROOT / EVIDENCE["product_manifest"])
          and published["archive_product_file_count"] == len(actual) == 359,
          "independent publication binding for the frozen product bytes")
    current = {str(path.relative_to(ROOT)): sha(path)
               for path in (ROOT / "custom_components/djconnect").rglob("*")
               if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    successor = ROOT / "docs/verification/vibecast-cast-session-update-actual-ha-matrix-20261124.json"
    successor_matrix = json.loads(successor.read_bytes())
    successor_rows = successor_matrix["results"]
    check(current == successor_matrix["source_pins"]
          == json.loads((ROOT / "docs/verification/vibecast-cast-session-update-product-manifest-20261124.json").read_bytes())
          and successor_matrix["source_before_after_equal"] is True
          and len(current) == 359 and len(successor_rows) == 54
          and all(row["exit_code"] == 0 and sha(ROOT / row["harness"]) == row["harness_sha256"]
                  for row in successor_rows), "current Music Canvas exact-source HA requalification")
    proof = loaded["qualification"]
    matrix_path = ROOT / "docs/verification/vibecast-baseline-actual-ha-matrix-20261124.json"
    matrix = json.loads(matrix_path.read_bytes())
    prior_matrix = json.loads((ROOT / "docs/verification/vibecast-ui-actual-ha-matrix-20261124.json").read_bytes())
    rows = matrix["results"]
    check(actual == loaded["product_manifest"] == proof.get("source_pins") == matrix["source_pins"]
          and len(actual) == 359 and proof.get("matrix_sha256") == sha(matrix_path)
          and proof.get("matrix_path") == str(matrix_path.relative_to(ROOT))
          and proof.get("source_before_after_equal") is matrix.get("source_before_after_equal") is True
          and len(rows) == proof.get("execution_count") == 54
          and {row["harness"] for row in rows} == {row["harness"] for row in prior_matrix["results"]}
          and all(row["exit_code"] == 0 and sha((BASELINE_ARCHIVE if row["harness"] in CHANGED_VERIFICATION_INPUTS else ROOT)
                  / row["harness"]) == row["harness_sha256"] for row in rows),
          "complete 359-file inventory and actual HA matrix")
    retry, = [row for row in rows if row["harness"] == "scripts/verification/verify_passive_observation_http.py"]
    check(retry.get("updated_helper") == "scripts/verification/passive_observation_sequence_lab.py"
          and retry.get("updated_helper_sha256") == sha(BASELINE_ARCHIVE / "scripts/verification/passive_observation_sequence_lab.py")
          and retry.get("previous_failed_run", {}).get("exit_code") == 1,
          "original failure and verified corrected passive-observation harness")
    widget = proof.get("additional_native_execution", {})
    widget_receipt = widget.get("receipt", {})
    widget_cases = widget_receipt.get("extension", {}).get("cases", [])
    check(widget.get("exit_code") == 0
          and widget.get("harness_sha256") == sha(ROOT / "scripts/verification/verify_native_widget_winner_actual_ha.py")
          and widget_receipt.get("product_source_pins") == actual
          and widget_receipt.get("product_source_before_after_equal") is True
          and len(widget_cases) == 10 and all(case.get("status") == "PASS" for case in widget_cases),
          "actual HA Widget winner and withdrawal scenarios")
    live = loaded["live_ui"]
    extension = live["extension"]
    live_cases = extension["requests"]
    from vibecast_ui_delta import EXPECTED_LIVE_CASES
    check(live.get("product_source_pins") == actual and live.get("product_source_before_after_equal") is True
          and live.get("live_ui_harness_sha256") == sha(ROOT / "scripts/verification/verify_vibecast_live_ui_actual_ha.py")
          and all(sha(ROOT / "scripts/verification" / name) == value for name, value in live["reused_harnesses"].items())
          and len(live_cases) == 11 and {case["scenario"] for case in live_cases} == EXPECTED_LIVE_CASES
          and all(case["status"] == "PASS" for case in live_cases)
          and extension.get("actual_ha") is extension.get("actual_verified_tls") is True
          and extension.get("live_ui_model_calls") == 0
          and extension.get("physical_native_app_TV_and_real_provider") == "NOT_RUN",
          "actual HA Live and provider scope")
    browser = loaded["browser"]
    check(browser.get("source_pins") == actual and browser.get("result") == "PASS"
          and browser.get("harness") == "tests/browser/vibecast_display_flow.cjs"
          and browser.get("harness_sha256") == sha(ROOT / "tests/browser/vibecast_display_flow.cjs")
          and browser.get("engines") == ["chromium", "webkit"]
          and set(browser.get("logs_sha256", {})) == {"chromium", "webkit"},
          "maintained two-engine renderer scenarios")
    derivation = loaded["derivation"]
    bindings = derivation.get("bindings", [])
    check(derivation.get("mode") == "write" and derivation.get("source_before_after_equal") is True
          and len(bindings) == 45 and all(sha(ROOT / row["current"]) == row["current_sha256"]
                                         and sha(ROOT / row["predecessor"]) == row["predecessor_sha256"]
                                         for row in bindings),
          "derived and immutable predecessor evidence bindings")
    previous = {**plan, "planning_maintenance": restored}
    with predecessor_files():
        return errors + previous_validator(previous)
