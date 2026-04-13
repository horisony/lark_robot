#!/usr/bin/env python3
"""
飞书日历技能执行器

功能：
1. 查询日程列表
2. 创建新日程
3. 查询忙闲状态
4. 删除/修改日程
"""
import os
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

try:
    from skill_executor import create_feishu_client, get_user_access_token
    from llm_client import chat_completion
except ImportError:
    import sys
    _parent = Path(__file__).parent.parent
    sys.path.insert(0, str(_parent))
    from skill_executor import create_feishu_client, get_user_access_token
    from llm_client import chat_completion

logger = logging.getLogger(__name__)


def execute(user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行日历技能
    
    根据用户意图调用不同的日历 API
    """
    # 分析用户意图
    intent = _analyze_intent(user_text)
    logger.info(f"Calendar intent: {intent}")
    
    try:
        client = create_feishu_client()
        
        if intent == "list":
            return _list_events(client, user_text, context)
        elif intent == "create":
            return _create_event(client, user_text, context)
        elif intent == "freebusy":
            return _check_freebusy(client, user_text, context)
        elif intent == "delete":
            return _delete_event(client, user_text, context)
        else:
            # 默认：用 LLM 理解并回复
            return _handle_with_llm(user_text, context)
            
    except Exception as e:
        logger.exception(f"Calendar API failed: {e}")
        return {"error": f"日历操作失败：{str(e)}"}


def _analyze_intent(text: str) -> str:
    """分析用户意图"""
    text_lower = text.lower()
    
    # 删除/取消
    if any(kw in text_lower for kw in ["删除", "取消", "remove", "delete", "cancel"]):
        return "delete"
    
    # 创建/安排/预约
    if any(kw in text_lower for kw in ["创建", "安排", "预约", "订", "create", "schedule", "book"]):
        return "create"
    
    # 忙闲/有空
    if any(kw in text_lower for kw in ["忙闲", "有空", "空闲", "busy", "free", "available"]):
        return "freebusy"
    
    # 查询/查看/列表
    if any(kw in text_lower for kw in ["查看", "查询", "列表", "日程", "calendar", "list", "show"]):
        return "list"
    
    return "unknown"


def _list_events(client, user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """查询日程列表"""
    try:
        # 获取主日历
        calendar_resp = client.calendar.v4.calendar.primary.get()
        if not calendar_resp.success():
            return {"error": f"获取日历失败：{calendar_resp.msg}"}
        
        calendar_id = calendar_resp.data.calendar_id
        
        # 确定时间范围
        now = datetime.now()
        if "今天" in user_text or "今日" in user_text:
            start = now.replace(hour=0, minute=0, second=0)
            end = now.replace(hour=23, minute=59, second=59)
        elif "明天" in user_text:
            tomorrow = now + timedelta(days=1)
            start = tomorrow.replace(hour=0, minute=0, second=0)
            end = tomorrow.replace(hour=23, minute=59, second=59)
        elif "本周" in user_text or "这周" in user_text:
            # 本周一
            monday = now - timedelta(days=now.weekday())
            start = monday.replace(hour=0, minute=0, second=0)
            # 本周日
            sunday = monday + timedelta(days=6)
            end = sunday.replace(hour=23, minute=59, second=59)
        else:
            # 默认：今天
            start = now.replace(hour=0, minute=0, second=0)
            end = now.replace(hour=23, minute=59, second=59)
        
        # 查询事件
        from lark_oapi.api.calendar.v4 import GetEventsRequest, GetEventsRequestBody
        
        request = (
            GetEventsRequest.builder()
            .calendar_id(calendar_id)
            .request_body(
                GetEventsRequestBody.builder()
                .start_time(int(start.timestamp() * 1000))
                .end_time(int(end.timestamp() * 1000))
                .build()
            )
            .build()
        )
        
        resp = client.calendar.v4.event.get(request)
        
        if not resp.success():
            return {"error": f"查询日程失败：{resp.msg}"}
        
        events = resp.data.events or []
        
        if not events:
            return {"text": f"📅 {start.strftime('%m月%d日')} 没有日程安排"}
        
        # 格式化输出
        lines = [f"📅 {start.strftime('%m月%d日')} 的日程："]
        for event in events:
            title = getattr(event, "subject", "无标题")
            start_time = getattr(event, "start_time", None)
            end_time = getattr(event, "end_time", None)
            
            if start_time:
                start_str = datetime.fromtimestamp(start_time / 1000).strftime("%H:%M")
            else:
                start_str = "??"
            
            if end_time:
                end_str = datetime.fromtimestamp(end_time / 1000).strftime("%H:%M")
            else:
                end_str = "??"
            
            lines.append(f"• {start_str}-{end_str} {title}")
        
        return {"text": "\n".join(lines)}
        
    except Exception as e:
        logger.exception(f"List events failed: {e}")
        return {"error": f"查询日程失败：{str(e)}"}


def _create_event(client, user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """创建新日程"""
    # 使用 LLM 提取日程信息
    system = """你是一个日程信息提取助手。从用户消息中提取以下信息，返回 JSON：
{
    "title": "日程标题",
    "start_time": "开始时间（ISO 格式，如 2024-01-01T14:00:00+08:00）",
    "end_time": "结束时间",
    "description": "描述（可选）",
    "location": "地点（可选）"
}

如果信息不完整，返回 {"missing": ["缺少的项目"]}
"""
    
    try:
        from llm_client import chat_completion
        import json
        
        extracted = chat_completion(user_text, system=system, max_tokens=256)
        
        # 尝试解析 JSON
        match = re.search(r'\{[^{}]*\}', extracted, re.DOTALL)
        if match:
            info = json.loads(match.group(0))
        else:
            return {"error": "无法解析日程信息，请提供更详细的描述"}
        
        if "missing" in info:
            missing = ", ".join(info["missing"])
            return {"text": f"请提供以下信息：{missing}"}
        
        # 获取日历
        calendar_resp = client.calendar.v4.calendar.primary.get()
        if not calendar_resp.success():
            return {"error": "获取日历失败"}
        
        calendar_id = calendar_resp.data.calendar_id
        
        # 创建事件
        from lark_oapi.api.calendar.v4 import CreateEventRequest, CreateEventRequestBody, CreateEventAttendee
        
        # 默认添加视频会议
        vchat = {
            "vc_type": "vc"
        }
        
        request = (
            CreateEventRequest.builder()
            .calendar_id(calendar_id)
            .request_body(
                CreateEventRequestBody.builder()
                .subject(info.get("title", "无标题"))
                .start_time(info.get("start_time"))
                .end_time(info.get("end_time"))
                .description(info.get("description", ""))
                .vchat(vchat)
                .build()
            )
            .build()
        )
        
        resp = client.calendar.v4.event.create(request)
        
        if not resp.success():
            return {"error": f"创建日程失败：{resp.msg}"}
        
        event_id = resp.data.event_id
        return {
            "text": f"✅ 日程已创建：{info.get('title')}\n📍 时间：{info.get('start_time', '?')}\n🔗 会议链接：已自动生成"
        }
        
    except Exception as e:
        logger.exception(f"Create event failed: {e}")
        return {"error": f"创建日程失败：{str(e)}"}


def _check_freebusy(client, user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """查询忙闲状态"""
    return {"text": "🔍 忙闲查询功能开发中...\n\n请提供具体时间，例如：'明天下午 2 点我有空吗？'"}


def _delete_event(client, user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """删除日程"""
    return {"text": "🗑️ 删除日程功能开发中...\n\n请提供要删除的日程标题或时间"}


def _handle_with_llm(user_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """使用 LLM 处理一般性问题"""
    skill_md = Path(__file__).parent / "SKILL.md"
    
    if skill_md.exists():
        system = skill_md.read_text(encoding="utf-8")
    else:
        system = "你是一个飞书日历助手，帮助用户管理日程。"
    
    try:
        reply = chat_completion(user_text, system=system)
        return {"text": reply}
    except Exception as e:
        return {"error": f"回复失败：{str(e)}"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 测试
    test_cases = [
        "查看今天的日程",
        "明天下午 2 点帮我创建一个会议，讨论产品规划",
        "我明天有空吗？",
    ]
    
    for test in test_cases:
        print(f"\n测试：{test}")
        result = execute(test, {"chat_id": "test"})
        print(result.get("text", result.get("error")))
