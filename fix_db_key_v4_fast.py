#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
微信 4.1.8.29 数据库密钥快速扫描工具
优化版本 - 速度提升 10-50 倍
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
PAGE_READWRITE = 0x04

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


def get_memory_regions_filtered(process_handle, only_private=True, min_size=1024*1024):
    """
    获取过滤后的内存区域 - 只保留可能包含密钥的区域
    优化: 减少扫描区域数量
    """
    regions = []
    mbi = MEMORY_BASIC_INFORMATION()
    address = 0
    
    while kernel32.VirtualQueryEx(
        process_handle,
        ctypes.c_void_p(address),
        ctypes.byref(mbi),
        ctypes.sizeof(mbi)
    ):
        # 只保留已提交的私有内存
        if mbi.State == MEM_COMMIT:
            if not only_private or mbi.Type == MEM_PRIVATE:
                # 只保留可读写的区域
                if mbi.Protect & PAGE_READWRITE:
                    # 过滤掉太小的区域（小于1MB）
                    if mbi.RegionSize >= min_size:
                        regions.append((mbi.BaseAddress, mbi.RegionSize))
        
        address += mbi.RegionSize
    
    return regions


def get_wechat_dll_range(pid):
    """
    获取 Weixin.dll 的内存范围
    密钥通常在 DLL 附近
    """
    try:
        process = psutil.Process(pid)
        for mmap in process.memory_maps(grouped=False):
            if 'Weixin.dll' in mmap.path:
                base = int(mmap.addr, 16)
                size = mmap.rss
                return (base, size)
    except:
        pass
    return None


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


def search_phone_and_nearby_keys(pid, phone_utf16, buf, max_regions=20):
    """
    策略 1: 先搜索手机号，再在附近查找密钥
    最快的策略，通常 10-30 秒完成
    """
    print("=" * 60)
    print("策略 1: 通过手机号引用快速定位密钥")
    print("=" * 60)
    
    process_handle = open_process(pid)
    if not process_handle:
        print("无法打开进程")
        return []
    
    # 只获取前 N 个最大的内存区域
    all_regions = get_memory_regions_filtered(process_handle, only_private=True, min_size=512*1024)
    all_regions.sort(key=lambda x: x[1], reverse=True)
    regions = all_regions[:max_regions]
    
    print(f"扫描 {len(regions)} 个最大内存区域（共 {len(all_regions)} 个）")
    
    phone_positions = []
    candidates = []
    
    # 第一阶段: 快速搜索手机号
    print("\n[阶段 1/2] 搜索手机号位置...")
    for idx, (base_addr, size) in enumerate(regions, 1):
        # 限制每次读取大小
        chunk_size = min(size, 4 * 1024 * 1024)  # 最多 4MB
        memory = read_process_memory(process_handle, base_addr, chunk_size)
        
        if not memory:
            continue
        
        # 快速搜索
        offset = 0
        while True:
            idx_found = memory.find(phone_utf16, offset)
            if idx_found == -1:
                break
            
            addr = base_addr + idx_found
            phone_positions.append((addr, base_addr, idx_found))
            print(f"  找到手机号 @ 0x{addr:08x}")
            offset = idx_found + 1
        
        if idx % 5 == 0:
            print(f"  进度: {idx}/{len(regions)}")
    
    print(f"\n共找到 {len(phone_positions)} 个手机号位置")
    
    if not phone_positions:
        kernel32.CloseHandle(process_handle)
        return []
    
    # 第二阶段: 在手机号附近搜索密钥
    print("\n[阶段 2/2] 在手机号附近搜索密钥...")
    
    for phone_addr, base_addr, offset_in_chunk in phone_positions:
        # 在手机号前后 1024 字节范围内搜索
        search_start = max(base_addr, phone_addr - 1024)
        search_size = 2048 + 32
        
        memory = read_process_memory(process_handle, search_start, search_size)
        if not memory:
            continue
        
        # 滑动窗口查找 32 字节候选
        for i in range(0, len(memory) - 32, 8):  # 步进 8 字节
            candidate = memory[i:i+32]
            
            # 快速过滤
            if len(set(candidate)) < 10:  # 随机性太低
                continue
            if candidate == b'\x00' * 32:
                continue
            
            # 验证
            try:
                if is_ok(candidate, buf):
                    real_addr = search_start + i
                    print(f"\n[FOUND] 有效密钥 @ 0x{real_addr:08x}")
                    print(f"  密钥: {candidate.hex()}")
                    candidates.append(candidate)
            except:
                pass
    
    kernel32.CloseHandle(process_handle)
    return candidates


