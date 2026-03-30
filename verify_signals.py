import os
import django
import sys
import datetime

# Redirect output
log_file = open('verify_signals_output.txt', 'w', encoding='utf-8')
sys.stdout = log_file
sys.stderr = log_file

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from partners.models import Partner
from accounting.models import Account, JournalHeader, JournalLine
from tenants.models import Tenant

def run_verify():
    print("--- VERIFYING SIGNALS ---")
    tenant = Tenant.objects.first()
    if not tenant:
        print("ERROR: No tenant found.")
        return

    # Create new Supplier with Opening Balance
    try:
        print("\nCreating Test Supplier...")
        supplier = Partner.objects.create(
            Tenant=tenant,
            Name="Signal Test Supplier",
            Type="Supplier",
            OpeningBalance=1250.00,
            OpeningBalanceDate=datetime.date.today(),
            Currency_id=1 # Assuming 1 exists
        )
        print(f"Supplier created: {supplier.Name} (ID: {supplier.PartnerID})")
        
        # Reload to get updated fields
        supplier.refresh_from_db()
        
        # 1. Verify Linked Account
        if supplier.LinkedAccount:
            print(f"PASS: Linked Account Created: {supplier.LinkedAccount.code} - {supplier.LinkedAccount.name}")
        else:
            print("FAIL: No Linked Account created.")
            
        # 2. Verify Opening Balance Journal
        journal = JournalHeader.objects.filter(
            reference_type='PARTNER_OPENING',
            reference_id=supplier.PartnerID
        ).first()
        
        if journal:
            print(f"PASS: Opening Balance Journal Created: ID {journal.id} - {journal.description}")
            print(f"Posted: {journal.is_posted}")
            
            lines = journal.lines.all()
            for line in lines:
                print(f"  Line: {line.account.name} | Dr: {line.debit} | Cr: {line.credit}")
                
            # Verify amounts
            # Supplier -> Credit Partner, Debit Offset
            partner_line = lines.filter(account=supplier.LinkedAccount).first()
            if partner_line and partner_line.credit == 1250.00:
                 print("PASS: Partner Account Credited correctly.")
            else:
                 print(f"FAIL: Partner Account line incorrect. Found: {partner_line}")

        else:
             print("FAIL: No Opening Balance Journal found.")
             
    except Exception as e:
        print(f"ERROR: {e}")

    log_file.close()

if __name__ == "__main__":
    run_verify()
