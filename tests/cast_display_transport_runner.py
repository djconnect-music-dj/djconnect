"""Real local TLS/aiohttp adapters over genuine unit-owner fixtures, not actual HA."""

import importlib
import ssl
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

from tests import test_cast_display as fixtures


class CastDisplayHTTPTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        real_web = importlib.import_module("aiohttp.web")
        real_timeout = importlib.import_module("aiohttp.client").ClientTimeout
        fixtures.CastDisplayTests.setUpClass()
        # The owner fixture replaces these two package attributes intentionally.
        # Restore actual aiohttp for this separate-process real-TLS qualification.
        cls.web_patch = patch.object(aiohttp, "web", real_web)
        cls.timeout_patch = patch.object(aiohttp, "ClientTimeout", real_timeout)
        cls.web_patch.start()
        cls.timeout_patch.start()
        cls.module = importlib.import_module("custom_components.djconnect.cast_display_transport")

    @classmethod
    def tearDownClass(cls):
        cls.timeout_patch.stop()
        cls.web_patch.stop()
        fixtures.CastDisplayTests.tearDownClass()

    async def asyncSetUp(self):
        self.case = fixtures.CastDisplayTests()
        await self.case.asyncSetUp()
        self.live = importlib.import_module("custom_components.djconnect.display_live")
        self.origin = patch.object(
            self.live, "selected_ha_origin", side_effect=lambda _: self.case.base.origin
        )
        self.origin.start()
        self.temp = tempfile.TemporaryDirectory(prefix="cast-tls-")
        certificate = Path(self.temp.name) / "cert.pem"
        key = Path(self.temp.name) / "key.pem"
        subprocess.run(
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(certificate),
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        app = web.Application()
        for view in self.module.cast_display_views(self.case.fixture.hass):
            if isinstance(view, self.module.CastDisplayLiveView):
                app.router.add_get(view.url, view.get)
            else:
                app.router.add_post(view.url, view.post)
                app.router.add_options(view.url, view.options)
        self.server = TestServer(app, scheme="https")
        await self.server.start_server(ssl=context)
        self.client = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()
        self.origin.stop()
        self.temp.cleanup()
        await self.case.asyncTearDown()

    async def post(self, action, body, *, headers=None):
        async with self.client.post(
            self.server.make_url("/api/djconnect/v1/cast/" + action),
            json={"contract_version": 1, **body},
            headers=headers or {},
        ) as response:
            return response.status, dict(response.headers), await response.json()

    async def admitted(self):
        status, _, b = await self.post(
            "owner/bootstrap",
            {
                "identity": self.case.fixture.identity,
                "session_id": self.case.fixture.active.session_id,
            },
            headers=self.case.fixture.headers,
        )
        self.assertEqual(status, 200, b)
        import secrets

        nonce = secrets.token_urlsafe(32)
        status, headers, c = await self.post(
            "claim",
            {"browser_nonce": nonce},
            headers={
                "Origin": self.module.RECEIVER_ORIGIN,
                "Authorization": "Bearer " + b["bootstrap_token"],
            },
        )
        self.assertEqual(status, 200, c)
        self.assertEqual(headers["Access-Control-Allow-Origin"], self.module.RECEIVER_ORIGIN)
        await self.case.base.call(
            "owner/approve",
            {
                **{k: c[k] for k in ("issuer_epoch", "claim_id", "browser_generation", "code")},
                "session_id": self.case.fixture.active.session_id,
                "share": {
                    "mode": "create",
                    "consent": True,
                    "live": True,
                    "lifetime_seconds": 14400,
                },
            },
        )
        status, _, p = await self.post(
            "collect",
            {
                **{
                    k: c[k]
                    for k in ("issuer_epoch", "claim_id", "claim_secret", "browser_generation")
                },
                "browser_nonce": nonce,
            },
            headers={"Origin": self.module.RECEIVER_ORIGIN},
        )
        self.assertEqual(status, 200, p)
        return p

    async def test_real_tls_claim_collect_and_same_real_B_connection_renew(self):
        p = await self.admitted()
        ws = await self.client.ws_connect(
            self.server.make_url("/api/djconnect/v1/cast/live"),
            headers={"Origin": self.module.RECEIVER_ORIGIN},
        )
        import secrets

        await ws.send_json(
            {
                "type": "authenticate",
                "contract_version": 1,
                "grant_token": p["grant_token"],
                "issuer_epoch": p["issuer_epoch"],
                "display_id": p["display_id"],
                "connection_nonce": secrets.token_urlsafe(32),
            }
        )
        frame = await ws.receive_json(timeout=3)
        self.assertEqual(frame["type"], "snapshot")
        self.assertEqual(frame["snapshot"]["display_id"], p["display_id"])
        manager = self.case.manager
        hub = importlib.import_module(
            "custom_components.djconnect.display_delivery"
        ).display_live_hub(manager)
        connection = hub.connections[p["display_id"]]
        self.assertIsInstance(connection, self.live._Connection)
        self.assertIs(connection.display, manager._display_admission._displays[p["display_id"]])
        self.assertEqual(connection.origin, self.case.base.origin)
        before = connection.display.lease_deadline
        clock = manager._display_admission._clock
        manager._display_admission._clock = lambda: clock() + 5
        status, _, renew = await self.post(
            "renew",
            {"issuer_epoch": p["issuer_epoch"], "display_id": p["display_id"], "renew_sequence": 1},
            headers={
                "Origin": self.module.RECEIVER_ORIGIN,
                "Authorization": "Bearer " + p["grant_token"],
            },
        )
        self.assertEqual(status, 200, renew)
        self.assertGreater(connection.display.lease_deadline, before)
        self.case.fixture.entry.disabled_by = "synthetic-withdrawn"
        closed = await ws.receive(timeout=3)
        self.assertIn(
            closed.type,
            (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR),
        )
        await ws.close()
        self.assertFalse(connection.current())

    async def test_CORS_is_closed_and_native_bootstrap_never_has_browser_CORS(self):
        path = self.server.make_url("/api/djconnect/v1/cast/claim")
        good = {
            "Origin": self.module.RECEIVER_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        }
        async with self.client.options(path, headers=good) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(
                response.headers["Access-Control-Allow-Origin"], self.module.RECEIVER_ORIGIN
            )
            self.assertNotIn("Access-Control-Allow-Credentials", response.headers)
        for delta in (
            {"Origin": "null"},
            {"Origin": "https://other.example.net"},
            {"Access-Control-Request-Method": "DELETE"},
            {"Access-Control-Request-Headers": "x-admin"},
        ):
            async with self.client.options(path, headers={**good, **delta}) as response:
                self.assertEqual(response.status, 403)
                self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        async with self.client.options(
            self.server.make_url("/api/djconnect/v1/cast/owner/bootstrap"), headers=good
        ) as response:
            self.assertEqual(response.status, 403)
        status, headers, _ = await self.post(
            "owner/bootstrap",
            {
                "identity": self.case.fixture.identity,
                "session_id": self.case.fixture.active.session_id,
            },
            headers=self.case.fixture.headers,
        )
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    async def test_duplicate_JSON_authorization_and_wrong_origin_are_rejected(self):
        path = self.server.make_url("/api/djconnect/v1/cast/claim")
        async with self.client.post(
            path,
            data='{"contract_version":1,"contract_version":1}',
            headers={"Content-Type": "application/json", "Origin": self.module.RECEIVER_ORIGIN},
        ) as response:
            self.assertEqual(response.status, 400)
        async with self.client.post(
            path,
            json={"contract_version": 1, "browser_nonce": "x" * 43},
            headers=[
                ("Origin", self.module.RECEIVER_ORIGIN),
                ("Authorization", "Bearer x"),
                ("Authorization", "Bearer y"),
            ],
        ) as response:
            self.assertEqual(response.status, 400)
        with self.assertRaises(aiohttp.WSServerHandshakeError) as caught:
            await self.client.ws_connect(
                self.server.make_url("/api/djconnect/v1/cast/live"),
                headers={"Origin": "https://other.example.net"},
            )
        self.assertEqual(caught.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
