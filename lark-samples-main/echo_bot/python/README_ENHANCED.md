# Echo Bot 增强版 - 完整 Skill 系统

本目录包含对原始 echo_bot 的增强改造，使其具备类似 OpenClaw 的完整 Skill 系统。

## 🎯 改造内容

### 1. 新增模块

| 文件 | 功能 | 说明 |
|-----|------|------|
| `session_store.py` | 会话管理 | 持久化用户对话历史、变量、技能状态 |
| `skill_executor.py` | 技能执行器 | 支持 Prompt 模式 + Code 模式执行技能 |
| `skills/feishu-calendar/` | 示例技能 | 飞书日历管理（查询/创建/删除日程） |

### 2. 修改内容

| 文件 | 修改 | 说明 |
|-----|------|------|
| `main.py` | `_process_im_message()` | 集成会话存储 + 技能执行器 |
| `.env.example` | 新增配置项 | 会话存储、OAuth 配置 |

### 3. 技能结构升级

**原始结构**（仅 Prompt）：
```
skills/
└── BaoAI-strategy/
    └── SKILL.md          # prompt 模板
```

**增强结构**（Prompt + Code）：
```
skills/
├── BaoAI-strategy/
│   ├── SKILL.md          # prompt 模板
│   └── executor.py       # 可执行代码（可选）
├── feishu-calendar/
│   ├── SKILL.md          # 技能说明
│   └── executor.py       # 调用飞书 API
└── ...
```

## 🚀 快速开始

### 1. 配置环境变量

复制 `.env.example` 为 `.env` 并填写：

```bash
cd echo_bot/python
cp .env.example .env
```

**必填项**：
- `APP_ID` / `APP_SECRET`：飞书开放平台凭证
- `ANTHROPIC_API_KEY` 或 `PACKY_API_KEY`：模型 API Key

**可选项**：
- `SESSION_STORE_DIR`：会话存储目录（默认 `./sessions`）
- `SKILL_ROUTER`：路由模式（`llm` / `keywords` / `off`）
- `SKILL_DEFAULT`：默认技能（默认 `BaoAI-strategy`）

### 2. 启动机器人

```bash
python3 main.py
```

或使用 Docker：

```bash
docker compose up --build
```

### 3. 测试技能

在飞书中发送消息：

- **战略分析**："我想做一个 AI 教育产品，帮我分析市场机会"
- **日历查询**："查看今天的日程"
- **创建会议**："明天下午 2 点帮我创建一个会议，讨论产品规划"

## 📚 开发指南

### 创建新技能

#### 方式 1：Prompt 模式（简单）

创建目录和 SKILL.md：

```bash
mkdir skills/my-skill
cat > skills/my-skill/SKILL.md << 'EOF'
---
name: my-skill
description: 我的技能描述
router_keywords:
  - 关键词 1
  - 关键词 2
---

# 你的技能 prompt

你是一个...
EOF
```

#### 方式 2：Code 模式（强大）

添加 `executor.py`：

```python
#!/usr/bin/env python3
"""我的技能执行器"""
from typing import Dict, Any

def execute(user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行技能
    
    Args:
        user_text: 用户消息
        context: 会话上下文 {chat_id, user_id, history, vars}
    
    Returns:
        {"text": "回复内容"} 或 {"error": "错误信息"}
    """
    # 可以调用飞书 API
    # 可以调用外部服务
    # 可以调用 LLM
    
    return {"text": "Hello from my skill!"}
```

### 调用飞书 API

使用 `skill_executor.py` 提供的工具函数：

```python
from skill_executor import create_feishu_client

def execute(user_text: str, context: dict):
    client = create_feishu_client()
    
    # 查询用户信息
    resp = client.contact.v3.me.get()
    user = resp.data
    
    return {"text": f"你好，{user.name}！"}
```

### 访问会话历史

