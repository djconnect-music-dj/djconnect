from __future__ import annotations

from typing import Any


def entry_unique_id(runtime: Any, suffix: str) -> str:
    """Return a unique entity id suffix scoped to the config entry."""
    entry_id = str(getattr(getattr(runtime, "entry", None), "entry_id", "") or "default")
    clean_suffix = str(suffix or "").removeprefix("djconnect_")
    return f"djconnect_{entry_id}_{clean_suffix}"


def remove_legacy_entities(
    hass: Any,
    runtime: Any,
    platform: str,
    keys: tuple[str, ...],
    *, registry_api: Any, domain: str, unique_id: Any,
) -> None:
    if registry_api is None:
        return
    registry = registry_api.async_get(hass)
    if registry is None:
        return
    get_entity_id = getattr(registry, "async_get_entity_id", None)
    remove_entity = getattr(registry, "async_remove", None)
    if not callable(get_entity_id) or not callable(remove_entity):
        return
    for key in keys:
        entity_id = get_entity_id(platform, domain, unique_id(runtime, key))
        if entity_id:
            remove_entity(entity_id)
