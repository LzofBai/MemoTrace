# Process Hacker 手动查找微信数据库密钥详细指南

## 1. 下载安装 Process Hacker / System Informer

### 下载地址
- **官方推荐**: System Informer（Process Hacker 的新版本）
  - 官网：https://systeminformer.sourceforge.io/
  - GitHub：https://github.com/winsiderss/systeminformer

- **旧版 Process Hacker**:
  - 官网：https://processhacker.sourceforge.io/

### 安装步骤
1. 下载对应版本（x64）
2. 解压或安装
3. **以管理员身份运行**（必须！）

---

## 2. 准备工作

### 确保微信正在运行
- 微信 4.1.8.29 必须正在运行
- 必须已登录账号（18206740264）
- 等待微信完全加载完成

### 确认目标信息（UTF-16LE 编码）

| 信息 | UTF-16LE 字节序列（十六进制） |
|------|---------------------------|
| 手机号 18206740264 | `31 00 38 00 32 00 30 00 36 00 37 00 34 00 30 00 32 00 36 00 34 00` |
| 昵称 "啊伟" | `4A 55 FF 67 70 5A` 或 `FF 4A 70 67`（取决于字节序） |

**注意**：UTF-16LE 每个字符后都有 `00`。

---

## 3. 详细操作步骤

### 步骤 1: 打开 System Informer

1. 右键点击 System Informer 图标
2. 选择"以管理员身份运行"
3. 等待进程列表加载

### 步骤 2: 找到 Weixin.exe 进程

1. 在进程列表中找到 `Weixin.exe`
2. **重要**: 可能有多个 Weixin.exe 进程
   - 查看"PID"列
   - 查看"Command line"列，找到包含实际数据目录的那个
3. 记下 PID（例如：12345）

### 步骤 3: 打开内存搜索功能

**方法 A - 使用查找句柄或 DLL 功能**:
1. 右键点击 Weixin.exe 进程
2. 选择 "Miscellaneous" -> "Search strings..."
   - 或者按 `Ctrl + Shift + S`

**方法 B - 使用内存编辑器**:
1. 右键点击 Weixin.exe
2. 选择 "Properties"
3. 切换到 "Memory" 标签页
4. 点击 "Search" 按钮

### 步骤 4: 搜索手机号

在搜索框中输入手机号的 UTF-16LE 格式：

1. **搜索类型**: 选择 "Unicode" 或 "UTF-16LE"
2. **搜索内容**: 输入 `18206740264`
3. **搜索范围**: 选择 "All memory regions" 或 "Private memory"
4. 点击 "Search" 或 "Find"

**或者使用十六进制搜索**:
1. 搜索类型选择 "Bytes" 或 "Hex"
2. 输入: `31 00 38 00 32 00 30 00 36 00 37 00 34 00 30 00 32 00 36 00 34 00`
3. 点击搜索

### 步骤 5: 分析搜索结果

找到手机号后，您会看到一个地址列表。例如：
```
Address: 0x000001D8B1234560
Value: 18206740264
```

双击第一个结果，打开内存编辑器。

### 步骤 6: 在手机号附近查找密钥

密钥通常存储在手机号附近（偏移 -512 到 +512 字节范围内）。

#### 6.1 查看内存布局

在内存编辑器中：
1. 您会看到一个十六进制视图
2. 左侧是地址，中间是十六进制数据，右侧是 ASCII 字符
3. 找到手机号的显示位置

#### 6.2 寻找密钥特征

微信数据库密钥的特征：
- **长度**: 32 字节（显示为 64 个十六进制字符）
- **内容**: 随机数据（看起来混乱，不是可打印字符）
- **位置**: 通常在手机号前面或后面不远处

**视觉识别**:
```
地址        十六进制数据                      ASCII
0x12345600: 4A 55 FF 67 70 5A 00 00 11 22 33 44 55 66 77 88  JU.gpZ..."3DUfw
0x12345610: 99 AA BB CC DD EE FF 00 01 02 03 04 05 06 07 08  ................
0x12345620: 31 00 38 00 32 00 30 00 36 00 37 00 34 00 30 00  1.8.2.0.6.7.4.0.
0x12345630: 32 00 36 00 34 00 00 00 ...                        2.6.4...
                 ↑
                 手机号开始位置 (18206740264)
```

上图中，`11 22 33 44...` 那 32 字节可能就是密钥。

#### 6.3 使用结构化视图

在 System Informer 中：
1. 右键点击内存区域
2. 选择 "Data" 或 "Structure"
3. 查看不同数据类型的解释

### 步骤 7: 提取候选密钥

找到可能的 32 字节数据后：

1. **选中数据**: 在十六进制视图中选中 32 字节（64 个字符）
2. **复制**: 右键 -> "Copy" -> "Copy as hex"
3. **保存**: 粘贴到记事本中

