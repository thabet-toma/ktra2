import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from tenants.models import Branch, BookHandoverRequest, Tenant, TenantSettings, TenantBook, UserCompanyMembership
from tenants.company_templates import COMPANY_TEMPLATES, DEFAULT_TEMPLATE
from accounting.models import Account, Currency
from core.plans import trial_end_date

logger = logging.getLogger(__name__)

# ISSUE #54: صلاحية طلب التسليم — أسبوعان، مثل دعوة الارتباط المحاسبي
# (`accountant_portal.PortalSettings.invitation_expiry_days` الافتراضي).
HANDOVER_REQUEST_EXPIRY_DAYS = 14

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
    # task13 M2: حسابات تشغيلية كانت مفقودة — دورة الشيكات وربط الصناديق
    # كانا يفشلان أو يرحّلان على حسابات خاطئة في أي شركة جديدة.
    ('1107', 'شيكات برسم التحصيل (Cheques Under Collection)', 'Asset', '11'),
    # CHQ-1: الورقة في اليد أصلٌ آخر غير الورقة في البنك — الفصل بينهما هو ما
    # يجعل «قيد الإيداع» ممكناً (1107 ÷ 1109) كما في دفترة والأصيل.
    # الكود 1109 لا 1108: **1108 مأخوذ إنتاجياً** لـ«بضاعة مسلَّمة لم تُفوتَر»
    # (`sales/services/flow.py` (`resolve_goods_delivered_unbilled_account`))
    # يُنشأ تلقائياً لأي شركة سلّمت بضاعة قبل فوترتها.
    ('1109', 'شيكات في المحفظة (Cheques in Hand)', 'Asset', '11'),
    ('1110', 'صناديق النقدية (Cash Boxes)', 'Asset', '11'),
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
    # task13 M2: آباء مخصصون لذمم شركاء اللوجستيات — كانت حسابات وكلاء الشحن
    # والمخلصين والنقل المحلي تُنشأ تحت القروض/المستحقات/ضريبة المخرجات (!).
    ('2106', 'ذمم وكلاء الشحن (Freight Forwarders Payable)', 'Liability', '21'),
    ('2107', 'ذمم المخلصين الجمركيين (Customs Brokers Payable)', 'Liability', '21'),
    ('2108', 'ذمم النقل المحلي (Local Transporters Payable)', 'Liability', '21'),
    ('2109', 'ذمم الناقلين (Carriers Payable)', 'Liability', '21'),
    # T-CHQ2: مرآة 1107 للجانب الصادر — الشيك الصادر التزام حتى يُصرف من
    # حسابنا. كان يُطابَق بالاسم فقط فيفشل ترحيل أي سند صرف بشيك.
    ('2111', 'شيكات برسم الدفع (Cheques Payable)', 'Liability', '21'),
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
    # T-CASHBOX M6: طرفا فرق جرد الصندوق — الزيادة إيراد والعجز مصروف.
    ('4202', 'زيادة الصندوق (Cash Overage)', 'Revenue', '42'),

    # Expenses (5)
    ('51', 'تكلفة المبيعات (Cost of Goods Sold)', 'Expense', '5'),
    ('52', 'المصاريف التشغيلية (Operating Expenses)', 'Expense', '5'),
    ('5201', 'الرواتب والأجور (Salaries and Wages)', 'Expense', '52'),
    ('5202', 'الإيجار (Rent)', 'Expense', '52'),
    ('5203', 'المرافق - كهرباء ومياه (Utilities)', 'Expense', '52'),
    ('5204', 'التسويق والإعلان (Marketing)', 'Expense', '52'),
    ('5205', 'مصاريف السفر (Travel Expenses)', 'Expense', '52'),
    ('5206', 'عجز الصندوق (Cash Shortage)', 'Expense', '52'),
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

#  الأكواد التي تتوقعها مسارات الترحيل (دورة الشيكات، ربط الصناديق، ذمم
#  شركاء اللوجستيات) — لا كل الأكواد تصلح لكل قالب. ISSUE #61: قالب «مكتب
#  محاسبة» يُسقط 2106-2109 عمداً من بذرته (لا مخزون ولا استيراد ⇒ لا وكلاء
#  شحن ولا مخلّصين ولا ناقلين)، فإعادة زرعها هنا كانت تنقض إسقاط البذرة.
OPERATIONAL_ACCOUNT_CODES = (
    "1107", "1109", "1110", "2106", "2107", "2108", "2109", "2111",
)


