import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.models import Account, JournalHeader, JournalLine
from partners.models import Partner, PartnerGroup
from tenants.models import Tenant

print("=" * 50)
print("FORCE DELETE ALL ACCOUNTS")
print("=" * 50)

# 1. Clear all partner links
print("\n1. Clearing partner links...")
Partner.objects.all().update(LinkedAccount=None, Group=None)
print("   ✓ Partner links cleared")

# 2. Delete all journals
print("\n2. Deleting journals...")
JournalLine.objects.all().delete()
JournalHeader.objects.all().delete()
print("   ✓ Journals deleted")

# 3. Delete ALL accounts
print("\n3. Deleting ALL accounts...")
deleted_count = Account.objects.all().count()
Account.objects.all().delete()
print(f"   ✓ Deleted {deleted_count} accounts")

# 4. Verify deletion
remaining = Account.objects.all().count()
print(f"\n4. Verification: {remaining} accounts remaining")

if remaining == 0:
    print("\n✅ SUCCESS! All old accounts deleted.")
    print("\nNow creating new structure...")
    
    tenant = Tenant.objects.first()
    
    # Create ROOT accounts
    root_1 = Account.objects.create(code='1', name='الأصول (Assets)', account_type='Asset', tenant=tenant, is_active=True)
    root_2 = Account.objects.create(code='2', name='الخصوم (Liabilities)', account_type='Liability', tenant=tenant, is_active=True)
    root_3 = Account.objects.create(code='3', name='حقوق الملكية (Equity)', account_type='Equity', tenant=tenant, is_active=True)
    root_4 = Account.objects.create(code='4', name='الإيرادات (Revenue)', account_type='Revenue', tenant=tenant, is_active=True)
    root_5 = Account.objects.create(code='5', name='المصروفات (Expenses)', account_type='Expense', tenant=tenant, is_active=True)
    
    print("✓ Root accounts created (1-5)")
    
    # Create sub-accounts
    curr_assets = Account.objects.create(code='11', name='الأصول المتداولة', account_type='Asset', parent=root_1, tenant=tenant, is_active=True)
    Account.objects.create(code='1101', name='النقدية', account_type='Asset', parent=curr_assets, tenant=tenant, is_active=True)
    Account.objects.create(code='1102', name='البنوك', account_type='Asset', parent=curr_assets, tenant=tenant, is_active=True)
    ar_acc = Account.objects.create(code='1103', name='ذمم العملاء', account_type='Asset', parent=curr_assets, tenant=tenant, is_active=True)
    Account.objects.create(code='1104', name='المخزون', account_type='Asset', parent=curr_assets, tenant=tenant, is_active=True)
    
    curr_liab = Account.objects.create(code='21', name='الخصوم المتداولة', account_type='Liability', parent=root_2, tenant=tenant, is_active=True)
    ap_acc = Account.objects.create(code='2101', name='ذمم الموردين', account_type='Liability', parent=curr_liab, tenant=tenant, is_active=True)
    
    print("✓ Sub-accounts created")
    
    # Create Partner Groups
    PartnerGroup.objects.all().delete()
    PartnerGroup.objects.create(Tenant=tenant, Name='عملاء محليين', Type='Customer', AccountReceivable=ar_acc)
    PartnerGroup.objects.create(Tenant=tenant, Name='موردين محليين', Type='Supplier', AccountPayable=ap_acc)
    
    print("✓ Partner Groups created")
    
    final_count = Account.objects.all().count()
    print(f"\n✅ COMPLETE! Total accounts: {final_count}")
else:
    print(f"\n❌ ERROR: Still {remaining} accounts remaining!")
