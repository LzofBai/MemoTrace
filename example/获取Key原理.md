# 微信4.x Key获取原理详解

## 📋 `get_info_v4()` 方法详细解析

### 1️⃣ 方法位置与入口

```python
# 文件: wxManager/decrypt/get_wx_info.py（第 399-424 行）
def get_info_v4():
    result_v4 = []
    for process in psutil.process_iter(['name', 'exe', 'pid']):
        if process.name() == 'Weixin.exe':
            # ... 处理逻辑
    return result_v4
```

**作用**：检测并收集微信4.x版本的用户信息和数据库密钥。

---

## 2️⃣ 核心流程（步骤分解）

### 步骤1：查找 Weixin.exe 进程

```python
for process in psutil.process_iter(['name', 'exe', 'pid']):
    if process.name() == 'Weixin.exe':  # 微信4.x 使用 Weixin.exe
```

- 遍历所有进程，找到微信4.x的主进程
- 微信3.x 用 `WeChat.exe`，微信4.x 用 `Weixin.exe`

### 步骤2：获取 DLL 基址

```python
wechat_base_address = 0
for module in process.memory_maps(grouped=False):
    if module.path and 'Weixin.dll' in module.path:
        wechat_base_address = int(module.addr, 16)
        break
```

- 获取 `Weixin.dll` 在内存中的基地址
- 用于后续内存读取的地址计算

### 步骤3：调用 `dump_wechat_info_v4(pid)` 获取详细信息

```python
pid = process.pid
wxinfo = dump_wechat_info_v4(pid)  # 核心函数，见下文
```

---

## 3️⃣ Key 获取的原理与路径

### A. `dump_wechat_info_v4()` 函数（wx_info_v4.py 第 570 行）

这是获取 Key 的**最核心函数**，分为以下阶段：

```
┌─────────────────────────────────────────────────────────────┐
│ dump_wechat_info_v4(pid)                                   │
├─────────────────────────────────────────────────────────────┤
│ 1️⃣ 打开进程                                                   │
│    ↓                                                         │
│ 2️⃣ 获取微信数据目录 (get_wx_dir)                             │
│    ↓                                                         │
│ 3️⃣ 查找数据库文件用于验证密钥                                 │
│    ↓                                                         │
│ 4️⃣ 【关键】扫描密钥 (get_key)                                 │
│    ↓                                                         │
│ 5️⃣ 并行获取昵称/手机号 (get_nickname)                        │
│    ↓                                                         │
│ 6️⃣ 返回 WeChatInfo 对象                                      │
└─────────────────────────────────────────────────────────────┘
```

### B. Key 获取的详细原理

#### 第一步：定位 Key 在内存中的位置（YARA 规则扫描）

```python
# wxManager/decrypt/wx_info_v4.py 第 335-344 行
rules_v4_key = r'''
    rule GetKeyAddrStub {
        strings:
            $a = /.{6}\x00{2}\x00{8}\x20\x00{7}\x2f\x00{7}/
            $b = /\x00{8}\x20\x00{7}\x2f\x00{7}.{32}/
        condition:
            any of them
    }
'''
```

- **YARA 规则** 用来模式匹配特定的内存字节序列
- 这些字节序列是 Key 的"特征标记"（前后有特定的填充字节）

#### 第二步：遍历内存区域提取候选地址

```python
def get_key_inner(pid, process_infos):
    # 第 374-377 行
    for base_address, region_size in process_infos:
        # 读取内存
        memory = read_process_memory(process_handle, base_address, region_size)
        matches = rules.match(data=target_data)
        
        # 从规则匹配的偏移量读取 8 字节的地址指针
        addr = read_num(target_data, offset, 8)  # 读取小端格式的 8 字节地址
        if addr != 0:
            pre_addresses.append(addr)  # 收集候选 Key 地址
```

#### 第三步：从候选地址读取 32 字节密钥

```python
# 第 389-395 行
for pre_address in pre_addresses:
    key = read_bytes_from_pid(pid, pre_address, 32)  # 读取 32 字节密钥
    if key and len(key) == 32 and key not in key_set:
        if key != b'\x00' * 32 and len(set(key)) > 1:  # 基础有效性检查
            keys.append(key)
```

#### 第四步：验证密钥有效性

```python
# 第 221-274 行 - is_ok() 函数
def is_ok(passphrase, buf):
    salt = buf[:SALT_SIZE]  # 读取数据库文件的 salt（前16字节）
    mac_salt = bytes(x ^ 0x3a for x in salt)  # 异或运算得到 mac_salt
    
    # 用 PBKDF2-SHA512 生成加密密钥和 MAC 密钥
    new_key = PBKDF2(passphrase, salt, dkLen=32, count=256000, hmac_hash_module=SHA512)
    mac_key = PBKDF2(new_key, mac_salt, dkLen=32, count=2, hmac_hash_module=SHA512)
    
    # 校验 HMAC 是否匹配
    mac = hmac.new(mac_key, buf[start:mac_data_end], SHA512)
    if hash_mac == stored_mac:  # ✅ 匹配 = 密钥正确
        return True
    return False
```

---

## 4️⃣ 数据流回溯图

```
1-decrypt.py
    ↓ dump_v4()
    ├─→ get_info_v4()  ← get_wx_info.py
    │       ├─→ dump_wechat_info_v4(pid)  ← wx_info_v4.py
    │       │    ├─→ get_wx_dir()  [扫描内存获取微信文件路径]
    │       │    ├─→ get_key()  [获取密钥]
    │       │    │    ├─→ get_memory_regions()  [获取进程内存区域]
    │       │    │    ├─→ get_key_inner()  [YARA规则扫描候选地址]
    │       │    │    └─→ is_ok()  [验证密钥有效性]
    │       │    └─→ get_nickname()  [并行提取昵称/手机号]
    │       │
    │       └─→ 返回字典
    │           {wxid, nick_name, key, phone, ...}
    │
    └─→ 输出到 wxid/db_storage/info.json
```

---

## 5️⃣ Key 获取路径总结

| 阶段 | 函数 | 作用 |
|------|------|------|
| **扫描** | `get_key_inner()` | 用YARA规则在内存中找候选Key地址 |
| **提取** | `read_bytes_from_pid()` | 从内存地址读取32字节原始密钥 |
| **验证** | `is_ok()` | 用数据库文件的salt验证密钥正确性 |
| **确认** | `get_key_()` | 多进程并行验证多个候选，返回第一个有效的 |

---

## 6️⃣ 关键技术点

✅ **YARA 规则匹配** - 高效的模式识别，避免逐字节比较  
✅ **多进程池** - 并行验证多个密钥候选，提升效率  
✅ **PBKDF2-SHA512** - SQLite 4.x 标准加密算法  
✅ **HMAC 校验** - 确保密钥的真实有效性  

这个实现相比 v3 更复杂，因为 v4 的密钥存储位置更隐蔽，需要通过特征字节模式才能定位！

---

## 7️⃣ 相关文件路径参考

| 文件 | 位置 | 说明 |
|------|------|------|
| 入口脚本 | `example/1-decrypt.py` | 微信数据库解密入口 |
| V4获取函数 | `wxManager/decrypt/get_wx_info.py` | `get_info_v4()` 方法定义处 |
| V4核心实现 | `wxManager/decrypt/wx_info_v4.py` | `dump_wechat_info_v4()` 密钥获取逻辑 |
| 数据模型 | `wxManager/decrypt/common.py` | `WeChatInfo` 类定义 |
| 数据库解密 | `wxManager/decrypt/decrypt_v4.py` | AES-256-CBC 解密算法实现 |
