"""Selected-contribution exploration on the existing Ask DJ read boundary."""
from __future__ import annotations

import re
import math

MORE_TEXT = {
    "en": "Tell me more",
    "nl": "Vertel meer",
    "de": "Erzähl mir mehr",
    "fr": "Dis-m’en plus",
    "es": "Cuéntame más",
}
ANGLES = {
    "age": "musician age birth date or band existence",
    "biography": "music biography documented history",
    "members": "band members interview",
    "live_history": "live performance concert history",
    "recording": "recording studio interview",
    "composition": "songwriting composition interview",
    "production": "record producer studio interview",
    "discography": "albums discography official",
    "current_events": "official concerts tour current dates",
}


def band_age_question(research, language, *, question="", age_target=""):
    """Clarify a source-identified group, never infer a person's age or birth date."""
    # An explicit selection of band duration/founding resolves the ambiguity;
    # it is still not evidence of the founding date or an uninterrupted career.
    if (re.fullmatch(r'(?:band|the band|de band|die band|le groupe|la banda)[.!? ]*', question, re.I)
            or re.search(r'hoe lang.*bestaat|how long.*(?:existed|exist)|wanneer.*opgericht|when.*(?:formed|founded)|wann.*gegründet|quand.*fondé|cuándo.*fundad', question, re.I)):
        return None
    from datetime import UTC, datetime
    from .biographical_dates import _group_source, _UNSAFE
    from .public_research import safe_subject, _sentences
    if not isinstance(research, dict):
        return None
    group = safe_subject(research.get("resolved_public_subject"), qualified=True)
    if not group or len(group) > 120 or not isinstance(research.get("sources"), list):
        return None
    found = False
    # The older biography receipt's group lens was only a prerequisite before
    # independent factual review. A local clarification needs its own direct
    # positive classification, never a later mention of a band in a film/book.
    descriptor = (r"(?:American|Belgian|Dutch|English|British|German|French|Spanish|Canadian|Irish|"
                  r"Australian|Swedish|Norwegian|Finnish|Danish|Scottish|Welsh|Italian|Japanese|"
                  r"Icelandic|New Zealand|South African|rock|pop|alternative|indie|electronic|folk|"
                  r"jazz|punk|metal|soul|hip-hop|hip hop|synth-pop|progressive|experimental)")
    classification = (re.escape(group) + r"\s+(?:is|was|are|were)\s+(?:a|an)\s+"
                      + rf"(?:{descriptor}\s+){{0,5}}(?:band|(?:music|musical|rock|pop|jazz|hip-hop) group)"
                      + r"(?=\.|,\s|\s+(?:led|formed|founded|from|based|consisting)\b)")
    for source in research["sources"]:
        if (not isinstance(source, dict) or source.get('language') != 'en'
                or not _group_source(source, group)):
            continue
        lead = _sentences(source['untrusted_excerpt'])[0]
        if _UNSAFE.search(lead) or not re.match(classification, lead, re.I):
            continue
        try:
            expiry = datetime.fromisoformat(source["expires_at"])
            found = expiry.tzinfo is not None and expiry > datetime.now(UTC)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if found:
            break
    if not found:
        return None
    if age_target == "band_duration":
        return None
    if age_target == "person_age":
        return {"en": "Which musician do you mean?", "nl": "Welke muzikant bedoel je?",
                "de": "Welchen Musiker meinst du?", "fr": "De quel musicien parles-tu ?",
                "es": "¿A qué músico te refieres?"}.get(language, "Which musician do you mean?")
    copy = {
        "en": "Do you mean how long the band {group} has existed, or the age of a particular musician?",
        "nl": "Bedoel je hoe lang de band {group} bestaat, of de leeftijd van een specifieke muzikant?",
        "de": "Meinst du, wie lange es die Band {group} gibt, oder das Alter eines bestimmten Musikers?",
        "fr": "Tu veux savoir depuis combien de temps le groupe {group} existe, ou l’âge d’un musicien en particulier ?",
        "es": "¿Te refieres a cuánto tiempo lleva existiendo la banda {group}, o a la edad de un músico en concreto?",
    }
    return copy.get(language, copy["en"]).format(group=group)


