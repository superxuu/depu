import os
from typing import List

class Settings:
    # 项目配置
    PROJECT_NAME = "AI扑克训练"
    VERSION = "1.0.0"
    DEBUG = True
    
    # 邀请码配置
    INVITE_CODES = ["POKER123", "TEXAS888", "GAME456", "1"]
    
    # 游戏配置
    DEFAULT_CHIPS = 1000
    MIN_BET = 5
    MAX_PLAYERS = 6
    
    # 安全配置
    SECRET_KEY = os.getenv("POKER_SECRET_KEY", "dev-secret-key-change-in-production")
    SESSION_TIMEOUT_MINUTES = 60
    
    # 路径配置
    STATIC_DIR = "static"
    TEMPLATES_DIR = "templates"
    DATABASE_PATH = "poker_game.db"
    
    # 服务器配置
    HOST = "0.0.0.0"
    PORT = 8058

# 全局配置实例
settings = Settings()