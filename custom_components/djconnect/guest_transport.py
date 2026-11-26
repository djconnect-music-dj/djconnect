"""Same bounded HTTPS/origin/final-release transport, separate guest API shapes."""
from .display_transport import DisplayTransitionView
from .guest_service import GuestParticipationService, SHAPES


class GuestTransitionView(DisplayTransitionView):
    namespace = 'participation'
    service_class = GuestParticipationService


def participation_views(hass):
    return [GuestTransitionView(hass, action) for action in SHAPES]
