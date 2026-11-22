## 2026-11-22 — Music Origin canonical freeform routing correction

#### Repository Status

`REVIEWABLE_FROZEN` / not merged. The approved source Core #1669 is merged as `9758cbea19e2af153f192cd53480e11a3f9c482b`; Apple #405 is merged as `e0fa68b870893343f4660f42786e3697d0c8e35d`. Their own main/publication evidence already passes. This is a bounded remediation of that same selected source before pending Finalizations Core #1670 / Apple #406, not a new roadmap increment or competing writer. Original WIP, locks, sources and receipts remain preserved.

#### Management Summary

The avatar menu already used type IDs correctly. Direct typed equivalents of the exact English, French and Spanish menu questions did not reach the origin producer because suffix/punctuation differed from the legacy recognizer. The existing backend owner now supplies all five canonical labels to that recognizer, with case/apostrophe/whitespace and terminal question-mark normalization. Prefix commands and negations remain rejected. No contract, schema, provider, narration budget, authority, playback, persistence or Apple product behavior changes.

#### Roadmap Position

Existing owner-selected `DJC-MUSIC-ORIGIN-MOMENT-V1-20261113` / Core #1581. The canonical source freeze/maintenance21 stays unchanged in this repair. Draft Finalizations will reconcile the corrected source only after its own approved merge and exact-main qualification. Joint MO01–MO18 acceptance remains OPEN.

#### Rolling Horizon (Execution Horizon — Next 5 Planned)

1. **MUSIC-ORIGIN::ACCEPTANCE — Joint MO01–MO18 acceptance** — Planned / OPEN; source repair and source qualification are prerequisites, not real-provider/editorial/device acceptance.
2. **ASK-DJ-MOMENTS::ACCEPTANCE — Existing AM01–AM12 acceptance** — Planned / OPEN_ACCEPTANCE.
3. **SETTINGS::APPLE::EDITOR — Shared settings editor** — Planned / NOT_ISSUED; fresh owning-lane selection required.
4. **SETTINGS::PI::ADOPTION — Shared settings adoption** — Planned / NOT_ISSUED; preserve owner/order.
5. **SETTINGS::ESP32::ADOPTION — Shared settings adoption** — Planned / NOT_ISSUED; preserve owner/order.

#### Validation and Acceptance

The original source function was read back unchanged: English, French and Spanish canonical questions returned false; Dutch/German returned true. New tests cover all five canonical labels, normalized variants, negation/command rejection and same-producer informational responses. Real HA2026.11.1 verified-TLS/paired requests exercise the avatar plus all five typed questions, original subject, direct SQLite commit and deduplication (six synthetic model calls, zero real-provider calls). All 47 actual isolated HA regression harnesses were rerun after the source change and pass with all322 product files stable. The complete 4,876-test suite passes with canonical coverage, 11 existing SKIP and zero FAIL/ERROR. New versioned receipts retain all predecessors; no assertion or gate is weakened. [Qualification](docs/verification/music-origin-canonical-locale-routing-20261122.json).

#### Blocked Items

Source repair needs its own protected review/CI and human merge decision. Draft Finalizations Core #1670 and Apple #406 remain on hold for that corrected exact-main/publication evidence. No installation, deployment, real-model, editorial or physical-device acceptance is inferred.

#### Deferred Items

No new provider, device run, release version, background lookup, debt-count target or successor dispatch is added. Existing installed build40531, HA-dev/prod baselines, rollback and original evidence remain preserved.

#### Repository and Workspace State

`REVIEWABLE_FROZEN`; pending protected source merge and separate Finalization. This bounded repair does not claim global `WORKSPACE_READY` or clean another writer's WIP/lock/evidence.
