import mysql.connector

try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="global_erp_pro"
    )
    cursor = conn.cursor()
    
    print("--- CHECKING PARTNERS ---")
    cursor.execute("SELECT PartnerID, Name, TenantID, Type, is_deleted FROM partners")
    rows = cursor.fetchall()
    print(f"Found {len(rows)} partners")
    for row in rows:
        print(row)
        
    print("\n--- CHECKING TENANTS ---")
    cursor.execute("SELECT TenantID, CompanyName FROM tenants")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
