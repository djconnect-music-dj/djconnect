# Native VibeCast guests and presentation refinements v1

Status: owner-selected implementation; not delivered or deployed.
Base: `20b9caa92dbcaec9faf3deda8166022f684ba4f4`.
Extends `docs/technical/VIBECAST_GUEST_PARTICIPATION_V1.md`; no parallel
guest issuer, conversation engine, Profile or playback owner is introduced.

## Selected scope and responsibility

Core owns public projections, source validity, shared renderer, guest admission,
requests, effect policy and observation. Apple owns native join, temporary client
presentation and controls. Receiver owns byte-identical renderer adoption and a
content-free native-open/install landing. Central API is not a rich guest relay.
All changed behavior requires golden and end-to-end regression coverage.

Guest v1 is native in the DJConnect app, text-only. The owner explicitly allows
guest Ask DJ model usage. No new responsive guest web application is selected.
Existing historical web guest support is not silently removed by this increment.
Core's existing host policy, request budgets and effect guards remain in force.

The guest-enabled function is named **VibeCast Live**. At share start the host
chooses a Live toggle, default off. Live enables guest admission and the tv QR;
off hides the QR and denies guest admission. The ordinary tv Session Flow and
its substantive DJ content are identical with Live on or off. Live is not a
second Session or content generator. On completion no shared Live data persists:
guest transcripts, request-to-participant bindings, reactions and public guest
snapshots are RAM-only and cleared by their owning runtime/client. Do not add
Live archives or retention in logs, analytics, crash reports or personal history.

## Native invitation link (selected producer/consumer contract)

The public QR points to `https://vibecast.tv/join` with a URL-encoded fragment:

`v=1&ha_url=<selected HTTPS origin>&issuer_epoch=<epoch>&invitation_id=<id>&invitation_secret=<one-time secret>`

The landing transfers that same fragment to `djconnect://join#...` only after an
explicit Open app action. The native app requires explicit Join confirmation
before redeeming. The fragment contains an existing one-time invitation,
never a guest/display/owner bearer. No extra origin authority is invented.
Consumers accept only the closed field set, v1, bounded identifiers and a plain
HTTPS origin without userinfo, path beyond `/`, query or fragment. They erase
the browser fragment before external navigation and keep the locator RAM-only.
Core's redeemed response, not untrusted link labels, owns session identity.
The exact five fields are v, ha_url, issuer_epoch, invitation_id and
invitation_secret; reject duplicates, unknown fields and malformed encoding.
The fragment is at most 2048 characters, ha_url at most 1024. Existing producer
identifiers are base64url ASCII `[A-Za-z0-9_-]`: epoch43, invitation_id32,
invitation_secret43 characters. No secret prefix is added.

The native scanner accepts the same canonical public QR URL directly. On macOS,
the guest can instead type the host and 12-character code shown next to the Live
QR and explicitly confirm Join. The code is an alternate representation of the
same one-time invitation. Core issues it from 60 random bits, applies the same
origin and attempt budget, and consumes both representations together. The app
posts it directly to that HTTPS installation via `participation/redeem-code`.

Reuse the current 120-second invitation lifetime. QR changes subtly every two
minutes; ordinary snapshots do not rotate it. Redemption remains single-use,
so a consumed invitation may need replacement for the next guest. Invite rotation
does not terminate already admitted guests. The independent 60-second guest
lease is renewed using the existing sequence contract. Leave/revocation/expiry
clears guest state. A disconnected guest must not retain a durable transcript.

The App Store fallback is `https://apps.apple.com/app/id6832635823`. TestFlight
needs a real applicable invitation; the TestFlight installer itself is not that
invitation. Installation does not preserve a spent/expired invitation: rescan
the tv QR. Universal Links/AASA are added only with the actual signed team/bundle
tuple. Scheme fallback is not claimed as Universal Link acceptance.

## Native guest capabilities and public presentation

