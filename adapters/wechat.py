"""WeChat Bot adapter — GA-compatible iLink API with async agent.

GA reference: https://github.com/lsdefine/GenericAgent/blob/main/frontends/wechatapp.py
"""
import asyncio, json, random, time, uuid, struct, base64
from pathlib import Path

import httpx

API_BASE = "https://ilinkai.weixin.qq.com"
TOKEN_FILE = Path.home() / ".wxbot" / "token.json"
VER = "2.1.10"
MSG_USER, MSG_BOT = 1, 2
ITEM_TEXT, ITEM_IMAGE, ITEM_FILE, ITEM_VIDEO = 1, 2, 4, 5

# ── adapter ──
class WeChatAdapter:
    def __init__(self, engine):
        self._engine = engine
        self._token = None
        self._bot_id = None
        self._buf = ""
        self._seen = set()
        self._session = None

    async def start(self):
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._session = httpx.AsyncClient(timeout=httpx.Timeout(65, connect=10))

        await self._load_token()
        if not self._token:
            await self._qr_login()

        print(f"[WeChat] Bot connected: {self._bot_id}")
        while True:
            try:
                msgs = await self._get_updates()
                for msg in msgs:
                    await self._on_message(msg)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[WeChat] Error: {e}"); await asyncio.sleep(5)

    async def stop(self):
        try: await self._session.aclose()
        except Exception: pass

    # ── token ──
    async def _load_token(self):
        if TOKEN_FILE.exists():
            d = json.loads(TOKEN_FILE.read_text())
            self._token = d.get("bot_token","")
            self._bot_id = d.get("ilink_bot_id","")
            self._buf = d.get("updates_buf","")

    def _save_token(self):
        TOKEN_FILE.write_text(json.dumps(dict(
            bot_token=self._token, ilink_bot_id=self._bot_id,
            updates_buf=self._buf, login_time=time.time())))

    # ── auth ──
    async def _qr_login(self):
        r = await self._session.get(f"{API_BASE}/ilink/bot/get_bot_qrcode?bot_type=3")
        qr = r.json()["qrcode"]
        url = r.json().get("qrcode_img_content","")
        print(f"[WeChat] QR: {url}")
        while True:
            await asyncio.sleep(2)
            s = (await self._session.get(f"{API_BASE}/ilink/bot/get_qrcode_status?qrcode={qr}")).json()
            if s.get("status") == "confirmed":
                self._token = s["bot_token"]; self._bot_id = s.get("ilink_bot_id",""); self._save_token()
                print(f"[WeChat] Logged in: {self._bot_id}"); return
            if s.get("status") == "expired": raise RuntimeError("QR expired")

    # ── http ──
    def _hdrs(self):
        u = base64.b64encode(str(random.randint(1,2**31-1)).encode()).decode()
        return {"Content-Type":"application/json","iLink-App-Id":"bot",
                "iLink-App-ClientVersion":VER,"X-WECHAT-UIN":u,
                "AuthorizationType":"ilink_bot_token",
                "Authorization":f"Bearer {self._token}"}

    async def _post(self, ep, body):
        r = await self._session.post(f"{API_BASE}{ep}", headers=self._hdrs(), json=body)
        if r.status_code != 200:
            print(f"[WeChat] {ep} HTTP {r.status_code}: {r.text[:200]}")
            return {}
        return r.json()

    # ── polling ──
    async def _get_updates(self):
        body = {"get_updates_buf": self._buf, "base_info": {"channel_version": VER}}
        try:
            d = await self._post("/ilink/bot/getupdates", body)
        except Exception:
            return []
        if d.get("errcode") == -14:
            self._buf = ""; self._save_token()
        else:
            nb = d.get("get_updates_buf","")
            if nb and nb != self._buf:
                self._buf = nb; self._save_token()
        return d.get("msgs",[])

    # ── send ──
    async def _send_text(self, to_user, text, ctx=""):
        body = {
            "msg": {
                "to_user_id": to_user, "message_type": MSG_BOT,
                "message_state": 2, "context_token": ctx,
                "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
            },
            "base_info": {"channel_version": VER},
        }
        return await self._post("/ilink/bot/sendmessage", body)

    # ── message handling ──
    async def _on_message(self, msg):
        if msg.get("message_type") != MSG_USER: return
        mid = msg.get("message_id","")
        if mid in self._seen: return
        self._seen.add(mid)
        if len(self._seen) > 2000: self._seen = set(list(self._seen)[-1000:])

        text = "".join(it.get("text_item",{}).get("text","")
                       for it in msg.get("item_list",[]) if it.get("type")==ITEM_TEXT)
        if not text.strip(): return

        uid = msg.get("from_user_id","")
        ctx = msg.get("context_token","")
        print(f"[WeChat] {uid[:15]}...: {text[:50]}")

        # Run agent
        result = await self._engine.run(text)
        print(f"[WeChat] Reply {len(result)} chars")

        # Send reply (split long messages)
        for i in range(0, len(result), 2000):
            chunk = result[i:i+2000]
            d = await self._send_text(uid, chunk, ctx if i==0 else "")
            if d.get("ret", 0) != 0:
                print(f"[WeChat] Send err: {d}")
