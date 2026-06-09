import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from tenants.models import Tenant, TenantSettings, TenantBook, UserCompanyMembership
from accounting.models import Account, Currency

logger = logging.getLogger(__name__)

COA_DATA = [
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

    # Expenses (5)
    ('51', 'تكلفة المبيعات (Cost of Goods Sold)', 'Expense', '5'),
    ('52', 'المصاريف التشغيلية (Operating Expenses)', 'Expense', '5'),
    ('5201', 'الرواتب والأجور (Salaries and Wages)', 'Expense', '52'),
    ('5202', 'الإيجار (Rent)', 'Expense', '52'),
    ('5203', 'المرافق - كهرباء ومياه (Utilities)', 'Expense', '52'),
    ('5204', 'التسويق والإعلان (Marketing)', 'Expense', '52'),
    ('5205', 'مصاريف السفر (Travel Expenses)', 'Expense', '52'),
    # Direct / Import-related expenses
    ('53', 'مصاريف الاستيراد المباشرة (Direct Import Expenses)', 'Expense', '5'),
    ('5301', 'مصاريف الشحن الدولي (International Shipping)', 'Expense', '53'),
    ('5302', 'مصاريف التخليص الجمركي (Customs Clearance Fees)', 'Expense', '53'),
    ('5303', 'الرسوم الجمركية (Customs Duties)', 'Expense', '53'),
    ('5304', 'مصاريف التأمين على الشحنات (Shipment Insurance)', 'Expense', '53'),
    ('5305', 'مصاريف الشحن المحلي (Local Shipping & Delivery)', 'Expense', '53'),
    ('5306', 'رسوم موانئ / تخزين (Port & Storage Fees)', 'Expense', '53'),
    ('5307', 'رسوم استيراد متنوعة (Misc. Import Fees)', 'Expense', '53'),
]

def create_company(name: str, creator_user) -> Tenant:
    """
    Creates a new Tenant, boots it with default settings, seeds its TenantBooks
    (10 per document type), seeds its professional Chart of Accounts (COA),
    and assigns a 'manager' membership to the creator_user.
    """
    if not name or not name.strip():
        raise ValidationError("اسم الشركة لا يمكن أن يكون فارغاً.")

    with transaction.atomic():
        # 1. Create Tenant
        tenant = Tenant.objects.create(
            CompanyName=name.strip(),
            SubscriptionPlan="Enterprise",
            Status="Active"
        )

        # 2. Create TenantSettings
        # Find base currency if available
        base_currency = Currency.objects.filter(IsBaseCurrency=True).first()
        TenantSettings.objects.create(
            tenant=tenant,
            company_name_primary=tenant.CompanyName,
            default_vat_rate=16.00,
            currency=base_currency
        )

        # 3. Seed TenantBooks
        for doc_type, doc_label in TenantBook.DOCUMENT_TYPES:
            for book_number in range(1, 11):
                TenantBook.objects.create(
                    tenant=tenant,
                    document_type=doc_type,
                    book_number=book_number,
                    name=f"{doc_label} — دفتر {book_number}",
                    last_used_number=0,
                    is_active=True
                )

        # 4. Seed Chart of Accounts
        account_map = {}
        for code, acc_name, acc_type, parent_code in COA_DATA:
            parent = account_map.get(parent_code) if parent_code else None
            account = Account.objects.create(
                tenant=tenant,
                code=code,
                name=acc_name,
                account_type=acc_type,
                parent=parent,
                is_active=True
            )
            account_map[code] = account

        # 5. Create UserCompanyMembership
        # If this is the user's only company, make it the default
        is_first = not UserCompanyMembership.objects.filter(user=creator_user).exists()
        UserCompanyMembership.objects.create(
            user=creator_user,
            tenant=tenant,
            role="manager",
            is_default=is_first
        )

        logger.info("Successfully booted new company '%s' (ID: %d) for user %s", tenant.CompanyName, tenant.TenantID, creator_user.username)
        return tenant
