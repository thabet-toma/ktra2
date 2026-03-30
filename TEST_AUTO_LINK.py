import os
import django
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner, PartnerGroup
from accounting.models import Account
from tenants.models import Tenant

print("=" * 60)
print("TESTING PARTNER-ACCOUNT AUTO-LINKING")
print("=" * 60)

tenant = Tenant.objects.first()

# 1. Check if Groups exist
print("\n1. Checking Partner Groups...")
groups = PartnerGroup.objects.all()
if groups.exists():
    for g in groups:
        print(f"   ✓ {g.Name} (Type: {g.Type})")
        if g.Type == 'Supplier':
            print(f"     AP Account: {g.AccountPayable.code if g.AccountPayable else 'None'}")
        else:
            print(f"     AR Account: {g.AccountReceivable.code if g.AccountReceivable else 'None'}")
else:
    print("   ❌ No groups found!")

# 2. Create a test supplier
print("\n2. Creating Test Supplier...")
supplier_group = PartnerGroup.objects.filter(Type='Supplier').first()

if supplier_group:
    test_supplier = Partner.objects.create(
        Tenant=tenant,
        Name="Test Supplier Auto-Link",
        Type="Supplier",
        Group=supplier_group,
        Currency_id=1
    )
    
    # Reload to get updated fields
    test_supplier.refresh_from_db()
    
    print(f"   ✓ Supplier created: {test_supplier.Name}")
    
    if test_supplier.LinkedAccount:
        print(f"   ✅ SUCCESS! Linked Account: {test_supplier.LinkedAccount.code} - {test_supplier.LinkedAccount.name}")
        print(f"   Parent Account: {test_supplier.LinkedAccount.parent.code if test_supplier.LinkedAccount.parent else 'None'}")
    else:
        print("   ❌ FAILED! No linked account created.")
else:
    print("   ❌ No supplier group found!")

# 3. Create a test customer
print("\n3. Creating Test Customer...")
customer_group = PartnerGroup.objects.filter(Type='Customer').first()

if customer_group:
    test_customer = Partner.objects.create(
        Tenant=tenant,
        Name="Test Customer Auto-Link",
        Type="Customer",
        Group=customer_group,
        Currency_id=1
    )
    
    test_customer.refresh_from_db()
    
    print(f"   ✓ Customer created: {test_customer.Name}")
    
    if test_customer.LinkedAccount:
        print(f"   ✅ SUCCESS! Linked Account: {test_customer.LinkedAccount.code} - {test_customer.LinkedAccount.name}")
        print(f"   Parent Account: {test_customer.LinkedAccount.parent.code if test_customer.LinkedAccount.parent else 'None'}")
    else:
        print("   ❌ FAILED! No linked account created.")
else:
    print("   ❌ No customer group found!")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
