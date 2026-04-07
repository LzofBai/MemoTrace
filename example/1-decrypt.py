#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/3/11 20:27
@Author      : SiYuan
@Email       : 863909694@qq.com
@File        : wxManager-1-decrypt.py
@Description :
"""

import json
import os
import sys
from pathlib import Path

#----------------------------------------------------------------
# 此操作只为能导入wxManager模块，若有其他方法可删除
# 添加项目根目录到Python路径，确保可以导入wxManager模块
current_file_path = Path(__file__).resolve()
project_root = current_file_path.parent.parent  # 回退到MemoTrace目录
sys.path.insert(0, str(project_root))
# 此操作只为能导入wxManager模块，实际使用时请删除或注释掉
#----------------------------------------------------------------


from multiprocessing import freeze_support

from wxManager import Me
from wxManager.decrypt import get_info_v4, get_info_v3
from wxManager.decrypt.decrypt_dat import get_decode_code_v4
from wxManager.decrypt import decrypt_v4, decrypt_v3


def dump_v3():
    """
    解析微信3.x版本的数据库
    """
    # 使用绝对路径来确保version_list.json文件能被找到
    #version_list.json存储不同微信版本对应的内存偏移地址偏移量列表，用于快速定位内存中昵称和电话号码，
    # 注： 昵称/手机号解析失败（用于显示微信用户信息，不影响数据库解密）。
    # 解密成功的关键在于get_key() 函数，它通过扫描 "iphone\0"、"android\0" 等模式来定位密钥。
    version_list_path = os.path.join(project_root, 'wxManager', 'decrypt', 'version_list.json')
    with open(version_list_path, "r", encoding="utf-8") as f:
        version_list = json.loads(f.read())
    r_3 = get_info_v3(version_list)  # 微信3.x
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
            print('error! 未找到key，请重启微信后再试')
            continue
        wx_dir = wx_info.wx_dir
        #解密数据库，此程序的核心功能，核心参数（KEY:数据库加密密钥，src_dir:微信数据目录，dest_dir:导出目录）
        #密匙从已登陆的微信程序中获取，密匙与账号绑定，可考虑一次获取存储，下次启动时读取
        decrypt_v3.decrypt_db_files(key, src_dir=wx_dir, dest_dir=output_dir)
        # 导出的数据库在 output_dir/Msg 文件夹下，后面会用到
        with open(os.path.join(output_dir, 'Msg', 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(info_data, f, ensure_ascii=False, indent=4)
        print(f'数据库解析成功，在{os.path.join(output_dir, "Msg")}路径下')


def dump_v4():
    """
    解析微信4.0版本的数据库
    """
    r_4 = get_info_v4()  # 微信4.0
    for wx_info in r_4:
        print(wx_info)
        # 检查必要的信息是否获取成功
        if not wx_info.wx_dir:
            print('error! 无法获取微信数据目录，请确保微信已登录')
            continue
        if not wx_info.wxid:
            print('error! 无法获取微信ID，请确保微信已登录')
            continue
        me = Me()
        me.wx_dir = wx_info.wx_dir
        me.wxid = wx_info.wxid
        me.name = wx_info.nick_name
        # 尝试获取异或密钥，如果失败则跳过该账号
        try:
            me.xor_key = get_decode_code_v4(wx_info.wx_dir)
        except ValueError as e:
            print(f'error! 获取异或密钥失败: {e}')
            continue
        info_data = me.to_json()
        output_dir = wx_info.wxid  # 数据库输出文件夹
        key = wx_info.key
        if not key:
            print('error! 未找到key，请重启微信后再试')
            continue
        wx_dir = wx_info.wx_dir
        # 解密数据库，此程序的核心功能，核心参数（KEY:数据库加密密钥，src_dir:微信数据目录，dest_dir:导出目录）
        decrypt_v4.decrypt_db_files(key, src_dir=wx_dir, dest_dir=output_dir)
        # 导出的数据库在 output_dir/db_storage 文件夹下，后面会用到
        with open(os.path.join(output_dir, 'db_storage', 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(info_data, f, ensure_ascii=False, indent=4)
        # 修复：打印正确的路径信息，对于v4版本是db_storage而非Msg
        print(f'数据库解析成功，在{os.path.join(output_dir, "db_storage")}路径下')

def test():
    """测试手动指定密钥的解密方式"""
    # 微信4.0数据库密钥（从内存中提取）
    key = r"c9eaed112cbb4dd896a5dd7314186a24598951f2efff4afe812fb7556f4fc4ce"
    # 微信数据目录
    wx_dir = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"
    # 输出目录
    output_dir = r"C:\Users\16267\Desktop\a"
    
    # 创建Me对象并设置信息
    me = Me()
    me.wxid = "wxid_5e3hd0zrse6w22_c8c9"
    me.wx_dir = wx_dir
    me.name = "啊伟"
    
    # 根据 find_xor_key.py 的查找结果，设置图片解密密钥
    # 请将下面的 0x00 替换为你的实际xor_key值
    me.xor_key = 0x13  # ⬅️ 修改这一行：例如 me.xor_key = 0x42
    
    print(f"[INFO] 正在解密...")
    print(f"  - 微信目录: {wx_dir}")
    print(f"  - 输出目录: {output_dir}")
    print(f"  - 图片xor_key: 0x{me.xor_key:02x}")
    
    try:
        decrypt_v4.decrypt_db_files(key, src_dir=wx_dir, dest_dir=output_dir)
        print(f"[SUCCESS] 解密完成，数据已保存到: {output_dir}")
    except Exception as e:
        print(f"[ERROR] 解密失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    freeze_support()  # 使用多进程必须
    # 根据自己的微信版本选择使用对应的函数
    #dump_v3()  # 微信3.x
    dump_v4() # 微信4.0
    # test()