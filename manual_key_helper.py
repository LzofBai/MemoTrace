#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
手动输入密钥辅助工具
当自动扫描失败时使用
"""

import os
import sys

WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"


def test_key_on_db(key_hex, db_path):
    """测试密钥是否能解密数据库"""
    try:
        import struct
        import hmac
        from Crypto.Protocol.KDF import PBKDF2
        from Crypto.Hash import SHA512
        
        key = bytes.fromhex(key_hex)
        
        with open(db_path, 'rb') as f:
            buf = f.read(4096)
        
        salt = buf[:16]
        if salt == b'\x00' * 16 or len(set(salt)) == 1:
            return False
        
        mac_salt = bytes(x ^ 0x3a for x in salt)
        new_key = PBKDF2(key, salt, dkLen=32, count=256000, hmac_hash_module=SHA512)
        mac_key = PBKDF2(new_key, mac_salt, dkLen=32, count=2, hmac_hash_module=SHA512)
        
        mac = hmac.new(mac_key, buf[16:4072], SHA512)
        mac.update(struct.pack('<I', 1))
        hash_mac = mac.digest()
        stored_mac = buf[4080:4144]
        
        return hash_mac == stored_mac
    except Exception as e:
        print(f"Error: {e}")
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


def main():
    print("=" * 60)
    print("Manual Key Input Helper")
    print("=" * 60)
    
    db_path = find_db()
    if not db_path:
        print("Database not found!")
        return
    
    print(f"Database: {db_path}")
    print()
    
    # 提示用户
    print("Auto-scan failed. You can manually enter a key to test.")
    print()
    print("Where to find the key:")
    print("1. If you have a backup of the key from before")
    print("2. From another device with the same account")
    print("3. From WeChat 3.x backup (may not work for 4.x)")
    print()
    print("The key is 64 hex characters (32 bytes).")
    print("Example: c9eaed112cbb4dd896a5dd7314186a24598951f2efff4afe812fb7556f4fc4ce")
    print()
    
    while True:
        key = input("Enter key (or 'quit' to exit): ").strip()
        
        if key.lower() == 'quit':
            break
        
        # 清理输入
        key = key.replace(" ", "").replace("-", "")
        
        if len(key) != 64:
            print(f"Invalid length: {len(key)} (should be 64)")
            continue
        
        try:
            bytes.fromhex(key)
        except:
            print("Invalid hex format")
            continue
        
        print(f"Testing key: {key[:16]}...{key[-16:]}")
        
        if test_key_on_db(key, db_path):
            print("\n" + "=" * 60)
            print("SUCCESS! Key is valid!")
            print("=" * 60)
            print(f"Key: {key}")
            print()
            print("Use this key in 1-decrypt-fixed.py:")
            print(f'MANUAL_KEY_V4 = "{key}"')
            print("=" * 60)
            
            # 保存到文件
            save = input("\nSave to key.txt? (y/n): ").strip().lower()
            if save == 'y':
                with open('wechat_key_41829.txt', 'w') as f:
                    f.write(key)
                print("Saved to wechat_key_41829.txt")
            
            return key
        else:
            print("Key is INVALID\n")
    
    return None


if __name__ == '__main__':
    main()
