#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
手动验证从 Process Hacker 找到的密钥
"""

import os
import sys
import struct
import hmac
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA512

# ============ 配置区域 ============

# 从 Process Hacker 复制的候选密钥（64字符十六进制）
CANDIDATE_KEY = ""

# 微信目录
WX_DIR = r"G:\微信\xwechat_files\wxid_5e3hd0zrse6w22_c8c9"

# 测试用的数据库文件（会自动查找）
TEST_DB_PATH = None  # 如果为 None，会自动查找

# ============ 配置结束 ============


def verify_key_v4(key_bytes, db_path):
    """
    验证微信 4.x 数据库密钥
    使用 PBKDF2-HMAC-SHA512
    """
    # 常量
    IV_SIZE = 16
    HMAC_SHA512_SIZE = 64
    KEY_SIZE = 32
    AES_BLOCK_SIZE = 16
    ROUND_COUNT = 256000
    PAGE_SIZE = 4096
    SALT_SIZE = 16
    
    try:
        with open(db_path, 'rb') as f:
            buf = f.read(PAGE_SIZE)
        
        if len(buf) < PAGE_SIZE:
            print(f"  错误: 文件太小 ({len(buf)} bytes)")
            return False
        
        # 获取 salt
        salt = buf[:SALT_SIZE]
        
        # 检查 salt 是否合理
        if salt == b'\x00' * SALT_SIZE or len(set(salt)) == 1:
            print(f"  错误: Salt 无效")
            return False
        
        # 计算 mac_salt
        mac_salt = bytes(x ^ 0x3a for x in salt)
        
        # 使用 PBKDF2 派生密钥
        new_key = PBKDF2(
            key_bytes, 
            salt, 
            dkLen=KEY_SIZE, 
            count=ROUND_COUNT, 
            hmac_hash_module=SHA512
        )
        
        # 计算 mac_key
        mac_key = PBKDF2(
            new_key, 
            mac_salt, 
            dkLen=KEY_SIZE, 
            count=2, 
            hmac_hash_module=SHA512
        )
        
        # 计算 reserve
        reserve = IV_SIZE + HMAC_SHA512_SIZE
        reserve = ((reserve + AES_BLOCK_SIZE - 1) // AES_BLOCK_SIZE) * AES_BLOCK_SIZE
        
        # 计算 MAC
        start = SALT_SIZE
        end = PAGE_SIZE
        
        mac_data_end = end - reserve + IV_SIZE
        if mac_data_end <= start or mac_data_end > len(buf):
            print(f"  错误: 数据范围无效")
            return False
        
        mac = hmac.new(mac_key, buf[start:mac_data_end], SHA512)
        mac.update(struct.pack('<I', 1))
        hash_mac = mac.digest()
        
        # 获取存储的 MAC
        hash_mac_start_offset = end - reserve + IV_SIZE
        hash_mac_end_offset = hash_mac_start_offset + len(hash_mac)
        
        if hash_mac_end_offset > len(buf):
            print(f"  错误: MAC 偏移超出范围")
            return False
        
        stored_mac = buf[hash_mac_start_offset:hash_mac_end_offset]
        
        # 比较
        is_valid = hash_mac == stored_mac
        
        if is_valid:
            print(f"  [OK] HMAC 验证成功!")
            print(f"  [OK] 计算值: {hash_mac.hex()[:32]}...")
            print(f"  [OK] 存储值: {stored_mac.hex()[:32]}...")
        else:
            print(f"  [FAIL] HMAC 不匹配")
            print(f"  [FAIL] 计算值: {hash_mac.hex()[:32]}...")
            print(f"  [FAIL] 存储值: {stored_mac.hex()[:32]}...")
        
        return is_valid
        
    except Exception as e:
        print(f"  错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def find_db_file(wx_dir):
    """查找用于测试的数据库文件"""
    if not os.path.exists(wx_dir):
        return None
    
    # 优先测试的文件
    priority_files = [
        'microMsg.db',
        'session.db',
        'favorite/favorite_fts.db',
    ]
    
    db_storage = os.path.join(wx_dir, 'db_storage')
    if os.path.exists(db_storage):
        for fname in priority_files:
            fpath = os.path.join(db_storage, fname)
            if os.path.exists(fpath):
                size = os.path.getsize(fpath)
                if size >= 4096:
                    return fpath
        
        # 遍历查找
        for root, dirs, files in os.walk(db_storage):
            for file in files:
                if file.endswith('.db'):
                    fpath = os.path.join(root, file)
                    size = os.path.getsize(fpath)
                    if size >= 4096:
                        return fpath
    
    return None


def analyze_candidate(candidate_hex):
    """分析候选密钥的特征"""
    print(f"\n候选密钥分析:")
    print(f"  长度: {len(candidate_hex)} 字符")
    
    if len(candidate_hex) != 64:
        print(f"  [警告] 密钥长度不是 64 字符，可能不正确")
        return None
    
    try:
        key_bytes = bytes.fromhex(candidate_hex)
        print(f"  字节长度: {len(key_bytes)} bytes")
        
        # 计算熵值（随机性）
        unique_bytes = len(set(key_bytes))
        print(f"  不同字节数: {unique_bytes}/256 (越高越随机)")
        
        if unique_bytes < 20:
            print(f"  [警告] 随机性太低，可能不是密钥")
        elif unique_bytes > 200:
            print(f"  [OK] 随机性很高，符合密钥特征")
        
        # 检查是否全是可打印字符
        printable_count = sum(1 for b in key_bytes if 32 <= b < 127)
        print(f"  可打印字符: {printable_count}/32")
        
        if printable_count > 20:
            print(f"  [警告] 可打印字符太多，可能是字符串而非密钥")
        
        return key_bytes
        
    except ValueError as e:
        print(f"  [错误] 无效的十六进制: {e}")
        return None


def interactive_mode():
    """交互模式"""
    print("=" * 60)
    print("微信数据库密钥验证工具")
    print("=" * 60)
    print(f"微信目录: {WX_DIR}")
    
    # 查找数据库文件
    db_path = TEST_DB_PATH or find_db_file(WX_DIR)
    
    if not db_path:
        print("错误: 未找到数据库文件")
        return
    
    print(f"测试文件: {db_path}")
    print(f"文件大小: {os.path.getsize(db_path)} bytes")
    print("=" * 60)
    
    while True:
        print("\n请输入候选密钥（64字符十六进制，或输入 'quit' 退出）:")
        print("提示: 从 Process Hacker 复制 32 字节数据的十六进制值")
        
        candidate = input("> ").strip()
        
        if candidate.lower() == 'quit':
            break
        
        if not candidate:
            continue
        
        # 移除可能的空格
        candidate = candidate.replace(" ", "").replace("-", "")
        
        # 分析
        key_bytes = analyze_candidate(candidate)
        
        if key_bytes:
            print(f"\n验证密钥: {candidate[:16]}...{candidate[-16:]}")
            is_valid = verify_key_v4(key_bytes, db_path)
            
            if is_valid:
                print("\n" + "=" * 60)
                print("[成功] 找到有效的数据库密钥!")
                print("=" * 60)
                print(f"密钥: {candidate}")
                print("=" * 60)
                
                # 询问是否保存
                save = input("\n是否保存此密钥到 key.txt? (y/n): ").strip().lower()
                if save == 'y':
                    with open('key.txt', 'w') as f:
                        f.write(candidate)
                    print("已保存到 key.txt")
                
                return candidate
            else:
                print("\n[失败] 此密钥无效，请尝试其他候选")


def auto_mode():
    """自动验证 CANDIDATE_KEY"""
    if not CANDIDATE_KEY:
        print("错误: 请在脚本中设置 CANDIDATE_KEY")
        return None
    
    candidate = CANDIDATE_KEY.replace(" ", "").replace("-", "")
    
    print("=" * 60)
    print("自动验证模式")
    print("=" * 60)
    
    db_path = TEST_DB_PATH or find_db_file(WX_DIR)
    if not db_path:
        print("错误: 未找到数据库文件")
        return None
    
    print(f"测试文件: {db_path}")
    
    key_bytes = analyze_candidate(candidate)
    if not key_bytes:
        return None
    
    is_valid = verify_key_v4(key_bytes, db_path)
    
    if is_valid:
        print("\n[成功] 密钥验证通过!")
        print(f"密钥: {candidate}")
        return candidate
    else:
        print("\n[失败] 密钥无效")
        return None


def test_multiple_candidates(candidates_file):
    """批量测试候选密钥"""
    if not os.path.exists(candidates_file):
        print(f"错误: 文件不存在 {candidates_file}")
        return
    
    with open(candidates_file, 'r') as f:
        lines = f.readlines()
    
    db_path = TEST_DB_PATH or find_db_file(WX_DIR)
    if not db_path:
        print("错误: 未找到数据库文件")
        return
    
    print(f"批量测试 {len(lines)} 个候选密钥...")
    
    valid_keys = []
    for i, line in enumerate(lines, 1):
        candidate = line.strip().replace(" ", "").replace("-", "")
        if len(candidate) != 64:
            continue
        
        print(f"\n{i}. 测试: {candidate[:16]}...{candidate[-16:]}")
        
        try:
            key_bytes = bytes.fromhex(candidate)
            if verify_key_v4(key_bytes, db_path):
                valid_keys.append(candidate)
                print("   [VALID]")
            else:
                print("   [INVALID]")
        except:
            print("   [ERROR]")
    
    print(f"\n找到 {len(valid_keys)} 个有效密钥:")
    for key in valid_keys:
        print(f"  {key}")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--auto':
            # 自动模式
            auto_mode()
        elif sys.argv[1] == '--batch':
            # 批量模式
            if len(sys.argv) > 2:
                test_multiple_candidates(sys.argv[2])
            else:
                print("用法: python verify_key_manual.py --batch candidates.txt")
        else:
            print("未知参数")
            print("用法:")
            print("  python verify_key_manual.py          # 交互模式")
            print("  python verify_key_manual.py --auto   # 自动验证 CANDIDATE_KEY")
            print("  python verify_key_manual.py --batch candidates.txt  # 批量测试")
    else:
        # 默认交互模式
        interactive_mode()
