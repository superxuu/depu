#!/usr/bin/env python3
"""
AI扑克训练主入口 - 使用纯sqlite3实现
"""
import os
import sys
import uuid
import time
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import db, get_user_by_session_token, get_user_by_nickname, create_user, update_user_session_token, create_room, create_fixed_room, get_all_rooms, get_room_by_id, update_room_status
from game_logic.game_engine import TexasHoldemGame, GameStage

# WebSocket连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        # 最近心跳时间戳（秒）
        self.last_seen: Dict[str, float] = {}
    
    async def connect(self, user_id: str, websocket: WebSocket):
        self.active_connections[user_id] = websocket
        # 记录连接建立时的心跳时间
        import time
        self.last_seen[user_id] = time.time()
    
    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        # 同步移除心跳记录
        if user_id in getattr(self, "last_seen", {}):
            del self.last_seen[user_id]
    
    async def send_personal_message(self, message: Dict[str, Any], user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(message)
    
    async def broadcast(self, message: Dict[str, Any], exclude_user_id: Optional[str] = None):
        for user_id, connection in self.active_connections.items():
            if user_id != exclude_user_id:
                await connection.send_json(message)

# 全局连接管理器
manager = ConnectionManager()

# 固定房间ID
FIXED_ROOM_ID = "00000000-0000-0000-0000-000000000000"

# 初始化FastAPI应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")

# 设置模板
templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)

# 内存中的游戏状态
active_games: Dict[str, Any] = {}  # room_id -> game instance
connected_players: Dict[str, WebSocket] = {}  # user_id -> websocket

# 观战/等待下一手
spectators: Dict[str, set] = {}
waiting_next_hand: Dict[str, set] = {}

# 超时检查任务
import asyncio
timeout_check_task: Optional[asyncio.Task] = None
cleanup_task: Optional[asyncio.Task] = None

async def check_timeout_loop():
    """定期检查游戏超时的后台任务"""
    while True:
        try:
            await asyncio.sleep(5)  # 每5秒检查一次
            
            for room_id, game in list(active_games.items()):
                # 检查单玩家场景
                if game and hasattr(game, 'single_player_waiting') and game.single_player_waiting:
                    waiting_info = game.single_player_waiting
                    user_id = waiting_info["user_id"]
                    
                    # 检查是否超时（默认等待时间15秒）
                    elapsed = time.time() - waiting_info["start_time"]
                    if elapsed > game.single_player_grace_period:
                        # 超时自动结束游戏
                        print(f"单玩家等待超时，自动结束游戏")
                        game.handle_single_player_decision(user_id, "end")
                        await handle_game_end(room_id, game)
                
                if game and hasattr(game, 'is_action_timeout') and game.is_action_timeout():
                    # 处理超时玩家
                    timed_out_players = game.auto_fold_timeout_players()
                    
                    if timed_out_players:
                        # 广播游戏状态更新
                        await manager.broadcast({
                            "type": "game_state_update",
                            "data": game.get_game_state()
                        })
                        
                        # 发送超时通知
                        for player in timed_out_players:
                            await manager.send_personal_message({
                                "type": "action_timeout",
                                "message": f"玩家 {player.nickname} 操作超时，自动{'过牌' if game.current_bet == 0 else '弃牌'}"
                            }, player.user_id)
                            
        except Exception as e:
            print(f"超时检查出错: {e}")
            await asyncio.sleep(5)  # 出错后等待5秒再继续

async def periodic_cleanup_loop():
    """定期清理离线玩家记录的后台任务"""
    while True:
        try:
            await asyncio.sleep(60)  # 每分钟执行一次清理
            
            # 获取当前时间戳
            current_time = time.time()
            TIMEOUT = 90  # 90秒无活动视为离线
            
            # 使用 list() 拷贝，避免迭代过程中修改字典
            for user_id, ws in list(manager.active_connections.items()):
                probe_failed = False
                try:
                    await ws.send_json({"type": "heartbeat_probe"})
                except Exception:
                    probe_failed = True
                
                last = getattr(manager, "last_seen", {}).get(user_id, 0.0)
                timed_out = (current_time - last) > TIMEOUT
                
                if probe_failed or timed_out:
                    # 清理失效或超时连接
                    manager.disconnect(user_id)
                    
                    # 先查昵称，再删除
                    row = db.execute_query(
                        "SELECT nickname FROM room_players WHERE room_id = ? AND user_id = ?",
                        (FIXED_ROOM_ID, user_id)
                    )
                    nickname = (row[0]["nickname"] if row and "nickname" in row[0] else None) or user_id
                    
                    db.execute_update(
                        "DELETE FROM room_players WHERE room_id = ? AND user_id = ?",
                        (FIXED_ROOM_ID, user_id)
                    )
                    
                    await manager.broadcast({
                        "type": "player_left",
                        "user_id": user_id,
                        "nickname": nickname
                    })
                    print(f"清理离线玩家: {nickname} (ID: {user_id})")
            
            # 刷新准备计数
            await update_ready_count(FIXED_ROOM_ID)
            
        except Exception as e:
            print(f"定期清理出错: {e}")
            await asyncio.sleep(60)  # 出错后等待1分钟再继续

def start_timeout_check():
    """启动超时检查任务"""
    global timeout_check_task
    if timeout_check_task is None:
        timeout_check_task = asyncio.create_task(check_timeout_loop())

