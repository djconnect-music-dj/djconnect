"""Bounded source-qualified current-track facts, never AI-created trivia.

Only exact Spotify catalog metadata, MusicBrainz core CC0 relationships and
Wikidata CC0 descriptions are eligible. Provider payloads remain transient.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, replace, field
from datetime import date
import re
import time
import unicodedata
from typing import Any


LANGUAGES = ("en", "nl", "de", "fr", "es")
USER_AGENT = "DJConnect/4.0 (https://github.com/djconnect-music-dj/djconnect; session-knowledge)"
MBID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")

CREDIT_ROLES = {
    "producer": ("Producer", "Producent", "Produzent", "Production", "Producción"),
    "instrument": ("Instruments", "Instrumenten", "Instrumente", "Instruments", "Instrumentos"),
    "vocal": ("Vocals", "Zang", "Gesang", "Voix", "Voces"),
}


def composer_fact_bodies(names: str) -> tuple[str, ...]:
    """Canonical normalized composer credit, shared by rendering and source projection."""
    return (f"Composers of the work behind this recording: {names}.",
            f"Componisten van het werk achter deze opname: {names}.",
            f"Komponisten des Werks hinter dieser Aufnahme: {names}.",
            f"Compositeurs de l’œuvre de cet enregistrement : {names}.",
            f"Compositores de la obra de esta grabación: {names}.")


def _credit_body(roles, index):
    return " · ".join(f"{CREDIT_ROLES[role][index]}: {', '.join(names)}" for role, names in roles)


def _album_release_bodies(subject, released):
    return (f"Spotify dates this edition of {subject} to {released}.",
            f"Spotify dateert deze uitgave van {subject} op {released}.",
            f"Spotify datiert diese Ausgabe von {subject} auf {released}.",
            f"Spotify date cette édition de {subject} de {released}.",
            f"Spotify fecha esta edición de {subject} en {released}.")


def _person_begin_bodies(subject, begin):
    return (f"Birth date of {subject}: {begin}.", f"Geboortedatum van {subject}: {begin}.",
            f"Geburtsdatum von {subject}: {begin}.", f"Date de naissance de {subject} : {begin}.",
            f"Fecha de nacimiento de {subject}: {begin}.")


def _group_begin_bodies(subject, begin):
    return (f"{subject} formed in {begin}.", f"{subject} is opgericht in {begin}.",
            f"{subject} wurde {begin} gegründet.", f"{subject} a été formé en {begin}.",
            f"{subject} se formó en {begin}.")


@dataclass(frozen=True)
class DisplayFactCore:
    """Normalized immutable display anchors; no raw payload or generated fact."""
    kind: str
    subject: str = ""
    roles: tuple[tuple[str, tuple[str, ...]], ...] = ()
    date: str = ""
    precision: str = ""
    entity_type: str = ""

    def validates(self, fact: QualifiedSessionFact) -> bool:
        if self.kind != fact.key:
            return False
        if self.kind == "genre_context":
            return self._genre_matches(fact)
        if self.kind == "recording_credits":
            return self._credits_match(fact)
        if self.kind == "album_release":
            return self._album_matches(fact)
        if self.kind == "artist_begin":
            return self._artist_matches(fact)
        if self.kind == "work_composers":
            return self._composers_match(fact)
        return False

    def _genre_matches(self, fact):
        if (self.entity_type != "ArtistGenre" or not label(self.subject, 160)
                or len(self.roles) != 2 or tuple(r for r, _ in self.roles) != ("track", "artist")
                or any(len(names) != 1 or not label(names[0], 160) for _, names in self.roles)):
            return False
        return fact.contents == tuple(zip(LANGUAGES, _genre_bodies(self.subject,
            self.roles[0][1][0], self.roles[1][1][0])))

    def _valid_credit_roles(self):
        return bool(self.roles and len({r for r, _ in self.roles}) == len(self.roles)
            and not any(r not in CREDIT_ROLES or not names or any(not label(n, 160) for n in names)
                        for r, names in self.roles))

    def _credits_match(self, fact):
        if not self._valid_credit_roles():
            return False
        contents = tuple((lang, _credit_body(self.roles, index))
                         for index, lang in enumerate(LANGUAGES))
        return contents == fact.contents

    def _album_matches(self, fact):
        bodies = _album_release_bodies(self.subject, self.date)
        return bool(label(self.subject) and qualified_date(self.date, self.precision)
                    and tuple(zip(LANGUAGES, bodies)) == fact.contents)

    def _artist_matches(self, fact):
        if not label(self.subject) or not qualified_date(self.date, self.precision):
            return False
        if self.entity_type == "Person":
            bodies = _person_begin_bodies(self.subject, self.date)
        elif self.entity_type == "Group":
            bodies = _group_begin_bodies(self.subject, self.date)
        else:
            return False
        return tuple(zip(LANGUAGES, bodies)) == fact.contents

    def _composers_match(self, fact):
        if len(self.roles) != 1 or self.roles[0][0] != "composer" or not self.roles[0][1]:
            return False
        names = ", ".join(self.roles[0][1])
        bodies = composer_fact_bodies(names)
        return all(label(n, 160) for n in self.roles[0][1]) and tuple(zip(LANGUAGES, bodies)) == fact.contents


@dataclass(frozen=True)
class ProducerCredit:
    contributor_id: str
    name: str
    role: str = "producer"
    qualifications: tuple[str, ...] = ()

    def eligible(self) -> bool:
        return bool(MBID.fullmatch(self.contributor_id) and label(self.name, 160)
                    and self.role == "producer" and not self.qualifications)


@dataclass(frozen=True)
class RecordingCreditEvidence:
    """Minimal proof, never historical playback or generated card text."""
    recording_id: str
    media_identity: str
    title: str
    producers: tuple[ProducerCredit, ...]
    source_url: str
    observed_at: float

    def _source_valid(self, now):
        return bool(MBID.fullmatch(self.recording_id)
                    and re.fullmatch(r"spotify:track:[A-Za-z0-9]{22}", self.media_identity)
                    and label(self.title, 160)
                    and self.source_url == "https://musicbrainz.org/recording/" + self.recording_id
                    and 0 <= now - self.observed_at <= 1800)

    def eligible(self, now: float) -> bool:
        return bool(self._source_valid(now) and self.producers
                    and all(p.eligible() for p in self.producers)
                    and len({p.contributor_id for p in self.producers}) == len(self.producers))


@dataclass(frozen=True)
class ComposerCredit:
    contributor_id: str
    name: str

    def eligible(self):
        return bool(MBID.fullmatch(self.contributor_id) and label(self.name,160))


@dataclass(frozen=True)
class WorkComposerEvidence:
    """Exact recording → underlying work → typed composer, never a producer."""
    recording_id: str
    work_id: str
    media_identity: str
    composers: tuple[ComposerCredit, ...]
    source_url: str
    observed_at: float

    def _source_valid(self, now):
        return bool(MBID.fullmatch(self.recording_id) and MBID.fullmatch(self.work_id)
            and re.fullmatch(r'spotify:track:[A-Za-z0-9]{22}', self.media_identity)
            and self.source_url == 'https://musicbrainz.org/work/' + self.work_id
            and 0 <= now - self.observed_at <= 1800)

    def eligible(self, now):
        return bool(self._source_valid(now) and self.composers
            and all(type(c) is ComposerCredit and c.eligible() for c in self.composers)
            and len({c.contributor_id for c in self.composers}) == len(self.composers))


def label(value: Any, limit: int = 320) -> str:
    text = str(value or "").strip()
    return text if 0 < len(text) <= limit and not any(ord(c) < 32 for c in text) else ""


def recording_label_matches(recording, proof, label):
    """Compare one exact recording label without coercing its result."""
    return recording.get(label) == getattr(proof, label)


def match_name(value: Any) -> str:
    return unicodedata.normalize("NFKC", label(value)).casefold()


def qualified_date(value: Any, precision: Any) -> str:
    text = str(value or "")
    patterns = {"year": r"\d{4}", "month": r"\d{4}-\d{2}", "day": r"\d{4}-\d{2}-\d{2}"}
    if not re.fullmatch(patterns.get(str(precision), r"(?!)"), text):
        return ""
    try:
        date.fromisoformat(text + {"year": "-01-01", "month": "-01", "day": ""}[str(precision)])
    except ValueError:
        return ""
    return text


@dataclass(frozen=True)
class ArtistImageIdentity:
    """Qualified primary-performer context, not a claim about other credits."""
    spotify_uri: str
    wikidata_id: str
    name: str
    musicbrainz_id: str

    def eligible(self):
        return bool(re.fullmatch(r'spotify:artist:[A-Za-z0-9]{22}',self.spotify_uri)
            and re.fullmatch(r'Q[1-9][0-9]*',self.wikidata_id)
            and MBID.fullmatch(self.musicbrainz_id) and label(self.name,160))


@dataclass(frozen=True)
class QualifiedSessionFact:
    """Normalized internal evidence; only text and attribution enter Broadcast."""

    key: str
    media_identity: str
    intent: str
    summaries: tuple[tuple[str, str], ...]
    contents: tuple[tuple[str, str], ...]
    provider: str
    source_url: str
    license: str
    observed_at: float
    recording_evidence: RecordingCreditEvidence | None = None
    display_core: DisplayFactCore | None = None
    artwork_subject_uri: str = ""
    artwork_album_uri: str = ""
    source_expires_at: float | None = None
    public_artist_qid: str = ""
    # Local lookup bindings, never public facts or model-processing authority.
    album_artist: str = ""
    album_artist_id: str = ""
    work_evidence: WorkComposerEvidence | None = None
    artwork_artist_identity: ArtistImageIdentity | None = None

    def copy_for(self, locale: str) -> tuple[str, str] | None:
        lang = locale[:2].lower()
        summary, content = dict(self.summaries).get(lang), dict(self.contents).get(lang)
        return (summary, content) if summary and content else None

    def _source_basis_valid(self):
        fields = {
            "album_release": ("Spotify", "album_story", "Spotify metadata display", r"https://open\.spotify\.com/album/[A-Za-z0-9]{22}"),
            "genre_context": ("Spotify", "genre_story", "Spotify metadata display", r"https://open\.spotify\.com/artist/[A-Za-z0-9]{22}"),
            "recording_credits": ("MusicBrainz", "track_context", "CC0-1.0", r"https://musicbrainz\.org/recording/" + MBID.pattern),
            "work_composers": ("MusicBrainz", "track_context", "CC0-1.0", r"https://musicbrainz\.org/work/" + MBID.pattern),
            "artist_begin": ("MusicBrainz", "artist_story", "CC0-1.0", r"https://musicbrainz\.org/artist/" + MBID.pattern),
            "artist_description": ("Wikidata", "artist_story", "CC0-1.0", r"https://www\.wikidata\.org/wiki/Q[1-9]\d*"),
        }
        qualified = fields.get(self.key)
        return bool(qualified is not None
                    and (self.provider, self.intent, self.license) == qualified[:3]
                    and re.fullmatch(qualified[3], self.source_url))

    def _original_source_current(self, now):
        return (self.source_expires_at is None or (not isinstance(self.source_expires_at, bool)
                and isinstance(self.source_expires_at, (int, float)) and math.isfinite(self.source_expires_at)
                and now < self.source_expires_at))

    def _genre_display_valid(self):
        return (self.key != "genre_context" or (self.source_expires_at is not None
                and self.display_core is not None and self.display_core.validates(self)))

    def eligible(self, media_identity: str, now: float) -> bool:
        # Relevance never widens the narrow visual-only producer contract.
        return bool(self._source_basis_valid()
                    and re.fullmatch(r"spotify:track:[A-Za-z0-9]{22}", media_identity)
                    and self.media_identity == media_identity
                    and 0 <= now - self.observed_at <= 1800
                    and self._original_source_current(now) and self._genre_display_valid())


@dataclass(frozen=True)
class SharedProducerFact(QualifiedSessionFact):
    """Closed derived visual relationship; not an ordinary provider field."""
    previous_evidence: RecordingCreditEvidence | None = None
    producer_id: str = ""

    @property
    def relation_key(self) -> tuple[str, str, str]:
        if self.recording_evidence is None or self.previous_evidence is None:
            return ("", "", "")
        a, b = sorted((self.recording_evidence.recording_id, self.previous_evidence.recording_id))
        return a, b, self.producer_id

    def _pair_valid(self, current, previous, media_identity, now):
        return bool(current is not None and previous is not None
                    and current.eligible(now) and previous.eligible(now)
                    and current.media_identity == media_identity and self.media_identity == media_identity
                    and current.media_identity != previous.media_identity
                    and current.recording_id != previous.recording_id)

    def _copy_matches(self, current, previous):
        a = next((p for p in current.producers if p.contributor_id == self.producer_id), None)
        b = next((p for p in previous.producers if p.contributor_id == self.producer_id), None)
        return bool(a and b and a == b and self.summaries == _shared_copy(current, previous, a)[0]
                    and self.contents == _shared_copy(current, previous, a)[1])

    def eligible(self, media_identity: str, now: float) -> bool:
        current, previous = self.recording_evidence, self.previous_evidence
        if (self.key != "shared_producer" or self.intent != "track_context"
                or (self.provider, self.license) != ("MusicBrainz", "CC0-1.0")
                or not self._pair_valid(current, previous, media_identity, now)
                or self.source_url != current.source_url or self.observed_at != current.observed_at):
            return False
        return self._copy_matches(current, previous)


def _shared_copy(current: RecordingCreditEvidence, previous: RecordingCreditEvidence,
                 producer: ProducerCredit) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    name, title, earlier = producer.name, current.title, previous.title
    titles = ["Shared producer", "Dezelfde producer", "Gemeinsamer Produzent",
              "Même producteur", "Mismo productor"]
    bodies = [
        f"{name} is credited as a producer on {title}, as on the earlier recording {earlier}.",
        f"{name} staat als producer vermeld bij {title}, net als bij de eerder besproken opname {earlier}.",
        f"{name} ist bei {title} als Produzent genannt, ebenso bei der zuvor besprochenen Aufnahme {earlier}.",
        f"{name} figure comme producteur sur {title}, comme sur l’enregistrement évoqué précédemment, {earlier}.",
        f"{name} figura como productor de {title}, al igual que en la grabación comentada antes, {earlier}.",
    ]
    return tuple(zip(LANGUAGES, titles)), tuple(zip(LANGUAGES, bodies))


def shared_producer_fact(current: RecordingCreditEvidence, previous: RecordingCreditEvidence,
                         now: float) -> SharedProducerFact | None:
    if not current.eligible(now) or not previous.eligible(now):
        return None
    candidates = sorted((p for p in current.producers if p in previous.producers),
                        key=lambda p: p.contributor_id)
    for producer in candidates:
        titles, bodies = _shared_copy(current, previous, producer)
        fact = SharedProducerFact("shared_producer", current.media_identity, "track_context",
            titles, bodies, "MusicBrainz", current.source_url, "CC0-1.0", current.observed_at,
            recording_evidence=current, previous_evidence=previous, producer_id=producer.contributor_id)
        if fact.eligible(current.media_identity, now):
            return fact
    return None


@dataclass(frozen=True)
class ProducerRecommendationFact(SharedProducerFact):
    """One optional revisit, based on an actually published earlier credit."""
    previous_moment_id: str = ''

    @property
    def recommended_media_identity(self):
        return self.previous_evidence.media_identity if self.previous_evidence else ''

    def eligible(self, media_identity, now):
        current, previous = self.recording_evidence, self.previous_evidence
        if (self.key != 'producer_recommendation' or self.intent != 'recommendation'
                or not re.fullmatch(r'moment-[0-9a-f]{32}', self.previous_moment_id)
                or current is None or previous is None):
            return False
        producer = next((p for p in current.producers if p.contributor_id == self.producer_id), None)
        if producer is None or (self.summaries, self.contents) != _recommendation_copy(current, previous, producer):
            return False
        titles, bodies = _shared_copy(current, previous, producer)
        proof = replace(self, key='shared_producer', intent='track_context', summaries=titles, contents=bodies)
        return SharedProducerFact.eligible(proof, media_identity, now)


def _recommendation_copy(current, previous, producer):
    titles = ('A connection to revisit', 'Een verbinding om te hernemen', 'Eine Verbindung zum Wiederentdecken',
              'Un lien à retrouver', 'Una conexión para retomar')
    bodies = (
        f'If you want to explore this connection, I suggest revisiting {previous.title}: {producer.name} is credited as producer there and on {current.title}.',
        f'Als je deze verbinding wilt verkennen, stel ik voor om {previous.title} nog eens op te zoeken: {producer.name} staat daar en bij {current.title} als producer vermeld.',
        f'Wenn du diese Verbindung erkunden möchtest, schlage ich vor, {previous.title} wieder aufzusuchen: {producer.name} ist dort und bei {current.title} als Produzent genannt.',
        f'Pour explorer ce lien, je te propose de retrouver {previous.title} : {producer.name} y est crédité à la production, comme sur {current.title}.',
        f'Si quieres explorar esta conexión, te propongo volver a {previous.title}: {producer.name} figura como productor allí y en {current.title}.')
    return tuple(zip(LANGUAGES, titles)), tuple(zip(LANGUAGES, bodies))


def producer_recommendation(relation, previous_moment_id, now):
    if type(relation) is not SharedProducerFact or not relation.eligible(relation.media_identity, now):
        return None
    producer = next(p for p in relation.recording_evidence.producers if p.contributor_id == relation.producer_id)
    titles, bodies = _recommendation_copy(relation.recording_evidence, relation.previous_evidence, producer)
    fact = ProducerRecommendationFact(**{**relation.__dict__, 'key':'producer_recommendation',
        'intent':'recommendation', 'summaries':titles, 'contents':bodies,
        'artwork_subject_uri':'', 'artwork_album_uri':'', 'previous_moment_id':previous_moment_id})
    return fact if fact.eligible(fact.media_identity, now) else None


@dataclass
class PublishedRecordingContext:
    """One Runtime's three observed tracks and published-only credit proofs."""
    observed_tracks: list[str] = field(default_factory=list)
    credits: dict[str, RecordingCreditEvidence] = field(default_factory=dict)
    used_relations: set[tuple[str, str, str]] = field(default_factory=set)
    connected_tracks: set[str] = field(default_factory=set)
    published_moment_ids: dict[str, str] = field(default_factory=dict)

    def observe(self, media_identity: str, now: float) -> None:
        if media_identity in self.observed_tracks:
            self.observed_tracks.remove(media_identity)
        self.observed_tracks.append(media_identity)
        self.observed_tracks[:] = self.observed_tracks[-3:]
        self.credits = {key: value for key, value in self.credits.items()
                        if key in self.observed_tracks and value.eligible(now)}
        self.published_moment_ids = {key: value for key, value in self.published_moment_ids.items() if key in self.credits}

    def commit(self, fact: QualifiedSessionFact, now: float, moment_id: str = '') -> None:
        evidence = fact.recording_evidence
        if (fact.key in {"recording_credits", "shared_producer"} and fact.eligible(fact.media_identity, now)
                and evidence and evidence.eligible(now) and evidence.media_identity == fact.media_identity
                and evidence.source_url == fact.source_url and evidence.observed_at == fact.observed_at
                and fact.media_identity in self.observed_tracks):
            self.credits[fact.media_identity] = evidence
            if re.fullmatch(r'moment-[0-9a-f]{32}', moment_id):
                self.published_moment_ids[fact.media_identity] = moment_id
        self.consume(fact, now)

    def consume(self, fact, now, *, semantic_accepted=False):
        # Semantic acceptance consumes a relation even when delivery is later
        # suppressed, without seeding a claim that its credit was discussed.
        if isinstance(fact, SharedProducerFact) and (semantic_accepted or fact.eligible(fact.media_identity, now)):
            self.used_relations.add(fact.relation_key)
            self.connected_tracks.add(fact.media_identity)

    @staticmethod
    def _current_proofs(facts, media_identity, now):
        return [f.recording_evidence for f in facts if f.key == "recording_credits"
                   and f.eligible(media_identity, now) and f.recording_evidence
                   and f.recording_evidence.media_identity == media_identity
                   and f.recording_evidence.source_url == f.source_url
                   and f.recording_evidence.observed_at == f.observed_at]

    def _published_relation(self, facts, current, previous, now):
        fact = shared_producer_fact(current, previous, now)
        if fact and fact.relation_key not in self.used_relations:
            original = next((f for f in facts if f.recording_evidence is current), None)
            return replace(fact, artwork_album_uri=getattr(original, "artwork_album_uri", ""))
        return None

    def candidate(self, facts: tuple[QualifiedSessionFact, ...], media_identity: str,
                  now: float) -> SharedProducerFact | None:
        if media_identity in self.connected_tracks:
            return None
        current = self._current_proofs(facts, media_identity, now)
        # Multiple conflicting proofs of the current recording fail closed.
        if not current or any(c != current[0] for c in current):
            return None
        for identity in reversed(self.observed_tracks):
            previous = self.credits.get(identity)
            if previous is not None:
                selected = self._published_relation(facts, current[0], previous, now)
                if selected is not None:
                    return selected
        return None

    def clear(self) -> None:
        self.observed_tracks.clear()
        self.credits.clear()
        self.used_relations.clear()
        self.connected_tracks.clear()
        self.published_moment_ids.clear()


