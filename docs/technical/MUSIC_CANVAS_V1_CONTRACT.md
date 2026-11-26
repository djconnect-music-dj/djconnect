# Music Canvas v1 implementation contract

Product authority: [MUSIC_CANVAS_V1](../product/MUSIC_CANVAS_V1.md). Assignment
`DJC-MUSIC-CANVAS-V1-20261115`. This additive contract is version 1. It does
not change the six-axis settings3 contract, playback, VibeScape, or VibeCast.

## Ownership and reuse

| Component | Decision |
| --- | --- |
| Profile binding | REUSE loaded paired-device authorization, Profile resolver, privacy and binding generation |
| Durable state | ADAPT canonical PersistenceService with forward migration; Profile-keyed Canvas preferences and installation-owned device registry |
| Session | REUSE SessionRuntimeManager.current_active and accepted playback observations; no second session owner |
| Model credentials | REUSE HA's explicitly configured preferred AI Task image entity; never copy credentials or silently select another provider |
| Samsung | NEW bounded samsungtvws adapter, HA shared SSDP discovery, independent DJConnect token; no HACS dependency |
| SwitchBot | ADAPT existing switchbot_cloud.upload_art_frame_image with HA registry device_id and image_url |
| Composition | NEW executor-side image compositor, native target ratio, deterministic matte, no UI/text overlays |
| Apple | ADAPT existing paired transport, session menu and shared SwiftUI controls; no local preference authority |
| Legacy | No existing Canvas implementation to retire; AmbientView is not introduced |

Samsung discovery reads the HA SSDP cache for MediaRenderer and the Samsung TV
discovery targets used by HA's `samsungtv` integration. A Samsung manufacturer,
device identifier and description host are required. When one host advertises
multiple descriptions at once, MediaRenderer preserves the existing Canvas
identifier. An advertisement establishes discovery only. Art API pairing and
display readback remain separate, and pairing credentials are never moved
between identifiers based on a network address.

When multicast is unavailable, a loaded Home Assistant Samsung TV entry
with a configured IP address and TV UDN also supplies discovery. Prefer the
SSDP identity where present. The fallback reads the configured address and
UDN only, and opens no connection during discovery. DJConnect still pairs
independently with the Art API before the screen can become ready.

An authenticated, active HA administrator can explicitly pair an already
discovered and registered Samsung TV using `djconnect.music_canvas_samsung_setup`
in HA. The action needs the HA device registry selection and any unknown
screen width, height and orientation. It uses the same bounded Art pairing
operation as native setup. It rechecks both HA administrator and exact registry
identity through the physical effect and commit. It changes no Profile mapping
or selection. The administrator must approve the independent Music Canvas
connection on the TV when its firmware presents a prompt.

Some Samsung Art endpoints do not issue an Art token. The explicit HA action
can register that endpoint after the TV confirms Art Mode and returns current
art over TLS. Core records the exact loaded Samsung entry and TLS peer digest.
Later device effects require that entry, stable TV identity, address and peer
certificate to match. A replaced endpoint requires another explicit setup.
This route uses only the Art channel and does not request remote-control access.

## Native wire

All native routes are POST under `/api/djconnect/v1/music_canvas/`, use the
existing paired bearer/device identity and transport policy, reject unknown
fields and return private no-store responses. Every request has
`contract_version:1,device_id,client_type`; no caller-supplied Profile ID.

* `read`: returns opaque binding, authoritative revision/preferences, target
  descriptors, per-target observed state, generation availability, and management
  permission. Reading/opening/preview never triggers generation or discovery scans.
  A target with an authorized preview can include an opaque `preview_revision`
  that changes when its committed JPEG changes. Clients can refetch the private
  preview when that revision changes while the settings page is open.
* `update`: binding, operation_id (UUID), expected_revision, patch. Accepted
  writes atomically persist preferences plus a bounded original-operation receipt.
  Conflict is 409; unknown transmission uses `operation`, never execute replay.
* `operation`: binding and original operation_id; receipts expire after 24h.
* `setup`: binding, operation_id, target_id and only missing screen-profile fields;
  deliberate Samsung pairing is explicit. Stable registry identity is not an IP.
* `forget`: binding, operation_id, target_id, cleanup_remote, allow_remaining_art.
  Requires actual linked HA-administrator authority, checked again at commit and
  effects. Ordinary selection is Profile-local; forgetting is installation-wide.
* `preview`: target_id. Authenticated bytes for a currently selected target only;
  no external source/token URLs are exposed to the client.

