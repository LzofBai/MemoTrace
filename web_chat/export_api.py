#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
聊天记录导出 API - 基于 MemoTrace exporter 模块
支持多种导出格式：HTML, TXT, Markdown, Excel, JSON, CSV, DOCX
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Set, Optional

from flask import Blueprint, jsonify, request, Response

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from wxManager import MessageType

# 导入 MemoTrace exporter 模块
EXPORTER_ERROR = None

# 格式到 FileType 的映射
FORMAT_TO_FILETYPE = {
    'html': 2,      # FileType.HTML
    'txt': 5,       # FileType.TXT
    'ai_txt': 17,   # FileType.AI_TXT
    'markdown': 23, # FileType.MARKDOWN
    'xlsx': 12,     # FileType.XLSX
    'json': 6,      # FileType.JSON
    'csv': 0,       # FileType.CSV
    'docx': 1,      # FileType.DOCX
}

try:
    from exporter.config import FileType
    from exporter import HtmlExporter, TxtExporter, MarkdownExporter, ExcelExporter
    from exporter.exporter_ai_txt import AiTxtExporter
    from exporter.exporter_csv import CSVExporter
    from exporter.exporter_json import JsonExporter
    
    try:
        from exporter.exporter_docx import DocxExporter
    except ImportError:
        DocxExporter = None
    
    EXPORTER_AVAILABLE = True
    print(f"[EXPORT] 导出器加载成功")
    
except Exception as e:
    EXPORTER_AVAILABLE = False
    EXPORTER_ERROR = str(e)
    print(f"[EXPORT] 警告: 无法导入 exporter 模块: {e}")
    import traceback
    print(traceback.format_exc())


export_bp = Blueprint('export', __name__, url_prefix='/api/export')


# 导出器类映射
EXPORTER_MAP = {
    'html': HtmlExporter,
    'txt': TxtExporter,
    'ai_txt': AiTxtExporter,
    'markdown': MarkdownExporter,
    'xlsx': ExcelExporter,
    'json': JsonExporter,
    'csv': CSVExporter,
    'docx': DocxExporter,
}

# 格式配置（用于前端显示）
FORMAT_CONFIG = {
    'html': {
        'label': 'HTML 网页',
        'icon': 'fa-html5',
        'color': '#e34c26',
        'ext': 'html',
        'description': '带样式的网页格式，可在浏览器中查看'
    },
    'txt': {
        'label': '纯文本',
        'icon': 'fa-file-alt',
        'color': '#6c757d',
        'ext': 'txt',
        'description': '简洁的文本格式，易于阅读'
    },
    'ai_txt': {
        'label': 'AI 训练文本',
        'icon': 'fa-robot',
        'color': '#10a37f',
        'ext': 'txt',
        'description': '适合用于 AI 模型训练的格式'
    },
    'markdown': {
        'label': 'Markdown',
        'icon': 'fa-markdown',
        'color': '#000000',
        'ext': 'md',
        'description': 'Markdown 格式，支持多种编辑器'
    },
    'xlsx': {
        'label': 'Excel 表格',
        'icon': 'fa-file-excel',
        'color': '#217346',
        'ext': 'xlsx',
        'description': 'Excel 电子表格，适合数据分析'
    },
    'json': {
        'label': 'JSON 数据',
        'icon': 'fa-file-code',
        'color': '#f4a460',
        'ext': 'json',
        'description': 'JSON 格式，适合程序处理'
    },
    'csv': {
        'label': 'CSV 表格',
        'icon': 'fa-file-csv',
        'color': '#2e7d32',
        'ext': 'csv',
        'description': 'CSV 格式，兼容各种表格软件'
    },
    'docx': {
        'label': 'Word 文档',
        'icon': 'fa-file-word',
        'color': '#2b579a',
        'ext': 'docx',
        'description': 'Microsoft Word 文档格式',
        'requires': 'python-docx'
    }
}

