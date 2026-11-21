"""Pure source/purpose qualification within the existing passive projection.

No research, narration, state mutation or second opportunity/Planner.
"""
from datetime import datetime
import math
import re
import time
from urllib.parse import parse_qs, unquote, urlsplit


SOURCE_FIELDS = {'provider', 'title', 'url', 'kind', 'language', 'fetched_at',
                 'expires_at', 'license', 'revision_url', 'wikidata_id',
                 'content_hash', 'claim_scope'}
WIKIPEDIA_HOSTS = {f'{language}.wikipedia.org' for language in ('en', 'nl', 'de', 'fr', 'es')}


def status(reason, state='unavailable'):
    return {'state': state, 'reason': reason}


def _passive_source_shape(source, public_url):
    if (not isinstance(source, dict) or set(source) != SOURCE_FIELDS
            or source.get('kind') != 'source' or not public_url(source.get('url'))
            or source.get('language') not in {'en', 'nl', 'de', 'fr', 'es'}
            or not isinstance(source.get('title'), str) or not source['title']
            or source.get('claim_scope') != 'fetched_public_music_reference'
            or not re.fullmatch('[0-9a-f]{64}', source.get('content_hash', ''))):
        return False
    return True


def _passive_wikipedia_reference(source, url, public_url):
    if not public_url(source['revision_url']):
        return False
    revision = urlsplit(source['revision_url'])
    query = parse_qs(revision.query)
    if (url.hostname not in WIKIPEDIA_HOSTS or not url.path.startswith('/wiki/')
            or revision.hostname != url.hostname or revision.path != '/w/index.php'
            or not re.fullmatch('[1-9][0-9]*', query.get('oldid', [''])[0])
            or unquote(url.path[6:]).replace('_', ' ') != source['title'].replace('_', ' ')
            or ('title' in query and query['title'] != [source['title']])):
        return False
    return True


def _passive_cc0_reference(source):
    if not (re.fullmatch(r'https://musicbrainz\.org/(artist|recording|release-group)/[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}', source['url'])
            if source['provider'] == 'MusicBrainz' else
            re.fullmatch(r'https://www\.wikidata\.org/wiki/Q[1-9][0-9]*', source['url'])):
        return False
    return True


def _passive_source_policy(source, url, public_url):
    if source['provider'] == 'Wikipedia' and source['license'] == 'CC-BY-SA-4.0':
        return 'wikipedia' if _passive_wikipedia_reference(source, url, public_url) else None
    if source['provider'] in {'MusicBrainz', 'Wikidata'} and source['license'] == 'CC0-1.0':
        return 'cc0' if _passive_cc0_reference(source) else None
    return None  # Generic web references have no passive-purpose permission.


def _qualified_passive_source(source, public_url):
    if not _passive_source_shape(source, public_url):
        return None
    try:
        expiry = datetime.fromisoformat(source['expires_at'])
        if expiry.tzinfo is None or not time.time() < expiry.timestamp():
            return None
        url = urlsplit(source['url'])
        return _passive_source_policy(source, url, public_url)
    except (ValueError, TypeError, KeyError, OverflowError):
        return None


def researched_sources(moment, now):
    """Sealed full copy plus EACH source's explicit passive-purpose policy."""
    from .public_artist_narration import admitted, sources_for
    from .ask_dj.public_research import public_url
    if not admitted(moment, now):
        return None
    sources = sources_for(moment)
    if not 1 <= len(sources) <= 3:
        return None
    wikipedia = False
    for source in sources:
        policy = _qualified_passive_source(source, public_url)
        if policy is None:
            return None
        if policy == 'wikipedia':
            wikipedia = True
    return sources if wikipedia else None


def _passive_source_basis(moment, researched):
    fact = moment.source_fact
    cc0 = not researched and fact is not None and fact.provider in {'MusicBrainz', 'Wikidata'} and fact.license == 'CC0-1.0'
    authored = fact is None and moment.source_references == ('session_direction',)
    return cc0, authored


