#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/1/10 2:36
@Author      : SiYuan
@Email       : 863909694@qq.com
@File        : wxManager-wx_info_v4.py
@Description : 部分思路参考：https://github.com/0xlane/wechat-dump-rs
"""

import ctypes
import multiprocessing
import os.path

import hmac
import os
import struct
import time
from ctypes import wintypes
from multiprocessing import freeze_support

import pymem
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512
import yara

from wxManager.decrypt.common import WeChatInfo
from wxManager.decrypt.common import get_version

# 定义必要的常量
PROCESS_ALL_ACCESS = 0x1F0FFF
PAGE_READWRITE = 0x04
MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000

# Constants
IV_SIZE = 16
HMAC_SHA256_SIZE = 64
HMAC_SHA512_SIZE = 64
KEY_SIZE = 32
AES_BLOCK_SIZE = 16
ROUND_COUNT = 256000
PAGE_SIZE = 4096
SALT_SIZE = 16

finish_flag = False


# 定义 MEMORY_BASIC_INFORMATION 结构
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


# Windows API Constants
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

# Load Windows DLLs
kernel32 = ctypes.windll.kernel32


# 打开目标进程
def open_process(pid):
    return ctypes.windll.kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)


# 读取目标进程内存
def read_process_memory(process_handle, address, size):
    buffer = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)
    success = ctypes.windll.kernel32.ReadProcessMemory(
        process_handle,
        ctypes.c_void_p(address),
        buffer,
        size,
        ctypes.byref(bytes_read)
    )
    if not success:
        return None
    return buffer.raw


# 获取所有内存区域
def get_memory_regions(process_handle):
    regions = []
    mbi = MEMORY_BASIC_INFORMATION()
    address = 0
    while ctypes.windll.kernel32.VirtualQueryEx(
            process_handle,
            ctypes.c_void_p(address),
            ctypes.byref(mbi),
            ctypes.sizeof(mbi)
    ):
        if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE:
            regions.append((mbi.BaseAddress, mbi.RegionSize))
        address += mbi.RegionSize
    return regions


rules_v4 = r'''
rule GetDataDir {
    strings:
        $a = /[a-zA-Z]:\\(.{1,100}?\\){0,1}?xwechat_files\\[0-9a-zA-Z_-]{6,24}?\\db_storage\\/
    condition:
        $a
}

rule GetPhoneNumberOffset {
    strings:
        $a = /[\x01-\x20]\x00{7}(\x0f|\x1f)\x00{7}[0-9]{11}\x00{5}\x0b\x00{7}\x0f\x00{7}/
    condition:
        $a
}
rule GetKeyAddrStub
{
    strings:
        $a = /.{6}\x00{2}\x00{8}\x20\x00{7}\x2f\x00{7}/
    condition:
        all of them
}
'''


def read_string(data: bytes, offset, size):
    try:
        return data[offset:offset + size].decode('utf-8')
    except:
        # print(data[offset:offset + size])
        # print(traceback.format_exc())
        return ''


def read_num(data: bytes, offset, size):
    # 构建格式字符串，根据 size 来选择相应的格式
    if size == 1:
        fmt = '<B'  # 1 字节，unsigned char
    elif size == 2:
        fmt = '<H'  # 2 字节，unsigned short
    elif size == 4:
        fmt = '<I'  # 4 字节，unsigned int
    elif size == 8:
        fmt = '<Q'  # 8 字节，unsigned long long
    else:
        raise ValueError("Unsupported size")

    # 使用 struct.unpack 从指定 offset 开始读取 size 字节的数据并转换为数字
    result = struct.unpack_from(fmt, data, offset)[0]  # 通过 unpack_from 来读取指定偏移的数据
    return result


def read_bytes(data: bytes, offset, size):
    return data[offset:offset + size]


# def read_bytes_from_pid(pid, offset, size):
#     with open(f'/proc/{pid}/mem', 'rb') as mem_file:
#         mem_file.seek(offset)
#         return mem_file.read(size)


# 导入 Windows API 函数
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

OpenProcess = kernel32.OpenProcess
OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
OpenProcess.restype = wintypes.HANDLE

ReadProcessMemory = kernel32.ReadProcessMemory
ReadProcessMemory.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, wintypes.LPVOID, ctypes.c_size_t,
                              ctypes.POINTER(ctypes.c_size_t)]
ReadProcessMemory.restype = wintypes.BOOL

CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [wintypes.HANDLE]
CloseHandle.restype = wintypes.BOOL


def read_bytes_from_pid(pid: int, addr: int, size: int):
    # 打开进程
    hprocess = OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not hprocess:
        raise Exception(f"Failed to open process with PID {pid}")
    buffer = b''
    try:
        # 创建缓冲区
        buffer = ctypes.create_string_buffer(size)

        # 读取内存
        bytes_read = ctypes.c_size_t(0)
        success = ReadProcessMemory(hprocess, addr, buffer, size, ctypes.byref(bytes_read))
        if not success:
            CloseHandle(hprocess)
            return b''
            raise Exception(f"Failed to read memory at address {hex(addr)}")

        # 关闭句柄
        CloseHandle(hprocess)
    except:
        pass
    # 返回读取的字节数组
    return bytes(buffer)


def read_string_from_pid(pid: int, addr: int, size: int):
    bytes0 = read_bytes_from_pid(pid, addr, size)
    try:
        return bytes0.decode('utf-8')
    except:
        return ''


def is_ok(passphrase, buf):
    global finish_flag
    if finish_flag:
        return False

    # 确保缓冲区至少有4096字节（一页）
    if len(buf) < PAGE_SIZE:
        return False

    # 获取文件开头的 salt
    salt = buf[:SALT_SIZE]

    # 检查 salt 是否合理（不全为0，不全相同）
    if salt == b'\x00' * SALT_SIZE or len(set(salt)) == 1:
        return False

    # salt 异或 0x3a 得到 mac_salt，用于计算 HMAC
    mac_salt = bytes(x ^ 0x3a for x in salt)
    # 使用 PBKDF2 生成新的密钥
    new_key = PBKDF2(passphrase, salt, dkLen=KEY_SIZE, count=ROUND_COUNT, hmac_hash_module=SHA512)
    # 使用新的密钥和 mac_salt 计算 mac_key
    mac_key = PBKDF2(new_key, mac_salt, dkLen=KEY_SIZE, count=2, hmac_hash_module=SHA512)
    # 计算 hash 校验码的保留空间
    reserve = IV_SIZE + HMAC_SHA512_SIZE
    reserve = ((reserve + AES_BLOCK_SIZE - 1) // AES_BLOCK_SIZE) * AES_BLOCK_SIZE
    # 校验 HMAC
    start = SALT_SIZE
    end = PAGE_SIZE

    # 确保缓冲区足够大
    if len(buf) < end:
        return False

    mac_data_end = end - reserve + IV_SIZE
    if mac_data_end <= start or mac_data_end > len(buf):
        return False

    mac = hmac.new(mac_key, buf[start:mac_data_end], SHA512)
    mac.update(struct.pack('<I', 1))  # page number as 1
    hash_mac = mac.digest()
    # 校验 HMAC 是否一致
    hash_mac_start_offset = end - reserve + IV_SIZE
    hash_mac_end_offset = hash_mac_start_offset + len(hash_mac)

    if hash_mac_end_offset > len(buf):
        return False

    stored_mac = buf[hash_mac_start_offset:hash_mac_end_offset]

    if hash_mac == stored_mac:
        print(f"[v] found key at 0x{start:x}")
        finish_flag = True
        return True
    return False


def check_chunk(chunk, buf):
    global finish_flag
    if finish_flag:
        return False
    if is_ok(chunk, buf):
        return chunk
    return False


def verify_key(key: bytes, buffer: bytes, flag, result):
    if len(key) != 32:
        return False
    if flag.value:  # 如果其他进程已找到结果，提前退出
        return False
    if is_ok(key, buffer):  # 替换为实际的目标检测条件
        print("Key found!", key)
        with flag.get_lock():  # 保证线程安全
            flag.value = True
            return key
    else:
        return False


def get_key_(keys, buf):
    print(f"[V4 KEY] 开始验证 {len(keys)} 个密钥候选")
    if not keys:
        return None

    # 限制验证的密钥数量，避免过多
    keys_to_check = keys[:100] if len(keys) > 100 else keys

    pool = multiprocessing.Pool(processes=max(1, multiprocessing.cpu_count() // 2))
    results = pool.starmap(check_chunk, ((key, buf) for key in keys_to_check))
    pool.close()
    pool.join()

    for r in results:
        if r:
            print(f"[V4 KEY] SUCCESS! 找到有效密钥: {bytes.hex(r)[:16]}...")
            return bytes.hex(r)

    print(f"[V4 KEY] 验证了 {len(keys_to_check)} 个密钥候选，但未找到有效密钥")
    return None


def get_key_inner(pid, process_infos):
    """
    扫描可能为key的内存
    :param pid:
    :param process_infos:
    :return:
    """
    process_handle = open_process(pid)
    if not process_handle:
        print(f"[V4 KEY] ERROR: 无法打开进程 {pid}")
        return []

    # 更新 yara 规则以支持更多版本的微信
    rules_v4_key = r'''
        rule GetKeyAddrStub
        {
            strings:
                $a = /.{6}\x00{2}\x00{8}\x20\x00{7}\x2f\x00{7}/
                $b = /\x00{8}\x20\x00{7}\x2f\x00{7}.{32}/
            condition:
                any of them
        }
        '''
    try:
        rules = yara.compile(source=rules_v4_key)
    except Exception as e:
        print(f"[V4 KEY] ERROR: YARA规则编译失败: {e}")
        ctypes.windll.kernel32.CloseHandle(process_handle)
        return []

    pre_addresses = []
    scan_count = 0
    match_count = 0

    for base_address, region_size in process_infos:
        memory = read_process_memory(process_handle, base_address, region_size)
        if not memory:
            continue

        scan_count += 1
        target_data = memory

        # 尝试匹配密钥地址stub
        matches = rules.match(data=target_data)
        if matches:
            match_count += 1
            for match in matches:
                rule_name = match.rule
                if rule_name == 'GetKeyAddrStub':
                    for string in match.strings:
                        instance = string.instances[0]
                        offset, content = instance.offset, instance.matched_data
                        addr = read_num(target_data, offset, 8)
                        if addr != 0:
                            pre_addresses.append(addr)
                            print(f"[V4 KEY] 找到候选地址: 0x{addr:x} (base=0x{base_address:x}, offset={offset})")

    ctypes.windll.kernel32.CloseHandle(process_handle)
    print(f"[V4 KEY] 扫描完成: 扫描了 {scan_count} 个内存区域，找到 {len(pre_addresses)} 个候选地址")

    keys = []
    key_set = set()
    for pre_address in pre_addresses:
        # 检查地址是否在有效的内存区域内
        in_range = any([base_address <= pre_address <= base_address + region_size - KEY_SIZE
                       for base_address, region_size in process_infos])
        if in_range or True:  # 暂时允许所有地址
            key = read_bytes_from_pid(pid, pre_address, 32)
            if key and len(key) == 32 and key not in key_set:
                # 检查是否是合理的密钥（不全为0，不全相同）
                if key != b'\x00' * 32 and len(set(key)) > 1:
                    keys.append(key)
                    key_set.add(key)
                    print(f"[V4 KEY] 读取到候选密钥 @ 0x{pre_address:x}: {key.hex()[:16]}...")

    print(f"[V4 KEY] 共收集 {len(keys)} 个唯一密钥候选")
    return keys


def get_key(pid, process_handle, buf):
    print(f"[V4 KEY] 开始获取密钥 for PID={pid}")
    process_infos = get_memory_regions(process_handle)
    print(f"[V4 KEY] 进程内存区域数量: {len(process_infos)}")

    def split_list(lst, n):
        k, m = divmod(len(lst), n)
        return (lst[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n))

    # 如果内存区域太多，使用多进程
    if len(process_infos) > 100:
        pool = multiprocessing.Pool(processes=max(1, multiprocessing.cpu_count() // 2))
        chunk_size = min(len(process_infos), 40)
        results = pool.starmap(get_key_inner, ((pid, process_info_) for process_info_ in
                                               split_list(process_infos, chunk_size)))
        pool.close()
        pool.join()
    else:
        # 内存区域较少时直接扫描
        results = [get_key_inner(pid, process_infos)]

    keys = []
    for r in results:
        if r:
            keys += r

    print(f"[V4 KEY] 所有进程扫描完成，共 {len(keys)} 个候选密钥")

    if not keys:
        print(f"[V4 KEY] WARNING: 未找到任何密钥候选")
        return None

    key = get_key_(keys, buf)
    print(f"[V4 KEY] 密钥验证结果: {'成功' if key else '失败'}")
    return key


def get_wx_dir(process_handle):
    # 支持多种路径格式（不区分大小写）
    # 微信4.x可能使用: WeChat Files, Wechat Files, wechat_files, xwechat_files 等
    rules_v4_dir = r'''
    rule GetDataDir {
        strings:
            $a = /[a-zA-Z]:\\(.{1,100}?\\){0,1}?[Ww][Ee][Cc][Hh][Aa][Tt][_\s][Ff][Ii][Ll][Ee][Ss]\\[0-9a-zA-Z_-]{6,24}?\\[Dd][Bb]_[Ss][Tt][Oo][Rr][Aa][Gg][Ee]\\/
            $b = /[a-zA-Z]:\\(.{1,100}?\\){0,1}?xwechat_files\\[0-9a-zA-Z_-]{6,24}?\\db_storage\\/
        condition:
            any of them
    }
    '''
    rules = yara.compile(source=rules_v4_dir)
    process_infos = get_memory_regions(process_handle)
    wx_dir_cnt = {}
    print(f"[V4 DEBUG] 开始扫描内存查找微信数据目录...")
    scan_count = 0
    for base_address, region_size in process_infos:
        memory = read_process_memory(process_handle, base_address, region_size)
        # 定义目标数据（如内存或文件内容）
        target_data = memory  # 二进制数据
        if not memory:
            continue
        # 检查是否包含 db_storage 或 Db_Storage（不区分大小写）
        target_lower = target_data.lower()
        if b'db_storage' not in target_lower and b'db storage' not in target_lower:
            continue
        scan_count += 1
        matches = rules.match(data=target_data)
        if matches:
            # 输出匹配结果
            for match in matches:
                rule_name = match.rule
                print(f"[V4 DEBUG] 规则匹配: {rule_name}")
                for string in match.strings:
                    content = string.instances[0].matched_data
                    print(f"[V4 DEBUG] 找到路径: {content}")
                    wx_dir_cnt[content] = wx_dir_cnt.get(content, 0) + 1
    print(f"[V4 DEBUG] 扫描了 {scan_count} 个内存区域，找到 {len(wx_dir_cnt)} 个候选路径")
    if wx_dir_cnt:
        best_match = max(wx_dir_cnt, key=wx_dir_cnt.get)
        print(f"[V4 DEBUG] 选择最佳路径: {best_match}")
        return best_match.decode('utf-8')
    return ''


def get_nickname(pid):
    process_handle = open_process(pid)
    if not process_handle:
        print(f"[V4 DEBUG] 无法打开进程 {pid}")
        return {}
    process_infos = get_memory_regions(process_handle)
    print(f"[V4 DEBUG] 内存区域数量: {len(process_infos)}")
    # 加载规则
    r'''$a = /(.{16}[\x00-\x20]\x00{7}(\x0f|\x1f)\x00{7}){2}.{16}[\x01-\x20]\x00{7}(\x0f|\x1f)\x00{7}[0-9]{11}\x00{5}\x0b\x00{7}\x0f\x00{7}.{25}\x00{7}(\x3f|\x2f|\x1f|\x0f)\x00{7}/s'''
    rules_v4_phone = r'''
    rule GetPhoneNumberOffset {
        strings:
            $a = /[\x01-\x20]\x00{7}(\x0f|\x1f)\x00{7}[0-9]{11}\x00{5}\x0b\x00{7}\x0f\x00{7}/
        condition:
            $a
    }
    '''
    nick_name = ''
    phone = ''
    account_name = ''
    rules = yara.compile(source=rules_v4_phone)
    match_count = 0
    for base_address, region_size in process_infos:
        memory = read_process_memory(process_handle, base_address, region_size)
        # 定义目标数据（如内存或文件内容）
        target_data = memory  # 二进制数据
        if not memory:
            continue
        # if not (b'db_storage' in target_data or b'USER_KEYINFO' in target_data):
        #     continue
        # if not (b'-----BEGIN PUBLIC KEY-----' in target_data):
        #     continue
        matches = rules.match(data=target_data)
        if matches:
            match_count += 1
            # 输出匹配结果
            for match in matches:
                rule_name = match.rule
                if rule_name == 'GetPhoneNumberOffset':
                    for string in match.strings:
                        instance = string.instances[0]
                        offset, content = instance.offset, instance.matched_data
                        phone_addr = offset + 0x10
                        phone = read_string(target_data, phone_addr, 11)

                        # 提取前 8 个字节
                        data_slice = target_data[offset:offset + 8]
                        # 使用 struct.unpack() 将字节转换为 u64，'<Q' 表示小端字节序的 8 字节无符号整数
                        try:
                            nick_name_length = struct.unpack('<Q', data_slice)[0]
                        except:
                            nick_name_length = 0
                        # print('nick_name_length', nick_name_length)
                        if 0 < nick_name_length < 100:  # 合理的昵称长度
                            nick_name = read_string(target_data, phone_addr - 0x20, nick_name_length)
                        a = target_data[phone_addr - 0x60:phone_addr + 0x50]
                        try:
                            account_name_length = read_num(target_data, phone_addr - 0x30, 8)
                        except:
                            account_name_length = 0
                        # print('account_name_length', account_name_length)
                        if 0 < account_name_length < 100:  # 合理的账号长度
                            account_name = read_string(target_data, phone_addr - 0x40, account_name_length)
                        # with open('a.bin', 'wb') as f:
                        #     f.write(target_data)
                        if not account_name and 0 < account_name_length < 100:
                            try:
                                addr = read_num(target_data, phone_addr - 0x40, 8)
                                # print(hex(addr))
                                account_name = read_string_from_pid(pid, addr, account_name_length)
                            except:
                                pass
    print(f"[V4 DEBUG] 匹配次数: {match_count}, nick_name={nick_name}, phone={phone}, account_name={account_name}")
    ctypes.windll.kernel32.CloseHandle(process_handle)
    return {
        'nick_name': nick_name,
        'phone': phone,
        'account_name': account_name
    }


def worker(pid, queue):
    nickname_dic = get_nickname(pid)
    queue.put(nickname_dic)


def dump_wechat_info_v4(pid) -> WeChatInfo | None:
    wechat_info = WeChatInfo()
    wechat_info.pid = pid
    wechat_info.version = get_version(pid)
    print(f"[V4] 微信版本: {wechat_info.version}")

    process_handle = open_process(pid)
    if not process_handle:
        print(f"[V4 ERROR] 无法打开进程 {pid}")
        wechat_info.errmsg = f"无法打开进程 {pid}"
        return wechat_info

    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=worker, args=(pid, queue))
    process.start()

    wechat_info.wx_dir = get_wx_dir(process_handle)
    print(f"[V4] 微信数据目录: {wechat_info.wx_dir}")

    if not wechat_info.wx_dir:
        print(f"[V4 ERROR] 无法获取微信数据目录")
        wechat_info.errmsg = "无法获取微信数据目录，请确保微信已登录"
        ctypes.windll.kernel32.CloseHandle(process_handle)
        process.terminate()
        return wechat_info

    # 尝试查找数据库文件用于密钥验证
    # 搜索所有可能的加密数据库文件
    possible_db_files = []

    # 首先尝试已知的固定路径
    fixed_paths = [
        os.path.join(wechat_info.wx_dir, 'favorite', 'favorite_fts.db'),
        os.path.join(wechat_info.wx_dir, 'head_image', 'head_image.db'),
        os.path.join(wechat_info.wx_dir, 'msg', 'message.db'),
        os.path.join(wechat_info.wx_dir, 'microMsg.db'),
        os.path.join(wechat_info.wx_dir, 'session.db'),
    ]

    for path in fixed_paths:
        if os.path.exists(path):
            possible_db_files.append(path)

    # 如果没有找到，遍历目录查找 .db 文件
    if not possible_db_files:
        print(f"[V4] 遍历目录查找数据库文件...")
        for root, dirs, files in os.walk(wechat_info.wx_dir):
            for file in files:
                if file.endswith('.db'):
                    possible_db_files.append(os.path.join(root, file))
            # 限制遍历深度，避免太慢
            if root.count(os.sep) > wechat_info.wx_dir.count(os.sep) + 2:
                break

    # 选择一个合适的数据库文件（优先选择较小的系统数据库）
    db_file_path = None
    buf = None

    if possible_db_files:
        # 按文件大小排序，优先选择较小的文件（系统数据库通常较小）
        possible_db_files.sort(key=lambda x: os.path.getsize(x) if os.path.exists(x) else float('inf'))
        print(f"[V4] 找到 {len(possible_db_files)} 个数据库文件")

        # 尝试每个数据库文件，直到找到一个可以读取的
        for path in possible_db_files[:5]:  # 最多尝试前5个
            try:
                with open(path, 'rb') as f:
                    buf = f.read(4096)  # 只读取第一页
                if len(buf) >= 4096:
                    db_file_path = path
                    print(f"[V4] 使用数据库文件: {db_file_path} ({os.path.getsize(db_file_path)} bytes)")
                    break
            except Exception as e:
                print(f"[V4] 无法读取 {path}: {e}")
                continue

    if not db_file_path or not buf:
        print(f"[V4 ERROR] 未找到可用的数据库文件用于密钥验证")
        wechat_info.errmsg = "未找到可用的数据库文件"
        wechat_info.errcode = 404
        ctypes.windll.kernel32.CloseHandle(process_handle)
        process.terminate()
        return wechat_info

    print(f"[V4] 开始扫描密钥...")
    wechat_info.key = get_key(pid, process_handle, buf)
    print(f"[V4] 密钥扫描结果: {'成功' if wechat_info.key else '失败'}")

    ctypes.windll.kernel32.CloseHandle(process_handle)

    # 提取 wxid 和简化 wx_dir
    try:
        wechat_info.wxid = '_'.join(wechat_info.wx_dir.split('\\')[-3].split('_')[0:-1])
        wechat_info.wx_dir = '\\'.join(wechat_info.wx_dir.split('\\')[:-2])
    except Exception as e:
        print(f"[V4 ERROR] 解析 wxid 失败: {e}")

    process.join(timeout=5)  # 等待子进程完成，最多5秒
    if process.is_alive():
        print(f"[V4 WARNING] 获取昵称进程超时")
        process.terminate()

    if not queue.empty():
        nickname_info = queue.get()
        wechat_info.nick_name = nickname_info.get('nick_name', '')
        wechat_info.phone = nickname_info.get('phone', '')
        wechat_info.account_name = nickname_info.get('account_name', '')
        print(f"[V4] 用户信息: 昵称={wechat_info.nick_name}, 手机={wechat_info.phone}")

    if not wechat_info.key:
        wechat_info.errcode = 404
        wechat_info.errmsg = "无法获取密钥，请重新登录微信"
    else:
        wechat_info.errcode = 200
        wechat_info.errmsg = "成功"

    print(f"[V4] 最终结果: errcode={wechat_info.errcode}, errmsg={wechat_info.errmsg}")
    return wechat_info


if __name__ == '__main__':
    freeze_support()
    st = time.time()
    pm = pymem.Pymem("Weixin.exe")
    pid = pm.process_id
    w = dump_wechat_info_v4(pid)
    print(w)
    et = time.time()
    print(et - st)
