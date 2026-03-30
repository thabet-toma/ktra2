import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from tenants.models import Currency

print("Available Currencies:")
for c in Currency.objects.all():
    print(f"ID: {c.CurrencyID}, Code: {c.Code}, Name: {c.Name}")
