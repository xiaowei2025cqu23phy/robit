#!/usr/bin/env python3
"""
聊天记录存储模块 — 官方/真人两种模式共用。

每个用户一个 JSON 文件: chat_logs/{safe_uid}.json
- 原子写入（临时文件 + os.replace），避免进程崩溃/并发导致 JSON 损坏
- 线程锁保护进程内并发；跨进程因 uid 天然不同（openid vs QQ 号），冲突概率极低
"""
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "chat_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

MAX_LOG = 300
_lock = threading.Lock()


def safe_uid(uid: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(uid))[:40]


def user_file(uid: str) -> Path:
    return LOG_DIR / f"{safe_uid(uid)}.json"


def read_user(uid: str) -> list:
    f = user_file(uid)
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_user(uid: str, msgs: list) -> None:
    """原子写：先写临时文件再 os.replace，避免中途崩溃留下半截 JSON"""
    f = user_file(uid)
    data = json.dumps(msgs[-MAX_LOG:], ensure_ascii=False, indent=2)
    tmp = f.with_suffix(f"{f.suffix}.tmp")
    try:
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, f)
    except Exception:
        try:
            tmp.unlink()
        except Exception:
            pass


def add_log(entry: dict) -> None:
    """线程安全地追加一条消息到对应用户文件。

    官方 botpy 回调在事件循环线程执行，真人号 WS 回调可能并发，
    故用进程内锁保护读改写。
    """
    entry["time"] = datetime.now().strftime("%H:%M:%S")
    entry["_date"] = datetime.now().strftime("%Y-%m-%d")
    uid = str(entry.get("peer_uid", entry.get("from", "?")))
    with _lock:
        msgs = read_user(uid)
        msgs.append(entry)
        save_user(uid, msgs)


def load_all_users() -> dict:
    """返回 {uid: [messages]}（读视图，供桌面/监控使用）"""
    result = {}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for f in sorted(LOG_DIR.glob("*.json")):
        try:
            msgs = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(msgs, list) and msgs:
                result[f.stem] = msgs
        except Exception:
            pass
    return result
