import mysql.connector
import sys

try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="123456",
        database="global_erp_pro"
    )
    cursor = conn.cursor()
    
    print("Checking Partners table...")
    cursor.execute("SELECT COUNT(*) FROM partners")
    print(f"Partners count: {cursor.fetchone()[0]}")
    
    print("Checking Products table...")
    cursor.execute("SELECT COUNT(*) FROM products")
    print(f"Products count: {cursor.fetchone()[0]}")
    
    cursor.close()
    conn.close()
    print("Database connection and data check successful.")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
