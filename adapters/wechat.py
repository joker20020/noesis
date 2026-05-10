"""OpenClaw Gateway WebSocket v3 protocol adapter.

Compatible with @tencent-weixin/openclaw-weixin plugin.
The plugin handles all WeChat iLink protocol complexity internally
and communicates with infoCap via the standard Gateway WS protocol.

Plugin connects to: ws://127.0.0.1:18789
"""

import asyncio
import json
import time
import uuid

try:
    import websockets
    HAS_WS = True
except ImportError:
    HAS_WS = False

PROTOCOL_VERSION = 3
DEFAULT_PORT = 18789


class GatewayProtocol:
    """OpenClaw Gateway WebSocket v3 protocol handler."""

    def __init__(self, engine, host: str = "127.0.0.1", port: int = DEFAULT_PORT):
        self._engine = engine
        self._host = host
        self._port = port
        self._running = False
        self._conn_id = None
        self._tick_count = 0

    async def start(self):
        if not HAS_WS:
            print("[Gateway] websockets not installed: pip install websockets")
            return

        self._running = True
        self._conn_id = uuid.uuid4().hex[:8]
        print(f"[Gateway] Listening on ws://{self._host}:{self._port}")
        print(f"[Gateway] Protocol v{PROTOCOL_VERSION}, connId: {self._conn_id}")
        print(f"[Gateway] Ready for openclaw-weixin plugin connection")

        async def handle(ws):
            await self._on_connect(ws)
            async for raw in ws:
                try:
                    frame = json.loads(raw)
                    await self._handle_frame(ws, frame)
                except Exception as e:
                    print(f"[Gateway] Frame error: {e}")

        try:
            async with websockets.serve(handle, self._host, self._port):
                await asyncio.Future()  # Run forever
        except OSError as e:
            print(f"[Gateway] Port {self._port} in use: {e}")

    async def stop(self):
        self._running = False

    async def _on_connect(self, ws):
        """Send connection challenge immediately on connect."""
        nonce = uuid.uuid4().hex[:16]
        ts = int(time.time() * 1000)
        challenge = {
            "type": "event",
            "event": "connect.challenge",
            "payload": {"nonce": nonce, "ts": ts},
        }
        await ws.send(json.dumps(challenge))

    async def _handle_frame(self, ws, frame: dict):
        ftype = frame.get("type", "")
        mid = frame.get("id", "")

        if ftype == "req":
            method = frame.get("method", "")
            params = frame.get("params", {})

            if method == "connect":
                await self._handle_connect(ws, mid, params)
            elif method == "health":
                await self._send_res(ws, mid, True, {"status": "ok", "connId": self._conn_id})
            elif method == "agent":
                await self._handle_agent(ws, mid, params)
            elif method == "chat.send":
                await self._handle_chat(ws, mid, params)
            elif method == "config.get":
                await self._send_res(ws, mid, True, {})
            else:
                await self._send_res(ws, mid, True, {"method": method, "handled": False})

    async def _handle_connect(self, ws, mid: str, params: dict):
        """Handle connect handshake."""
        client_info = params.get("client", {})
        print(f"[Gateway] Client connected: {client_info.get('id', '?')} v{client_info.get('version', '?')}")

        hello = {
            "type": "res", "id": mid, "ok": True,
            "payload": {
                "type": "hello-ok",
                "protocol": PROTOCOL_VERSION,
                "server": {"version": "infocap-0.4.0", "connId": self._conn_id},
                "features": {
                    "methods": ["connect", "health", "agent", "agent.wait", "chat.send", "config.get"],
                    "events": ["tick", "agent", "presence"],
                },
                "policy": {
                    "maxPayload": 26214400,
                    "maxBufferedBytes": 52428800,
                    "tickIntervalMs": 30000,
                },
            },
        }
        await ws.send(json.dumps(hello))

    async def _handle_agent(self, ws, mid: str, params: dict):
        """Handle agent request — the core method for WeChat messages."""
        message = params.get("message") or params.get("text") or params.get("prompt", "")
        session_key = params.get("sessionKey") or params.get("sessionId") or f"wechat_{uuid.uuid4().hex[:8]}"

        if not message or not isinstance(message, str):
            await self._send_res(ws, mid, False, error={"code": "INVALID_MESSAGE", "message": "Missing message"})
            return

        print(f"[Gateway] Agent request: session={session_key[:20]}... msg={message[:50]}...")

        try:
            # Send "thinking" tick
            self._tick_count += 1
            await ws.send(json.dumps({
                "type": "event", "event": "tick",
                "payload": {"status": "thinking", "sessionKey": session_key},
                "seq": self._tick_count,
            }))

            # Run agent
            result = await self._engine.run(message)

            # Send response
            await self._send_res(ws, mid, True, {
                "type": "agent-response",
                "text": result,
                "sessionKey": session_key,
                "finishReason": "stop",
            })

            # Send completion event
            self._tick_count += 1
            await ws.send(json.dumps({
                "type": "event", "event": "agent",
                "payload": {"status": "done", "sessionKey": session_key, "text": result[:200]},
                "seq": self._tick_count,
            }))

        except Exception as e:
            await self._send_res(ws, mid, False, error={"code": "AGENT_ERROR", "message": str(e)})

    async def _handle_chat(self, ws, mid: str, params: dict):
        """Handle chat.send — simpler message interface."""
        text = params.get("text") or params.get("message", "")
        session_key = params.get("sessionKey", f"chat_{uuid.uuid4().hex[:8]}")
        if text:
            result = await self._engine.run(text)
            await self._send_res(ws, mid, True, {"text": result, "sessionKey": session_key})
        else:
            await self._send_res(ws, mid, False, error={"code": "EMPTY", "message": "No text"})

    async def _send_res(self, ws, mid: str, ok: bool, payload=None, error=None):
        frame = {"type": "res", "id": mid, "ok": ok}
        if ok:
            frame["payload"] = payload or {}
        else:
            frame["error"] = error or {"code": "UNKNOWN", "message": "Unknown error"}
        await ws.send(json.dumps(frame, default=str))
