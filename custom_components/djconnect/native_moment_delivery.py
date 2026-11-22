"""Dynamic native display admission; semantic Moments stay immutable.

Only existing field-qualified normalized facts and Runtime-authored context
are admitted. No provider access, payload interpretation or action execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import math
from typing import Any

from .session_facts import (
    QualifiedSessionFact, SharedProducerFact, AlbumContinuityFact, recording_label_matches,
)


@dataclass(frozen=True)
class MomentDeliveryBoundary:
    """Original publication clocks, never renewed by reads or reconnect."""

    published_monotonic: float
    published_at: str
    playback_item_id: str
    track_snapshot: tuple[tuple[str, Any], ...] = ()
    persona_revision: int | None = None

    def utc_at(self, deadline: float) -> str:
        return (
            datetime.fromisoformat(self.published_at)
            + timedelta(seconds=deadline - self.published_monotonic)
        ).isoformat()


def source_deadline(fact: QualifiedSessionFact) -> float:
    observations = [fact.observed_at]
    if isinstance(fact, SharedProducerFact) and fact.previous_evidence is not None:
        observations.append(fact.previous_evidence.observed_at)
    if isinstance(fact, AlbumContinuityFact) and fact.previous_album is not None:
        observations.append(fact.previous_album.observed_at)
    deadline = min(observations) + 1800
    return min(deadline, fact.source_expires_at) if fact.source_expires_at is not None else deadline


def admission(moment, boundary, **context):
    """Explicit owner presentation reuses every ordinary source qualification."""
    from .requested_moment_proof import proof, admitted, display_admission

    requested = proof(moment)
    if requested is None:
        return _ordinary_admission(moment, boundary, **context)
    original = {**context, "playing": True, "playback_item_id": requested.original_item_id}
    result = _ordinary_admission(moment, boundary, **original)
    allowed = admitted(moment, committed=True) and result["qualification"] == "qualified"
    display = display_admission(moment)
    # Explicit current-card admission is returned only to the requesting action;
    # ordinary Broadcast current selection retains its existing playing identity.
    result["current_display_allowed"] = False
    result["active_flow_display_allowed"] = allowed and moment.moment_id in context["flow_ids"]
    result["display_expires_at"] = display["expires_at"]
    return result


def _publication_window(moment, boundary, now):
    try:
        stamp = datetime.fromisoformat(boundary.published_at)
        duration = moment.presentation_intent.maximum_duration_seconds
        if stamp.tzinfo is None or not isinstance(duration, int) or not 0 < duration <= 90:
            return None
        if (
            not math.isfinite(now)
            or not math.isfinite(boundary.published_monotonic)
            or now < boundary.published_monotonic
        ):
            return None
        deadline = boundary.published_monotonic + duration
    except (TypeError, ValueError, OverflowError):
        return None
    return stamp, deadline, duration


@dataclass
class _NativeAdmission:
    """One original publication, qualified by its existing source owner only."""

    moment: Any
    boundary: MomentDeliveryBoundary
    session_id: str
    flow_ids: set[str]
    playback_item_id: str
    playing: bool
    now: float
    settings_revision: tuple[str, int] | None
    stamp: datetime
    deadline: float
    duration: int
    result: dict[str, Any]
    source: Any = None
    history_allowed: bool = False

    def _intentional_silence(self):
        if (
            self.moment.content
            or self.moment.artwork_url
            or self.moment.actions
            or self.moment.source_references
            or self.moment.source_attribution
            or self.moment.knowledge_intent.intent_type.value != "silence"
        ):
            return False
        return True

    def silence(self):
        if not self._intentional_silence():
            return self.result
        self.result["qualification"] = "intentional_silence"
        self.result["display_expires_at"] = self.boundary.utc_at(self.deadline)
        self.result["active_flow_display_allowed"] = bool(
            self.playing
            and self.moment.moment_id in self.flow_ids
            and self.boundary.playback_item_id
            and self.boundary.playback_item_id == self.playback_item_id
            and self.boundary.published_monotonic <= self.now < self.deadline
        )
        return self.result

    def origin(self):
        from .music_origin import admitted
        if not admitted(self.moment):
            return self.result
        self.result.update(qualification="qualified", source_expires_at=None,
            display_expires_at=self.boundary.utc_at(self.deadline),
            current_display_allowed=bool(self.playing and self.playback_item_id == self.boundary.playback_item_id
                and self.boundary.published_monotonic <= self.now < self.deadline),
            active_flow_display_allowed=self.moment.moment_id in self.flow_ids)
        return self.result

    def live(self):
        from .live_impression import admitted as admitted_live

        if not admitted_live(self.moment):
            return self.result
        self.result.update(
            qualification="qualified",
            source_expires_at=None,
            display_expires_at=self.boundary.utc_at(self.deadline),
            current_display_allowed=bool(
                self.playing
                and self.playback_item_id == self.boundary.playback_item_id
                and self.boundary.published_monotonic <= self.now < self.deadline
            ),
            active_flow_display_allowed=self.moment.moment_id in self.flow_ids,
        )
        return self.result

    def announcement(self, announcement):
        from .track_start_announcement import accepted, retained

        if (
            not accepted(self.moment)
            or self.boundary.playback_item_id != announcement.occurrence.item_id
        ):
            return self.result
        self.result["qualification"] = "qualified"
        self.result["requires_spotify_attribution"] = True
        self.result["source_expires_at"] = (
            announcement.retained_until
            if retained(self.moment)
            else self.boundary.utc_at(announcement.occurrence.deadline)
        )
        self.result["display_expires_at"] = self.boundary.utc_at(
            min(self.deadline, announcement.occurrence.deadline)
        )
        occurrence = announcement.occurrence
        from .track_start_announcement import START_WINDOW_SECONDS

        initial_position = START_WINDOW_SECONDS - (occurrence.deadline - occurrence.observed_at)
        remaining = (
            occurrence.duration_ms / 1000 - initial_position - (self.now - occurrence.observed_at)
            if occurrence.duration_ms is not None
            else 0
        )
        self.result["current_display_allowed"] = bool(
            self.playing
            and self.playback_item_id == self.boundary.playback_item_id
            and self.duration <= 10
            and remaining >= self.duration
            and self.now < min(self.deadline, occurrence.deadline)
        )
        self.result["active_flow_display_allowed"] = (
            self.moment.moment_id in self.flow_ids and retained(self.moment)
        )
        return self.result

    def bulletin(self):
        from .bulletin_runtime import BulletinProof, admitted as bulletin_admitted

        if not bulletin_admitted(self.moment, monotonic=self.now):
            if type(self.moment.bulletin) is BulletinProof:
                candidate = self.moment.bulletin.candidate
                import time

                if self.now >= candidate.monotonic_deadline or time.time() >= candidate.expires_at:
                    self.result["qualification"] = "expired"
            return self.result
        candidate = self.moment.bulletin.candidate
        limit = candidate.monotonic_deadline
        self.result["qualification"] = "qualified"
        self.result["source_expires_at"] = datetime.fromtimestamp(
            candidate.expires_at, self.stamp.tzinfo
        ).isoformat()
        self.result["display_expires_at"] = min(
            self.boundary.utc_at(min(self.deadline, limit)), self.result["source_expires_at"]
        )
        self.result["current_display_allowed"] = bool(
            self.playing
            and self.boundary.playback_item_id
            and self.boundary.playback_item_id == self.playback_item_id
            and self.boundary.published_monotonic <= self.now < min(self.deadline, limit)
        )
        self.result["active_flow_display_allowed"] = (
            self.moment.moment_id in self.flow_ids and self.now < limit
        )
        return self.result

    def confirmation(self, confirmation):
        data = confirmation.data()
        self.result["qualification"] = "qualified"
        self.result["display_expires_at"] = self.boundary.utc_at(self.deadline)
        self.result["active_flow_display_allowed"] = self.moment.moment_id in self.flow_ids
        self.result["current_display_allowed"] = bool(
            self.settings_revision == (data["settings_generation"], data["settings_revision"])
            and self.boundary.published_monotonic <= self.now < self.deadline
        )
        return self.result

    def researched(self):
        from .public_artist_narration import admitted

        receipt = self.moment.narration_acceptance
        source_limit = receipt.accepted.expires_at
        self.result["source_expires_at"] = self.boundary.utc_at(source_limit)
        if not admitted(self.moment, self.now):
            self.result["qualification"] = "expired" if self.now >= source_limit else "unqualified"
            return False
        if (
            hashlib.sha256(self.source.media_identity.encode()).hexdigest()[:24]
            != self.boundary.playback_item_id
        ):
            return False
        self.history_allowed = True
        self.deadline = min(self.deadline, source_limit)
        return True

    def qualified_fact(self):
        try:
            source_limit = source_deadline(self.source)
            self.result["source_expires_at"] = self.boundary.utc_at(source_limit)
            if self.now >= source_limit:
                self.result["qualification"] = "expired"
                return False
            attributes = dict(self.moment.source_attribution)
            expected = {
                "provider": self.source.provider,
                "url": self.source.source_url,
                "license": self.source.license,
            }
            if isinstance(self.source, SharedProducerFact) and self.source.previous_evidence:
                expected["url_previous"] = self.source.previous_evidence.source_url
            if (
                not self.source.eligible(self.source.media_identity, self.now)
                or attributes != expected
            ):
                return False
            bound_identity = hashlib.sha256(self.source.media_identity.encode()).hexdigest()[:24]
            if bound_identity != self.boundary.playback_item_id:
                return False
            self.history_allowed = (
                self.source.provider in {"MusicBrainz", "Wikidata"}
                and self.source.license == "CC0-1.0"
            )
            self.result["requires_spotify_attribution"] = self.source.provider == "Spotify"
            self.deadline = min(self.deadline, source_limit)
        except (AttributeError, TypeError, ValueError, OverflowError):
            return False
        return True

    def _source_kind_matches(self, moment_type, intent_type, references):
        return (
            self.moment.moment_type.value == moment_type
            and self.moment.knowledge_intent.intent_type.value == intent_type
            and self.moment.source_references == references
        )

    def _track_identity_matches(self, snapshot, proof):
        return (
            self.boundary.playback_item_id == proof.item_id
            and recording_label_matches(snapshot, proof, "title")
            and recording_label_matches(snapshot, proof, "artist")
        )

    @staticmethod
    def _transition_metadata_matches(metadata, proof):
        return (
            metadata.get("relation") == "discover_same_artist_genre"
            and metadata.get("transition_from_moment_id") == proof.source_moment_id
            and metadata.get("transition_to_moment_id") == proof.target_moment_id
        )

    def genre_transition(self):
        from .narration_brief import admitted_runtime_text
        from .session_runtime import GenreTransitionNarration
        from .context_expression import transition_copy

        proof = self.moment.genre_transition
        if not isinstance(proof, GenreTransitionNarration):
            return False
        source_limit = min(source_deadline(proof.earlier), proof.current.observed_at + 30)
        self.result["source_expires_at"] = self.boundary.utc_at(source_limit)
        if not proof.eligible(self.now):
            self.result["qualification"] = "expired"
            return False
        snapshot, metadata = (
            dict(self.boundary.track_snapshot),
            dict(self.moment.generation_metadata),
        )
        if (
            not self._source_kind_matches("transition", "transition", ("session_flow",))
            or not self._transition_metadata_matches(metadata, proof)
            or not self._track_identity_matches(snapshot, proof.current)
            or dict(self.moment.source_attribution)
            != {
                "provider": "Spotify",
                "url": proof.current.source_url,
                "url_previous": proof.earlier.source_url,
                "license": "Spotify-Policy",
            }
            or (
                self.moment.content
                != transition_copy(
                    locale=proof.current.locale,
                    persona=self.moment.presentation_intent.dj_persona.value,
                    context=proof.context(),
                    relation="discover_same_artist_genre",
                )
                and not admitted_runtime_text(self.moment)
            )
        ):
            return False
        self.result["requires_spotify_attribution"] = True
        self.deadline = min(self.deadline, source_limit)
        return True

    def observed_playback(self):
        from .narration_brief import admitted_runtime_text
        from .session_runtime import ObservedPlaybackNarration
        from .context_expression import playback_copy

        observed = self.moment.observed_playback
        if not isinstance(observed, ObservedPlaybackNarration):
            return False
        source_limit = observed.observed_at + 30
        self.result["source_expires_at"] = self.boundary.utc_at(source_limit)
        if not observed.eligible(self.now):
            self.result["qualification"] = "expired"
            return False
        snapshot = dict(self.boundary.track_snapshot)
        if (
            not self._source_kind_matches("track", "track_context", ("spotify_playback_status",))
            or dict(self.moment.source_attribution)
            != {"provider": "Spotify", "url": observed.source_url, "license": "Spotify-Policy"}
            or not self._track_identity_matches(snapshot, observed)
            or (
                self.moment.content
                not in {
                    playback_copy(
                        locale=observed.locale,
                        persona=self.moment.presentation_intent.dj_persona.value,
                        form=form,
                        title=observed.title,
                        artist=observed.artist,
                    )
                    for form in (0, 1)
                }
                and not admitted_runtime_text(self.moment)
            )
        ):
            return False
        self.result["requires_spotify_attribution"] = True
        self.deadline = min(self.deadline, source_limit)
        return True

    def session_opening(self):
        from .session_opening import admitted_opening

        if not admitted_opening(self.moment):
            return False
        self.history_allowed = True
        return True

    def authored_direction(self):
        if (
            not self.moment.source_attribution
            and self.moment.source_references == ("session_direction",)
            and (self.moment.moment_type.value == "session")
            and (self.moment.knowledge_intent.intent_type.value == "session_direction")
            and (dict(self.moment.generation_metadata).get("context_source") == "session_direction")
            and (dict(self.moment.generation_metadata).get("validated") == "true")
        ):
            self.history_allowed = True
            return True
        return False

    def project_navigation(self):
        from .moment_navigation import navigation, TTL_SECONDS

        if (
            self.result["qualification"] == "qualified"
            and (
                self.result["current_display_allowed"] or self.result["active_flow_display_allowed"]
            )
            and self.now
            < min(
                self.boundary.published_monotonic + TTL_SECONDS,
                source_deadline(self.source)
                if isinstance(self.source, QualifiedSessionFact)
                else self.deadline,
            )
        ):
            self.result["navigation_actions"] = [
                {
                    **nav,
                    "expires_at": self.boundary.utc_at(
                        min(
                            self.boundary.published_monotonic + TTL_SECONDS,
                            source_deadline(self.source),
                        )
                    ),
                }
                for action in self.moment.actions
                if (nav := navigation(action))
                and nav["reference"]["session_id"] == self.session_id
                and nav["reference"]["moment_id"] == self.moment.moment_id
            ][:1]

    def complete(self):
        self.result["qualification"] = "qualified"
        self.result["display_expires_at"] = self.boundary.utc_at(self.deadline)
        self.result["current_display_allowed"] = bool(
            self.playing
            and self.boundary.playback_item_id
            and self.boundary.playback_item_id == self.playback_item_id
            and self.boundary.published_monotonic <= self.now < self.deadline
        )
        self.result["active_flow_display_allowed"] = (
            self.history_allowed and self.moment.moment_id in self.flow_ids
        )
        self.project_navigation()
        return self.result

    def project(self):
        if self.moment.moment_type.value == "silence":
            return self.silence()
        if getattr(self.moment, "music_origin", None) is not None:
            return self.origin()
        if getattr(self.moment, "live_impression", None) is not None:
            return self.live()
        self.source = getattr(self.moment, "source_fact", None)
        from .track_start_announcement import contribution

        announcement = contribution(self.moment)
        if announcement is not None:
            return self.announcement(announcement)
        if getattr(self.moment, "bulletin", None) is not None:
            return self.bulletin()
        from .settings_confirmation import context as settings_context

        confirmation = settings_context(self.moment)
        if confirmation is not None:
            return self.confirmation(confirmation)
        if not self.source_qualified():
            return self.result
        return self.complete()

    def source_qualified(self):
        from .public_artist_narration import ResearchMomentAcceptance

        if type(getattr(self.moment, "narration_acceptance", None)) is ResearchMomentAcceptance:
            return self.researched()
        if isinstance(self.source, QualifiedSessionFact):
            return self.qualified_fact()
        if getattr(self.moment, "genre_transition", None) is not None:
            return self.genre_transition()
        if getattr(self.moment, "observed_playback", None) is not None:
            return self.observed_playback()
        if getattr(self.moment, "session_opening", None) is not None:
            return self.session_opening()
        return self.authored_direction()


def _ordinary_admission(
    moment: Any,
    boundary: MomentDeliveryBoundary | None,
    *,
    session_id: str,
    active: bool,
    flow_ids: set[str],
    playback_item_id: str,
    playing: bool,
    now: float,
    settings_revision: tuple[str, int] | None = None,
) -> dict[str, Any]:
    """Fail closed without inferring provenance from rendered text or names."""
    result = {
        "moment_id": moment.moment_id,
        "qualification": "unqualified",
        "current_display_allowed": False,
        "active_flow_display_allowed": False,
        "source_expires_at": None,
        "display_expires_at": None,
        "executable_actions": [],
        "requires_spotify_attribution": False,
    }
    if boundary is None or moment.session_id != session_id or not active:
        return result
    window = _publication_window(moment, boundary, now)
    if window is None:
        return result
    stamp, deadline, duration = window
    owner = _NativeAdmission(
        moment,
        boundary,
        session_id,
        flow_ids,
        playback_item_id,
        playing,
        now,
        settings_revision,
        stamp,
        deadline,
        duration,
        result,
    )
    return owner.project()


def withdrawn_native_delivery(session_id: str) -> dict[str, Any]:
    """Complete terminal denial for one transport authority, never a grant."""
    result = {
        "schema_version": 1,
        "session_id": session_id,
        "current_moment_id": None,
        "current_silence_moment_id": None,
        "active_flow_moment_ids": [],
        "admissions": [],
        "revocation_scope": "subscription",
    }
    result["revision"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[
        :24
    ]
    return result
