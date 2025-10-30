# AI扑克训练技术文档

## 项目概述
基于FastAPI开发的AI扑克训练，专为朋友间休闲娱乐设计。采用简化用户系统（邀请码机制），支持多人实时对战。

## 技术栈
- **后端框架**: FastAPI 0.104.1
- **数据库**: SQLite (Python内置sqlite3)
- **实时通信**: WebSocket (FastAPI内置)
- **前端技术**: HTML5 + CSS3 + JavaScript (Vanilla JS)
- **模板引擎**: Jinja2
- **服务器**: Uvicorn
- **依赖管理**: Python 3.8+

## 系统架构

### 后端架构
```
poker_app/
├── main.py                 # 应用入口点
├── config.py               # 配置文件
├── database.py             # 数据库连接和会话管理
├── models.py               # 数据模型（dataclasses）
├── game_logic/             # 游戏核心逻辑
│   ├── card.py             # 扑克牌类
│   ├── deck.py             # 牌组管理
│   ├── hand_evaluator.py   # 牌型判断算法
│   ├── game_engine.py      # 游戏流程控制器
│   └── player.py           # 玩家类
# API路由和WebSocket处理器已集成到main.py中
├── static/                 # 静态文件
│   ├── css/
│   │   ├── style.css       # 主样式文件
│   │   └── game.css        # 游戏界面样式
│   ├── js/
│   │   ├── main.js         # 主逻辑
│   │   ├── game.js         # 游戏界面逻辑
│   │   └── websocket.js    # WebSocket通信
│   └── images/             # 图片资源
└── templates/              # Jinja2模板
    ├── base.html           # 基础模板
    ├── index.html          # 首页（邀请码验证）
    ├── lobby.html          # 游戏大厅
    ├── game.html           # 游戏界面
    └── admin.html          # 管理员界面
```

### 数据库设计

#### Users表
```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    nickname TEXT UNIQUE NOT NULL,
    invite_code TEXT NOT NULL,
    chips INTEGER DEFAULT 1000,
    session_token TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);
```

#### Rooms表
```sql
CREATE TABLE rooms (
    room_id TEXT PRIMARY KEY,
    room_name TEXT NOT NULL,
    creator_id TEXT NOT NULL,
    max_players INTEGER DEFAULT 6,
    min_bet INTEGER DEFAULT 5,
    status TEXT DEFAULT 'waiting',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (creator_id) REFERENCES users (user_id)
);
```

#### Games表
```sql
CREATE TABLE games (
    game_id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    pot_size INTEGER DEFAULT 0,
    community_cards TEXT,
    winner_id TEXT,
    FOREIGN KEY (room_id) REFERENCES rooms (room_id),
    FOREIGN KEY (winner_id) REFERENCES users (user_id)
);
```

#### PlayerGames表
```sql
CREATE TABLE player_games (
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
);
```

## 核心功能实现

### 1. 用户系统（邀请码机制）

**预定义邀请码**：
```python
INVITE_CODES = ["POKER123", "TEXAS888", "GAME456", "FRIENDS999"]
```

**用户注册流程**：
1. 用户访问首页，输入邀请码
2. 服务端验证邀请码有效性
3. 验证通过后，用户设置昵称
4. 系统检查昵称是否已存在：
   - 如果昵称已存在，返回现有用户账户
   - 如果昵称不存在，创建新用户账户
5. 生成session_token，存储到浏览器cookie
6. 自动跳转到游戏大厅（重定向到固定房间）

**会话管理**：
- 使用session_token实现持久化登录
- token有效期30天
- 支持多设备登录（同一用户）
- 相同昵称视为同一用户，共享账户和筹码

**邀请码机制**：
- 邀请码仅作为加入游戏的门槛验证
- 同一个邀请码可被多人重复使用
- 邀请码验证在设置昵称时进行

### 2. 游戏逻辑实现

#### 扑克牌表示
```python
class Card:
    def __init__(self, rank: str, suit: str):
        self.rank = rank  # 2-10, J, Q, K, A
        self.suit = suit  # hearts, diamonds, clubs, spades
        
    def __str__(self):
        return f"{self.rank}{self.suit[0].upper()}"
```

