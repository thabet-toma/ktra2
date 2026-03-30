from django.core.management.base import BaseCommand
from accounting.models import Account
from tenants.models import Tenant
from django.db import transaction

class Command(BaseCommand):
    help = 'Seeds a true expert hierarchical Chart of Accounts'

    def handle(self, *args, **options):
        tenant = Tenant.objects.first()
        if not tenant:
            self.stdout.write(self.style.ERROR("No tenant found!"))
            return

        # (Code, Name, Type, ParentCode)
        coa_data = [
            # 1. Assets
            ('1', 'الأصول (Assets)', 'Asset', None),
            ('11', 'الأصول المتداولة (Current Assets)', 'Asset', '1'),
            ('1101', 'النقدية (Cash)', 'Asset', '11'),
            ('1102', 'البنوك (Banks)', 'Asset', '11'),
            ('1103', 'ذمم العملاء (Accounts Receivable)', 'Asset', '11'), # Parent for Customers
            ('1104', 'المخزون (Inventory)', 'Asset', '11'),
            
            ('12', 'الأصول غير المتداولة (Non-Current Assets)', 'Asset', '1'),
            ('1201', 'الأراضي والمباني (Land & Buildings)', 'Asset', '12'),
            ('1202', 'الآلات والمعدات (Machinery & Equipment)', 'Asset', '12'),
            ('1203', 'الأثاث والمفروشات (Furniture & Fixtures)', 'Asset', '12'),

            # 2. Liabilities
            ('2', 'الخصوم (Liabilities)', 'Liability', None),
            ('21', 'الخصوم المتداولة (Current Liabilities)', 'Liability', '2'),
            ('2101', 'ذمم الموردين (Accounts Payable)', 'Liability', '21'), # Parent for Suppliers
            ('2102', 'أوراق الدفع (Notes Payable)', 'Liability', '21'),
            ('2103', 'مصروفات مستحقة (Accrued Expenses)', 'Liability', '21'),
            
            ('22', 'الخصوم غير المتداولة (Long-term Liabilities)', 'Liability', '2'),
            ('2201', 'قروض طويلة الأجل (Long-term Loans)', 'Liability', '22'),

            # 3. Equity
            ('3', 'حقوق الملكية (Equity)', 'Equity', None),
            ('31', 'رأس المال (Capital)', 'Equity', '3'),
            ('32', 'الأرباح المحتجزة (Retained Earnings)', 'Equity', '3'),
            ('33', 'مسحوبات الشركاء (Partners Drawings)', 'Equity', '3'),

            # 4. Revenue
            ('4', 'الإيرادات (Revenue)', 'Revenue', None),
            ('41', 'إيرادات المبيعات (Sales Revenue)', 'Revenue', '4'),
            ('42', 'إيرادات أخرى (Other Income)', 'Revenue', '4'),

            # 5. Expenses
            ('5', 'المصروفات (Expenses)', 'Expense', None),
            ('51', 'تكلفة البضاعة المباعة (Cost of Goods Sold)', 'Expense', '5'),
            ('52', 'المصروفات التشغيلية (Operating Expenses)', 'Expense', '5'),
            ('5201', 'الرواتب والأجور (Salaries & Wages)', 'Expense', '52'),
            ('5202', 'الإيجارات (Rent)', 'Expense', '52'),
            ('5203', 'المنافع - كهرباء ومياه (Utilities)', 'Expense', '52'),
            ('5204', 'مصروفات تسويقية (Marketing Expenses)', 'Expense', '52'),
            ('5205', 'مصروفات إصلاح وصيانة (Repairs & Maintenance)', 'Expense', '52'),
        ]

        with transaction.atomic():
            self.stdout.write("Seeding expert COA...")
            accounts_by_code = {}
            
            for code, name, acc_type, parent_code in coa_data:
                parent = accounts_by_code.get(parent_code)
                
                acc, created = Account.objects.update_or_create(
                    code=code,
                    tenant=tenant,
                    defaults={
                        'name': name,
                        'account_type': acc_type,
                        'parent': parent,
                        'is_active': True
                    }
                )
                accounts_by_code[code] = acc
                
                status = "Created" if created else "Updated"
                self.stdout.write(f"  [{status}] {code} - {name}")

        self.stdout.write(self.style.SUCCESS("Expert COA seeded successfully."))
