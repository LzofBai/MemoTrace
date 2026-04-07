# System Informer 替代搜索方法

由于新版 System Informer 的菜单结构变化，以下是替代的密钥查找方法。

## 方法 1: 使用 Properties -> Memory（推荐）

### 步骤

1. **右键 Weixin.exe** -> **Properties**（或按 Enter）

2. 切换到 **Memory** 标签页

3. 点击 **Strings** 按钮（如果可见）
   - 或者点击 **Search** 按钮

4. 在搜索框中输入：
   - 搜索类型：选择 **Unicode** 或 **UTF-16**
   - 搜索内容：`18206740264`

### 如果没有 Strings 按钮

1. 在 Memory 标签页中，右键点击列表
2. 查看是否有 **Search** 或 **Find** 选项
3. 如果没有，尝试 **Save** 保存内存转储，然后用其他工具搜索

---

## 方法 2: 使用内存区域搜索

### 步骤

1. 右键 Weixin.exe -> **Properties**

2. 切换到 **Memory** 标签页

3. 你会看到内存区域列表，包含以下列：
   - Base address (基址)
   - Type (类型)
   - Size (大小)
   - Protection (保护)

4. 找到 **Type** 为 **Private** 且 **Protection** 包含 **Read/Write** 的区域

5. 双击其中一个区域打开 **Memory Editor**

6. 在 Memory Editor 中：
   - 按 **Ctrl + F** 打开查找
   - 或使用菜单中的 **Search** 功能

7. 搜索手机号：
   - 选择 **Unicode** 类型
   - 输入：`18206740264`

---

## 方法 3: 使用 Python 脚本自动搜索（最简单）

由于 System Informer 的搜索功能有限，推荐直接使用 Python 脚本：

```bash
python fix_db_key_v4.py
```

这个脚本会自动：
1. 打开 Weixin.exe 进程
2. 在内存中搜索手机号
3. 在附近查找 32 字节密钥
4. 验证每个候选密钥

**确保微信正在运行**，然后执行脚本。

---

## 方法 4: 使用 Cheat Engine（替代工具）

如果 System Informer 不方便，可以使用 Cheat Engine：

### 下载
- 官网：https://www.cheatengine.org/

### 步骤

1. 打开 Cheat Engine

2. 点击电脑图标，选择 Weixin.exe 进程

3. 在 **Value** 框中输入：`18206740264`

4. **Scan Type**：Exact Value

5. **Value Type**：String

6. 勾选 **Unicode**（重要！）

7. 点击 **First Scan**

8. 等待扫描完成

9. 在结果列表中，右键点击地址 -> **Browse this memory region**

10. 在内存浏览器中：
    - 查看手机号周围的内存
    - 寻找 32 字节的随机数据
    - 右键选中 32 字节 -> **Copy** -> **Hex**

---

## 方法 5: 手动内存转储 + 分析

### 步骤 1: 导出内存

1. System Informer 中右键 Weixin.exe -> **Create dump file**

2. 选择 **Minidump** 或 **Full dump**

3. 保存到文件（如 `weixin.dmp`）

### 步骤 2: 使用 Python 分析

```python
import re

# 读取内存转储
with open('weixin.dmp', 'rb') as f:
    data = f.read()

# 搜索手机号 (UTF-16LE)
phone_pattern = b'1\x008\x002\x000\x006\x007\x004\x000\x002\x006\x004\x00'

matches = []
for m in re.finditer(phone_pattern, data):
    matches.append(m.start())

print(f"找到 {len(matches)} 个匹配")

# 在每个匹配附近查找密钥
for pos in matches:
    print(f"\n位置: 0x{pos:08x}")
    # 查看前后 512 字节
    start = max(0, pos - 512)
    end = min(len(data), pos + 512)
    chunk = data[start:end]
    
    # 查找 32 字节的高随机性数据
    for i in range(0, len(chunk) - 32, 8):
        candidate = chunk[i:i+32]
        # 检查随机性
        if len(set(candidate)) > 20 and len(set(candidate)) < 256:
            # 不是全可打印字符
            printable = sum(1 for b in candidate if 32 <= b < 127)
            if printable < 10:
                print(f"  候选 @ +{i}: {candidate.hex()}")
```

---

## 方法 6: WinDbg（高级）

### 安装
- 从 Microsoft Store 安装 WinDbg Preview

### 步骤

1. 打开 WinDbg Preview

2. File -> Attach to process -> 选择 Weixin.exe

3. 在命令框中输入：

```windbg
# 搜索手机号 (UTF-16LE)
s -u 0x0 L?0x7FFFFFFF "18206740264"
```

4. 记下找到的地址（如 `000001d8b1234560`）

5. 查看内存：
```windbg
# 查看地址附近的内存
db 000001d8b1234560-200 L400
```

6. 在输出中寻找 32 字节随机数据

---

## 快速推荐

| 您的情况 | 推荐方法 |
|---------|---------|
| 想快速找到密钥 | **方法 3**: `python fix_db_key_v4.py` |
| 喜欢图形界面 | **方法 4**: Cheat Engine |
| 想深入学习 | **方法 5**: 内存转储分析 |
| 已有调试经验 | **方法 6**: WinDbg |

---

## 最简流程（推荐）

```bash
# 1. 确保微信运行且已登录
# 2. 直接运行自动扫描脚本
python fix_db_key_v4.py

# 3. 如果找到密钥，验证它
python verify_key_manual.py

# 4. 使用密钥解密
python 1-decrypt-fixed.py
```

这个流程不需要手动操作 System Informer 的内存搜索！
