import sqlite3
try:
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='partners';")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM partners")
        count = cursor.fetchone()[0]
        print(f"SQLite 'partners' table has {count} records")
        if count > 0:
            cursor.execute("SELECT Name FROM partners LIMIT 5")
            rows = cursor.fetchall()
            for row in rows:
                print(f"Partner in SQLite: {row[0]}")
    else:
        print("SQLite 'partners' table does not exist")
    conn.close()
except Exception as e:
    print(f"SQLite check failed: {e}")
