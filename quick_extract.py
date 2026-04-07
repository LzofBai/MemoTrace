#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import struct
import hmac
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

DUMP_FILE = "Weixin.exe_0x23414606000-0x89000.txt"
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"
PHONE = "18206740264"
DUMP_BASE_ADDR = 0x23414606000


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
    print("Quick Key Extractor")
    print("=" * 60)
    
    # Find DB
    db_path = os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db')
    if not os.path.exists(db_path):
        print("DB not found!")
        return
    
    print(f"DB: {db_path}")
    
    # Read dump
    if not os.path.exists(DUMP_FILE):
        print(f"File not found: {DUMP_FILE}")
        return
    
    with open(DUMP_FILE, 'rb') as f:
        data = f.read()
    
    print(f"Dump: {len(data)} bytes")
    
    # Find phone
    phone = PHONE.encode('utf-16le')
    phone_offset = data.find(phone)
    
    if phone_offset == -1:
        print("Phone not found in dump!")
        return
    
    phone_addr = DUMP_BASE_ADDR + phone_offset
    print(f"\nPhone at offset: {phone_offset}")
    print(f"Phone address: 0x{phone_addr:x}")
    
    # Scan around phone (limited range for speed)
    print("\nScanning around phone...")
    found = []
    
    # Define search ranges (relative to phone_offset)
    ranges = [
        (-512, -32),   # 512 bytes before
        (-256, -32),   # 256 bytes before
        (-128, -32),   # 128 bytes before
        (32, 256),     # 256 bytes after
    ]
    
    for start, end in ranges:
        s = phone_offset + start
        e = phone_offset + end
        
        if s < 0:
            s = 0
        if e > len(data):
            e = len(data)
        
        print(f"\nRange: offset {s} to {e}")
        
        for i in range(s, e - 32, 8):
            k = data[i:i+32]
            
            if len(set(k)) < 15:
                continue
            if k == b'\x00' * 32:
                continue
            
            try:
                if verify(k, db_path):
                    addr = DUMP_BASE_ADDR + i
                    print(f"\n[FOUND] Key at 0x{addr:x}")
                    print(f"  {k.hex()}")
                    found.append(k.hex())
            except:
                pass
    
    # Summary
    print("\n" + "=" * 60)
    if found:
        print("VALID KEY(S) FOUND!")
        print("=" * 60)
        for k in found:
            print(f"\n{k}")
            print(f'\nMANUAL_KEY_V4 = "{k}"')
        
        with open('KEY_FOUND.txt', 'w') as f:
            f.write('\n'.join(found))
        print("\nSaved to KEY_FOUND.txt")
    else:
        print("No keys found in standard ranges.")
        print("\nTry manual extraction:")
        print("1. Open the dump in a hex editor")
        print("2. Find the phone number")
        print("3. Look for 32 random bytes nearby")
        print("4. Copy the hex value and test with verify_key_manual.py")


if __name__ == '__main__':
    main()