#### 牌型判断算法
实现德州扑克所有牌型判断：
1. 皇家同花顺
2. 同花顺
3. 四条
4. 葫芦
5. 同花
6. 顺子
7. 三条
8. 两对
9. 一对
10. 高牌

#### 游戏流程控制
```python
class TexasHoldemGame:
    def __init__(self, players: List[Player]):
        self.players = players
        self.deck = Deck()
        self.community_cards = []
        self.pot = 0
        self.current_bet = 0
        self.dealer_position = 0
        
    async def start_game(self):
        # 1. 洗牌和发牌
        # 2. 前置盲注
        # 3. 第一轮下注
        # 4. 翻牌
        # 5. 第二轮下注
        # 6. 转牌
        # 7. 第三轮下注
        # 8. 河牌
        # 9. 最后下注
        # 10. 比牌和结算
        pass
```

### 3. 实时通信协议

#### WebSocket消息格式
```json
// 游戏状态更新
{
  "type": "game_state_update",
  "data": {
    "players": [
      {
        "user_id": "uuid",
        "nickname": "玩家1",
        "chips": 1000,
        "current_bet": 50,
        "is_turn": true,
        "is_folded": false,
        "hole_cards": ["As", "Kd"]  // 仅对当前玩家可见
      }
    ],
    "community_cards": ["2h", "5d", "9c"],
    "pot_size": 300,
    "current_bet": 50,
    "game_stage": "flop"  // preflop/flop/turn/river
  }
}

// 玩家操作
{
  "type": "player_action",
  "action": "call",  // call/raise/fold/check
  "amount": 50       // 加注金额（仅raise时需要）
}

// 聊天消息
{
  "type": "chat_message",
  "message": "大家好！",
  "sender": "玩家1"
}
```

#### WebSocket端点
- `/ws/game/{room_id}` - 游戏实时通信
- `/ws/chat/{room_id}` - 聊天功能

### 4. 前端界面设计

#### 首页 (index.html)
- 邀请码输入表单
- 昵称设置
- 简单的欢迎界面

#### 游戏大厅 (lobby.html)
- 房间列表显示
- 创建房间功能
- 加入房间按钮
- 用户信息显示（昵称、筹码）

#### 游戏界面 (game.html) - 椭圆牌桌设计
- 椭圆形的绿色牌桌，玩家围坐在周围
- 每个玩家用圆圈表示，圆圈内显示昵称
- 当前玩家视角为中心视角
- 最多支持8个玩家位置

```html
<div class="poker-table-container">
  <div class="poker-table">
    <div class="players-around-table">
      <!-- 玩家圆圈，根据位置动态定位 -->
      <div class="player-circle player-position-0">
        <div class="player-nickname">玩家昵称</div>
        <div class="player-chips-circle">筹码数量</div>
        <div class="player-status-circle">状态</div>
      </div>
    </div>
    <div class="community-cards-section">
      <!-- 公共牌区域 -->
    </div>
  </div>
  <div class="action-section">
    <!-- 操作按钮区域 -->
  </div>
  <div class="chat-section">
    <!-- 聊天区域 -->
  </div>
</div>
```

## API接口设计

### 认证接口
- `POST /api/verify-invite` - 验证邀请码
- `POST /api/create-user` - 创建用户
- `GET /api/user-info` - 获取用户信息

### 房间接口
- `GET /api/rooms` - 获取房间列表
- `POST /api/rooms` - 创建房间
- `GET /api/rooms/{room_id}` - 获取房间详情
- `POST /api/rooms/{room_id}/join` - 加入房间

### 游戏接口
- `GET /api/games/{game_id}` - 获取游戏状态
- `POST /api/games/{game_id}/action` - 执行游戏操作

### 管理员接口
- `GET /api/admin/users` - 获取所有用户
- `DELETE /api/admin/users/{user_id}` - 删除用户
- `PUT /api/admin/users/{user_id}/chips` - 修改用户筹码
- `GET /api/admin/invite-codes` - 获取邀请码列表

