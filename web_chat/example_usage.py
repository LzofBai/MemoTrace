#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
MemoTrace Web 聊天界面 - 使用示例
展示如何使用 wxManager 获取数据进行开发
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from wxManager import DatabaseConnection


class WeChatDataAPI:
    """封装微信数据获取 API"""
    
    def __init__(self, db_dir: str, db_version: int = 3):
        """
        初始化数据库连接
        
        Args:
            db_dir: 解密后的数据库目录路径
            db_version: 数据库版本 (3 或 4)
        """
        self.conn = DatabaseConnection(db_dir, db_version)
        self.db = self.conn.get_interface()
        print(f"✅ 数据库连接成功: {db_dir}")
    
    def get_all_contacts(self):
        """获取所有联系人（好友和群聊）"""
        contacts = self.db.get_contacts()
        result = []
        for contact in contacts:
            result.append({
                'wxid': contact.wxid,
                'nickname': contact.nickname,
                'remark': contact.remark,
                'is_chatroom': contact.is_chatroom(),
                'is_public': contact.is_public(),
                'gender': contact.gender,
                'region': contact.region
            })
        return result
    
    def get_friends(self):
        """获取所有好友（不包括群聊和公众号）"""
        contacts = self.get_all_contacts()
        return [c for c in contacts if not c['is_chatroom'] and not c['is_public']]
    
    def get_chatrooms(self):
        """获取所有群聊"""
        contacts = self.get_all_contacts()
        return [c for c in contacts if c['is_chatroom']]
    
    def get_chatroom_members(self, room_id: str):
        """获取群成员列表"""
        if not room_id.endswith('@chatroom'):
            raise ValueError('不是有效的群聊ID')
        
        members = self.db.get_chatroom_members(room_id)
        return [
            {
                'wxid': m.wxid,
                'nickname': m.nickname,
                'remark': m.remark
            }
            for m in members.values()
        ]
    
    def get_messages(self, wxid: str, limit: int = 100):
        """
        获取与某人的聊天记录
        
        Args:
            wxid: 聊天对象 wxid
            limit: 返回消息数量限制 (0 表示全部)
        """
        messages = self.db.get_messages(wxid)
        
        result = []
        for msg in messages[:limit] if limit > 0 else messages:
            msg_data = {
                'timestamp': msg.timestamp,
                'time': msg.str_time,
                'type': msg.type,
                'type_name': msg.type_name(),
                'is_sender': msg.is_sender,
                'sender_id': msg.sender_id,
                'display_name': msg.display_name,
                'content': msg.to_text()
            }
            
            # 文本消息添加 content 字段
            if hasattr(msg, 'content'):
                msg_data['text'] = msg.content
            
            # 文件/图片/视频添加路径
            if hasattr(msg, 'path'):
                msg_data['file_path'] = msg.path
            
            result.append(msg_data)
        
        return result
    
    def get_recent_messages(self, wxid: str, num: int = 20):
        """
        获取最近的 N 条消息（用于分页）
        
        Args:
            wxid: 聊天对象 wxid
            num: 消息数量
        """
        messages, last_seq = self.db.get_messages_by_num(wxid, 0xFFFFFFFF, num)
        
        result = []
        for msg in messages:
            result.append({
                'server_id': str(msg.server_id),
                'sort_seq': msg.sort_seq,
                'timestamp': msg.timestamp,
                'time': msg.str_time,
                'type': msg.type,
                'type_name': msg.type_name(),
                'is_sender': msg.is_sender,
                'sender_id': msg.sender_id,
                'display_name': msg.display_name,
                'content': msg.to_text()
            })
        
        return result, last_seq
    
    def get_sessions(self):
        """获取最近会话列表（类似微信首页）
        
        Returns:
            统一的字典格式列表，包含:
            - username: 聊天对象 wxid
            - nickname: 昵称
            - remark: 备注
            - last_message: 最后一条消息内容
            - last_time: 最后消息时间
            - unread_count: 未读数
        """
        raw_sessions = self.db.get_session()
        result = []
        
        for session in raw_sessions:
            # 根据数据库版本不同，字段顺序和数量不同
            # V3: strUsrName(0), nOrder(1), nUnreadCount(2), strNickName(3), nIsSend(4), strContent(5), nMsgType(6), nTime(7), strTime(8) - 共9个字段
            # V4: username(0), type(1), unread_count(2), unread_first_msg_srv_id(3), last_timestamp(4), summary(5), last_msg_type(6), last_msg_sub_type(7), strTime(8), last_sender_display_name(9), last_msg_sender(10) - 共11个字段
            
            username = session[0]
            if not username:
                continue
            
            # 获取联系人信息（用于获取备注）
            nickname = ''
            remark = ''
            try:
                contact = self.db.get_contact_by_username(username)
                if contact:
                    nickname = contact.nickname
                    remark = contact.remark
            except:
                pass
            
            # 根据字段数量判断版本
            if len(session) == 9:  # V3 版本
                # V3: strNickName 在第3位
                if not nickname:
                    nickname = session[3] or username
                last_message = session[5] or ''  # strContent
                last_time = session[7] or 0  # nTime
                unread_count = session[2] or 0  # nUnreadCount
            else:  # V4 版本 (11个字段)
                if not nickname:
                    nickname = username
                last_message = session[5] or ''  # summary
                last_time = session[4] or 0  # last_timestamp
                unread_count = session[2] or 0  # unread_count
            
            result.append({
                'username': username,
                'nickname': nickname,
                'remark': remark,
                'last_message': last_message,
                'last_time': last_time,
                'unread_count': unread_count,
                'is_chatroom': username.endswith('@chatroom')
            })
        
        return result
    
    def search_messages(self, wxid: str, keyword: str, num: int = 10):
        """搜索聊天记录"""
        return self.db.get_messages_by_keyword(wxid, keyword, num)
    
    def get_stats(self):
        """获取统计信息"""
        contacts = self.get_all_contacts()
        friends = [c for c in contacts if not c['is_chatroom'] and not c['is_public']]
        chatrooms = [c for c in contacts if c['is_chatroom']]
        
        return {
            'total_contacts': len(contacts),
            'friends': len(friends),
            'chatrooms': len(chatrooms),
            'public_accounts': len(contacts) - len(friends) - len(chatrooms)
        }


