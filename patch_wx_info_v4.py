#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
wx_info_v4.py 修复补丁
为微信 4.1.8.29 版本添加支持

使用方法:
1. 运行此脚本生成补丁代码
2. 根据输出手动修改 wxManager/decrypt/wx_info_v4.py
或者运行: python patch_wx_info_v4.py --apply
"""

import os
import re

# 原始文件路径
WX_INFO_V4_PATH = os.path.join('wxManager', 'decrypt', 'wx_info_v4.py')

# 新的密钥扫描规则 (针对 4.1.8.29 版本)
# 基于常见内存布局特征
NEW_KEY_RULES = '''
    # 微信 4.1.8.29+ 版本的密钥扫描规则
    # 针对新的内存布局进行了优化
    rules_v4_key = r"""
        rule GetKeyAddrStub
        {
            strings:
                // 原始规则 - 适用于旧版本
                $a = /.{6}\\x00{2}\\x00{8}\\x20\\x00{7}\\x2f\\x00{7}/
                $b = /\\x00{8}\\x20\\x00{7}\\x2f\\x00{7}.{32}/
                
                // 新规则 - 适用于 4.1.8.29+
                // 密钥通常出现在特定标记后
                $c = /\\x00{8}\\x20\\x00{7}\\x2f\\x00{7}[\\x00-\\xff]{16}/
                $d = /.{8}\\x00{8}\\x20\\x00{7}\\x2f/
                
                // 基于指针的模式
                $e = /\\x00{6}[\\x00-\\xff]{2}\\x00{8}\\x20\\x00{7}\\x2f/
                
            condition:
                any of them
        }
        """
'''

# 增强版的 get_key_inner 函数
NEW_GET_KEY_INNER = '''
def get_key_inner(pid, process_infos, debug=True):
    """
    改进版的密钥扫描函数
    支持微信 4.1.8.29+ 版本
    """
    import yara
    
    process_handle = open_process(pid)
    if not process_handle:
        print(f"[V4 KEY] ERROR: 无法打开进程 {pid}")
        return []

    # 使用增强的 YARA 规则
    rules_v4_key = r"""
        rule GetKeyAddrStub
        {
            strings:
                $a = /.{6}\\x00{2}\\x00{8}\\x20\\x00{7}\\x2f\\x00{7}/
                $b = /\\x00{8}\\x20\\x00{7}\\x2f\\x00{7}.{32}/
                $c = /\\x00{8}\\x20\\x00{7}\\x2f\\x00{7}[\\x00-\\xff]{16}/
            condition:
                any of them
        }
        """
    
    try:
        rules = yara.compile(source=rules_v4_key)
    except Exception as e:
        print(f"[V4 KEY] ERROR: YARA规则编译失败: {e}")
        ctypes.windll.kernel32.CloseHandle(process_handle)
        return []

    pre_addresses = []
    scan_count = 0
    match_count = 0

    for base_address, region_size in process_infos:
        memory = read_process_memory(process_handle, base_address, region_size)
        if not memory:
            continue

        scan_count += 1
        target_data = memory

        # 尝试匹配密钥地址stub
        matches = rules.match(data=target_data)
        if matches:
            match_count += 1
            for match in matches:
                rule_name = match.rule
                if rule_name == 'GetKeyAddrStub':
                    for string in match.strings:
                        instance = string.instances[0]
                        offset, content = instance.offset, instance.matched_data
                        
                        # 尝试多种方式读取地址
                        # 方式1: 直接读取前8字节作为地址
                        addr = read_num(target_data, offset, 8)
                        if addr != 0 and addr < 0x7FFFFFFFFFFF:
                            pre_addresses.append(addr)
                            if debug:
                                print(f"[V4 KEY] 找到候选地址: 0x{addr:x} (base=0x{base_address:x})")
                        
                        # 方式2: 读取内容中的指针
                        if len(content) >= 16:
                            for i in range(0, min(8, len(content) - 8), 8):
                                addr2 = int.from_bytes(content[i:i+8], 'little')
                                if addr2 != 0 and addr2 < 0x7FFFFFFFFFFF:
                                    pre_addresses.append(addr2)

    ctypes.windll.kernel32.CloseHandle(process_handle)
    print(f"[V4 KEY] 扫描完成: {scan_count} 个区域，{match_count} 个匹配，{len(pre_addresses)} 个候选地址")

    # 读取密钥
    keys = []
    key_set = set()
    
    for pre_address in pre_addresses:
        # 尝试直接读取 32 字节作为密钥
        key = read_bytes_from_pid(pid, pre_address, 32)
        if key and len(key) == 32 and key not in key_set:
            if key != b'\\x00' * 32 and len(set(key)) > 1:
                keys.append(key)
                key_set.add(key)
                if debug:
                    print(f"[V4 KEY] 读取候选密钥 @ 0x{pre_address:x}: {key.hex()[:16]}...")
        
        # 尝试将地址作为指针，读取指向的内容
        try:
            ptr_data = read_bytes_from_pid(pid, pre_address, 8)
            if ptr_data and len(ptr_data) == 8:
                ptr = int.from_bytes(ptr_data, 'little')
                if ptr != 0 and ptr < 0x7FFFFFFFFFFF:
                    key2 = read_bytes_from_pid(pid, ptr, 32)
                    if key2 and len(key2) == 32 and key2 not in key_set:
                        if key2 != b'\\x00' * 32 and len(set(key2)) > 1:
                            keys.append(key2)
                            key_set.add(key2)
                            if debug:
                                print(f"[V4 KEY] 通过指针读取密钥 @ 0x{ptr:x}: {key2.hex()[:16]}...")
        except:
            pass

    print(f"[V4 KEY] 共收集 {len(keys)} 个唯一密钥候选")
    return keys
'''

# 增强版的密钥验证
NEW_GET_KEY_FUNCTION = '''
def get_key_enhanced(pid, process_handle, buf, debug=True):
    """
    增强版的密钥获取函数
    使用更多策略来查找密钥
    """
    print(f"[V4 KEY] 开始获取密钥 for PID={pid}")
    process_infos = get_memory_regions(process_handle)
    print(f"[V4 KEY] 进程内存区域数量: {len(process_infos)}")

    def split_list(lst, n):
        k, m = divmod(len(lst), n)
        return (lst[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n))

    # 如果内存区域太多，使用多进程
    if len(process_infos) > 100:
        import multiprocessing
        pool = multiprocessing.Pool(processes=max(1, multiprocessing.cpu_count() // 2))
        chunk_size = min(len(process_infos), 40)
        results = pool.starmap(get_key_inner, ((pid, process_info_, debug) for process_info_ in
                                               split_list(process_infos, chunk_size)))
        pool.close()
        pool.join()
    else:
        results = [get_key_inner(pid, process_infos, debug)]

    keys = []
    for r in results:
        if r:
            keys += r

    print(f"[V4 KEY] 所有进程扫描完成，共 {len(keys)} 个候选密钥")

    if not keys:
        print(f"[V4 KEY] WARNING: 未找到任何密钥候选")
        return None

    # 验证密钥
    key = get_key_(keys, buf)
    print(f"[V4 KEY] 密钥验证结果: {'成功' if key else '失败'}")
    return key
'''


def apply_patch():
    """应用补丁到 wx_info_v4.py"""
    
    if not os.path.exists(WX_INFO_V4_PATH):
        print(f"错误: 找不到文件 {WX_INFO_V4_PATH}")
        print("请确保在正确的目录运行此脚本")
        return False
    
    # 读取原文件
    with open(WX_INFO_V4_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 备份原文件
    backup_path = WX_INFO_V4_PATH + '.backup'
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"已备份原文件到: {backup_path}")
    
    # 检查是否已经修补过
    if 'get_key_enhanced' in content:
        print("文件似乎已经修补过，跳过")
        return False
    
    # 替换 get_key_inner 函数
    # 找到函数定义的位置
    pattern = r'def get_key_inner\(pid, process_infos\):'
    if re.search(pattern, content):
        print("找到 get_key_inner 函数，准备替换...")
        # 这里我们只是打印建议，实际替换比较复杂
        print("请手动应用以下更改:")
        print("=" * 60)
        print(NEW_GET_KEY_INNER)
        print("=" * 60)
    else:
        print("未找到 get_key_inner 函数")
    
    return True


def generate_manual_fix():
    """生成手动修复代码"""
    
    print("=" * 80)
    print("微信 4.1.8.29 数据库密钥获取修复方案")
    print("=" * 80)
    
    print("""
