#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
在已知手机号地址附近扫描密钥
基于 Cheat Engine 找到的地址: 0x23414606788
"""

import os
import sys
import ctypes
import struct
import psutil
import hashlib
import hmac

# 常量
PAGE_SIZE = 4096
SALT_SIZE = 16
KEY_SIZE = 32
ROUND_COUNT = 256000

# Windows API
kernel32 = ctypes.windll.kernel32
PROCESS_ALL_ACCESS = 0x1F0FFF
PROCESS_VM_READ = 0x0010

# 已知信息
PHONE_ADDR = 0x23414606788  # Cheat Engine 找到的地址
PHONE_NUMBER = "18206740264"
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"


def open_process(pid):
    return kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)


def read_memory(process_handle, address, size):
    buffer = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)
    if kernel32.ReadProcessMemory(process_handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(bytes_read)):
        return buffer.raw
    return None


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
    paths = [
        os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db'),
        os.path.join(WX_DIR, 'db_storage', 'microMsg.db'),
        os.path.join(WX_DIR, 'db_storage', 'session.db'),
    ]
    
    for p in paths:
        if os.path.exists(p):
            with open(p, 'rb') as f:
                return f.read(4096), p
    return None, None


def scan_near_address(pid, phone_addr, buf):
    """
    在手机号地址附近扫描密钥
    根据微信内存布局，密钥通常在用户信息结构体中
    """
    print("=" * 60)
    print("Scanning near phone number address")
    print("=" * 60)
    print(f"Phone address: 0x{phone_addr:016x}")
    
    h = open_process(pid)
    if not h:
        print("Cannot open process")
        return []
    
    found_keys = []
    
    # 读取大范围上下文 (4KB 前后)
    search_start = phone_addr - 2048
    search_size = 4096 + 32
    
    print(f"\nReading memory: 0x{search_start:016x} - 0x{search_start + search_size:016x}")
    
    mem = read_memory(h, search_start, search_size)
    if not mem:
        print("Failed to read memory")
        kernel32.CloseHandle(h)
        return []
    
    print(f"Read {len(mem)} bytes")
    
    # 找到手机号在读取内存中的偏移
    phone_utf16 = PHONE_NUMBER.encode('utf-16le')
    phone_offset = mem.find(phone_utf16)
    
    if phone_offset == -1:
        print("Phone number not found in read memory")
        kernel32.CloseHandle(h)
        return []
    
    print(f"Phone number at offset: {phone_offset}")
    
    # 在手机号周围搜索密钥
    # 微信通常将密钥存储在用户信息结构体中
    # 常见偏移：-0x200, -0x100, -0x80, +0x40, +0x80 等
    
    search_ranges = [
        (phone_offset - 512, phone_offset - 32),   # 前面 512 字节
        (phone_offset - 256, phone_offset - 32),   # 前面 256 字节
        (phone_offset - 128, phone_offset - 32),   # 前面 128 字节
        (phone_offset + 32, phone_offset + 256),   # 后面 256 字节
    ]
    
    print("\nSearching for 32-byte keys...")
    
    for start, end in search_ranges:
        print(f"\nRange: offset {start} to {end}")
        
        for i in range(start, end - 32, 8):  # 步进 8 字节
            if i < 0 or i + 32 > len(mem):
                continue
            
            candidate = mem[i:i+32]
            
            # 快速过滤
            unique_bytes = len(set(candidate))
            if unique_bytes < 15:  # 随机性太低
                continue
            if candidate == b'\x00' * 32:
                continue
            
            # 检查是否全是可打印字符（密钥应该是随机的）
            printable = sum(1 for b in candidate if 32 <= b < 127)
            if printable > 20:  # 太多可打印字符，可能是字符串
                continue
            
            # 验证
            try:
                if is_ok(candidate, buf):
                    real_addr = search_start + i
                    print(f"\n[FOUND] Valid key at offset {i} (0x{real_addr:016x})")
                    print(f"  Key: {candidate.hex()}")
                    found_keys.append((candidate, real_addr))
            except:
                pass
    
    # 如果没有找到，尝试更激进的扫描
    if not found_keys:
        print("\n[!] Standard ranges failed, trying aggressive scan...")
        
        # 扫描整个 4KB 范围
        for i in range(0, len(mem) - 32, 4):  # 步进 4 字节
            candidate = mem[i:i+32]
            
            if len(set(candidate)) < 15:
                continue
            
            try:
                if is_ok(candidate, buf):
                    real_addr = search_start + i
                    print(f"\n[FOUND] Valid key at 0x{real_addr:016x}")
                    print(f"  Key: {candidate.hex()}")
                    found_keys.append((candidate, real_addr))
            except:
                pass
    
    kernel32.CloseHandle(h)
    return found_keys


def analyze_memory_structure(pid, phone_addr):
    """
    分析手机号附近的内存结构
    帮助理解微信的数据布局
    """
    print("\n" + "=" * 60)
    print("Memory Structure Analysis")
    print("=" * 60)
    
    h = open_process(pid)
    if not h:
        return
    
    # 读取大范围
    search_start = phone_addr - 1024
    mem = read_memory(h, search_start, 2048 + 32)
    
    if not mem:
        print("Failed to read memory")
        kernel32.CloseHandle(h)
        return
    
    # 找到手机号偏移
    phone_utf16 = PHONE_NUMBER.encode('utf-16le')
    phone_offset = mem.find(phone_utf16)
    
    print(f"\nPhone number at offset: {phone_offset}")
    print(f"Absolute address: 0x{search_start + phone_offset:016x}")
    
    # 显示周围的内存结构
    print("\nMemory layout around phone number:")
    print("-" * 60)
    
    # 显示前后各 256 字节
    display_start = max(0, phone_offset - 256)
    display_end = min(len(mem), phone_offset + 256)
    
    for offset in range(display_start, display_end, 16):
        hex_str = ' '.join(f'{b:02x}' for b in mem[offset:offset+16])
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in mem[offset:offset+16])
        marker = " <-- PHONE" if offset <= phone_offset < offset + 16 else ""
        print(f"{offset:04x}: {hex_str:<48} {ascii_str}{marker}")
    
    kernel32.CloseHandle(h)


def get_pid():
    """获取微信 PID"""
    for p in psutil.process_iter(['pid', 'name']):
        if p.name() == 'Weixin.exe':
            return p.pid
    return None


def main():
    print("=" * 60)
    print("WeChat Key Scanner - Near Phone Address")
    print("=" * 60)
    print(f"Target phone: {PHONE_NUMBER}")
    print(f"Phone address: 0x{PHONE_ADDR:016x}")
    
    # 获取 PID
    pid = get_pid()
    if not pid:
        print("WeChat not running!")
        return
    
    print(f"WeChat PID: {pid}")
    
    # 获取数据库
    buf, db_path = find_db()
    if not buf:
        print("Database not found!")
        return
    
    print(f"Database: {db_path}")
    
    # 分析内存结构（可选）
    analyze = input("\nAnalyze memory structure first? (y/n): ").strip().lower()
    if analyze == 'y':
        analyze_memory_structure(pid, PHONE_ADDR)
    
    # 扫描密钥
    print("\n" + "=" * 60)
    print("Scanning for keys...")
    print("=" * 60)
    
    keys = scan_near_address(pid, PHONE_ADDR, buf)
    
    if keys:
        print("\n" + "=" * 60)
        print("SUCCESS! Found valid key(s):")
        print("=" * 60)
        
        for key, addr in keys:
            print(f"\nAddress: 0x{addr:016x}")
            print(f"Key: {key.hex()}")
            print()
            print("Use this in 1-decrypt-fixed.py:")
            print(f'MANUAL_KEY_V4 = "{key.hex()}"')
        
        # 保存
        save = input("\nSave to file? (y/n): ").strip().lower()
        if save == 'y':
            with open('found_key.txt', 'w') as f:
                for key, addr in keys:
                    f.write(f"Address: 0x{addr:016x}\n")
                    f.write(f"Key: {key.hex()}\n")
            print("Saved to found_key.txt")
    else:
        print("\n[!] No valid key found")
        print("Suggestions:")
        print("1. Verify the phone address is correct")
        print("2. WeChat may have changed memory layout")
        print("3. Try scanning a larger range")


if __name__ == '__main__':
    try:
        from Crypto.Protocol.KDF import PBKDF2
        from Crypto.Hash import SHA512
        main()
    except ImportError:
        print("Please install: pip install pycryptodome")
