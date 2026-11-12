"""مسارات مكتب المحاسبة — كلها تحت `/api/accounting-office/`.

`SimpleRouter` لا `DefaultRouter`: الأخير يولّد فهرساً على الجذر غير محروسٍ
بـ`require_module` فيكشف وجود الوحدة لشركةٍ لم تشترها.
"""
from django.urls import include, path, re_path
from rest_framework.routers import SimpleRouter

from accounting_office.views import (
    OfficeAlertsViewSet,
    OfficeAppointmentViewSet,
    OfficeCalendarViewSet,
    OfficeClientBookViewSet,
    OfficeClientViewSet,
    OfficeContactViewSet,
    OfficeCustomRuleViewSet,
    OfficeDeadlineRuleViewSet,
    OfficeDocumentFileViewSet,
    OfficeDocumentItemViewSet,
    OfficeDocumentViewSet,
    OfficeFeeDraftViewSet,
    OfficeFeeExtraServiceViewSet,
    OfficeFeeLedgerViewSet,
    OfficeFeePaymentViewSet,
    OfficeFeeServicePriceViewSet,
    OfficeFeeSubscriptionViewSet,
    OfficeHolidayViewSet,
    OfficeObligationViewSet,
    OfficePackageViewSet,
    OfficeReadyToSendViewSet,
    OfficeReminderLogViewSet,
    OfficeReminderTemplateViewSet,
    OfficeServiceViewSet,
    OfficeSettingsViewSet,
    OfficeTaskViewSet,
    OfficeTodayViewSet,
)

