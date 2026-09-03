"""ISSUE #83 — بيان الواجهة: شريطٌ لكل قالب، شاشةُ بدايةٍ، وإجراءٌ أول.

#77 القسم ٦. **بياناتٌ لا شجرة مكوّنات**: مجموعات الشريط وترتيبها وتسمياتها
(بمفاتيح المعجم `core.terminology`) وشاشة البداية والإجراء الأول ونصّ الحالة
الفارغة — لكل قالب. يُسلَّم على حمولة `/api/permissions/me` نفسها
(`core/permissions_api.py`) مع `modules` و`terms` — القرار 8 في #46: لا آلية
ثالثة.

**القاعدة الملزِمة (جوهر التذكرة): البيان عرضٌ لا تصريح.** القناع الحقيقي لا
يُمَسّ هنا ويبقى حيث هو: `core.permissions.TemplateSurfacePermission` خادمياً
على مسارات الـAPI، و`TEMPLATE_HIDDEN_VIEWS`
(`frontend_v2/utils/viewPermissions.ts`) على روابط الشريط. هذا البيان قد
يذكر شاشةً يرفضها ذلك القناع (`stock-movements` في تقارير «مكتب محاسبة»
عمداً، ليبقى للحارس حالة حقيقية) — الواجهة (`utils/shellManifest.ts`
— `filterShellGroups`) تُقصيها قبل الرسم، ولا نسخة مقنَّعة موازية تُبنى هنا.

`general` بلا بيان (`shell_manifest` تعيد `None`) — الشريط الحالي المكتوب
يدوياً في `Sidebar.tsx` يبقى حرفياً بلا مسّ؛ فراغُ البيان هو آلية التراجع.

شاشةٌ واحدة مذكورة أدناه لم تُبنَ بعد (`UNBUILT_VIEWS`) وتأتي في تذكرةٍ لاحقة:
«المكتب» (`office-desk`، لوحة مكتب مكتب المحاسبة). الواجهة تسقط بها إلى
`dashboard`. **«ترميز مستندات» (`document-coding`) بُنيت في issue #85** —
`frontend_v2/components/accounting/DocumentCodingPage.tsx` فوق
`POST vouchers/batch-save/` التي بنتها #84 خادمياً — وخرجت من هذه القائمة.
"""
import copy

# شاشةٌ واحدة يذكرها البيان بلا شاشةٍ فعلية بعد — الواجهة تسقط بها إلى `dashboard`.
UNBUILT_VIEWS: frozenset[str] = frozenset({"office-desk"})

