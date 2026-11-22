"""Native HA ingress authority; intelligence and dialogue remain in Ask DJ."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
from uuid import uuid4

from .session_conversation import SessionConversationError
from .domain.errors import ResolverError

current_admission: ContextVar[VoiceAdmission | None] = ContextVar("djconnect_native_voice", default=None)


@dataclass(frozen=True)
class VoiceAdmission:
    hass: object
    runtime: object
    device_id: str
    profile_id: str
    household: object
    registry_device: object
    options: str
    authority_revision: int
    bound_runtime: object = None

    def validate(self):
        """Recheck installation consent, actual endpoint and the loaded entry at every fence."""
        from homeassistant.helpers import device_registry as dr
        from .api_handlers import _ha_native_service_identity
        from .profile_context import profile_storage
        _ha_native_service_identity(self.hass, self.runtime)
        storage = profile_storage(self.hass)
        if (storage.household is not self.household
                or dr.async_get(self.hass).async_get(self.device_id) is not self.registry_device
                or _configuration_digest(self.runtime) != self.options):
            raise SessionConversationError("native_voice_authority_changed", 409)
        profile = storage.resolver().resolve_personal_voice_endpoint(self.device_id)
        if profile.profile_id != self.profile_id:
            raise SessionConversationError("native_voice_authority_changed", 409)
        return profile


def active_for(hass, runtime):
    value = current_admission.get()
    if isinstance(runtime, NativeRuntimeView):
        value = runtime.admission
    return value if value is not None and value.hass is hass and (value.runtime is runtime or value.bound_runtime is runtime) else None


class NativeRuntimeView:
    """Per-turn routing, never shared mutable personal context on the agent entry.

    The original loaded entry remains the transport owner. Existing provider
    entries retain credentials/caches; profile_backend resolves them from this
    admitted Profile, never from the synthetic agent's old default binding.
    """

    def __init__(self, admission):
        self.admission = admission

    @property
    def config(self):
        from .profile_backend import _PROVIDER_CONFIG_KEYS, PROFILE_BACKEND_ENTRY_ID, profile_backend_entry_id
        profile = self.admission.validate()
        conf = {key: value for key, value in self.admission.runtime.config.items()
                if key not in {*_PROVIDER_CONFIG_KEYS, PROFILE_BACKEND_ENTRY_ID, "music_account_id", "profile_id"}}
        conf.update(profile_id=profile.profile_id, music_backend=profile.preferences.default_backend_id,
                    music_account_id=profile.preferences.default_music_account_id)
        owner = profile_backend_entry_id(self.admission.hass, profile.profile_id)
        if owner:
            conf[PROFILE_BACKEND_ENTRY_ID] = owner
        return conf

    def __getattr__(self, name):
        if name.startswith("profile_context_"):
            raise AttributeError(name)
        return getattr(self.admission.runtime, name)


async def admit(hass, runtime, user_input):
    """Only an actual HA device and explicit personal endpoint mapping confer personal access."""
    from homeassistant.helpers import device_registry as dr
    from .api_handlers import _ha_native_service_identity
    from .profile_context import profile_storage
    _ha_native_service_identity(hass, runtime)
    device_id = getattr(user_input, "device_id", None)
    if not isinstance(device_id, str) or not device_id or len(device_id) > 128:
        raise SessionConversationError("native_voice_endpoint_required", 403)
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        raise SessionConversationError("native_voice_endpoint_required", 403)
    storage = profile_storage(hass)
    await storage.async_load()
    try:
        profile = storage.resolver().resolve_personal_voice_endpoint(device_id)
    except ResolverError as exc:
        raise SessionConversationError("native_voice_personal_access_required", 403) from exc
    # HA's public conversation API can carry a caller-supplied device_id. An
    # authenticated HA user must ALSO be mapped to this Profile; a device label
    # alone must not let a different user impersonate an admitted satellite.
    user_id = getattr(getattr(user_input, "context", None), "user_id", None)
    if user_id and storage.household.shared.ha_user_profile_ids.get(user_id) != profile.profile_id:
        raise SessionConversationError("native_voice_personal_access_required", 403)
    value = VoiceAdmission(hass, runtime, device_id, profile.profile_id, storage.household,
                           device, _configuration_digest(runtime), storage.authority_revision)
    object.__setattr__(value, "bound_runtime", NativeRuntimeView(value))
    value.validate()
    return value


def _configuration_digest(runtime):
    # Capture configuration identity without retaining a second plaintext secret copy.
    return hashlib.sha256(json.dumps(dict(runtime.config), sort_keys=True, default=str).encode()).hexdigest()


def source_authority(hass, runtime, owner_profile_id, expected_source=None):
    """Qualify the actual native principal and existing provider owner, never fabricate pairing.

    This is personal Core read/source authority. It grants no independent shared
    display, guest, physical speech-delivery or provider redistribution rights.
    """
    from .profile_backend import profile_backend_runtime
    try:
        admission = runtime.admission
        profile = admission.validate()
        if admission.hass is not hass or profile.profile_id != owner_profile_id:
            return lambda: False
        household = admission.household
        prefs = profile.preferences
        account = household.music_accounts.get(prefs.default_music_account_id)
        backend = household.music_backends.get(prefs.default_backend_id)
        provider = profile_backend_runtime(hass, runtime, provider_only=True)
        entry = provider.entry
        original = _configuration_digest(provider)
        source = {"backend_id": prefs.default_backend_id,
                  "music_account_id": prefs.default_music_account_id,
                  "provider_account_id": getattr(account, "provider_account_id", ""),
                  "provider_entry_id": entry.entry_id}
        if expected_source and any(source.get(key) != value for key, value in expected_source.items()):
            return lambda: False
    except (AttributeError, KeyError, ValueError, ResolverError):
        return lambda: False

    def allowed():
        try:
            current = admission.validate()
            return bool(account is not None and backend is not None
                and current is profile and str(profile.state) == "active"
                and str(account.state) == "active" and str(backend.state) == "active"
                and owner_profile_id in account.linked_profile_ids
                and account.backend_id == backend.backend_id
                and profile_backend_runtime(hass, runtime, provider_only=True) is provider
                and hass.data.get("djconnect", {}).get(entry.entry_id) is provider
                and hass.config_entries.async_get_entry(entry.entry_id) is entry
                and entry.disabled_by is None
                and getattr(entry.state, "value", entry.state) == "loaded"
                and _configuration_digest(provider) == original)
        except (AttributeError, KeyError, ValueError, ResolverError):
            return False
    return allowed


def guard_model(hass, data):
    """A native ingress can never call another DJConnect ingress or an implicit default agent."""
    value = current_admission.get()
    if value is None or value.hass is not hass:
        return
    value.validate()
    from homeassistant.components.conversation import async_get_agent
    identifier = data.get("agent_id")
    agent = async_get_agent(hass, identifier) if identifier else None
    from .conversation import DJConnectConversationAgent
    if agent is None or isinstance(agent, DJConnectConversationAgent):
        raise SessionConversationError("native_voice_backend_agent_required", 409)


async def exchange(hass, runtime, user_input):
    """Translate HA transport once; the existing app boundary owns the complete turn."""
    if current_admission.get() is not None:
        raise SessionConversationError("native_voice_recursive_agent", 409)
    value = await admit(hass, runtime, user_input)
    from .pipeline import _assist_context
    token = current_admission.set(value)
    try:
        guard_model(hass, _assist_context(hass, runtime.config))
        conversation_id = getattr(user_input, "conversation_id", None) or uuid4().hex
        if not isinstance(conversation_id, str) or len(conversation_id) > 128:
            raise SessionConversationError("invalid_conversation_context", 400)
        if not getattr(runtime, "native_voice_epoch", None):
            runtime.native_voice_epoch = uuid4().hex
        thread = "ha-" + hashlib.sha256(json.dumps([
            runtime.entry.entry_id, value.device_id, value.profile_id, conversation_id,
            runtime.native_voice_epoch, value.authority_revision,
        ]).encode()).hexdigest()
        context = {"thread_id": thread}
        from .session_runtime import session_runtime_manager
        active = session_runtime_manager(hass).current_active(value.profile_id)
        from .http import _history_manager
        history = _history_manager(hass, runtime)
        threads = history.dialogue.owners.get("profile:" + value.profile_id, {})
        for key, old in list(threads.items()):
            if (key.startswith("ha-") and old.native_voice_session_id
                    and (active is None or old.native_voice_session_id != active.session_id)
                    and not old.inflight):
                old.reset("native_voice_session_ended")
                del threads[key]
        if active is not None:
            context["session_id"] = active.session_id
        # HA's context id identifies this delivery attempt, never a DJ Session.
        request_context = getattr(user_input, "context", None)
        request_id = getattr(request_context, "id", None) or uuid4().hex
        identifier = "ha-turn-" + hashlib.sha256(json.dumps([
            runtime.entry.entry_id, value.device_id, value.profile_id,
            conversation_id, request_id, user_input.text,
        ]).encode()).hexdigest()
        payload = {"text": user_input.text, "language": user_input.language,
                   "client_message_id": identifier, "conversation_context": context,
                   "audio_response": "never", "speech_contract_version": 3}
        from .api_handlers import async_handle_ask_dj_message_payload
        result, status = await async_handle_ask_dj_message_payload(
            hass, payload, voice_input=True, _ha_service_runtime=runtime)
        value.validate()
        if status >= 400:
            raise SessionConversationError(str(result.get("error") or "native_voice_unavailable"), status)
        # A Core pending choice is not an assertion about hardware listening support.
        frame = history.dialogue.owners.get("profile:" + value.profile_id, {}).get(thread)
        if frame is not None:
            frame.native_voice_session_id = context.get("session_id") or (
                result.get("session_lifecycle", {}).get("session", {}).get("session_id")
                if result.get("action") == "session_start" and result.get("success") else "")
        pending = bool(frame and (frame.pending or (
            frame.result_set and frame.result_set.get("first_play_admission") is not None
            and frame.result_set["deadline"] > _history_manager(hass, runtime).dialogue.clock())))
        return result, conversation_id, pending
    finally:
        current_admission.reset(token)


COPY = {
    "empty": (
        "Ik heb niets verstaan. Probeer het nog eens.", "I did not hear anything. Please try again.",
        "Ich habe nichts verstanden. Bitte versuche es noch einmal.",
        "Je n’ai rien compris. Réessayez.", "No he entendido nada. Inténtalo de nuevo.",
    ),
    "admission": (
        "Geef dit spraakapparaat eerst persoonlijke toegang tot een DJConnect-profiel in de integratieopties.",
        "First grant this voice device personal access to a DJConnect profile in the integration options.",
        "Erlaube diesem Sprachgerät zuerst persönlichen Zugriff auf ein DJConnect-Profil in den Integrationsoptionen.",
        "Autorisez d’abord cet appareil vocal à accéder à un profil DJConnect dans les options de l’intégration.",
        "Primero autoriza el acceso personal de este dispositivo de voz a un perfil DJConnect en las opciones de la integración.",
    ),
    "backend": (
        "Kies voor DJConnect een afzonderlijke AI-conversatieagent als backend, niet DJConnect DJ zelf.",
        "Select a separate AI conversation agent as the DJConnect backend, rather than DJConnect DJ itself.",
        "Wähle einen separaten KI-Konversationsagenten als DJConnect-Backend statt DJConnect DJ selbst.",
        "Choisissez un agent de conversation IA distinct comme backend DJConnect, plutôt que DJConnect DJ lui-même.",
        "Selecciona un agente de conversación de IA distinto como backend de DJConnect, en lugar del propio DJConnect DJ.",
    ),
    "unavailable": (
        "DJConnect kon je verzoek niet verwerken. Probeer het opnieuw.",
        "DJConnect could not process your request. Please try again.",
        "DJConnect konnte deine Anfrage nicht verarbeiten. Bitte versuche es erneut.",
        "DJConnect n’a pas pu traiter votre demande. Réessayez.",
        "DJConnect no ha podido procesar tu solicitud. Inténtalo de nuevo.",
    ),
}


def copy_for(key, language):
    family = str(language or "en").replace("_", "-").split("-", 1)[0].lower()
    return COPY[key][("nl", "en", "de", "fr", "es").index(family) if family in {"nl", "en", "de", "fr", "es"} else 1]
