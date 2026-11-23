# HA-native DJ conversation

Owner: Core #1532, `DJC-HA-VOICE-CORE-CONVERGENCE-V1-20261107`.
Implementation selection: owner request of 22 November 2026. Source baseline:
`d987f79f8c281dab3cbcc1dc4bc5981d129f5d23`. Implementation and physical
acceptance are separate; this document does not assert either is complete.

## One application service

HA wake word, capture, STT, continuation and TTS remain HA transport. The native
conversation entity calls `api_handlers.async_handle_ask_dj_message_payload`
in-process, which calls `ask_dj.service.async_exchange`, exactly like Apple.
The legacy `run_text_command(play=True)` entrypoint is retired from this entity.
No self-HTTP, borrowed client credential, parallel prompt stack, recommender,
Session, history store, speech engine or queue is introduced.

## Admission and identity

A registered loaded agent entry is transport authority, not personal owner
authority. Physical `ConversationInput.device_id` must name a real HA registry
device explicitly admitted as a personal voice endpoint in installation-owned
Profile mappings. Existing generic room/device/Profile mappings and HA service
user identity do not confer this privilege. HA administrators configure and
withdraw that consent in the existing integration options. Imported household
data cannot restore personal endpoint trust. Deleting a Profile removes its
endpoint trust rather than transferring it to a replacement Profile.

Unconfigured/shared endpoints fail closed until an actual shared actor and
guest-request policy is admitted by its owning service. They never fall back
to the synthetic conversation-agent device's Profile. Wording cannot grant
personal rights. Full shared living-room delivery additionally requires the
existing #1174 guest policy, exact recording consideration/enqueue receipts and
an independently authorized display projection; a personal endpoint is not a
shortcut for that contract.

HA device, agent, pipeline, conversation, Core operational thread, Profile,
music output and DJ Session retain separate identities. Endpoint/Profile/HA
conversation scope selects a bounded Core thread. HA conversation IDs never
become DJ Session IDs; agent IDs never become pipeline IDs. A track change
does not clear the thread's conversation subject. Profile/consent/entry changes
invalidate in-flight work before effects and before accepted results.

## Conversation, choices and speech

General questions do not create Sessions or playback. Existing contextual
research, Moment/history lookup, language, Mood/Persona, resultsets, pending
confirmation and effect owners remain authoritative. Personal and room
threads do not merge because they share a Profile. Repeating a published
contribution is distinct from proving that it was spoken: no generated answer
is labelled a physical delivery receipt.

Use the one existing Session lifecycle and Voor jou offer; native discussion,
ordinals, output clarification and mix completion must refer to its actual
offer/actions. The iPhone/iPad/Mac card closes only on common confirmed mix
completion. Watch gains no Session start or Voor jou card. Information and
explanations do not replace a queue; explicit collection/mix selection and
owner single-track best-effort preservation retain their common meanings.

Accepted speech is returned once through HA. This ingress requests no extra
Core audio URL or Apple/TV auto-speech. Native continuation follows actual
pending Core input; hardware wake/continuation/barge-in remains separately
qualified. Never mutate global pipeline/provider/voice settings. Self-reference
to any DJConnect ingress agent fails explicitly without alternate-agent retry.
NL/EN/DE/FR/ES use existing language boundaries, with hardware STT/TTS capability
qualified independently.

## Stages and acceptance

1. Foundation: common service, explicit personal endpoint admission, isolated
   threads, topic versus live context, original contribution recall, native
   answer/continuation, truthful availability and recursion prevention.
2. Choose/start: common lifecycle and the same Voor jou resultset, explain,
   select, speaker clarification, once-only completion and cross-client state.
3. Shared living room: explicit host policy, shared actor, existing guest
   request pipeline and permitted read-only VibeCast focus/return. No private
   transcript, Music DNA, owner image grant or full playback rights on TV.

Use owner scenarios V01–V18 in #1532. Unit/contract and actual isolated HA
entity tests establish software behavior; genuine satellite turn taking,
latency/echo, provider editorial quality and shared physical display acceptance
require separately recorded actual runs. No installation, paid-provider run,
public release or deployment is authorized by the implementation selection.

