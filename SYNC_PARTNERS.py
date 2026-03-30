import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner
from partners.signals import manage_partner_account

print("--- SYNCING PARTNER ACCOUNTS ---")

# Find partners without a linked account
partners_without_acc = Partner.objects.filter(LinkedAccount__isnull=True)

print(f"Found {partners_without_acc.count()} partners without accounts.")

for p in partners_without_acc:
    print(f"Processing ID: {p.PartnerID} | Name: {p.Name} | Type: {p.Type}")
    # Trigger the signal logic manually
    manage_partner_account(sender=Partner, instance=p, created=False)
    
    # Reload from DB to check status
    p.refresh_from_db()
    if p.LinkedAccount:
        print(f"  SUCCESS: Linked to {p.LinkedAccount.code} - {p.LinkedAccount.name}")
    else:
        # Check why it failed
        print(f"  FAILED: Still no account. Check if Parent account exists for type {p.Type}")

print("\n--- SYNC COMPLETED ---")
