import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.serializers import AccountSerializer
from tenants.models import Tenant

# Check if tenant exists
tenant = Tenant.objects.first()
if not tenant:
    print("No tenants found in DB!")
else:
    print(f"Using Tenant: {tenant.TenantID}")
    data = {
        "Code": "12",
        "Name": "صندوق دولار",
        "Type": "Asset",
        "Parent": None,
        "IsActive": True,
        "Tenant": tenant.TenantID
    }
    serializer = AccountSerializer(data=data)
    if serializer.is_valid():
        print("Serializer is valid!")
    else:
        print(f"Serializer errors: {serializer.errors}")
