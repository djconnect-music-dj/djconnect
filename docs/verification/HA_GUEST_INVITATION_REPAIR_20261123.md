# Same-tab guest invitation correction

The real browser reproduced a defect on released main
`48c25f820fbfa39270137e3c7a4f01823511875f`: after following a fresh
invitation fragment in the same already open document, joining stayed hidden
and the fragment stayed in the URL until a manual reload. Previous access and
transcript stayed cleared. The browser used explicitly synthetic loopback HTTP
responses, no HA/provider/owner credentials or playback effect.

A `hashchange` transition now discards the original temporary UI/grant scope and
performs a full reload. The existing bootstrap then validates and erases the
fresh fragment before requesting anything; joining still requires an explicit
click. An invalid invitation stays closed. Pending old callbacks cannot migrate
into the new document. No backend, actor, guest wire, queue, model, privacy,
publication or localization contract is changed. Only maintained `guest.js`
and its builder-generated `vibecast_guest.html` change in the product.

## Evidence and boundaries

The expanded source DOM/HTTP regression fails on the delivered code and passes
after the repair. All five original checks remain; two new checks cover active
scope disposal/reload with no automatic POST and malformed admission staying
closed. The maintained renderer/build tests pass. Actual browser retest verifies
five outcomes, including a distinct declared fixture guest only after a new
explicit join. See `ha-guest-invitation-browser-receipt-20261123.json`.

All54 actual isolated HA SDK regressions were executed again on the same full
343-file candidate manifest. Fresh raw execution receipts, full before/after
source equality and 45 current inherited proof bindings replace no historical
receipt; prior source/publication proof remains byte-preserved. See
`ha-guest-invitation-qualification-20261123.json`. Model/Spotify/hardware inputs
in those HA probes are declared fixtures. Browser proof is distinct from the
HA SDK probe and neither proves real provider, physical satellite, installed
receiver/native or editorial acceptance.

## Admission and delivery

The owner replied “ga verder” to the concrete bounded workspace-exception
request: repair/tests/review PR while retaining
`codex/ha-native-shared-participation-20261123` at
`bf0494f6d5756b1756c526c46d04a9631e6b81b3`. This exception changes only the
branch-retention readiness prerequisite for this repair; it grants no deletion,
merge, internal publication, installation, deployment or paid-provider run.
Fresh remote main, clean starting tree, no competing Core PR/writer and host
MATCH were checked before the new sole branch
`codex/ha-guest-invitation-repair-20261123` began. Original checkouts remain
untouched. Canonical acceptance owners/nodes stay open and unchanged.

Full root regression/static/bootstrap/roadmap results are recorded in the
review PR. Current source remains local/unmerged until that PR's own checks,
review and separate owner merge decision. A later Finalization remains separate.
