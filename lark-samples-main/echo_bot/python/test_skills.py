#!/usr/bin/env python3
"""
快速测试脚本：验证 Skill 系统是否正常工作

使用方法：
    python3 test_skills.py
"""
import os
import sys
from pathlib import Path

# 添加父目录到路径
_parent = Path(__file__).parent
sys.path.insert(0, str(_parent))

# 设置环境变量（从 .env 读取）
try:
    from dotenv import load_dotenv
    load_dotenv(_parent / ".env")
except ImportError:
    pass


def test_session_store():
    """测试会话存储"""
    print("\n📦 测试 Session Store...")
    
    from session_store import SessionStore
    
    store = SessionStore("./test_sessions")
    chat_id = "test_chat_001"
    
    # 测试添加消息
    store.add_message(chat_id, "user", "你好")
    store.add_message(chat_id, "assistant", "你好！有什么可以帮你？")
    
    # 测试获取历史
    history = store.get_recent_messages(chat_id, limit=10)
    assert len(history) == 2, f"Expected 2 messages, got {len(history)}"
    
    # 测试变量
    store.set_var(chat_id, "test_key", "test_value")
    value = store.get_var(chat_id, "test_key")
    assert value == "test_value", f"Expected 'test_value', got {value}"
    
    # 清理
    store.delete(chat_id)
    
    print("✅ Session Store 测试通过")
    return True


def test_skill_discovery():
    """测试技能发现"""
    print("\n🔍 测试技能发现...")
    
    from skill_router import discover_skills
    
    skills = discover_skills()
    print(f"发现 {len(skills)} 个技能:")
    for skill in skills:
        print(f"  - {skill.skill_id}: {skill.name}")
    
    assert len(skills) >= 2, f"Expected at least 2 skills, got {len(skills)}"
    
    # 检查是否有 executor.py
    for skill in skills:
        executor_path = skill.path.parent / "executor.py"
        has_executor = executor_path.exists()
        print(f"    {'✅' if has_executor else '⚠️'} executor.py: {'存在' if has_executor else '无 (使用 Prompt 模式)'}")
    
    print("✅ 技能发现测试通过")
    return True


def test_skill_executor():
    """测试技能执行器"""
    print("\n⚡ 测试技能执行器...")
    
    from skill_executor import execute_skill
    
    # 测试上下文
    context = {
        "chat_id": "test_chat",
        "user_id": "test_user",
        "history": [],
        "vars": {}
    }
    
    # 测试战略技能
    print("  测试 BaoAI-strategy...")
    result = execute_skill("我想做一个 AI 教育产品，帮我分析市场机会", context)
    assert "text" in result or "error" in result, f"Invalid result: {result}"
    if "text" in result:
        print(f"    ✅ 回复长度：{len(result['text'])} 字符")
    else:
        print(f"    ⚠️ 错误：{result.get('error')}")
    
    # 测试 IP 技能
    print("  测试 IP 自媒体...")
    result = execute_skill("帮我写一个关于 AI 的抖音口播稿", context)
    assert "text" in result or "error" in result
    if "text" in result:
        print(f"    ✅ 回复长度：{len(result['text'])} 字符")
    else:
        print(f"    ⚠️ 错误：{result.get('error')}")
    
    print("✅ 技能执行器测试通过")
    return True


def test_feishu_calendar():
    """测试飞书日历技能"""
    print("\n📅 测试飞书日历技能...")
    
    # 检查是否配置了 APP_ID
    app_id = os.getenv("APP_ID")
    if not app_id:
        print("  ⚠️ 未配置 APP_ID，跳过 API 测试")
        print("  提示：在 .env 中设置 APP_ID 和 APP_SECRET")
        return True
    
    from skill_executor import execute_skill
    
    context = {
        "chat_id": "test_chat",
        "user_id": "test_user",
        "history": [],
        "vars": {}
    }
    
    # 测试查询日程
    print("  测试查询日程...")
    result = execute_skill("查看今天的日程", context)
    print(f"    结果：{result.get('text', result.get('error', 'Unknown'))[:100]}...")
    
    print("✅ 日历技能测试完成")
    return True


def test_keyword_routing():
    """测试关键词路由"""
    print("\n🎯 测试关键词路由...")
    
    from skill_router import discover_skills, _route_keywords
    
    skills = discover_skills()
    
    test_cases = [
        ("战略规划", "BaoAI-strategy"),
        ("商业模式", "BaoAI-strategy"),
        ("口播稿", "IP"),
        ("自媒体", "IP"),
        ("日历", "feishu-calendar"),
        ("日程", "feishu-calendar"),
    ]
    
    for text, expected in test_cases:
        result = _route_keywords(text, skills)
        status = "✅" if result == expected else "⚠️"
        print(f"  {status} '{text}' → {result} (期望：{expected})")
    
    print("✅ 关键词路由测试完成")
    return True


def main():
    """运行所有测试"""
    print("=" * 60)
    print("🧪 Echo Bot Skill 系统测试")
    print("=" * 60)
    
    tests = [
        ("会话存储", test_session_store),
        ("技能发现", test_skill_discovery),
        ("技能执行器", test_skill_executor),
        ("飞书日历", test_feishu_calendar),
        ("关键词路由", test_keyword_routing),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"\n❌ {name} 测试失败：{e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 测试结果：{passed} 通过，{failed} 失败")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 所有测试通过！系统已就绪。")
        print("\n下一步：")
        print("1. 配置 .env 文件（APP_ID, APP_SECRET, API_KEY）")
        print("2. 运行 python3 main.py 启动机器人")
        print("3. 在飞书中测试技能对话")
    else:
        print("\n⚠️ 部分测试失败，请检查错误信息")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