Reuse `/api/djconnect/v1/participation/` redeem/renew/leave/context/ask/request/
request/status. Add only scoped missing reads/events after their exact wire is
implemented and tested. Native guests see public shared flow, current music,
Horizon and Vibescape; they may propose songs and ask music questions. They
cannot execute playback, change output/volume, alter Session settings, access
host private content, Music DNA, Discover or For you. Queue, Playlists and the
standalone Ask DJ screen remain empty. Guest contextual Help lists only actually
available guest actions. Track Insight is withheld for v1 pending a separate
guest-safe decision. No guest TTS/STT. Host settings govern presentation;
guest-adjustable Vibescape dynamics defaults to its own local view.

Core keeps temporary participant-to-request ownership for private status and
personal feedback. The shared flow exposes anonymous contributions, never a
guest name, Profile, private transcript or public stable participant identifier.
Requests remain proposals under existing host review/auto-queue policy. Only
independent matching playback observation means actually playing. The requesting
guest receives a deduplicated personal iPhone update for its own request; queue
confirmation alone must not trigger it. No new APNs grant is implied.

The tv exposes a count of currently admitted, unexpired guests, not scans or
pending invitations. Emotions attach to the original current playback item,
not contributions; five native buttons and an emoji-only chat submission share
one bounded, guest-authorized event path. Core can handle emoji-only input
without a model call. Do not interpret arbitrary text as a playback action.
Receivers animate only admitted, unexpired events for the matching playback;
repeated snapshots cannot replay them. Reactions never train Music DNA.

## Presentation and share refinements

Create shares default to 14400 seconds. Preserve the existing accepted lifetime
range 120..28800 seconds and compatibility with explicit 7200-second requests.
Apple shows remaining time from the actual share expiry. A share's selected
language comes from the creating app; it must not mutate host Profile defaults.

Horizon shows the actual forward-looking text directly, without subheadings,
the redundant current-track paragraph or the change-warning sentence. Identical
valid content survives status refresh without rebuilding DOM or blanking. Source
expiry/withdrawal still clears it. All flow items retain a large readable font.
The lower edge transitions smoothly, rather than clipping behind the footer.
Artwork stays stable for an unchanged qualified reference as its authorized
deadline refreshes; withdrawal or changed track must not show stale pixels.
Track artwork may breathe subtly with Reduce Motion and hidden-state respect.
Spotify source presentation uses the existing logo and correct accessible link.

Native Up next is a temporary Horizon DJ-moment near track end with next-track
art/title and short backend-authored text; it does not replace announcements.
Its producer, timing and public/source contract must be implemented before any
consumer invents that content. The persistent small DJ avatar and brief avatar
on real session changes use existing confirmed session presentation.

## Validation and delivery

Golden and E2E cover renderer refresh/expiry/withdrawal, both host adapters,
QR rotation/strict fragment parsing, guest join/leave/data clearance, two-guest
isolation, effect denial, anonymous public flow, own-request observation feedback,
guest Help, track-bound reactions and reduced motion. Live provider, physical
Cast/iPhone, installed Mac and actual deployment outcomes remain separate from
software fixture evidence. Owner authorizes HA-dev/Mac-mini installation,
Spotify Schuur operation, and receiver/API production deployment, subject to the
normal exact-artifact qualification and rollback requirements.

## Owner refinement: general DJ disclaimer placement

The owner explicitly moves the generic “Je DJ kan zich vergissen” disclaimer
from the ordinary Apple Ask DJ and Session surfaces into contextual Help. Do not
show the permanent composer warning. This supersedes earlier placement guidance
in the Music Origin design; source attribution and specific factual uncertainty
remain part of their original content contracts. Update all five UI languages
and the layout/help regressions.
# Guest artwork read purpose

