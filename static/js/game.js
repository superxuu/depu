class PokerGame {
    constructor(user) {
        this.user = user;
        this.socket = null;
        this.gameState = null;
        this.isConnected = false;
        
        this.initializeSocket();
        this.startHeartbeat();
    }
    
    initializeSocket() {
        try {
            this.socket = new WebSocket(`ws://${window.location.host}/ws/game`);
            
            this.socket.onopen = () => {
                this.isConnected = true;
                this.hideConnectionMessages();
                this.authenticate();
            };
            
            this.socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    console.error('解析消息错误:', error);
                }
            };
            
            this.socket.onclose = (event) => {
                this.isConnected = false;
                this.showDisconnectedMessage();
                
                // 自动重连机制（如果不是手动关闭）
                if (!this.isManuallyClosed) {
                    setTimeout(() => {
                        this.initializeSocket();
                    }, 3000);
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
        
        // 设置认证超时检查（5秒）
        this.authTimeout = setTimeout(() => {
            if (!this.isConnected) {
                this.showErrorMessage('认证超时，请检查网络连接');
            }
        }, 5000);
    }
    
    handleMessage(data) {
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
            
            case 'player_joined':
                this.handlePlayerJoined(data);
                break;
            case 'player_left':
                this.handlePlayerLeft(data);
                break;
            case 'player_disconnected':
                this.handlePlayerDisconnected(data);
                break;
            case 'game_started':
                this.handleGameStarted();
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
            default:
                console.warn('未知的消息类型:', data.type);
        }
    }
    
    handleAuthSuccess(data) {
        // 清除认证超时
        if (this.authTimeout) {
            clearTimeout(this.authTimeout);
            this.authTimeout = null;
        }
        
        this.isConnected = true;
        this.hideConnectionMessages();
        console.log('认证成功');
        
        // 更新用户信息（确保session_token一致）
        if (this.user) {
            this.user = { ...this.user, ...data.user };
        }
        
        // 认证成功后设置事件监听器
        this.setupEventListeners();
        // 认证成功后立即更新玩家列表
        this.updateRoomPlayers();
        
        this.showToast('连接成功', 'success');
    }
    
    handleGameState(gameState) {
        this.gameState = gameState;
        this.renderGameState();
    }
    
    handleGameStateUpdate(gameState) {
        this.gameState = gameState;
        
        // 检查游戏阶段，如果是结束阶段，不调用renderGameState以避免覆盖准备按钮
        const stage = this.normalizeStage(gameState.stage);
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
    
    
    
    handlePlayerJoined(data) {
        // 提示并主动刷新玩家列表，避免依赖后端额外广播
        this.showToast(`${data.nickname} 加入了游戏`, 'info');
        setTimeout(() => this.updateRoomPlayers(), 150);
    }
    
    handlePlayerLeft(data) {
        // 提示并主动刷新玩家列表
        this.showToast(`玩家 ${data.nickname || data.user_id} 离开了游戏`, 'info');
        setTimeout(() => this.updateRoomPlayers(), 150);
    }
    
    handlePlayerDisconnected(data) {
        this.showToast(`玩家 ${data.user_id} 断开连接`, 'warning');
        setTimeout(() => this.updateRoomPlayers(), 150);
    }
    
    handleGameStarted() {
        this.showToast('游戏开始！', 'success');
        this.updateGameStage('preflop');
        // 游戏开始，切换到游戏操作按钮
        this.toggleGameActions(true);
    }
    
    handleGameEnded(data) {
        console.log('收到game_ended消息:', data);
        
        if (data.winner && data.winner.user_id === this.user.user_id) {
            this.showToast('恭喜你获胜！', 'success');
        } else if (data.winner) {
            this.showToast(`${data.winner.nickname} 获胜！`, 'info');
        }
        this.updateGameStage('ended');
        
        // 强制显示准备按钮区域，隐藏游戏操作区域
        const readySection = document.getElementById('ready-section');
        const gameActionSection = document.getElementById('game-action-section');
        
        console.log('准备按钮区域元素:', readySection);
        console.log('游戏操作区域元素:', gameActionSection);
        
        if (readySection) {
            readySection.style.display = 'flex';
            console.log('准备按钮区域已显示');
        } else {
            console.error('找不到准备按钮区域元素');
        }
        
        if (gameActionSection) {
            gameActionSection.style.display = 'none';
            console.log('游戏操作区域已隐藏');
        } else {
            console.error('找不到游戏操作区域元素');
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
    
    setReady() {
        this.sendMessage({
            type: 'player_ready',
            is_ready: true
        });
    }
    
    setUnready() {
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
        
        if (readySection && gameActionSection) {
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
    
    sendAction(action, amount = 0) {
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

        let players = [];
        // 优先使用 WebSocket 推送的 gameState 数据，这是最实时的权威来源
        if (this.gameState && this.gameState.players && this.gameState.players.length > 0) {
            players = this.gameState.players;
        } else {
            // 仅在 gameState 不可用时（如页面首次加载），回退到 API
            try {
                const response = await fetch('/api/players');
                if (response.ok) {
                    const data = await response.json();
                    players = (data.players || []).filter(p => p && p.connected === true);
                } else {
                    console.error('API 获取玩家列表失败');
                    return;
                }
            } catch (error) {
                console.error('API 请求玩家信息失败:', error);
                return;
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
                    console.error(`渲染玩家 ${player.nickname} 时出错:`, error);
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
                return await response.json();
            }
            return [];
        } catch (error) {
            console.error('获取房间玩家失败:', error);
            return [];
        }
    }
    
    async updateRoomPlayers() {
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
        // “过牌”按钮始终可用
        if (checkBtn) {
            checkBtn.disabled = false;
        }
        
        const raiseBtn = document.getElementById('raise-btn');
        const raiseInput = document.getElementById('raise-amount');
        if (raiseBtn && raiseInput) {
            const minRaise = safeCurrentBet + safeMinBet;
            raiseInput.min = String(minRaise);
            // 保护：无 chips 时设置为0
            raiseInput.max = String(Number(currentPlayer.chips || 0));
            // 不能加注时置灰，但不隐藏
            raiseBtn.disabled = Number(currentPlayer.chips || 0) < minRaise;
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
        
        playerEl.className = `player-circle 
                            ${player.user_id === this.user.user_id ? 'current-player' : ''} 
                            ${player.is_folded ? 'folded' : ''} 
                            ${player.is_current_turn ? 'current-turn' : ''}
                            ${player.is_all_in ? 'all-in' : ''}
                            ${player.is_ready ? 'ready' : ''}
                            ${player.win ? 'winner' : ''}`;
        
        // 设置玩家在椭圆上的位置（百分比）
        playerEl.style.left = `${position.x}%`;
        playerEl.style.top = `${position.y}%`;
        
        // 如果是当前玩家，在专门的个人牌显示区域显示个人牌
        if (player.user_id === this.user.user_id && player.hole_cards && player.hole_cards.length > 0) {
            this.renderPlayerHoleCards(player.hole_cards);
        }
        
        // 准备状态指示器
        const readyIndicator = player.is_ready ? 
            `<div class="ready-indicator" title="已准备">✓</div>` : '';
        // 胜利徽标（摊牌后）
        const winBadge = player.win ? `<div class="win-badge" title="本手牌获胜">WIN</div>` : '';
        // 手牌净变化（仅在非0时展示）
        const deltaHtml = (typeof player.hand_delta === 'number' && player.hand_delta !== 0)
            ? `<div class="player-delta ${player.hand_delta > 0 ? 'pos' : 'neg'}">
                   ${player.hand_delta > 0 ? '+' : ''}${player.hand_delta}
               </div>`
            : '';
        
        playerEl.innerHTML = `
            <div class="player-nickname">${player.nickname}</div>
            <div class="player-chips-circle">${player.chips}</div>
            ${deltaHtml}
            ${player.current_bet > 0 ? `<div class="player-bet-circle">下注: ${player.current_bet}</div>` : ''}
            <div class="player-status-circle">${this.getPlayerStatusText(player)}</div>
            ${readyIndicator}
            ${winBadge}
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

    // 摊牌阶段展示所有仍在局内玩家的手牌
    renderShowdownReveal(state) {
        if (!state || !Array.isArray(state.showdown_reveal) || state.showdown_reveal.length === 0) return;
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
        title.textContent = `摊牌：公开仍在局内玩家的手牌`;
        container.appendChild(title)

        const list = document.createElement('div');
        list.style.display = 'flex';
        list.style.flexWrap = 'wrap';
        list.style.gap = '8px';

        state.showdown_reveal.forEach(p => {
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
    
    setupEventListeners() {
        // 准备按钮
        document.getElementById('ready-btn')?.addEventListener('click', () => this.setReady());
        document.getElementById('unready-btn')?.addEventListener('click', () => this.setUnready());
        // 刷新房间玩家按钮：主动拉取并重绘围坐（直接绑定）
        document.getElementById('refresh-room-btn')?.addEventListener('click', async () => {
            const btn = document.getElementById('refresh-room-btn');
            console.log('[UI] 点击刷新房间玩家');
            if (btn) btn.disabled = true;
            try {
                // 先请求后端做一次心跳清理
                try {
                    await fetch('/api/cleanup-stale', { method: 'POST' });
                } catch (probeErr) {
                    console.warn('心跳清理请求失败：', probeErr);
                }
                this.gameState = null;
                await this.updateRoomPlayers();
                this.showToast('房间玩家已刷新', 'info');
            } catch (e) {
                console.error('刷新失败:', e);
                this.showToast('刷新失败，请重试', 'error');
            } finally {
                if (btn) btn.disabled = false;
            }
        });

        // 兜底：全局事件代理，确保按钮即使动态渲染也能触发
        document.addEventListener('click', async (e) => {
            const target = e.target;
            if (target && target.id === 'refresh-room-btn') {
                console.log('[UI] 代理点击刷新房间玩家');
                try {
                    target.disabled = true;
                    // 先请求后端做一次心跳清理
                    try {
                        await fetch('/api/cleanup-stale', { method: 'POST' });
                    } catch (probeErr) {
                        console.warn('心跳清理请求失败：', probeErr);
                    }
                    this.gameState = null;
                    await this.updateRoomPlayers();
                    this.showToast('房间玩家已刷新', 'info');
                } catch (err) {
                    console.error('代理刷新失败:', err);
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
            const amount = parseInt(document.getElementById('raise-amount')?.value || 0);
            this.raise(amount);
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
            console.error('获取sessionToken出错:', e);
            return null;
        }
    }
    

}

// 初始化游戏
document.addEventListener('DOMContentLoaded', function() {
    // 从页面模板中获取用户数据
    const userDataElement = document.getElementById('user-data');
    if (userDataElement) {
        const userData = JSON.parse(userDataElement.textContent);
        window.pokerGame = new PokerGame(userData);
    } else {
        window.location.href = '/';
    }
});