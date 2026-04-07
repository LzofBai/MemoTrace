#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
微信 4.1.8.29 数据库密钥极速扫描工具
只使用最快策略，预计 5-15 秒完成
"""

import os
import sys
import ctypes
import struct
import psutil
import hashlib
import hmac
import time

# 常量
PAGE_SIZE = 4096
SALT_SIZE = 16
KEY_SIZE = 32
ROUND_COUNT = 256000

# Windows API
kernel32 = ctypes.windll.kernel32
PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
PAGE_READWRITE = 0x04

# 信息
PHONE = "18206740264"
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


def read_memory(process_handle, address, size):
    buffer = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(process_handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(bytes_read)):
        return buffer.raw
    return None


def get_regions(process_handle):
    """只获取大内存区域"""
    regions = []
    mbi = MEMORY_BASIC_INFORMATION()
    address = 0
    while kernel32.VirtualQueryEx(process_handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE and (mbi.Protect & PAGE_READWRITE):
            if mbi.RegionSize >= 1024 * 1024:  # 只保留 >= 1MB
                regions.append((mbi.BaseAddress, mbi.RegionSize))
        address += mbi.RegionSize
    return regions


def is_ok(key, buf):
    """验证密钥"""
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Hash import SHA512
    
    salt = buf[:SALT_SIZE]
    if salt == b'\x00' * SALT_SIZE or len(set(salt)) == 1:
        return False
    
    mac_salt = bytes(x ^ 0x3a for x in salt)
    new_key = PBKDF2(key, salt, dkLen=KEY_SIZE, count=ROUND_COUNT, hmac_hash_module=SHA512)
    mac_key = PBKDF2(new_key, mac_salt, dkLen=KEY_SIZE, count=2, hmac_hash_module=SHA512)
    
    mac = hmac.new(mac_key, buf[16:4072], SHA512)
    mac.update(struct.pack('<I', 1))
    hash_mac = mac.digest()
    stored_mac = buf[4080:4144]
    
    return hash_mac == stored_mac


def find_db():
    """查找数据库"""
    # 尝试多个可能的路径
    paths = [
        os.path.join(WX_DIR, 'db_storage', 'microMsg.db'),
        os.path.join(WX_DIR, 'db_storage', 'session.db'),
        os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db'),
        os.path.join(WX_DIR, 'db_storage', 'msg', 'message.db'),
    ]
    
    for path in paths:
        if os.path.exists(path):
            print(f"Found DB: {path}")
            with open(path, 'rb') as f:
                return f.read(4096)
    
    # 自动搜索
    db_storage = os.path.join(WX_DIR, 'db_storage')
    if os.path.exists(db_storage):
        for root, dirs, files in os.walk(db_storage):
            for file in files:
                if file.endswith('.db'):
                    path = os.path.join(root, file)
                    try:
                        with open(path, 'rb') as f:
                            data = f.read(4096)
                        if len(data) >= 4096:
                            print(f"Found DB: {path}")
                            return data
                    except:
                        pass
            break  # 只搜索一层
    
    print("No database found in:", WX_DIR)
    print("Subdirectories:")
    if os.path.exists(WX_DIR):
        for item in os.listdir(WX_DIR):
            print("  -", item)
    return None


def scan_fast(pid, buf):
    """极速扫描 - 只找手机号附近"""
    phone = PHONE.encode('utf-16le')
    
    h = open_process(pid)
    if not h:
        print("无法打开进程")
        return []
    
    regions = get_regions(h)
    # 只取最大的 15 个区域
    regions.sort(key=lambda x: x[1], reverse=True)
    regions = regions[:15]
    
    print(f"扫描 {len(regions)} 个大内存区域...")
    
    found = []
    
    # 第一步：找手机号
    for base, size in regions:
        chunk = min(size, 4 * 1024 * 1024)
        mem = read_memory(h, base, chunk)
        if not mem:
            continue
        
        idx = mem.find(phone)
        if idx != -1:
            addr = base + idx
            print(f"  找到手机号 @ 0x{addr:08x}")
            
            # 在附近找密钥
            start = max(0, idx - 1024)
            end = min(len(mem), idx + 1024)
            
            for i in range(start, end - 32, 8):
                k = mem[i:i+32]
                if len(set(k)) > 15:
                    try:
                        if is_ok(k, buf):
                            print(f"\n[成功] 找到密钥 @ 0x{base + i:08x}")
                            print(f"密钥: {k.hex()}")
                            found.append(k)
                            return found
                    except:
                        pass
    
    # 如果没找到，暴力扫大区域
    if not found:
        print("  手机号定位失败，尝试扫描大区域...")
        for base, size in regions[:5]:
            for offset in range(0, min(size, 64 * 1024 * 1024), 16 * 1024 * 1024):
                mem = read_memory(h, base + offset, 16 * 1024 * 1024)
                if not mem:
                    continue
                
                for i in range(0, len(mem) - 32, 64):
                    k = mem[i:i+32]
                    if len(set(k)) > 15:
                        try:
                            if is_ok(k, buf):
                                print(f"\n[成功] 找到密钥 @ 0x{base + offset + i:08x}")
                                print(f"密钥: {k.hex()}")
                                found.append(k)
                                return found
                        except:
                            pass
    
    kernel32.CloseHandle(h)
    return found


def main():
    print("=" * 50)
    print("微信密钥极速扫描")
    print("=" * 50)
    
    # 找进程
    pid = None
    for p in psutil.process_iter(['pid', 'name']):
        if p.name() == 'Weixin.exe':
            pid = p.pid
            break
    
    if not pid:
        print("错误: 微信未运行")
        return
    
    print(f"微信 PID: {pid}")
    
    # 找数据库
    buf = find_db()
    if not buf:
        print("错误: 未找到数据库")
        return
    
    print("开始扫描...")
    start = time.time()
    
    keys = scan_fast(pid, buf)
    
    elapsed = time.time() - start
    
    if keys:
        print(f"\n耗时: {elapsed:.2f} 秒")
        print("=" * 50)
        print("请在 1-decrypt-fixed.py 中使用此密钥:")
        print(f"MANUAL_KEY_V4 = \"{keys[0].hex()}\"")
        print("=" * 50)
    else:
        print(f"\n未找到密钥，耗时: {elapsed:.2f} 秒")
        print("建议: 重启微信后再试")


if __name__ == '__main__':
    try:
        from Crypto.Protocol.KDF import PBKDF2
        from Crypto.Hash import SHA512
        main()
    except ImportError:
        print("请安装: pip install pycryptodome")
