#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys

wx_dir = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"

if len(sys.argv) > 1:
    wx_dir = sys.argv[1]

print("Checking:", wx_dir)

if not os.path.exists(wx_dir):
    print("Directory not found!")
    sys.exit(1)

print("Directory exists")
print("\nSubdirectories:")
for item in os.listdir(wx_dir):
    full = os.path.join(wx_dir, item)
    if os.path.isdir(full):
        print("  -", item)

print("\nLooking for .db files...")
db_files = []
for root, dirs, files in os.walk(wx_dir):
    for f in files:
        if f.endswith('.db'):
            db_files.append(os.path.join(root, f))
    if len(db_files) > 20:
        break

print(f"Found {len(db_files)} database files:")
for db in db_files[:10]:
    size = os.path.getsize(db) / 1024 / 1024
    print(f"  {db} ({size:.2f} MB)")
