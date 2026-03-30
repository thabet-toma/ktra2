import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ktra.settings')
django.setup()

from partners.models import Partner
from inventory.models import Product, ProductCategory, UnitOfMeasure
from tenants.models import Tenant

def check_counts():
    print(f"Tenants: {Tenant.objects.count()}")
    print(f"Partners: {Partner.objects.count()}")
    print(f"Categories: {ProductCategory.objects.count()}")
    print(f"Products: {Product.objects.count()}")
    print(f"UOMs: {UnitOfMeasure.objects.count()}")

if __name__ == "__main__":
    check_counts()
