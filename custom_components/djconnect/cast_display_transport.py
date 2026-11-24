"""Closed Cast prefix only; original B routes and shell policy are unchanged."""

from aiohttp import web

from .cast_display import (
    CastDisplayService,
    RECEIVER_ORIGIN,
    OWNER_ACTIONS,
    BROWSER_ACTIONS,
    PARTICIPATION_ACTIONS,
    require_cast_display,
)
from .display_live import DisplayLiveView
from .display_transport import DisplayTransitionView, SECURITY_HEADERS


def cors(request):
    if tuple(request.headers.getall("Origin", [])) != (RECEIVER_ORIGIN,):
        return {"Vary": "Origin"}
    return {"Access-Control-Allow-Origin": RECEIVER_ORIGIN, "Vary": "Origin"}


class CastDisplayTransitionView(DisplayTransitionView):
    namespace = "cast"
    service_class = CastDisplayService

    def register(self, hass, app, router):
        """Keep this closed prefix's preflight separate from configured HA CORS.

        HomeAssistantView.register adds its automatic OPTIONS handler whenever
        HA has configured CORS origins. That conflicts with our explicit
        preflight and would also apply an unrelated global origin policy here.
        Retain HA's normal request wrapper for both actual route handlers.
        """
        from homeassistant.components.http.view import request_handler_factory

        for method in ("post", "options"):
            router.add_route(
                method, self.url, request_handler_factory(hass, self, getattr(self, method))
            )

    async def post(self, request):
        response = await super().post(request)
        if self.action not in OWNER_ACTIONS:
            response.headers.update(cors(request))
        return response

    async def options(self, request):
        origin = tuple(request.headers.getall("Origin", []))
        headers = request.headers.get("Access-Control-Request-Headers", "")
        requested = {item.strip().lower() for item in headers.split(",") if item.strip()}
        if (
            self.action in OWNER_ACTIONS
            or not request.secure
            or request.query_string
            or origin != (RECEIVER_ORIGIN,)
            or request.headers.get("Access-Control-Request-Method") != "POST"
            or requested - {"content-type", "authorization"}
        ):
            return web.Response(status=403, headers={**SECURITY_HEADERS, "Vary": "Origin"})
        return web.Response(
            status=204,
            headers={
                **SECURITY_HEADERS,
                **cors(request),
                "Access-Control-Allow-Methods": "POST",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            },
        )


class CastDisplayLiveView(DisplayLiveView):
    url = "/api/djconnect/v1/cast/live"
    name = "api:djconnect:cast:live"

    def browser_origin_allowed(self, request, selected):
        return tuple(request.headers.getall("Origin", [])) == (RECEIVER_ORIGIN,)

    def authorize_transport_display(self, manager, display):
        require_cast_display(self.hass, manager, display)


def cast_display_views(hass):
    return [
        CastDisplayTransitionView(hass, action)
        for action in (
            *OWNER_ACTIONS,
            *sorted(BROWSER_ACTIONS),
            *("participation/display/" + name for name in sorted(PARTICIPATION_ACTIONS)),
        )
    ] + [CastDisplayLiveView(hass)]
