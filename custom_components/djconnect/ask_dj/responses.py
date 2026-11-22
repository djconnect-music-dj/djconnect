"""Ask DJ response and media helpers."""
from __future__ import annotations

from ..image_proxy import image_proxy_target, register_image_proxy_url

__all__ = ["image_proxy_target", "register_image_proxy_url"]


def _core_answer(message, /, **fields):
    """Keep the common successful response fields in their existing order."""
    return {"success": True, "text": message, "dj_text": message, **fields}
