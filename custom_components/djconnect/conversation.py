"""Conversation agent support for DJConnect."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME, DOMAIN
from .native_voice import copy_for, exchange
from .session_conversation import SessionConversationError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DJConnect conversation agent."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DJConnectConversationAgent(runtime)])


class DJConnectConversationAgent(conversation.ConversationEntity):
    """DJConnect Assist conversation agent."""

    _attr_has_entity_name = False
    _attr_name = "DJConnect DJ"
    _attr_should_poll = False

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._attr_unique_id = f"{runtime.entry.entry_id}_conversation"

        device_name = str(
            runtime.config.get(CONF_DEVICE_NAME)
            or runtime.config.get("name")
            or DEFAULT_DEVICE_NAME
        ).strip()

        self._attr_device_info = {
            "identifiers": {(DOMAIN, runtime.entry.entry_id)},
            "name": device_name or DEFAULT_DEVICE_NAME,
            "manufacturer": "DJConnect",
        }

    @property
    def available(self) -> bool:
        """Report loaded transport/backend readiness without provider or auth probing."""
        try:
            from .api_handlers import _ha_native_service_identity
            from .pipeline import _assist_context
            from homeassistant.components.conversation import async_get_agent
            _ha_native_service_identity(self.hass, self._runtime)
            identifier = _assist_context(self.hass, self._runtime.config).get("agent_id")
            backend = async_get_agent(self.hass, identifier) if identifier else None
            if backend is None or isinstance(backend, DJConnectConversationAgent) or not getattr(backend, "available", True):
                return False
            from .ask_dj.dialogue import qualify_agent
            qualify_agent(self.hass, identifier)
            return True
        except (AttributeError, KeyError, ValueError, SessionConversationError):
            return False

    @property
    def state(self) -> str:
        return "ready" if self.available else "unavailable"

    @property
    def supported_languages(self) -> list[str]:
        # Supported semantic languages, not a claim of physical STT/TTS support.
        return ["nl", "en", "de", "fr", "es"]

    async def _async_handle_message(self, user_input, chat_log):
        """HA ChatLog remains transport; Core owns topic/history and resultsets."""
        return await self.async_process(user_input)

    async def async_process(self, user_input):
        """Route one admitted native turn through the same app service as Apple."""
        language = str(getattr(user_input, "language", None) or "en")
        response = intent.IntentResponse(language=language)
        conversation_id = getattr(user_input, "conversation_id", None)
        pending = False
        if not str(getattr(user_input, "text", "") or "").strip():
            speech = copy_for("empty", language)
        else:
            try:
                result, conversation_id, pending = await exchange(self.hass, self._runtime, user_input)
                speech = str(result.get("text") or result.get("dj_text") or "").strip()
                if not speech:
                    speech = copy_for("unavailable", language)
                    pending = False
            except SessionConversationError as exc:
                # Stable code only: never log user speech, private replies or provider errors.
                _LOGGER.warning("DJConnect native conversation rejected: %s", exc.code)
                key = ("backend" if exc.code in {"native_voice_backend_agent_required", "native_voice_recursive_agent"}
                       else "admission" if exc.code in {"native_voice_endpoint_required", "native_voice_personal_access_required"}
                       else "unavailable")
                speech = copy_for(key, language)
            except Exception:  # noqa: BLE001
                _LOGGER.error("DJConnect native conversation failed")
                speech = copy_for("unavailable", language)
        response.async_set_speech(speech)
        return conversation.ConversationResult(response=response, conversation_id=conversation_id,
                                               continue_conversation=pending)