def captured_age_pending(turn):
    """Validate the original RAM-only clarification and user-named reference."""
    from .dialogue import DialogueError, PublicQueryReference
    pending = turn.pending_at_start
    if not isinstance(pending, dict) or pending.get("type") != "public_age_clarification":
        return None
    reference = turn.public_reference_at_start
    keys = {"type", "stage", "subject", "scope", "thread_id", "generation",
            "read_context_revision", "public_request_hash", "request_hash", "source_request_hashes", "created_at", "deadline"}
    hashes = pending.get("source_request_hashes")
    if (set(pending) != keys or pending.get("stage") not in {"choose_scope", "choose_person"}
            or any(type(pending.get(k)) not in (int, float) or not math.isfinite(pending[k]) for k in ("created_at", "deadline"))
            or pending["deadline"] != pending["created_at"] + 120
            or not pending["created_at"] <= turn.history.dialogue.clock() < pending["deadline"]
            or pending.get("scope") != turn.scope or pending.get("thread_id") != turn.thread_id
            or pending.get("generation") != turn.generation
            or pending.get("read_context_revision") != turn.read_context_revision
            or turn.frame.generation != turn.generation
            or turn.frame.read_context_revision != turn.read_context_revision
            or turn.frame.pending is not pending
            or turn.frame.pending_revision != turn.pending_revision_at_start
            or type(reference) is not PublicQueryReference
            or turn.frame.public_query_reference is not reference
            or turn.frame.public_query_revision != turn.public_reference_revision_at_start
            or reference.scope != turn.scope or reference.thread_id != turn.thread_id
            or reference.subject != pending.get("subject")
            or reference.request_hash != pending.get("public_request_hash")
            or type(hashes) is not list or not 1 <= len(hashes) <= 64
            or any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h)
                   for h in [pending.get("public_request_hash"), pending.get("request_hash"), *hashes])):
        raise DialogueError("conversation_context_changed", 409)
    return pending


def _age_completion_valid(turn, pending):
    return (pending["scope"] == turn.scope and pending["thread_id"] == turn.thread_id
            and pending["generation"] == turn.generation
            and pending["read_context_revision"] == turn.read_context_revision
            and pending["created_at"] <= turn.history.dialogue.clock() < pending["deadline"]
            and turn.public_age_completion_revision is not None
            and turn.frame.pending_revision == turn.public_age_completion_revision
            and turn.frame.pending is turn.public_age_completion_pending
            and turn.frame.public_query_reference is turn.public_age_completion_reference
            and turn.frame.public_query_revision == turn.public_age_completion_reference_revision
            and turn.frame.current_client_id == turn.client_id
            and turn.frame.generation == turn.generation
            and turn.frame.read_context_revision == turn.read_context_revision)


def bind_age_pending(turn):
    """Consume progress only after successful common-owner completion."""
    from copy import deepcopy
    from .dialogue import DialogueError
    pending = captured_age_pending(turn)
    if pending is None:
        raise DialogueError("conversation_context_changed", 409)
    original = deepcopy(pending)
    def validate():
        if _age_completion_valid(turn, original):
            return
        if captured_age_pending(turn) is not pending or pending != original:
            raise DialogueError("conversation_context_changed", 409)
    validate()
    turn.consume_public_age_pending = True
    turn.source_request_hashes.update([pending["request_hash"], pending["public_request_hash"],
                                       *pending["source_request_hashes"]])
    turn.effect_validators.append(validate)
    turn.delivery_validators.append(validate)


def stage_age_pending(turn, subject, text, *, person=False):
    """Stage source-qualified choice, without creating implicit public authority."""
    from .dialogue import DialogueError, PublicQueryReference
    from ..ask_dj_history import _request_hash
    reference = turn.public_reference_at_start
    current_hash = _request_hash(turn.scope, turn.client_id)
    if turn.public_query_candidate == subject and named_in_question(subject, text):
        public_hash = current_hash
    elif (type(reference) is PublicQueryReference and reference.subject == subject
            and reference.scope == turn.scope and reference.thread_id == turn.thread_id
            and not turn.reset_topic):
        public_hash = reference.request_hash
    else:
        return
    hashes = sorted({public_hash, current_hash, *turn.source_request_hashes})
    if len(hashes) > 64:
        raise DialogueError("conversation_context_changed", 409)
    previous = captured_age_pending(turn) if turn.consume_public_age_pending else None
    created = previous["created_at"] if previous is not None else turn.history.dialogue.clock()
    pending = {"created_at": created, "deadline": created + 120,
        "type": "public_age_clarification", "stage": "choose_person" if person else "choose_scope",
        "subject": subject, "scope": turn.scope, "thread_id": turn.thread_id,
        "generation": turn.generation, "read_context_revision": turn.read_context_revision,
        "public_request_hash": public_hash, "request_hash": current_hash, "source_request_hashes": hashes}
    def validate():
        if (turn.frame.generation != pending["generation"]
                or turn.frame.read_context_revision != pending["read_context_revision"]
                or not pending["created_at"] <= turn.history.dialogue.clock() < pending["deadline"]):
            raise DialogueError("conversation_context_changed", 409)
        if _age_completion_valid(turn, pending):
            if turn.frame.pending != pending:
                raise DialogueError("conversation_context_changed", 409)
            return
        if (turn.frame.pending is not turn.pending_at_start
                or turn.frame.pending_revision != turn.pending_revision_at_start
                or turn.frame.public_query_reference is not turn.public_reference_at_start
                or turn.frame.public_query_revision != turn.public_reference_revision_at_start):
            raise DialogueError("conversation_context_changed", 409)
    validate()
    turn.effect_validators.append(validate)
    turn.delivery_validators.append(validate)
    turn.pending = pending