def ensure_operational_accounts(tenant) -> list[str]:
    """task13 M2 — يضمن وجود الحسابات التشغيلية في شجرة قائمة (idempotent).

    الشركات المبذورة قبل task13 تنقصها حسابات تتوقعها مسارات الترحيل:
    1107 شيكات برسم التحصيل، 1109 شيكات في المحفظة، 1110 صناديق النقدية،
    2106-2109 ذمم شركاء اللوجستيات، 2111 شيكات برسم الدفع. لا يُنشأ حساب إذا
    غاب أبوه (شجرة غير معيارية) — لا دمج أعمى. يعيد قائمة الأكواد المُنشأة.

    ISSUE #61: الحسابات المضمونة تُشتقّ من **بذرة قالب هذه الشركة** لا من
    COA_DATA دائماً — وإلا أعاد `heal_company_seed` زرع 2106-2109 في شجرة
    مكتب محاسبة أسقطتهما بذرتها عمداً. `general` (coa=None) يعني COA_DATA
    نفسها فتبقى بلا أي تغيير.
    """
    template_config = COMPANY_TEMPLATES.get(tenant.template) or COMPANY_TEMPLATES[DEFAULT_TEMPLATE]
    seed_rows = template_config['coa'] or COA_DATA
    needed = [row for row in seed_rows if row[0] in OPERATIONAL_ACCOUNT_CODES]
    created = []
    for code, acc_name, acc_type, parent_code in needed:
        if Account.objects.filter(tenant=tenant, code=code).exists():
            continue
        parent = Account.objects.filter(tenant=tenant, code=parent_code).first()
        if parent is None:
            logger.warning(
                "ensure_operational_accounts: tenant=%s missing parent %s — skipped %s",
                tenant.TenantID, parent_code, code,
            )
            continue
        Account.objects.create(
            tenant=tenant, code=code, name=acc_name,
            account_type=acc_type, parent=parent, is_active=True,
        )
        created.append(code)
    return created


def ensure_operational_account(tenant, code: str):
    """يضمن حساباً تشغيلياً واحداً ويعيده — يُنشئه ولو غاب أبوه المعياري.

    `ensure_operational_accounts` يتخطّى الحساب إن غاب أبوه (لا دمج أعمى في
    شجرة غير معيارية)، لكن مسارات الترحيل التي تستهلكه — كترحيل سند فيه شيك —
    تتوقّف عندها عمل المستخدم وتطلب منه تعيين الحساب يدوياً. فهنا نتدرّج في
    الأب: الأب المعياري ← جذر نوعه ← بلا أب، ولا نردّ المستخدم أبداً.
    """
    row = next((r for r in COA_DATA if r[0] == code), None)
    if row is None:
        return None
    _, acc_name, acc_type, parent_code = row

    def _existing():
        # بالكود أولاً، ثم بالاسم المعياري مهما كان نوعه أو حالته: الحساب
        # المعطَّل أو المصنَّف خطأً موجودٌ فعلاً، وإنشاء ثانٍ باسمه يكرّر الشجرة
        # (ويصطدم بقيد فريد على (tenant, name) في القواعد المُرحَّلة من 0001).
        return (
            Account.objects.filter(tenant=tenant, code=code).first()
            or Account.objects.filter(tenant=tenant, name=acc_name).first()
        )

    existing = _existing()
    if existing is not None:
        return existing

    parent = (
        Account.objects.filter(tenant=tenant, code=parent_code).first()
        or Account.objects.filter(tenant=tenant, code=parent_code[:1]).first()
    )
    if parent is None:
        logger.warning(
            "ensure_operational_account: tenant=%s creating %s without a parent "
            "(non-standard tree)", tenant.TenantID, code,
        )
    try:
        account = Account.objects.create(
            tenant=tenant, code=code, name=acc_name,
            account_type=acc_type, parent=parent, is_active=True,
        )
    except IntegrityError:
        # قيد فريد قديم أو سباق بين طلبين — لا يجوز أن يتحول إلى 500 في وجه
        # المستخدم وهو يحفظ سنداً. نعيد القراءة ونستعمل الموجود.
        logger.warning(
            "ensure_operational_account: tenant=%s insert of %s hit a unique "
            "constraint — reusing the existing account", tenant.TenantID, code,
        )
        return _existing()
    logger.info(
        "ensure_operational_account: tenant=%s created %s (%s) parent=%s",
        tenant.TenantID, code, acc_name, parent.code if parent else "-",
    )
    return account


