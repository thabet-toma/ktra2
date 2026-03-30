import os
import django
import sys
import datetime

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ktra_erp.settings')
django.setup()

from accounting.models import Account, JournalLine

OUTPUT_FILE = 'debug_gl_output.txt'

def get_all_child_accounts(acc):
    # Mimic the view logic EXACTLY
    children = Account.objects.filter(parent=acc)
    acc_list = {acc.id: acc}
    for child in children:
        sub_children = get_all_child_accounts(child)
        for sub in sub_children:
            acc_list[sub.id] = sub
    
    if acc.code:
         code_children = Account.objects.filter(code__startswith=acc.code).exclude(id__in=acc_list.keys())
         for child in code_children:
             acc_list[child.id] = child

    return list(acc_list.values())

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write("--- DEBUG GL START ---\n")
    
    # 1. Find Assets Account
    assets = Account.objects.filter(name__icontains='Asset').first() or Account.objects.filter(name__icontains='الأصول').first()
    
    if not assets:
        f.write("No 'Assets' account found.\n")
    else:
        f.write(f"Found Parent: {assets.name} (ID: {assets.id}, Code: {assets.code})\n")
        
        # 2. Find Children
        targets = get_all_child_accounts(assets)
        f.write(f"Found {len(targets)} total accounts in hierarchy:\n")
        target_ids = []
        for t in targets:
            f.write(f" - {t.name} (Code: {t.code}, ID: {t.id})\n")
            target_ids.append(t.id)
            
        # 3. Find Posted Lines
        lines = JournalLine.objects.filter(
            account__id__in=target_ids,
            journal__is_posted=True
        )
        f.write(f"\nTotal Posted Lines found: {lines.count()}\n")
        
        for line in lines:
            f.write(f" > Line {line.id}: Journal {line.journal.id} ({line.journal.transaction_date}) -> {line.account.name} | Dr: {line.debit} Cr: {line.credit}\n")

    f.write("--- DEBUG GL END ---\n")
