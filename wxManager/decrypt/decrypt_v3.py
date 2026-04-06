# -*- coding: utf-8 -*-#
# -------------------------------------------------------------------------------
# Name:         getwxinfo.py
# Description:
# Author:       xaoyaoo
# Date:         2023/08/21
# 微信数据库采用的加密算法是256位的AES-CBC。数据库的默认的页大小是4096字节即4KB，其中每一个页都是被单独加解密的。
# 加密文件的每一个页都有一个随机的初始化向量，它被保存在每一页的末尾。
# 加密文件的每一页都存有着消息认证码，算法使用的是HMAC-SHA1（安卓数据库使用的是SHA512）。它也被保存在每一页的末尾。
# 每一个数据库文件的开头16字节都保存了一段唯一且随机的盐值，作为HMAC的验证和数据的解密。
# 用来计算HMAC的key与解密的key是不同的，解密用的密钥是主密钥和之前提到的16字节的盐值通过PKCS5_PBKF2_HMAC1密钥扩展算法迭代64000次计算得到的。而计算HMAC的密钥是刚提到的解密密钥和16字节盐值异或0x3a的值通过PKCS5_PBKF2_HMAC1密钥扩展算法迭代2次计算得到的。
# 为了保证数据部分长度是16字节即AES块大小的整倍数，每一页的末尾将填充一段空字节，使得保留字段的长度为48字节。
# 综上，加密文件结构为第一页4KB数据前16字节为盐值，紧接着4032字节数据，再加上16字节IV和20字节HMAC以及12字节空字节；而后的页均是4048字节长度的加密数据段和48字节的保留段。
# -------------------------------------------------------------------------------
import argparse
import hmac
import hashlib
import os
import traceback
from concurrent.futures import ProcessPoolExecutor
from typing import Union, List
from Crypto.Cipher import AES

from wxManager.log import logger

SQLITE_FILE_HEADER = "SQLite format 3\x00"  # SQLite文件头

KEY_SIZE = 32
DEFAULT_PAGESIZE = 4096
DEFAULT_ITER = 64000


# 通过密钥解密数据库
def decrypt_db_file_v3(key: str, db_path, out_path):
    """
    通过密钥解密数据库
    :param key: 密钥 64位16进制字符串
    :param db_path:  待解密的数据库路径(必须是文件)
    :param out_path:  解密后的数据库输出路径(必须是文件)
    :return:
    """
    if not os.path.exists(db_path) or not os.path.isfile(db_path):
        return False, f"[-] db_path:'{db_path}' File not found!"
    if not os.path.exists(os.path.dirname(out_path)):
        return False, f"[-] out_path:'{out_path}' File not found!"

    if len(key) != 64:
        return False, f"[-] key:'{key}' Len Error!"

    password = bytes.fromhex(key.strip())
    try:
        with open(db_path, "rb") as file:
            blist = file.read()
    except:
        logger.error(traceback.format_exc())
        logger.info(db_path + '->' + out_path)
        return False, 'error'
    salt = blist[:16]
    byteKey = hashlib.pbkdf2_hmac("sha1", password, salt, DEFAULT_ITER, KEY_SIZE)
    first = blist[16:DEFAULT_PAGESIZE]
    if len(salt) != 16:
        return False, f"[-] db_path:'{db_path}' File Error!"

    mac_salt = bytes([(salt[i] ^ 58) for i in range(16)])
    mac_key = hashlib.pbkdf2_hmac("sha1", byteKey, mac_salt, 2, KEY_SIZE)
    hash_mac = hmac.new(mac_key, first[:-32], hashlib.sha1)
    hash_mac.update(b'\x01\x00\x00\x00')

    if hash_mac.digest() != first[-32:-12]:
        return False, f"[-] Key Error! (db_path:'{db_path}' )"

    newblist = [blist[i:i + DEFAULT_PAGESIZE] for i in range(DEFAULT_PAGESIZE, len(blist), DEFAULT_PAGESIZE)]

    with open(out_path, "wb") as deFile:
        deFile.write(SQLITE_FILE_HEADER.encode())
        t = AES.new(byteKey, AES.MODE_CBC, first[-48:-32])
        decrypted = t.decrypt(first[:-48])
        deFile.write(decrypted)
        deFile.write(first[-48:])

        for i in newblist:
            t = AES.new(byteKey, AES.MODE_CBC, i[-48:-32])
            decrypted = t.decrypt(i[:-48])
            deFile.write(decrypted)
            deFile.write(i[-48:])
    return True, [db_path, out_path, key]


