"""Original accepted conversation reply, distinct from music repeat controls."""
from __future__ import annotations

PHRASES = {
    "herhaal het", "herhaal dat", "herhaal wat je net zei", "wat zei je net", "wat vertelde je net",
    "repeat that", "repeat what you just said", "what did you just say", "say that again",
    "wiederhole das", "was hast du gerade gesagt", "sag das noch einmal",
    "répète ça", "répète ce que tu viens de dire", "qu’as-tu dit", "répète cela",
    "repite eso", "repite lo que acabas de decir", "qué acabas de decir", "dilo otra vez",
}
STOP_PHRASES = {"stop met vertellen", "stop met praten", "stop met antwoorden",
                "stop talking", "stop speaking", "stop narrating",
                "hör auf zu sprechen", "hör auf zu erzählen",
                "arrête de parler", "arrête de raconter", "deja de hablar", "deja de narrar"}


def stop_requested(text):
    return " ".join(str(text or "").strip().casefold().rstrip(".!?").split()) in STOP_PHRASES


async def stop_reply(turn):
    """End this dialogue's pending input; no playback command or global room-audio claim."""
    await turn.guard()
    turn.clear_pending = True
    turn.clear_result_set = True
    turn.archiveable = False
    locale = turn.style.get("language", "en")
    text = {"nl": "Ik stop dit gesprek. De muziek blijft ongemoeid.",
            "en": "I will stop this conversation. Music stays unchanged.",
            "de": "Ich beende dieses Gespräch. Die Musik bleibt unverändert.",
            "fr": "J’arrête cette conversation. La musique reste inchangée.",
            "es": "Termino esta conversación. La música sigue sin cambios."}.get(locale)
    return {"success": True, "text": text, "text_source": "runtime_acknowledgement",
            "is_generated_text": False, "_private_current_context": True,
            "intent": {"category": "action", "intent": "conversation_stop"},
            "playback_actions": []}


def requested(text):
    return " ".join(str(text or "").strip().casefold().rstrip(".!?").split()) in PHRASES


async def reply(turn):
    """Revalidate original thread/source; never substitute the latest unrelated Moment."""
    await turn.guard()
    last = next((item for item in reversed(turn.frame.local_turns)
                 if item.get("role") == "assistant" and item.get("text")), None)
    locale = turn.style.get("language", "en")
    index = ("nl", "en", "de", "fr", "es").index(locale) if locale in {"nl", "en", "de", "fr", "es"} else 1
    if last is None:
        text = (
            "Welke bijdrage bedoel je? Ik kan niet vaststellen wat je net hoorde.",
            "Which contribution do you mean? I cannot establish what you just heard.",
            "Welchen Beitrag meinst du? Ich kann nicht feststellen, was du gerade gehört hast.",
            "De quelle intervention parlez-vous ? Je ne peux pas déterminer ce que vous venez d’entendre.",
            "¿A qué intervención te refieres? No puedo determinar qué acabas de oír.",
        )[index]
    else:
        prefix = ("Mijn laatste antwoord in dit gesprek:", "My last answer in this conversation:",
                  "Meine letzte Antwort in diesem Gespräch:", "Ma dernière réponse dans cette conversation :",
                  "Mi última respuesta en esta conversación:")[index]
        text = prefix + " " + last["text"]
    # Returning an accepted answer to HA is not a physical spoken-delivery receipt.
    turn.archiveable = False
    return {"success": True, "text": text, "dj_text": text,
            "text_source": "original_conversation_reply" if last else "runtime_clarification",
            "is_generated_text": False, "_private_current_context": True,
            "intent": {"category": "informational", "intent": "conversation_recall"},
            "playback_actions": []}
