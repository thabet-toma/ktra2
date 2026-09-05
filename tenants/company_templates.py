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

# ISSUE #78: خمس خدمات مهنية جاهزة، كلٌّ مربوطٌ بحساب أتعابه في `ACCOUNTING_FIRM_COA`
# — بلا هذا الربط تبقى `4103`-`4106` حساباتٍ ميتة لا يصلها شيء. (sku, name_ar, account_code)
ACCOUNTING_FIRM_SERVICES = [
    ('SVC-BOOKKEEPING', 'مسك دفاتر شهري', '4103'),
    ('SVC-VAT-RETURN', 'إعداد إقرار ض.ق.م', '4104'),
    ('SVC-INCOME-TAX', 'إقرار ضريبة دخل سنوي', '4104'),
    ('SVC-AUDIT', 'تدقيق ومراجعة', '4105'),
    ('SVC-CONSULTING', 'تأسيس واستشارات', '4106'),
]

# ── ISSUE #81 — بذرة قالب «دفتر عميل» (القسم ١ من #77) — من التذكرة حرفياً ──
#
# دفترٌ يفتحه مكتب محاسبة (ISSUE #65 `ClientBooksPanel`) ليمسك حسابات زبونه
# **يدوياً بالسندات**، لا بفواتير بيع وشراء ولا بمخزون — الجرد دوريّ يُقفله
# المحاسب بقيدٍ واحد. من يحتاج مخزوناً فعلياً يلزمه قالب `general`.
#
# `52` هو نفسه `EXPENSE_VOUCHER_PARENT_CODE` و`42` هو `REVENUE_VOUCHER_PARENT_CODE`
# (`accounting/services.py`) — أب حساب مصروف/إيراد يُنشأ بالاسم من داخل السند
# يهبط هنا افتراضاً، فوجودهما في هذه البذرة ليس اختيارياً.
CLIENT_BOOK_COA = [
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
    ('1103', 'المدينون التجاريون (ذمم عملاء)', 'Asset', '11'),
    ('1105', 'ضريبة القيمة المضافة - مدخلات', 'Asset', '11'),

    # Liabilities (2)
    ('21', 'الالتزامات المتداولة', 'Liability', '2'),
    ('2101', 'الدائنون التجاريون (ذمم موردين)', 'Liability', '21'),
    ('2103', 'مصاريف مستحقة', 'Liability', '21'),
    ('2104', 'ضريبة القيمة المضافة - مخرجات', 'Liability', '21'),

    # Equity (3)
    ('31', 'رأس المال', 'Equity', '3'),
    ('3101', 'رأس المال المدفوع', 'Equity', '31'),
    ('32', 'الأرباح المحتجزة', 'Equity', '3'),
    ('33', 'مسحوبات المالك', 'Equity', '3'),

    # Revenue (4)
    ('41', 'المبيعات', 'Revenue', '4'),
    ('4101', 'إيرادات المبيعات', 'Revenue', '41'),
    ('42', 'إيرادات أخرى', 'Revenue', '4'),

    # Expenses (5) — لا 51 تكلفة بضاعة مباعة ولا 1104 مخزون: المشتريات مصروفٌ
    # مباشر، والجرد الدوري يُسوّى بقيدٍ يدوي واحد لا بحساب مخزون حيّ.
    ('51', 'المشتريات', 'Expense', '5'),
    ('52', 'المصاريف التشغيلية', 'Expense', '5'),
    ('5201', 'إيجار', 'Expense', '52'),
    ('5202', 'رواتب وأجور', 'Expense', '52'),
    ('5203', 'كهرباء ومياه', 'Expense', '52'),
    ('5204', 'اتصالات وإنترنت', 'Expense', '52'),
    ('5205', 'نقل ومحروقات', 'Expense', '52'),
    ('5206', 'قرطاسية ومطبوعات', 'Expense', '52'),
    ('5207', 'صيانة وإصلاحات', 'Expense', '52'),
    ('5208', 'مصاريف بنكية وعمولات', 'Expense', '52'),
    ('5209', 'دعاية وإعلان', 'Expense', '52'),
    ('5210', 'رسوم ورخص واشتراكات', 'Expense', '52'),
    ('5211', 'أتعاب مهنية', 'Expense', '52'),
    ('5212', 'تأمين', 'Expense', '52'),
    ('5213', 'اهتلاك', 'Expense', '52'),
    ('53', 'مصاريف نثرية', 'Expense', '5'),
]