例如提取到的数据：
```
11223344556677889900AABBCCDDEEFF00112233445566778899AABBCCDDEEFF
```

### 步骤 8: 验证密钥

使用 Python 脚本验证：

```python
import os
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512
import hmac
import struct

def verify_key(key_hex, db_path):
    """验证密钥是否正确"""
    key = bytes.fromhex(key_hex)
    
    with open(db_path, 'rb') as f:
        buf = f.read(4096)
    
    salt = buf[:16]
    mac_salt = bytes(x ^ 0x3a for x in salt)
    
    new_key = PBKDF2(key, salt, dkLen=32, count=256000, hmac_hash_module=SHA512)
    mac_key = PBKDF2(new_key, mac_salt, dkLen=32, count=2, hmac_hash_module=SHA512)
    
    mac = hmac.new(mac_key, buf[16:4072], SHA512)
    mac.update(struct.pack('<I', 1))
    hash_mac = mac.digest()
    
    stored_mac = buf[4080:4144]  # 根据实际偏移调整
    
    return hash_mac == stored_mac

# 测试
key = "11223344556677889900AABBCCDDEEFF00112233445566778899AABBCCDDEEFF"
db_path = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9\db_storage\microMsg.db"

if os.path.exists(db_path):
    result = verify_key(key, db_path)
    print(f"密钥验证: {'成功！' if result else '失败'}")
else:
    print("数据库文件不存在")
```

---

## 4. 高级技巧

### 技巧 1: 搜索密钥标记

微信密钥前常有特定标记字节：
```
00 00 00 00 00 00 00 20 00 00 00 00 00 00 00 2F
```

在 System Informer 中搜索这个十六进制序列，密钥通常在标记后 8-24 字节处。

### 技巧 2: 过滤内存区域

只搜索可读写的私有内存：
1. 在内存视图窗口
2. 查看 "Type" 列，选择 "Private"
3. 查看 "Protection" 列，选择 "Read/Write"

### 技巧 3: 使用正则搜索

如果支持，搜索以下模式：
```
.{32}\x00{8}\x20\x00{7}\x2f
```
这表示：32字节随机数据 + 8个0 + 0x20 + 7个0 + 0x2f

### 技巧 4: 同时搜索昵称

如果手机号搜索结果太多，可以同时搜索昵称 "啊伟"：
- UTF-16LE: `4A 55 FF 67 70 5A`
- 或者尝试反向: `FF 4A 70 67`

找到昵称后，密钥通常在附近。

---

## 5. 常见问题

### Q: 找到很多匹配结果怎么办？

A: 
1. 优先查看与 Weixin.dll 模块相关的地址
2. 优先查看可读写的内存区域（非只读）
3. 尝试排除明显的字符串数据（如路径、URL）
4. 使用验证脚本逐一测试

### Q: 内存显示为 "???" 怎么办？

A: 
- 确保以管理员身份运行
- 该内存页可能受保护，尝试使用 "Query" 功能而非 "Read"

### Q: 搜索不到手机号？

A:
- 确认微信已完全登录
- 尝试搜索不带 `00` 的版本（ASCII）
- 尝试搜索部分号码（如后4位 `0264`）
- 检查微信是否使用了内存保护或加密

### Q: 如何确定找到的32字节是密钥？

A:
- 密钥应该完全随机（熵值高）
- 不应该包含可打印字符（ASCII 32-126）
- 使用 Python 脚本验证是唯一可靠的方法

---

## 6. 替代工具

如果 System Informer 无法找到，可以尝试：

### Cheat Engine
- 官网：https://www.cheatengine.org/
- 功能：内存扫描、十六进制编辑

### WinDbg
- Windows 调试工具
- 命令：`s -u 0x0 L?0x7FFFFFFF "18206740264"`

### 自定义 Python 脚本
运行 `fix_db_key_v4.py`（已提供）

---

## 7. 安全提醒

⚠️ **重要**:
1. 仅从官方网站下载工具
2. 不要将密钥分享给他人
3. 操作完成后关闭内存编辑工具
4. 仅在个人数据备份场景使用

---

## 8. 流程图

```
开始
  ↓
微信 4.1.8.29 运行中？
  ↓ 是
打开 System Informer (管理员)
  ↓
找到 Weixin.exe 进程
  ↓
搜索 "18206740264" (UTF-16LE)
  ↓
找到匹配地址
  ↓
查看附近内存 (-512 ~ +512 字节)
  ↓
寻找 32 字节随机数据
  ↓
复制十六进制值
  ↓
使用 Python 脚本验证
  ↓
成功？→ 保存密钥 → 解密数据库
  ↓ 失败
尝试其他候选
```

祝您成功找到密钥！
