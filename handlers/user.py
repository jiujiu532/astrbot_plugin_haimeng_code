# -*- coding: utf-8 -*-
"""用户消息处理模块"""

from typing import Optional
from datetime import datetime
from astrbot.api.event import AstrMessageEvent

from ..config import ConfigManager
from ..data import DataManager
from ..utils.session import SessionManager
from ..utils.templates import Templates
from ..lottery.engine import TIER_INFO


class UserHandler:
    """用户消息处理器"""
    
    def __init__(self, config: ConfigManager, data: DataManager, session: SessionManager, 
                 lottery_engine, group_verifier=None):
        self.config = config
        self.data = data
        self.session = session
        self.lottery = lottery_engine
        self.group_verifier = group_verifier  # 群验证器
    
    async def handle(self, event: AstrMessageEvent, qq: str, message: str) -> Optional[str]:
        """处理用户消息"""
        trigger_keyword = self.config.get_trigger_keyword()
        
        # 检查触发词
        if message == trigger_keyword:
            self.session.set(qq, "menu")
            return Templates.USER_MENU
        
        # 检查会话状态
        session = self.session.get(qq)
        if not session:
            return None
        
        state = session.get("state")
        
        # 取消操作
        if message.upper() == "Q":
            self.session.clear(qq)
            return Templates.CANCEL_OK
        
        # 分发处理
        if state == "menu":
            return await self._handle_menu_choice(event, qq, message)
        elif state == "lottery_confirm":
            return await self._handle_lottery_confirm(event, qq, message)
        
        return None
    
    async def _handle_menu_choice(self, event: AstrMessageEvent, qq: str, choice: str) -> str:
        """处理菜单选择"""
        self.session.clear(qq)
        
        if choice == "1":
            return await self._get_registration_code(event, qq)
        elif choice == "2":
            return await self._start_lottery(event, qq)
        elif choice == "3":
            return self.lottery.get_pool_info()
        elif choice == "4":
            return self._get_my_info(qq)
        elif choice == "5":
            return self._get_announcement()
        elif choice == "6":
            return Templates.USER_HELP
        else:
            self.session.set(qq, "menu")
            return Templates.ERROR_INVALID_CHOICE + "\n\n" + Templates.USER_MENU
    
    async def _get_registration_code(self, event: AstrMessageEvent, qq: str) -> str:
        """获取注册码"""
        # 检查黑名单
        if self.data.is_blacklisted(qq):
            return Templates.ERROR_BLACKLISTED
        
        # 检查群成员
        if not self._check_group(event, qq):
            return Templates.ERROR_NOT_IN_GROUP
        
        # 原子事务：判资格 + 扣库存 + 记账
        success, status, code = self.data.try_register_user(qq, self.config.is_test_mode())
        
        if not success:
            if status == "already_registered":
                info = self.data.get_user_info(qq)
                reg_code = info.get("reg_code", "未知") if info else "未知"
                reg_time = info.get("reg_time", "未知")[:10] if info and info.get("reg_time") else "未知"
                return f"""🎉 你已经是海梦家族成员啦！

📋 你的注册码: {reg_code}
📅 注册时间: {reg_time}

如需帮助请联系久~"""
            elif status == "no_stock":
                return "⚠️ 注册码暂时缺货了\n\n请联系久补充~"
        
        # 记录日志（脱敏）
        self.data.log_action("注册", qq, "获得注册码")
        
        return f"""🎉 欢迎加入海梦家族！

你的专属注册码：
📋 {code}

请妥善保管，每人仅限一次哦~"""
    
    async def _start_lottery(self, event: AstrMessageEvent, qq: str) -> str:
        """开始抽奖"""
        # 检查黑名单
        if self.data.is_blacklisted(qq):
            return Templates.ERROR_BLACKLISTED
        
        # 检查群成员
        if not self._check_group(event, qq):
            return Templates.ERROR_NOT_IN_GROUP
        
        # 未注册
        if not self.data.is_registered(qq):
            return Templates.ERROR_NOT_REGISTERED
        
        # 检查发放时间
        if not self.config.is_in_exchange_time():
            return self._get_time_info()
        
        # 检查是否可以抽奖
        can_draw, reason = self.data.can_draw_lottery(qq)
        if not can_draw:
            return f"❌ {reason}"
        
        # 显示确认
        pool_info = self.lottery.get_pool_info()
        self.session.set(qq, "lottery_confirm")
        return Templates.LOTTERY_CONFIRM.format(pool_info=pool_info)
    
    async def _handle_lottery_confirm(self, event: AstrMessageEvent, qq: str, message: str) -> str:
        """处理抽奖确认"""
        self.session.clear(qq)
        
        if message.upper() != "GO":
            return "❌ 已取消抽奖"
        
        # 执行抽奖
        tier, code, msg = self.lottery.draw(qq, self.config.is_test_mode())
        
        if not tier:
            return f"❌ {msg}"
        
        # 记录日志（不含明文码）
        tier_name = TIER_INFO.get(tier, {}).get("name", tier)
        self.data.log_action("抽奖", qq, f"抽中{tier_name}")
        
        return self.lottery.get_draw_result_message(tier, code, qq)
    
    def _get_my_info(self, qq: str) -> str:
        """获取个人信息"""
        if not self.data.is_registered(qq):
            return """👤 【我的信息】

📋 注册状态: 未注册 ❌

回复 1 立即加入海梦家族~"""
        
        info = self.data.get_user_info(qq)
        reg_code = info.get("reg_code", "未知") if info else "未知"
        reg_time = info.get("reg_time", "未知")
        imported = "是" if info and info.get("imported") else "否"
        
        # 抽奖数据
        lottery_data = self.data.get_user_lottery_data(qq)
        total_draws = lottery_data.get("total_draws", 0)
        week_draws = lottery_data.get("week_draws", 0)
        pity_count = lottery_data.get("pity_count", 0)
        config = self.data.get_lottery_config()
        weekly_limit = config.get("weekly_limit", 1)
        pity_threshold = config.get("pity_threshold", 10)
        
        msg = f"""👤 【我的信息】

📋 注册状态: 已注册 ✅
📝 注册码: {reg_code}
📅 注册时间: {reg_time[:10] if len(str(reg_time)) > 10 else reg_time}
📦 导入用户: {imported}

🎰 抽奖数据:
├ 累计抽奖: {total_draws} 次
├ 本周已抽: {week_draws}/{weekly_limit} 次
└ 保底进度: {pity_count}/{pity_threshold}"""
        
        return msg
    
    def _get_announcement(self) -> str:
        """获取公告"""
        announcement = self.data.get_announcement()
        content = announcement.get("content", "")
        time_str = announcement.get("time", "")
        
        if not content:
            return """📢 【最新公告】

暂无公告~

关注久获取最新消息！"""
        
        return f"""📢 【最新公告】

{content}

━━━━━━━━━━━━━━━━━
发布时间: {time_str[:16] if len(time_str) > 16 else time_str}"""
    
    def _get_time_info(self) -> str:
        """获取发放时间信息"""
        time_str = self.config.get_exchange_time_str()
        
        if time_str == "暂未设置" or time_str == "配置异常，请重新设置":
            return "📅 【发放时间】\n\n⏰ 发放时间: 暂未设置\n\n请联系久设置发放时间~"
        
        # 通过 ConfigManager API 读取
        exchange_time = self.config.get("exchange_time", {})
        
        try:
            weekday = int(exchange_time.get("weekday", 0))
            hour = int(exchange_time.get("hour", 0))
            if not (0 <= weekday <= 6) or not (0 <= hour <= 23):
                return "📅 【发放时间】\n\n⚠️ 时间配置异常，请联系久重新设置"
        except (ValueError, TypeError):
            return "📅 【发放时间】\n\n⚠️ 时间配置异常，请联系久重新设置"
        
        now = datetime.now()
        days_until = (weekday - now.weekday()) % 7
        
        if days_until == 0 and now.hour >= hour:
            countdown = "✅ 当前正在发放中！"
        elif days_until == 0:
            hours_until = hour - now.hour
            countdown = f"⏳ 距离发放: 约 {hours_until} 小时"
        else:
            countdown = f"⏳ 距离下次发放: {days_until} 天"
        
        weekly_limit = self.data.get_lottery_config().get("weekly_limit", 1)
        limit_text = f"每周限 {weekly_limit} 次" if weekly_limit > 0 else "每周不限次数"
        
        return f"""📅 【发放时间】

⏰ 发放时段: {time_str}
🔄 重置时间: 每周一 00:00

{countdown}

💡 温馨提示:
• 注册码随时可领（仅限一次）
• 抽奖{limit_text}"""
    
    def _check_group(self, event: AstrMessageEvent, qq: str = None) -> bool:
        """
        检查群成员（双重验证）
        1. 尝试从临时会话获取来源群
        2. 从群成员缓存检查
        """
        # 使用群验证器
        if self.group_verifier:
            passed, method, group_id = self.group_verifier.verify_user(qq, event)
            return passed
        
        # 备用：老方法
        if self.config.get("skip_group_check", False):
            return True
        
        target_groups = self.config.get_target_groups()
        if not target_groups:
            return True
        
        # 尝试获取群ID
        group_id = None
        
        if hasattr(event, 'unified_msg_origin'):
            origin = event.unified_msg_origin
            if hasattr(origin, 'group_id'):
                group_id = str(origin.group_id)
        
        if not group_id and hasattr(event, 'message_obj'):
            msg_obj = event.message_obj
            if hasattr(msg_obj, 'group_id'):
                group_id = str(msg_obj.group_id)
        
        if group_id:
            return group_id in target_groups
        
        return False
