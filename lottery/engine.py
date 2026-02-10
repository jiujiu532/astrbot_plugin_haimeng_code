# -*- coding: utf-8 -*-
"""抽奖引擎模块 - v2.1

使用DataManager的完整原子事务API，确保线程安全和数据一致性。
资格检查和抽奖在同一个事务中完成，防止并发超发。
"""

from typing import Optional, Tuple


# 卡片档次信息
TIER_INFO = {
    "gold": {"name": "金卡", "icon": "🥇", "color": "金色"},
    "purple": {"name": "紫卡", "icon": "💜", "color": "紫色"},
    "blue": {"name": "蓝卡", "icon": "💙", "color": "蓝色"},
    "event": {"name": "活动卡", "icon": "🎪", "color": "彩色"}
}


class LotteryEngine:
    """抽奖引擎"""
    
    def __init__(self, data_manager):
        self.data = data_manager
    
    def draw(self, qq: str, test_mode: bool = False) -> Tuple[Optional[str], Optional[str], str]:
        """
        执行抽奖（使用完整原子事务）
        
        资格检查和抽奖在同一个事务中完成，防止并发超发
        
        返回: (tier, code, message)
        """
        # 使用完整原子事务
        success, status, tier, code = self.data.try_lottery_draw_atomic(qq, test_mode)
        
        if success:
            return tier, code, "success"
        else:
            return None, None, status
    
    def get_pool_info(self) -> str:
        """获取奖池信息（展示真实可抽概率，含活动卡）"""
        pools = self.data.get_all_pool_counts()
        config = self.data.get_lottery_config()
        
        # 计算有库存的档次的真实概率（含活动卡，权重夹逼与引擎一致）
        gold_w = max(1, int(config.get("gold_weight", 5) or 1)) if pools["gold"] > 0 else 0
        purple_w = max(1, int(config.get("purple_weight", 20) or 1)) if pools["purple"] > 0 else 0
        blue_w = max(1, int(config.get("blue_weight", 75) or 1)) if pools["blue"] > 0 else 0
        event_w = max(1, int(config.get("event_weight", 10) or 1)) if (self.data.is_event_pool_active() and pools.get("event", 0) > 0) else 0
        
        total_w = gold_w + purple_w + blue_w + event_w
        if total_w == 0:
            total_w = 1  # 避免除零
        
        # 实际概率
        gold_p = round(gold_w * 100 / total_w) if gold_w else 0
        purple_p = round(purple_w * 100 / total_w) if purple_w else 0
        blue_p = round(blue_w * 100 / total_w) if blue_w else 0
        event_p = round(event_w * 100 / total_w) if event_w else 0
        
        msg = f"""🎰 【奖池信息】

当前奖池:
🥇 金卡 x {pools['gold']} (概率 {gold_p}%{'⚠️缺货' if pools['gold'] == 0 else ''})
💜 紫卡 x {pools['purple']} (概率 {purple_p}%{'⚠️缺货' if pools['purple'] == 0 else ''})
💙 蓝卡 x {pools['blue']} (概率 {blue_p}%{'⚠️缺货' if pools['blue'] == 0 else ''})"""
        
        # 活动卡池
        if event_w > 0:
            event_info = self.data.get_event_pool_info()
            msg += f"""

🎪 【限时活动】{event_info['name']}
🎁 活动卡 x {pools['event']} (概率 {event_p}%)
⏰ 结束时间: {event_info['end_time'][:16] if event_info['end_time'] else '未设置'}"""
        
        # 保底提示
        pity = config.get("pity_threshold", 10)
        msg += f"""

💡 保底机制: 连续 {pity} 次蓝卡后必出紫卡或以上"""
        
        return msg
    
    def get_draw_result_message(self, tier: str, code: str, qq: str) -> str:
        """获取抽奖结果消息"""
        tier_info = TIER_INFO.get(tier, {})
        icon = tier_info.get("icon", "🎁")
        name = tier_info.get("name", "未知")
        
        user_data = self.data.get_user_lottery_data(qq)
        total_draws = user_data.get("total_draws", 0)
        
        if tier == "gold":
            return f"""🎰 正在抽奖...

🎊🎊🎊 超级幸运！🎊🎊🎊

✨✨ 恭喜你抽中了 {icon}【{name}】！✨✨

你的兑换码：
🎁 {code}

太厉害了！你是欧皇！
累计抽奖: {total_draws} 次"""
        
        elif tier == "purple":
            return f"""🎰 正在抽奖...

🎉 运气不错！

✨ 恭喜你抽中了 {icon}【{name}】！

你的兑换码：
🎁 {code}

紫卡哦，比很多人都幸运~
累计抽奖: {total_draws} 次"""
        
        elif tier == "blue":
            config = self.data.get_lottery_config()
            pity_count = user_data.get("pity_count", 0)
            pity_threshold = config.get("pity_threshold", 10)
            
            return f"""🎰 正在抽奖...

恭喜你抽中了 {icon}【{name}】！

你的兑换码：
🎁 {code}

下次说不定能抽到紫卡或金卡~
保底进度: {pity_count}/{pity_threshold}"""
        
        elif tier == "event":
            event_info = self.data.get_event_pool_info()
            event_name = event_info.get("name", "活动")
            return f"""🎰 正在抽奖...

🎪 哇！抽中了限定活动卡！

✨ 恭喜你抽中了 {icon}【{event_name}】！

你的兑换码：
🎁 {code}

这是限定活动卡，非常珍贵！"""
        
        return f"恭喜你抽中了 {icon}【{name}】！\n兑换码: {code}"
    
    def get_history_message(self, limit: int = 10) -> str:
        """获取抽奖历史消息"""
        history = self.data.get_lottery_history(limit)
        
        if not history:
            return "📜 暂无抽奖记录"
        
        msg = f"📜 【最近 {len(history)} 条抽奖记录】\n\n"
        
        for i, record in enumerate(history, 1):
            tier_info = TIER_INFO.get(record["tier"], {})
            icon = tier_info.get("icon", "🎁")
            name = tier_info.get("name", "未知")
            time_str = record["time"][11:16] if len(record["time"]) > 16 else record["time"]
            qq = record["qq"]
            
            # 隐藏部分QQ
            if len(qq) > 4:
                qq_display = qq[:3] + "***" + qq[-2:]
            else:
                qq_display = qq
            
            msg += f"{i}. {qq_display} → {icon} {name} ({time_str})\n"
        
        return msg
