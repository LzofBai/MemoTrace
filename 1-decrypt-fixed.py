#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
修复版的 1-decrypt.py
支持微信 4.1.8.29 版本，允许手动设置已知密钥
"""

import json
import os
from multiprocessing import freeze_support

from wxManager import Me
from wxManager.decrypt import get_info_v4, get_info_v3
from wxManager.decrypt.decrypt_dat import get_decode_code_v4
from wxManager.decrypt import decrypt_v4, decrypt_v3

# ============ 手动配置区域 ============
# 如果自动获取密钥失败，请在这里手动设置

# 微信 4.x 数据库密钥 (64字符十六进制字符串)
# 示例格式: "a1b2c3d4e5f6..." (共64个字符，32字节)
MANUAL_KEY_V4 = ""  # <-- 在这里填入已知的 4.1.8.29 密钥

# 微信 4.x 数据目录
# 示例: r"G:\微信\xwechat_files\wxid_xxx"
MANUAL_WX_DIR_V4 = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"

# 微信信息
MANUAL_WXID = "wxid_5e3hd0zrse6w22"
MANUAL_NICKNAME = "啊伟"
MANUAL_PHONE = "18206740264"

# ============ 配置结束 ============


def dump_v4_manual():
    """
    使用手动配置的密钥解析微信 4.0 数据库
    当自动获取失败时使用
    """
    if not MANUAL_KEY_V4 or len(MANUAL_KEY_V4) != 64:
        print("错误: 请先在脚本中设置 MANUAL_KEY_V4 (64字符十六进制密钥)")
        print(f"当前密钥长度: {len(MANUAL_KEY_V4) if MANUAL_KEY_V4 else 0}")
        return
    
    if not os.path.exists(MANUAL_WX_DIR_V4):
        print(f"错误: 微信目录不存在: {MANUAL_WX_DIR_V4}")
        return
    
    print("=" * 60)
    print("使用手动配置的密钥解析微信 4.x 数据库")
    print("=" * 60)
    print(f"微信目录: {MANUAL_WX_DIR_V4}")
    print(f"密钥: {MANUAL_KEY_V4[:16]}...{MANUAL_KEY_V4[-16:]}")
    print(f"昵称: {MANUAL_NICKNAME}")
    print(f"手机号: {MANUAL_PHONE}")
    print("=" * 60)
    
    # 创建 Me 对象
    me = Me()
    me.wx_dir = MANUAL_WX_DIR_V4
    me.wxid = MANUAL_WXID
    me.name = MANUAL_NICKNAME
    me.phone = MANUAL_PHONE
    
    # 尝试获取图片解密密钥
    try:
        me.xor_key = get_decode_code_v4(MANUAL_WX_DIR_V4)
        print(f"图片异或密钥: 0x{me.xor_key:02x}")
    except Exception as e:
        print(f"获取图片密钥失败: {e}")
        me.xor_key = 0
    
    info_data = me.to_json()
    output_dir = MANUAL_WXID
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 解密数据库
    try:
        decrypt_v4.decrypt_db_files(MANUAL_KEY_V4, src_dir=MANUAL_WX_DIR_V4, dest_dir=output_dir)
        
        # 保存信息文件
        db_storage_dir = os.path.join(output_dir, 'db_storage')
        os.makedirs(db_storage_dir, exist_ok=True)
        
        with open(os.path.join(db_storage_dir, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(info_data, f, ensure_ascii=False, indent=4)
        
        print(f"\n成功! 数据库已解密到: {os.path.abspath(db_storage_dir)}")
        
    except Exception as e:
        print(f"\n解密失败: {e}")
        import traceback
        traceback.print_exc()


def dump_v4_auto():
    """
    自动解析微信 4.0 版本的数据库 (原始方法)
    """
    print("尝试自动获取微信 4.x 信息...")
    r_4 = get_info_v4()
    
    if not r_4:
        print("自动获取失败，请使用手动模式")
        return
    
    for wx_info in r_4:
        print(f"\n获取到微信信息:")
        print(f"  版本: {wx_info.get('version', 'unknown')}")
        print(f"  昵称: {wx_info.get('name', 'unknown')}")
        print(f"  手机号: {wx_info.get('mobile', 'unknown')}")
        print(f"  密钥: {wx_info.get('key', 'not found')}")
        
        if not wx_info.get('key') or wx_info.get('key') == 'None':
            print("错误! 未找到密钥")
            continue
        
        me = Me()
        me.wx_dir = wx_info.get('wx_dir', '')
        me.wxid = wx_info.get('wxid', '')
        me.name = wx_info.get('name', '')
        me.phone = wx_info.get('mobile', '')
        
        try:
            me.xor_key = get_decode_code_v4(wx_info.get('wx_dir', ''))
        except:
            me.xor_key = 0
        
        info_data = me.to_json()
        output_dir = wx_info.get('wxid', 'output')
        key = wx_info.get('key', '')
        wx_dir = wx_info.get('wx_dir', '')
        
        try:
            decrypt_v4.decrypt_db_files(key, src_dir=wx_dir, dest_dir=output_dir)
            
            db_storage_dir = os.path.join(output_dir, 'db_storage')
            os.makedirs(db_storage_dir, exist_ok=True)
            
            with open(os.path.join(db_storage_dir, 'info.json'), 'w', encoding='utf-8') as f:
                json.dump(info_data, f, ensure_ascii=False, indent=4)
            
            print(f'数据库解析成功，保存在: {os.path.abspath(db_storage_dir)}')
            
        except Exception as e:
            print(f"解密失败: {e}")


def dump_v3():
    """
    解析微信 3.x 版本的数据库
    """
    version_list_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'wxManager', 'decrypt', 'version_list.json'
    )
    
    if not os.path.exists(version_list_path):
        print(f"错误: 版本列表文件不存在: {version_list_path}")
        return
    
    with open(version_list_path, "r", encoding="utf-8") as f:
        version_list = json.loads(f.read())
    
    r_3 = get_info_v3(version_list)
    
    for wx_info in r_3:
        print(wx_info)
        me = Me()
        me.wx_dir = wx_info.wx_dir
        me.wxid = wx_info.wxid
        me.name = wx_info.nick_name
        info_data = me.to_json()
        output_dir = wx_info.wxid
        key = wx_info.key
        
        if not key:
            print('错误! 未找到 key，请重启微信后再试')
            continue
        
        wx_dir = wx_info.wx_dir
        decrypt_v3.decrypt_db_files(key, src_dir=wx_dir, dest_dir=output_dir)
        
        msg_dir = os.path.join(output_dir, 'Msg')
        os.makedirs(msg_dir, exist_ok=True)
        
        with open(os.path.join(msg_dir, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(info_data, f, ensure_ascii=False, indent=4)
        
        print(f'数据库解析成功，保存在: {os.path.abspath(msg_dir)}')


if __name__ == '__main__':
    freeze_support()
    
    print("微信数据库解密工具 (修复版)")
    print("=" * 60)
    print("1. 自动获取密钥 (微信 4.x)")
    print("2. 手动设置密钥 (微信 4.x)")
    print("3. 解密微信 3.x")
    print("=" * 60)
    
    choice = input("请选择模式 (1/2/3): ").strip()
    
    if choice == '1':
        dump_v4_auto()
    elif choice == '2':
        dump_v4_manual()
    elif choice == '3':
        dump_v3()
    else:
        print("无效选择")