def start_periodic_cleanup():
    """启动定期清理任务"""
    global cleanup_task
    if cleanup_task is None:
        cleanup_task = asyncio.create_task(periodic_cleanup_loop())

# 工具函数
def create_session_token() -> str:
    """创建会话令牌"""
    return str(uuid.uuid4())

async def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """获取当前用户 - 支持cookie和Authorization头"""
    # 1. 首先尝试从Authorization头获取
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        session_token = auth_header[7:]  # 去掉"Bearer "前缀
        user = get_user_by_session_token(session_token)
        if user:
            return user
    
    # 2. 尝试从cookie获取
    session_token = request.cookies.get("session_token")
    if session_token:
        user = get_user_by_session_token(session_token)
        if user:
            return user
    
    # 3. 尝试从查询参数获取（用于调试）
    session_token = request.query_params.get("session_token")
    if session_token:
        user = get_user_by_session_token(session_token)
        if user:
            return user
    
    return None

# 路由处理
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """首页"""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "settings": settings
    })

@app.post("/verify-invite")
async def verify_invite_code(request: Request):
    """验证邀请码"""
    form_data = await request.form()
    invite_code = form_data.get("invite_code", "").strip().upper()
    
    if not invite_code:
        raise HTTPException(status_code=400, detail="请输入邀请码")
    
    if invite_code not in settings.INVITE_CODES:
        raise HTTPException(status_code=400, detail="无效的邀请码")
    
    return {"status": "success", "invite_code": invite_code}

@app.post("/create-user")
async def create_user_endpoint(request: Request):
    """创建或获取用户"""
    form_data = await request.form()
    nickname = form_data.get("nickname", "").strip()
    invite_code = form_data.get("invite_code", "").strip().upper()
    
    if not nickname:
        raise HTTPException(status_code=400, detail="请输入昵称")
    
    if not invite_code or invite_code not in settings.INVITE_CODES:
        raise HTTPException(status_code=400, detail="无效的邀请码")
    
    # 检查昵称是否已存在，如果存在则返回现有用户
    existing_user = get_user_by_nickname(nickname)
    if existing_user:
        user = existing_user
    else:
        # 创建新用户
        user = create_user(nickname, invite_code, settings.DEFAULT_CHIPS)
    
    # 将用户添加到固定房间
    db.execute_update(
        "INSERT OR REPLACE INTO room_players (room_id, user_id, nickname, chips) VALUES (?, ?, ?, ?)",
        (FIXED_ROOM_ID, user["user_id"], user["nickname"], user["chips"])
    )
    
    # 设置session_token cookie并重定向到房间页面
    response = RedirectResponse("/room", status_code=303)
    
    # 调试：打印cookie信息
    print(f"DEBUG: 设置cookie - key: session_token, value: {user['session_token']}")
    
    response.set_cookie(
        key="session_token",
        value=user["session_token"],
        httponly=False,  # 暂时关闭httponly以便调试
        max_age=settings.SESSION_TIMEOUT_MINUTES * 60,
        samesite="lax",
        path="/",  # 确保cookie在所有路径下可用
        domain=None  # 明确设置domain为None
    )
    
    # 调试：检查cookie是否设置成功
    cookie_header = response.headers.get('set-cookie')
    print(f"DEBUG: Set-Cookie头: {cookie_header}")
    
    return response

@app.get("/lobby", response_class=HTMLResponse)
async def lobby(request: Request):
    """游戏大厅 - 直接重定向到固定房间"""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    
    # 确保固定房间存在
    room = get_room_by_id(FIXED_ROOM_ID)
    if not room:
        create_fixed_room(
            room_id=FIXED_ROOM_ID,
            room_name="主游戏房间",
            creator_id=user["user_id"],
            min_bet=10,
            max_players=9
        )
    
    # 保留会话令牌的重定向
    response = RedirectResponse("/room", status_code=303)
    response.set_cookie(
        key="session_token",
        value=user["session_token"],
        httponly=True,
        max_age=settings.SESSION_TIMEOUT_MINUTES * 60,
        samesite="lax",
        path="/"  # 确保cookie在整个网站都可访问
    )
    return response

