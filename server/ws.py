"""WebSocket handler — fixed session for all platforms."""
import json
from fastapi import WebSocket, WebSocketDisconnect

FIXED_SESSION = "infocap"


class ChatHandler:
    def __init__(self, engine):
        self._engine = engine

    async def handle(self, ws: WebSocket):
        await ws.accept()
        # Load history for fixed session
        try:
            records = await self._engine.neo4j.run(
                """MATCH (s:Session {session_id: $sid})-[:HAS_STEP]->(first:ExecutionStep)
                   MATCH (first)-[:NEXT*0..]->(step:ExecutionStep)
                   RETURN DISTINCT step ORDER BY step.step_index""",
                {"sid": FIXED_SESSION},
            )
            history = []
            for r in records:
                step = r["step"]
                content = step.get("content", "")
                if isinstance(content, str):
                    try:
                        blocks = json.loads(content)
                    except Exception:
                        continue
                    for block in blocks:
                        if block["type"] == "text":
                            history.append({"role": step.get("role", "assistant"), "content": block.get("text", "")})
                        elif block["type"] == "tool_result":
                            history.append({"role": "system", "content": f"[{block.get('name', 'tool')}]\n{block.get('output', '')}"})
            await ws.send_text(json.dumps({"type": "history", "messages": history}, default=str))
        except Exception:
            pass

        try:
            while True:
                msg = await ws.receive_text()
                data = json.loads(msg)
                if data.get("__abort"):
                    self._engine.abort()
                    await ws.send_text(json.dumps({"type": "message", "content": "[Interrupted]"}))
                    continue
                user_input = data.get("content", "")
                if not user_input.strip():
                    continue

                await ws.send_text(json.dumps({"type": "status", "status": "thinking"}))

                async def on_event(event):
                    await ws.send_text(json.dumps(event, default=str))

                await self._engine.run(user_input, on_event=on_event)
        except WebSocketDisconnect:
            pass
