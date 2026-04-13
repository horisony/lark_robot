#!/usr/bin/env python3
"""
BaoAI-strategy 战略专家技能执行器

此技能专注于商业战略分析，使用麦肯锡框架 + 毛泽东战略语言
"""
import os
import logging
from typing import Dict, Any
from pathlib import Path

try:
    from llm_client import chat_completion
except ImportError:
    import sys
    _parent = Path(__file__).parent.parent
    sys.path.insert(0, str(_parent))
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
    skill_dir = Path(__file__).parent
    
    # 查找 SKILL.md 文件（兼容不同命名）
    skill_md = None
    for pattern in ["*SKILL.md", "*.md"]:
        matches = list(skill_dir.glob(pattern))
        if matches:
            skill_md = matches[0]
            break
    
    if not skill_md or not skill_md.exists():
        logger.error(f"SKILL.md not found in {skill_dir}")
        return {"error": "技能配置文件未找到"}
    
    logger.info(f"Using skill file: {skill_md.name}")
    system_prompt = skill_md.read_text(encoding="utf-8")
    
    try:
        reply = chat_completion(user_text, system=system_prompt, max_tokens=4096)
        return {"text": reply}
    except Exception as e:
        logger.exception(f"LLM call failed: {e}")
        return {"error": f"战略分析失败：{str(e)}"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_text = "我想做一个 AI 教育产品，帮我分析市场"
    result = execute(test_text, {"chat_id": "test"})
    print(result.get("text", result.get("error"))[:200])