ALBUM_CONTINUITY_FORMS = {
    "en": (
        "Another track from the edition mentioned earlier.",
        "Our earlier album note connects to this track: the edition is the same.",
        "Same edition, another track. Back to our album note:",
        "That edition returns here, with a different track.",
    ),
    "nl": (
        "Nog een nummer uit de eerder genoemde uitgave.",
        "Onze eerdere albumnotitie sluit aan bij dit nummer: het is dezelfde uitgave.",
        "Dezelfde uitgave, een ander nummer. Terug naar onze albumnotitie:",
        "Diezelfde uitgave komt weer langs, nu met een ander nummer.",
    ),
    "de": (
        "Ein weiterer Titel aus der zuvor erwähnten Ausgabe.",
        "Unsere frühere Albumnotiz passt zu diesem Titel: Es ist dieselbe Ausgabe.",
        "Dieselbe Ausgabe, ein anderer Titel. Zurück zu unserer Albumnotiz:",
        "Dieselbe Ausgabe ist wieder da, jetzt mit einem anderen Titel.",
    ),
    "fr": (
        "Un autre titre de l’édition présentée plus tôt.",
        "Ce titre vient de l’édition présentée plus tôt.",
        "Même édition, autre titre. Retour à notre note sur l’album :",
        "Cette même édition revient, avec un autre titre.",
    ),
    "es": (
        "Otro tema de la edición mencionada antes.",
        "Nuestra nota anterior sobre el álbum conecta con este tema: es la misma edición.",
        "La misma edición, otro tema. Volvemos a nuestra nota sobre el álbum:",
        "Vuelve esa misma edición, ahora con otro tema.",
    ),
}


