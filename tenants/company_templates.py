"""ISSUE #50 — سِجلّ قوالب الشركة.

قالب واحد يحمل: المفتاح، الاسم العربي، الأيقونة، وصف سطر، جدول بذرة الحسابات،
وأنواع دفاتر المستندات المزروعة. `create_company` (`tenants/services.py`)
يستهلك السِجلّ عند الزرع الأول. تبديل القالب لشركة قائمة منطقٌ مستقل
(`switch_company_template`، ISSUE #64) — يستهلك نفس السِجلّ ليزرع الناقص فقط
(قرار 4: يرفع القناع ولا ينزع المزروع)، عبر `TenantViewSet.set_template`.

`general` هو الافتراضي (قرار 16): `coa=None` و`document_types=None` يعنيان
«استعمل ما ينتجه النظام اليوم حرفياً» — `COA_DATA` وأنواع المستندات الخمسة
عشر كاملةً في `tenants/models.py` (`TenantBook.DOCUMENT_TYPES`) — فالشركات
القائمة والقالب العام الجديد ينتجان نفس الشجرة بلا أي انحراف.
"""

# ── بذرة قالب «مكتب محاسبة» — من التذكرة حرفياً، لا تُعدَّل بلا فتح تذكرة ──
#
# قاعدة صارمة: 4102 لا يُغيَّر كوده مهما تغيّر اسمه — `sales/services/calc.py`
# يطابقه رقماً، وتغييره يكسر ترحيل كل فاتورة أتعاب بصمت.
#
# يسقط عمداً مقابل البذرة التجارية: 1104 المخزون، 1106 دفعات مقدمة للموردين،
# 1201/1202/1203 الأراضي والمباني والآلات، 2105–2109 ذمم اللوجستيات،
# 5101 تكلفة البضاعة المباعة، 53xx مصاريف الاستيراد، 4101 مبيعات المنتجات.
#
# ملاحظة: البند «55 مصاريف إدارية وعمومية» ورد في التذكرة بلا أكواد فرعية
# (بنكية · قانونية · اهتلاك وصفٌ لما يغطّيه لا حسابات مرقّمة)، فزُرع حساباً
# واحداً — على نمط «32 الأرباح المحتجزة» في القالب العام.
ACCOUNTING_FIRM_COA = [
    # Root nodes
    ('1', 'الأصول', 'Asset', None),
    ('2', 'الالتزامات', 'Liability', None),
    ('3', 'حقوق الملكية', 'Equity', None),
    ('4', 'الإيرادات', 'Revenue', None),
    ('5', 'المصروفات', 'Expense', None),

    # Assets (1)
    ('11', 'الأصول المتداولة', 'Asset', '1'),
    ('1101', 'النقدية', 'Asset', '11'),
    ('1102', 'البنوك', 'Asset', '11'),
    ('1103', 'المدينون التجاريون (ذمم عملاء المكتب)', 'Asset', '11'),
    ('1105', 'ضريبة القيمة المضافة - مدخلات', 'Asset', '11'),
    ('1107', 'شيكات برسم التحصيل', 'Asset', '11'),
    ('1109', 'شيكات في المحفظة', 'Asset', '11'),
    ('1110', 'صناديق النقدية', 'Asset', '11'),
    ('1112', 'مصاريف مدفوعة مقدماً', 'Asset', '11'),
    ('1113', 'أمانات لدى الغير عن العملاء', 'Asset', '11'),
    ('12', 'الأصول الثابتة', 'Asset', '1'),
    ('1204', 'الأثاث والتجهيزات', 'Asset', '12'),
    ('1205', 'أجهزة وحواسيب', 'Asset', '12'),
    ('1206', 'مجمّع الاهتلاك', 'Asset', '12'),

    # Liabilities (2)
    ('21', 'الالتزامات المتداولة', 'Liability', '2'),
    ('2101', 'الدائنون التجاريون', 'Liability', '21'),
    ('2103', 'مصاريف مستحقة', 'Liability', '21'),
    ('2104', 'ضريبة القيمة المضافة - مخرجات', 'Liability', '21'),
    ('2110', 'أمانات عملاء', 'Liability', '21'),
    ('2111', 'شيكات برسم الدفع', 'Liability', '21'),
    ('2112', 'رواتب مستحقة', 'Liability', '21'),
    ('22', 'الالتزامات غير المتداولة', 'Liability', '2'),
    ('2201', 'قروض طويلة الأجل', 'Liability', '22'),

    # Equity (3)
    ('31', 'رأس المال', 'Equity', '3'),
    ('3101', 'رأس المال المدفوع', 'Equity', '31'),
    ('32', 'الأرباح المحتجزة', 'Equity', '3'),

    # Revenue (4)
    ('41', 'الأتعاب المهنية', 'Revenue', '4'),
    ('4102', 'إيرادات الخدمات', 'Revenue', '41'),
    ('4103', 'أتعاب مسك الدفاتر', 'Revenue', '41'),
    ('4104', 'أتعاب الإقرارات الضريبية', 'Revenue', '41'),
    ('4105', 'أتعاب التدقيق والمراجعة', 'Revenue', '41'),
    ('4106', 'أتعاب الاستشارات والتأسيس', 'Revenue', '41'),
    ('42', 'إيرادات أخرى', 'Revenue', '4'),

    # Expenses (5)
    ('51', 'مصاريف الموظفين', 'Expense', '5'),
    ('5102', 'رواتب', 'Expense', '51'),
    ('5103', 'ضمان اجتماعي', 'Expense', '51'),
    ('5104', 'مكافآت', 'Expense', '51'),
    ('52', 'مصاريف المكتب', 'Expense', '5'),
    ('5202', 'إيجار', 'Expense', '52'),
    ('5203', 'كهرباء ومياه', 'Expense', '52'),
    ('5204', 'اتصالات وإنترنت', 'Expense', '52'),
    ('5205', 'قرطاسية', 'Expense', '52'),
    ('54', 'مصاريف مهنية', 'Expense', '5'),
    ('5401', 'اشتراكات نقابية ورخص', 'Expense', '54'),
    ('5402', 'تأمين مسؤولية مهنية', 'Expense', '54'),
    ('5403', 'اشتراكات برمجيات', 'Expense', '54'),
    ('5404', 'تدريب وتأهيل', 'Expense', '54'),
    ('55', 'مصاريف إدارية وعمومية', 'Expense', '5'),
]

