#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复版的 get_decode_code_v4 函数
针对微信 4.1.8.29 版本的问题进行改进
"""

import os
import struct

# 微信 4.x 图片加密使用的 AES 密钥映射
# 这些密钥是固定的，从微信二进制中提取
AES_KEY_MAP = {
    b'\x07\x08V1\x08\x07': b'cfcd208495d565ef',  # 4.0第一代图片密钥 (前8字节)
    b'\x07\x08V2\x08\x07': b'43e7d25eb1b9bb64',  # 4.0第二代图片密钥
}

# 可能的 V3 异或密钥（基于已知信息反推）
# 这些是基于常见微信版本的可能密钥
COMMON_XOR_KEYS = [
    0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
    0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17,
    0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F,
    0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27,
    0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F,
    0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37,
    0x38, 0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F,
    0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47,
    0x48, 0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F,
    0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57,
    0x58, 0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F,
    0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66, 0x67,
    0x68, 0x69, 0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x6F,
    0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77,
    0x78, 0x79, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F,
    0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87,
    0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x8D, 0x8E, 0x8F,
    0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97,
    0x98, 0x99, 0x9A, 0x9B, 0x9C, 0x9D, 0x9E, 0x9F,
    0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
    0xA8, 0xA9, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF,
    0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7,
    0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF,
    0xC0, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
    0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF,
    0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7,
    0xD8, 0xD9, 0xDA, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF,
    0xE0, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7,
    0xE8, 0xE9, 0xEA, 0xEB, 0xEC, 0xED, 0xEE, 0xEF,
    0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7,
    0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF,
]

# 图片文件头特征
PIC_HEADERS = {
    'jpg': (0xff, 0xd8),
    'png': (0x89, 0x50),
    'gif': (0x47, 0x49),
}


def is_v4_image(header: bytes) -> bool:
    """检查是否是微信 4.x 格式的加密图片"""
    return header[:6] in AES_KEY_MAP


def get_image_type_from_header(data: bytes) -> str:
    """根据解密后的头部判断图片类型"""
    if data.startswith(b'\xff\xd8'):
        return 'jpg'
    elif data.startswith(b'\x89PNG'):
        return 'png'
    elif data.startswith(b'GIF'):
        return 'gif'
    return 'unknown'


def try_xor_decrypt(data: bytes, xor_key: int) -> bytes:
    """尝试使用异或密钥解密数据"""
    return bytes([b ^ xor_key for b in data])


def find_xor_key_by_header(data: bytes) -> int:
    """通过尝试解密头部来查找异或密钥"""
    if len(data) < 2:
        return -1
    
    for xor_key in COMMON_XOR_KEYS:
        decrypted = try_xor_decrypt(data[:16], xor_key)
        
        # 检查是否是已知的图片格式
        if decrypted.startswith(b'\xff\xd8'):  # JPG
            return xor_key
        elif decrypted.startswith(b'\x89PNG'):  # PNG
            return xor_key
        elif decrypted.startswith(b'GIF'):  # GIF
            return xor_key
    
    return -1


def find_xor_key_by_trailer(data: bytes) -> int:
    """通过文件尾部推导异或密钥（假设是 JPG）"""
    if len(data) < 2:
        return -1
    
    # JPG 文件尾: FF D9
    # PNG 文件尾: AE 42 60 82
    jpg_tail = b'\xff\xd9'
    
    # 检查最后2字节
    file_tail = data[-2:]
    xor_key = file_tail[0] ^ jpg_tail[0]
    
    # 验证
    decrypted_tail = try_xor_decrypt(file_tail, xor_key)
    if decrypted_tail == jpg_tail:
        # 额外验证：解密更多尾部数据
        if len(data) >= 10:
            more_tail = data[-10:-2]
            decrypted_more = try_xor_decrypt(more_tail, xor_key)
            # JPG 的尾部通常包含扫描结束标记
            if b'\xff' in decrypted_more:
                return xor_key
    
    return -1


def get_decode_code_v4_fixed(wx_dir: str, debug: bool = True) -> int:
    """
    修复版的 get_decode_code_v4 函数
    针对微信 4.1.8.29 版本进行改进
    
    :param wx_dir: 微信数据目录
    :param debug: 是否输出调试信息
    :return: 异或密钥，如果找不到返回 0
    """
    if not wx_dir:
        raise ValueError(f'微信路径为空，请检查: {wx_dir}')
    if not os.path.isdir(wx_dir):
        raise ValueError(f'微信路径不是一个有效目录: {wx_dir}')
    
    if debug:
        print(f"[*] 开始查找异或密钥...")
        print(f"[*] 微信目录: {wx_dir}")
    
    # 要搜索的目录列表（按优先级）
    search_dirs = []
    
    # 1. 首选 cache 目录
    cache_dir = os.path.join(wx_dir, 'cache')
    if os.path.exists(cache_dir):
        search_dirs.append(('cache', cache_dir))
    
    # 2. temp 目录
    temp_dir = os.path.join(wx_dir, 'temp')
    if os.path.exists(temp_dir):
        search_dirs.append(('temp', temp_dir))
    
    # 3. msg 目录
    msg_dir = os.path.join(wx_dir, 'msg')
    if os.path.exists(msg_dir):
        search_dirs.append(('msg', msg_dir))
    
    # 4. 其他可能的目录
    for subdir in ['image', 'video', 'attachment']:
        full_path = os.path.join(wx_dir, subdir)
        if os.path.exists(full_path):
            search_dirs.append((subdir, full_path))
    
    if debug:
        print(f"[*] 将搜索以下目录: {[name for name, _ in search_dirs]}")
    
    def search_in_dir(dir_name: str, dir_path: str) -> int:
        """在指定目录中搜索异或密钥"""
        if debug:
            print(f"\n[*] 搜索目录: {dir_name} ({dir_path})")
        
        dat_files = []
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                if file.endswith('.dat'):
                    dat_files.append(os.path.join(root, file))
            # 限制文件数量
            if len(dat_files) > 100:
                break
        
        if debug:
            print(f"  找到 {len(dat_files)} 个 .dat 文件")
        
        for dat_file in dat_files:
            try:
                with open(dat_file, 'rb') as f:
                    data = f.read()
                
                if len(data) < 16:
                    continue
                
                header = data[:16]
                
                # 检查是否是 V4 AES 加密格式
                if is_v4_image(header):
                    if debug:
                        print(f"  [V4] 发现 AES 加密图片: {os.path.basename(dat_file)}")
                        print(f"       微信 4.x 图片使用 AES 加密，不需要异或密钥")
                        print(f"       AES 密钥: {AES_KEY_MAP.get(header[:6], b'unknown').hex()}")
                    # V4 图片不需要异或密钥，返回特殊值
                    return 0x100  # 特殊标记表示 V4 AES 格式
                
                # 尝试通过头部推导异或密钥
                xor_key = find_xor_key_by_header(data)
                if xor_key != -1:
                    if debug:
                        print(f"  [FOUND] 通过头部找到密钥 0x{xor_key:02x}: {os.path.basename(dat_file)}")
                    return xor_key
                
                # 尝试通过尾部推导（如果是 _t.dat 文件）
                if dat_file.endswith('_t.dat'):
                    xor_key = find_xor_key_by_trailer(data)
                    if xor_key != -1:
                        if debug:
                            print(f"  [FOUND] 通过尾部找到密钥 0x{xor_key:02x}: {os.path.basename(dat_file)}")
                        return xor_key
                
            except Exception as e:
                if debug:
                    print(f"  [ERROR] 读取 {dat_file}: {e}")
                continue
        
        return -1
    
    # 搜索所有目录
    for dir_name, dir_path in search_dirs:
        result = search_in_dir(dir_name, dir_path)
        if result != -1:
            return result
    
    if debug:
        print("\n[!] 未找到异或密钥")
        print("[!] 可能原因:")
        print("    1. 微信 4.1.8.29 版本改变了图片加密方式")
        print("    2. 缓存目录中没有足够的 .dat 文件")
        print("    3. 图片使用全新的加密方案")
    
    return 0


def get_decode_code_v4_manual(xor_key_hex: str = None) -> int:
    """
    手动设置异或密钥（用于已知密钥的情况）
    
    :param xor_key_hex: 十六进制格式的密钥，如 '0x5c' 或 '5c'
    :return: 整数格式的密钥
    """
    if xor_key_hex:
        # 处理各种格式
        key_str = xor_key_hex.strip().replace('0x', '')
        return int(key_str, 16)
    return 0


# 导出函数
__all__ = [
    'get_decode_code_v4_fixed',
    'get_decode_code_v4_manual',
    'is_v4_image',
    'AES_KEY_MAP',
]


if __name__ == '__main__':
    # 测试
    WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"
    
    if os.path.exists(WX_DIR):
        key = get_decode_code_v4_fixed(WX_DIR, debug=True)
        print(f"\n[*] 最终结果: 0x{key:02x}")
    else:
        print(f"目录不存在: {WX_DIR}")
        print("请修改脚本中的 WX_DIR 变量指向正确的微信目录")
