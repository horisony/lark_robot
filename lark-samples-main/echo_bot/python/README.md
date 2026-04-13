# 回声机器人（长连接 + PackyAPI）

用户文本优先经 **MiniMax**（Anthropic 兼容：`ANTHROPIC_BASE_URL` + `ANTHROPIC_API_KEY` + `MiniMax-M2.7` 等）；失败时若配置了 **Packy**，则回退 **POST** `PACKY_API_BASE/chat/completions`。

开发文档（长连接接入）：https://open.feishu.cn/document/uAjLw4CM/uMzNwEjLzcDMx4yM3ATM/develop-an-echo-bot/introduction

## 效果

![](./assets/image.png)

- 用户输入纯文本消息，机器人回复：收到你发送的消息：XXXX。
- 用户在群组内 @机器人并发送纯文本消息，机器人引用这条消息并回复：收到你发送的消息：XXXX。

## 启动项目

### 方式一：环境变量（与官方一致）

macOS/Linux： `APP_ID=<app_id> APP_SECRET=<app_secret> ./bootstrap.sh`

Windows： `set APP_ID=<app_id>&set APP_SECRET=<app_secret>&bootstrap.bat`

### 方式二：`.env`（推荐）

1. 复制 `.env.example` 为 `.env`，至少配置 **`APP_ID`、`APP_SECRET`**，以及 **`ANTHROPIC_API_KEY`（MiniMax）和/或 `PACKY_API_KEY`（备用）**；或运行 **`python3 wizard.py`**。
2. 安装依赖：`pip install -r requirements.txt`
3. 启动：`python3 main.py`

可选环境变量：`LARK_DOMAIN`、`LOG_LEVEL`。

**模型优先级**：若配置了 `ANTHROPIC_API_KEY`（或 `MINIMAX_API_KEY`），优先走 MiniMax 官方 **Anthropic 兼容** 接口（默认 `ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic`，`MINIMAX_MODEL=MiniMax-M2.7`）。调用失败且配置了 `PACKY_API_KEY` 时，回退 **OpenAI 兼容** `POST .../chat/completions`（Packy 等）。仅配 Packy 则只走 Packy。

若在日志里看到 **`processor not found, type: im.message.message_read_v1`**：表示开放平台订阅了 **消息已读** 事件，但代码未处理；当前已注册空处理器。若不需要已读事件，也可在开放平台 **事件订阅** 中取消 `im.message.message_read_v1` 以减少无关推送。

若飞书里看到 **`Packy 备用接口不可用（HTTP 403）`**：这是 **回退通道 Packy** 被拒绝（密钥/额度/封禁等），不一定是 MiniMax 的问题。请查看容器日志里是否先有 **MiniMax 调用失败**；调试时可 **`LLM_DISABLE_PACKY_FALLBACK=1`** 或 **暂时去掉 `PACKY_API_KEY`**，只测 MiniMax。并确认 Docker 里已加载 `ANTHROPIC_API_KEY`：`docker compose exec echo-bot env | grep ANTHROPIC`。

### 方式三：Docker

```bash
docker compose up --build
```

需先在当前目录准备好 `.env`（可用 `wizard.py`）。

### 飞书后台

事件订阅请选择 **长连接**，并订阅 **`im.message.receive_v1`**。无需配置公网 HTTPS 回调地址。

### 可选：企业 TLS / 代理

若启动时报 **`CERTIFICATE_VERIFY_FAILED` / `self-signed certificate in certificate chain`**（公司 HTTPS 解密常见）：

1. **推荐**：向 IT 要根证书，在 `.env` 中设置 **`FEISHU_SSL_CA_BUNDLE=/绝对路径/根证书.pem`**（或重新运行 **`python3 wizard.py`**，按提示填写 CA 路径）。
2. **仅本机调试**：在 `.env` 增加一行 **`FEISHU_INSECURE_SSL=1`**（关闭校验，**勿用于生产**）。

说明：`wizard.py` 在询问 `LARK_DOMAIN` 之后会询问 CA 路径与是否开启调试 TLS。

- SOCKS 代理环境需依赖 **`python-socks[asyncio]`**（已写入 `requirements.txt`）。

### 关于 `pkg_resources is deprecated`

来自 `lark-oapi` 依赖，不影响连接；可等待 SDK 更新，或本机设置 `export PYTHONWARNINGS=ignore::UserWarning` 减少提示。

### 云端常驻（如阿里云 ECS）

出站访问飞书即可，无需对公网开放入站端口。可参考 `deploy/feishu-bot.service` 使用 systemd 保活。

## 本目录新增文件说明（相对最小 echo 示例）

| 文件 | 说明 |
|------|------|
| `tls_extra.py` | 企业 TLS 补丁，在 `main()` 里、`wsClient.start()` 前执行 |
| `llm_client.py` | PackyAPI `POST .../chat/completions`（Bearer + JSON） |
| `wizard.py` / `wizard.sh` | 交互生成 `.env` |
| `.env.example` | 环境变量模板 |
| `Dockerfile` / `docker-compose.yml` | 容器运行 |
| `deploy/feishu-bot.service` | systemd 示例 |

`main.py` 在 **import `lark_oapi` 之前** 调用 `load_dotenv`，以便与官方一样使用 `lark.APP_ID` / `lark.APP_SECRET`；并增加 **`LARK_DOMAIN`** 传给 `Client` 与 `ws.Client`。