def decode_wrapper(tasks):
    """用于包装解码函数的顶层定义"""
    return decrypt_db_file_v3(*tasks)


def decrypt_db_files(key, src_dir: str, dest_dir: str):
    """
    批量解密微信 V3 版本的加密数据库文件

    该函数遍历源目录下所有的 .db 文件，并使用多进程并行解密。
    解密后的文件会保持原有的子目录结构。

    微信数据库加密原理（V3版本）：
        - 采用 256 位 AES-CBC 加密算法
        - 数据库默认页大小为 4096 字节（4KB），每一页单独加解密
        - 每个页面末尾保存 16 字节的初始化向量(IV)和 20 字节的 HMAC-SHA1 消息认证码
        - 文件开头 16 字节为随机盐值，用于密钥派生
        - 解密密钥由主密钥和盐值通过 PKCS5_PBKF2_HMAC1 算法迭代 64000 次计算得到

    Args:
        key (str): 解密密钥，必须为 64 位十六进制字符串（32 字节）。
                   该密钥通常通过 get_wx_info 等函数从微信进程中获取。
                   示例: "a1b2c3d4e5f6..."（共 64 个字符）

        src_dir (str): 源文件夹路径，包含待解密的微信加密数据库文件。
                       函数会递归遍历该目录下所有子文件夹中的 .db 文件。
                       常见路径: 微信数据目录下的 Msg、MicroMsg.db 等数据库文件

        dest_dir (str): 目标文件夹路径，用于存放解密后的数据库文件。
                        如果目录不存在，函数会自动创建。
                        解密后的文件将保持与源目录相同的子目录结构。

    Returns:
        None: 该函数无返回值，解密结果会打印到控制台。

    Raises:
        无显式异常抛出，但解密过程中的错误会通过 decrypt_db_file_v3 函数返回错误信息。

    Example:
        >>> # 解密微信数据库文件
        >>> key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        >>> src = "C:/Users/xxx/Documents/WeChat Files/wxid_xxx/Msg"
        >>> dest = "D:/decrypted_db"
        >>> decrypt_db_files(key, src, dest)

    Note:
        - 使用 ProcessPoolExecutor 进行多进程并行解密，最大并发数为 16
        - 解密单个文件的具体实现参见 decrypt_db_file_v3 函数
        - 仅处理 .db 扩展名的文件，其他文件将被忽略
    """
    # 检查源文件夹是否存在
    if not os.path.exists(src_dir):
        print(f"源文件夹 {src_dir} 不存在")
        return

    # 如果目标文件夹不存在，则创建它
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)

    # 收集所有解密任务
    decrypt_tasks = []
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            # 仅处理 .db 扩展名的数据库文件
            if file.endswith(".db"):
                # 构造源文件的完整路径
                src_file_path = os.path.join(root, file)

                # 计算目标路径，保持原有的子文件夹结构
                relative_path = os.path.relpath(root, src_dir)
                dest_sub_dir = os.path.join(dest_dir, relative_path)
                dest_file_path = os.path.join(dest_sub_dir, file)

                # 确保目标子文件夹存在
                if not os.path.exists(dest_sub_dir):
                    os.makedirs(dest_sub_dir)

                print(dest_file_path)
                # 将解密任务参数打包添加到任务列表
                decrypt_tasks.append((key, src_file_path, dest_file_path))

    # 使用多进程并行执行解密任务，最大并发数为 16
    with ProcessPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(decode_wrapper, decrypt_tasks))
