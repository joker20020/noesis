"""Telegram Bot adapter — python-telegram-bot with streaming & media support."""
import asyncio
import os
import re
import time
from pathlib import Path

from adapters.formatters import format_event, should_skip_for_platform

try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
    from telegram.error import RetryAfter
    HAS_TG = True
except ImportError:
    HAS_TG = False

TEMP_DIR = Path("./workspace/telegram_media")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

_MAX_MSG_LEN = 4096
_STREAM_INTERVAL = 2.0
_STREAM_MIN_CHARS = 80


class _StreamSession:
    """Manages one or more live-edited Telegram messages for a single turn."""

    def __init__(self, bot, chat_id):
        self.bot = bot
        self.chat_id = chat_id
        self.msgs = []
        self.raw = ""
        self._last_update = 0.0
        self._last_raw_len = 0
        self._retry_until = 0.0
        self._lock = asyncio.Lock()

    def _now(self):
        return time.time()

    def _is_retrying(self):
        return self._now() < self._retry_until

    def _set_retry(self, exc: RetryAfter):
        ra = getattr(exc, "retry_after", 0) or 0
        if hasattr(ra, "total_seconds"):
            ra = ra.total_seconds()
        try:
            wait = max(0.0, float(ra)) + 1.0
        except (TypeError, ValueError):
            wait = 5.0
        self._retry_until = max(self._retry_until, self._now() + wait)

    def _should_update(self):
        if not self.msgs:
            return True
        elapsed = self._now() - self._last_update
        delta = len(self.raw) - self._last_raw_len
        return elapsed >= _STREAM_INTERVAL or delta >= _STREAM_MIN_CHARS

    async def _safe_edit(self, msg, text):
        while True:
            wait = self._retry_until - self._now()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await msg.edit_text(text)
            except RetryAfter as exc:
                self._set_retry(exc)
            except Exception as exc:
                s = str(exc).lower()
                if "not modified" in s or "exactly the same" in s:
                    return msg
                raise

    async def _safe_send(self, text):
        while True:
            wait = self._retry_until - self._now()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await self.bot.send_message(self.chat_id, text)
            except RetryAfter as exc:
                self._set_retry(exc)

    async def _sync(self):
        chunks = _split_text(self.raw, _MAX_MSG_LEN)
        for i, chunk in enumerate(chunks):
            if i < len(self.msgs):
                await self._safe_edit(self.msgs[i], chunk)
            else:
                msg = await self._safe_send(chunk)
                if msg:
                    self.msgs.append(msg)
        self._last_update = self._now()
        self._last_raw_len = len(self.raw)

    async def add_text(self, text):
        async with self._lock:
            self.raw += text
            if self._is_retrying() or not self._should_update():
                return
            await self._sync()

    async def finalize(self, text):
        async with self._lock:
            self.raw = text
            await self._sync()


def _split_text(text, limit):
    if len(text) <= limit:
        return [text]
    return [text[i:i + limit] for i in range(0, len(text), limit)]


class TelegramAdapter:
    def __init__(self, engine, token: str = "", allowed_users: str = ""):
        self._engine = engine
        self._token = token
        self._allowed = {int(u.strip()) for u in allowed_users.split(",") if u.strip()} if allowed_users else set()
        self._app = None

    async def start(self):
        if not HAS_TG:
            raise RuntimeError("pip install python-telegram-bot")
        if not self._token:
            raise RuntimeError("Telegram token not configured")

        self._app = ApplicationBuilder().token(self._token).build()

        async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            uid = update.effective_user.id if update.effective_user else 0
            if self._allowed and uid not in self._allowed:
                await update.message.reply_text("Access denied")
                return
            text = update.message.text or ""
            await self._handle_message(update, ctx, text, [])

        async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            uid = update.effective_user.id if update.effective_user else 0
            if self._allowed and uid not in self._allowed:
                await update.message.reply_text("Access denied")
                return
            photo = update.message.photo[-1] if update.message.photo else None
            if not photo:
                return
            file = await photo.get_file()
            fpath = TEMP_DIR / f"tg_{photo.file_unique_id}.jpg"
            await file.download_to_drive(fpath)
            caption = update.message.caption or ""
            await self._handle_message(update, ctx, caption, [str(fpath)])

        async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            uid = update.effective_user.id if update.effective_user else 0
            if self._allowed and uid not in self._allowed:
                await update.message.reply_text("Access denied")
                return
            doc = update.message.document
            if not doc:
                return
            file = await doc.get_file()
            ext = os.path.splitext(doc.file_name or "")[1] or ""
            fpath = TEMP_DIR / f"tg_{doc.file_unique_id}{ext}"
            await file.download_to_drive(fpath)
            caption = update.message.caption or ""
            await self._handle_message(update, ctx, caption, [str(fpath)])

        async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text("Noesis ready. Commands: /new /stop /restart /help")

        async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text(
                "Commands:\n/new — reset session\n/stop — abort current task\n/restart — restart session\n/help — show this"
            )

        async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            await self._engine.restart_session()
            await update.message.reply_text("Session reset.")

        async def cmd_stop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            self._engine.abort()
            await update.message.reply_text("Stopping...")

        async def cmd_restart(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            await self._engine.restart_session()
            await update.message.reply_text("Session restarted.")

        self._app.add_handler(CommandHandler("start", cmd_start))
        self._app.add_handler(CommandHandler("help", cmd_help))
        self._app.add_handler(CommandHandler("new", cmd_new))
        self._app.add_handler(CommandHandler("stop", cmd_stop))
        self._app.add_handler(CommandHandler("restart", cmd_restart))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        self._app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        self._app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

        print(f"[Telegram] Started (allowed: {len(self._allowed)} users)")
        await self._app.run_polling()

    async def stop(self):
        if self._app:
            await self._app.stop()
            await self._app.shutdown()

    async def _handle_message(self, update, ctx, text: str, media_paths: list[str]):
        chat_id = update.effective_chat.id

        parts = []
        if text.strip():
            parts.append(text.strip())
        for p in media_paths:
            parts.append(f"[File: source: {p}]")
        prompt = "\n".join(parts).strip()
        if not prompt:
            return

        await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

        session = _StreamSession(ctx.bot, chat_id)

        async def on_event(event):
            if should_skip_for_platform(event, "telegram"):
                return
            txt = format_event(event, "telegram")
            if not txt:
                return
            await session.add_text(txt + "\n")

        try:
            result = await self._engine.run(prompt, on_event=on_event)
            await session.finalize(result or "Done")
            for m in re.finditer(r'\[FILE:([^\]]+)\]', result or ""):
                path = m.group(1)
                if path in media_paths or not Path(path).exists():
                    continue
                await self._send_file(ctx.bot, chat_id, path)
        except Exception as e:
            print(f"[TelegramAdapter] engine.run failed: {e}")
            await ctx.bot.send_message(chat_id=chat_id, text=f"Error: {e}")

    async def _send_file(self, bot, chat_id, file_path):
        path = Path(file_path)
        if not path.exists():
            return
        ext = path.suffix.lower()
        try:
            if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
                with open(file_path, "rb") as f:
                    await bot.send_photo(chat_id, photo=f)
            else:
                with open(file_path, "rb") as f:
                    await bot.send_document(chat_id, document=f)
        except Exception as e:
            print(f"[Telegram] send_file failed: {e}")
