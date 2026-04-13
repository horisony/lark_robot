#!/usr/bin/env python3
"""
会话存储模块：持久化用户对话上下文
支持：历史消息、变量存储、技能状态
"""
import json
import time
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class SessionData:
    """会话数据结构"""
    chat_id: str
    user_id: Optional[str] = None
    history: list = field(default_factory=list)  # [{"role": "user|assistant", "content": "...", "timestamp": 123}]
    vars: dict = field(default_factory=dict)  # 自定义变量
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    skill_state: dict = field(default_factory=dict)  # 技能特定状态
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "SessionData":
        return cls(**data)


class SessionStore:
    """会话存储器"""
    
    def __init__(self, storage_dir: Optional[str] = None):
        """
        初始化会话存储
        
        Args:
            storage_dir: 存储目录，默认 ./sessions
        """
        if storage_dir is None:
            import os
            storage_dir = os.environ.get("SESSION_STORE_DIR", "./sessions")
        
        self.dir = Path(storage_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"SessionStore initialized at {self.dir.absolute()}")
    
    def _get_path(self, chat_id: str) -> Path:
        """获取会话文件路径"""
        # 清理 chat_id 中的非法字符
        safe_id = chat_id.replace("/", "_").replace("\\", "_")
        return self.dir / f"{safe_id}.json"
    
    def get(self, chat_id: str) -> SessionData:
        """
        获取会话数据
        
        Args:
            chat_id: 会话 ID
            
        Returns:
            SessionData 对象
        """
        path = self._get_path(chat_id)
        
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                session = SessionData.from_dict(data)
                logger.debug(f"Loaded session for {chat_id}")
                return session
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Failed to load session {chat_id}: {e}")
        
        # 创建新会话
        session = SessionData(chat_id=chat_id)
        logger.info(f"Created new session for {chat_id}")
        return session
    
    def set(self, chat_id: str, session: SessionData) -> None:
        """
        保存会话数据
        
        Args:
            chat_id: 会话 ID
            session: SessionData 对象
        """
        path = self._get_path(chat_id)
        session.updated_at = time.time()
        
        # 原子写入：先写临时文件再重命名
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        tmp_path.rename(path)
        logger.debug(f"Saved session for {chat_id}")
    
    def delete(self, chat_id: str) -> bool:
        """
        删除会话
        
        Args:
            chat_id: 会话 ID
            
        Returns:
            是否删除成功
        """
        path = self._get_path(chat_id)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted session for {chat_id}")
            return True
        return False
    
    def add_message(self, chat_id: str, role: str, content: str, metadata: Optional[dict] = None) -> None:
        """
        添加消息到会话历史
        
        Args:
            chat_id: 会话 ID
            role: "user" 或 "assistant"
            content: 消息内容
            metadata: 额外元数据（可选）
        """
        session = self.get(chat_id)
        
        message = {
            "role": role,
            "content": content,
            "timestamp": time.time(),
            **(metadata or {})
        }
        
        session.history.append(message)
        
        # 限制历史记录数量（默认保留最近 50 条）
        import os
        max_history = int(os.environ.get("SESSION_MAX_HISTORY", "50"))
        if len(session.history) > max_history:
            session.history = session.history[-max_history:]
        
        self.set(chat_id, session)
    
    def get_recent_messages(self, chat_id: str, limit: int = 10) -> list:
        """
        获取最近的消息
        
        Args:
            chat_id: 会话 ID
            limit: 返回数量
            
        Returns:
            消息列表
        """
        session = self.get(chat_id)
        return session.history[-limit:]
    
    def clear_history(self, chat_id: str) -> None:
        """
        清空会话历史（保留变量）
        
        Args:
            chat_id: 会话 ID
        """
        session = self.get(chat_id)
        session.history = []
        self.set(chat_id, session)
    
    def set_var(self, chat_id: str, key: str, value) -> None:
        """设置会话变量"""
        session = self.get(chat_id)
        session.vars[key] = value
        self.set(chat_id, session)
    
    def get_var(self, chat_id: str, key: str, default=None):
        """获取会话变量"""
        session = self.get(chat_id)
        return session.vars.get(key, default)
    
    def list_sessions(self) -> list:
        """列出所有会话 ID"""
        return [p.stem for p in self.dir.glob("*.json")]
    
    def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """
        清理过期会话
        
        Args:
            max_age_days: 最大保留天数
            
        Returns:
            删除的会话数量
        """
        cutoff = time.time() - (max_age_days * 24 * 60 * 60)
        deleted = 0
        
        for path in self.dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                if data.get("updated_at", 0) < cutoff:
                    path.unlink()
                    deleted += 1
            except (json.JSONDecodeError, KeyError):
                path.unlink()
                deleted += 1
        
        logger.info(f"Cleaned up {deleted} old sessions")
        return deleted


# 全局单例
_default_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """获取全局会话存储实例"""
    global _default_store
    if _default_store is None:
        _default_store = SessionStore()
    return _default_store
