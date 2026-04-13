#!/usr/bin/env python3
"""
BaoAI-strategy 战略专家技能执行器

此技能专注于商业战略分析，使用麦肯锡框架 + 毛泽东战略语言
"""
import os
import logging
from typing import Dict, Any
from pathlib import Path

# 导入工具函数
try:
    from skill_executor import create_feishu_client
    from llm_client import chat_completion
except ImportError:
    import sys
    _parent = Path(__file__).parent.parent
    sys.path.insert(0, str(_parent))
    from skill_executor import create_feishu_client
    from llm_client import chat_completion

logger = logging.getLogger(__name__)


def execute(user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行 BaoAI 战略分析技能
    
    Args:
        user_text: 用户消息
        context: 会话上下文
    
    Returns:
        {"text": "..."} 战略分析报告
    """
    # 读取 SKILL.md 作为 system prompt
    skill_md = Path(__file__).parent / "BaoAI 战略专家_战略_SKILL.md"
    
    if not skill_md.exists():
        logger.error(f"SKILL.md not found at {skill_md}")
        return {"error": "技能配置文件未找到"}
    
    system_prompt = skill_md.read_text(encoding="utf-8")
    
    # 调用 LLM 生成战略分析
    try:
        reply = chat_completion(
            user_text,
            system=system_prompt,
            max_tokens=4096  # 战略报告通常较长
        )
        return {"text": reply}
    except Exception as e:
        logger.exception(f"LLM call failed: {e}")
        return {"error": f"战略分析失败：{str(e)}"}


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    test_text = "我想做一个 AI 教育产品，帮我分析市场机会"
    result = execute(test_text, {"chat_id": "test", "user_id": "test"})
    print(result.get("text", result.get("error")))
