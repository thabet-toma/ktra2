import MySQLdb
try:
    conn = MySQLdb.connect(
        host="localhost",
        user="root",
        passwd="123456",
        db="global_erp_pro"
    )
    print("CONNECTION SUCCESSFUL")
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    print(f"Tables found: {len(tables)}")
    conn.close()
except Exception as e:
    print(f"CONNECTION FAILED: {e}")
