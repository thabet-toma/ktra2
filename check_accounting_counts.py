import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.models import Account, JournalHeader, JournalLine, FiscalPeriod
from tenants.models import Tenant

def check_db():
    print(f"Tenants: {Tenant.objects.count()}")
    for t in Tenant.objects.all():
        print(f"Tenant: {t.Name} (ID: {t.TenantID})")
        print(f"  Accounts: {Account.objects.filter(tenant=t).count()}")
        print(f"  Journal Headers: {JournalHeader.objects.filter(tenant=t).count()}")
        print(f"  Journal Lines: {JournalLine.objects.filter(tenant=t).count()}")
        print(f"  Fiscal Periods: {FiscalPeriod.objects.filter(tenant=t).count()}")

if __name__ == "__main__":
    check_db()
