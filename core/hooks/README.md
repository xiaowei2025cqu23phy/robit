# 信息转发钩子（hooks）

把任意 `.py` 放到本目录，实现 `handle(event)`，即可在机器人每条收发消息时被调用。
下划线开头的文件（如 `_example.py`）不会被加载。

## 事件结构（event）

```python
{
    "source": "official" | "real",     # 来源模式
    "type": "private" | "group",       # 消息类型
    "direction": "in" | "out",         # 收到 / 机器人发出
    "uid": "...",                      # 对端用户标识
    "from": "...",                     # 发送者标识
    "from_name": "...",                # 显示名
    "text": "...",                     # 消息正文
    "time": "HH:MM:SS", "date": "YYYY-MM-DD", "ts": "ISO8601",
}
```

## 示例

```python
# my_hook.py
def handle(event):
    print(f"[my_hook] {event['direction']} {event['type']}: {event['text'][:30]}")

# 也支持异步
async def handle(event):
    await some_async_save(event)
```

## 面向「远程 Agent 文件/任务接口」的扩展

本接口是双向扩展的基础：`event` 可携带任意结构化字段（例如 `data={"kind":"file","name":...,"url":...}`），
下游钩子既可「消费」事件（收文件、记日志），未来也可作为「任务入口」回传指令给 Agent。
