import random
from typing import List, Optional
from .card import Card, CardCollection

class Deck(CardCollection):
    """表示一副扑克牌"""
    
    def __init__(self):
        # 创建标准的52张扑克牌
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        
        cards = [Card(rank, suit) for suit in suits for rank in ranks]
        super().__init__(cards)
    
    def shuffle(self) -> None:
        """洗牌"""
        random.shuffle(self.cards)
    
    def deal(self, num_cards: int = 1) -> List[Card]:
        """发指定数量的牌"""
        if num_cards > len(self.cards):
            raise ValueError("牌不够了")
        
        dealt_cards = self.cards[:num_cards]
        self.cards = self.cards[num_cards:]
        return dealt_cards
    
    def deal_one(self) -> Card:
        """发一张牌"""
        return self.deal(1)[0]
    
    def reset(self) -> None:
        """重置牌组（重新创建52张牌）"""
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        
        self.cards = [Card(rank, suit) for suit in suits for rank in ranks]
        self.shuffle()
    
    def __str__(self) -> str:
        return f"Deck with {len(self.cards)} cards"
    
    def __repr__(self) -> str:
        return f"Deck(cards={len(self.cards)})"

class Hand(CardCollection):
    """表示一个玩家的手牌"""
    
    def __init__(self, cards: Optional[List[Card]] = None):
        super().__init__(cards)
    
    def __str__(self) -> str:
        if self.is_empty():
            return "Empty Hand"
        return " ".join(str(card) for card in self.cards)
    
    def evaluate_strength(self, community_cards: List[Card]) -> dict:
        """
        评估手牌强度（结合公共牌）
        返回包含牌型信息和强度的字典
        """
        all_cards = self.cards + community_cards
        if len(all_cards) < 5:
            return {"type": "high_card", "strength": 0, "cards": self.cards}
        
        # 这里会调用hand_evaluator进行评估
        # 暂时返回简单评估
        return self._simple_evaluation(all_cards)
    
    def _simple_evaluation(self, all_cards: List[Card]) -> dict:
        """简单的牌型评估（后续会被hand_evaluator替换）"""
        # 按点数排序
        sorted_cards = sorted(all_cards, key=lambda x: x.value, reverse=True)
        
        # 检查对子
        rank_count = {}
        for card in all_cards:
            rank_count[card.rank] = rank_count.get(card.rank, 0) + 1
        
        pairs = [rank for rank, count in rank_count.items() if count >= 2]
        
        if pairs:
            pair_strength = max(card.value for card in all_cards if card.rank in pairs)
            return {
                "type": "pair",
                "strength": pair_strength,
                "cards": [card for card in sorted_cards if card.rank in pairs][:2]
            }
        
        # 高牌
        return {
            "type": "high_card", 
            "strength": sorted_cards[0].value,
            "cards": sorted_cards[:1]
        }
    
    def to_string_list(self) -> List[str]:
        """转换为字符串列表"""
        return [str(card) for card in self.cards]