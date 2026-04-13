#!/usr/bin/env python3
"""
技能执行器：加载并执行选中的技能
支持两种模式：
1. Prompt 模式：读取 SKILL.md 作为 system prompt（兼容现有）
2. Executor 模式：执行 executor.py 中的代码（新增）
"""
import importlib.util
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

from skill_router import discover_skills, _route_keywords, _route_llm, SkillEntry
from llm_client import chat_completion, PackyApiError

logger = logging.getLogger(__name__)

# 技能执行结果类型
ExecuteResult = Dict[str, Any]


def execute_skill(user_text: str, context: Dict[str, Any]) -> ExecuteResult:
    """
    执行选中的技能
    
    Args:
        user_text: 用户消息文本
        context: 会话上下文，包含：
            - chat_id: 会话 ID
            - user_id: 用户 ID
            - message_id: 消息 ID
            - history: 历史消息
            - vars: 会话变量
    
    Returns:
        执行结果字典，可能包含：
            - text: 文本回复
            - card: 消息卡片（Feishu 卡片格式）
            - file: 文件路径
            - error: 错误信息
    """
    # 发现可用技能
    entries = discover_skills()
    
    if not entries:
        logger.warning("No skills found")
        return {"text": "技能系统未初始化，请检查 skills 目录"}
    
    # 路由选择技能
    chosen_id = _route_skill(user_text, entries)
    logger.info(f"Selected skill: {chosen_id}")
    
    # 查找技能目录
    skill_entry = next((e for e in entries if e.skill_id == chosen_id), None)
    if not skill_entry:
        return {"error": f"Skill not found: {chosen_id}"}
    
    # 尝试执行技能
    return _execute_skill_entry(skill_entry, user_text, context)


def _route_skill(user_text: str, entries: list) -> str:
    """
    路由到最合适的技能
    
    策略：
    1. 关键词匹配优先（快速）
    2. LLM 智能路由（准确）
    """
    # 尝试关键词匹配
    mode = (os.getenv("SKILL_ROUTER") or "llm").strip().lower()
    
    if mode in ("0", "off", "false"):
        # 禁用路由，使用默认技能
        default = os.getenv("SKILL_DEFAULT") or entries[0].skill_id
        logger.info(f"Router disabled, using default: {default}")
        return default
    
    # 关键词优先
    kw_first = (os.getenv("SKILL_ROUTER_KEYWORDS") or "1").strip().lower() not in ("0", "off", "false")
    if kw_first:
        from skill_router import _route_keywords
        kw_id = _route_keywords(user_text, entries)
        if kw_id:
            logger.info(f"Keyword match: {kw_id}")
            return kw_id
    
    # LLM 路由
    from skill_router import _route_llm
    default_id = os.getenv("SKILL_DEFAULT") or entries[0].skill_id
    return _route_llm(user_text, entries, default_id)


def _execute_skill_entry(entry: SkillEntry, user_text: str, context: Dict[str, Any]) -> ExecuteResult:
    """
    执行单个技能
    
    优先级：
    1. executor.py（如果有）
    2. SKILL.md prompt 模式（回退）
    """
    skill_dir = entry.path.parent
    
    # 尝试加载 executor.py
    executor_path = skill_dir / "executor.py"
    if executor_path.exists():
        logger.info(f"Executing skill with code: {entry.skill_id}")
        return _execute_with_code(entry, executor_path, user_text, context)
    
    # 回退到 prompt 模式
    logger.info(f"Executing skill with prompt: {entry.skill_id}")
    return _execute_with_prompt(entry, user_text, context)


