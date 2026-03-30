import os
import django
import sys

# Redirect output
log_file = open('verify_groups_output.txt', 'w', encoding='utf-8')
sys.stdout = log_file
sys.stderr = log_file

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner, PartnerGroup
from accounting.models import Account
from tenants.models import Tenant

def run_verify():
    print("--- VERIFYING PARTNER GROUPS ---")
    tenant = Tenant.objects.first()
    
    # 1. Fetch Group
    group = PartnerGroup.objects.filter(Name__contains="Local Suppliers").first()
    if not group:
        print("FAIL: 'Local Suppliers' group not found.")
        return
    print(f"PASS: Group Found: {group.Name} (AP Account: {group.AccountPayable.code})")

    # 2. Create Partner with Group
    print("\nCreating Partner with Group...")
    partner = Partner.objects.create(
        Tenant=tenant,
        Name="Grouped Supplier Test",
        Type="Supplier",
        Group=group,
        Currency_id=1
    )
    
    # Reload
    partner.refresh_from_db()
    
    # 3. Verify Account Creation
    if partner.LinkedAccount:
        print(f"PASS: Linked Account Created: {partner.LinkedAccount.code} - {partner.LinkedAccount.name}")
        
        # Verify parent is the Group's AP account
        if partner.LinkedAccount.parent == group.AccountPayable:
            print("PASS: Linked Account matches Group Control Account.")
        else:
             print(f"FAIL: Parent mismatch. Expected {group.AccountPayable.code}, Got {partner.LinkedAccount.parent.code if partner.LinkedAccount.parent else 'None'}")
    else:
        print("FAIL: No Linked Account created.")

    log_file.close()

if __name__ == "__main__":
    run_verify()
