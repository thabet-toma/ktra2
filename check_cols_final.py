import mysql.connector

try:
    conn = mysql.connector.connect(host="localhost", user="root", password="123456", database="global_erp_pro")
    cursor = conn.cursor()
    cursor.execute("DESCRIBE partners")
    cols = [row[0] for row in cursor.fetchall()]
    print(f"Columns: {cols}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
