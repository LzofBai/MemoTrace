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
    
    # 测试已知的偏移量组合
    test_offsets = [
        # 基于 3.9.12.51
        {'name': 94555176, 'account': 94556512, 'mobile': 94554984, 'desc': '3.9.12.51 基准'},
        # 附近偏移量
        {'name': 94555176, 'account': 94556512, 'mobile': 94554984 + 8, 'desc': 'mobile +8'},
        {'name': 94555176, 'account': 94556512, 'mobile': 94554984 - 8, 'desc': 'mobile -8'},
        {'name': 94555176 + 8, 'account': 94556512 + 8, 'mobile': 94554984 + 8, 'desc': '全部 +8'},
        {'name': 94555176 - 8, 'account': 94556512 - 8, 'mobile': 94554984 - 8, 'desc': '全部 -8'},
        # 更大范围
        {'name': 94555176 + 16, 'account': 94556512 + 16, 'mobile': 94554984 + 16, 'desc': '全部 +16'},
        {'name': 94555176 + 24, 'account': 94556512 + 24, 'mobile': 94554984 + 24, 'desc': '全部 +24'},
        {'name': 94555176 + 32, 'account': 94556512 + 32, 'mobile': 94554984 + 32, 'desc': '全部 +32'},
    ]
    
    print("\n[*] 测试已知偏移量组合:")
    best_match = None
    best_score = 0
    
    for offset in test_offsets:
        results = test_offset(Handle, wechat_base, offset['name'], offset['account'], offset['mobile'])
        if results:
            score = 0
            if results['name'] == TARGET_NICKNAME:
                score += 2
            elif results['name'] and len(results['name']) > 0:
                score += 1
                
            if results['mobile'] == TARGET_PHONE:
                score += 2
            elif results['mobile'] and len(str(results['mobile'])) == 11:
                score += 1
            
            status = ""
            if results['name'] == TARGET_NICKNAME:
                status += "[昵称OK]"
            if results['mobile'] == TARGET_PHONE:
                status += "[手机号OK]"
            
            print(f"\n  {offset['desc']}:")
            print(f"    name={results['name']}, mobile={results['mobile']}, account={results['account']} {status}")
            
            if score > best_score:
                best_score = score
                best_match = {'offset': offset, 'results': results}
    
    ctypes.windll.kernel32.CloseHandle(Handle)
    
    # 输出最佳匹配
    print("\n" + "="*60)
    if best_match and best_score >= 2:
        print("[*] 最佳匹配偏移量:")
        print(f"    name: {best_match['offset']['name']}")
        print(f"    account: {best_match['offset']['account']}")
        print(f"    mobile: {best_match['offset']['mobile']}")
        print(f"\n[*] 读取结果:")
        print(f"    昵称: {best_match['results']['name']}")
        print(f"    账号: {best_match['results']['account']}")
        print(f"    手机号: {best_match['results']['mobile']}")
    else:
        print("[-] 未找到匹配的偏移量")
        print("[*] 当前版本 3.9.12.55 可能需要新的偏移量")
    print("="*60)


if __name__ == '__main__':
    find_offsets()
