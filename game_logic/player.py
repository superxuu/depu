from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from .card import Card
from .hand_evaluator import HandEvaluator

@dataclass
class Player:
    """德州扑克玩家类"""
    
    user_id: str
    nickname: str
    chips: int
    position: int  # 座位位置
    is_active: bool = True
    is_folded: bool = False
    current_bet: int = 0
    hole_cards: List[Card] = field(default_factory=list)
    total_bet: int = 0
    # 本手牌起始筹码，用于计算手牌净变化
    starting_chips: int = 0
    # 是否为本手牌胜者
    win: bool = False
    # 最近一次操作（fold/check/call/raise/sb/bb/all-in等）
    last_action: str = ''
    
    def receive_cards(self, cards: List[Card]) -> None:
        """接收手牌"""
        self.hole_cards.extend(cards)
    
    def fold(self) -> None:
        """弃牌"""
        self.is_folded = True
        self.is_active = False
        self.last_action = 'fold'
    
    def bet(self, amount: int) -> int:
        """下注"""
        if amount > self.chips:
            amount = self.chips  # 全下
        
        self.chips -= amount
        self.current_bet += amount
        self.total_bet += amount
        return amount
    
    def call(self, amount: int) -> int:
        """跟注"""
        self.last_action = 'call'
        return self.bet(amount - self.current_bet)
    
    def raise_bet(self, amount: int) -> int:
        """加注"""
        self.last_action = 'raise'
        return self.bet(amount)
    
    def check(self) -> None:
        """过牌"""
        self.last_action = 'check'
        pass  # 不需要操作
    
    def reset_round(self) -> None:
        """重置回合状态"""
        self.current_bet = 0
        self.is_folded = False
        # 确保活跃状态正确（除非玩家被明确移除，否则保持活跃）
        if not self.is_active:
            self.is_active = True
    
    def reset_game(self) -> None:
        """重置游戏状态"""
        self.reset_round()
        self.hole_cards.clear()
        self.total_bet = 0
        # 记录本手牌起始筹码并重置胜负标记
        self.starting_chips = self.chips
        self.win = False
        # 重置操作记录
        self.last_action = ''
    
    def evaluate_hand(self, community_cards: List[Card]) -> Dict[str, Any]:
        """评估手牌强度"""
        return HandEvaluator.evaluate_hand(self.hole_cards, community_cards)
    
    def can_afford(self, amount: int) -> bool:
        """检查是否能支付指定金额"""
        return self.chips >= amount
    
    def is_all_in(self) -> bool:
        """检查是否全下"""
        return self.chips == 0 and not self.is_folded and self.is_active
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于序列化）"""
        return {
            "user_id": self.user_id,
            "nickname": self.nickname,
            "chips": self.chips,
            "position": self.position,
            "is_active": self.is_active,
            "is_folded": self.is_folded,
            "current_bet": self.current_bet,
            "total_bet": self.total_bet,
            "hole_cards": [card.to_dict() for card in self.hole_cards],
            "is_all_in": self.is_all_in(),
            # 新增用于前端展示的字段
            "hand_delta": self.chips - self.starting_chips if self.starting_chips else 0,
            "win": self.win,
            "last_action": self.last_action
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Player':
        """从字典创建Player对象"""
        player = cls(
            user_id=data['user_id'],
            nickname=data['nickname'],
            chips=data['chips'],
            position=data['position']
        )
        player.is_active = data.get('is_active', True)
        player.is_folded = data.get('is_folded', False)
        player.current_bet = data.get('current_bet', 0)
        player.total_bet = data.get('total_bet', 0)
        player.starting_chips = data.get('starting_chips', player.chips)
        player.win = data.get('win', False)
        
        # 恢复手牌
        if data.get('hole_cards'):
            cards = [Card.from_dict(card_data) for card_data in data['hole_cards']]
            player.hole_cards = cards
        
        return player

class PlayerManager:
    """玩家管理器"""
    
    def __init__(self):
        self.players: List[Player] = []
        self.dealer_position: int = 0
    
    def add_player(self, player: Player) -> None:
        """添加玩家"""
        self.players.append(player)
    
    def remove_player(self, user_id: str) -> None:
        """移除玩家"""
        self.players = [p for p in self.players if p.user_id != user_id]
    
    def get_player(self, user_id: str) -> Optional[Player]:
        """获取指定玩家"""
        for player in self.players:
            if player.user_id == user_id:
                return player
        return None
    
    def get_player_by_position(self, position: int) -> Optional[Player]:
        """根据位置获取玩家"""
        for player in self.players:
            if player.position == position:
                return player
        return None
    
    def get_active_players(self) -> List[Player]:
        """获取活跃玩家（未弃牌）"""
        return [p for p in self.players if p.is_active and not p.is_folded]
    
    def get_playing_players(self) -> List[Player]:
        """获取正在游戏的玩家（未弃牌且非全下）"""
        return [p for p in self.get_active_players() if not p.is_all_in()]
    
    def get_next_player(self, current_position: int) -> Optional[Player]:
        """获取下一个玩家"""
        # 首先尝试获取正在游戏的玩家（未全下）
        active_players = self.get_playing_players()
        
        # 如果没有正在游戏的玩家（例如所有玩家都全下或弃牌），则获取所有活跃玩家
        if not active_players:
            active_players = self.get_active_players()
            
        if not active_players:
            return None
        
        # 按位置排序
        active_players.sort(key=lambda x: x.position)
        
        # 找到当前玩家位置
        current_index = None
        for i, player in enumerate(active_players):
            if player.position == current_position:
                current_index = i
                break
        
        # 如果找不到当前玩家位置，返回列表中的第一个玩家
        if current_index is None:
            return active_players[0]
        
        # 获取下一个玩家
        next_index = (current_index + 1) % len(active_players)
        return active_players[next_index]
    
    def move_dealer_button(self) -> None:
        """移动庄家按钮"""
        active_players = self.get_active_players()
        if not active_players:
            return
        
        # 找到当前庄家的下一个玩家
        active_players.sort(key=lambda x: x.position)
        current_dealer_index = None
        for i, player in enumerate(active_players):
            if player.position == self.dealer_position:
                current_dealer_index = i
                break
        
        if current_dealer_index is None:
            self.dealer_position = active_players[0].position
        else:
            next_index = (current_dealer_index + 1) % len(active_players)
            self.dealer_position = active_players[next_index].position
    
    def get_small_blind_position(self) -> Optional[int]:
        """获取小盲注位置"""
        active_players = self.get_active_players()
        if not active_players:
            return None
        
        active_players.sort(key=lambda x: x.position)
        # 两人局规则：庄家即小盲
        if len(active_players) == 2:
            return self.dealer_position
        
        dealer_index = None
        for i, player in enumerate(active_players):
            if player.position == self.dealer_position:
                dealer_index = i
                break
        
        if dealer_index is None:
            return active_players[0].position
        
        small_blind_index = (dealer_index + 1) % len(active_players)
        return active_players[small_blind_index].position
    
    def get_big_blind_position(self) -> Optional[int]:
        """获取大盲注位置"""
        active_players = self.get_active_players()
        if not active_players:
            return None
        
        active_players.sort(key=lambda x: x.position)
        # 两人局规则：非庄家即大盲
        if len(active_players) == 2:
            if active_players[0].position == self.dealer_position:
                return active_players[1].position
            else:
                return active_players[0].position
        
        small_blind_pos = self.get_small_blind_position()
        if small_blind_pos is None:
            return None
        
        small_blind_index = None
        for i, player in enumerate(active_players):
            if player.position == small_blind_pos:
                small_blind_index = i
                break
        
        if small_blind_index is None:
            return active_players[0].position
        
        big_blind_index = (small_blind_index + 1) % len(active_players)
        return active_players[big_blind_index].position
    
    def reset_round(self) -> None:
        """重置所有玩家的回合状态"""
        for player in self.players:
            player.reset_round()
    
    def reset_game(self) -> None:
        """重置所有玩家的游戏状态"""
        for player in self.players:
            player.reset_game()
    
    def to_dict_list(self) -> List[Dict[str, Any]]:
        """转换为字典列表"""
        return [player.to_dict() for player in self.players]
    
    @classmethod
    def from_dict_list(cls, data: List[Dict[str, Any]]) -> 'PlayerManager':
        """从字典列表创建PlayerManager"""
        manager = cls()
        for player_data in data:
            manager.add_player(Player.from_dict(player_data))
        return manager