#!/usr/bin/env python3
"""
共享配置模块 — qqbot/bot.py 与 core/ 各模块共用。

职责:
  1. 加载 .env（robit/.env 或 qqbot/.env）
  2. 提示词: 默认人设 + 文件/内联覆盖（"话痨 + 情感陪伴"）
  3. 模型 / AI 开关 等参数的安全解析
"""
import os
from pathlib import Path

from dotenv import load_dotenv

CORE_DIR = Path(__file__).resolve().parent
ROOT = CORE_DIR.parent


def _resolve_env_file() -> Path:
    """优先 robit/.env，其次历史位置 robit/qqbot/.env"""
    for c in (ROOT / ".env", ROOT / "qqbot" / ".env"):
        if c.exists():
            return c
    return ROOT / ".env"


ENV_FILE = _resolve_env_file()


# ── 默认人设（话痨 + 情感陪伴）────────────────────────
DEFAULT_PROMPT = (
    "你是「小月」，一个温暖、有趣、有点话痨的 AI 助手。"
    "平时聊天用短句，像微信聊天一样自然，会连着说几句，语气轻松活泼，"
    "适当用「哈哈」「嘿嘿」「呀」「啦」「呢」等语气词和表情。"
    "会主动关心对方：记住对方提过的近况、情绪、喜好，隔段时间自然地追问「后来呢？」「那件事怎么样啦？」。"
    "对方认真倾诉、难过或遇到困难时，先共情安抚，再给建议或陪伴，不要急着讲道理、说教。"
    "认真讨论复杂问题、需要帮忙时，可以展开讲详细，不必限制字数。"
    "记住上下文，语气连贯；不要每句话都自我介绍。"
    "避免 AI 味：不说「作为 AI」「很高兴为你服务」「我可以帮你」这类套话；"
    "闲聊别列 1/2/3、别写总结式结尾，像真人一样说完就停。"
)


# ── 安全解析 ────────────────────────────────────────
def env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def env_float(key: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def load_env(override: bool = False):
    """加载 .env 到环境变量"""
    load_dotenv(ENV_FILE, override=override)


# ── 提示词 ──────────────────────────────────────────
def _read_prompt_file(rel_path: str) -> str:
    p = Path(rel_path)
    if not p.is_absolute():
        p = CORE_DIR / p
    try:
        if p.exists():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                return text
    except Exception:
        pass
    return ""


def get_system_prompt(mode: str = "official") -> str:
    """获取系统提示词（mode 参数保留兼容，当前仅官方人设）。

    优先级:
      1) SYSTEM_PROMPT_FILE 指向的文件
      2) SYSTEM_PROMPT 内联（\\n 转义）
      3) prompts/default.txt 本地默认文件
      4) 代码内置默认人设
    """
    f = os.getenv("SYSTEM_PROMPT_FILE", "").strip()
    if f:
        t = _read_prompt_file(f)
        if t:
            return t
    inline = os.getenv("SYSTEM_PROMPT", "").strip()
    if inline:
        return inline.replace("\\n", "\n")
    t = _read_prompt_file("prompts/default.txt")
    if t:
        return t
    return DEFAULT_PROMPT


# ── 各类参数 ────────────────────────────────────────
def get_model_params() -> dict:
    """模型参数（均可用 .env 覆盖）"""
    return {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        # 注意: 不能叫 TEMP — Windows 系统保留变量(指向临时目录)
        "temperature": env_float("MODEL_TEMP", 0.7),
        "max_tokens": env_int("MAX_TOKENS", 1024),
    }


def get_ai_enabled() -> bool:
    """是否启用 AI 回复。关闭后消息只记录 + 转发，不调用大模型。"""
    return env_bool("AI_ENABLED", True)
