# 阿里云部署指南

本文档指导如何将 Echo Bot 部署到阿里云服务器，实现 7x24 小时运行。

---

## 📋 准备工作

### 1. 阿里云服务器要求

| 配置 | 最低要求 | 推荐配置 |
|-----|---------|---------|
| CPU | 1 核 | 2 核 |
| 内存 | 512MB | 2GB |
| 磁盘 | 10GB | 20GB |
| 系统 | Ubuntu 20.04+ | Ubuntu 22.04 LTS |
| 网络 | 能访问 GitHub 和飞书 API | - |

### 2. 开放防火墙端口

阿里云控制台 → 安全组 → 添加入站规则：
- **无需开放端口**（机器人通过长连接接收消息，不需要入站端口）

---

## 🚀 快速部署（Docker 方案）

### 方法一：自动部署脚本（推荐）

```bash
# 1. 克隆代码（本地）
cd /home/admin/.openclaw/workspace/lark_robot

# 2. 运行部署脚本
chmod +x deploy.sh
./deploy.sh
```

脚本会：
1. 提交最新代码到 GitHub
2. SSH 登录阿里云
3. 自动安装 Docker、拉取代码、构建镜像、启动服务
4. 提示你配置 `.env` 文件

### 方法二：手动部署

#### 步骤 1：SSH 登录阿里云

```bash
ssh root@<你的阿里云 IP>
```

#### 步骤 2：安装 Docker

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | bash -s docker

# 启动 Docker
systemctl enable docker
systemctl start docker

# 验证
docker --version
docker compose version
```

#### 步骤 3：克隆代码

```bash
# 创建部署目录
mkdir -p /opt/lark-bot
cd /opt/lark-bot

# 克隆代码
git clone https://github.com/horisony/lark_robot.git temp
mv temp/lark-samples-main/echo_bot/python/* .
mv temp/lark-samples-main/echo_bot/python/.* . 2>/dev/null || true
rm -rf temp
```

#### 步骤 4：配置环境变量

```bash
# 复制配置模板
cp .env.production.example .env

# 编辑配置
vim .env
```

**必填配置**：
```bash
# 飞书应用
APP_ID=cli_xxx
APP_SECRET=xxx

# 模型 API（至少配置一个）
ANTHROPIC_API_KEY=sk-xxx
# 或
PACKY_API_KEY=xxx
```

#### 步骤 5：构建并启动

```bash
# 创建数据目录
mkdir -p sessions logs

# 构建镜像
docker compose build

# 启动服务
docker compose up -d

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f
```

---

## 🔧 管理命令

### 查看状态

```bash
# SSH 登录
ssh root@<你的阿里云 IP>

# 查看容器状态
docker compose ps

# 查看详细状态
docker inspect lark-echo-bot
```

### 查看日志

```bash
# 实时日志
docker compose logs -f

# 最近 100 行
docker compose logs --tail=100

# 错误日志
docker compose logs | grep ERROR
```

### 重启服务

```bash
# 重启
docker compose restart

# 停止
docker compose down

# 停止并删除数据
docker compose down -v
```

### 更新代码

```bash
cd /opt/lark-bot

# 拉取最新代码
git pull origin master

# 重新构建并启动
docker compose up -d --build

# 查看日志确认启动成功
docker compose logs -f
```

---

## 📊 方案二：systemd 服务（无 Docker）

如果不想用 Docker，可以用 systemd：

### 步骤 1：安装 Python 依赖

```bash
cd /opt/lark-bot

# 安装 Python
apt update
apt install -y python3 python3-pip python3-venv

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 步骤 2：创建 systemd 服务

```bash
cat > /etc/systemd/system/lark-bot.service << EOF
[Unit]
Description=Lark Echo Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/lark-bot
Environment="PATH=/opt/lark-bot/venv/bin"
ExecStart=/opt/lark-bot/venv/bin/python3 main.py
Restart=always
RestartSec=10

# 日志
StandardOutput=journal
StandardError=journal
SyslogIdentifier=lark-bot

[Install]
WantedBy=multi-user.target
EOF
```

### 步骤 3：启动服务

```bash
# 重载 systemd
systemctl daemon-reload

# 启用服务（开机自启）
systemctl enable lark-bot

# 启动服务
systemctl start lark-bot

# 查看状态
systemctl status lark-bot

# 查看日志
journalctl -u lark-bot -f
```

### 步骤 4：管理命令

```bash
# 查看状态
systemctl status lark-bot

# 重启
systemctl restart lark-bot

# 停止
systemctl stop lark-bot

# 查看日志
journalctl -u lark-bot -n 100
```

---

## 🔍 故障排查

### 容器启动失败

```bash
# 查看日志
docker compose logs

# 进入容器调试
docker compose run --rm lark-bot bash

# 手动启动测试
python3 main.py
```

### 飞书消息无响应

1. 检查飞书开放平台配置：
   - 应用凭证是否正确
   - 事件订阅 URL 是否正确
   - 权限是否已配置

2. 查看日志：
```bash
docker compose logs | grep -i error
```

3. 测试连接：
```bash
docker compose exec lark-bot python3 -c "
import lark_oapi as lark
client = lark.Client.builder().app_id('xxx').app_secret('xxx').build()
resp = client.contact.v3.me.get()
print(resp.data)
"
```

### 内存占用过高

```bash
# 查看资源使用
docker stats lark-echo-bot

# 限制内存（修改 docker-compose.yml）
deploy:
  resources:
    limits:
      memory: 512M
```

---

## 📈 监控建议

### 1. 系统监控

安装阿里云监控插件：
```bash
# 云监控插件
wget http://cms-agent-cn-hangzhou.oss-cn-hangzhou.aliyuncs.com/release/cms_darwin_amd64.zip
# 参考：https://help.aliyun.com/document_detail/97673.html
```

### 2. 日志监控

配置日志告警（阿里云日志服务）：
```bash
# 安装 logtail
wget http://logtail-release.oss-cn-hangzhou.aliyuncs.com/linux64/logtail.sh
chmod +x logtail.sh
./logtail.sh install
```

### 3. 健康检查

添加健康检查脚本：
```bash
cat > /opt/lark-bot/healthcheck.sh << 'EOF'
#!/bin/bash
# 检查容器是否健康
docker inspect --format='{{.State.Health.Status}}' lark-echo-bot
EOF

chmod +x healthcheck.sh
```

---

## 🎯 部署检查清单

- [ ] 阿里云服务器已创建
- [ ] Docker 已安装
- [ ] 代码已克隆到 `/opt/lark-bot`
- [ ] `.env` 文件已配置（APP_ID, APP_SECRET, API_KEY）
- [ ] 容器已启动（`docker compose ps` 显示 UP）
- [ ] 日志无 ERROR（`docker compose logs`）
- [ ] 飞书机器人可正常响应

---

## 📞 后续支持

如有问题：
1. 查看日志：`docker compose logs -f`
2. 检查配置：`cat .env`
3. 重启服务：`docker compose restart`

**部署完成后，在飞书中发送消息测试即可！**