## 安全设计

### 1. 邀请码安全
- 服务端验证邀请码
- 邀请码预定义，防止随意注册
- 邀请码使用次数限制（可选）

### 2. WebSocket安全
- 连接时验证用户身份
- 每个房间独立的连接管理
- 操作权限验证

### 3. 数据安全
- SQL注入防护（参数化查询）
- XSS防护（模板自动转义）
- CSRF防护（SameSite cookies）

### 4. 游戏逻辑安全
- 所有关键逻辑在服务端执行
- 客户端只负责显示和用户输入
- 防止作弊的机制

## 部署方案

### 开发环境
```bash
# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 生产环境
```bash
# 使用Uvicorn生产服务器
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# 使用Nginx反向代理
# nginx配置WebSocket支持
```

### 环境变量配置
```python
# config.py
import os

class Settings:
    DATABASE_PATH = os.getenv("DATABASE_PATH", "poker_game.db")
    SECRET_KEY = os.getenv("SECRET_KEY", "development-secret")
    INVITE_CODES = os.getenv("INVITE_CODES", "POKER123,TEXAS888,GAME456").split(",")
```

## 测试策略

### 单元测试
- 游戏逻辑测试（牌型判断、游戏流程）
- 数据库操作测试
- API接口测试

### 集成测试
- WebSocket通信测试
- 多玩家游戏场景测试
- 完整游戏流程测试

### 性能测试
- 多房间并发测试
- WebSocket连接压力测试
- 数据库操作性能测试

## 扩展功能规划

### 第一阶段（MVP）
- [ ] 基本游戏逻辑实现
- [ ] 邀请码用户系统
- [ ] 实时游戏功能
- [ ] 基本前端界面

### 第二阶段
- [ ] 管理员功能
- [ ] 游戏记录和统计
- [ ] 聊天功能增强
- [ ] 移动端适配

### 第三阶段
- [ ] 观战模式
- [ ] 游戏回放功能
- [ ] 高级统计和分析
- [ ] 社交功能（好友系统）

## 维护和监控

### 日志记录
- 访问日志
- 游戏事件日志
- 错误日志
- 性能监控日志

### 健康检查
- API健康检查端点
- 数据库连接检查
- WebSocket连接状态监控

## 附录

### 牌型权重表
| 牌型 | 权重 | 描述 |
|------|------|------|
| 皇家同花顺 | 10 | A-K-Q-J-10同花 |
| 同花顺 | 9 | 五张连续同花牌 |
| 四条 | 8 | 四张相同点数 |
| 葫芦 | 7 | 三条加一对 |
| 同花 | 6 | 五张同花牌 |
| 顺子 | 5 | 五张连续牌 |
| 三条 | 4 | 三张相同点数 |
| 两对 | 3 | 两个不同的对子 |
| 一对 | 2 | 一个对子 |
| 高牌 | 1 | 不符合以上牌型 |

### 开发规范
1. 代码遵循PEP8规范
2. 使用类型注解
3. 函数和类添加文档字符串
4. 提交信息规范
5. 分支管理策略

此文档将作为项目开发的基准参考，所有开发工作都基于此文档进行。

补充规则：
1、整个游戏只有1个房间，所有用户通过邀请码验证后都进入同一个房间；
2、邀请码只是校验能否加入游戏的门槛，同一个邀请码可以给很多人用，只用昵称来区分用户，同样的昵称就是同一个用户，新的昵称就是新用户，在设置昵称，点击开始游戏时校验，另外这里的开始游戏按钮改为加入房间按钮
3、进入房间后，用户围坐在椭圆牌桌上，每个进入的用户自己都是主视角，每个人在牌桌上用圆圈代表，圆圈里面是昵称。

加注逻辑：
最小加注额 = 跟注所需金额 + 上一次加注增量金额
玩家实际输入的加注金额 大于等于最小加注额即可
加注增量 = 玩家实际输入的加注金额 - 跟注所需金额
目标总注 = 玩家当前下注额 + 玩家实际输入的加注金额