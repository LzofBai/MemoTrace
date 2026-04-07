#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
手动提取密钥辅助工具
用于验证从 Cheat Engine 手动复制的密钥
"""

import os
import struct
import hmac
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"


def verify(key_hex):
    """验证密钥"""
    try:
        key = bytes.fromhex(key_hex.replace(' ', ''))
    except:
        return False, "Invalid hex"
    
    if len(key) != 32:
        return False, f"Length {len(key)} != 32"
    
    # Find DB
    paths = [
        os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db'),
        os.path.join(WX_DIR, 'db_storage', 'microMsg.db'),
    ]
    
    db_path = None
    for p in paths:
        if os.path.exists(p):
            db_path = p
            break
    
    if not db_path:
        return False, "DB not found"
    
    with open(db_path, 'rb') as f:
        buf = f.read(4096)
    
    salt = buf[:16]
    if salt == b'\x00' * 16:
        return False, "Invalid salt"
    
    mac_salt = bytes(x ^ 0x3a for x in salt)
    new_key = PBKDF2(key, salt, dkLen=32, count=256000, hmac_hash_module=SHA512)
    mac_key = PBKDF2(new_key, mac_salt, dkLen=32, count=2, hmac_hash_module=SHA512)
    
    mac = hmac.new(mac_key, buf[16:4072], SHA512)
    mac.update(struct.pack('<I', 1))
    
    if mac.digest() == buf[4080:4144]:
        return True, "Valid key!"
    else:
        return False, "HMAC mismatch"


def main():
    print("=" * 60)
    print("Manual Key Extract Helper")
    print("=" * 60)
    print()
    print("Instructions:")
    print("1. In Cheat Engine, find phone number 18206740264")
    print("2. Look for 32 bytes of random data nearby")
    print("3. Right-click -> Copy -> Hex")
    print("4. Paste here (64 hex characters)")
    print()
    print("The key should look like: a1b2c3d4... (64 chars)")
    print("=" * 60)
    
    while True:
        print()
        data = input("Paste hex (or 'quit'): ").strip()
        
        if data.lower() == 'quit':
            break
        
        # Clean
        data = data.replace(' ', '').replace('-', '')
        
        if len(data) != 64:
            print(f"Length {len(data)} != 64, skipping")
            continue
        
        print(f"Testing: {data[:16]}...{data[-16:]}")
        
        valid, msg = verify(data)
        
        if valid:
            print("\n" + "=" * 60)
            print("SUCCESS! Valid key found!")
            print("=" * 60)
            print(f"Key: {data}")
            print()
            print("Use in 1-decrypt-fixed.py:")
            print(f'MANUAL_KEY_V4 = "{data}"')
            print("=" * 60)
            
            with open('WECHAT_KEY.txt', 'w') as f:
                f.write(data)
            print("\nSaved to WECHAT_KEY.txt")
            break
        else:
            print(f"Invalid: {msg}")


if __name__ == '__main__':
    main()