DEFAULT_CURRENCIES = [
    # (Code, Name, Symbol) — الأول هو الأساسي عند غياب أي عملة أساسية
    ('ILS', 'شيكل', '₪'),
    ('USD', 'دولار', '$'),
]


def ensure_base_currencies():
    """يضمن وجود العملات الافتراضية ويعيد العملة الأساسية (idempotent).

    جدول العملات عام (بلا tenant) ولا تزرعه أي هجرة، فأي قاعدة تُبنى من صفر
    تبقى بجدول فارغ: نموذج فاتورة الشراء يرسل الرمز 'ILS' نصاً ثابتاً فيرفضه
    الخادم بـ «عنصر ب Code=ILS غير موجود». نزرعها هنا فلا تتكرر المصيدة.
    لا نغيّر عملة أساسية قائمة — إن وُجدت نحترمها كما هي.
    """
    for code, cur_name, symbol in DEFAULT_CURRENCIES:
        Currency.objects.get_or_create(
            Code=code, defaults={'Name': cur_name, 'Symbol': symbol},
        )
    base = Currency.objects.filter(IsBaseCurrency=True).first()
    if base is None:
        base = Currency.objects.filter(Code=DEFAULT_CURRENCIES[0][0]).first()
        if base is not None:
            base.IsBaseCurrency = True
            base.save(update_fields=['IsBaseCurrency'])
    return base


def create_company(
    name: str, creator_user, *,
    template: str = DEFAULT_TEMPLATE, managed_by: Tenant | None = None,
) -> Tenant:
    """
    Creates a new Tenant, boots it with default settings, seeds its TenantBooks
    (per the template's document types), seeds its Chart of Accounts (COA) per
    the template (`tenants/company_templates.py`), and assigns a 'manager'
    membership to the creator_user.

    ISSUE #50: `template` هو مفتاح كلمة (keyword-only) بافتراضي `general` عمداً
    — عشرات ملفات الاختبار تستدعي `create_company(name, user)` موضعياً، وبقاؤها
    تعمل بلا تعديل هو قرار 16 نفسه مطبَّقاً على التوافق.

    ISSUE #52: `managed_by` كلمة مفتاحية أيضاً — دفترٌ يديره مكتب محاسبة يمرّ
    من هذه الدالة نفسها لا مساراً موازياً، وإلا افترق الزرع (الحسابات والدفاتر
    والفرع والمستودع الافتراضي) بين الشركة العادية والدفتر المُدار.
    """
    if not name or not name.strip():
        raise ValidationError("اسم الشركة لا يمكن أن يكون فارغاً.")
    template_config = COMPANY_TEMPLATES.get(template)
    if template_config is None:
        raise ValidationError(f"قالب الشركة «{template}» غير معروف.")

    with transaction.atomic():
        # 1. Create Tenant
        # T-TRIAL: الشركة الجديدة تبدأ **تجريبية** بأربعة عشر يوماً — كانت تُنشأ
        # `Enterprise/Active`، أي بلا حدود وبلا تاريخ انتهاء مجاناً للأبد، فما
        # كانت التجربة تبدأ لأحد إلا بتدخّل يدوي من السوبر أدمن. حدود التجربة
        # حدود Pro (`core.plans.PLAN_DEFAULTS`)، والتمديد أو الترقية من لوحة
        # المنصة: تعديل التاريخ أو تبديل الخطة — والحدود تتبع الخطة تلقائياً.
        tenant = Tenant.objects.create(
            CompanyName=name.strip(),
            SubscriptionPlan="Trial",
            Status="Trial",
            subscription_ends_at=trial_end_date(),
            template=template_config['key'],
            managed_by=managed_by,
        )

        # 2. Create TenantSettings
        # Find base currency if available
        base_currency = ensure_base_currencies()
        TenantSettings.objects.create(
            tenant=tenant,
            company_name_primary=tenant.CompanyName,
            default_vat_rate=16.00,
            currency=base_currency
        )

        # 3. Seed TenantBooks — أنواع القالب فقط (`document_types=None` = الخمسة
        # عشر كاملةً كما تُنتَج اليوم).
        doc_type_labels = dict(TenantBook.DOCUMENT_TYPES)
        doc_types = template_config['document_types'] or list(doc_type_labels)
        for doc_type in doc_types:
            doc_label = doc_type_labels[doc_type]
            for book_number in range(1, 11):
                TenantBook.objects.create(
                    tenant=tenant,
                    document_type=doc_type,
                    book_number=book_number,
                    name=f"{doc_label} — دفتر {book_number}",
                    last_used_number=0,
                    is_active=True
                )

        # 4. Seed Chart of Accounts — بذرة القالب (`coa=None` = COA_DATA كما هي).
        account_map = {}
        coa_rows = template_config['coa'] or COA_DATA
        for code, acc_name, acc_type, parent_code in coa_rows:
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

        # 4.5 Main branch — every company starts with one
        Branch.objects.create(
            tenant=tenant, name="الفرع الرئيسي", code="MAIN", is_main=True, is_active=True)

        # 4.6 Default warehouse — وجهة استلام البضاعة الافتراضية
        from inventory.models import Product, Warehouse
        Warehouse.objects.create(
            tenant=tenant, name="المستودع الرئيسي", code="MAIN",
            is_default=True, is_active=True)

        # 4.7 Seed template services (ISSUE #78) — بند خدميّ لكل حساب أتعابٍ في
        # بذرة القالب، وإلا بقيت `4103`-`4106` حسابات ميتة بلا بندٍ يرحّل إليها.
        # `general` بلا `services` (`None`) فلا شيء يُزرع — لا خدمات تجارية مفترَضة.
        for sku, name_ar, account_code in template_config.get('services') or []:
            Product.objects.create(
                tenant=tenant, sku=sku, name_ar=name_ar, is_service=True,
                quantity_on_hand=0, avg_cost=0,
                sale_account_override=account_map.get(account_code),
            )

        # 5. Create UserCompanyMembership
        # If this is the user's only company, make it the default
        is_first = not UserCompanyMembership.objects.filter(
            user=creator_user, is_example_access=False,
        ).exists()
        UserCompanyMembership.objects.create(
            user=creator_user,
            tenant=tenant,
            role="manager",
            is_default=is_first
        )

        # The single-tenant auto-resolve cache must reset once a 2nd company exists.
        from core.tenant_utils import invalidate_tenant_cache
        invalidate_tenant_cache()

        logger.info("Successfully booted new company '%s' (ID: %d) for user %s", tenant.CompanyName, tenant.TenantID, creator_user.username)
        return tenant


