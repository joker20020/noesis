"""Discord Bot adapter — discord.py, prefix '!'. """
import asyncio

try:
    import discord
    HAS_DC = True
except ImportError:
    HAS_DC = False


class DiscordAdapter:
    def __init__(self, engine, token: str = "", channel_ids: list[int] | None = None):
        self._engine = engine
        self._token = token
        self._channel_ids = channel_ids or []
        self._client = None

    async def start(self):
        if not HAS_DC:
            print("[Discord] discord.py not installed: pip install discord.py")
            return
        if not self._token:
            print("[Discord] Token not configured, skipping")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            print(f"[Discord] Logged in as {self._client.user}")

        @self._client.event
        async def on_message(message):
            if message.author == self._client.user:
                return
            if self._channel_ids and message.channel.id not in self._channel_ids:
                return
            if not message.content.startswith("!"):
                return
            prompt = message.content[1:].strip()
            if not prompt:
                return
            async with message.channel.typing():
                result = await self._engine.run(prompt, session_id=f"dc_{message.author.id}")
                for i in range(0, len(result), 1900):
                    await message.reply(result[i:i+1900])

        await self._client.start(self._token)

    async def stop(self):
        if self._client:
            await self._client.close()
