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
    from wxManager import Me
    logger.info("✅ 核心模块导入成功")
except Exception as e:
    logger.error(f"❌ 核心模块导入失败: {e}")
    logger.error(traceback.format_exc())
    raise

# 尝试导入微信解密相关模块（可选，需要 yara-python）
try:
    from wxManager.decrypt.decrypt_dat import decode_dat, is_v4_image, get_aes_key
    from wxManager.decrypt import decrypt_v3, decrypt_v4
    DECRYPT_MODULES_AVAILABLE = True
    logger.info("✅ 微信解密模块导入成功")
except ImportError as e:
    DECRYPT_MODULES_AVAILABLE = False
    decode_dat = None
    is_v4_image = None
    get_aes_key = None
    decrypt_v3 = None
    decrypt_v4 = None
    logger.warning(f"⚠️ 微信解密模块导入失败（可能需要安装 yara-python）: {e}")
    logger.warning("提示: 如需使用微信 V4 自动检测功能，请运行: pip install yara-python")

# 尝试导入微信信息获取模块
try:
    import json
    import os
    from pathlib import Path
    WXMANAGER_DIR = Path(__file__).parent.parent / 'wxManager'
    version_list_path = WXMANAGER_DIR / 'decrypt' / 'version_list.json'
    if version_list_path.exists():
        with open(version_list_path, 'r', encoding='utf-8') as f:
            VERSION_LIST = json.load(f)
    else:
        VERSION_LIST = {}
        logger.warning(f"[INIT] 版本列表文件不存在: {version_list_path}")
    
    from wxManager.decrypt import get_info_v3, get_info_v4
    logger.info("✅ 微信信息获取模块导入成功")
except Exception as e:
    logger.warning(f"⚠️ 微信信息获取模块导入失败: {e}")
    get_info_v3 = None
    get_info_v4 = None
    VERSION_LIST = {}

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

# 配置文件路径
CONFIG_FILE = BASE_DIR / 'config.json'

def load_config():
    """加载配置文件"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f'加载配置文件失败: {e}')
    return {
        'wechat_path': '',
        'db_path': DB_DIR,
        'db_version': DB_VERSION
    }

def save_config(config):
    """保存配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f'保存配置文件失败: {e}')
        return False

# 启动时加载配置
initial_config = load_config()
if initial_config.get('db_path'):
    DB_DIR = initial_config['db_path']
if initial_config.get('db_version'):
    DB_VERSION = initial_config['db_version']

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
        # 不抛出异常，返回 None，让调用者处理
        database = None
        return None


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
        if is_v4_image and is_v4_image(header):
            logger.info("[IMAGE] 检测到V4格式图片，使用AES解密")
            aes_key = get_aes_key(header) if get_aes_key else None
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


@app.route('/api/config', methods=['GET'])
def get_config():
    """获取配置"""
    logger.info("[API] GET /api/config - 获取配置")
    config = load_config()
    return jsonify({
        'code': 0,
        'data': {
            'wechat_path': config.get('wechat_path', ''),
            'db_path': config.get('db_path', DB_DIR),
            'db_version': config.get('db_version', DB_VERSION)
        }
    })


@app.route('/api/config', methods=['POST'])
def update_config():
    """更新配置"""
    global DB_DIR, DB_VERSION, database
    logger.info("[API] POST /api/config - 更新配置")
    
    try:
        config = request.json
        logger.info(f"[API] 收到的配置: {config}")
        
        # 保存配置
        if save_config(config):
            # 更新全局变量
            new_db_path = config.get('db_path', DB_DIR)
            new_db_version = config.get('db_version', DB_VERSION)
            
            # 如果数据库路径或版本变化，需要重置数据库连接
            if new_db_path != DB_DIR or new_db_version != DB_VERSION:
                DB_DIR = new_db_path
                DB_VERSION = new_db_version
                database = None  # 重置数据库连接，下次使用时重新初始化
                logger.info(f"[API] 数据库配置已更新: DB_DIR={DB_DIR}, DB_VERSION={DB_VERSION}")
            
            return jsonify({
                'code': 0,
                'msg': '配置已保存'
            })
        else:
            return jsonify({
                'code': -1,
                'msg': '保存配置失败'
            })
    except Exception as e:
        logger.error(f"[API] ❌ 更新配置失败: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'code': -1,
            'msg': f'更新配置失败: {str(e)}'
        })


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


