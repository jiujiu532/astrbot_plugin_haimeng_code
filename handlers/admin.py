# -*- coding: utf-8 -*-
"""管理员消息处理模块"""

from typing import Optional, List, Union
from datetime import datetime

from ..config import ConfigManager
from ..data import DataManager
from ..utils.session import SessionManager
from ..utils.templates import Templates
from ..lottery.engine import TIER_INFO


class AdminHandler:
    """管理员消息处理器"""
    
    def __init__(self, config: ConfigManager, data: DataManager, session: SessionManager, 
                 lottery_engine, group_manager=None):
        self.config = config
        self.data = data
        self.session = session
        self.lottery = lottery_engine
        self.group_manager = group_manager  # 群成员管理器
    
    # ==================== 菜单层级导航 ====================
    # D=回退一级  D2=回退两级  Q=返回主菜单  不输入=保活留在当前菜单
    
    STATE_PARENT = {
        "admin_menu": None,
        "stock_menu": "admin_menu",
        "user_menu": "admin_menu",
        "blacklist_menu": "admin_menu",
        "time_menu": "admin_menu",
        "announcement_menu": "admin_menu",
        "lottery_config_menu": "admin_menu",
        "event_menu": "admin_menu",
        "add_reg_codes": "admin_menu",
        "select_lottery_tier": "admin_menu",
        "set_announcement": "announcement_menu",
        "import_users": "user_menu",
    }
    
    def _get_parent_state(self, state: str) -> Optional[str]:
        """获取上级菜单状态"""
        if state and state.startswith("add_lottery_"):
            return "select_lottery_tier"
        return self.STATE_PARENT.get(state)
    
    def _get_menu_display(self, qq: str, state: str) -> str:
        """获取指定菜单状态的展示文本"""
        if state == "admin_menu":
            return Templates.ADMIN_MENU
        elif state == "stock_menu":
            return self._show_stock_menu()
        elif state == "user_menu":
            return self._show_user_menu()
        elif state == "blacklist_menu":
            return self._show_blacklist_menu()
        elif state == "time_menu":
            return self._show_time_menu()
        elif state == "announcement_menu":
            return self._show_announcement_menu(qq)
        elif state == "lottery_config_menu":
            return self._show_lottery_config()
        elif state == "event_menu":
            return self._show_event_pool_menu()
        elif state == "select_lottery_tier":
            return Templates.ADMIN_ADD_LOTTERY_SELECT
        return Templates.ADMIN_MENU
    
    async def handle(self, qq: str, message: str) -> Optional[Union[str, List[str]]]:
        """处理管理员消息"""
        lines = message.split('\n')
        cmd = lines[0].strip()
        
        # 检查管理员面板触发
        if cmd == "jiu":
            self.session.set(qq, "admin_menu", is_admin=True)
            return Templates.ADMIN_MENU
        
        # 检查会话状态
        session = self.session.get(qq, is_admin=True)
        if session:
            state = session.get("state")
            context = session.get("context", {})
            upper_msg = message.upper().strip()
            
            # Q = 返回主菜单
            if upper_msg == "Q":
                self.session.set(qq, "admin_menu", is_admin=True)
                return "↩️ 已返回主菜单\n\n" + Templates.ADMIN_MENU
            
            # D = 回退一级
            if upper_msg == "D":
                parent = self._get_parent_state(state)
                if parent:
                    self.session.set(qq, parent, is_admin=True)
                    return "↩️ 已返回上级\n\n" + self._get_menu_display(qq, parent)
                return "📍 已在主菜单，无法继续回退"
            
            # D2 = 回退两级
            if upper_msg == "D2":
                parent = self._get_parent_state(state)
                grand = self._get_parent_state(parent) if parent else None
                target = grand or parent or "admin_menu"
                self.session.set(qq, target, is_admin=True)
                return "↩️ 已返回\n\n" + self._get_menu_display(qq, target)
            
            # 处理各种会话状态
            return await self._handle_session_state(qq, message, lines, state, context)
        
        # 不在会话中，尝试处理快捷命令
        return await self._handle_quick_command(qq, message, lines)
    
    async def _handle_session_state(self, qq: str, message: str, lines: List[str], state: str, context: dict) -> Optional[Union[str, List[str]]]:
        """处理会话状态（保活：操作后留在当前菜单，输入态回到上级）"""
        if state == "admin_menu":
            return await self._handle_menu_choice(qq, message, lines)
        
        # ========== 输入状态（完成后回到上级）==========
        elif state == "add_reg_codes":
            self.session.set(qq, "admin_menu", is_admin=True)
            return self._add_codes(message, "registration")
        elif state == "select_lottery_tier":
            return self._handle_tier_select(qq, message)
        elif state.startswith("add_lottery_"):
            tier = state.replace("add_lottery_", "")
            self.session.set(qq, "admin_menu", is_admin=True)
            return self._add_lottery_codes(message, tier)
        elif state == "set_announcement":
            self.session.set(qq, "announcement_menu", is_admin=True)
            return self._set_announcement(message)
        elif state == "import_users":
            self.session.set(qq, "user_menu", is_admin=True)
            return self._import_users(message)

        # ========== 子菜单状态（保活：操作后留在当前菜单）==========
        elif state == "stock_menu":
            if message.upper().startswith("3-"):
                return self._handle_stock_action(qq, message)
            return "❌ 无效操作，请使用 3-G/P/B/R 查看库存\n\n💡 D=返回上级 Q=返回主菜单"
        
        elif state == "user_menu":
            if message.upper().startswith("4-"):
                if message.upper() == "4-5":
                    self.session.set(qq, "import_users", is_admin=True)
                    return """📥 【导入已注册用户】

请回复要导入的 QQ 号列表
每行一个 QQ 号

导入后这些用户将无法再领取注册码

💡 D=返回上级 Q=返回主菜单"""
                return self._handle_user_action(qq, message, lines)
            return "❌ 无效操作，请使用 4-1/2/3/4/5/6\n\n💡 D=返回上级 Q=返回主菜单"
        
        elif state == "blacklist_menu":
            if message.upper().startswith("6-"):
                return self._handle_blacklist_action(message, lines)
            return "❌ 无效操作，请使用 6-1/2/3 QQ号\n\n💡 D=返回上级 Q=返回主菜单"
        
        elif state == "time_menu":
            if message.upper().startswith("7-"):
                return self._handle_time_action(message, lines)
            return "❌ 无效操作，请使用 7-1 周X 或 7-2 小时\n\n💡 D=返回上级 Q=返回主菜单"
        
        elif state == "announcement_menu":
            if message.upper().startswith("8-"):
                return self._handle_announcement_action(qq, message)
            return "❌ 无效操作，请使用 8-1 设置公告 或 8-2 清空\n\n💡 D=返回上级 Q=返回主菜单"
        
        elif state == "lottery_config_menu":
            if message.upper().startswith("10-"):
                return self._handle_lottery_config_action(message, lines)
            return "❌ 无效操作，请使用 10-G/P/B/T/W/D 数值\n\n💡 D=返回上级 Q=返回主菜单"
        
        elif state == "event_menu":
            if message.upper().startswith("E-"):
                return self._handle_event_pool_action(message, lines)
            return "❌ 无效操作，请使用 E-1/E-2/E-3\n\n💡 D=返回上级 Q=返回主菜单"
        
        return None
    
    async def _handle_menu_choice(self, qq: str, choice: str, lines: List[str]) -> str:
        """处理管理员菜单选择"""
        # 不要在这里 clear，子菜单需要自己管理会话
        
        if choice == "0":
            self.session.clear(qq, is_admin=True)
            return Templates.ADMIN_HELP
        elif choice == "1":
            self.session.set(qq, "add_reg_codes", is_admin=True)
            return """📋 【添加注册码】

请回复要添加的注册码
每行一个，支持批量添加

回复 Q 取消操作"""
        elif choice == "2":
            self.session.set(qq, "select_lottery_tier", is_admin=True)
            return Templates.ADMIN_ADD_LOTTERY_SELECT
        elif choice == "3":
            self.session.set(qq, "stock_menu", is_admin=True)
            return self._show_stock_menu()
        elif choice == "4":
            self.session.set(qq, "user_menu", is_admin=True)
            return self._show_user_menu()
        elif choice == "5":
            self.session.clear(qq, is_admin=True)  # 纯展示，可清除
            return self._show_statistics()
        elif choice == "6":
            self.session.set(qq, "blacklist_menu", is_admin=True)
            return self._show_blacklist_menu()
        elif choice == "7":
            self.session.set(qq, "time_menu", is_admin=True)
            return self._show_time_menu()
        elif choice == "8":
            self.session.set(qq, "announcement_menu", is_admin=True)
            return self._show_announcement_menu(qq)
        elif choice == "9":
            self.session.clear(qq, is_admin=True)  # 纯展示，可清除
            return self._show_status()
        elif choice == "10":
            self.session.set(qq, "lottery_config_menu", is_admin=True)
            return self._show_lottery_config()
        elif choice == "11":  # 活动卡池管理
            self.session.set(qq, "event_menu", is_admin=True)
            return self._show_event_pool_menu()
        
        # 快捷操作
        elif choice.startswith("3-"):
            return self._handle_stock_action(qq, choice)
        elif choice.startswith("4-"):
            return self._handle_user_action(qq, choice, lines)
        elif choice.startswith("6-"):
            return self._handle_blacklist_action(choice, lines)
        elif choice.startswith("7-"):
            return self._handle_time_action(choice, lines)
        elif choice.startswith("8-"):
            return self._handle_announcement_action(qq, choice)
        elif choice.startswith("10-"):
            return self._handle_lottery_config_action(choice, lines)
        elif choice.upper().startswith("E-"):
            return self._handle_event_pool_action(choice, lines)
        elif choice.upper() in ["G", "P", "B", "E"]:
            return self._handle_tier_select(qq, choice)
        
        self.session.set(qq, "admin_menu", is_admin=True)
        return "❌ 无效选择\n\n" + Templates.ADMIN_MENU
    
    def _handle_tier_select(self, qq: str, choice: str) -> str:
        """处理档次选择"""
        tier_map = {"G": "gold", "P": "purple", "B": "blue", "E": "event"}
        template_map = {
            "G": Templates.ADMIN_ADD_GOLD,
            "P": Templates.ADMIN_ADD_PURPLE,
            "B": Templates.ADMIN_ADD_BLUE,
            "E": Templates.ADMIN_ADD_EVENT
        }
        
        choice_upper = choice.upper()
        if choice_upper in tier_map:
            tier = tier_map[choice_upper]
            self.session.set(qq, f"add_lottery_{tier}", is_admin=True)
            return template_map[choice_upper]
        
        self.session.clear(qq, is_admin=True)
        return "❌ 无效选择"
    
    def _add_codes(self, message: str, code_type: str) -> str:
        """添加注册码（通过DataManager公共API）"""
        codes = [line.strip() for line in message.split('\n') if line.strip()]
        if not codes:
            return "❌ 没有找到有效的码"
        
        result = self.data.add_registration_codes(codes)
        added = result["added"]
        skipped = result["skipped"]
        
        self.data.log_action("添加注册码", "ADMIN", f"添加{added}个")
        
        # 获取当前库存
        stats = self.data.get_statistics()
        current_stock = stats["registration_codes"]["unused"]
        
        return f"""✅ 注册码添加成功！

添加: {added} 个
跳过重复: {skipped} 个

当前库存: {current_stock} 个"""
    
    def _add_lottery_codes(self, message: str, tier: str) -> str:
        """添加抽奖码（通过DataManager公共API）"""
        codes = [line.strip() for line in message.split('\n') if line.strip()]
        if not codes:
            return "❌ 没有找到有效的码"
        
        tier_info = TIER_INFO.get(tier, {})
        tier_name = tier_info.get("name", tier)
        tier_icon = tier_info.get("icon", "🎁")
        
        if tier == "event":
            result = self.data.add_event_codes(codes)
        else:
            result = self.data.add_lottery_codes(tier, codes)
        
        if "error" in result:
            return f"❌ {result['error']}"
        
        added = result["added"]
        skipped = result["skipped"]
        
        self.data.log_action(f"添加{tier_name}", "ADMIN", f"添加{added}个")
        
        # 获取当前库存
        pools = self.data.get_all_pool_counts()
        current_stock = pools.get(tier, 0)
        
        return f"""✅ {tier_icon} {tier_name}添加成功！

添加: {added} 个
跳过重复: {skipped} 个

当前库存: {current_stock} 个"""
    
    def _set_announcement(self, content: str) -> str:
        """设置公告"""
        self.data.set_announcement(content)
        self.data.log_action("设置公告", "ADMIN", content[:30])
        return f"✅ 公告已更新！\n\n{content}"
    
    def _show_stock_menu(self) -> str:
        """显示库存菜单（通过DataManager公共API）"""
        stats = self.data.get_statistics()
        pools = stats["lottery_pool"]
        reg_unused = stats["registration_codes"]["unused"]
        reg_used = stats["registration_codes"]["used"]
        
        # 检查预警
        threshold = self.config.get("stock_alert_threshold", 10)
        alerts = []
        if reg_unused < threshold:
            alerts.append(f"⚠️ 注册码不足: {reg_unused}个")
        if pools["gold"] < 5:
            alerts.append(f"⚠️ 金卡不足: {pools['gold']}个")
        if pools["purple"] < 10:
            alerts.append(f"⚠️ 紫卡不足: {pools['purple']}个")
        
        alert_str = "\n".join(alerts) if alerts else "无"
        
        msg = f"""📦 【库存详情】

📋 注册码:
├ 未用: {reg_unused} 个
└ 已发: {reg_used} 个

🎰 抽奖卡池:
🥇 金卡: {pools['gold']} 个
💜 紫卡: {pools['purple']} 个
💙 蓝卡: {pools['blue']} 个"""
        
        if pools.get('event', 0) > 0:
            msg += f"\n🎪 活动卡: {pools['event']} 个"
        
        msg += f"""

⚠️ 库存预警: {alert_str}

━━━━━━━━━━━━━━━━━
快捷操作:
回复 3-G 查看金卡列表
回复 3-P 查看紫卡列表
回复 3-B 查看蓝卡列表
回复 3-R 查看注册码列表"""
        
        return msg
    
    def _show_user_menu(self) -> str:
        """显示用户管理菜单（通过DataManager公共API）"""
        stats = self.data.get_statistics()
        total = stats["registered_users"]
        week_draws = stats.get("total_lottery_draws", 0)
        
        return f"""👥 【用户管理】

📊 总注册: {total} 人
🎰 累计抽奖: {week_draws} 次

━━━━━━━━━━━━━━━━━
快捷操作:
回复 4-1 查看用户列表
回复 4-2 QQ号 查询用户
回复 4-3 QQ号 重置用户
回复 4-4 QQ号 清空抽奖数据
回复 4-5 批量导入用户
回复 4-6 📤 导出全部用户"""
    
    def _show_statistics(self) -> str:
        """显示统计（通过DataManager公共API）"""
        stats = self.data.get_statistics()
        pools = stats["lottery_pool"]
        tier_counts = stats.get("lottery_counts", {"gold": 0, "purple": 0, "blue": 0, "event": 0})
        
        return f"""📊 【数据统计】

👥 用户数据:
├ 总注册: {stats['registered_users']} 人
└ 黑名单: {stats['blacklist_count']} 人

📋 注册码:
├ 未用: {stats['registration_codes']['unused']} 个
└ 已发: {stats['registration_codes']['used']} 个

🎰 抽奖统计 (最近100次):
├ 🥇 金卡: {tier_counts['gold']} 次
├ 💜 紫卡: {tier_counts['purple']} 次
├ 💙 蓝卡: {tier_counts['blue']} 次
└ 🎪 活动卡: {tier_counts['event']} 次

📦 当前库存:
├ 🥇 金卡: {pools['gold']} 个
├ 💜 紫卡: {pools['purple']} 个
├ 💙 蓝卡: {pools['blue']} 个
└ 🎪 活动卡: {pools['event']} 个"""
    
    def _show_blacklist_menu(self) -> str:
        """显示黑名单菜单（通过DataManager公共API）"""
        blacklist = self.data.get_blacklist()
        
        if not blacklist:
            list_str = "（空）"
        else:
            list_str = "\n".join([f"QQ{qq}" for qq in blacklist[:10]])
            if len(blacklist) > 10:
                list_str += f"\n... 还有 {len(blacklist) - 10} 人"
        
        return f"""🚫 【黑名单管理】

当前黑名单: {len(blacklist)} 人

{list_str}

━━━━━━━━━━━━━━━━━
快捷操作:
回复 6-1 QQ号 添加黑名单
回复 6-2 QQ号 移除黑名单
回复 6-3 清空黑名单"""
    
    def _show_time_menu(self) -> str:
        """显示时间设置菜单"""
        time_str = self.config.get_exchange_time_str()
        
        return f"""⏰ 【发放时间设置】

当前设置: {time_str}

━━━━━━━━━━━━━━━━━
修改设置:
回复 7-1 星期 设置星期几（如: 7-1 周日）
回复 7-2 小时 设置几点开始（如: 7-2 9）
回复 7-3 星期 小时 一键设置（如: 7-3 周日 9）"""
    
    def _show_announcement_menu(self, qq: str) -> str:
        """显示公告管理菜单"""
        announcement = self.data.get_announcement()
        content = announcement.get("content", "")
        time_str = announcement.get("time", "")
        
        if content:
            current = f"━━━━━━━━━━━━━━━━━\n{content}\n━━━━━━━━━━━━━━━━━\n发布时间: {time_str[:16] if time_str else '未知'}"
        else:
            current = "暂无公告"
        
        return f"""📢 【公告管理】

当前公告:
{current}

━━━━━━━━━━━━━━━━━
快捷操作:
回复 8-1 设置新公告
回复 8-2 清空公告"""
    
    def _show_status(self) -> str:
        """显示系统状态"""
        enabled = self.config.is_enabled()
        test_mode = self.config.is_test_mode()
        pools = self.data.get_all_pool_counts()
        
        stats = self.data.get_statistics()
        reg_stock = stats["registration_codes"]["unused"]
        
        return f"""⚙️ 【系统状态】

🔌 插件状态: {'已开启 ✅' if enabled else '已关闭 ❌'}
🧪 测试模式: {'开启 ✅' if test_mode else '关闭 ❌'}

📋 基础配置:
├ 触发词: {self.config.get_trigger_keyword()}
├ 目标群: {', '.join(self.config.get_target_groups()) or '未设置'}
└ 发放时间: {self.config.get_exchange_time_str()}

📦 库存状态:
├ 注册码: {reg_stock} 个
├ 🥇 金卡: {pools['gold']} 个
├ 💜 紫卡: {pools['purple']} 个
└ 💙 蓝卡: {pools['blue']} 个"""
    
    def _show_health(self) -> str:
        """显示系统健康状态"""
        import os
        from pathlib import Path
        
        lines = ["🩺 【系统健康检查】\n"]
        
        # 数据文件状态
        data_file = self.data.data_file
        backup_file = Path(str(data_file) + '.bak')
        lines.append("📁 数据文件:")
        if data_file.exists():
            size = os.path.getsize(data_file)
            lines.append(f"  ✅ data.json: {size:,} 字节")
        else:
            lines.append("  ❌ data.json: 缺失")
        if backup_file.exists():
            size = os.path.getsize(backup_file)
            lines.append(f"  ✅ data.json.bak: {size:,} 字节")
        else:
            lines.append("  ⚠️ data.json.bak: 无备份")
        
        # 群缓存状态
        if self.group_manager:
            lines.append(f"\n👥 群缓存:")
            lines.append(f"  {self.group_manager.get_cache_status()}")
        
        # 日志数量
        logs = self.data.get_logs(1)
        total_logs = len(self.data.get_logs(500))
        if logs:
            lines.append(f"\n📋 审计日志: {total_logs} 条")
            lines.append(f"  最近: {logs[0].get('action', '?')} ({logs[0].get('time', '?')[:16]})")
        
        # 配置摘要
        lines.append(f"\n⚙️ 配置:")
        lines.append(f"  插件状态: {'✅ 开启' if self.config.is_enabled() else '⏸️ 关闭'}")
        lines.append(f"  测试模式: {'⚠️ 开启' if self.config.is_test_mode() else '关闭'}")
        lines.append(f"  发放时间: {self.config.get_exchange_time_str()}")
        
        return "\n".join(lines)
    
    def _show_lottery_config(self) -> str:
        """显示抽奖配置（通过DataManager公共API）"""
        config = self.data.get_lottery_config()
        
        # 夹逼权重（与引擎一致，防止手工编辑为负数）
        gold_w = max(1, int(config.get("gold_weight", 5) or 1))
        purple_w = max(1, int(config.get("purple_weight", 20) or 1))
        blue_w = max(1, int(config.get("blue_weight", 75) or 1))
        event_w = max(1, int(config.get("event_weight", 10) or 1))
        # 基础概率（不含活动卡时）
        base_total = gold_w + purple_w + blue_w
        # 含活动卡概率（活动开启时）
        full_total = base_total + event_w
        
        pity_tier_name = TIER_INFO.get(config.get("pity_tier", "purple"), {}).get("name", "紫卡")
        
        base_info = Templates.ADMIN_LOTTERY_CONFIG.format(
            gold_weight=gold_w,
            purple_weight=purple_w,
            blue_weight=blue_w,
            gold_percent=round(gold_w * 100 / base_total) if base_total else 0,
            purple_percent=round(purple_w * 100 / base_total) if base_total else 0,
            blue_percent=round(blue_w * 100 / base_total) if base_total else 0,
            pity_threshold=config.get("pity_threshold", 10),
            pity_tier=pity_tier_name,
            daily_limit=config.get("daily_limit", 0),
            weekly_limit=config.get("weekly_limit", 1)
        )
        
        # 活动卡权重及其对概率的影响
        event_active = self.data.is_event_pool_active()
        event_status = "✅ 开启中" if event_active else "未开启"
        event_percent = round(event_w * 100 / full_total) if full_total else 0
        base_info += f"\n\n🎪 活动卡权重: {event_w} ({event_status})"
        if event_active:
            base_info += f"\n   活动开启时概率: {event_percent}%"
        base_info += f"\n回复 10-E 数字 修改活动卡权重"
        return base_info
    
    def _handle_stock_action(self, qq: str, action: str) -> str:
        """处理库存操作（通过DataManager公共API）"""
        tier_map = {"3-G": "gold", "3-P": "purple", "3-B": "blue", "3-R": "registration"}
        
        action_upper = action.upper()
        if action_upper in tier_map:
            tier = tier_map[action_upper]
            
            # 获取真实库存数
            if tier == "registration":
                stats = self.data.get_statistics()
                total_count = stats["registration_codes"]["unused"]
                codes = self.data.get_codes_preview("registration", limit=30)
            else:
                pools = self.data.get_all_pool_counts()
                total_count = pools.get(tier, 0)
                codes = self.data.get_codes_preview("lottery", tier, limit=30)
            
            tier_info = TIER_INFO.get(tier, {"name": "注册码", "icon": "📋"})
            
            if not codes:
                return f"{tier_info['icon']} 【{tier_info['name']}】库存为空"
            
            msg = f"{tier_info['icon']} 【{tier_info['name']}库存】\n总计: {total_count} 个\n\n"
            for code in codes:
                msg += f"{code}\n"
            
            if total_count > len(codes):
                msg += f"\n... 仅显示前 {len(codes)} 个（脱敏）"
            
            return msg
        
        return "❌ 无效操作"
    
    def _handle_user_action(self, qq: str, action: str, lines: List[str]) -> Union[str, List[str]]:
        """处理用户管理操作（通过DataManager公共API）"""
        parts = action.split(" ", 1)
        cmd = parts[0]
        param = parts[1].strip() if len(parts) > 1 else ""
        
        if cmd == "4-1":
            # 获取用户列表
            users = self.data.get_registered_users_list(50)
            if not users:
                return "📋 暂无注册用户"
            
            stats = self.data.get_statistics()
            msg = f"📋 【已注册用户】\n共 {stats['registered_users']} 人\n\n"
            for user_qq, info in users:
                msg += f"QQ{user_qq}\n"
            return msg
        
        elif cmd == "4-2" and param:
            user_qq = param
            info = self.data.get_user_info(user_qq)
            if not info:
                return f"❌ 用户 {user_qq} 未注册"
            
            lottery_data = self.data.get_user_lottery_data(user_qq)
            
            return f"""👤 【用户 {user_qq}】

📋 注册码: {info.get('reg_code', '未知')}
📅 注册时间: {info.get('reg_time', '')[:10] if info.get('reg_time') else '未知'}
📦 导入用户: {'是' if info.get('imported') else '否'}

🎰 抽奖数据:
├ 累计抽奖: {lottery_data.get('total_draws', 0)} 次
├ 本周已抽: {lottery_data.get('week_draws', 0)} 次
└ 保底进度: {lottery_data.get('pity_count', 0)}"""
        
        elif cmd == "4-3" and param:
            user_qq = param
            if self.data.reset_user_registration(user_qq):
                return f"✅ 已重置用户 {user_qq} 的注册"
            return f"❌ 用户 {user_qq} 未注册"
        
        elif cmd == "4-4" and param:
            user_qq = param
            if self.data.reset_user_lottery_data(user_qq):
                return f"✅ 已清空用户 {user_qq} 的抽奖数据"
            return f"❌ 用户 {user_qq} 无抽奖记录"
        
        elif cmd == "4-6":
            # 导出全部用户
            return self._export_users()
        
        return "❌ 格式错误\n示例: 4-2 123456"
    

    def _handle_blacklist_action(self, action: str, lines: List[str]) -> str:
        """处理黑名单操作（通过DataManager公共API）"""
        parts = action.split(" ", 1)
        cmd = parts[0]
        param = parts[1].strip() if len(parts) > 1 else ""
        
        if cmd == "6-1" and param:
            self.data.add_to_blacklist(param)
            return f"✅ 已将 {param} 加入黑名单"
        elif cmd == "6-2" and param:
            self.data.remove_from_blacklist(param)
            return f"✅ 已将 {param} 移出黑名单"
        elif cmd == "6-3":
            self.data.clear_blacklist()
            return "✅ 黑名单已清空"
        
        return "❌ 格式错误\n示例: 6-1 123456"
    
    def _handle_time_action(self, action: str, lines: List[str]) -> str:
        """处理时间设置"""
        parts = action.split(" ", 2)
        cmd = parts[0]
        
        weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
        
        if cmd == "7-1" and len(parts) > 1:
            weekday_str = parts[1]
            if weekday_str in weekday_map:
                self.config.set("exchange_time.weekday", weekday_map[weekday_str])
                return f"✅ 发放日已设置为: {weekday_str}"
            return "❌ 无效的星期"
        
        elif cmd == "7-2" and len(parts) > 1:
            try:
                hour = int(parts[1])
                if 0 <= hour <= 23:
                    self.config.set("exchange_time.hour", hour)
                    return f"✅ 开始时间已设置为: {hour}:00"
            except ValueError:
                pass
            return "❌ 请输入有效的小时数 (0-23)"
        
        elif cmd == "7-3" and len(parts) > 2:
            weekday_str = parts[1]
            try:
                hour = int(parts[2].replace("点", ""))
                if weekday_str in weekday_map and 0 <= hour <= 23:
                    self.config.set("exchange_time.weekday", weekday_map[weekday_str])
                    self.config.set("exchange_time.hour", hour)
                    return f"✅ 发放时间已设置为: 每{weekday_str} {hour}:00 - 24:00"
            except (ValueError, KeyError):
                pass
            return "❌ 格式错误\n示例: 7-3 周日 9"
        
        return "❌ 格式错误"
    
    def _handle_announcement_action(self, qq: str, action: str) -> str:
        """处理公告操作"""
        if action == "8-1":
            self.session.set(qq, "set_announcement", is_admin=True)
            return """📝 【设置公告】

请直接回复公告内容
支持多行，回复后立即生效

回复 Q 取消操作"""
        elif action == "8-2":
            self.data.clear_announcement()
            return "✅ 公告已清空"
        
        return "❌ 无效操作"
    
    def _handle_lottery_config_action(self, action: str, lines: List[str]) -> str:
        """处理抽奖配置操作（通过DataManager公共API）"""
        parts = action.split(" ", 1)
        cmd = parts[0].upper()
        value = parts[1].strip() if len(parts) > 1 else ""
        
        try:
            num = int(value)
        except ValueError:
            return "❌ 请输入有效的数字"
        
        if cmd == "10-G":
            actual = max(1, num)
            self.data.update_lottery_config("gold_weight", actual)
            return f"✅ 金卡权重已设置为: {actual}"
        elif cmd == "10-P":
            actual = max(1, num)
            self.data.update_lottery_config("purple_weight", actual)
            return f"✅ 紫卡权重已设置为: {actual}"
        elif cmd == "10-B":
            actual = max(1, num)
            self.data.update_lottery_config("blue_weight", actual)
            return f"✅ 蓝卡权重已设置为: {actual}"
        elif cmd == "10-T":
            actual = max(1, num)
            self.data.update_lottery_config("pity_threshold", actual)
            return f"✅ 保底阈值已设置为: {actual}"
        elif cmd == "10-W":
            actual = max(0, num)
            self.data.update_lottery_config("weekly_limit", actual)
            return f"✅ 每周限制已设置为: {actual}"
        elif cmd == "10-D":
            actual = max(0, num)
            self.data.update_lottery_config("daily_limit", actual)
            return f"✅ 每日限制已设置为: {actual}"
        elif cmd == "10-E":
            actual = max(1, num)
            self.data.update_lottery_config("event_weight", actual)
            return f"✅ 活动卡权重已设置为: {actual}"
        
        return "❌ 无效操作"
    
    async def _handle_quick_command(self, qq: str, message: str, lines: List[str]) -> Optional[Union[str, List[str]]]:
        """处理快捷命令"""
        cmd = lines[0].strip()
        
        if cmd == "jiu状态":
            return self._show_status()
        elif cmd == "jiu库":
            return self._show_stock_menu()
        elif cmd == "jiu统计":
            return self._show_statistics()
        elif cmd == "jiu帮助":
            return Templates.ADMIN_HELP
        elif cmd == "jiu记录":
            return self.lottery.get_history_message(20)
        elif cmd == "jiu健康":
            return self._show_health()
        elif cmd == "jiu开启":
            self.config.set("enabled", True)
            return "✅ 插件已开启"
        elif cmd == "jiu关闭":
            self.config.set("enabled", False)
            return "⏸️ 插件已关闭"
        elif cmd == "jiu测试":
            new_mode = not self.config.is_test_mode()
            self.config.set("test_mode", new_mode)
            return f"✅ 测试模式已{'开启' if new_mode else '关闭'}"
        
        # 添加码命令
        if cmd.startswith("jiu注册") and len(lines) > 1:
            codes = [line.strip() for line in lines[1:] if line.strip()]
            return self._add_codes("\n".join(codes), "registration")
        elif cmd.startswith("jiu金卡") and len(lines) > 1:
            codes = [line.strip() for line in lines[1:] if line.strip()]
            return self._add_lottery_codes("\n".join(codes), "gold")
        elif cmd.startswith("jiu紫卡") and len(lines) > 1:
            codes = [line.strip() for line in lines[1:] if line.strip()]
            return self._add_lottery_codes("\n".join(codes), "purple")
        elif cmd.startswith("jiu蓝卡") and len(lines) > 1:
            codes = [line.strip() for line in lines[1:] if line.strip()]
            return self._add_lottery_codes("\n".join(codes), "blue")
        elif cmd.startswith("jiu活动卡") and len(lines) > 1:
            codes = [line.strip() for line in lines[1:] if line.strip()]
            return self._add_lottery_codes("\n".join(codes), "event")
        
        # 用户管理快捷命令
        elif cmd.startswith("jiu用户"):
            target_qq = cmd.replace("jiu用户", "").strip()
            if target_qq:
                return self._handle_user_action(qq, f"4-2 {target_qq}", lines)
            return "❌ 格式: jiu用户 QQ号"
        elif cmd.startswith("jiu重置"):
            target_qq = cmd.replace("jiu重置", "").strip()
            if target_qq:
                return self._handle_user_action(qq, f"4-3 {target_qq}", lines)
            return "❌ 格式: jiu重置 QQ号"
        elif cmd.startswith("jiu黑名单"):
            target_qq = cmd.replace("jiu黑名单", "").strip()
            if target_qq:
                return self._handle_blacklist_action(f"6-1 {target_qq}", lines)
            return "❌ 格式: jiu黑名单 QQ号"
        elif cmd.startswith("jiu解黑"):
            target_qq = cmd.replace("jiu解黑", "").strip()
            if target_qq:
                return self._handle_blacklist_action(f"6-2 {target_qq}", lines)
            return "❌ 格式: jiu解黑 QQ号"
        elif cmd == "jiu导出":
            return self._export_users()
        elif cmd.startswith("jiu时间"):
            # jiu时间 周X X / jiu时间 每周X X点
            args = cmd.replace("jiu时间", "").strip()
            if args:
                parts = args.split()
                if len(parts) >= 2:
                    # 兼容 "每周X" 和 "周X" 两种格式
                    weekday_part = parts[0].replace("每", "")
                    hour_part = parts[1].replace("点", "")
                    return self._handle_time_action(f"7-3 {weekday_part} {hour_part}", lines)
            return "❌ 格式: jiu时间 周X 小时\n示例: jiu时间 周日 9"
        elif cmd == "jiu公告":
            self.session.set(qq, "announcement_menu", is_admin=True)
            return self._show_announcement_menu(qq)
        
        return None
    
    # ==================== 活动卡池管理 ====================
    
    def _show_event_pool_menu(self) -> str:
        """显示活动卡池管理菜单"""
        event_info = self.data.get_event_pool_info()
        pools = self.data.get_all_pool_counts()
        
        status = "✅ 已开启" if event_info["enabled"] else "❌ 已关闭"
        name = event_info.get("name") or "未设置"
        end_time = event_info.get("end_time", "")[:16] if event_info.get("end_time") else "未设置"
        count = pools.get("event", 0)
        
        return Templates.ADMIN_EVENT_POOL.format(
            status=status,
            name=name,
            end_time=end_time,
            count=count
        )
    
    def _handle_event_pool_action(self, action: str, lines: List[str]) -> str:
        """处理活动卡池操作"""
        # 只对命令部分upper，保留参数原始大小写
        parts = action.split(" ", 2)
        cmd = parts[0].upper()
        
        if cmd == "E-1":
            # 开启活动：E-1 活动名 结束时间（最后一段为日期，前面为活动名）
            rest = action[len(parts[0]):].strip()
            rest_parts = rest.rsplit(" ", 1)
            if len(rest_parts) < 2 or not rest_parts[0].strip():
                return """❌ 格式错误

正确格式: E-1 活动名 结束时间
示例: E-1 春节活动 2026-02-15"""
            
            name = rest_parts[0].strip()
            end_time = rest_parts[1].strip()
            
            # 验证日期格式
            try:
                datetime.fromisoformat(end_time)
            except ValueError:
                return "❌ 日期格式错误，请使用 YYYY-MM-DD 格式"
            
            if self.data.set_event_pool(name, end_time):
                self.data.log_action("开启活动卡池", "ADMIN", f"{name}, 结束: {end_time}")
                return f"""✅ 活动卡池已开启！

🎪 活动名称: {name}
⏰ 结束时间: {end_time}

💡 请使用菜单 2 → E 添加活动卡码"""
            return "❌ 开启失败"
        
        elif cmd == "E-2":
            # 关闭活动
            if self.data.disable_event_pool():
                self.data.log_action("关闭活动卡池", "ADMIN", "")
                return "✅ 活动卡池已关闭"
            return "❌ 关闭失败"
        
        elif cmd == "E-3":
            # 查看活动卡列表
            event_info = self.data.get_event_pool_info()
            total_count = event_info.get("stock", 0)
            codes = self.data.get_codes_preview("event", limit=30)
            if not codes:
                return "📋 活动卡库存为空"
            
            code_list = "\n".join([f"  {c}" for c in codes[:20]])
            more = f"\n  ... 仅显示前 20 个（脱敏）" if len(codes) > 20 else ""
            
            return f"""📋 【活动卡列表】（脱敏显示）

{code_list}{more}

总计: {total_count} 个"""
        
        return "❌ 无效操作，请使用 E-1/E-2/E-3"
    
    # ==================== 用户导入/导出 ====================
    
    def _import_users(self, message: str) -> str:
        """处理批量导入用户"""
        qq_list = [line.strip() for line in message.split('\n') if line.strip()]
        if not qq_list:
            return "❌ 未检测到有效的 QQ 号"
        
        # 过滤非数字
        valid_list = [qq for qq in qq_list if qq.isdigit()]
        invalid_count = len(qq_list) - len(valid_list)
        if not valid_list:
            return "❌ 未检测到有效的 QQ 号（QQ号应为纯数字）"
        
        result = self.data.import_registered_users(valid_list)
        self.data.log_action("批量导入用户", "ADMIN", f"新增{result['added']}人，跳过{result['skipped']}人")
        
        msg = f"""✅ 导入完成！

📊 结果:
├ 新增: {result['added']} 人
└ 跳过（已注册）: {result['skipped']} 人"""
        if invalid_count > 0:
            msg += f"\n⚠️ 跳过 {invalid_count} 个非数字项"
        return msg
    
    def _export_users(self) -> Union[str, List[str]]:
        """导出全部用户数据（分批发送，每批50个，适配QQ消息长度限制）"""
        users = self.data.get_all_registered_users()
        total = len(users)
        
        if total == 0:
            return "📋 暂无注册用户可导出"
        
        BATCH_SIZE = 50
        batches = []
        total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
        
        for i in range(0, total, BATCH_SIZE):
            batch = users[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            
            header = f"📤 【用户导出】({batch_num}/{total_batches}) 共 {total} 人\n"
            header += f"第 {i + 1}-{min(i + BATCH_SIZE, total)} 个\n"
            header += "━━━━━━━━━━━━━━━━━\n"
            
            lines = []
            for user_qq, info in batch:
                lines.append(user_qq)
            
            batches.append(header + "\n".join(lines))
        
        # 在最后一批追加提示
        batches[-1] += f"\n━━━━━━━━━━━━━━━━━\n✅ 导出完毕，共 {total} 人\n💡 可复制 QQ 号列表用于 4-5 批量导入"
        
        self.data.log_action("导出用户数据", "ADMIN", f"共{total}人，分{total_batches}批")
        return batches
