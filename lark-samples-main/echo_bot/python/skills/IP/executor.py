#!/usr/bin/env python3
"""
IP 自媒体技能执行器

专注于个人 IP 打造、自媒体运营、内容创作
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
    执行 IP 自媒体技能
    
    Args:
        user_text: 用户消息
        context: 会话上下文
    
    Returns:
        {"text": "..."} 自媒体运营建议或内容
    """
    # 查找 SKILL.md 文件
    skill_md = Path(__file__).parent / "BaoAI 战略专家_IP 自媒体_SKILL.md"
    
    if not skill_md.exists():
        # 尝试其他可能的文件名
        for md_file in Path(__file__).parent.glob("*SKILL.md"):
            skill_md = md_file
            break
    
    if not skill_md.exists():
        logger.error("SKILL.md not found")
        return {"error": "技能配置文件未找到"}
    
    system_prompt = skill_md.read_text(encoding="utf-8")
    
    try:
        reply = chat_completion(user_text, system=system_prompt)
        return {"text": reply}
    except Exception as e:
        logger.exception(f"LLM call failed: {e}")
        return {"error": f"内容创作失败：{str(e)}"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_text = "帮我写一个关于 AI 产品的抖音口播稿"
    result = execute(test_text, {"chat_id": "test"})
    print(result.get("text", result.get("error")))
