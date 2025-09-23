import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (creator_id) REFERENCES users (user_id)
        )
        ''')
        
        # 游戏记录表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            game_id TEXT PRIMARY KEY,
            room_id TEXT NOT NULL,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            pot_size INTEGER DEFAULT 0,
            community_cards TEXT,
            winner_id TEXT,
            FOREIGN KEY (room_id) REFERENCES rooms (room_id),
            FOREIGN KEY (winner_id) REFERENCES users (user_id)
        )
        ''')
        
        # 玩家游戏记录表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS player_games (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            position INTEGER,
            hole_cards TEXT,
            final_chips INTEGER,
            final_hand TEXT,
            actions TEXT,
            FOREIGN KEY (game_id) REFERENCES games (game_id),
            FOREIGN KEY (user_id) REFERENCES users (user_id)
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
            FOREIGN KEY (room_id) REFERENCES rooms (room_id),
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            UNIQUE(room_id, user_id)
        )
        ''')
        
        # 添加is_ready字段（如果表已存在）
        try:
            cursor.execute('ALTER TABLE room_players ADD COLUMN is_ready BOOLEAN DEFAULT FALSE')
        except sqlite3.OperationalError:
            # 字段可能已经存在
            pass
        
        conn.commit()
        conn.close()
    
    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """执行查询并返回结果列表"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
    
    def execute_single(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """执行查询并返回单个结果"""
        results = self.execute_query(query, params)
        return results[0] if results else None
    
    def execute_update(self, query: str, params: tuple = ()) -> int:
        """执行更新操作并返回影响的行数"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        affected = cursor.rowcount
        conn.close()
        return affected
    
    def execute_insert(self, query: str, params: tuple = ()) -> int:
        """执行插入操作并返回最后插入的ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id

# 全局数据库实例
db = Database()

def get_user_by_session_token(session_token: str) -> Optional[Dict[str, Any]]:
    """通过session_token获取用户"""
    return db.execute_single(
        "SELECT user_id, nickname, chips, session_token FROM users WHERE session_token = ? AND is_active = TRUE",
        (session_token,)
    )

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """通过ID获取用户"""
    return db.execute_single(
        "SELECT user_id, nickname, chips, session_token FROM users WHERE user_id = ? AND is_active = TRUE",
        (user_id,)
    )

def get_user_by_nickname(nickname: str) -> Optional[Dict[str, Any]]:
    """通过昵称获取用户"""
    return db.execute_single(
        "SELECT user_id, nickname, chips, session_token FROM users WHERE nickname = ? AND is_active = TRUE",
        (nickname,)
    )

def create_user(nickname: str, invite_code: str, chips: int = 1000) -> Dict[str, Any]:
    """创建新用户"""
    import uuid
    user_id = str(uuid.uuid4())
    session_token = str(uuid.uuid4())
    
    db.execute_update(
        "INSERT INTO users (user_id, nickname, invite_code, chips, session_token) VALUES (?, ?, ?, ?, ?)",
        (user_id, nickname, invite_code, chips, session_token)
    )
    
    return {
        "user_id": user_id,
        "nickname": nickname,
        "chips": chips,
        "session_token": session_token
    }

def update_user_session_token(user_id: str, session_token: str) -> bool:
    """更新用户的session_token"""
    affected = db.execute_update(
        "UPDATE users SET session_token = ?, last_login = ? WHERE user_id = ?",
        (session_token, datetime.now(), user_id)
    )
    return affected > 0

def get_all_users() -> List[Dict[str, Any]]:
    """获取所有用户"""
    return db.execute_query(
        "SELECT user_id, nickname, chips, created_at, last_login FROM users WHERE is_active = TRUE ORDER BY created_at DESC"
    )

def delete_user(user_id: str) -> bool:
    """删除用户（软删除）"""
    affected = db.execute_update(
        "UPDATE users SET is_active = FALSE WHERE user_id = ?",
        (user_id,)
    )
    return affected > 0

def update_user_chips(user_id: str, chips: int) -> bool:
    """更新用户筹码"""
    affected = db.execute_update(
        "UPDATE users SET chips = ? WHERE user_id = ?",
        (chips, user_id)
    )
    return affected > 0

def create_room(room_name: str, creator_id: str, max_players: int = 6, min_bet: int = 10) -> Dict[str, Any]:
    """创建新房间"""
    import uuid
    room_id = str(uuid.uuid4())
    
    db.execute_update(
        "INSERT INTO rooms (room_id, room_name, creator_id, max_players, min_bet) VALUES (?, ?, ?, ?, ?)",
        (room_id, room_name, creator_id, max_players, min_bet)
    )
    
    return {
        "room_id": room_id,
        "room_name": room_name,
        "creator_id": creator_id,
        "max_players": max_players,
        "min_bet": min_bet,
        "status": "waiting",
        "created_at": datetime.now().isoformat()
    }

def create_fixed_room(room_id: str, room_name: str, creator_id: str, max_players: int = 6, min_bet: int = 10) -> Dict[str, Any]:
    """创建固定ID的房间"""
    db.execute_update(
        "INSERT OR IGNORE INTO rooms (room_id, room_name, creator_id, max_players, min_bet) VALUES (?, ?, ?, ?, ?)",
        (room_id, room_name, creator_id, max_players, min_bet)
    )
    
    return get_room_by_id(room_id) or {
        "room_id": room_id,
        "room_name": room_name,
        "creator_id": creator_id,
        "max_players": max_players,
        "min_bet": min_bet,
        "status": "waiting",
        "created_at": datetime.now().isoformat()
    }

def get_all_rooms() -> List[Dict[str, Any]]:
    """获取所有房间列表"""
    return db.execute_query(
        "SELECT room_id, room_name, creator_id, max_players, min_bet, status, created_at FROM rooms ORDER BY created_at DESC"
    )

def get_room_by_id(room_id: str) -> Optional[Dict[str, Any]]:
    """通过ID获取房间"""
    return db.execute_single(
        "SELECT room_id, room_name, creator_id, max_players, min_bet, status, created_at FROM rooms WHERE room_id = ?",
        (room_id,)
    )

def update_room_status(room_id: str, status: str) -> bool:
    """更新房间状态"""
    affected = db.execute_update(
        "UPDATE rooms SET status = ? WHERE room_id = ?",
        (status, room_id)
    )
    return affected > 0

def delete_room(room_id: str) -> bool:
    """删除房间"""
    affected = db.execute_update(
        "DELETE FROM rooms WHERE room_id = ?",
        (room_id,)
    )
    return affected > 0