import os
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

# 检查是否为Render环境
is_render_env = os.environ.get('RENDER')

# 检查是否配置了PostgreSQL数据库
database_url = os.environ.get('DATABASE_URL')

# 优先使用PostgreSQL，如果不可用则使用SQLite
if is_render_env and database_url:
    # Render环境使用PostgreSQL（使用psycopg替代psycopg2）
    import psycopg
    from psycopg.rows import dict_row
    
    class Database:
        def __init__(self):
            self.database_url = database_url
            self.init_database()
        
        def get_connection(self):
            """获取数据库连接"""
            conn = psycopg.connect(self.database_url)
            return conn
        
        def init_database(self):
            """初始化数据库表"""
            try:
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
                
                # 房间玩家关联表
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS room_players (
                    id SERIAL PRIMARY KEY,
                    room_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    chips INTEGER DEFAULT 1000,
                    position INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_ready BOOLEAN DEFAULT FALSE,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(room_id, user_id)
                )
                ''')
                
                conn.commit()
                cursor.close()
                conn.close()
                print("PostgreSQL数据库初始化成功")
            except Exception as e:
                print(f"PostgreSQL初始化失败: {e}")
                # 如果PostgreSQL失败，回退到SQLite
                import sqlite3
                self._use_sqlite = True
                self.db_path = "poker_game.db"
                self._init_sqlite()
        
        def _init_sqlite(self):
            """初始化SQLite数据库"""
            import sqlite3
            conn = sqlite3.connect(self.db_path)
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
            
            # 房间玩家关联表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS room_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                nickname TEXT NOT NULL,
                chips INTEGER DEFAULT 1000,
                position INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                is_ready BOOLEAN DEFAULT FALSE,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(room_id, user_id)
            )
            ''')
            
            conn.commit()
            conn.close()
            print("SQLite数据库初始化成功")
        
        def execute_query(self, query: str, params: tuple = ()):
            """执行查询并返回结果"""
            if hasattr(self, '_use_sqlite') and self._use_sqlite:
                # 使用SQLite
                import sqlite3
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                result = [dict(row) for row in cursor.fetchall()]
                conn.close()
                return result
            else:
                # 使用PostgreSQL
                conn = self.get_connection()
                cursor = conn.cursor(row_factory=dict_row)
                cursor.execute(query, params)
                result = cursor.fetchall()
                conn.commit()
                cursor.close()
                conn.close()
                return result
        
        def execute_update(self, query: str, params: tuple = ()):
            """执行更新操作"""
            if hasattr(self, '_use_sqlite') and self._use_sqlite:
                # 使用SQLite
                import sqlite3
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                conn.close()
            else:
                # 使用PostgreSQL
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                cursor.close()
                conn.close()

else:
    # 本地环境或Render没有PostgreSQL时使用SQLite
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
            
            # 房间玩家关联表
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS room_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                nickname TEXT NOT NULL,
                chips INTEGER DEFAULT 1000,
                position INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                is_ready BOOLEAN DEFAULT FALSE,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(room_id, user_id)
            )
            ''')
            
            conn.commit()
            conn.close()
            print("SQLite数据库初始化成功")
        
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

# 数据库操作函数（兼容两种数据库语法）
placeholder = "%s" if (is_render_env and database_url) else "?"

def get_user_by_session_token(session_token: str) -> Optional[Dict[str, Any]]:
    """根据session_token获取用户"""
    query = f"SELECT * FROM users WHERE session_token = {placeholder} AND is_active = TRUE"
    result = db.execute_query(query, (session_token,))
    return result[0] if result else None

def get_user_by_nickname(nickname: str) -> Optional[Dict[str, Any]]:
    """根据昵称获取用户"""
    query = f"SELECT * FROM users WHERE nickname = {placeholder} AND is_active = TRUE"
    result = db.execute_query(query, (nickname,))
    return result[0] if result else None

def create_user(nickname: str, invite_code: str, chips: int = 1000) -> Dict[str, Any]:
    """创建新用户"""
    import uuid
    user_id = str(uuid.uuid4())
    session_token = str(uuid.uuid4())
    
    query = f"""
    INSERT INTO users (user_id, nickname, invite_code, session_token, chips)
    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
    """
    db.execute_update(query, (user_id, nickname, invite_code, session_token, chips))
    
    return {
        "user_id": user_id,
        "nickname": nickname,
        "invite_code": invite_code,
        "session_token": session_token,
        "chips": chips
    }

def update_user_session_token(user_id: str, session_token: str):
    """更新用户session_token"""
    query = f"UPDATE users SET session_token = {placeholder}, last_login = CURRENT_TIMESTAMP WHERE user_id = {placeholder}"
    db.execute_update(query, (session_token, user_id))

def create_room(room_name: str, creator_id: str, max_players: int = 6, min_bet: int = 5) -> Dict[str, Any]:
    """创建新房间"""
    import uuid
    room_id = str(uuid.uuid4())
    
    query = f"""
    INSERT INTO rooms (room_id, room_name, creator_id, max_players, min_bet)
    VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
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

def create_fixed_room(room_id: str, room_name: str, creator_id: str, max_players: int = 6, min_bet: int = 10) -> Dict[str, Any]:
    """创建固定ID的房间"""
    db.execute_update(
        "INSERT INTO rooms (room_id, room_name, creator_id, max_players, min_bet) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (room_id) DO UPDATE SET room_name = %s, max_players = %s, min_bet = %s",
        (room_id, room_name, creator_id, max_players, min_bet, room_name, max_players, min_bet)
    )
    return get_room_by_id(room_id)

def get_all_rooms() -> List[Dict[str, Any]]:
    """获取所有房间"""
    query = "SELECT * FROM rooms WHERE status = 'waiting' ORDER BY created_at DESC"
    return db.execute_query(query)

def get_room_by_id(room_id: str) -> Optional[Dict[str, Any]]:
    """根据房间ID获取房间"""
    query = f"SELECT * FROM rooms WHERE room_id = {placeholder}"
    result = db.execute_query(query, (room_id,))
    return result[0] if result else None

def update_room_status(room_id: str, status: str):
    """更新房间状态"""
    query = f"UPDATE rooms SET status = {placeholder} WHERE room_id = {placeholder}"
    db.execute_update(query, (status, room_id))