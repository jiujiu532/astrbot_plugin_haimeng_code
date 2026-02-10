# -*- coding: utf-8 -*-
"""群成员管理模块 - v2.1

由于机器人不是群管理员，无法直接调用获取群成员列表API。
采用以下方式收集群成员：
1. 监听群消息 - 记录在群里发过言的用户（带活跃时间TTL）
2. 临时会话来源 - 用户从群发起私聊时获取

验证时采用双重方式：
1. 优先：临时会话来源（最准确）
2. 备选：已收集的群成员缓存（带TTL）

v2.1 新增：
- 成员缓存带TTL，超过指定天数的成员记录会被清理
- 每次验证时会更新该成员的活跃时间
"""

import asyncio
from typing import Set, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path
import json
from astrbot.api import logger


# 默认缓存TTL（天）- 超过这个时间未活跃的成员会被清理
DEFAULT_CACHE_TTL_DAYS = 30


class GroupMemberManager:
    """群成员管理器 - 通过监听群消息收集成员（带TTL，线程安全）"""
    
    def __init__(self, context, config_manager, plugin_dir: Path = None):
        import threading
        
        self.context = context
        self.config = config_manager
        
        # 线程锁
        self._lock = threading.RLock()
        
        # 群成员缓存 {群号: {成员QQ: 最后活跃时间}}
        self._member_cache: Dict[str, Dict[str, str]] = {}
        
        # 持久化文件
        self._cache_file = plugin_dir / "group_members.json" if plugin_dir else None
        
        # TTL（可配置）
        self._cache_ttl_days = DEFAULT_CACHE_TTL_DAYS
        
        # 统计（必须先于 _load_cache 初始化）
        self._stats = {
            "total_collected": 0,
            "last_collect_time": None,
            "last_cleanup_time": None
        }
        
        # 加载已保存的缓存
        self._load_cache()
        
        # 启动时清理过期成员
        self._cleanup_expired_members()
    
    def _load_cache(self):
        """加载缓存（带备份自动恢复）"""
        if not self._cache_file:
            return
        
        backup_file = Path(str(self._cache_file) + '.bak')
        
        # 尝试加载主文件
        if self._cache_file.exists():
            try:
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._parse_cache_data(data)
                logger.info(f"[海梦酱] 加载群成员缓存: {self.get_member_count()} 人")
                return
            except json.JSONDecodeError as e:
                logger.error(f"[海梦酱] 群成员缓存格式错误: {e}，尝试从备份恢复...")
            except Exception as e:
                logger.error(f"[海梦酱] 加载群成员缓存失败: {e}，尝试从备份恢复...")
        
        # 尝试从备份恢复
        if backup_file.exists():
            try:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._parse_cache_data(data)
                
                # 恢复成功，修复主文件
                logger.warning("[海梦酱] ⚠️ 群成员缓存从备份恢复成功！")
                try:
                    import shutil
                    shutil.copy2(backup_file, self._cache_file)
                    logger.info("[海梦酱] ✅ 群成员缓存主文件已从备份恢复")
                except Exception as e:
                    logger.error(f"[海梦酱] 修复群成员缓存主文件失败: {e}")
                return
            except Exception as e:
                logger.error(f"[海梦酱] 群成员缓存备份也损坏: {e}")
    
    def _parse_cache_data(self, data: dict):
        """解析缓存数据"""
        # 兼容旧格式（无TTL的Set）
        for group_id, members in data.get("members", {}).items():
            if isinstance(members, list):
                # 旧格式：列表，转换为带时间戳的字典
                self._member_cache[group_id] = {
                    qq: datetime.now().isoformat() for qq in members
                }
            elif isinstance(members, dict):
                # 新格式：字典 {qq: last_active_time}
                self._member_cache[group_id] = members
        
        self._stats = data.get("stats", self._stats)
        raw_ttl = data.get("cache_ttl_days", DEFAULT_CACHE_TTL_DAYS)
        try:
            ttl = int(raw_ttl)
            if ttl <= 0:
                raise ValueError
            self._cache_ttl_days = ttl
        except (TypeError, ValueError):
            self._cache_ttl_days = DEFAULT_CACHE_TTL_DAYS
            logger.warning(f"[海梦酱] 群缓存 TTL 值异常: {raw_ttl!r}，回退默认 {DEFAULT_CACHE_TTL_DAYS} 天")
    
    def _save_cache(self):
        """保存缓存（原子写入）"""
        if not self._cache_file:
            return
        
        import tempfile
        import os
        
        try:
            data = {
                "members": self._member_cache,
                "stats": self._stats,
                "cache_ttl_days": self._cache_ttl_days
            }
            
            # 写入临时文件
            dir_path = self._cache_file.parent
            fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix='group_members_', suffix='.tmp')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                if os.name == 'nt':  # Windows 备份策略
                    backup_path = str(self._cache_file) + '.bak'
                    if self._cache_file.exists():
                        try:
                            if os.path.exists(backup_path):
                                os.remove(backup_path)
                            os.rename(self._cache_file, backup_path)
                        except OSError as e:
                            logger.warning(f"[海梦酱] 群成员缓存备份失败: {e}")
                    
                    os.rename(temp_path, self._cache_file)
                    
                    # 注意：不删除备份文件，_load_cache() 依赖 .bak 做异常恢复
                else:  # Unix
                    os.replace(temp_path, self._cache_file)
                    
            except Exception as e:
                logger.error(f"[海梦酱] 保存群成员缓存失败: {e}")
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except OSError:
                    pass
        except Exception as e:
            logger.error(f"[海梦酱] 保存群成员缓存失败: {e}")
    
    def _cleanup_expired_members(self):
        """清理过期成员"""
        now = datetime.now()
        cutoff = now - timedelta(days=self._cache_ttl_days)
        cleaned = 0
        
        for group_id in list(self._member_cache.keys()):
            members = self._member_cache[group_id]
            for qq in list(members.keys()):
                try:
                    last_active = datetime.fromisoformat(members[qq])
                    if last_active < cutoff:
                        del members[qq]
                        cleaned += 1
                except (ValueError, KeyError):
                    # 无效时间格式 = 脏数据，清理掉
                    del members[qq]
                    cleaned += 1
            
            # 如果群成员为空，删除该群
            if not members:
                del self._member_cache[group_id]
        
        if cleaned > 0:
            self._stats["last_cleanup_time"] = now.isoformat()
            self._save_cache()
            logger.info(f"[海梦酱] 清理过期群成员: {cleaned} 人")
    
    def start(self):
        """启动（同步）"""
        logger.info(f"[海梦酱] 群成员管理器已启动（监听模式，TTL={self._cache_ttl_days}天），已缓存 {self.get_member_count()} 人")
    
    def stop(self):
        """停止并flush缓存（同步，可安全在__del__中调用）"""
        with self._lock:
            self._save_cache()
        logger.info("[海梦酱] 群成员缓存已保存")
    
    def record_member(self, group_id: str, qq: str):
        """
        记录群成员（带时间戳，线程安全）
        
        Args:
            group_id: 群号
            qq: 用户QQ号
        """
        target_groups = self.config.get_target_groups()
        
        # 只记录目标群的成员
        if target_groups and group_id not in target_groups:
            return
        
        with self._lock:
            if group_id not in self._member_cache:
                self._member_cache[group_id] = {}
            
            now = datetime.now().isoformat()
            is_new = qq not in self._member_cache[group_id]
            
            # 更新活跃时间
            self._member_cache[group_id][qq] = now
            
            if is_new:
                self._stats["total_collected"] += 1
                self._stats["last_collect_time"] = now
                
                # 每收集50个新成员保存一次
                if self._stats["total_collected"] % 50 == 0:
                    self._save_cache()
            else:
                # 活跃更新也定期落盘，防止重启丢失活跃时间
                self._active_update_count = getattr(self, '_active_update_count', 0) + 1
                if self._active_update_count % 200 == 0:
                    self._save_cache()
    
    def record_member_join(self, group_id: str, qq: str):
        """记录新成员入群"""
        self.record_member(group_id, qq)
        logger.info(f"[海梦酱] 新成员入群: 群{group_id} QQ{qq}")
    
    def record_member_leave(self, group_id: str, qq: str):
        """记录成员退群（线程安全）"""
        with self._lock:
            if group_id in self._member_cache:
                if qq in self._member_cache[group_id]:
                    del self._member_cache[group_id][qq]
                    self._save_cache()
                    logger.info(f"[海梦酱] 成员退群: 群{group_id} QQ{qq}")
    
    def is_group_member(self, qq: str, group_id: Optional[str] = None) -> bool:
        """
        检查用户是否是群成员（从缓存检查，带TTL，线程安全）
        
        安全策略：
        - 时间戳解析失败视为无效（防止TTL绕过）
        - 检查时按 target_groups 过滤
        
        Args:
            qq: 用户QQ号
            group_id: 指定群号，为None时检查目标群
            
        Returns:
            是否是群成员（且未过期）
        """
        now = datetime.now()
        cutoff = now - timedelta(days=self._cache_ttl_days)
        target_groups = self.config.get_target_groups()
        
        with self._lock:
            if group_id:
                # 检查指定群是否在目标群内
                if target_groups and group_id not in target_groups:
                    return False
                
                members = self._member_cache.get(group_id, {})
                if qq in members:
                    try:
                        last_active = datetime.fromisoformat(members[qq])
                        return last_active >= cutoff
                    except ValueError:
                        # 时间戳解析失败，视为无效（安全策略）
                        logger.debug(f"[海梦酱] 成员 {qq} 时间戳格式错误，视为无效")
                        return False
                return False
            else:
                # 检查所有目标群
                groups_to_check = target_groups if target_groups else self._member_cache.keys()
                
                for gid in groups_to_check:
                    members = self._member_cache.get(gid, {})
                    if qq in members:
                        try:
                            last_active = datetime.fromisoformat(members[qq])
                            if last_active >= cutoff:
                                return True
                        except ValueError:
                            # 时间戳解析失败，继续检查其他群
                            continue
                return False
    
    def get_member_count(self, group_id: Optional[str] = None) -> int:
        """获取成员数量（线程安全）"""
        with self._lock:
            if group_id:
                return len(self._member_cache.get(group_id, {}))
            else:
                # 去重统计
                all_members = set()
                for members in self._member_cache.values():
                    all_members.update(members.keys())
                return len(all_members)
    
    def get_cache_status(self) -> str:
        """获取缓存状态信息（线程安全）"""
        with self._lock:
            if not self._member_cache:
                return f"群成员缓存: 暂无数据\n💡 用户在群里发言后会自动记录\n⏰ TTL: {self._cache_ttl_days} 天"
            
            lines = [f"群成员缓存状态 (TTL={self._cache_ttl_days}天):"]
            for group_id, members in self._member_cache.items():
                lines.append(f"  群{group_id}: {len(members)} 人")
            
            lines.append(f"\n累计收集: {self._stats.get('total_collected', 0)} 次")
            last_time = self._stats.get("last_collect_time")
            if last_time:
                lines.append(f"最后更新: {last_time[:16]}")
            
            last_cleanup = self._stats.get("last_cleanup_time")
            if last_cleanup:
                lines.append(f"最后清理: {last_cleanup[:16]}")
            
            return "\n".join(lines)
    
    def force_update(self, group_id: Optional[str] = None):
        """强制更新（保存缓存并清理过期）"""
        with self._lock:
            self._cleanup_expired_members()
            self._save_cache()
        return "✅ 缓存已保存并清理过期成员"


