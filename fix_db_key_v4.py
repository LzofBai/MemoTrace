#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信 4.1.8.29 版本数据库密钥获取修复工具
针对 dump_wechat_info_v4() 和 get_key() 方法的问题
"""

import os
import sys
import ctypes
import struct
import psutil
import hashlib
import hmac
import time
from multiprocessing import freeze_support

# 微信加密相关常量
IV_SIZE = 16
HMAC_SHA512_SIZE = 64
KEY_SIZE = 32
AES_BLOCK_SIZE = 16
ROUND_COUNT = 256000
PAGE_SIZE = 4096
SALT_SIZE = 16

# Windows API
kernel32 = ctypes.windll.kernel32
PROCESS_ALL_ACCESS = 0x1F0FFF
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000

# 已知信息
WECHAT_VERSION = "4.1.8.29"
PHONE_NUMBER = "18206740264"
NICK_NAME = "啊伟"
KNOWN_KEY_35955 = "c9eaed112cbb4dd896a5dd7314186a24598951f2efff4afe812fb7556f4fc4ce"
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.c_ulong),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.c_ulong),
        ("Protect", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
    ]


def open_process(pid):
    return kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)


def read_process_memory(process_handle, address, size):
    buffer = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)
    success = kernel32.ReadProcessMemory(
        process_handle,
        ctypes.c_void_p(address),
        buffer,
        size,
        ctypes.byref(bytes_read)
    )
    if not success:
        return None
    return buffer.raw


def get_memory_regions(process_handle):
    regions = []
    mbi = MEMORY_BASIC_INFORMATION()
    address = 0
    while kernel32.VirtualQueryEx(
        process_handle,
        ctypes.c_void_p(address),
        ctypes.byref(mbi),
        ctypes.sizeof(mbi)
    ):
        if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE:
            regions.append((mbi.BaseAddress, mbi.RegionSize))
        address += mbi.RegionSize
    return regions


def is_ok(key, buf):
    """验证密钥是否正确"""
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Hash import SHA512
    
    if len(buf) < PAGE_SIZE:
        return False
    
    salt = buf[:SALT_SIZE]
    if salt == b'\x00' * SALT_SIZE or len(set(salt)) == 1:
        return False
    
    mac_salt = bytes(x ^ 0x3a for x in salt)
    new_key = PBKDF2(key, salt, dkLen=KEY_SIZE, count=ROUND_COUNT, hmac_hash_module=SHA512)
    mac_key = PBKDF2(new_key, mac_salt, dkLen=KEY_SIZE, count=2, hmac_hash_module=SHA512)
    
    reserve = IV_SIZE + HMAC_SHA512_SIZE
    reserve = ((reserve + AES_BLOCK_SIZE - 1) // AES_BLOCK_SIZE) * AES_BLOCK_SIZE
    
    start = SALT_SIZE
    end = PAGE_SIZE
    
    if len(buf) < end:
        return False
    
    mac_data_end = end - reserve + IV_SIZE
    if mac_data_end <= start or mac_data_end > len(buf):
        return False
    
    mac = hmac.new(mac_key, buf[start:mac_data_end], SHA512)
    mac.update(struct.pack('<I', 1))
    hash_mac = mac.digest()
    
    hash_mac_start_offset = end - reserve + IV_SIZE
    hash_mac_end_offset = hash_mac_start_offset + len(hash_mac)
    
    if hash_mac_end_offset > len(buf):
        return False
    
    stored_mac = buf[hash_mac_start_offset:hash_mac_end_offset]
    return hash_mac == stored_mac


def find_db_file_for_testing(wx_dir):
    """查找用于测试的数据库文件"""
    possible_paths = [
        os.path.join(wx_dir, 'db_storage', 'microMsg.db'),
        os.path.join(wx_dir, 'db_storage', 'session.db'),
        os.path.join(wx_dir, 'db_storage', 'favorite', 'favorite_fts.db'),
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, 'rb') as f:
                    buf = f.read(4096)
                if len(buf) >= 4096:
                    return path, buf
            except:
                pass
    
    # 遍历查找
    db_dir = os.path.join(wx_dir, 'db_storage')
    if os.path.exists(db_dir):
        for root, dirs, files in os.walk(db_dir):
            for file in files:
                if file.endswith('.db'):
                    path = os.path.join(root, file)
                    try:
                        with open(path, 'rb') as f:
                            buf = f.read(4096)
                        if len(buf) >= 4096:
                            return path, buf
                    except:
                        pass
    
    return None, None


def test_key_candidates(keys, buf):
    """测试密钥候选列表"""
    valid_keys = []
    for key in keys:
        if len(key) != 32:
            continue
        try:
            if is_ok(key, buf):
                valid_keys.append(key)
                print(f"  [VALID] 密钥有效: {key.hex()[:32]}...")
        except Exception as e:
            pass
    return valid_keys


def generate_key_candidates_from_known_info():
    """基于已知信息生成可能的密钥候选"""
    candidates = []
    
    # 1. 参考密钥变体
    key_35955 = bytes.fromhex(KNOWN_KEY_35955)
    candidates.append(("3.5.9.55 原始密钥", key_35955))
    candidates.append(("3.5.9.55 反转", key_35955[::-1]))
    candidates.append(("3.5.9.55 XOR 0xFF", bytes([b ^ 0xFF for b in key_35955])))
    
    # 2. 基于手机号和昵称的派生密钥
    phone_bytes = PHONE_NUMBER.encode('utf-8')
    nick_bytes = NICK_NAME.encode('utf-8')
    combined = phone_bytes + nick_bytes
    
    # 使用不同哈希算法
    candidates.append(("SHA256(手机+昵称)", hashlib.sha256(combined).digest()))
    candidates.append(("SHA256(昵称+手机)", hashlib.sha256(nick_bytes + phone_bytes).digest()))
    candidates.append(("MD5(手机+昵称)", hashlib.md5(combined).digest() + hashlib.md5(combined).digest()))
    
    # 3. 基于 wxid
    wxid = "wxid_5e3hd0zrse6w22"
    candidates.append(("SHA256(wxid)", hashlib.sha256(wxid.encode()).digest()))
    
    return candidates


def scan_memory_brute_force(pid, buf):
    """暴力扫描内存中的所有 32 字节序列作为密钥候选"""
    print("=" * 60)
    print(f"暴力扫描内存 (PID: {pid})")
    print("=" * 60)
    
    process_handle = open_process(pid)
    if not process_handle:
        print("无法打开进程")
        return []
    
    regions = get_memory_regions(process_handle)
    print(f"找到 {len(regions)} 个内存区域")
    
    candidates = []
    checked = 0
    
    # 限制扫描区域数量
    for base_addr, size in regions[:100]:
        # 限制每次读取大小
        read_size = min(size, 1024 * 1024)  # 最多 1MB
        
        memory = read_process_memory(process_handle, base_addr, read_size)
        if not memory:
            continue
        
        checked += 1
        
        # 滑动窗口查找 32 字节序列
        for offset in range(0, len(memory) - 32, 8):  # 步进 8 字节
            candidate = memory[offset:offset+32]
            
            # 简单过滤：不能有连续太多 0 或相同字节
            if candidate == b'\x00' * 32:
                continue
            if len(set(candidate)) < 8:
                continue
            
            # 测试密钥
            try:
                if is_ok(candidate, buf):
                    addr = base_addr + offset
                    print(f"\n[FOUND] 有效密钥 @ 0x{addr:08x}")
                    print(f"  密钥: {candidate.hex()}")
                    candidates.append(candidate)
            except:
                pass
        
        if checked % 10 == 0:
            print(f"  已检查 {checked} 个区域，找到 {len(candidates)} 个有效密钥")
    
    kernel32.CloseHandle(process_handle)
    print(f"\n扫描完成，共找到 {len(candidates)} 个有效密钥")
    return candidates


def scan_memory_pattern_based(pid, buf):
    """基于模式匹配扫描内存"""
    print("\n" + "=" * 60)
    print(f"基于模式匹配扫描内存 (PID: {pid})")
    print("=" * 60)
    
    process_handle = open_process(pid)
    if not process_handle:
        print("无法打开进程")
        return []
    
    regions = get_memory_regions(process_handle)
    
    candidates = []
    
    # 微信密钥通常有特定的内存特征
    # 常见模式：在密钥前可能有特定的标记字节
    
    for base_addr, size in regions[:50]:
        read_size = min(size, 512 * 1024)
        memory = read_process_memory(process_handle, base_addr, read_size)
        if not memory:
            continue
        
        # 搜索特定的内存模式
        # 模式1: 00 00 00 00 00 00 00 20 00 00 00 00 00 00 00 2F (密钥地址标记)
        pattern1 = b'\x00\x00\x00\x00\x00\x00\x00\x20\x00\x00\x00\x00\x00\x00\x00\x2f'
        
        offset = 0
        while True:
            idx = memory.find(pattern1, offset)
            if idx == -1:
                break
            
            # 在模式后读取可能的密钥地址
            if idx + 32 < len(memory):
                # 尝试直接读取后面的 32 字节作为密钥
                candidate = memory[idx+16:idx+48]
                if len(candidate) == 32 and len(set(candidate)) > 8:
                    try:
                        if is_ok(candidate, buf):
                            addr = base_addr + idx + 16
                            print(f"\n[FOUND] 模式1发现密钥 @ 0x{addr:08x}")
                            print(f"  密钥: {candidate.hex()}")
                            candidates.append(candidate)
                    except:
                        pass
            
            offset = idx + 1
    
    kernel32.CloseHandle(process_handle)
    return candidates


def find_key_by_phone_reference(pid, buf):
    """通过手机号引用找到附近的密钥"""
    print("\n" + "=" * 60)
    print(f"通过手机号引用查找密钥 (PID: {pid})")
    print("=" * 60)
    
    process_handle = open_process(pid)
    if not process_handle:
        print("无法打开进程")
        return []
    
    regions = get_memory_regions(process_handle)
    
    candidates = []
    phone_utf16 = PHONE_NUMBER.encode('utf-16le')
    
    for base_addr, size in regions[:30]:
        read_size = min(size, 1024 * 1024)
        memory = read_process_memory(process_handle, base_addr, read_size)
        if not memory:
            continue
        
        # 查找手机号
        offset = 0
        while True:
            idx = memory.find(phone_utf16, offset)
            if idx == -1:
                break
            
            print(f"\n[FOUND] 手机号 @ 0x{base_addr + idx:08x}")
            
            # 在手机号周围搜索可能的密钥
            context_start = max(0, idx - 512)
            context_end = min(len(memory), idx + 512)
            context = memory[context_start:context_end]
            
            # 在上下文中滑动查找 32 字节候选
            for key_offset in range(0, len(context) - 32, 8):
                candidate = context[key_offset:key_offset+32]
                if len(set(candidate)) > 8 and candidate != b'\x00' * 32:
                    try:
                        if is_ok(candidate, buf):
                            real_addr = base_addr + context_start + key_offset
                            print(f"  [VALID] 密钥 @ 0x{real_addr:08x}: {candidate.hex()}")
                            candidates.append(candidate)
                    except:
                        pass
            
            offset = idx + 1
    
    kernel32.CloseHandle(process_handle)
    return candidates


def manual_key_test():
    """手动测试已知密钥"""
    print("=" * 60)
    print("手动测试已知密钥")
    print("=" * 60)
    
    db_path, buf = find_db_file_for_testing(WX_DIR)
    if not db_path:
        print("未找到数据库文件")
        return
    
    print(f"测试文件: {db_path}")
    
    # 测试从已知信息生成的候选密钥
    candidates = generate_key_candidates_from_known_info()
    
    print(f"\n生成 {len(candidates)} 个候选密钥:\n")
    
    valid_keys = []
    for name, key in candidates:
        try:
            if is_ok(key, buf):
                print(f"[VALID] {name}: {key.hex()}")
                valid_keys.append((name, key))
            else:
                print(f"[INVALID] {name}")
        except Exception as e:
            print(f"[ERROR] {name}: {e}")
    
    return valid_keys


def suggest_yara_rules_for_41829():
    """为 4.1.8.29 版本建议 YARA 规则"""
    print("\n" + "=" * 60)
    print("建议的 YARA 规则 (针对 4.1.8.29)")
    print("=" * 60)
    
    phone_utf16 = PHONE_NUMBER.encode('utf-16le')
    nick_utf16 = NICK_NAME.encode('utf-16le')
    
    print(f"""
