import os
import django
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.models import FiscalPeriod
from tenants.models import Tenant

def fix_periods():
    print("--- Fixing Fiscal Periods for 2026 ---")
    
    # 1. Get all tenants + None (for shared/system)
    try:
        tenants = list(Tenant.objects.all())
        tenant_ids = {t.TenantID for t in tenants}
    except Exception as e:
        print(f"Warning: Could not fetch tenants: {e}")
        tenant_ids = set()

    tenant_ids.add(0) # System tenant fallback
    
    print(f"Targeting Tenants: {tenant_ids}")

    start_date = datetime.date(2026, 1, 1)
    end_date = datetime.date(2026, 12, 31)

    for tid in tenant_ids:
        # Check if exists
        exists = FiscalPeriod.objects.filter(
            tenant_id=tid, 
            status='Open',
            start_date__lte=datetime.date(2026, 2, 1),
            end_date__gte=datetime.date(2026, 2, 1)
        ).exists()
        
        if exists:
            print(f"[Tenant {tid}] Period already exists.")
            continue
            
        print(f"[Tenant {tid}] Creating Fiscal Year 2026...")
        try:
            FiscalPeriod.objects.create(
                tenant_id=tid,
                name=f"Fiscal Year 2026 - Tenant {tid}",
                start_date=start_date,
                end_date=end_date,
                status='Open'
            )
            print(f"[Tenant {tid}] SUCCESS.")
        except Exception as e:
            print(f"[Tenant {tid}] FAILED: {e}")

if __name__ == "__main__":
    fix_periods()
