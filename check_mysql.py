import mysql.connector

try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="123456",
        database="global_erp_pro"
    )
    cursor = conn.cursor()
    
    tables = ['partners', 'products', 'product_categories', 'tenants', 'chartofaccounts']
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"Table {table}: {count} records")
        
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
