#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
从Cheat Engine导出文件中查找微信数据库密钥
"""

import os
import sys
import struct
import hmac
import re
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

DUMP_FILE = "Weixin.exe_0x23414606000-0x89000.txt"
RESULTS_FILE = "Search results.txt"
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"


def verify_key(key_bytes, db_path):
    """验证密钥是否能解密数据库"""
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
    except:
        return False


def is_key_like(data):
    """检查数据是否符合密钥特征"""
    if len(data) != 32:
        return False, "Length not 32"
    
    # 检查随机性
    unique = len(set(data))
    if unique < 15:
        return False, f"Low entropy: {unique}"
    
    # 检查是否全零
    if data == b'\x00' * 32:
        return False, "All zeros"
    
    # 检查可打印字符比例
    printable = sum(1 for b in data if 32 <= b < 127)
    if printable > 20:
        return False, f"Too printable: {printable}"
    
    return True, "Good candidate"


def extract_candidates_from_binary(data):
    """从二进制数据中提取候选密钥"""
    candidates = []
    
    for i in range(0, len(data) - 32, 8):  # 步进8字节
        chunk = data[i:i+32]
        is_like, reason = is_key_like(chunk)
        if is_like:
            candidates.append((i, chunk))
    
    return candidates


def extract_candidates_from_text(text):
    """从文本中提取十六进制候选"""
    # 查找64字符的十六进制字符串
    hex_pattern = r'[0-9a-fA-F]{64}'
    matches = re.findall(hex_pattern, text)
    
    candidates = []
    for match in matches:
        try:
            data = bytes.fromhex(match)
            is_like, reason = is_key_like(data)
            if is_like:
                candidates.append((-1, data, match))  # -1表示来自文本
        except:
            pass
    
    return candidates


def analyze_dump_file():
    """分析内存转储文件"""
    print("=" * 70)
    print("Analyzing Memory Dump File")
    print("=" * 70)
    print(f"File: {DUMP_FILE}")
    
    if not os.path.exists(DUMP_FILE):
        print("File not found!")
        return []
    
    # 读取文件
    with open(DUMP_FILE, 'rb') as f:
        data = f.read()
    
    print(f"Size: {len(data)} bytes ({len(data)/1024:.1f} KB)")
    print("\nExtracting candidates...")
    
    candidates = extract_candidates_from_binary(data)
    print(f"Found {len(candidates)} candidates matching key characteristics")
    
    return candidates


def analyze_results_file():
    """分析搜索结果文件"""
    print("\n" + "=" * 70)
    print("Analyzing Search Results File")
    print("=" * 70)
    print(f"File: {RESULTS_FILE}")
    
    if not os.path.exists(RESULTS_FILE):
        print("File not found!")
        return []
    
    # 读取文件
    with open(RESULTS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    
    print(f"Size: {len(text)} bytes ({len(text)/1024:.1f} KB)")
    print("\nExtracting hex candidates...")
    
    candidates = extract_candidates_from_text(text)
    print(f"Found {len(candidates)} candidates matching key characteristics")
    
    return candidates


def verify_candidates(candidates, db_path, source_name):
    """验证候选密钥"""
    print(f"\nVerifying {len(candidates)} candidates from {source_name}...")
    
    valid_keys = []
    
    for i, item in enumerate(candidates, 1):
        if len(item) == 3:  # 来自文本
            offset, data, hex_str = item
            addr_str = "from text"
        else:  # 来自二进制
            offset, data = item
            addr_str = f"offset {offset}"
        
        print(f"  [{i}/{len(candidates)}] Testing {addr_str}...", end='\r')
        
        try:
            if verify_key(data, db_path):
                print(f"\n  [VALID] Found valid key!")
                print(f"    {data.hex()}")
                valid_keys.append(data.hex())
        except:
            pass
    
    print(f"\n  Checked {len(candidates)} candidates")
    return valid_keys


def find_db():
    """查找数据库文件"""
    paths = [
        os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db'),
        os.path.join(WX_DIR, 'db_storage', 'microMsg.db'),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def main():
    print("=" * 70)
    print("WeChat Key Finder - Analyzing Cheat Engine Files")
    print("=" * 70)
    
    # 查找数据库
    db_path = find_db()
    if not db_path:
        print("Database not found!")
        return
    
    print(f"Database: {db_path}\n")
    
    # 分析转储文件
    dump_candidates = analyze_dump_file()
    
    # 分析搜索结果文件
    results_candidates = analyze_results_file()
    
    # 验证候选
    print("\n" + "=" * 70)
    print("Verification Phase")
    print("=" * 70)
    
    valid_from_dump = verify_candidates(dump_candidates, db_path, "memory dump")
    valid_from_results = verify_candidates(results_candidates, db_path, "search results")
    
    # 汇总
    all_valid = list(set(valid_from_dump + valid_from_results))
    
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    
    if all_valid:
        print(f"\nFound {len(all_valid)} valid key(s):\n")
        
        for i, key in enumerate(all_valid, 1):
            print(f"  Key {i}:")
            print(f"  {key}")
            print()
            print(f"  Use this in 1-decrypt-fixed.py:")
            print(f'  MANUAL_KEY_V4 = "{key}"')
            print()
        
        # 保存
        with open('VALID_KEYS.txt', 'w') as f:
            for key in all_valid:
                f.write(key + '\n')
        
        print("=" * 70)
        print("Saved to VALID_KEYS.txt")
        print("=" * 70)
    else:
        print("\nNo valid keys found.")
        print("\nThe key might be:")
        print("1. Outside the dumped memory range")
        print("2. In a different format")
        print("3. Encrypted or obfuscated")
        print("\nTry manually extracting 32 bytes near the phone number")


if __name__ == '__main__':
    main()
