"""Native transport unit tests with private HA stubs; real SDK is qualified separately."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
import types
import unittest
ROOT = Path(__file__).resolve().parents[1]


def install_conversation_stubs():
    names = ('homeassistant', 'homeassistant.components', 'homeassistant.components.conversation',
             'homeassistant.config_entries', 'homeassistant.core', 'homeassistant.helpers',
             'homeassistant.helpers.intent', 'homeassistant.helpers.entity_platform')
    modules = {name: types.ModuleType(name) for name in names}
    sys.modules.update(modules)
    for name, value in modules.items():
        if '.' in name:
            parent, attr = name.rsplit('.', 1)
            if parent in modules:
                setattr(modules[parent], attr, value)
    class ConversationEntity:
        pass
    class ConversationResult:
        def __init__(self, *, response, conversation_id=None, continue_conversation=False):
            self.response, self.conversation_id = response, conversation_id
            self.continue_conversation = continue_conversation
    class IntentResponse:
        def __init__(self, language):
            self.language, self.speech = language, None
        def async_set_speech(self, text):
            self.speech = text
    modules['homeassistant.components.conversation'].ConversationEntity = ConversationEntity
    modules['homeassistant.components.conversation'].ConversationResult = ConversationResult
    modules['homeassistant.helpers.intent'].IntentResponse = IntentResponse
    modules['homeassistant.config_entries'].ConfigEntry = object
    modules['homeassistant.core'].HomeAssistant = object
    modules['homeassistant.helpers.entity_platform'].AddEntitiesCallback = object
    if 'custom_components.djconnect' not in sys.modules:
        package = types.ModuleType('custom_components.djconnect')
        package.__path__ = [str(ROOT/'custom_components/djconnect')]
        sys.modules['custom_components.djconnect'] = package


class ConversationAgentTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = dict(sys.modules)
        install_conversation_stubs()
        spec = importlib.util.spec_from_file_location("custom_components.djconnect._conversation_unit", ROOT/'custom_components/djconnect/conversation.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    @classmethod
    def tearDownClass(cls):
        for name in list(sys.modules):
            if name == 'homeassistant' or name.startswith('homeassistant.'):
                if name in cls.before:
                    sys.modules[name] = cls.before[name]
                else:
                    sys.modules.pop(name, None)

    def agent(self):
        runtime = types.SimpleNamespace(entry=types.SimpleNamespace(entry_id="entry-1"), config={})
        agent = self.module.DJConnectConversationAgent(runtime)
        agent.hass = object()
        return agent

    async def test_thin_entity_returns_common_service_speech_and_pending(self):
        from unittest.mock import patch, AsyncMock
        agent = self.agent()
        user = types.SimpleNamespace(text="Why that album?", language="en", conversation_id="ha-thread")
        with patch.object(self.module, "exchange", AsyncMock(return_value=(
                {"text": "Which recording do you mean?"}, "ha-thread", True))) as common:
            reply = await agent._async_handle_message(user, object())
        common.assert_awaited_once_with(agent.hass, agent._runtime, user)
        self.assertEqual(reply.response.speech, "Which recording do you mean?")
        self.assertEqual(reply.conversation_id, "ha-thread")
        self.assertTrue(reply.continue_conversation)
        self.assertFalse(hasattr(agent, "conversation_tools"))
        self.assertFalse(hasattr(self.module, "run_text_command"))

    async def test_empty_input_never_enters_common_service(self):
        from unittest.mock import patch, AsyncMock
        for locale in ("nl", "en", "de", "fr", "es"):
            with patch.object(self.module, "exchange", AsyncMock()) as common:
                result = await self.agent().async_process(types.SimpleNamespace(text="", language=locale))
            self.assertFalse(result.continue_conversation)
            self.assertTrue(result.response.speech)
            common.assert_not_awaited()

    async def test_failures_do_not_claim_playback_or_log_private_exception(self):
        from unittest.mock import patch, AsyncMock
        from custom_components.djconnect.session_conversation import SessionConversationError
        for code in ("native_voice_personal_access_required", "native_voice_backend_agent_required", "native_voice_authority_changed"):
            with patch.object(self.module, "exchange", AsyncMock(side_effect=SessionConversationError(code))), self.assertLogs(self.module._LOGGER, level="WARNING") as logs:
                result = await self.agent().async_process(types.SimpleNamespace(text="private input", language="en"))
            self.assertFalse(result.continue_conversation)
            self.assertNotIn("private input", str(logs.output))
            self.assertNotIn("start it", result.response.speech)

    def test_availability_requires_loaded_transport_and_separate_backend(self):
        from unittest.mock import patch
        agent = self.agent()
        agent_api = types.SimpleNamespace(_ha_native_service_identity=lambda *a: {})
        pipeline = types.SimpleNamespace(_assist_context=lambda *a: {"agent_id": "conversation.backend"})
        conversation = sys.modules["homeassistant.components.conversation"]
        with patch.dict(sys.modules, {"custom_components.djconnect.api_handlers": agent_api,
                                     "custom_components.djconnect.pipeline": pipeline}), patch.object(conversation, "async_get_agent", return_value=agent, create=True):
            self.assertFalse(agent.available)
            self.assertEqual(agent.state, "unavailable")
        with patch.dict(sys.modules, {"custom_components.djconnect.api_handlers": agent_api,
                                     "custom_components.djconnect.pipeline": pipeline}), patch.object(conversation, "async_get_agent", return_value=object(), create=True):
            self.assertTrue(agent.available)
            self.assertEqual(agent.state, "ready")
        self.assertEqual(agent.supported_languages, ["nl", "en", "de", "fr", "es"])


if __name__ == "__main__":
    unittest.main()
