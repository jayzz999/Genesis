import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.genesis.api import router as genesis_router
from backend.genesis import events as _genesis_events

logging.basicConfig(level=logging.INFO)


# ── WebSocket connection manager ──────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, ws: WebSocket, client_id: str):
        await ws.accept()
        self.active[client_id] = ws

    def disconnect(self, client_id: str):
        self.active.pop(client_id, None)

    async def broadcast(self, event: dict):
        dead = []
        for cid, ws in self.active.items():
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.active.pop(cid, None)


manager = ConnectionManager()


async def _genesis_to_ws(event: dict) -> None:
    await manager.broadcast(event)


# ── App lifecycle ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start organism heartbeat supervisor
    from backend.genesis import lifecycle as _lifecycle
    _lifecycle.start()
    print("[Genesis] Lifecycle supervisor started")

    # Register MCP global servers from catalog
    from backend.genesis.mcp import client as _mcp_client, catalog as _mcp_catalog
    global_specs = _mcp_catalog.load_global_specs()
    if global_specs:
        await _mcp_client.pool.ensure_global(global_specs)
        print(f"[Genesis] MCP pool: {len(global_specs)} global server(s) registered")

    # Forward all genesis events to WebSocket clients
    _genesis_events.subscribe(_genesis_to_ws)

    yield

    # Shutdown
    try:
        from backend.genesis import lifecycle as _lifecycle
        await _lifecycle.stop()
    except Exception:
        pass
    try:
        from backend.genesis.mcp import client as _mcp_client
        await _mcp_client.pool.shutdown()
    except Exception:
        pass


app = FastAPI(title="Genesis", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(genesis_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Genesis"}


# ── WebSocket endpoint ────────────────────────────────────────

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(ws: WebSocket, client_id: str):
    await manager.connect(ws, client_id)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        manager.disconnect(client_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8002")),
        reload=True,
    )
