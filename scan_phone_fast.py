#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
在手机号地址附近快速扫描密钥
地址: 0x23414606788
"""

import os
import ctypes
import struct
import psutil
import hmac

# 配置
PHONE_ADDR = 0x23414606788
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"

# Windows API
kernel32 = ctypes.windll.kernel32
PROCESS_VM_READ = 0x0010


def read_mem(pid, addr, size):
    h = kernel32.OpenProcess(PROCESS_VM_READ, False, pid)
    if not h:
        return None
    buf = ctypes.create_string_buffer(size)
    read = ctypes.c_size_t(0)
    success = kernel32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(read))
    kernel32.CloseHandle(h)
    return buf.raw if success else None


def verify(key, buf):
    from Crypto.Protocol.KDF import PBKDF2
    from Crypto.Hash import SHA512
    
    salt = buf[:16]
    if salt == b'\x00' * 16 or len(set(salt)) == 1:
        return False
    
    mac_salt = bytes(x ^ 0x3a for x in salt)
    new_key = PBKDF2(key, salt, dkLen=32, count=256000, hmac_hash_module=SHA512)
    mac_key = PBKDF2(new_key, mac_salt, dkLen=32, count=2, hmac_hash_module=SHA512)
    
    mac = hmac.new(mac_key, buf[16:4072], SHA512)
    mac.update(struct.pack('<I', 1))
    return mac.digest() == buf[4080:4144]


def main():
    print("Scanning for key near phone address...")
    print(f"Phone: 0x{PHONE_ADDR:016x}")
    
    # Get PID
    pid = None
    for p in psutil.process_iter(['pid', 'name']):
        if p.name() == 'Weixin.exe':
            pid = p.pid
            break
    
    if not pid:
        print("WeChat not running!")
        return
    
    # Get DB
    db_path = os.path.join(WX_DIR, 'db_storage', 'favorite', 'favorite_fts.db')
    with open(db_path, 'rb') as f:
        buf = f.read(4096)
    
    # Read memory around phone
    start = PHONE_ADDR - 1024
    mem = read_mem(pid, start, 2048 + 32)
    
    if not mem:
        print("Failed to read memory")
        return
    
    print(f"Read {len(mem)} bytes")
    
    # Find phone
    phone = b'1\x008\x002\x000\x006\x007\x004\x000\x002\x006\x004\x00'
    off = mem.find(phone)
    
    if off == -1:
        print("Phone not found in memory!")
        return
    
    print(f"Phone at offset: {off}")
    
    # Scan around phone
    found = []
    for i in range(0, len(mem) - 32, 8):
        k = mem[i:i+32]
        if len(set(k)) > 15 and k != b'\x00' * 32:
            try:
                if verify(k, buf):
                    addr = start + i
                    print(f"\n[FOUND] Key at 0x{addr:016x}")
                    print(f"Key: {k.hex()}")
                    found.append(k.hex())
            except:
                pass
    
    if found:
        print(f"\n{'='*50}")
        print("VALID KEY(S) FOUND!")
        for k in found:
            print(f"  {k}")
        print(f"{'='*50}")
        with open('key_found.txt', 'w') as f:
            f.write('\n'.join(found))
        print("Saved to key_found.txt")
    else:
        print("\nNo valid key found")
        print("Try increasing scan range or manual search")


if __name__ == '__main__':
    try:
        from Crypto.Protocol.KDF import PBKDF2
        from Crypto.Hash import SHA512
        main()
    except ImportError:
        print("pip install pycryptodome")
