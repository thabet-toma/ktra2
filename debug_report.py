import os
import django
import sys
import datetime

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ktra_erp.settings')
django.setup()

from accounting.models import Account, JournalLine
from django.db.models import Sum

def get_all_child_accounts(acc):
    children = Account.objects.filter(parent=acc)
    acc_list = [acc]
    for child in children:
        acc_list.extend(get_all_child_accounts(child))
    return acc_list

try:
    # 1. Find "Assets" account (Usually code 1 or name contains Assets)
    assets = Account.objects.filter(name__icontains='Asset').first() or Account.objects.filter(name__icontains='الأصول').first()
    
    if not assets:
        print("Could not find 'Assets' account.")
    else:
        print(f"Found Account: {assets.name} (ID: {assets.id}, Code: {assets.code})")
        
        # 2. Test Recursion
        all_accounts = get_all_child_accounts(assets)
        print(f"Total Accounts in Hierarchy: {len(all_accounts)}")
        for a in all_accounts:
            print(f" - {a.name} (ID: {a.id})")

        # 3. Check for Posted Lines
        lines = JournalLine.objects.filter(
            account__in=all_accounts,
            journal__is_posted=True
        )
        print(f"Found {lines.count()} posted lines for this hierarchy.")
        
        for line in lines:
            print(f" Line ID: {line.id} | Journal: {line.journal.id} | Date: {line.journal.transaction_date} | Debit: {line.debit} | Credit: {line.credit}")

except Exception as e:
    print(f"Error: {e}")
