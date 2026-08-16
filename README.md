# xiaoyue — DeepSeek QQ 机器人

> Powered by [DeepSeek API](https://platform.deepseek.com/)

一个基于 QQ 开放平台（botpy SDK）+ DeepSeek 的 AI 聊天机器人，支持**双模式**（情感 / 办公）、
多用户独立会话、上下文记忆、聊天记录持久化，以及一个可扩展的**信息转发接口**
（消息不止转发给 AI，可推送到任意 Webhook / 本地钩子）。

---

## 功能特性

- 私聊自动回复（60 分钟内被动回复）、群聊 @ 回复（5 分钟内被动回复）
- **双模式**：情感（话痨 + 情感陪伴人设）/ 办公（`#办公` → deepseek-harness 在电脑工作区干活）
- 重启后记住最近两句，接得上话
- 多用户独立会话
- 自定义提示词（`core/prompts/`，可直接编辑）
- **信息转发接口**：Webhook + 本地钩子，不止给 AI
- **富格式**：markdown 消息、键盘按钮切换模式、Ark 卡片（办公结果）、`#图` 发图
- 聊天记录持久化（`chat_logs/`）

---

## 两种模式：情感 / 办公

机器人每条消息按前缀路由到两种模式：

- **情感模式**（默认）：普通聊天就是「话痨 + 情感陪伴」人设（`core/prompts/`）；
- **办公模式**：消息以 `#办公` 开头（`OFFICE_PREFIX` 可改），把前缀后的内容当作任务交给
  [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 的 agent，在 `HARNESS_CWD`
  指定的工作区里干活，完成后把 `final_response` 回传给你——**手机发消息，电脑选工作区干活**。

办公模式依赖（按需安装，较重，不进 requirements.txt）：

```bash
pip install deepseek-harness-sdk
```

**模式命令**：`#办公 <任务>`（临时任务）、`#办公模式`（切办公）、`#情感`（切回情感）、
`#菜单`（弹键盘按钮）、`#图 <链接>`（发图）。

**富格式**：办公结果默认发 **markdown 消息**（代码块/列表保留），配 `ARK_TEMPLATE_ID`
后改发 **Ark 卡片**，`#菜单` 带**键盘按钮**切换模式。

---

## 目录结构

```
robit/
├── qqbot/                # 机器人入口
│   ├── bot.py            #   botpy SDK + DeepSeek（被动回复）
│   ├── .env              #   密钥配置（不提交 Git）
│   └── .env.example      #   配置模板
├── core/                 # 核心逻辑
│   ├── config.py         #   配置：提示词 / 模型 / 转发 / 端口
│   ├── store.py          #   聊天记录存储（原子写）
│   ├── forwarder.py      #   信息转发接口（Webhook + 本地钩子）
│   ├── harness.py        #   办公模式：deepseek-harness 桥接
│   ├── modes.py          #   双模式路由（情感/办公）
│   ├── prompts/          #   本地提示词模板（可编辑）
│   └── hooks/            #   转发钩子脚本目录（*.py 自动加载）
├── requirements.txt      # 统一依赖
├── chat_logs/            # 聊天记录（运行时生成，每人一个 JSON 文件，不提交）
├── README.md             # 本文档
└── 技术文档.md           # 技术细节（本地私有，含隐私信息，不提交）
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置密钥

1. 复制 `qqbot/.env.example` 为 `qqbot/.env`；
2. 填入真实值（所有配置项见下表）。

| 配置项 | 必填 | 说明 |
|--------|:---:|------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek 平台密钥（platform.deepseek.com） |
| `DEEPSEEK_API_URL` | 否 | DeepSeek API 地址，默认官方地址 |
| `DEEPSEEK_MODEL` | 否 | 模型，默认 `deepseek-chat` |
| `BOT_APPID` / `BOT_SECRET` | ✅ | q.qq.com 开放平台创建机器人后获取 |
| `BOT_QQ_ID` | 建议 | 机器人 QQ 号，用于日志显示 |
| `SUPERUSERS` | 否 | 管理员 QQ 号，多个用英文逗号分隔 |
| `SYSTEM_PROMPT_FILE` | 否 | 自定义提示词文件（多行，推荐）；不配置则读 `core/prompts/default.txt` |
| `SYSTEM_PROMPT` | 否 | 提示词内联写法（单行，换行用 `\n`），文件优先 |
| `AI_ENABLED` | 否 | AI 回复总开关，默认 `true`；关闭后只记录+转发，不调用大模型 |
| `FORWARD_ENABLED` | 否 | 信息转发开关，默认 `true` |
| `FORWARD_URLS` | 否 | 逗号分隔的 Webhook URL，每条消息 POST JSON（**不止转发给 AI**） |
| `FORWARD_REPLIES` | 否 | 是否也转发机器人自己的回复，默认 `true` |
| `FORWARD_TIMEOUT` | 否 | 单个 Webhook 超时秒数，默认 `5` |
| `MODEL_TEMP` | 否 | 采样温度 0-2，默认 `0.7`（不能叫 TEMP，Windows 保留变量） |
| `MAX_TOKENS` | 否 | 单次最大输出，默认 `1024` |
| `OFFICE_PREFIX` | 否 | 办公模式触发前缀，默认 `#办公` |
| `SWITCH_OFFICE_CMD` | 否 | 切换办公模式命令，默认 `#办公模式` |
| `SWITCH_EMOTION_CMD` | 否 | 切回情感模式命令，默认 `#情感` |
| `MENU_CMD` | 否 | 模式菜单命令，默认 `#菜单` |
| `IMAGE_CMD` | 否 | 发图命令，默认 `#图` |
| `ARK_TEMPLATE_ID` | 否 | 办公结果 Ark 卡片模板 id（0=用 markdown） |
| `HARNESS_ENABLED` | 否 | 办公模式开关，默认 `true` |
| `HARNESS_CWD` | 否 | 办公模式工作区目录，默认项目根目录 |
| `HARNESS_SESSION_ROOT` | 否 | 会话持久化目录（可选） |
| `HARNESS_MODEL` | 否 | 办公模式模型，默认 `deepseek-chat` |
| `HARNESS_MAX_TOKENS` | 否 | 办公模式每次最大输出，默认 0=用提供方默认 |
| `HARNESS_TIMEOUT` | 否 | 单次任务超时秒数，默认 0=不限 |
| `HARNESS_REPLY_MAX` | 否 | 办公结果回传最长字数（纯文本），默认 1000 |
| `HARNESS_MARKDOWN_MAX` | 否 | 办公结果 markdown 回传最长字数，默认 3000 |

> 💡 配置直接编辑 `.env`（或 `core/prompts/` 下的提示词文件），重启生效。
> ⚠️ `.env` 已在 `.gitignore` 中，**绝不会提交**。

### 3. 启动

```bash
python qqbot/bot.py
```

### 4. 验证

- 私聊机器人 QQ、或群内 @机器人，应收到回复；
- 发 `#菜单` 会弹键盘按钮（切换情感/办公模式）；
- 发 `#办公 <任务>` 走办公模式（需先 `pip install deepseek-harness-sdk`）。

---

## 信息转发接口（不止转发给 AI）

机器人收到的每一条消息（以及它自己的回复）除了送给 DeepSeek 之外，还会通过
`core/forwarder.py` 转发到任意下游，失败只打印日志、不影响主流程。

**两种转发目的地：**

1. **Webhook**：在 `.env` 配 `FORWARD_URLS=https://a.com/hook,https://b.com/hook`，
   每条消息以 JSON POST 到这些地址（事件结构见 `core/hooks/README.md`）。
2. **本地钩子**：把任意 `.py` 放进 `core/hooks/`，实现 `def handle(event)`（可 `async`），
   每条消息自动调用。

**纯转发模式**：把 `AI_ENABLED=false`，机器人就只记录 + 转发、不调用大模型，
可用于把 QQ 当作「消息采集管道」，由下游任意系统处理。

事件结构（节选）：`source`(official)、`type`(private/group)、`direction`(in/out)、
`uid`、`from`、`from_name`、`text`、`time`/`date`/`ts`。事件可携带任意扩展字段。

---

## 聊天记录

- 存储：`chat_logs/{uid}.json`，每人独立文件，最多保留 300 条；
- 每条消息带 `mode`（official）、`direction`（in/out）、`time`/`_date`；
- 隐私：`chat_logs/` 已加入 `.gitignore`，不会提交。

---

## 常见问题

| 问题 | 原因与解决 |
|------|-----------|
| 机器人没回复 | 检查 `.env` 中 DeepSeek Key 与网络/代理（默认 `http://127.0.0.1:7897`，失败自动直连） |
| 官方模式登录失败 | AppID/Secret 错误，到 q.qq.com 后台确认 |
| 办公模式没反应 | 确认已 `pip install deepseek-harness-sdk`，且 `HARNESS_CWD` 指向正确工作区 |

---

## 安全

- `.env`、`chat_logs/`、`*.log*`、`技术文档.md` 全部在 `.gitignore` 中，不会推送；
- 推送前建议运行一次敏感信息扫描（`sk-`、QQ 号、openid 等模式）；
- 若怀疑密钥泄露，请到 DeepSeek / q.qq.com 平台重新生成密钥并更新 `.env`。

## 许可证

MIT
