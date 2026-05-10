"""Telegram Bot adapter — python-telegram-bot, polling mode."""
import asyncio

try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
    HAS_TG = True
except ImportError:
    HAS_TG = False


class TelegramAdapter:
    """GA pattern: async polling with command dispatch. Config in platform config."""

    def __init__(self, engine, token: str = "", allowed_users: str = ""):
        self._engine = engine
        self._token = token
        self._allowed = {int(u.strip()) for u in allowed_users.split(",") if u.strip()} if allowed_users else set()
        self._app = None
        self._session_prefix = "tg"

    async def start(self):
        if not HAS_TG:
            raise RuntimeError("pip install python-telegram-bot")
        if not self._token:
            raise RuntimeError("Telegram token not configured")

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
            result = await self._engine.run(text, session_id=f"{self._session_prefix}_{uid}")
            for i in range(0, len(result), 4000):
                await update.message.reply_text(result[i:i+4000])

        async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text("infoCap ready. Commands: /new (reset), /stop (abort).")

        async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            self._engine.abort()
            await update.message.reply_text("Session reset.")

        async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            self._engine.abort()
            await update.message.reply_text("Stopped.")

        self._app.add_handler(CommandHandler("start", cmd_start))
        self._app.add_handler(CommandHandler("new", cmd_new))
        self._app.add_handler(CommandHandler("stop", cmd_stop))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

        print(f"[Telegram] Started (allowed: {len(self._allowed)} users)")
        await self._app.run_polling()

    async def stop(self):
        if self._app:
            await self._app.stop()
            await self._app.shutdown()
