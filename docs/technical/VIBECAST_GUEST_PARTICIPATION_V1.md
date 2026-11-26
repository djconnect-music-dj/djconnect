# Core shared HA and VibeCast participation v1

Status: selected implementation in progress, not merged/installed/qualified. Parent owner decisions: Core #1532 stage3 and #1174. Base bbf56161c4b920ce43f701d3e951e721bba9d6df. Reuse WEB::CHAT/REQUEST/EFFECT-POLICY/ENQUEUE/SHARED; no new Session or parallel recommendation/request engine.

## Real authority, default off

The existing SessionRuntimeManager and DisplayAdmissionState own the live share. A genuinely paired, currently admitted owner or the distinct HA installation-admin OptionsFlow role can configure participation on that actual share. HA administration does not become paired B owner or Profile personal-read authority. Guest authority is subordinate to the original share, Session, owner/source fence, origin, policy revision and a bounded lease. A browser invitation is single-use, short-lived, independent of the TV/owner token. Redemption issues its own CSPRNG bearer once; lost issuance never mints a second grant. Guest bearer secrets stay memory-only in the client; the server retains their hashes only. Owner/display/guest bearers never enter URLs, logs, public projections or durable Profile storage. A single-use invitation uses only the deliberate guest-page URL fragment, erased before admission requests. The server may retain that one invitation in RAM for its original 120-second QR lifetime; redemption/rotation/expiry removes it. It is not a reusable guest or owner bearer.

A real HA registry endpoint can be admitted as a shared room participant through explicit host policy. It is not the personal owner and is not a recognized human speaker. Endpoint, guest principal, owner Profile/source, output, share and display retain separate identities. Conflicting personal/shared endpoint admission fails closed. Speech cannot promote itself to owner by naming a person or confirming an old owner action. Room budgets are per endpoint and Session, not invented per-human fairness.

Share close/end, owner/source withdrawal, origin change, lease expiry and policy revocation invalidate guest context and pending work. An already dispatched queue effect has no fabricated rollback. No guest registration persists across Runtime restart or imports. Rotating invitations invalidates new admission, without silently terminating already admitted guests; changing/removing host participation authority does terminate its admitted guests.

## One conversation and request owner

Guest turns enter the same ask_dj.service application boundary with a sealed in-process actor admission, separate bounded operational scope and no durable archive. Guest context uses only qualified shared current music/Moments and effective Session Persona/Mood. Profile defaults, Music DNA, private history, private images, internal Forecast slots and owner resultsets are unavailable at reads and effect dispatch, not merely hidden by prompting. Browser and HA use the same Core request IDs, exact recording choices, policy decisions and status projection.

Requests are proposals: received / clarification / identified / considering / planned / queue-confirmed / effect-uncertain / actually-playing / rejected or expired remain distinct. Host policy defaults closed; enabling public information does not enable requests. Any bounded auto-enqueue mode needs explicit host selection and current source/output/capacity checks. Exact URI/version selection uses existing catalog choices; no genre recommender or parallel voice planner. Uncertain enqueue is not retried blindly. Only matching independently observed playback can claim playing, and requests do not train host DNA or interrupt current music as an owner play-now action.

## Permitted presentation

Explicit show/recall/return targets the original eligible shared Moment on the actual admitted display. It does not publish private conversation, regrant owner image/audio rights, select another concert or manufacture delivery. Public text/media deadlines and source revocation continue to apply through the existing shared projection and renderer. Default view returns without playback or microphone effects. A personal voice endpoint alone grants no presentation right.

## Delivery and evidence

This document introduces the producer contract to be implemented, not pre-existing live API paths. Closed versioned request shapes, origin handling and capabilities must accompany the actual Core endpoints and generated shared consumer. No API-rendezvous, paid model, deployment or physical-device claim is inferred. Real isolated HA tests must create genuine source/share/guest admissions and exercise both browser and HA entrypoints; unit fixtures alone do not prove physical speech, provider behavior or installed shared UI. Keep guest/private leakage, stale confirmation, withdrawal, retry and uncertain-effect regressions explicit.

## Selected shared image purpose

Shared focus may use an original licensed Live-impressie photo only through a separate display-purpose read. It must not reuse the Profile-only Session image URL, its owner token, personal-read grant or native image registry. The genuine current display grant, host-enabled screen-focus policy, original live guest focus revision, exact still-public Moment and original sealed event/photo/reference are all required at preparation and final byte release. The existing original-photo refetch validates exact source metadata, license and pixel revision; it must never search for another event, select a replacement image or regenerate pixels. At most four bounded 2 MiB reads are in flight; no durable pixels or image bearer is introduced. Withdrawal and source expiry clear the prepared image. A text-only shared Moment stays text-only when no original shared photo is eligible.