```python
def execute(user_text: str, context: dict):
    # 获取历史消息
    history = context.get("history", [])
    
    # 获取会话变量
    vars = context.get("vars", {})
    
    # 设置变量（会在下次对话时保留）
    # 需要在 main.py 中通过 session_store.set_var 实现
    
    return {"text": f"我们之前聊了 {len(history)} 条消息"}
```

## 🔧 高级配置

### 技能路由策略

| 模式 | 配置 | 说明 |
|-----|------|------|
| LLM 路由 | `SKILL_ROUTER=llm` | 最准确，消耗 Token |
| 关键词路由 | `SKILL_ROUTER=keywords` | 快速，不消耗 Token |
| 混合模式 | `SKILL_ROUTER=llm` + `SKILL_ROUTER_KEYWORDS=1` | 先关键词，平局时 LLM（推荐） |
| 固定技能 | `SKILL_ROUTER=fixed:BaoAI-strategy` | 调试用，始终用指定技能 |
| 禁用路由 | `SKILL_ROUTER=off` | 只用 `MINIMAX_SYSTEM` |

### 会话管理

```bash
# 会话存储位置
SESSION_STORE_DIR=/path/to/sessions

# 保留历史消息数（默认 50）
SESSION_MAX_HISTORY=100

# 清理过期会话（30 天）
python3 -c "from session_store import get_session_store; get_session_store().cleanup_old_sessions(30)"
```

### 飞书 OAuth（操作用户数据）

要使用用户的日历、任务、多维表格等，需要 OAuth 授权：

1. **配置应用**：飞书开放平台 → 应用开发 → 权限管理
   - 添加所需权限（如 `calendar:calendar`、`task:task`）

2. **实现 OAuth 流程**：
   ```python
   # 参考：https://open.feishu.cn/document/ukTMukTMukTM/ukjN1UjL04SO14iN
   # 1. 引导用户授权
   # 2. 获取 auth_code
   # 3. 换取 user_access_token
   # 4. 存储 token（数据库/Redis）
   # 5. 使用 token 调用用户数据 API
   ```

3. **临时方案**（测试用）：
   ```bash
   # .env 中设置
   FEISHU_USER_ACCESS_TOKEN=cli_xxx...
   ```

## 🐛 故障排查

### 技能未加载

```bash
# 检查 skills 目录
ls -la skills/

# 查看日志
grep "skill_router" logs/*.log
```

### 飞书 API 调用失败

1. 检查 `APP_ID` / `APP_SECRET` 是否正确
2. 检查应用权限是否已配置
3. 查看错误日志：
   ```python
   logging.basicConfig(level=logging.DEBUG)
   ```

### 会话未保存

```bash
# 检查存储目录权限
ls -la sessions/
chmod 755 sessions/
```

## 📊 与 OpenClaw 对比

| 特性 | OpenClaw | Echo Bot 增强版 |
|-----|---------|----------------|
| Skill 加载 | ✅ | ✅ |
| 意图路由 | ✅ | ✅ |
| 工具调用 | ✅ | ✅（通过 executor.py） |
| 会话管理 | ✅ | ✅ |
| 飞书 OAuth | ✅ | ⚠️ 需自行实现 |
| 技能安装 CLI | ✅ (clawhub) | ❌ 手动复制 |
| 多会话并发 | ✅ | ✅ |

## 📝 更新日志

### 2026-04-13
- ✅ 新增 `session_store.py`：会话持久化
- ✅ 新增 `skill_executor.py`：支持 Code 模式执行
- ✅ 新增 `feishu-calendar` 技能示例
- ✅ 修改 `main.py`：集成新模块
- ✅ 更新 `.env.example`：新增配置项

## 🔗 参考资料

- [飞书开放平台](https://open.feishu.cn/document)
- [OpenClaw 文档](https://docs.openclaw.ai)
- [Skill Router 实现](skill_router.py)
- [会话存储实现](session_store.py)
