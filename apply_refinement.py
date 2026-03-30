import mysql.connector

try:
    conn = mysql.connector.connect(
        host='localhost',
        user='root',
        password='',
        database='global_erp_pro'
    )
    cursor = conn.cursor()
    
    with open('db/refinement_ops.sql', 'r', encoding='utf-8') as f:
        sql_script = f.read()
    
    # Simple split by semicolon (caution: won't handle semicolons in strings/comments, 
    # but our script is clean)
    commands = [cmd.strip() for cmd in sql_script.split(';') if cmd.strip()]
    
    for cmd in commands:
        print(f"Executing: {cmd[:50]}...")
        cursor.execute(cmd)
    
    conn.commit()
    cursor.close()
    conn.close()
    print("SQL execution successful")
except Exception as e:
    print(f"Error: {e}")
