#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/4/7
@Author      : Assistant
@Description : 从微信缓存目录中推导图片解密密钥(xor_key)
用途: 当get_decode_code_v4()无法自动找到密钥时，使用此脚本手动查找
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
current_file_path = Path(__file__).resolve()
project_root = current_file_path.parent.parent
sys.path.insert(0, str(project_root))

from wxManager.decrypt.decrypt_dat import is_v4_image


def find_xor_key_manual(wx_dir):
    """
    从微信目录手动查找xor_key
    原理: 微信4.0图片文件末尾与JPG标志\xff\xd9异或得到xor_key
    """
    print(f"[*] 开始扫描目录: {wx_dir}")
    
    # 需要扫描的目录列表
    scan_dirs = [
        os.path.join(wx_dir, 'cache'),
        os.path.join(wx_dir, 'temp'),
        os.path.join(wx_dir, 'msg'),
        os.path.join(wx_dir, 'db_storage', 'cache'),
    ]
    
    jpg_known_tail = b'\xff\xd9'  # JPG文件末尾标志
    found_keys = {}  # {xor_key: count}
    
    for dir_path in scan_dirs:
        if not os.path.exists(dir_path):
            print(f"[SKIP] 目录不存在: {dir_path}")
            continue
        
        print(f"[*] 扫描目录: {dir_path}")
        
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                if file.endswith("_t.dat"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'rb') as f:
                            data = f.read()
                        
                        # 检查是否是V4格式图片
                        if not is_v4_image(data):
                            continue
                        
                        # 获取文件末尾2字节
                        file_tail = data[-2:]
                        
                        # 推导xor_key
                        xor_key_pair = [c ^ p for c, p in zip(file_tail, jpg_known_tail)]
                        
                        # 检查两个字节的xor_key是否相同（正确的密钥应该相同）
                        if len(set(xor_key_pair)) == 1:
                            xor_key = xor_key_pair[0]
                            found_keys[xor_key] = found_keys.get(xor_key, 0) + 1
                            print(f"[FOUND] {file_path}")
                            print(f"        xor_key: 0x{xor_key:02x} (十进制: {xor_key})")
                    
                    except Exception as e:
                        print(f"[ERROR] 读取文件失败: {file_path} - {e}")
                        continue
    
    if not found_keys:
        print(f"\n[!] 未找到任何有效的xor_key")
        return None
    
    # 统计并返回最常见的密钥
    best_key = max(found_keys, key=found_keys.get)
    count = found_keys[best_key]
    
    print(f"\n[*] 找到的所有密钥:")
    for key, cnt in sorted(found_keys.items()):
        print(f"    0x{key:02x} (十进制: {key:3d}) - 出现 {cnt} 次")
    
    print(f"\n[SUCCESS] 推荐使用的xor_key: 0x{best_key:02x} (十进制: {best_key}, 出现 {count} 次)")
    return best_key


def find_xor_key_v4_advanced(wx_dir):
    """
    高级查找方法: 扫描db_storage目录中的加密图片
    """
    print(f"\n[ADVANCED] 使用高级方法扫描db_storage...")
    
    db_storage_path = os.path.join(wx_dir, 'db_storage')
    if not os.path.exists(db_storage_path):
        print(f"[SKIP] db_storage目录不存在: {db_storage_path}")
        return None
    
    found_keys = {}
    jpg_known_tail = b'\xff\xd9'
    
    # 递归扫描所有.dat文件
    for root, dirs, files in os.walk(db_storage_path):
        for file in files:
            if file.endswith('.dat'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'rb') as f:
                        data = f.read()
                    
                    # 检查是否是V4格式图片
                    if not is_v4_image(data):
                        continue
                    
                    file_tail = data[-2:]
                    xor_key_pair = [c ^ p for c, p in zip(file_tail, jpg_known_tail)]
                    
                    if len(set(xor_key_pair)) == 1:
                        xor_key = xor_key_pair[0]
                        found_keys[xor_key] = found_keys.get(xor_key, 0) + 1
                        print(f"[FOUND] {file_path}")
                        print(f"        xor_key: 0x{xor_key:02x}")
                
                except Exception as e:
                    pass
    
    if found_keys:
        best_key = max(found_keys, key=found_keys.get)
        return best_key
    
    return None


if __name__ == '__main__':
    # 配置你的微信目录
    wx_dir = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"
    
    print("=" * 60)
    print("微信4.0 图片解密密钥查找工具")
    print("=" * 60)
    print(f"微信目录: {wx_dir}\n")
    
    # 检查目录是否存在
    if not os.path.exists(wx_dir):
        print(f"[ERROR] 微信目录不存在: {wx_dir}")
        sys.exit(1)
    
    # 方法1: 基础查找
    xor_key = find_xor_key_manual(wx_dir)
    
    # 方法2: 高级查找（如果第一种方法没找到）
    if xor_key is None:
        xor_key = find_xor_key_v4_advanced(wx_dir)
    
    if xor_key is not None:
        print("\n" + "=" * 60)
        print(f"找到的xor_key: 0x{xor_key:02x} (十进制: {xor_key})")
        print("=" * 60)
        print(f"\n在 1-decrypt.py 中使用此密钥:")
        print(f"\n    me.xor_key = 0x{xor_key:02x}")
    else:
        print("\n[!] 未能自动找到xor_key")
        print("可能的原因:")
        print("  1. cache目录中没有V4格式的图片文件")
        print("  2. 微信版本差异导致密钥存储位置改变")
        print("  3. 请确保微信已登录且有图片消息缓存")
