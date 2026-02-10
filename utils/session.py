# -*- coding: utf-8 -*-
"""会话管理模块（线程安全，带容量限制）"""

import time
import threading
from typing import Optional


# 单池最大会话数（超过时清理过期 + LRU淘汰）
MAX_SESSIONS = 500


class SessionManager:
    """会话管理器（线程安全，带容量限制）"""
    
    def __init__(self, timeout: int = 300):
        self._lock = threading.RLock()
        self.user_sessions = {}    # 用户会话
        self.admin_sessions = {}   # 管理员会话
        self.timeout = timeout
    
    def get(self, qq: str, is_admin: bool = False) -> Optional[dict]:
        """获取会话"""
        with self._lock:
            sessions = self.admin_sessions if is_admin else self.user_sessions
            
            if qq in sessions:
                session = sessions[qq]
                if session.get("expire", 0) > time.time():
                    return session
                else:
                    del sessions[qq]
            
            return None
    
    def set(self, qq: str, state: str, context: dict = None, is_admin: bool = False):
        """设置会话"""
        with self._lock:
            sessions = self.admin_sessions if is_admin else self.user_sessions
            sessions[qq] = {
                "state": state,
                "context": context or {},
                "expire": time.time() + self.timeout
            }
            # 容量保护：超限时清理
            if len(sessions) > MAX_SESSIONS:
                self._evict(sessions)
    
    def clear(self, qq: str, is_admin: bool = False):
        """清除会话"""
        with self._lock:
            sessions = self.admin_sessions if is_admin else self.user_sessions
            if qq in sessions:
                del sessions[qq]
    
    def get_state(self, qq: str, is_admin: bool = False) -> Optional[str]:
        """获取会话状态"""
        session = self.get(qq, is_admin)
        return session.get("state") if session else None
    
    def get_context(self, qq: str, is_admin: bool = False) -> dict:
        """获取会话上下文"""
        session = self.get(qq, is_admin)
        return session.get("context", {}) if session else {}
    
    def _evict(self, sessions: dict):
        """淘汰过期会话；若仍超限则淘汰最早过期的"""
        now = time.time()
        # 1. 清理所有过期会话
        expired = [k for k, v in sessions.items() if v.get("expire", 0) <= now]
        for k in expired:
            del sessions[k]
        
        # 2. 若仍超限，按 expire 升序淘汰最旧的
        if len(sessions) > MAX_SESSIONS:
            sorted_keys = sorted(sessions, key=lambda k: sessions[k].get("expire", 0))
            to_remove = len(sessions) - MAX_SESSIONS
            for k in sorted_keys[:to_remove]:
                del sessions[k]
