#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信 4.1.8.29 版本内存分析和密钥定位工具
用于反推 get_decode_code_v4() 和 get_info_v4() 的正确实现
"""

import os
import sys
import ctypes
import struct
import psutil

# 加载 Windows API
kernel32 = ctypes.windll.kernel32
PROCESS_ALL_ACCESS = 0x1F0FFF
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

# 已知信息
WECHAT_VERSION = "4.1.8.29"
PHONE_NUMBER = "18206740264"
NICK_NAME = "啊伟"
KNOWN_KEY = "c9eaed112cbb4dd896a5dd7314186a24598951f2efff4afe812fb7556f4fc4ce"
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"

# 密钥字节
KEY_BYTES = bytes.fromhex(KNOWN_KEY)


def open_process(pid):
    """打开进程"""
    return kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)


def read_process_memory(process_handle, address, size):
    """读取进程内存"""
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


def get_memory_regions(process_handle):
    """获取所有内存区域"""
    regions = []
    mbi = MEMORY_BASIC_INFORMATION()
    address = 0
    MEM_COMMIT = 0x1000
    MEM_PRIVATE = 0x20000
    
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


def find_key_in_memory(pid):
    """在内存中查找已知密钥"""
    print("=" * 60)
    print(f"在 Weixin.exe (PID: {pid}) 内存中查找密钥")
    print("=" * 60)
    
    process_handle = open_process(pid)
    if not process_handle:
        print("无法打开进程")
        return None
    
    regions = get_memory_regions(process_handle)
    print(f"找到 {len(regions)} 个内存区域")
    
    matches = []
    checked = 0
    
    for base_addr, size in regions:
        # 限制大小，避免读取过大区域
        read_size = min(size, 1024 * 1024)  # 每次最多 1MB
        
        memory = read_process_memory(process_handle, base_addr, read_size)
        if not memory:
            continue
        
        checked += 1
        
        # 查找完整密钥
        offset = memory.find(KEY_BYTES)
        if offset != -1:
            addr = base_addr + offset
            print(f"\n[发现] 完整密钥 @ 0x{addr:08x}")
            print(f"  所在区域: 0x{base_addr:08x} - 0x{base_addr + size:08x}")
            matches.append((addr, "full_key"))
        
        # 查找密钥特征（前8字节）
        if len(matches) < 5:
            key_prefix = KEY_BYTES[:8]
            offset = 0
            while True:
                offset = memory.find(key_prefix, offset)
                if offset == -1:
                    break
                addr = base_addr + offset
                # 验证后续字节
                candidate = memory[offset:offset+32]
                if len(candidate) == 32:
                    match_count = sum(1 for a, b in zip(candidate, KEY_BYTES) if a == b)
                    if match_count >= 24:  # 至少24字节匹配
                        print(f"\n[发现] 部分匹配密钥 @ 0x{addr:08x} (匹配 {match_count}/32 字节)")
                        print(f"  候选密钥: {candidate.hex()}")
                        matches.append((addr, f"partial_{match_count}"))
                offset += 1
    
    kernel32.CloseHandle(process_handle)
    print(f"\n检查了 {checked} 个内存区域")
    print(f"找到 {len(matches)} 个匹配")
    
    return matches


def find_phone_in_memory(pid):
    """在内存中查找手机号，帮助定位用户信息结构"""
    print("\n" + "=" * 60)
    print(f"在内存中查找手机号: {PHONE_NUMBER}")
    print("=" * 60)
    
    process_handle = open_process(pid)
    if not process_handle:
        print("无法打开进程")
        return
    
    # 手机号的不同编码
    phone_utf8 = PHONE_NUMBER.encode('utf-8')
    phone_utf16 = PHONE_NUMBER.encode('utf-16le')
    
    regions = get_memory_regions(process_handle)
    
    for base_addr, size in regions[:50]:  # 只检查前50个区域
        read_size = min(size, 512 * 1024)
        memory = read_process_memory(process_handle, base_addr, read_size)
        if not memory:
            continue
        
        # 查找 UTF-16 编码的手机号
        offset = memory.find(phone_utf16)
        if offset != -1:
            addr = base_addr + offset
            print(f"\n[发现] 手机号 (UTF-16LE) @ 0x{addr:08x}")
            # 读取周围数据
            context_start = max(0, offset - 128)
            context_end = min(len(memory), offset + 128)
            context = memory[context_start:context_end]
            print(f"  上下文 (hex): {context.hex()}")
            
            # 尝试查找附近的昵称
            try:
                nickname_utf16 = NICK_NAME.encode('utf-16le')
                nick_offset = context.find(nickname_utf16)
                if nick_offset != -1:
                    print(f"  [发现] 昵称在附近! 偏移: {nick_offset - offset}")
            except:
                pass
    
    kernel32.CloseHandle(process_handle)


def analyze_wechat_dll(pid):
    """分析 Weixin.dll 的基址和大小"""
    print("\n" + "=" * 60)
    print("分析 Weixin.dll 信息")
    print("=" * 60)
    
    for process in psutil.process_iter(['pid', 'name', 'memory_maps']):
        if process.pid == pid:
            try:
                for mmap in process.memory_maps(grouped=False):
                    if 'Weixin.dll' in mmap.path:
                        base_addr = int(mmap.addr, 16)
                        size = mmap.rss
                        print(f"Weixin.dll:")
                        print(f"  基址: 0x{base_addr:08x}")
                        print(f"  大小: {size} bytes ({size/1024/1024:.2f} MB)")
                        print(f"  路径: {mmap.path}")
                        return base_addr
            except:
                pass
    return None


def find_xor_key_in_cache():
    """在缓存中查找图片异或密钥"""
    print("\n" + "=" * 60)
    print("查找图片异或密钥 (get_decode_code_v4 分析)")
    print("=" * 60)
    
    cache_dir = os.path.join(WX_DIR, 'cache')
    
    if not os.path.exists(cache_dir):
        print(f"缓存目录不存在: {cache_dir}")
        # 尝试其他目录
        for subdir in ['temp', 'msg']:
            alt_dir = os.path.join(WX_DIR, subdir)
            if os.path.exists(alt_dir):
                cache_dir = alt_dir
                break
    
    if not os.path.exists(cache_dir):
        print("未找到任何缓存目录")
        return
    
    print(f"搜索目录: {cache_dir}")
    
    # 查找 _t.dat 文件
    dat_files = []
    for root, dirs, files in os.walk(cache_dir):
        for file in files:
            if file.endswith('.dat'):
                dat_files.append(os.path.join(root, file))
    
    print(f"找到 {len(dat_files)} 个 .dat 文件")
    
    # V4 图片加密头部
    V4_HEADERS = [
        b'\x07\x08V1\x08\x07',
        b'\x07\x08V2\x08\x07',
    ]
    
    for dat_file in dat_files[:10]:
        try:
            with open(dat_file, 'rb') as f:
                data = f.read()
            
            if len(data) < 16:
                continue
            
            header = data[:16]
            
            # 检查 V4 格式
            is_v4 = any(header.startswith(h) for h in V4_HEADERS)
            
            print(f"\n文件: {os.path.basename(dat_file)}")
            print(f"  大小: {len(data)} bytes")
            print(f"  头部: {header.hex()}")
            
            if is_v4:
                print(f"  格式: V4 AES 加密")
                # 提取加密长度
                encrypt_length = struct.unpack_from('<H', header, 6)[0]
                print(f"  加密长度: {encrypt_length}")
                # V4 使用固定 AES 密钥，不需要异或密钥
            else:
                print(f"  格式: 可能是传统 XOR 加密")
                # 尝试推导异或密钥（基于 JPG 文件尾）
                if len(data) >= 2:
                    jpg_tail = b'\xff\xd9'
                    file_tail = data[-2:]
                    xor_key = [c ^ p for c, p in zip(file_tail, jpg_tail)]
                    if len(set(xor_key)) == 1:
                        print(f"  推导的异或密钥: 0x{xor_key[0]:02x}")
                    
        except Exception as e:
            print(f"  错误: {e}")


def suggest_memory_pattern():
    """基于已知信息建议内存搜索模式"""
    print("\n" + "=" * 60)
    print("建议的内存搜索模式 (用于更新 YARA 规则)")
    print("=" * 60)
    
    # 密钥字节
    key = KEY_BYTES
    
    print(f"\n完整密钥 (hex): {key.hex()}")
    print(f"密钥长度: {len(key)} bytes")
    
    # 常见的密钥存储模式
    print("\n可能的内存存储模式:")
    
    # 模式1: 直接存储
    print(f"  1. 直接存储: {key.hex()}")
    
    # 模式2: 带长度前缀
    length_prefix = struct.pack('<Q', 32)  # 64位长度
    print(f"  2. 64位长度前缀: {length_prefix.hex()} {key.hex()}")
    
    # 模式3: 带指针结构
    print(f"  3. 可能的指针指向密钥地址")
    
    # 基于手机号的模式
    phone_bytes = PHONE_NUMBER.encode('utf-16le')
    print(f"\n手机号 UTF-16LE (hex): {phone_bytes.hex()}")
    
    # 昵称
    nick_bytes = NICK_NAME.encode('utf-16le')
    print(f"昵称 UTF-16LE (hex): {nick_bytes.hex()}")
    
    print("\n建议的 YARA 规则片段:")
    print("""
    rule FindKey_41829 {
        strings:
            // 直接搜索密钥前8字节
            $key_prefix = { """ + key[:8].hex() + """ }
            
            // 手机号 UTF-16LE
            $phone = { """ + phone_bytes.hex() + """ }
            
        condition:
            $key_prefix or $phone
    }
    """)


def check_process_running():
    """检查微信进程是否运行"""
    print("=" * 60)
    print("检查微信进程")
    print("=" * 60)
    
    weixin_found = False
    for process in psutil.process_iter(['pid', 'name', 'exe']):
        if process.name() == 'Weixin.exe':
            weixin_found = True
            print(f"\n发现 Weixin.exe:")
            print(f"  PID: {process.pid}")
            try:
                print(f"  路径: {process.exe()}")
            except:
                pass
            return process.pid
    
    if not weixin_found:
        print("\n错误: 未找到 Weixin.exe 进程")
        print("请确保微信 4.x 正在运行并已登录")
        return None


if __name__ == '__main__':
    print("微信 4.1.8.29 版本内存分析工具")
    print("用于反推 get_decode_code_v4() 和 get_info_v4() 的正确实现")
    print()
    
    # 检查微信是否运行
    pid = check_process_running()
    
    if pid:
        # 分析 DLL
        dll_base = analyze_wechat_dll(pid)
        
        # 查找密钥
        matches = find_key_in_memory(pid)
        
        # 查找手机号
        find_phone_in_memory(pid)
    
    # 分析缓存
    find_xor_key_in_cache()
    
    # 建议模式
    suggest_memory_pattern()
    
    print("\n" + "=" * 60)
    print("分析完成")
    print("=" * 60)
    print("""
根据分析结果，您可以:
1. 如果找到密钥在内存中的位置，更新 wx_info_v4.py 中的 YARA 规则
2. 如果找到手机号/昵称的结构，更新偏移量计算
3. 如果是图片解密问题，检查是否需要新的 AES 密钥
""")
