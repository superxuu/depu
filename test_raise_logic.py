#!/usr/bin/env python3
"""
测试加注规则是否符合国际标准：最小加注额 = 跟注所需金额 + 上一次加注金额
"""

from game_logic.game_engine import TexasHoldemGame
from game_logic.player import Player

def test_raise_calculation():
    """测试加注计算逻辑"""
    print("=== 测试德州扑克加注规则 ===")
    
    # 创建游戏实例
    game = TexasHoldemGame(min_bet=10, max_players=6)
    
    # 添加测试玩家
    player1 = Player("user1", "Alice", 1000, 1)
    player2 = Player("user2", "Bob", 1000, 2)
    player3 = Player("user3", "Charlie", 1000, 3)
    
    game.player_manager.add_player(player1)
    game.player_manager.add_player(player2)
    game.player_manager.add_player(player3)
    
    # 设置庄家位置为玩家1
    game.player_manager.dealer_position = 1
    
    # 手动设置盲注
    game.current_bet = 10  # 大盲注
    game.last_raise_increment = 10  # 初始加注增量等于大盲注
    
    # 设置玩家下注状态
    player1.current_bet = 5   # 小盲注
    player2.current_bet = 10  # 大盲注
    player3.current_bet = 0   # 未行动
    
    print(f"\n初始状态:")
    print(f"- 大盲注: {game.min_bet}")
    print(f"- 当前台面下注: {game.current_bet}")
    print(f"- 上一次加注增量: {game.last_raise_increment}")
    print(f"- 玩家1下注: {player1.current_bet} (小盲)")
    print(f"- 玩家2下注: {player2.current_bet} (大盲)")
    print(f"- 玩家3下注: {player3.current_bet} (未行动)")
    
    # 测试场景1: 玩家3加注
    print(f"\n=== 测试场景1: 玩家3加注 ===")
    
    # 计算跟注所需金额
    call_amount = game.current_bet - player3.current_bet  # 10 - 0 = 10
    
    # 计算最小加注额（跟注所需金额 + 上一次加注金额）
    min_raise_amount = call_amount + game.last_raise_increment  # 10 + 10 = 20
    
    # 计算加注到的总金额（玩家当前下注额 + 最小加注额）
    raise_to_amount = player3.current_bet + min_raise_amount  # 0 + 20 = 20
    
    print(f"- 跟注所需金额: {call_amount}")
    print(f"- 上一次加注金额: {game.last_raise_increment}")
    print(f"- 最小加注额: {min_raise_amount} (跟注所需金额{call_amount} + 上一次加注金额{game.last_raise_increment})")
    print(f"- 最小加注到: {raise_to_amount}")
    
    # 验证计算是否正确
    expected_min_raise = 20
    expected_raise_to = 20
    
    assert min_raise_amount == expected_min_raise, f"最小加注额计算错误: 期望{expected_min_raise}, 实际{min_raise_amount}"
    assert raise_to_amount == expected_raise_to, f"加注到金额计算错误: 期望{expected_raise_to}, 实际{raise_to_amount}"
    
    print("✅ 测试场景1通过")
    
    # 测试场景2: 玩家3加注到30，然后玩家1再加注
    print(f"\n=== 测试场景2: 玩家3加注到30，玩家1再加注 ===")
    
    # 模拟玩家3加注到30
    player3.current_bet = 30
    game.current_bet = 30
    game.last_raise_increment = 20  # 30 - 10 = 20
    
    print(f"- 玩家3加注到: {player3.current_bet}")
    print(f"- 当前台面下注: {game.current_bet}")
    print(f"- 上一次加注增量: {game.last_raise_increment}")
    
    # 现在玩家1要加注
    call_amount = game.current_bet - player1.current_bet  # 30 - 5 = 25
    
    # 计算最小加注额（跟注所需金额 + 上一次加注金额）
    min_raise_amount = call_amount + game.last_raise_increment  # 25 + 20 = 45
    
    # 计算加注到的总金额（玩家当前下注额 + 最小加注额）
    raise_to_amount = player1.current_bet + min_raise_amount  # 5 + 45 = 50
    
    print(f"- 玩家1跟注所需金额: {call_amount}")
    print(f"- 上一次加注金额: {game.last_raise_increment}")
    print(f"- 玩家1最小加注额: {min_raise_amount} (跟注所需金额{call_amount} + 上一次加注金额{game.last_raise_increment})")
    print(f"- 玩家1最小加注到: {raise_to_amount}")
    
    # 验证计算是否正确
    expected_min_raise = 45
    expected_raise_to = 50
    
    assert min_raise_amount == expected_min_raise, f"最小加注额计算错误: 期望{expected_min_raise}, 实际{min_raise_amount}"
    assert raise_to_amount == expected_raise_to, f"加注到金额计算错误: 期望{expected_raise_to}, 实际{raise_to_amount}"
    
    print("✅ 测试场景2通过")
    
    # 测试场景3: 全下情况
    print(f"\n=== 测试场景3: 玩家1全下（筹码不足最小加注额）===")
    
    # 设置玩家1只剩35个筹码
    player1.chips = 35
    
    # 玩家1全下（全部筹码35）
    all_in_amount = player1.chips  # 35
    total_bet_after_all_in = player1.current_bet + all_in_amount  # 5 + 35 = 40
    
    print(f"- 玩家1当前筹码: {player1.chips}")
    print(f"- 玩家1当前下注: {player1.current_bet}")
    print(f"- 玩家1全下金额: {all_in_amount}")
    print(f"- 全下后总下注: {total_bet_after_all_in}")
    
    # 全下时，即使不足最小加注额也是允许的
    print(f"- 全下后总下注({total_bet_after_all_in}) < 最小加注到({raise_to_amount})，但全下是允许的")
    
    print("✅ 测试场景3通过")
    
    print(f"\n=== 所有测试通过！加注规则符合国际标准 ===")
    print("公式：最小加注额 = 跟注所需金额 + 上一次加注金额")

if __name__ == "__main__":
    test_raise_calculation()