# 消息类型配置
MESSAGE_TYPES = {
    'text': {'label': '文本消息', 'types': [MessageType.Text, MessageType.Text2], 'icon': 'fa-comment'},
    'image': {'label': '图片消息', 'types': [MessageType.Image], 'icon': 'fa-image'},
    'audio': {'label': '语音消息', 'types': [MessageType.Audio], 'icon': 'fa-microphone'},
    'video': {'label': '视频消息', 'types': [MessageType.Video], 'icon': 'fa-video'},
    'emoji': {'label': '表情包', 'types': [MessageType.Emoji], 'icon': 'fa-smile'},
    'file': {'label': '文件消息', 'types': [MessageType.File], 'icon': 'fa-file'},
    'location': {'label': '位置分享', 'types': [MessageType.Position], 'icon': 'fa-map-marker-alt'},
    'voip': {'label': '音视频通话', 'types': [MessageType.Voip], 'icon': 'fa-phone'},
    'card': {'label': '名片消息', 'types': [MessageType.BusinessCard, MessageType.OpenIMBCard], 'icon': 'fa-id-card'},
    'link': {'label': '链接/分享', 'types': [MessageType.LinkMessage, MessageType.LinkMessage2, MessageType.LinkMessage4, MessageType.LinkMessage5, MessageType.LinkMessage6, MessageType.Music], 'icon': 'fa-link'},
    'redpacket': {'label': '红包', 'types': [MessageType.RedEnvelope], 'icon': 'fa-envelope'},
    'transfer': {'label': '转账', 'types': [MessageType.Transfer], 'icon': 'fa-money-bill'},
    'quote': {'label': '引用消息', 'types': [MessageType.Quote], 'icon': 'fa-quote-left'},
    'merged': {'label': '合并转发', 'types': [MessageType.MergedMessages], 'icon': 'fa-folder-open'},
    'wechat_video': {'label': '视频号', 'types': [MessageType.WeChatVideo], 'icon': 'fa-play-circle'},
    'applet': {'label': '小程序', 'types': [MessageType.Applet, MessageType.Applet2], 'icon': 'fa-th-large'},
    'fav_note': {'label': '收藏笔记', 'types': [MessageType.FavNote], 'icon': 'fa-bookmark'},
    'pat': {'label': '拍一拍', 'types': [MessageType.Pat], 'icon': 'fa-hand-point-up'},
    'system': {'label': '系统消息', 'types': [MessageType.System], 'icon': 'fa-info-circle'},
    'unknown': {'label': '其他/未知', 'types': [MessageType.Unknown], 'icon': 'fa-question-circle'}
}


def parse_date_range(date_range_type: str, start_date: str = None, end_date: str = None) -> List[str]:
    """解析日期范围为字符串格式 ['YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DD HH:MM:SS']"""
    now = datetime.now()
    
    if date_range_type == 'month':
        start = now - timedelta(days=30)
        end = now
    elif date_range_type == 'quarter':
        start = now - timedelta(days=90)
        end = now
    elif date_range_type == 'custom':
        if start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        else:
            raise ValueError('自定义时间需要提供开始和结束日期')
    else:
        start = datetime(2000, 1, 1)
        end = now
    
    return [
        start.strftime('%Y-%m-%d 00:00:00'),
        end.strftime('%Y-%m-%d 23:59:59')
    ]


def get_message_types(type_list: List[str]) -> Optional[Set[MessageType]]:
    """根据类型名称列表获取消息类型集合"""
    if not type_list:
        return None
    result = set()
    for type_name in type_list:
        if type_name in MESSAGE_TYPES:
            result.update(MESSAGE_TYPES[type_name]['types'])
    return result if result else None


def get_exporter(format: str):
    """获取导出器类"""
    if not EXPORTER_AVAILABLE:
        return None
    exporter_class = EXPORTER_MAP.get(format)
    if exporter_class is None:
        return None
    # 检查 DocxExporter 是否可用
    if format == 'docx' and exporter_class is None:
        return None
    return exporter_class


def is_format_available(format: str) -> bool:
    """检查格式是否可用"""
    if not EXPORTER_AVAILABLE:
        return False
    exporter = EXPORTER_MAP.get(format)
    if exporter is None:
        return False
    if format == 'docx' and exporter is None:
        return False
    return True


@export_bp.route('/config', methods=['GET'])
def get_export_config():
    """获取导出配置选项"""
    formats = []
    for key, config in FORMAT_CONFIG.items():
        formats.append({
            'value': key,
            'label': config['label'],
            'icon': config['icon'],
            'color': config['color'],
            'description': config['description'],
            'available': is_format_available(key),
            'requires': config.get('requires', '')
        })
    
    message_types = [
        {'value': key, 'label': config['label'], 'icon': config['icon']}
        for key, config in MESSAGE_TYPES.items()
    ]
    
    return jsonify({
        'code': 0,
        'data': {
            'formats': formats,
            'message_types': message_types,
            'date_ranges': [
                {'value': 'month', 'label': '近一个月'},
                {'value': 'quarter', 'label': '近三个月'},
                {'value': 'custom', 'label': '自定义时间'},
                {'value': 'all', 'label': '全部'},
            ],
            'exporter_available': EXPORTER_AVAILABLE,
            'exporter_error': EXPORTER_ERROR
        }
    })