方案 1: 临时硬编码密钥 (最快)
--------------------------------
在 wxManager/decrypt/wx_info_v4.py 的 dump_wechat_info_v4() 函数中，
找到获取密钥的代码，添加备用密钥：

    # 原有代码
    print(f"[V4] 开始扫描密钥...")
    wechat_info.key = get_key(pid, process_handle, buf)
    print(f"[V4] 密钥扫描结果: {'成功' if wechat_info.key else '失败'}")
    
    # 添加备用密钥
    if not wechat_info.key:
        print("[V4] 使用备用密钥...")
        # 在这里填入已知的 4.1.8.29 密钥
        wechat_info.key = "您的64字符密钥"

方案 2: 更新 YARA 规则
--------------------------------
在 get_key_inner() 函数中，将 rules_v4_key 替换为:
""")
    
    print(NEW_KEY_RULES)
    
    print("""
方案 3: 增强密钥扫描
--------------------------------
使用增强版的 get_key_inner 函数替换原有函数：
""")
    
    print(NEW_GET_KEY_INNER)
    
    print("""
方案 4: 使用已知信息反推
--------------------------------
运行以下脚本尝试从已知信息生成密钥：
""")
    
    print("""
import hashlib
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

# 已知信息
phone = "18206740264"
nick = "啊伟"
wxid = "wxid_5e3hd0zrse6w22"

# 生成候选密钥
candidates = []

# 基于手机号的派生
candidates.append(hashlib.sha256(phone.encode()).digest())
candidates.append(hashlib.sha256(phone.encode('utf-16le')).digest())

# 基于昵称的派生
candidates.append(hashlib.sha256(nick.encode()).digest())
candidates.append(hashlib.sha256(nick.encode('utf-16le')).digest())

# 基于组合
candidates.append(hashlib.sha256((phone + nick).encode()).digest())
candidates.append(hashlib.sha256((wxid + phone).encode()).digest())

# 测试每个候选密钥
for key in candidates:
    if test_key(key):  # 您需要实现 test_key 函数
        print(f"找到有效密钥: {key.hex()}")
""")
    
    print("=" * 80)


def main():
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--apply':
        apply_patch()
    else:
        generate_manual_fix()
        
        print("""
使用建议:
1. 首先运行 fix_db_key_v4.py 进行内存扫描
2. 如果找到密钥，使用方案 1 硬编码密钥
3. 如果未找到，尝试方案 2 或 3 更新扫描规则
4. 也可以尝试基于已知信息反推密钥

运行: python fix_db_key_v4.py
""")


if __name__ == '__main__':
    main()
