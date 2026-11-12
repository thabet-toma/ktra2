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

ISSUE #291: لم يبقَ في البيان شاشةٌ مذكورةٌ بلا بناء. كانت `UNBUILT_VIEWS`
تحمل «المكتب» (`office-desk`) وحدها، وهي شاشةُ بيان `accounting_firm` الذي
حُذف مع طبقة المكتب القديمة — فحُذفت القائمة ومفتاح `unbuilt_views` من الحمولة.
"""
import copy

# ── مجموعاتٌ مشتركة داخل بيان مكتب المحاسبة ───────────────────────────────
#
# «الخزينة» و«حسابات المكتب» و«التقارير» تُعرَّف **مرّةً واحدةً هنا** ويقرؤها
# البيان، فلا قائمةٌ ثانيةٌ تفترق عنها عند أول شاشةٍ تُضاف. (كانت مشتركةً بين
# بيانَي `accounting_firm` و`accounting_office`؛ حُذف بيانُ القديم في #291.)
TREASURY_VIEWS: tuple[str, ...] = (
    "cash-boxes", "accounting-banks", "accounting-bank-reconciliation",
    "accounting-cheques", "accounting-expense-vouchers",
    "accounting-revenue-vouchers", "credit-debit-notes",
    "supplier-payments", "supplier-management",
)

# «payroll» ليست هنا: بندُها الثابت في «إدارة الموظفين» (خارج مجموعات البيان،
# `Sidebar.tsx`) يبقى ظاهراً بلا شرط القالب — تكرارُها هنا يُظهرها مرّتين.
OFFICE_ACCOUNTING_VIEWS: tuple[str, ...] = (
    "accounting-coa", "accounting-journals", "accounting-journal-entry",
    "accounting-general-ledger", "accounting-trial-balance",
    "accounting-vat-report", "accounting-fiscal-periods",
    "accounting-opening-balances", "accounting-exchange-rates",
    "accounting-balance-sheet", "accounting-income-statement",
    "accounting-vat-statements", "accounting-year-end-close",
)

# «stock-movements» مقصودة: يقنّعها القناع الحيّ لقالب المكتب —
# حالة اختبارٍ حقيقية لا مصطنعة لقاعدة «البيان لا يفرض القناع».
REPORT_VIEWS: tuple[str, ...] = (
    "reports", "stock-movements", "accounting-trial-balance",
    "accounting-income-statement", "accounting-balance-sheet",
    "accounting-vat-report",
)

SHELL_MANIFESTS: dict[str, dict] = {
    # ISSUE #271 — بيانُ موديول مكتب المحاسبة، والبيانُ الحيّ الوحيد للمكاتب.
    #
    # ISSUE #291: كان **بجانب** `accounting_firm`؛ حُذف بيانُ القديم مع طبقة
    # المكتب القديمة (`client-books`، `office-desk`) فبقي هذا وحده. ومجموعاتُه
    # المشتركة (`TREASURY_VIEWS`/`OFFICE_ACCOUNTING_VIEWS`/`REPORT_VIEWS`) تقرأ
    # الثوابت أعلاه لا نسخاً نصّيّة: قائمةٌ ثانيةٌ تعني تعديلين عند كل شاشة
    # تُضاف، وأحدهما يُنسى.
    #
    # ما لا مجموعةَ له هنا: «الأتعاب» (تذكرة الأتعاب لاحقة)، و`client-books`
    # و`office-desk` (شاشاتُ طبقة المكتب القديمة — حُذفت معها).
    "accounting_office": {
        # شاشة البداية قائمةُ الزبائن: أولُ ما يفعله مكتبٌ جديد هو إدخال زبون.
        "start_view": "office-clients",
        "first_action": {"view": "office-clients", "label_term": "action.add_office_client"},
        "empty_state_term": "empty.office_shell",
        "groups": [
            # #275: «اليوم» **أوّلُ** مجموعات البيان — شاشةُ العمل الصباحيّة:
            # ما حان وقتُه من التزامات وشغلات. وقبلها كانت البدايةُ الزبائن.
            {"id": "today", "label_term": "nav.office_today", "views": ["office-today"]},
            # #280/ب: «جاهز للإرسال» **بعد «اليوم»** مباشرةً — ثاني شاشة عملٍ
            # صباحيّة: ما حان إرسالُه اليوم لكل شخصٍ بلغته. ومجموعتُها مستقلّةٌ
            # كاستقلال التقويم، لا بنداً داخل «اليوم».
            {
                "id": "ready-to-send",
                "label_term": "nav.office_ready_to_send",
                "views": ["office-ready-to-send"],
            },
            # #282/أ٢/٢: «المسودّات» — قائمةُ مسودّات الأتعاب وأفعالُها (اعتمادٌ
            # واعتمادُ الكلّ وإلغاء)، وبطاقةُ الورقة الصادرة لكلٍّ. ومجموعتُها
            # مستقلّةٌ كاستقلال «جاهز للإرسال»: عملٌ يُنجَز ثم يخرج من القائمة.
            {
                "id": "fee-drafts",
                "label_term": "nav.office_fee_drafts",
                "views": ["office-fee-drafts"],
            },
            # #289: لوحةُ صاحب المكتب بعد شاشتَي العمل الصباحيّتين — «اليوم»
            # و«جاهز للإرسال» عملُ كلّ عضوٍ، واللوحةُ أرقامُ المالك وحده. والبيانُ
            # عرضٌ لا تصريح: الدورُ (مالك) يحرسها في الموجّه (`managerOnlyViews`)
            # والخادمُ يردّ غيرَه 403.
            {
                "id": "dashboard",
                "label_term": "nav.office_dashboard",
                "views": ["office-dashboard"],
            },
            {"id": "clients", "label_term": "nav.office_clients", "views": ["office-clients"]},
            # #274: التقويم شاشةٌ مستقلّة عن قائمة الزبائن (تُقرأ من لائحة المواعيد
            # المحسوبة)، فمجموعتُها مستقلّة كما استقلّت «إعدادات المكتب» في #271.
            {
                "id": "calendar",
                "label_term": "nav.office_calendar",
                "views": ["office-calendar"],
            },
            {
                "id": "office-settings",
                "label_term": "nav.office_settings",
                "views": ["office-settings"],
            },
            {
                "id": "treasury",
                "label_term": "nav.treasury",
                "views": list(TREASURY_VIEWS),
            },
            {
                "id": "office-accounting",
                "label_term": "nav.office_accounting",
                "views": list(OFFICE_ACCOUNTING_VIEWS),
            },
            {
                "id": "reports",
                "label_term": "nav.reports",
                "views": list(REPORT_VIEWS),
            },
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
    return copy.deepcopy(base)
