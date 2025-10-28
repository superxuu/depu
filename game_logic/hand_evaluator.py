from typing import List, Dict, Tuple, Optional
from .card import Card

class HandEvaluator:
    """德州扑克手牌评估器"""
    
    # 牌型权重
    HAND_RANKS = {
        "high_card": 1,
        "pair": 2,
        "two_pair": 3,
        "three_of_a_kind": 4,
        "straight": 5,
        "flush": 6,
        "full_house": 7,
        "four_of_a_kind": 8,
        "straight_flush": 9,
        "royal_flush": 10
    }
    
    @staticmethod
    def evaluate_hand(hole_cards: List[Card], community_cards: List[Card]) -> Dict:
        """
        评估最好的5张牌组合
        返回包含牌型信息和强度的字典
        """
        all_cards = hole_cards + community_cards
        
        if len(all_cards) < 5:
            return HandEvaluator._evaluate_insufficient_cards(hole_cards)
        
        # 检查所有可能的5张牌组合
        best_hand = None
        
        # 这里实现完整的牌型检查逻辑
        # 按优先级从高到低检查
        
        # 1. 检查皇家同花顺
        royal_flush = HandEvaluator._check_royal_flush(all_cards)
        if royal_flush:
            return {
                "type": "royal_flush",
                "strength": HandEvaluator.HAND_RANKS["royal_flush"],
                "cards": royal_flush,
                "description": "皇家同花顺"
            }
        
        # 2. 检查同花顺
        straight_flush = HandEvaluator._check_straight_flush(all_cards)
        if straight_flush:
            return {
                "type": "straight_flush",
                "strength": HandEvaluator.HAND_RANKS["straight_flush"],
                "cards": straight_flush,
                "description": "同花顺"
            }
        
        # 3. 检查四条
        four_of_a_kind = HandEvaluator._check_four_of_a_kind(all_cards)
        if four_of_a_kind:
            return {
                "type": "four_of_a_kind",
                "strength": HandEvaluator.HAND_RANKS["four_of_a_kind"],
                "cards": four_of_a_kind,
                "description": "四条"
            }
        
        # 4. 检查葫芦
        full_house = HandEvaluator._check_full_house(all_cards)
        if full_house:
            return {
                "type": "full_house",
                "strength": HandEvaluator.HAND_RANKS["full_house"],
                "cards": full_house,
                "description": "葫芦"
            }
        
        # 5. 检查同花
        flush = HandEvaluator._check_flush(all_cards)
        if flush:
            return {
                "type": "flush",
                "strength": HandEvaluator.HAND_RANKS["flush"],
                "cards": flush,
                "description": "同花"
            }
        
        # 6. 检查顺子
        straight = HandEvaluator._check_straight(all_cards)
        if straight:
            return {
                "type": "straight",
                "strength": HandEvaluator.HAND_RANKS["straight"],
                "cards": straight,
                "description": "顺子"
            }
        
        # 7. 检查三条
        three_of_a_kind = HandEvaluator._check_three_of_a_kind(all_cards)
        if three_of_a_kind:
            return {
                "type": "three_of_a_kind",
                "strength": HandEvaluator.HAND_RANKS["three_of_a_kind"],
                "cards": three_of_a_kind,
                "description": "三条"
            }
        
        # 8. 检查两对
        two_pair = HandEvaluator._check_two_pair(all_cards)
        if two_pair:
            return {
                "type": "two_pair",
                "strength": HandEvaluator.HAND_RANKS["two_pair"],
                "cards": two_pair,
                "description": "两对"
            }
        
        # 9. 检查对子
        pair = HandEvaluator._check_pair(all_cards)
        if pair:
            return {
                "type": "pair",
                "strength": HandEvaluator.HAND_RANKS["pair"],
                "cards": pair,
                "description": "对子"
            }
        
        # 10. 高牌
        high_card = HandEvaluator._check_high_card(all_cards)
        return {
            "type": "high_card",
            "strength": HandEvaluator.HAND_RANKS["high_card"],
            "cards": high_card,
            "description": "高牌"
        }
    
    @staticmethod
    def _evaluate_insufficient_cards(hole_cards: List[Card]) -> Dict:
        """牌不够时的评估"""
        if len(hole_cards) == 2:
            # 只有手牌时，按对子或高牌评估
            if hole_cards[0].rank == hole_cards[1].rank:
                return {
                    "type": "pair",
                    "strength": hole_cards[0].value,
                    "cards": hole_cards,
                    "description": "口袋对子"
                }
            else:
                high_card = max(hole_cards, key=lambda x: x.value)
                return {
                    "type": "high_card",
                    "strength": high_card.value,
                    "cards": [high_card],
                    "description": "高牌"
                }
        return {
            "type": "high_card",
            "strength": 0,
            "cards": hole_cards[:1] if hole_cards else [],
            "description": "高牌"
        }
    
    @staticmethod
    def _check_royal_flush(cards: List[Card]) -> Optional[List[Card]]:
        """检查皇家同花顺"""
        straight_flush = HandEvaluator._check_straight_flush(cards)
        if not straight_flush:
            return None
        
        # 检查是否是10-J-Q-K-A的同花顺
        values = sorted([card.value for card in straight_flush], reverse=True)
        # 皇家同花顺必须是A-K-Q-J-10
        if values == [14, 13, 12, 11, 10]:
            return straight_flush
        return None
    
    @staticmethod
    def _check_straight_flush(cards: List[Card]) -> Optional[List[Card]]:
        """检查同花顺"""
        # 按花色分组
        suits = {}
        for card in cards:
            if card.suit not in suits:
                suits[card.suit] = []
            suits[card.suit].append(card)
        
        # 检查每个花色是否有顺子
        for suit_cards in suits.values():
            if len(suit_cards) >= 5:
                straight = HandEvaluator._check_straight(suit_cards)
                if straight:
                    return straight
        return None
    
    @staticmethod
    def _check_four_of_a_kind(cards: List[Card]) -> Optional[List[Card]]:
        """检查四条"""
        rank_count = {}
        for card in cards:
            rank_count[card.rank] = rank_count.get(card.rank, 0) + 1
        
        for rank, count in rank_count.items():
            if count >= 4:
                four_cards = [card for card in cards if card.rank == rank][:4]
                # 添加最高的一张侧牌
                kicker = max([card for card in cards if card.rank != rank], 
                            key=lambda x: x.value, default=None)
                if kicker:
                    four_cards.append(kicker)
                return four_cards[:5]
        return None
    
    @staticmethod
    def _check_full_house(cards: List[Card]) -> Optional[List[Card]]:
        """检查葫芦"""
        rank_count = {}
        for card in cards:
            rank_count[card.rank] = rank_count.get(card.rank, 0) + 1
        
        # 按点数排序三条，选择最大的三条
        three_ranks = sorted([rank for rank, count in rank_count.items() if count >= 3], 
                           key=lambda x: max(card.value for card in cards if card.rank == x), reverse=True)
        
        # 如果有三条，找对子
        if three_ranks:
            best_three = three_ranks[0]
            # 找出不是三条的对子
            pair_ranks = []
            for rank, count in rank_count.items():
                if rank != best_three and count >= 2:
                    pair_ranks.append(rank)
            
            # 如果没有单独的对子，但有多个三条，用次大的三条做对子
            if not pair_ranks and len(three_ranks) >= 2:
                pair_ranks = [three_ranks[1]]
            
            if pair_ranks:
                three_cards = [card for card in cards if card.rank == best_three][:3]
                pair_cards = [card for card in cards if card.rank == pair_ranks[0]][:2]
                return three_cards + pair_cards
        
        return None
    
    @staticmethod
    def _check_flush(cards: List[Card]) -> Optional[List[Card]]:
        """检查同花"""
        suits = {}
        for card in cards:
            if card.suit not in suits:
                suits[card.suit] = []
            suits[card.suit].append(card)
        
        for suit_cards in suits.values():
            if len(suit_cards) >= 5:
                # 取同花中点数最高的5张牌
                flush_cards = sorted(suit_cards, key=lambda x: x.value, reverse=True)[:5]
                return flush_cards
        return None
    
    @staticmethod
    def _check_straight(cards: List[Card]) -> Optional[List[Card]]:
        """检查顺子"""
        # 转换点数并去重排序
        values = sorted(set(card.value for card in cards), reverse=True)
        
        # 先检查普通顺子（A作为14）
        for i in range(len(values) - 4):
            if values[i] - values[i+4] == 4:
                # 找到顺子，获取对应的牌
                straight_values = values[i:i+5]
                straight_cards = []
                for value in straight_values:
                    # 取该点数值最高的牌
                    card_for_value = max([card for card in cards if card.value == value], 
                                        key=lambda x: x.value)
                    straight_cards.append(card_for_value)
                return straight_cards
        
        # 检查A-5特殊顺子（A作为1）
        if 14 in values:  # 有A
            # 创建A作为1的值列表
            low_ace_values = [v if v != 14 else 1 for v in values]
            low_ace_values = sorted(set(low_ace_values), reverse=True)
            
            # 检查5-4-3-2-A顺子
            for i in range(len(low_ace_values) - 4):
                if low_ace_values[i] - low_ace_values[i+4] == 4:
                    if low_ace_values[i] == 5 and low_ace_values[i+4] == 1:  # 确认是5-4-3-2-A
                        # 获取对应的牌（A作为1，但实际牌值是14）
                        straight_values = [5, 4, 3, 2, 14]
                        straight_cards = []
                        for value in straight_values:
                            # 取该点数值最高的牌
                            card_for_value = max([card for card in cards if card.value == value], 
                                                key=lambda x: x.value)
                            straight_cards.append(card_for_value)
                        return straight_cards
        return None
    
    @staticmethod
    def _check_three_of_a_kind(cards: List[Card]) -> Optional[List[Card]]:
        """检查三条"""
        rank_count = {}
        for card in cards:
            rank_count[card.rank] = rank_count.get(card.rank, 0) + 1
        
        for rank, count in rank_count.items():
            if count >= 3:
                three_cards = [card for card in cards if card.rank == rank][:3]
                # 添加两张最高的侧牌
                kickers = sorted([card for card in cards if card.rank != rank], 
                                key=lambda x: x.value, reverse=True)[:2]
                return three_cards + kickers
        return None
    
    @staticmethod
    def _check_two_pair(cards: List[Card]) -> Optional[List[Card]]:
        """检查两对"""
        rank_count = {}
        for card in cards:
            rank_count[card.rank] = rank_count.get(card.rank, 0) + 1
        
        pair_ranks = [rank for rank, count in rank_count.items() if count >= 2]
        if len(pair_ranks) >= 2:
            # 取最高的两对
            pair_ranks.sort(key=lambda x: max(card.value for card in cards if card.rank == x), 
                          reverse=True)
            first_pair = [card for card in cards if card.rank == pair_ranks[0]][:2]
            second_pair = [card for card in cards if card.rank == pair_ranks[1]][:2]
            # 添加一张最高的侧牌
            kicker = max([card for card in cards if card.rank not in pair_ranks[:2]], 
                        key=lambda x: x.value, default=None)
            if kicker:
                return first_pair + second_pair + [kicker]
        return None
    
    @staticmethod
    def _check_pair(cards: List[Card]) -> Optional[List[Card]]:
        """检查对子"""
        rank_count = {}
        for card in cards:
            rank_count[card.rank] = rank_count.get(card.rank, 0) + 1
        
        pair_ranks = [rank for rank, count in rank_count.items() if count >= 2]
        if pair_ranks:
            # 取最高的对子
            best_pair_rank = max(pair_ranks, key=lambda x: max(card.value for card in cards if card.rank == x))
            pair_cards = [card for card in cards if card.rank == best_pair_rank][:2]
            # 添加三张最高的侧牌
            kickers = sorted([card for card in cards if card.rank != best_pair_rank], 
                            key=lambda x: x.value, reverse=True)[:3]
            return pair_cards + kickers
        return None
    
    @staticmethod
    def _check_high_card(cards: List[Card]) -> List[Card]:
        """高牌"""
        return sorted(cards, key=lambda x: x.value, reverse=True)[:5]
    
    @staticmethod
    def compare_hands(hand1: Dict, hand2: Dict) -> int:
        """比较两手牌的强度，返回1: hand1赢, -1: hand2赢, 0: 平局"""
        if hand1["strength"] > hand2["strength"]:
            return 1
        elif hand1["strength"] < hand2["strength"]:
            return -1
        else:
            # 同类型牌型，比较具体点数
            return HandEvaluator._compare_same_hand_type(hand1, hand2)
    
    @staticmethod
    def _compare_same_hand_type(hand1: Dict, hand2: Dict) -> int:
        """比较同类型牌型的强度"""
        cards1 = hand1["cards"]
        cards2 = hand2["cards"]
        
        # 按点数降序排列
        values1 = sorted([card.value for card in cards1], reverse=True)
        values2 = sorted([card.value for card in cards2], reverse=True)
        
        # 逐个比较点数
        for v1, v2 in zip(values1, values2):
            if v1 > v2:
                return 1
            elif v1 < v2:
                return -1
        return 0