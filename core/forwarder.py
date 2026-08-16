#!/usr/bin/env python3
"""
信息转发接口 — 把机器人收到的/发出的消息转发到任意目的地（不止 DeepSeek AI）。

默认只把消息送给 AI；本模块提供一个可扩展的「转发接口」，让每条消息(收发)
都能被推送到 Webhook、本地钩子脚本等任意下游，失败不影响主流程。

配置(.env):
  FORWARD_ENABLED   是否启用转发，默认 true
  FORWARD_URLS      逗号分隔的 Webhook URL，POST JSON，默认空
  FORWARD_REPLIES   是否也转发机器人自己的回复，默认 true
  FORWARD_TIMEOUT   单个 Webhook 超时秒数，默认 5

本地钩子:
  把任意 .py 放入 core/hooks/，实现 def handle(event) 或 async def handle(event)，
  即可在每条消息时被调用。event 字段见 EVENT_FIELDS。

用法(在 qqbot/bot.py / agent/real.py 中):
  from core.forwarder import emit
  await emit(event)
"""
import asyncio
import importlib.util
import os
from datetime import datetime
from pathlib import Path

try:
    import aiohttp
except ImportError:  # 纯转发（AI_ENABLED=false）也可不用 AI，但建议仍安装 aiohttp
    aiohttp = None

HOOKS_DIR = Path(__file__).resolve().parent / "hooks"
_session = None
_hooks = None  # [(name, handle)] 惰性加载


# event 字段说明（所有下游统一收到该结构）
EVENT_FIELDS = {
    "source": "来源模式: official / real",
    "mode": "同 source（兼容旧字段）",
    "type": "消息类型: private / group / broadcast",
    "direction": "方向: in(收到) / out(机器人发出)",
    "uid": "对端用户标识(peer_uid)",
    "from": "发送者标识",
    "from_name": "显示名",
    "text": "消息正文",
    "time": "HH:MM:SS",
    "date": "YYYY-MM-DD",
    "ts": "完整时间戳 ISO8601",
}


def _b(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _i(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def config() -> dict:
    urls = [u.strip() for u in os.getenv("FORWARD_URLS", "").split(",") if u.strip()]
    return {
        "enabled": _b("FORWARD_ENABLED", True),
        "urls": urls,
        "forward_replies": _b("FORWARD_REPLIES", True),
        "timeout": _i("FORWARD_TIMEOUT", 5),
    }


def load_hooks() -> list:
    """加载 core/hooks/ 下所有 forward 钩子模块（缓存，按文件路径加载，不污染 sys.path）"""
    global _hooks
    if _hooks is not None:
        return _hooks
    hooks = []
    if HOOKS_DIR.exists():
        for f in sorted(HOOKS_DIR.glob("*.py")):
            if f.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"forward_hook_{f.stem}", f)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                fn = getattr(mod, "handle", None)
                if callable(fn):
                    hooks.append((f.stem, fn))
            except Exception as e:
                print(f"[forward] 加载钩子失败 {f.name}: {e}")
    _hooks = hooks
    return hooks


async def _post(url: str, event: dict, timeout: int) -> None:
    if aiohttp is None:
        return
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(force_close=True))
    try:
        async with _session.post(
            url, json=event, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status >= 400:
                print(f"[forward] webhook {url} -> HTTP {resp.status}")
    except Exception as e:
        print(f"[forward] webhook {url} 失败: {e}")


async def emit(event: dict) -> None:
    """转发一条消息事件到所有目的地(webhook + 本地钩子)。任何失败只打印，不影响主流程。"""
    if not _b("FORWARD_ENABLED", True):
        return
    cfg = config()
    event.setdefault("ts", datetime.now().isoformat(timespec="seconds"))
    event.setdefault("time", datetime.now().strftime("%H:%M:%S"))
    event.setdefault("date", datetime.now().strftime("%Y-%m-%d"))

    for url in cfg["urls"]:
        try:
            await _post(url, event, cfg["timeout"])
        except Exception as e:
            print(f"[forward] webhook {url} 异常: {e}")

    for name, fn in load_hooks():
        try:
            r = fn(event)
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:
            print(f"[forward] 钩子 {name} 异常: {e}")


async def close() -> None:
    """释放 aiohttp 会话（进程退出前调用）"""
    global _session
    if _session is not None and not _session.closed:
        try:
            await _session.close()
        except Exception:
            pass
    _session = None
