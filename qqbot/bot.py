#!/usr/bin/env python3
"""
QQ 机器人 — 官方 API v2 + DeepSeek
聊天记录按用户分文件: chat_logs/{uid}.json（存储逻辑见 core/store.py）
"""
import asyncio
import json
import os
import sys
from pathlib import Path

import aiohttp
import botpy
from botpy.message import GroupMessage, C2CMessage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import config as cfg  # noqa: E402
from core import harness  # noqa: E402
from core import modes  # noqa: E402
from core.store import LOG_DIR, add_log, read_user, safe_uid  # noqa: E402
from core.forwarder import emit  # noqa: E402

LOG_DIR.mkdir(parents=True, exist_ok=True)

cfg.load_env()

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
BOT_APPID = os.getenv("BOT_APPID")
BOT_SECRET = os.getenv("BOT_SECRET")
BOT_QQ = os.getenv("BOT_QQ_ID", "未知")
PROXY = os.getenv("HTTPS_PROXY", os.getenv("HTTP_PROXY", "http://127.0.0.1:7897"))
SYSTEM_PROMPT = cfg.get_system_prompt("official")
MODEL_PARAMS = cfg.get_model_params()
AI_ENABLED = cfg.get_ai_enabled()
AI_ERR_FRIENDLY = "哎呀，我这边有点卡住了，没接住你的话，你再说一次嘛～"

sessions: dict = {}  # uid -> [messages] 内存会话（含 system prompt）


async def ask_deepseek(uid: str, msg: str):
    """异步调用 DeepSeek，代理失败自动直连；返回文本或 None（AI 关闭时）"""
    if not AI_ENABLED:
        return None
    s = sessions.setdefault(uid, [])
    if not s:
        s.append({"role": "system", "content": SYSTEM_PROMPT})
        # 新会话：从聊天记录恢复最近两条消息（重启后也能接上话）
        try:
            for m in read_user(safe_uid(uid))[-2:]:
                role = "user" if m.get("direction") == "in" else "assistant"
                content = str(m.get("text", "")).strip()
                if content:
                    s.append({"role": role, "content": content[:500]})
        except Exception:
            pass
    s.append({"role": "user", "content": msg})
    if len(s) > 22:
        s[:] = [s[0]] + s[-20:]

    body = {"model": MODEL_PARAMS["model"], "messages": s,
            "temperature": MODEL_PARAMS["temperature"], "max_tokens": MODEL_PARAMS["max_tokens"]}
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=60)

    for attempt, use_px in enumerate([True, False]):
        session = None
        try:
            kwargs = {"json": body, "headers": headers, "timeout": timeout}
            if use_px and PROXY:
                kwargs["proxy"] = PROXY
            session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(force_close=True))
            async with session.post(DEEPSEEK_URL, **kwargs) as resp:
                text = await resp.text()
                if resp.status == 200:
                    data = json.loads(text)
                    reply = data["choices"][0]["message"]["content"]
                    s.append({"role": "assistant", "content": reply})
                    print(f"[DeepSeek ✓] {reply[:60]}...")
                    return reply
                print(f"[DeepSeek {resp.status}] {text[:120]}")
                if attempt == 1:
                    return AI_ERR_FRIENDLY
        except Exception as e:
            print(f"[DeepSeek 异常] attempt={attempt} {e}")
            if attempt == 1:
                return AI_ERR_FRIENDLY
        finally:
            if session is not None:
                await session.close()
    return AI_ERR_FRIENDLY


