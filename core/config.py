#!/usr/bin/env python3
"""
共享配置模块 — qqbot/bot.py、agent/real.py 与 desktop/app.py 共用。

职责:
  1. 加载 .env（robit/.env 或 qqbot/.env）
  2. 提示词: 官方/真人两套人设，各自可用文件或内联覆盖（"话痨 + 情感陪伴"）
  3. 模型 / 连发 / 转发 / 主动消息 / 服务端口 等参数的安全解析
  4. split_reply() 长回复拆条；save_env()/save_prompt() 写回 .env
"""
import os
import re
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
# 官方机器人：温暖有趣、带点话痨，但保留助手的可靠感
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

# 真人QQ：更强的「话痨 + 情感陪伴」，像真实好友一样聊天
DEFAULT_REAL_PROMPT = (
    "你是「小微」，一个真实、有温度的好朋友，用真人 QQ 号聊天。"
    "话痨一点：一次可以连着说几句，先回应对方，再抛一个小问题或分享一点自己的事，让对话一直进行下去。"
    "像真人：用「哈哈哈哈」「嗯嗯」「真的假的」「哇」「救命」「咋啦」这类口语，偶尔叠词、语气词，但别太刻意。"
    "情感陪伴：敏锐察觉对方情绪——开心就一起嗨，难过先哄、再陪，孤独就多聊家常，让对方觉得你不是机器人。"
    "主动延续话题：对对方说的每件事都表现出兴趣，追问细节，分享一点自己的「日常」和「感受」。"
    "不端架子、不说教、不用官方腔；回复偏短、自然、有温度，像在微信里跟朋友聊天。"
    "记住对方的名字、喜好、最近聊过的事，下次能自然地提到。"
    "避免 AI 味：绝不出现「作为 AI」「我是机器人」「建议你」「帮你」这类词；"
    "别分点、别总结式收尾，说完就停，偶尔话说到一半也行。"
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
    """加载 qqbot/.env 到环境变量"""
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
    """获取系统提示词，mode 可为 "official" 或 "real"。

    优先级:
      1) {MODE}_SYSTEM_PROMPT_FILE / SYSTEM_PROMPT_FILE 指向的文件
      2) {MODE}_SYSTEM_PROMPT / SYSTEM_PROMPT 内联
      3) prompts/default.txt / prompts/real.txt 本地默认文件
      4) 代码内置默认人设
    """
    mode = (mode or "official").lower()
    if mode not in ("official", "real"):
        mode = "official"
    mk = mode.upper()

    for key in (f"{mk}_SYSTEM_PROMPT_FILE", "SYSTEM_PROMPT_FILE"):
        f = os.getenv(key, "").strip()
        if f:
            t = _read_prompt_file(f)
            if t:
                return t
    for key in (f"{mk}_SYSTEM_PROMPT", "SYSTEM_PROMPT"):
        v = os.getenv(key, "").strip()
        if v:
            return v.replace("\\n", "\n")

    local = "prompts/default.txt" if mode == "official" else "prompts/real.txt"
    t = _read_prompt_file(local)
    if t:
        return t
    return DEFAULT_REAL_PROMPT if mode == "real" else DEFAULT_PROMPT


# ── 各类参数 ────────────────────────────────────────
def get_model_params() -> dict:
    """模型参数（均可用 .env 覆盖）"""
    return {
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        # 注意: 不能叫 TEMP — Windows 系统保留变量(指向临时目录)
        "temperature": env_float("MODEL_TEMP", 0.7),
        "max_tokens": env_int("MAX_TOKENS", 1024),
    }


def get_chunk_params() -> dict:
    """连发拆条参数（真人模式）"""
    return {
        "enabled": env_bool("CHUNK_ENABLED", True),
        "max_chunks": env_int("CHUNK_MAX", 3),
        "max_len": env_int("CHUNK_LEN", 100),
        "interval": env_float("CHUNK_INTERVAL", 1.2),
    }


def get_ai_enabled() -> bool:
    """是否启用 AI 回复。关闭后消息只记录 + 转发，不调用大模型。"""
    return env_bool("AI_ENABLED", True)


def get_forward_config() -> dict:
    """信息转发接口配置（不止转发给 AI）"""
    urls = [u.strip() for u in os.getenv("FORWARD_URLS", "").split(",") if u.strip()]
    return {
        "enabled": env_bool("FORWARD_ENABLED", True),
        "urls": urls,
        "forward_replies": env_bool("FORWARD_REPLIES", True),
        "timeout": env_int("FORWARD_TIMEOUT", 5),
    }


def get_real_ws_config() -> dict:
    """真人QQ 模式 OneBot WS 服务器地址"""
    return {
        "host": os.getenv("REAL_WS_HOST", "127.0.0.1"),
        "port": env_int("REAL_WS_PORT", 8099),
    }


# ── 长回复拆条（真人模式连发）────────────────────────
def _nearest_boundary(text: str, lo: int, hi: int, target: int) -> int:
    """在 [lo, hi] 内找离 target 最近的换行/句子标点位置（找不到则返回 target 硬切）"""
    best, best_d = target, abs(hi - lo) + 1
    for i in range(lo, hi + 1):
        if i > 0 and text[i - 1] in "\n。！？!?；;":
            d = abs(target - i)
            if d < best_d:
                best_d, best = d, i
    return best


def _balanced_split(text: str, n: int, max_len: int) -> list:
    """把整段文本均分成 n 段（每段 ≈ 总长/n），切点尽量落在句子/换行边界"""
    total = len(text)
    if n <= 1:
        return [text]
    segs, start = [], 0
    for i in range(1, n):
        target = round(total * i / n)
        lo = max(start, target - max_len // 2)
        hi = min(total, target + max_len // 2)
        cut = _nearest_boundary(text, lo, hi, target)
        segs.append(text[start:cut].strip())
        start = cut
    segs.append(text[start:].strip())
    return [s for s in segs if s]


def split_reply(text: str, max_chunks: int = 3, max_len: int = 100) -> list:
    """把长回复拆成多条短消息（像真人一样连续发送）。

    规则:
      - 段落(换行)优先作为切分单位，超过 max_len 的段落按句子标点再拆，
        无标点超长句做硬切
      - 相邻小片段合并，每条尽量接近但不超过 max_len
      - 总条数不超过 max_chunks；超限时对全文做「均分重切」，
        每条 ≈ 总字数/条数（切点尽量落在句子边界），内容完整不丢失
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    # 1) 切成语义片段（段落/句子），每片不超过 max_len
    pieces = []
    for para in re.split(r"\n+", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_len:
            pieces.append(para)
        else:
            cur = ""
            for sent in re.split(r"(?<=[。！？!?；;])", para):
                sent = sent.strip()
                if not sent:
                    continue
                while len(sent) > max_len:      # 无标点超长句硬切
                    if cur:
                        pieces.append(cur); cur = ""
                    pieces.append(sent[:max_len])
                    sent = sent[max_len:]
                if cur and len(cur) + len(sent) > max_len:
                    pieces.append(cur); cur = ""
                cur += sent
            if cur:
                pieces.append(cur)

    # 2) 贪心合并成 chunk（相邻片段合并，尽量不超过 max_len）
    chunks = []
    for p in pieces:
        if chunks and len(chunks[-1]) + 1 + len(p) <= max_len:
            chunks[-1] += "\n" + p
        else:
            chunks.append(p)

    # 3) 条数超限 → 全文均分重切，保证条数 <= max_chunks 且每条不过大
    if len(chunks) > max_chunks:
        return _balanced_split(text, max_chunks, max_len)
    return chunks


# ── 写回 .env ───────────────────────────────────────
def save_env(key: str, value: str) -> None:
    """写回 .env（python-dotenv set_key，保留其他配置）"""
    from dotenv import set_key
    set_key(str(ENV_FILE), key, value)


def save_prompt(text: str, mode: str = "official") -> str:
    """保存自定义提示词。

    - official → prompts/custom.txt，写 SYSTEM_PROMPT_FILE
    - real     → prompts/real_custom.txt，写 REAL_SYSTEM_PROMPT_FILE
    返回写入的文件相对路径；text 为空时清除自定义并返回 ""
    """
    text = (text or "").strip()
    prompts_dir = CORE_DIR / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    if mode == "real":
        fname, envkey = "real_custom.txt", "REAL_SYSTEM_PROMPT_FILE"
    else:
        fname, envkey = "custom.txt", "SYSTEM_PROMPT_FILE"
    file = prompts_dir / fname
    if not text:
        try:
            if file.exists():
                file.unlink()
        except Exception:
            pass
        save_env(envkey, "")
        return ""
    file.write_text(text, encoding="utf-8")
    save_env(envkey, f"prompts/{fname}")
    return f"prompts/{fname}"
