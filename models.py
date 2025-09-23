from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from datetime import datetime
import json

@dataclass
class User:
    user_id: str
    nickname: str
    invite_code: str
    chips: int
    session_token: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "nickname": self.nickname,
            "chips": self.chips,
            "session_token": self.session_token,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'User':
        return cls(
            user_id=data['user_id'],
            nickname=data['nickname'],
            invite_code=data.get('invite_code', ''),
            chips=data['chips'],
            session_token=data.get('session_token'),
            is_active=data.get('is_active', True),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
            last_login=datetime.fromisoformat(data['last_login']) if data.get('last_login') else None
        )

@dataclass
class Room:
    room_id: str
    room_name: str
    creator_id: str
    max_players: int = 6
    min_bet: int = 5
    status: str = "waiting"  # waiting, playing, finished
    created_at: Optional[datetime] = None
    players: List[Dict] = None
    
    def __post_init__(self):
        if self.players is None:
            self.players = []
    
    def to_dict(self) -> Dict:
        return {
            "room_id": self.room_id,
            "room_name": self.room_name,
            "creator_id": self.creator_id,
            "max_players": self.max_players,
            "min_bet": self.min_bet,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "players": self.players
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Room':
        return cls(
            room_id=data['room_id'],
            room_name=data['room_name'],
            creator_id=data['creator_id'],
            max_players=data.get('max_players', 6),
            min_bet=data.get('min_bet', 5),
            status=data.get('status', 'waiting'),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
            players=data.get('players', [])
        )

@dataclass
class GameState:
    room_id: str
    stage: str  # preflop, flop, turn, river, showdown, ended
    community_cards: List[Dict]
    players: List[Dict]
    current_player: Optional[str] = None
    pot: int = 0
    current_bet: int = 0
    dealer_position: int = 0
    small_blind: int = 2
    big_blind: int = 5
    
    def to_dict(self) -> Dict:
        return {
            "room_id": self.room_id,
            "stage": self.stage,
            "community_cards": self.community_cards,
            "players": self.players,
            "current_player": self.current_player,
            "pot": self.pot,
            "current_bet": self.current_bet,
            "dealer_position": self.dealer_position,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'GameState':
        return cls(
            room_id=data['room_id'],
            stage=data['stage'],
            community_cards=data['community_cards'],
            players=data['players'],
            current_player=data.get('current_player'),
            pot=data.get('pot', 0),
            current_bet=data.get('current_bet', 0),
            dealer_position=data.get('dealer_position', 0),
            small_blind=data.get('small_blind', 2),
            big_blind=data.get('big_blind', 5)
        )

@dataclass
class Card:
    rank: str  # 2-10, J, Q, K, A
    suit: str  # hearts, diamonds, clubs, spades
    
    def to_dict(self) -> Dict:
        return {"rank": self.rank, "suit": self.suit}
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Card':
        return cls(rank=data['rank'], suit=data['suit'])

@dataclass
class PlayerState:
    user_id: str
    nickname: str
    chips: int
    hole_cards: List[Card]
    current_bet: int = 0
    is_folded: bool = False
    is_all_in: bool = False
    is_current_turn: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "nickname": self.nickname,
            "chips": self.chips,
            "hole_cards": [card.to_dict() for card in self.hole_cards],
            "current_bet": self.current_bet,
            "is_folded": self.is_folded,
            "is_all_in": self.is_all_in,
            "is_current_turn": self.is_current_turn
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PlayerState':
        return cls(
            user_id=data['user_id'],
            nickname=data['nickname'],
            chips=data['chips'],
            hole_cards=[Card.from_dict(card) for card in data['hole_cards']],
            current_bet=data.get('current_bet', 0),
            is_folded=data.get('is_folded', False),
            is_all_in=data.get('is_all_in', False),
            is_current_turn=data.get('is_current_turn', False)
        )