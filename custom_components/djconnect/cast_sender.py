"""Home Assistant sender for one selected VibeCast receiver handoff."""

import logging
from queue import Full, Queue
import re
from secrets import token_hex
from threading import Lock
from uuid import UUID

from .display_admission import DisplayAdmissionError

APP_ID = "8EA92910"
NAMESPACE = "urn:x-cast:com.djconnect.vibecast.v1"


def receiver_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise DisplayAdmissionError("display_code_invalid", 400)
    return UUID(hex=value)


class CastSender:
    def __init__(self, target, known_hosts):
        self.target = target
        self._known_hosts = known_hosts
        self._lock = Lock()
        self._closed = False
        self._cast = None
        self._browser = None

    def connect(self):
        with self._lock:
            try:
                import pychromecast

                if self._closed:
                    raise RuntimeError
                devices, self._browser = pychromecast.get_listed_chromecasts(
                    uuids=[self.target], known_hosts=self._known_hosts,
                    discovery_timeout=5, timeout=4, tries=1,
                )
                if len(devices) != 1:
                    raise RuntimeError
                self._cast = device = devices[0]
                if device.cast_info.uuid != self.target or device.cast_info.cast_type != "cast":
                    raise RuntimeError
                # PyChromecast's debug messages can contain custom-channel payloads.
                # Silence just this connection, independently of HA logger settings.
                logger = logging.Logger(__name__)
                logger.disabled = True
                device.socket_client.logger = logger
                device.socket_client.source_id = "sender-" + token_hex(16)
                device.wait(timeout=5)
            except Exception:
                raise DisplayAdmissionError("cast_receiver_unavailable", 503) from None

    def launch(self):
        with self._lock:
            try:
                if self._closed:
                    raise RuntimeError
                self._cast.start_app(APP_ID, timeout=7)
            except Exception:
                raise DisplayAdmissionError("cast_receiver_unavailable", 503) from None

    def claim(self, envelope):
        from pychromecast.controllers import BaseController

        with self._lock:
            receiver = self._cast
            status = receiver.status
            if self._closed or status is None or status.app_id != APP_ID or (
                not status.transport_id or NAMESPACE not in status.namespaces
            ):
                raise DisplayAdmissionError("cast_receiver_unavailable", 503)
            replies = Queue(maxsize=1)
            destination = status.transport_id

            class Channel(BaseController):
                def receive_message(self, message, data):
                    if (
                        message.source_id == destination
                        and message.destination_id == receiver.socket_client.source_id
                        and data.get("kind") == "vibecast_display_claim"
                        and data.get("handoff_id") == envelope["handoff_id"]
                    ):
                        try:
                            replies.put_nowait(data)
                        except Full:
                            pass
                    return True

            try:
                receiver.register_handler(Channel(NAMESPACE))
                receiver.socket_client.send_message(
                    destination, NAMESPACE, envelope, no_add_request_id=True
                )
                return replies.get(timeout=7)
            except Exception:
                raise DisplayAdmissionError("cast_receiver_unavailable", 503) from None

    def close(self):
        with self._lock:
            self._closed = True
            try:
                if self._cast is not None and self._cast.socket_client.is_alive():
                    self._cast.disconnect(timeout=3)
            finally:
                if self._browser is not None:
                    self._browser.stop_discovery()