# ── ISSUE #64: تبديل قالب الشركة (القرار 4 — يرفع القناع ولا ينزع المزروع) ──

def switch_company_template(tenant: Tenant, template: str, *, actor_user=None) -> dict:
    """يبدّل `tenant.template` ويزرع ما تحتاجه بذرة القالب الجديد ولا تملكه
    الشركة بعد — حسابات دليلٍ وأنواع دفاتر. **لا نزع إطلاقاً**: حسابٌ أو دفترٌ
    زرعه قالبٌ سابق يبقى كما هو (لا حذف، لا تعطيل `is_active`، لا إعادة تسمية) —
    القناع الحيّ (`TemplateSurfacePermission`) هو ما يخفيه عن القالب الجديد، لا
    محو الصفّ. حساب موجود بكودٍ يتكرر في القالبين (مثل `4102`) يبقى باسمه
    القديم — لا يُعاد إنشاؤه ولا يُعاد تسميته على بذرة القالب الجديد.

    ذرّي بالكامل (قفل صفّ الشركة)، ويعيد `{tenant, accounts_created,
    book_types_created}` كي تسجّله نقطة الـAPI في سجل التدقيق ويعرضه للمستخدم.
    """
    template_config = COMPANY_TEMPLATES.get(template)
    if template_config is None:
        raise ValidationError(f"قالب الشركة «{template}» غير معروف.")

    with transaction.atomic():
        tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
        old_template = tenant.template

        # 1) الحسابات الناقصة من بذرة القالب الجديد — الصفوف مرتّبة أباً قبل
        # ابنه في كلا السِجلّين (COA_DATA و ACCOUNTING_FIRM_COA)، فمرورٌ واحد
        # كافٍ. حسابٌ بنفس الكود موجود مسبقاً (من القالب القديم) يُترَك كما هو.
        coa_rows = template_config['coa'] or COA_DATA
        wanted_codes = [row[0] for row in coa_rows]
        account_map = {
            acc.code: acc
            for acc in Account.objects.filter(tenant=tenant, code__in=wanted_codes)
        }
        accounts_created: list[str] = []
        for code, acc_name, acc_type, parent_code in coa_rows:
            if code in account_map:
                continue
            parent = account_map.get(parent_code) if parent_code else None
            if parent_code and parent is None:
                logger.warning(
                    "switch_company_template: tenant=%s missing parent %s for "
                    "%s — skipped (seed row out of order?)",
                    tenant.TenantID, parent_code, code,
                )
                continue
            account = Account.objects.create(
                tenant=tenant, code=code, name=acc_name,
                account_type=acc_type, parent=parent, is_active=True,
            )
            account_map[code] = account
            accounts_created.append(code)

        # 2) أنواع الدفاتر الناقصة — أي نوعٍ للشركة منه دفترٌ واحد على الأقل
        # (من أي قالب) لا يُعاد زرعه، فلا تكرار على `unique_together`.
        doc_type_labels = dict(TenantBook.DOCUMENT_TYPES)
        doc_types = template_config['document_types'] or list(doc_type_labels)
        existing_doc_types = set(
            TenantBook.objects.filter(tenant=tenant, document_type__in=doc_types)
            .values_list('document_type', flat=True).distinct()
        )
        book_types_created: list[str] = []
        for doc_type in doc_types:
            if doc_type in existing_doc_types:
                continue
            doc_label = doc_type_labels[doc_type]
            for book_number in range(1, 11):
                TenantBook.objects.create(
                    tenant=tenant, document_type=doc_type, book_number=book_number,
                    name=f"{doc_label} — دفتر {book_number}",
                    last_used_number=0, is_active=True,
                )
            book_types_created.append(doc_type)

        tenant.template = template_config['key']
        tenant.save(update_fields=['template'])

        from accounting.models import AccountingAuditLog
        AccountingAuditLog.objects.create(
            tenant=tenant,
            user=actor_user,
            action='TEMPLATE_SWITCH',
            model_name='Tenant',
            object_id=tenant.pk,
            change_details=(
                f"template: {old_template} → {template_config['key']}; "
                f"accounts_created={accounts_created}; "
                f"book_types_created={book_types_created}"
            ),
        )

    # القناع الحيّ يقرأ `tenant.template` عبر get_tenant — النشر أحادي الشركة
    # يخزّن مرجعاً للكائن نفسه بمعزل عن هذه الصفقة (`core.tenant_utils`)، فبلا
    # هذا الإبطال يبقى القناع يقرأ القيمة القديمة حتى إعادة تشغيل العملية.
    from core.tenant_utils import invalidate_tenant_cache
    invalidate_tenant_cache()

    logger.info(
        "template_switch tenant=%s %s -> %s accounts_created=%s book_types_created=%s",
        tenant.TenantID, old_template, tenant.template, accounts_created, book_types_created,
    )
    return {
        'tenant': tenant,
        'accounts_created': accounts_created,
        'book_types_created': book_types_created,
    }


