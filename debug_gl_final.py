import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings') # FIXED
django.setup()

from accounting.models import Account, JournalLine

OUTPUT_FILE = 'debug_gl_final.txt'

try:
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("--- DEBUG ACCOUNTS START ---\n")
        
        accounts = Account.objects.all().order_by('code')
        for acc in accounts:
            parent = acc.parent.code if acc.parent else "None"
            f.write(f"ID: {acc.id} | Code: {acc.code} | Name: {acc.name} | Parent: {parent}\n")

        f.write("\n--- POSTED LINES ---\n")
        lines = JournalLine.objects.filter(journal__is_posted=True)
        for line in lines:
            f.write(f"Line {line.id}: Account {line.account.code} ({line.account.name}) | Amount: {line.debit or line.credit}\n")

        f.write("--- DEBUG ACCOUNTS END ---\n")
except Exception as e:
    with open('debug_error.txt', 'w') as err:
        err.write(str(e))
