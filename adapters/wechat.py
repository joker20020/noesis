"""WeChat Bot adapter — GA-compatible iLink API with media support.

Reference: https://github.com/lsdefine/GenericAgent/blob/main/frontends/wechatapp.py
"""
import asyncio, base64, hashlib, json, random, re, struct, time, uuid
from pathlib import Path
from Crypto.Cipher import AES
import httpx
from adapters.formatters import merge_events

API = "https://ilinkai.weixin.qq.com"
CDN = "https://novac2c.cdn.weixin.qq.com/c2c"
TOKEN_FILE = Path("./workspace/wechat_token.json")
TEMP_DIR = Path("./workspace/wechat_media")
VER = "2.1.10"
MSG_USER, MSG_BOT = 1, 2
STATE_FINISH = 2
ITEM_TEXT, ITEM_IMAGE, ITEM_FILE, ITEM_VIDEO = 1, 2, 4, 5


# ── Adapter ──
class WeChatAdapter:
    def __init__(self, engine):
        self._engine = engine
        self._token = ""
        self._bot_id = ""
        self._buf = ""
        self._seen = set()
        self._session = None
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

    async def start(self):
        try:
            self._session = httpx.AsyncClient(timeout=httpx.Timeout(65, connect=10))
            await self._load_token()
            if not self._token:
                await self._qr_login()
            print(f"[WeChat] Bot connected: {self._bot_id}")
        except Exception as e:
            print(f"[WeChat] Startup failed: {e}")
            return

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
            self._token = d.get("bot_token", "")
            self._bot_id = d.get("ilink_bot_id", "")
            self._buf = d.get("updates_buf", "")

    def _save_token(self):
        TOKEN_FILE.write_text(json.dumps(dict(
            bot_token=self._token, ilink_bot_id=self._bot_id,
            updates_buf=self._buf, login_time=time.time())))

    # ── auth ──
    def _uin(self):
        return base64.b64encode(struct.pack(">I", random.randint(1, 2**31 - 1))).decode()

    def _hdrs(self):
        return {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": self._uin(),
            "iLink-App-Id": "bot",
            "iLink-App-ClientVersion": VER,
            "Authorization": f"Bearer {self._token}",
        }

    async def _post(self, ep, body, timeout=30):
        r = await self._session.post(f"{API}/{ep}", headers=self._hdrs(), json=body, timeout=timeout)
        if r.status_code != 200:
            print(f"[WeChat] HTTP {r.status_code} {ep}: {r.text[:200]}")
            return {}
        return r.json()

    async def _qr_login(self):
        r = (await self._session.get(f"{API}/ilink/bot/get_bot_qrcode?bot_type=3")).json()
        qr_id = r["qrcode"]
        print(f"[WeChat] QR: {r.get('qrcode_img_content', '')}")
        while True:
            await asyncio.sleep(2)
            s = (await self._session.get(f"{API}/ilink/bot/get_qrcode_status?qrcode={qr_id}")).json()
            st = s.get("status", "")
            if st == "confirmed":
                self._token = s["bot_token"]; self._bot_id = s.get("ilink_bot_id", ""); self._save_token()
                print(f"[WeChat] Logged in: {self._bot_id}"); return
            if st == "expired": raise RuntimeError("QR expired")

    # ── polling ──
    async def _get_updates(self):
        body = {"get_updates_buf": self._buf, "base_info": {"channel_version": VER}}
        try:
            d = await self._post("ilink/bot/getupdates", body, timeout=35)
        except Exception:
            return []
        if d.get("errcode") == -14:
            self._buf = ""; self._save_token()
        else:
            nb = d.get("get_updates_buf", "")
            if nb and nb != self._buf:
                self._buf = nb; self._save_token()
        return d.get("msgs", [])

    # ── send text ──
    async def _send_text(self, to_user, text, ctx=""):
        body = {
            "msg": {
                "from_user_id": "", "to_user_id": to_user,
                "client_id": f"py-{uuid.uuid4().hex[:8]}",
                "message_type": MSG_BOT, "message_state": STATE_FINISH,
                "context_token": ctx,
                "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
            },
            "base_info": {"channel_version": VER},
        }
        return await self._post("ilink/bot/sendmessage", body)

    # ── media helpers ──
    @staticmethod
    def _pkcs7_pad(data, block_size=16):
        n = block_size - len(data) % block_size
        return data + bytes([n] * n)

    @staticmethod
    def _pkcs7_unpad(data):
        return data[:-data[-1]]

    def _enc(self, raw, aes_key):
        return AES.new(aes_key, AES.MODE_ECB).encrypt(self._pkcs7_pad(raw))

    def _dec(self, raw, aes_key):
        return self._pkcs7_unpad(AES.new(aes_key, AES.MODE_ECB).decrypt(raw))

    async def _upload_media(self, filekey, upload_param, raw, aes_key):
        url = f"{CDN}/upload?encrypted_query_param={upload_param.get('encrypt_query_param','')}&filekey={filekey}"
        for attempt in range(3):
            try:
                r = await self._session.post(url, content=self._enc(raw, aes_key),
                    headers={"Content-Type": "application/octet-stream"}, timeout=120)
                if r.status_code >= 500:
                    await asyncio.sleep(2 ** attempt); continue
                eq = r.headers.get("x-encrypted-param", "")
                return {"encrypt_query_param": eq, "aes_key": base64.b64encode(aes_key.hex().encode()).decode(), "encrypt_type": 1}
            except Exception:
                if attempt == 2: raise
                await asyncio.sleep(2 ** attempt)

    async def _send_media(self, to_user, file_path, media_type, item_type, item_key, ctx=""):
        raw = Path(file_path).read_bytes()
        filekey = uuid.uuid4().hex
        aes_key = random.randbytes(16)
        ciphertext_size = ((len(raw) // 16) + 1) * 16
        thumb_raw, thumb_w, thumb_h, thumb_ct_size = b"", 0, 0, 0

        # Thumbnail for images
        if item_key == "image_item":
            try:
                from PIL import Image
                img = Image.open(file_path)
                img.thumbnail((240, 240))
                buf = __import__('io').BytesIO()
                img.save(buf, format="JPEG")
                thumb_raw = buf.getvalue()
                thumb_w, thumb_h = img.size
                thumb_ct_size = ((len(thumb_raw) // 16) + 1) * 16
            except Exception:
                pass

        upload_body = {
            "filekey": filekey, "media_type": media_type, "to_user_id": to_user,
            "rawsize": len(raw), "rawfilemd5": hashlib.md5(raw).hexdigest(),
            "filesize": ciphertext_size, "aeskey": aes_key.hex(),
        }
        if thumb_raw:
            upload_body.update({
                "thumb_rawsize": len(thumb_raw), "thumb_rawfilemd5": hashlib.md5(thumb_raw).hexdigest(),
                "thumb_filesize": thumb_ct_size, "no_need_thumb": False,
            })
        else:
            upload_body["no_need_thumb"] = True

        up = await self._post("ilink/bot/getuploadurl", upload_body)
        if not up:
            return False

        main = await self._upload_media(filekey, up, raw, aes_key)
        item = {"encrypt_query_param": main["encrypt_query_param"], "aes_key": main["aes_key"]}
        if item_key == "file_item":
            item["file_name"] = Path(file_path).name
        elif item_key == "image_item":
            item["mid_size"] = len(raw)
            if thumb_raw and up.get("thumb_upload_param"):
                thumb_up = await self._upload_media(f"{filekey}_thumb", up.get("thumb_upload_param", up), thumb_raw, aes_key)
                item["thumb_media"] = {"encrypt_query_param": thumb_up["encrypt_query_param"], "aes_key": thumb_up["aes_key"]}
            else:
                item["thumb_media"] = dict(item)
            item["thumb_size"] = thumb_ct_size
            item["thumb_width"] = thumb_w; item["thumb_height"] = thumb_h
        elif item_key == "video_item":
            item["video_size"] = len(raw)

        body = {
            "msg": {
                "from_user_id": "", "to_user_id": to_user,
                "client_id": f"py-{uuid.uuid4().hex[:8]}",
                "message_type": MSG_BOT, "message_state": STATE_FINISH,
                "context_token": ctx,
                "item_list": [{"type": item_type, item_key: item}],
            },
            "base_info": {"channel_version": VER},
        }
        return await self._post("ilink/bot/sendmessage", body)

    async def send_image(self, to_user, path, ctx=""):
        return await self._send_media(to_user, path, 1, ITEM_IMAGE, "image_item", ctx)
    async def send_file(self, to_user, path, ctx=""):
        return await self._send_media(to_user, path, 3, ITEM_FILE, "file_item", ctx)
    async def send_video(self, to_user, path, ctx=""):
        return await self._send_media(to_user, path, 2, ITEM_VIDEO, "video_item", ctx)

    # ── message handling ──
    @staticmethod
    def extract_text(msg):
        return "".join(it.get("text_item", {}).get("text", "")
                       for it in msg.get("item_list", []) if it.get("type") == ITEM_TEXT)

    @staticmethod
    def is_user_msg(msg):
        return msg.get("message_type") == MSG_USER

    async def _dl_media(self, msg):
        files = []
        for it in msg.get("item_list", []):
            ext = ""
            d = None
            if "image_item" in it: d = it["image_item"]; ext = ".jpg"
            elif "video_item" in it: d = it["video_item"]; ext = ".mp4"
            elif "file_item" in it: d = it["file_item"]; ext = ""
            elif "voice_item" in it: d = it["voice_item"]; ext = ".silk"
            if not d: continue
            eq = d.get("encrypt_query_param", "")
            ak_b64 = d.get("aes_key", "")
            try: ak = bytes.fromhex(base64.b64decode(ak_b64).decode()) if ak_b64 else None
            except Exception: ak = None
            if not ak or not eq: continue
            url = f"{CDN}/download?encrypted_query_param={eq}"
            raw = (await self._session.get(url, headers=self._hdrs())).content
            dec = self._dec(raw, ak)
            name = d.get("file_name") or f"{uuid.uuid4().hex[:8]}{ext}"
            path = TEMP_DIR / name
            path.write_bytes(dec)
            files.append(str(path))
        return files

    async def _on_message(self, msg):
        if not self.is_user_msg(msg): return
        mid = msg.get("message_id", "")
        if mid in self._seen: return
        self._seen.add(mid)
        if len(self._seen) > 2000: self._seen = set(list(self._seen)[-1000:])

        text = self.extract_text(msg)
        media_paths = await self._dl_media(msg)
        if media_paths:
            text += "\n" + "\n".join(f"[FILE:{p}]" for p in media_paths)

        uid = msg.get("from_user_id", "")
        ctx = msg.get("context_token", "")
        if not text.strip(): return

        print(f"[WeChat] {uid[:15]}...: {text[:50]}")

        # Commands
        if text.startswith("/stop") or text.startswith("/abort"):
            self._engine.abort()
            await self._send_text(uid, "已停止", ctx); return
        if text.startswith("/restart") or text.startswith("/clear"):
            await self._engine.restart_session()
            await self._send_text(uid, "会话已重置", ctx); return

        # Run agent with intermediate events
        event_buffer: list[dict] = []

        async def on_event(event):
            event_buffer.append(event)

        result = await self._engine.run(text, on_event=on_event)
        print(f"[WeChat] Reply {len(result)} chars, {len(event_buffer)} intermediate events")

        # Send merged intermediate events
        merged = merge_events(event_buffer, platform="wechat")
        sent = 0
        for chunk in merged:
            if sent >= 5:
                break
            for i in range(0, len(chunk), 2000):
                if sent >= 5:
                    break
                piece = chunk[i:i + 2000]
                d = await self._send_text(uid, piece, ctx if sent == 0 else "")
                if d.get("ret", 0) == 0:
                    sent += 1
                await asyncio.sleep(1)

        # Send final result
        for i in range(0, len(result), 2000):
            chunk = result[i:i + 2000]
            if sent >= 9:
                break
            d = await self._send_text(uid, chunk, ctx if i == 0 else "")
            if d.get("ret", 0) == 0:
                sent += 1
            await asyncio.sleep(1)

        # Send files if referenced
        for m in re.finditer(r'\[FILE:([^\]]+)\]', result):
            path = m.group(1)
            if path in media_paths or not Path(path).exists(): continue
            ext = Path(path).suffix.lower()
            if ext in ('.mp4', '.mov'): await self.send_video(uid, path, ctx)
            elif ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'): await self.send_image(uid, path, ctx)
            elif ext: await self.send_file(uid, path, ctx)