# 基于已知信息生成的 YARA 规则
# 微信版本: {WECHAT_VERSION}
# 手机号: {PHONE_NUMBER}
# 昵称: {NICK_NAME}

rule FindPhoneNumber_41829 {{
    strings:
        $phone = {{ {phone_utf16.hex(' ')} }}
    condition:
        $phone
}}

rule FindNickname_41829 {{
    strings:
        $nick = {{ {nick_utf16.hex(' ')} }}
    condition:
        $nick
}}

rule FindKeyByPattern_41829 {{
    strings:
        # 尝试不同的密钥标记模式
        $pattern1 = {{ 00 00 00 00 00 00 00 20 00 00 00 00 00 00 00 2f }}
        $pattern2 = {{ 00 00 00 00 00 00 00 20 ?? ?? ?? ?? ?? ?? ?? ?? }}
    condition:
        any of them
}}
""")


def get_wechat_pid():
    """获取 Weixin.exe 进程 ID"""
    for process in psutil.process_iter(['pid', 'name']):
        if process.name() == 'Weixin.exe':
            return process.pid
    return None


def main():
    print("微信 4.1.8.29 数据库密钥获取修复工具")
    print("=" * 60)
    print(f"版本: {WECHAT_VERSION}")
    print(f"手机号: {PHONE_NUMBER}")
    print(f"昵称: {NICK_NAME}")
    print(f"微信目录: {WX_DIR}")
    print("=" * 60)
    
    # 1. 手动测试已知密钥
    valid_keys = manual_key_test()
    
    # 2. 如果微信正在运行，进行内存扫描
    pid = get_wechat_pid()
    if pid:
        print(f"\n发现 Weixin.exe (PID: {pid})，开始内存扫描...")
        
        db_path, buf = find_db_file_for_testing(WX_DIR)
        if buf:
            # 暴力扫描
            keys1 = scan_memory_brute_force(pid, buf)
            
            # 模式匹配扫描
            keys2 = scan_memory_pattern_based(pid, buf)
            
            # 通过手机号引用查找
            keys3 = find_key_by_phone_reference(pid, buf)
            
            all_keys = keys1 + keys2 + keys3
            
            if all_keys:
                print("\n" + "=" * 60)
                print("找到的有效密钥汇总:")
                print("=" * 60)
                for i, key in enumerate(set(all_keys), 1):
                    print(f"{i}. {key.hex()}")
        else:
            print("未找到数据库文件用于验证")
    else:
        print("\nWeixin.exe 未运行，跳过内存扫描")
    
    # 3. 输出建议的 YARA 规则
    suggest_yara_rules_for_41829()
    
    print("\n" + "=" * 60)
    print("修复建议")
    print("=" * 60)
    print("""
1. 如果找到有效密钥，更新 wx_info_v4.py:
   - 将找到的密钥硬编码用于测试
   - 或者更新 YARA 规则以匹配新的内存布局

2. 如果密钥与 3.5.9.55 版本不同:
   - 说明 4.1.8.29 使用了新的密钥派生方式
   - 需要分析密钥是如何从账号信息生成的

3. 临时解决方案:
   在 wx_info_v4.py 的 dump_wechat_info_v4() 函数中:
   
   # 临时硬编码密钥
   if not wechat_info.key:
       wechat_info.key = "找到的有效密钥"
""")


if __name__ == '__main__':
    freeze_support()
    try:
        from Crypto.Protocol.KDF import PBKDF2
        from Crypto.Hash import SHA512
        main()
    except ImportError as e:
        print(f"缺少依赖: {e}")
        print("请安装: pip install pycryptodome")
