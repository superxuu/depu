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
    
    def __init__(self, min_bet: int = 10, max_players: int = 9):
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
        return True
    
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
        if len(self.player_manager.get_active_players()) < 2:
            return False  # 至少需要2名玩家
        
        # 重置游戏状态
        self.deck.reset()
        self.community_cards.clear()
        self.pot = 0
        self.side_pots.clear()
        self.current_bet = 0
        self.stage = GameStage.PREFLOP
        self.winner = None
        
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
        """下盲注"""
        small_blind_pos = self.player_manager.get_small_blind_position()
        big_blind_pos = self.player_manager.get_big_blind_position()
        
        if small_blind_pos:
            small_blind_player = self.player_manager.get_player_by_position(small_blind_pos)
            if small_blind_player:
                small_blind_player.bet(self.min_bet // 2)
                self.pot += self.min_bet // 2
        
        if big_blind_pos:
            big_blind_player = self.player_manager.get_player_by_position(big_blind_pos)
            if big_blind_player:
                big_blind_player.bet(self.min_bet)
                self.pot += self.min_bet
                self.current_bet = self.min_bet
    
    def _set_initial_player(self) -> None:
        """设置初始玩家（大盲注后面的玩家）"""
        big_blind_pos = self.player_manager.get_big_blind_position()
        if big_blind_pos:
            active_players = self.player_manager.get_active_players()
            active_players.sort(key=lambda x: x.position)
            
            # 找到大盲注玩家的索引
            big_blind_index = None
            for i, player in enumerate(active_players):
                if player.position == big_blind_pos:
                    big_blind_index = i
                    break
            
            if big_blind_index is not None:
                next_index = (big_blind_index + 1) % len(active_players)
                self.current_player_position = active_players[next_index].position
                # 记录本街首个行动位
                self.first_to_act_position = self.current_player_position
    
    def next_stage(self) -> bool:
        """进入下一阶段"""
        if self.stage == GameStage.PREFLOP:
            # 发翻牌
            self._deal_flop()
            self.stage = GameStage.FLOP
        elif self.stage == GameStage.FLOP:
            # 发转牌
            self._deal_turn()
            self.stage = GameStage.TURN
        elif self.stage == GameStage.TURN:
            # 发河牌
            self._deal_river()
            self.stage = GameStage.RIVER
        elif self.stage == GameStage.RIVER:
            # 进入摊牌
            self.stage = GameStage.SHOWDOWN
            return self._determine_winner()
        elif self.stage == GameStage.SHOWDOWN:
            # 游戏结束
            self.stage = GameStage.ENDED
            return True
        
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
        
        self.current_bet = 0
        # 重置本街行动记录
        self.acted_positions = set()
        # 设置当前玩家为庄家后面的第一个玩家
        self._set_initial_player()
    
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
            # 回合结束判定：若应结束则直接进入下一阶段，否则轮到下一位
            if self._should_advance_stage():
                self.next_stage()
            else:
                self._move_to_next_player()
        
        return result
    
    def _process_action(self, player: Player, action: str, amount: int) -> Dict[str, Any]:
        """处理具体操作"""
        if action == "fold":
            player.fold()
            return {"success": True, "message": "弃牌成功"}
        
        elif action == "check":
            if player.current_bet < self.current_bet:
                return {"success": False, "message": "必须跟注或加注"}
            player.check()
            # 记录行动
            self.acted_positions.add(player.position)
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
                # 记录行动
                self.acted_positions.add(player.position)
                return {"success": True, "message": "全下成功", "all_in": True}
            
            # 注意：Player.call 期望传入的是“台面总注”，内部会以该值与当前下注差额计算
            player.call(self.current_bet)
            self.pot += call_amount
            # 记录行动
            self.acted_positions.add(player.position)
            return {"success": True, "message": "跟注成功"}
        
        elif action == "raise":
            if amount <= self.current_bet:
                return {"success": False, "message": "加注金额必须大于当前下注"}
            
            raise_amount = amount - player.current_bet
            if not player.can_afford(raise_amount):
                return {"success": False, "message": "筹码不足"}
            
            player.raise_bet(raise_amount)
            self.pot += raise_amount
            self.current_bet = amount
            # 加注后重置“已行动”集合，仅保留加注者（其他人需重新表态）
            self.acted_positions = {player.position}
            return {"success": True, "message": "加注成功"}
        
        return {"success": False, "message": "无效操作"}
    
    def _should_advance_stage(self) -> bool:
        """判断是否应结束当前下注回合并进入下一阶段"""
        # 仅统计仍在玩的非全下玩家（需要继续表态的）
        active_players = self.player_manager.get_playing_players()
        if not active_players:
            return True
        # 若有下注：所有仍在玩的非全下玩家 current_bet 必须已匹配到当前注
        if self.current_bet > 0:
            for p in active_players:
                if p.current_bet < self.current_bet:
                    return False
            return True
        # 无下注：所有仍在玩的非全下玩家都至少行动过一次（check）
        return len(self.acted_positions) >= len(active_players)
    
    def _move_to_next_player(self) -> None:
        """移动到下一个玩家"""
        # 若当前玩家位置未知，无法推进到下一位（避免向 get_next_player 传入 None）
        if self.current_player_position is None:
            return
        next_player = self.player_manager.get_next_player(self.current_player_position)
        if next_player:
            self.current_player_position = next_player.position
        else:
            # 没有更多玩家，进入下一阶段
            self.next_stage()
    
    def _determine_winner(self) -> bool:
        """确定赢家并分配筹码"""
        active_players = self.player_manager.get_active_players()
        # 重置本手牌胜利标记
        for p in self.player_manager.players:
            p.win = False
        if not active_players:
            return False
        # 如果只剩一个玩家，直接获胜
        if len(active_players) == 1:
            active_players[0].chips += self.pot
            self.winner = active_players[0]
            # 标记胜者
            self.winner.win = True
            return True
        
        # 评估所有玩家的手牌
        player_hands = []
        for player in active_players:
            hand_evaluation = player.evaluate_hand(self.community_cards)
            player_hands.append({
                "player": player,
                "evaluation": hand_evaluation
            })
        
        # 按牌型强度排序
        player_hands.sort(key=lambda x: (
            HandEvaluator.HAND_RANKS[x["evaluation"]["type"]],
            x["evaluation"]["strength"]
        ), reverse=True)
        
        # 确定赢家（可能有多个平局）
        winners = [player_hands[0]]
        for i in range(1, len(player_hands)):
            if (player_hands[i]["evaluation"]["type"] == winners[0]["evaluation"]["type"] and
                player_hands[i]["evaluation"]["strength"] == winners[0]["evaluation"]["strength"]):
                winners.append(player_hands[i])
            else:
                break
        
        # 分配底池
        if len(winners) == 1:
            winners[0]["player"].chips += self.pot
            self.winner = winners[0]["player"]
            self.winner.win = True
        else:
            # 平局，平均分配并处理余数
            share = self.pot // len(winners)
            remainder = self.pot % len(winners)
            for i, winner in enumerate(winners):
                additional = 1 if i < remainder else 0
                winner["player"].chips += share + additional
            # 标记所有平分胜者
            for w in winners:
                w["player"].win = True
        
        return True
    
    def get_game_state(self) -> Dict[str, Any]:
        """获取游戏状态"""
        current_player_id: Optional[str] = None
        if self.current_player_position is not None:
            cp = self.player_manager.get_player_by_position(self.current_player_position)
            if cp:
                current_player_id = cp.user_id

        return {
            "stage": self.stage.value,  # 小写阶段字符串，便于前端渲染
            "community_cards": [card.to_dict() for card in self.community_cards],
            "pot": self.pot,
            "current_bet": self.current_bet,
            # 兼容字段：保留已有 current_player（位置号），并补充更明确的两个字段
            "current_player": self.current_player_position,            # 位置号（向后兼容）
            "current_player_position": self.current_player_position,   # 位置号（显式）
            "current_player_id": current_player_id,                    # user_id（前端直接使用）
            "players": self.player_manager.to_dict_list(),
            "winner": self.winner.to_dict() if self.winner else None,
            "side_pots": self.side_pots
        }
    
    def is_action_timeout(self) -> bool:
        """检查是否操作超时"""
        return time.time() - self.last_action_time > self.action_timeout
    
    def auto_fold_timeout_players(self) -> List[Player]:
        """自动弃牌超时玩家"""
        timed_out_players = []
        if self.is_action_timeout() and self.current_player_position:
            current_player = self.player_manager.get_player_by_position(self.current_player_position)
            if current_player:
                current_player.fold()
                timed_out_players.append(current_player)
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