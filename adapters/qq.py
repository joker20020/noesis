"""QQ Bot adapter — Tencent official botpy SDK. GA-compatible approach."""
import asyncio
import time
from collections import deque

try:
    import botpy
    from botpy.message import C2CMessage, GroupMessage
    HAS_BOTPY = True
except ImportError:
    HAS_BOTPY = False


class QQAdapter:
    """GA pattern: official QQ Bot SDK. Requires app_id + app_secret from QQ Open Platform."""

    def __init__(self, engine, app_id: str = "", app_secret: str = "", allowed_users: str = ""):
        self._engine = engine
        self._app_id = app_id
        self._app_secret = app_secret
        self._allowed = {u.strip() for u in allowed_users.split(",") if u.strip()} if allowed_users else set()
        self._client = None
        self._seen = deque(maxlen=500)
        self._msg_seq = 0

    async def start(self):
        if not HAS_BOTPY:
            raise RuntimeError("pip install qq-botpy")
        if not self._app_id or not self._app_secret:
            raise RuntimeError("QQ app_id and app_secret required")

        self._client = _QQClient(self._engine, self._allowed, self._seen, self)
        print(f"[QQ] Starting botpy client (allowed: {len(self._allowed)} users)")
        backoff = 5
        while True:
            try:
                start = time.time()
                await self._client.start(appid=self._app_id, secret=self._app_secret)
            except Exception as e:
                elapsed = time.time() - start
                print(f"[QQ] Disconnected after {elapsed:.0f}s: {e}")
            backoff = min(backoff * 2, 300) if elapsed < 60 else 5
            print(f"[QQ] Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)

    async def stop(self):
        pass

    def next_seq(self) -> int:
        self._msg_seq += 1
        return self._msg_seq


class _QQClient(botpy.Client):
    def __init__(self, engine, allowed, seen, adapter):
        intents = botpy.Intents(public_messages=True, direct_message=True)
        super().__init__(intents=intents)
        self._engine = engine
        self._allowed = allowed
        self._seen = seen
        self._adapter = adapter

    async def on_c2c_message_create(self, message: C2CMessage):
        await self._handle(message, is_group=False)

    async def on_group_at_message_create(self, message: GroupMessage):
        await self._handle(message, is_group=True)

    async def _handle(self, message, is_group: bool):
        msg_id = message.id
        if msg_id in self._seen:
            return
        self._seen.append(msg_id)

        user_id = getattr(message, 'member_openid', None) if is_group else getattr(message, 'user_openid', None)
        user_id = user_id or getattr(message, 'author', {}).get('id', 'unknown')
        if self._allowed and str(user_id) not in self._allowed:
            return

        content = getattr(message, 'content', '') or ''
        if not content.strip():
            return

        result = await self._engine.run(content, session_id=f"qq_{user_id}")
        seq = self._adapter.next_seq()
        for i in range(0, len(result), 1500):
            chunk = result[i:i+1500]
            if is_group:
                await self.api.post_group_message(group_openid=message.group_openid,
                    content=chunk, msg_id=msg_id, msg_seq=seq)
            else:
                await self.api.post_c2c_message(openid=user_id,
                    content=chunk, msg_id=msg_id, msg_seq=seq)
