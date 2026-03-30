import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.models import Account, JournalHeader, JournalLine
from tenants.models import Tenant
from django.db import transaction

def test_creation():
    print("--- Debugging Journal Creation ---")
    
    tenant = Tenant.objects.first()
    if not tenant:
        print("No tenant found. Using ID 0 (System).")
        tenant_context = {'tenant_id': 0}
    else:
        print(f"Using Tenant: {tenant}")
        tenant_context = {'tenant': tenant}

    account = Account.objects.filter(is_active=True).first()
    if not account:
        print("ERROR: No active account found.")
        return

    print(f"Using Account: {account.id} - {account.name}")

    try:
        with transaction.atomic():
            # 1. Create Header
            header = JournalHeader.objects.create(
                transaction_date='2026-02-01',
                description='Debug Entry',
                **tenant_context
            )
            print(f"Header Created: ID {header.id}")

            # 2. Create Line
            line = JournalLine.objects.create(
                journal=header,
                account=account,
                debit=100,
                credit=0,
                **tenant_context
            )
            print(f"Line Created: ID {line.id} linked to Journal {line.journal_id}")
            
            # Verify count
            count = JournalLine.objects.filter(journal=header).count()
            print(f"Lines count for header {header.id}: {count}")
            
            if count == 0:
                print("CRITICAL FAILURE: Line created but not found via relation!")
            else:
                print("SUCCESS: Line persisted correctly.")
            
            # We will NOT rollback to leave evidence in DB, or rollback if we want clean test?
            # User wants to FIX it, so if this works, the issue is VIEW.
            # I'll raise Exception to rollback to keep DB clean.
            raise Exception("Rolling back test transaction")

    except Exception as e:
        print(f"Transaction Result: {e}")

if __name__ == "__main__":
    test_creation()
