# app.py 程序运行路径介绍

## 概述
`app.py` 是 MemoTrace Web 聊天服务的主程序，提供 Flask Web 服务，供前端获取微信联系人列表和聊天记录。

---

## 启动流程

### 1. **初始化阶段**（第1-43行）
- **日志系统配置**：在 `web_chat/logs` 目录下生成时间戳日志文件
- **项目路径设置**：将项目根目录添加到 Python 路径
- **输出**：启动消息和项目根目录日志

### 2. **依赖模块导入**（第45-93行）

#### 必需模块（第45-54行）
```
✅ 成功则继续
- flask (Flask Web框架)
- flask_cors (跨域请求支持)
- wxManager.DatabaseConnection (数据库连接)
- wxManager.Me (微信用户信息)

❌ 失败则抛异常中止
```

#### 可选模块（第56-70行）
```
✅ 成功导入解密功能
- wxManager.decrypt (微信数据解密)
- yara-python (图片识别)

⚠️ 失败则仅记录警告，继续运行（降级模式）
```

#### 微信信息获取模块（第72-93行）
```
✅ 加载微信版本列表
- version_list.json 配置文件
- get_info_v3/v4 函数（可选）

⚠️ 失败则记录警告
```

### 3. **Flask 应用配置**（第94-110行）
- **静态文件目录**：`web_chat/static/`
- **缓存目录**：`web_chat/cache/`（自动创建）
- **CORS跨域支持**：允许前端跨域请求
- **导出API**：注册 `export_api` 蓝图

### 4. **数据库配置**（第111-151行）

#### 配置文件读取流程
```
config.json 存在？
    ├─ YES → 读取配置（db_path, db_version）
    ├─ NO  → 使用默认值：
    │       ├─ db_path: J:\Github\MemoTrace_test\wxid_xxx\Msg
    │       └─ db_version: 3
    └─ 更新全局变量 DB_DIR 和 DB_VERSION
```

#### 配置优先级
1. `config.json` 中的设置（最高）
2. 代码中的硬编码默认值（第113-114行）
3. 前端动态配置（通过 `/api/config` POST）

---

## 核心功能路由

### 数据库初始化（第157-189行）
**入口**：`init_database()`
```
检查数据库是否已初始化
    ├─ YES → 返回缓存实例
    ├─ NO  → 创建新连接：
    │       ├─ DatabaseConnection(DB_DIR, DB_VERSION)
    │       ├─ 获取图片解密密钥 (xor_key)
    │       ├─ 测试连接：get_contacts()
    │       └─ 返回数据库接口对象
    └─ 异常 → 返回 None（降级处理）
```

### API 路由（第334-1123行）

#### 首页路由
- **GET** `/` → `index.html`

#### 配置管理
- **GET** `/api/config` → 获取当前配置
- **POST** `/api/config` → 更新配置并重置数据库连接

#### 数据库测试
- **GET** `/api/test` → 测试数据库连接，返回统计信息
- **GET** `/api/db/check` → 检查数据库有效性

#### 微信信息获取
- **GET** `/api/wechat/info` → 获取登录微信账号信息和解密密钥

#### 数据解密
- **POST** `/api/decrypt` → 解密微信数据库
  - 流程：解密 → 保存配置 → 重置数据库连接
  - V3：输出目录为 `Msg`
  - V4：输出目录为 `db_storage`

#### 联系人管理
- **GET** `/api/contacts` → 分页获取联系人列表
- **GET** `/api/contacts/search` → 搜索联系人
- **GET** `/api/avatar/<wxid>` → 获取用户头像

#### 群聊管理
- **GET** `/api/chatroom/members?room_id=<wxid>` → 获取群成员

#### 聊天记录
- **GET** `/api/messages` → 分页获取聊天记录
  - 参数：`wxid`, `page`, `page_size`, `start_seq`
- **GET** `/api/messages/all` → 获取全部聊天记录（不分页）

#### 会话管理
- **GET** `/api/session` → 获取最近会话列表

#### 统计信息
- **GET** `/api/stats` → 获取数据统计

#### 图片处理
- **GET** `/api/image?path=<image_path>` → 获取解密后的图片
  - 支持路径组合查找：DB_DIR → 微信目录 → 项目根目录

---

