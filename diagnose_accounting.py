import os
import django
from datetime import date

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from tenants.models import Tenant
from accounting.models import FiscalPeriod, JournalHeader

def run_diagnosis():
    print("=== ACCOUNTING DIAGNOSIS TOOL ===")
    
    # 1. Check Tenants
    print("\n[1] CHECKING TENANTS:")
    tenants = Tenant.objects.all()
    if not tenants:
        print("  WARNING: No tenants found in database!")
    for t in tenants:
        print(f"  - ID: {t.TenantID}, Name: {t.Name}, Domain: {t.Domain}")

    # 2. Check Fiscal Periods
    print("\n[2] CHECKING FISCAL PERIODS (2026):")
    periods = FiscalPeriod.objects.all().order_by('tenant', 'start_date')
    if not periods:
        print("  WARNING: No fiscal periods found at all!")
    
    for p in periods:
        print(f"  - Tenant: {p.tenant_id} | {p.name} | {p.start_date} to {p.end_date} | Status: {p.status}")

    # 3. Check Recent Journals
    print("\n[3] RECENT JOURNAL ENTRIES:")
    recent = JournalHeader.objects.all().order_by('-id')[:5]
    for j in recent:
        print(f"  - ID: {j.id} | Date: {j.transaction_date} | Posted: {j.is_posted} | Tenant: {j.tenant_id}")
        lines = j.lines.all()
        print(f"    Lines: {lines.count()}")

    print("\n=== DIAGNOSIS COMPLETE ===")

if __name__ == "__main__":
    run_diagnosis()
