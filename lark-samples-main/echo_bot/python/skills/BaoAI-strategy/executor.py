#!/usr/bin/env python3
"""
BaoAI-strategy 战略专家技能执行器

支持：
1. 标准 Markdown 战略报告
2. HTML 可视化输出（9:16 多页长图）
3. 文件生成和发送
"""
import os
import logging
import re
from typing import Dict, Any, Optional
from pathlib import Path

try:
    from llm_client import chat_completion
except ImportError:
    import sys
    _parent = Path(__file__).parent.parent
    sys.path.insert(0, str(_parent))
    from llm_client import chat_completion

logger = logging.getLogger(__name__)

# HTML 模板（简化版 9:16 配色）
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
 <meta charset="UTF-8">
 <meta name="viewport" content="width=device-width, initial-scale=1.0">
 <title>BaoAI 战略报告</title>
 <style>
 * { margin: 0; padding: 0; box-sizing: border-box; }
 body {
 font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
 background-color: #FDF9F3;
 color: #4E342E;
 line-height: 1.6;
 }
 .container { max-width: 540px; margin: 0 auto; }
 .page {
 width: 100%;
 min-height: 960px;
 padding: 40px 32px;
 background-color: #FDF9F3;
 border-bottom: 1px solid #E6D5C3;
 position: relative;
 }
 .page-header {
 display: flex;
 justify-content: space-between;
 align-items: center;
 margin-bottom: 32px;
 padding-bottom: 16px;
 border-bottom: 2px solid #EE8136;
 }
 .brand { font-size: 14px; font-weight: 600; color: #EE8136; letter-spacing: 1px; }
 .page-number { font-size: 12px; color: #7D5A50; }
 .content { margin-bottom: 32px; }
 h1 { font-size: 28px; font-weight: 700; margin-bottom: 24px; color: #4E342E; border-left: 4px solid #EE8136; padding-left: 16px; }
 h2 { font-size: 22px; font-weight: 600; margin-bottom: 20px; color: #4E342E; }
 h3 { font-size: 18px; font-weight: 600; margin-bottom: 16px; color: #7D5A50; }
 .quote { background-color: #FFF3E0; border-left: 3px solid #EE8136; padding: 16px 20px; margin: 20px 0; font-style: italic; color: #7D5A50; font-size: 14px; }
 .quote-source { text-align: right; margin-top: 8px; font-size: 12px; color: #7D5A50; }
 table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; }
 th { background-color: #F5EBE0; padding: 12px 8px; text-align: left; font-weight: 600; color: #4E342E; border: 1px solid #D7CCC8; }
 td { padding: 12px 8px; border: 1px solid #D7CCC8; color: #4E342E; }
 tr:nth-child(even) { background-color: #FAF5F0; }
 .highlight { background-color: #FFF3E0; padding: 20px; border-radius: 8px; margin: 20px 0; }
 .highlight-title { font-weight: 600; color: #EE8136; margin-bottom: 12px; font-size: 16px; }
 .action-list { list-style: none; margin: 20px 0; }
 .action-list li { padding: 12px 16px; margin-bottom: 12px; background-color: #FFF3E0; border-left: 3px solid #EE8136; border-radius: 0 8px 8px 0; font-size: 14px; }
 .page-footer {
 position: absolute;
 bottom: 32px;
 left: 32px;
 right: 32px;
 text-align: center;
 font-size: 11px;
 color: #7D5A50;
 padding-top: 16px;
 border-top: 1px solid #E6D5C3;
 }
 .confidential { letter-spacing: 2px; }
 </style>
</head>
<body>
 <div class="container">
 <div class="page">
 <div class="page-header">
 <div class="brand">◆ BaoAI 战略部</div>
 <div class="page-number">01 / 01</div>
 </div>
 <div class="content">
{{content}}
 </div>
 <div class="page-footer">
 <div class="confidential">机密 · 仅供内部传阅 · BaoAI 战略部</div>
 </div>
 </div>
 </div>
</body>
</html>
'''


def execute(user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行 BaoAI 战略分析技能
    
    Args:
        user_text: 用户消息
        context: 会话上下文 {chat_id, user_id, history, vars}
    
    Returns:
        {"text": "..."} 或 {"text": "...", "file": "path/to/file.html"}
    """
    skill_dir = Path(__file__).parent
    
    # 查找 SKILL.md 文件
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
    
    # 检测是否需要 HTML 输出
    needs_html = any(kw in user_text.lower() for kw in ['html', '可视化', '长图', '分享版', '精美排版', '发给团队', '9:16'])
    
    try:
        # 如果需要 HTML，在 system prompt 中添加指示
        if needs_html:
            html_instruction = "\n\n【HTML 输出要求】用户要求可视化输出，请在报告结尾生成完整的 HTML 代码（9:16 手机屏幕比例，暖棕色配色），放在 ```html 代码块中。"
            system_prompt += html_instruction
        
        reply = chat_completion(user_text, system=system_prompt, max_tokens=8192)
        
        # 如果回复中包含 HTML 代码块，提取并保存为文件
        html_file = None
        if needs_html:
            html_match = re.search(r'```html\s*(.*?)\s*```', reply, re.DOTALL)
            if html_match:
                html_content = html_match.group(1)
                html_file = save_html_file(html_content, context.get('chat_id', 'unknown'))
                logger.info(f"HTML file saved: {html_file}")
        
        result = {"text": reply}
        if html_file:
            result["file"] = html_file
        
        return result
        
    except Exception as e:
        logger.exception(f"LLM call failed: {e}")
        return {"error": f"战略分析失败：{str(e)}"}


def save_html_file(html_content: str, chat_id: str) -> str:
    """保存 HTML 文件到 sessions 目录"""
    import time
    timestamp = int(time.time())
    safe_chat_id = chat_id.replace('/', '_').replace('\\', '_')
    filename = f"strategy_{safe_chat_id}_{timestamp}.html"
    
    # 保存到 sessions 目录
    sessions_dir = Path('/app/sessions')
    sessions_dir.mkdir(exist_ok=True)
    file_path = sessions_dir / filename
    
    file_path.write_text(html_content, encoding='utf-8')
    logger.info(f"Saved HTML to {file_path}")
    
    return str(file_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 测试 1：标准战略分析
    test1 = "我想做一个 AI 教育产品，帮我做战略分析"
    print(f"\n测试 1: {test1}")
    result1 = execute(test1, {"chat_id": "test"})
    print(f"结果：{result1.get('error', 'OK')}")
    
    # 测试 2：HTML 输出
    test2 = "帮我做战略分析，生成 HTML 可视化版本发给团队"
    print(f"\n测试 2: {test2}")
    result2 = execute(test2, {"chat_id": "test"})
    print(f"结果：{result2.get('error', 'OK')}, 文件：{result2.get('file')}")