HA's existing administrator-protected OptionsFlow supplies installation-admin participation consent as a distinct internal role. It uses the actual loaded config entry and actual existing share/source/Session, never a fabricated paired-device tuple or the share owner's bearer. It can configure temporary shared-room endpoints and review requests; it cannot approve B displays or obtain a Profile personal-read grant. The paired host API remains a separate real-owner route. This is implementation scope, not installed or physical acceptance.

## Wire and operational bounds

`/api/djconnect/v1/participation/` is a closed version1 HTTPS/same-origin namespace. Every POST has `contract_version: 1`; owner actions use the existing real paired `identity`, `session_id`, `share_id` and paired Authorization header. Guest actions use the separately redeemed `guest_id`, `issuer_epoch` and `Bearer djcg_…`. Display-only actions use their original `display_id`, `issuer_epoch` and `Bearer djcd_…`. Tokens are not interchangeable; no query/cookie/CORS authority exists.

- Owner: `owner/context`, `owner/configure`, `owner/invite`, `owner/remove`, `owner/voice`, `owner/unbind-voice`, `owner/requests`, `owner/decide`.
- Guest admission: `redeem` accepts the single-use invitation triple carried by the TV QR. Display invitation responses provide only the QR and its invitation metadata. `renew` uses sequenced renewal, followed by `leave` and safe `context` as needed.
- One conversation: `ask` with text/client message/thread/language and optional original shared Moment ID. `request` uses that same application owner and its frozen `choice_action` IDs; it exposes proposals only. `request/status`, `focus` and `return` retain the same original guest/share scope.
- Read-only display extension: `display/invitation`, `display/focus`, `display/return`, `display/focus-photo`. The existing B snapshot contract is unchanged. No owner command or microphone permission is added to the TV.

The historical browser guest artifact is available for fixture verification and its route is retired in Home Assistant. Guest state/transcript/bearer stay in RAM. Invitation fragments are removed before admission or any external request. A lost request response retries the exact original body/client ID; a lost grant issuance needs a new one-time invitation. No analytics, cookies, third-party assets or private image token are introduced.

Limits are 64 temporary guests, 32 shared HA endpoints, 120-second invitation, 60-second guest lease, 30-second focus, 12 new Core turns per guest/48 per share per minute, and 8 actual model reservations per guest/32 per share per minute. The existing per-turn/model-input caps remain. Request policy allows1–10 pending requests per participant (default3), with a share cap12, bounded128 retained request receipts and256 client bindings in the current Runtime. Unexpired dedup proof is never evicted to admit another queue effect. A withdrawn/expired participant expires its unstarted proposal; an already dispatched effect is not rolled back. Policy/endpoint retries preserve the original principal when unchanged. HA's real Context ULID timestamp is used only as a negative fence against input predating endpoint admission; it is not speaker recognition or physical capture proof. Missing/invalid producer context fails shared admission.

`enqueue_track` is a distinct typed capability; `queue` remains a read. Spotify Direct supports this single exact recording operation; unsupported backends are not silently substituted. Dispatch uses the existing durable OperationJournal, explicit original current provider device ID, the canonical playback-identity projection, original recording and current host-policy admission. It sends at most once. Current-output changes yield uncertainty rather than claiming queue placement or targeting another speaker. A subsequent read may confirm that exact recording currently in the original queue; no new atomic global-queue proof requirement is imposed. Only the independent same-Session playback projection supports `actually_playing`. Guest requests/transcript do not write host preferences, history or DNA. Any existing genuine playback-learning policy remains its own independently consented source.

The existing Live-impressie producer is owner-only. This increment does not promote its private publications. The conditional image-purpose boundary requires a separately eligible shared/public original Moment; its source/audience, licensing, hash and late-withdrawal behavior are tested with a declared public-audience source vector. Real public event-photo/physical screen acceptance is not claimed by the basic guest/request HA test.


## Flow and VibeScape display controls

The paired Apple remote and the currently admitted display can choose Flow or
VibeScape for their active share. The browser control uses a same-origin
display-grant action with only the display ID, issuer epoch and selected mode.
It cannot set dynamics, change guest policy, alter playback or target a
different share. These choices are ephemeral and available with Live guest
participation off. The display refresh returns the authoritative mode and a
share-local presentation revision so a late response cannot restore an older
choice. The Apple remote reads that same mode while its controls are visible.