Official API references: [conversation entity](https://contributors.home-assistant.io/core/entities/conversation/)
and [Assist satellite](https://www.home-assistant.io/integrations/assist_satellite/).
Implementation must verify the repository-supported HA version rather than
infer physical support from a stubbed ConversationInput attribute.

## Complete owner requirements

The following requirements preserve the complete owner decision from #1532.
References to the original design-only intake describe that intake's history;
the owner's 22 November implementation request now selects the implementation.
No execution/merge/install claim follows from this recorded specification.

## 1. Product decision

> Praat met jouw DJ over wat je hoort, ontdek samen wat erna komt en laat je vrienden meedoen. Zonder je telefoon te pakken.

The satellite is not a separate DJ product or a collection of music commands. It is the **native Home Assistant voice interface to the same DJConnect Core** used by the personal apps and the authorized VibeCast experience. The user should feel that the DJ on the screen is the DJ they are talking to: context-aware, personal where permitted, responsive, and consistent with the actual Session Mood and Persona.

Four principal experiences:

1. **A continuing music conversation:** ask, listen, follow up, correct, compare and request an action without repeating every artist/track name.
2. **Choose a session together:** voice lifecycle, the same three personal **Voor jou** offers, explanations, genre selection, necessary output clarification, then playback.
3. **Talk and look:** recall or explain the relevant shared DJMoment, Track Insight or qualified Live-impressie on the admitted VibeCast display.
4. **Listen with friends:** shared music questions and guest song requests without letting an arbitrary room voice take over owner playback or private information.

Pause, volume and next/previous are supporting controls, not the defining proposition. “Knows my music and horizon” means access to genuine permitted context, not invented listening, facts, measured audio features or future playback promises.

## 2. Non-negotiable architecture: one Core, one conversation/service path

```text
HA satellite: wake word / explicit activation / microphone
  -> HA-native speech recognition and conversation transport
  -> thin DJConnect HA conversation adapter
  -> existing Core Ask DJ application service
       -> existing actor/Profile/privacy resolution
       -> existing Core conversation topics, choices and confirmation state
       -> existing Session Runtime / Planner / Knowledge / Moment owners
       -> existing Track Insight / research / Forecast services
       -> existing Voor jou offer and mix services
       -> existing output and playback effect owners
       -> existing VibeCast guest authority/request policy when applicable
  -> accepted Core answer / follow-up / result / presentation
       -> HA-native speech output
       -> existing authorized conversation history / Session Flow
       -> existing authorized VibeCast Broadcast projection, if appropriate
```

**HA owns:** physical satellite lifecycle, firmware, wake word, capture, STT/TTS transport and device capabilities. **DJConnect Core owns:** Session, intelligence, interpretation, context, music choices, services, effect authorization, actual results and retained product records. **Apple/VibeCast own:** presentation of permitted Core state, not another conversational brain.

The adapter only translates genuine HA input/context to the shared Core boundary and accepted Core results back to HA. Prefer an in-process call to the existing application service, not a self-HTTP loop with borrowed owner tokens. A narrow supported principal/transport adapter may be added to the shared service where the current contract is paired-device-only; it must not bypass that contract or impersonate an Apple device.

No separate satellite prompt stack, LLM agent with its own tools, recommendation generator, Session Runtime, voice-only music engine, result store, history database, workflow service or independent event bus. No YAML/Node-RED/custom sentence tree implementing the Voor jou business flow. HA conversation mechanisms are transport, not a second business-state owner. Core's already configured model/provider transport can remain; it must not call the DJConnect ingress agent recursively.

No fallback from failed common-service admission into the old direct command processor. Reuse lower-level modules that the common service legitimately uses; this is not an instruction to delete shared playback/parser code indiscriminately. Necessary compatibility aliases must converge on the same implementation and must not leave an independently functioning legacy voice route.

## 3. Current source evidence and bounded correction inventory

Latest Core main read for this registration: `59d51e692c3c1681b6b9711edd1e2e52c363bf68`. At that exact ref, `custom_components/djconnect/conversation.py`, blob `6cc7c972cdc73df6fafce3836fa0aa1db146c80c`, still calls `run_text_command(play=True, correct_stt=False)`, returns NL/EN-oriented response text and does not invoke the shared contextual Ask DJ service. It copies HA `conversation_id` into `session_id`, `agent_id` into `assist_pipeline_id`, and reports constant ready/available. The previous broader audit was at `b0e491c33596c60c1a1b5fcb804f25fd95e8a218`; it is historical evidence, not a newer implementation pin.

Current writer must re-read main/WIP and address remaining discrepancies, without rebuilding already delivered internals:

- Connect the native agent to `ask_dj/service.py` and the existing application/service authorization boundary.
- Remove the adapter-level assumption that arbitrary input is an immediate playback request. Information and discovery must not start music.
- Separate HA conversation identity, HA agent identity, actual HA pipeline identity, Core thread identity and DJ Session identity.
- Validate actual HA device/satellite/context delivery; unit-test attributes manually placed on stubs are not physical-HA proof.
- Resolve the synthetic `djconnect-conversation-agent` device binding versus actual endpoint/area mappings: it must not silently force every room to one personal owner.
- Detect self-referencing conversation/provider configurations and return an actionable non-recursive error; do not silently change the selected backend agent.
- Project genuine availability, pending input and supported language capabilities rather than unconditional readiness.
- Bring five-language Core speech/copy and tests into parity where supported; keep real STT/TTS availability explicit.
- Preserve existing pairing, profile mappings and nonvoice users. Do not remove unrelated modules or other client routes without an explicit disposition.

These findings are source observations and risks to reproduce, not a claim that a physical failure has already been demonstrated.

## 4. Contextual conversation semantics

The product supports general music conversation without an active DJ Session. A question does not create a Session as a side effect. An explicit authorized Session-start request uses the existing lifecycle service; joining/replacing a currently active Session follows the same existing target/confirmation semantics as other ingress.

Use **two distinct context anchors**:

- live listening context: actual current track/artist, output, playback, Session settings and qualified direction;
- conversation subject: the track, artist, album, concert, selected published Moment or offered result currently being discussed.

A track change must not erase the conversational subject. “En wanneer was dat optreden?” remains about the discussed event; “Wat speelt er nu?” deliberately changes to current playback. Resolve ambiguity in Core, not through a separate satellite parser.

Example goal sequence:

> “Wat maakt dit nummer bijzonder?” → relevant grounded answer.  
> “Was dat hun eerste album?” → retain artist/album.  
> “Heeft die zanger ook solo gewerkt?” → resolve the referenced person or clarify.  
> “Heb je daar iets van?” → show/speak actual options; no implicit playback.  
> “Laat de tweede eens horen.” → execute the exact offered second action through the existing owner.

Use Core's existing bounded operational thread, resultset and pending confirmation. The HA ChatLog is a transport representation, not an independent durable source of product memory. Do not import all HA history or run an additional prompt over it. Multiple satellites must not accidentally share the same pending “yes” or default private topic. Bind a voice conversation to the actual admitted endpoint/actor and corresponding Core thread; explicit authorized cross-surface handoff may reuse the same subject/resultset, but sharing a Profile alone does not merge conversations.

Maintain the distinction between:

- the last **actually delivered/spoken** contribution on the applicable voice output;
- the latest published eligible Moment;
- the item selected/displayed on the admitted screen;
- current playback.

“What did you just say?” should prefer a genuine recent delivery reference when available. Do not fabricate a spoken-delivery receipt merely because a Moment was generated. If the reference is ambiguous/unavailable, clarify briefly. No second delivery-history database; use existing presentation/operation state with a minimal transient reference if needed.

Identity, original Session, original choice/revision, output and request identifiers remain bounded. Pending references do not silently rebind after clear, end, Profile/account change or a newer proposal. Natural paraphrases, corrections, ordinals and “starten maar” resolve in the existing Core choice handling. An ambiguous yes never authorizes an unrelated pending action.

## 5. Personal style and conversation rhythm

Use the confirmed effective Mood and Persona from Core for every response and follow-up. Persona affects wording, rhythm and warmth, not facts, rights or action semantics. Mood influences atmosphere and selection; it must not imply measured acoustic properties or a rewritten queue.

Start with a useful compact answer, then allow depth. Do not recite all Track Insight fields, speak technical labels, or append “Wil je meer weten?” to every response. Clarify only when information or authority is actually missing. Supported NL, EN, DE, FR and ES copy/behavior belongs to the existing locale contract, with actual speech-engine limitations reported honestly.

Use native conversation continuation for genuine pending questions. An optional short follow-up window must be bounded and visible/clearly indicated where hardware supports it; no perpetual ambient recording, covert listening or new wake-word implementation. On devices without continuation, the same Core context should survive a new permitted wake-word turn. Hands-free barge-in and far-field performance are hardware-dependent acceptance items, not promised by a software flag.

The configured Core speech/presentation policy and native HA TTS transport determine what can be spoken. Semantic Persona is not a promise that every HA TTS engine supports dynamic voice/timbre switching. Do not mutate global HA pipeline voices to simulate per-turn Persona. Do not inherit an unrelated Apple device's autoplay preference as satellite authorization. Reactive answers, manual replay and proactive narration remain separate purposes.

Explicit user interaction takes priority over an unstarted automatic DJ narration. One authorized output speaks each accepted reply; no simultaneous satellite/iPhone/TV duplicates. Use existing audio arbitration/cancellation where available. Ducking and restoration use the established output service when supported; do not blindly restore a stale volume after someone changes it, and do not create a universal mixer in the adapter.

“Stop met vertellen” stops narration/listening as appropriate, not music. “Pauzeer de muziek” is playback. “Beëindig de DJ-sessie” is lifecycle. Clarify an ambiguous stop where needed. Canceling a pending choice has no queued playback effect; canceling after dispatch is not an invented rollback.

## 6. Voice-based Track Insight, recent Moments and horizon

Natural information requests include: “Wie heeft dit geproduceerd?”, “Wat maakt deze opname bijzonder?”, “Waar ken ik dit nummer van?” and “Vertel iets over deze artiest.” Route to the existing Track Insight/research/Knowledge owners. Only claim facts, instruments, credits, sound measurements or recording relationships when the actual evidence supports them.

For published contributions:

- **Herhaal het:** read/play the original accepted contribution, not a newly invented similar story.
- **Vat het kort samen:** a new, clearly scoped reply derived from that contribution; never rewrite the saved Moment.
- **Vertel daar meer over:** continue using the exact retained subject, with the existing research services when needed.
- **Laat dat optreden zien:** request a permitted presentation of that exact Live-impressie/event, not an arbitrary artist photo or another concert.

Recall/replay is not a new DJMoment, a second proactive budget charge or an instruction to replay the song. Persistence, source rights, privacy, expiry and deletion continue through existing owners. An ended Session is not reopened by historical recall.

The DJ can discuss actual playback, an actually observed queue, qualified Forecast/direction and user requests for change. These are not interchangeable. “Waar gaan we muzikaal naartoe?” returns the actual supported intention, not a guaranteed next-15-minute programme or private Planner slots. A supported Mood adjustment uses the existing settings service; changing Mood alone is not equivalent to generating/replacing music. Missing capabilities/data receive a useful honest response rather than a fabricated horizon.

## 7. Voor jou: one offer, voice and visual interaction

**Voor jou replaces Verras me.** The voice experience consumes the same server-owned three-option offer, mix identities, recommendation reasons, action IDs, output continuation and Session-scoped completion state as the existing personal UI. No voice-only recommender, old Verras-me launcher or parallel offer store.

Canonical earlier decisions: [Core transformation](https://github.com/pcvantol/djconnect/issues/1101#issuecomment-6660680798), [Apple transformation](https://github.com/pcvantol/djconnect-app/issues/87#issuecomment-6660720788). The startup card remains on iPhone/iPad/Mac only. **No Watch Session-start or Voor jou startup card is introduced.** HA-native voice is a separate permitted interaction host and may submit an explicitly authorized Core Session Start Request.

At every real new Session, prepare the existing offer irrespective of playing/paused/stopped or empty/full queue. Music remains unchanged while discussing choices. Use permitted Mood, Music DNA and earlier confirmed choices for relevance and variation; no invented personal memories, no new preference engine. Displaying or rejecting a card is not musical dislike. Missing previous choices is normal first use.

Voice flow:

1. Explicitly start/enter the applicable Session using the existing lifecycle owner. Reuse valid defaults; avoid a mandatory spoken settings questionnaire.
2. Briefly introduce the three actual genres/mixes and their meaningful differences. Personal intro in first person, consistent with Persona/Mood and evidence. Speak ordered labels so “de tweede” is meaningful. The exact offer and ordering remain stable during the conversation.
3. “Waarom die?”, “Wat is het verschil tussen één en drie?” and “Vertel meer over de tweede” are information, not effects.
4. “Die tweede, starten maar” selects the exact existing mix.
5. Valid current/explicitly configured usable speaker: start there without redundant speaker/yes/Play Now dialogs. Make the destination and replacement semantics clear before the effect.
6. Missing/ambiguous/unavailable speaker: use the existing Core output-continuation question, e.g. “Op welke speaker wil je deze mix afspelen?” Speak real options. The same response is an ordinary Ask DJ bubble in the personal Session Flow if that surface is open; no separate voice workflow or speaker overlay.
7. Speaker selection completes the already authorized mix request. Do not regenerate the mix, ask the genre again, or add a third confirmation.
8. **The complete mix replaces the current queue**, using the existing collection effect. It is not the single-track best-effort preserve operation.
9. After actual successful start, mark the common offer consumed so all authorized personal consumers remove the startup card and voice does not re-offer it. A raw ACK or speaker selection alone is not completion. Failure/uncertainty keeps the common recovery path; no blind duplicate dispatch.
10. Explicit “laat maar” closes the applicable proposal without touching current music. Apply existing documented dismissal scope: do not silently turn a client-scoped UI dismissal into a new household-wide preference. A successful start is the shared Core outcome; the corresponding voice conversation stops offering it. A later explicit recommendation question uses general Ask DJ, not a resurrected startup card.

Ordinary pause, queue exhaustion, reconnect, polling or reopening the same Session does not create a fresh startup proposal. A new real Session can. No surprise transfer or queue replacement occurs merely because a satellite wakes up.

## 8. VibeCast: one DJ, complementary voice and screen

The satellite supplies interaction/audio, the admitted VibeCast display presents the same authorized meaning. Do not create a TV conversation engine, peer-to-peer control channel or independent screen-owned Session.

An explicit user request can focus an allowed shared contribution, artist presentation, actual offer projection or exact concert photo through Core and the existing Broadcast/presentation owners. “Terug naar de muziek” restores the normal ambient composition. Recalling a card is a presentation action, not a new Moment/history entry.

Any additional transient focus/reference field must be a minimal versioned extension to the existing presentation contract and display grant, not a new semantic eventbus. TV remains read-only: receiving an authorized presentation update does not grant it owner controls. Opening/zooming imagery causes no playback or microphone effect.

No persistent full transcript or support-chat panel on TV. Use restrained transient listening/responding/choice states only when authorized and supported, then return to the normal screen. No automatic display of private conversations. Sharing a topic or result must have a documented audience projection, not infer consent from a running VibeCast screen.

**Private Voor jou is not automatically shared.** If a host deliberately presents its music choices to the room, project only allowed genre/mix labels, safe descriptions and permitted visuals. Exclude Music DNA, listening history, prior private choices, internal horizon/planner state and raw personal intro. No direct copying of owner image/audio grants to a guest screen. Reuse the For-you visual consumer direction where applicable; no Spotify mix cover substitution mandated by this voice work.

Live-impressie is an optional content dependency, not a blocker for the conversation adapter. When that separately delivered Moment exists, voice references its actual event, photograph and stored story; it does not fabricate live pictures or establish image rights. Shared imagery and spoken delivery each retain their existing permissions.

## 9. Friends in the living room: safe participation, real request handling

Provide a host-controlled shared-listening policy on the **same Session**, not a second party Session/engine. Default unverified room speech is a room/guest participant under explicit endpoint policy, not the personal owner just because the hardware or HA service runs with that owner's account.

No assumed speaker recognition or owner privilege from “ik ben Peter”. A deliberately configured trusted personal endpoint can use its admitted privileges, but a shared endpoint must not silently inherit personal history or full playback authority. The room voice input has no reliable per-human identity; use endpoint/room and Session request budgets, without fabricated per-person fairness or voiceprints.

Guest information requests use the same Core Ask DJ with permitted current music/Moment context, Session style and an isolated temporary conversation scope. No private host history/Music DNA, unrestricted output selection, session ending, queue replacement or settings/profile writes. Apply this at the actual service/tool/effect boundary, not only in prompting.

A spoken **verzoeknummer** must enter the SAME guest-request process as browser/app VibeCast requests from #1174. It is a proposal, not owner Speel nu:

```text
Received -> clarification if needed -> exact recording identified
  -> guest confirms the intended request -> DJ considers under host policy
  -> accepted/planned -> actual enqueue confirmed -> actually observed playing
```

No extra confirmation when the clear first request already fixes the desired recording and common policy permits it; ambiguity/version selection is clarified. Host may enable bounded autoacceptance so every routine request does not require a phone tap. Preserve the existing policy for capacity, repeats, acceptance, refusal and deferment; do not implement a rival request planner in the voice adapter.

“Ontvangen”, “gepland”, “staat in de wachtrij” and “speelt nu” mean different actual outcomes. Only observed correct playback can support “dit is jullie verzoeknummer”. Do not promise an exact play time/order not supported by the backend. Lost responses use existing operation/readback handling rather than repeated enqueue.

A guest request does not normally interrupt the current track. It stays distinct from an authorized owner's **Speel nu** for a single track (existing accepted best-effort queue preservation). Albums, playlists and whole Voor jou mixes deliberately replace the current queue. Reuse those exact common effect meanings; no new atomic-queue proof requirement or separate voice player.

Guest requests, reactions and room conversations do not automatically become the host's personal Music DNA. TV may show a bounded anonymous accepted-request notice where allowed, never raw private chat or an invented speaker identity. Leaving the room/client does not promise reversal of an already accepted queue effect. Stop VibeCast and end the DJ Session remain different operations with their existing owners.

## 10. Audio output, room mapping and trust

Distinguish four identities: voice endpoint, resolved actor/Profile, actual music output, and authorized visual display/share. They are not inferred from one another by friendly name alone.

Start with explicit installation-owned mappings using existing resolution/configuration owners. A known current usable output is reusable; a reliable configured room default can be used under declared policy; missing/ambiguous output requires the existing clarification. Do not infer Spotify device identity from a matching label or silently choose the first online speaker.

Reactive Assist answers and proactive DJ narration are different capabilities. First deliver the real conversation. Autonomous room announcements reuse existing Session-Moment, speech and audio-renderer owners with explicit eligibility; complete automatic area routing is separately deferred in `ROOM_PRESENTATION_ROUTING_ARCHITECTURE.md` and must not become an artificial dependency for the basic voice experience.

Avoid echo loops: own TTS is not a new human utterance, a listening state must not cause automatic speech, and a VibeCast audio consumer must not duplicate the chosen HA answer. Preserve actual hardware limitations and test turn-taking with music playing. No new APNs, central API relay, cloud speech subscription or firmware requirement for normal HA voice requests.

## 11. Native HA integration boundary and official references

Implement against the repository-supported HA version. Current official documentation describes `ConversationEntity._async_handle_message`, `ConversationInput`, `ChatLog`, `ConversationResult` and `continue_conversation`. The older `async_process` interface remains backward compatible; a rename alone does not solve semantic integration.

Use `continue_conversation` from the accepted Core need-for-input state where the actual satellite supports it. `agent_id` names the conversation agent, not an Assist pipeline. HA conversation IDs track HA conversations, not DJ Sessions. HA `assist_satellite.announce`, `ask_question` and `start_conversation` are transport features with platform constraints; do not convert their local answer matcher into a parallel Voor jou state machine or assume universal full-duplex/barge-in.

Reviewed official sources:
- https://developers.home-assistant.io/docs/core/entity/conversation/
- https://developers.home-assistant.io/docs/intent_conversation_api/
- https://www.home-assistant.io/integrations/assist_satellite/

Technical assertions remain version-bound; verify the actual installed/native behavior during implementation. Do not mutate global pipelines or silently fall back to an unrelated default conversation agent. No raw voice recording archive, unredacted prompt/token logs or cloud provider changes are authorized here.

## 12. Reuse / extend / retire map

| Existing owner/building block | Disposition |
| --- | --- |
| `conversation.py` HA entity and setup identity | Adapt as thin native ingress/egress; preserve valid configuration/migrate intentionally. |
| `ask_dj/service.py`, shared interpretation/history/context/results | Reuse and extend the existing service for admitted HA/room actors where necessary. |
| `profile_context.py`, canonical ProfileResolver and HA registry context | Reuse; repair actual endpoint/principal binding and ID conflation. |
| Session Runtime, lifecycle/settings, Planner, Knowledge, Moments | Reuse as sole semantic owners; no satellite-created state. |
| Track Insight, research, Forecast, retained Moment lookup | Reuse exact subject/source-aware reads and speech preparation. |
| Voor jou offer/mix/output continuation and completion | One cross-surface offer/action path; no legacy Verras me fork. |
| Playback backend/effect receipts | Reuse; preserve single-track vs collection vs guest-request differences. |
| VibeCast shared projection, guest thread/request policy, Broadcast | Reuse/targeted extension; no parallel guest queue or TV intelligence. |
| HA ChatLog/STT/TTS/continuation | Transport integration only; actual hardware capability checks. |
| Old direct voice command route / permissive fallback | Retire from normal agent execution in the same delivery; no hidden fallback. |
| Native LilyGO ESP32 firmware | Separate product; no generic satellite firmware task inferred. |
| Central API/APNs | No new dependency or work package for voice. |

## 13. Canonical documentation integration checklist

The admitted Core writer must incorporate this specification into the canonical documentation, not leave this issue as the sole architecture source:

- [ ] Add or update the single technical architecture document `docs/technical/HA_NATIVE_VOICE_DJCONNECT_CORE_V1.md`, referencing this decision and real source pins.
- [ ] Update `docs/product/ASK_DJ_CONVERSATIONAL_EXPERIENCE_V1.md` and `ASK_DJ_CONTEXTUAL_DIALOGUE_CONTRACT_V1.md` with the native HA adapter, scoped identities, choice continuation and migration boundary; no second dialogue contract.
- [ ] Reconcile `docs/technical/VOICE_TRANSPORT.md`, `AUDIO_RENDERER_HOST_ARCHITECTURE.md` and `ROOM_PRESENTATION_ROUTING_ARCHITECTURE.md`: reactive conversation now selected for integration; broader automatic room routing remains separately qualified/deferred.
- [ ] Reconcile `CLIENT_CAPABILITY_MATRIX.md` and `DJCONNECT_CAPABILITY_MODEL.md`: distinguish central capability, actual HA host adoption and physical acceptance. Preserve historical evidence; add a current clarification to CMB-09 rather than rewriting its old assessment into runtime proof.
- [ ] Cross-reference existing Voor jou/start lifecycle and VibeCast #1174 documents. State iPhone/iPad/Mac card scope and unchanged Watch absence. Keep visual-only VibeScape #1271 isolated; this native music conversation does not widen that director's tools/persistence.
- [ ] Register the decision in the existing architecture/document index/ADR structure if required; discover actual filenames/numbering rather than inventing existing ADRs.
- [ ] Update `docs/roadmap/v1/djconnect-platform-v1.json` as the single graph source, regenerate CATALOGUE, DEPENDENCIES, OPEN_WORK and affected lane views; do not hand-edit generated status tables as a second truth.
- [ ] Correct user/setup copy only to the extent supported by the delivered subset. Native satellite availability, personal access and autonomous room narration are not implied by simply selecting an agent.

## 14. Lanes, stages and DAG dependency shape

**DJC-CORE is the owning delivery lane** for architecture, HA conversation adapter, actor/context mapping, shared service integration, voice projection, common lifecycle/choices/effects, guest policy and producer fixtures. Reuse existing `CONVERSATION::CORE::SHARED-DIALOGUE`, `ENTRY::CORE::LIFECYCLE`, `ENTRY::CORE::ASK-LIFECYCLE`, `SPEECH::CORE::*`, `WEB::CHAT`, `WEB::REQUEST`, `WEB::EFFECT-POLICY`, `WEB::ENQUEUE` and `WEB::SHARED` records where their scope fits. Add an explicit HA-native consumer/adoption/physical acceptance leaf only where the canonical DAG lacks it. Proposed IDs must be introduced once by the owning graph edit, not asserted as already existing.

**DJC-APPLE** owns only the necessary existing host-policy/configuration UI and cross-surface consistency acceptance: shared Voor jou completion, appropriate personal Flow, existing controls/privacy, no duplicate audio, no Watch start/card. It does not implement a second voice engine or become a dependency for a standalone HA conversation on an already configured endpoint. Reuse existing guest/host UI work rather than a duplicate screen.

**DJC-VIBECAST** owns visible shared presentation/focus/choice/request-status adoption in the existing web renderer and distribution handoff. Check actual source ownership: Core retains shared renderer source where canonical; receiver consumes the existing build/package process instead of hand-patching generated files. No speech intelligence or owner authority in the browser.

**ESP32, Pi, API and Website:** no new implementation dispatch by this issue. Preserve their contracts; route concrete regressions or later copy changes to their existing owners only if required. Generic HA satellites are not native LilyGO firmware. No API/push task invented to satisfy voice.

Stage sequence, for later admitted implementation:

1. **Conversation foundation:** shared service + correct actor/IDs + current track and multi-turn topic + recent published/spoken contribution + native answer/continuation. Deliverable without VibeCast, personal recommendation availability or automatic room routing.
2. **Choose/start together:** integrate existing lifecycle + Voor jou + common result/output continuation + one completed mix effect. Reuse early versioned fixtures for consumers; no wait for unrelated documentary closures.
3. **Shared living-room experience:** admitted shared presentation + guest Ask DJ/request effect policy + receiver adoption. Explicit event-photo content is optional and not a dependency of basic guest requests.

Document preparation and contract work can be read-only/fixture-driven in parallel under existing rules. Functional dependencies, writer/resource admission and release/installation gates must remain distinct. Do not create an all-platform/all-feature completion gate that prevents an independently useful stage from shipping through its normal approved route.

## 15. Acceptance: demonstrate the experience, not just call plumbing

| ID | Required scenario / observable outcome |
| --- | --- |
| V01 | General question without Session: useful answer, no implicit Session or playback. |
| V02 | 5+ conversational turns about track -> album -> artist -> other work, with a track change in between; subject remains correct. Explicit current-track question changes focus. |
| V03 | Information/list questions create no play/pause/queue/volume/output effects. Choice/action uses the actual common resultset and correct output. |
| V04 | “Wat zei je net?” / repeat / summarize / more: correct original contribution and original subject; no new Moment on replay or fabricated delivery. |
| V05 | Correct Mood/Persona across responses, natural concise speech, no forced follow-up after every answer; grounded facts and honest limited Horizon. |
| V06 | Session start -> three real same Voor jou options -> explain/compare second -> choose -> valid known speaker -> mix starts once and common card closes. |
| V07 | Same flow without output -> one Core speaker question -> speak option -> same mix starts; no new genre generation or extra confirmation. |
| V08 | Playing and paused/full-queue starts work; showing/explaining/canceling leaves existing playback untouched. Mix replaces queue only after deliberate complete choice. |
| V09 | Failed/uncertain start, double utterance, lost response, cross-client choice: common operation/readback prevents duplicate effects; no false success/dismissal. |
| V10 | Clear/end/replace/profile/output/offer changes, late STT/model replies, concurrent endpoints: no stale retargeting or cross-room pending confirmation. |
| V11 | Real HA context identifies endpoint/agent/pipeline/thread separately; two differently mapped satellites do not collapse into synthetic-device owner. |
| V12 | Misconfigured self-referencing agent fails clearly, without recursion or unrelated-agent fallback; reported readiness/language matches actual route. |
| V13 | Native continuation and cancellation on a physical satellite; unsupported follow-up/barge-in capability has honest fallback. Music and speech are not conflated. |
| V14 | VibeCast explicit show/recall/return uses same permitted Moment/subject; no permanent transcript, private DNA/history leakage or duplicate publication. |
| V15 | Guest requests same exact recording/version through voice and phone path; guest cannot acquire owner privilege by wording/confirmation/retry. No unrequested interruption. |
| V16 | Received/planned/enqueued/playing remain distinct; correct “jullie verzoeknummer” only at actual matching playback. Guest requests do not train host DNA. |
| V17 | Stop VibeCast vs end Session vs stop narration vs pause music have distinct actual effects; no display/voice route assumes owner permission. |
| V18 | Architecture tests/spies prove both native HA and existing app ingress use the one application service; no legacy fallback, second recommendation producer/history writer or parallel effect path. |

Use proportionate unit/contract tests plus real isolated HA integration with the actual conversation entity and a supported physical satellite. Mocked `run_text_command` or fabricated ConversationInput fields alone cannot close native conversational acceptance. Test NL/EN/DE/FR/ES at the supported Core language boundary, then qualify actual hardware/STT/TTS combinations separately. Record real turn latency, false activations/echo, response intelligibility and successful follow-ups with music playing; do not invent numerical performance promises before measurement.