Preferences: enabled=false, selected_targets=[], composition=central,
matte=off, cadence=1800; composition central/free/full, matte off/matching/contrast,
cadence track/900/1800/3600 are the Profile defaults.
The v1 preference `presentation_overrides` stores `matte` and
`show_track_title` and optionally `composition` and `cadence` for each configured
screen ID. The read response advertises `per_screen_composition_and_cadence`
for clients that can edit the additional fields. A screen without an entry
inherits the previous Profile-wide values for Samsung and uses matte off and
title false for SwitchBot. Overrides remain when a screen is deselected and are
removed when its registration is forgotten. Core adds the confirmed playback
title to the rendered artwork only
when enabled. With a matte it adjusts the dominant artwork color for contrast
and centers the title in the bottom matte band. Without a matte it chooses
white-on-black or black-on-white outlined text based on the artwork immediately
behind the title. Changing the toggle
or matte setting can recompose the current Profile's cached source for that
screen without a new provider request.
If a screen has no explicit interval, Core uses an existing selected-screen
`cadence_overrides` entry and then the legacy shared `cadence` value.
Screen dimensions and orientation carry provenance; unknown values remain unknown.

## Runtime and safety

Core owns a single lifecycle scheduler. One model call may run at once, with
a conservative installation budget of 48 attempts per rolling hour. An unknown
provider outcome consumes its attempt. SwitchBot keeps at most two outstanding
file leases per target and 32 installation-wide; backpressure preserves the last
good work and coalesces later music instead of generating discarded images. First confirmed stable playing track is
eligible immediately after debounce, then cadence applies. An accepted Session
mood revision wakes the scheduler and triggers a fresh generation for every
eligible target, independently of its cadence or current track. The attempt
starts a new cadence window. Superseded work cannot publish after acceptance.
Paused/ended/stale observations do not generate. No backlog catchup. One bounded generation runs at
a time; equal target profiles share bytes. Target arbitration reserves a physical
device for one active Profile; a competing Profile receives busy, never last-wins.
Every await is fenced against original Profile, Session, revision and device
epoch. Disable/end/forget cancel future work and prohibit late delivery.

Model input is bounded untrusted inspiration data, never instructions. V1 starts
with permitted textual title/context; no Spotify artwork/lyrics attachment or
image-caption laundering. No fictitious factual claim. The preferred HA image
provider remains an explicit setup dependency. No paid model calls are made by
development tests. Private/shared privacy modes that suppress personal persistence
suspend new Canvas output; Profile deletion purges preferences, receipts and private
previews through the existing Profile lifecycle. Hardware pairing remains
installation-owned and is not deleted with an unrelated Profile.

Samsung upload and select are separate. Only an already-on Art Mode target may
receive an upload; qualification of no-wake behavior is a hardware admission,
not inferred from show=false. Manual artwork takeover is persisted and stops delivery. Resume requires explicit HA-admin setup/reconnect; a background tick, restart or new track cannot resume it. Setup retains the existing token and screen values and clears only this takeover fence. Interval jobs freeze their chosen track but retain all Session/Profile/settings/device authority checks; per-track jobs also fence the original occurrence. Repeated cancellation drains a shielded physical executor before releasing its effect slot. Track owned content
IDs durably, never delete by prefix. Unknown upload outcome is not automatically
retried. Local token removal does not claim TV-side revocation.

SwitchBot uses only loaded native Cloud integration devices and the real upload
service schema. A temporary file-scoped HTTPS asset lease must be explicitly
configured and reachable by the cloud. The asset route requires actual HTTPS
(or HA's explicitly trusted HTTPS proxy scheme); unqualified plaintext ingress
is rejected. Reverse-proxy/HA configuration is an operator prerequisite, never
inferred from a URL or untrusted forwarded headers; no automatic public endpoint, HA bearer,
www directory or Base64 fallback. Status is delivered_unknown until independent
display evidence exists. A submitted cloud job cannot be recalled by forgetting.

Keep only current previews and in-flight shared assets, bounded leases/retry,
reference-aware cleanup and compact provenance/remote ownership. No gallery.
When two Samsung uploads are recorded and a selection acknowledgement was
missed, Core can recover capacity after the paired TV verifies the newest
owned upload is on screen. It retires only the older Core-owned upload.
Remote cleanup defaults off. Failed cleanup retains pairing until the user
explicitly chooses allow_remaining_art; then remove local registration, selected
references and leases, honestly reporting remaining art.

## Qualification boundary

Source tests, real HA contract tests, real-provider generation, Samsung firmware
no-wake/readback, portrait SwitchBot, native iPhone/iPad/Mac and joint end-to-end
acceptance are separate results. Hardware not exercised remains NOT_RUN.
No install, deployment, account creation or new provider expense is authorized
by this source increment.

Verified references: installed HA2026.11.1 ai_task.task and
switchbot_cloud.services; samsungtvws3.0.7 Art API signatures. Public upstream:
https://www.home-assistant.io/integrations/ai_task/
https://www.home-assistant.io/actions/switchbot_cloud.upload_art_frame_image/
https://github.com/xchwarze/samsung-tv-ws-api

Golden Scenario relationship: Canvas does not alter Planner/Moment decisions or playback. Existing Session lifecycle, pairing, Profile settings, artwork and Ask DJ Golden regressions remain required. Its new actual-HA probe uses declared synthetic image/hardware boundaries and cannot close real-provider or physical acceptance.
