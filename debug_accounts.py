import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ktra_erp.settings')
django.setup()

from accounting.models import Account

print("ID | Code | Name | Parent ID")
for acc in Account.objects.all():
    pid = acc.parent_id if acc.parent_id else "None"
    print(f"{acc.id} | {acc.code} | {acc.name} | {pid}")
