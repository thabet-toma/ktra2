from django.core.management.base import BaseCommand
from django.db import transaction
from tenants.models import Tenant, Currency
from accounting.models import Account, FiscalPeriod
from datetime import date
from django.utils import timezone

ACCOUNT_TREE = [
    ('1000', 'الأصول', 'Asset', None),
    ('1100', 'النقدية', 'Asset', '1000'),
    ('1101', 'صندوق 1', 'Asset', '1100'),
    ('1200', 'البنوك', 'Asset', '1000'),
    ('1300', 'المدينون', 'Asset', '1000'),
    ('1400', 'المخزون', 'Asset', '1000'),
    ('2000', 'الالتزامات', 'Liability', None),
    ('2100', 'الدائنون', 'Liability', '2000'),
    ('2200', 'قروض', 'Liability', '2000'),
    ('3000', 'حقوق الملكية', 'Equity', None),
    ('3100', 'رأس المال', 'Equity', '3000'),
    ('3200', 'الأرباح المحتجزة', 'Equity', '3000'),
    ('4000', 'الإيرادات', 'Revenue', None),
    ('4100', 'مبيعات', 'Revenue', '4000'),
    ('5000', 'المصاريف', 'Expense', None),
    ('5100', 'تكلفة المبيعات', 'Expense', '5000'),
    ('5200', 'مصاريف تشغيلية', 'Expense', '5000'),
]


class Command(BaseCommand):
    help = 'Idempotent: creates minimum Tenant + Currencies + Account tree + FiscalPeriod.'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, default='الشركة الرئيسية', help='Tenant name')

    @transaction.atomic
    def handle(self, *args, **options):
        name = options['name']
        tenant, created = Tenant.objects.get_or_create(
            TenantID=1,
            defaults={'CompanyName': name}
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Tenant created: {name}'))
        else:
            self.stdout.write(f'Tenant already exists: {tenant.CompanyName}')

        currencies_data = {'ILS': '₪', 'USD': '$'}
        for code, symbol in currencies_data.items():
            cur, cur_created = Currency.objects.get_or_create(
                Code=code,
                defaults={'Symbol': symbol, 'IsBaseCurrency': code == 'ILS'}
            )
            if cur_created:
                self.stdout.write(f'  Currency created: {code}')
            else:
                self.stdout.write(f'  Currency exists: {code}')

        code_map = {}
        for item in ACCOUNT_TREE:
            code, name, acc_type, parent_code = item
            parent = code_map.get(parent_code) if parent_code else None
            acc, acc_created = Account.objects.get_or_create(
                tenant=tenant, code=code,
                defaults={'name': name, 'account_type': acc_type, 'parent': parent, 'is_active': True}
            )
            code_map[code] = acc
            if acc_created:
                self.stdout.write(f'  Account created: {code} {name}')
            else:
                if acc.name != name or acc.account_type != acc_type or acc.parent != parent:
                    acc.name = name
                    acc.account_type = acc_type
                    acc.parent = parent
                    acc.save()
                    self.stdout.write(f'  Account updated: {code} {name}')

        today = timezone.localdate()
        year = today.year
        fp, fp_created = FiscalPeriod.objects.get_or_create(
            tenant=tenant, name=str(year),
            defaults={
                'start_date': date(year, 1, 1),
                'end_date': date(year, 12, 31),
                'is_closed': False,
                'is_active': True,
            }
        )
        if fp_created:
            self.stdout.write(f'  FiscalPeriod created: {year}')
        else:
            self.stdout.write(f'  FiscalPeriod exists: {year}')

        self.stdout.write(self.style.SUCCESS('Minimum tenant seed complete.'))
