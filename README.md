# 德州扑克在线游戏

基于FastAPI开发的在线德州扑克游戏，专为朋友间休闲娱乐使用。

## 功能特性

- 🎯 完整的德州扑克游戏规则实现
- 👥 简化的用户系统（邀请码验证）
- 💬 实时聊天功能
- 🎮 WebSocket实时游戏同步
- 📱 响应式界面设计（椭圆牌桌布局）
- 🔒 安全的会话管理

## 技术栈

- **后端**: FastAPI + WebSocket
- **数据库**: SQLite + SQLAlchemy
- **前端**: HTML5 + CSS3 + JavaScript
- **模板**: Jinja2
- **部署**: Uvicorn

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行应用

```bash
python main.py
```

或者使用Uvicorn：

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 访问应用

打开浏览器访问：http://localhost:8000

## 使用说明

### 首次使用

1. 访问首页
2. 输入预定义的邀请码（如：POKER123, TEXAS888, GAME456）
3. 设置你的昵称
4. 系统会自动创建账户并跳转到游戏大厅

### 游戏界面特色

- 🎯 **椭圆牌桌设计**：玩家围坐在椭圆形牌桌周围
- 👥 **主视角体验**：每个玩家看到自己都是中心视角
- 🔄 **动态定位**：玩家位置根据人数自动调整
- 💫 **视觉反馈**：当前行动玩家高亮显示

### 游戏流程

1. **加入房间**：输入邀请码后进入唯一游戏房间
2. **自动定位**：系统自动将玩家放置在椭圆牌桌的合适位置
3. **开始游戏**：房间满员后自动开始游戏
4. **游戏操作**：根据游戏状态进行弃牌、过牌、跟注、加注等操作
5. **游戏结束**：比牌后结算筹码，可开始新一局

### 管理员功能

- 查看所有用户列表
- 删除用户账户
- 重置用户筹码
- 管理邀请码列表

## 项目结构

```
poker_app/
├── main.py                 # FastAPI应用入口
├── config.py               # 配置文件
├── database.py             # 数据库连接
├── models.py               # 数据模型
├── schemas.py              # Pydantic模型
├── routers/                # API路由
│   ├── auth.py             # 认证相关
│   ├── users.py            # 用户管理
│   ├── rooms.py            # 房间管理
│   └── games.py            # 游戏操作
├── game_logic/             # 游戏核心逻辑
│   ├── card.py             # 扑克牌类
│   ├── deck.py             # 牌组管理
│   ├── hand_evaluator.py   # 牌型判断
│   ├── player.py           # 玩家类
│   └── game_engine.py      # 游戏引擎
├── websockets/             # WebSocket处理
│   ├── connection_manager.py  # 连接管理
│   └── game_handler.py     # 游戏事件处理
├── static/                 # 静态文件
│   ├── css/
│   ├── js/
│   └── images/
└── templates/              # HTML模板
    ├── index.html          # 首页
    ├── lobby.html          # 游戏大厅
    └── game.html           # 游戏界面
```

## 配置说明

编辑 `config.py` 文件可以修改以下配置：

- `INVITE_CODES`: 预定义的邀请码列表
- `DEFAULT_CHIPS`: 新用户默认筹码数量
- `SECRET_KEY`: JWT加密密钥
- `DATABASE_URL`: 数据库连接字符串

## API文档

启动应用后访问：http://localhost:8000/docs

## 开发说明

### 数据库迁移

项目使用SQLAlchemy ORM，数据库表会在首次运行时自动创建。

### 添加新功能

1. 在对应模块中添加功能
2. 更新数据模型（如果需要）
3. 添加API路由
4. 更新前端界面

### 测试

```bash
# 运行测试（需要先编写测试）
python -m pytest tests/
```

## 部署说明

### 生产环境部署

1. 修改 `config.py` 中的配置
2. 使用生产环境的数据库（如PostgreSQL）
3. 配置反向代理（Nginx）
4. 使用进程管理器（如Supervisor）

### Docker部署

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建Pull Request

## 许可证

MIT License

## 联系方式

如有问题或建议，请通过GitHub Issues提交。