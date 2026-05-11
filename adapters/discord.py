"""Discord Bot adapter — discord.py gateway, prefix commands."""
import asyncio

from adapters.formatters import format_event

try:
    import discord
    from discord.ext import commands
    HAS_DC = True
except ImportError:
    HAS_DC = False


class DiscordAdapter:
    """GA pattern: gateway connection with command dispatch. Messages with prefix trigger agent."""

    def __init__(self, engine, token: str = "", channel_ids: str = ""):
        self._engine = engine
        self._token = token
        self._channel_ids = {int(c.strip()) for c in channel_ids.split(",") if c.strip()} if channel_ids else set()
        self._client = None
        self._prefix = "!"

    async def start(self):
        if not HAS_DC:
            raise RuntimeError("pip install discord.py")
        if not self._token:
            raise RuntimeError("Discord token not configured")

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
            if not message.content.startswith(self._prefix):
                return

            text = message.content[len(self._prefix):].strip()
            if not text:
                return

            # Command dispatch
            if text.startswith("restart") or text.startswith("clear"):
                await self._engine.restart_session()
                await message.reply("Session restarted (DB + memory cleared).")
                return
            if text.startswith("stop"):
                self._engine.abort()
                await message.reply("Stopped.")
                return

            async with message.channel.typing():
                async def on_event(event):
                    text = format_event(event, platform="discord")
                    if text:
                        for i in range(0, len(text), 1900):
                            await message.channel.send(text[i:i+1900])

                result = await self._engine.run(text, on_event=on_event)
                if result and result not in ("[Interrupted]", "Max rounds reached."):
                    for i in range(0, len(result), 1900):
                        await message.reply(result[i:i+1900])

        await self._client.start(self._token)

    async def stop(self):
        if self._client:
            await self._client.close()
