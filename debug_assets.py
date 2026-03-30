import os
import django
import sys
import datetime

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ktra_erp.settings')
django.setup()

from accounting.models import Account, JournalLine

print("--- DEBUGGING ASSETS ACCOUNT ---")

# Try to find accounts named 'Assets' or similar
accounts = Account.objects.filter(name__icontains='Asset') | Account.objects.filter(name__icontains='الأصول')

if not accounts.exists():
    print("No account found with name 'Asset' or 'الأصول'")
else:
    for acc in accounts:
        print(f"\nAccount: {acc.name} (ID: {acc.id}, Code: {acc.code}, Parent: {acc.parent_id})")
        
        # Find ALL lines for this account
        all_lines = JournalLine.objects.filter(account=acc)
        print(f"  Total Lines Found: {all_lines.count()}")
        
        for line in all_lines:
            status = "POSTED" if line.journal.is_posted else "DRAFT"
            date = line.journal.transaction_date
            print(f"   - Line ID: {line.id} | Journal: {line.journal.id} | Date: {date} | Status: {status} | DR: {line.debit} | CR: {line.credit}")

print("\n--- END DEBUG ---")
