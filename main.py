# -*- coding: utf-8 -*-
"""
海梦酱码管理系统 v2.2.1
AstrBot 插件 - 智能管理注册码和抽奖兑换码

功能特性:
- 用户交互式菜单
- 管理员控制面板
- 抽奖系统（金/紫/蓝卡三档）
- 保底机制
- 活动限定卡池
- 公告系统
- 群成员验证（定期更新+临时会话双重验证）
"""

import asyncio
from pathlib import Path
from typing import Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .config import ConfigManager
from .data import DataManager
from .utils.session import SessionManager
from .utils.group_manager import GroupMemberManager, GroupVerifier
from .lottery.engine import LotteryEngine
from .handlers.user import UserHandler
from .handlers.admin import AdminHandler
from .utils.templates import Templates


@register("astrbot_plugin_haimeng_code", "久", "海梦酱码管理系统 - 智能抽奖发码", "2.2.1")
class HaimengCodePlugin(Star):
    """海梦酱码管理插件"""
    
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.context = context
        self.plugin_config = config
        
        # 插件目录
        self.plugin_dir = Path(__file__).parent
        
        # 初始化管理器
        self.config_mgr = ConfigManager(self.plugin_dir)
        self.data_mgr = DataManager(self.plugin_dir)
        self.session_mgr = SessionManager(self.config_mgr.config.get("session_timeout", 300))
        
        # 群成员管理器（通过监听群消息收集成员）
        self.group_mgr = GroupMemberManager(context, self.config_mgr, self.plugin_dir)
        self.group_verifier = GroupVerifier(self.config_mgr, self.group_mgr)
        
        # 初始化抽奖引擎
        self.lottery = LotteryEngine(self.data_mgr)
        
        # 初始化处理器（传入群验证器）
        self.user_handler = UserHandler(
            self.config_mgr, self.data_mgr, self.session_mgr, 
            self.lottery, self.group_verifier
        )
        self.admin_handler = AdminHandler(
            self.config_mgr, self.data_mgr, self.session_mgr, 
            self.lottery, self.group_mgr
        )
        
        # 定时任务
        self._reset_task = None
        self._task_started = False
        
        # 尝试启动定时任务
        self._try_start_scheduled_tasks()
        
        # 清理标记
        self._terminated = False
        
        logger.info("[海梦酱] 插件加载成功！v2.2.1")
    
    def _do_cleanup(self):
        """执行清理逻辑（去重保护，同步安全）"""
        if self._terminated:
            return
        self._terminated = True
        
        try:
            # 取消定时任务
            if hasattr(self, '_reset_task') and self._reset_task and not self._reset_task.done():
                self._reset_task.cancel()
            
            # flush缓存（同步调用，安全）
            if hasattr(self, 'group_mgr'):
                self.group_mgr.stop()
            if hasattr(self, 'data_mgr'):
                self.data_mgr.save()
            logger.info("[海梦酱] 插件卸载，数据已保存")
        except Exception as e:
            logger.debug(f"[海梦酱] 卸载时保存异常: {e}")
    
    def terminate(self):
        """AstrBot 卸载/禁用时调用（正式生命周期钩子）"""
        self._do_cleanup()
    
    def __del__(self):
        """备用清理（不保证被调用，但聊胜于无）"""
        self._do_cleanup()
    
    def _try_start_scheduled_tasks(self):
        """尝试启动定时任务"""
        try:
            loop = asyncio.get_running_loop()
            self._reset_task = loop.create_task(self._schedule_weekly_reset())
            self._task_started = True
            self.group_mgr.start()
            logger.info("[海梦酱] 定时任务已在初始化时启动")
        except RuntimeError:
            logger.info("[海梦酱] 定时任务将在首次消息时启动")
    
    async def _ensure_scheduled_tasks(self):
        """确保定时任务已启动"""
        if self._task_started:
            # 检查任务是否已结束（异常或被取消），自动重启
            if self._reset_task and self._reset_task.done():
                if not self._terminated:
                    if self._reset_task.cancelled():
                        logger.warning("[海梦酱] 定时任务被取消，正在重启...")
                    else:
                        exc = self._reset_task.exception()
                        if exc:
                            logger.warning(f"[海梦酱] 定时任务异常退出: {exc}，正在重启...")
                    self._reset_task = asyncio.create_task(self._schedule_weekly_reset())
            return
        
        try:
            # 启动周重置任务
            self._reset_task = asyncio.create_task(self._schedule_weekly_reset())
            
            # 启动群成员管理器
            self.group_mgr.start()
            
            self._task_started = True
            logger.info("[海梦酱] 定时任务已启动")
        except Exception as e:
            logger.error(f"[海梦酱] 启动定时任务失败: {e}")
    
    async def _schedule_weekly_reset(self):
        """每周重置定时任务（异常自愈）"""
        from datetime import datetime, timedelta
        
        while True:
            try:
                now = datetime.now()
                
                # 计算下一个周一00:00
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0 and now.hour >= 0:
                    days_until_monday = 7
                
                next_monday = now.replace(hour=0, minute=0, second=0, microsecond=0)
                next_monday += timedelta(days=days_until_monday)
                
                wait_seconds = (next_monday - now).total_seconds()
                logger.info(f"[海梦酱] 下次重置: {next_monday.strftime('%Y-%m-%d %H:%M')}, 等待 {wait_seconds:.0f}秒")
                
                await asyncio.sleep(wait_seconds)
                
                # 执行重置
                self.data_mgr.weekly_reset()
                logger.info("[海梦酱] 每周重置完成")
            except asyncio.CancelledError:
                logger.info("[海梦酱] 定时任务已取消")
                break
            except Exception as e:
                logger.error(f"[海梦酱] 定时任务执行异常: {e}，60秒后重试")
                await asyncio.sleep(60)
    
    # ==================== 消息处理 ====================
    
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def on_private_message(self, event: AstrMessageEvent):
        """处理私聊消息"""
        await self._ensure_scheduled_tasks()
        
        message = event.message_str.strip()
        qq = str(event.get_sender_id())
        
        # 管理员消息处理（拦截所有管理员私聊，阻止AI回复）
        if self.config_mgr.is_admin(qq):
            response = await self.admin_handler.handle(qq, message)
            if response:
                # 支持批量消息（如用户导出分批发送）
                if isinstance(response, list):
                    for msg in response:
                        yield event.plain_result(msg)
                        await asyncio.sleep(0.5)  # 避免QQ消息限流
                else:
                    yield event.plain_result(response)
            else:
                # 管理员发了不认识的消息，也要消费掉，防止AI抢回复
                yield event.plain_result("💡 发送 jiu 打开控制面板")
            return
        
        # 插件关闭时不响应普通用户
        if not self.config_mgr.is_enabled():
            return
        
        # 黑名单检查
        if self.data_mgr.is_blacklisted(qq):
            return
        
        # 用户消息处理
        response = await self.user_handler.handle(event, qq, message)
        if response:
            yield event.plain_result(Templates.USER_WARNING + response)
            return
        
        # 兜底：消费所有未处理的私聊消息，防止AI回复无关内容
        trigger = self.config_mgr.get_trigger_keyword()
        yield event.plain_result(f"💡 发送「{trigger}」开始使用")
    
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """
        处理群消息
        主要用于收集群成员（当用户在群里发言时自动记录）
        """
        try:
            await self._ensure_scheduled_tasks()
            
            qq = str(event.get_sender_id())
            
            # 尝试获取群ID
            group_id = None
            
            if hasattr(event, 'unified_msg_origin'):
                origin = event.unified_msg_origin
                if hasattr(origin, 'group_id') and origin.group_id:
                    group_id = str(origin.group_id)
            
            if not group_id and hasattr(event, 'message_obj'):
                msg_obj = event.message_obj
                if hasattr(msg_obj, 'group_id') and msg_obj.group_id:
                    group_id = str(msg_obj.group_id)
            
            # 记录群成员
            if group_id and qq:
                self.group_mgr.record_member(group_id, qq)
                
        except Exception as e:
            logger.debug(f"[海梦酱] 处理群消息异常: {e}")  # 记录日志而非静默
