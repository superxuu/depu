#!/usr/bin/env python3
"""
AI扑克训练主入口 - 使用纯sqlite3实现
"""
import os
import sys
import uuid
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
    
    async def connect(self, user_id: str, websocket: WebSocket):
        self.active_connections[user_id] = websocket
    
    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
    
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
    
    # 从数据库获取固定房间的玩家信息
    players = db.execute_query(
        "SELECT user_id, nickname, chips FROM room_players WHERE room_id = ?",
        (FIXED_ROOM_ID,)
    )
    print(f"DEBUG: 从数据库获取的玩家: {players}")
    
    players_list = [
        {
            "user_id": player["user_id"],
            "nickname": player["nickname"],
            "chips": player["chips"],
            "connected": player["user_id"] in manager.active_connections
        }
        for player in players
    ]
    
    print(f"DEBUG: players_list: {players_list}")
    return {
        "players": players_list,
        "total_players": len(players_list)
    }

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
        
        # 广播玩家加入消息
        await manager.broadcast({
            "type": "player_joined",
            "user_id": user["user_id"],
            "nickname": user["nickname"]
        }, user["user_id"])
        
        # 玩家加入后，更新准备计数
        await update_ready_count(room_id)
        # 加一道自动开局检查：若此时所有玩家都已准备，直接触发开局
        await check_game_start_condition(room_id)
        
        # 保持连接并处理消息
        while True:
            data = await websocket.receive_json()
            
            # 处理不同类型的消息
            if data.get("type") == "ping":
                await manager.send_personal_message({"type": "pong"}, user["user_id"])
            elif data.get("type") == "game_action":
                await handle_game_action(user, data, room_id)
            elif data.get("type") == "player_ready":
                await handle_player_ready(user, data, room_id)
                
    except WebSocketDisconnect:
        print("WebSocket连接断开")
        user_id = None
        for uid, conn in manager.active_connections.items():
            if conn == websocket:
                user_id = uid
                break
        
        if user_id:
            manager.disconnect(user_id)
            
            # 从数据库中移除玩家
            db.execute_update(
                "DELETE FROM room_players WHERE room_id = ? AND user_id = ?",
                (FIXED_ROOM_ID, user_id)
            )
            
            # 广播玩家离开消息
            await manager.broadcast({
                "type": "player_left",
                "user_id": user_id
            })

            # 玩家离开后，更新准备计数
            await update_ready_count(FIXED_ROOM_ID)
            # 离开后也检查一次是否满足开局条件（例如剩余玩家全部已准备且≥2）
            await check_game_start_condition(FIXED_ROOM_ID)

            # 检查房间是否还有玩家
            remaining_players = db.execute_query(
                "SELECT COUNT(*) as count FROM room_players WHERE room_id = ?",
                (FIXED_ROOM_ID,)
            )
            
            # 如果房间没有玩家了，清理游戏实例
            if remaining_players and remaining_players[0]["count"] == 0:
                if FIXED_ROOM_ID in active_games:
                    del active_games[FIXED_ROOM_ID]
    except Exception as e:
        print(f"WebSocket错误: {e}")
        try:
            await websocket.close(code=1011, reason="内部错误")
        except:
            pass



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
    
    # 清理游戏实例
    if room_id in active_games:
        del active_games[room_id]
    
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
    
    # 至少2名玩家，且玩家全部准备；且当前房间未有活跃游戏
    if online_total >= 2 and ready_online == online_total and room_id not in active_games:
        await start_game_in_room(room_id)

async def update_ready_count(room_id: str):
    """更新准备人数计数"""
    # 获取准备状态信息
    players_data = db.execute_query(
        "SELECT is_ready FROM room_players WHERE room_id = ?",
        (room_id,)
    )
    
    total_players = len(players_data)
    ready_players = sum(1 for player in players_data if player["is_ready"])
    
    # 广播准备人数更新
    await manager.broadcast({
        "type": "ready_count_update",
        "ready_count": ready_players,
        "total_players": total_players,
        "game_started": room_id in active_games
    })

async def start_game_in_room(room_id: str):
    """在房间中开始新游戏"""
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
        
        # 人数不足2，不启动
        if len(eligible_players) < 2:
            if room_id in active_games:
                del active_games[room_id]
            return False
        
        # 添加玩家到游戏（顺序按当前列表顺序）
        for player in eligible_players:
            game.add_player(
                user_id=player["user_id"],
                nickname=player["nickname"],
                chips=player["chips"],
                position=len(game.player_manager.players) + 1
            )
        
        # 开始游戏
        if game.start_game():
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
    
    return False

if __name__ == "__main__":
    import uvicorn
    print("AI扑克训练启动中...")
    print(f"访问地址: http://{settings.HOST}:{settings.PORT}")
    print(f"API文档: http://{settings.HOST}:{settings.PORT}/docs")
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )