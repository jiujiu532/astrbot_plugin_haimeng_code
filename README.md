# 🌸 海梦酱码管理系统 v2.2.0

> AstrBot 插件 - 智能抽奖发码系统

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![AstrBot](https://img.shields.io/badge/AstrBot-Plugin-green.svg)](https://github.com/Soulter/AstrBot)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📖 目录

- [功能特性](#-功能特性)
- [项目结构](#-项目结构)
- [安装部署](#-安装部署)
- [配置说明](#-配置说明)
- [使用指南](#-使用指南)
- [代码架构](#-代码架构)
- [并发安全机制](#-并发安全机制)
- [安全机制](#-安全机制)
- [API 参考](#-api-参考)
- [常见问题](#-常见问题)
- [更新日志](#-更新日志)
- [测试检查清单](#-测试检查清单)

---

## ✨ 功能特性

### 核心功能

| 功能 | 描述 |
|------|------|
| 🎫 **注册码发放** | 新用户专属，仅限领取一次，原子事务保证不会重复发放 |
| 🎰 **抽奖系统** | 金/紫/蓝三档卡池，加权随机，支持活动卡池 |
| 🎯 **保底机制** | 连续N次蓝卡后必出紫卡或以上，保底计数器持久化 |
| 📊 **统计分析** | 完整的抽奖记录和数据统计，日志脱敏处理 |
| 📢 **公告系统** | 发布活动公告，实时推送 |
| ⏰ **定时任务** | 每周一自动重置周抽奖次数 |

### 管理功能

| 功能 | 描述 |
|------|------|
| 🔧 **控制面板** | 管理员专属交互式面板，支持快捷命令 |
| 📦 **库存管理** | 添加/查看注册码和抽奖码，支持批量导入 |
| 👥 **用户管理** | 查询/重置用户数据，支持批量操作 |
| 🚫 **黑名单** | 封禁恶意用户，支持添加/移除/清空 |
| ⚙️ **抽奖配置** | 动态调整概率、保底阈值、每日/周限制 |

### 安全特性

| 特性 | 描述 |
|------|------|
| 🔒 **线程安全** | 使用 `threading.RLock()` 可重入锁保护所有数据操作 |
| 💾 **原子写入** | Windows备份策略 / Unix os.replace，防止写入中断导致数据损坏 |
| 🔐 **完整原子事务** | 抽奖全流程（资格检查+档次决定+扣库存+记账）在同一个锁内完成 |
| 🛡️ **群成员验证** | 双重验证机制（临时会话来源 + 带TTL的成员缓存） |
| 📝 **日志脱敏** | 兑换码不记录明文，历史记录固定 `code[:4]+"****"` |
| ⏱️ **缓存TTL** | 群成员缓存默认30天过期，防止历史成员绕过验证 |

---

## 📁 项目结构

```
astrbot_plugin_haimeng_code/
│
├── main.py                 # 插件入口，消息路由，定时任务，群消息监听
├── config.py               # 配置管理（深拷贝保护）
├── data.py                 # 数据管理（原子事务，原子写入，线程安全）
├── metadata.yaml           # 插件元信息
├── README.md               # 本文档
│
├── handlers/               # 消息处理器
│   ├── __init__.py         # 模块导出
│   ├── user.py             # 用户消息处理（菜单、抽奖、查询）
│   └── admin.py            # 管理员消息处理（控制面板、状态机）
│
├── lottery/                # 抽奖模块
│   ├── __init__.py         # 模块导出
│   └── engine.py           # 抽奖引擎（调用DataManager原子事务）
│
├── utils/                  # 工具模块
│   ├── __init__.py         # 模块导出
│   ├── session.py          # 会话状态管理
│   ├── templates.py        # 消息模板
│   └── group_manager.py    # 群成员管理（带TTL缓存）与验证
│
├── config.json             # 配置文件（需手动创建）
├── data.json               # 数据存储（自动生成）
├── data.json.bak           # Windows写入时的备份文件（自动生成，保留供异常恢复）
└── group_members.json      # 群成员缓存（自动生成，带TTL）
```

---

## 🚀 安装部署

### 1. 下载插件

将整个 `astrbot_plugin_haimeng_code` 文件夹放入 AstrBot 的插件目录：

```
AstrBot/
└── addons/
    └── plugins/
        └── astrbot_plugin_haimeng_code/   ← 放这里
```

### 2. 创建配置文件

在插件目录创建 `config.json`：

```json
{
  "admin_qq": "你的QQ号",
  "target_groups": ["目标群号1", "目标群号2"],
  "trigger_keyword": "海梦酱你好鸭",
  "exchange_time": {
    "weekday": 6,
    "hour": 9
  },
  "enabled": true,
  "test_mode": false,
  "skip_group_check": false,
  "session_timeout": 300,
  "stock_alert_threshold": 10
}
```

### 3. 重启 AstrBot

```bash
# 重启后查看日志确认加载成功
[海梦酱] 插件加载成功！v2.2.0
[海梦酱] 群成员管理器已启动（监听模式，TTL=30天），已缓存 0 人
```

### 4. 初始化库存

私聊机器人发送 `jiu` 进入管理面板，添加码：

```
jiu
↓
2（添加抽奖码）
↓
G（金卡）/ P（紫卡）/ B（蓝卡）
↓
粘贴码列表（每行一个）
```

---

## ⚙️ 配置说明

### config.json 完整配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `admin_qq` | string | - | **必填** 管理员QQ号 |
| `target_groups` | array | [] | 目标群号列表，用于群成员验证 |
| `trigger_keyword` | string | "海梦酱你好鸭" | 用户触发词 |
| `exchange_time.weekday` | int | null | 发放日（0=周一，6=周日） |
| `exchange_time.hour` | int | null | 开始时间（0-23） |
| `enabled` | bool | true | 插件开关 |
| `test_mode` | bool | false | 测试模式（不消耗真实码，但会计入次数限制） |
| `skip_group_check` | bool | false | 跳过群成员验证 |
| `session_timeout` | int | 300 | 会话超时秒数 |
| `stock_alert_threshold` | int | 10 | 库存预警阈值 |

### 抽奖配置（存储在 data.json）

| 配置项 | 默认值 | 说明 | 修改命令 |
|--------|--------|------|----------|
| `gold_weight` | 5 | 金卡权重（最小1） | `10-G 5` |
| `purple_weight` | 20 | 紫卡权重（最小1） | `10-P 20` |
| `blue_weight` | 75 | 蓝卡权重（最小1） | `10-B 75` |
| `event_weight` | 10 | 活动卡权重（最小1） | `10-E 10` |
| `pity_threshold` | 10 | 保底阈值（连续N次蓝卡触发保底） | `10-T 10` |
| `pity_tier` | "purple" | 保底档次（gold/purple/blue/event） | - |
| `weekly_limit` | 1 | 每周抽奖限制 | `10-W 1` |
| `daily_limit` | 0 | 每日抽奖限制（0=不限） | `10-D 0` |

### 概率计算说明

```
概率 = 档次权重 / 有库存档次权重之和

例如：gold_weight=5, purple_weight=20, blue_weight=75

情况1：全部有库存
  金卡概率 = 5 / (5+20+75) = 5%
  紫卡概率 = 20 / 100 = 20%
  蓝卡概率 = 75 / 100 = 75%

情况2：金卡缺货
  紫卡概率 = 20 / (20+75) ≈ 21%
  蓝卡概率 = 75 / 95 ≈ 79%
```

---

## 📚 使用指南

### 用户使用

#### 触发菜单

私聊机器人发送触发词（默认：`海梦酱你好鸭`）

```
🌸 你好鸭！欢迎来到海梦家族~

请选择你想要的服务：

1️⃣ 获取注册码（新用户专属）
2️⃣ 🎰 幸运抽奖（每周限量）
3️⃣ 查看奖池信息
4️⃣ 查看我的信息
5️⃣ 最新公告
6️⃣ 帮助说明
```

#### 抽奖流程

```
用户: 2
机器人: [奖池信息] 回复 GO 开始抽奖

用户: GO
机器人: 🎰 正在抽奖...
        🎉 恭喜你抽中了 💜【紫卡】！
        你的兑换码: PURPLE001
```

### 管理员使用

#### 打开控制面板

私聊发送 `jiu`

```
🔧 【久控制面板】

📦 码管理:
1️⃣ 添加注册码
2️⃣ 添加抽奖码
3️⃣ 查看库存

📊 数据管理:
4️⃣ 用户管理
5️⃣ 数据统计
6️⃣ 黑名单管理

⚙️ 系统设置:
7️⃣ 发放时间设置
8️⃣ 公告管理
9️⃣ 系统状态
🔟 抽奖配置
```

#### 快捷命令

| 命令 | 说明 |
|------|------|
| `jiu` | 打开控制面板 |
| `jiu状态` | 查看系统状态 |
| `jiu库` | 查看库存 |
| `jiu统计` | 查看统计 |
| `jiu记录` | 查看抽奖记录（脱敏） |
| `jiu开启` | 开启插件 |
| `jiu关闭` | 关闭插件 |
| `jiu测试` | 切换测试模式 |
| `jiu帮助` | 查看帮助 |

#### 快捷添加码

```
jiu金卡
CODE001
CODE002
CODE003
```

#### 子菜单操作（进入对应菜单后使用）

**库存菜单（选择3后）：**

| 命令 | 说明 |
|------|------|
| `3-G` | 查看金卡列表（脱敏） |
| `3-P` | 查看紫卡列表（脱敏） |
| `3-B` | 查看蓝卡列表（脱敏） |
| `3-R` | 查看注册码列表（脱敏） |

**用户菜单（选择4后）：**

| 命令 | 说明 |
|------|------|
| `4-1` | 查看用户列表 |
| `4-2 QQ号` | 查询指定用户 |
| `4-3 QQ号` | 重置用户注册 |
| `4-4 QQ号` | 清空用户抽奖数据 |

**黑名单菜单（选择6后）：**

| 命令 | 说明 |
|------|------|
| `6-1 QQ号` | 添加黑名单 |
| `6-2 QQ号` | 移除黑名单 |
| `6-3` | 清空黑名单 |

**时间菜单（选择7后）：**

| 命令 | 说明 |
|------|------|
| `7-1 周日` | 设置发放日 |
| `7-2 9` | 设置发放时间 |

**公告菜单（选择8后）：**

| 命令 | 说明 |
|------|------|
| `8-1` | 设置公告（进入编辑模式） |
| `8-2` | 清空公告 |

**抽奖配置菜单（选择10后）：**

| 命令 | 说明 |
|------|------|
| `10-G 数值` | 设置金卡权重 |
| `10-P 数值` | 设置紫卡权重 |
| `10-B 数值` | 设置蓝卡权重 |
| `10-T 数值` | 设置保底阈值 |
| `10-W 数值` | 设置每周限制 |
| `10-D 数值` | 设置每日限制 |

---

## 🏗️ 代码架构

### 模块职责

#### main.py - 插件入口

```python
@register("astrbot_plugin_haimeng_code", "久", "海梦酱码管理系统", "2.2.0")
class HaimengCodePlugin(Star):
    """
    职责：
    1. 初始化所有模块
    2. 消息路由（私聊/群聊分发）
    3. 定时任务调度（每周重置）
    4. 群消息监听（收集群成员，异常记录日志）
    """
```

#### config.py - 配置管理

```python
class ConfigManager:
    """
    职责：
    1. 加载/保存配置文件（JSON）
    2. 提供配置读取/写入接口
    3. 管理员权限验证
    4. 发放时间检查
    
    安全设计：
    - 使用 @staticmethod 方法返回默认配置，每次返回新副本
    - 使用 copy.deepcopy() 深度合并，防止污染
    - 配置加载异常记录日志
    """
```

#### data.py - 数据管理（核心模块）

```python
class DataManager:
    """
    职责：
    1. 数据持久化（JSON）
    2. 注册码/抽奖码/用户数据管理
    3. 统一的公共API接口（handlers不直接访问内部数据）
    
    并发安全设计：
    - 使用 threading.RLock() 可重入锁保护所有操作
    - 完整原子事务：try_lottery_draw_atomic()
    - 原子写入：_save_atomic()（Windows备份策略/Unix os.replace）
    
    数据保护设计：
    - 返回数据使用 copy.deepcopy() 防止外部修改污染
    - 默认数据结构使用 @staticmethod 方法返回新副本
    - 日志不记录明文码
    """
```

#### lottery/engine.py - 抽奖引擎

```python
class LotteryEngine:
    """
    职责：
    1. 调用 DataManager.try_lottery_draw_atomic() 执行抽奖
    2. 生成奖池信息（真实概率）
    3. 生成抽奖结果消息
    4. 生成抽奖历史消息
    
    v2.1 改进：
    - 不再自行实现加权随机和资格检查
    - 完全依赖 DataManager 的原子事务
    - 确保并发安全
    """
```

#### handlers/admin.py - 管理员处理

```python
class AdminHandler:
    """
    职责：
    1. 控制面板交互（状态机）
    2. 码管理（通过DataManager公共API）
    3. 用户管理（通过DataManager公共API）
    4. 系统配置（通过ConfigManager）
    
    v2.1 改进：
    - 完整的子菜单状态机处理
    - 状态：admin_menu, add_reg_codes, select_lottery_tier, add_lottery_*,
           set_announcement, stock_menu, user_menu, blacklist_menu,
           time_menu, announcement_menu, lottery_config_menu
    """
```

#### utils/group_manager.py - 群成员管理

```python
class GroupMemberManager:
    """
    职责：
    1. 监听群消息记录成员（被动收集）
    2. 群成员缓存持久化（带TTL）
    3. 成员查询
    
    v2.1 新增TTL机制：
    - 缓存格式：{群号: {成员QQ: 最后活跃时间}}
    - 默认TTL：30天
    - 启动时自动清理过期成员
    - is_group_member() 检查时验证TTL
    """

class GroupVerifier:
    """
    职责：双重验证用户群身份
    
    验证方式（优先级）：
    1. 临时会话来源（最准确，同时更新活跃时间）
    2. 群成员缓存（备选，带TTL检查）
    """
```

---

## 🔒 并发安全机制

### 1. 完整抽奖原子事务

**问题**：如果资格检查和抽奖分开执行，可能导致并发超发

**解决方案**：`try_lottery_draw_atomic()` 在同一个锁内完成全部操作

```python
def try_lottery_draw_atomic(self, qq: str, test_mode: bool = False):
    """完整抽奖原子事务"""
    with self._lock:
        # ========== 1. 资格检查（在锁内）==========
        # 初始化/重置用户数据
        # 检查周限制
        # 检查日限制
        
        # ========== 2. 检查库存 ==========
        # 计算各档次库存
        
        # ========== 3. 决定档次 ==========
        # 保底判断
        # 加权随机（缺货档次权重为0）
        
        # ========== 4. 取码 ==========
        # test_mode 返回 TEST-XXX-CODE
        # 正常模式从池中取码
        
        # ========== 5. 更新用户数据 ==========
        # test_mode 也计入次数（防止无限抽测试码）
        # 更新 total_draws, week_draws, day_draws
        # 更新保底计数
        
        # ========== 6. 记录历史 ==========
        # 脱敏：code[:4] + "****"
        
        # ========== 7. 保存 ==========
        # test_mode 不消耗真实码，但计次落盘
        
        return True, "success", tier, code
```

### 2. 原子写入

**问题**：写入过程中断电/崩溃可能导致数据损坏

**解决方案**：

```python
def _save_atomic(self):
    """原子写入"""
    # 1. 写入临时文件
    fd, temp_path = tempfile.mkstemp(...)
    json.dump(data_to_save, f)
    
    if os.name == 'nt':  # Windows
        # 备份策略：原文件→备份→新文件（保留备份供崩溃恢复）
        backup_path = str(self.data_file) + '.bak'
        os.rename(self.data_file, backup_path)  # 原文件备份
        os.rename(temp_path, self.data_file)    # 新文件写入
        # 保留 .bak 供异常恢复
    else:  # Unix
        # os.replace 原子替换
        os.replace(temp_path, self.data_file)
```

### 3. 注册原子事务

```python
def try_register_user(self, qq: str, test_mode: bool = False):
    """注册原子事务"""
    with self._lock:
        # 1. 检查是否已注册
        # 2. 获取注册码
        # 3. 记录注册
        # 4. 保存
        return success, status, code
```

### 4. 锁的选择

使用 `threading.RLock()` 而非 `threading.Lock()`：

- RLock 支持同一线程多次获取锁（可重入）
- 防止内部方法调用导致死锁

---

## 🔐 安全机制

### 1. 日志脱敏

| 场景 | 处理方式 |
|------|----------|
| 抽奖历史记录 | `code[:4] + "****"` |
| handlers日志 | 不传递明文码，只记录档次 |
| test_mode历史 | 固定 `"TEST****"` |

**示例**：

```python
# handlers/user.py - 不传明文码
self.data.log_action("抽奖", qq, f"抽中{tier_name}")

# data.py - 历史记录脱敏
self.data["lottery_history"].insert(0, {
    "qq": qq,
    "tier": tier,
    "code_hash": code[:4] + "****" if not test_mode else "TEST****",
    "time": now.isoformat()
})
```

### 2. 群成员验证（带TTL）

```
验证流程:
1. skip_group_check=true → 跳过验证

2. 临时会话来源验证（优先）
   ├── 有来源群 && 在target_groups → ✅通过 + 更新活跃时间
   ├── 有来源群 && 不在target_groups → ❌拒绝
   └── 无来源 → 下一步

3. 群成员缓存验证（带TTL）
   ├── 在缓存 && 活跃时间 < 30天 → ✅通过
   └── 不在缓存 || 活跃时间 > 30天 → ❌拒绝
```

### 3. 会话管理

| 机制 | 实现 |
|------|------|
| 会话超时 | 可配置 `session_timeout`（默认300秒） |
| 状态机 | SessionManager 管理用户/管理员状态 |
| 子菜单状态 | 进入子菜单后保持状态，操作完成后清除 |
| 取消操作 | 任何时候回复 `Q` 取消当前操作 |

---

## 📖 API 参考

### DataManager 公共API

#### 核心原子事务

```python
# 完整抽奖原子事务（推荐使用）
try_lottery_draw_atomic(qq: str, test_mode: bool = False) 
    -> Tuple[bool, str, Optional[str], Optional[str]]
# 返回: (成功, 状态, 档次, 兑换码)
# 状态: "success" / "本周抽奖次数已用完" / "今日抽奖次数已用完" / "奖池已空" / "no_stock"

# 注册原子事务
try_register_user(qq: str, test_mode: bool = False) 
    -> Tuple[bool, str, Optional[str]]
# 返回: (成功, 状态["success"/"already_registered"/"no_stock"], 注册码)
```

#### 查询类（只读，返回深拷贝）

```python
is_registered(qq: str) -> bool
get_user_info(qq: str) -> Optional[dict]
get_registered_users_list(limit: int = 50) -> List[Tuple[str, dict]]
get_user_lottery_data(qq: str) -> dict
can_draw_lottery(qq: str) -> Tuple[bool, str]  # 仅用于UI展示
get_all_pool_counts() -> dict  # {"gold": n, "purple": n, "blue": n, "event": n}
get_lottery_config() -> dict
get_lottery_history(limit: int = 10) -> list  # 脱敏
get_statistics() -> dict
get_blacklist() -> List[str]
get_announcement() -> dict
```

#### 管理类（写操作，线程安全）

```python
# 码管理
add_registration_codes(codes: List[str]) -> dict  # {"added": n, "skipped": m}
add_lottery_codes(tier: str, codes: List[str]) -> dict
add_event_codes(codes: List[str]) -> dict
get_codes_preview(pool_type: str, tier: str = None, limit: int = 30) -> List[str]  # 脱敏

# 用户管理
reset_user_registration(qq: str) -> bool
reset_user_lottery_data(qq: str) -> bool

# 配置管理
update_lottery_config(key: str, value) -> bool

# 黑名单
add_to_blacklist(qq: str) -> bool
remove_from_blacklist(qq: str) -> bool
clear_blacklist() -> bool
is_blacklisted(qq: str) -> bool

# 公告
set_announcement(content: str) -> bool
clear_announcement() -> bool

# 日志
log_action(action: str, qq: str, detail: str)  # 不要传明文码
```

---

## ❓ 常见问题

### Q1: test_mode 下会消耗抽奖次数吗？

**会**。v2.1 修复了 test_mode 不计入次数的问题：

- test_mode 返回 `TEST-XXX-CODE` 假码
- test_mode **会**更新 `total_draws`, `week_draws`, `day_draws`
- test_mode **会**保存次数数据（防止重启重置）
- test_mode **不会**消耗真实码库存

这样设计是为了防止管理员用 test_mode 无限测试，且重启后次数限制仍然有效。

### Q2: 并发抽奖会超发吗？

**不会**。v2.1 使用完整原子事务：

```python
# lottery/engine.py
def draw(self, qq: str, test_mode: bool = False):
    # 直接调用原子事务，资格检查和抽奖在同一个锁内完成
    success, status, tier, code = self.data.try_lottery_draw_atomic(qq, test_mode)
```

### Q3: Windows 下写入中断会丢数据吗？

**极低概率**。v2.1 使用备份策略：

1. 原文件 → 备份（`.bak`）
2. 临时文件 → 目标文件
3. 保留 `.bak` 备份供崩溃恢复

即使在步骤2失败，备份文件仍存在，下次启动时自动从 `.bak` 恢复。

### Q4: 用户验证失败怎么办？

1. 确保用户从目标群发起临时会话（最准确）
2. 让用户在群里发一条消息（会更新缓存活跃时间）
3. 临时关闭验证：`skip_group_check: true`

### Q5: 群成员缓存多久过期？

默认 **30天**。超过30天未在群里发言的用户，缓存失效，需要重新从群发起会话或在群里发言。

### Q6: 管理员子菜单为什么没反应？

v2.1 修复了此问题。确保：

1. 先进入主菜单（发送 `jiu`）
2. 选择子菜单（如 `3` 进入库存）
3. 在子菜单状态下输入操作（如 `3-G`）

回复 `Q` 可随时取消并返回。

---

## 📝 更新日志

### v2.1.6 (2026-02-10) - 生命周期版

**🔧 P1生命周期修复**
- `group_manager.start()/stop()` 改为同步方法，`__del__` 不再产生未 await 协程
- `__del__` 卸载时主动 cancel 定时任务
- 定时任务异常自愈：`weekly_reset()` 抛异常不会导致任务退出，60秒后重试
- `_ensure_scheduled_tasks` 检测任务异常退出并自动重启
- `_try_start_scheduled_tasks` 也调用 `group_mgr.start()`

**🔧 数据安全**
- test_mode 码唯一化：注册码 `TEST-REG-{qq}`，抽奖码 `TEST-{TIER}-{qq}-{HHMMSS}`
- 缓存清理时删除时间戳解析失败的脏数据

**🔧 功能完善**
- 新增 `10-E` 活动卡权重管理命令
- 抽奖配置面板展示 `event_weight`

### v2.1.5 (2026-02-10) - 稳态版

**🔧 P1事务安全**
- 抽奖事务内实时校验活动卡到期，防止确认到扣码窗口期间过期卡被发出
- `_get_time_info` 类型防护，配置异常不再抛错

**🔧 数据安全**
- 群缓存活跃时间更新每200次定期落盘，防重启丢失
- 添加插件卸载钩子 `__del__`，退出时 flush 群缓存和数据

**🔧 一致性**
- 活动卡权重抽取从 config 读取 `event_weight`，与展示统一
- 配置回显用夹逼后实际值，不再显示负数
- 活动名不再被强制大写
- 消除所有 `config.config` 直接读取，统一走 `ConfigManager.get()`

### v2.1.4 (2026-02-10) - 数据完整性版

**🔧 数据完整性**
- 旧版 used 索引自动迁移：启动时自动检测 `qq->code` 并转换为 `code->{qq,time}`
- `reset_user_registration` 修复：按 reg_code 删除 used（不再按 qq 误删）

**🔧 安全加固**
- 活动结束时间解析失败时 fail-close（视为已过期），而不是放行
- weekday/hour 非法值防护，避免手改 config 导致异常

**🔧 一致性修复**
- 概率展示纳入活动卡权重，与实际抽取一致
- 金卡文案改为动态（不再硬编码 5%）
- `jiu用户` 路由修复（4-2 查询用户，而非 4-1 列用户）
- 定时任务兆底启动同时挂到群消息路径

**🔧 文档清理**
- 清除所有 v2.1.0 残留描述
- 修复 test_mode 旧注释、错别字
- 未落地配置字段标记为“预留”

### v2.1.3 (2026-02-10) - 硬伤修复版

**🔧 数据完整性**
- 已发码索引改为 `code -> {qq, time}`（原来 `qq -> code` 会覆盖，导致重复码可能被重新导入）
- 注册码/抽奖码/活动码类型统一采用新索引，重复检查统一改为 `code in pool["used"]`

**🔧 保底逻辑修复**
- 保底档缺货时向上降级（purple→gold→event），绝不回落蓝卡
- 所有非蓝档均缺货时明确提示，而不是无声失败

**🔧 活动卡池修复**
- 纯日期 `YYYY-MM-DD` 自动补到当天23:59:59，防止活动当天一开始就过期

**🔧 并发安全**
- 群缓存所有公开方法统一加锁（`record_member_leave`/`get_member_count`/`get_cache_status`/`force_update`）

**🔧 功能完善**
- 补齐文档中承诺的快捷命令：`jiu用户`/`jiu重置`/`jiu黑名单`/`jiu解黑`/`jiu时间`/`jiu公告`

### v2.1.2 (2026-02-10) - 强健版

**🔧 P1可靠性修复**
- data.json/config.json/group_members.json 加载时自动检测损坏并从 .bak 恢复
- 备份恢复成功后自动修复主文件
- 审计日志 log_action 改为即时落盘，防止异常退出丢失

**🔧 P1安全修复**
- 群成员TTL验证：时间戳解析失败视为无效（原来是默认有效，存在绕过风险）
- 群成员验证按 target_groups 过滤，防止非目标群成员被错误放行

### v2.1.1 (2026-02-10) - 文档一致性版

**🔧 文档修复**
- 修复 README 中 test_mode 落盘描述与实现不一致的问题

**🔧 并发安全强化**
- ConfigManager 添加 RLock，get/set 方法线程安全
- group_members.json 改为原子写入（与data.json一致的备份策略）

**🔧 功能完善**
- 活动卡池管理命令完整实现（E-1开启/E-2关闭/E-3查看）
- 菜单新增 11 - 活动卡池管理
- 快捷命令支持 `jiu活动卡` 添加活动卡码

### v2.1.0 (2026-02-10) - 安全加固版

**🔧 并发安全修复**
- `try_lottery_draw_atomic()`：完整原子事务，资格检查+档次决定+扣库存+记账 全部在同一个锁内完成
- `test_mode` 抽奖计入次数限制 **且落盘保存**，防止重启重置次数
- Windows/Unix 数据文件原子写入（备份策略）
- ConfigManager.save() 改为原子写入
- 群成员缓存操作添加 RLock 保护，消除并发竞态

**🔧 状态机修复**
- 管理员子菜单状态处理完整化
- 新增状态：`stock_menu`, `user_menu`, `blacklist_menu`, `time_menu`, `announcement_menu`, `lottery_config_menu`

**🔧 安全加固**
- 群成员缓存增加 TTL 机制（默认30天）
- 日志脱敏：handlers 不传明文码，只记录档次
- 历史记录脱敏：固定 `code[:4]+"****"`
- 移除裸 `except:`，改为具体异常类型

**🔧 代码质量**
- 抽奖引擎简化，完全依赖 DataManager 原子事务
- 异常不再静默吞掉，记录 debug 日志
- 版本号统一为 `2.1.0`

### v2.0.0 (2026-02-09) - 模块化重构版

**🔧 架构重构**
- 移除所有 `self.data.data[...]` 直接访问（原25+处 → 0处）
- 所有操作通过 DataManager 公共API
- 返回数据使用 `copy.deepcopy()` 防止污染

**🔧 并发安全**
- 引入 `threading.RLock()` 保护数据操作
- 注册原子事务 `try_register_user()`
- 原子写入 `_save_atomic()`

**🔧 其他修复**
- 群成员管理器初始化顺序修正
- 配置深拷贝保护
- 异常日志记录

### v1.0.0

- ✨ 初始版本

---

## 🧪 测试检查清单

### 并发安全测试

- [ ] 同一用户并发注册，只获得1个码
- [ ] 同一用户并发抽奖，不会超过次数限制
- [ ] 并发添加码，不会丢失或重复
- [ ] test_mode 抽奖会计入次数限制

### 功能测试

- [ ] 注册流程正常
- [ ] 抽奖流程正常
- [ ] 保底机制触发正确（连续N次蓝卡后必出紫卡）
- [ ] 次数限制生效（周/日）
- [ ] 群成员验证生效
- [ ] 缺货时概率重算正确

### 管理员测试

- [ ] 控制面板正常打开
- [ ] 子菜单操作正常（3-X, 4-X, 6-X, 7-X, 8-X, 10-X）
- [ ] 快捷命令正常（jiu状态, jiu库等）
- [ ] 批量添加码正常

### 边界测试

- [ ] 库存为空时提示正确
- [ ] 某档次缺货时概率展示正确
- [ ] 黑名单用户无法操作
- [ ] 会话超时后状态正确重置

### 安全测试

- [ ] 日志不包含明文码
- [ ] 历史记录码脱敏
- [ ] 群成员缓存过期后验证失败
- [ ] Windows 写入中断后数据可恢复

---

## 📋 更新日志

### v2.2.0 - "防御性版" (2026-02-10)

**🛡️ 安全防御（P1）**
- **datetime naive/aware 安全比较**: 新增 `_parse_naive_datetime()` 统一剥离时区信息，防止带时区的结束时间触发 TypeError
- **启动时 schema 校验**: 新增 `_validate_schema()` 对权重、限次、保底阈值、pity_tier、event_pool.enabled 做类型/范围修正，非法值自动回退默认并记告警

**🔒 数据完整性（P2）**
- **重置注册不再删 used**: `reset_user_registration` 改为标记 `revoked=True`，防止同一码被重新入库再发放
- **群缓存 TTL 校验**: 读入时做类型/范围校验，非法值回退默认 30 天

**📝 文案修正**
- 概率描述从写死“5%/20%/75%”改为中性描述（低/中/高概率）
- README 抽奖配置表补充 `event_weight`、`pity_tier` 可选值说明

### v2.1.9 - "完整性版" (2026-02-10)
*全局码去重、活动名空格支持、会话容量保护、硬编码文案修正*

### v2.1.8 - "一致性版" (2026-02-10)
*文档版本号统一、SessionManager 加锁、菜单文案修正*

### v2.1.7 - "工程化版" (2026-02-10)
*备份文件保留、生命周期 terminate()、权重夹逼、码列表真实库存、健康检查等*

### v2.1.6 - "生命周期版"
*参见此前更新记录*

## 📄 许可证

MIT License

---

## 💬 技术支持

如有问题请联系 **久**