def _passive_research(moment, now, projection_version=None):
    from .public_artist_narration import ResearchMomentAcceptance
    researched = type(moment.narration_acceptance) is ResearchMomentAcceptance
    sources = None
    if researched:
        if projection_version == 1:
            return researched, None, 'representation_not_supported'
        sources = researched_sources(moment, now)
        if sources is None:
            return researched, None, 'source_not_qualified'
    return researched, sources, None


def _passive_body(moment, boundary):
    return {'moment_id': moment.moment_id, 'published_at': boundary.published_at,
            'text': moment.content, 'persona': moment.presentation_intent.dj_persona.value,
            'source_attribution': dict(moment.source_attribution)}


def _passive_usage_basis(sources, cc0):
    return ('public_artist_narration_v1' if sources else
            'cc0_facts_authored_expression' if cc0 else 'runtime_authored_direction')


def _passive_rights():
    return {'passive_cache': True, 'os_snapshot': True,
            'external_relay': False, 'watch_replication': False}


def _attach_passive_research(body, sources):
    if sources:
        body['sources'] = sources
        body['expression_license'] = {'id': 'CC-BY-SA-4.0',
            'url': 'https://creativecommons.org/licenses/by-sa/4.0/',
            'adapted': True, 'attribution_required': True}


def _current_publication_reason(moment, boundary, admission, prior_reason):
    if (not boundary or admission.get('qualification') != 'qualified'
            or not (admission.get('current_display_allowed') or admission.get('active_flow_display_allowed'))
            or moment.presentation_intent.visibility.value == 'owner_only' or not moment.content):
        return prior_reason or ('original_deadline_expired' if admission.get('qualification') == 'expired'
                else 'source_not_qualified')
    return None


def _short_passive_deadline(moment, admission, boundary, now):
    try:
        deadline = datetime.fromisoformat(admission['display_expires_at'])
        valid = (deadline.tzinfo is not None and math.isfinite(now)
                 and boundary.published_monotonic <= now < boundary.published_monotonic + min(
                     120, moment.presentation_intent.maximum_duration_seconds)
                 and time.time() < deadline.timestamp())
    except (TypeError, ValueError, KeyError, OverflowError):
        valid = False
    return deadline if valid else None


def _current_passive_candidate(moment, admission, boundary, now, projection_version, prior_reason):
    reason = _current_publication_reason(moment, boundary, admission, prior_reason)
    if reason is not None:
        return None, reason
    if len(moment.content) > 640:
        return None, 'copy_too_long'
    researched, sources, reason = _passive_research(moment, now, projection_version)
    if reason is not None:
        return None, reason
    cc0, authored = _passive_source_basis(moment, researched)
    if not (cc0 or authored or sources):
        return None, 'source_not_qualified'
    deadline = _short_passive_deadline(moment, admission, boundary, now)
    if deadline is None:
        return None, 'original_deadline_expired'
    body = {**_passive_body(moment, boundary),
            'usage_basis': _passive_usage_basis(sources, cc0), 'expires_at': deadline.isoformat()}
    if projection_version in (2, 3):
        body['rights'] = _passive_rights()
    _attach_passive_research(body, sources)
    return body, None


def contribution(broadcast, now, *, projection_version=1):
    """Select the original newest eligible publication; Silence is a barrier."""
    if broadcast.content_pending or broadcast.content_current_withdrawn:
        return None, status('source_not_qualified')
    if broadcast.state.selected_presence == 'music_only':
        return None, status('presence_music_only', 'suppressed')
    admissions = {a['moment_id']: a for a in broadcast.native_delivery()['admissions']}
    reason = None
    for moment in reversed(broadcast.state.dj_moments):
        if moment.moment_type.value == 'silence':
            return None, status('intentional_silence', 'suppressed')
        admission = admissions.get(moment.moment_id, {})
        boundary = broadcast._moment_delivery_boundaries.get(moment.moment_id)
        body, unavailable_reason = _current_passive_candidate(moment, admission, boundary, now, projection_version, reason)
        if body is not None:
            return body, status('qualified', 'available')
        reason = reason or unavailable_reason
    return None, status(reason or 'no_publication')


