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


def read_ptr(h_process, address, addr_len=8):
    array = ctypes.create_string_buffer(addr_len)
    if ReadProcessMemory(h_process, void_p(address), array, addr_len, 0) == 0:
        return None
    return int.from_bytes(bytes(array), byteorder='little')


def get_info_smart(h_process, address, n_size=64, prefer_wide=True):
    """
    智能读取内存字符串，兼容直接存储和指针存储模式，支持UTF-16LE和UTF-8
    微信3.9.12+版本常使用指针+UTF-16LE存储基本信息
    """

    def try_decode(data, wide):
        if wide:
            try:
                text = data.decode('utf-16le', errors='ignore').split('\x00')[0]
                if text.strip():
                    return text.strip()
            except:
                pass
        try:
            text = data.split(b'\x00')[0].decode('utf-8', errors='ignore')
            if text.strip():
                return text.strip()
        except:
            pass
        return None

    # 尝试将address当作指针读取
    ptr = read_ptr(h_process, address)
    if ptr:
        buf = ctypes.create_string_buffer(n_size * 2)
        if ReadProcessMemory(h_process, void_p(ptr), buf, n_size * 2, 0) != 0:
            result = try_decode(bytes(buf), prefer_wide)
            if result:
                return result

    # 直接读取address处数据
    buf = ctypes.create_string_buffer(n_size * 2)
    if ReadProcessMemory(h_process, void_p(address), buf, n_size * 2, 0) == 0:
        return "None"
    result = try_decode(bytes(buf), prefer_wide)
    return result if result else "None"


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


def read_key_bytes(h_process, address, address_len=8):
    """
    从指定内存地址读取密钥字节（先读指针再读密钥）
    """
    array = ctypes.create_string_buffer(address_len)
    if ReadProcessMemory(h_process, void_p(address), array, address_len, 0) == 0:
        return b""
    address = int.from_bytes(bytes(array), byteorder='little')
    key = ctypes.create_string_buffer(32)
    if ReadProcessMemory(h_process, void_p(address), key, 32, 0) == 0:
        return b""
    return bytes(key)


def verify_key(key, wx_db_path):
    """
    验证密钥是否正确
    """
    if not wx_db_path:
        return True
    KEY_SIZE = 32
    DEFAULT_PAGESIZE = 4096
    DEFAULT_ITER = 64000
    try:
        with open(wx_db_path, "rb") as file:
            blist = file.read(5000)
    except FileNotFoundError:
        return True
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


def get_key(db_path, addr_len):
    """
    从微信进程中获取数据库解密密钥
    """
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
    if type_addrs == "":
        return ""
    for i in type_addrs[::-1]:
        for j in range(i, i - 2000, -addr_len):
            key_bytes = read_key_bytes(pm.process_handle, j, addr_len)
            if not key_bytes:
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

    name_base_address = wechat_base_address + bias_list[0]
    account__base_address = wechat_base_address + bias_list[1]
    mobile_base_address = wechat_base_address + bias_list[2]
    key_offset = bias_list[4] if len(bias_list) > 4 else 0

    # 3.9.12+ 版本的昵称、账号、手机号常使用UTF-16LE编码，且可能通过指针存储
    version_tuple = tuple(map(int, wechat_info.version.split('.')))
    is_new_version = version_tuple >= (3, 9, 12)

    wechat_info.nick_name = get_info_smart(Handle, name_base_address, 64, prefer_wide=is_new_version) if bias_list[0] != 0 else "None"
    wechat_info.account_name = get_info_smart(Handle, account__base_address, 32, prefer_wide=is_new_version) if bias_list[1] != 0 else "None"
    wechat_info.phone = get_info_smart(Handle, mobile_base_address, 64, prefer_wide=is_new_version) if bias_list[2] != 0 else "None"

    addrLen = get_exe_bit(process.exe()) // 8

    wechat_info.wxid = get_info_wxid(Handle)
    wechat_info.wx_dir = get_wx_dir(wechat_info.wxid)

    # 优先尝试使用 version_list 中的 key 偏移量读取密钥
    key = ""
    MicroMsg_path = os.path.join(wechat_info.wx_dir, "MSG", "MicroMsg.db")
    if key_offset != 0:
        key_base_address = wechat_base_address + key_offset
        # 尝试作为指针读取
        key_bytes = read_key_bytes(Handle, key_base_address, addrLen)
        if key_bytes and verify_key(key_bytes, MicroMsg_path):
            key = key_bytes.hex()
        else:
            # 尝试直接读取 32 字节密钥
            direct_key = ctypes.create_string_buffer(32)
            if ReadProcessMemory(Handle, void_p(key_base_address), direct_key, 32, 0) != 0:
                direct_key_bytes = bytes(direct_key)
                if verify_key(direct_key_bytes, MicroMsg_path):
                    key = direct_key_bytes.hex()

    if not key:
        key = get_key(wechat_info.wx_dir, addrLen)

    wechat_info.key = key
    if not wechat_info.key:
        wechat_info.errcode = 404
        wechat_info.errmsg = '请重启微信后重试。'
    else:
        wechat_info.errcode = 200
    return wechat_info