@app.route('/api/decrypt', methods=['POST'])
def decrypt_wechat_db():
    """
    解密微信数据库
    参数:
        key: 解密密钥
        wx_dir: 微信数据目录
        output_dir: 输出目录
        version: 版本 (3 或 4)
    """
    logger.info("[API] POST /api/decrypt - 解密数据库")
    
    try:
        data = request.json
        key = data.get('key', '')
        wx_dir = data.get('wx_dir', '')
        output_dir = data.get('output_dir', '')
        version = int(data.get('version', 3))
        
        if not key or not wx_dir or not output_dir:
            return jsonify({
                'code': -1,
                'msg': '缺少必要参数: key, wx_dir, output_dir'
            })
        
        if not os.path.exists(wx_dir):
            return jsonify({
                'code': -1,
                'msg': f'微信目录不存在: {wx_dir}'
            })
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"[API] 开始解密: version={version}, wx_dir={wx_dir}, output_dir={output_dir}")
        
        # 根据版本选择解密函数
        if version == 4:
            from wxManager.decrypt.decrypt_dat import get_decode_code_v4
            decrypt_v4.decrypt_db_files(key, src_dir=wx_dir, dest_dir=output_dir)
            db_subdir = 'db_storage'
        else:
            decrypt_v3.decrypt_db_files(key, src_dir=wx_dir, dest_dir=output_dir)
            db_subdir = 'Msg'
        
        # 检查解密结果
        decrypted_db_path = os.path.join(output_dir, db_subdir)
        if os.path.exists(decrypted_db_path):
            # 保存配置
            save_config({
                'wechat_path': wx_dir,
                'db_path': decrypted_db_path,
                'db_version': version
            })
            
            # 重置数据库连接
            global DB_DIR, DB_VERSION, database
            DB_DIR = decrypted_db_path
            DB_VERSION = version
            database = None
            
            logger.info(f"[API] 解密成功: {decrypted_db_path}")
            return jsonify({
                'code': 0,
                'msg': '解密成功',
                'data': {
                    'db_path': decrypted_db_path,
                    'version': version
                }
            })
        else:
            return jsonify({
                'code': -1,
                'msg': '解密失败，未找到输出文件'
            })
            
    except Exception as e:
        logger.error(f"[API] 解密失败: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'code': -1,
            'msg': f'解密失败: {str(e)}'
        })


