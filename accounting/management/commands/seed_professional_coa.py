from django.core.management.base import BaseCommand
from accounting.models import Account
from tenants.models import Tenant
from django.db import transaction

class Command(BaseCommand):
    help = 'Seeds a professional hierarchical Chart of Accounts.'

    def handle(self, *args, **options):
        # Force single tenant mode as per project context
        tenant = Tenant.objects.first()
        if not tenant:
            self.stdout.write(self.style.ERROR("No tenant found. Please create a tenant first."))
            return

        tenant_label = getattr(tenant, "CompanyName", None) or getattr(tenant, "Name", None) or f"#{tenant.pk}"
        self.stdout.write(f"Seeding professional COA for tenant: {tenant_label}")

        # Define Schema: (Code, Name, Type, ParentCode)
        # Type is only needed for Root nodes or if it changes (usually inherited)
        coa_data = [
            # Root Nodes
            ('1', 'الأصول (Assets)', 'Asset', None),
            ('2', 'الخصوم (Liabilities)', 'Liability', None),
            ('3', 'حقوق الملكية (Equity)', 'Equity', None),
            ('4', 'الإيرادات (Revenue)', 'Revenue', None),
            ('5', 'المصروفات (Expenses)', 'Expense', None),

            # Assets (1)
            ('11', 'الأصول المتداولة (Current Assets)', 'Asset', '1'),
            ('1101', 'النقدية (Cash)', 'Asset', '11'),
            ('1102', 'البنوك (Banks)', 'Asset', '11'),
            ('1103', 'المدينون التجاريون (Trade Receivables)', 'Asset', '11'),
            ('1104', 'المخزون (Inventory)', 'Asset', '11'),
            ('1105', 'ضريبة القيمة المضافة - مدخلات (VAT Input)', 'Asset', '11'),
            ('1106', 'دفعات مقدمة للموردين (Supplier Advances)', 'Asset', '11'),
            ('12', 'الأصول الثابتة (Fixed Assets)', 'Asset', '1'),
            ('1201', 'الأراضي (Land)', 'Asset', '12'),
            ('1202', 'المباني (Buildings)', 'Asset', '12'),
            ('1203', 'الآلات والمعدات (Machinery)', 'Asset', '12'),
            ('1204', 'الأثاث (Furniture)', 'Asset', '12'),

            # Liabilities (2)
            ('21', 'الالتزامات المتداولة (Current Liabilities)', 'Liability', '2'),
            ('2101', 'الدائنون التجاريون (Trade Payables)', 'Liability', '21'),
            ('2102', 'قروض قصيرة الأجل (Short-term Loans)', 'Liability', '21'),
            ('2103', 'مصاريف مستحقة (Accrued Expenses)', 'Liability', '21'),
            ('2104', 'ضريبة القيمة المضافة - مخرجات (VAT Output)', 'Liability', '21'),
            ('2105', 'رسوم جمركية مستحقة (Customs Duties Payable)', 'Liability', '21'),
            ('2106', 'بضاعة مُستلَمة لم تُفوتَر (GR/IR Clearing)', 'Liability', '21'),
            ('22', 'الالتزامات غير المتداولة (Non-current Liabilities)', 'Liability', '2'),
            ('2201', 'قروض طويلة الأجل (Long-term Loans)', 'Liability', '22'),

            # Equity (3)
            ('31', 'رأس المال (Capital)', 'Equity', '3'),
            ('3101', 'رأس المال المدفوع (Paid-in Capital)', 'Equity', '31'),
            ('32', 'الأرباح المحتجزة (Retained Earnings)', 'Equity', '3'),

            # Revenue (4)
            ('41', 'المبيعات (Sales)', 'Revenue', '4'),
            ('4101', 'مبيعات المنتجات (Product Sales)', 'Revenue', '41'),
            ('4102', 'مبيعات الخدمات (Service Sales)', 'Revenue', '41'),
            ('42', 'إيرادات أخرى (Other Revenue)', 'Revenue', '4'),
            ('4201', 'فروق صرف محقّقة (Realized FX Gain/Loss)', 'Revenue', '42'),

            # Expenses (5)
            ('51', 'تكلفة المبيعات (Cost of Goods Sold)', 'Expense', '5'),
            ('52', 'المصاريف التشغيلية (Operating Expenses)', 'Expense', '5'),
            ('5201', 'الرواتب والأجور (Salaries and Wages)', 'Expense', '52'),
            ('5202', 'الإيجار (Rent)', 'Expense', '52'),
            ('5203', 'المرافق - كهرباء ومياه (Utilities)', 'Expense', '52'),
            ('5204', 'التسويق والإعلان (Marketing)', 'Expense', '52'),
            ('5205', 'مصاريف السفر (Travel Expenses)', 'Expense', '52'),
            # Direct / Import-related expenses (for import/export ERP)
            ('53', 'مصاريف الاستيراد المباشرة (Direct Import Expenses)', 'Expense', '5'),
            ('5301', 'مصاريف الشحن الدولي (International Shipping)', 'Expense', '53'),
            ('5302', 'مصاريف التخليص الجمركي (Customs Clearance Fees)', 'Expense', '53'),
            ('5303', 'الرسوم الجمركية (Customs Duties)', 'Expense', '53'),
            ('5304', 'مصاريف التأمين على الشحنات (Shipment Insurance)', 'Expense', '53'),
            ('5305', 'مصاريف الشحن المحلي (Local Shipping & Delivery)', 'Expense', '53'),
            ('5306', 'رسوم موانئ / تخزين (Port & Storage Fees)', 'Expense', '53'),
            ('5307', 'رسوم استيراد متنوعة (Misc. Import Fees)', 'Expense', '53'),
        ]

        with transaction.atomic():
            created_count = 0
            updated_count = 0
            
            # Map for code lookup
            account_map = {acc.code: acc for acc in Account.objects.filter(tenant=tenant)}

            for code, name, acc_type, parent_code in coa_data:
                parent = None
                if parent_code:
                    parent = account_map.get(parent_code)
                    if not parent:
                         # Fallback search in case it was created in this loop but not in map
                         parent = Account.objects.filter(tenant=tenant, code=parent_code).first()

                account, created = Account.objects.get_or_create(
                    tenant=tenant,
                    code=code,
                    defaults={
                        'name': name,
                        'account_type': acc_type,
                        'parent': parent,
                        'is_active': True
                    }
                )

                if created:
                    created_count += 1
                    account_map[code] = account
                else:
                    # Update existing to ensure correct name/type/parent if re-seeding
                    # Only update if explicitly requested or if it's missing crucial info
                    changed = False
                    if account.name != name:
                        account.name = name
                        changed = True
                    if account.account_type != acc_type:
                        account.account_type = acc_type
                        changed = True
                    if account.parent != parent:
                        account.parent = parent
                        changed = True
                    
                    if changed:
                        account.save()
                        updated_count += 1
                
            self.stdout.write(self.style.SUCCESS(f"Finished seeding. Created: {created_count}, Updated: {updated_count}"))
            
            # Re-map orphans - if there are any existing accounts with codes starting with these prefixes
            self.stdout.write("Checking for orphans to re-parent...")
            orphans = Account.objects.filter(tenant=tenant, parent__isnull=True).exclude(code__in=[c[0] for c in coa_data])
            orphan_count = 0
            for acc in orphans:
                if not acc.code: continue
                # Longest prefix match
                for i in range(len(acc.code) - 1, 0, -1):
                    prefix = acc.code[:i]
                    if prefix in account_map:
                        acc.parent = account_map[prefix]
                        acc.save()
                        orphan_count += 1
                        break
            
            if orphan_count:
                self.stdout.write(self.style.SUCCESS(f"Re-parented {orphan_count} orphan accounts."))
