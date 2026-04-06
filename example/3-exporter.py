#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
@Time        : 2025/3/11 20:50 
@Author      : SiYuan 
@Email       : 863909694@qq.com 
@File        : wxManager-3-exporter.py
@Description : 
"""

import time
from multiprocessing import freeze_support
import time
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

from exporter.config import FileType
# 仅导入不需要额外依赖的导出器
from exporter import HtmlExporter, TxtExporter, AiTxtExporter, MarkdownExporter, ExcelExporter
# from exporter import DocxExporter  # 需要python-docx库才启用
from wxManager import DatabaseConnection, MessageType


def export():
    st = time.time()

    db_dir = 'J:\Github\MemoTrace_test\wxid_5e3hd0zrse6w22\Msg'  # 解析后的数据库路径，例如：./db_storage
    db_version = 3  # 数据库版本，4 or 3

    wxid = 'wxid_00112233'  # 要导出好友的wxid
    output_dir = './data/'  # 输出文件夹

    conn = DatabaseConnection(db_dir, db_version)  # 创建数据库连接
    database = conn.get_interface()  # 获取数据库接口

    contact = database.get_contact_by_username(wxid)  # 查找某个联系人
    exporter = HtmlExporter(
        database,
        contact,
        output_dir=output_dir,
        type_=FileType.HTML,
        message_types=None,  # 要导出的消息类型，默认全导出
        time_range=['2020-01-01 00:00:00', '2035-03-12 00:00:00'],  # 要导出的日期范围，默认全导出
        group_members=None  # 指定导出群聊里某个或者几个群成员的聊天记录
    )

    exporter.start()
    et = time.time()
    print(f'耗时：{et - st:.2f}s')


def batch_export():
    """
    批量导出HTML
    :return:
    """
    st = time.time()

    db_dir = ''  # 解析后的数据库路径，例如：./db_storage
    db_version = 3  # 数据库版本，4 or 3
    output_dir = './data/'  # 输出文件夹

    conn = DatabaseConnection(db_dir, db_version)  # 创建数据库连接
    database = conn.get_interface()  # 获取数据库接口

    contacts = database.get_contacts()  # 查找某个联系人
    for contact in contacts:
        exporter = HtmlExporter(
            database,
            contact,
            output_dir=output_dir,
            type_=FileType.HTML,
            message_types={MessageType.Text, MessageType.Image, MessageType.LinkMessage},  # 要导出的消息类型，默认全导出
            time_range=['2020-01-01 00:00:00', '2035-03-12 00:00:00'],  # 要导出的日期范围，默认全导出
            group_members=None  # 指定导出群聊里某个或者几个群成员的聊天记录
        )

        exporter.start()
    et = time.time()
    print(f'耗时：{et - st:.2f}s')


def batch_export_by_fmt():
    """
    批量导出多种格式
    :return:
    """
    st = time.time()

    db_dir = ''  # 解析后的数据库路径，例如：./db_storage
    db_version = 3  # 数据库版本，4 or 3

    #wxid来源说明：
    #V3版本来源于MicroMsg.db数据库文件，表名Contact，Remark列:记录微信备注名称，NickName列：记录微信原名称
    #V4版本来源于contact.db数据库文件，表名contact
    wxid = 'wxid_00112233'  # 要导出好友的wxid
    output_dir = './data/'  # 输出文件夹

    conn = DatabaseConnection(db_dir, db_version)  # 创建数据库连接
    database = conn.get_interface()  # 获取数据库接口

    contact = database.get_contact_by_username(wxid)  # 查找某个联系人
    exporters = {
        FileType.HTML: HtmlExporter,
        FileType.TXT: TxtExporter,
        FileType.AI_TXT: AiTxtExporter,
        FileType.MARKDOWN: MarkdownExporter,
        FileType.XLSX: ExcelExporter,
        FileType.DOCX: DocxExporter
    }
    for file_type, exporter in exporters.items():
        execute = exporter(
            database,
            contact,
            output_dir=output_dir,
            type_=file_type,
            message_types=None,  # 要导出的消息类型，默认全导出
            time_range=['2020-01-01 00:00:00', '2035-03-12 00:00:00'],  # 要导出的日期范围，默认全导出
            group_members=None  # 指定导出群聊里某个或者几个群成员的聊天记录
        )

        execute.start()
    et = time.time()
    print(f'耗时：{et - st:.2f}s')


if __name__ == '__main__':
    freeze_support()
    export()
    # batch_export()
    # batch_export_by_fmt()
