import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from tenants.models import Tenant
from partners.models import Partner

def verify():
    print("Verifying Tenants...")
    try:
        tenant, created = Tenant.objects.get_or_create(
            CompanyName="Test Corp",
            defaults={'SubscriptionPlan': 'Pro', 'DomainName': 'test.com'}
        )
        print(f"Tenant verified: {tenant} (Created: {created})")
    except Exception as e:
        print(f"FAILED to access/create Tenant: {e}")
        return

    print("Verifying Partners...")
    try:
        partner = Partner.objects.create(
            Tenant=tenant,
            Name="Test Partner 2",
            Type="Customer",
            Phone="123456",
            Address="Test Address"
        )
        print(f"Partner created: {partner} (ID: {partner.PartnerID})")
    except Exception as e:
        print(f"FAILED to create Partner: {e}")

if __name__ == "__main__":
    verify()
