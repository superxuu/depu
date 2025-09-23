from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Card:
    """表示一张扑克牌"""
    rank: str  # 2-10, J, Q, K, A
    suit: str  # hearts, diamonds, clubs, spades
    
    def __str__(self) -> str:
        """返回牌的字符串表示，如 'As' (Ace of spades)"""
        suit_symbols = {
            'hearts': '♥',
            'diamonds': '♦', 
            'clubs': '♣',
            'spades': '♠'
        }
        return f"{self.rank}{suit_symbols.get(self.suit, self.suit[0].upper())}"
    
    def __repr__(self) -> str:
        return f"Card(rank='{self.rank}', suit='{self.suit}')"
    
    @property
    def value(self) -> int:
        """获取牌的点数值（用于比较）"""
        rank_values = {
            '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
            '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
        }
        return rank_values.get(self.rank, 0)
    
    def to_dict(self) -> dict:
        """转换为字典格式（用于JSON序列化）"""
        return {'rank': self.rank, 'suit': self.suit}
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Card':
        """从字典创建Card对象"""
        return cls(rank=data['rank'], suit=data['suit'])

class CardCollection:
    """扑克牌集合的基类"""
    
    def __init__(self, cards: Optional[List[Card]] = None):
        self.cards = cards or []
    
    def __len__(self) -> int:
        return len(self.cards)
    
    def __getitem__(self, index: int) -> Card:
        return self.cards[index]
    
    def __iter__(self):
        return iter(self.cards)
    
    def add_card(self, card: Card) -> None:
        """添加一张牌"""
        self.cards.append(card)
    
    def remove_card(self, card: Card) -> None:
        """移除一张牌"""
        self.cards.remove(card)
    
    def clear(self) -> None:
        """清空所有牌"""
        self.cards.clear()
    
    def is_empty(self) -> bool:
        """检查是否为空"""
        return len(self.cards) == 0
    
    def to_dict_list(self) -> List[dict]:
        """转换为字典列表（用于JSON序列化）"""
        return [card.to_dict() for card in self.cards]
    
    @classmethod
    def from_dict_list(cls, data: List[dict]) -> 'CardCollection':
        """从字典列表创建CardCollection对象"""
        cards = [Card.from_dict(card_data) for card_data in data]
        return cls(cards)