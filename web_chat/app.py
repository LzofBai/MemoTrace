#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
微信聊天 Web 服务端 - 带详细日志版本
提供 API 接口供前端获取联系人列表和聊天记录
"""

import os
import sys
import base64
import io
import logging
import traceback
import json
from pathlib import Path
from datetime import datetime

# ==================== 日志配置 ====================
LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        # 文件日志 - 记录所有详细信息
        logging.FileHandler(LOG_DIR / f'app_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        # 控制台日志 - 记录重要信息
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

logger.info("="*60)
logger.info("MemoTrace Web Chat 服务启动")
logger.info("="*60)

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
logger.info(f"项目根目录: {project_root}")

try:
    from flask import Flask, jsonify, request, send_from_directory, send_file, Response
    from flask_cors import CORS
    from wxManager import DatabaseConnection
    from wxManager.decrypt.decrypt_dat import decode_dat, is_v4_image, get_aes_key
    from wxManager import Me
    logger.info("✅ 所有模块导入成功")
except Exception as e:
    logger.error(f"❌ 模块导入失败: {e}")
    logger.error(traceback.format_exc())
    raise

# 获取当前文件所在目录
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / 'static'
CACHE_DIR = BASE_DIR / 'cache'
CACHE_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path='/static')
CORS(app)  # 允许跨域请求

# 注册导出蓝图
try:
    from export_api import export_bp
    app.register_blueprint(export_bp)
    logger.info("[INIT] 导出API模块加载成功")
except Exception as e:
    logger.error(f"[INIT] 导出API模块加载失败: {e}")

# ==================== 配置 ====================
# 请根据实际情况修改以下配置
DB_DIR = r'J:\Github\MemoTrace_test\wxid_5e3hd0zrse6w22\Msg'  # 解密后的数据库路径
DB_VERSION = 3  # 数据库版本: 3 或 4

logger.info(f"数据库配置: DB_DIR={DB_DIR}, DB_VERSION={DB_VERSION}")

# 全局数据库连接
database = None
xor_key = 0  # 用于解密图片的异或密钥


def init_database():
    """初始化数据库连接"""
    global database, xor_key
    
    logger.info("[DB] 开始初始化数据库连接...")
    
    if database is not None:
        logger.debug("[DB] 数据库已初始化，返回缓存实例")
        return database
    
    try:
        logger.info(f"[DB] 创建数据库连接: path={DB_DIR}, version={DB_VERSION}")
        conn = DatabaseConnection(DB_DIR, DB_VERSION)
        database = conn.get_interface()
        
        # 尝试获取图片解密密钥
        try:
            xor_key = Me().xor_key if hasattr(Me(), 'xor_key') else 0
            logger.info(f"[DB] 图片解密密钥: {xor_key}")
        except Exception as e:
            logger.warning(f"[DB] 无法获取图片解密密钥: {e}")
        
        # 测试数据库连接
        test_contacts = database.get_contacts()
        logger.info(f"[DB] ✅ 数据库连接成功! 共 {len(test_contacts)} 个联系人")
        
        return database
    except Exception as e:
        logger.error(f"[DB] ❌ 数据库连接失败: {e}")
        logger.error(traceback.format_exc())
        raise


# ==================== 辅助函数 ====================

def log_request(endpoint, params=None):
    """记录请求日志"""
    logger.info(f"[API] {endpoint} | 参数: {params or {}}")


def log_response(endpoint, data_summary):
    """记录响应日志"""
    logger.info(f"[API] {endpoint} | 返回: {data_summary}")


def get_avatar_data(wxid):
    """获取头像二进制数据"""
    logger.debug(f"[AVATAR] 获取头像: wxid={wxid}")
    
    db = init_database()
    try:
        avatar_bytes = db.get_avatar_buffer(wxid)
        if avatar_bytes:
            logger.debug(f"[AVATAR] ✅ 获取成功: {len(avatar_bytes)} bytes")
        else:
            logger.debug(f"[AVATAR] ⚠️ 无头像数据")
        return avatar_bytes
    except Exception as e:
        logger.error(f"[AVATAR] ❌ 获取失败: {e}")
        return None


def decrypt_image(image_path):
    """
    解密微信图片
    返回: (image_bytes, mime_type) 或 (None, None)
    """
    logger.info(f"[IMAGE] 开始解密图片: {image_path}")
    
    if not image_path:
        logger.warning("[IMAGE] ❌ 图片路径为空")
        return None, None
    
    if not os.path.exists(image_path):
        logger.warning(f"[IMAGE] ❌ 图片不存在: {image_path}")
        return None, None
    
    file_size = os.path.getsize(image_path)
    logger.info(f"[IMAGE] 文件大小: {file_size} bytes")
    
    # 如果不是 .dat 文件，直接读取
    if not image_path.endswith('.dat'):
        logger.info("[IMAGE] 直接读取非dat文件")
        try:
            with open(image_path, 'rb') as f:
                data = f.read()
            logger.info(f"[IMAGE] ✅ 读取成功: {len(data)} bytes")
            return data, 'image/jpeg'
        except Exception as e:
            logger.error(f"[IMAGE] ❌ 读取失败: {e}")
            return None, None
    
    # 如果是 .dat 文件，需要解密
    logger.info("[IMAGE] 开始解密dat文件...")
    
    try:
        # 读取文件头判断类型
        with open(image_path, 'rb') as f:
            header = f.read(0x20)
        
        logger.debug(f"[IMAGE] 文件头: {header[:16].hex()}")
        
        # 检查是否是 V4 格式
        if is_v4_image(header):
            logger.info("[IMAGE] 检测到V4格式图片，使用AES解密")
            aes_key = get_aes_key(header)
            if aes_key:
                logger.info(f"[IMAGE] AES密钥: {aes_key.hex()}")
                from Crypto.Cipher import AES
                with open(image_path, 'rb') as f:
                    data = f.read()
                # 跳过头部
                encrypted_data = data[0x10:]
                cipher = AES.new(aes_key, AES.MODE_ECB)
                decrypted = cipher.decrypt(encrypted_data)
                # 移除填充
                decrypted = decrypted.rstrip(b'\x00')
                logger.info(f"[IMAGE] ✅ V4解密成功: {len(decrypted)} bytes")
                return decrypted, 'image/jpeg'
            else:
                logger.error("[IMAGE] ❌ 无法获取AES密钥")
        else:
            logger.info("[IMAGE] 检测到V3格式图片，使用XOR解密")
            
            with open(image_path, 'rb') as f:
                header = f.read(2)
            
            if len(header) < 2:
                logger.error("[IMAGE] ❌ 文件头不足2字节")
                return None, None
            
            # 计算解密码
            pic_head = (0xff, 0xd8, 0x89, 0x50, 0x47, 0x49)
            decode_code = None
            file_type = 'jpg'
            
            for i in range(0, len(pic_head), 2):
                code = header[0] ^ pic_head[i]
                if header[1] ^ code == pic_head[i + 1]:
                    decode_code = code
                    if i == 0:
                        file_type = 'jpg'
                    elif i == 2:
                        file_type = 'png'
                    elif i == 4:
                        file_type = 'gif'
                    break
            
            logger.info(f"[IMAGE] 计算的解密码: {decode_code}, 文件类型: {file_type}")
            
            if decode_code is None and xor_key:
                decode_code = xor_key
                logger.info(f"[IMAGE] 使用全局xor_key: {xor_key}")
            
            if decode_code is None:
                logger.error("[IMAGE] ❌ 无法获取解密码")
                return None, None
            
            # 解密整个文件
            with open(image_path, 'rb') as f:
                data = f.read()
            
            decrypted = bytes([byte ^ decode_code for byte in data])
            mime_type = f'image/{file_type}'
            logger.info(f"[IMAGE] ✅ V3解密成功: {len(decrypted)} bytes, type={mime_type}")
            return decrypted, mime_type
    
    except Exception as e:
        logger.error(f"[IMAGE] ❌ 解密失败: {e}")
        logger.error(traceback.format_exc())
        return None, None


# ==================== API 路由 ====================

@app.route('/')
def index():
    """主页"""
    logger.info("[HTTP] GET / - 访问首页")
    return send_from_directory(str(STATIC_DIR), 'index.html')


@app.route('/api/test')
def test():
    """测试数据库连接"""
    logger.info("[API] GET /api/test - 测试连接")
    
    try:
        db = init_database()
        contacts = db.get_contacts()
        sessions = db.get_session()
        
        result = {
            'code': 0,
            'msg': '连接成功',
            'data': {
                'db_dir': DB_DIR,
                'db_version': DB_VERSION,
                'contacts_count': len(contacts),
                'sessions_count': len(sessions),
                'xor_key': xor_key
            }
        }
        logger.info(f"[API] /api/test 返回: {result['data']}")
        return jsonify(result)
    except Exception as e:
        logger.error(f"[API] /api/test 失败: {e}")
        return jsonify({
            'code': -1,
            'msg': f'连接失败: {str(e)}',
            'data': None
        })


@app.route('/api/avatar/<wxid>')
def get_avatar(wxid):
    """
    获取用户头像
    返回头像图片数据
    """
    logger.info(f"[API] GET /api/avatar/{wxid}")
    
    avatar_bytes = get_avatar_data(wxid)
    
    if avatar_bytes:
        logger.info(f"[API] /api/avatar/{wxid} ✅ 返回头像: {len(avatar_bytes)} bytes")
        return Response(avatar_bytes, mimetype='image/jpeg')
    else:
        logger.warning(f"[API] /api/avatar/{wxid} ⚠️ 无头像，返回默认")
        # 返回默认头像（1x1透明像素）
        default_avatar = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=='
        return Response(base64.b64decode(default_avatar), mimetype='image/png')


@app.route('/api/image')
def get_image():
    """
    获取解密后的图片
    参数: path - 图片路径
    """
    image_path = request.args.get('path', '')
    logger.info(f"[API] GET /api/image?path={image_path}")
    
    if not image_path:
        logger.error("[API] /api/image ❌ 缺少路径参数")
        return jsonify({'code': -1, 'msg': '缺少路径参数'})
    
    # 支持相对路径和绝对路径
    full_path = None
    tried_paths = []
    
    if os.path.isabs(image_path):
        full_path = image_path
        tried_paths.append(full_path)
    else:
        # 尝试多种路径组合
        possible_paths = [
            # 从数据库目录开始
            os.path.join(DB_DIR, image_path),
            # 从上级目录（微信数据目录）
            os.path.join(os.path.dirname(DB_DIR), image_path),
            # 从项目根目录
            os.path.join(BASE_DIR.parent, image_path),
            # 直接使用（可能是相对项目根目录）
            os.path.join(BASE_DIR, image_path),
        ]
        
        for path in possible_paths:
            tried_paths.append(path)
            if os.path.exists(path):
                full_path = path
                logger.info(f"[API] /api/image 找到图片: {path}")
                break
    
    logger.info(f"[API] /api/image 尝试的路径: {tried_paths}")
    
    if not full_path or not os.path.exists(full_path):
        logger.error(f"[API] /api/image ❌ 图片不存在，已尝试路径: {tried_paths}")
        return jsonify({'code': -1, 'msg': f'图片不存在，已尝试: {[p for p in tried_paths]}'})
    
    # 解密图片
    image_bytes, mime_type = decrypt_image(full_path)
    
    if image_bytes:
        logger.info(f"[API] /api/image ✅ 返回图片: {len(image_bytes)} bytes, type={mime_type}")
        return Response(image_bytes, mimetype=mime_type or 'image/jpeg')
    else:
        logger.error("[API] /api/image ❌ 图片解密失败")
        return jsonify({'code': -1, 'msg': '图片解密失败'})


@app.route('/api/contacts')
def get_contacts():
    """
    获取所有联系人列表（好友和群聊）
    参数: page - 页码(从1开始), page_size - 每页数量
    """
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 100))
    
    logger.info(f"[API] GET /api/contacts?page={page}&page_size={page_size}")
    
    db = init_database()
    
    try:
        contacts = db.get_contacts()
        total = len(contacts)
        
        # 分页
        start = (page - 1) * page_size
        end = start + page_size
        contacts_page = contacts[start:end]
        
        logger.info(f"[API] /api/contacts 共 {total} 个联系人, 返回第 {page} 页 ({len(contacts_page)} 个)")
        
        result = []
        for i, contact in enumerate(contacts_page):
            result.append({
                'wxid': contact.wxid,
                'nickname': contact.nickname,
                'remark': contact.remark,
                'alias': contact.alias,
                'avatar_url': f'/api/avatar/{contact.wxid}',
                'is_chatroom': contact.is_chatroom(),
                'is_public': contact.is_public(),
                'type': contact.type,
                'gender': contact.gender,
                'region': contact.region
            })
            if i < 3:  # 只记录前3个的详情
                logger.debug(f"[API] /api/contacts 联系人[{i}]: {contact.nickname} ({contact.wxid})")
        
        return jsonify({
            'code': 0,
            'data': result,
            'total': total,
            'page': page,
            'page_size': page_size,
            'has_more': end < total
        })
    except Exception as e:
        logger.error(f"[API] /api/contacts ❌ 错误: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'code': -1, 'msg': str(e), 'data': []})


@app.route('/api/contacts/search')
def search_contacts():
    """
    搜索联系人
    参数: keyword - 搜索关键词
    """
    keyword = request.args.get('keyword', '').lower()
    logger.info(f"[API] GET /api/contacts/search?keyword={keyword}")
    
    db = init_database()
    
    try:
        contacts = db.get_contacts()
        result = []
        
        for contact in contacts:
            if (keyword in contact.nickname.lower() or 
                keyword in contact.remark.lower() or
                keyword in contact.wxid.lower()):
                result.append({
                    'wxid': contact.wxid,
                    'nickname': contact.nickname,
                    'remark': contact.remark,
                    'avatar_url': f'/api/avatar/{contact.wxid}',
                    'is_chatroom': contact.is_chatroom()
                })
        
        logger.info(f"[API] /api/contacts/search 找到 {len(result)} 个匹配项")
        return jsonify({'code': 0, 'data': result})
    except Exception as e:
        logger.error(f"[API] /api/contacts/search ❌ 错误: {e}")
        return jsonify({'code': -1, 'msg': str(e), 'data': []})


@app.route('/api/chatroom/members')
def get_chatroom_members():
    """
    获取群成员列表
    参数: room_id - 群聊 wxid
    """
    room_id = request.args.get('room_id', '')
    logger.info(f"[API] GET /api/chatroom/members?room_id={room_id}")
    
    if not room_id.endswith('@chatroom'):
        logger.error(f"[API] /api/chatroom/members ❌ 无效的群聊ID: {room_id}")
        return jsonify({'code': -1, 'msg': '不是有效的群聊ID'})
    
    db = init_database()
    
    try:
        members = db.get_chatroom_members(room_id)
        result = []
        
        for wxid, member in members.items():
            result.append({
                'wxid': member.wxid,
                'nickname': member.nickname,
                'remark': member.remark,
                'avatar_url': f'/api/avatar/{member.wxid}'
            })
        
        logger.info(f"[API] /api/chatroom/members 返回 {len(result)} 个成员")
        return jsonify({'code': 0, 'data': result})
    except Exception as e:
        logger.error(f"[API] /api/chatroom/members ❌ 错误: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'code': -1, 'msg': str(e), 'data': []})


@app.route('/api/messages')
def get_messages():
    """
    获取聊天记录
    参数:
        wxid: 聊天对象的 wxid
        page: 页码 (默认 1)
        page_size: 每页数量 (默认 20)
        start_seq: 起始排序序号 (用于分页加载)
    """
    wxid = request.args.get('wxid', '')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    start_seq = request.args.get('start_seq', None)
    
    logger.info(f"[API] GET /api/messages?wxid={wxid}&page={page}&page_size={page_size}&start_seq={start_seq}")
    
    if not wxid:
        logger.error("[API] /api/messages ❌ 缺少 wxid 参数")
        return jsonify({'code': -1, 'msg': '缺少 wxid 参数'})
    
    db = init_database()
    
    try:
        # 使用 get_messages_by_num 实现分页
        if start_seq:
            start_seq = int(start_seq)
        else:
            start_seq = 0xFFFFFFFF  # 从最新消息开始
        
        logger.info(f"[API] /api/messages 调用 get_messages_by_num(wxid={wxid}, start_seq={start_seq}, num={page_size})")
        
        messages, last_seq = db.get_messages_by_num(wxid, start_seq, page_size)
        
        logger.info(f"[API] /api/messages 获取到 {len(messages)} 条消息, last_seq={last_seq}")
        
        result = []
        for i, msg in enumerate(messages):
            msg_data = {
                'local_id': msg.local_id,
                'server_id': str(msg.server_id),
                'sort_seq': msg.sort_seq,
                'timestamp': msg.timestamp,
                'str_time': msg.str_time,
                'type': msg.type,
                'type_name': msg.type_name(),
                'talker_id': msg.talker_id,
                'is_sender': msg.is_sender,
                'sender_id': msg.sender_id,
                'display_name': msg.display_name,
                'content': msg.to_text()
            }
            
            # 根据消息类型添加额外信息
            if hasattr(msg, 'content'):
                msg_data['text'] = msg.content
            
            # 图片消息特殊处理
            if msg.type == 3:
                logger.debug(f"[API] /api/messages 图片消息[{i}]: server_id={msg.server_id}")
                
                if hasattr(msg, 'path'):
                    msg_data['file_path'] = msg.path
                    msg_data['image_url'] = f'/api/image?path={msg.path}'
                    logger.debug(f"[API] /api/messages 图片[{i}] path: {msg.path}")
                else:
                    logger.warning(f"[API] /api/messages 图片[{i}] 无 path 属性")
                    
                if hasattr(msg, 'thumb_path'):
                    msg_data['thumb_path'] = msg.thumb_path
                    msg_data['thumb_url'] = f'/api/image?path={msg.thumb_path}'
                    logger.debug(f"[API] /api/messages 图片[{i}] thumb_path: {msg.thumb_path}")
                else:
                    logger.debug(f"[API] /api/messages 图片[{i}] 无 thumb_path")
            else:
                # 非图片消息也记录path（如果有）
                if hasattr(msg, 'path'):
                    msg_data['file_path'] = msg.path
                if hasattr(msg, 'thumb_path'):
                    msg_data['thumb_path'] = msg.thumb_path
                    
            if hasattr(msg, 'duration'):
                msg_data['duration'] = msg.duration
            if hasattr(msg, 'audio_text'):
                msg_data['audio_text'] = msg.audio_text
            
            result.append(msg_data)
            
            if i < 3:  # 只记录前3条消息的详情
                logger.debug(f"[API] /api/messages 消息[{i}]: type={msg.type}, sender={msg.display_name}, is_sender={msg.is_sender}, has_path={hasattr(msg, 'path')}")
        
        has_more = len(result) >= page_size
        logger.info(f"[API] /api/messages ✅ 返回 {len(result)} 条消息, has_more={has_more}")
        
        return jsonify({
            'code': 0,
            'data': result,
            'last_seq': last_seq,
            'has_more': has_more
        })
    except Exception as e:
        logger.error(f"[API] /api/messages ❌ 错误: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'code': -1, 'msg': str(e), 'data': []})


@app.route('/api/messages/all')
def get_all_messages():
    """
    获取与某个联系人的全部聊天记录（不分页，适合导出）
    参数: wxid - 聊天对象的 wxid
    """
    wxid = request.args.get('wxid', '')
    logger.info(f"[API] GET /api/messages/all?wxid={wxid}")
    
    if not wxid:
        return jsonify({'code': -1, 'msg': '缺少 wxid 参数'})
    
    db = init_database()
    
    try:
        messages = db.get_messages(wxid)
        
        result = []
        for msg in messages:
            result.append({
                'timestamp': msg.timestamp,
                'str_time': msg.str_time,
                'type': msg.type_name(),
                'is_sender': msg.is_sender,
                'sender_id': msg.sender_id,
                'display_name': msg.display_name,
                'content': msg.to_text()
            })
        
        logger.info(f"[API] /api/messages/all 返回 {len(result)} 条消息")
        return jsonify({'code': 0, 'data': result, 'total': len(result)})
    except Exception as e:
        logger.error(f"[API] /api/messages/all ❌ 错误: {e}")
        return jsonify({'code': -1, 'msg': str(e), 'data': []})


@app.route('/api/session')
def get_session():
    """
    获取最近会话列表（类似微信首页的聊天列表）
    参数: page, page_size 支持分页
    """
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))
    
    logger.info(f"[API] GET /api/session?page={page}&page_size={page_size}")
    
    db = init_database()
    
    try:
        raw_sessions = db.get_session()
        total = len(raw_sessions)
        
        # 分页
        start = (page - 1) * page_size
        end = start + page_size
        sessions_page = raw_sessions[start:end]
        
        logger.info(f"[API] /api/session 共 {total} 个会话, 返回第 {page} 页")
        
        result = []
        for session in sessions_page:
            # V3: strUsrName(0), nOrder(1), nUnreadCount(2), strNickName(3), nIsSend(4), strContent(5), nMsgType(6), nTime(7), strTime(8)
            # V4: username(0), type(1), unread_count(2), ..., last_timestamp(4), summary(5), ..., strTime(8), ...
            
            username = session[0]
            if not username:
                continue
            
            # 获取联系人信息
            nickname = ''
            remark = ''
            try:
                contact = db.get_contact_by_username(username)
                if contact:
                    nickname = contact.nickname
                    remark = contact.remark
            except:
                pass
            
            # 根据字段数量判断版本
            if len(session) == 9:  # V3
                if not nickname:
                    nickname = session[3] or username
                last_message = session[5] or ''
                last_time = session[7] or 0
                unread_count = session[2] or 0
            else:  # V4
                if not nickname:
                    nickname = username
                last_message = session[5] or ''
                last_time = session[4] or 0
                unread_count = session[2] or 0
            
            result.append({
                'wxid': username,
                'nickname': nickname,
                'remark': remark,
                'last_message': last_message,
                'last_time': last_time,
                'unread_count': unread_count,
                'is_chatroom': username.endswith('@chatroom'),
                'avatar_url': f'/api/avatar/{username}'
            })
        
        logger.info(f"[API] /api/session ✅ 返回 {len(result)} 个会话")
        return jsonify({
            'code': 0,
            'data': result,
            'total': total,
            'has_more': end < total
        })
    except Exception as e:
        logger.error(f"[API] /api/session ❌ 错误: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'code': -1, 'msg': str(e), 'data': []})


@app.route('/api/stats')
def get_stats():
    """
    获取统计信息
    """
    logger.info("[API] GET /api/stats")
    
    db = init_database()
    
    try:
        contacts = db.get_contacts()
        
        total_contacts = len(contacts)
        chatrooms = sum(1 for c in contacts if c.is_chatroom())
        friends = total_contacts - chatrooms
        
        logger.info(f"[API] /api/stats 统计: 总计={total_contacts}, 好友={friends}, 群聊={chatrooms}")
        
        return jsonify({
            'code': 0,
            'data': {
                'total_contacts': total_contacts,
                'friends': friends,
                'chatrooms': chatrooms
            }
        })
    except Exception as e:
        logger.error(f"[API] /api/stats ❌ 错误: {e}")
        return jsonify({'code': -1, 'msg': str(e)})


# ==================== 启动服务 ====================

if __name__ == '__main__':
    # 初始化数据库
    logger.info("[START] 正在初始化数据库...")
    try:
        init_database()
        logger.info("[START] ✅ 数据库初始化完成")
    except Exception as e:
        logger.error(f"[START] ❌ 数据库初始化失败: {e}")
        sys.exit(1)
    
    # 启动 Flask 服务
    logger.info("=" * 60)
    logger.info("🚀 Flask 服务启动成功!")
    logger.info("📍 访问地址: http://127.0.0.1:5000")
    logger.info("📁 日志目录: " + str(LOG_DIR))
    logger.info("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
