import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.models import Account, JournalLine

OUTPUT_FILE = 'debug_code_1_output.txt'

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    f.write("--- TARGETED DEBUG CODE '1' ---\n")
    
    # 1. Find the Account being filtered
    root = Account.objects.filter(code='1').first()
    if not root:
        f.write("CRITICAL: No Account found with code='1'\n")
        # Try searching by name
        f.write("Searching by name 'Asset'...\n")
        others = Account.objects.filter(name__icontains='Asset')
        for o in others:
            f.write(f" - Found: {o.name} | Code: '{o.code}' (Len: {len(o.code) if o.code else 0}) | ID: {o.id}\n")
    else:
        f.write(f"FOUND ROOT: {root.name} | ID: {root.id} | Code: '{root.code}'\n")
        
        # 2. Simulate View Logic (Code based)
        children = Account.objects.filter(code__startswith='1')
        f.write(f"Found {children.count()} children with code starting with '1':\n")
        child_ids = []
        for c in children:
            f.write(f" - [{c.id}] {c.code} : {c.name}\n")
            child_ids.append(c.id)
            
        # 3. Search Lines
        f.write(f"\nSearching for lines in IDs: {child_ids}\n")
        lines = JournalLine.objects.filter(account__id__in=child_ids)
        f.write(f"Total Lines Found: {lines.count()}\n")
        
        for line in lines:
            posted = "POSTED" if line.journal.is_posted else "DRAFT"
            f.write(f" > Line {line.id} | Account: {line.account.code} | Amount: {line.debit} | Status: {line.journal.is_posted}\n")

    f.write("\n--- END ---\n")