@app.get("/api/user-info")
async def get_user_info(request: Request):
    """获取当前用户信息"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user

@app.get("/api/rooms")
async def get_rooms():
    """获取房间列表 - 只返回固定房间"""
    # 确保固定房间存在
    room = get_room_by_id(FIXED_ROOM_ID)
    if not room:
        # 如果没有用户登录，创建一个默认用户来创建房间
        create_fixed_room(
            room_id=FIXED_ROOM_ID,
            room_name="主游戏房间",
            creator_id="system",
            min_bet=10,
            max_players=9
        )
        room = get_room_by_id(FIXED_ROOM_ID)
    
    return [room] if room else []

@app.get("/api/room/status")
async def get_room_status():
    """获取房间状态（单一房间）"""
    room = get_room_by_id(FIXED_ROOM_ID)
    if not room:
        raise HTTPException(status_code=404, detail="房间不存在")
    
    # 从数据库获取房间中的玩家信息
    players = db.execute_query(
        "SELECT user_id, nickname, chips FROM room_players WHERE room_id = ?",
        (FIXED_ROOM_ID,)
    )
    print(f"从数据库获取的玩家: {players}")
    
    players_list = [
        {
            "user_id": player["user_id"],
            "nickname": player["nickname"],
            "chips": player["chips"],
            "connected": player["user_id"] in manager.active_connections
        }
        for player in players
    ]
    
    # 检查是否有活跃游戏
    game_active = FIXED_ROOM_ID in active_games
    game_state = None
    if game_active:
        game = active_games[FIXED_ROOM_ID]
        game_state = game.get_game_state() if hasattr(game, 'get_game_state') else None
    
    return {
        "room": room,
        "players": players_list,
        "total_players": len(players_list),
        "game_active": game_active,
        "game_state": game_state
    }

@app.get("/api/players")
async def get_players(request: Request):
    """获取所有玩家信息"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    # 从数据库获取固定房间的玩家信息（包含准备状态）
    players = db.execute_query(
        "SELECT user_id, nickname, chips, is_ready FROM room_players WHERE room_id = ?",
        (FIXED_ROOM_ID,)
    )
    print(f"DEBUG: 从数据库获取的玩家: {players}")
    
    players_list = [
        {
            "user_id": player["user_id"],
            "nickname": player["nickname"],
            "chips": player["chips"],
            "is_ready": player.get("is_ready", 0),
            "connected": player["user_id"] in manager.active_connections,
            "is_spectator": player["user_id"] in spectators.get(FIXED_ROOM_ID, set()),
            "waiting_next_hand": player["user_id"] in waiting_next_hand.get(FIXED_ROOM_ID, set())
        }
        for player in players
    ]
    
    print(f"DEBUG: players_list: {players_list}")
    return {
        "players": players_list,
        "total_players": len(players_list)
    }

@app.post("/api/cleanup-stale")
async def cleanup_stale_connections():
    """
    心跳探测并清理失效连接：
    - 尝试向每个连接发送一次探测消息
    - 发送失败或超过阈值未心跳则视为断开：移除 active_connections，删除房间记录，广播 player_left
    - 更新准备人数计数
    """
    room_id = FIXED_ROOM_ID
    cleaned = []
    import time
    now = time.time()
    TIMEOUT = 90  # 超过该秒数未心跳视为僵尸连接
    # 使用 list() 拷贝，避免迭代过程中修改字典
    for user_id, ws in list(manager.active_connections.items()):
        probe_failed = False
        try:
            await ws.send_json({"type": "heartbeat_probe"})
        except Exception:
            probe_failed = True
        last = getattr(manager, "last_seen", {}).get(user_id, 0.0)
        timed_out = (now - last) > TIMEOUT
        if probe_failed or timed_out:
            # 清理失效或超时连接
            manager.disconnect(user_id)
            # 先查昵称，再删除
            row = db.execute_query(
                "SELECT nickname FROM room_players WHERE room_id = ? AND user_id = ?",
                (room_id, user_id)
            )
            nickname = (row[0]["nickname"] if row and "nickname" in row[0] else None) or user_id
            db.execute_update(
                "DELETE FROM room_players WHERE room_id = ? AND user_id = ?",
                (room_id, user_id)
            )
            await manager.broadcast({
                "type": "player_left",
                "user_id": user_id,
                "nickname": nickname
            })
            cleaned.append(user_id)
    # 刷新准备计数
    await update_ready_count(room_id)
    return {"cleaned": cleaned, "count": len(cleaned)}

