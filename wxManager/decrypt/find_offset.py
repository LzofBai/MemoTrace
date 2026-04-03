#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
临时模块：通过已知信息反向查找内存偏移量
用于校准微信版本 3.9.12.55 的偏移量
"""

import os
import sys
import ctypes
import psutil
import pymem
from win32com.client import Dispatch

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


def find_offsets():
    """查找偏移量"""
    print(f"[*] 开始查找微信 {TARGET_VERSION} 的偏移量")
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
    
    # 扫描内存查找手机号 - 全内存扫描
    print(f"\n[*] 全内存扫描查找手机号: {TARGET_PHONE}")
    phone_addrs = scan_all_memory(Handle, TARGET_PHONE)
    
    print(f"[+] 找到 {len(phone_addrs)} 个手机号地址:")
    for addr, enc, base in phone_addrs[:10]:
        if wechat_base:
            offset = addr - wechat_base
            print(f"    0x{addr:x} (偏移: {offset}, 编码: {enc})")
        else:
            print(f"    0x{addr:x} (编码: {enc})")
    
    # 扫描昵称
    print(f"\n[*] 全内存扫描查找昵称: {TARGET_NICKNAME}")
    nickname_addrs = scan_all_memory(Handle, TARGET_NICKNAME)
    
    print(f"[+] 找到 {len(nickname_addrs)} 个昵称地址:")
    for addr, enc, base in nickname_addrs[:10]:
        if wechat_base:
            offset = addr - wechat_base
            print(f"    0x{addr:x} (偏移: {offset}, 编码: {enc})")
        else:
            print(f"    0x{addr:x} (编码: {enc})")
    
    # 分析可能的偏移量
    print("\n[*] 分析可能的偏移量组合:")
    
    # 已知的参考偏移（从version_list.json）
    ref_offsets = {
        '3.9.12.51': {'name': 94555176, 'account': 94556512, 'mobile': 94554984},
        '3.9.12.45': {'name': 94503784, 'account': 94505120, 'mobile': 94503592},
    }
    
    if version in ref_offsets:
        ref = ref_offsets[version]
        print(f"\n[*] 参考版本 {version} 的偏移量:")
        print(f"    name: {ref['name']}")
        print(f"    account: {ref['account']}")
        print(f"    mobile: {ref['mobile']}")
    
    # 尝试从找到的地址推断偏移量
    if phone_addrs and nickname_addrs:
        print("\n[*] 从扫描结果推断的偏移量:")
        for phone_addr in phone_addrs[:3]:
            phone_offset = phone_addr - wechat_base
            for nick_addr in nickname_addrs[:3]:
                nick_offset = nick_addr - wechat_base
                print(f"    昵称偏移: {nick_offset}, 手机号偏移: {phone_offset}")
    
    ctypes.windll.kernel32.CloseHandle(Handle)
    
    # 建议的偏移量
    print("\n" + "="*60)
    print("[*] 建议的偏移量（基于 3.9.12.51 推断）:")
    print("    版本 3.9.12.55 与 3.9.12.51 接近，使用相同偏移量:")
    print("    name: 94555176")
    print("    account: 94556512")
    print("    mobile: 94554984")
    print("="*60)


if __name__ == '__main__':
    find_offsets()
