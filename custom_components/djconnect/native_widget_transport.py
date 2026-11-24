"""Native-provenance Widget transport; no CF credentials or legacy redemption."""
from __future__ import annotations

import json

from .native_widget_issuer import CoreWidgetIssuerOwner
from .surface_issuer_owner import IssuerOwnerCapture
from .surface_issuer_transport import IssuerHTTPS
from .surface_issuer_wire import PREFIX, signing_bytes
from .surface_push_contract import require
from .surface_push_purpose import SurfacePurposeCredential

_ROUTES = {name: "/v1/push/surface/" + name for name in ("register", "revoke", "event", "status")}


class ProductionWidgetHTTPS(IssuerHTTPS):
    """Retain the actual native enrolled role, never an operator-row fallback."""

    def __init__(self, owner):
        require(type(owner) is CoreWidgetIssuerOwner, "native_widget_transport_unavailable", 503)
        role = owner._historical()
        super().__init__(monotonic=role.monotonic)
        self._owner, self._origin = owner, role.base.origin

    def validate_origin(self, origin):
        role = self._owner._historical()
        require(origin == self._origin == role.base.origin,
                "native_widget_transport_unavailable", 503)

    async def post_once(self, capture, action, envelope, *, guard, deadline):
        require(type(capture) is IssuerOwnerCapture,
                "surface_issuer_owner_capture_invalid", 503)
        capture.comparisons()
        require(action in {"challenge", "issue", "status", "withdraw"}
                and type(envelope) is dict and set(envelope) == {"payload", "signature"},
                "surface_issuer_wire_invalid", 403)
        signing_bytes(PREFIX + action, envelope["payload"])
        return await self._send(capture.origin, PREFIX + action, envelope, {}, guard, deadline)

    async def relay(self, admission, action, body, *, deadline):
        require(action in _ROUTES, "surface_relay_route_invalid", 403)
        purpose = admission.purpose
        require(type(purpose) is SurfacePurposeCredential and purpose.private_transport is self
                and json.loads(purpose.policy_json)["token_role"] == "widget",
                "surface_purpose_unavailable", 503)

        def guard():
            admission.validate()
            require(admission.purpose is purpose, "surface_purpose_unavailable", 503)
            if action in {"register", "event"}:
                self._owner._live()
            return purpose.authorize(action, body)

        bearer = guard()
        return await self._send(purpose.origin, _ROUTES[action], body,
            {"Authorization": "Bearer " + bearer}, guard, deadline)

    async def _send(self, origin, path, body, headers, guard, deadline):
        owner = self._owner
        def current():
            guard()
            require(self._owner is owner, "native_widget_transport_unavailable", 503)
            self.validate_origin(origin)
        current()
        reply = await self._post(origin, path, body, headers, guard=current, deadline=deadline)
        current()
        return reply
