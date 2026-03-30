import os
import django
import sys

# Setup Django
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ktra.settings')
django.setup()

from accounting.models import Account
from tenants.models import Tenant

def debug_coa():
    print("--- Checking All Accounts (including soft-deleted) ---")
    all_accounts = Account.all_objects.all()
    print(f"Total accounts in DB: {all_accounts.count()}")
    for acc in all_accounts:
        print(f"ID: {acc.id}, Code: {acc.code}, Name: {acc.name}, IsDeleted: {acc.is_deleted}, Tenant: {acc.tenant_id}")

    print("\n--- Checking Active Accounts (Default Manager) ---")
    active_accounts = Account.objects.all()
    print(f"Total active accounts: {active_accounts.count()}")

    print("\n--- Attempting to create a test account ---")
    try:
        tenant = Tenant.objects.first()
        new_acc = Account.objects.create(
            tenant=tenant,
            code="DEBUG-101",
            name="Test Debug Account",
            account_type="Asset",
            is_active=True
        )
        print(f"Successfully created account ID: {new_acc.id}")
        new_acc.delete() # Hard delete or soft? Mixed in mixin it's soft
        print("Soft deleted test account.")
    except Exception as e:
        import traceback
        print(f"Error creating account: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    debug_coa()