def album_continuity_copy(current: QualifiedSessionFact, profile: int = 0
                          ) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """Authored framing; preserve the exact qualified catalog sentence."""
    return current.summaries, tuple(
        (lang, f"{ALBUM_CONTINUITY_FORMS[lang][profile]} {dict(current.contents)[lang]}")
        for lang in LANGUAGES
    )


def _qualified_album(fact: QualifiedSessionFact, now: float) -> bool:
    return bool(type(fact) is QualifiedSessionFact and fact.key == "album_release"
                and fact.eligible(fact.media_identity, now) and type(fact.display_core) is DisplayFactCore
                and fact.display_core.validates(fact)
                and fact.summaries == tuple((lang, fact.display_core.subject) for lang in LANGUAGES)
                and len(fact.summaries) == len(fact.contents) == len(LANGUAGES)
                and set(dict(fact.summaries)) == set(dict(fact.contents)) == set(LANGUAGES))


@dataclass(frozen=True)
class AlbumContinuityFact(QualifiedSessionFact):
    """Closed current-edition relationship, never historical Spotify recall."""
    current_album: QualifiedSessionFact | None = None
    previous_album: QualifiedSessionFact | None = None

    @property
    def relation_key(self) -> tuple[str, str, str]:
        if self.current_album is None or self.previous_album is None:
            return "", "", ""
        a, b = sorted((self.current_album.media_identity, self.previous_album.media_identity))
        return a, b, self.source_url

    def _pair_valid(self, current, previous, media_identity, now):
        return bool(current and previous and _qualified_album(current, now)
                    and _qualified_album(previous, now)
                    and current.media_identity == self.media_identity == media_identity
                    and current.media_identity != previous.media_identity
                    and current.source_url == previous.source_url == self.source_url
                    and current.display_core == previous.display_core)

    def eligible(self, media_identity: str, now: float) -> bool:
        current, previous = self.current_album, self.previous_album
        return bool(self._pair_valid(current, previous, media_identity, now)
                    and (self.key, self.intent, self.provider, self.license)
                        == ("album_continuity", "track_context", "Spotify", "Spotify metadata display")
                    and self.observed_at == current.observed_at
                    and self.display_core == current.display_core
                    and (self.summaries, self.contents) == album_continuity_copy(current))


