"""Feishu/Lark Bot adapter — lark-oapi SDK with media, card & file support."""
import asyncio
import json
import os
import re
import time
from pathlib import Path

from adapters.formatters import format_event

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import *
    HAS_LARK = True
except ImportError:
    HAS_LARK = False

TEMP_DIR = Path("./workspace/feishu_media")
TEMP_DIR.mkdir(parents=True, exist_ok=True)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".tif"}
_AUDIO_EXTS = {".opus", ".mp3", ".wav", ".m4a", ".aac"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
_FILE_TYPE_MAP = {
    ".opus": "opus", ".mp4": "mp4", ".pdf": "pdf", ".doc": "doc", ".docx": "doc",
    ".xls": "xls", ".xlsx": "xls", ".ppt": "ppt", ".pptx": "ppt",
}

_TAG_PATS = [r"<" + t + r">.*?</" + t + r">" for t in ("thinking", "summary", "tool_use", "file_content")]
_TRUNC_TAIL = 300


def _clean(text):
    for pat in _TAG_PATS:
        text = re.sub(pat, "", text or "", flags=re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _strip_files(text):
    return re.sub(r"\[FILE:[^\]]+\]", "", text or "").strip()


def _display_text(text):
    cleaned = _strip_files(_clean(text))
    if cleaned:
        return cleaned
    tail = (text or "").strip()[-_TRUNC_TAIL:]
    return "（无文本输出）" + (f"\n…{tail}" if tail else "")


def _extract_files(text):
    return re.findall(r"\[FILE:([^\]]+)\]", text or "")


def _parse_json(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


class FeishuAdapter:
    """GA pattern: lark-oapi with event subscription. Long-connection mode."""

    def __init__(self, engine, app_id: str = "", app_secret: str = ""):
        self._engine = engine
        self._app_id = app_id
        self._app_secret = app_secret
        self._ws_client = None
        self._client = None

    async def start(self):
        if not HAS_LARK:
            raise RuntimeError("pip install lark-oapi")
        if not self._app_id or not self._app_secret:
            raise RuntimeError("Feishu app_id and app_secret required")

        self._client = lark.Client.builder() \
            .app_id(self._app_id) \
            .app_secret(self._app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

        ws_client = lark.ws.Client(
            lark.ws.ClientConfig(
                app_id=self._app_id,
                app_secret=self._app_secret,
                event_handler=_FeishuHandler(self._engine, self._client),
            )
        )
        self._ws_client = ws_client
        print(f"[Feishu] WebSocket client starting...")
        await ws_client.start()

    async def stop(self):
        if self._ws_client:
            await self._ws_client.stop()


class _FeishuHandler(lark.ws.EventHandler):
    def __init__(self, engine, client):
        self._engine = engine
        self._client = client

    async def handle_p2_im_message_receive_v1(self, ctx, event):
        message = event.message
        msg_type = message.message_type
        chat_id = message.chat_id
        sender = event.sender
        open_id = sender.sender_id.open_id if sender and sender.sender_id else ""

        user_input, media_paths = self._build_user_message(message)
        if not user_input:
            reply = f"⚠️ 暂不支持处理此类飞书消息：{msg_type}"
            if chat_id:
                await self._send_text(ctx, chat_id, reply, receive_id_type="chat_id")
            else:
                await self._send_text(ctx, open_id, reply)
            return

        if user_input.startswith("/"):
            return await self._handle_command(ctx, open_id, user_input, chat_id)

        receive_id = chat_id or open_id
        rid_type = "chat_id" if chat_id else "open_id"

        card = _TaskCard(ctx, receive_id, rid_type)
        await card.start()

        msg_count = 0
        last_send_time = time.time()

        async def on_event(agent_event):
            nonlocal msg_count, last_send_time
            try:
                txt = format_event(agent_event, platform="feishu")
                if not txt:
                    return
                await card.update(txt)
                for i in range(0, len(txt), 5000):
                    piece = txt[i:i + 5000]
                    if msg_count > 0:
                        now = time.time()
                        if now - last_send_time < 0.5 * msg_count:
                            await asyncio.sleep(0.5 * msg_count - (now - last_send_time))
                    await self._send_text(ctx, receive_id, piece, receive_id_type=rid_type)
                    msg_count += 1
                    last_send_time = time.time()
            except Exception as e:
                print(f"[FeishuAdapter] on_event failed: {e}")

        try:
            result = await self._engine.run(user_input, on_event=on_event)
            await card.done(result or "已完成")
            for path in _extract_files(result or ""):
                if path in media_paths or not Path(path).exists():
                    continue
                await self._send_local_file(ctx, receive_id, path, receive_id_type=rid_type)
        except Exception as e:
            print(f"[FeishuAdapter] engine.run failed: {e}")
            await card.fail(str(e))
            await self._send_text(ctx, receive_id, f"Error: {e}", receive_id_type=rid_type)

    def _build_user_message(self, message):
        msg_type = message.message_type
        content_json = _parse_json(message.content)
        parts, media_paths = [], []

        if msg_type == "text":
            text = str(content_json.get("text", "") or "").strip()
            if text:
                parts.append(text)
        elif msg_type == "post":
            text, image_keys = self._extract_post_content(content_json)
            if text:
                parts.append(text)
            for image_key in image_keys:
                fp, fn = self._download_media("image", {"image_key": image_key}, message.message_id)
                if fp:
                    parts.append(f"[image: {fn}]\n[Image: source: {fp}]")
                    media_paths.append(fp)
                else:
                    parts.append("[image: download failed]")
        elif msg_type in ("image", "audio", "file", "media"):
            fp, fn = self._download_media(msg_type, content_json, message.message_id)
            if fp:
                parts.append(f"[{msg_type}: {fn}]\n[File: source: {fp}]")
                media_paths.append(fp)
            else:
                parts.append(f"[{msg_type}: download failed]")
        elif msg_type in ("share_chat", "share_user", "interactive", "share_calendar_event", "system", "merge_forward"):
            parts.append(self._extract_share_card_content(content_json, msg_type))
        else:
            parts.append(f"[{msg_type}]")

        return "\n".join(p for p in parts if p).strip(), media_paths

    async def _download_media(self, msg_type, content_json, message_id):
        try:
            if msg_type == "image":
                file_key = content_json.get("image_key")
                if not file_key or not message_id:
                    return None, None
                req = GetMessageResourceRequest.builder() \
                    .message_id(message_id).file_key(file_key).type("image").build()
                resp = await asyncio.to_thread(self._client.im.v1.message_resource.get, req)
                if not resp.success():
                    return None, None
                data = resp.file.read() if hasattr(resp.file, "read") else resp.file
                filename = f"{file_key[:16]}.jpg"
            elif msg_type in ("file", "media", "audio"):
                file_key = content_json.get("file_key")
                if not file_key or not message_id:
                    return None, None
                rtype = "file" if msg_type == "audio" else msg_type
                req = GetMessageResourceRequest.builder() \
                    .message_id(message_id).file_key(file_key).type(rtype).build()
                resp = await asyncio.to_thread(self._client.im.v1.message_resource.get, req)
                if not resp.success():
                    return None, None
                data = resp.file.read() if hasattr(resp.file, "read") else resp.file
                filename = file_key[:16]
                if msg_type == "audio" and not filename.endswith(".opus"):
                    filename += ".opus"
            else:
                return None, None

            if not data:
                return None, None
            file_path = TEMP_DIR / filename
            file_path.write_bytes(data)
            return str(file_path), filename
        except Exception as e:
            print(f"[Feishu] download media failed: {e}")
            return None, None

    def _extract_share_card_content(self, content_json, msg_type):
        parts = []
        if msg_type == "share_chat":
            parts.append(f"[shared chat: {content_json.get('chat_id', '')}]")
        elif msg_type == "share_user":
            parts.append(f"[shared user: {content_json.get('user_id', '')}]")
        elif msg_type == "interactive":
            parts.extend(self._extract_interactive_content(content_json))
        elif msg_type == "share_calendar_event":
            parts.append(f"[shared calendar event: {content_json.get('event_key', '')}]")
        elif msg_type == "system":
            parts.append("[system message]")
        elif msg_type == "merge_forward":
            parts.append("[merged forward messages]")
        return "\n".join(p for p in parts if p).strip() or f"[{msg_type}]"

    def _extract_interactive_content(self, content):
        parts = []
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                return [content] if content.strip() else []
        if not isinstance(content, dict):
            return parts
        title = content.get("title")
        if isinstance(title, dict):
            title_text = title.get("content", "") or title.get("text", "")
            if title_text:
                parts.append(f"title: {title_text}")
        elif isinstance(title, str) and title:
            parts.append(f"title: {title}")
        elements = content.get("elements", [])
        if isinstance(elements, list):
            for row in elements:
                if isinstance(row, dict):
                    parts.extend(self._extract_element_content(row))
                elif isinstance(row, list):
                    for el in row:
                        parts.extend(self._extract_element_content(el))
        card = content.get("card", {})
        if card:
            parts.extend(self._extract_interactive_content(card))
        header = content.get("header", {})
        if isinstance(header, dict):
            header_title = header.get("title", {})
            if isinstance(header_title, dict):
                header_text = header_title.get("content", "") or header_title.get("text", "")
                if header_text:
                    parts.append(f"title: {header_text}")
        return [p for p in parts if p]

    def _extract_element_content(self, element):
        parts = []
        if not isinstance(element, dict):
            return parts
        tag = element.get("tag", "")
        if tag in ("markdown", "lark_md"):
            content = element.get("content", "")
            if content:
                parts.append(content)
        elif tag == "div":
            text = element.get("text", {})
            if isinstance(text, dict):
                text_content = text.get("content", "") or text.get("text", "")
                if text_content:
                    parts.append(text_content)
            elif isinstance(text, str) and text:
                parts.append(text)
            for field in element.get("fields", []) or []:
                if isinstance(field, dict):
                    field_text = field.get("text", {})
                    if isinstance(field_text, dict):
                        content = field_text.get("content", "") or field_text.get("text", "")
                        if content:
                            parts.append(content)
        elif tag == "a":
            href = element.get("href", "")
            text = element.get("text", "")
            if href:
                parts.append(f"link: {href}")
            if text:
                parts.append(text)
        elif tag == "button":
            text = element.get("text", {})
            if isinstance(text, dict):
                content = text.get("content", "") or text.get("text", "")
                if content:
                    parts.append(content)
            url = element.get("url", "") or (element.get("multi_url", {}) or {}).get("url", "")
            if url:
                parts.append(f"link: {url}")
        elif tag == "img":
            alt = element.get("alt", {})
            if isinstance(alt, dict):
                parts.append(alt.get("content", "[image]") or "[image]")
            else:
                parts.append("[image]")
        for child in element.get("elements", []) or []:
            parts.extend(self._extract_element_content(child))
        for col in element.get("columns", []) or []:
            for child in (col.get("elements", []) if isinstance(col, dict) else []):
                parts.extend(self._extract_element_content(child))
        return parts

    def _extract_post_content(self, content_json):
        def _parse_block(block):
            if not isinstance(block, dict) or not isinstance(block.get("content"), list):
                return None, []
            texts, images = [], []
            if block.get("title"):
                texts.append(block["title"])
            for row in block["content"]:
                if not isinstance(row, list):
                    continue
                for el in row:
                    if not isinstance(el, dict):
                        continue
                    tag = el.get("tag")
                    if tag in ("text", "a"):
                        texts.append(el.get("text", ""))
                    elif tag == "at":
                        texts.append(f"@{el.get('user_name', 'user')}")
                    elif tag == "img" and el.get("image_key"):
                        images.append(el["image_key"])
            text = " ".join(t for t in texts if t).strip()
            return text or None, images

        root = content_json
        if isinstance(root, dict) and isinstance(root.get("post"), dict):
            root = root["post"]
        if not isinstance(root, dict):
            return "", []
        if "content" in root:
            text, imgs = _parse_block(root)
            if text or imgs:
                return text or "", imgs
        for key in ("zh_cn", "en_us", "ja_jp"):
            if key in root:
                text, imgs = _parse_block(root[key])
                if text or imgs:
                    return text or "", imgs
        for val in root.values():
            if isinstance(val, dict):
                text, imgs = _parse_block(val)
                if text or imgs:
                    return text or "", imgs
        return "", []

    async def _send_text(self, ctx, receive_id, text, receive_id_type="open_id"):
        try:
            req = CreateMessageRequest.builder() \
                .receive_id_type(receive_id_type) \
                .request_body(CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type("text")
                    .content(json.dumps({"text": text}, ensure_ascii=False))
                    .build()) \
                .build()
            resp = await ctx.do(req)
            if resp and not resp.success():
                print(f"[Feishu] send_text failed: {resp.code}, {resp.msg}")
        except Exception as e:
            print(f"[Feishu] send_text exception: {e}")

    async def _send_local_file(self, ctx, receive_id, file_path, receive_id_type="open_id"):
        path = Path(file_path)
        if not path.exists():
            await self._send_text(ctx, receive_id, f"⚠️ 文件不存在: {path.name}", receive_id_type)
            return False
        ext = path.suffix.lower()
        try:
            if ext in _IMAGE_EXTS:
                with open(file_path, "rb") as f:
                    req = CreateImageRequest.builder() \
                        .request_body(CreateImageRequestBody.builder()
                            .image_type("message").image(f).build()) \
                        .build()
                    resp = await asyncio.to_thread(self._client.im.v1.image.create, req)
                    if resp and resp.success() and resp.data:
                        img_key = resp.data.image_key
                        payload = json.dumps({"image_key": img_key}, ensure_ascii=False)
                        req2 = CreateMessageRequest.builder() \
                            .receive_id_type(receive_id_type) \
                            .request_body(CreateMessageRequestBody.builder()
                                .receive_id(receive_id).msg_type("image").content(payload).build()) \
                            .build()
                        await ctx.do(req2)
                        return True
            else:
                file_type = _FILE_TYPE_MAP.get(ext, "stream")
                with open(file_path, "rb") as f:
                    req = CreateFileRequest.builder() \
                        .request_body(CreateFileRequestBody.builder()
                            .file_type(file_type).file_name(path.name).file(f).build()) \
                        .build()
                    resp = await asyncio.to_thread(self._client.im.v1.file.create, req)
                    if resp and resp.success() and resp.data:
                        file_key = resp.data.file_key
                        msg_type = "media" if ext in _AUDIO_EXTS or ext in _VIDEO_EXTS else "file"
                        payload = json.dumps({"file_key": file_key}, ensure_ascii=False)
                        req2 = CreateMessageRequest.builder() \
                            .receive_id_type(receive_id_type) \
                            .request_body(CreateMessageRequestBody.builder()
                                .receive_id(receive_id).msg_type(msg_type).content(payload).build()) \
                            .build()
                        await ctx.do(req2)
                        return True
            await self._send_text(ctx, receive_id, f"⚠️ 文件发送失败: {path.name}", receive_id_type)
            return False
        except Exception as e:
            print(f"[Feishu] send_local_file failed: {e}")
            await self._send_text(ctx, receive_id, f"⚠️ 文件发送失败: {path.name}", receive_id_type)
            return False

    async def _handle_command(self, ctx, open_id, cmd, chat_id=None):
        rid = chat_id or open_id
        rid_type = "chat_id" if chat_id else "open_id"
        parts = cmd.strip().split()
        op = parts[0].lower() if parts else ""

        if op in ("/stop", "/abort"):
            self._engine.abort()
            await self._send_text(ctx, rid, "正在停止...", receive_id_type=rid_type)
        elif op in ("/restart", "/new", "/clear"):
            await self._engine.restart_session()
            await self._send_text(ctx, rid, "会话已重置", receive_id_type=rid_type)
        elif op == "/help":
            await self._send_text(ctx, rid,
                "命令列表:\n/stop — 停止当前任务\n/restart — 重启会话\n/help — 显示帮助",
                receive_id_type=rid_type)
        else:
            await self._send_text(ctx, rid, f"未知命令: {cmd}", receive_id_type=rid_type)


class _TaskCard:
    def __init__(self, ctx, receive_id, rid_type):
        self.ctx = ctx
        self.rid = receive_id
        self.rtype = rid_type
        self.msg_id = None
        self.status = "🤔 思考中..."
        self.content = ""
        self.page_no = 1
        self.note = None

    def _build(self):
        header = f"**{self.status}**"
        if self.page_no > 1:
            header += f"\n\n📄 工作卡片 {self.page_no}"
        els = [{"tag": "markdown", "content": header}]
        if self.note:
            els.append({"tag": "markdown", "content": self.note})
        els.append({"tag": "markdown", "content": self.content[:8000] or "..."})
        return json.dumps({
            "schema": "2.0",
            "config": {"streaming_mode": False, "width_mode": "fill"},
            "body": {"elements": els},
        }, ensure_ascii=False)

    async def _patch(self):
        if not self.msg_id:
            req = CreateMessageRequest.builder() \
                .receive_id_type(self.rtype) \
                .request_body(CreateMessageRequestBody.builder()
                    .receive_id(self.rid)
                    .msg_type("interactive")
                    .content(self._build())
                    .build()) \
                .build()
            resp = await self.ctx.do(req)
            if resp and resp.success() and resp.data:
                self.msg_id = resp.data.message_id
            return True, False

        req = PatchMessageRequest.builder() \
            .message_id(self.msg_id) \
            .request_body(PatchMessageRequestBody.builder()
                .content(self._build())
                .build()) \
            .build()
        resp = await self.ctx.do(req)
        if resp and resp.success():
            return True, False
        msg = f"{getattr(resp, 'code', '')} {getattr(resp, 'msg', '')}".lower()
        limit = "230099" in msg or "11310" in msg or "element exceeds" in msg
        return False, limit

    async def _rollover(self):
        self.page_no += 1
        self.msg_id = None
        self.note = "⚠️ 上一张工作卡片达到飞书限制，本页继续展示后续进展。"

    async def start(self):
        await self._patch()

    async def update(self, text):
        self.content += text + "\n\n"
        ok, limit = await self._patch()
        if limit:
            await self._rollover()
            await self._patch()

    async def done(self, text):
        self.status = "✅ 已完成"
        self.content = (_display_text(text) or "已完成")[:6000]
        ok, limit = await self._patch()
        if limit:
            await self._rollover()
            self.content = (_display_text(text) or "已完成")[:6000]
            await self._patch()

    async def fail(self, msg):
        self.status = f"❌ {msg}"
        await self._patch()
