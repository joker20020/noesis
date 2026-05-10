# Platform Adapter Setup Guide (Agent Reference)

This guide helps you assist users in setting up chat platform adapters for Noesis.
All configuration is in `.env` file. Each platform is independently enabled/disabled.

## Quick Reference

| Platform | .env Key | Protocol | External Dependency |
|----------|---------|----------|-------------------|
| Web UI | `NOESIS_PLATFORM_WEB_ENABLED` | HTTP/WS on :8000 | None (built-in) |
| WeChat | `NOESIS_PLATFORM_WECHAT_ENABLED` | OpenClaw Gateway v3 | `@tencent-weixin/openclaw-weixin` plugin |
| QQ | `NOESIS_PLATFORM_QQ_ENABLED` | NapCatQQ OneBot v11 | NapCatQQ |
| Telegram | `NOESIS_PLATFORM_TELEGRAM_ENABLED` | Bot API (polling) | Bot token from @BotFather |
| Discord | `NOESIS_PLATFORM_DISCORD_ENABLED` | Gateway (prefix: !) | Bot token from Developer Portal |

---

## Web UI (always available)

No setup needed. Access at `http://localhost:8000` after starting Noesis.

---

## WeChat (OpenClaw Gateway Mode)

**How it works:** Noesis implements the OpenClaw Gateway WebSocket v3 protocol on ws://127.0.0.1:18789. The `@tencent-weixin/openclaw-weixin` plugin connects to it. All WeChat complexity is handled by the plugin.

**Setup steps for user:**
1. Install OpenClaw: `npm install -g openclaw`
2. Install WeChat plugin: `openclaw plugins install @tencent-weixin/openclaw-weixin`
3. Configure plugin to connect to: `ws://127.0.0.1:18789`
4. Scan QR code to login: `openclaw channels login --channel openclaw-weixin`
5. In `.env`: set `NOESIS_PLATFORM_WECHAT_ENABLED=true`
6. Start Noesis

**Troubleshooting:**
- Plugin can't connect → check Noesis is running and port 18789 is not blocked
- Messages not arriving → check WeChat ClawBot plugin is logged in
- iOS requires WeChat 8.0.70+, Android 8.0.69+

---

## QQ

**How it works:** Noesis starts a WebSocket server. NapCatQQ connects to it (reverse WebSocket mode) and forwards QQ messages via OneBot v11 protocol.

**Setup steps:**
1. Download NapCatQQ: https://github.com/NapNeko/NapCatQQ
2. Launch NapCatQQ, open WebUI at `http://127.0.0.1:6099`
3. In NapCat WebUI → Network → New → WebSocket Client:
   - URL: `ws://127.0.0.1:8080/onebot/v11/ws`
   - Message Format: Array
4. Login with QQ account (use a secondary account for safety)
5. In `.env`:
```bash
NOESIS_PLATFORM_QQ_ENABLED=true
NOESIS_PLATFORM_QQ_HOST=0.0.0.0
NOESIS_PLATFORM_QQ_PORT=8080
NOESIS_PLATFORM_QQ_NAPCAT_HTTP=http://127.0.0.1:3000
```
6. Start Noesis

**Troubleshooting:**
- NapCat crashes → try using the Docker version
- Can't login → QQ might require phone verification on first login
- No messages → check WebSocket URL exactly matches

---

## Telegram

**How it works:** Noesis uses python-telegram-bot to poll for messages. User sends message → bot replies.

**Setup steps:**
1. Create bot via @BotFather on Telegram, get token
2. Get your Telegram user ID (send /start to @userinfobot)
3. Install: `pip install python-telegram-bot`
4. In `.env`:
```bash
NOESIS_PLATFORM_TELEGRAM_ENABLED=true
NOESIS_PLATFORM_TELEGRAM_TOKEN=123456:ABC-DEF1234gh
NOESIS_PLATFORM_TELEGRAM_ALLOWED_USERS=123456789
```
5. Start Noesis

**Troubleshooting:**
- Bot not responding → check token is correct
- Access denied → check your user ID is in allowed_users

---

## Discord

**How it works:** Noesis connects via discord.py gateway. Messages starting with `!` trigger the agent.

**Setup steps:**
1. Go to https://discord.com/developers/applications
2. Create New Application → Bot → Copy Token
3. Enable "Message Content Intent" in Bot settings
4. Invite bot to server: OAuth2 → URL Generator → bot + Send Messages → copy URL
5. Enable Developer Mode in Discord → right-click channel → Copy ID
6. Install: `pip install discord.py`
7. In `.env`:
```bash
NOESIS_PLATFORM_DISCORD_ENABLED=true
NOESIS_PLATFORM_DISCORD_TOKEN=your_bot_token
NOESIS_PLATFORM_DISCORD_CHANNELS=123456789
```
8. Start Noesis

**Troubleshooting:**
- Bot offline → check token
- No response → messages must start with `!`
- Privileged intents error → enable "Message Content Intent" in Developer Portal

---

## How to Help Users

When a user asks "how do I connect Noesis to X platform":

1. **Identify** which platform they want
2. **Read** their current `.env` with file_read to check current settings
3. **Guide** them through the steps above using code_run to check installations
4. **Edit** their `.env` using file_patch to enable the platform
5. **Verify** by checking if Noesis logs show the adapter started correctly

Common .env editing pattern:
```bash
# Use file_patch to change enabled flag
old: NOESIS_PLATFORM_TELEGRAM_ENABLED=false
new: NOESIS_PLATFORM_TELEGRAM_ENABLED=true

# Add token if missing
old: NOESIS_PLATFORM_TELEGRAM_TOKEN=
new: NOESIS_PLATFORM_TELEGRAM_TOKEN=their_token_here
```
