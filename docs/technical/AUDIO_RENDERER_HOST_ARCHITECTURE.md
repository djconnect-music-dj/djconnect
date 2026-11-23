## HA-native conversation implementation — 22 November 2026

## 2026-11-23 shared HA and browser participation candidate

The selected continuation of Core #1532 stage3 is implemented locally on `codex/ha-native-shared-participation-20261123`, based on `bbf56161c4b920ce43f701d3e951e721bba9d6df`. The same Core application service now admits temporary shared-room and browser guests, with host policy, exact-recording proposals, once-only queue dispatch/readback and eligible shared Moment focus/return. The actual paired host and the separate HA OptionsFlow administrator role remain distinct from guest and display principals. No personal Profile history, Music DNA, owner image/audio grants, private transcript or unrestricted controls are granted to a room participant. Core owns the maintained shared renderer and guest page; no duplicate Apple conversation engine or central API/firmware change is introduced.

This is a source candidate, not a protected merge, internal publication, installed capability or physical speech/screen acceptance. Existing broader WEB/Apple/receiver distribution and hardware/editorial acceptance remain open. The previous sections retain the personal-stage scope; the versioned shared contract and limits are in [VIBECAST_GUEST_PARTICIPATION_V1.md](VIBECAST_GUEST_PARTICIPATION_V1.md).

Owner #1532 now selects the native HA adapter to the same Core Ask DJ service.
See [canonical design](HA_NATIVE_VOICE_DJCONNECT_CORE_V1.md). Personal endpoints require explicit installation
consent and separate HA/agent/thread/Profile/Session identity. The ordinary
lifecycle and exact existing Voor jou offer are reused; Apple keeps the same
completion/privacy/audio rules and Watch gains no start/card. Reactive HA
conversation is selected; autonomous room routing and shared guest/request/
display authority remain separately qualified. Local implementation and actual
isolated HA software evidence do not establish merge, installation, provider
quality or physical satellite/audio/display acceptance.

# Audio Renderer Host Architecture

## Status

Canonical terminology and architecture clarification. This document introduces
no Renderer Host, Home Assistant integration, Runtime, Broadcast, transport,
speech, configuration or user-interface implementation.

## Purpose

DJConnect distinguishes external Home Assistant terminology from its internal,
platform-neutral presentation abstraction:

| Context | Canonical term | Meaning |
| --- | --- | --- |
| Home Assistant documentation, entities, configuration and UI | **Voice Satellite** | The Home Assistant product and entity terminology. |
| DJConnect presentation architecture | **Audio Renderer Host** | A Renderer Host whose primary responsibility is rendering DJConnect audio presentation. |

DJConnect must not redefine or replace Home Assistant's user-facing **Voice
Satellite** term. A Home Assistant Voice Satellite is one current
implementation of an Audio Renderer Host when it renders an approved DJConnect
audio presentation.

## Renderer Host model

**Renderer Host** is the platform-neutral presentation boundary. It can have a
primary presentation role:

```text
Renderer Host
├── Visual Renderer Host
└── Audio Renderer Host
```

Visual and Audio Renderer Hosts consume the same immutable DJMoment and
Presentation Intent. They render that approved meaning through their own local
capabilities; neither creates a Moment, changes the Intent or becomes
authoritative over another Renderer Host.

Device Lifecycle (Guest/Registered) and Experience Mode
(Interactive/Ambient) remain independent axes defined by
[Renderer Host Classification](RENDERER_HOST_CLASSIFICATION.md). Ambient is an
experience mode, not a third host role. An **Ambient Renderer Host** means a
Visual or Audio Renderer Host operating in Ambient mode; it does not create a
new Runtime, Broadcast or peer-synchronization model.

## Responsibilities and boundaries

An Audio Renderer Host owns only local audio presentation, including:

- playback of server-approved speech;
- future renderer-local ambient audio cues; and
- declared renderer-local audio capabilities.

For Speech Presentation it may also own local Role Mapping: semantic Speaker
Role to configured local voice to configured local TTS provider. This mapping
is never sent to Presentation Composer or Broadcast. A missing local speech
capability does not invalidate the immutable Presentation; a Visual Renderer
may still render its text through the same Projection.

It does not own the Session Runtime, Planner, Knowledge Engine, DJ Moment
Engine, Session Flow, business logic, DJMoment generation, Presentation Intent
selection, provider playback, provider credentials or Broadcast state.

The term is intentionally broader than Voice Satellite. Future implementations
may include a dedicated audio appliance, renderer-capable speaker or room audio
endpoint without changing the core presentation architecture.

## Room Presentation Routing

[Room Presentation Routing](ROOM_PRESENTATION_ROUTING_ARCHITECTURE.md) may
select eligible Visual Renderer Hosts and Audio Renderer Hosts within a reliably
resolved Home Assistant Area. A current Home Assistant Voice Satellite is one
possible eligible Audio Renderer Host; the phrase **Voice Satellite** remains
correct whenever the document refers to the Home Assistant product, entity,
configuration or UI.

If the Area cannot be reliably resolved, DJConnect must not autonomously route
speech to an arbitrary room. Audio routing stays disabled while existing Visual
Guest Renderers may continue their authorized renderer-safe Broadcast
presentation.

## Non-goals

This terminology does not authorize Voice Satellite routing, TTS generation,
audio-device control, Audio Renderer Host discovery, registration, pairing,
Area Presentation Policy, Output Target Binding, a new HTTP endpoint, a new
WebSocket channel, persistence, Runtime behavior or Home Assistant terminology
changes.

## References

- [DJ Presentation Architecture](../product/DJ_PRESENTATION_ARCHITECTURE.md)
- [Renderer Host Classification](RENDERER_HOST_CLASSIFICATION.md)
- [Room Presentation Routing Architecture](ROOM_PRESENTATION_ROUTING_ARCHITECTURE.md)
- [Platform Ambient Experience](PLATFORM_AMBIENT_EXPERIENCE.md)
- [Speech Rendering Contract](SPEECH_RENDERING_CONTRACT.md)
