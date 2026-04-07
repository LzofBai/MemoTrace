# 微信 4.1.8.29 密钥获取最终解决方案

## 当前状态

✅ **数据库已找到**: `G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9\db_storage\favorite\favorite_fts.db`

❌ **自动扫描未找到密钥**: 扫描完成但未发现有效密钥

---

## 为什么自动扫描失败？

可能原因：

1. **微信 4.1.8.29 内存布局改变** - 密钥存储位置和之前版本不同
2. **密钥不在预期区域** - 可能在只读内存或其他保护区域
3. **扫描策略不匹配** - 当前策略无法定位新版本的密钥

---

## 解决方案（按成功率排序）

### 方案 1: 使用已有密钥（最简单）

如果您有以下任一来源的密钥：
- 之前备份的密钥文件
- 从其他设备导出的密钥
- 微信 3.x 迁移时的密钥（可能有效）

运行：
```bash
python manual_key_helper.py
```

然后输入密钥进行验证。

### 方案 2: 使用 Cheat Engine 手动查找

由于 System Informer 功能受限，推荐使用 **Cheat Engine**：

#### 步骤 1: 下载安装
- 官网：https://www.cheatengine.org/
- 下载并安装

#### 步骤 2: 附加进程
1. 打开 Cheat Engine
2. 点击左上角的电脑图标
3. 选择 `Weixin.exe` 进程

#### 步骤 3: 搜索手机号
1. **Value Type**: String
2. **Text**: `18206740264`
3. 勾选 **Unicode**（重要！）
4. 点击 **First Scan**

#### 步骤 4: 分析结果
1. 在结果列表中右键点击地址
2. 选择 **Browse this memory region**
3. 在内存浏览器中查看手机号周围的内存

#### 步骤 5: 识别密钥
在手机号前后 1024 字节范围内，寻找：
- 32 字节长度（64 个十六进制字符）
- 随机数据（不是可打印字符串）
- 示例：`a1b2c3d4e5f6...`（看起来像乱码）

#### 步骤 6: 提取并验证
1. 选中 32 字节数据
2. 右键 -> Copy -> Hex
3. 粘贴到 `manual_key_helper.py` 中验证

### 方案 3: 使用 WinDbg 命令行扫描

#### 安装 WinDbg
从 Microsoft Store 安装 "WinDbg Preview"

#### 执行命令
```bash
# 以管理员身份运行 WinDbg
# File -> Attach to process -> Weixin.exe

# 在命令框中输入：
# 搜索手机号（UTF-16LE）
s -u 0x0 L?0x7FFFFFFF "18206740264"

# 记下找到的地址，例如：000001d8b1234560
# 查看附近内存
db 000001d8b1234560-200 L400

# 寻找 32 字节随机数据
```

### 方案 4: 内存转储分析

#### 步骤 1: 创建内存转储
1. 右键 Weixin.exe 进程
2. 选择 "Create dump file" -> "Full dump"
3. 保存到文件

#### 步骤 2: 分析转储文件
```python
# 使用 Python 分析
with open('Weixin.dmp', 'rb') as f:
    data = f.read()

# 搜索手机号
phone = b'1\x008\x002\x000\x006\x007\x004\x000\x002\x006\x004\x00'
pos = data.find(phone)

if pos != -1:
    print(f"Phone found at: {hex(pos)}")
    # 查看前后数据
    context = data[pos-512:pos+512]
    # 寻找高随机性的 32 字节块
```

### 方案 5: 从其他微信版本获取

如果同一账号在其他设备/版本上登录过：

1. **微信 3.x 版本**:
   - 运行旧版解密工具
   - 获取密钥格式不同，但可能可用

2. **手机微信**:
   - 使用 iTunes 备份（iOS）
   - 使用第三方备份工具（Android）
   - 提取数据库密钥

---

## 密钥验证

找到候选密钥后，使用以下方法验证：

### 方法 1: 使用 manual_key_helper.py
```bash
python manual_key_helper.py
# 输入密钥，自动验证
```

### 方法 2: 使用 verify_key_manual.py
```bash
python verify_key_manual.py
# 交互式验证
```

### 方法 3: 直接解密测试
```bash
# 编辑 1-decrypt-fixed.py
MANUAL_KEY_V4 = "你的密钥"

# 运行
python 1-decrypt-fixed.py
```

---

## 密钥格式示例

有效的微信 4.x 数据库密钥：
- 长度：64 个十六进制字符
- 示例：`c9eaed112cbb4dd896a5dd7314186a24598951f2efff4afe812fb7556f4fc4ce`

---

## 推荐执行顺序

```
第一步: 检查是否有备份的密钥文件
        搜索电脑中的 .txt 或 .key 文件
        
        ↓ 如果没有
        
第二步: 下载 Cheat Engine
        https://www.cheatengine.org/
        
        ↓
        
第三步: 按照"方案 2"步骤查找密钥
        预计时间：5-15 分钟
        
        ↓ 找到候选密钥
        
第四步: python manual_key_helper.py
        验证密钥是否有效
        
        ↓ 验证成功
        
第五步: python 1-decrypt-fixed.py
        解密数据库
```

---

## 常见问题

### Q: Cheat Engine 找不到手机号？

A: 尝试：
1. 确保微信已完全登录（能看到聊天列表）
2. 尝试搜索部分号码，如 `0264`
3. 尝试搜索昵称 "啊伟"（UTF-16LE）

### Q: 找到多个候选密钥？

A: 逐一验证，通常只有一个能正确解密。

### Q: 密钥验证失败？

A: 可能原因：
1. 候选数据不是密钥
2. 数据库文件已损坏
3. 密钥版本不匹配

### Q: 所有方法都失败了？

A: 最后手段：
1. 使用微信官方备份功能备份聊天记录
2. 在另一台电脑上安装相同版本微信
3. 迁移聊天记录到新设备
4. 在新设备上获取密钥

---

## 联系支持

如果以上方法都无法解决问题：
1. 提供微信版本号（4.1.8.29）
2. 提供操作系统版本
3. 说明尝试过的方法
4. 提供错误日志（如果有）

---

**祝您成功找到密钥！**
