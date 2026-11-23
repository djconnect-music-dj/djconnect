"""Original per-pair Widget roles and explicit purpose preparation, RAM only."""
from __future__ import annotations

from dataclasses import dataclass

from .native_widget_issuer import CoreWidgetIssuerOwner
from .native_widget_transport import ProductionWidgetHTTPS
from .surface_issuer_journal import IssuerStageJournal, IssuerStageStore
from .surface_issuer_lifecycle import IssuerLifecycle
from .surface_push_contract import require
from .surface_push_wire import canonical
from .surface_widget_adoption import MAX_HANDLES

_ERROR = "native_widget_preparation_unavailable"


@dataclass(repr=False)
class _OriginalRole:
    owner: CoreWidgetIssuerOwner
    registration: object
    lifecycle: IssuerLifecycle
    operation: str | None = None
    handle: object = None


class NativeWidgetPreparation:
    """One service-owned journal; exact per-role lifecycles never substitute."""

    def __init__(self, surface, native):
        from .surface_push_service import SurfacePushService
        require(type(surface) is SurfacePushService and surface.hass is native.hass,
                _ERROR, 503)
        self.surface, self.native = surface, native
        self.manager = surface.manager
        self.adoptions = surface._widget_adoptions
        self.journal = IssuerStageJournal(IssuerStageStore(self.adoptions.persistence))
        self.roles = {}
        self.operations = {}

    def _current(self):
        from .native_pair_enrollment import KEY
        domain = self.native.hass.data.get("djconnect", {})
        require(not self.native.hass.is_stopping and not self.surface.closed
                and domain.get(KEY) is self.native
                and domain.get("surface_push_service") is self.surface
                and getattr(self.surface, "_native_widget_preparation", None) is self
                and self.surface.manager is self.manager
                and self.surface._widget_adoptions is self.adoptions,
                _ERROR, 503)

    def admit(self, owner):
        self._current()
        require(type(owner) is CoreWidgetIssuerOwner, _ERROR, 503)
        role = owner._live()
        registration = role.first_original[0].registration
        require(role.service is self.native and id(registration) not in self.roles
                and len(self.roles) < MAX_HANDLES, _ERROR, 503)
        lifecycle = IssuerLifecycle(owner, self.journal, ProductionWidgetHTTPS(owner),
            wall=lambda: int(self.native.wall() * 1000), monotonic=self.native.monotonic)
        self.adoptions.admit_native_lifecycle(lifecycle, self.journal)
        self.roles[id(registration)] = _OriginalRole(owner, registration, lifecycle)

    async def prepare(self, payload, headers):
        from .direct_rich_pair import capture_pair
        from .direct_rich_wire import RichError
        self._current()
        identity = {key: payload[key] for key in ("device_id", "client_type")}
        require(identity["client_type"] == "ios", _ERROR, 403)
        try:
            pair = capture_pair(self.native.hass, headers, **identity)
        except RichError as error:
            from .surface_push_contract import SurfacePushError
            raise SurfacePushError(error.code, error.status) from None
        operation = payload["operation_id"]
        body = canonical(payload)
        previous = self.operations.get(operation)
        if previous is not None:
            original_body, record = previous
            require(body == original_body and record.registration is pair.registration,
                    _ERROR, 409)
        else:
            record = self.roles.get(id(pair.registration))
            require(record is not None and record.registration is pair.registration
                    and record.operation is None and len(self.operations) < MAX_HANDLES,
                    _ERROR, 503)
            role = record.owner._live()
            require(role.first_original[0].runtime is pair.runtime, _ERROR, 403)
            active = self.surface.manager.current_active(role.authority.context.profile_id)
            require(active is not None and active.session_id == payload["session_id"], _ERROR, 409)
            # Capture the original owner, Session and source BEFORE first await.
            handle = self.surface.begin_widget_adoption(record.lifecycle, operation,
                                                        identity, dict(headers))
            if handle.capture.session_id != payload["session_id"]:
                self.surface.withdraw_widget_adoption(handle)
                require(False, _ERROR, 409)
            record.operation, record.handle = operation, handle
            self.operations[operation] = (body, record)
        record.owner._live()
        try:
            purpose = await self.surface.adopt_widget(record.handle)
            self._current()
            record.owner._live()
            require(pair.current() and record.registration is pair.registration
                    and record.handle.adopted and record.handle.purpose is purpose
                    and purpose.is_current(), _ERROR, 503)
            return {"contract_version": 1, "state": "prepared", "operation_id": operation,
                    "session_id": payload["session_id"]}
        except BaseException:
            self.surface.withdraw_widget_adoption(record.handle)
            raise

    def fence_pair(self, registration):
        record = self.roles.get(id(registration))
        if record is not None and record.registration is registration:
            record.owner.fence_live()
            if record.handle is not None:
                self.surface.withdraw_widget_adoption(record.handle)


async def accept_registered_winner(native, operation_id, headers):
    """Called only by the original successful register continuation, never status."""
    from .surface_push_service import SurfacePushService
    surface = native.hass.data.get("djconnect", {}).get("surface_push_service")
    require(type(surface) is SurfacePushService and not surface.closed, _ERROR, 503)
    pool = getattr(surface, "_native_widget_preparation", None)
    if pool is None:
        pool = NativeWidgetPreparation(surface, native)
        surface._native_widget_preparation = pool
    require(type(pool) is NativeWidgetPreparation and pool.native is native, _ERROR, 503)
    owner = await CoreWidgetIssuerOwner.enrol(native, operation_id, headers)
    pool.admit(owner)
