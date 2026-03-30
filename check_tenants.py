import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
try:
    django.setup()
    from tenants.models import Tenant
    tenants = list(Tenant.objects.all())
    print(f"Total Tenants: {len(tenants)}")
    for t in tenants:
        print(f"ID: {t.TenantID}, Name: {t.CompanyName}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
