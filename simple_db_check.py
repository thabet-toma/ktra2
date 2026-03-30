import MySQLdb
try:
    db = MySQLdb.connect(host="localhost", user="root", passwd="123456", db="global_erp_pro")
    cursor = db.cursor()
    cursor.execute("SELECT TenantID, CompanyName FROM tenants")
    for row in cursor.fetchall():
        print(row)
    db.close()
    print("DB connection successful!")
except Exception as e:
    print(f"Error: {e}")
