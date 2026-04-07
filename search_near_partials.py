#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
在部分手机号匹配附近搜索密钥
"""

import os
import struct
import hmac
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

DUMP_FILE = "Weixin.exe_0x23414606000-0x89000.txt"
DUMP_BASE = 0x23414606000
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"

# 部分匹配地址
PARTIAL_ADDRS = [
    0x2341464c9ec,
    0x2341467ff06,
    0x2341460625e,
    0x23414606260,
    0x23414615242,
    0x2341467ff1a,
    0x2341465019a,
    0x23414612e40,
    0x2341462076a,
]


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


def main():
    print("=" * 60)
    print("Searching Near Partial Phone Matches")
    print("=" * 60)
    
    # Load dump
    with open(DUMP_FILE, 'rb') as f:
        dump = f.read()
    
    print(f"Dump: {len(dump)} bytes")
    
    # Find DB
    db_path = os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db')
    
    found_keys = []
    
    for addr in PARTIAL_ADDRS:
        offset = addr - DUMP_BASE
        
        if offset < 0 or offset >= len(dump):
            continue
        
        print(f"\nChecking address 0x{addr:x} (offset {offset})")
        
        # Search 512 bytes around this address
        start = max(0, offset - 512)
        end = min(len(dump) - 32, offset + 512)
        
        for i in range(start, end, 8):
            k = dump[i:i+32]
            
            # Filter
            if len(set(k)) < 15:
                continue
            if k == b'\x00' * 32:
                continue
            
            # Check printable
            printable = sum(1 for b in k if 32 <= b < 127)
            if printable > 20:
                continue
            
            try:
                if verify(k, db_path):
                    real_addr = DUMP_BASE + i
                    print(f"\n[FOUND] Key at 0x{real_addr:x}")
                    print(f"  {k.hex()}")
                    found_keys.append(k.hex())
            except:
                pass
    
    # Summary
    print("\n" + "=" * 60)
    if found_keys:
        print("VALID KEY(S) FOUND!")
        for k in set(found_keys):
            print(f"\n{k}")
        
        with open('FOUND_KEY.txt', 'w') as f:
            f.write('\n'.join(set(found_keys)))
        print("\nSaved to FOUND_KEY.txt")
    else:
        print("No keys found near partial matches.")


if __name__ == '__main__':
    main()
