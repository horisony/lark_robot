#!/bin/bash
# 阿里云部署脚本
# 使用方法：./deploy.sh

set -e

echo "🚀 开始部署到阿里云..."
echo ""

# 1. 提交并推送最新代码
echo "📦 步骤 1/5: 提交最新代码..."
git add Dockerfile docker-compose.yml .env.production.example
git commit -m "deploy: 添加 Docker 部署配置" || echo "无更改"
git push origin master

# 2. SSH 到阿里云
echo ""
echo "📦 步骤 2/5: 请配置阿里云信息"
read -p "阿里云服务器 IP: " ALIYUN_IP
read -p "SSH 端口 [22]: " SSH_PORT
SSH_PORT=${SSH_PORT:-22}
read -p "SSH 用户 [root]: " SSH_USER
SSH_USER=${SSH_USER:-root}
read -p "部署目录 [/opt/lark-bot]: " DEPLOY_DIR
DEPLOY_DIR=${DEPLOY_DIR:-/opt/lark-bot}

echo ""
echo "配置信息:"
echo "  IP: $ALIYUN_IP"
echo "  用户：$SSH_USER"
echo "  目录：$DEPLOY_DIR"
read -p "确认？[y/N]: " confirm
if [[ ! $confirm =~ ^[Yy]$ ]]; then
    echo "取消部署"
    exit 1
fi

# 3. 在阿里云上执行部署
echo ""
echo "📦 步骤 3/5: 远程部署..."
ssh -p $SSH_PORT $SSH_USER@$ALIYUN_IP << 'ENDSSH'
# 创建部署目录
mkdir -p DEPLOY_DIR
cd DEPLOY_DIR

# 克隆代码（如果是首次部署）
if [ ! -d ".git" ]; then
    git clone https://github.com/horisony/lark_robot.git temp
    mv temp/lark-samples-main/echo_bot/python/* .
    mv temp/lark-samples-main/echo_bot/python/.* . 2>/dev/null || true
    rm -rf temp
else
    # 已存在，更新代码
    git pull origin master
fi

# 创建配置目录
mkdir -p sessions logs

# 创建 .env 文件
if [ ! -f ".env" ]; then
    echo "⚠️  需要配置 .env 文件"
    echo "请执行：cp .env.production.example .env && vim .env"
    exit 1
fi

# 构建并启动
docker compose down || true
docker compose build --no-cache
docker compose up -d

# 查看状态
echo ""
echo "📊 容器状态:"
docker compose ps

# 查看日志
echo ""
echo "📋 最近日志:"
docker compose logs --tail=20
ENDSSH

# 4. 验证部署
echo ""
echo "📦 步骤 4/5: 验证部署..."
ssh -p $SSH_PORT $SSH_USER@$ALIYUN_IP "docker compose ps"

# 5. 完成
echo ""
echo "✅ 部署完成！"
echo ""
echo "管理命令："
echo "  查看状态：ssh $SSH_USER@$ALIYUN_IP 'docker compose ps'"
echo "  查看日志：ssh $SSH_USER@$ALIYUN_IP 'docker compose logs -f'"
echo "  重启服务：ssh $SSH_USER@$ALIYUN_IP 'docker compose restart'"
echo "  停止服务：ssh $SSH_USER@$ALIYUN_IP 'docker compose down'"
echo "  更新代码：ssh $SSH_USER@$ALIYUN_IP 'cd $DEPLOY_DIR && git pull && docker compose up -d --build'"
echo ""
echo "📝 记得在阿里云配置 .env 文件！"