def set_example_company(tenant: Tenant | None) -> None:
    """يعيّن شركة المثال الوحيدة ويزامن عضويات الوصول التلقائية بأمان."""
    user_model = get_user_model()
    with transaction.atomic():
        # التعيين نادر ومنصة-فقط؛ قفل صفوف الشركات كلها يمنع طلبين متزامنين من
        # تعيين شركتين عندما لا تكون هناك شركة مثال سابقة لقفلها.
        list(Tenant.objects.select_for_update().values_list("pk", flat=True))
        Tenant.objects.filter(is_example=True).exclude(
            pk=getattr(tenant, "pk", None)
        ).update(is_example=False)
        UserCompanyMembership.objects.filter(is_example_access=True).delete()

        if tenant is None:
            logger.info("Example company cleared")
            return

        if not tenant.is_example:
            tenant.is_example = True
            tenant.save(update_fields=["is_example"])

        existing_user_ids = set(
            UserCompanyMembership.objects.filter(tenant=tenant)
            .values_list("user_id", flat=True)
        )
        UserCompanyMembership.objects.bulk_create([
            UserCompanyMembership(
                user_id=user_id,
                tenant=tenant,
                role="staff",
                is_example_access=True,
            )
            for user_id in user_model.objects.exclude(pk__in=existing_user_ids)
            .values_list("pk", flat=True)
        ])
        logger.info("Example company assigned tenant=%s", tenant.pk)


