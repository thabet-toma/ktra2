import mysql.connector

try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="123456"
    )
    cursor = conn.cursor()
    
    cursor.execute("SHOW DATABASES")
    databases = [db[0] for db in cursor.fetchall()]
    print(f"Databases: {databases}")
    
    for db in databases:
        if db in ['information_schema', 'mysql', 'performance_schema', 'sys']:
            continue
        print(f"\n--- Database: {db} ---")
        cursor.execute(f"USE {db}")
        cursor.execute("SHOW TABLES")
        tables = [t[0] for t in cursor.fetchall()]
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  Table {table}: {count} records")
            
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