@dataclass
class PublishedAlbumContext:
    """Bounded published-only edition proofs and non-evicting relation guards."""
    observed_tracks: list[str] = field(default_factory=list)
    albums: dict[str, QualifiedSessionFact] = field(default_factory=dict)
    used_relations: set[tuple[str, str, str]] = field(default_factory=set)
    connected_tracks: set[str] = field(default_factory=set)
    published_moment_ids: dict[str, str] = field(default_factory=dict)

    def observe(self, media_identity: str, now: float) -> None:
        if media_identity in self.observed_tracks:
            self.observed_tracks.remove(media_identity)
        self.observed_tracks.append(media_identity)
        self.observed_tracks[:] = self.observed_tracks[-3:]
        self.albums = {key: value for key, value in self.albums.items()
                       if key in self.observed_tracks and _qualified_album(value, now)}

    def commit(self, fact: QualifiedSessionFact, now: float) -> None:
        if (_qualified_album(fact, now) and fact.media_identity in self.observed_tracks
                and len(self.used_relations) < 6):
            self.albums[fact.media_identity] = fact
        elif (isinstance(fact, AlbumContinuityFact) and fact.eligible(fact.media_identity, now)
              and fact.media_identity in self.observed_tracks and len(self.used_relations) < 6):
            self.used_relations.add(fact.relation_key)
            self.connected_tracks.add(fact.media_identity)

    def _can_connect(self, media_identity):
        return (len(self.used_relations) < 6 and media_identity not in self.connected_tracks
                and media_identity in self.observed_tracks)

    @staticmethod
    def _current_proofs(facts, media_identity, now):
        return [f for f in facts if _qualified_album(f, now) and f.media_identity == media_identity]

    def _relation_candidate(self, current, previous, media_identity, now):
        summaries, contents = album_continuity_copy(current)
        fact = AlbumContinuityFact(
            "album_continuity", media_identity, "track_context", summaries, contents,
            "Spotify", current.source_url, "Spotify metadata display", current.observed_at,
            display_core=current.display_core, current_album=current, previous_album=previous,
            artwork_album_uri=current.artwork_album_uri)
        if fact.eligible(media_identity, now) and fact.relation_key not in self.used_relations:
            return fact
        return None

    def candidate(self, facts: tuple[QualifiedSessionFact, ...], media_identity: str,
                  now: float) -> AlbumContinuityFact | None:
        if not self._can_connect(media_identity):
            return None
        current = self._current_proofs(facts, media_identity, now)
        if not current or any(f != current[0] for f in current):
            return None
        for identity in reversed(self.observed_tracks):
            previous = self.albums.get(identity)
            if previous is None:
                continue
            selected = self._relation_candidate(current[0], previous, media_identity, now)
            if selected is not None:
                return selected
        return None

    def close_lines(self) -> None:
        self.albums.clear()

    def clear(self) -> None:
        self.observed_tracks.clear()
        self.albums.clear()
        self.used_relations.clear()
        self.connected_tracks.clear()


def _fact(
    key: str,
    catalog: dict[str, Any],
    intent: str,
    titles: list[str],
    bodies: list[str],
    provider: str,
    url: str,
    core: DisplayFactCore | None = None,
) -> QualifiedSessionFact:
    return QualifiedSessionFact(
        key,
        catalog["uri"],
        intent,
        tuple(zip(LANGUAGES, titles)),
        tuple(zip(LANGUAGES, bodies)),
        provider,
        url,
        "Spotify metadata display" if provider == "Spotify" else "CC0-1.0",
        time.monotonic(),
        display_core=core,
        artwork_album_uri=str(catalog.get("album_uri") or "") if re.fullmatch(
            r"spotify:album:[A-Za-z0-9]{22}", str(catalog.get("album_uri") or "")) else "",
    )


