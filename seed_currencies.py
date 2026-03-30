import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from tenants.models import Currency

currencies = [
    {'CurrencyID': 1, 'Code': 'ILS', 'Name': 'Israeli New Shekel', 'Symbol': '₪', 'IsBaseCurrency': True},
    {'CurrencyID': 2, 'Code': 'USD', 'Name': 'United States Dollar', 'Symbol': '$', 'IsBaseCurrency': False},
    {'CurrencyID': 3, 'Code': 'EUR', 'Name': 'Euro', 'Symbol': '€', 'IsBaseCurrency': False},
    {'CurrencyID': 4, 'Code': 'JOD', 'Name': 'Jordanian Dinar', 'Symbol': 'د.أ', 'IsBaseCurrency': False},
]

for curr_data in currencies:
    curr, created = Currency.objects.get_or_create(
        CurrencyID=curr_data['CurrencyID'],
        defaults={
            'Code': curr_data['Code'],
            'Name': curr_data['Name'],
            'Symbol': curr_data['Symbol'],
            'IsBaseCurrency': curr_data['IsBaseCurrency']
        }
    )
    if created:
        print(f"تمت إضافة العملة: {curr_data['Code']}")
    else:
        # Update if exists but different
        updated = False
        if curr.Code != curr_data['Code']:
            curr.Code = curr_data['Code']
            updated = True
        if updated:
            curr.save()
            print(f"تم تحديث العملة: {curr_data['Code']}")
        else:
            print(f"العملة موجودة بالفعل: {curr_data['Code']}")
