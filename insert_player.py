import sqlite3

# 连接到数据库
conn = sqlite3.connect('poker_game.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 插入一条记录到room_players表
try:
    cursor.execute(
        "INSERT OR REPLACE INTO room_players (room_id, user_id, nickname, chips) VALUES (?, ?, ?, ?)",
        ('00000000-0000-0000-0000-000000000000', '111974a5-0a09-46d8-845b-0bd8754dc02d', 'TestUser', 1000)
    )
    conn.commit()
    print("记录插入成功")
    
    # 查询room_players表中的记录
    cursor.execute("SELECT * FROM room_players")
    rows = cursor.fetchall()
    
    if rows:
        print(f"room_players表中有{len(rows)}条记录:")
        for row in rows:
            print(dict(row))
    else:
        print("room_players表中没有记录")
except Exception as e:
    print(f"插入记录时出错: {e}")
finally:
    conn.close()