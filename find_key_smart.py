#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
智能查找密钥 - 只验证最佳候选
"""

import os
import struct
import hmac
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

DUMP_FILE = "Weixin.exe_0x23414606000-0x89000.txt"
RESULTS_FILE = "Search results.txt"
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"
PHONE = "18206740264"


def verify(key, db_path):
    with open(db_path, 'rb') as f:
        buf = f.read(4096)
    salt = buf[:16]
    if salt == b'\x00' * 16:
        return False
    mac_salt = bytes(x ^ 0x3a for x in salt)
    new_key = PBKDF2(key, salt, dkLen=32, count=256000, hmac_hash_module=SHA512)
    mac_key = PBKDF2(new_key, mac_salt, dkLen=32, count=2, hmac_hash_module=SHA512)
    mac = hmac.new(mac_key, buf[16:4072], SHA512)
    mac.update(struct.pack('<I', 1))
    return mac.digest() == buf[4080:4144]


def score_candidate(data):
    """给候选评分，越高越可能是密钥"""
    score = 0
    
    # 随机性评分
    unique = len(set(data))
    score += unique
    
    # 惩罚可打印字符
    printable = sum(1 for b in data if 32 <= b < 127)
    score -= printable * 2
    
    # 惩罚连续相同字节
    for i in range(len(data) - 1):
        if data[i] == data[i+1]:
            score -= 5
    
    # 奖励特定范围内的字节
    for b in data:
        if 0x20 <= b <= 0xDF:  # 避开常见字符串范围
            score += 1
    
    return score


def main():
    print("=" * 60)
    print("Smart Key Finder")
    print("=" * 60)
    
    db_path = os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db')
    
    # Read dump
    with open(DUMP_FILE, 'rb') as f:
        dump = f.read()
    
    print(f"Dump: {len(dump)} bytes")
    
    # Find phone
    phone = PHONE.encode('utf-16le')
    phone_off = dump.find(phone)
    
    if phone_off == -1:
        print("Phone not found!")
        return
    
    print(f"Phone at offset: {phone_off}")
    
    # Collect candidates near phone
    candidates = []
    
    # Search range: 1KB before and after phone
    for i in range(max(0, phone_off - 1024), min(len(dump) - 32, phone_off + 1024), 8):
        k = dump[i:i+32]
        if len(set(k)) > 15 and k != b'\x00' * 32:
            score = score_candidate(k)
            candidates.append((score, i, k))
    
    # Sort by score
    candidates.sort(reverse=True)
    
    print(f"\nTop 50 candidates near phone:")
    print("-" * 60)
    
    # Test top 50
    found = []
    for score, offset, key in candidates[:50]:
        try:
            if verify(key, db_path):
                addr = 0x23414606000 + offset
                print(f"\n[FOUND] Valid key!")
                print(f"  Offset: {offset}")
                print(f"  Address: 0x{addr:x}")
                print(f"  Key: {key.hex()}")
                found.append(key.hex())
        except:
            pass
    
    if found:
        print(f"\n{'='*60}")
        print("VALID KEY(S):")
        for k in found:
            print(f"  {k}")
        print(f"{'='*60}")
        
        with open('KEY.txt', 'w') as f:
            f.write('\n'.join(found))
        print("Saved to KEY.txt")
    else:
        print("\nNo valid key found in top 50 candidates.")
        print("The key might be outside the 1KB range.")


if __name__ == '__main__':
    main()
