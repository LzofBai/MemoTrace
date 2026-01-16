#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/3/7 16:30 
@Author      : SiYuan 
@Email       : 863909694@qq.com 
@File        : MemoTrace-wx_info_v3.py 
@Description : 
"""

# -*- coding: utf-8 -*-#
# -------------------------------------------------------------------------------
# Name:         getwxinfo.py
# Description:
# Author:       xaoyaoo
# Date:         2023/08/21
# -------------------------------------------------------------------------------

import os
import sys
import hmac
import hashlib
import ctypes
import winreg
import pymem
import pythoncom
import psutil
import pymem.process

from wxManager.decrypt.common import WeChatInfo
from wxManager.decrypt.common import get_version

ReadProcessMemory = ctypes.windll.kernel32.ReadProcessMemory
void_p = ctypes.c_void_p


def get_exe_bit(file_path):
    """
    获取可执行文件的位数（32位或64位）

    通过读取PE（Portable Executable）文件头信息来判断Windows可执行文件是32位还是64位。
    函数会检查DOS头、PE签名以及Machine字段来确定架构类型。

    Args:
        file_path (str): 可执行文件的路径

    Returns:
        int: 返回可执行文件的位数，32表示32位，64表示64位或其他情况
    """
    try:
        with open(file_path, 'rb') as f:
            dos_header = f.read(2)
            if dos_header != b'MZ':
                print('get exe bit error: Invalid PE file')
                return 64
            # Seek to the offset of the PE signature
            f.seek(60)
            pe_offset_bytes = f.read(4)
            pe_offset = int.from_bytes(pe_offset_bytes, byteorder='little')

            # Seek to the Machine field in the PE header
            f.seek(pe_offset + 4)
            machine_bytes = f.read(2)
            machine = int.from_bytes(machine_bytes, byteorder='little')

            if machine == 0x14c:
                return 32
            elif machine == 0x8664:
                return 64
            else:
                return 64
    except:
        return 64


def get_info_without_key(h_process, address, n_size=64):
    """
    从指定进程内存地址读取信息并转换为字符串
    
    该函数通过调用ReadProcessMemory从指定进程中读取数据，
    将读取的数据转换为字符串格式并去除空字符和空白字符。
    
    Args:
        h_process: 进程句柄，用于标识要读取的目标进程
        address: 内存地址，表示要读取数据的起始位置
        n_size: 要读取的字节数，默认为64字节
    
    Returns:
        str: 成功时返回读取到的字符串内容（已去除空字符和首尾空白），
             失败或无有效内容时返回"None"
    """
    array = ctypes.create_string_buffer(n_size)  # 创建一个指定大小的缓冲区来存储读取的数据
    if ReadProcessMemory(h_process, void_p(address), array, n_size, 0) == 0: return "None"  # 尝试从目标进程内存中读取数据
    array = bytes(array).split(b"\x00")[0] if b"\x00" in array else bytes(array)  # 分割字节数组以去除空终止符后的部分
    text = array.decode('utf-8', errors='ignore')  # 将字节数组解码为UTF-8字符串
    return text.strip() if text.strip() != "" else "None"  # 去除字符串首尾空白并返回结果


def pattern_scan_all(handle, pattern, *, return_multiple=False, find_num=100):
    """
    在内存中扫描指定的字节模式，查找所有匹配项或第一个匹配项

    参数:
        handle: 进程句柄，用于访问目标进程内存
        pattern (bytes): 要搜索的字节模式
        return_multiple (bool, optional): 是否返回多个结果，默认为False
        find_num (int, optional): 最大查找数量限制，默认为100

    返回:
        如果return_multiple为True，返回找到的所有地址列表；否则返回第一个找到的地址
    """
    # 初始化下一个要扫描的内存区域起始地址
    next_region = 0
    # 存储找到的地址
    found = []
    # 根据系统架构确定用户空间地址上限
    user_space_limit = 0x7FFFFFFF0000 if sys.maxsize > 2 ** 32 else 0x7fff0000
    while next_region < user_space_limit:
        try:
            # 扫描单个内存页以查找模式
            next_region, page_found = pymem.pattern.scan_pattern_page(
                handle,
                next_region,
                pattern,
                return_multiple=return_multiple
            )
        except Exception as e:
            print(e)
            break
        # 如果只需要返回单个结果且找到了匹配项，则直接返回
        if not return_multiple and page_found:
            return page_found
        # 如果在当前页面找到匹配项，将其添加到结果列表
        if page_found:
            found += page_found
        # 检查是否已找到足够的匹配项
        if len(found) > find_num:
            break
    return found


def get_info_wxid(h_process):
    """
    从微信进程内存中获取微信号ID
    
    参数:
        h_process: 进程句柄，用于读取目标进程的内存
    
    返回值:
        str: 微信号ID，如果无法获取则返回"None"
    """
    # 设置查找数量限制
    find_num = 100
    # 在进程中扫描包含'\\Msg\\FTSContact'模式的所有地址
    addrs = pattern_scan_all(h_process, br'\\Msg\\FTSContact', return_multiple=True, find_num=find_num)
    wxids = []
    for addr in addrs:
        # 创建一个80字节的缓冲区来存储读取的数据
        array = ctypes.create_string_buffer(80)
        # 从进程内存中读取数据到缓冲区
        if ReadProcessMemory(h_process, void_p(addr - 30), array, 80, 0) == 0: return "None"
        array = bytes(array)  # .split(b"\\")[0]
        # 提取微信号部分，先截断到"\Msg"位置
        array = array.split(b"\\Msg")[0]
        # 获取最后一个反斜杠后的部分（即微信号）
        array = array.split(b"\\")[-1]
        # 将字节数组转换为字符串并添加到列表
        wxids.append(array.decode('utf-8', errors='ignore'))
    # 使用出现次数最多的微信号作为结果
    wxid = max(wxids, key=wxids.count) if wxids else "None"
    return wxid


def get_wx_dir(wxid):
    """
    根据微信号获取微信文件存储目录路径

    参数:
        wxid (str): 微信号ID

    返回值:
        str: 微信文件存储目录路径，如果无法获取则返回空字符串
    """
    if not wxid:
        return ''
    try:
        is_w_dir = False
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Tencent\WeChat", 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "FileSavePath")
            winreg.CloseKey(key)
            w_dir = value
            is_w_dir = True
        except Exception as e:
            w_dir = "MyDocument:"

        if not is_w_dir:
            try:
                user_profile = os.environ.get("USERPROFILE")
                path_3ebffe94 = os.path.join(user_profile, "AppData", "Roaming", "Tencent", "WeChat", "All Users",
                                             "config",
                                             "3ebffe94.ini")
                with open(path_3ebffe94, "r", encoding="utf-8") as f:
                    w_dir = f.read()
                is_w_dir = True
            except Exception as e:
                w_dir = "MyDocument:"

        if w_dir == "MyDocument:":
            try:
                # 打开注册表路径
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
                documents_path = winreg.QueryValueEx(key, "Personal")[0]  # 读取文档实际目录路径
                winreg.CloseKey(key)  # 关闭注册表
                documents_paths = os.path.split(documents_path)
                if "%" in documents_paths[0]:
                    w_dir = os.environ.get(documents_paths[0].replace("%", ""))
                    w_dir = os.path.join(w_dir, os.path.join(*documents_paths[1:]))
                    # print(1, w_dir)
                else:
                    w_dir = documents_path
            except Exception as e:
                profile = os.environ.get("USERPROFILE")
                w_dir = os.path.join(profile, "Documents")
        msg_dir = os.path.join(w_dir, "WeChat Files", wxid)
        return msg_dir
    except FileNotFoundError:
        return ''


def get_key(db_path, addr_len):
    """
    从微信进程中获取数据库解密密钥

    参数:
        db_path (str): 微信数据库路径
        addr_len (int): 地址长度（字节）

    返回值:
        str: 32字节密钥的十六进制字符串表示，如果获取失败则返回空字符串
    """
    
    def read_key_bytes(h_process, address, address_len=8):
        """
        从指定内存地址读取密钥字节
        
        参数:
            h_process: 进程句柄
            address: 内存地址
            address_len: 要读取的地址长度，默认为8字节
            
        返回:
            bytes: 读取到的密钥字节，失败则返回空字符串
        """
        array = ctypes.create_string_buffer(address_len)
        if ReadProcessMemory(h_process, void_p(address), array, address_len, 0) == 0: return ""
        address = int.from_bytes(array, byteorder='little')  # 逆序转换为int地址（key地址）
        key = ctypes.create_string_buffer(32)
        if ReadProcessMemory(h_process, void_p(address), key, 32, 0) == 0: return ""
        key_bytes = bytes(key)
        return key_bytes

    def verify_key(key, wx_db_path):
        """
        验证密钥是否正确
        
        参数:
            key (bytes): 待验证的密钥
            wx_db_path (str): 微信数据库路径
            
        返回:
            bool: 密钥是否正确
        """
        if not wx_db_path:
            return True
        KEY_SIZE = 32
        DEFAULT_PAGESIZE = 4096
        DEFAULT_ITER = 64000
        with open(wx_db_path, "rb") as file:
            blist = file.read(5000)
        salt = blist[:16]
        byteKey = hashlib.pbkdf2_hmac("sha1", key, salt, DEFAULT_ITER, KEY_SIZE)
        first = blist[16:DEFAULT_PAGESIZE]

        mac_salt = bytes([(salt[i] ^ 58) for i in range(16)])
        mac_key = hashlib.pbkdf2_hmac("sha1", byteKey, mac_salt, 2, KEY_SIZE)
        hash_mac = hmac.new(mac_key, first[:-32], hashlib.sha1)
        hash_mac.update(b'\x01\x00\x00\x00')

        if hash_mac.digest() != first[-32:-12]:
            return False
        return True

    phone_type1 = "iphone\x00"
    phone_type2 = "android\x00"
    phone_type3 = "ipad\x00"

    pm = pymem.Pymem("WeChat.exe")
    module_name = "WeChatWin.dll"

    MicroMsg_path = os.path.join(db_path, "MSG", "MicroMsg.db")

    type1_addrs = pm.pattern_scan_module(phone_type1.encode(), module_name, return_multiple=True)
    type2_addrs = pm.pattern_scan_module(phone_type2.encode(), module_name, return_multiple=True)
    type3_addrs = pm.pattern_scan_module(phone_type3.encode(), module_name, return_multiple=True)
    type_addrs = type1_addrs if len(type1_addrs) >= 2 else type2_addrs if len(type2_addrs) >= 2 else type3_addrs if len(
        type3_addrs) >= 2 else ""
    # print(type_addrs)
    if type_addrs == "":
        return ""
    for i in type_addrs[::-1]:
        for j in range(i, i - 2000, -addr_len):
            key_bytes = read_key_bytes(pm.process_handle, j, addr_len)
            if key_bytes == "":
                continue
            if db_path != "" and verify_key(key_bytes, MicroMsg_path):
                return key_bytes.hex()
    return ""


def dump_wechat_info_v3(version_list, pid) -> WeChatInfo:
    """
    从微信 v3.x 进程中提取完整的账户信息

    参数:
        version_list (dict): 包含不同微信版本偏移地址的字典
        pid (int): 微信进程ID

    返回:
        WeChatInfo: 包含微信账户信息的对象
    """
    wechat_info = WeChatInfo()
    wechat_info.pid = pid
    wechat_info.version = get_version(pid)
    process = psutil.Process(pid)
    pythoncom.CoInitialize()

    wechat_base_address = 0
    for module in process.memory_maps(grouped=False):
        if module.path and 'WeChatWin.dll' in module.path:
            wechat_base_address = int(module.addr, 16)
            break

    if wechat_base_address == 0:
        wechat_info.errmsg = '错误！请登录微信。'
        return wechat_info

    Handle = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, process.pid)

    bias_list = version_list.get(wechat_info.version)
    if not isinstance(bias_list, list) or len(bias_list) <= 4:
        wechat_info.errcode = 405
        wechat_info.errmsg = '错误！微信版本不匹配，请手动填写信息。'
        return wechat_info
    else:
        name_base_address = wechat_base_address + bias_list[0]
        account__base_address = wechat_base_address + bias_list[1]
        mobile_base_address = wechat_base_address + bias_list[2]

        wechat_info.account_name = get_info_without_key(Handle, account__base_address, 32) if bias_list[1] != 0 else "None"
        wechat_info.phone = get_info_without_key(Handle, mobile_base_address, 64) if bias_list[2] != 0 else "None"
        wechat_info.nick_name = get_info_without_key(Handle, name_base_address, 64) if bias_list[0] != 0 else "None"

    addrLen = get_exe_bit(process.exe()) // 8

    wechat_info.wxid = get_info_wxid(Handle)
    wechat_info.wx_dir = get_wx_dir(wechat_info.wxid)
    wechat_info.key = get_key(wechat_info.wx_dir, addrLen)
    if not wechat_info.key:
        wechat_info.errcode = 404
        wechat_info.errmsg = '请重启微信后重试。'
    else:
        wechat_info.errcode = 200
    return wechat_info