The guest context may include optional `artwork` on `playback` and on an already
qualified public `shared_flow` item. Each descriptor contains only `reference`
(64 lowercase hex), `item_id` and the original source `expires_at`. The native
client additionally respects its original guest/share lease. No provider image
URL, personal image grant, display bearer or fabricated display identity is
exported. A reference is scoped to the original issuer, guest, participation
generation, share generation, Session, item, prepared asset, original source
expiry and current/flow purpose. A genuinely new admitted source expiry receives
a new guest reference, even if identical decoded pixels keep the shared display
reference stable. It cannot be transferred to another guest or promoted to current art.

`POST /api/djconnect/v1/participation/artwork` accepts exactly
`{contract_version:1, issuer_epoch, guest_id, reference}` with the existing
`Bearer djcg_…` guest credential. It returns prepared JPEG/PNG/WebP bytes only,
up to 256000 bytes, with the ordinary no-store/no-referrer headers. It performs
no provider request, refresh, image preparation or new source admission. A
current-source/share/guest check immediately precedes body release. The source
must have admitted the same original share when pixels were prepared; flow art
also requires continued membership in the current qualified public flow.
Reads share the existing bounded media budget with a separate guest accounting
key. Leaving, Live-off, source withdrawal, item changes, expiry or share end
invalidates pending reads. A missing optional descriptor is rendered without
art; a client never substitutes another track's image.

# Public observed playback

The ordinary shared display and native guest context additionally expose bounded
`observed_playback` entries captured only from an accepted original playing
sample while that share is active. Each has `entry_id`, `playback_item_id`,
`title`, `artist`, `album`, `source_url` (public Spotify track only), `observed_at`
and `expires_at`, with optional separately qualified prepared artwork. These are
metadata observations, not DJ Moments, full-listen claims or guest identities.
They are identical with Live on or off. They live only inside the original
in-memory share, retain the original provider/account source witness, and expire
at the earlier share end or thirty minutes from their original observation.
Reads do not create entries, renew their deadlines or read personal history.
Repeated observations of the same recording occurrence do not add entries.
Share end clears this memory before pending responses can release it.

# Shared presentation dynamics

`owner/presentation` retains required `mode` and may include `dynamics`, a finite
number in [0,1] (booleans are invalid). The original paired host can copy its
current native presentation slider into the active share; the acknowledged
value is returned as `view.dynamics` and projected to the TV and joined guests.
Omitting the field preserves the previous acknowledged value, initially 0.5.
This is temporary share presentation state, not a Profile or musical preference.
Guest-local dynamics changes remain local and never call this owner route.

## Native legacy Google Cast owner lifecycle — 24 November 2026

The selected iOS sender uses the real Google Cast SDK and the existing
`POST /session/broadcast/token` owner-read route. At an explicit connect action,
capture the actual paired origin/install/device/token, authorized Profile and
active Session once. Validate that same original capture around the one token
read and the original SDK launch/channel handoff. A device name, Bonjour match,
old status DTO or historical receiver app ID alone is no owned connection.

Scene background or UI-history suspension stops discovery/status observation
and fences their callbacks, but sends no Cast-stop for an already explicitly
handed-off readonly TV view. Retain only its exact owned SDK session/channel
as an optional withdrawal handle. Do not refresh its status lease, request a
new token or send another handoff while suspended. Foreground status remains
unconfirmed until fresh original owner validation; a new handoff requires an
explicit connect intent and its own single current token read. No old15-second
status observation is revived by a timer or reconnection.

Explicit Stop and actual pairing, origin, token, Profile or Session withdrawal
may revoke only that original owned handoff. A late launch callback cannot stop
an unrelated successor or a pre-existing session. The real receiver App ID and
current published registration remain separately qualified inputs.

This legacy `view_broadcast` token conveys no A/B display/share admission,
four-hour Live share, guest QR or owner-control grant. Current native guest and
Live display content continue to use their existing independently owned share
contracts. A future legacy-CAF/Live bridge needs an explicit Core projection
and original share binding; this lifecycle selection does not manufacture it.
