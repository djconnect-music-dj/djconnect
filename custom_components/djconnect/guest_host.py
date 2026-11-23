"""HA installation-admin consent, distinct from paired owner or guest identity.

Only the HA-admin-protected OptionsFlow calls this internal adapter. It confers
participation policy/request rights on an existing real share, never B display
approval, a Profile personal grant, or an invented paired device identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import secrets

from .display_admission import DisplayAdmissionError


@dataclass(frozen=True, repr=False)
class InstallationAdminConsent:
    share: object
    entry: object
    hass: object
    manager: object
    stamp: str

    @property
    def profile_id(self):
        return self.share.owner.profile_id

    @property
    def session_id(self):
        return self.share.owner.session_id

    def valid(self):
        state = self.manager._display_admission
        active = self.manager.current_active(self.profile_id)
        actual = self.hass.config_entries.async_get_entry(self.entry.entry_id)
        return (actual is self.entry and not self.entry.disabled_by
                and getattr(self.entry.state, 'value', self.entry.state) == 'loaded'
                and state._shares.get(self.share.share_id) is self.share
                and self.share.owner.valid() and self.share.deadline > state._clock()
                and active is not None and active.session_id == self.session_id)


def options_consent(flow, manager, share_id):
    # This is a framework OptionsFlow instance and its actual loaded config
    # entry, not an external API's claim that it is an administrator.
    from homeassistant.config_entries import OptionsFlow
    if not isinstance(flow, OptionsFlow) or not flow.flow_id:
        raise DisplayAdmissionError('guest_host_unavailable', 403)
    entry = flow.hass.config_entries.async_get_entry(flow._config_entry.entry_id)
    share = manager._display_admission._shares.get(share_id)
    if entry is not flow._config_entry or share is None:
        raise DisplayAdmissionError('guest_host_unavailable', 403)
    consent = InstallationAdminConsent(share, entry, flow.hass, manager, secrets.token_urlsafe(24))
    if not consent.valid():
        raise DisplayAdmissionError('guest_host_unavailable', 403)
    return consent
