#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/1/10 2:34 
@Author      : SiYuan 
@Email       : 863909694@qq.com 
@File        : wxManager-__init__.py.py 
@Description : 
"""
from typing import List

import psutil

from wxManager.decrypt.wx_info_v3 import dump_wechat_info_v3
from wxManager.decrypt.wx_info_v4 import dump_wechat_info_v4
from wxManager.decrypt.common import WeChatInfo


def get_info_v4() -> List[WeChatInfo]:
    result_v4 = []
    # 微信4.x可能的进程名
    weixin_process_names = ['Weixin.exe', 'WeChat.exe']
    # 微信4.x可能的模块名
    weixin_module_names = ['Weixin.dll', 'WeChatWin.dll', 'weixin.dll', 'wechatwin.dll']

    for process in psutil.process_iter(['name', 'exe', 'pid']):
        process_name = process.name()
        if process_name not in weixin_process_names:
            continue

        print(f"[V4] 发现微信进程: {process_name} (PID: {process.pid})")

        wechat_base_address = 0
        try:
            for module in process.memory_maps(grouped=False):
                if module.path:
                    module_path_lower = module.path.lower()
                    for mod_name in weixin_module_names:
                        if mod_name.lower() in module_path_lower:
                            wechat_base_address = int(module.addr, 16)
                            print(f"[V4] 找到模块: {module.path} @ 0x{wechat_base_address:x}")
                            break
                    if wechat_base_address != 0:
                        break
        except Exception as e:
            print(f"[V4] 获取进程内存映射失败: {e}")
            continue

        if wechat_base_address == 0:
            print(f"[V4] 警告: 未找到微信模块基地址，尝试继续...")
            # 不跳过，仍然尝试获取信息

        pid = process.pid
        try:
            wxinfo = dump_wechat_info_v4(pid)
            print(f"[V4] 获取信息结果: errcode={wxinfo.errcode}, wxid={wxinfo.wxid}, key={'有' if wxinfo.key else '无'}")
            result_v4.append(wxinfo)
        except Exception as e:
            print(f"[V4] 获取微信信息失败: {e}")
            import traceback
            traceback.print_exc()

    if not result_v4:
        print(f"[V4] 未找到任何微信4.x进程，已检查的进程名: {weixin_process_names}")

    return result_v4


def get_info_v3(version_list) -> List[WeChatInfo]:
    result = []
    for process in psutil.process_iter(['name', 'exe', 'pid']):
        if process.name() == 'WeChat.exe':
            pid = process.pid
            wxinfo = dump_wechat_info_v3(version_list, pid)
            result.append(
                wxinfo
            )
    return result


if __name__ == "__main__":
    import json

    file_path = r'E:\Project\Python\MemoTrace\resources\data\version_list.json'
    with open(file_path, "r", encoding="utf-8") as f:
        version_list = json.loads(f.read())

    r_4 = get_info_v4()
    r_3 = get_info_v3(version_list)
    for wx_info in r_4+r_3:
        print(wx_info)