def demo():
    """使用示例演示"""
    
    # 请修改为您的数据库路径
    DB_DIR = r'J:\Github\MemoTrace_test\wxid_5e3hd0zrse6w22\Msg'
    DB_VERSION = 3
    
    print("=" * 60)
    print("MemoTrace 数据获取示例")
    print("=" * 60)
    
    # 初始化 API
    api = WeChatDataAPI(DB_DIR, DB_VERSION)
    
    # 1. 获取统计信息
    print("\n📊 统计信息:")
    stats = api.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # 2. 获取最近会话
    print("\n💬 最近会话:")
    sessions = api.get_sessions()
    for s in sessions[:5]:
        print(f"   {s.get('remark') or s.get('nickname')}: {s.get('last_message', '')[:30]}...")
    
    # 3. 获取好友列表
    print("\n👥 好友列表 (前5个):")
    friends = api.get_friends()
    for f in friends[:5]:
        print(f"   {f['remark'] or f['nickname']} ({f['wxid']})")
    
    # 4. 获取群聊列表
    print("\n👨‍👩‍👧‍👦 群聊列表 (前5个):")
    groups = api.get_chatrooms()
    for g in groups[:5]:
        print(f"   {g['nickname']}")
    
    # 5. 获取某个好友的聊天记录
    if friends:
        friend = friends[0]
        print(f"\n💌 与 [{friend['remark'] or friend['nickname']}] 的最近消息:")
        messages, _ = api.get_recent_messages(friend['wxid'], 5)
        for msg in messages:
            sender = "我" if msg['is_sender'] else msg['display_name']
            print(f"   [{msg['time']}] {sender}: {msg['content'][:50]}...")
    
    # 6. 获取群成员（如果有群聊）
    if groups:
        group = groups[0]
        print(f"\n👨‍👩‍👧‍👦 群 [{group['nickname']}] 的成员:")
        members = api.get_chatroom_members(group['wxid'])
        for m in members[:5]:
            print(f"   {m['remark'] or m['nickname']}")
        if len(members) > 5:
            print(f"   ... 共 {len(members)} 人")
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)


if __name__ == '__main__':
    demo()