@app.route('/api/db/check')
def check_database():
    """检查数据库是否存在且有效"""
    logger.info("[API] GET /api/db/check - 检查数据库")
    
    try:
        # 尝试初始化数据库
        db = init_database()
        
        # 如果数据库初始化失败，返回不存在
        if db is None:
            logger.warning(f"[API] /api/db/check 数据库未初始化")
            return jsonify({
                'code': -1,
                'msg': '数据库未初始化',
                'data': {
                    'exists': False,
                    'db_dir': DB_DIR
                }
            })
        
        contacts = db.get_contacts()
        
        return jsonify({
            'code': 0,
            'msg': '数据库有效',
            'data': {
                'exists': True,
                'contacts_count': len(contacts),
                'db_dir': DB_DIR,
                'db_version': DB_VERSION
            }
        })
    except Exception as e:
        logger.warning(f"[API] /api/db/check 数据库无效: {e}")
        return jsonify({
            'code': -1,
            'msg': f'数据库无效: {str(e)}',
            'data': {
                'exists': False,
                'db_dir': DB_DIR
            }
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


@app.route('/api/wechat/info')
def get_wechat_info():
    """
    获取登录微信的信息（包括Key）
    需要微信已登录且运行中
    """
    logger.info("[API] GET /api/wechat/info - 获取微信信息")
    
    if get_info_v3 is None and get_info_v4 is None:
        logger.error("[API] /api/wechat/info ❌ 微信信息获取模块未加载")
        return jsonify({
            'code': -1,
            'msg': '微信信息获取模块未加载，请检查依赖',
            'data': None
        })
    
    try:
        result = []
        
        # 尝试获取V3版本微信信息
        if get_info_v3:
            try:
                logger.info("[API] 尝试获取V3微信信息...")
                v3_info = get_info_v3(VERSION_LIST)
                logger.info(f"[API] V3原始返回数量: {len(v3_info) if v3_info else 0}")
                if v3_info:
                    for info in v3_info:
                        logger.info(f"[API] V3处理账号: errcode={info.errcode}, name={info.nick_name}, mobile={info.phone}")
                        if info.errcode == 200:
                            result.append({
                                'version': info.version,
                                'wxid': info.wxid,
                                'name': info.nick_name,
                                'account': info.account_name,
                                'mobile': info.phone,
                                'key': info.key,  # 包含解密密钥
                                'wx_dir': info.wx_dir,
                                'type': 'v3'
                            })
                            logger.info(f"[API] 获取到V3微信信息: name={info.nick_name}, mobile={info.phone}, wxid={info.wxid}")
                        else:
                            logger.warning(f"[API] V3微信信息获取失败: errcode={info.errcode}, errmsg={info.errmsg}")
            except Exception as e:
                logger.warning(f"[API] 获取V3微信信息失败: {e}")
                logger.error(traceback.format_exc())
        
        # 尝试获取V4版本微信信息
        v4_errors = []
        if get_info_v4:
            try:
                logger.info("[API] 尝试获取V4微信信息...")
                v4_info_list = get_info_v4()
                logger.info(f"[API] V4原始返回类型: {type(v4_info_list)}, 数量: {len(v4_info_list) if v4_info_list else 0}")
                if v4_info_list:
                    for info in v4_info_list:
                        # WeChatInfo对象转字典
                        info_dict = {
                            'pid': info.pid,
                            'version': info.version,
                            'account_name': info.account_name,
                            'nick_name': info.nick_name,
                            'phone': info.phone,
                            'wx_dir': info.wx_dir,
                            'key': info.key,
                            'wxid': info.wxid,
                            'errcode': info.errcode,
                            'errmsg': info.errmsg
                        }
                        logger.info(f"[API] V4处理账号: errcode={info_dict['errcode']}, nick_name={info_dict['nick_name']}, phone={info_dict['phone']}")
                        if info_dict['errcode'] == 200:
                            result.append({
                                'version': info_dict['version'],
                                'wxid': info_dict['wxid'],
                                'name': info_dict['nick_name'],
                                'account': info_dict['account_name'],
                                'mobile': info_dict['phone'],
                                'key': info_dict['key'],  # 包含解密密钥
                                'wx_dir': info_dict['wx_dir'],
                                'type': 'v4'
                            })
                            logger.info(f"[API] 获取到V4微信信息: name={info_dict['nick_name']}, mobile={info_dict['phone']}, wxid={info_dict['wxid']}")
                        else:
                            error_msg = f"V4微信信息获取失败: errcode={info_dict['errcode']}, errmsg={info_dict['errmsg']}, pid={info_dict['pid']}, version={info_dict['version']}, wx_dir={info_dict['wx_dir']}"
                            logger.warning(f"[API] {error_msg}")
                            v4_errors.append(error_msg)
            except Exception as e:
                error_msg = f"获取V4微信信息异常: {str(e)}"
                logger.warning(f"[API] {error_msg}")
                logger.error(traceback.format_exc())
                v4_errors.append(error_msg)
        
        if result:
            logger.info(f"[API] /api/wechat/info ✅ 成功获取 {len(result)} 个微信账号信息")
            return jsonify({
                'code': 0,
                'msg': '获取成功',
                'data': result
            })
        else:
            # 收集所有错误信息
            all_errors = v4_errors
            error_detail = '; '.join(all_errors) if all_errors else '未找到登录的微信进程'
            logger.warning(f"[API] /api/wechat/info ⚠️ {error_detail}")
            return jsonify({
                'code': 404,
                'msg': f'未找到登录的微信，请确保微信已登录并运行。详情: {error_detail}',
                'data': [],
                'errors': all_errors
            })
    
    except Exception as e:
        logger.error(f"[API] /api/wechat/info ❌ 错误: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'code': -1,
            'msg': f'获取微信信息失败: {str(e)}',
            'data': None
        })


# ==================== 启动服务 ====================

if __name__ == '__main__':
    # 启动 Flask 服务（不再强制初始化数据库，让用户在登录界面配置）
    logger.info("=" * 60)
    logger.info("🚀 Flask 服务启动成功!")
    logger.info("📍 访问地址: http://127.0.0.1:5000")
    logger.info("📁 日志目录: " + str(LOG_DIR))
    logger.info("💡 请在登录界面配置数据库路径")
    logger.info("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
