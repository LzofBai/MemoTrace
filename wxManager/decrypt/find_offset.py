#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
临时模块：通过已知信息反向查找内存偏移量
用于校准微信版本 3.9.12.55 的偏移量
"""

import os
import sys
import ctypes
import json
import psutil
import pymem
from win32com.client import Dispatch
from pathlib import Path

# 已知正确信息
TARGET_PHONE = "18206740264"
TARGET_NICKNAME = "啊伟"
TARGET_VERSION = "3.9.12.55"

ReadProcessMemory = ctypes.windll.kernel32.ReadProcessMemory
void_p = ctypes.c_void_p


def get_exe_bit(file_path):
    """获取 PE 文件的位数"""
    try:
        with open(file_path, 'rb') as f:
            dos_header = f.read(2)
            if dos_header != b'MZ':
                return 64
            f.seek(60)
            pe_offset = int.from_bytes(f.read(4), byteorder='little')
            f.seek(pe_offset + 4)
            machine = int.from_bytes(f.read(2), byteorder='little')
            if machine == 0x14c:
                return 32
            elif machine == 0x8664:
                return 64
    except:
        pass
    return 64


def read_memory(h_process, address, n_size=128):
    """读取内存字节"""
    array = ctypes.create_string_buffer(n_size)
    if ReadProcessMemory(h_process, void_p(address), array, n_size, 0) == 0:
        return None
    return bytes(array)


def decode_utf8(data):
    """尝试UTF-8解码"""
    try:
        text = data.split(b'\x00')[0].decode('utf-8', errors='ignore')
        return text.strip() if text.strip() else None
    except:
        return None


def decode_utf16le(data):
    """尝试UTF-16LE解码"""
    try:
        text = data.decode('utf-16le', errors='ignore').split('\x00')[0]
        return text.strip() if text.strip() else None
    except:
        return None


def scan_for_string(h_process, base_addr, size, target, encoding='utf-16le'):
    """扫描内存区域查找目标字符串"""
    results = []
    chunk_size = 4096
    
    # 准备不同编码的目标字节
    target_utf8 = target.encode('utf-8')
    target_utf16le = target.encode('utf-16le')
    # 尝试带BOM的UTF-16
    target_utf16le_bom = b'\xff\xfe' + target_utf16le
    
    for offset in range(0, size, chunk_size):
        addr = base_addr + offset
        data = read_memory(h_process, addr, min(chunk_size, size - offset))
        if not data:
            continue
        
        # 检查各种编码
        for target_bytes, enc_name in [(target_utf16le, 'utf-16le'), 
                                        (target_utf8, 'utf-8'),
                                        (target_utf16le_bom, 'utf-16le-bom')]:
            idx = 0
            while True:
                idx = data.find(target_bytes, idx)
                if idx == -1:
                    break
                found_addr = addr + idx
                results.append((found_addr, enc_name))
                idx += 1
    
    return results


def scan_all_memory(h_process, target):
    """扫描所有可访问内存"""
    results = []
    target_utf16le = target.encode('utf-16le')
    target_utf8 = target.encode('utf-8')
    
    # 获取所有内存区域
    process = psutil.Process()
    for proc in psutil.process_iter(['pid']):
        if proc.pid == process.pid:
            continue
    
    # 使用 pymem 扫描
    pm = pymem.Pymem("WeChat.exe")
    
    # 扫描整个内存空间
    addr = 0
    while addr < 0x7FFFFFFF0000:
        try:
            mbi = pymem.memory.virtual_query(pm.process_handle, addr)
            if mbi.state == pymem.structures.MEMORY_STATE.MEM_COMMIT:
                try:
                    data = pymem.memory.read_bytes(pm.process_handle, mbi.BaseAddress, mbi.RegionSize)
                    # 查找UTF-16LE
                    idx = data.find(target_utf16le)
                    if idx != -1:
                        found_addr = mbi.BaseAddress + idx
                        results.append((found_addr, 'utf-16le', mbi.BaseAddress))
                    # 查找UTF-8
                    idx = data.find(target_utf8)
                    if idx != -1:
                        found_addr = mbi.BaseAddress + idx
                        results.append((found_addr, 'utf-8', mbi.BaseAddress))
                except:
                    pass
            addr = mbi.BaseAddress + mbi.RegionSize
        except:
            addr += 0x1000
    
    return results


def test_offset(Handle, wechat_base, name_offset, account_offset, mobile_offset):
    """测试一组偏移量是否正确"""
    name_addr = wechat_base + name_offset
    account_addr = wechat_base + account_offset
    mobile_addr = wechat_base + mobile_offset
    
    # 读取数据
    name_data = read_memory(Handle, name_addr, 128)
    account_data = read_memory(Handle, account_addr, 64)
    mobile_data = read_memory(Handle, mobile_addr, 64)
    
    if not name_data or not account_data or not mobile_data:
        return None
    
    # 尝试解码
    results = {}
    
    # 昵称 - 尝试UTF-16LE和UTF-8
    name_utf16 = decode_utf16le(name_data)
    name_utf8 = decode_utf8(name_data)
    results['name'] = name_utf16 if name_utf16 else name_utf8
    
    # 账号
    account_utf16 = decode_utf16le(account_data)
    account_utf8 = decode_utf8(account_data)
    results['account'] = account_utf16 if account_utf16 else account_utf8
    
    # 手机号
    mobile_utf16 = decode_utf16le(mobile_data)
    mobile_utf8 = decode_utf8(mobile_data)
    results['mobile'] = mobile_utf16 if mobile_utf16 else mobile_utf8
    
    return results


def find_offsets():
    """查找偏移量"""
    print(f"[*] 开始验证微信 {TARGET_VERSION} 的偏移量")
    print(f"[*] 目标手机号: {TARGET_PHONE}")
    print(f"[*] 目标昵称: {TARGET_NICKNAME}")
    
    # 查找微信进程
    wechat_pid = None
    wechat_exe = None
    for process in psutil.process_iter(['name', 'exe', 'pid']):
        if process.name() == 'WeChat.exe':
            wechat_pid = process.pid
            wechat_exe = process.exe()
            break
    
    if not wechat_pid:
        print("[-] 未找到微信进程，请先登录微信")
        return
    
    print(f"[+] 找到微信进程 PID: {wechat_pid}")
    
    # 获取版本
    try:
        version = Dispatch("Scripting.FileSystemObject").GetFileVersion(wechat_exe)
        print(f"[+] 微信版本: {version}")
    except:
        print("[-] 无法获取版本号")
        return
    
    # 获取WeChatWin.dll基址
    wechat_base = 0
    for module in psutil.Process(wechat_pid).memory_maps(grouped=False):
        if module.path and 'WeChatWin.dll' in module.path:
            wechat_base = int(module.addr, 16)
            break
    
    if wechat_base == 0:
        print("[-] 未找到 WeChatWin.dll")
        return
    
    print(f"[+] WeChatWin.dll 基址: 0x{wechat_base:x}")
    
    # 打开进程
    Handle = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, wechat_pid)
    pm = pymem.Pymem("WeChat.exe")
    
    print("\n[*] 步骤1: 在内存中搜索手机号...")
    phone_addrs = pm.pattern_scan_all(TARGET_PHONE.encode('utf-16le'), return_multiple=True)
    print(f"[+] 找到 {len(phone_addrs)} 个手机号地址")
    
    if not phone_addrs:
        print("[-] 未找到手机号")
        return
    
    phone_data_addr = phone_addrs[0]
    print(f"    第一个地址: 0x{phone_data_addr:x}")
    
    print("\n[*] 步骤2: 在内存中搜索昵称...")
    name_addrs = pm.pattern_scan_all(TARGET_NICKNAME.encode('utf-16le'), return_multiple=True)
    print(f"[+] 找到 {len(name_addrs)} 个昵称地址")
    
    if not name_addrs:
        print("[-] 未找到昵称")
        return
    
    name_data_addr = name_addrs[0]
    print(f"    第一个地址: 0x{name_data_addr:x}")
    
    print("\n[*] 步骤3: 在 WeChatWin.dll 中搜索指向手机号的指针...")
    # 在整个 DLL 范围内搜索（约 100MB）
    dll_size = 200 * 1024 * 1024  # 200MB
    
    mobile_pointer_offset = None
    name_pointer_offset = None
    
    # 分块搜索，每次 1MB
    chunk_size = 1024 * 1024
    for chunk_start in range(0, min(dll_size, 150*1024*1024), chunk_size):
        chunk_end = min(chunk_start + chunk_size, dll_size)
        
        for offset in range(chunk_start, chunk_end, 8):
            addr = wechat_base + offset
            
            ptr_buf = ctypes.create_string_buffer(8)
            if ReadProcessMemory(Handle, void_p(addr), ptr_buf, 8, 0) == 0:
                continue
            
            ptr = int.from_bytes(bytes(ptr_buf), byteorder='little')
            
            # 检查是否指向手机号
            if ptr == phone_data_addr and mobile_pointer_offset is None:
                mobile_pointer_offset = offset
                print(f"[+] 找到手机号指针! 偏移: {offset}, 地址: 0x{addr:x}")
            
            # 检查是否指向昵称
            if ptr == name_data_addr and name_pointer_offset is None:
                name_pointer_offset = offset
                print(f"[+] 找到昵称指针! 偏移: {offset}, 地址: 0x{addr:x}")
            
            # 如果都找到了，退出
            if mobile_pointer_offset and name_pointer_offset:
                break
        
        if mobile_pointer_offset and name_pointer_offset:
            break
        
        # 每 10MB 显示进度
        if chunk_start % (10*1024*1024) == 0:
            print(f"    进度: {chunk_start // (1024*1024)}MB...")
    
    ctypes.windll.kernel32.CloseHandle(Handle)
    
    print("\n" + "="*70)
    if mobile_pointer_offset and name_pointer_offset:
        print("✅ 成功找到偏移量!")
        print("="*70)
        print(f"\n建议配置:")
        print(f"[")
        print(f"  {name_pointer_offset},      // name (昵称)")
        print(f"  {name_pointer_offset},      // account (账号)")
        print(f"  {mobile_pointer_offset},    // mobile (手机号)")
        print(f"  0,                          // mail")
        print(f"  0                           // key")
        print(f"]")
        
        config = {
            TARGET_VERSION: [
                name_pointer_offset,
                name_pointer_offset,
                mobile_pointer_offset,
                0,
                0
            ]
        }
        
        print(f"\nJSON 格式:")
        print(json.dumps(config, indent=4))
        
        update = input("\n是否更新 version_list.json? (y/n): ").strip().lower()
        if update == 'y':
            import json as json_module
            version_list_path = Path(__file__).parent / 'version_list.json'
            with open(version_list_path, 'r', encoding='utf-8') as f:
                version_list = json_module.load(f)

            # 保留已有的 key 偏移量（如果存在），避免被 0 覆盖
            existing = version_list.get(TARGET_VERSION)
            if existing and isinstance(existing, list) and len(existing) > 4 and existing[4] != 0:
                config[TARGET_VERSION][4] = existing[4]
                print(f"[INFO] 保留已有的 key 偏移量: {existing[4]}")
            else:
                print("[WARN] key 偏移量为 0，如需使用 key 偏移读取，请手动填入或从相近版本继承")

            version_list[TARGET_VERSION] = config[TARGET_VERSION]

            with open(version_list_path, 'w', encoding='utf-8') as f:
                json_module.dump(version_list, f, indent=4, ensure_ascii=False)

            print("✅ 已更新 version_list.json")
            print("请重启 app.py 测试")
    else:
        print("❌ 未找到完整的偏移量")
        if mobile_pointer_offset:
            print(f"   找到手机号指针: {mobile_pointer_offset}")
        if name_pointer_offset:
            print(f"   找到昵称指针: {name_pointer_offset}")
    print("="*70)


if __name__ == '__main__':
    find_offsets()
