import os
import django
import sys
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.models import FiscalPeriod

def inspect():
    print("--- INSPECTING TENANT 1 PERIODS ---")
    sys.stdout.flush()
    
    periods = FiscalPeriod.objects.filter(tenant_id=1)
    print(f"Total Periods found: {periods.count()}")
    
    for p in periods:
        print(f"ID: {p.id}")
        print(f"Name: '{p.name}'")
        print(f"Start: {p.start_date} (Type: {type(p.start_date)})")
        print(f"End:   {p.end_date} (Type: {type(p.end_date)})")
        print(f"Status: '{p.status}'")
        print(f"Tenant: {p.tenant_id}")
        
        # Test comparison manually
        target = datetime.date(2026, 2, 1)
        start_ok = p.start_date <= target
        end_ok = p.end_date >= target
        status_ok = p.status == 'Open'
        
        print(f"  Match 2026-02-01? Start({start_ok}) End({end_ok}) Status({status_ok})")
        print("-" * 20)
        sys.stdout.flush()

if __name__ == "__main__":
    inspect()
