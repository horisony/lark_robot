# 回声机器人

开发文档：https://open.feishu.cn/document/uAjLw4CM/uMzNwEjLzcDMx4yM3ATM/develop-an-echo-bot/introduction

## 效果

![](./assets/image.png)

- 用户输入纯文本消息，机器人回复：收到你发送的消息：XXXX。
- 用户在群组内 @机器人并发送纯文本消息，机器人引用这条消息并回复：收到你发送的消息：XXXX。

## 启动项目

### 方式一：环境变量（与官方一致）

macOS/Linux： `APP_ID=<app_id> APP_SECRET=<app_secret> ./bootstrap.sh`

Windows： `set APP_ID=<app_id>&set APP_SECRET=<app_secret>&bootstrap.bat`

### 方式二：`.env`（推荐）

1. 复制 `.env.example` 为 `.env` 并填写 `APP_ID`、`APP_SECRET`，或运行 **`python3 wizard.py`**（`./wizard.sh`）。
2. 安装依赖：`pip install -r requirements.txt`
3. 启动：`python3 main.py`

可选环境变量：`LARK_DOMAIN`（默认 `https://open.feishu.cn`，Lark 国际版常用 `https://open.larksuite.com`）、`LOG_LEVEL`。

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
| `wizard.py` / `wizard.sh` | 交互生成 `.env` |
| `.env.example` | 环境变量模板 |
| `Dockerfile` / `docker-compose.yml` | 容器运行 |
| `deploy/feishu-bot.service` | systemd 示例 |

`main.py` 在 **import `lark_oapi` 之前** 调用 `load_dotenv`，以便与官方一样使用 `lark.APP_ID` / `lark.APP_SECRET`；并增加 **`LARK_DOMAIN`** 传给 `Client` 与 `ws.Client`。