## 数据流向

### 消息获取流程
```
前端请求 /api/messages?wxid=XXX
    ↓
init_database() → 获取数据库对象
    ↓
db.get_messages_by_num(wxid, start_seq, page_size)
    ↓
返回消息列表 + 最新序号
    ↓
图片消息处理：
    ├─ 获取 msg.path（图片文件路径）
    ├─ 返回 /api/image?path=XXX URL
    └─ 前端触发图片请求时解密
```

### 图片解密流程
```
/api/image?path=XXX
    ↓
检查文件类型：
    ├─ .dat 文件 → 解密
    │   ├─ 检测 V4 格式（AES） → 用 AES 解密
    │   └─ V3 格式（XOR） → 用 XOR 码解密
    └─ 其他文件 → 直接返回
    ↓
返回解密后的二进制图片数据
```

### 微信信息获取流程
```
/api/wechat/info
    ↓
尝试获取 V3 微信信息（get_info_v3）
    ↓
尝试获取 V4 微信信息（get_info_v4）
    ↓
整合结果并返回：
    ├─ wxid, 账号名, 昵称, 电话
    ├─ 解密密钥 (key)
    └─ 微信目录路径 (wx_dir)
```

---

## 关键变量

| 变量名 | 类型 | 说明 |
|-------|------|------|
| `DB_DIR` | str | 解密后数据库路径 |
| `DB_VERSION` | int | 数据库版本（3 或 4） |
| `database` | object | 全局数据库连接对象（缓存） |
| `xor_key` | int | 图片解密密钥（XOR） |
| `DECRYPT_MODULES_AVAILABLE` | bool | 解密模块是否可用 |
| `STATIC_DIR` | Path | 静态文件目录 |
| `LOG_DIR` | Path | 日志文件目录 |

---

## 错误处理机制

### 分级降级处理
1. **严重错误**（导致中止）
   - 核心模块导入失败（Flask, wxManager）

2. **警告错误**（记录但继续）
   - 解密模块导入失败 → 不支持图片解密
   - 微信信息获取失败 → 无法自动获取密钥
   - 数据库初始化失败 → 返回 None，让调用者处理

3. **可恢复错误**（单个请求失败）
   - API 请求异常 → 返回 HTTP 错误响应
   - 文件不存在 → 返回默认值或错误提示

---

## 日志输出

### 日志位置
- **文件日志**：`web_chat/logs/app_YYYYMMDD_HHMMSS.log`
- **控制台日志**：实时输出（DEBUG 级别）

### 日志标签约定
- `[INIT]` - 初始化阶段
- `[DB]` - 数据库操作
- `[API]` - API 请求
- `[IMAGE]` - 图片处理
- `[AVATAR]` - 头像处理
- `[HTTP]` - HTTP 请求

---

## 启动命令

```bash
python app.py
```

### 启动输出示例
```
================================================== 
MemoTrace Web Chat 服务启动
================================================== 
项目根目录: g:\github\MemoTrace_test\MemoTrace
✅ 核心模块导入成功
✅ 微信解密模块导入成功
✅ 微信信息获取模块导入成功
数据库配置: DB_DIR=..., DB_VERSION=3
[INIT] 导出API模块加载成功

============================================================
🚀 Flask 服务启动成功!
📍 访问地址: http://127.0.0.1:5000
📁 日志目录: g:\github\MemoTrace_test\MemoTrace\web_chat\logs
💡 请在登录界面配置数据库路径
============================================================
```

---

## 配置文件示例

### config.json
```json
{
  "wechat_path": "C:\\Users\\Username\\AppData\\Local\\Tencent\\WeChat",
  "db_path": "J:\\Github\\MemoTrace_test\\wxid_xxx\\Msg",
  "db_version": 3
}
```

---

## 注意事项

1. **数据库路径必须是解密后的数据库目录**，通常包含 `MSG.db` 等文件
2. **V3 版本数据库**：数据库文件位于 `Msg` 子目录
3. **V4 版本数据库**：数据库文件位于 `db_storage` 子目录
4. **图片解密**：需要正确的 XOR 密钥或 AES 密钥
5. **跨域请求**：前端可以从任意域名发起请求
6. **日志大小**：每次启动生成新日志文件，需要定期清理
