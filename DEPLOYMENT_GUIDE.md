# 飞书机器人部署手册

**版本**：v1.0  
**最后更新**：2026-04-13  
**适用环境**：阿里云 + Alibaba Cloud Linux + Docker

---

## 📋 目录

1. [飞书开放平台配置](#1-飞书开放平台配置)
2. [阿里云服务器准备](#2-阿里云服务器准备)
3. [一键部署命令](#3-一键部署命令)
4. [配置环境变量](#4-配置环境变量)
5. [验证与测试](#5-验证与测试)
6. [日常运维](#6-日常运维)
7. [故障排查](#7-故障排查)

---

## 1. 飞书开放平台配置

### 1.1 创建应用

1. 访问 https://open.feishu.cn/app
2. 点击 **创建应用**
3. 选择 **机器人** 类型
4. 填写应用名称（如：Echo Bot）
5. 点击 **创建**

### 1.2 获取应用凭证

1. 进入应用管理页面
2. 左侧菜单 → **凭证与基础信息**
3. 记录以下信息（后续配置要用）：
   - **App ID**：`cli_xxxxxxxxxxxxxxxx`
   - **App Secret**：`xxxxxxxxxxxxxxxxxxxxxxxx`

### 1.3 配置机器人

1. 左侧菜单 → **机器人**
2. 点击 **添加机器人**
3. 填写：
   - 机器人名称：Echo Bot
   - 机器人头像：（可选）
4. 点击 **完成**

### 1.4 开通权限

1. 左侧菜单 → **权限管理**
2. 点击 **开通权限**
3. 搜索并添加以下权限：

| 权限名称 | 权限标识 | 用途 |
|---------|---------|------|
| 获取用户信息 | `contact:user` | 查询用户信息 |
| 发送消息 | `im:message` | 回复用户消息 |
| 读取会话信息 | `im:chat` | 获取会话详情 |
| 日历管理 | `calendar:calendar` | 查询/创建日程（可选） |
| 任务管理 | `task:task` | 创建/查询任务（可选） |
| 多维表格 | `bitable:app` | 操作多维表格（可选） |

4. 点击 **申请**（如需要管理员审批）

### 1.5 配置事件订阅

1. 左侧菜单 → **事件订阅**
2. 开启 **启用事件订阅**
3. 订阅以下事件：
   - **接收消息**：`im.message.receive_v1`
   - **消息已读**：`im.message.message_read_v1`（可选）
4. 点击 **保存**

### 1.6 发布应用

1. 左侧菜单 → **版本管理与发布**
2. 点击 **创建版本**
3. 填写版本号（如：1.0.0）
4. 点击 **提交审核**（如需要）
5. 审核通过后点击 **发布**

### 1.7 邀请机器人到群

1. 打开飞书客户端
2. 进入目标群聊
3. 点击右上角 **设置** → **群机器人**
4. 点击 **添加机器人**
5. 选择你创建的机器人
6. 点击 **添加**

---

## 2. 阿里云服务器准备

### 2.1 创建实例

1. 访问 https://ecs.console.aliyun.com
2. 点击 **创建实例**
3. 配置：
   - **地域**：选择离你最近的
   - **镜像**：Alibaba Cloud Linux 3（或 Ubuntu 22.04）
   - **实例规格**：ecs.t5/t6（1 核 2G 即可）
   - **存储**：40GB ESSD
   - **网络**：分配公网 IP
4. 设置 **root 密码**（记住！）
5. 点击 **确认订单**

### 2.2 配置安全组

1. 实例创建完成后，进入 **安全组** 配置
2. 添加入站规则：

| 规则 | 端口 | 授权对象 | 协议 |
|-----|------|---------|------|
| SSH | 22 | 0.0.0.0/0 | TCP |
| HTTP（可选） | 80 | 0.0.0.0/0 | TCP |
| HTTPS（可选） | 443 | 0.0.0.0/0 | TCP |

### 2.3 获取公网 IP

1. 在 ECS 控制台找到你的实例
2. 记录 **公网 IP**（如：`47.98.123.45`）

---

## 3. 一键部署命令

### 3.1 SSH 登录阿里云

```bash
ssh root@<你的公网 IP>
# 示例：ssh root@47.98.123.45
# 输入 root 密码
```

### 3.2 安装 Docker

```bash
# Alibaba Cloud Linux 使用 yum 安装
yum install -y docker
systemctl start docker
systemctl enable docker

# 验证
docker --version
```

### 3.3 克隆代码

```bash
# 创建部署目录
mkdir -p /opt/lark-bot
cd /opt/lark-bot

# 克隆代码
git clone https://github.com/horisony/lark_robot.git temp
mv temp/lark-samples-main/echo_bot/python/* .
mv temp/lark-samples-main/echo_bot/python/.* . 2>/dev/null || true
rm -rf temp

# 验证文件
ls -la
```

### 3.4 配置环境变量

```bash
# 复制配置模板
cp .env.production.example .env

# 编辑配置
vim .env
```

按 `i` 进入编辑模式，填写以下内容（**替换为你的实际值**）：

```bash
# 飞书应用配置（必填）
APP_ID=cli_xxxxxxxxxxxxxxxx
APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx

# 模型配置（必填其一）
# 方案 1：MiniMax（推荐）
ANTHROPIC_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
MINIMAX_MODEL=MiniMax-M2.7

# 方案 2：Packy（备用）
# PACKY_API_KEY=xxx
# PACKY_API_BASE=https://www.packyapi.com/v1
# PACKY_MODEL=claude-opus-4-6

# 技能配置（可选）
SKILL_ROUTER=llm
SKILL_DEFAULT=BaoAI-strategy

# 会话存储（可选）
SESSION_STORE_DIR=/app/sessions
SESSION_MAX_HISTORY=50

# 日志级别（可选）
LOG_LEVEL=INFO
```

填写完成后：
- 按 `Esc` 键
- 输入 `:wq` 保存退出

### 3.5 启动服务

```bash
# 创建数据目录
mkdir -p sessions logs

# 启动 Docker Compose
docker compose up -d

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f
```

---

## 4. 配置环境变量详解

### 4.1 必填配置

| 变量名 | 说明 | 获取方式 |
|-------|------|---------|
| `APP_ID` | 飞书应用 ID | 飞书开放平台 → 凭证与基础信息 |
| `APP_SECRET` | 飞书应用密钥 | 飞书开放平台 → 凭证与基础信息 |
| `ANTHROPIC_API_KEY` | MiniMax API Key | https://api.minimax.io |
| 或 `PACKY_API_KEY` | Packy API Key | https://www.packyapi.com |

### 4.2 可选配置

| 变量名 | 默认值 | 说明 |
|-------|--------|------|
| `SKILL_ROUTER` | `llm` | 技能路由模式（`llm` / `keywords` / `off`） |
| `SKILL_DEFAULT` | `BaoAI-strategy` | 默认技能 |
| `SESSION_STORE_DIR` | `/app/sessions` | 会话存储目录 |
| `LOG_LEVEL` | `INFO` | 日志级别（`DEBUG` / `INFO` / `WARNING` / `ERROR`） |

---

## 5. 验证与测试

### 5.1 检查服务状态

```bash
# 查看容器状态
docker compose ps

# 应该看到
NAME              STATUS
lark-echo-bot     Up (healthy)
```

### 5.2 查看日志

```bash
# 实时日志
docker compose logs -f

# 最近 100 行
docker compose logs --tail=100

# 成功标志
# ✅ connected to wss://msg-frontier.feishu.cn/ws/v2
# ✅ ping success
# ✅ receive pong
```

### 5.3 飞书测试

在飞书中给机器人发送以下消息：

| 测试消息 | 预期技能 | 预期结果 |
|---------|---------|---------|
| "你好" | 默认 | 机器人回复问候 |
| "我想做一个 AI 教育产品，帮我分析市场" | BaoAI-strategy | 战略分析报告 |
| "帮我写一个抖音口播稿" | IP 自媒体 | 口播文案 |
| "查看今天的日程" | feishu-calendar | 日程列表（需 OAuth） |

### 5.4 测试技能路由

```bash
# 进入容器测试
docker compose exec lark-bot python3 test_skills.py
```

---

## 6. 日常运维

### 6.1 查看状态

```bash
# 容器状态
docker compose ps

# 资源使用
docker stats lark-echo-bot

# 磁盘使用
df -h
```

### 6.2 查看日志

```bash
# 实时日志
docker compose logs -f

# 错误日志
docker compose logs | grep ERROR

# 最近 100 行
docker compose logs --tail=100
```

### 6.3 重启服务

```bash
# 重启
docker compose restart

# 停止
docker compose down

# 停止并删除数据
docker compose down -v
```

### 6.4 更新代码

```bash
cd /opt/lark-bot

# 拉取最新代码
git pull origin master

# 重新构建并启动
docker compose up -d --build

# 查看日志
docker compose logs -f
```

### 6.5 备份数据

```bash
# 备份会话数据
tar -czf sessions_backup_$(date +%Y%m%d).tar.gz sessions/

# 备份日志
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/

# 下载备份（本地执行）
scp root@<公网 IP>:/opt/lark-bot/sessions_backup_*.tar.gz ./
```

### 6.6 监控告警

```bash
# 创建健康检查脚本
cat > /opt/lark-bot/healthcheck.sh << 'EOF'
#!/bin/bash
STATUS=$(docker inspect --format='{{.State.Health.Status}}' lark-echo-bot)
if [ "$STATUS" != "healthy" ]; then
    echo "⚠️  机器人异常！" | mail -s "Lark Bot Alert" your@email.com
fi
EOF

chmod +x /opt/lark-bot/healthcheck.sh

# 添加到 crontab（每 5 分钟检查一次）
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/lark-bot/healthcheck.sh") | crontab -
```

---

## 7. 故障排查

### 7.1 容器启动失败

```bash
# 查看日志
docker compose logs

# 进入容器调试
docker compose run --rm lark-bot bash

# 手动启动测试
python3 main.py
```

### 7.2 飞书消息无响应

**检查清单**：
- [ ] APP_ID / APP_SECRET 是否正确
- [ ] 事件订阅是否开启
- [ ] 权限是否已开通
- [ ] 机器人是否已邀请到群

**排查步骤**：
```bash
# 1. 查看日志
docker compose logs | grep -i error

# 2. 测试飞书连接
docker compose exec lark-bot python3 -c "
import lark_oapi as lark
import os
client = lark.Client.builder().app_id(os.getenv('APP_ID')).app_secret(os.getenv('APP_SECRET')).build()
resp = client.contact.v3.me.get()
print('连接成功:', resp.data)
"

# 3. 重启服务
docker compose restart
```

### 7.3 模型调用失败

```bash
# 检查 API Key
docker compose exec lark-bot env | grep API_KEY

# 测试模型连接
docker compose exec lark-bot python3 -c "
from llm_client import chat_completion
try:
    reply = chat_completion('测试', system='You are a helpful assistant.')
    print('模型连接成功:', reply[:50])
except Exception as e:
    print('模型连接失败:', e)
"
```

### 7.4 内存占用过高

```bash
# 查看资源使用
docker stats lark-echo-bot

# 限制内存（修改 docker-compose.yml）
# 添加：
# deploy:
#   resources:
#     limits:
#       memory: 512M

# 重启服务
docker compose up -d
```

### 7.5 会话数据丢失

```bash
# 检查存储目录
ls -la /opt/lark-bot/sessions/

# 恢复备份
tar -xzf sessions_backup_*.tar.gz -C /opt/lark-bot/

# 重启服务
docker compose restart
```

---

## 8. 快速参考卡片

### 8.1 常用命令速查

```bash
# 登录阿里云
ssh root@<公网 IP>

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f

# 重启服务
docker compose restart

# 更新代码
cd /opt/lark-bot && git pull && docker compose up -d --build

# 备份数据
tar -czf backup_$(date +%Y%m%d).tar.gz sessions/ logs/
```

### 8.2 配置文件位置

| 文件 | 路径 | 用途 |
|-----|------|------|
| 环境变量 | `/opt/lark-bot/.env` | APP_ID, API_KEY 等 |
| 会话数据 | `/opt/lark-bot/sessions/` | 用户对话历史 |
| 日志文件 | `/opt/lark-bot/logs/` | 运行日志 |
| Docker 配置 | `/opt/lark-bot/docker-compose.yml` | 容器编排 |

### 8.3 关键 URL

| 名称 | URL |
|-----|-----|
| 飞书开放平台 | https://open.feishu.cn |
| 阿里云 ECS 控制台 | https://ecs.console.aliyun.com |
| GitHub 仓库 | https://github.com/horisony/lark_robot |

---

## 9. 附录

### 9.1 docker-compose.yml 完整配置

```yaml
version: '3.8'

services:
  lark-bot:
    build: .
    container_name: lark-echo-bot
    restart: always
    environment:
      - APP_ID=${APP_ID}
      - APP_SECRET=${APP_SECRET}
      - LARK_DOMAIN=https://open.feishu.cn
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
      - MINIMAX_MODEL=MiniMax-M2.7
      - SKILL_ROUTER=llm
      - SKILL_DEFAULT=BaoAI-strategy
      - SESSION_STORE_DIR=/app/sessions
      - LOG_LEVEL=INFO
    volumes:
      - ./sessions:/app/sessions
      - ./logs:/app/logs
    networks:
      - bot-network
    deploy:
      resources:
        limits:
          memory: 512M

networks:
  bot-network:
    driver: bridge
```

### 9.2 .env 完整示例

```bash
# 飞书应用配置
APP_ID=cli_xxxxxxxxxxxxxxxx
APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx

# 模型配置
ANTHROPIC_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
MINIMAX_MODEL=MiniMax-M2.7

# 技能配置
SKILL_ROUTER=llm
SKILL_DEFAULT=BaoAI-strategy

# 会话存储
SESSION_STORE_DIR=/app/sessions
SESSION_MAX_HISTORY=50

# 日志
LOG_LEVEL=INFO
```

---

**文档结束**

如有问题，请查看日志或联系技术支持。
