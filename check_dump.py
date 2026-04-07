#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
检查转储文件内容
"""

DUMP_FILE = "Weixin.exe_0x23414606000-0x89000.txt"
PHONE = "18206740264"

# 转储的基址
DUMP_BASE = 0x23414606000

with open(DUMP_FILE, 'rb') as f:
    data = f.read()

print(f"Dump size: {len(data)} bytes")
print(f"Dump range: 0x{DUMP_BASE:x} - 0x{DUMP_BASE + len(data):x}")

# 查找手机号
phone = PHONE.encode('utf-16le')
pos = data.find(phone)

if pos != -1:
    addr = DUMP_BASE + pos
    print(f"\nPhone found at:")
    print(f"  Offset: {pos}")
    print(f"  Address: 0x{addr:x}")
else:
    print("\nPhone not found!")
    
    # 尝试部分匹配
    print("\nTrying partial matches...")
    for i in range(0, len(phone) - 4, 2):
        partial = phone[i:i+4]
        pos = data.find(partial)
        if pos != -1:
            addr = DUMP_BASE + pos
            print(f"  Found partial at 0x{addr:x}")

# 显示文件开头
print("\nFirst 256 bytes (hex):")
print(' '.join(f'{b:02x}' for b in data[:256]))