SHELL_MANIFESTS: dict[str, dict] = {
    "accounting_firm": {
        "start_view": "dashboard",
        "first_action": {"view": "sales-invoices", "label_term": "doc.sales_invoice"},
        "empty_state_term": "empty.shell",
        "groups": [
            {"id": "home", "label_term": "nav.home", "views": ["dashboard"]},
            {"id": "clients", "label_term": "nav.clients", "views": ["client-books"]},
            {
                "id": "fees",
                "label_term": "nav.fees",
                "views": [
                    "sales-invoices", "sales-quotations", "credit-debit-notes",
                    "sales-return", "sales-customers", "sales-customer-payments",
                    "sales-settings",
                ],
            },
            {
                "id": "treasury",
                "label_term": "nav.treasury",
                "views": [
                    "cash-boxes", "accounting-banks", "accounting-bank-reconciliation",
                    "accounting-cheques", "accounting-expense-vouchers",
                    "accounting-revenue-vouchers",
                    "supplier-payments", "supplier-management",
                ],
            },
            {
                "id": "office-accounting",
                "label_term": "nav.office_accounting",
                # لا «payroll» هنا: بندها الثابت في «إدارة الموظفين» (خارج
                # مجموعات البيان، `Sidebar.tsx`) يبقى ظاهراً بلا شرط القالب —
                # تكرارها هنا يُظهرها مرّتين.
                "views": [
                    "accounting-coa", "accounting-journals", "accounting-journal-entry",
                    "accounting-general-ledger", "accounting-trial-balance",
                    "accounting-vat-report", "accounting-fiscal-periods",
                    "accounting-opening-balances", "accounting-exchange-rates",
                    "accounting-balance-sheet", "accounting-income-statement",
                    "accounting-vat-statements", "accounting-year-end-close",
                ],
            },
            {
                "id": "reports",
                "label_term": "nav.reports",
                # «stock-movements» مقصودة: يقنّعها القناع الحيّ لهذا القالب —
                # حالة اختبارٍ حقيقية لا مصطنعة لقاعدة «البيان لا يفرض القناع».
                "views": [
                    "reports", "stock-movements", "accounting-trial-balance",
                    "accounting-income-statement", "accounting-balance-sheet",
                    "accounting-vat-report",
                ],
            },
            {"id": "office", "label_term": "nav.office", "views": ["office-desk"]},
        ],
    },
    "client_book": {
        "start_view": "dashboard",
        "first_action": {"view": "document-coding", "label_term": "action.document_coding"},
        "empty_state_term": "empty.shell",
        "groups": [
            {"id": "home", "label_term": "nav.home", "views": ["dashboard"]},
            {
                "id": "entry",
                "label_term": "nav.entry",
                # سندا المصروف والإيراد **هنا** لا في «الحسابات»: هما مادّةُ هذا
                # القالب اليومية — رزمةُ الورق التي يفتح المحاسبُ الدفترَ من
                # أجلها — لا فرعٌ من إدارة شجرة الحسابات. وكان سند الإيراد بلا
                # شاشةٍ أصلاً فلم يكن له مكانٌ يُذكر فيه.
                "views": [
                    "document-coding", "accounting-expense-vouchers",
                    "accounting-revenue-vouchers", "accounting-journal-entry",
                ],
            },
            {
                "id": "receipt-payment",
                "label_term": "nav.receipt_payment",
                "views": ["sales-customer-payments", "supplier-payments", "accounting-cheques"],
            },
            {
                "id": "parties",
                "label_term": "nav.parties",
                "views": ["sales-customers", "supplier-management", "sql-partners"],
            },
            {
                "id": "accounts",
                "label_term": "nav.accounts",
                "views": [
                    "accounting-coa", "accounting-journals", "accounting-general-ledger",
                    "accounting-trial-balance", "cash-boxes", "accounting-banks",
                    "accounting-bank-reconciliation",
                ],
            },
            {
                # سببُ مسك الدفتر أصلاً: كم ربح، وكم عليه من ضريبة. كانت شاشة
                # «الوضع المالي» تعرض الأربعة على شاشة البداية ثم لا يجد من
                # غادرها طريقاً يعود به، ولا قائمةَ دخلٍ ولا ميزانيةً في الشريط
                # كلّه — فبدا القالبُ دفترَ إدخالٍ بلا نتيجة.
                "id": "results",
                "label_term": "nav.results",
                "views": [
                    "dashboard", "accounting-income-statement",
                    "accounting-balance-sheet", "reports",
                ],
            },
            {
                "id": "declarations",
                "label_term": "nav.declarations",
                "views": ["accounting-vat-report", "accounting-vat-statements", "accounting-fiscal-periods"],
            },
            {"id": "settings", "label_term": "nav.settings", "views": ["settings"]},
        ],
    },
}


def shell_manifest(template_key: str | None) -> dict | None:
    """بيان الشريط لهذا القالب — `None` لـ`general` (ولأي قالبٍ بلا بيان).

    نسخةٌ كاملة (`deepcopy`) لا مرجع إلى `SHELL_MANIFESTS`: القاموس وحدةٌ
    مشتركة بين الطلبات، وأي تعديل عرَضي على ناتج نداءٍ (تسلسلٌ إلى JSON مثلاً)
    يجب ألا يُصيب نداءً تالياً.
    """
    base = SHELL_MANIFESTS.get(template_key or "")
    if base is None:
        return None
    manifest = copy.deepcopy(base)
    manifest["unbuilt_views"] = sorted(UNBUILT_VIEWS)
    return manifest
