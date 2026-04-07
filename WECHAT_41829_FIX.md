# 微信 4.1.8.29 版本解密问题修复指南

## 问题概述

您遇到的问题是 `get_decode_code_v4()` 方法无法正确获取密钥。根据已知信息分析，这个问题涉及两个层面的混淆：

### 关键区分

| 类型 | 密钥格式 | 用途 | 获取方式 |
|------|----------|------|----------|
| **数据库密钥** | 64字符十六进制 (32字节) | 解密 SQLite 数据库 | `get_info_v4()` / `dump_wechat_info_v4()` |
| **图片异或密钥** | 1字节 (0x00-0xFF) | 解密 `.dat` 图片文件 | `get_decode_code_v4()` |

您提供的 `c9eaed112cbb4dd896a5dd7314186a24598951f2efff4afe812fb7556f4fc4ce` 是 **3.5.9.55 版本的数据库密钥**，不是图片异或密钥。

---

## 已知信息分析

### 提供的信息
- **微信版本**: 4.1.8.29
- **手机号**: 18206740264
- **昵称**: 啊伟
- **微信目录**: `G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9`
- **参考密钥** (3.5.9.55): `c9eaed112cbb4dd896a5dd7314186a24598951f2efff4afe812fb7556f4fc4ce`

### 关键观察
1. 微信目录使用 `xwechat_files`，这是 **微信 4.x** 的特征（3.x 使用 `WeChat Files`）
2. 微信 4.x 的数据库使用 **AES-256-CBC** + **SHA512** 加密
3. 微信 4.x 的图片使用 **AES** 加密而非简单异或

---

## 问题诊断步骤

### 步骤 1: 确认问题类型

运行 `test_decrypt_v4.py` 脚本：

```bash
python test_decrypt_v4.py
```

这将测试：
- 已知密钥是否能解密当前版本数据库
- 数据库文件结构分析
- 基于已知信息的密钥变体测试

### 步骤 2: 内存分析（微信运行时）

运行 `analyze_wechat_41829.py` 脚本（需要微信正在运行）：

```bash
python analyze_wechat_41829.py
```

这将：
- 在 Weixin.exe 内存中搜索密钥
- 查找手机号/昵称位置
- 分析内存布局
- 建议新的 YARA 规则

### 步骤 3: 图片密钥分析

运行 `decrypt_dat_fixed.py` 脚本：

```bash
python decrypt_dat_fixed.py
```

这将：
- 使用改进的算法搜索图片异或密钥
- 识别 V4 AES 加密图片
- 尝试多种密钥推导方法

---

## 可能的修复方案

### 方案 A: 如果问题出在数据库密钥获取

如果 `get_info_v4()` 无法获取数据库密钥，需要更新 `wxManager/decrypt/wx_info_v4.py`：

```python
# 在 get_key_inner 函数中更新 YARA 规则
rules_v4_key = r'''
    rule GetKeyAddrStub_41829
    {
        strings:
            // 原有规则
            $a = /.{6}\x00{2}\x00{8}\x20\x00{7}\x2f\x00{7}/
            $b = /\x00{8}\x20\x00{7}\x2f\x00{7}.{32}/
            // 4.1.8.29 可能的新模式 - 需要根据实际情况添加
            $c = { c9 ea ed 11 2c bb 4d d8 ... }  // 如果密钥固定
        condition:
            any of them
    }
'''
```

### 方案 B: 如果问题出在图片异或密钥

微信 4.x 图片可能使用 **纯 AES 加密**，不再需要异或密钥。修改 `decrypt_dat.py`：

```python
def get_decode_code_v4(wx_dir):
    """
    微信 4.x 图片使用 AES 加密，不需要异或密钥
    返回特殊值表示使用 AES 模式
    """
    # 检查是否存在 V4 格式的图片
    cache_dir = os.path.join(wx_dir, 'cache')
    if os.path.exists(cache_dir):
        for root, dirs, files in os.walk(cache_dir):
            for file in files:
                if file.endswith('.dat'):
                    with open(os.path.join(root, file), 'rb') as f:
                        header = f.read(16)
                    if is_v4_image(header):
                        # 返回特殊值表示使用 AES 模式
                        return 0x100  # 或其他标记值
    return 0
```

### 方案 C: 手动设置已知密钥（临时方案）

如果已知 4.1.8.29 的数据库密钥，可以直接硬编码：

```python
# 在 wx_info_v4.py 的 dump_wechat_info_v4 函数中
def dump_wechat_info_v4(pid) -> WeChatInfo | None:
    wechat_info = WeChatInfo()
    # ... 其他代码 ...
    
    # 临时：直接设置已知密钥
    # wechat_info.key = get_key(pid, process_handle, buf)
    wechat_info.key = "your_known_key_here"  # 替换为实际密钥
    
    return wechat_info
```

---

## 反推密钥的方法

### 方法 1: 从内存转储中提取

1. 使用 Process Hacker 或 WinDbg 附加到 Weixin.exe
2. 搜索已知的密钥模式（如 3.5.9.55 密钥的前 8 字节）
3. 分析周围的内存结构

### 方法 2: 从数据库文件反推

如果能获取到解密后的数据库文件（从备份或其他设备）：

```python
import hashlib
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

# 尝试从已知的明文-密文对推导密钥
# 这需要大量计算，通常不实用
```

### 方法 3: 对比不同版本

对比 3.5.9.55 和 4.1.8.29 的内存布局：

1. 同时运行两个版本的微信（在不同机器或虚拟机）
2. 使用相同的账号登录
3. 对比密钥在内存中的存储位置和周围特征

---

## 验证修复

修复后，运行以下测试：

```python
from wxManager.decrypt import get_info_v4

# 测试数据库密钥获取
result = get_info_v4()
for info in result:
    print(f"版本: {info['version']}")
    print(f"密钥: {info['key']}")
    print(f"手机号: {info['mobile']}")
    print(f"昵称: {info['name']}")
```

---

## 参考信息

### 微信 4.x 加密变化

1. **数据库加密**: 
   - 算法: AES-256-CBC → PBKDF2 (SHA512, 256000 rounds)
   - 页大小: 4096 bytes
   - HMAC: SHA512

2. **图片加密**:
   - V1: AES ECB, 密钥 `cfcd208495d565ef...`
   - V2: AES ECB, 密钥 `43e7d25eb1b9bb64...`

### 关键文件位置

```
G:\微信\xwechat_files\wxid_xxx\db_storage\  <- 数据库文件
G:\微信\xwechat_files\wxid_xxx\cache\       <- 图片缓存
G:\微信\xwechat_files\wxid_xxx\temp\        <- 临时文件
```

---

## 下一步行动

1. **运行诊断脚本**: 执行 `python test_decrypt_v4.py`
2. **确认问题类型**: 是数据库密钥还是图片密钥问题
3. **内存分析**: 如果微信正在运行，执行 `python analyze_wechat_41829.py`
4. **提供反馈**: 将脚本输出结果提供给开发者，以便更新代码

---

## 注意事项

⚠️ **重要**: 
- 修改内存或解密微信数据可能违反微信服务条款
- 仅用于数据备份和个人使用
- 不要传播或分享解密密钥
