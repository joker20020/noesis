"""QQ Bot adapter via NapCatQQ (OneBot v11 protocol, reverse WebSocket).

Setup:
1. Install NapCatQQ: https://github.com/NapNeko/NapCatQQ
2. Configure NapCat WebUI → Network → New → WebSocket Client
   URL: ws://127.0.0.1:8080/onebot/v11/ws
   Message Format: Array
3. Start infoCap — it listens on ws://0.0.0.0:8080/onebot/v11/ws
4. Send QQ messages — infoCap auto-replies

Architecture:
  QQ → NapCatQQ → reverse WS → infoCap qq adapter → Agent Engine → OneBot API reply
"""
import asyncio
import json
import time
from urllib.parse import urlparse
import httpx
try:
    import websockets
    HAS_WS = True
except ImportError:
    HAS_WS = False


class QQAdapter:
    def __init__(self, engine, host: str = "0.0.0.0", port: int = 8080,
                 napcat_http: str = "http://127.0.0.1:3000"):
        self._engine = engine
        self._host = host
        self._port = port
        self._napcat_http = napcat_http
        self._running = False
        self._msg_counter = 0

    async def start(self):
        if not HAS_WS:
            print("[QQ] websockets not installed: pip install websockets")
            return

        self._running = True
        path = "/onebot/v11/ws"
        print(f"[QQ] Listening on ws://{self._host}:{self._port}{path}")
        print(f"[QQ] NapCat HTTP API: {self._napcat_http}")
        print(f"[QQ] Configure NapCat WebUI → WebSocket Client → ws://127.0.0.1:{self._port}{path}")

        async def handle(websocket):
            async for raw in websocket:
                try:
                    data = json.loads(raw)
                    await self._handle_event(websocket, data)
                except Exception as e:
                    print(f"[QQ] Event error: {e}")

        async with websockets.serve(handle, self._host, self._port) as server:
            await server.wait_closed()

    async def stop(self):
        self._running = False

    async def _handle_event(self, ws, data: dict):
        """Handle OneBot v11 event."""
        post_type = data.get("post_type", "")
        if post_type == "message":
            await self._handle_message(ws, data)
        elif post_type == "meta_event":
            if data.get("meta_event_type") == "lifecycle":
                print(f"[QQ] NapCat connected: {data.get('sub_type')}")

    async def _handle_message(self, ws, data: dict):
        """Handle incoming QQ message."""
        msg_type = data.get("message_type", "private")
        user_id = str(data.get("user_id", "unknown"))
        raw_msg = data.get("raw_message", data.get("message", ""))
        message_id = data.get("message_id", 0)

        if isinstance(raw_msg, list):
            # CQ code array format
            texts = []
            for seg in raw_msg:
                if seg.get("type") == "text":
                    texts.append(seg.get("data", {}).get("text", ""))
            raw_msg = "".join(texts)

        if not isinstance(raw_msg, str) or not raw_msg.strip():
            return

        self._msg_counter += 1
        print(f"[QQ #{self._msg_counter}] {msg_type} from {user_id}: {raw_msg[:50]}")

        session_id = f"qq_{user_id}"
        if msg_type == "group":
            group_id = data.get("group_id", "")
            session_id = f"qq_group_{group_id}_{user_id}"

        try:
            result = await self._engine.run(raw_msg, session_id=session_id)
        except Exception as e:
            result = f"Error: {e}"

        # Split long responses
        for chunk in [result[i:i+1500] for i in range(0, len(result), 1500)]:
            await self._send_reply(ws, data, chunk)
            await asyncio.sleep(0.3)  # Rate limit

    async def _send_reply(self, ws, original: dict, content: str):
        """Send reply via OneBot API."""
        msg_type = original.get("message_type", "private")
        reply = {
            "action": "send_private_msg" if msg_type == "private" else "send_group_msg",
            "params": {
                "message": [{"type": "text", "data": {"text": content}}],
            },
            "echo": f"infocap_{int(time.time())}",
        }
        if msg_type == "private":
            reply["params"]["user_id"] = original.get("user_id")
        else:
            reply["params"]["group_id"] = original.get("group_id")

        await ws.send(json.dumps(reply, ensure_ascii=False))

    async def send_direct(self, user_id: int, content: str, is_group: bool = False,
                          group_id: int | None = None):
        """Direct HTTP API call (alternative to WS reply)."""
        action = "send_group_msg" if is_group else "send_private_msg"
        params = {"message": [{"type": "text", "data": {"text": content}}]}
        if is_group and group_id:
            params["group_id"] = group_id
        else:
            params["user_id"] = user_id

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._napcat_http}/{action}",
                json=params,
            )
            return resp.json()
