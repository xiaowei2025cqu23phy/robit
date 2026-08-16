# 示例钩子：改名为不带下划线的 .py（如 my_hook.py）即可启用。
# 每条消息都会调用 handle(event)，event 字段见 README.md。
def handle(event):
    print(f"[example-hook] {event.get('direction')} {event.get('type')}: "
          f"{(event.get('text') or '')[:30]}")
