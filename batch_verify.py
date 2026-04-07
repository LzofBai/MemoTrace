#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
批量验证转储中的候选密钥
"""

import os
import struct
import hmac
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

DUMP_FILE = "Weixin.exe_0x23414606000-0x89000.txt"
DUMP_BASE = 0x23414606000
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"


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


def is_good_candidate(data):
    """严格过滤"""
    if len(data) != 32:
        return False
    
    unique = len(set(data))
    if unique < 20:  # 要求更高随机性
        return False
    
    printable = sum(1 for b in data if 32 <= b < 127)
    if printable > 15:  # 更少可打印字符
        return False
    
    # 检查是否有连续重复
    repeats = sum(1 for i in range(len(data)-1) if data[i] == data[i+1])
    if repeats > 2:
        return False
    
    return True


def main():
    print("Batch Verify Keys from Dump")
    print("=" * 60)
    
    # Load dump
    with open(DUMP_FILE, 'rb') as f:
        dump = f.read()
    
    print(f"Dump: {len(dump)} bytes")
    
    # Find DB
    db_path = os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db')
    
    # Collect candidates
    candidates = []
    for i in range(0, len(dump) - 32, 32):  # 32字节对齐
        k = dump[i:i+32]
        if is_good_candidate(k):
            candidates.append((i, k))
    
    print(f"Found {len(candidates)} good candidates")
    print(f"Verifying first 100...")
    
    # Verify
    found = []
    for idx, (offset, key) in enumerate(candidates[:100], 1):
        print(f"  [{idx}/100] offset {offset}...", end='\r')
        try:
            if verify(key, db_path):
                addr = DUMP_BASE + offset
                print(f"\n[FOUND] Key at 0x{addr:x}")
                print(f"  {key.hex()}")
                found.append(key.hex())
        except:
            pass
    
    print(f"\n\nChecked 100 candidates")
    
    if found:
        print(f"\n{'='*60}")
        print("VALID KEY(S):")
        for k in found:
            print(f"  {k}")
        with open('VALID_KEY.txt', 'w') as f:
            f.write('\n'.join(found))
    else:
        print("\nNo valid keys in first 100 candidates.")
        print("Trying next 100...")
        
        # Try more
        for idx, (offset, key) in enumerate(candidates[100:200], 1):
            print(f"  [{idx}/100] offset {offset}...", end='\r')
            try:
                if verify(key, db_path):
                    addr = DUMP_BASE + offset
                    print(f"\n[FOUND] Key at 0x{addr:x}")
                    print(f"  {key.hex()}")
                    found.append(key.hex())
            except:
                pass
        
        if found:
            print(f"\n{'='*60}")
            print("VALID KEY(S):")
            for k in found:
                print(f"  {k}")
            with open('VALID_KEY.txt', 'w') as f:
                f.write('\n'.join(found))
        else:
            print("\nStill no valid keys.")


if __name__ == '__main__':
    main()
