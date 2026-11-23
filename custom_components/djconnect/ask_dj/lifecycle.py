"""Explicit conversational lifecycle commands, shared by every Ask DJ ingress."""
from __future__ import annotations

START = (
    "start een dj sessie", "start de dj sessie", "start een dj-sessie", "start de dj-sessie",
    "start a dj session", "start the dj session", "start dj session",
    "starte eine dj session", "starte die dj session",
    "démarre une session dj", "commence une session dj",
    "inicia una sesión dj", "empieza una sesión dj",
)
END = (
    "beëindig de dj sessie", "beëindig de dj-sessie", "stop de dj sessie", "stop de dj-sessie",
    "end the dj session", "end dj session", "stop the dj session",
    "beende die dj session", "termine la session dj", "arrête la session dj",
    "termina la sesión dj", "finaliza la sesión dj",
)


def requested(text):
    value = " ".join(str(text or "").casefold().strip().rstrip(".!?").split())
    return "session_start" if value in START else "session_end" if value in END else None


async def reply(hass, runtime, payload, context, headers, native_runtime):
    """Same lifecycle owner, one reserved dialogue operation and original Session target."""
    from .dialogue import current_turn, DialogueError
    from ..api_handlers import async_handle_session_start_payload, async_handle_session_end_payload
    from ..session_runtime import session_runtime_manager
    turn = current_turn.get()
    command = requested(payload.get("text"))
    if turn is None or command is None:
        raise DialogueError("conversation_authority_required", 403)
    manager = session_runtime_manager(hass)
    original = manager.current_active(context.profile_id)
    turn.require_effect(command)
    await turn.before_effect()
    data = {key: payload[key] for key in ("device_id", "client_type", "language") if key in payload}
    data["profile_id"] = context.profile_id
    if command == "session_end":
        if original is None:
            return {"success": False, "text": _copy(turn.style, "missing"), "action": command}
        data["session_id"] = original.session_id
    handler = async_handle_session_start_payload if command == "session_start" else async_handle_session_end_payload
    result, status = await handler(hass, data, headers=headers, _ha_service_runtime=native_runtime)
    if status >= 400:
        return {"success": False, "text": _copy(turn.style,
            "exists" if result.get("error") == "active_session_exists" else "failed"),
            "action": command, "error": result.get("error")}
    turn.accepted_lifecycle = (command, result["session"]["session_id"])
    # Do not bind a newly created Session's operation to its predecessor's topic.
    turn.clear_result_set = True
    turn.clear_pending = True
    text = _copy(turn.style, "started" if command == "session_start" else "ended")
    if command == "session_start":
        from ..mood_music_steering import reuse_for_you_offer
        turn.session_id = result["session"]["session_id"]
        offer = reuse_for_you_offer(hass, runtime, turn)
        if offer is not None:
            text += " " + offer["text"]
    return {"success": True, "text": text,
            "action": command, "session_lifecycle": result}


def _copy(style, kind):
    language = style.get("language", "en")
    index = ("nl", "en", "de", "fr", "es").index(language) if language in {"nl", "en", "de", "fr", "es"} else 1
    return {
        "started": ("Je DJ-sessie is gestart. Vraag gerust naar Voor jou.", "Your DJ session has started. You can ask about For you.",
                    "Deine DJ-Session wurde gestartet. Du kannst nach Für dich fragen.", "Votre session DJ a démarré. Vous pouvez demander Pour vous.", "Tu sesión DJ ha comenzado. Puedes preguntar por Para ti."),
        "ended": ("Je DJ-sessie is beëindigd. De muziek is niet gepauzeerd.", "Your DJ session has ended. Music was not paused.",
                  "Deine DJ-Session wurde beendet. Die Musik wurde nicht pausiert.", "Votre session DJ est terminée. La musique n’a pas été mise en pause.", "Tu sesión DJ ha terminado. La música no se ha pausado."),
        "missing": ("Er is geen actieve DJ-sessie.", "There is no active DJ session.", "Es gibt keine aktive DJ-Session.", "Il n’y a pas de session DJ active.", "No hay ninguna sesión DJ activa."),
        "exists": ("Je hebt al een actieve DJ-sessie. Die blijft behouden.", "You already have an active DJ session. It remains unchanged.", "Du hast bereits eine aktive DJ-Session. Sie bleibt unverändert.", "Vous avez déjà une session DJ active. Elle reste inchangée.", "Ya tienes una sesión DJ activa. Se mantiene sin cambios."),
        "failed": ("De DJ-sessie kon niet worden gewijzigd.", "The DJ session could not be changed.", "Die DJ-Session konnte nicht geändert werden.", "La session DJ n’a pas pu être modifiée.", "No se ha podido cambiar la sesión DJ."),
    }[kind][index]