def _execute_with_code(entry: SkillEntry, executor_path: Path, user_text: str, context: Dict[str, Any]) -> ExecuteResult:
    """使用 executor.py 执行技能"""
    try:
        # 动态加载模块
        spec = importlib.util.spec_from_file_location("skill_executor", executor_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load spec for {executor_path}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 调用 execute 函数
        if not hasattr(module, "execute"):
            raise AttributeError(f"executor.py must define 'execute(user_text, context)' function")
        
        # 准备执行上下文
        exec_context = {
            "skill_id": entry.skill_id,
            "skill_dir": str(entry.path.parent),
            **context
        }
        
        result = module.execute(user_text, exec_context)
        
        # 确保返回字典
        if not isinstance(result, dict):
            result = {"text": str(result)}
        
        return result
        
    except Exception as e:
        logger.exception(f"Skill execution failed: {e}")
        return {
            "error": f"技能执行失败：{str(e)}",
            "skill_id": entry.skill_id
        }


def _execute_with_prompt(entry: SkillEntry, user_text: str, context: Dict[str, Any]) -> ExecuteResult:
    """使用 SKILL.md 作为 prompt 执行技能"""
    try:
        # 读取 skill 内容作为 system prompt
        system_prompt = entry.body
        
        # 如果没有 body，重新读取文件
        if not system_prompt:
            system_prompt = entry.path.read_text(encoding="utf-8")
        
        # 调用 LLM
        reply = chat_completion(user_text, system=system_prompt)
        
        return {"text": reply}
        
    except PackyApiError as e:
        logger.exception(f"LLM call failed: {e}")
        return {
            "error": f"模型调用失败：{str(e)}",
            "status_code": getattr(e, "status_code", None)
        }
    except Exception as e:
        logger.exception(f"Prompt execution failed: {e}")
        return {"error": f"技能执行失败：{str(e)}"}


# ============ 工具函数 ============

def create_feishu_client():
    """创建飞书客户端（辅助函数，供 executor.py 使用）"""
    import lark_oapi as lark
    
    app_id = os.getenv("APP_ID")
    app_secret = os.getenv("APP_SECRET")
    
    if not app_id or not app_secret:
        raise ValueError("APP_ID and APP_SECRET must be set")
    
    domain = os.getenv("LARK_DOMAIN", "https://open.feishu.cn")
    
    return (
        lark.Client.builder()
        .app_id(app_id)
        .app_secret(app_secret)
        .domain(domain)
        .build()
    )


def get_user_access_token(user_id: Optional[str] = None):
    """
    获取用户 access token（用于代表用户操作）
    
    注意：需要先完成 OAuth 授权流程
    """
    # TODO: 实现 OAuth token 存储和获取
    # 目前从环境变量读取（临时方案）
    token = os.getenv("FEISHU_USER_ACCESS_TOKEN")
    if not token:
        logger.warning("FEISHU_USER_ACCESS_TOKEN not set, using app token only")
    return token


# ============ 示例 Executor 模板 ============

EXAMPLE_EXECUTOR_TEMPLATE = '''#!/usr/bin/env python3
"""
{skill_name} 技能执行器

此文件定义技能的可执行代码，可以：
1. 调用飞书 API（发消息、查日历、创任务等）
2. 调用外部 API
3. 操作文件系统
4. 调用 LLM 生成回复
"""
import os
import logging
from typing import Dict, Any

# 从父目录导入工具
try:
    from skill_executor import create_feishu_client, get_user_access_token
    from llm_client import chat_completion
except ImportError:
    # 兼容直接运行
    import sys
    from pathlib import Path
    _parent = Path(__file__).parent.parent
    sys.path.insert(0, str(_parent))
    from skill_executor import create_feishu_client, get_user_access_token
    from llm_client import chat_completion

logger = logging.getLogger(__name__)


def execute(user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行技能
    
    Args:
        user_text: 用户消息
        context: 会话上下文 {
            "chat_id": "...",
            "user_id": "...",
            "message_id": "...",
            "history": [...],
            "vars": {...}
        }
    
    Returns:
        {
            "text": "回复文本",  # 必需
            "card": {...},       # 可选：飞书卡片
            "file": "路径",      # 可选：文件
            "error": "错误信息"   # 可选：错误
        }
    """
    # 示例 1：直接调用 LLM
    # system_prompt = open("SKILL.md").read()
    # reply = chat_completion(user_text, system=system_prompt)
    # return {{"text": reply}}
    
    # 示例 2：调用飞书 API
    # client = create_feishu_client()
    # resp = client.contact.v3.me.get()
    # return {{"text": f"当前用户：{{resp.data.user_id}}"}}
    
    # 示例 3：根据用户意图执行不同逻辑
    if "日历" in user_text or "日程" in user_text:
        return _handle_calendar(user_text, context)
    elif "任务" in user_text:
        return _handle_task(user_text, context)
    else:
        # 默认：调用 LLM
        system_prompt = open("SKILL.md").read()
        reply = chat_completion(user_text, system=system_prompt)
        return {{"text": reply}}


def _handle_calendar(user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """处理日历相关请求"""
    client = create_feishu_client()
    
    # TODO: 实现日历查询逻辑
    # 参考：https://open.feishu.cn/document/ukTMukTMukTM/uQjL04SO25jN14iN
    
    return {{"text": "日历功能开发中..."}}


def _handle_task(user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """处理任务相关请求"""
    client = create_feishu_client()
    
    # TODO: 实现任务管理逻辑
    # 参考：https://open.feishu.cn/document/ukTMukTMukTM/uAjLw4CM/ukTMukTMukTM/reference/task-v1/overview
    
    return {{"text": "任务功能开发中..."}}


if __name__ == "__main__":
    # 测试执行
    logging.basicConfig(level=logging.INFO)
    result = execute("测试消息", {"chat_id": "test", "user_id": "test"})
    print(result)
'''


def create_executor_template(skill_name: str, output_path: Path) -> None:
    """创建 executor 模板文件"""
    content = EXAMPLE_EXECUTOR_TEMPLATE.format(skill_name=skill_name)
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"Created executor template at {output_path}")
