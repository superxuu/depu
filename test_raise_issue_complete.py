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

def test_raise_issue():
    """测试加注规则问题"""
    print("=== 测试德扑游戏加注规则问题 ===")
    
    # 创建游戏
    game = TexasHoldemGame(min_bet=10)
    
    # 添加玩家
    game.add_player(1, "玩家A", 1000, 0)
    game.add_player(2, "玩家B", 1000, 1)
    
    # 设置玩家在线
    game.connected_players = {1, 2}
    
    # 开始游戏
    game.start_game()
    
    print(f"初始状态:")
    print(f"- 大盲注: {game.min_bet}")
    print(f"- 当前台面下注: {game.current_bet}")
    print(f"- 上一次加注增量: {game.last_raise_increment}")
    print(f"- 当前玩家位置: {game.current_player_position}")
    
    # 获取玩家状态
    players = game.player_manager.to_dict_list()
    for p in players:
        if p['user_id'] == 1:
            print(f"- 玩家A下注: {p['current_bet']} (小盲)")
        elif p['user_id'] == 2:
            print(f"- 玩家B下注: {p['current_bet']} (大盲)")
    
    # 场景1: 玩家A(小盲)加注到20（加注10）
    print("\n=== 场景1: 玩家A(小盲)加注到20（加注10） ===")
    player_a = game.player_manager.get_player(1)
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
    
    # 移动到下一个玩家
    game._move_to_next_player()
    print(f"- 当前玩家位置: {game.current_player_position}")
    
    # 场景2: 玩家B(大盲)加注到40（加注20）
    print("\n=== 场景2: 玩家B(大盲)加注到40（加注20） ===")
    player_b = game.player_manager.get_player(2)
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
    
    # 移动到下一个玩家
    game._move_to_next_player()
    print(f"- 当前玩家位置: {game.current_player_position}")
    
    # 场景3: 玩家A再次加注，最小加注额应该是20，但实际提示至少加到30
    print("\n=== 场景3: 玩家A再次加注，问题重现 ===")
    player_a = game.player_manager.get_player(1)
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
    
    # 分析问题原因
    print("\n=== 问题分析 ===")
    print(f"根据国际德扑规则，最小加注额应该是：跟注所需金额 + 上一次加注金额")
    print(f"在场景3中：")
    print(f"- 玩家A跟注所需金额: {call_amount} (当前台面下注{game.current_bet} - 玩家A当前下注{player_a.current_bet})")
    print(f"- 上一次加注金额: {game.last_raise_increment}")
    print(f"- 因此最小加注额: {call_amount} + {game.last_raise_increment} = {min_raise_amount}")
    print(f"- 最小加注到: 玩家A当前下注{player_a.current_bet} + 最小加注额{min_raise_amount} = {min_raise_to}")
    
    # 检查是否符合用户期望
    print("\n=== 用户期望 vs 实际结果 ===")
    print(f"用户期望：玩家A此时最小加注20")
    print(f"实际结果：最小加注到{min_raise_to}，即需要加注{min_raise_to - player_a.current_bet}")
    
    if min_raise_amount == 20:
        print(f"✅ 符合用户期望：最小加注额为20")
    else:
        print(f"❌ 不符合用户期望：最小加注额为{min_raise_amount}，用户期望为20")

if __name__ == "__main__":
    test_raise_issue()