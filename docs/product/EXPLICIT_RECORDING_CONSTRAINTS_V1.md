# Explicit recording constraints

A request naming a track, artist and album describes one recording, not an
album playback request or permission to substitute the provider's first result.
The literal request owns these constraints. A model proposal cannot replace
them. The existing playback/output authorization remains mandatory.

Core preserves the explicit album alongside the track title and artist through
its existing internal intent and Spotify dispatch. The backend searches a bounded
set of track candidates and checks their provider title, artist credits and album
against all original constraints before dispatch. No match or multiple distinct
matching recordings fail closed without a playback write. Punctuation/case and
Unicode normalization do not permit edition, remix or album substitutions.

An inline speaker suffix may be separated only after exactly one current,
non-cached, unrestricted backend inventory device matches. If its exact device
ID is already selected by the existing dialogue output owner, Core retains that
binding. Otherwise Core offers the existing Play-here continuation; its existing
owner revalidates the device ID and single-use retained request before dispatch.
Matching a name creates no grant or automatic transfer. Unknown or ambiguous
output words are never silently discarded. No public API, model call,
client-side selector or catalogue fact is added.
The reported old HA-dev request lacks the original interpreter/provider trace;
a reproduced parser bug is distinct from proving which live provider result
caused the observed different recording.
