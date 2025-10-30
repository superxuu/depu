#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试德扑游戏加注规则问题
重现用户描述的场景：2人游戏，底注A10,B5，B跟注5；A此时最小加注10，A加注10；B此时最小加注20，B加注20；A此时最小加注20，但是此时A在加注框里输入20，点击加注，却提示至少加到30
"""

import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from game_logic.game_engine import TexasHoldemGame
from game_logic.player import Player

def test_raise_issue():
    """测试加注规则问题"""
    print("=== 测试德扑游戏加注规则问题 ===")
    
    # 创建游戏
    game = TexasHoldemGame(min_bet=10)
    
    # 创建玩家
    player_a = Player(user_id=1, nickname="玩家A", position=0, chips=1000)
    player_b = Player(user_id=2, nickname="玩家B", position=1, chips=1000)
    
    # 添加玩家
    game.add_player(player_a.user_id, player_a.nickname, player_a.chips, player_a.position)
    game.add_player(player_b.user_id, player_b.nickname, player_b.chips, player_b.position)
    
    # 设置玩家在线
    game.connected_players = {1, 2}
    
    # 开始游戏
    game.start_game()
    
    # 下盲注
    game._post_blinds()
    
    print(f"初始状态:")
    print(f"- 大盲注: {game.min_bet}")
    print(f"- 当前台面下注: {game.current_bet}")
    print(f"- 上一次加注增量: {game.last_raise_increment}")
    
    # 获取玩家状态
    players = game.player_manager.to_dict_list()
    for p in players:
        if p['user_id'] == 1:
            print(f"- 玩家A下注: {p['current_bet']} (小盲)")
        elif p['user_id'] == 2:
            print(f"- 玩家B下注: {p['current_bet']} (大盲)")
    
    # 场景1: 玩家B跟注5
    print("\n=== 场景1: 玩家B跟注 ===")
    player_b_action = game.player_action(player_b.user_id, "call", 0)
    print(f"玩家B跟注结果: {player_b_action['message']}")
    print(f"- 当前台面下注: {game.current_bet}")
    print(f"- 上一次加注增量: {game.last_raise_increment}")
    
    # 场景2: 玩家A加注10（加注到20）
    print("\n=== 场景2: 玩家A加注10（加注到20） ===")
    # 计算最小加注额
    call_amount = game.current_bet - player_a.current_bet
    min_raise_amount = call_amount + game.last_raise_increment
    min_raise_to = player_a.current_bet + min_raise_amount
    print(f"- 玩家A跟注所需金额: {call_amount}")
    print(f"- 上一次加注金额: {game.last_raise_increment}")
    print(f"- 最小加注额: {min_raise_amount} (跟注所需金额{call_amount} + 上一次加注金额{game.last_raise_increment})")
    print(f"- 最小加注到: {min_raise_to}")
    
    # 执行加注
    player_a_action = game.player_action(player_a.user_id, "raise", 20)
    print(f"玩家A加注结果: {player_a_action['message']}")
    print(f"- 当前台面下注: {game.current_bet}")
    print(f"- 上一次加注增量: {game.last_raise_increment}")
    
    # 场景3: 玩家B加注20（加注到40）
    print("\n=== 场景3: 玩家B加注20（加注到40） ===")
    # 计算最小加注额
    call_amount = game.current_bet - player_b.current_bet
    min_raise_amount = call_amount + game.last_raise_increment
    min_raise_to = player_b.current_bet + min_raise_amount
    print(f"- 玩家B跟注所需金额: {call_amount}")
    print(f"- 上一次加注金额: {game.last_raise_increment}")
    print(f"- 最小加注额: {min_raise_amount} (跟注所需金额{call_amount} + 上一次加注金额{game.last_raise_increment})")
    print(f"- 最小加注到: {min_raise_to}")
    
    # 执行加注
    player_b_action = game.player_action(player_b.user_id, "raise", 40)
    print(f"玩家B加注结果: {player_b_action['message']}")
    print(f"- 当前台面下注: {game.current_bet}")
    print(f"- 上一次加注增量: {game.last_raise_increment}")
    
    # 场景4: 玩家A再次加注，最小加注额应该是20，但实际提示至少加到30
    print("\n=== 场景4: 玩家A再次加注，问题重现 ===")
    # 计算最小加注额
    call_amount = game.current_bet - player_a.current_bet
    min_raise_amount = call_amount + game.last_raise_increment
    min_raise_to = player_a.current_bet + min_raise_amount
    print(f"- 玩家A当前下注: {player_a.current_bet}")
    print(f"- 玩家A跟注所需金额: {call_amount}")
    print(f"- 上一次加注金额: {game.last_raise_increment}")
    print(f"- 最小加注额: {min_raise_amount} (跟注所需金额{call_amount} + 上一次加注金额{game.last_raise_increment})")
    print(f"- 最小加注到: {min_raise_to}")
    
    # 检查问题：如果玩家A输入20（加注到60），是否满足最小加注要求
    target_amount = 60  # 玩家A想加注到60（加注20）
    if target_amount < min_raise_to:
        print(f"❌ 问题重现：玩家A想加注到{target_amount}，但最小需要加注到{min_raise_to}")
        print(f"   前端会提示：至少加到 {min_raise_to}")
    else:
        print(f"✅ 玩家A可以加注到{target_amount}，满足最小加注要求")

if __name__ == "__main__":
    test_raise_issue()