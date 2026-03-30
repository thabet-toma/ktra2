import os
import django
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.models import FiscalPeriod
from tenants.models import Tenant

def setup_periods():
    print("--- Checking Fiscal Periods ---")
    
    tenant = Tenant.objects.first()
    if not tenant:
        print("No tenant found. Assuming System (ID=0) setup.")
        tenant_id = 0
    else:
        tenant_id = tenant.TenantID
        print(f"Using Tenant: {tenant}")

    # Check for 2026
    start_date = datetime.date(2026, 1, 1)
    end_date = datetime.date(2026, 12, 31)
    
    exists = FiscalPeriod.objects.filter(
        tenant_id=tenant_id,
        start_date__lte=datetime.date(2026, 2, 1), # Check coverage for feb
        end_date__gte=datetime.date(2026, 2, 1)
    ).exists()
    
    if exists:
        print("Fiscal Period for Feb 2026 ALREADY EXISTS.")
        for p in FiscalPeriod.objects.filter(tenant_id=tenant_id):
             print(f"- {p}")
        return

    print("Creating Fiscal Year 2026...")
    try:
        if tenant_id != 0:
             # Need a Tenant instance for FK if not 0?
             # Model: tenant = ForeignKey(Tenant).
             # If tenant_id=0, we might need a dummy tenant or handle it raw.
             # But tenant_obj exists here.
             pass

        # Create 12 months or 1 year? 
        # Requirement was "FiscalPeriod". Usually monthly or yearly.
        # I'll create a full Year Open period for simplicity.
        
        fp = FiscalPeriod(
            tenant=tenant if tenant else None, # or handle ID manually if pure raw
            name="Fiscal Year 2026",
            start_date=start_date,
            end_date=end_date,
            status='Open'
        )
        if not tenant:
             fp.tenant_id = 0
             
        fp.save()
        print(f"SUCCESS: Created {fp}")
        
    except Exception as e:
        print(f"FAILED to create fiscal period: {e}")

if __name__ == "__main__":
    setup_periods()
