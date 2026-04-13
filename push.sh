#!/bin/bash
# 推送代码到 GitHub
# 使用方法：./push.sh

set -e

echo "📦 准备推送到 GitHub..."
echo ""
echo "请选择认证方式："
echo "1. 使用 GitHub Personal Access Token"
echo "2. 使用 SSH Key"
echo "3. 手动推送（显示命令）"
echo ""
read -p "选择 [1/2/3]: " choice

case $choice in
    1)
        read -p "请输入 GitHub Personal Access Token: " -s token
        echo ""
        git push https://horisony:$token@github.com/horisony/lark_robot.git master
        ;;
    2)
        echo "请确保已配置 SSH Key："
        echo "  ssh-keygen -t ed25519 -C 'your_email@example.com'"
        echo "  然后到 GitHub Settings → SSH and GPG keys 添加公钥"
        git push git@github.com:horisony/lark_robot.git master
        ;;
    3)
        echo ""
        echo "手动推送命令："
        echo "  cd /home/admin/.openclaw/workspace/lark_robot"
        echo "  git push origin master"
        echo ""
        echo "或使用 Token："
        echo "  git push https://<YOUR_TOKEN>@github.com/horisony/lark_robot.git master"
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac

echo ""
echo "✅ 推送完成！"