# دفاتر القالب المزروعة — سبعة أنواع فقط، لا الخمسة عشر كاملة.
ACCOUNTING_FIRM_DOCUMENT_TYPES = [
    'sales_invoice', 'receipt_voucher', 'payment_voucher', 'journal_entry',
    'quotation', 'credit_note', 'debit_note',
]

DEFAULT_TEMPLATE = 'general'

# ── ISSUE #51 — القناع الحيّ: مسارات API تختفي كاملةً لقالب مكتب المحاسبة ──
#
# طرحيّ لا إضافي (فرّق عن `core/modules.py` (`MODULES`)): بادئات مسار كاملة —
# المخزون والمستودعات والجرد، الاستيراد واللوجستيات وملف الاستيراد، المتجر،
# ما بعد البيع، والأجهزة الحساسة. يستهلكها `core.permissions.TemplateSurfacePermission`
# (الحارس الوحيد — فحصٌ ببادئة المسار لا لمسٌ لكل ViewSet). مرآتها في الواجهة:
# `frontend_v2/utils/viewPermissions.ts` (`TEMPLATE_HIDDEN_VIEWS`) — سِجلٌّ
# مستقلّ بمفاتيح شاشات لا مسارات، فلا تتوقّع تطابقاً حرفياً بين الاثنين.
TEMPLATE_HIDDEN_PATH_PREFIXES: dict[str, tuple[str, ...]] = {
    'accounting_firm': (
        '/api/inventory/',
        # `logistics` **لا تُقنَّع جملةً**: `supplier-payments` (سند الصرف) يعيش
        # تحتها لأسبابٍ تاريخية، والتذكرة تُبقي «سندات القبض والصرف» صراحةً في
        # «ما يبقى» — والمكتب يحتاجه فعلاً ليسدّد ذمّة `2101` التي يفتحها سند
        # المصروف. فتُسمّى المسارات المقنَّعة واحداً واحداً.
        '/api/logistics/supplier-quotations/',
        '/api/logistics/purchase-orders/',
        '/api/logistics/deals/',
        '/api/logistics/shipments/',
        '/api/logistics/clearances/',
        '/api/logistics/payments/',
        '/api/logistics/purchase-invoices/',
        '/api/logistics/local-shipments/',
        '/api/logistics/import-journey/',
        '/api/logistics/reports/landed-cost/',
        '/api/logistics/purchase-settings/',
        '/api/logistics/goods-receipts/',
        '/api/import-file/',
        '/api/devices/',
        '/api/after-sales/',
        '/api/store/',
    ),
}

_ALL_HIDDEN_PREFIXES = tuple(sorted({
    prefix
    for prefixes in TEMPLATE_HIDDEN_PATH_PREFIXES.values()
    for prefix in prefixes
}))


def any_template_hides_path(path: str) -> bool:
    """فحصٌ رخيص بلا استعلام قاعدة بيانات — هل قد يخفي *أيّ* قالب هذا المسار؟

    يُستدعى أولاً في `TemplateSurfacePermission` كي لا تتحمّل شركة `general`
    (الغالبية) استعلام `get_tenant` الإضافي على كل طلب.
    """
    return path.startswith(_ALL_HIDDEN_PREFIXES)


def template_hides_path(template_key: str | None, path: str) -> bool:
    """أيخفي قالب هذه الشركة تحديداً هذا المسار؟"""
    prefixes = TEMPLATE_HIDDEN_PATH_PREFIXES.get(template_key or DEFAULT_TEMPLATE, ())
    return path.startswith(prefixes)


COMPANY_TEMPLATES = {
    'general': {
        'key': 'general',
        'name': 'عام / تجاري',
        'icon': 'building-2',
        'description': 'دليل حسابات تجاري كامل — مخزون واستيراد وكل أنواع المستندات.',
        # None = بلا قناع وبلا تغيير سلوك (قرار 16): تُستعمل COA_DATA وكل أنواع
        # المستندات الخمسة عشر كما تُنتَج اليوم حرفياً.
        'coa': None,
        'document_types': None,
        'masked_views': [],
    },
    'accounting_firm': {
        'key': 'accounting_firm',
        'name': 'مكتب محاسبة',
        'icon': 'calculator',
        'description': 'أتعاب مهنية بلا مخزون ولا استيراد — سبعة أنواع مستندات فقط.',
        'coa': ACCOUNTING_FIRM_COA,
        'document_types': ACCOUNTING_FIRM_DOCUMENT_TYPES,
        'masked_views': [],
    },
}
