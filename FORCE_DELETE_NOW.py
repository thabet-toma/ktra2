import MySQLdb
import sys

try:
    print("Connecting to database...")
    db = MySQLdb.connect(host="localhost", user="root", passwd="123456", db="global_erp_pro")
    cursor = db.cursor()
    
    print("Disabling foreign key checks...")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    
    print("Deleting ALL old accounts...")
    cursor.execute("DELETE FROM chartofaccounts")
    db.commit()
    print(f"Deleted accounts. Rows affected: {cursor.rowcount}")
    
    print("Deleting journal lines...")
    cursor.execute("DELETE FROM journal_lines")
    db.commit()
    
    print("Deleting journal headers...")
    cursor.execute("DELETE FROM journal_headers")
    db.commit()
    
    print("Clearing partner links...")
    cursor.execute("UPDATE partners SET LinkedAccountID = NULL, GroupID = NULL")
    db.commit()
    
    print("\nInserting ROOT accounts (1-5)...")
    cursor.execute("""
        INSERT INTO chartofaccounts (AccountID, TenantID, Code, Name, Type, IsActive) VALUES
        (1, 1, '1', 'الأصول (Assets)', 'Asset', 1),
        (2, 1, '2', 'الخصوم (Liabilities)', 'Liability', 1),
        (3, 1, '3', 'حقوق الملكية (Equity)', 'Equity', 1),
        (4, 1, '4', 'الإيرادات (Revenue)', 'Revenue', 1),
        (5, 1, '5', 'المصروفات (Expenses)', 'Expense', 1)
    """)
    db.commit()
    print("ROOT accounts created!")
    
    print("\nInserting sub-accounts...")
    cursor.execute("""
        INSERT INTO chartofaccounts (AccountID, TenantID, Code, Name, ParentID, Type, IsActive) VALUES
        (6, 1, '11', 'الأصول المتداولة', 1, 'Asset', 1),
        (7, 1, '1101', 'النقدية', 6, 'Asset', 1),
        (8, 1, '1102', 'البنوك', 6, 'Asset', 1),
        (9, 1, '1103', 'ذمم العملاء', 6, 'Asset', 1),
        (10, 1, '1104', 'المخزون', 6, 'Asset', 1),
        (11, 1, '12', 'الأصول غير المتداولة', 1, 'Asset', 1),
        (12, 1, '1201', 'الأراضي والمباني', 11, 'Asset', 1),
        (13, 1, '1202', 'الآلات والمعدات', 11, 'Asset', 1),
        (14, 1, '21', 'الخصوم المتداولة', 2, 'Liability', 1),
        (15, 1, '2101', 'ذمم الموردين', 14, 'Liability', 1),
        (16, 1, '2102', 'أوراق الدفع', 14, 'Liability', 1),
        (17, 1, '31', 'رأس المال', 3, 'Equity', 1),
        (18, 1, '32', 'الأرباح المحتجزة', 3, 'Equity', 1),
        (19, 1, '33', 'الأرصدة الافتتاحية', 3, 'Equity', 1),
        (20, 1, '3300', 'وسيط الأرصدة', 19, 'Equity', 1),
        (21, 1, '41', 'إيرادات المبيعات', 4, 'Revenue', 1),
        (22, 1, '51', 'تكلفة البضاعة المباعة', 5, 'Expense', 1),
        (23, 1, '52', 'المصروفات التشغيلية', 5, 'Expense', 1)
    """)
    db.commit()
    print("Sub-accounts created!")
    
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    
    cursor.execute("SELECT COUNT(*) FROM chartofaccounts")
    count = cursor.fetchone()[0]
    print(f"\n✅ SUCCESS! Total accounts now: {count}")
    
    db.close()
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    sys.exit(1)
