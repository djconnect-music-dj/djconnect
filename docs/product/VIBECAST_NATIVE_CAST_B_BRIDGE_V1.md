# Native Google Cast B-display bridge v1

Status: implementation contract for this isolated increment; not a deployed or
jointly accepted capability. The existing B same-origin routes and shell/CSP,
legacy view_broadcast token, vibecast.tv rendezvous and guest principals retain
their existing boundaries. Cast SDK device/session/AppID/name are data, never
paired-owner authority. Core remains sole owner of actual B claims and grants.

## Exact HTTP and custody contract

All routes are TLS-only, no query/cookie credentials, duplicate-key JSON denied,
4096-byte request bound. `contract_version` is strict integer1. Relative expiry
and original request clocks are independent upper bounds, never refreshed by
parsing/retries. No secrets in logs, URLs, persistence or artifacts.

Native bootstrap DATA decoding caps the operation by the minimum of the
original request monotonic instant plus at-most30seconds and the original
absolute expiry. It does not additionally require the absolute timestamp to
fall within30seconds of the client's response wall sample: mint/transit timing
and independent wall samples do not extend the original monotonic cap. Wrong
origin/epoch/Session, expiry, clock rollback and the original request deadline
still reject. This is not native clock qualification or display authority.

Directed claim retransmissions report a shrinking remaining duration. Native
claim DATA keeps the minimum of the original handoff plus120seconds, receipt
instant plus that remaining duration, original absolute expiry and any earlier
accepted claim pin. A retransmission cannot renew that original pin. Its
remaining duration must not be subtracted twice by anchoring it back at the
original handoff. Actual Core claim validity and explicit owner approval remain
independent requirements.

`POST /api/djconnect/v1/cast/owner/bootstrap` uses normal paired-device Bearer.
Body: `{contract_version,identity:{device_id,client_type},session_id}` only.
The genuine owner/current Session, selected external HA origin and issuer epoch
are captured. It grants only one receiver claim creation, no display/share/Live.
Response: `{success,contract_version,bootstrap_token,bootstrap_expires_in,
bootstrap_expires_at,ha_origin,receiver_origin,issuer_epoch,session_id}`.
`receiver_origin` is exactly `https://receiver.djconnect.dev`; `ha_origin` is the
selected HTTPS HA origin. Lifetime is at most30seconds. Token is RAM-only,
hash-indexed, opaque `djccb_`+43base64url. Never reuse after uncertain response.

`POST /api/djconnect/v1/cast/claim`: actual exact receiver Origin and bootstrap
Bearer; body `{contract_version,browser_nonce}` only (nonce43base64url).
Successful real `DisplayAdmissionState.create_claim` consumes bootstrap once.
Response is the existing B claim wire: issuer_epoch,claim_id,claim_secret,code,
browser_generation,expires_in,expires_at with success/contract_version.
Claim secret and nonce stay receiver RAM. Core retains an association to the
real original owner/claim; SDK metadata cannot create that association.

Receiver sends only code/claim_id/browser_generation/issuer_epoch/original expiry
and current handoff_id back to the original SDK sender/channel. Apple calls
existing paired `display/owner/resolve` with code, joins all returned IDs, then
existing `display/owner/approve` after explicit existing4h/Live/language/share
choice. Connect/SDK readiness alone never implies this consent. The approval
must match the original real bootstrap owner binding. Existing shares cannot be
extended by this flow; same current one-screen capacity remains.

`POST /api/djconnect/v1/cast/{collect,cancel}` uses the existing B browser body:
contract_version,issuer_epoch,claim_id,claim_secret,browser_generation,browser_nonce.
No bootstrap replay or fake Origin. Collect calls the real B collect factory;
its djcd_ grant/display/share/session/lease/capabilities are unchanged.

`POST /api/djconnect/v1/cast/{renew,leave,snapshot,artwork}` uses real associated
B grant Bearer and existing bodies (epoch/display_id, plus renew_sequence or
reference as applicable). No existing non-Cast grant is silently adopted.
`POST /api/djconnect/v1/cast/participation/display/{invitation,focus,return,focus-photo,presentation}`
uses that same real display grant and existing display-only shapes (epoch,
display_id, plus focus_revision for focus-photo or mode for presentation).
Presentation selects Flow or VibeScape for the authorized active share only.
The associated display grant cannot change dynamics or playback. The mode
revision prevents a stale response from restoring an older view.
No guest/owner ask, request,
configure or other authority is exposed.

`GET /api/djconnect/v1/cast/live` checks actual receiver Origin then uses the
existing real B hub/_Connection. First WS frame is unchanged:
`{type:"authenticate",contract_version:1,grant_token,issuer_epoch,display_id,connection_nonce}`.
No grant in URL. Selected HA issuer/source origin stays distinct from browser
Origin. Existing lease renewal requires the actual current live writer.

