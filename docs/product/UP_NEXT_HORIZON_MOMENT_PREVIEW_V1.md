# Up-next Horizon DJ Moment preview V1

This temporary Session card previews the first track in the actually observed
queue during the last45seconds of the current playing track. It supplements
the existing music announcement. It neither speaks nor replaces an accepted
announcement, changes playback or publishes a durable Moment/history entry.
Its short DJ introduction is authored in the Session language/persona using
only the observed next title and artist; it claims no unobserved musical facts.

The existing original queue source/command/output admission remains the owner.
Every read requires the original queue deadline, current playing recording,
exact observed upcoming Spotify track, and matching queue-prefix title/artist.
No provider/model call, queue refresh, publication or deadline renewal occurs on
a read. Pause, recording/output/command/source withdrawal, queue expiry/change
and Session end withdraw the preview. Repeated reads are pure and its stable
preview ID does not establish a new lease. A genuinely fresh admitted queue
observation may supply a new original expiry for the same preview.

Owner Broadcast projections add nullable `horizon_moment`:

```json
{
  "contract_version": 1,
  "type": "horizon",
  "preview_id": "64-lowercase-hex",
  "session_id": "original-session",
  "current_item_id": "original-playing-item",
  "text": "Short authored DJ introduction using the observed next track.",
  "expires_at": "original-source-UTC-expiry",
  "track": {
    "item_id": "SHA256(spotify:track:ID) first24 hex",
    "title": "Observed next title",
    "artist": "Observed next artist",
    "source_url": "https://open.spotify.com/track/ID",
    "artwork_url": "/api/djconnect/v1/image_proxy/original-proxy-id"
  }
}
```

`artwork_url` is optional and remains the existing owner-authorized image proxy,
never a provider URL or new media grant. The native card shows art/title/artist,
the short text and DJ identity, then disappears at the original expiry or
withdrawal. It must not forward a `preview_id` as a selected Moment ID, persist
the card, trigger TTS, infer a request was played, or send it through the Watch
Moment alert channel. Null withdraws the card on owner updates. Historical and
shared/non-owner Broadcasts omit it; extending shared prepared-pixel purpose is
a separate producer step, not implicit permission from this owner preview.

The already observed `playback.up_next` gains optional canonical `source_url`
from that exact first provider queue entry. Existing consumers may ignore it.
No numeric analysis, Music DNA or recommendation is inferred from this card.