@export_bp.route('/members', methods=['GET'])
def get_chatroom_members():
    """获取群成员列表（用于导出时选择）"""
    wxid = request.args.get('wxid', '')
    if not wxid:
        return jsonify({'code': -1, 'msg': '缺少 wxid 参数'})
    
    from app import init_database
    db = init_database()
    
    try:
        members = db.get_chatroom_members(wxid)
        result = []
        for member_id, member in members.items():
            result.append({
                'wxid': member.wxid,
                'nickname': member.nickname,
                'remark': member.remark,
                'display_name': member.remark or member.nickname or member.wxid
            })
        return jsonify({'code': 0, 'data': result})
    except Exception as e:
        return jsonify({'code': -1, 'msg': str(e)})


@export_bp.route('/file', methods=['POST'])
def export_file():
    """
    导出聊天记录到文件
    
    请求参数:
    {
        "wxid": "聊天对象ID",
        "contact_name": "聊天对象名称",
        "format": "html|txt|markdown|xlsx|json|csv|docx|ai_txt",
        "date_range": "month|quarter|custom|all",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "sender_ids": ["wxid1", "wxid2"],
        "message_types": ["text", "image", "video"]
    }
    """
    if not EXPORTER_AVAILABLE:
        return jsonify({'code': -1, 'msg': f'导出模块不可用: {EXPORTER_ERROR}'})
    
    data = request.get_json()
    if not data or 'wxid' not in data:
        return jsonify({'code': -1, 'msg': '缺少必要参数'})
    
    wxid = data.get('wxid')
    contact_name = data.get('contact_name', '未知')
    export_format = data.get('format', 'html')
    date_range_type = data.get('date_range', 'all')
    
    print(f"[EXPORT] 导出请求: format={export_format}, wxid={wxid}")
    
    # 验证格式
    if export_format not in FORMAT_CONFIG:
        return jsonify({'code': -1, 'msg': f'不支持的导出格式: {export_format}'})
    
    exporter_class = get_exporter(export_format)
    if not exporter_class:
        requires = FORMAT_CONFIG[export_format].get('requires', '缺少依赖')
        return jsonify({'code': -1, 'msg': f'该格式不可用: {requires}'})
    
    try:
        # 解析参数
        time_range = parse_date_range(
            date_range_type,
            data.get('start_date'),
            data.get('end_date')
        )
        message_types = get_message_types(data.get('message_types', []))
        sender_ids = set(data.get('sender_ids')) if data.get('sender_ids') else None
        
        # 获取数据库和联系人
        from app import init_database
        db = init_database()
        contact = db.get_contact_by_username(wxid)
        if not contact:
            return jsonify({'code': -1, 'msg': '找不到联系人信息'})
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 创建并执行导出器
            file_type = FORMAT_TO_FILETYPE[export_format]
            exporter = exporter_class(
                database=db,
                contact=contact,
                output_dir=temp_dir,
                type_=file_type,
                message_types=message_types,
                time_range=time_range,
                group_members=sender_ids
            )
            
            print(f"[EXPORT] 开始导出: {exporter_class.__name__}")
            exporter.start()
            print(f"[EXPORT] 导出完成")
            
            # 查找生成的文件
            # 导出器生成的文件路径: {temp_dir}/聊天记录/{remark}({wxid})/{remark}.{ext}
            ext = FORMAT_CONFIG[export_format]['ext']
            output_files = list(Path(temp_dir).rglob(f'*.{ext}'))
            
            if not output_files:
                # 如果没找到指定扩展名的文件，查找任何文件
                output_files = [f for f in Path(temp_dir).rglob('*') if f.is_file()]
            
            if not output_files:
                return jsonify({'code': -1, 'msg': '导出失败：未生成文件'})
            
            output_file = output_files[0]
            print(f"[EXPORT] 找到文件: {output_file}")
            
            # 读取文件内容
            with open(output_file, 'rb') as f:
                file_data = f.read()
            
            # 生成下载文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = "".join(c for c in contact_name if c.isalnum() or c in (' ', '-', '_')).strip()
            download_name = f"{safe_name}_{export_format.upper()}_{timestamp}.{ext}"
            
            # MIME 类型映射
            mime_types = {
                'html': 'text/html; charset=utf-8',
                'txt': 'text/plain; charset=utf-8',
                'md': 'text/markdown; charset=utf-8',
                'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'json': 'application/json; charset=utf-8',
                'csv': 'text/csv; charset=utf-8-sig',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            }
            mime_type = mime_types.get(ext, 'application/octet-stream')
            
            print(f"[EXPORT] 返回文件: {download_name}, size={len(file_data)} bytes")
            
            return Response(
                file_data,
                mimetype=mime_type,
                headers={
                    'Content-Disposition': f'attachment; filename="{download_name}"',
                    'Content-Length': str(len(file_data))
                }
            )
        
        finally:
            # 清理临时目录
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'code': -1, 'msg': f'导出失败: {str(e)}'})