def ensure_example_company_access(user) -> None:
    """يلحق المستخدمين الذين سُجّلوا بعد التعيين بشركة المثال عند أول تحميل."""
    if user is None or not getattr(user, "is_authenticated", False):
        return
    example = Tenant.objects.filter(is_example=True).first()
    if example is None:
        return
    _, created = UserCompanyMembership.objects.get_or_create(
        user=user,
        tenant=example,
        defaults={"role": "staff", "is_example_access": True},
    )
    if created:
        logger.info("Example company access granted tenant=%s user=%s", example.pk, user.pk)


def member_payload(m: UserCompanyMembership) -> dict:
    """تمثيل عضوية موحّد — تستهلكه إدارة الشركة (المدير) ولوحة المنصة (السوبر أدمن)."""
    return {
        "membership_id": m.id,
        "user_id": m.user_id,
        "username": m.user.username,
        "email": m.user.email or "",
        "full_name": (f"{m.user.first_name} {m.user.last_name}").strip(),
        "role": m.role,
        "is_default": m.is_default,
        "can_access_import": m.can_access_import,
        "is_active": m.user.is_active,
        "created_at": m.created_at,
    }


def is_last_manager(tenant: Tenant, membership: UserCompanyMembership) -> bool:
    """هل هذه العضوية آخر مدير في الشركة؟ (كل طبقة ترفع خطأها الخاص)."""
    if membership.role != "manager":
        return False
    return not (
        UserCompanyMembership.objects
        .filter(tenant=tenant, role="manager")
        .exclude(id=membership.id)
        .exists()
    )


def create_branch(tenant: Tenant, name: str, code: str) -> Branch:
    """task11 M4 — إنشاء فرع تحت شركة أم.

    الفرع يشارك الشركة شجرةَ الحسابات والمنتجات والشركاء تلقائياً (لأنها
    على مستوى الـ tenant)، بينما تُعزل فواتيره ومخزونه وقيوده عبر بُعد
    branch. دفاتر ترقيمه تُنشأ تلقائياً عند أول مستند (get_next_number).
    """
    name = (name or "").strip()
    code = (code or "").strip().upper()
    if not name:
        raise ValidationError("اسم الفرع لا يمكن أن يكون فارغاً.")
    if not code:
        raise ValidationError("رمز الفرع مطلوب (يدخل في بادئة ترقيم المستندات).")
    if Branch.objects.filter(tenant=tenant, code=code).exists():
        raise ValidationError(f"رمز الفرع «{code}» مستخدم مسبقاً في هذه الشركة.")

    branch = Branch.objects.create(tenant=tenant, name=name, code=code, is_active=True)
    logger.info(
        "Created branch '%s' (code=%s, id=%d) under tenant %d",
        name, code, branch.pk, tenant.TenantID,
    )
    return branch


# ── ISSUE #54: تسليم الدفاتر (نمط Xero) ─────────────────────────────────

def create_handover_request(*, book: Tenant, requested_by, client_identifier: str) -> BookHandoverRequest:
    """يفتح طلب تسليم على دفتر مُدار — لا يمسّ `book` نفسه إطلاقاً.

    العميل مستخدمٌ **مسجَّل مسبقاً** على المنصة، بنفس قاعدة إضافة عضو
    (`TenantViewSet.members`): معرَّفٌ غير موجود يعني أن على العميل التسجيل
    أولاً — لا بنية دعوةٍ بالبريد الإلكتروني منفصلة.
    """
    if book.managed_by_id is None:
        raise ValidationError("هذا الدفتر ليس دفتراً مُداراً — لا تسليم لشركة عادية.")
    if BookHandoverRequest.objects.filter(book=book, status='pending').exists():
        raise ValidationError("يوجد طلب تسليم قائم على هذا الدفتر بالفعل.")

    from django.contrib.auth.models import User as AuthUser
    from django.db.models import Q

    ident = (client_identifier or "").strip()
    if not ident:
        raise ValidationError("اسم مستخدم العميل أو بريده الإلكتروني مطلوب.")
    client_user = AuthUser.objects.filter(
        Q(username__iexact=ident) | Q(email__iexact=ident)
    ).first()
    if client_user is None:
        raise ValidationError(
            "لا يوجد مستخدم بهذا الاسم/البريد. يجب أن يسجّل العميل حسابه أولاً."
        )

    request = BookHandoverRequest.objects.create(
        book=book,
        office_id=book.managed_by_id,
        invited_user=client_user,
        created_by=requested_by,
        expires_at=timezone.now() + timedelta(days=HANDOVER_REQUEST_EXPIRY_DAYS),
    )
    logger.info(
        "handover_request_created id=%s book=%s office=%s invited_user=%s",
        request.pk, book.pk, book.managed_by_id, client_user.pk,
    )
    return request