class DeepSeekBot(botpy.Client):
    # ── 基础发送（文本）──
    async def _reply_group(self, group_openid, content, msg_id, safe):
        try:
            # msg_id 用于被动消息回复（5 分钟内有效，避免频控）
            await self.api.post_group_message(group_openid=group_openid, content=content, msg_id=msg_id)
            add_log({"peer_uid": safe, "type": "group", "mode": "official",
                     "from": BOT_QQ, "from_name": "xiaoyue", "text": content, "direction": "out"})
            await emit({"source": "official", "mode": "official", "type": "group", "direction": "out",
                        "uid": safe, "from": BOT_QQ, "from_name": "xiaoyue", "text": content})
        except Exception as e:
            print(f"[群回失败] {e}")

    async def _reply_c2c(self, openid, content, msg_id, safe):
        try:
            await self.api.post_c2c_message(openid=openid, content=content, msg_id=msg_id)
            add_log({"peer_uid": safe, "type": "private", "mode": "official",
                     "from": BOT_QQ, "from_name": "xiaoyue", "text": content, "direction": "out"})
            await emit({"source": "official", "mode": "official", "type": "private", "direction": "out",
                        "uid": safe, "from": BOT_QQ, "from_name": "xiaoyue", "text": content})
        except Exception as e:
            print(f"[私回失败] {e}")

    # ── markdown 发送（富格式，失败回退文本）──
    async def _reply_group_markdown(self, group_openid, md_text, msg_id, safe):
        try:
            await self.api.post_group_message(group_openid=group_openid, msg_type=2,
                                              markdown={"content": md_text}, msg_id=msg_id)
            add_log({"peer_uid": safe, "type": "group", "mode": "official",
                     "from": BOT_QQ, "from_name": "xiaoyue", "text": md_text, "direction": "out"})
            await emit({"source": "official", "mode": "official", "type": "group", "direction": "out",
                        "uid": safe, "from": BOT_QQ, "from_name": "xiaoyue", "text": md_text})
        except Exception as e:
            print(f"[群回 markdown 失败，回退文本] {e}")
            await self._reply_group(group_openid, md_text, msg_id, safe)

    async def _reply_c2c_markdown(self, openid, md_text, msg_id, safe):
        try:
            await self.api.post_c2c_message(openid=openid, msg_type=2,
                                            markdown={"content": md_text}, msg_id=msg_id)
            add_log({"peer_uid": safe, "type": "private", "mode": "official",
                     "from": BOT_QQ, "from_name": "xiaoyue", "text": md_text, "direction": "out"})
            await emit({"source": "official", "mode": "official", "type": "private", "direction": "out",
                        "uid": safe, "from": BOT_QQ, "from_name": "xiaoyue", "text": md_text})
        except Exception as e:
            print(f"[私回 markdown 失败，回退文本] {e}")
            await self._reply_c2c(openid, md_text, msg_id, safe)

    # ── 模式菜单（markdown + 键盘按钮）──
    async def _reply_group_menu(self, group_openid, uid, msg_id, safe):
        md = modes.menu_text(uid)
        try:
            await self.api.post_group_message(group_openid=group_openid, msg_type=2,
                                              markdown={"content": md}, keyboard=modes.build_keyboard(), msg_id=msg_id)
            add_log({"peer_uid": safe, "type": "group", "mode": "official",
                     "from": BOT_QQ, "from_name": "xiaoyue", "text": md, "direction": "out"})
            await emit({"source": "official", "mode": "official", "type": "group", "direction": "out",
                        "uid": safe, "from": BOT_QQ, "from_name": "xiaoyue", "text": md})
        except Exception as e:
            print(f"[菜单 markdown 失败，回退文本] {e}")
            await self._reply_group(group_openid, md, msg_id, safe)

    async def _reply_c2c_menu(self, openid, uid, msg_id, safe):
        md = modes.menu_text(uid)
        try:
            await self.api.post_c2c_message(openid=openid, msg_type=2,
                                            markdown={"content": md}, keyboard=modes.build_keyboard(), msg_id=msg_id)
            add_log({"peer_uid": safe, "type": "private", "mode": "official",
                     "from": BOT_QQ, "from_name": "xiaoyue", "text": md, "direction": "out"})
            await emit({"source": "official", "mode": "official", "type": "private", "direction": "out",
                        "uid": safe, "from": BOT_QQ, "from_name": "xiaoyue", "text": md})
        except Exception as e:
            print(f"[菜单 markdown 失败，回退文本] {e}")
            await self._reply_c2c(openid, md, msg_id, safe)

    # ── 办公结果（Ark 卡片优先，回退 markdown）──
    async def _send_office_result(self, raw, kind, target, msg_id, safe):
        log_type = "group" if kind == "group" else "private"
        ark_tid = cfg.env_int("ARK_TEMPLATE_ID", 0)
        if ark_tid:
            desc = harness.format_result(raw)
            ark = {"template_id": ark_tid,
                   "kv": [{"key": "#TITLE#", "value": "办公任务完成"},
                          {"key": "#DESC#", "value": desc}]}
            try:
                if kind == "group":
                    await self.api.post_group_message(group_openid=target, msg_type=3, ark=ark, msg_id=msg_id)
                else:
                    await self.api.post_c2c_message(openid=target, msg_type=3, ark=ark, msg_id=msg_id)
                add_log({"peer_uid": safe, "type": log_type, "mode": "official",
                         "from": BOT_QQ, "from_name": "xiaoyue", "text": desc, "direction": "out"})
                await emit({"source": "official", "mode": "official", "type": log_type, "direction": "out",
                            "uid": safe, "from": BOT_QQ, "from_name": "xiaoyue", "text": desc})
                return
            except Exception as e:
                print(f"[{kind} ark 失败，回退 markdown] {e}")
        md = harness.office_reply_markdown(raw)
        if kind == "group":
            await self._reply_group_markdown(target, md, msg_id, safe)
        else:
            await self._reply_c2c_markdown(target, md, msg_id, safe)

    # ── 发图（官方：URL 上传直接发送）──
    async def _reply_image(self, target, image_url, is_group, safe):
        try:
            if is_group:
                await self.api.post_group_file(group_openid=target, file_type=1, url=image_url, srv_send_msg=True)
            else:
                await self.api.post_c2c_file(openid=target, file_type=1, url=image_url, srv_send_msg=True)
            log_type = "group" if is_group else "private"
            add_log({"peer_uid": safe, "type": log_type, "mode": "official",
                     "from": BOT_QQ, "from_name": "xiaoyue", "text": "[图片]", "direction": "out"})
            await emit({"source": "official", "mode": "official", "type": "image", "direction": "out",
                        "uid": safe, "from": BOT_QQ, "from_name": "xiaoyue", "text": "",
                        "data": {"kind": "image", "url": image_url}})
        except Exception as e:
            print(f"[发图失败] {e}")
            msg = "图片没发出去，链接可能打不开，换一个试试？"
            if is_group:
                await self._reply_group(target, msg, None, safe)
            else:
                await self._reply_c2c(target, msg, None, safe)

    # ── 统一路由 ──
    async def _handle(self, uid, text, kind, target, msg_id, safe):
        async def send_text(t):
            if kind == "group":
                await self._reply_group(target, t, msg_id, safe)
            else:
                await self._reply_c2c(target, t, msg_id, safe)

        action, payload = modes.parse(text)
        cur = modes.state.get(uid)

        if action == "usage":
            await send_text(modes.usage_hint()); return
        if action == "switch_office":
            modes.state.set(uid, modes.MODE_OFFICE)
            await send_text("好的，已切换为 💼 办公模式，之后每条消息我都当任务去办～"); return
        if action == "switch_emotion":
            modes.state.set(uid, modes.MODE_EMOTION)
            await send_text("好呀，切回 💬 情感模式，继续陪你聊天～"); return
        if action == "menu":
            if kind == "group":
                await self._reply_group_menu(target, uid, msg_id, safe)
            else:
                await self._reply_c2c_menu(target, uid, msg_id, safe)
            return
        if action == "send_image":
            await self._reply_image(target, payload, kind == "group", safe)
            return

        task = payload if action == "office_task" else (text if cur == modes.MODE_OFFICE else None)
        if task is not None:
            await send_text(harness.OFFICE_ACK)
            try:
                raw = await asyncio.to_thread(harness.run_task_sync, task)
                await self._send_office_result(raw, kind, target, msg_id, safe)
            except Exception as e:
                await send_text(harness.OFFICE_FAIL + str(e))
            return

        reply = await ask_deepseek(uid, text)
        if reply is None:
            return
        print(f"[{'群' if kind == 'group' else '私'}回] {reply[:60]}...")
        await send_text(reply)

    # ── 事件 ──
    async def on_ready(self):
        print(f"\n  🤖 {self.robot.name}  已上线  |  日志: {LOG_DIR}")

    async def on_interaction_create(self, interaction):
        """键盘按钮回调：切换情感/办公模式，并回应交互避免客户端一直 loading"""
        try:
            resolved = interaction.data.resolved
            mode = (resolved.button_data or resolved.button_id or "").strip()
            uid = interaction.user_openid or interaction.group_member_openid or (resolved.user_id or "")
            try:
                await self.api.on_interaction_result(interaction.id, 0)
            except Exception as e:
                print(f"[interaction 回应失败] {e}")
            if mode in ("emotion", "office"):
                modes.state.set(uid, mode)
                reply = f"好的，已切换为 {modes.mode_label(mode)}～"
            else:
                reply = "收到～"
            safe = safe_uid(uid)
            if interaction.user_openid:
                await self._reply_c2c(interaction.user_openid, reply, None, safe)
            elif interaction.group_openid:
                await self._reply_group(interaction.group_openid, reply, None, safe)
        except Exception as e:
            print(f"[interaction 处理失败] {e}")

    async def on_group_at_message_create(self, msg: GroupMessage):
        uid = str(msg.author.member_openid) if msg.author else "?"
        text = msg.content.strip()
        if not text:
            return
        print(f"[群] {uid[:16]}...: {text}")
        safe = safe_uid(uid)
        add_log({"peer_uid": safe, "type": "group", "mode": "official",
                 "from": uid[:16], "from_name": "群成员", "text": text, "direction": "in"})
        await emit({"source": "official", "mode": "official", "type": "group", "direction": "in",
                    "uid": safe, "from": uid[:16], "from_name": "群成员", "text": text})
        await self._handle(uid, text, "group", msg.group_openid, msg.id, safe)

    async def on_c2c_message_create(self, msg: C2CMessage):
        uid = str(msg.author.user_openid) if msg.author else "?"
        text = msg.content.strip()
        if not text:
            return
        print(f"[私] {uid[:16]}...: {text}")
        safe = safe_uid(uid)
        add_log({"peer_uid": safe, "type": "private", "mode": "official",
                 "from": uid[:16], "from_name": "好友", "text": text, "direction": "in"})
        await emit({"source": "official", "mode": "official", "type": "private", "direction": "in",
                    "uid": safe, "from": uid[:16], "from_name": "好友", "text": text})
        await self._handle(uid, text, "c2c", uid, msg.id, safe)


if __name__ == "__main__":
    missing = [k for k, v in {"BOT_APPID": BOT_APPID, "BOT_SECRET": BOT_SECRET, "DEEPSEEK_API_KEY": DEEPSEEK_KEY}.items() if not v]
    if missing:
        print(f"\n  ❌ 配置缺失: {', '.join(missing)}")
        print(f"     请检查 qqbot/.env 文件（参考 .env.example）")
        raise SystemExit(1)
    print(f"\n  DeepSeek QQ Bot  |  AppID: {BOT_APPID}  模型: {MODEL_PARAMS['model']}"
          f"  AI: {'开' if AI_ENABLED else '关'}\n")
    intents = botpy.Intents(public_messages=True, direct_message=True, interaction=True)
    DeepSeekBot(intents=intents, is_sandbox=False).run(appid=BOT_APPID, secret=BOT_SECRET)