router = SimpleRouter()
router.register("clients", OfficeClientViewSet, basename="accounting-office-clients")
# #286: دفترُ الزبون — قراءةٌ وكتابةٌ، **ولا حذف**. مسارُه مفتاحُه الزبون لأن
# الدفتر واحدٌ له (`client-books/<client_id>/…`)، و«للإدخال» فعلٌ على الجمع
# (`client-books/pending-entry/`) فلا يلتبس بمسارِ تفصيل.
router.register(
    "client-books",
    OfficeClientBookViewSet,
    basename="accounting-office-client-books",
)
router.register("contacts", OfficeContactViewSet, basename="accounting-office-contacts")
router.register("services", OfficeServiceViewSet, basename="accounting-office-services")
router.register("packages", OfficePackageViewSet, basename="accounting-office-packages")
router.register("settings", OfficeSettingsViewSet, basename="accounting-office-settings")
# #274: قراءتان — التقويم المحسوب، ولائحة المواعيد التي يقرؤها.
router.register("calendar", OfficeCalendarViewSet, basename="accounting-office-calendar")
router.register(
    "deadline-rules", OfficeDeadlineRuleViewSet, basename="accounting-office-deadline-rules",
)
# #275: شاشةُ «اليوم» (تُشغّل التحديث اليوميّ أوّلاً) وأفعالُ الالتزامات والشغلات.
router.register("today", OfficeTodayViewSet, basename="accounting-office-today")
# #281: المواعيد — حجزٌ وأفعالُه (تأكيد/تأجيل/إلغاء/«صار»)، بلا حذف ولا تعديلٍ
# جزئيّ. مسارُها جمعُها لأن الفعل يقع على الموعد نفسه (`appointments/<pk>/confirm/`).
router.register(
    "appointments",
    OfficeAppointmentViewSet,
    basename="accounting-office-appointments",
)
router.register(
    "obligations", OfficeObligationViewSet, basename="accounting-office-obligations",
)
router.register("tasks", OfficeTaskViewSet, basename="accounting-office-tasks")
# #276: الجرس — تنبيهاتُ العضو نفسه، و«شفته»، و«شفتهم كلهم».
router.register("alerts", OfficeAlertsViewSet, basename="accounting-office-alerts")
# #277: التزاماتُ المكتب الخاصة — بلا حذف (التعطيلُ هو الفعل).
router.register(
    "custom-rules", OfficeCustomRuleViewSet, basename="accounting-office-custom-rules",
)
# #278: صفوفُ الأوراق وحالتُها وملفاتُها، وقالبُ بنود الأوراق (وقراءةُ بنوده لكل
# عضوٍ لملفّ الزبون، وكتابتُها بمفتاح الإعدادات).
router.register(
    "documents", OfficeDocumentViewSet, basename="accounting-office-documents",
)
router.register(
    "document-files",
    OfficeDocumentFileViewSet,
    basename="accounting-office-document-files",
)
router.register(
    "document-items",
    OfficeDocumentItemViewSet,
    basename="accounting-office-document-items",
)
# #280: «جاهز للإرسال» وأفعالها، وسجلُّ التذكيرات (إلحاقيّ)، ونصوصُ المكتب،
# وعطلُه. والسجلُّ على `reminder-log` لا `reminders`: هذا مستلِمو الأنواع منذ #271.
router.register(
    "ready-to-send", OfficeReadyToSendViewSet, basename="accounting-office-ready-to-send",
)
router.register(
    "reminder-log", OfficeReminderLogViewSet, basename="accounting-office-reminder-log",
)
router.register(
    "reminder-templates",
    OfficeReminderTemplateViewSet,
    basename="accounting-office-reminder-templates",
)
router.register(
    "office-holidays", OfficeHolidayViewSet, basename="accounting-office-holidays",
)
# #282: الأتعاب — الاشتراكُ وأسعارُ الخدمات والإضافاتُ والمسودّاتُ والاعتماد
# (الجزءُ أ١، الخادمُ وحده). ولا حذفَ في الأربعة: `http_method_names` في
# الـviewsets تُغلق الطريقة، ولا `PUT`/`PATCH` كذلك.
# ومسارُ `fees/drafts/approve-all/` مسارُ جمعٍ لأنها فعلٌ على كل المنتظر، لا واحدة.
router.register(
    "fees/subscriptions",
    OfficeFeeSubscriptionViewSet,
    basename="accounting-office-fee-subscriptions",
)
router.register(
    "fees/drafts",
    OfficeFeeDraftViewSet,
    basename="accounting-office-fee-drafts",
)
router.register(
    "fees/extras",
    OfficeFeeExtraServiceViewSet,
    basename="accounting-office-fee-extras",
)
# أسعارُ خدمات الزبائن: بها تُكتمل طريقةُ «سعرٌ لكل خدمة» — تُقرأ وتُسعَّر ولا
# تُحذف ولا تُعدَّل (إعادةُ التسعير `POST` ثانٍ يحدّث صفَّ الخدمة الواحد).
router.register(
    "fees/service-prices",
    OfficeFeeServicePriceViewSet,
    basename="accounting-office-fee-service-prices",
)
# #283: الدفعات — قراءةٌ بفلترة وإنشاءٌ بتخصيص، **ولا حذفَ ولا تعديل**. والشطبُ
# فعلٌ على المسودّة (`fees/drafts/<pk>/write-off/`) لأن السطرَ يخصّها لا الدفعة.
router.register(
    "fees/payments",
    OfficeFeePaymentViewSet,
    basename="accounting-office-fee-payments",
)
# كشفُ الحساب: الفواتيرُ المعتمدةُ والدفعات، بفلترةٍ وترقيمٍ في الاستعلام.
router.register(
    "fees/ledger",
    OfficeFeeLedgerViewSet,
    basename="accounting-office-fee-ledger",
)

urlpatterns = [
    # #288/ب-١: مستخرجا Excel مُسجَّلان هنا لا بـ`@action` — الراوترُ يُلحق
    # شرطةً أخيرةً بكل فعل، و`export.xlsx/` اسمُ ملفٍّ تفصله شرطةٌ عمّا قبله
    # فيُقرأ مساراً لا ملفّاً. والـviewset نفسُه حارسُهما: الترخيصُ في `initial`
    # والعزلُ في `_book`، فالمسارُ لا يفتح باباً ثانياً.
    re_path(
        r"^client-books/(?P<pk>[0-9]+)/reports/(?P<kind>[a-z_]+)/export\.xlsx$",
        OfficeClientBookViewSet.as_view({"get": "export_report_xlsx"}),
        name="accounting-office-client-book-report-xlsx",
    ),
    re_path(
        r"^client-books/(?P<pk>[0-9]+)/export\.xlsx$",
        OfficeClientBookViewSet.as_view({"get": "export_book_xlsx"}),
        name="accounting-office-client-book-xlsx",
    ),
    path("", include(router.urls)),
]