@app.post("/api/reset-chips")
async def reset_chips(request: Request):
    """
    重置筹码（仅当前固定房间）：
    - 仅在无进行中的手牌时允许
    - scope: 'all'（当前房间全部） | 'selected'（多选玩家）
    - 兼容旧格式：scope=='one' 且提供 user_id 时，等同于 selected 的单个
    请求体：
      { scope: 'all'|'selected'|'one', code: str, user_ids?: [str], user_id?: str }
    返回 chips_reset 广播：
      { type:'chips_reset', scope, default_chips, affected:[{user_id,nickname}] }
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="无效的请求体")

    code = str(payload.get("code", "")).strip()
    if code != getattr(settings, "RESET_CODE", "583079759"):
        raise HTTPException(status_code=403, detail="验证码错误")

    # 不允许在进行中重置
    if FIXED_ROOM_ID in active_games:
        game = active_games[FIXED_ROOM_ID]
        try:
            if hasattr(game, "stage") and game.stage not in (GameStage.ENDED,):
                raise HTTPException(status_code=409, detail="当前有进行中的手牌，无法重置")
        except Exception:
            raise HTTPException(status_code=409, detail="当前有进行中的手牌，无法重置")

    scope = str(payload.get("scope", "all")).lower()
    default_chips = int(getattr(settings, "DEFAULT_CHIPS", 1000))
    affected = []

    # 兼容旧协议 one -> selected
    if scope == "one" and payload.get("user_id"):
        scope = "selected"
        payload["user_ids"] = [payload.get("user_id")]

    if scope == "all":
        # 仅重置当前房间所有玩家
        players = db.execute_query(
            "SELECT user_id, nickname FROM room_players WHERE room_id = ?",
            (FIXED_ROOM_ID,)
        )
        for p in players:
            uid = p["user_id"]
            db.execute_update(
                "UPDATE room_players SET chips = ? WHERE room_id = ? AND user_id = ?",
                (default_chips, FIXED_ROOM_ID, uid)
            )
            db.execute_update(
                "UPDATE users SET chips = ? WHERE user_id = ?",
                (default_chips, uid)
            )
        affected = players

    elif scope == "selected":
        user_ids = payload.get("user_ids") or []
        if not isinstance(user_ids, list) or not user_ids:
            raise HTTPException(status_code=400, detail="请选择至少一名玩家")
        # 仅限当前房间玩家
        q_marks = ",".join("?" for _ in user_ids)
        params = [FIXED_ROOM_ID] + user_ids
        rows = db.execute_query(
            f"SELECT user_id, nickname FROM room_players WHERE room_id = ? AND user_id IN ({q_marks})",
            tuple(params)
        )
        if not rows:
            raise HTTPException(status_code=404, detail="所选玩家不在当前房间")
        for p in rows:
            uid = p["user_id"]
            db.execute_update(
                "UPDATE room_players SET chips = ? WHERE room_id = ? AND user_id = ?",
                (default_chips, FIXED_ROOM_ID, uid)
            )
            db.execute_update(
                "UPDATE users SET chips = ? WHERE user_id = ?",
                (default_chips, uid)
            )
        affected = rows
    else:
        raise HTTPException(status_code=400, detail="无效的重置范围")

    await manager.broadcast({
        "type": "chips_reset",
        "scope": scope,
        "default_chips": default_chips,
        "affected": [{"user_id": p["user_id"], "nickname": p.get("nickname")} for p in affected]
    })
    return {"success": True, "scope": scope, "default_chips": default_chips, "count": len(affected)}

@app.post("/api/rooms")
async def create_room_endpoint(request: Request):
    """创建新房间"""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    

    
    # 确保固定房间存在
    room = get_room_by_id(FIXED_ROOM_ID)
    if not room:
        create_fixed_room(
            room_id=FIXED_ROOM_ID,
            room_name="主游戏房间",
            creator_id=user["user_id"],
            min_bet=10,
            max_players=9
        )
        room = get_room_by_id(FIXED_ROOM_ID)
    
    return {"room_id": FIXED_ROOM_ID, "message": "已加入主游戏房间"}

@app.get("/room", response_class=HTMLResponse)
async def room_page(request: Request):
    """房间页面（单一房间）"""
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)
    
    # 确保固定房间存在
    room = get_room_by_id(FIXED_ROOM_ID)
    if not room:
        create_fixed_room(
            room_id=FIXED_ROOM_ID,
            room_name="主游戏房间",
            creator_id="system",
            min_bet=10,
            max_players=9
        )
        room = get_room_by_id(FIXED_ROOM_ID)
    
    return templates.TemplateResponse("game.html", {
        "request": request,
        "user": user,
        "room": room,
        "settings": settings
    })

# WebSocket连接管理
# 重复定义已删除，使用第21行定义的ConnectionManager

@app.websocket("/ws/game")
async def websocket_game_endpoint(websocket: WebSocket):
    """WebSocket游戏端点（单一房间）"""
    await websocket.accept()
    
    try:
        # 等待认证消息
        print("等待认证消息（单一房间）")
        auth_data = await websocket.receive_json()
        print(f"收到认证消息: {auth_data}")
        
        if auth_data.get("type") != "auth":
            print("认证失败: 消息类型不是auth")
            await websocket.close(code=1008, reason="需要认证")
            return
        
        session_token = auth_data.get("session_token")
        if not session_token:
            print("认证失败: 缺少session_token")
            await websocket.close(code=1008, reason="无效的会话令牌")
            return
        
        # 验证用户
        print(f"验证session_token: {session_token}")
        user = get_user_by_session_token(session_token)
        if not user:
            print("认证失败: 无效的session_token")
            await websocket.close(code=1008, reason="无效的会话令牌")
            return
        
        print(f"认证成功: 用户 {user['nickname']}")
        
        # 存储连接
        await manager.connect(user["user_id"], websocket)
        
        # 使用固定房间ID
        room_id = FIXED_ROOM_ID
        
        # 通知游戏引擎玩家上线
        if room_id in active_games:
            active_games[room_id].handle_player_reconnect(user["user_id"])
            
            # 广播玩家重连消息
            await manager.broadcast({
                "type": "player_reconnected",
                "user_id": user["user_id"],
                "nickname": user["nickname"]
            }, user["user_id"])
        
        # 添加玩家到房间（使用数据库存储）
        db.execute_update(
            "INSERT OR REPLACE INTO room_players (room_id, user_id, nickname, chips) VALUES (?, ?, ?, ?)",
            (room_id, user["user_id"], user["nickname"], user["chips"])
        )
        print(f"玩家 {user['nickname']} 已添加到房间 {room_id}")
        
        # 获取当前房间的所有玩家
        players = db.execute_query(
            "SELECT user_id, nickname, chips FROM room_players WHERE room_id = ?",
            (room_id,)
        )
        print(f"当前房间玩家: {players}")
        
        # 发送认证成功消息
        await manager.send_personal_message({
            "type": "auth_success",
            "message": f"欢迎 {user['nickname']} 加入房间!",
            "user": user
        }, user["user_id"])
        
        # 先获取最新的玩家状态
        players = db.execute_query(
            "SELECT user_id, nickname, chips, is_ready FROM room_players WHERE room_id = ?",
            (room_id,)
        )
        
        # 构建完整的玩家状态信息
        players_status = []
        for player in players:
            players_status.append({
                "user_id": player["user_id"],
                "nickname": player["nickname"],
                "chips": player["chips"],
                "is_ready": player.get("is_ready", 0),
                "connected": player["user_id"] in manager.active_connections
            })
        
        # 广播玩家加入消息，同时包含最新的玩家状态
        await manager.broadcast({
            "type": "player_joined",
            "user_id": user["user_id"],
            "nickname": user["nickname"],
            "players": players_status  # 包含完整的玩家状态数据
        }, user["user_id"])
        
        # 若房间已有正在进行的游戏，单播当前权威状态给刚加入/重连的玩家，避免回到准备界面
        if room_id in active_games:
            try:
                game = active_games[room_id]
                if hasattr(game, "get_game_state"):
                    state = game.get_game_state()
                    await manager.send_personal_message({
                        "type": "game_state",
                        "data": state
                    }, user["user_id"])
                    # 不在本手牌玩家中 -> 标记观战并告知观战状态
                    try:
                        const_in_hand = any(p.get("user_id") == user["user_id"] for p in state.get("players", []))
                    except Exception:
                        const_in_hand = False
                    if not const_in_hand:
                        spectators.setdefault(room_id, set()).add(user["user_id"])
                        await manager.send_personal_message({
                            "type": "spectator_status",
                            "is_spectator": True,
                            "waiting_next_hand": user["user_id"] in waiting_next_hand.get(room_id, set())
                        }, user["user_id"])
            except Exception as _e:
                # 仅记录，不影响后续流程
                print(f"单播进行中游戏状态失败: {_e}")
        
        # 玩家加入后，更新准备计数
        await update_ready_count(room_id)
        # 立即更新所有玩家的状态显示（确保其他消息也包含最新状态）
        await update_all_players_status(room_id)
        # 加一道自动开局检查：若此时所有玩家都已准备，直接触发开局
        await check_game_start_condition(room_id)
        
        # 保持连接并处理消息
        while True:
            data = await websocket.receive_json()
            
            # 处理不同类型的消息
            if data.get("type") == "ping":
                await manager.send_personal_message({"type": "pong"}, user["user_id"])
                # 更新最近心跳时间
                import time
                manager.last_seen[user["user_id"]] = time.time()
            elif data.get("type") == "game_action":
                await handle_game_action(user, data, room_id)
            elif data.get("type") == "player_ready":
                await handle_player_ready(user, data, room_id)
            elif data.get("type") == "sit_next_hand":
                # 申请在下一手入座：记录等待队列与观战身份
                waiting_next_hand.setdefault(room_id, set()).add(user["user_id"])
                spectators.setdefault(room_id, set()).add(user["user_id"])
                await manager.send_personal_message({"type": "sit_ack", "success": True}, user["user_id"])
            elif data.get("type") == "manual_show_cards":
                # 自愿摊牌：公开当前玩家的两张手牌给所有人
                game = active_games.get(room_id)
                if game and hasattr(game, "voluntary_reveal"):
                    ok = game.voluntary_reveal(user["user_id"])
                    if ok:
                        await manager.broadcast({
                            "type": "game_state_update",
                            "data": game.get_game_state()
                        })
                    else:
                        await manager.send_personal_message({
                            "type": "action_error",
                            "message": "当前阶段不允许摊牌或用户不存在"
                        }, user["user_id"])
                else:
                    await manager.send_personal_message({
                        "type": "action_error",
                        "message": "服务器暂不支持自愿摊牌或游戏未开始"
                    }, user["user_id"])
            elif data.get("type") == "single_player_decision":
                # 处理单玩家的决定（继续/结束）
                game = active_games.get(room_id)
                if game:
                    decision = data.get("decision")  # "continue" 或 "end"
                    success = game.handle_single_player_decision(user["user_id"], decision)
                    if success:
                        # 广播游戏状态更新
                        game_state = game.get_game_state()
                        await manager.broadcast({
                            "type": "game_state_update",
                            "data": game_state
                        })
                        
                        # 如果选择结束，调用游戏结束处理
                        if decision == "end":
                            await handle_game_end(room_id, game)
                    else:
                        await manager.send_personal_message({
                            "type": "action_error",
                            "message": "无法处理您的决定"
                        }, user["user_id"])
                
    except WebSocketDisconnect:
        print("WebSocket连接断开")
        user_id = None
        for uid, conn in manager.active_connections.items():
            if conn == websocket:
                user_id = uid
                break
        
        if user_id:
            # 先断开连接管理器
            manager.disconnect(user_id)
            
            # 在删除前查询昵称
            row = db.execute_query(
                "SELECT nickname FROM room_players WHERE room_id = ? AND user_id = ?",
                (FIXED_ROOM_ID, user_id)
            )
            nickname = (row[0]["nickname"] if row and "nickname" in row[0] else None) or user_id

            # 从数据库中移除玩家
            db.execute_update(
                "DELETE FROM room_players WHERE room_id = ? AND user_id = ?",
                (FIXED_ROOM_ID, user_id)
            )
            
            # 确保数据库操作完成后再广播消息
            import time
            time.sleep(0.1)  # 短暂延迟确保数据库操作完成
            
            # 立即广播玩家离开消息（包含昵称）
            await manager.broadcast({
                "type": "player_left",
                "user_id": user_id,
                "nickname": nickname
            })
            
            # 通知游戏引擎玩家离线
            game = active_games.get(FIXED_ROOM_ID)
            if game:
                # 先标记为离线
                game.set_player_disconnected(user_id)
                
                # 检查是否需要自动跳过当前玩家
                if (game.current_player_position and 
                    game.player_manager.get_player(user_id) and 
                    game.player_manager.get_player(user_id).position == game.current_player_position):
                    # 当前离线玩家需要行动，自动跳过
                    game._move_to_next_player()
                
                # 延迟检查单玩家场景（等待5秒，确认玩家是否重连）
                async def check_single_player_after_delay():
                    await asyncio.sleep(5)  # 等待5秒
                    
                    # 再次检查是否有游戏
                    if FIXED_ROOM_ID not in active_games:
                        return
                    
                    game_check = active_games.get(FIXED_ROOM_ID)
                    if not game_check:
                        return
                    
                    # 检查该玩家是否已重连
                    if user_id in manager.active_connections:
                        print(f"玩家 {user_id} 已重连，不触发单玩家场景")
                        return
                    
                    # 玩家确实离线，检查是否只剩1人
                    online_count = len([p for p in game_check.player_manager.get_active_players() 
                                      if p.user_id in game_check.connected_players and 
                                      p.user_id not in game_check.spectating_players])
                    
                    print(f"延迟检查: 玩家 {user_id} 确实离线，剩余在线玩家: {online_count}")
                    
                    if online_count == 1:
                        print("触发单玩家等待场景")
                        game_check._check_single_player_and_wait()
                        await manager.broadcast({
                            "type": "game_state_update",
                            "data": game_check.get_game_state()
                        })
                
                # 启动延迟检查任务
                asyncio.create_task(check_single_player_after_delay())
                
                # 立即广播当前状态（移除该玩家的显示）
                await manager.broadcast({
                    "type": "game_state_update",
                    "data": game.get_game_state()
                })

            # 先获取最新的玩家状态
            players = db.execute_query(
                "SELECT user_id, nickname, chips, is_ready FROM room_players WHERE room_id = ?",
                (FIXED_ROOM_ID,)
            )
            
            # 构建完整的玩家状态信息
            players_status = []
            for player in players:
                players_status.append({
                    "user_id": player["user_id"],
                    "nickname": player["nickname"],
                    "chips": player["chips"],
                    "is_ready": player.get("is_ready", 0),
                    "connected": player["user_id"] in manager.active_connections
                })
            
            # 玩家离开后，更新准备计数
            await update_ready_count(FIXED_ROOM_ID)
            # 立即更新所有玩家的状态显示
            await update_all_players_status(FIXED_ROOM_ID)
            
            # 广播玩家离开消息，同时包含最新的玩家状态
            await manager.broadcast({
                "type": "player_left",
                "user_id": user_id,
                "nickname": nickname,
                "players": players_status  # 包含完整的玩家状态数据
            })
            
            # 检查房间是否还有玩家
            remaining_players = db.execute_query(
                "SELECT COUNT(*) as count FROM room_players WHERE room_id = ?",
                (FIXED_ROOM_ID,)
            )
            
            # 如果房间没有玩家了，清理游戏实例
            if remaining_players and remaining_players[0]["count"] == 0:
                if FIXED_ROOM_ID in active_games:
                    del active_games[FIXED_ROOM_ID]
            # 如果游戏因玩家不足自动结束，延迟检查开局条件，避免状态冲突
            elif FIXED_ROOM_ID in active_games:
                game = active_games[FIXED_ROOM_ID]
                if hasattr(game, "stage") and game.stage == GameStage.ENDED:
                    # 游戏已因玩家不足结束，延迟2秒后再检查开局条件
                    # 给前端足够时间处理游戏结束状态
                    import asyncio
                    await asyncio.sleep(2)
                    await check_game_start_condition(FIXED_ROOM_ID)
                else:
                    # 正常情况，立即检查开局条件
                    await check_game_start_condition(FIXED_ROOM_ID)
            else:
                # 没有游戏实例，正常检查开局条件
                await check_game_start_condition(FIXED_ROOM_ID)
    except Exception as e:
        print(f"WebSocket错误: {e}")
        try:
            await websocket.close(code=1011, reason="内部错误")
        except:
            pass



async def update_all_players_status(room_id: str):
    """更新所有玩家的状态显示"""
    # 获取最新的玩家列表和状态
    players = db.execute_query(
        "SELECT user_id, nickname, chips, is_ready FROM room_players WHERE room_id = ?",
        (room_id,)
    )
    
    if players:
        # 构建完整的玩家状态信息
        players_status = []
        for player in players:
            players_status.append({
                "user_id": player["user_id"],
                "nickname": player["nickname"],
                "chips": player["chips"],
                "is_ready": player.get("is_ready", 0),
                "connected": player["user_id"] in manager.active_connections
            })
        
        # 广播完整的玩家状态更新
        await manager.broadcast({
            "type": "players_status_update",
            "players": players_status
        })

async def handle_player_ready(user: Dict[str, Any], data: Dict[str, Any], room_id: str):
    """处理玩家准备状态"""
    is_ready = data.get("is_ready", False)
    
    # 更新数据库中的准备状态
    db.execute_update(
        "UPDATE room_players SET is_ready = ? WHERE room_id = ? AND user_id = ?",
        (is_ready, room_id, user["user_id"])
    )
    
    # 广播准备状态更新
    await manager.broadcast({
        "type": "ready_state_update",
        "user_id": user["user_id"],
        "is_ready": is_ready
    })
    
    # 立即更新所有玩家的状态显示
    await update_all_players_status(room_id)
    
    # 检查是否可以开始游戏
    await check_game_start_condition(room_id)
    
    # 更新准备人数计数
    await update_ready_count(room_id)

async def handle_game_action(user: Dict[str, Any], data: Dict[str, Any], room_id: str):
    """处理游戏操作"""
    if room_id not in active_games:
        await manager.send_personal_message({
            "type": "action_error",
            "message": "游戏未开始"
        }, user["user_id"])
        return
    
    game = active_games[room_id]
    action = data.get("action")
    amount = data.get("amount", 0)
    
    # 验证操作类型
    valid_actions = ["fold", "check", "call", "raise"]
    if action not in valid_actions:
        await manager.send_personal_message({
            "type": "action_error",
            "message": "无效的操作类型"
        }, user["user_id"])
        return
    
    # 验证加注金额
    if action == "raise" and amount <= game.current_bet:
        await manager.send_personal_message({
            "type": "action_error",
            "message": "加注金额必须大于当前下注"
        }, user["user_id"])
        return
    
    # 验证当前玩家
    if game.current_player_position is None:
        await manager.send_personal_message({
            "type": "action_error",
            "message": "游戏状态异常"
        }, user["user_id"])
        return
    
    current_player = game.player_manager.get_player_by_position(game.current_player_position)
    if not current_player or user["user_id"] != current_player.user_id:
        await manager.send_personal_message({
            "type": "action_error",
            "message": "不是当前操作玩家"
        }, user["user_id"])
        return
    
    # 验证游戏阶段
    if game.stage in [GameStage.SHOWDOWN, GameStage.ENDED]:
        await manager.send_personal_message({
            "type": "action_error",
            "message": "游戏已进入摊牌或结束阶段"
        }, user["user_id"])
        return
    
    # 验证玩家状态
    if current_player.is_folded:
        await manager.send_personal_message({
            "type": "action_error",
            "message": "您已弃牌，无法操作"
        }, user["user_id"])
        return
    
    try:
        result = game.player_action(user["user_id"], action, amount)
        
        if result["success"]:
            # 发送操作确认
            await manager.send_personal_message({
                "type": "action_confirmation",
                "message": result["message"],
                "all_in": result.get("all_in", False)
            }, user["user_id"])
            
            # 广播游戏状态更新
            game_state = game.get_game_state()
            await manager.broadcast({
                "type": "game_state_update",
                "data": game_state
            })
            
            # 检查游戏是否结束
            if not game.is_game_active():
                await handle_game_end(room_id, game)
        else:
            await manager.send_personal_message({
                "type": "action_error",
                "message": result["message"]
            }, user["user_id"])
            
    except Exception as e:
        print(f"游戏操作错误: {e}")
        await manager.send_personal_message({
            "type": "action_error",
            "message": "操作失败，请重试"
        }, user["user_id"])

async def handle_game_end(room_id: str, game: TexasHoldemGame):
    """处理游戏结束"""
    # 更新房间状态
    update_room_status(room_id, "waiting")
    
    # 保存玩家筹码到数据库
    for player in game.player_manager.players:
        # 更新房间玩家筹码
        db.execute_update(
            "UPDATE room_players SET chips = ? WHERE room_id = ? AND user_id = ?",
            (player.chips, room_id, player.user_id)
        )
        # 更新用户总筹码
        db.execute_update(
            "UPDATE users SET chips = ? WHERE user_id = ?",
            (player.chips, player.user_id)
        )
    
    # 游戏结束后重置所有玩家的准备状态为未准备
    db.execute_update(
        "UPDATE room_players SET is_ready = 0 WHERE room_id = ?",
        (room_id,)
    )
    
    # 广播游戏结束消息
    game_state = game.get_game_state()
    await manager.broadcast({
        "type": "game_ended",
        "winner": game_state["winner"],
        "pot": game_state["pot"]
    })
    # 同步一次权威的游戏状态（stage 应为 ended），确保前端进入准备区
    await manager.broadcast({
        "type": "game_state_update",
        "data": game_state
    })
    
    # 保留已结束的游戏实例，以便结束后仍可自愿摊牌；新一局开始时再清理
    # （不在此处删除 active_games[room_id]）
    
    # 重置全房间玩家的准备状态，并广播准备计数，进入“等待准备”状态
    db.execute_update(
        "UPDATE room_players SET is_ready = 0 WHERE room_id = ?",
        (room_id,)
    )
    await update_ready_count(room_id)
    
    print(f"房间 {room_id} 的游戏已结束")
    
    # 游戏结束后检查是否可以开始新游戏（如果玩家已经准备好）
    await check_game_start_condition(room_id)

async def check_game_start_condition(room_id: str):
    """检查是否可以开始游戏（仅按当前连接玩家计算）"""
    # 读取房间玩家的准备状态
    players_data = db.execute_query(
        "SELECT user_id, is_ready FROM room_players WHERE room_id = ?",
        (room_id,)
    )
    
    # 仅统计当前连接的玩家
    online_players = [p for p in players_data if p["user_id"] in manager.active_connections]
    online_total = len(online_players)
    ready_online = sum(1 for p in online_players if p["is_ready"])
    
    # 添加调试信息
    print(f"房间 {room_id} 准备检查: 在线{online_total}人，已准备{ready_online}人")
    
    # 至少2名在线玩家，且全部已准备；允许在“无实例”或“存在已结束实例”情况下开启新局
    if online_total >= 2 and ready_online == online_total:
        if room_id in active_games:
            existing = active_games[room_id]
            try:
                from game_logic.game_engine import GameStage
                if hasattr(existing, "stage"):
                    # 如果游戏已结束，可以开始新游戏
                    if existing.stage == GameStage.ENDED:
                        await start_game_in_room(room_id)
                    # 如果游戏还未结束，不做任何操作
                    else:
                        print(f"房间 {room_id} 游戏正在进行中，不重新开始")
                else:
                    # 没有stage属性，开始新游戏
                    await start_game_in_room(room_id)
            except Exception as e:
                print(f"检查游戏阶段时出错: {e}")
                await start_game_in_room(room_id)
        else:
            await start_game_in_room(room_id)

async def update_ready_count(room_id: str):
    """更新准备人数计数"""
    # 获取准备状态信息
    players_data = db.execute_query(
        "SELECT user_id, is_ready FROM room_players WHERE room_id = ?",
        (room_id,)
    )
    
    # 只统计在线玩家
    online_players = [p for p in players_data if p["user_id"] in manager.active_connections]
    total_players = len(online_players)
    ready_players = sum(1 for player in online_players if player["is_ready"])
    
    # 广播准备人数更新
    await manager.broadcast({
        "type": "ready_count_update",
        "ready_count": ready_players,
        "total_players": total_players,
        "game_started": room_id in active_games
    })

async def start_game_in_room(room_id: str):
    """在房间中开始新游戏"""
    print(f"开始房间 {room_id} 的新游戏")
    
    # 若存在已结束的游戏实例，允许重启：先移除旧实例以便开始新手牌
    if room_id in active_games:
        existing = active_games[room_id]
        try:
            if hasattr(existing, "stage") and existing.stage == GameStage.ENDED:
                del active_games[room_id]
                print(f"移除已结束的游戏实例")
            else:
                print(f"游戏实例存在且未结束，阶段: {existing.stage}")
        except Exception as e:
            print(f"检查游戏实例时出错: {e}")
            del active_games[room_id]
    if room_id not in active_games:
        # 创建新游戏实例
        room = get_room_by_id(room_id)
        if not room:
            return False
        
        game = TexasHoldemGame(min_bet=room["min_bet"], max_players=room["max_players"])
        active_games[room_id] = game
        
        # 从数据库获取房间玩家（包含准备状态）
        room_players_data = db.execute_query(
            "SELECT user_id, nickname, chips, is_ready FROM room_players WHERE room_id = ?",
            (room_id,)
        )
        
        # 仅添加“已连接且已准备”的玩家进入本手牌
        eligible_players = [
            p for p in room_players_data
            if p["user_id"] in manager.active_connections and p.get("is_ready")
        ]
        
        print(f"符合条件玩家数: {len(eligible_players)}, 玩家详情: {eligible_players}")
        
        # 人数不足2，不启动
        if len(eligible_players) < 2:
            print(f"人数不足2人，无法开始游戏")
            if room_id in active_games:
                del active_games[room_id]
            # 向所有在线玩家发送错误信息
            await manager.broadcast({
                "type": "game_start_error",
                "message": f"人数不足，无法开始游戏。当前在线玩家：{len(eligible_players)}人，至少需要2人才能开始游戏。"
            })
            return False
        
        # 添加玩家到游戏（顺序按当前列表顺序）
        for player in eligible_players:
            print(f"添加玩家到游戏: {player['nickname']} (ID: {player['user_id']})")
            
            # 检查筹码，如果不足则补充到默认筹码
            if player["chips"] < game.min_bet:
                print(f"玩家 {player['nickname']} 筹码不足 ({player['chips']} < {game.min_bet})，自动补充到默认筹码")
                # 更新数据库中的筹码
                db.execute_update(
                    "UPDATE users SET chips = ? WHERE user_id = ?",
                    (1000, player["user_id"])
                )
                # 更新房间玩家表中的筹码
                db.execute_update(
                    "UPDATE room_players SET chips = ? WHERE room_id = ? AND user_id = ?",
                    (1000, room_id, player["user_id"])
                )
                # 更新本地筹码
                player["chips"] = 1000
            
            game.add_player(
                user_id=player["user_id"],
                nickname=player["nickname"],
                chips=player["chips"],
                position=len(game.player_manager.players) + 1
            )
            # 确保玩家在线状态正确设置
            game.set_player_connected(player["user_id"])
        
        print(f"游戏中玩家总数: {len(game.player_manager.players)}")
        print(f"在线活跃玩家数: {len(game.get_online_active_players())}")
        
        # 开始游戏
        print(f"尝试开始游戏...")
        if game.start_game():
            print(f"游戏成功开始！")
            update_room_status(room_id, "playing")
            
            # 广播游戏开始（提示用）
            game_state = game.get_game_state()
            await manager.broadcast({
                "type": "game_started",
                "data": game_state
            })
            # 立刻广播一次权威游戏状态，确保前端渲染完整状态（盲注、底牌、当前行动位等）
            await manager.broadcast({
                "type": "game_state_update",
                "data": game_state
            })
            
            return True
        else:
            print(f"游戏开始失败")
            # 向所有在线玩家发送错误信息
            await manager.broadcast({
                "type": "game_start_error",
                "message": "游戏开始失败，请检查玩家筹码是否充足。"
            })
    
    return False

@app.on_event("startup")
async def startup_event():
    """应用启动时初始化"""
    print("AI扑克训练启动中...")
    print(f"访问地址: http://{settings.HOST}:{settings.PORT}")
    print(f"API文档: http://{settings.HOST}:{settings.PORT}/docs")
    
    # 启动超时检查任务
    start_timeout_check()
    print("游戏超时检查任务已启动")
    
    # 启动定期清理任务
    start_periodic_cleanup()
    print("定期清理任务已启动")

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )