"""Telegram Bot adapter — async polling mode, python-telegram-bot."""
import asyncio
import json

try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
    HAS_TG = True
except ImportError:
    HAS_TG = False


class TelegramAdapter:
    def __init__(self, engine, token: str = "", allowed_users: set[int] | None = None):
        self._engine = engine
        self._token = token
        self._allowed = allowed_users or set()
        self._app = None

    async def start(self):
        if not HAS_TG:
            print("[Telegram] python-telegram-bot not installed: pip install python-telegram-bot")
            return
        if not self._token:
            print("[Telegram] Token not configured, skipping")
            return

        self._app = ApplicationBuilder().token(self._token).build()

        async def handle_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            uid = update.effective_user.id if update.effective_user else 0
            if self._allowed and uid not in self._allowed:
                await update.message.reply_text("Access denied")
                return
            text = update.message.text or ""
            if not text.strip():
                return
            await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            result = await self._engine.run(text, session_id=f"tg_{uid}")
            # Split long messages
            for i in range(0, len(result), 4000):
                await update.message.reply_text(result[i:i+4000])

        async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text("infoCap ready. Send a message to start.")

        self._app.add_handler(CommandHandler("start", cmd_start))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

        print(f"[Telegram] Bot started (allowed: {len(self._allowed)} users)")
        await self._app.run_polling()

    async def stop(self):
        if self._app:
            await self._app.stop()