def _genre_bodies(genre: str, title: str, artist: str) -> list[str]:
    return [
        f"The genre context for {title} by {artist} is {genre}.",
        f"De genrecontext bij {title} van {artist} is {genre}.",
        f"Der Genrekontext zu {title} von {artist} ist {genre}.",
        f"Le contexte de genre de {title} par {artist} est {genre}.",
        f"El contexto de género de {title} de {artist} es {genre}.",
    ]


def _genre_current_source(evidence, media_identity):
    return (isinstance(evidence, dict) and evidence.get("source") == "spotify_playback_status"
            and evidence.get("backend") == "spotify_direct" and evidence.get("is_playing") is True
            and evidence.get("media_identity") == media_identity
            and re.fullmatch(r"spotify:track:[A-Za-z0-9]{22}", media_identity))


def _genre_observation_matches(evidence, media_identity, title, artist):
    return (_genre_current_source(evidence, media_identity)
            and evidence.get("title") == title and evidence.get("artist") == artist
            and label(title, 160) == title and label(artist, 160) == artist)


def _genre_deadline_current(deadline, now):
    return (not isinstance(deadline, bool) and isinstance(deadline, (int, float))
            and math.isfinite(deadline) and now < deadline <= now + 6 * 60 * 60)


def _genre_artist_fields_valid(ids, genres):
    return (isinstance(ids, (list, tuple)) and len(ids) == 1
            and isinstance(ids[0], str) and re.fullmatch(r"[A-Za-z0-9]{22}", ids[0])
            and isinstance(genres, (list, tuple)) and 0 < len(genres) <= 10)


def observed_genre_facts(evidence: Any, *, media_identity: str, title: str, artist: str) -> tuple[QualifiedSessionFact, ...]:
    """Reuse exact-ID current status evidence, never a name-search genre guess."""
    if not _genre_observation_matches(evidence, media_identity, title, artist):
        return ()
    ids, genres = evidence.get("artist_ids"), evidence.get("genres")
    now, deadline = time.monotonic(), evidence.get("genre_source_expires_at")
    if not _genre_deadline_current(deadline, now):
        return ()
    if not _genre_artist_fields_valid(ids, genres):
        return ()
    genre = next((value for value in genres if isinstance(value, str) and label(value, 160) == value), "")
    if not genre:
        return ()
    fact = _fact("genre_context", {"uri": media_identity}, "genre_story", [genre]*5,
        _genre_bodies(genre, title, artist), "Spotify", "https://open.spotify.com/artist/"+ids[0],
        DisplayFactCore("genre_context", genre, roles=(("track", (title,)), ("artist", (artist,))),
                        entity_type="ArtistGenre"))
    return (replace(fact, source_expires_at=min(deadline, fact.observed_at+1800)),)


def _album_with_performer(fact, catalog):
    ids = catalog.get('artist_ids')
    if (isinstance(ids, (list, tuple)) and len(ids) == 1
            and isinstance(ids[0], str) and re.fullmatch(r'[A-Za-z0-9]{22}', ids[0])
            and label(catalog.get('artist'), 160)):
        fact = replace(fact, album_artist=label(catalog['artist'], 160), album_artist_id=ids[0])
    return fact


def catalog_facts(catalog: dict[str, Any]) -> list[QualifiedSessionFact]:
    uri = str(catalog.get("uri") or "")
    if not re.fullmatch(r"spotify:track:[A-Za-z0-9]{22}", uri):
        return []
    album, album_uri = label(catalog.get("album_name")), str(catalog.get("album_uri") or "")
    released = qualified_date(catalog.get("release_date"), catalog.get("release_date_precision"))
    if not album or not released or not re.fullmatch(r"spotify:album:[A-Za-z0-9]{22}", album_uri):
        return []
    fact = _fact(
            "album_release",
            catalog,
            "album_story",
            [album] * 5,
            list(_album_release_bodies(album, released)),
            "Spotify",
            "https://open.spotify.com/album/" + album_uri.split(":")[-1],
            DisplayFactCore("album_release", album, date=released, precision=str(catalog.get("release_date_precision"))),
        )
    return [_album_with_performer(fact, catalog)]


def _public_artist_targets(relations):
    return [r.get("artist") for r in relations if isinstance(r, dict)
            and r.get("target-type") == "artist" and isinstance(r.get("artist"), dict)]


def _unique_public_artist_id(actors):
    ids = {a.get("id") for a in actors if isinstance(a.get("id"), str)}
    if (not actors or len(ids) != 1 or len(actors) != sum(isinstance(a.get("id"), str) for a in actors)
            or not MBID.fullmatch(next(iter(ids)))):
        return None
    return next(iter(ids))


def _active_public_wikidata_ids(relations):
    return {m[1] for r in relations if isinstance(r, dict) and r.get("type") == "wikidata"
            and isinstance(r.get("url"), dict) and not r.get("ended")
            and (m := re.fullmatch(r"https?://www\.wikidata\.org/wiki/(Q[1-9][0-9]*)",
                                  str(r["url"].get("resource") or "")))}


def _active_public_streaming_urls(relations):
    return {r["url"].get("resource") for r in relations if isinstance(r, dict)
            and r.get("type") in {"streaming", "free streaming"} and not r.get("ended")
            and isinstance(r.get("url"), dict)}


def _public_artist_linked_qid(person, relations, artist, mbid, resource):
    qids = _active_public_wikidata_ids(relations)
    links = _active_public_streaming_urls(relations)
    if (person.get("id") != mbid or match_name(person.get("name")) != match_name(artist)
            or person.get("type") not in {"Person", "Group"} or resource not in links or len(qids) != 1):
        return None
    return next(iter(qids))


def _public_identity_claims(entity, property_id):
    return {c.get("mainsnak", {}).get("datavalue", {}).get("value")
            for c in entity.get("claims", {}).get(property_id, [])
            if isinstance(c, dict) and c.get("rank") != "deprecated"}


def _public_catalog_artist_url(artist, spotify_id):
    if (not isinstance(spotify_id, str) or not re.fullmatch(r"[A-Za-z0-9]{22}", spotify_id)
            or not label(artist, 160)):
        return None
    return "https://open.spotify.com/artist/" + spotify_id


def _public_entity_matches(entity, qid, mbid, spotify_id):
    reciprocal = _public_identity_claims(entity, "P434")
    provider = _public_identity_claims(entity, "P1902")
    return (entity.get("id") == qid and reciprocal == {mbid}
            and (not provider or provider == {spotify_id}))


async def public_artist_identity(get, artist: str, spotify_id: str):
    """Exact provider URL and reciprocal public artist; no recording assertion.

    The caller supplies its existing guarded request owner/deadline. Catalogue
    names/IDs select the lookup locally; they are not model evidence.
    """
    resource = _public_catalog_artist_url(artist, spotify_id)
    if resource is None:
        return None
    data = await get("url", {"resource": resource, "inc": "artist-rels", "fmt": "json"})
    if data.get("resource") != resource or not isinstance(data.get("relations"), list):
        return None
    actors = _public_artist_targets(data["relations"])
    mbid = _unique_public_artist_id(actors)
    if mbid is None:
        return None
    person = await get("artist/" + mbid, {"fmt": "json", "inc": "url-rels"})
    relations = person.get("relations", [])
    if not isinstance(relations, list):
        return None
    qid = _public_artist_linked_qid(person, relations, artist, mbid, resource)
    if qid is None:
        return None
    entity = (await get("", {"action": "wbgetentities", "ids": qid,
        "props": "labels|descriptions|claims", "languages": "|".join(LANGUAGES),
        "format": "json", "maxlag": "5"}, wikidata=True)).get("entities", {}).get(qid, {})
    if not _public_entity_matches(entity, qid, mbid, spotify_id):
        return None
    return person, entity, qid