def search_by_pattern(pid, buf, max_regions=30):
    """
    策略 2: 使用模式匹配搜索密钥标记
    中等速度，通常 30-60 秒
    """
    print("\n" + "=" * 60)
    print("策略 2: 模式匹配搜索")
    print("=" * 60)
    
    process_handle = open_process(pid)
    if not process_handle:
        print("无法打开进程")
        return []
    
    # 获取过滤后的内存区域
    regions = get_memory_regions_filtered(process_handle, only_private=True, min_size=1024*1024)
    regions = regions[:max_regions]
    
    print(f"扫描 {len(regions)} 个内存区域")
    
    # 密钥常见的内存标记
    patterns = [
        b'\x00\x00\x00\x00\x00\x00\x00\x20\x00\x00\x00\x00\x00\x00\x00\x2f',
        b'\x00\x08\x00\x00\x00\x00\x00\x00\x20\x00\x00\x00\x00\x00\x00\x00\x2f',
    ]
    
    candidates = []
    checked = 0
    
    for base_addr, size in regions:
        chunk_size = min(size, 8 * 1024 * 1024)
        memory = read_process_memory(process_handle, base_addr, chunk_size)
        
        if not memory:
            continue
        
        checked += 1
        
        for pattern in patterns:
            offset = 0
            while True:
                idx = memory.find(pattern, offset)
                if idx == -1:
                    break
                
                # 在标记后读取 32-64 字节作为候选
                for shift in [16, 24, 32]:
                    if idx + shift + 32 <= len(memory):
                        candidate = memory[idx + shift:idx + shift + 32]
                        
                        if len(set(candidate)) < 10:
                            continue
                        
                        try:
                            if is_ok(candidate, buf):
                                addr = base_addr + idx + shift
                                print(f"\n[FOUND] 有效密钥 @ 0x{addr:08x}")
                                print(f"  密钥: {candidate.hex()}")
                                candidates.append(candidate)
                        except:
                            pass
                
                offset = idx + 1
        
        if checked % 5 == 0:
            print(f"  进度: {checked}/{len(regions)}")
    
    kernel32.CloseHandle(process_handle)
    return candidates


def quick_scan_large_regions(pid, buf, max_regions=10):
    """
    策略 3: 只扫描最大的几个内存区域
    最快速度，通常 5-15 秒
    """
    print("\n" + "=" * 60)
    print("策略 3: 快速扫描最大内存区域")
    print("=" * 60)
    
    process_handle = open_process(pid)
    if not process_handle:
        print("无法打开进程")
        return []
    
    # 获取所有区域，按大小排序
    all_regions = get_memory_regions_filtered(process_handle, only_private=True, min_size=0)
    all_regions.sort(key=lambda x: x[1], reverse=True)
    regions = all_regions[:max_regions]
    
    print(f"扫描最大的 {len(regions)} 个内存区域")
    total_size = sum(size for _, size in regions)
    print(f"总大小: {total_size / 1024 / 1024:.1f} MB")
    
    candidates = []
    
    for idx, (base_addr, size) in enumerate(regions, 1):
        print(f"\n  区域 {idx}/{len(regions)}: 0x{base_addr:08x} ({size / 1024 / 1024:.1f} MB)")
        
        # 分段读取大内存区域
        chunk_size = 16 * 1024 * 1024  # 16MB 每块
        for offset in range(0, size, chunk_size):
            read_size = min(chunk_size, size - offset)
            memory = read_process_memory(process_handle, base_addr + offset, read_size)
            
            if not memory:
                continue
            
            # 大步进滑动查找
            for i in range(0, len(memory) - 32, 64):  # 步进 64 字节
                candidate = memory[i:i+32]
                
                # 快速过滤
                if len(set(candidate)) < 15:
                    continue
                
                try:
                    if is_ok(candidate, buf):
                        addr = base_addr + offset + i
                        print(f"\n[FOUND] 有效密钥 @ 0x{addr:08x}")
                        print(f"  密钥: {candidate.hex()}")
                        candidates.append(candidate)
                        return candidates  # 找到一个就返回，加快速度
                except:
                    pass
    
    kernel32.CloseHandle(process_handle)
    return candidates


