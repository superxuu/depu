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
        # 最低加注增量（用于后续加注合法性校验）
        self.last_raise_increment: int = 0
        # 最后主动者（用于亮牌规则提示）
        self.last_aggressor_user_id: Optional[str] = None
        # 摊牌阶段公开的玩家手牌
        self.showdown_reveal: List[Dict[str, Any]] = []
    
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
        # 重置摊牌公开列表
        self.showdown_reveal = []
        
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
                    self.pot += sb_amount
                else:
                    # SB 全下
                    actual = small_blind_player.chips
                    if actual > 0:
                        small_blind_player.bet(actual)
                        self.pot += actual
        
        if big_blind_pos:
            big_blind_player = self.player_manager.get_player_by_position(big_blind_pos)
            if big_blind_player:
                bb_amount = self.min_bet
                if big_blind_player.can_afford(bb_amount):
                    big_blind_player.bet(bb_amount)
                    self.pot += bb_amount
                    self.current_bet = bb_amount
                    # 初始化最低加注增量为大盲额
                    self.last_raise_increment = bb_amount
                else:
                    # BB 全下
                    actual = big_blind_player.chips
                    if actual > 0:
                        big_blind_player.bet(actual)
                        self.pot += actual
                        self.current_bet = max(self.current_bet, actual)
                        self.last_raise_increment = max(self.last_raise_increment, actual)
    
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
            # 若即时结算已结束整手牌，则不再推进或轮转
            if self.stage == GameStage.ENDED:
                return result
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
            # 检查是否仅剩一人活跃，若是则立刻结算
            self._check_instant_win()
            # 若已结束，清理当前行动位，避免继续轮转
            if self.stage == GameStage.ENDED:
                self.current_player_position = None
            return {"success": True, "message": "弃牌成功"}
        
        elif action == "check":
            if player.current_bet < self.current_bet:
                return {"success": False, "message": "必须跟注或加注"}
            player.check()
            # 记录行动（仅仍需表态者）
            if not player.is_all_in and not player.is_folded:
                self.acted_positions.add(player.position)
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
            if not player.is_all_in and not player.is_folded:
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
            
            # 最低加注增量校验（All-in可放宽）
            increment = amount - self.current_bet
            if player.chips >= raise_amount and self.last_raise_increment > 0 and increment < self.last_raise_increment:
                return {"success": False, "message": "加注增量不足"}
            
            player.raise_bet(raise_amount)
            self.pot += raise_amount
            # 更新当前台面总注与最低加注增量
            self.current_bet = amount
            # 全下（raise_amount 等于剩余筹码）小于最低增量允许，但不重开行动；否则更新最低增量
            if player.chips == 0 and increment < self.last_raise_increment:
                # 不更新 last_raise_increment（不重开行动）
                pass
            else:
                self.last_raise_increment = increment
            # 加注后重置“已行动”集合，仅保留加注者（其他人需重新表态）
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
        # 仅统计仍在玩的非全下玩家（需要继续表态的）
        still_needs_action = [p for p in self.player_manager.get_active_players() if not p.is_all_in()]
        if not still_needs_action:
            return True
        # 若有下注：所有仍需表态的玩家 current_bet 必须匹配到当前注
        if self.current_bet > 0:
            for p in still_needs_action:
                if p.current_bet < self.current_bet:
                    return False
            return True
        # 无下注：所有仍需表态的玩家都至少行动过一次（check）
        return len(self.acted_positions) >= len(still_needs_action)
    
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
    
    def _build_side_pots(self) -> List[Dict[str, Any]]:
        """
        基于各玩家的总投入（total_bet）与弃牌状态，构建主池与边池：
        - 以所有未弃牌玩家的 total_bet 作为贡献上限，按升序形成若干cap层
        - 每层池的金额 = (cap_i - cap_{i-1}) * 该层资格玩家数（资格：total_bet >= cap_i 且未弃牌）
        """
        # 仅考虑未弃牌玩家的投入
        active_players = [p for p in self.player_manager.players if not p.is_folded]
        if not active_players:
            return []
        caps = sorted(set(max(0, p.total_bet) for p in active_players))
        pots: List[Dict[str, Any]] = []
        prev = 0
        for cap in caps:
            if cap <= prev:
                continue
            eligible = [p for p in active_players if p.total_bet >= cap]
            if not eligible:
                prev = cap
                continue
            amount = (cap - prev) * len(eligible)
            pots.append({"cap": cap, "amount": amount, "eligible": eligible})
            prev = cap
        # 记录到状态，便于前端显示
        self.side_pots = [{"cap": pot["cap"], "amount": pot["amount"], "eligible_count": len(pot["eligible"])} for pot in pots]
        return pots
    
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
            winner_player = active_players[0]
            winner_player.chips += self.pot
            winner_player.win = True
            self.winner = winner_player
            # 直接结束本手牌
            self.stage = GameStage.ENDED
            return True
        
        # 摊牌需公开仍在局内玩家的手牌
        self.showdown_reveal = [
            {
                "user_id": p.user_id,
                "nickname": p.nickname,
                "position": p.position,
                "hole_cards": [card.to_dict() for card in p.hole_cards]
            }
            for p in active_players
        ]
        
        # 评估所有玩家的手牌
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
            # 均分该池并按庄家左侧顺序分配 odd chip
            share = pot["amount"] // len(winners_pool)
            rem = pot["amount"] % len(winners_pool)
            ordered_positions = self._seat_order_from_dealer_left()
            ordered_winners = sorted(winners_pool, key=lambda w: ordered_positions.index(w["player"].position))
            for w in ordered_winners:
                w["player"].chips += share
                w["player"].win = True
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
            "side_pots": self.side_pots,
            "last_aggressor": self.last_aggressor_user_id,
            "showdown_reveal": self.showdown_reveal
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
                if self.current_bet == 0:
                    current_player.check()
                else:
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