def _catalog_artist_lookup(catalog):
    artist_ids = catalog.get("artist_ids")
    artist_id = (artist_ids[0] if isinstance(artist_ids, (list, tuple))
                 and len(artist_ids) == 1 and isinstance(artist_ids[0], str) else "")
    original_catalog = dict(catalog)
    original_catalog["artist_ids"] = [artist_id] if artist_id else []
    return artist_id, original_catalog


def _recording_summary(recording, title, artist):
    credit = recording.get("artist-credit") or []
    names = [c.get("artist", {}).get("name") for c in credit if isinstance(c, dict)]
    if match_name(recording.get("title")) != match_name(title) or match_name(
        ", ".join(str(n) for n in names)
    ) != match_name(artist):
        return None
    recording_id = str(recording.get("id") or "")
    if not MBID.fullmatch(recording_id):
        return None
    return recording_id, credit


def _recording_detail_matches(detailed, recording_id, title, artist):
    if detailed.get("id") != recording_id or match_name(detailed.get("title")) != match_name(title):
        return False
    detailed_names = [c.get("artist", {}).get("name") for c in detailed.get("artist-credit", [])
                      if isinstance(c, dict)]
    return match_name(", ".join(str(n) for n in detailed_names)) == match_name(artist)


async def _resolved_recording(get, isrc, title, artist):
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}\d{7}", isrc):
        return None
    data = await get("isrc/" + isrc, {"fmt": "json", "inc": "artist-credits"})
    recordings = data.get("recordings") or []
    # A reused ISRC stays ambiguous even when one title looks close.
    if len(recordings) != 1 or not isinstance(recordings[0], dict):
        return None
    summary = _recording_summary(recordings[0], title, artist)
    if summary is None:
        return None
    recording_id, credit = summary
    detailed = await get("recording/" + recording_id,
        {"fmt": "json", "inc": "artist-credits+artist-rels+work-rels+work-level-rels"})
    if not _recording_detail_matches(detailed, recording_id, title, artist):
        return None
    return detailed, credit


def _recording_artist_qids(person):
    return {m.group(1) for r in person.get("relations", [])
            if isinstance(r, dict) and r.get("type") == "wikidata"
            and (m := re.fullmatch(r"https?://www.wikidata.org/wiki/(Q\d+)",
                                  str(r.get("url", {}).get("resource") or "")))}


async def _recording_artist_entity(get, person, artist_id):
    wikidata_ids = _recording_artist_qids(person)
    if len(wikidata_ids) != 1:
        return None
    qid = next(iter(wikidata_ids))
    entity_data = await get("", {"action": "wbgetentities", "ids": qid,
        "props": "labels|descriptions|claims", "languages": "|".join(LANGUAGES),
        "format": "json", "maxlag": "5"}, wikidata=True)
    entity = entity_data.get("entities", {}).get(qid, {})
    # This existing recording chain intentionally has its own claim shape rules.
    ids = {c.get("mainsnak", {}).get("datavalue", {}).get("value")
           for c in entity.get("claims", {}).get("P434", []) if c.get("rank") != "deprecated"}
    if entity.get("id") == qid and ids == {artist_id}:
        return entity, qid
    return None


def _with_recording_artist_identity(facts, catalog, person, entity, qid):
    # Only a reciprocal public identity admits further artist context.
    facts = [replace(f, public_artist_qid=qid)
             if f.key in {"artist_begin", "recording_credits", "work_composers"} else f for f in facts]
    fact = description_fact(catalog, entity, qid, person=person)
    if fact:
        facts.append(replace(fact, public_artist_qid=qid))
    image_identity = qualified_artist_image_identity(catalog, person, entity, qid)
    if image_identity is not None:
        facts = [replace(f, artwork_artist_identity=image_identity)
                 if f.key in {'artist_begin', 'artist_description', 'recording_credits', 'work_composers'}
                 else f for f in facts]
    return facts


async def _recording_artist_context(get, catalog, credit, artist, facts):
    if len(credit) != 1 or not isinstance(credit[0], dict):
        return facts
    artist_id = str(credit[0].get("artist", {}).get("id") or "")
    if not MBID.fullmatch(artist_id):
        return facts
    person = await get("artist/" + artist_id, {"fmt": "json", "inc": "url-rels"})
    if person.get("id") != artist_id or match_name(person.get("name")) != match_name(artist):
        return facts
    facts.extend(artist_facts(catalog, person))
    source = await _recording_artist_entity(get, person, artist_id)
    if source is None:
        return facts
    entity, qid = source
    return _with_recording_artist_identity(facts, catalog, person, entity, qid)


class SessionFactsResolver:
    """One HA-wide rate limiter, no persistent cache or personal source query."""

    def __init__(self, hass: Any) -> None:
        self.hass = hass
        self.lock = asyncio.Lock()
        self.backoff_until = 0.0

    async def _get(
        self, path: str, params: dict[str, str] | None = None, *, wikidata: bool = False,
        authorize=None,
    ) -> dict[str, Any]:
        async with self.lock:
            if authorize is not None:
                authorize()
            now = time.monotonic()
            if now < self.backoff_until:
                from .ask_dj.public_research import note_temporary_source_failure
                note_temporary_source_failure()
                return {}
            from . import musicbrainz_rate
            async def rate_guard():
                authorize()
            if not wikidata and not await musicbrainz_rate.admit(
                    rate_guard if authorize is not None else None):
                from .ask_dj.public_research import note_temporary_source_failure
                note_temporary_source_failure()
                return {}
            if authorize is not None:
                authorize()
            url = (
                "https://www.wikidata.org/w/api.php"
                if wikidata
                else "https://musicbrainz.org/ws/2/" + path
            )
            try:
                from aiohttp import ClientTimeout, ClientError
                from homeassistant.helpers.aiohttp_client import async_get_clientsession

                session = async_get_clientsession(self.hass)
                async with session.get(
                    url,
                    params=params or {"fmt": "json"},
                    headers={"User-Agent": USER_AGENT},
                    timeout=ClientTimeout(total=8),
                    allow_redirects=False,
                ) as response:
                    return await self._consume_response(response, wikidata, musicbrainz_rate, authorize)
            except (ValueError, OSError, ClientError, asyncio.TimeoutError):
                from .ask_dj.public_research import note_temporary_source_failure
                note_temporary_source_failure()
                return {}

    def _response_available(self, response, wikidata, musicbrainz_rate):
        if response.status in {429, 503}:
            from .ask_dj.public_research import note_temporary_source_failure
            note_temporary_source_failure()
            retry = response.headers.get("Retry-After", "60")
            if not wikidata:
                musicbrainz_rate.defer(retry)
            self.backoff_until = time.monotonic() + max(
                60, min(3600, int(retry) if retry.isdigit() else 60)
            )
            return False
        if response.status == 429 or response.status >= 500:
            from .ask_dj.public_research import note_temporary_source_failure
            note_temporary_source_failure()
        return response.status == 200

    async def _consume_response(self, response, wikidata, musicbrainz_rate, authorize):
        if not self._response_available(response, wikidata, musicbrainz_rate):
            return {}
        # Bound response size before parsing; never retain raw responses.
        if response.content_length and response.content_length > 512_000:
            return {}
        raw = bytearray()
        async for chunk in response.content.iter_chunked(16_384):
            raw.extend(chunk)
            if len(raw) > 512_000:
                return {}
        import json
        result = json.loads(raw)
        if authorize is not None:
            authorize()
        if isinstance(result, dict) and result.get("error"):
            self.backoff_until = time.monotonic() + 60
            return {}
        return result if isinstance(result, dict) else {}

    async def resolve(self, catalog: dict[str, Any], *, authorize=None,
                      credits_only: bool = False) -> tuple[QualifiedSessionFact, ...]:
        # Explicit detail uses the same public resolver and rate limiter, with
        # original request authority around every wait. Legacy Session callers
        # retain their existing complete fact lookup.
        async def get(*args, **kwargs):
            if authorize is not None:
                authorize()
                kwargs["authorize"] = authorize
            value = await self._get(*args, **kwargs)
            if authorize is not None:
                authorize()
            return value

        if authorize is not None:
            authorize()
        facts = catalog_facts(catalog)
        uri, title, artist = (
            str(catalog.get("uri") or ""),
            label(catalog.get("title")),
            label(catalog.get("artist")),
        )
        isrc = str(catalog.get("isrc") or "").upper()
        if not re.fullmatch(r"spotify:track:[A-Za-z0-9]{22}", uri) or not title or not artist:
            return tuple(facts)
        # Capture the local lookup selection before any source await. It may
        # qualify this artist only, never the observed recording or its work.
        artist_id, original_catalog = _catalog_artist_lookup(catalog)
        async def artist_only():
            if credits_only:
                return tuple(facts)
            identity = await public_artist_identity(get, artist, artist_id)
            if identity is None:
                return tuple(facts)
            person, entity, qid = identity
            artist_context = artist_facts(original_catalog, person)
            description = description_fact(original_catalog, entity, qid, person=person)
            if description is not None:
                artist_context.append(description)
            image = qualified_artist_image_identity(original_catalog, person, entity, qid)
            return tuple((*facts, *(replace(f, public_artist_qid=qid,
                artwork_artist_identity=image) for f in artist_context)))[:6]

        async with asyncio.timeout(35):
            source = await _resolved_recording(get, isrc, title, artist)
            if source is None:
                return await artist_only()
            detailed, credit = source
            facts.extend(recording_facts(catalog, detailed))
            facts.extend(work_facts(catalog, detailed))
            if credits_only:
                return tuple(facts[:6])
            facts = await _recording_artist_context(get, catalog, credit, artist, facts)
        return tuple(facts[:6])


