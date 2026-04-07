#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import struct
import hmac
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

# 文件路径
DUMP_FILE = "Weixin.exe_0x23414606000-0x89000.txt"
RESULTS_FILE = "Search results.txt"

# 微信目录
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


def analyze_dump():
    print("=" * 60)
    print("Analyzing Memory Dump")
    print("=" * 60)
    
    db_path = find_db()
    if not db_path:
        print("DB not found!")
        return []
    
    print(f"DB: {db_path}")
    
    # Check if file exists
    if not os.path.exists(DUMP_FILE):
        print(f"File not found: {DUMP_FILE}")
        return []
    
    # Read file
    with open(DUMP_FILE, 'rb') as f:
        data = f.read()
    
    print(f"Dump size: {len(data)} bytes ({len(data)/1024:.1f} KB)")
    
    # Find phone
    phone = PHONE.encode('utf-16le')
    pos = data.find(phone)
    
    if pos != -1:
        print(f"\nPhone found at offset: {pos} (0x{pos:x})")
    else:
        print("\nPhone not found")
    
    # Scan for keys
    print("\nScanning for 32-byte keys...")
    found = []
    total = len(data) - 32
    
    for i in range(0, total, 8):
        k = data[i:i+32]
        
        # Filter
        if len(set(k)) < 15:
            continue
        if k == b'\x00' * 32:
            continue
        
        # Check
        try:
            if verify(k, db_path):
                addr = 0x23414606000 + i
                print(f"\n[FOUND] Key at offset {i}")
                print(f"  Address: 0x{addr:x}")
                print(f"  Key: {k.hex()}")
                found.append(k.hex())
        except:
            pass
        
        if i % 10000 == 0:
            print(f"  Progress: {i}/{total} ({i*100//total}%)\r", end='')
    
    print(f"\n\nChecked {total//8} candidates")
    return found


def extract_from_results():
    print("\n" + "=" * 60)
    print("Extracting from Search Results")
    print("=" * 60)
    
    if not os.path.exists(RESULTS_FILE):
        print(f"File not found: {RESULTS_FILE}")
        return []
    
    db_path = find_db()
    
    with open(RESULTS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    print(f"File size: {len(content)} bytes")
    
    # Extract 64-char hex strings
    import re
    hex_strings = re.findall(r'[0-9a-fA-F]{64}', content)
    
    print(f"Found {len(hex_strings)} hex candidates")
    
    # Test each
    found = []
    for candidate in hex_strings:
        try:
            key = bytes.fromhex(candidate)
            if verify(key, db_path):
                print(f"\n[FOUND] Valid key: {candidate}")
                found.append(candidate)
        except:
            pass
    
    return found


def main():
    print("=" * 60)
    print("Cheat Engine Files Analysis")
    print("=" * 60)
    
    # Analyze dump
    keys_from_dump = analyze_dump()
    
    # Analyze results
    keys_from_results = extract_from_results()
    
    # Summary
    all_keys = list(set(keys_from_dump + keys_from_results))
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    if all_keys:
        print(f"\nFound {len(all_keys)} valid key(s):\n")
        for key in all_keys:
            print(f"  {key}")
            print(f"\n  Use in 1-decrypt-fixed.py:")
            print(f'  MANUAL_KEY_V4 = "{key}"')
            print()
        
        with open('FOUND_KEY.txt', 'w') as f:
            f.write('\n'.join(all_keys))
        print("Saved to FOUND_KEY.txt")
    else:
        print("\nNo valid keys found.")
        print("\nNext steps:")
        print("1. Check if the dump includes the area near phone number")
        print("2. The key might be in a different memory region")
        print("3. Try manually extracting 32 bytes near the phone")


if __name__ == '__main__':
    main()
