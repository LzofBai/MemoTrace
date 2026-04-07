#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
查找微信数据库文件
"""

import os

# 可能的微信目录
POSSIBLE_PATHS = [
    r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9",
    r"G:\xwechat_files\wxid_5e3hd0zrse6w22_c8c9",
    r"C:\Users\16267\Documents\xwechat_files\wxid_5e3hd0zrse6w22_c8c9",
]


def find_db_files(wx_dir):
    """递归查找所有数据库文件"""
    db_files = []
    
    if not os.path.exists(wx_dir):
        return db_files
    
    print(f"扫描目录: {wx_dir}")
    
    for root, dirs, files in os.walk(wx_dir):
        for file in files:
            if file.endswith('.db'):
                full_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(full_path)
                    db_files.append((full_path, size))
                except:
                    pass
        
        # 限制深度
        if root.count(os.sep) > wx_dir.count(os.sep) + 3:
            break
    
    return db_files


def main():
    print("=" * 60)
    print("查找微信数据库文件")
    print("=" * 60)
    
    all_db_files = []
    
    for path in POSSIBLE_PATHS:
        print(f"\n检查: {path}")
        if os.path.exists(path):
            print(f"  目录存在 ✓")
            db_files = find_db_files(path)
            all_db_files.extend(db_files)
            
            # 显示子目录结构
            print(f"  子目录:")
            for item in os.listdir(path):
                full = os.path.join(path, item)
                if os.path.isdir(full):
                    print(f"    - {item}/")
        else:
            print(f"  目录不存在 ✗")
    
    # 显示找到的数据库
    print("\n" + "=" * 60)
    print(f"找到 {len(all_db_files)} 个数据库文件:")
    print("=" * 60)
    
    # 按大小排序
    all_db_files.sort(key=lambda x: x[1])
    
    for path, size in all_db_files[:20]:  # 只显示前20个
        size_mb = size / 1024 / 1024
        print(f"{path}")
        print(f"  大小: {size_mb:.2f} MB\n")
    
    # 推荐用于测试的文件
    print("\n" + "=" * 60)
    print("推荐用于密钥测试的文件（较小的系统数据库）:")
    print("=" * 60)
    
    small_dbs = [f for f in all_db_files if f[1] < 10 * 1024 * 1024]  # < 10MB
    if small_dbs:
        for path, size in small_dbs[:5]:
            print(f"  {path}")
    else:
        print("  未找到小数据库，使用:")
        if all_db_files:
            print(f"  {all_db_files[0][0]}")


if __name__ == '__main__':
    # 也检查用户指定的目录
    import sys
    if len(sys.argv) > 1:
        custom_path = sys.argv[1]
        if custom_path not in POSSIBLE_PATHS:
            POSSIBLE_PATHS.insert(0, custom_path)
    
    main()