# دفاتر القالب المزروعة — خمسة أنواع فقط: سندات القبض والصرف والمصروف والإيراد
# وقيد اليومية. لا فواتير بيع/شراء ولا إشعارات دائنة/مدينة (لا مرجع لها بلا فواتير).
CLIENT_BOOK_DOCUMENT_TYPES = [
    'receipt_voucher', 'payment_voucher', 'expense_voucher', 'revenue_voucher',
    'journal_entry',
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
# مشترَكة بين `accounting_firm` و`client_book`: مخزون واستيراد ولوجستيات ومتجر
# وما بعد بيع وأجهزة حسّاسة — أيّ قالبٍ بلا حركة بضاعة فعلية لا يحتاجها.
# `logistics` **لا تُقنَّع جملةً**: `supplier-payments` (سند الصرف) يعيش تحتها
# لأسبابٍ تاريخية، وكلا القالبين يُبقي «سندات القبض والصرف» صراحةً في «ما يبقى»
# — يحتاجه المكتب فعلاً ليسدّد ذمّة `2101` التي يفتحها سند المصروف. فتُسمّى
# المسارات المقنَّعة واحداً واحداً.
_GOODS_MOVEMENT_HIDDEN_PATHS = (
    '/api/inventory/',
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
)

TEMPLATE_HIDDEN_PATH_PREFIXES: dict[str, tuple[str, ...]] = {
    'accounting_firm': _GOODS_MOVEMENT_HIDDEN_PATHS,
    # ISSUE #81: `client_book` يُقنِّع كل ما يُقنِّعه `accounting_firm` — ويزيد
    # عليه فواتير البيع نفسها (لا فواتير بيع/شراء في هذا القالب، السندات وحدها)
    # وأوامر البيع وعروض الأسعار والإرساليات والمحجوزات — بضاعةٌ لا مكان لها في
    # دفتر لا مخزون فيه. «أرباح الفواتير» فرعٌ من `/api/sales/invoices/` فتقنيعها
    # يقنِّعه معه بلا سطرٍ إضافي. حساب العميل نفسه (`/api/sales/payments/` سند
    # القبض) يبقى مفتوحاً — أحد الدفاتر الخمسة المزروعة.
    'client_book': _GOODS_MOVEMENT_HIDDEN_PATHS + (
        '/api/sales/invoices/',
        '/api/sales/quotations/',
        '/api/sales/orders/',
        '/api/sales/delivery-orders/',
        '/api/sales/reports/reserved-stock/',
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
        'services': None,
    },
    'accounting_firm': {
        'key': 'accounting_firm',
        'name': 'مكتب محاسبة',
        'icon': 'calculator',
        'description': 'أتعاب مهنية بلا مخزون ولا استيراد — سبعة أنواع مستندات فقط.',
        'coa': ACCOUNTING_FIRM_COA,
        'document_types': ACCOUNTING_FIRM_DOCUMENT_TYPES,
        'masked_views': [],
        'services': ACCOUNTING_FIRM_SERVICES,
    },
    'client_book': {
        'key': 'client_book',
        'name': 'دفتر عميل',
        'icon': 'book-open-check',
        'description': (
            'دفتر مكتب محاسبة لزبونٍ يُمسَك بالسندات — نقدية وبنوك وذمم ومصاريف '
            'تشغيلية، بلا مخزون ولا فواتير بيع أو شراء.'
        ),
        'coa': CLIENT_BOOK_COA,
        'document_types': CLIENT_BOOK_DOCUMENT_TYPES,
        'masked_views': [],
        'services': None,
    },
    # ── قالب «إطارات» — مفتاحٌ منفصل، بذرةٌ مطابقة لـ`general` اليوم ──
    #
    # `coa: None` و`document_types: None` مقصودان تماماً كما في `general`: يعنيان
    # «استعمل ما ينتجه النظام اليوم حرفياً» — فشركة تُنشأ بهذا القالب تحصل على
    # نفس `COA_DATA` ونفس أنواع المستندات الخمسة عشر كاملةً، بلا أي انحراف عن
    # القالب التجاري. الفائدة ليست سلوكاً مختلفاً اليوم، بل **مفتاحٌ مستقل**
    # (`tenant.template == 'tyres'`) تُعلَّق عليه لاحقاً تخصيصات قطاع الإطارات
    # (بذرة حسابات، أنواع مستندات، أو قناع مسارات) دون المساس بشركات `general`
    # القائمة أصلاً.
    'tyres': {
        'key': 'tyres',
        'name': 'إطارات',
        'icon': 'disc',
        'description': 'مطابقٌ اليوم لقالب «عام / تجاري» حرفياً — مفتاحٌ مستقل تُعلَّق عليه تخصيصات قطاع الإطارات لاحقاً.',
        'coa': None,
        'document_types': None,
        'masked_views': [],
        'services': None,
    },
}


# ── أين يُعرض كل قالب؟ ──────────────────────────────────────────────────
#
# القوالب ليست قائمةً واحدة تُعرض في كل باب. لها بابان مختلفان:
#
# - **إنشاء شركة** (`companies/` و`companies/{id}/set-template/`): شركةُ المستخدم
#   نفسه. `client_book` **لا مكان له هنا**: دفتر العميل ليس شركةً يملكها أحد،
#   بل دفترٌ يفتحه مكتبُ محاسبةٍ لزبونه تحت حصّة `office.managed_books`،
#   وشاشةُ بدايته وقناعه ووحدتُه المرخَّصة (issue #87) كلّها مبنيّة على وجود
#   مكتبٍ فوقه. من أنشأه كشركةٍ مستقلّة حصل على دفترٍ بلا مكتب: بلا زرّ عودة،
#   وبلا مكانٍ يظهر فيه.
# - **فتح دفتر عميل** (`companies/{id}/managed-books/`): `client_book` وحده.
#   القالبان الآخران يفتحان ERP كاملاً للزبون — وهو نقيض ما بُني له هذا الباب.
BOOK_ONLY_TEMPLATES: frozenset[str] = frozenset({'client_book'})
SELF_SERVE_TEMPLATES: tuple[str, ...] = tuple(
    key for key in COMPANY_TEMPLATES if key not in BOOK_ONLY_TEMPLATES
)
DEFAULT_BOOK_TEMPLATE = 'client_book'


def assert_self_serve_template(template_key: str) -> None:
    """قالبٌ يصلح لشركةٍ يملكها المستخدم — لا قالب دفترٍ يلزمه مكتبٌ فوقه."""
    if template_key in BOOK_ONLY_TEMPLATES:
        raise ValueError(
            f'قالب «{COMPANY_TEMPLATES[template_key]["name"]}» لا يُنشأ كشركة '
            'مستقلّة — يفتحه مكتب المحاسبة لزبونه من «دفاتر عملائي».'
        )


def assert_book_template(template_key: str) -> None:
    """قالبٌ يصلح لدفتر زبونٍ يمسكه مكتب."""
    if template_key not in BOOK_ONLY_TEMPLATES:
        raise ValueError(
            f'قالب «{COMPANY_TEMPLATES[template_key]["name"]}» يفتح نظاماً '
            'كاملاً لا دفتراً — دفاتر العملاء تُفتح بقالب «دفتر عميل».'
        )