def _display_credit_eligible(relation, roles):
    if (
        not isinstance(relation, dict)
        or relation.get("target-type") != "artist"
        or relation.get("type") not in roles
    ):
        return False
    if relation.get("type") == "producer" and (
        relation.get("attributes") or relation.get("attribute-values")
        or relation.get("ended") or not isinstance(relation.get("attributes", []), list)
    ):
        # Do not display a restricted producer as an unqualified producer.
        return False
    return True


def _recording_display_roles(recording, roles):
    collected: dict[str, list[str]] = {}
    for relation in recording.get("relations", []):
        if not _display_credit_eligible(relation, roles):
            continue
        name = label(relation.get("artist", {}).get("name"), 160)
        if name:
            collected.setdefault(relation["type"], []).append(name)
    return collected


def _credit_display_fact(catalog, recording, collected, roles):
    lines = []
    for index in range(5):
        lines.append(
            " · ".join(
                f"{roles[role][index]}: {', '.join(dict.fromkeys(names))}"
                for role, names in collected.items()
            )
        )
    if any(len(line) > 700 for line in lines):
        return None
    return _fact(
            "recording_credits",
            catalog,
            "track_context",
            [
                "Recording credits",
                "Wie werkten mee?",
                "Aufnahme-Credits",
                "Crédits de l’enregistrement",
                "Créditos de la grabación",
            ],
            lines,
            "MusicBrainz",
            "https://musicbrainz.org/recording/" + recording["id"],
            DisplayFactCore("recording_credits", roles=tuple((role,tuple(dict.fromkeys(names))) for role,names in collected.items())),
        )


def _register_producer(producers, conflicts, identity, name, relation):
    qualifications = relation.get("attributes", [])
    if qualifications or not isinstance(qualifications, list) or relation.get("attribute-values") or relation.get("ended"):
        conflicts.add(identity)
        return
    producer = ProducerCredit(identity, name)
    if not producer.eligible() or (identity in producers and producers[identity] != producer):
        conflicts.add(identity)
    else:
        producers[identity] = producer


def _recording_producers(recording):
    producers: dict[str, ProducerCredit] = {}
    conflicts: set[str] = set()
    for relation in recording.get("relations", []):
        if not isinstance(relation, dict) or relation.get("target-type") != "artist" or relation.get("type") != "producer":
            continue
        artist = relation.get("artist")
        if not isinstance(artist, dict):
            continue
        identity, name = str(artist.get("id") or ""), label(artist.get("name"), 160)
        if not MBID.fullmatch(identity):
            continue
        _register_producer(producers, conflicts, identity, name, relation)
    return producers, conflicts


def _proof_recording_artist_names(recording):
    return [c.get("artist", {}).get("name") for c in recording.get("artist-credit", [])
                       if isinstance(c, dict) and isinstance(c.get("artist"), dict)]


def _proof_matches_recording(proof, catalog, recording, fact):
    recording_names = _proof_recording_artist_names(recording)
    return (proof.eligible(fact.observed_at)
            and match_name(recording.get("title")) == match_name(catalog.get("title"))
            and match_name(", ".join(str(n) for n in recording_names)) == match_name(catalog.get("artist")))


def _with_recording_proof(catalog, recording, fact, producers, conflicts):
    proof = RecordingCreditEvidence(str(recording.get("id") or ""), str(catalog.get("uri") or ""),
        label(catalog.get("title"), 160), tuple(producers[key] for key in sorted(producers) if key not in conflicts),
        fact.source_url, fact.observed_at)
    if _proof_matches_recording(proof, catalog, recording, fact):
        fact = replace(fact, recording_evidence=proof)
    return fact


def recording_facts(
    catalog: dict[str, Any], recording: dict[str, Any]
) -> list[QualifiedSessionFact]:
    roles = CREDIT_ROLES
    collected = _recording_display_roles(recording, roles)
    if not collected:
        return []
    fact = _credit_display_fact(catalog, recording, collected, roles)
    if fact is None:
        return []
    producers, conflicts = _recording_producers(recording)
    fact = _with_recording_proof(catalog, recording, fact, producers, conflicts)
    return [fact]


def artist_facts(catalog: dict[str, Any], person: dict[str, Any]) -> list[QualifiedSessionFact]:
    begin = str(person.get("life-span", {}).get("begin") or "")
    precision = {4: "year", 7: "month", 10: "day"}.get(len(begin), "")
    if not qualified_date(begin, precision) or person.get("type") not in {"Person", "Group"}:
        return []
    artist = label(person.get("name"))
    person_copy = list(_person_begin_bodies(artist, begin))
    group_copy = list(_group_begin_bodies(artist, begin))
    facts = [
        _fact(
            "artist_begin",
            catalog,
            "artist_story",
            [artist] * 5,
            person_copy if person["type"] == "Person" else group_copy,
            "MusicBrainz",
            "https://musicbrainz.org/artist/" + person["id"],
            DisplayFactCore("artist_begin", artist, date=begin, precision=precision, entity_type=person["type"]),
        )
    ]

    uri = _artist_spotify_uri(catalog, person)
    return [replace(f, artwork_subject_uri=uri) for f in facts] if uri else facts


