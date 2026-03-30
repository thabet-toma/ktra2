import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner, PartnerGroup
from accounting.models import Account

print("--- RECENT PARTNERS ---")
for p in Partner.objects.all().order_by('-PartnerID')[:5]:
    status = f"Linked to: {p.LinkedAccount.Code if p.LinkedAccount else 'NONE'}"
    group = f"Group: {p.Group.Name if p.Group else 'NONE'}"
    print(f"ID: {p.PartnerID} | Name: {p.Name} | Type: {p.Type} | {group} | {status}")

print("\n--- RECENT ACCOUNTS ---")
for a in Account.objects.all().order_by('-AccountID')[:5]:
    print(f"ID: {a.AccountID} | Code: {a.Code} | Name: {a.Name} | Parent: {a.Parent.Code if a.Parent else 'NONE'}")
