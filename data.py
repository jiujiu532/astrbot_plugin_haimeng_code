# -*- coding: utf-8 -*-
"""数据管理模块 - 重构版

所有数据操作都通过本模块的公共方法进行，确保：
1. 线程安全（统一加锁）
2. 原子写入（临时文件替换）
3. 事务完整性（判资格+扣库存+记账 一体化）
"""

from pathlib import Path
import json
import copy
import threading
import tempfile
import os
from typing import Optional, Tuple, List
from datetime import datetime, timedelta
from astrbot.api import logger


class DataManager:
    """数据管理器 - 线程安全的数据操作"""
    
    # 使用类方法获取默认数据，避免浅拷贝污染
    @staticmethod
    def _get_default_structure() -> dict:
        """获取默认数据结构（每次返回新副本）"""
        return {
            "registration_codes": {"unused": [], "used": {}},
            "lottery_pool": {
                "gold": {"unused": [], "used": {}},
                "purple": {"unused": [], "used": {}},
                "blue": {"unused": [], "used": {}}
            },
            "event_pool": {
                "enabled": False,
                "name": "",
                "end_time": "",
                "cards": {"unused": [], "used": {}}
            },
            "lottery_config": {
                "gold_weight": 5,
                "purple_weight": 20,
                "blue_weight": 75,
                "event_weight": 10,
                "pity_threshold": 10,
                "pity_tier": "purple",
                "daily_limit": 0,
                "weekly_limit": 1
            },
            "lottery_history": [],
            "user_lottery": {},
            "registered_users": {},
            "weekly_claims": {},   # 预留：周领取记录，待接入
            "blacklist": [],
            "rate_limit": {},     # 预留：限流记录，待接入
            "spam_count": {},     # 预留：刷屏计数，待接入
            "logs": [],
            "announcement": {"content": "", "time": ""}
        }
    
    # 卡片档次信息
    TIER_INFO = {
        "gold": {"name": "金卡", "icon": "🥇", "color": "金色"},
        "purple": {"name": "紫卡", "icon": "💜", "color": "紫色"},
        "blue": {"name": "蓝卡", "icon": "💙", "color": "蓝色"},
        "event": {"name": "活动卡", "icon": "🎪", "color": "彩色"}
    }
    
    @staticmethod
    def _parse_naive_datetime(time_str: str):
        """解析时间字符串为 naive datetime（剥离时区信息，防止 naive/aware 比较异常）
        
        支持格式：YYYY-MM-DD / YYYY-MM-DDTHH:MM:SS / 带时区的 ISO 格式
        纯日期自动补到当天 23:59:59
        返回 (datetime, 是否成功) 元组
        """
        try:
            dt = datetime.fromisoformat(time_str)
            # 如果是 aware datetime，剥离时区信息保留本地时间
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            # 纯日期格式补到当天末尾
            if len(time_str) <= 10:
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt, True
        except (ValueError, TypeError):
            return None, False
    
    def __init__(self, plugin_dir: Path):
        self.data_file = plugin_dir / "data.json"
        self.plugin_dir = plugin_dir
        
        # 主锁 - 保护所有数据操作
        self._lock = threading.RLock()  # 使用可重入锁
        
        # 加载数据
        self.data = self._load()
    
    def _load(self) -> dict:
        """
        加载数据（带备份自动恢复）
        
        恢复链路：
        1. 尝试加载主文件
        2. 主文件不存在或损坏 → 尝试加载.bak备份
        3. 备份恢复成功后自动修复主文件
        """
        backup_file = Path(str(self.data_file) + '.bak')
        
        # 尝试加载主文件
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                data = self._deep_merge(self._get_default_structure(), loaded)
                # 确保黑名单是 set
                if isinstance(data.get("blacklist"), list):
                    data["blacklist"] = set(data["blacklist"])
                else:
                    data["blacklist"] = set()
                self._migrate_used_index(data)
                self._validate_schema(data)
                return data
            except json.JSONDecodeError as e:
                logger.error(f"[海梦酱] 数据文件格式错误: {e}，尝试从备份恢复...")
            except Exception as e:
                logger.error(f"[海梦酱] 加载数据失败: {e}，尝试从备份恢复...")
        else:
            # 主文件不存在，检查是否有备份
            if backup_file.exists():
                logger.warning("[海梦酱] 主数据文件缺失，尝试从备份恢复...")
        
        # 尝试从备份恢复
        if backup_file.exists():
            try:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                data = self._deep_merge(self._get_default_structure(), loaded)
                if isinstance(data.get("blacklist"), list):
                    data["blacklist"] = set(data["blacklist"])
                else:
                    data["blacklist"] = set()
                self._migrate_used_index(data)
                self._validate_schema(data)
                
                # 备份恢复成功，修复主文件
                logger.warning("[海梦酱] ⚠️ 从备份恢复成功！正在修复主文件...")
                try:
                    import shutil
                    shutil.copy2(backup_file, self.data_file)
                    logger.info("[海梦酱] ✅ 主文件已从备份恢复")
                except Exception as e:
                    logger.error(f"[海梦酱] 修复主文件失败: {e}")
                
                return data
            except Exception as e:
                logger.error(f"[海梦酱] 备份文件也损坏: {e}")
        
        # 返回默认数据
        logger.warning("[海梦酱] 使用默认数据结构初始化")
        data = self._get_default_structure()
        data["blacklist"] = set()
        return data
    
    def _migrate_used_index(self, data: dict):
        """
        迁移旧版 used 索引：qq->code → code->{qq,time}
        
        旧格式: {"123456": "CODE001"}   (qq是key, code是value)
        新格式: {"CODE001": {"qq": "123456", "time": "..."}}  (code是key)
        
        检测方式: 如果value是str则为旧格式，如果value是dict则已是新格式
        """
        migrated = False
        now_str = datetime.now().isoformat()
        
        # 迁移注册码 used
        reg_used = data.get("registration_codes", {}).get("used", {})
        if reg_used:
            new_reg_used = {}
            for k, v in reg_used.items():
                if isinstance(v, str):
                    # 旧格式: k=qq, v=code → 转换为 code->{qq,time}
                    new_reg_used[v] = {"qq": k, "time": now_str}
                    migrated = True
                elif isinstance(v, dict):
                    # 已是新格式: k=code, v={qq,time}
                    new_reg_used[k] = v
                else:
                    new_reg_used[k] = v
            data["registration_codes"]["used"] = new_reg_used
        
        # 迁移抽奖码 used (gold/purple/blue)
        for tier in ["gold", "purple", "blue"]:
            pool = data.get("lottery_pool", {}).get(tier, {})
            tier_used = pool.get("used", {})
            if tier_used:
                new_tier_used = {}
                for k, v in tier_used.items():
                    if isinstance(v, str):
                        new_tier_used[v] = {"qq": k, "time": now_str}
                        migrated = True
                    elif isinstance(v, dict):
                        new_tier_used[k] = v
                    else:
                        new_tier_used[k] = v
                pool["used"] = new_tier_used
        
        # 迁移活动卡 used
        event_used = data.get("event_pool", {}).get("cards", {}).get("used", {})
        if event_used:
            new_event_used = {}
            for k, v in event_used.items():
                if isinstance(v, str):
                    new_event_used[v] = {"qq": k, "time": now_str}
                    migrated = True
                elif isinstance(v, dict):
                    new_event_used[k] = v
                else:
                    new_event_used[k] = v
            data["event_pool"]["cards"]["used"] = new_event_used
        
        if migrated:
            logger.info("[海梦酱] ✅ 已自动迁移旧版 used 索引到新格式（code->info）")
    
    def _validate_schema(self, data: dict):
        """启动时轻量 schema 校验：关键字段类型/范围修正，非法值回退默认并告警"""
        defaults = self._get_default_structure()
        config = data.get("lottery_config", {})
        default_config = defaults["lottery_config"]
        
        # 整数且 >= 1 的字段
        int_min1_fields = [
            "gold_weight", "purple_weight", "blue_weight", "event_weight", "pity_threshold"
        ]
        for field in int_min1_fields:
            val = config.get(field)
            try:
                val = int(val)
                if val < 1:
                    raise ValueError
                config[field] = val
            except (TypeError, ValueError):
                old_val = config.get(field)
                config[field] = default_config[field]
                logger.warning(f"[海梦酱] schema校验: lottery_config.{field}={old_val!r} 非法，回退为 {config[field]}")
        
        # 整数且 >= 0 的字段
        int_min0_fields = ["weekly_limit", "daily_limit"]
        for field in int_min0_fields:
            val = config.get(field)
            try:
                val = int(val)
                if val < 0:
                    raise ValueError
                config[field] = val
            except (TypeError, ValueError):
                old_val = config.get(field)
                config[field] = default_config[field]
                logger.warning(f"[海梦酱] schema校验: lottery_config.{field}={old_val!r} 非法，回退为 {config[field]}")
        
        # pity_tier 必须是有效档次
        valid_tiers = {"gold", "purple", "blue", "event"}
        if config.get("pity_tier") not in valid_tiers:
            old_val = config.get("pity_tier")
            config["pity_tier"] = default_config["pity_tier"]
            logger.warning(f"[海梦酱] schema校验: lottery_config.pity_tier={old_val!r} 非法，回退为 {config['pity_tier']}")
        
        data["lottery_config"] = config
        
        # event_pool.enabled 必须是 bool
        ep = data.get("event_pool", {})
        if not isinstance(ep.get("enabled"), bool):
            ep["enabled"] = False
            logger.warning("[海梦酱] schema校验: event_pool.enabled 类型异常，回退为 False")
    
    def _deep_merge(self, default: dict, loaded: dict) -> dict:
        """深度合并（使用深拷贝避免污染）"""
        result = copy.deepcopy(default)
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value) if isinstance(value, (dict, list)) else value
        return result
    
    def _save_atomic(self):
        """
        原子写入数据文件
        
        Windows策略：原文件 -> 备份 -> 新文件写入 -> 删备份
        Unix策略：临时文件 -> os.replace 原子替换
        """
        data_to_save = copy.deepcopy(self.data)
        
        # 转换 set 为 list
        if isinstance(data_to_save.get("blacklist"), set):
            data_to_save["blacklist"] = list(data_to_save["blacklist"])
        
        # 写入临时文件
        fd, temp_path = tempfile.mkstemp(
            dir=self.plugin_dir, 
            prefix='data_', 
            suffix='.tmp'
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
            
            if os.name == 'nt':  # Windows - 使用备份策略
                backup_path = str(self.data_file) + '.bak'
                
                # 1. 原文件存在则先备份（保留备份供异常恢复）
                if self.data_file.exists():
                    try:
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        os.rename(self.data_file, backup_path)
                    except OSError as e:
                        logger.warning(f"[海梦酱] 备份失败，尝试直接替换: {e}")
                
                # 2. 临时文件重命名为目标文件
                os.rename(temp_path, self.data_file)
                
                # 注意：不删除备份文件，_load() 依赖 .bak 做异常恢复
                    
            else:  # Unix - os.replace 原子替换
                os.replace(temp_path, self.data_file)
                
        except Exception as e:
            logger.error(f"[海梦酱] 保存数据失败: {e}")
            # 清理临时文件
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
            raise
    
    def save(self):
        """保存数据（加锁 + 原子写入）"""
        with self._lock:
            self._save_atomic()
    
    # ==================== 注册码 - 原子事务 ====================
    
    def try_register_user(self, qq: str, test_mode: bool = False) -> Tuple[bool, str, Optional[str]]:
        """
        尝试注册用户（原子事务：判资格 + 扣库存 + 记账）
        
        Returns:
            (成功, 消息, 注册码)
        """
        with self._lock:
            # 1. 检查是否已注册
            if qq in self.data["registered_users"]:
                info = self.data["registered_users"][qq]
                return False, "already_registered", info.get("reg_code")
            
            # 2. 获取注册码
            now = datetime.now()
            if test_mode:
                code = f"TEST-REG-{qq}"
            else:
                unused = self.data["registration_codes"]["unused"]
                if not unused:
                    return False, "no_stock", None
                code = unused.pop(0)
            
            # 3. 记录注册（用 code -> info 索引，确保已发码全集完整）
            self.data["registration_codes"]["used"][code] = {"qq": qq, "time": now.isoformat()}
            self.data["registered_users"][qq] = {
                "reg_code": code,
                "reg_time": now.isoformat(),
                "imported": False
            }
            
            # 4. 保存
            self._save_atomic()
            
            return True, "success", code
    
    def is_registered(self, qq: str) -> bool:
        """检查是否已注册"""
        with self._lock:
            return qq in self.data["registered_users"]
    
    def get_user_info(self, qq: str) -> Optional[dict]:
        """获取用户信息"""
        with self._lock:
            info = self.data["registered_users"].get(qq)
            return copy.deepcopy(info) if info else None
    
    # ==================== 抽奖 - 完整原子事务 ====================
    
    def try_lottery_draw_atomic(self, qq: str, test_mode: bool = False) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        完整抽奖原子事务：资格检查 + 档次决定 + 扣库存 + 记账
        
        所有操作在同一个锁内完成，防止并发超发
        
        Args:
            qq: 用户QQ
            test_mode: 测试模式
            
        Returns:
            (成功, 状态/原因, 档次, 兑换码)
        """
        with self._lock:
            now = datetime.now()
            today = now.date().isoformat()
            config = self.data["lottery_config"]
            
            # ========== 1. 资格检查（在锁内）==========
            
            # 获取或初始化用户数据
            if qq not in self.data["user_lottery"]:
                self.data["user_lottery"][qq] = {
                    "pity_count": 0, "total_draws": 0,
                    "week_draws": 0, "day_draws": 0,
                    "last_draw": "", "last_draw_date": ""
                }
            
            user_data = self.data["user_lottery"][qq]
            
            # 重置日计数
            if user_data.get("last_draw_date") != today:
                user_data["day_draws"] = 0
            
            # 检查是否新的一周
            last_draw = user_data.get("last_draw")
            if last_draw:
                try:
                    last_draw_dt = datetime.fromisoformat(last_draw)
                    last_monday = last_draw_dt - timedelta(days=last_draw_dt.weekday())
                    this_monday = now - timedelta(days=now.weekday())
                    if last_monday.date() < this_monday.date():
                        user_data["week_draws"] = 0
                except ValueError:
                    pass
            
            # 检查周限制
            weekly_limit = config.get("weekly_limit", 1)
            if weekly_limit > 0 and user_data.get("week_draws", 0) >= weekly_limit:
                return False, "本周抽奖次数已用完", None, None
            
            # 检查日限制
            daily_limit = config.get("daily_limit", 0)
            if daily_limit > 0 and user_data.get("day_draws", 0) >= daily_limit:
                return False, "今日抽奖次数已用完", None, None
            
            # ========== 2. 检查库存（事务内实时校验活动卡到期）==========
            
            # 事务内实时判断活动卡是否有效（防止确认到扣码之间到期）
            event_available = False
            if self.data["event_pool"]["enabled"]:
                end_time = self.data["event_pool"]["end_time"]
                if end_time:
                    end_dt, ok = self._parse_naive_datetime(end_time)
                    if ok and datetime.now() <= end_dt:
                        event_available = True
                    elif not ok:
                        # 解析失败 → fail-close
                        self.data["event_pool"]["enabled"] = False
                    else:
                        # 已过期，同步关闭
                        self.data["event_pool"]["enabled"] = False
                else:
                    event_available = True  # 无结束时间 = 手动关闭前有效
            
            pools = {
                "gold": len(self.data["lottery_pool"]["gold"]["unused"]),
                "purple": len(self.data["lottery_pool"]["purple"]["unused"]),
                "blue": len(self.data["lottery_pool"]["blue"]["unused"]),
                "event": len(self.data["event_pool"]["cards"]["unused"]) if event_available else 0
            }
            
            total_stock = pools["gold"] + pools["purple"] + pools["blue"] + pools["event"]
            if total_stock == 0:
                return False, "奖池已空，请联系久补充~", None, None
            
            # ========== 3. 决定档次（保底或随机）==========
            
            pity_threshold = config.get("pity_threshold", 10)
            pity_tier = config.get("pity_tier", "purple")
            
            pity_triggered = user_data.get("pity_count", 0) >= pity_threshold
            tier = None
            
            if pity_triggered:
                # 保底触发 → 向上降级策略：
                # 1. 尝试保底档次（默认purple）
                # 2. 保底档缺货 → 尝试更高档（gold）
                # 3. 全部缺货 → 尝试event
                # 绝不回落蓝卡！
                pity_fallback_order = []
                if pity_tier == "purple":
                    pity_fallback_order = ["purple", "gold", "event"]
                elif pity_tier == "gold":
                    pity_fallback_order = ["gold", "event"]
                else:
                    pity_fallback_order = [pity_tier, "gold", "event"]
                
                for candidate in pity_fallback_order:
                    if pools.get(candidate, 0) > 0:
                        tier = candidate
                        break
                
                if not tier:
                    # 所有非蓝档均缺货，提示用户
                    return False, "保底触发但高档卡已售罄，请联系久补充~", None, None
            else:
                tier = self._weighted_random_internal(pools, config)
            
            if not tier:
                return False, "抽奖失败，请重试", None, None
            
            # ========== 4. 取码 ==========
            
            if test_mode:
                code = f"TEST-{tier.upper()}-{qq}-{now.strftime('%H%M%S')}"
            else:
                if tier == "event":
                    pool = self.data["event_pool"]["cards"]
                else:
                    pool = self.data["lottery_pool"][tier]
                
                if not pool["unused"]:
                    return False, "no_stock", None, None
                
                code = pool["unused"].pop(0)
                # 改为 code -> {qq, time}，确保已发码全集完整，不会被覆盖
                pool["used"][code] = {"qq": qq, "time": now.isoformat()}
            
            # ========== 5. 更新用户数据（test_mode也记账）==========
            
            user_data["total_draws"] += 1
            user_data["week_draws"] = user_data.get("week_draws", 0) + 1
            user_data["day_draws"] = user_data.get("day_draws", 0) + 1
            user_data["last_draw"] = now.isoformat()
            user_data["last_draw_date"] = today
            
            # 更新保底计数
            if tier == "blue":
                user_data["pity_count"] = user_data.get("pity_count", 0) + 1
            else:
                user_data["pity_count"] = 0
            
            # ========== 6. 记录历史（脱敏）==========
            
            self.data["lottery_history"].insert(0, {
                "qq": qq,
                "tier": tier,
                "code_hash": code[:4] + "****" if not test_mode else "TEST****",
                "time": now.isoformat()
            })
            self.data["lottery_history"] = self.data["lottery_history"][:100]
            
            # ========== 7. 保存 ==========
            # test_mode 保存次数数据（防重启重置），但不消耗真实码
            # 因为test_mode取的是假码，真实库存未变
            self._save_atomic()
            
            return True, "success", tier, code
    
    def _weighted_random_internal(self, pools: dict, config: dict) -> Optional[str]:
        """内部加权随机（供原子事务调用，不加锁）"""
        import random
        
        weights = {}
        
        # 活动卡池（权重从config读取，与展示一致）
        if pools.get("event", 0) > 0 and self.data["event_pool"]["enabled"]:
            weights["event"] = max(1, int(config.get("event_weight", 10) or 1))
        
        if pools.get("gold", 0) > 0:
            weights["gold"] = max(1, int(config.get("gold_weight", 5) or 1))
        if pools.get("purple", 0) > 0:
            weights["purple"] = max(1, int(config.get("purple_weight", 20) or 1))
        if pools.get("blue", 0) > 0:
            weights["blue"] = max(1, int(config.get("blue_weight", 75) or 1))
        
        if not weights:
            return None
        
        total = sum(weights.values())
        if total <= 0:
            # 理论上不会到这里（已clamp），但做最终防线
            return list(weights.keys())[0]
        
        r = random.randint(1, total)
        
        cumulative = 0
        for tier, weight in weights.items():
            cumulative += weight
            if r <= cumulative:
                return tier
        
        # 兜底：浮点精度问题时返回最后一个
        return list(weights.keys())[-1]
    
    def can_draw_lottery(self, qq: str) -> Tuple[bool, str]:
        """检查用户是否可以抽奖（仅用于UI展示，实际抽奖使用try_lottery_draw_atomic）"""
        with self._lock:
            config = self.data["lottery_config"]
            now = datetime.now()
            today = now.date().isoformat()
            
            if qq not in self.data["user_lottery"]:
                return True, ""
            
            user_data = self.data["user_lottery"][qq]
            
            # 检查日计数重置
            if user_data.get("last_draw_date") != today:
                day_draws = 0
            else:
                day_draws = user_data.get("day_draws", 0)
            
            # 检查周计数重置
            week_draws = user_data.get("week_draws", 0)
            last_draw = user_data.get("last_draw")
            if last_draw:
                try:
                    last_draw_dt = datetime.fromisoformat(last_draw)
                    last_monday = last_draw_dt - timedelta(days=last_draw_dt.weekday())
                    this_monday = now - timedelta(days=now.weekday())
                    if last_monday.date() < this_monday.date():
                        week_draws = 0
                except ValueError:
                    pass
            
            # 检查周限制
            weekly_limit = config.get("weekly_limit", 1)
            if weekly_limit > 0 and week_draws >= weekly_limit:
                return False, "本周抽奖次数已用完"
            
            # 检查日限制
            daily_limit = config.get("daily_limit", 0)
            if daily_limit > 0 and day_draws >= daily_limit:
                return False, "今日抽奖次数已用完"
            
            return True, ""
    
    def get_user_lottery_data(self, qq: str) -> dict:
        """获取用户抽奖数据"""
        with self._lock:
            if qq not in self.data["user_lottery"]:
                return {
                    "pity_count": 0, "total_draws": 0,
                    "week_draws": 0, "day_draws": 0
                }
            return copy.deepcopy(self.data["user_lottery"][qq])
    
    def get_all_pool_counts(self) -> dict:
        """获取所有档次的库存数量"""
        with self._lock:
            return {
                "gold": len(self.data["lottery_pool"]["gold"]["unused"]),
                "purple": len(self.data["lottery_pool"]["purple"]["unused"]),
                "blue": len(self.data["lottery_pool"]["blue"]["unused"]),
                "event": len(self.data["event_pool"]["cards"]["unused"]) if self.data["event_pool"]["enabled"] else 0
            }
    
    def get_lottery_config(self) -> dict:
        """获取抽奖配置（副本）"""
        with self._lock:
            return copy.deepcopy(self.data["lottery_config"])
    
    def update_lottery_config(self, key: str, value) -> bool:
        """更新抽奖配置"""
        with self._lock:
            if key in self.data["lottery_config"]:
                self.data["lottery_config"][key] = value
                self._save_atomic()
                return True
            return False
    
    def get_lottery_history(self, limit: int = 10) -> list:
        """获取抽奖历史"""
        with self._lock:
            return copy.deepcopy(self.data["lottery_history"][:limit])
    
    # ==================== 活动卡池 ====================
    
    def set_event_pool(self, name: str, end_time: str) -> bool:
        """设置活动卡池"""
        with self._lock:
            self.data["event_pool"]["enabled"] = True
            self.data["event_pool"]["name"] = name
            self.data["event_pool"]["end_time"] = end_time
            self._save_atomic()
            return True
    
    def disable_event_pool(self) -> bool:
        """关闭活动卡池"""
        with self._lock:
            self.data["event_pool"]["enabled"] = False
            self._save_atomic()
            return True
    
    def is_event_pool_active(self) -> bool:
        """检查活动卡池是否激活"""
        with self._lock:
            if not self.data["event_pool"]["enabled"]:
                return False
            
            end_time = self.data["event_pool"]["end_time"]
            if end_time:
                end_dt, ok = self._parse_naive_datetime(end_time)
                if not ok:
                    logger.warning(f"[海梦酱] 活动结束时间格式异常: {end_time}，视为已过期")
                    self.data["event_pool"]["enabled"] = False
                    self._save_atomic()
                    return False
                if datetime.now() > end_dt:
                    self.data["event_pool"]["enabled"] = False
                    self._save_atomic()
                    return False
            
            return True
    
    def get_event_pool_info(self) -> dict:
        """获取活动卡池信息"""
        with self._lock:
            return {
                "enabled": self.data["event_pool"]["enabled"],
                "name": self.data["event_pool"]["name"],
                "end_time": self.data["event_pool"]["end_time"],
                "stock": len(self.data["event_pool"]["cards"]["unused"])
            }
    
    def _is_code_globally_used(self, code: str) -> bool:
        """全局码查重：检查码是否已存在于任何池（调用者已持有锁）"""
        # 注册码池
        reg = self.data["registration_codes"]
        if code in reg["unused"] or code in reg["used"]:
            return True
        # 抽奖码池（金/紫/蓝）
        for tier in ["gold", "purple", "blue"]:
            pool = self.data["lottery_pool"][tier]
            if code in pool["unused"] or code in pool["used"]:
                return True
        # 活动卡池
        event = self.data["event_pool"]["cards"]
        if code in event["unused"] or code in event["used"]:
            return True
        return False
    
    def add_event_codes(self, codes: List[str]) -> dict:
        """添加活动卡码（全局去重）"""
        with self._lock:
            pool = self.data["event_pool"]["cards"]
            added = 0
            skipped = 0
            
            for code in codes:
                code = code.strip()
                if not code:
                    continue
                if self._is_code_globally_used(code):
                    skipped += 1
                    continue
                pool["unused"].append(code)
                added += 1
            
            if added > 0:
                self._save_atomic()
            
            return {"added": added, "skipped": skipped}
    
    # ==================== 码管理 ====================
    
    def add_registration_codes(self, codes: List[str]) -> dict:
        """添加注册码（全局去重）"""
        with self._lock:
            pool = self.data["registration_codes"]
            added = 0
            skipped = 0
            
            for code in codes:
                code = code.strip()
                if not code:
                    continue
                if self._is_code_globally_used(code):
                    skipped += 1
                    continue
                pool["unused"].append(code)
                added += 1
            
            if added > 0:
                self._save_atomic()
            
            return {"added": added, "skipped": skipped}
    
    def add_lottery_codes(self, tier: str, codes: List[str]) -> dict:
        """添加抽奖码（全局去重）"""
        with self._lock:
            if tier not in ["gold", "purple", "blue"]:
                return {"added": 0, "skipped": 0, "error": "无效档次"}
            
            pool = self.data["lottery_pool"][tier]
            added = 0
            skipped = 0
            
            for code in codes:
                code = code.strip()
                if not code:
                    continue
                if self._is_code_globally_used(code):
                    skipped += 1
                    continue
                pool["unused"].append(code)
                added += 1
            
            if added > 0:
                self._save_atomic()
            
            return {"added": added, "skipped": skipped}
    
    def get_codes_preview(self, pool_type: str, tier: str = None, limit: int = 30) -> List[str]:
        """获取码预览（脱敏）"""
        with self._lock:
            if pool_type == "registration":
                codes = self.data["registration_codes"]["unused"][:limit]
            elif pool_type == "lottery" and tier:
                codes = self.data["lottery_pool"].get(tier, {}).get("unused", [])[:limit]
            elif pool_type == "event":
                codes = self.data["event_pool"]["cards"]["unused"][:limit]
            else:
                return []
            
            # 脱敏：显示前4后2，中间*
            result = []
            for code in codes:
                if len(code) > 8:
                    result.append(code[:4] + "****" + code[-2:])
                else:
                    result.append(code[:2] + "****")
            return result
    
    # ==================== 黑名单 ====================
    
    def is_blacklisted(self, qq: str) -> bool:
        """检查是否在黑名单"""
        with self._lock:
            blacklist = self.data["blacklist"]
            if isinstance(blacklist, list):
                blacklist = set(blacklist)
                self.data["blacklist"] = blacklist
            return qq in blacklist
    
    def add_to_blacklist(self, qq: str) -> bool:
        """添加到黑名单"""
        with self._lock:
            if isinstance(self.data["blacklist"], list):
                self.data["blacklist"] = set(self.data["blacklist"])
            self.data["blacklist"].add(qq)
            self._save_atomic()
            return True
    
    def remove_from_blacklist(self, qq: str) -> bool:
        """从黑名单移除"""
        with self._lock:
            if isinstance(self.data["blacklist"], list):
                self.data["blacklist"] = set(self.data["blacklist"])
            self.data["blacklist"].discard(qq)
            self._save_atomic()
            return True
    
    def get_blacklist(self) -> List[str]:
        """获取黑名单列表"""
        with self._lock:
            blacklist = self.data["blacklist"]
            if isinstance(blacklist, set):
                return list(blacklist)
            return list(blacklist) if blacklist else []
    
    def clear_blacklist(self) -> bool:
        """清空黑名单"""
        with self._lock:
            self.data["blacklist"] = set()
            self._save_atomic()
            return True
    
    # ==================== 公告 ====================
    
    def get_announcement(self) -> dict:
        """获取公告"""
        with self._lock:
            return copy.deepcopy(self.data.get("announcement", {"content": "", "time": ""}))
    
    def set_announcement(self, content: str) -> bool:
        """设置公告"""
        with self._lock:
            self.data["announcement"] = {
                "content": content,
                "time": datetime.now().isoformat()
            }
            self._save_atomic()
            return True
    
    def clear_announcement(self) -> bool:
        """清空公告"""
        with self._lock:
            self.data["announcement"] = {"content": "", "time": ""}
            self._save_atomic()
            return True
    
    # ==================== 用户管理 ====================
    
    def get_registered_users_count(self) -> int:
        """获取注册用户数"""
        with self._lock:
            return len(self.data["registered_users"])
    
    def get_registered_users_list(self, limit: int = 50) -> List[Tuple[str, dict]]:
        """获取注册用户列表"""
        with self._lock:
            items = list(self.data["registered_users"].items())[:limit]
            return [(qq, copy.deepcopy(info)) for qq, info in items]
    
    def get_all_registered_users(self) -> List[Tuple[str, dict]]:
        """获取全部注册用户列表（用于导出，无数量限制）"""
        with self._lock:
            items = list(self.data["registered_users"].items())
            return [(qq, copy.deepcopy(info)) for qq, info in items]
    
    def import_registered_users(self, qq_list: List[str]) -> dict:
        """批量导入已注册用户（标记为已注册，不消耗注册码）"""
        with self._lock:
            added = 0
            skipped = 0
            now = datetime.now().isoformat()
            
            for qq in qq_list:
                qq = qq.strip()
                if not qq:
                    continue
                if qq in self.data["registered_users"]:
                    skipped += 1
                    continue
                self.data["registered_users"][qq] = {
                    "reg_code": "已导入",
                    "reg_time": now
                }
                added += 1
            
            if added > 0:
                self._save_atomic()
            
            return {"added": added, "skipped": skipped}
    
    def reset_user_registration(self, qq: str) -> bool:
        """重置用户注册（保留 used 占用防止一码多发，标记 revoked）"""
        with self._lock:
            if qq in self.data["registered_users"]:
                user_info = self.data["registered_users"][qq]
                reg_code = user_info.get("reg_code")
                
                # 不删除 used 记录，而是标记 revoked 防止码被重新入库
                if reg_code and reg_code in self.data["registration_codes"]["used"]:
                    self.data["registration_codes"]["used"][reg_code]["revoked"] = True
                
                del self.data["registered_users"][qq]
                self._save_atomic()
                return True
            return False
    
    def reset_user_lottery_data(self, qq: str) -> bool:
        """重置用户抽奖数据"""
        with self._lock:
            if qq in self.data["user_lottery"]:
                self.data["user_lottery"][qq] = {
                    "pity_count": 0, "total_draws": 0,
                    "week_draws": 0, "day_draws": 0,
                    "last_draw": "", "last_draw_date": ""
                }
                self._save_atomic()
                return True
            return False
    
    # ==================== 日志（脱敏） ====================
    
    def log_action(self, action: str, qq: str, detail: str = ""):
        """记录操作日志（脱敏处理）"""
        with self._lock:
            # 脱敏：移除可能的码明文
            safe_detail = detail
            if len(detail) > 20:
                # 可能包含码，截断
                safe_detail = detail[:15] + "..."
            
            log_entry = {
                "time": datetime.now().isoformat(),
                "action": action,
                "qq": qq,
                "detail": safe_detail
            }
            self.data["logs"].insert(0, log_entry)
            self.data["logs"] = self.data["logs"][:500]
            
            # 审计日志即时落盘，防止异常退出丢失
            self._save_atomic()
    
    def get_logs(self, limit: int = 50) -> List[dict]:
        """获取日志"""
        with self._lock:
            return copy.deepcopy(self.data["logs"][:limit])
    
    # ==================== 统计 ====================
    
    def get_statistics(self) -> dict:
        """获取统计数据"""
        with self._lock:
            pools = self.get_all_pool_counts()
            
            # 统计抽奖次数
            tier_counts = {"gold": 0, "purple": 0, "blue": 0, "event": 0}
            for record in self.data["lottery_history"]:
                tier = record.get("tier", "")
                if tier in tier_counts:
                    tier_counts[tier] += 1
            
            return {
                "registered_users": len(self.data["registered_users"]),
                "registration_codes": {
                    "unused": len(self.data["registration_codes"]["unused"]),
                    "used": len(self.data["registration_codes"]["used"])
                },
                "lottery_pool": pools,
                "lottery_counts": tier_counts,
                "blacklist_count": len(self.data["blacklist"]),
                "total_lottery_draws": sum(
                    u.get("total_draws", 0) 
                    for u in self.data["user_lottery"].values()
                )
            }
    
    # ==================== 每周重置 ====================
    
    def weekly_reset(self):
        """每周重置"""
        with self._lock:
            for qq in self.data["user_lottery"]:
                self.data["user_lottery"][qq]["week_draws"] = 0
            
            self.data["weekly_claims"] = {}
            self._save_atomic()
            
            self.log_action("系统", "AUTO", "每周重置完成")
