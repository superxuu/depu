
class PokerGame {
    constructor(user) {
        this.user = user;
        this.socket = null;
        this.gameState = null;
        this.isConnected = false;
        this.isManuallyClosed = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000; // 初始重连延迟3秒
        this.lastGameWinners = []; // 保存上一局的赢家信息
        this.lastGameWinnerDeltas = {}; // 保存赢家的筹码变化信息
        
        this.initializeSocket();
        this.startHeartbeat();
    }
    
    initializeSocket() {
        try {
            this.socket = new WebSocket(`ws://${window.location.host}/ws/game`);
            
            this.socket.onopen = () => {
                this.isConnected = true;
                this.hideConnectionMessages();
                try { this.showToast('WS已连接', 'info'); } catch (e) { }
                this.authenticate();
            };
            
            this.socket.onmessage = async (event) => {
                try {
                    const data = JSON.parse(event.data);
                    await this.handleMessage(data);
                } catch (error) {
                    try { this.showToast('消息解析错误', 'error'); } catch (e) {}
                }
            };
            
            this.socket.onclose = (event) => {
                this.isConnected = false;
                this.showDisconnectedMessage();
                
                // 显示重连按钮
                this.showReconnectButton();
                
                // 自动重连机制（如果不是手动关闭且未超过最大重连次数）
                if (!this.isManuallyClosed && this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    
                    // 计算重连延迟，每次重连延迟增加
                    const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);
                    
                    // 游戏结束后延迟重连，避免状态冲突
                    const finalDelay = this.gameState && this.gameState.stage === 'ended' ? Math.max(delay, 5000) : delay;
                    

                    
                    setTimeout(() => {
                        this.initializeSocket();
                    }, finalDelay);
                } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
                    this.showErrorMessage('已达到最大重连次数，请刷新页面重试');
                }
            };
            