Only the NEW Cast browser routes receive exact-origin CORS/OPTIONS (POST,
Content-Type and Authorization, no credentials/wildcards/redirects). Owner bootstrap
has no browser CORS. Existing /display and /participation origin policy and B
shell framing/CSP remain unchanged. Source capability advertisement requires all
HTTP, Live and display-participation adapters actually mounted; until then no
positive capability is advertised.

## SDK and renderer protocol

Same owned custom channel; new closed kind `vibecast_display_bootstrap`,version1,
with handoff_id,ha_origin,bootstrap_token,expires_in. Receiver only accepts the
original selected senderId and handoff operation; replies are directed, never
broadcast. Claim lookup metadata kind is `vibecast_display_claim`,version1,
handoff_id,issuer_epoch,claim_id,browser_generation,code,expires_in,expires_at.
No claim_secret/browser_nonce/grant/owner credential is echoed to the app.

Use the existing Core B renderer with transport injection; no iframe and no
second product renderer. Receiver deployment must adopt the exact supplying Core
bundle. Presenting requires actual matching B snapshot and renderer presentation,
not merely approval, SDK READY or legacy snapshot. Original connection_generation,
issuer/display/share/session identities fence statuses. Legacy vibecast_handoff
remains view_broadcast-only with no fallback upgrade to B.

## Revocation and limits

Real owner/Profile/Session/origin/epoch withdrawal invalidates pending bootstrap,
claims and real B delivery, with no new expiry. Bootstrap registry is bounded
(32global,2pending per owner); claim and display state keep their existing limits.
No durable second principal, artificial permission tuple or fabricated owner.
One-use response loss remains uncertain/fail-closed. Sender observation loss is
not an implicit owner Stop. Explicit Stop uses actual B owner revoke/real grant
leave. No unrelated SDK session termination or audio/media playback authority.

Joint installed/native/receiver/TV qualification remains required separately.

## Exact directed status / Stop wire

Receiver status is `vibecast_display_status`,version1 with handoff_id, sequence
(strictly increasing per original handoff), state, lease_ms15000 and optional
reason. States: receiver_ready,claim_ready,approved,snapshot_accepted,presenting,
recovering,error,stopped. Actual issuer_epoch,display_id,share_id,share_generation,
session_id appear only after genuine collect; connection_generation only after
a matching genuine B WS frame. presentation (`moment` or `silence`) appears only
in presenting, after shared renderer DOM application. Recovering clears positive
presentation. These are software observations, never physical TV visibility.

A receiver view Stop is `vibecast_display_stop`,version1,handoff_id only. Exact
original sender/channel/handoff correlation is mandatory. It leaves only that
receiver's real display grant; it is not owner share-close or Session-end. Host
owner revoke still uses the ordinary actual receipt. Sender disconnect alone
does not imply owner revocation or implicitly stop a four-hour shared screen.
Visual-only CAF sets disableIdleTimeout=true; Core actual share/lease/owner
deadlines continue to bound viewing. No audio/media load is introduced.

The one immutable Core Cast export declares additive cast_display_versions:[1],
pins display-host.js as an input and embeds that shared B lifecycle before the
CAF adapter. Legacy contract fields and view_broadcast-only handling stay
separate. Receiver imports the complete matching manifest/verifier/bundle, not
edited wwwroot HTML. This version declaration is compatibility metadata, not an
authority grant or installed-port advertisement.

## macOS via Home Assistant

The Mac selects the UUID from the device's Google Cast Bonjour TXT record.
`POST /api/djconnect/v1/cast/owner/launch` is a paired, TLS-only owner action.
The closed request contains `contract_version`, `identity`, `session_id`, and
`receiver_id` (the selected UUID). Core checks active owner/Session and resolves
that exact UUID through LAN discovery. The client cannot supply a network address,
receiver App ID, namespace, or destination URL. In networks where HA cannot
see multicast discovery, PyChromecast also probes the known hosts configured
by the administrator in Home Assistant's Google Cast integration and still
requires a UUID match. Connect only to a video-capable device and launch the
configured VibeCast receiver (App ID 8EA92910).

Core sends one existing B bootstrap over the custom channel after launch.
The receiver creates the standard B claim. Core matches the directed reply to
the handoff and the actual claim created by this bootstrap. The successful
response contains only `issuer_epoch`, `claim_id`, `browser_generation`,
`code` and the standard success and version fields. The Mac joins those IDs
against the paired resolve response, then presents the existing explicit
approval. The API neither grants display access nor confirms physical visibility.
Closing the sender connection leaves an approved B display under Core's
existing share and revoke rules. Uncertain attempts require a new explicit
selection.
