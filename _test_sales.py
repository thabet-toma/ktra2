"""Smoke test for sales save + auto-post logic."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from tenants.models import Tenant
from sales.services import get_or_create_sales_settings, get_or_create_default_customer

tenant = Tenant.objects.first()
print('Tenant:', tenant)
if not tenant:
    print('NO TENANT')
    raise SystemExit(0)

cust = get_or_create_default_customer(tenant)
print('Default customer:', cust.id, cust.name)

ss = get_or_create_sales_settings(tenant)
print('Settings:', ss.id, 'default_customer=', ss.default_customer_id, 'rev_product=', ss.default_revenue_account_product_id, 'vat=', ss.default_vat_rate_id)
