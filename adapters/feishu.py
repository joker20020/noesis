"""Feishu/Lark Bot adapter — lark-oapi SDK. GA-compatible approach."""
import asyncio
import json

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import *
    HAS_LARK = True
except ImportError:
    HAS_LARK = False


class FeishuAdapter:
    """GA pattern: lark-oapi with event subscription. Long-connection mode."""

    def __init__(self, engine, app_id: str = "", app_secret: str = ""):
        self._engine = engine
        self._app_id = app_id
        self._app_secret = app_secret
        self._ws_client = None

    async def start(self):
        if not HAS_LARK:
            raise RuntimeError("pip install lark-oapi")
        if not self._app_id or not self._app_secret:
            raise RuntimeError("Feishu app_id and app_secret required")

        client = lark.ws.Client(
            lark.ws.ClientConfig(
                app_id=self._app_id,
                app_secret=self._app_secret,
                event_handler=_FeishuHandler(self._engine),
            )
        )
        self._ws_client = client
        print(f"[Feishu] WebSocket client starting...")
        await client.start()

    async def stop(self):
        if self._ws_client:
            await self._ws_client.stop()


class _FeishuHandler(lark.ws.EventHandler):
    def __init__(self, engine):
        self._engine = engine

    async def handle_p2_im_message_receive_v1(self, ctx, event):
        msg_type = event.message.message_type
        if msg_type != "text":
            return
        content = json.loads(event.message.content)
        text = content.get("text", "").strip()
        if not text:
            return
        chat_id = event.message.chat_id

        if text.startswith("/restart") or text.startswith("/clear"):
            await self._engine.restart_session()
            await ctx.do(CreateMessageRequest.builder().receive_id_type("chat_id").request_body(
                CreateMessageRequestBody.builder().msg_type("text").content(json.dumps({"text": "会话已重置"})).build()).build())
            return

        result = await self._engine.run(text)
        # Split and reply
        for i in range(0, len(result), 4000):
            reply = result[i:i+4000]
            req = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(CreateMessageRequestBody.builder()
                    .msg_type("text")
                    .content(json.dumps({"text": reply}))
                    .build()) \
                .build()
            await ctx.do(req)