def _retained_publication_reason(moment, boundary, admission):
    if (not boundary or admission.get('qualification') != 'qualified'
            or not admission.get('active_flow_display_allowed')
            or moment.presentation_intent.visibility.value == 'owner_only' or not moment.content):
        return 'source_not_qualified'
    return None


def _retained_source_bounds(boundary, admission, cc0, sources):
    wall = time.time()
    published = datetime.fromisoformat(boundary.published_at)
    limits = [datetime.fromisoformat(boundary.utc_at(boundary.published_monotonic + 1800))]
    source_expiry = admission.get('source_expires_at')
    if (cc0 or sources) and not source_expiry:
        return None
    if source_expiry:
        limits.append(datetime.fromisoformat(source_expiry))
    if sources:
        limits.extend(datetime.fromisoformat(s['expires_at']) for s in sources)
    if any(d.tzinfo is None for d in [published, *limits]):
        return None
    return wall, published, min(limits)


def _retained_snapshot_deadline(broadcast, boundary, now, wall, published, retained):
    observed_mono, observed_wall = broadcast.passive_state_observed
    clocks = (wall, now, boundary.published_monotonic, published.timestamp(),
              observed_mono, observed_wall, retained.timestamp())
    if (not all(type(v) in (int, float) and math.isfinite(v) for v in clocks)
            or not boundary.published_monotonic <= now < boundary.published_monotonic + 1800
            or not published.timestamp() <= wall < retained.timestamp()):
        return None, status('original_deadline_expired')
    if (not observed_mono <= now < observed_mono + 120
            or not 0 < observed_wall <= wall < observed_wall + 120):
        return None, status('original_snapshot_expired', 'stale')
    return min(retained.timestamp(), observed_wall + 120), None


def _retained_passive_deadline(broadcast, boundary, admission, cc0, sources, now):
    try:
        bounds = _retained_source_bounds(boundary, admission, cc0, sources)
        if bounds is None:
            return None, None, status('source_not_qualified')
        wall, published, retained = bounds
        expiry, reason = _retained_snapshot_deadline(broadcast, boundary, now, wall, published, retained)
        return retained, expiry, reason
    except (ValueError, TypeError, KeyError, OverflowError, OSError):
        return None, None, status('source_not_qualified')


def _retained_passive_candidate(broadcast, moment, admission, boundary, now):
    reason = _retained_publication_reason(moment, boundary, admission)
    if reason is not None:
        return None, status(reason)
    if len(moment.content) > 640:
        return None, status('copy_too_long')
    researched, sources, reason = _passive_research(moment, now)
    if reason is not None:
        return None, status(reason)
    cc0, authored = _passive_source_basis(moment, researched)
    if not (cc0 or authored or sources):
        return None, status('source_not_qualified')
    retained, expiry, reason = _retained_passive_deadline(broadcast, boundary, admission, cc0, sources, now)
    if reason is not None:
        return None, reason
    from datetime import UTC
    body = {**_passive_body(moment, boundary), 'purpose': 'retained_latest',
            'usage_basis': _passive_usage_basis(sources, cc0),
            'retained_expires_at': retained.isoformat(),
            'expires_at': datetime.fromtimestamp(expiry, UTC).isoformat(),
            'rights': _passive_rights()}
    _attach_passive_research(body, sources)
    return body, status('qualified', 'available')


def retained_latest(broadcast, now):
    """One original public publication, separately consented; no older fallback."""
    if broadcast.content_pending or broadcast.content_current_withdrawn:
        return None, status('source_not_qualified')
    if broadcast.state.selected_presence == 'music_only':
        return None, status('presence_music_only', 'suppressed')
    if not broadcast.state.dj_moments:
        return None, status('no_publication')
    moment = broadcast.state.dj_moments[-1]
    if moment.moment_type.value == 'silence':
        return None, status('intentional_silence', 'suppressed')
    admission = next((a for a in broadcast.native_delivery()['admissions']
                      if a['moment_id'] == moment.moment_id), {})
    boundary = broadcast._moment_delivery_boundaries.get(moment.moment_id)
    return _retained_passive_candidate(broadcast, moment, admission, boundary, now)
