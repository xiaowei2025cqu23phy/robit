#!/usr/bin/env python3
"""
双模式路由 — 情感模式 / 办公模式（官方/真人共用）。

命令（前缀均可用 .env 覆盖）:
  #办公 <任务>   一次性办公任务（交给 harness）
  #办公模式       切换到办公模式（之后每条消息都当任务）
  #情感          切回情感模式（默认）
  #菜单          发送模式菜单（官方机器人带键盘按钮）
  #图 <URL/图>   让机器人发一张图片

每用户模式状态存内存（进程内），重启回到默认情感模式。
"""
import os

MODE_EMOTION = "emotion"
MODE_OFFICE = "office"

OFFICE_PREFIX = os.getenv("OFFICE_PREFIX", "#办公")
SWITCH_OFFICE_CMD = os.getenv("SWITCH_OFFICE_CMD", "#办公模式")
SWITCH_EMOTION_CMD = os.getenv("SWITCH_EMOTION_CMD", "#情感")
MENU_CMD = os.getenv("MENU_CMD", "#菜单")
IMAGE_CMD = os.getenv("IMAGE_CMD", "#图")


class ModeState:
    """每用户当前模式（内存态）"""

    def __init__(self):
        self._modes = {}

    def get(self, uid) -> str:
        return self._modes.get(str(uid), MODE_EMOTION)

    def set(self, uid, mode: str):
        self._modes[str(uid)] = mode


state = ModeState()


def parse(text: str):
    """解析消息 → (action, payload)。

    action: office_task / switch_office / switch_emotion / menu / send_image / usage / chat
    """
    text = (text or "").strip()
    # 精确命令优先于前缀（避免「#办公模式」被「#办公」前缀吞掉）
    if text == SWITCH_OFFICE_CMD:
        return ("switch_office", None)
    if text == SWITCH_EMOTION_CMD:
        return ("switch_emotion", None)
    if text == MENU_CMD:
        return ("menu", None)
    if text.startswith(OFFICE_PREFIX):
        rest = text[len(OFFICE_PREFIX):].strip()
        return ("office_task", rest) if rest else ("usage", None)
    if text.startswith(IMAGE_CMD):
        img = text[len(IMAGE_CMD):].strip()
        return ("send_image", img) if img else ("usage", IMAGE_CMD)
    return ("chat", text)


def mode_label(mode: str) -> str:
    return "💼 办公模式" if mode == MODE_OFFICE else "💬 情感模式"


def usage_hint() -> str:
    return f"用法：{OFFICE_PREFIX} <要做的事>，比如「{OFFICE_PREFIX} 把 README 的错别字改掉」"


def menu_text(uid=None) -> str:
    m = state.get(uid) if uid is not None else MODE_EMOTION
    return (f"我现在是{mode_label(m)}。\n"
            f"· {OFFICE_PREFIX} <要做的事>：临时交办一件任务\n"
            f"· {SWITCH_OFFICE_CMD}：切成办公模式（之后每条都是任务）\n"
            f"· {SWITCH_EMOTION_CMD}：切回情感聊天\n"
            f"· {IMAGE_CMD} <图片链接>：让我发张图")


def build_keyboard():
    """官方机器人的内联键盘（回调按钮 action.type=1，挂在 markdown 消息上）"""

    def _btn(btn_id, label, data):
        return {
            "id": btn_id,
            "render_data": {"label": label, "visited_label": label, "style": 1},
            "action": {
                "type": 1,  # 1 = 回调按钮，data 回传后台
                "permission": {"type": 2, "specify_role_ids": [], "specify_user_ids": []},
                "click_limit": 0,
                "data": data,
                "at_bot_show_channel_list": False,
            },
        }

    return {"content": {"rows": [{"buttons": [
        _btn("mode_emotion", "💬 情感模式", "emotion"),
        _btn("mode_office", "💼 办公模式", "office"),
    ]}]}}
