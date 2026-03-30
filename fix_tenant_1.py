import os
import django
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.models import FiscalPeriod
from tenants.models import Tenant

def fix_tenant_1():
    RELEVANT_TENANT_ID = 1
    print(f"--- Fixing Fiscal Period for Tenant {RELEVANT_TENANT_ID} ---")
    
    # Check if period exists
    exists = FiscalPeriod.objects.filter(
        tenant_id=RELEVANT_TENANT_ID,
        start_date__lte=datetime.date(2026, 2, 1),
        end_date__gte=datetime.date(2026, 2, 1),
        status='Open'
    ).exists()
    
    if exists:
        print("Fiscal Period for Tenant 1 ALREADY EXISTS (Feb 2026 is covered).")
        # List them just to be sure
        for p in FiscalPeriod.objects.filter(tenant_id=RELEVANT_TENANT_ID):
            print(f"  - {p.name}: {p.start_date} -> {p.end_date} [{p.status}]")
    else:
        print("Creating Fiscal Year 2026 for Tenant 1...")
        try:
            # unique name to avoid collision if run multiple times
            fp = FiscalPeriod.objects.create(
                tenant_id=RELEVANT_TENANT_ID,
                name="Fiscal Year 2026 (Fixed)",
                start_date=datetime.date(2026, 1, 1),
                end_date=datetime.date(2026, 12, 31),
                status='Open'
            )
            print(f"SUCCESS: Created {fp}")
        except Exception as e:
            print(f"FAILED: {e}")

if __name__ == "__main__":
    fix_tenant_1()