def _artist_image_streaming_urls(person):
    return {r.get("url", {}).get("resource") for r in person.get("relations", [])
             if isinstance(r, dict) and r.get("type") in {"streaming", "free streaming"}
             and not r.get("ended")}


def _artist_spotify_uri(catalog, person):
    """Reuse an explicit provider cross-reference; never search by name."""
    artist_ids = catalog.get("artist_ids") or []
    links = _artist_image_streaming_urls(person)
    exact = {i for i in artist_ids if isinstance(i, str) and re.fullmatch(r"[A-Za-z0-9]{22}", i)
             and "https://open.spotify.com/artist/" + i in links}
    return "spotify:artist:" + next(iter(exact)) if len(exact) == 1 else ""



def _artist_image_qids(person):
    return {m[1] for r in person.get('relations',[]) if isinstance(r,dict) and r.get('type')=='wikidata'
          and (m:=re.fullmatch(r'https?://www\.wikidata\.org/wiki/(Q[1-9][0-9]*)',str(r.get('url',{}).get('resource') or '')))}


def _artist_image_binding_valid(value, *, entity, qid, qids, reciprocal, person, catalog, provider, uri):
    return (value.eligible() and entity.get('id') == qid and qids == {qid}
            and reciprocal == {value.musicbrainz_id} and person.get('type') in {'Person', 'Group'}
            and match_name(person.get('name')) == match_name(catalog.get('artist'))
            and (not provider or provider == {uri.rsplit(':', 1)[-1]}))


def qualified_artist_image_identity(catalog,person,entity,qid):
    """Exact provider artist cross-reference plus reciprocal public identity."""
    if not all(isinstance(v,dict) for v in (catalog,person,entity)):
        return None
    uri=_artist_spotify_uri(catalog,person)
    reciprocal = _public_identity_claims(entity, 'P434')
    provider = _public_identity_claims(entity, 'P1902')
    qids = _artist_image_qids(person)
    value=ArtistImageIdentity(uri,str(qid),label(person.get('name'),160),str(person.get('id') or ''))
    if not _artist_image_binding_valid(value, entity=entity, qid=qid, qids=qids,
            reciprocal=reciprocal, person=person, catalog=catalog, provider=provider, uri=uri):
        return None
    return value


def _description_artwork(fact, catalog, entity, qid, person):
    source_ids = _public_identity_claims(entity, "P1902")
    ids = set(catalog.get("artist_ids") or [])
    if len(source_ids) == 1 and source_ids.issubset(ids):
        identifier = next(iter(source_ids))
        if isinstance(identifier, str) and re.fullmatch(r"[A-Za-z0-9]{22}", identifier):
            fact = replace(fact, artwork_subject_uri="spotify:artist:" + identifier)
    elif not source_ids and isinstance(person, dict):
        identity=qualified_artist_image_identity(catalog,person,entity,qid)
        if identity is not None:
            fact=replace(fact,artwork_subject_uri=identity.spotify_uri)
    return fact


def description_fact(
    catalog: dict[str, Any], entity: dict[str, Any], qid: str,
    *, person: dict[str, Any] | None = None,
) -> QualifiedSessionFact | None:
    descriptions = entity.get("descriptions", {})
    texts = [label(descriptions.get(lang, {}).get("value"), 400) for lang in LANGUAGES]
    if not any(texts):
        return None
    artist = label(catalog.get("artist"))
    # Missing translations suppress this card in that locale; never show English as Dutch.
    fact = _fact(
        "artist_description",
        catalog,
        "artist_story",
        [artist if text else "" for text in texts],
        texts,
        "Wikidata",
        "https://www.wikidata.org/wiki/" + qid,
    )

    return _description_artwork(fact, catalog, entity, qid, person)


def _recording_performance_work(recording):
    works = [
        r.get("work")
        for r in recording.get("relations", [])
        if isinstance(r, dict)
        and r.get("target-type") == "work"
        and r.get("type") == "performance"
        and isinstance(r.get("work"), dict)
    ]
    if len(works) != 1:
        return None
    work = works[0]
    work_id = str(work.get("id") or "")
    if not MBID.fullmatch(work_id):
        return None
    return work, work_id


def _work_display_composers(work):
    composers = list(
        dict.fromkeys(
            label(r.get("artist", {}).get("name"), 160)
            for r in work.get("relations", [])
            if isinstance(r, dict)
            and r.get("target-type") == "artist"
            and r.get("type") == "composer"
        )
    )
    composers = [name for name in composers if name]
    if not composers or len(composers) > 8:
        return None
    return composers


def _work_display_fact(catalog, work_id, composers):
    names = ", ".join(composers)
    return _fact(
            "work_composers",
            catalog,
            "track_context",
            [
                "Behind the composition",
                "Achter de compositie",
                "Hinter der Komposition",
                "Derrière la composition",
                "Detrás de la composición",
            ],
            composer_fact_bodies(names),
            "MusicBrainz",
            "https://musicbrainz.org/work/" + work_id,
            DisplayFactCore("work_composers", roles=(("composer",tuple(composers)),)),
        )


def _work_credit_unrestricted(credit, relation):
    return (credit.eligible() and isinstance(relation.get('attributes', []), list)
            and not relation.get('attributes') and not relation.get('attribute-values')
            and not relation.get('ended'))


def _work_source_credits(work):
    credits=[]
    for relation in work.get('relations',[]):
        if not isinstance(relation,dict) or relation.get('target-type')!='artist' or relation.get('type')!='composer':
            continue
        actor=relation.get('artist') or {}
        credit=ComposerCredit(str(actor.get('id') or ''),label(actor.get('name'),160))
        if not _work_credit_unrestricted(credit, relation):
            return None
        credits.append(credit)
    return credits


def _with_work_proof(catalog, recording, work_id, fact, credits, composers):
    proof=WorkComposerEvidence(str(recording.get('id') or ''),work_id,fact.media_identity,
        tuple(credits),fact.source_url,fact.observed_at)
    recording_names = _proof_recording_artist_names(recording)
    if (proof.eligible(fact.observed_at)
            and tuple(c.name for c in credits)==tuple(composers)
            and match_name(recording.get('title'))==match_name(catalog.get('title'))
            and match_name(', '.join(str(n) for n in recording_names))==match_name(catalog.get('artist'))):
        fact=replace(fact,work_evidence=proof)
    return fact


def work_facts(catalog: dict[str, Any], recording: dict[str, Any]) -> list[QualifiedSessionFact]:
    selected = _recording_performance_work(recording)
    if selected is None:
        return []
    work, work_id = selected
    composers = _work_display_composers(work)
    if composers is None:
        return []
    fact = _work_display_fact(catalog, work_id, composers)
    credits = _work_source_credits(work)
    if credits is None:
        return [fact]
    return [_with_work_proof(catalog, recording, work_id, fact, credits, composers)]


def session_facts_resolver(hass: Any) -> SessionFactsResolver:
    data = hass.data.setdefault("djconnect", {})
    if "session_facts_resolver" not in data:
        data["session_facts_resolver"] = SessionFactsResolver(hass)
    return data["session_facts_resolver"]
