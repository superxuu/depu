from typing import List, Dict, Optional, Tuple, Any, Set
from enum import Enum
import time
import random
from .deck import Deck
from .player import Player, PlayerManager
from .card import Card
from .hand_evaluator import HandEvaluator

class GameStage(Enum):
    """游戏阶段枚举"""
    PREFLOP = "preflop"    # 翻牌前
    FLOP = "flop"          # 翻牌
    TURN = "turn"          # 转牌
    RIVER = "river"        # 河牌
    SHOWDOWN = "showdown"  # 摊牌
    ENDED = "ended"        # 结束

class TexasHoldemGame:
    """德州扑克游戏引擎"""
    
    def __init__(self, min_bet: int = 10, max_players: int = 10):
        self.min_bet = min_bet
        self.max_players = max_players
        self.deck = Deck()
        self.player_manager = PlayerManager()
        self.community_cards: List[Card] = []
        self.pot = 0
        self.side_pots: List[Dict[str, Any]] = []  # 边池列表
        self.current_bet = 0
        self.current_player_position: Optional[int] = None
        self.stage = GameStage.PREFLOP
        self.winner: Optional[Player] = None
        self.last_action_time = time.time()
        self.action_timeout = 30  # 操作超时时间（秒）
        # 本街首个行动位（用于无下注全员过牌的回合结束判定）
        self.first_to_act_position: Optional[int] = None
        # 本街已行动的玩家座位集合（统计仍在玩的非全下玩家）
        self.acted_positions: Set[int] = set()
        # 最低加注增量（用于后续加注合法性校验）
        self.last_raise_increment: int = 0
        # 最后主动者（用于亮牌规则提示）
        self.last_aggressor_user_id: Optional[str] = None
        # 摊牌阶段公开的玩家手牌
        self.showdown_reveal: List[Dict[str, Any]] = []
        # 玩家连接状态追踪
        self.connected_players: Set[str] = set()  # 在线玩家user_id集合
        self.disconnected_players: Set[str] = set()  # 已断开连接的玩家user_id集合
        self.spectating_players: Set[str] = set()  # 旁观玩家user_id集合（本轮不参与结算）
        # 仅剩一名在线活跃玩家时的等待提示状态
        self.single_player_waiting: Optional[Dict[str, Any]] = None
        self.single_player_grace_period: int = 15  # 秒
    
    def add_player(self, user_id: str, nickname: str, chips: int, position: int) -> bool:
        """添加玩家"""
        if len(self.player_manager.players) >= self.max_players:
            return False
        
        # 检查位置是否被占用
        for player in self.player_manager.players:
            if player.position == position:
                return False
        
        player = Player(user_id, nickname, chips, position)
        self.player_manager.add_player(player)
        # 标记为在线玩家
        self.connected_players.add(user_id)
        return True
    
    def set_player_connected(self, user_id: str) -> None:
        """设置玩家为在线状态"""
        self.connected_players.add(user_id)
        self.disconnected_players.discard(user_id)
    
    def set_player_disconnected(self, user_id: str) -> None:
        """设置玩家为离线状态"""
        self.connected_players.discard(user_id)
        self.disconnected_players.add(user_id)
        
        # 如果游戏进行中，检查是否为单玩家场景
        if self.stage != GameStage.ENDED and user_id not in self.spectating_players:
            # 先计算剩余在线玩家（不包括刚离线的这个）
            online_active_count = len([p for p in self.player_manager.get_active_players() 
                                     if p.user_id in self.connected_players and 
                                     p.user_id not in self.spectating_players])
            
            print(f"玩家 {user_id} 离线，剩余在线活跃玩家数: {online_active_count}")
            
            # 如果只剩1个在线活跃玩家（排除刚离线的），不再自动弃牌，等待后端超时检查
            if online_active_count == 1:
                print(f"玩家 {user_id} 离线，检测到只剩1个活跃玩家，等待超时检查")
                # 不自动弃牌离线玩家，让超时检查任务处理
                return
            
            # 多人游戏时（≥3人），离线玩家立即自动弃牌
            print(f"玩家 {user_id} 离线，多人游戏（剩余在线≥2人），自动弃牌")
            player = self.player_manager.get_player(user_id)
            if player and not player.is_folded:
                self.spectating_players.add(user_id)
                # 玩家自动弃牌，但不参与本轮结算
                player.fold()
    
    def get_player_connection_status(self, user_id: str) -> str:
        """获取玩家连接状态：online/offline"""
        if user_id in self.connected_players:
            return "online"
        elif user_id in self.disconnected_players:
            return "offline"
        else:
            return "unknown"
    
    def is_player_connected(self, user_id: str) -> bool:
        """检查玩家是否在线"""
        return user_id in self.connected_players
    
    def get_online_active_players(self) -> List[Player]:
        """获取在线且仍在游戏的玩家"""
        return [p for p in self.player_manager.get_active_players() 
                if p.user_id in self.connected_players and p.user_id not in self.spectating_players]
    
    def handle_player_reconnect(self, user_id: str) -> None:
        """处理玩家重连逻辑"""
        # 设置玩家为在线状态
        self.set_player_connected(user_id)
        
        # 如果当前处于单玩家等待状态，且重连的玩家是等待中的玩家，清除等待状态
        if (self.single_player_waiting and 
            self.single_player_waiting["user_id"] == user_id):
            print(f"玩家 {user_id} 重连，清除单玩家等待状态")
            self.single_player_waiting = None
    
    def remove_player(self, user_id: str) -> bool:
        """移除玩家"""
        player = self.player_manager.get_player(user_id)
        if not player:
            return False
        
        # 如果游戏正在进行，玩家自动弃牌
        if self.stage != GameStage.ENDED:
            player.fold()
        
        self.player_manager.remove_player(user_id)
        return True
    
    def start_game(self) -> bool:
        """开始新游戏"""
        print("开始检查游戏开始条件...")
        
        # 只检查在线且非旁观的活跃玩家
        active_players = self.get_online_active_players()
        print(f"在线活跃玩家: {[p.nickname for p in active_players]}")
        
        if len(active_players) < 2:
            print(f"游戏开始失败：在线活跃玩家不足2人，当前只有{len(active_players)}人")
            return False  # 至少需要2名玩家
        
        # 检查是否有玩家筹码不足以支付大盲注
        for player in active_players:
            if player.chips < self.min_bet:
                print(f"游戏开始失败：玩家 {player.nickname} 筹码不足，需要{self.min_bet}，当前只有{player.chips}")
                return False  # 筹码不足以支付大盲注
        
        # 重置游戏状态
        self.deck.reset()
        self.community_cards.clear()
        self.pot = 0
        self.side_pots.clear()
        self.current_bet = 0
        self.stage = GameStage.PREFLOP
        self.winner = None
        # 重置摊牌公开列表
        self.showdown_reveal = []
        
        # 重置旁观状态（新游戏开始时清空旁观列表）
        self.spectating_players.clear()
        
        # 重置玩家状态
        self.player_manager.reset_game()
        
        # 首局随机定庄：如果当前庄家位置不在活跃玩家中，则随机选一位作为庄家
        active_players = self.player_manager.get_active_players()
        active_players.sort(key=lambda x: x.position)
        active_positions = [p.position for p in active_players]
        if not active_positions:
            return False
        if self.player_manager.dealer_position not in active_positions:
            self.player_manager.dealer_position = random.choice(active_positions)
        
        # 移动庄家按钮（后续每局顺时针移动）
        self.player_manager.move_dealer_button()
        
        # 发牌
        self._deal_cards()
        
        # 设置盲注
        self._post_blinds()
        
        # 设置当前玩家（大盲注后面的玩家）
        self._set_initial_player()
        
        return True
    
    def _deal_cards(self) -> None:
        """发手牌"""
        active_players = self.player_manager.get_active_players()
        for player in active_players:
            # 每人发两张牌
            cards = self.deck.deal(2)
            player.receive_cards(cards)
    
    def _post_blinds(self) -> None:
        """下盲注（不足则按全下处理）"""
        small_blind_pos = self.player_manager.get_small_blind_position()
        big_blind_pos = self.player_manager.get_big_blind_position()
        
        if small_blind_pos:
            small_blind_player = self.player_manager.get_player_by_position(small_blind_pos)
            if small_blind_player:
                sb_amount = self.min_bet // 2
                if small_blind_player.can_afford(sb_amount):
                    small_blind_player.bet(sb_amount)
                    small_blind_player.last_action = 'sb'
                    self.pot += sb_amount
                else:
                    # SB 全下
                    actual = small_blind_player.chips
                    if actual > 0:
                        small_blind_player.bet(actual)
                        small_blind_player.last_action = 'sb'
                        self.pot += actual
        
        if big_blind_pos:
            big_blind_player = self.player_manager.get_player_by_position(big_blind_pos)
            if big_blind_player:
                bb_amount = self.min_bet
                if big_blind_player.can_afford(bb_amount):
                    big_blind_player.bet(bb_amount)
                    big_blind_player.last_action = 'bb'
                    self.pot += bb_amount
                    self.current_bet = bb_amount
                    # 初始化最低加注增量为大盲额
                    self.last_raise_increment = bb_amount
                else:
                    # BB 全下
                    actual = big_blind_player.chips
                    if actual > 0:
                        big_blind_player.bet(actual)
                        big_blind_player.last_action = 'bb'
                        self.pot += actual
                        self.current_bet = max(self.current_bet, actual)
                        # BB全下时，最低加注增量仍为大盲注额（不是全下金额）
                        if self.last_raise_increment == 0:
                            self.last_raise_increment = self.min_bet
    
    def _set_initial_player(self) -> None:
        """设置本街首个行动位：
        - 常规：翻牌前从BB左侧（UTG）；翻牌后从庄家左侧（SB）
        - 两人局（heads-up）特殊：
          * 翻牌前由小盲（庄家）先行动
          * 翻牌/转牌/河牌由大盲先行动
        """
        active_players = self.player_manager.get_active_players()
        if not active_players:
            self.current_player_position = None
            self.first_to_act_position = None
            return
        
        # 检查是否还有需要操作的玩家（未全下）
        playing_players = [p for p in active_players if not p.is_all_in()]
        if not playing_players:
            # 所有玩家都已ALL IN，无需设置当前玩家
            self.current_player_position = None
            self.first_to_act_position = None
            return
        
        # heads-up 特殊处理
        if len(active_players) == 2:
            if self.stage == GameStage.PREFLOP:
                sb_pos = self.player_manager.get_small_blind_position()
                if sb_pos is not None:
                    self.current_player_position = sb_pos
                    self.first_to_act_position = sb_pos
                else:
                    self.current_player_position = None
                    self.first_to_act_position = None
            else:
                bb_pos = self.player_manager.get_big_blind_position()
                if bb_pos is not None:
                    self.current_player_position = bb_pos
                    self.first_to_act_position = bb_pos
                else:
                    self.current_player_position = None
                    self.first_to_act_position = None
            return
        
        if self.stage == GameStage.PREFLOP:
            bb_pos = self.player_manager.get_big_blind_position()
            if bb_pos is None:
                self.current_player_position = None
                self.first_to_act_position = None
                return
            # 从BB之后的第一个仍在局内的玩家开始
            next_player = self.player_manager.get_next_player(bb_pos)
            if next_player:
                self.current_player_position = next_player.position
                self.first_to_act_position = self.current_player_position
            else:
                self.current_player_position = None
                self.first_to_act_position = None
        else:
            dealer_pos = self.player_manager.dealer_position
            # 从庄家左侧开始，找到仍在局内的第一个
            next_player = self.player_manager.get_next_player(dealer_pos)
            if next_player:
                self.current_player_position = next_player.position
                self.first_to_act_position = self.current_player_position
            else:
                self.current_player_position = None
                self.first_to_act_position = None
    
    def next_stage(self) -> bool:
        """进入下一阶段"""
        print(f"DEBUG: next_stage - 当前阶段: {self.stage}")
        
        # 检查是否还有需要操作的玩家
        playing_players = [p for p in self.player_manager.get_active_players() if not p.is_all_in()]
        
        if self.stage == GameStage.PREFLOP:
            # 发翻牌
            self._deal_flop()
            self.stage = GameStage.FLOP
            print(f"DEBUG: next_stage - 进入翻牌阶段")
        elif self.stage == GameStage.FLOP:
            # 发转牌
            self._deal_turn()
            self.stage = GameStage.TURN
            print(f"DEBUG: next_stage - 进入转牌阶段")
        elif self.stage == GameStage.TURN:
            # 发河牌
            self._deal_river()
            self.stage = GameStage.RIVER
            print(f"DEBUG: next_stage - 进入河牌阶段")
        elif self.stage == GameStage.RIVER:
            # 进入摊牌
            self.stage = GameStage.SHOWDOWN
            print(f"DEBUG: next_stage - 进入摊牌阶段")
            return self._determine_winner()
        elif self.stage == GameStage.SHOWDOWN:
            # 游戏结束
            self.stage = GameStage.ENDED
            print(f"DEBUG: next_stage - 游戏结束")
            return True
        
        # 如果所有玩家都已ALL IN，自动发完剩余牌并摊牌
        if not playing_players:
            print(f"DEBUG: next_stage - 所有玩家ALL IN，自动发完剩余牌")
            # 自动推进到河牌，然后摊牌
            while self.stage != GameStage.RIVER:
                if self.stage == GameStage.PREFLOP:
                    self._deal_flop()
                    self.stage = GameStage.FLOP
                elif self.stage == GameStage.FLOP:
                    self._deal_turn()
                    self.stage = GameStage.TURN
                elif self.stage == GameStage.TURN:
                    self._deal_river()
                    self.stage = GameStage.RIVER
            
            # 到达河牌后直接摊牌
            self.stage = GameStage.SHOWDOWN
            return self._determine_winner()
        
        # 重置下注状态
        self._reset_betting_round()
        return True
    
    def _deal_flop(self) -> None:
        """发翻牌（3张公共牌）"""
        # 烧一张牌
        self.deck.deal_one()
        # 发3张翻牌
        self.community_cards.extend(self.deck.deal(3))
    
    def _deal_turn(self) -> None:
        """发转牌"""
        # 烧一张牌
        self.deck.deal_one()
        # 发1张转牌
        self.community_cards.extend(self.deck.deal(1))
    
    def _deal_river(self) -> None:
        """发河牌"""
        # 烧一张牌
        self.deck.deal_one()
        # 发1张河牌
        self.community_cards.extend(self.deck.deal(1))
    
    def _reset_betting_round(self) -> None:
        """重置下注回合"""
        # 重置玩家当前下注额
        for player in self.player_manager.players:
            player.current_bet = 0
            # 新一轮下注开始时清空上轮"最近一次操作"标记
            player.last_action = ''
        
        self.current_bet = 0
        # 新回合：最小加注增量重置为大盲额（min_bet），符合德扑规则
        self.last_raise_increment = self.min_bet
        # 重置本街行动记录
        self.acted_positions = set()
        # 设置当前玩家为庄家后面的第一个玩家
        self._set_initial_player()
        print(f"DEBUG: _reset_betting_round - 设置当前玩家为 {self.current_player_position}")
    
    def player_action(self, user_id: str, action: str, amount: int = 0) -> Dict[str, Any]:
        """处理玩家操作"""
        player = self.player_manager.get_player(user_id)
        if not player or player.position != self.current_player_position:
            return {"success": False, "message": "不是当前玩家"}
        
        if player.is_folded:
            return {"success": False, "message": "玩家已弃牌"}
        
        result = self._process_action(player, action, amount)
        if result["success"]:
            self.last_action_time = time.time()
            # 若即时结算已结束整手牌，则不再推进或轮转
            if self.stage == GameStage.ENDED:
                return result
            should_advance = self._should_advance_stage()
            if self.single_player_waiting:
                print("DEBUG: player_action - 单玩家等待中，暂停推进")
            elif should_advance:
                print("DEBUG: player_action - 调用 next_stage()")
                self.next_stage()
            else:
                print("DEBUG: player_action - 调用 _move_to_next_player()")
                self._move_to_next_player()
        
        return result
    
    def _process_action(self, player: Player, action: str, amount: int) -> Dict[str, Any]:
        """处理具体操作"""
        if action == "fold":
            player.fold()
            # 检查是否仅剩一人活跃，若是则立刻结算
            self._check_instant_win()
            # 若已结束，清理当前行动位，避免继续轮转
            if self.stage == GameStage.ENDED:
                self.current_player_position = None
            return {"success": True, "message": "弃牌成功"}
        
        elif action == "check":
            print(f"DEBUG: 玩家 {player.position} 尝试过牌")
            print(f"DEBUG: 玩家状态 - is_all_in: {player.is_all_in()}, is_folded: {player.is_folded}")
            print(f"DEBUG: 玩家当前下注: {player.current_bet}, 台面当前下注: {self.current_bet}")
            
            if player.current_bet < self.current_bet:
                print("DEBUG: 过牌失败，必须跟注或加注")
                return {"success": False, "message": "必须跟注或加注"}
            player.check()
            # 记录行动（仅仍需表态者）
            if not player.is_all_in() and not player.is_folded:
                print(f"DEBUG: 玩家 {player.position} 过牌，添加到 acted_positions")
                self.acted_positions.add(player.position)
                print(f"DEBUG: 过牌后 acted_positions={self.acted_positions}")
            else:
                print(f"DEBUG: 玩家 {player.position} 未添加到 acted_positions，因为 is_all_in={player.is_all_in()}, is_folded={player.is_folded}")
            # 过牌后若只剩一人未弃牌，立即结算
            self._check_instant_win()
            return {"success": True, "message": "过牌成功"}
        
        elif action == "call":
            call_amount = self.current_bet - player.current_bet
            if call_amount <= 0:
                return {"success": False, "message": "无需跟注"}
            
            if not player.can_afford(call_amount):
                # 全下
                actual_amount = player.chips
                player.bet(actual_amount)
                self.pot += actual_amount
                # 全下后若只剩一人未弃牌，立即结算
                self._check_instant_win()
                return {"success": True, "message": "全下成功", "all_in": True}
            
            # 注意：Player.call 期望传入的是“台面总注”，内部会以该值与当前下注差额计算
            player.call(self.current_bet)
            self.pot += call_amount
            # 记录行动（仅仍需表态者）
            if not player.is_all_in() and not player.is_folded:
                self.acted_positions.add(player.position)
            # 实时更新边池概览
            self._update_side_pots_snapshot()
            # 跟注后若只剩一人未弃牌，立即结算
            self._check_instant_win()
            return {"success": True, "message": "跟注成功"}
        
        elif action == "raise":
            if amount <= self.current_bet:
                return {"success": False, "message": "加注金额必须大于当前下注"}
            
            raise_amount = amount - player.current_bet
            if not player.can_afford(raise_amount):
                return {"success": False, "message": "筹码不足"}
            
            # 最低加注增量校验
            increment = amount - self.current_bet
            is_all_in = (raise_amount >= player.chips)
            
            # 如果不是全下，必须满足最低加注增量
            if not is_all_in and self.last_raise_increment > 0 and increment < self.last_raise_increment:
                return {"success": False, "message": f"加注增量不足，最少加注{self.last_raise_increment}"}
            
            player.raise_bet(raise_amount)
            self.pot += raise_amount
            # 更新当前台面总注与最低加注增量
            self.current_bet = amount
            # 只有足额加注才更新最低增量，全下不更新
            if not is_all_in:
                self.last_raise_increment = increment
            # 加注后重置"已行动"集合，仅保留加注者（其他人需重新表态）
            self.acted_positions = {player.position}
            # 记录最后主动者（用于亮牌规则提示）
            self.last_aggressor_user_id = player.user_id
            # 实时更新边池概览
            self._update_side_pots_snapshot()
            # 加注后若只剩一人未弃牌，立即结算
            self._check_instant_win()
            return {"success": True, "message": "加注成功"}
        
        return {"success": False, "message": "无效操作"}
    
    def _update_side_pots_snapshot(self) -> None:
        """下注过程实时生成边池概览（用于前端显示），分配仍以摊牌构建为准"""
        pots = self._build_side_pots()
        # 已在 _build_side_pots 中同步了 self.side_pots
    
    def _check_instant_win(self) -> None:
        """当只剩一名活跃玩家时，立即授予底池并结束手牌"""
        active_players = self.player_manager.get_active_players()
        if len(active_players) == 1:
            winner_player = active_players[0]
            winner_player.chips += self.pot
            winner_player.win = True
            self.winner = winner_player
            self.stage = GameStage.ENDED
    
    def _should_advance_stage(self) -> bool:
        """判断是否应结束当前下注回合并进入下一阶段"""
        # 检查是否只剩1人在线，如果是则进入单玩家等待状态
        online_active_players = self.get_online_active_players()
        if len(online_active_players) <= 1 and self.stage != GameStage.ENDED and not self.single_player_waiting:
            self._check_single_player_and_wait()
            return False  # 等待用户决定，不立即推进
        
        active_players = self.player_manager.get_active_players()
        if not active_players:
            return True
        
        # 统计仍需表态的玩家（未弃牌且未全下且在线）
        still_needs_action = [p for p in active_players 
                            if not p.is_all_in() and 
                            p.user_id in self.connected_players and 
                            p.user_id not in self.spectating_players]
        
        # 如果没有需要表态的玩家（全部全下、弃牌、离线或旁观），直接进入下一阶段
        if not still_needs_action:
            return True
        
        # 如果有下注，检查所有仍需表态的玩家是否都已跟注到当前注
        if self.current_bet > 0:
            for p in still_needs_action:
                if p.current_bet < self.current_bet:
                    return False  # 还有玩家需要跟注
            return True  # 所有玩家都已跟注
        
        # 如果没有下注（过牌情况），检查是否所有需要表态的玩家都已行动过
        # 并且当前玩家已经回到了first_to_act_position，表示完成了一整轮
        
        # 添加调试日志
        print(f"DEBUG: acted_positions={self.acted_positions}, still_needs_action={[p.position for p in still_needs_action]}")
        print(f"DEBUG: current_player_position={self.current_player_position}, first_to_act_position={self.first_to_act_position}")
        
        # 获取所有需要表态的玩家的位置
        still_needs_action_positions = {p.position for p in still_needs_action}
        
        # 检查是否所有需要表态的玩家都已经行动过
        all_acted = still_needs_action_positions.issubset(self.acted_positions)
        
        # 所有仍需表态的玩家都已行动（全部过牌），立即推进到下一阶段
        if all_acted:
            print("DEBUG: 所有需要表态的玩家都已行动（全部过牌），推进阶段")
            return True
        
        # 如果还没有玩家行动，或者行动玩家数不足，不推进阶段
        return False
    
    def _seat_order_from_dealer_left(self) -> List[int]:
        """返回从庄家左侧开始的座位顺序（位置号列表），用于odd chip分配排序"""
        active_players = self.player_manager.get_active_players()
        if not active_players:
            return []
        active_players.sort(key=lambda x: x.position)
        dealer_pos = self.player_manager.dealer_position
        # 找到dealer在有序列表中的索引
        start_index = 0
        for i, p in enumerate(active_players):
            if p.position == dealer_pos:
                start_index = (i + 1) % len(active_players)
                break
        ordered = []
        for i in range(len(active_players)):
            ordered.append(active_players[(start_index + i) % len(active_players)].position)
        return ordered
    
    def _move_to_next_player(self) -> None:
        """移动到下一个玩家，跳过离线玩家"""
        print("DEBUG: _move_to_next_player - 开始执行")
        
        # 检查是否只剩1人在线，如果是则进入单玩家等待状态
        online_active_players = self.get_online_active_players()
        if len(online_active_players) <= 1 and self.stage != GameStage.ENDED and not self.single_player_waiting:
            self._check_single_player_and_wait()
            return
        
        # 若当前玩家位置未知，无法推进到下一位（避免向 get_next_player 传入 None）
        if self.current_player_position is None:
            print("DEBUG: 当前玩家位置为None，无法推进到下一位")
            return
        
        max_attempts = len(self.player_manager.players)  # 防止无限循环
        attempts = 0
        
        while attempts < max_attempts:
            next_player = self.player_manager.get_next_player(self.current_player_position)
            if not next_player:
                # 没有更多玩家，设置当前玩家为None
                print("DEBUG: _move_to_next_player - 没有更多玩家，设置current_player_position为None")
                self.current_player_position = None
                return
            
            # 检查下一个玩家是否在线且不是旁观状态
            if (next_player.user_id in self.connected_players and 
                next_player.user_id not in self.spectating_players):
                print(f"DEBUG: _move_to_next_player - 移动到下一个玩家 {next_player.position}")
                self.current_player_position = next_player.position
                return
            
            # 如果下一个玩家离线或旁观，跳过他们并继续寻找
            if next_player.user_id not in self.connected_players:
                # 玩家离线，自动弃牌并设为旁观
                self.set_player_disconnected(next_player.user_id)
            
            self.current_player_position = next_player.position
            attempts += 1
        
        # 如果找不到合适的下一个玩家，设置当前玩家为None
        print("DEBUG: _move_to_next_player - 找不到合适的下一个玩家，设置current_player_position为None")
        self.current_player_position = None
    
    def _terminate_game_insufficient_players(self) -> None:
        """因玩家不足终止游戏"""
        # 游戏终止，不进行结算
        self.stage = GameStage.ENDED
        self.winner = None
        self.current_player_position = None
        self.first_to_act_position = None
        
        # 清空底池（本轮不结算）
        self.pot = 0
        self.side_pots = []
        
        # 重置所有玩家状态但保留筹码
        for player in self.player_manager.players:
            player.reset_round()
            player.current_bet = 0
            player.total_bet = 0
    
    def _check_single_player_and_wait(self) -> None:
        """检查是否为单玩家场景，如果是则设置等待状态"""
        online_active_players = self.get_online_active_players()
        if len(online_active_players) == 1 and not self.single_player_waiting:
            # 获取唯一的在线玩家
            remaining_player = online_active_players[0]
            print(f"检测到只剩一个玩家: {remaining_player.nickname}，进入等待状态")
            
            # 设置等待状态
            self.single_player_waiting = {
                "user_id": remaining_player.user_id,
                "start_time": time.time(),
                "confirmed": False
            }
    
    def handle_single_player_decision(self, user_id: str, decision: str) -> bool:
        """处理单玩家的决定（继续/结束游戏）"""
        if not self.single_player_waiting or self.single_player_waiting["user_id"] != user_id:
            return False
        
        if decision == "continue":
            # 玩家选择继续，清除等待状态
            self.single_player_waiting = None
            return True
        elif decision == "end":
            # 玩家选择结束，终止游戏
            self.single_player_waiting = None
            self._terminate_game_insufficient_players()
            return True
        
        return False
    
    def _build_side_pots(self) -> List[Dict[str, Any]]:
        """
        构建主池与边池：
        - 按玩家投入金额分层，每层独立的池
        - 简化逻辑：只按实际投入金额分层
        """
        # 仅考虑未弃牌玩家的投入
        active_players = [p for p in self.player_manager.players if not p.is_folded]
        if not active_players:
            self.side_pots = []
            return []
        
        # 获取所有不同的投入金额并排序
        bet_amounts = sorted(set(p.total_bet for p in active_players if p.total_bet > 0))
        if not bet_amounts:
            self.side_pots = []
            return []
        
        pots: List[Dict[str, Any]] = []
        prev_amount = 0
        
        for amount in bet_amounts:
            # 找出投入至少为当前金额的玩家
            eligible = [p for p in active_players if p.total_bet >= amount]
            if not eligible:
                continue
            
            # 计算这一层的池金额
            layer_amount = (amount - prev_amount) * len(eligible)
            if layer_amount > 0:
                pots.append({
                    "cap": amount,
                    "amount": layer_amount,
                    "eligible": eligible
                })
            prev_amount = amount
        
        # 更新边池状态（用于前端显示）
        self.side_pots = [
            {
                "cap": pot["cap"], 
                "amount": pot["amount"], 
                "eligible_count": len(pot["eligible"])
            } 
            for pot in pots
        ]
        
        return pots
    
    def voluntary_reveal(self, user_id: str) -> bool:
        """自愿亮牌：在摊牌/结束阶段，允许任意玩家将自己的两张手牌公开给所有人"""
        # 仅在 SHOWDOWN 或 ENDED 阶段允许
        if self.stage not in (GameStage.SHOWDOWN, GameStage.ENDED):
            return False
        player = self.player_manager.get_player(user_id)
        if not player:
            return False
        # 已有则不重复添加
        exists = any(item.get("user_id") == user_id for item in (self.showdown_reveal or []))
        if exists:
            return True
        # 追加该玩家手牌
        self.showdown_reveal = (self.showdown_reveal or []) + [{
            "user_id": player.user_id,
            "nickname": player.nickname,
            "position": player.position,
            "hole_cards": [card.to_dict() for card in player.hole_cards]
        }]
        return True

    def _determine_winner(self) -> bool:
        """确定赢家并分配筹码"""
        # 只考虑在线且非旁观的活跃玩家
        active_players = [p for p in self.player_manager.get_active_players() 
                        if p.user_id in self.connected_players and 
                        p.user_id not in self.spectating_players]
        
        # 重置本手牌胜利标记
        for p in self.player_manager.players:
            p.win = False
            
        if not active_players:
            # 没有符合条件的玩家，游戏结束但不结算
            self.stage = GameStage.ENDED
            return False
            
        # 如果只剩一个玩家，直接获胜
        if len(active_players) == 1:
            winner_player = active_players[0]
            winner_player.chips += self.pot
            winner_player.win = True
            self.winner = winner_player
            # 直接结束本手牌
            self.stage = GameStage.ENDED
            return True
        
        # 摊牌需公开在线且非旁观玩家的手牌
        all_active_players = self.player_manager.get_active_players()
        self.showdown_reveal = [
            {
                "user_id": p.user_id,
                "nickname": p.nickname,
                "position": p.position,
                "hole_cards": [card.to_dict() for card in p.hole_cards],
                "is_spectating": p.user_id in self.spectating_players
            }
            for p in all_active_players
        ]
        
        # 只评估在线且非旁观玩家的手牌
        player_hands = []
        for player in active_players:
            hand_evaluation = player.evaluate_hand(self.community_cards)
            player_hands.append({
                "player": player,
                "evaluation": hand_evaluation
            })
        
        # 通过精确比较确定赢家（支持平局）
        winners = [player_hands[0]]
        for i in range(1, len(player_hands)):
            cmp = HandEvaluator.compare_hands(player_hands[i]["evaluation"], winners[0]["evaluation"])
            if cmp > 0:
                # 当前更强，重置赢家列表
                winners = [player_hands[i]]
            elif cmp == 0:
                # 完全相同（平局），加入赢家列表
                winners.append(player_hands[i])
            # cmp < 0 则忽略较弱者
        
        # 分配主池与边池：按资格玩家独立评估与分配
        pots = self._build_side_pots()
        if not pots:
            # 无池时按整体 winners 分配（防御）
            if len(winners) == 1:
                wp = winners[0]["player"]
                wp.chips += self.pot
                wp.win = True
                self.winner = wp
            else:
                # 平局：平均分配并按庄家左侧顺序分配 odd chip
                share = self.pot // len(winners)
                rem = self.pot % len(winners)
                ordered_positions = self._seat_order_from_dealer_left()
                ordered_winners = sorted(winners, key=lambda w: ordered_positions.index(w["player"].position))
                for w in ordered_winners:
                    w["player"].chips += share
                    w["player"].win = True
                for i in range(rem):
                    ordered_winners[i]["player"].chips += 1
            self.stage = GameStage.ENDED
            return True
        
        # 逐池分配；主池为最后一个cap（最大cap），其赢家作为self.winner
        main_pot_winner: Optional[Player] = None
        for idx, pot in enumerate(pots):
            eligible_players = pot["eligible"]
            # 若资格玩家仅一人，直接获该池
            if len(eligible_players) == 1:
                ep = eligible_players[0]
                ep.chips += pot["amount"]
                ep.win = True
                if idx == len(pots) - 1:
                    main_pot_winner = ep
                continue
            # 评估该池资格玩家
            evals = [{"player": p, "evaluation": p.evaluate_hand(self.community_cards)} for p in eligible_players]
            winners_pool = [evals[0]]
            for i in range(1, len(evals)):
                cmp = HandEvaluator.compare_hands(evals[i]["evaluation"], winners_pool[0]["evaluation"])
                if cmp > 0:
                    winners_pool = [evals[i]]
                elif cmp == 0:
                    winners_pool.append(evals[i])
            # 均分该池并按庄家左侧顺序分配 odd chip（符合国际规则）
            share = pot["amount"] // len(winners_pool)
            rem = pot["amount"] % len(winners_pool)
            ordered_positions = self._seat_order_from_dealer_left()
            ordered_winners = sorted(
                winners_pool,
                key=lambda w: ordered_positions.index(w["player"].position)
            )
            for w in ordered_winners:
                w["player"].chips += share
                w["player"].win = True
            # odd chip分配：从庄家左侧开始，依次分配给赢家
            for i in range(rem):
                ordered_winners[i]["player"].chips += 1
            if idx == len(pots) - 1:
                main_pot_winner = ordered_winners[0]["player"]
        
        # 记录主池赢家并结束
        if main_pot_winner:
            self.winner = main_pot_winner
        self.stage = GameStage.ENDED
        return True
    
    def get_game_state(self) -> Dict[str, Any]:
        """获取游戏状态"""
        current_player_id: Optional[str] = None
        if self.current_player_position is not None:
            cp = self.player_manager.get_player_by_position(self.current_player_position)
            if cp:
                current_player_id = cp.user_id

        # 计算剩余超时时间
        time_remaining = max(0, self.action_timeout - (time.time() - self.last_action_time))

        # 为每个玩家添加连接状态
        players_with_status = []
        for player_dict in self.player_manager.to_dict_list():
            player_dict_copy = player_dict.copy()
            player_dict_copy["connection_status"] = self.get_player_connection_status(player_dict["user_id"])
            players_with_status.append(player_dict_copy)

        return {
            "stage": self.stage.value,  # 小写阶段字符串，便于前端渲染
            "community_cards": [card.to_dict() for card in self.community_cards],
            "pot": self.pot,
            "current_bet": self.current_bet,
            "dealer_position": self.player_manager.dealer_position,
            # 兼容字段：保留已有 current_player（位置号），并补充更明确的两个字段
            "current_player": self.current_player_position,            # 位置号（向后兼容）
            "current_player_position": self.current_player_position,   # 位置号（显式）
            "current_player_id": current_player_id,                    # user_id（前端直接使用）
            "players": players_with_status,
            "winner": self.winner.to_dict() if self.winner else None,
            "side_pots": self.side_pots,
            "last_raise_increment": self.last_raise_increment,
            "last_aggressor": self.last_aggressor_user_id,
            "showdown_reveal": self.showdown_reveal,
            # 超时相关信息
            "action_timeout": self.action_timeout,  # 总超时时间（秒）
            "time_remaining": time_remaining,      # 剩余时间（秒）
            "is_timeout": self.is_action_timeout(),  # 是否已超时
            # 单玩家等待状态
            "single_player_waiting": self.single_player_waiting
        }
    
    def is_action_timeout(self) -> bool:
        """检查是否操作超时"""
        return time.time() - self.last_action_time > self.action_timeout
    
    def auto_fold_timeout_players(self) -> List[Player]:
        """自动处理超时：无下注时自动过牌，有下注时弃牌"""
        timed_out_players = []
        if self.is_action_timeout() and self.current_player_position:
            current_player = self.player_manager.get_player_by_position(self.current_player_position)
            if current_player:
                # 更新最后操作时间，避免重复处理
                self.last_action_time = time.time()
                
                if self.current_bet == 0:
                    current_player.check()
                else:
                    current_player.fold()
                    timed_out_players.append(current_player)
                
                # 移动到下一个玩家（会自动跳过离线玩家）
                self._move_to_next_player()
        
        return timed_out_players
    
    def can_start_game(self) -> bool:
        """检查是否可以开始游戏"""
        return len(self.player_manager.get_active_players()) >= 2
    
    def is_game_active(self) -> bool:
        """检查游戏是否在进行中"""
        return self.stage != GameStage.ENDED
    
    def get_active_player_count(self) -> int:
        """获取活跃玩家数量"""
        return len(self.player_manager.get_active_players())