def more_request(text):
    """Fast common affordance, not the free-language interpreter's whitelist."""
    return bool(re.fullmatch(
        r"(?:tell me more|vertel (?:me )?meer|erz[aä]hl(?:e)? (?:mir )?mehr|"
        r"dis[- ]m['’]en plus|cu[eé]ntame m[aá]s)[.!? ]*", text.strip(), re.I))


def capability():
    return {"version": 1, "operation": "ask_dj/message",
            "context": ["selected_entry", "selected_moment"],
            "generic_questions": dict(MORE_TEXT),
            "attribute_required": False, "effect": "informational",
            "subject_authority":"qualified_selected_public_context",
            "unqualified_context":"existing_source_unavailable_response",
            "client_gesture_owner":"client", "maximum_agent_calls":3}


def admitted_subject(subject, angle, context):
    """An interpreter chooses public context; it cannot manufacture authority."""
    from .public_research import safe_subject
    if angle not in ANGLES or not isinstance(context, dict):
        return None
    if context.get("basis") != "cc0_normalized_fields_v1":
        return None
    name = safe_subject(subject, qualified=True)
    if not name or len(name) > 120:
        return None
    subjects = context.get("subjects", [])
    names = [s.get("name") for s in subjects if isinstance(s, dict)]
    if names:
        # Full identities and their roles are resolved by Core, not a guessed
        # partial name, client prose, image label or model's preferred band.
        return next((n for n in names if isinstance(n, str) and n.casefold() == name.casefold()), None)
    # A word in an old excerpt is not a canonical identity ("Brian" in
    # "Brian Eno", for example). Generic questions need no caller attribute,
    # but their subject must still come from Core's qualified full identities.
    return None


def named_in_question(subject, text):
    """A full user name can contain a small typo, never missing name parts."""
    if re.search(r"(?<!\w)"+re.escape(subject)+r"(?!\w)",text,re.I):
        return True
    names=re.findall(r"[^\W\d_]+",subject.casefold())
    words=re.findall(r"[^\W\d_]+",text.casefold())
    if not names or (len(names)==1 and len(names[0])<4):
        return False
    def distance(left,right):
        if left==right:
            return 0
        if min(len(left),len(right))<4 or abs(len(left)-len(right))>2:
            return 3
        row=list(range(len(right)+1))
        for i,a in enumerate(left,1):
            new=[i]
            for j,b in enumerate(right,1):
                new.append(min(new[-1]+1,row[j]+1,row[j-1]+(a!=b)))
            row=new
        return row[-1]
    return any(sum(distance(a,b) for a,b in zip(names,words[i:i+len(names)],strict=True))<=2
               for i in range(len(words)-len(names)+1))


async def research_response(hass, runtime, text, plan, *, recent_reference=None):
    from .dialogue import current_turn
    from . import _informational_assist_response
    turn = current_turn.get()
    if turn is None:
        return None
    if plan.reference == "named":
        from .public_research import safe_subject
        subject=safe_subject(plan.subject)
        # The model may select an angle, but the complete public name must
        # actually be in this question. No invented fallback to another artist.
        if not subject or not named_in_question(subject,text):
            return None
        turn.public_query_candidate = subject
        turn.source_context={}
        turn.selected_read_context=None
        turn.dependencies.clear()
        turn.reset_topic=True
        turn.explicit_research_subject=True
    elif plan.reference == 'recent':
        from .dialogue import PublicQueryReference
        if (type(recent_reference) is not PublicQueryReference
                or turn.frame.public_query_reference is not recent_reference
                or recent_reference.scope != turn.scope or recent_reference.thread_id != turn.thread_id):
            return None
        subject = recent_reference.subject
        turn.source_context = {}
        turn.selected_read_context = None
        turn.dependencies.clear()
    else:
        if turn.selected_read_context is None:
            return None
        subject = admitted_subject(plan.subject, plan.angle, turn.source_context)
    if not subject:
        return None
    await turn.guard()
    turn.interpreted_context_research = True
    return await _informational_assist_response(hass, runtime, text, {}, {}, {}, [],
        research_subject=subject, research_angle=plan.angle, contextual_research=True)
