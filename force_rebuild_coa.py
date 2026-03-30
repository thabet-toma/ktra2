import os
import django
from django.db import connection, transaction

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.models import Account, JournalHeader, JournalLine, AccountingAuditLog
from partners.models import PartnerGroup
from tenants.models import Tenant

def rebuild():
    print("--- FORCE REBUILD ACCOUNTING DATA & GROUPS ---")
    tenant = Tenant.objects.first()
    if not tenant:
        print("ERROR: No tenant found.")
        return

    with transaction.atomic():
        with connection.cursor() as cursor:
            print("Wiping data...")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            cursor.execute("TRUNCATE TABLE journal_lines;")
            cursor.execute("TRUNCATE TABLE journal_headers;")
            cursor.execute("TRUNCATE TABLE chartofaccounts;")
            cursor.execute("TRUNCATE TABLE accounting_audit_logs;")
            cursor.execute("TRUNCATE TABLE partner_groups;")
            cursor.execute("UPDATE partners SET GroupID = NULL;") 
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            print("Wipe complete.")

    # Seeding
    coa_data = [
        # 1. Assets
        ('1', 'الأصول (Assets)', 'Asset', None),
        ('11', 'الأصول المتداولة (Current Assets)', 'Asset', '1'),
        ('1101', 'النقدية (Cash)', 'Asset', '11'),
        ('1102', 'البنوك (Banks)', 'Asset', '11'),
        ('1103', 'ذمم العملاء (Accounts Receivable)', 'Asset', '11'),
        ('1104', 'المخزون (Inventory)', 'Asset', '11'),
        
        ('12', 'الأصول غير المتداولة (Non-Current Assets)', 'Asset', '1'),
        ('1201', 'الأراضي والمباني (Land & Buildings)', 'Asset', '12'),
        ('1202', 'الآلات والمعدات (Machinery & Equipment)', 'Asset', '12'),

        # 2. Liabilities
        ('2', 'الخصوم (Liabilities)', 'Liability', None),
        ('21', 'الخصوم المتداولة (Current Liabilities)', 'Liability', '2'),
        ('2101', 'ذمم الموردين (Accounts Payable)', 'Liability', '21'),
        ('2102', 'أوراق الدفع (Notes Payable)', 'Liability', '21'),

        # 3. Equity
        ('3', 'حقوق الملكية (Equity)', 'Equity', None),
        ('31', 'رأس المال (Capital)', 'Equity', '3'),
        ('32', 'الأرباح المحتجزة (Retained Earnings)', 'Equity', '3'),
        # Root for Opening Balances
        ('33', 'الأرصدة الافتتاحية (Opening Balances)', 'Equity', '3'),
        ('3300', 'وسيط الأرصدة الافتتاحية', 'Equity', '33'),

        # 4. Revenue
        ('4', 'الإيرادات (Revenue)', 'Revenue', None),
        ('41', 'إيرادات المبيعات (Sales Revenue)', 'Revenue', '4'),

        # 5. Expenses
        ('5', 'المصروفات (Expenses)', 'Expense', None),
        ('51', 'تكلفة البضاعة المباعة (Cost of Goods Sold)', 'Expense', '5'),
        ('52', 'المصروفات التشغيلية (Operating Expenses)', 'Expense', '5'),
    ]

    print("Seeding expert COA...")
    accounts_by_code = {}
    for code, name, acc_type, parent_code in coa_data:
        parent = accounts_by_code.get(parent_code)
        acc = Account.objects.create(
            code=code,
            name=name,
            account_type=acc_type,
            parent=parent,
            tenant=tenant,
            is_active=True
        )
        accounts_by_code[code] = acc
        print(f"  Created: {code} - {name}")

    # Seed Partner Groups
    print("\nSeeding Partner Groups...")
    
    # 1. Local Customers Group
    ar_acc = accounts_by_code.get('1103')
    PartnerGroup.objects.create(
        Tenant=tenant,
        Name="عملاء محليين (Local Customers)",
        Type='Customer',
        AccountReceivable=ar_acc
    )
    print("  Created: Local Customers Group")

    # 2. Local Suppliers Group
    ap_acc = accounts_by_code.get('2101')
    PartnerGroup.objects.create(
        Tenant=tenant,
        Name="موردين محليين (Local Suppliers)",
        Type='Supplier',
        AccountPayable=ap_acc
    )
    print("  Created: Local Suppliers Group")

    print("\n--- REBUILD COMPLETE ---")
    print(f"Final Account Count: {Account.objects.all().count()}")
    print(f"Final Group Count: {PartnerGroup.objects.all().count()}")

if __name__ == "__main__":
    rebuild()