def accept_handover_request(*, request_id: int, accepting_user) -> BookHandoverRequest:
    """القبول وحده يُسقط `managed_by` — عَلَمُ ملكيةٍ بلا أي أثر محاسبي.

    ذرّي بالكامل (قفل صفّ الطلب والدفتر معاً)، ويُبقي عضويات المكتب على
    الدفتر كما هي — إلغاء وصول المكتب إجراءٌ منفصل صريح (`members/remove`
    القائم أصلاً)، لا يقع تلقائياً هنا.

    فحص الانتهاء (وتثبيته `expired`) خارج الصفقة الذرّية عمداً: لو كان داخلها
    لتراجع مع كل استثناء لاحق — طلبٌ يُرفَض لسببٍ آخر كان يعود `pending` رغم
    فوات وقته، ناقضاً «ينتهي بانتهاء صلاحيته».
    """
    request = BookHandoverRequest.objects.filter(pk=request_id).first()
    if request is None or request.invited_user_id != accepting_user.pk:
        # لا نفرّق «غير موجود» عن «ليس لك» — نفس حَكَم عزل الدفاتر المُدارة.
        raise ValidationError("طلب التسليم غير موجود.")
    if request.status == 'pending' and request.expires_at <= timezone.now():
        request.status = 'expired'
        request.save(update_fields=['status'])
    if request.status != 'pending':
        raise ValidationError("طلب التسليم لم يعد قابلاً للقبول (انتهت صلاحيته أو استُعمل سابقاً).")

    with transaction.atomic():
        request = BookHandoverRequest.objects.select_for_update().get(pk=request.pk)
        if request.status != 'pending':
            raise ValidationError("طلب التسليم لم يعد قابلاً للقبول (انتهت صلاحيته أو استُعمل سابقاً).")

        book = Tenant.objects.select_for_update().get(pk=request.book_id)
        if book.managed_by_id != request.office_id:
            # سباق أو تسليمٌ سابقٌ أنهى الحالة المُدارة قبل هذا القبول.
            raise ValidationError("طلب التسليم لم يعد صالحاً — حالة الدفتر تغيّرت.")

        book.managed_by = None
        changed = ['managed_by']
        # «بلا لحظة انقطاعٍ واحدة» شرطُ قبولٍ لا تفصيلُ واجهة — وهو بالضبط ما
        # رُفض به نمط QuickBooks. الدفتر حمل من `create_company` تجربةً تبدأ
        # **يوم فتحه المكتب**، وما ظهر أثرها لأنه كان يقرأ اشتراكه من مكتبه
        # (`core/plans.py` — `_billing_tenant`). لحظةَ سقوط `managed_by` يعود
        # إلى ساعته هو — ساعةٍ قد تكون بدأت قبل شهور — فيستلم العميل شركةً
        # للقراءة فقط. فتبدأ تجربته من اليوم. ولا نمسّ خطةً غير تجريبية:
        # ترقيةٌ صريحة من لوحة المنصة ليست لنا أن نُسقطها.
        if book.SubscriptionPlan == "Trial":
            book.Status = "Trial"
            book.subscription_ends_at = trial_end_date()
            changed += ['Status', 'subscription_ends_at']
        book.save(update_fields=changed)

        membership, _ = UserCompanyMembership.objects.get_or_create(
            user=accepting_user, tenant=book, defaults={'role': 'manager'},
        )
        if membership.role != 'manager':
            membership.role = 'manager'
            membership.save(update_fields=['role'])

        request.status = 'accepted'
        request.accepted_at = timezone.now()
        request.save(update_fields=['status', 'accepted_at'])

    from core.tenant_utils import invalidate_tenant_cache
    invalidate_tenant_cache()

    logger.info(
        "handover_request_accepted id=%s book=%s former_office=%s accepted_by=%s",
        request.pk, book.pk, request.office_id, accepting_user.pk,
    )
    return request
