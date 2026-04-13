FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建会话存储目录
RUN mkdir -p /app/sessions

# 环境变量（可在 docker-compose.yml 中覆盖）
ENV LOG_LEVEL=INFO
ENV SESSION_STORE_DIR=/app/sessions
ENV SKILL_ROUTER=llm
ENV SKILL_DEFAULT=BaoAI-strategy

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)" || exit 1

# 启动命令
CMD ["python3", "main.py"]
