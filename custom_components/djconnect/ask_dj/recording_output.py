"""Resolve an inline output only into the existing inventory-owned choice."""
import re

from ..music_intent import parse_spoken_music_request


async def current_inventory(hass, runtime):
    """A source read, not a freshness label inferred from retained UI state."""
    from ..use_cases import run_music_command
    try:
        result = await run_music_command(hass, runtime, 'devices', {'inventory':'current_provider'})
    except Exception:  # An unavailable source cannot authorize suffix removal.
        return []
    if (not isinstance(result, dict) or result.get('success') is not True
            or result.get('inventory') != 'current_provider' or not isinstance(result.get('devices'), list)):
        return []
    return result['devices']


def inventory_suffix(text, devices):
    """Matching produces data, never an output grant or transfer."""
    if not parse_spoken_music_request(text).get('album'):
        return None
    matches = []
    for device in devices:
        if (not isinstance(device, dict) or type(device.get('id')) is not str or not device['id']
                or type(device.get('name')) is not str or not device['name']
                or device.get('is_restricted') or device.get('cached')):
            continue
        match = re.fullmatch(r'(.+?)\s+(?:op|on|auf|sur|en)\s+'
                             + re.escape(device['name']) + r'[.!?]*', text.strip(), re.I)
        if match and parse_spoken_music_request(match[1]).get('album'):
            matches.append((match[1], device))
    return matches[0] if len(matches) == 1 else None


async def prepare(hass, runtime, text, payload, classification, *, inventory, offer, turn):
    album = parse_spoken_music_request(text).get('album') or ''
    if turn is None or not re.search(r'\s(?:op|on|auf|sur|en)\s', album, re.I):
        return text, None
    devices = await inventory(hass, runtime)
    await turn.guard()
    matched = inventory_suffix(text, devices)
    if matched is None:
        return text, None
    cleaned, device = matched
    # Only an existing owner-selected exact output permits immediate reuse.
    # No local string match can create an EffectGrant or choose an output.
    if turn.play_output_id == device['id']:
        return cleaned, None
    return text, await offer(hass, runtime, cleaned, payload or {}, classification,
                            devices=[device])
