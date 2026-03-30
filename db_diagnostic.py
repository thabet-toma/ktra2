import os
import django
import sys

# Add current directory to path
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from tenants.models import Tenant
from partners.models import Partner
from inventory.models import Product

def run_check():
    print("--- DATABASE CHECK ---")
    tenants = Tenant.objects.all()
    print(f"Tenants count: {tenants.count()}")
    for t in tenants:
        print(f"  Tenant {t.TenantID}: {t.CompanyName}")
    
    partners = Partner.objects.all()
    print(f"Partners count: {partners.count()}")
    
    products = Product.objects.all()
    print(f"Products count: {products.count()}")
    
    if tenants.exists():
        first_tenant = tenants.first()
        print(f"First Tenant ID: {first_tenant.TenantID}")
        p_count = Partner.objects.filter(tenant=first_tenant).count()
        print(f"Partners for first tenant: {p_count}")

if __name__ == "__main__":
    run_check()
