"""Music Canvas state shares the canonical transactional persistence owner."""
from __future__ import annotations
import json
from copy import deepcopy
from .service import PersistenceRepository
from ..music_canvas import fresh_state, need


class CanvasRepository(PersistenceRepository):
    async def read(self, authorize=None):
        def read(tx):
            row = tx.fetchone("SELECT body FROM djconnect_music_canvas WHERE singleton=1")
            return json.loads(row[0]) if row else fresh_state()
        return await self._async_in_transaction(read, authorize=authorize)

    async def mutate(self, change, authorize):
        def mutate(tx):
            row = tx.fetchone("SELECT body FROM djconnect_music_canvas WHERE singleton=1")
            state = json.loads(row[0]) if row else fresh_state()
            result = change(state)
            body = json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False)
            need(len(body.encode()) <= 262144, "canvas_storage_full", 503)
            tx.execute("INSERT INTO djconnect_music_canvas(singleton,body) VALUES(1,?) "
                       "ON CONFLICT(singleton) DO UPDATE SET body=excluded.body", (body,))
            return deepcopy(result)
        return await self._async_in_transaction(mutate, authorize=authorize, finalize_authorize=authorize)
