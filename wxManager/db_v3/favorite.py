import os.path
import sqlite3
import threading
from datetime import date
from typing import Tuple

from wxManager.db_v3.msg import convert_to_timestamp

lock = threading.Lock()
DB = None
cursor = None
db_path = '.'

'''
这段代码是Favorite类的get_items方法，用于查询收藏项目。功能包括：
1. 接收可选的时间范围参数，转换为时间戳
2. 构造SQL查询语句，根据时间范围条件筛选收藏项
3. 使用数据库锁确保线程安全
4. 执行查询并返回结果，异常时返回空列表
   这个 get_items 方法是用于从微信收藏数据库中查询收藏项目。
   它接收一个可选的时间范围参数，然后从 FavItems 表中查询指定时间范围内的收藏记录。
   方法中使用了线程锁来确保数据库操作的线程安全，
   并且包含了异常处理以避免查询出错。查询结果按更新时间排序并返回。
'''
class Favorite:
    def get_items(self, time_range: Tuple[int | float | str | date, int | float | str | date] = None, ):
        if time_range:
            start_time, end_time = convert_to_timestamp(time_range)
        sql = f'''
            select FavLocalID, Type, FromUser, RealChatName, SearchKey, UpdateTime, XmlBuf
            from FavItems
            where StrTalker=?
            {'AND UpdateTime>' + str(start_time) + ' AND UpdateTime<' + str(end_time) if time_range else ''}
            order by UpdateTime
        '''
        res = []
        try:
            lock.acquire(True)
            self.cursor.execute(sql)
            res = self.cursor.fechall()
            self.DB.commit()
        except:
            res = []
        finally:
            lock.release()
        return res if res else []
