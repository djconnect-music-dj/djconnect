"""Consumer connection status for configured Home Assistant AI routes."""
from __future__ import annotations

import importlib
import sys
import types
import unittest
from unittest.mock import patch

from tests.test_pipeline import install_pipeline_stubs


class LLMBackendStatusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_pipeline_stubs()
        cls.pipeline = importlib.import_module("custom_components.djconnect.pipeline")

    def test_one_llm_status_covers_all_selected_routes_without_probing(self):
        health = self.pipeline
        from custom_components.djconnect.ask_dj import dialogue
        from custom_components.djconnect import music_canvas_render, structured_playback

        def entity(identifier):
            return types.SimpleNamespace(entity_id=identifier, entry=types.SimpleNamespace(modified_at=1),
                                         available=True, supported_features=2)
        conversation = entity("conversation.configured")
        structured = entity("ai_task.structured")
        image = entity("ai_task.image")
        hass = types.SimpleNamespace(data={"loaded_pipeline": object()})
        config = {structured_playback.TASK_CONFIG: structured.entity_id}
        modules = {
            "homeassistant.components.assist_pipeline.pipeline": types.SimpleNamespace(KEY_ASSIST_PIPELINE="loaded_pipeline"),
            "homeassistant.components.ai_task.const": types.SimpleNamespace(
                AITaskEntityFeature=types.SimpleNamespace(GENERATE_IMAGE=2)),
        }
        with (patch.dict(sys.modules, modules),
              patch.object(health, "_assist_context", return_value={"agent_id": conversation.entity_id}),
              patch.object(health, "_loaded_llm_agent", return_value=conversation),
              patch.object(dialogue, "qualify_agent", return_value=conversation),
              patch.object(structured_playback, "capture_task", return_value=types.SimpleNamespace(entity=structured)),
              patch.object(music_canvas_render, "selected_image_provider", return_value=(image.entity_id, image))):
            self.assertEqual(health.current_llm_backend_status(hass, config), "configured")
            for route, provider in (("conversation", conversation), ("structured", structured), ("image", image)):
                health.observe_llm_backend(hass, route, provider, health.llm_backend_observation_key(provider), "active")
            self.assertEqual(health.current_llm_backend_status(hass, config), "active")
            original = health.llm_backend_observation_key(structured)
            health.observe_llm_backend(hass, "structured", structured, original, "billing")
            self.assertEqual(health.current_llm_backend_status(hass, config), "billing")
            structured.entry.modified_at = 2
            health.observe_llm_backend(hass, "structured", structured, original, "billing")
            self.assertEqual(health.current_llm_backend_status(hass, config), "configured")
            health.observe_llm_backend(hass, "conversation", conversation,
                                       health.llm_backend_observation_key(conversation), "unavailable")
            self.assertEqual(health.current_llm_backend_status(hass, config), "unavailable")
