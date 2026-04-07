#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
微信 4.1.8.29 数据库密钥问题快速诊断
"""

import os
import sys

def check_environment():
    """检查环境"""
    print("=" * 60)
    print("环境检查")
    print("=" * 60)
    
    # 检查 Python 版本
    print(f"Python 版本: {sys.version}")
    
    # 检查依赖
    try:
        import pymem
        print(f"[OK] pymem 已安装")
    except ImportError:
        print("✗ pymem 未安装 (pip install pymem)")
    
    try:
        import yara
        print(f"[OK] yara-python 已安装")
    except ImportError:
        print("✗ yara-python 未安装 (pip install yara-python)")
    
    try:
        from Crypto.Protocol.KDF import PBKDF2
        print(f"[OK] pycryptodome 已安装")
    except ImportError:
        print("✗ pycryptodome 未安装 (pip install pycryptodome)")
    
    try:
        import psutil
        print(f"[OK] psutil 已安装")
    except ImportError:
        print("✗ psutil 未安装 (pip install psutil)")
    
    print()


def check_wechat_running():
    """检查微信是否运行"""
    print("=" * 60)
    print("微信进程检查")
    print("=" * 60)
    
    try:
        import psutil
        
        weixin_found = False
        for process in psutil.process_iter(['pid', 'name', 'exe']):
            if process.name() == 'Weixin.exe':
                weixin_found = True
                print(f"[OK] 发现 Weixin.exe (PID: {process.pid})")
                try:
                    print(f"  路径: {process.exe()}")
                except:
                    pass
                
                # 检查 Weixin.dll
                for module in process.memory_maps(grouped=False):
                    if 'Weixin.dll' in module.path:
                        base_addr = int(module.addr, 16)
                        print(f"  Weixin.dll 基址: 0x{base_addr:08x}")
                        break
        
        if not weixin_found:
            print("✗ Weixin.exe 未运行")
            print("  请先登录微信 4.x 后再运行解密")
        
    except Exception as e:
        print(f"[FAIL] 检查失败: {e}")
    
    print()


def check_wechat_directory():
    """检查微信目录"""
    print("=" * 60)
    print("微信目录检查")
    print("=" * 60)
    
    wx_dir = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"
    
    print(f"指定目录: {wx_dir}")
    
    if os.path.exists(wx_dir):
        print("[OK] 目录存在")
        
        # 检查子目录
        subdirs = ['db_storage', 'cache', 'temp', 'msg']
        for subdir in subdirs:
            full_path = os.path.join(wx_dir, subdir)
            if os.path.exists(full_path):
                print(f"  [OK] {subdir}/")
            else:
                print(f"  [FAIL] {subdir}/ (不存在)")
        
        # 检查数据库文件
        db_storage = os.path.join(wx_dir, 'db_storage')
        if os.path.exists(db_storage):
            db_files = []
            for root, dirs, files in os.walk(db_storage):
                for file in files:
                    if file.endswith('.db'):
                        db_files.append(os.path.join(root, file))
                if len(db_files) > 10:
                    break
            
            print(f"\n  找到 {len(db_files)} 个数据库文件:")
            for db_file in db_files[:5]:
                size = os.path.getsize(db_file)
                print(f"    - {os.path.basename(db_file)} ({size} bytes)")
    else:
        print("[FAIL] 目录不存在")
    
    print()


def check_version_list():
    """检查版本列表"""
    print("=" * 60)
    print("版本列表检查")
    print("=" * 60)
    
    version_list_path = os.path.join('wxManager', 'decrypt', 'version_list.json')
    
    if os.path.exists(version_list_path):
        print(f"[OK] 版本列表存在: {version_list_path}")
        
        try:
            import json
            with open(version_list_path, 'r', encoding='utf-8') as f:
                versions = json.load(f)
            
            # 检查是否包含 4.1.8.29
            if '4.1.8.29' in versions:
                print("[OK] 版本 4.1.8.29 已记录在版本列表中")
            else:
                print("[FAIL] 版本 4.1.8.29 未记录在版本列表中")
                print("  注意: 版本列表主要用于 3.x 版本，4.x 版本使用内存扫描")
        except Exception as e:
            print(f"[FAIL] 读取版本列表失败: {e}")
    else:
        print(f"[FAIL] 版本列表不存在: {version_list_path}")
    
    print()


def check_key_file():
    """检查是否有保存的密钥文件"""
    print("=" * 60)
    print("密钥文件检查")
    print("=" * 60)
    
    key_files = [
        'wechat_key.txt',
        'key.txt',
        'config.json',
    ]
    
    found = False
    for key_file in key_files:
        if os.path.exists(key_file):
            print(f"[OK] 发现密钥文件: {key_file}")
            found = True
            try:
                with open(key_file, 'r') as f:
                    content = f.read().strip()
                if len(content) == 64:
                    print(f"  内容看起来是一个有效的密钥")
                else:
                    print(f"  内容长度 {len(content)}，可能不是密钥")
            except:
                pass
    
    if not found:
        print("未找到密钥文件")
    
    print()


def provide_solutions():
    """提供解决方案"""
    print("=" * 60)
    print("解决方案")
    print("=" * 60)
    
    print("""
根据诊断结果，您可以尝试以下方案：

【方案 A: 使用修复版解密脚本】(推荐)
1. 编辑 1-decrypt-fixed.py
2. 在 MANUAL_KEY_V4 变量中填入已知的 4.1.8.29 密钥
3. 运行: python 1-decrypt-fixed.py
4. 选择模式 2 (手动设置密钥)

【方案 B: 内存扫描获取密钥】
1. 确保微信 4.1.8.29 正在运行且已登录
2. 运行: python fix_db_key_v4.py
3. 脚本会尝试在内存中扫描密钥

【方案 C: 更新密钥扫描规则】
1. 查看 patch_wx_info_v4.py 中的修复建议
2. 手动修改 wxManager/decrypt/wx_info_v4.py
3. 重新运行 1-decrypt.py

【方案 D: 联系开发者】
如果以上方案都无效，请提供以下信息：
- 微信版本: 4.1.8.29
- 运行日志 (如果有)
- 内存扫描结果
""")


def main():
    print("微信 4.1.8.29 数据库密钥问题诊断工具")
    print("=" * 60)
    print()
    
    check_environment()
    check_wechat_running()
    check_wechat_directory()
    check_version_list()
    check_key_file()
    provide_solutions()
    
    print("=" * 60)
    print("诊断完成")
    print("=" * 60)


if __name__ == '__main__':
    main()
