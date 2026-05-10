"""QQ Bot adapter — Tencent official botpy SDK. GA-compatible approach."""
import asyncio
import threading
import time
from collections import deque

try:
    import botpy
    from botpy.message import C2CMessage, GroupMessage
    HAS_BOTPY = True
except ImportError:
    HAS_BOTPY = False


class QQAdapter:
    """GA pattern: official QQ Bot SDK. app_id + app_secret from QQ Open Platform."""

    def __init__(self, engine, app_id: str = "", app_secret: str = "", allowed_users: str = ""):
        self._engine = engine
        self._app_id = app_id
        self._app_secret = app_secret
        self._allowed = {u.strip() for u in allowed_users.split(",") if u.strip()} if allowed_users else set()
        self._client = None
        self._seen = deque(maxlen=500)
        self._seq = 0
        self._seq_lock = threading.Lock()

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    async def start(self):
        if not HAS_BOTPY:
            raise RuntimeError("pip install qq-botpy")
        if not self._app_id or not self._app_secret:
            raise RuntimeError("QQ app_id and app_secret required")

        intents = self._build_intents()
        adapter = self

        class _BotClient(botpy.Client):
            def __init__(self):
                super().__init__(intents=intents, ext_handlers=False)

            async def on_ready(self):
                print(f"[QQ] Ready: {self.robot.name}")

            async def on_c2c_message_create(self, msg: C2CMessage):
                await adapter._on_message(msg, is_group=False)

            async def on_group_at_message_create(self, msg: GroupMessage):
                await adapter._on_message(msg, is_group=True)

            async def on_direct_message_create(self, msg):
                await adapter._on_message(msg, is_group=False)

        self._client = _BotClient()
        print(f"[QQ] Bot starting (allowed: {len(self._allowed)} users)")
        backoff = 5
        while True:
            try:
                start = time.time()
                await self._client.start(appid=self._app_id, secret=self._app_secret)
            except Exception as e:
                elapsed = time.time() - start
                print(f"[QQ] Disconnected ({elapsed:.0f}s): {e}")
                backoff = 5 if elapsed >= 60 else min(backoff * 2, 300)
                print(f"[QQ] Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)

    @staticmethod
    def _build_intents():
        try:
            return botpy.Intents(public_messages=True, direct_message=True)
        except Exception:
            intents = botpy.Intents()
            for attr in ("public_messages", "direct_message", "c2c_message",
                         "group_at_message", "guild_messages"):
                try:
                    setattr(intents, attr, True)
                except Exception:
                    pass
            return intents

    async def stop(self):
        pass

    async def _on_message(self, message, is_group: bool):
        msg_id = getattr(message, 'id', None) or str(time.time())
        if msg_id in self._seen:
            return
        self._seen.append(msg_id)

        content = getattr(message, 'content', '') or ''
        if not content.strip():
            return

        # botpy: _User has .user_openid; GroupMessage author also has .user_openid
        author = getattr(message, 'author', None)
        user_id = getattr(author, 'user_openid', '') if author else ''

        if self._allowed and str(user_id) not in self._allowed:
            return

        result = await self._engine.run(content)
        await self._send_reply(message, result, user_id, is_group)

    async def _send_reply(self, message, text: str, user_id: str, is_group: bool):
        chunks = self._split_text(text, 1500)
        for chunk in chunks:
            seq = self._next_seq()
            if is_group:
                await self._client.api.post_group_message(
                    group_openid=message.group_openid,
                    content=chunk, msg_type=0, msg_id=getattr(message, 'id', ''),
                    msg_seq=seq)
            else:
                await self._client.api.post_c2c_message(
                    openid=user_id,
                    content=chunk, msg_type=0, msg_id=getattr(message, 'id', ''),
                    msg_seq=seq)

    @staticmethod
    def _split_text(text: str, limit: int) -> list[str]:
        if len(text) <= limit:
            return [text]
        chunks = []
        for i in range(0, len(text), limit):
            chunks.append(text[i:i+limit])
        return chunks