class GroupVerifier:
    """群验证器 - 综合多种方式验证用户"""
    
    def __init__(self, config_manager, member_manager: GroupMemberManager):
        self.config = config_manager
        self.member_manager = member_manager
    
    def verify_user(self, qq: str, event=None) -> tuple:
        """
        验证用户是否来自指定群
        
        验证方式（按优先级）：
        1. 临时会话来源 - 最准确，同时更新成员活跃时间
        2. 群成员缓存 - 备选，带TTL检查
        
        Args:
            qq: 用户QQ号
            event: 消息事件，用于获取临时会话来源
            
        Returns:
            (通过, 验证方式, 群号)
        """
        # 跳过验证
        if self.config.get("skip_group_check", False):
            return True, "跳过验证", None
        
        target_groups = self.config.get_target_groups()
        if not target_groups:
            return True, "无目标群", None
        
        # 方式1: 尝试从事件获取临时会话来源（最准确）
        if event:
            source_group = self._get_temp_session_source(event)
            if source_group:
                if source_group in target_groups:
                    # 记录该用户（更新活跃时间）
                    self.member_manager.record_member(source_group, qq)
                    return True, "临时会话", source_group
                else:
                    return False, "非目标群", source_group
        
        # 方式2: 从缓存检查（带TTL）
        if self.member_manager.is_group_member(qq):
            return True, "成员缓存", None
        
        # 验证失败
        return False, "验证失败", None
    
    def _get_temp_session_source(self, event) -> Optional[str]:
        """
        获取临时会话来源群号
        尝试多种方式获取
        """
        try:
            # 方式1: unified_msg_origin
            if hasattr(event, 'unified_msg_origin'):
                origin = event.unified_msg_origin
                if hasattr(origin, 'group_id') and origin.group_id:
                    return str(origin.group_id)
            
            # 方式2: message_obj
            if hasattr(event, 'message_obj'):
                msg_obj = event.message_obj
                
                # 检查 group_id
                if hasattr(msg_obj, 'group_id') and msg_obj.group_id:
                    return str(msg_obj.group_id)
                
                # 检查 temp_source
                if hasattr(msg_obj, 'temp_source') and msg_obj.temp_source:
                    return str(msg_obj.temp_source)
                
                # 检查 sender
                if hasattr(msg_obj, 'sender'):
                    sender = msg_obj.sender
                    if hasattr(sender, 'group_id') and sender.group_id:
                        return str(sender.group_id)
            
            # 方式3: raw_message
            if hasattr(event, 'raw_message') and isinstance(event.raw_message, dict):
                raw = event.raw_message
                if 'group_id' in raw:
                    return str(raw['group_id'])
                if 'temp_source' in raw:
                    return str(raw['temp_source'])
                if 'sender' in raw and isinstance(raw['sender'], dict):
                    if 'group_id' in raw['sender']:
                        return str(raw['sender']['group_id'])
            
            # 方式4: 检查 sub_type (群临时会话)
            if hasattr(event, 'message_obj'):
                msg_obj = event.message_obj
                if hasattr(msg_obj, 'sub_type') and msg_obj.sub_type == 'group':
                    if hasattr(msg_obj, 'group_id'):
                        return str(msg_obj.group_id)
                        
        except Exception as e:
            logger.debug(f"[海梦酱] 获取临时会话来源失败: {e}")
        
        return None
