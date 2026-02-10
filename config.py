# -*- coding: utf-8 -*-
"""配置管理模块"""

from pathlib import Path
import json
import copy
from typing import Optional
from datetime import datetime
from astrbot.api import logger


class ConfigManager:
    """配置管理器"""
    
    @staticmethod
    def _get_default_config() -> dict:
        """获取默认配置（每次返回新副本）"""
        return {
            "admin_qq": "",
            "target_groups": [],
            "trigger_keyword": "海梦酱你好鸭",
            "exchange_time": {
                "weekday": None,
                "hour": None
            },
            "enabled": True,
            "test_mode": False,
            "rate_limit_hours": 1,      # 预留：限流时间窗口（小时），待接入
            "spam_threshold": 5,         # 预留：刷屏阈值，待接入
            "stock_alert_threshold": 10,
            "skip_group_check": False,
            "session_timeout": 300,
        }
    
    def __init__(self, plugin_dir: Path):
        import threading
        self._lock = threading.RLock()
        self.config_file = plugin_dir / "config.json"
        self.config = self._load()
    
    def _load(self) -> dict:
        """加载配置（带备份自动恢复）"""
        from pathlib import Path
        backup_file = Path(str(self.config_file) + '.bak')
        
        # 尝试加载主文件
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                return self._deep_merge(self._get_default_config(), loaded)
            except json.JSONDecodeError as e:
                logger.error(f"[海梦酱] 配置文件格式错误: {e}，尝试从备份恢复...")
            except Exception as e:
                logger.error(f"[海梦酱] 加载配置失败: {e}，尝试从备份恢复...")
        
        # 尝试从备份恢复
        if backup_file.exists():
            try:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                
                # 恢复成功，修复主文件
                logger.warning("[海梦酱] ⚠️ 配置从备份恢复成功！")
                try:
                    import shutil
                    shutil.copy2(backup_file, self.config_file)
                    logger.info("[海梦酱] ✅ 配置主文件已从备份恢复")
                except Exception as e:
                    logger.error(f"[海梦酱] 修复配置主文件失败: {e}")
                
                return self._deep_merge(self._get_default_config(), loaded)
            except Exception as e:
                logger.error(f"[海梦酱] 配置备份也损坏: {e}")
        
        return self._get_default_config()
    
    def _deep_merge(self, default: dict, loaded: dict) -> dict:
        """深度合并配置（使用深拷贝）"""
        result = copy.deepcopy(default)
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value) if isinstance(value, (dict, list)) else value
        return result
    
    def save(self):
        """保存配置（原子写入）"""
        import tempfile
        import os
        
        # 写入临时文件
        dir_path = self.config_file.parent
        fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix='config_', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            
            if os.name == 'nt':  # Windows 备份策略
                backup_path = str(self.config_file) + '.bak'
                if self.config_file.exists():
                    try:
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        os.rename(self.config_file, backup_path)
                    except OSError as e:
                        logger.warning(f"[海梦酱] 配置备份失败: {e}")
                
                os.rename(temp_path, self.config_file)
                
                # 注意：不删除备份文件，_load() 依赖 .bak 做异常恢复
            else:  # Unix
                os.replace(temp_path, self.config_file)
                
        except Exception as e:
            logger.error(f"[海梦酱] 保存配置失败: {e}")
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass
            raise
    
    def get(self, key: str, default=None):
        """获取配置项（线程安全）"""
        with self._lock:
            keys = key.split('.')
            value = self.config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
    
    def set(self, key: str, value):
        """设置配置项（线程安全）"""
        with self._lock:
            keys = key.split('.')
            config = self.config
            for k in keys[:-1]:
                if k not in config:
                    config[k] = {}
                config = config[k]
            config[keys[-1]] = value
            self.save()
    
    def is_admin(self, qq: str) -> bool:
        """检查是否是管理员"""
        with self._lock:
            return str(qq) == str(self.config.get("admin_qq", ""))
    
    def is_enabled(self) -> bool:
        """检查插件是否启用"""
        with self._lock:
            return self.config.get("enabled", True)
    
    def is_test_mode(self) -> bool:
        """检查是否测试模式"""
        with self._lock:
            return self.config.get("test_mode", False)
    
    def get_trigger_keyword(self) -> str:
        """获取触发词"""
        with self._lock:
            return self.config.get("trigger_keyword", "海梦酱你好鸭")
    
    def get_target_groups(self) -> list:
        """获取目标群列表"""
        with self._lock:
            groups = self.config.get("target_groups", [])
            return [str(g) for g in groups] if isinstance(groups, list) else []
    
    def is_in_exchange_time(self) -> bool:
        """检查是否在发放时间内"""
        with self._lock:
            exchange_time = self.config.get("exchange_time", {})
            weekday = exchange_time.get("weekday")
            hour = exchange_time.get("hour")
            
            if weekday is None or hour is None:
                return False
            
            # 校验合法性
            try:
                weekday = int(weekday)
                hour = int(hour)
                if not (0 <= weekday <= 6) or not (0 <= hour <= 23):
                    return False
            except (ValueError, TypeError):
                return False
            
            now = datetime.now()
            return now.weekday() == weekday and now.hour >= hour
    
    def get_exchange_time_str(self) -> str:
        """获取发放时间字符串"""
        with self._lock:
            exchange_time = self.config.get("exchange_time", {})
            weekday = exchange_time.get("weekday")
            hour = exchange_time.get("hour")
            
            if weekday is None or hour is None:
                return "暂未设置"
            
            weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            try:
                weekday = int(weekday)
                hour = int(hour)
                if not (0 <= weekday <= 6) or not (0 <= hour <= 23):
                    return "配置异常，请重新设置"
                return f"每{weekdays[weekday]} {hour}:00 - 24:00"
            except (ValueError, TypeError):
                return "配置异常，请重新设置"