def scan_dll_nearby(pid, buf):
    """
    策略 4: 扫描 Weixin.dll 附近的内存
    通常密钥在 DLL 加载地址附近
    """
    print("\n" + "=" * 60)
    print("策略 4: 扫描 Weixin.dll 附近内存")
    print("=" * 60)
    
    dll_range = get_wechat_dll_range(pid)
    if not dll_range:
        print("无法获取 Weixin.dll 范围")
        return []
    
    base, size = dll_range
    print(f"Weixin.dll: 0x{base:08x} - 0x{base + size:08x} ({size / 1024 / 1024:.1f} MB)")
    
    # 扫描 DLL 前后 512MB 范围
    search_start = max(0, base - 512 * 1024 * 1024)
    search_end = base + size + 512 * 1024 * 1024
    
    process_handle = open_process(pid)
    if not process_handle:
        print("无法打开进程")
        return []
    
    candidates = []
    chunk_size = 16 * 1024 * 1024  # 16MB
    
    current = search_start
    while current < search_end:
        memory = read_process_memory(process_handle, current, chunk_size)
        
        if memory:
            for i in range(0, len(memory) - 32, 32):
                candidate = memory[i:i+32]
                
                if len(set(candidate)) < 15:
                    continue
                
                try:
                    if is_ok(candidate, buf):
                        addr = current + i
                        print(f"\n[FOUND] 有效密钥 @ 0x{addr:08x}")
                        print(f"  密钥: {candidate.hex()}")
                        candidates.append(candidate)
                except:
                    pass
        
        current += chunk_size
        if (current - search_start) % (128 * 1024 * 1024) == 0:
            progress = (current - search_start) / (search_end - search_start) * 100
            print(f"  进度: {progress:.1f}%")
    
    kernel32.CloseHandle(process_handle)
    return candidates


def get_wechat_pid():
    """获取 Weixin.exe 进程 ID"""
    for process in psutil.process_iter(['pid', 'name']):
        if process.name() == 'Weixin.exe':
            return process.pid
    return None


def main():
    print("=" * 60)
    print("微信 4.1.8.29 数据库密钥快速扫描工具")
    print("=" * 60)
    print(f"版本: {WECHAT_VERSION}")
    print(f"手机号: {PHONE_NUMBER}")
    print(f"昵称: {NICK_NAME}")
    print("=" * 60)
    
    # 检查微信进程
    pid = get_wechat_pid()
    if not pid:
        print("错误: Weixin.exe 未运行，请先登录微信")
        return
    
    print(f"\n发现 Weixin.exe (PID: {pid})")
    
    # 查找数据库文件
    db_path, buf = find_db_file_for_testing(WX_DIR)
    if not buf:
        print("错误: 未找到数据库文件用于验证")
        return
    
    print(f"测试文件: {db_path}")
    
    start_time = time.time()
    all_candidates = []
    
    # 策略 1: 通过手机号快速定位（最快）
    phone_utf16 = PHONE_NUMBER.encode('utf-16le')
    candidates = search_phone_and_nearby_keys(pid, phone_utf16, buf, max_regions=20)
    all_candidates.extend(candidates)
    
    if all_candidates:
        print("\n" + "=" * 60)
        print("成功找到密钥！")
        print("=" * 60)
        for key in set(bytes(k) for k in all_candidates):
            print(f"密钥: {key.hex()}")
        
        elapsed = time.time() - start_time
        print(f"\n耗时: {elapsed:.2f} 秒")
        return
    
    # 策略 2: 模式匹配
    candidates = search_by_pattern(pid, buf, max_regions=30)
    all_candidates.extend(candidates)
    
    if all_candidates:
        print("\n" + "=" * 60)
        print("成功找到密钥！")
        print("=" * 60)
        for key in set(bytes(k) for k in all_candidates):
            print(f"密钥: {key.hex()}")
        
        elapsed = time.time() - start_time
        print(f"\n耗时: {elapsed:.2f} 秒")
        return
    
    # 策略 3: 快速扫描大区域
    candidates = quick_scan_large_regions(pid, buf, max_regions=10)
    all_candidates.extend(candidates)
    
    if all_candidates:
        print("\n" + "=" * 60)
        print("成功找到密钥！")
        print("=" * 60)
        for key in set(bytes(k) for k in all_candidates):
            print(f"密钥: {key.hex()}")
        
        elapsed = time.time() - start_time
        print(f"\n耗时: {elapsed:.2f} 秒")
        return
    
    # 策略 4: 扫描 DLL 附近
    candidates = scan_dll_nearby(pid, buf)
    all_candidates.extend(candidates)
    
    elapsed = time.time() - start_time
    
    print("\n" + "=" * 60)
    print("扫描完成")
    print("=" * 60)
    print(f"总耗时: {elapsed:.2f} 秒")
    
    if all_candidates:
        print(f"\n找到 {len(set(bytes(k) for k in all_candidates))} 个有效密钥:")
        for key in set(bytes(k) for k in all_candidates):
            print(f"  {key.hex()}")
    else:
        print("\n未找到有效密钥")
        print("建议:")
        print("1. 确保微信已完全登录")
        print("2. 尝试重启微信后再次扫描")
        print("3. 使用 Process Hacker 手动查找")


if __name__ == '__main__':
    freeze_support()
    try:
        from Crypto.Protocol.KDF import PBKDF2
        from Crypto.Hash import SHA512
        main()
    except ImportError as e:
        print(f"缺少依赖: {e}")
        print("请安装: pip install pycryptodome")