            this.socket.onerror = (error) => {
                this.showErrorMessage('网络连接错误，请重试');
            };
            
        } catch (error) {
            this.showErrorMessage('初始化连接失败，请刷新页面');
        }
    }
    
    authenticate() {
        const sessionToken = this.getSessionToken();
        if (!sessionToken) {
            this.showErrorMessage('未找到会话令牌，请重新登录');
            // 重定向到首页
            setTimeout(() => {
                window.location.href = '/';
            }, 2000);
            return;
        }
        
        this.sendMessage({
            type: 'auth',
            session_token: sessionToken
        });
        
        // 设置认证超时检查（增加到10秒）
        this.authTimeout = setTimeout(() => {
            if (!this.isConnected) {
                this.showErrorMessage('认证超时，正在尝试重新连接...');
                // 关闭当前连接，触发自动重连
                if (this.socket) {
                    this.socket.close();
                }
            }
        }, 10000);
    }
    
    async handleMessage(data) {
        switch (data.type) {
            case 'auth_success':
                this.handleAuthSuccess(data);
                break;
            case 'game_state':
                this.handleGameState(data.data);
                break;
            case 'game_state_update':
                this.handleGameStateUpdate(data.data);
                break;
            case 'action_confirmation':
                this.handleActionConfirmation(data);
                break;
            case 'action_error':
                this.handleActionError(data);
                break;
            
            case 'game_start_error':
                this.handleGameStartError(data);
                break;
            
            case 'player_joined':
                await this.handlePlayerJoined(data);
                break;
            case 'player_left':
                await this.handlePlayerLeft(data);
                break;
            case 'player_disconnected':
                await this.handlePlayerDisconnected(data);
                break;
            case 'player_reconnected':
                await this.handlePlayerReconnected(data);
                break;
            case 'game_started':
                this.handleGameStarted(data);
                break;
            case 'game_ended':
                this.handleGameEnded(data);
                break;
            case 'pong':
                this.handlePong();
                break;
            case 'error':
                this.handleError(data);
                break;
            case 'ready_state_update':
                this.handleReadyStateUpdate(data);
                break;
            case 'ready_count_update':
                this.handleReadyCountUpdate(data);
                break;
            case 'chips_reset':
                this.handleChipsReset(data);
                break;
            case 'players_status_update':
                this.handlePlayersStatusUpdate(data);
                break;
            default:
                // 未知消息类型
        }
    }
    
    async handleAuthSuccess(data) {
        // 清除认证超时
        if (this.authTimeout) {
            clearTimeout(this.authTimeout);
            this.authTimeout = null;
        }
        
        // 重置重连计数器
        this.reconnectAttempts = 0;
        
        this.isConnected = true;
        this.hideConnectionMessages();
        
        // 隐藏重连按钮
        this.hideReconnectButton();
        
        // 更新用户信息（确保session_token一致）
        if (this.user) {
            this.user = { ...this.user, ...data.user };
        }
        
        // 认证成功后立即更新玩家列表
        await this.updateRoomPlayers();
        
        // 认证成功后设置事件监听器（确保在DOM元素加载后）
        this.setupEventListeners();

        // 兜底：如果房间已有进行中的对局或刚开局，拉取权威状态并立刻渲染，以便显示庄家 D
        try {
            const resp = await fetch('/api/room/status');
            if (resp.ok) {
                const js = await resp.json();
                if (js && js.game_state) {
                    this.gameState = js.game_state;
                    // 用权威状态立即渲染玩家和阶段（显示庄家 D）
                    const stage = this.normalizeStage(this.gameState?.stage || 'waiting');
                    this.updateGameStage(stage);
                    this.renderPlayers();
                }
            }
        } catch (e) {
        }
        
        this.showToast('连接成功', 'success');
    }
    
    handleGameState(gameState) {
        this.gameState = gameState;
        this.renderGameState();
    }
    
    handleGameStateUpdate(gameState) {
        this.gameState = gameState;
        
        // 重要：同步更新玩家数据，确保赢家标志正确显示
        this.latestPlayersData = { players: gameState.players };
        
        // 检查游戏阶段，如果是结束阶段，不调用renderGameState以避免覆盖准备按钮
        const stage = this.normalizeStage(gameState.stage);
        
        // 检查单玩家等待状态（只在有游戏进行中时检查）
        // 只有当single_player_waiting存在且当前用户是等待用户时才显示弹框
        // 同时检查在线玩家数量，避免在多人游戏时错误显示弹框
        if (stage && stage !== 'ended' && stage !== 'waiting' && 
            gameState.single_player_waiting && 
            gameState.single_player_waiting.user_id === this.user?.user_id) {
            
            // 额外检查：确保当前确实只有一名在线活跃玩家
            const onlinePlayers = gameState.players?.filter(p => 
                p.connection_status === 'online' && !p.is_folded
            ) || [];
            
            if (onlinePlayers.length <= 1) {
                // 只有游戏中的最后一个玩家才能看到单玩家弹框
                this.showSinglePlayerDialog();
            } else {
                // 如果在线玩家超过1人，说明已经恢复为多人游戏，隐藏弹框
                this.hideSinglePlayerDialog();
            }
        } else {
            this.hideSinglePlayerDialog();
        }
        
        // 重要：在游戏状态更新时，立即渲染玩家个人手牌
        this.renderPlayerHoleCardsFromGameState();
        
        if (stage !== 'ended') {
            this.renderGameState();
        } else {
            // 游戏结束阶段，只更新必要的UI元素，并强制显示准备区
            this.renderCommunityCards();
            this.renderPlayers();
            this.renderPot();
            this.updateGameStage(stage);
            // 强制切换到准备区，避免因消息顺序导致按钮不出现
            this.toggleGameActions(false);
        }
        // 摊牌/结束阶段渲染明牌
        if (stage === 'showdown' || stage === 'ended') {
            this.renderShowdownReveal(this.gameState);
        }
    }
    
    handleActionConfirmation(data) {
        this.showToast(data.message, 'success');
    }
    
    handleActionError(data) {
        this.showToast(data.message, 'error');
        this.enableActionButtons();
    }
    
    handleGameStartError(data) {
        this.showToast(data.message || '游戏开始失败', 'error');
    }
    
    // 规范化阶段值，兼容后端大写/枚举等形式
    normalizeStage(stage) {
        if (!stage) return 'waiting';
        const s = String(stage).toLowerCase();
        // 去掉可能的前缀如 "gamestage."
        const last = s.includes('.') ? s.split('.').pop() : s;
        const mapping = {
            preflop: 'preflop',
            flop: 'flop',
            turn: 'turn',
            river: 'river',
            showdown: 'showdown',
            ended: 'ended',
            waiting: 'waiting',
            start: 'preflop',
            started: 'preflop'
        };
        return mapping[last] || last;
    }
    
    // 推导当前行动玩家的 user_id，兼容 user_id/position 多种字段
    deriveCurrentPlayerId() {
        if (!this.gameState || !Array.isArray(this.gameState.players)) return null;

        // 若后端直接提供了 user_id
        if (typeof this.gameState.current_player_id === 'string') {
            return this.gameState.current_player_id;
        }
        if (typeof this.gameState.current_player === 'string') {
            return this.gameState.current_player;
        }

        // 若提供的是位置号（数字），支持 current_player 或 current_player_position
        const pos = (typeof this.gameState.current_player === 'number')
            ? this.gameState.current_player
            : this.gameState.current_player_position;

        if (pos != null) {
            // 优先通过玩家的 position 字段映射
            const p = this.gameState.players.find(x => Number(x.position) === Number(pos));
            if (p) return p.user_id;
            // 回退：如果 position 从1开始且顺序与数组位置相同
            if (pos >= 1 && pos <= this.gameState.players.length) {
                return this.gameState.players[pos - 1]?.user_id || null;
            }
        }
        return null;
    }
    
    
    
    async handlePlayerJoined(data) {
        // 提示并立即刷新玩家列表
        this.showToast(`${data.nickname || data.user_id} 加入了游戏`, 'info');
        
        // 如果消息中包含玩家数据，直接使用；否则从API获取
        if (data.players) {
            this.latestPlayersData = { players: data.players };
            await this.renderPlayers();
        } else {
            // 兜底：从API获取最新玩家数据
            await this.updateRoomPlayersForce();
        }
    }
    
    async handlePlayerLeft(data) {
        // 提示并立即刷新玩家列表
        this.showToast(`玩家 ${data.nickname || data.user_id} 离开了游戏`, 'info');
        
        // 如果消息中包含玩家数据，直接使用；否则从API获取
        if (data.players) {
            this.latestPlayersData = { players: data.players };
            await this.renderPlayers();
        } else {
            // 兜底：从API获取最新玩家数据
            await this.updateRoomPlayersForce();
        }
    }
    
    async handlePlayerDisconnected(data) {
        this.showToast(`玩家 ${data.nickname || data.user_id} 断开连接`, 'warning');
        
        // 强制从API获取最新玩家数据，确保实时性
        await this.updateRoomPlayersForce();
    }
    
    async handlePlayerReconnected(data) {
        this.showToast(`玩家 ${data.nickname || data.user_id} 重新连接`, 'success');
        
        // 强制从API获取最新玩家数据，确保实时性
        await this.updateRoomPlayersForce();
        
        // 玩家重连时，自动隐藏单玩家弹框（恢复为多人游戏）
        this.hideSinglePlayerDialog();
        
        // 重要：请求最新的游戏状态，确保游戏可以继续
        // 后端已经广播了game_state_update消息，前端会自动处理
    }
    
    async handleGameStarted(payload) {
        const ov = document.getElementById('showdown-reveal');
        if (ov) ov.remove();
        // 优先使用服务端随附的权威状态
        if (payload && payload.data) {
            this.gameState = payload.data;
        } else {
            // 兜底：立即从后端获取当前房间状态，拿到 dealer_position 等权威信息
            try {
                const resp = await fetch('/api/room/status');
                if (resp.ok) {
                    const js = await resp.json();
                    if (js && js.game_state) this.gameState = js.game_state;
                }
            } catch (e) {

            }
        }
        this.showToast('游戏开始！', 'success');
        
        // 清除上一局的赢家信息，因为新游戏开始了
        this.lastGameWinners = [];
        
        // 依据当前状态更新阶段显示并立刻渲染玩家（以显示庄家 D）
        const stage = this.normalizeStage(this.gameState?.stage || 'preflop');
        this.updateGameStage(stage);
        this.renderPlayers();
        // 游戏开始，切换到游戏操作按钮
        this.toggleGameActions(true);
    }
    
    handleGameEnded(data) {
        
        if (data.winner && data.winner.user_id === this.user.user_id) {
            this.showToast('恭喜你获胜！', 'success');
        } else if (data.winner) {
            this.showToast(`${data.winner.nickname} 获胜！`, 'info');
        }
        
        // 保存赢家信息和筹码变化，用于在玩家点击准备按钮前继续显示
        if (data.winner) {
            this.lastGameWinners = [data.winner.user_id];
            // 保存赢家的筹码变化信息
            this.lastGameWinnerDeltas = {};
            this.lastGameWinnerDeltas[data.winner.user_id] = data.winner.hand_delta || 0;
        } else {
            this.lastGameWinners = [];
            this.lastGameWinnerDeltas = {};
        }
        
        this.updateGameStage('ended');
        
        // 重要：在游戏结束后立即渲染玩家，显示赢家标志和筹码变化
        this.renderPlayers();
        
        // 强制显示准备按钮区域，隐藏游戏操作区域
        const readySection = document.getElementById('ready-section');
        const gameActionSection = document.getElementById('game-action-section');
        
        if (readySection) {
            readySection.style.display = 'flex';
        }
        
        if (gameActionSection) {
            gameActionSection.style.display = 'none';
        }
        
        // 重置当前玩家的准备状态为未准备
        if (this.user) {
            this.updateReadyUI(false);
        }
        
        // 游戏结束后，广播准备状态更新，确保所有玩家看到准备按钮
        this.sendMessage({
            type: 'player_ready',
            is_ready: false
        });
    }
    
    handlePong() {
        // 心跳响应
        this.lastPongTime = Date.now();
    }
    
    handleError(data) {
        this.showToast(data.message, 'error');
    }
    
    handleReadyStateUpdate(data) {
        // 仅当变更的是“本机用户”时，才切换本机准备/取消按钮
        if (data.user_id === this.user.user_id) {
            this.updateReadyUI(!!data.is_ready);
        }
        
        // 无论是谁，都只更新对应玩家的就地展示状态，不影响本机按钮
        this.updatePlayerReadyStatus(data.user_id, !!data.is_ready);
    }
    
    handleReadyCountUpdate(data) {
        // 只负责更新准备人数显示，UI切换由 game_started 和 gameState 驱动
        this.updateReadyCount(data.ready_count, data.total_players);
    }
    
    handlePlayersStatusUpdate(data) {
        // 处理玩家状态更新消息，保存最新数据并立即刷新玩家列表显示
        this.latestPlayersData = data;
        this.renderPlayers();
    }
    
    setReady() {
        const ov = document.getElementById('showdown-reveal');
        if (ov) ov.remove();
        
        // 检查连接状态
        if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {

            this.showToast('连接已断开，请刷新页面', 'error');
            return;
        }
        
        // 如果当前玩家是上一局的赢家，点击准备后清除赢家标志和筹码变化信息
        if (this.lastGameWinners.includes(this.user.user_id)) {
            this.lastGameWinners = this.lastGameWinners.filter(id => id !== this.user.user_id);
            delete this.lastGameWinnerDeltas[this.user.user_id];
        }
        
        this.sendMessage({
            type: 'player_ready',
            is_ready: true
        });
    }
    
    setUnready() {
        const ov = document.getElementById('showdown-reveal');
        if (ov) ov.remove();
        
        // 检查连接状态
        if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
            this.showToast('连接已断开，请刷新页面', 'error');
            return;
        }
        
        this.sendMessage({
            type: 'player_ready',
            is_ready: false
        });
    }
    
    updateReadyUI(isReady) {
        // 仅切换本机的两个全局按钮，不影响其他元素
        const readyBtn = document.getElementById('ready-btn');
        const unreadyBtn = document.getElementById('unready-btn');
        if (!readyBtn || !unreadyBtn) return;
        
        if (isReady) {
            readyBtn.style.display = 'none';
            unreadyBtn.style.display = 'block';
        } else {
            readyBtn.style.display = 'block';
            unreadyBtn.style.display = 'none';
        }
    }
    
    updateReadyCount(readyCount, totalPlayers) {
        const readyCountEl = document.getElementById('ready-count');
        if (readyCountEl) {
            readyCountEl.textContent = `准备: ${readyCount}/${totalPlayers}`;
        }
    }
    
    updatePlayerReadyStatus(userId, isReady) {
        // 更新玩家列表中的准备状态显示
        const playerEl = document.querySelector(`[data-user-id="${userId}"]`);
        if (playerEl) {
            // 更新CSS类
            if (isReady) {
                playerEl.classList.add('ready');
            } else {
                playerEl.classList.remove('ready');
            }
            
            // 更新状态文本
            const statusEl = playerEl.querySelector('.player-status-circle');
            if (statusEl) {
                if (isReady) {
                    statusEl.textContent = '已准备';
                } else {
                    statusEl.textContent = '';
                }
            }
            
            // 更新准备指示器
            let readyIndicator = playerEl.querySelector('.ready-indicator');
            if (isReady) {
                if (!readyIndicator) {
                    readyIndicator = document.createElement('div');
                    readyIndicator.className = 'ready-indicator';
                    readyIndicator.title = '已准备';
                    readyIndicator.textContent = '✓';
                    playerEl.appendChild(readyIndicator);
                }
            } else if (readyIndicator) {
                readyIndicator.remove();
            }
        }
    }
    
    toggleGameActions(showGameActions) {
        const readySection = document.getElementById('ready-section');
        const gameActionSection = document.getElementById('game-action-section');

        // 判定是否为观战者：当游戏有状态且本机用户不在本手牌 players 列表中
        const isSpectator = !!(this.gameState
            && Array.isArray(this.gameState.players)
            && !this.gameState.players.some(p => p && p.user_id === this.user?.user_id));

        if (readySection && gameActionSection) {
            if (isSpectator) {
                // 观战者：不显示游戏操作区，始终显示“准备”以加入下一手
                readySection.style.display = 'flex';
                gameActionSection.style.display = 'none';
                return;
            }
            if (showGameActions) {
                // 仅在服务端明确开始游戏时切换到操作区
                readySection.style.display = 'none';
                gameActionSection.style.display = 'flex';
            } else {
                // 默认：显示准备区、隐藏操作区（不会被他人“准备”影响）
                readySection.style.display = 'flex';
                gameActionSection.style.display = 'none';
            }
        }
    }
    
    sendMessage(message) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(message));
        } else {
            this.showErrorMessage('网络连接异常，请重试');
            
            // 尝试重新连接
            if (!this.isConnected) {
                setTimeout(() => {
                    this.initializeSocket();
                }, 1000);
            }
        }
    }
    
    showSinglePlayerDialog() {
        const overlay = document.getElementById('single-player-overlay');
        if (overlay) {
            overlay.classList.add('active');
            
            // 启动倒计时
            this.startSinglePlayerCountdown();
        }
    }
    
    startSinglePlayerCountdown() {
        // 清除之前的倒计时
        if (this.singlePlayerCountdownInterval) {
            clearInterval(this.singlePlayerCountdownInterval);
        }
        
        let countdown = 20; // 20秒倒计时
        const countdownEl = document.getElementById('single-player-countdown');
        
        if (countdownEl) {
            countdownEl.textContent = countdown;
        }
        
        this.singlePlayerCountdownInterval = setInterval(() => {
            countdown--;
            if (countdownEl) {
                countdownEl.textContent = countdown;
            }
            
            if (countdown <= 0) {
                // 倒计时结束，自动结束游戏
                clearInterval(this.singlePlayerCountdownInterval);
                this.sendSinglePlayerDecision('end');
                this.hideSinglePlayerDialog();
            }
        }, 1000);
    }
    
    hideSinglePlayerDialog() {
        const overlay = document.getElementById('single-player-overlay');
        if (overlay) {
            overlay.classList.remove('active');
        }
        
        // 清除倒计时
        if (this.singlePlayerCountdownInterval) {
            clearInterval(this.singlePlayerCountdownInterval);
            this.singlePlayerCountdownInterval = null;
        }
    }
    
    hideSinglePlayerDialog() {
        const overlay = document.getElementById('single-player-overlay');
        if (overlay) {
            overlay.classList.remove('active');
        }
    }
    
    sendSinglePlayerDecision(decision) {
        this.sendMessage({
            type: 'single_player_decision',
            decision: decision
        });
    }
    
    sendAction(action, amount = 0) {
        // 确保只在“轮到我行动”时发送
        const cpUserId = this.deriveCurrentPlayerId();
        if (cpUserId && cpUserId !== this.user.user_id) {
            this.showToast('未轮到你行动', 'warning');
            return;
        }
        this.disableActionButtons();
        this.sendMessage({
            type: 'game_action',
            action: action,
            amount: amount
        });
    }
    
    
    
    fold() {
        this.sendAction('fold');
    }
    
    check() {
        this.sendAction('check');
    }
    
    call() {
        const callAmount = this.calculateCallAmount();
        this.sendAction('call', callAmount);
    }
    
    raise(amount) {
        this.sendAction('raise', amount);
    }
    
    calculateCallAmount() {
        if (!this.gameState) return 0;
        
        const currentPlayer = this.gameState.players.find(p => p.user_id === this.user.user_id);
        if (!currentPlayer) return 0;
        
        return this.gameState.current_bet - currentPlayer.current_bet;
    }
    
    // 统一：本回合最小加注增量（优先后端last_raise_increment，否则min_bet）
    getLastIncrement() {
        const inc = Number(this.gameState?.last_raise_increment ?? this.gameState?.min_bet ?? 0);
        return isNaN(inc) ? 0 : inc;
    }
    // 统一：本回合“最小加到”目标总注 = 台面当前总注 + 最小增量
    getMinRaiseTarget() {
        const tableBet = Number(this.gameState?.current_bet || 0);
        const lastInc = this.getLastIncrement();
        return tableBet + lastInc;
    }

    renderGameState() {
        if (!this.gameState) return;
        
        const stage = this.normalizeStage(this.gameState.stage);
        
        // 只在非 waiting/ended 阶段显示操作区
        // 如果游戏已经结束（ended阶段），保持准备按钮显示
        if (stage === 'ended') {
            // 游戏结束阶段，确保准备按钮显示，游戏操作区域隐藏
            const readySection = document.getElementById('ready-section');
            const gameActionSection = document.getElementById('game-action-section');
            
            if (readySection) {
                readySection.style.display = 'flex';
            }
            if (gameActionSection) {
                gameActionSection.style.display = 'none';
            }
        } else {
            const gameInProgress = stage && !['waiting'].includes(stage);
            this.toggleGameActions(gameInProgress);
        }

        this.renderCommunityCards();
        this.renderPlayers();
        this.renderPot();
        this.renderActionButtons();
        this.updateGameStage(stage);
        // 摊牌阶段渲染明牌
        if (stage === 'showdown' || stage === 'ended') {
            this.renderShowdownReveal(this.gameState);
        }
    }
    
    renderCommunityCards() {
        const communityCardsEl = document.getElementById('community-cards-center');
        if (!communityCardsEl) {
            return;
        }
        
        communityCardsEl.innerHTML = '';
        
        // 检查是否有游戏状态数据
        if (!this.gameState) {
            return;
        }
        
        // 在PREFLOP阶段没有公共牌是正常的
        if (this.gameState.stage === 'preflop') {
            return;
        }
        
        if (!this.gameState.community_cards || this.gameState.community_cards.length === 0) {
            return;
        }
        
        this.gameState.community_cards.forEach(card => {
            const cardEl = this.createCardElement(card);
            communityCardsEl.appendChild(cardEl);
        });
    }
    
    async renderPlayers() {
        const playersContainer = document.getElementById('players-container');
        if (!playersContainer) {
    
            return;
        }
        playersContainer.innerHTML = '';
        // 预计算用于渲染的庄家位置（优先使用后端提供，其次用小盲推导）
        this.dealerPositionForRender = this.computeDealerPositionForRender();

        let players = [];
        
        // 优先使用WebSocket消息中的实时玩家数据
        if (this.latestPlayersData && this.latestPlayersData.players) {
            players = this.latestPlayersData.players;
        } else {
            // 兜底：从API获取最新的玩家数据
            try {
                const response = await fetch('/api/players');
                if (response.ok) {
                    const data = await response.json();
                    // 不过滤离线玩家，显示所有玩家但通过样式区分连接状态
                    players = data.players || [];
                } else {
                    // 即使API失败也要继续，至少清空列表
                    players = [];
                }
            } catch (error) {

                // 继续执行，不返回
                players = [];
            }
        }

        if (players.length > 0) {
            // 1. 绝对稳定排序：所有客户端都按 user_id 排序，确保玩家顺序一致
            const sortedPlayers = [...players].sort((a, b) => String(a.user_id).localeCompare(String(b.user_id)));
            
            // 2. 找到当前玩家在排序后列表中的索引
            const currentPlayerIndex = sortedPlayers.findIndex(p => p.user_id === this.user?.user_id);

            // 3. 渲染每个玩家
            sortedPlayers.forEach((player, index) => {
                try {
                    // 计算相对索引，将当前玩家旋转到索引0（底部）
                    const relativeIndex = currentPlayerIndex !== -1
                        ? (index - currentPlayerIndex + sortedPlayers.length) % sortedPlayers.length
                        : index;
                    
                    const playerEl = this.createPlayerCircleElement(player, relativeIndex, sortedPlayers.length);
                    playersContainer.appendChild(playerEl);
                } catch (error) {
        
                }
            });
        } else {
            // 没有玩家，显示等待状态
            const waitingEl = document.createElement('div');
            waitingEl.className = 'waiting-message';
            waitingEl.innerHTML = '<div class="waiting-text">等待其他玩家加入...</div>';
            playersContainer.appendChild(waitingEl);
        }
    }
    
    async getRoomPlayers() {
        try {
            const response = await fetch('/api/players');
            if (response.ok) {
                const data = await response.json();
                // 修复：正确返回API响应中的players数组
                return data.players || [];
            }
            return [];
        } catch (error) {

            return [];
        }
    }
    
    async updateRoomPlayers() {
        // 直接调用renderPlayers，因为它现在总是从API获取最新数据
        await this.renderPlayers();
    }
    
    async updateRoomPlayersForce() {
        // 强制清空缓存数据，确保从API获取最新数据
        this.latestPlayersData = null;
        // 直接调用renderPlayers，它会从API获取最新数据
        await this.renderPlayers();
    }
    
    renderPlayersWithData(players) {
        this.renderPlayers();
    }
    
    renderPot() {
        const potEl = document.getElementById('pot-size');
        if (potEl) {
            potEl.textContent = `底池: ${this.gameState.pot}`;
        }
    }
    
    renderActionButtons() {
        if (!this.gameState || !Array.isArray(this.gameState.players)) {
            this.disableActionButtons();
            return;
        }
        const cpUserId = this.deriveCurrentPlayerId();
        const currentPlayer = this.gameState.players.find(p => p.user_id === this.user.user_id);
        const isCurrentPlayer = cpUserId && cpUserId === this.user.user_id;

        if (!isCurrentPlayer || !currentPlayer || currentPlayer.is_folded) {
            this.disableActionButtons();
            return;
        }
        
        this.enableActionButtons();

        const safeCurrentBet = Number(this.gameState.current_bet || 0);
        const safeMinBet = Number(this.gameState.min_bet || 0);

        const callAmount = Math.max(0, this.calculateCallAmount() || 0);
        const callBtn = document.getElementById('call-btn');
        const checkBtn = document.getElementById('check-btn');
        if (callBtn) {
            // 始终显示“跟注”按钮，避免布局跳动
            callBtn.style.display = 'inline-block';
            if (callAmount > 0) {
                // 需要跟注：显示金额
                callBtn.textContent = `跟注 ${callAmount}`;
                callBtn.disabled = Number(currentPlayer.chips || 0) < callAmount;
            } else {
                // 无需跟注：保持按钮但置灰，文案固定为“跟注”
                callBtn.textContent = '跟注';
                callBtn.disabled = true;
            }
        }
        // 仅在无需跟注（本街无下注或己方已匹配当前注）时允许过牌
        if (checkBtn) {
            checkBtn.disabled = callAmount > 0;
            if (checkBtn.disabled) {
                checkBtn.title = '当前有未匹配的下注，需跟注或加注';
            } else {
                checkBtn.title = '';
            }
        }
        
        const raiseBtn = document.getElementById('raise-btn');
        const raiseInput = document.getElementById('raise-amount');
        const allinBtn = document.getElementById('allin-btn');
        if (raiseBtn && raiseInput) {
            const chips = Number(currentPlayer.chips || 0);
            const lastInc = this.getLastIncrement();
            const callNeed = Math.max(0, callAmount); // 需先补足的跟注额

            // 输入框表示“加到的总注（raise-to）”，范围：下限=至少加到，上限=我的当前总注+剩余筹码
            const minTarget = this.getMinRaiseTarget();
            const myBet = Number(currentPlayer.current_bet || 0);
            raiseInput.min = String(minTarget);
            raiseInput.max = String(myBet + chips);

            // 若筹码不足以达到“跟注额 + 最小增量”，加注按钮置灰
            raiseBtn.disabled = chips < (callNeed + lastInc);

            // 更新最小增量提示（同时展示“至少加到”目标总注）
            const hintEl = document.getElementById('min-increment-hint');
            if (hintEl) {
                const minTargetText = this.getMinRaiseTarget();
                hintEl.textContent = `（最小增量：${lastInc}；加注是在跟注的基础上再增加的下注。）`;
            }
        }
        if (allinBtn) {
            const chipsLeft = Number(currentPlayer.chips || 0);
            allinBtn.textContent = `全下 ${chipsLeft}`;
            allinBtn.disabled = chipsLeft <= 0;
        }
    }
    
    createCardElement(cardData) {
        const cardEl = document.createElement('div');
        cardEl.className = 'card';
        cardEl.setAttribute('data-suit', cardData.suit); // 添加花色属性用于CSS样式
        cardEl.innerHTML = `
            <div class="card-rank">${cardData.rank}</div>
            <div class="card-suit">${this.getSuitSymbol(cardData.suit)}</div>
        `;
        return cardEl;
    }


    
    createPlayerCircleElement(player, index, totalPlayers) {
        const playerEl = document.createElement('div');
        const position = this.calculatePlayerPosition(index, totalPlayers);
        
        // 获取玩家连接状态 - 使用后端返回的 connected 字段
        const isConnected = player.connected === true;
        
        playerEl.className = `player-circle 
                            ${player.user_id === this.user.user_id ? 'current-player' : ''} 
                            ${player.is_folded ? 'folded' : ''} 
                            ${player.is_current_turn ? 'current-turn' : ''}
                            ${player.is_all_in ? 'all-in' : ''}
                            ${player.is_ready ? 'ready' : ''}
                            ${player.win ? 'winner' : ''}
                            ${!isConnected ? 'offline' : ''}`;
        
        // 设置玩家在椭圆上的位置（百分比）
        playerEl.style.left = `${position.x}%`;
        playerEl.style.top = `${position.y}%`;
        
        // 如果是当前玩家，在专门的个人牌显示区域显示个人牌
        if (player.user_id === this.user.user_id && player.hole_cards && player.hole_cards.length > 0) {
            this.renderPlayerHoleCards(player.hole_cards);
        }
        
        // 庄家徽标（D）- 优先使用后端字段，缺失则使用兜底推导
        const dealerPos = Number(this.gameState?.dealer_position || 0) || Number(this.dealerPositionForRender || 0);
        const isDealer = dealerPos && Number(dealerPos) === Number(player.position);
        const dealerBadge = isDealer ? `<div class="dealer-badge" title="庄家" style="display:inline-block;min-width:18px;height:18px;line-height:18px;text-align:center;border-radius:50%;background:#ffb300;color:#000;font-weight:bold;font-size:12px;margin-left:6px;">D</div>` : '';
        
        // 离线状态标识
        const offlineBadge = !isConnected ? 
            `<div class="offline-badge" title="离线">⚫</div>` : '';
        
        // 准备状态指示器
        const readyIndicator = player.is_ready ? 
            `<div class="ready-indicator" title="已准备">✓</div>` : '';
        
        // 胜利状态 - 在游戏结束后阶段持续显示赢家圆圈效果，直到玩家点击准备按钮
        let isWinner = player.win;
        // 如果游戏已经结束，检查保存的赢家信息（赢家圆圈效果持续显示直到玩家点击准备）
        const stage = this.normalizeStage(this.gameState?.stage || 'waiting');
        if (stage === 'ended' && this.lastGameWinners.includes(player.user_id)) {
            isWinner = true;
        }
        
        // 添加winner类到玩家圆圈，显示金色边框效果
        if (isWinner) {
            playerEl.classList.add('winner');
        } else {
            playerEl.classList.remove('winner');
        }
        // 操作徽标（最近一次操作）
        const actionMap = { 'check': '过牌', 'call': '跟注', 'raise': '加注', 'fold': '弃牌', 'sb': '小盲', 'bb': '大盲' };
        let actionText = '';
        if (player && player.is_all_in) {
            actionText = 'ALL-IN';
        } else if (player && player.last_action && actionMap[player.last_action]) {
            actionText = actionMap[player.last_action];
        }
        const actionBadge = actionText ? `<div class="action-badge" style="display:inline-block;padding:2px 6px;border-radius:10px;background:rgba(255,255,255,0.85);color:#000;font-size:12px;margin-top:4px;">${actionText}</div>` : '';
        // 手牌净变化（仅在非0时展示）- 在游戏结束后阶段持续显示赢家的筹码变化
        let showDelta = (typeof player.hand_delta === 'number' && player.hand_delta !== 0);
        let deltaValue = player.hand_delta;
        
        // 如果游戏已经结束，检查保存的赢家筹码变化信息
        if (stage === 'ended' && this.lastGameWinners.includes(player.user_id)) {
            const savedDelta = this.lastGameWinnerDeltas[player.user_id];
            if (savedDelta !== undefined && savedDelta !== 0) {
                showDelta = true;
                deltaValue = savedDelta;
            }
        }
        
        const deltaHtml = showDelta
            ? `<div class="player-delta ${deltaValue > 0 ? 'pos' : 'neg'}">
                   ${deltaValue > 0 ? '+' : ''}${deltaValue}
               </div>`
            : '';
        
        playerEl.innerHTML = `
            <div class="player-nickname">${player.nickname}${dealerBadge}${offlineBadge}</div>
            <div class="player-chips-circle">${player.chips}</div>
            ${deltaHtml}
            ${player.current_bet > 0 ? `<div class="player-bet-circle">下注: ${player.current_bet}</div>` : ''}
            <div class="player-status-circle">${this.getPlayerStatusText(player)}</div>
            ${actionBadge}
            ${readyIndicator}
        `;
        
        // 设置data-user-id属性用于后续更新
        playerEl.setAttribute('data-user-id', player.user_id);
        
        return playerEl;
    }
    
    // 在专门的个人牌显示区域渲染玩家个人牌
    renderPlayerHoleCards(holeCards) {
        const playerHoleCardsEl = document.getElementById('player-hole-cards');
        if (playerHoleCardsEl) {
            playerHoleCardsEl.innerHTML = '';
            holeCards.forEach(card => {
                const cardEl = this.createCardElement(card);
                playerHoleCardsEl.appendChild(cardEl);
            });
        }
    }
    
    // 从游戏状态中提取当前用户的手牌并渲染
    renderPlayerHoleCardsFromGameState() {
        if (!this.gameState || !this.gameState.players || !this.user) {
            return;
        }
        
        // 查找当前用户在游戏状态中的信息
        const currentPlayer = this.gameState.players.find(p => p.user_id === this.user.user_id);
        if (currentPlayer && currentPlayer.hole_cards && currentPlayer.hole_cards.length > 0) {
            this.renderPlayerHoleCards(currentPlayer.hole_cards);
        } else {
            // 如果没有手牌数据，清空手牌显示区域
            const playerHoleCardsEl = document.getElementById('player-hole-cards');
            if (playerHoleCardsEl) {
                playerHoleCardsEl.innerHTML = '';
            }
        }
    }
    
    calculatePlayerPosition(index, totalPlayers) {
        // 椭圆参数：中心点(50%, 50%)
        const centerX = 50; // 百分比
        const centerY = 50; // 百分比
        const radiusX = 48; // 调整椭圆长轴半径，让左右玩家也贴边
        const radiusY = 48; // 调整椭圆短轴半径，让所有方向均匀贴边
        
        // 计算玩家在椭圆上的角度（均匀分布，从正下方开始顺时针）
        // 让当前玩家（index=0）总是处于正下方（270度）
        // 当只有一个玩家时，直接放在正下方
        if (totalPlayers === 1) {
            return { x: 50, y: 98 }; // 正下方底部
        }
        
        // 多个玩家时，从正下方开始顺时针排列
        // 角度计算：90度 = π/2，浏览器坐标系中 y 轴向下，π/2 对应正下方
        const angle = (index / totalPlayers) * 2 * Math.PI + (Math.PI / 2);
        
        // 计算椭圆上的坐标（百分比）- 玩家贴在牌桌外圈
        const x = centerX + radiusX * Math.cos(angle);
        const y = centerY + radiusY * Math.sin(angle);
        
        // 确保玩家在可见范围内（贴近牌桌边缘）
        const adjustedX = Math.max(2, Math.min(98, x));
        const adjustedY = Math.max(2, Math.min(98, y));
        
        return { x: adjustedX, y: adjustedY };
    }
    
    renderPlayerCards(player) {
        if (player.user_id === this.user.user_id || this.gameState.stage === 'showdown') {
            // 显示自己的牌或摊牌时显示所有牌
            return player.hole_cards.map(card => 
                `<div class="card">${card.rank}${this.getSuitSymbol(card.suit)}</div>`
            ).join('');
        } else if (player.is_folded) {
            return '已弃牌';
        } else {
            return '??'; // 其他玩家的牌不显示
        }
    }
    
    getPlayerStatusText(player) {
        if (player.is_folded) return '已弃牌';
        if (player.is_all_in) return '全下';
        if (player.is_current_turn) return '行动中';
        if (player.is_ready) return '已准备';
        return '';
    }
    
    getSuitSymbol(suit) {
        const symbols = {
            'hearts': '♥',
            'diamonds': '♦',
            'clubs': '♣',
            'spades': '♠'
        };
        return symbols[suit] || suit[0].toUpperCase();
    }

    // 依据当前 gameState 推导庄家位置（兜底逻辑）
    computeDealerPositionForRender() {
        const gs = this.gameState;
        if (!gs || !Array.isArray(gs.players) || gs.players.length === 0) return 0;

        // 1) 若后端已提供，则直接使用
        const provided = Number(gs.dealer_position || 0);
        if (provided) return provided;

        // 收集活跃玩家的座位号（未弃牌）
        const active = gs.players.filter(p => p && !p.is_folded);
        const positions = active
            .map(p => Number(p.position))
            .filter(n => !isNaN(n))
            .sort((a, b) => a - b);
        if (positions.length === 0) return 0;

        // 工具：取 positions 中 pos 的前一位/前两位（环绕）
        const prevOf = (pos) => {
            const i = positions.indexOf(Number(pos));
            if (i === -1) return 0;
            return positions[(i - 1 + positions.length) % positions.length] || 0;
        };
        const prev2Of = (pos) => {
            const i = positions.indexOf(Number(pos));
            if (i === -1) return 0;
            return positions[(i - 2 + positions.length) % positions.length] || 0;
        };

        // 2) 若有小盲 sb：两人局=sb，多人局=sb 的前一位
        const sb = gs.players.find(p => p && p.last_action === 'sb');
        if (sb) {
            if (active.length === 2) return Number(sb.position || 0);
            return prevOf(sb.position);
        }

        // 3) 若仅看到大盲 bb：
        const bb = gs.players.find(p => p && p.last_action === 'bb');
        if (bb) {
            if (active.length === 2) {
                // 两人局：庄家=非 bb 的那位
                const other = positions.find(x => x !== Number(bb.position));
                return Number(other || 0);
            }
            // 多人局：dealer -> sb -> bb，故 dealer 为 bb 的前两位
            return prev2Of(bb.position);
        }

        // 4) 两人局额外兜底：用当前下注额推断SB/BB
        if (active.length === 2) {
            const a = active[0];
            const b = active[1];
            const abet = Number(a.current_bet || 0);
            const bbet = Number(b.current_bet || 0);
            if (abet > 0 && bbet > 0) {
                // 较小的是小盲 -> 庄家
                if (abet < bbet) return Number(a.position || 0);
                if (bbet < abet) return Number(b.position || 0);
            } else if (abet > 0 && bbet === 0) {
                // 仅a有下注，视为BB -> 庄家为另一个(b)
                return Number(b.position || 0);
            } else if (bbet > 0 && abet === 0) {
                // 仅b有下注，视为BB -> 庄家为另一个(a)
                return Number(a.position || 0);
            }
        }

        // 5) 无法推导则不显示
        return 0;
    }

    // 摊牌阶段展示所有仍在局内玩家的手牌
    renderShowdownReveal(state) {
        if (!state) return;
        // 容器：优先使用现有ID，否则创建一个固定位置的overlay
        let container = document.getElementById('showdown-reveal');
        if (!container) {
            container = document.createElement('div');
            container.id = 'showdown-reveal';
            container.style.position = 'fixed';
            container.style.bottom = '16px';
            container.style.left = '50%';
            container.style.transform = 'translateX(-50%)';
            container.style.background = 'rgba(0,0,0,0.7)';
            container.style.color = '#fff';
            container.style.padding = '8px 12px';
            container.style.borderRadius = '8px';
            container.style.zIndex = '9999';
            container.style.maxWidth = '90%';
            container.style.fontSize = '14px';
            container.style.boxShadow = '0 2px 8px rgba(0,0,0,0.3)';
            document.body.appendChild(container);
        }
        // 确保每次渲染时显示出来（即便之前被关闭/隐藏）
        container.style.display = 'block';
        // 为右上角关闭按钮预留空间，避免按钮压近内容
        container.style.paddingRight = '28px';
        // 清空并渲染
        container.innerHTML = '';
        // 加入右上角关闭按钮
        const closeBtn = document.createElement('button');
        closeBtn.className = 'showdown-close';
        closeBtn.textContent = '×';
        closeBtn.style.position = 'absolute';
        closeBtn.style.top = '6px';
        closeBtn.style.right = '8px';
        closeBtn.style.background = 'transparent';
        closeBtn.style.color = '#fff';
        closeBtn.style.border = 'none';
        closeBtn.style.cursor = 'pointer';
        closeBtn.style.fontSize = '18px';
        closeBtn.style.lineHeight = '18px';
        closeBtn.style.padding = '0';
        closeBtn.title = '关闭';
        closeBtn.addEventListener('click', () => {
            container.style.display = 'none';
        });
        container.appendChild(closeBtn);
        const title = document.createElement('div');
        title.style.fontWeight = 'bold';
        title.style.marginBottom = '6px';
        // 为右上角关闭按钮预留标题右侧空间
        title.style.marginRight = '28px';
        title.textContent = `摊牌：公开局内或自愿亮牌的手牌`;
        container.appendChild(title);

        // 标题下方的操作区域，避免与右上角“×”靠太近
        const actions = document.createElement('div');
        actions.style.display = 'flex';
        actions.style.alignItems = 'center';
        actions.style.gap = '8px';
        actions.style.marginTop = '6px';
        container.appendChild(actions);

        // 如果当前用户未在公开列表中，提供“摊牌”按钮（自愿亮牌给所有人）
        const alreadyRevealed = Array.isArray(state.showdown_reveal) && state.showdown_reveal.some(p => p.user_id === this.user?.user_id);
        if (!alreadyRevealed) {
            const revealBtn = document.createElement('button');
            revealBtn.textContent = '摊牌';
            revealBtn.style.padding = '4px 8px';
            revealBtn.style.background = '#1976d2';
            revealBtn.style.color = '#fff';
            revealBtn.style.border = 'none';
            revealBtn.style.borderRadius = '4px';
            revealBtn.style.cursor = 'pointer';
            revealBtn.addEventListener('click', () => {
                try {
                    this.sendMessage({ type: 'manual_show_cards' });
                    this.showToast('已请求自愿摊牌', 'info');
                } catch (e) {
    
                }
            });
            actions.appendChild(revealBtn);
        }

        const list = document.createElement('div');
        list.style.display = 'flex';
        list.style.flexWrap = 'wrap';
        list.style.gap = '8px';

        (Array.isArray(state.showdown_reveal) ? state.showdown_reveal : []).forEach(p => {
            const item = document.createElement('div');
            item.style.background = 'rgba(255,255,255,0.1)';
            item.style.border = '1px solid rgba(255,255,255,0.2)';
            item.style.borderRadius = '6px';
            item.style.padding = '6px 8px';
            item.style.display = 'flex';
            item.style.alignItems = 'center';
            item.style.gap = '6px';

            const info = document.createElement('div');
            info.textContent = `${p.nickname}（座位${p.position}）`;
            info.style.marginRight = '6px';
            item.appendChild(info);

            const cardsWrap = document.createElement('div');
            cardsWrap.style.display = 'flex';
            cardsWrap.style.gap = '4px';
            (p.hole_cards || []).forEach(card => {
                const cardEl = document.createElement('div');
                cardEl.className = 'card';
                cardEl.style.width = '28px';
                cardEl.style.height = '40px';
                cardEl.style.display = 'flex';
                cardEl.style.flexDirection = 'column';
                cardEl.style.alignItems = 'center';
                cardEl.style.justifyContent = 'center';
                cardEl.style.background = '#fff';
                cardEl.style.color = '#000';
                cardEl.style.borderRadius = '4px';
                cardEl.style.fontSize = '12px';
                cardEl.style.boxShadow = '0 1px 3px rgba(0,0,0,0.25)';
                cardEl.innerHTML = `
                    <div>${card.rank}</div>
                    <div>${this.getSuitSymbol(card.suit)}</div>
                `;
                // 按花色设置显式颜色，确保跨浏览器显示一致
                const isRedSuit = (card.suit === 'hearts' || card.suit === 'diamonds');
                cardEl.style.color = isRedSuit ? '#d32f2f' : '#000'; // 红桃/方块红色，其余黑色
                cardEl.style.border = isRedSuit ? '1px solid rgba(211,47,47,0.6)' : '1px solid rgba(0,0,0,0.2)';
                cardEl.setAttribute('data-suit', card.suit);
                cardsWrap.appendChild(cardEl);
            });
            item.appendChild(cardsWrap);

            list.appendChild(item);
        });

        container.appendChild(list);
    }
    
    // 显示重连按钮
    showReconnectButton() {
        const reconnectBtn = document.getElementById('reconnect-btn');
        if (reconnectBtn) {
            reconnectBtn.style.display = 'block';
        }
    }
    
    // 隐藏重连按钮
    hideReconnectButton() {
        const reconnectBtn = document.getElementById('reconnect-btn');
        if (reconnectBtn) {
            reconnectBtn.style.display = 'none';
        }
    }
    
    // 手动重连方法
    manualReconnect() {
        // 如果已经连接，不执行重连
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.showToast('已连接，无需重连', 'info');
            return;
        }
        
        // 重置重连计数器
        this.reconnectAttempts = 0;
        
        // 显示重连中提示
        this.showToast('正在尝试重新连接...', 'info');
        
        // 关闭当前连接（如果存在）
        if (this.socket) {
            this.isManuallyClosed = true;
            this.socket.close();
            this.socket = null;
        }
        
        // 延迟一点时间后重新初始化连接
        setTimeout(() => {
            this.isManuallyClosed = false;
            this.initializeSocket();
        }, 500);
    }
    
    setupEventListeners() {
        // 准备按钮 - 使用更可靠的事件绑定方式
        const readyBtn = document.getElementById('ready-btn');
        if (readyBtn) {
            readyBtn.addEventListener('click', () => this.setReady());
        } else {
        }
        
        const unreadyBtn = document.getElementById('unready-btn');
        if (unreadyBtn) {
            unreadyBtn.addEventListener('click', () => this.setUnready());
        } else {
        }
        // 刷新房间玩家按钮：主动拉取并重绘围坐（直接绑定）
        document.getElementById('refresh-room-btn')?.addEventListener('click', async () => {
            const btn = document.getElementById('refresh-room-btn');
            if (btn) btn.disabled = true;
            try {
                // 先请求后端做一次心跳清理
                try {
                    await fetch('/api/cleanup-stale', { method: 'POST' });
                } catch (probeErr) {
                }
                this.gameState = null;
                await this.updateRoomPlayers();
                this.showToast('房间玩家已刷新', 'info');
            } catch (e) {
                this.showToast('刷新失败，请重试', 'error');
            } finally {
                if (btn) btn.disabled = false;
            }
        });

        // 兜底：全局事件代理，确保按钮即使动态渲染也能触发
        document.addEventListener('click', async (e) => {
            const target = e.target;
            
            // 处理准备按钮点击
            if (target && target.id === 'ready-btn') {
                this.setReady();
                return;
            }
            
            // 处理取消准备按钮点击
            if (target && target.id === 'unready-btn') {
                this.setUnready();
                return;
            }
            
            // 处理刷新房间玩家按钮
            if (target && target.id === 'refresh-room-btn') {
                try {
                    target.disabled = true;
                    // 先请求后端做一次心跳清理
                    try {
                        await fetch('/api/cleanup-stale', { method: 'POST' });
                    } catch (probeErr) {
                    }
                    this.gameState = null;
                    await this.updateRoomPlayers();
                    this.showToast('房间玩家已刷新', 'info');
                } catch (err) {
                    this.showToast('刷新失败，请重试', 'error');
                } finally {
                    target.disabled = false;
                }
            }
        });

        
        // 操作按钮
        document.getElementById('fold-btn')?.addEventListener('click', () => this.fold());
        document.getElementById('check-btn')?.addEventListener('click', () => this.check());
        document.getElementById('call-btn')?.addEventListener('click', () => this.call());
        document.getElementById('raise-btn')?.addEventListener('click', () => {
            const inputEl = document.getElementById('raise-amount');
            const raw = inputEl ? Number(inputEl.value || 0) : 0; // 目标总注（raise-to）
            if (!this.gameState || !Array.isArray(this.gameState.players)) return;

            const me = this.gameState.players.find(p => p.user_id === this.user.user_id);
            if (!me) return;
            const chips = Number(me.chips || 0);
            const myBet = Number(me.current_bet || 0);
            const minTarget = this.getMinRaiseTarget(); // 当前台面总注 + 最小增量

            // 校验：目标总注不得低于“至少加到”
            if (raw < minTarget) {
                this.showToast(`至少加到 ${minTarget}`, 'error');
                return;
            }
            // 我需要补的筹码 = 目标总注 - 我的当前总注
            const need = Math.max(0, raw - myBet);
            if (chips < need) {
                this.showToast(`筹码不足：至少需要 ${need}`, 'error');
                return;
            }
            // 发送到后端的 amount 是“目标总注（raise-to）”
            this.raise(raw);
        });

        // 全下（不足额加注不重开行动由后端处理）
        document.getElementById('allin-btn')?.addEventListener('click', () => {
            if (!this.gameState || !Array.isArray(this.gameState.players)) return;
            const me = this.gameState.players.find(p => p.user_id === this.user.user_id);
            if (!me) return;
            const myBet = Number(me.current_bet || 0);
            const chips = Number(me.chips || 0);
            if (chips <= 0) {
                this.showToast('没有可用筹码，无法全下', 'error');
                return;
            }
            const target = myBet + chips; // 目标总注=当前总注+剩余筹码
            this.raise(target);
        });
        
        // 单玩家弹窗按钮
        document.getElementById('single-player-immediate-end')?.addEventListener('click', () => {
            // 立即结束游戏
            this.sendSinglePlayerDecision('end');
            this.hideSinglePlayerDialog();
        });

        // 重置筹码按钮（使用弹窗进行范围/玩家/验证码选择）
        document.getElementById('reset-chips-btn')?.addEventListener('click', async () => {
            try {
                return await this.openResetChipsDialog();
            } catch (e) {
                this.showToast('重置筹码失败，请重试', 'error');
            }
        });
        
        // 手动重连按钮
        document.getElementById('reconnect-btn')?.addEventListener('click', () => {
            this.manualReconnect();
        });

        
        // 页面退出/隐藏时主动告知后端离开并关闭socket，避免僵尸连接
        const sendLeave = () => {
            try {
                this.sendMessage({ type: 'player_leave' });
            } catch (e) {}
            try {
                this.isManuallyClosed = true;
                this.socket?.close();
            } catch (e) {}
        };
        window.addEventListener('pagehide', sendLeave);
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden') sendLeave();
        });
        window.addEventListener('beforeunload', sendLeave);



    }
    
    disableActionButtons() {
        // 只禁用“游戏操作区”的按钮，避免误伤准备区按钮
        const buttons = document.querySelectorAll('#game-action-section .action-btn');
        buttons.forEach(btn => btn.disabled = true);
    }
    
    enableActionButtons() {
        // 仅启用“游戏操作区”的按钮
        const buttons = document.querySelectorAll('#game-action-section .action-btn');
        buttons.forEach(btn => btn.disabled = false);
    }
    
    async handleChipsReset(data) {
        if (data.scope === 'all') {
            this.showToast(`已将所有人筹码重置为 ${data.default_chips}`, 'info');
        } else {
            // 构造昵称列表，兼容多选与不同后端载荷；确保尽可能显示具体昵称
            let names = '';
            const tryMap = (ids, list) => {
                if (!Array.isArray(ids) || ids.length === 0) return '';
                const arr = ids.map(uid => {
                    const p = list.find(x => x && String(x.user_id) === String(uid));
                    return p ? (p.nickname || String(uid)) : String(uid);
                });
                return arr.join('、');
            };
            try {
                if (Array.isArray(data.nicknames) && data.nicknames.length > 0) {
                    names = data.nicknames.join('、');
                } else if (Array.isArray(data.affected) && data.affected.length > 0) {
                    // 后端标准载荷：affected[{user_id,nickname}]
                    names = (data.affected || []).map(p => (p && (p.nickname || String(p.user_id)))).filter(Boolean).join('、');
                } else if (Array.isArray(data.players) && data.players.length > 0) {
                    // 直接从对象数组中提取昵称
                    names = (data.players || []).map(p => p && p.nickname).filter(Boolean).join('、');
                } else if (Array.isArray(data.affected_players) && data.affected_players.length > 0) {
                    // 兼容另一种字段名
                    names = (data.affected_players || []).map(p => p && p.nickname).filter(Boolean).join('、');
                } else if (Array.isArray(data.user_ids) && data.user_ids.length > 0) {
                    // 1) 先用当前 gameState
                    const src1 = (this.gameState && Array.isArray(this.gameState.players)) ? this.gameState.players : [];
                    names = tryMap(data.user_ids, src1);
                    // 2) 若仍为空或映射不全，则拉取 /api/players 按房间+在线再映射
                    if (!names || /^\s*$/.test(names)) {
                        try {
                            const resp = await fetch('/api/players');
                            const js = await resp.json().catch(() => ({ players: [] }));
                            let list = Array.isArray(js.players) ? js.players : [];
                            // 在线与房间过滤
                            list = list.filter(p => p && p.connected === true);
                            const roomId = this.user?.room_id || this.currentRoomId || window.ROOM_ID;
                            if (roomId != null && roomId !== '') {
                                list = list.filter(p => String(p.room_id ?? p.roomId ?? '') === String(roomId));
                            }
                            names = tryMap(data.user_ids, list);
                        } catch (e2) {}
                    }
                    // 3) 若仍为空，最终用 user_ids 字符串展示
                    if (!names || /^\s*$/.test(names)) {
                        names = data.user_ids.map(String).join('、');
                    }
                } else if (data.nickname) {
                    names = data.nickname;
                } else if (data.user_id) {
                    names = String(data.user_id);
                }
            } catch (e) {}
            // 最终提示（尽量为具体昵称）
            this.showToast(`已将 ${names && names.trim() ? names : '所选玩家'} 的筹码重置为 ${data.default_chips}`, 'info');
        }
        // 刷新围坐显示
        this.gameState = null;
        await this.updateRoomPlayersForce();
    }

    // 重置筹码弹窗（范围选择+玩家昵称选择+验证码）
    async openResetChipsDialog() {
        // 创建遮罩和对话框
        const overlay = document.createElement('div');
        overlay.style.position = 'fixed';
        overlay.style.left = '0';
        overlay.style.top = '0';
        overlay.style.right = '0';
        overlay.style.bottom = '0';
        overlay.style.background = 'rgba(0,0,0,0.45)';
        overlay.style.zIndex = '10000';
        overlay.style.display = 'flex';
        overlay.style.alignItems = 'center';
        overlay.style.justifyContent = 'center';

        const dialog = document.createElement('div');
        dialog.style.background = '#fff';
        dialog.style.color = '#000';
        dialog.style.padding = '16px';
        dialog.style.borderRadius = '8px';
        dialog.style.minWidth = '320px';
        dialog.style.maxWidth = '90%';
        dialog.style.boxShadow = '0 6px 24px rgba(0,0,0,0.2)';
        dialog.innerHTML = `
            <div style="font-weight:600;font-size:16px;margin-bottom:10px;">重置筹码</div>
            <div style="display:flex;flex-direction:column;gap:10px;">
                <label style="display:flex;flex-direction:column;gap:6px;">
                    <span>重置范围</span>
                    <select id="reset-scope" style="padding:6px 8px;">
                        <option value="all">所有人</option>
                        <option value="selected">选择玩家</option>
                    </select>
                </label>
                <label id="reset-player-wrap" style="display:none;flex-direction:column;gap:6px;">
                    <span>选择玩家（昵称）</span>
                    <select id="reset-player" multiple style="padding:6px 8px; min-width: 200px; min-height: 80px;"></select>
                </label>
                <label style="display:flex;flex-direction:column;gap:6px;">
                    <span>验证码</span>
                    <input id="reset-code" type="text" placeholder="请输入验证码" style="padding:6px 8px;border:1px solid #ddd;border-radius:4px;" />
                </label>
                <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:6px;">
                    <button id="reset-cancel" class="action-btn btn-secondary">取消</button>
                    <button id="reset-confirm" class="action-btn btn-warning">确认重置</button>
                </div>
            </div>
        `;
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        // 数据加载：玩家列表（昵称）
        let players = [];
        try {
            const data = await this.getRoomPlayers();
            players = Array.isArray(data.players) ? data.players : [];
            // 仅保留当前房间的玩家，防止跨房间数据混入
            try {
                const roomId = this.user?.room_id || this.currentRoomId || window.ROOM_ID;
                if (roomId != null && roomId !== '') {
                    players = players.filter(p => String(p.room_id ?? p.roomId) === String(roomId));
                }
            } catch (e) {
                // 忽略过滤异常，回退为后端返回列表
            }
            // 仅保留在线玩家
            players = (players || []).filter(p => p && p.connected === true);
        } catch (e) {
        }

        const scopeSel = dialog.querySelector('#reset-scope');
        const playerWrap = dialog.querySelector('#reset-player-wrap');
        const playerSel = dialog.querySelector('#reset-player');
        const codeInput = dialog.querySelector('#reset-code');
        const btnCancel = dialog.querySelector('#reset-cancel');
        const btnConfirm = dialog.querySelector('#reset-confirm');

        // 填充玩家下拉：文本=昵称，值=user_id
        const fillPlayers = () => {
            if (!playerSel) return;
            playerSel.innerHTML = '';
            players.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.user_id;
                opt.textContent = p.nickname;
                playerSel.appendChild(opt);
            });
        };

        const refreshVisibility = () => {
            if (scopeSel.value === 'selected') {
                playerWrap.style.display = 'flex';
                if (playerSel.options.length === 0) fillPlayers();
            } else {
                playerWrap.style.display = 'none';
            }
        };

        scopeSel.addEventListener('change', refreshVisibility);
        refreshVisibility();

        const close = () => {
            try { document.body.removeChild(overlay); } catch (e) {}
        };
        btnCancel.addEventListener('click', () => close());

        btnConfirm.addEventListener('click', async () => {
            try {
                const scope = scopeSel.value;
                const code = String(codeInput.value || '').trim();
                if (!code) {
                    this.showToast('请输入验证码', 'error');
                    return;
                }
                let userIds = [];
                if (scope === 'selected') {
                    userIds = Array.from(playerSel?.selectedOptions || []).map(o => o.value).filter(Boolean);
                    if (userIds.length === 0) {
                        this.showToast('请选择至少一位玩家', 'error');
                        return;
                    }
                }
                const payload = (scope === 'all')
                    ? { scope, code }
                    : { scope: 'selected', user_ids: userIds, code };
                const resp = await fetch('/api/reset-chips', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    this.showToast(err.detail || '重置失败', 'error');
                    return;
                }
                const js = await resp.json().catch(() => ({}));
                await this.updateRoomPlayers();
                if (js && js.scope === 'all') {
                    this.showToast('已重置所有人筹码为默认值', 'success');
                } else {
                    this.showToast('已重置所选玩家筹码为默认值', 'success');
                }
                close();
            } catch (e) {
                this.showToast('重置失败，请重试', 'error');
            }
        });

        return true;
    }


    updateGameStage(stage) {
        const stageEl = document.getElementById('game-stage');
        if (stageEl) {
            const stageNames = {
                'preflop': '翻牌前',
                'flop': '翻牌',
                'turn': '转牌', 
                'river': '河牌',
                'showdown': '摊牌',
                'ended': '结束'
            };
            stageEl.textContent = stageNames[stage] || stage;
        }
    }
    
    
    
    showToast(message, type = 'info') {
        // 简单的toast实现
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
    
    showErrorMessage(message) {
        this.showToast(message, 'error');
    }
    
    showDisconnectedMessage() {
        this.showToast('连接已断开，正在尝试重新连接...', 'warning');
    }
    
    hideConnectionMessages() {
        // 隐藏连接状态消息
    }
    
    startHeartbeat() {
        setInterval(() => {
            if (this.isConnected) {
                this.sendMessage({ type: 'ping' });
            }
        }, 25000); // 每25秒发送一次心跳
    }
    
    getSessionToken() {
        try {
            // 简化的cookie认证（符合技术方案）
            const cookie = document.cookie.split(';').find(c => c.trim().startsWith('session_token='));
            const token = cookie ? cookie.split('=')[1] : null;
            
            if (token) {
                return token;
            }
            
            this.showToast('无法获取会话令牌，请重新登录', 'error');
            return null;
        } catch (e) {
            return null;
        }
    }
    

}













