#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
从 Cheat Engine 内存浏览器直接复制数据后验证
"""

import os
import struct
import hmac
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"


def verify_key(key_hex):
    """验证密钥"""
    try:
        key = bytes.fromhex(key_hex.replace(' ', ''))
    except:
        print("Invalid hex format")
        return False
    
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
        print("DB not found")
        return False
    
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
    print("Cheat Engine Key Extractor")
    print("=" * 60)
    print()
    print("Instructions:")
    print("1. In Cheat Engine memory browser, find 32 bytes of random data")
    print("   near the phone number (within 500 bytes)")
    print("2. Right click -> Copy -> Hex (NOT 'Hex string')")
    print("3. Paste here and press Enter")
    print()
    print("The key should look like:")
    print("  a1b2c3d4e5f6789012345678abcdef00...")
    print("  (64 hex characters, 32 bytes)")
    print()
    print("-" * 60)
    
    while True:
        data = input("\nPaste hex data (or 'quit'): ").strip()
        
        if data.lower() == 'quit':
            break
        
        # Clean input
        data = data.replace(' ', '').replace('-', '')
        
        # Try different lengths
        candidates = []
        
        # If input is exactly 64 chars, test as-is
        if len(data) == 64:
            candidates.append(data)
        
        # If longer, extract 64-char chunks
        elif len(data) > 64:
            for i in range(0, len(data) - 63, 2):
                chunk = data[i:i+64]
                if len(chunk) == 64:
                    candidates.append(chunk)
        
        if not candidates:
            print("Input too short or invalid")
            continue
        
        print(f"\nTesting {len(candidates)} candidate(s)...")
        
        found = False
        for candidate in candidates:
            try:
                if verify_key(candidate):
                    print("\n" + "=" * 60)
                    print("SUCCESS! Valid key found!")
                    print("=" * 60)
                    print(f"Key: {candidate}")
                    print()
                    print("Edit 1-decrypt-fixed.py:")
                    print(f'MANUAL_KEY_V4 = "{candidate}"')
                    print("=" * 60)
                    
                    with open('wechat_key.txt', 'w') as f:
                        f.write(candidate)
                    print("\nSaved to wechat_key.txt")
                    found = True
                    break
            except Exception as e:
                pass
        
        if not found:
            print("No valid key in the provided data")
            print("Try copying a different 32-byte region")


if __name__ == '__main__':
    main()
