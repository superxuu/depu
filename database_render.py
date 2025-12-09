import os
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

# 检查是否为Render环境
is_render_env = os.environ.get('RENDER')

if is_render_env:
    # Render环境使用PostgreSQL
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    class Database:
        def __init__(self):
            self.database_url = os.environ.get('DATABASE_URL')
            self.init_database()
        
        def get_connection(self):
            """获取数据库连接"""
            conn = psycopg2.connect(self.database_url)
            return conn
        
        def init_database(self):
            """初始化数据库表"""
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 用户表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                nickname TEXT UNIQUE NOT NULL,
                invite_code TEXT NOT NULL,
                chips INTEGER DEFAULT 1000,
                session_token TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
            ''')
            
            # 房间表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                room_name TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                max_players INTEGER DEFAULT 6,
                min_bet INTEGER DEFAULT 5,
                status TEXT DEFAULT 'waiting',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            conn.commit()
            cursor.close()
            conn.close()
        
        def execute_query(self, query: str, params: tuple = ()):
            """执行查询并返回结果"""
            conn = self.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params)
            result = cursor.fetchall()
            conn.commit()
            cursor.close()
            conn.close()
            return result
        
        def execute_update(self, query: str, params: tuple = ()):
            """执行更新操作"""
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            cursor.close()
            conn.close()
else:
    # 本地环境使用SQLite
    import sqlite3
    
    class Database:
        def __init__(self, db_path: str = "poker_game.db"):
            self.db_path = db_path
            self.init_database()
        
        def get_connection(self):
            """获取数据库连接"""
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        
        def init_database(self):
            """初始化数据库表"""
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 用户表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                nickname TEXT UNIQUE NOT NULL,
                invite_code TEXT NOT NULL,
                chips INTEGER DEFAULT 1000,
                session_token TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
            ''')
            
            # 房间表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                room_id TEXT PRIMARY KEY,
                room_name TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                max_players INTEGER DEFAULT 6,
                min_bet INTEGER DEFAULT 5,
                status TEXT DEFAULT 'waiting',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            conn.commit()
            conn.close()
        
        def execute_query(self, query: str, params: tuple = ()):
            """执行查询并返回结果"""
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return result
        
        def execute_update(self, query: str, params: tuple = ()):
            """执行更新操作"""
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            conn.close()

# 创建全局数据库实例
db = Database()

# 数据库操作函数
def get_user_by_session_token(session_token: str) -> Optional[Dict[str, Any]]:
    """根据session_token获取用户"""
    query = "SELECT * FROM users WHERE session_token = ? AND is_active = TRUE"
    result = db.execute_query(query, (session_token,))
    return result[0] if result else None

def get_user_by_nickname(nickname: str) -> Optional[Dict[str, Any]]:
    """根据昵称获取用户"""
    query = "SELECT * FROM users WHERE nickname = ? AND is_active = TRUE"
    result = db.execute_query(query, (nickname,))
    return result[0] if result else None

def create_user(nickname: str, invite_code: str) -> Dict[str, Any]:
    """创建新用户"""
    import uuid
    user_id = str(uuid.uuid4())
    session_token = str(uuid.uuid4())
    
    query = """
    INSERT INTO users (user_id, nickname, invite_code, session_token, chips)
    VALUES (?, ?, ?, ?, 1000)
    """
    db.execute_update(query, (user_id, nickname, invite_code, session_token))
    
    return {
        "user_id": user_id,
        "nickname": nickname,
        "invite_code": invite_code,
        "session_token": session_token,
        "chips": 1000
    }

def update_user_session_token(user_id: str, session_token: str):
    """更新用户session_token"""
    query = "UPDATE users SET session_token = ?, last_login = CURRENT_TIMESTAMP WHERE user_id = ?"
    db.execute_update(query, (session_token, user_id))

def create_room(room_name: str, creator_id: str, max_players: int = 6, min_bet: int = 5) -> Dict[str, Any]:
    """创建新房间"""
    import uuid
    room_id = str(uuid.uuid4())
    
    query = """
    INSERT INTO rooms (room_id, room_name, creator_id, max_players, min_bet)
    VALUES (?, ?, ?, ?, ?)
    """
    db.execute_update(query, (room_id, room_name, creator_id, max_players, min_bet))
    
    return {
        "room_id": room_id,
        "room_name": room_name,
        "creator_id": creator_id,
        "max_players": max_players,
        "min_bet": min_bet,
        "status": "waiting"
    }

def create_fixed_room():
    """创建固定房间"""
    return create_room("快速游戏", "system", 6, 5)

def get_all_rooms() -> List[Dict[str, Any]]:
    """获取所有房间"""
    query = "SELECT * FROM rooms WHERE status = 'waiting' ORDER BY created_at DESC"
    return db.execute_query(query)

def get_room_by_id(room_id: str) -> Optional[Dict[str, Any]]:
    """根据房间ID获取房间"""
    query = "SELECT * FROM rooms WHERE room_id = ?"
    result = db.execute_query(query, (room_id,))
    return result[0] if result else None

def update_room_status(room_id: str, status: str):
    """更新房间状态"""
    query = "UPDATE rooms SET status = ? WHERE room_id = ?"
    db.execute_update(query, (status, room_id))