/**
 * 仅按屏幕宽度等比例缩放牌桌容器 #table-stage，并居中显示
 * 不改变内部元素尺寸/围坐布局；其他区域可自由调整
 */
function fitTableWidth() {
    const stage = document.getElementById('table-stage');
    if (!stage) return;
    const baseWidth = 800; // 设计基准宽度
    const vw = document.documentElement.clientWidth;
    const padding = 24;    // 视口左右预留
    const scale = Math.min(1, (vw - padding) / baseWidth);
    stage.style.transformOrigin = 'center top';
    stage.style.transform = `scale(${scale})`;
    stage.style.marginLeft = 'auto';
    stage.style.marginRight = 'auto';
}

function initTableWidthResponsive() {
    fitTableWidth();
    window.addEventListener('resize', fitTableWidth);
    window.addEventListener('orientationchange', () => setTimeout(fitTableWidth, 200));
}

// 初始化游戏
document.addEventListener('DOMContentLoaded', function() {

    // 从页面模板中获取用户数据
    const userDataElement = document.getElementById('user-data');
    
    if (userDataElement) {
        try {
            const userData = JSON.parse(userDataElement.textContent);
            
            // 创建PokerGame实例
            window.pokerGame = new PokerGame(userData);
            
            // 手机端：牌桌按屏幕宽度自适配并居中
            initTableWidthResponsive();
            // 进入房间后自动聚焦到牌桌区域（仅移动端）
            try {
                if (document.documentElement.clientWidth <= 768) {
                    document.getElementById('table-stage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            } catch (e) {}
        } catch (error) {
            window.location.href = '/';
        }
    } else {
        window.location.href = '/';
    }
});