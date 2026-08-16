#!/usr/bin/env python3
"""
办公模式 — 桥接 deepseek-harness（可选依赖，未安装时优雅降级）。

让机器人把「办公」消息当作任务交给 DeepSeek Harness 的 agent，在指定工作区(cwd)里执行，
并把最终结果整理成适合 QQ 的文案回传给用户。适合：手机发消息 → 电脑上的 agent 选工作区干活。

依赖（按需安装，较重，故不放进 requirements.txt）:
    pip install deepseek-harness-sdk

配置(.env):
  HARNESS_ENABLED     是否启用办公模式，默认 true
  OFFICE_PREFIX       办公模式触发前缀，默认 #办公
  HARNESS_CWD         工作区目录（agent 在此干活），默认项目根目录
  HARNESS_SESSION_ROOT 会话持久化目录（可选）
  HARNESS_MODEL       模型，默认 deepseek-chat
  HARNESS_MAX_TOKENS  每次最大输出，默认 0=用提供方默认
  HARNESS_TIMEOUT     单次任务超时秒数，默认 0=不限
  HARNESS_REPLY_MAX   回传结果最长字数（纯文本），默认 1000（超长截断）
  HARNESS_MARKDOWN_MAX 官方机器人 markdown 回传最长字数，默认 3000
"""
import os
import re
import threading
from pathlib import Path

from . import config as cfg

ROOT = Path(__file__).resolve().parent.parent

# 办公任务的三段文案：确认 / 成功 / 失败
OFFICE_ACK = "🤖 收到办公任务，正在工作区执行，完成后马上回复你～"
OFFICE_DONE = "✅ 办公任务完成啦：\n"
OFFICE_FAIL = "❌ 办公任务没跑成："

_runner = None
_runner_lock = threading.Lock()


def is_available() -> bool:
    """deepseek-harness-sdk 是否已安装"""
    try:
        import deepseek_harness  # noqa: F401
        return True
    except Exception:
        return False


def is_enabled() -> bool:
    return cfg.env_bool("HARNESS_ENABLED", True)


def format_result(text: str, max_len: int | None = None) -> str:
    """把 harness 原始输出整理成适合 QQ 的文案：去 markdown、收敛空白、超长截断。"""
    if max_len is None:
        max_len = cfg.env_int("HARNESS_REPLY_MAX", 1000) or 1000
    text = (text or "").strip()
    # 去掉 markdown 代码围栏 / 标题 / 加粗 / 行内代码
    text = re.sub(r"```[a-zA-Z0-9_+\- ]*\n?", "", text)
    text = text.replace("```", "")
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # 收敛空白
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) > max_len:
        text = text[:max_len] + "\n…（内容太长，已截断，完整结果见日志）"
    return text


def office_reply(raw: str) -> str:
    """成功时的回传文案（纯文本）：✅ 标题 + 整理后的结果"""
    return OFFICE_DONE + format_result(raw)


def format_result_markdown(text: str, max_len: int | None = None) -> str:
    """官方机器人的 markdown 版本：保留代码块/标题/列表等结构，只收敛空行 + 超长截断。"""
    if max_len is None:
        max_len = cfg.env_int("HARNESS_MARKDOWN_MAX", 3000) or 3000
    text = (text or "").strip()
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) > max_len:
        text = text[:max_len] + "\n\n> …（内容过长，已截断）"
    return text


def office_reply_markdown(raw: str) -> str:
    """官方机器人的成功回传（markdown 消息，保留富格式）"""
    return OFFICE_DONE + format_result_markdown(raw)


class _HarnessRunner:
    """持有单个可复用的 DeepSeekHarness 子进程，串行执行办公任务（run() 是阻塞的）。"""

    def __init__(self):
        self._harness = None
        self._lock = threading.Lock()

    def _get(self):
        if self._harness is None:
            from deepseek_harness import DeepSeekHarness
            cwd = os.getenv("HARNESS_CWD", "").strip() or str(ROOT)
            session_root = os.getenv("HARNESS_SESSION_ROOT", "").strip() or None
            max_tokens = cfg.env_int("HARNESS_MAX_TOKENS", 0) or None
            timeout = cfg.env_int("HARNESS_TIMEOUT", 0) or None
            self._harness = DeepSeekHarness(
                cwd=cwd,
                session_root=session_root,
                model=os.getenv("HARNESS_MODEL", "deepseek-chat"),
                max_tokens=max_tokens,
                request_timeout_seconds=timeout,
            )
        return self._harness

    def run(self, task: str) -> str:
        with self._lock:
            try:
                result = self._get().run(task)
            except Exception as e:
                raise RuntimeError(f"任务执行失败：{e}") from e
        reply = (result.final_response or "").strip()
        return reply or f"（已执行，结束原因：{result.finish_reason}）"

    def close(self):
        with self._lock:
            if self._harness is not None:
                try:
                    self._harness.close()
                except Exception:
                    pass
                self._harness = None


def run_task_sync(task: str) -> str:
    """执行办公任务（阻塞，调用方放进线程池）。出错时抛 RuntimeError，由调用方转成友好文案。"""
    global _runner
    if not is_enabled():
        raise RuntimeError("办公模式未启用（HARNESS_ENABLED=false）")
    if not is_available():
        raise RuntimeError("未安装 deepseek-harness-sdk，请先 pip install deepseek-harness-sdk")
    with _runner_lock:
        if _runner is None:
            _runner = _HarnessRunner()
    return _runner.run(task)


def close():
    """进程退出前释放 harness 子进程"""
    global _runner
    with _runner_lock:
        if _runner is not None:
            _runner.close()
            _runner = None
