#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
分析 Cheat Engine 导出的内存文件
查找微信数据库密钥
"""

import os
import struct
import hmac
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

# 文件路径
DUMP_FILE = "@Weixin.exe_0x23414606000-0x89000.tx"
RESULTS_FILE = "@Search results.txt"

# 微信目录
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"

# 已知信息
PHONE_NUMBER = "18206740264"


def verify_key(key_bytes, db_path):
    """验证密钥是否正确"""
    try:
        with open(db_path, 'rb') as f:
            buf = f.read(4096)
        
        salt = buf[:16]
        if salt == b'\x00' * 16 or len(set(salt)) == 1:
            return False
        
        mac_salt = bytes(x ^ 0x3a for x in salt)
        new_key = PBKDF2(key_bytes, salt, dkLen=32, count=256000, hmac_hash_module=SHA512)
        mac_key = PBKDF2(new_key, mac_salt, dkLen=32, count=2, hmac_hash_module=SHA512)
        
        mac = hmac.new(mac_key, buf[16:4072], SHA512)
        mac.update(struct.pack('<I', 1))
        hash_mac = mac.digest()
        stored_mac = buf[4080:4144]
        
        return hash_mac == stored_mac
    except Exception as e:
        return False


def find_db():
    """查找数据库文件"""
    paths = [
        os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db'),
        os.path.join(WX_DIR, 'db_storage', 'microMsg.db'),
        os.path.join(WX_DIR, 'db_storage', 'session.db'),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def analyze_dump_file(dump_path, db_path):
    """
    分析内存转储文件
    在转储中查找密钥
    """
    print("=" * 60)
    print("Analyzing Memory Dump File")
    print("=" * 60)
    print(f"File: {dump_path}")
    
    if not os.path.exists(dump_path):
        print(f"File not found: {dump_path}")
        return []
    
    # 读取转储文件
    with open(dump_path, 'rb') as f:
        data = f.read()
    
    print(f"Dump size: {len(data)} bytes ({len(data)/1024:.1f} KB)")
    
    # 查找手机号位置
    phone_utf16 = PHONE_NUMBER.encode('utf-16le')
    phone_pos = data.find(phone_utf16)
    
    if phone_pos != -1:
        print(f"\nPhone number found at offset: {phone_pos} (0x{phone_pos:04x})")
    else:
        print("\nPhone number not found in dump")
    
    # 在转储中滑动查找 32 字节密钥候选
    print("\nScanning for 32-byte keys...")
    
    valid_keys = []
    checked = 0
    
    # 扫描整个转储
    for i in range(0, len(data) - 32, 8):  # 步进 8 字节
        candidate = data[i:i+32]
        
        # 快速过滤
        unique_bytes = len(set(candidate))
        if unique_bytes < 15:  # 随机性太低
            continue
        if candidate == b'\x00' * 32:
            continue
        
        # 检查可打印字符比例
        printable = sum(1 for b in candidate if 32 <= b < 127)
        if printable > 20:  # 太多可打印字符
            continue
        
        checked += 1
        
        # 验证密钥
        try:
            if verify_key(candidate, db_path):
                print(f"\n[FOUND] Valid key at offset {i} (0x{i:04x})")
                print(f"  Key: {candidate.hex()}")
                valid_keys.append((i, candidate))
        except:
            pass
        
        if checked % 1000 == 0:
            print(f"  Checked {checked} candidates...", end='\r')
    
    print(f"\nTotal candidates checked: {checked}")
    return valid_keys


def analyze_results_file(results_path):
    """
    分析搜索结果文件
    提取可能的地址信息
    """
    print("\n" + "=" * 60)
    print("Analyzing Search Results File")
    print("=" * 60)
    print(f"File: {results_path}")
    
    if not os.path.exists(results_path):
        print(f"File not found: {results_path}")
        return
    
    with open(results_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    print(f"File size: {len(content)} bytes")
    print("\nContent preview:")
    print("-" * 60)
    print(content[:2000])
    print("-" * 60)


def extract_hex_from_text(text):
    """从文本中提取十六进制数据"""
    import re
    
    # 查找连续的十六进制字符串（64字符 = 32字节）
    hex_pattern = r'[0-9a-fA-F]{64}'
    matches = re.findall(hex_pattern, text)
    
    return matches


def test_candidates_from_file(file_path, db_path):
    """测试文件中提取的候选密钥"""
    print("\n" + "=" * 60)
    print("Testing Candidates from File")
    print("=" * 60)
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # 提取十六进制候选
    candidates = extract_hex_from_text(content)
    
    print(f"Found {len(candidates)} hex candidates (64 chars)")
    
    valid_keys = []
    for candidate in candidates:
        try:
            key_bytes = bytes.fromhex(candidate)
            if verify_key(key_bytes, db_path):
                print(f"\n[VALID] {candidate}")
                valid_keys.append(candidate)
        except:
            pass
    
    return valid_keys


def main():
    print("=" * 60)
    print("Cheat Engine Dump Analyzer")
    print("=" * 60)
    
    # 查找数据库
    db_path = find_db()
    if not db_path:
        print("Database not found!")
        return
    
    print(f"Database: {db_path}")
    print()
    
    # 分析内存转储
    keys_from_dump = []
    if os.path.exists(DUMP_FILE):
        keys_from_dump = analyze_dump_file(DUMP_FILE, db_path)
    else:
        print(f"Dump file not found: {DUMP_FILE}")
        print("Please ensure the file is in the current directory")
    
    # 分析搜索结果
    if os.path.exists(RESULTS_FILE):
        analyze_results_file(RESULTS_FILE)
        
        # 也尝试从结果文件中提取密钥
        keys_from_results = test_candidates_from_file(RESULTS_FILE, db_path)
    else:
        print(f"Results file not found: {RESULTS_FILE}")
        keys_from_results = []
    
    # 汇总结果
    all_keys = set()
    for offset, key in keys_from_dump:
        all_keys.add(key.hex())
    for key in keys_from_results:
        all_keys.add(key)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if all_keys:
        print(f"\nFound {len(all_keys)} valid key(s):")
        for key in all_keys:
            print(f"\n  {key}")
            print(f"  Use in 1-decrypt-fixed.py:")
            print(f'  MANUAL_KEY_V4 = "{key}"')
        
        # 保存到文件
        with open('found_keys.txt', 'w') as f:
            for key in all_keys:
                f.write(key + '\n')
        print("\nSaved to found_keys.txt")
    else:
        print("\nNo valid keys found in the dump files.")
        print("\nSuggestions:")
        print("1. Make sure the dump includes the area near the phone number")
        print("2. Try dumping a larger memory range in Cheat Engine")
        print("3. Look for 32 bytes of random data near the phone manually")


if __name__ == '__main__':
    main()
