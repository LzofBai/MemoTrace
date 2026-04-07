#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
处理 Cheat Engine 导出文件
用法: python process_ce_files.py <dump_file> [results_file]
"""

import os
import sys
import struct
import hmac
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

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


def find_db():
    paths = [
        os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db'),
        os.path.join(WX_DIR, 'db_storage', 'microMsg.db'),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def scan_dump(dump_path, db_path):
    print(f"Scanning: {dump_path}")
    
    with open(dump_path, 'rb') as f:
        data = f.read()
    
    print(f"Size: {len(data)} bytes")
    
    # Find phone
    phone = PHONE.encode('utf-16le')
    pos = data.find(phone)
    if pos != -1:
        print(f"Phone at offset: {pos}")
    
    # Scan for keys
    found = []
    for i in range(0, len(data) - 32, 8):
        k = data[i:i+32]
        if len(set(k)) > 15 and k != b'\x00' * 32:
            try:
                if verify(k, db_path):
                    print(f"\n[FOUND] Key at offset {i}")
                    print(f"  {k.hex()}")
                    found.append(k.hex())
            except:
                pass
    
    return found


def main():
    if len(sys.argv) < 2:
        print("Usage: python process_ce_files.py <dump_file>")
        print("Example: python process_ce_files.py @Weixin.exe_0x23414606000-0x89000.tx")
        return
    
    dump_file = sys.argv[1]
    
    if not os.path.exists(dump_file):
        print(f"File not found: {dump_file}")
        return
    
    db_path = find_db()
    if not db_path:
        print("Database not found!")
        return
    
    print(f"DB: {db_path}")
    keys = scan_dump(dump_file, db_path)
    
    if keys:
        print(f"\n{'='*50}")
        print("VALID KEYS:")
        for k in keys:
            print(f"  {k}")
        with open('found_key.txt', 'w') as f:
            f.write('\n'.join(keys))
        print(f"{'='*50}")
    else:
        print("\nNo valid key found")


if __name__ == '__main__':
    main()
