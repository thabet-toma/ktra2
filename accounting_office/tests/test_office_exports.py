"""تصديرُ بيانات المكتب الكامل وتذكيرُه الشهري — #290 (§أ و§ب و§د).

**ما يثبّته هذا الملفّ:**

- **الحدودُ قبل كل شيء**: التصديرُ يحوي زبائنَ مكتبٍ واحدٍ ولا شيء من مكتبٍ آخر —
  مكتبان ببياناتٍ **متشابهة** عمداً (الاسمُ نفسُه في الآخر) فالمقارنةُ بالاسم لا
  بالعدد: عدّادٌ متساوٍ لا يقول أيَّ زبونٍ خرج.
- **البوّابة**: المالكُ وحده (دورٌ في `ENTRY_APPROVER_ROLES` **و** مفتاح
  `office.clients.all` **و** رؤيةُ المبالغ) — ومن نقصه أحدُ الثلاثة **403**؛
  والمحاسبُ لا يُصدَّر له جزئياً (رفضٌ صريح أوضح من ملفٍّ ناقص يظنّه كاملاً).
- **المصنَّف**: ملفُّ `xlsx` حقيقيٌّ يُفتح بـ`openpyxl` ويعطي **تسع أوراقٍ**
  بأسمائها وترتيبها، والمبالغُ فيه **أرقامٌ** بصيغة `#,##0.00` لا نصوصاً.
- **الإعدادان المقفلان** (`official_invoicing` و`auto_send`): يُعرضان `False`
  ومعهما `locked`، ويُرفَض فتحُهما **400** من الـAPI برسالتهما العربية.
- **التذكيرُ الشهري**: تنبيهٌ واحد لكل مستلِمٍ في الشهر ولو تكرّر التحديث،
  وإعدادُ `off` لا يولّد شيئاً، **وأخذُ النسخة يُسكِته** بمسار `seen` القائم.
- **رابطُ PDF**: يُنشأ نوعُ `office_data_export` ويُفتح عامّاً بالجداول التسعة،
  وإطفاءُ `office_report_pdf_link` يردّه **400** بينما يبقى Excelُ عاملاً.
"""
import datetime
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.utils import timezone
from openpyxl import load_workbook

from accounting_office import book_exports, services
from accounting_office.models import (
    OFFICE_ALERT_KIND_DATA_EXPORT_DUE,
    FeePayment,
    OfficeAlert,
)
from accounting_office.tests.test_book_reports import BookReportsTestCase
from tenants.models import MemberPermission, UserCompanyMembership

BASE = "/api/accounting-office/"
EXPORT_FULL = f"{BASE}exports/full/"
EXPORT_FULL_LINK = f"{BASE}exports/full-link/"
EXPORT_CLIENT_NAMES = f"{BASE}exports/client-names/"
SETTINGS = f"{BASE}settings/"

THIS_YEAR = timezone.localdate().year
#: يومُ التحديث — داخل السنة، فلا يهمّ أيُّ شهرٍ فيها: التنبيهُ شهريٌّ والتاريخُ صريح.
DAY = datetime.date(THIS_YEAR, 6, 10)

#: أسماءُ الأوراق التسع بترتيبها المحسوم — العقدُ الذي يحرسه اختبارُ المصنَّف.
SHEET_TITLES = [
    "الزباين",
    "البطاقات",
    "الخدمات",
    "الالتزامات",
    "الأوراق",
    "سجل التذكيرات",
    "الفواتير",
    "الدفعات",
    "الدفاتر",
]

#: رسالةُ تذكير النسخة — نصٌّ واحدٌ يقارنه الاختبار وتكتبه الخدمة كما هو.
REMINDER_MESSAGE = (
    "نسخة بيانات المكتب لهذا الشهر — خُذها من الإعدادات ← التشغيل والنسخ"
)


def sheet_texts(sheet):
    """كلُّ نصٍّ على الورقة — للبحث عن الأسماء والعناوين في المُخرَج."""
    return [
        cell.value
        for row in sheet.iter_rows()
        for cell in row
        if isinstance(cell.value, str)
    ]


def month_ref(day):
    return f"export:{day.year:04d}-{day.month:02d}"


class OfficeExportsTestCase(BookReportsTestCase):
    """مكتبٌ مرخَّصٌ بمالكه ومديرِ مكتبٍ ومحاسبٍ وزميلٍ ومراقب، ومكتبٌ ثانٍ."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role,
            )
            return user

        #: مديرُ المكتب (#288/ب-٢) — دوره في `ENTRY_APPROVER_ROLES` أيضاً، فيرى
        # ما يراه المالك في هذه النقطة (القرارُ «دوران» لا «المالك المُنشئ»).
        cls.office_manager = member("oe_office_manager", "office_manager")

    # ── أفعالٌ مشتركة ────────────────────────────────────────────────────
    def export_full(self, *, expect=200, user=None, tenant=None):
        if user is not None:
            self.as_user(user)
        res = self.client.post(
            EXPORT_FULL, {}, format="json", **self.headers(tenant=tenant),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res

    def workbook(self, **kwargs):
        res = self.export_full(**kwargs)
        self.assertIn("spreadsheetml", res["Content-Type"])
        return load_workbook(BytesIO(res.content))

    def settings_rows(self):
        res = self.client.get(SETTINGS, **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        return res.data, {row["key"]: row for row in res.data["settings"]}

    def sheet_values(self, title):
        """صفوفُ البيانات في ورقة — **بلا صفوف المجاميع** التي تُكتب أسفلها."""
        workbook = self.workbook()
        rows = [
            [cell.value for cell in row]
            for row in workbook[title].iter_rows(min_row=2)
            if any(cell.value not in (None, "") for cell in row)
        ]
        return [
            row for row in rows
            if not (isinstance(row[0], str) and row[0].startswith("مجموع"))
        ]

    def refresh(self, day=DAY):
        return services.refresh_office(self.tenant, day=day)

    def export_alerts(self, day=DAY):
        return OfficeAlert.objects.filter(
            tenant=self.tenant,
            kind=OFFICE_ALERT_KIND_DATA_EXPORT_DUE,
            ref_key=month_ref(day),
        )


class ScopingTest(OfficeExportsTestCase):
    """التصديرُ يحوي زبائن مكتبٍ واحد — والمكتبان ببياناتٍ **متشابهة** عمداً.

    التماثلُ مقصود: مبلغٌ واحدٌ في دفعة كلٍّ منهما، وكتابٌ لكلٍّ — فاختبارُ
    الحدود لا يمرّ لأن أحدهما فارغ بل لأن صفَّ الآخر لم يُقرأ.
    """

    def setUp(self):
        super().setUp()
        FeePayment.objects.create(
            tenant=self.tenant, client=self.mine, method="cash",
            amount=Decimal("500.00"), paid_at=DAY,
            receipt_number=f"{THIS_YEAR}-00001",
        )
        #: الدفعةُ نفسُها في المكتب الثاني — بالاسم والمبلغ والتاريخ أنفسهم.
        self.outside_payment = FeePayment.objects.create(
            tenant=self.tenant_b, client=self.outside, method="cash",
            amount=Decimal("500.00"), paid_at=DAY,
            receipt_number=f"{THIS_YEAR}-00001",
        )

    def test_the_clients_sheet_carries_the_offices_clients_and_nothing_of_the_other(self):
        texts = sheet_texts(self.workbook()["الزباين"])

        self.assertIn(self.mine.name, texts)
        self.assertNotIn(self.outside.name, texts)

    def test_the_payments_sheet_has_one_row_even_though_both_offices_paid_the_same(self):
        rows = self.sheet_values("الدفعات")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], f"{THIS_YEAR}-00001")
        self.assertEqual(rows[0][2], self.mine.name)

    def test_the_ledger_sheet_keeps_the_clients_of_its_own_office_only(self):
        self.create_book(self.mine, opened_on=datetime.date(THIS_YEAR - 1, 1, 5))
        self.add_entry(self.mine, entry_date=DAY, lines=self.balanced("150.00"))

        rows = self.sheet_values("الدفاتر")

        self.assertTrue(rows)
        self.assertEqual({row[0] for row in rows}, {self.mine.name})


class PermissionGateTest(OfficeExportsTestCase):
    """التصديرُ الكاملُ للمالك وحده — ثلاثةُ حرّاسٍ برسالةٍ تسمّي السبب."""

    def test_the_owner_exports_and_a_plain_accountant_is_refused(self):
        self.export_full()

        refused = self.export_full(expect=403, user=self.accountant)
        # 403 لا 400: الطلبُ سليمٌ والدورُ ناقص — والرسالةُ تسمّي المفتاح.
        self.assertIn("التصدير", refused.content.decode("utf-8"))

    def test_a_viewer_and_a_colleague_are_refused_too(self):
        self.export_full(expect=403, user=self.viewer)
        self.export_full(expect=403, user=self.colleague)

    def test_an_office_manager_without_the_all_clients_key_is_refused(self):
        """الدورُ وحده لا يكفي: المفتاحُ الثاني شرطٌ مستقلّ — والحارسُ 403.

        **مديرُ المكتب لا المالك**: `core/access.user_permissions` تعيد للمالك
        (`manager`) كلَّ مفاتيحه ولا تقبل سلبَ مفتاحٍ منه («المديرُ مالكُ الشركة
        — لا يُقفل خارج نظامه بتجاوز»). فالحالةُ القابلة للقياس دورٌ **آخر** في
        `ENTRY_APPROVER_ROLES` سُلب مفتاحَه صراحةً.
        """
        membership = UserCompanyMembership.objects.get(
            tenant=self.tenant, user=self.office_manager,
        )
        MemberPermission.objects.create(
            membership=membership,
            permission_key="office.clients.all",
            allowed=False,
        )

        res = self.export_full(expect=403, user=self.office_manager)

        self.assertIn("office.clients.all", res.content.decode("utf-8"))

    def test_an_office_manager_without_the_amounts_key_never_reaches_the_file(self):
        """«مبالغُه لله وحده»: من لا يرى المبالغَ لا يُنتَج له ملفٌّ بمبالغ."""
        membership = UserCompanyMembership.objects.get(
            tenant=self.tenant, user=self.office_manager,
        )
        MemberPermission.objects.create(
            membership=membership,
            permission_key="office.amounts.view",
            allowed=False,
        )

        res = self.export_full(expect=403, user=self.office_manager)

        self.assertIn("يرى المبالغ", res.content.decode("utf-8"))

    def test_the_office_manager_exports_when_both_keys_are_his(self):
        res = self.export_full(user=self.office_manager)

        self.assertIn("attachment", res["Content-Disposition"])


class WorkbookTest(OfficeExportsTestCase):
    """المصنَّفُ نفسُه: تسعُ أوراقٍ بأسمائها، وأعمدةٌ ثابتة، وأرقامٌ أرقام. """

    def test_the_file_opens_with_the_nine_sheets_in_order(self):
        workbook = self.workbook()

        self.assertEqual(workbook.sheetnames, SHEET_TITLES)

    def test_every_sheet_starts_with_its_arabic_header_row(self):
        workbook = self.workbook()
        headers = {
            title: [cell.value for cell in workbook[title][1]]
            for title in SHEET_TITLES
        }

        for title in SHEET_TITLES:
            self.assertTrue(all(headers[title]), title)
            self.assertTrue(
                all(isinstance(value, str) for value in headers[title]), title,
            )

        self.assertEqual(headers["الزباين"][0], "الاسم")
        # ورقةُ «الدفاتر» تُفصّل الحركةَ والبنودَ في أعمدةٍ متسلسلة (#290/أ).
        self.assertEqual(
            headers["الدفاتر"],
            [
                "الزبون", "الدفتر", "رقم الحركة", "التاريخ", "النوع", "الحساب",
                "مدين", "دائن", "الضريبة", "الطرف", "ملاحظة",
            ],
        )

    def test_the_download_name_carries_todays_date(self):
        res = self.export_full()

        self.assertIn(
            timezone.localdate().isoformat(), res["Content-Disposition"],
        )

    def test_amounts_land_as_numbers_with_the_two_decimal_format(self):
        FeePayment.objects.create(
            tenant=self.tenant,
            client=self.mine,
            method="cash",
            amount=Decimal("1234.50"),
            paid_at=DAY,
            receipt_number=f"{THIS_YEAR}-00001",
        )
        sheet = self.workbook()["الدفعات"]
        amounts = [
            cell
            for row in sheet.iter_rows()
            for cell in row
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
        ]

        self.assertTrue(amounts, "لا رقمَ في ورقة الدفعات — المبلغُ نصٌّ أو غائب")
        matched = [cell for cell in amounts if Decimal(str(cell.value)) == Decimal("1234.50")]
        self.assertTrue(matched, "مبلغُ الدفعة لم يظهر عدداً في الورقة")
        self.assertEqual(matched[0].number_format, book_exports.MONEY_FORMAT)

    def test_the_ledger_sheet_carries_the_entry_lines_with_their_tax_column(self):
        self.create_book(self.mine, opened_on=datetime.date(THIS_YEAR - 1, 1, 5))
        self.add_entry(
            self.mine, entry_date=DAY, memo="حركة التصدير",
            lines=[
                {"account_code": "1100", "debit": "200.00", "tax_amount": "30.00"},
                {"account_code": "4100", "credit": "200.00"},
            ],
        )

        rows = ScopingTest.sheet_values(self, "الدفاتر")

        self.assertEqual(len(rows), 2)
        first = rows[0]
        self.assertEqual(first[0], self.mine.name)
        self.assertEqual(first[10], "حركة التصدير")
        self.assertEqual(Decimal(str(first[6])), Decimal("200.00"))
        self.assertEqual(Decimal(str(first[8])), Decimal("30.00"))


class LockedSettingsTest(OfficeExportsTestCase):
    """مجموعةُ «التشغيل والنسخ»: إعدادان ظاهران مطفآن ومقفلان + تذكيرُ النسخة."""

    def test_the_operations_group_is_served_with_its_three_settings(self):
        payload, rows = self.settings_rows()
        groups = {group["id"]: group["label"] for group in payload["groups"]}

        self.assertEqual(groups.get("operations"), "التشغيل والنسخ")
        self.assertEqual(rows["official_invoicing"]["group"], "operations")
        self.assertEqual(rows["auto_send"]["group"], "operations")
        self.assertEqual(rows["data_export_reminder"]["group"], "operations")
        self.assertEqual(rows["data_export_reminder"]["value"], "monthly")

    def test_the_two_locked_settings_are_off_and_flagged_locked(self):
        _payload, rows = self.settings_rows()

        for key in ("official_invoicing", "auto_send"):
            with self.subTest(key=key):
                self.assertIs(rows[key]["value"], False)
                self.assertIs(rows[key]["locked"], True)

    def test_the_api_refuses_to_open_a_locked_setting_with_its_message(self):
        for key in ("official_invoicing", "auto_send"):
            with self.subTest(key=key):
                res = self.client.put(
                    f"{SETTINGS}{key}/", {"value": True}, format="json",
                    **self.headers(),
                )
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("مقفلٌ في هذه المرحلة", res.content.decode("utf-8"))

    def test_the_data_export_reminder_setting_is_open_and_writable(self):
        res = self.client.put(
            f"{SETTINGS}data_export_reminder/", {"value": "off"}, format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["value"], "off")


class MonthlyReminderTest(OfficeExportsTestCase):
    """التذكيرُ الشهري: مرّةً في الشهر، بالإعداد، ويُسكِته أخذُ النسخة."""

    def test_the_reminder_is_raised_once_per_month_for_every_approver(self):
        self.refresh()
        self.refresh()
        self.refresh(day=DAY + datetime.timedelta(days=1))

        rows = list(self.export_alerts())

        self.assertEqual(len(rows), 2, "تنبيهٌ مكرَّرٌ أو ناقصٌ في الشهر نفسه")
        self.assertEqual(
            {row.recipient_id for row in rows},
            {self.owner.pk, self.office_manager.pk},
        )
        self.assertEqual({row.message for row in rows}, {REMINDER_MESSAGE})
        self.assertFalse(any(row.client_id for row in rows))
        self.assertIsNone(rows[0].seen_at)

    def test_a_new_month_raises_a_new_reminder(self):
        self.refresh()
        next_month = datetime.date(THIS_YEAR, 7, 2)

        self.refresh(day=next_month)

        self.assertEqual(self.export_alerts().count(), 2)
        self.assertEqual(self.export_alerts(day=next_month).count(), 2)

    def test_switching_the_setting_off_raises_nothing(self):
        services.set_office_setting(self.tenant, "data_export_reminder", "off")

        self.refresh()

        self.assertEqual(self.export_alerts().count(), 0)

    def test_taking_the_copy_marks_this_months_alerts_seen(self):
        today = timezone.localdate()
        self.refresh(day=today)
        # تنبيهُ شهرٍ سابق يبقى غيرَ مقروء: التصديرُ يُسكِت شهرَه وحده.
        old = OfficeAlert.objects.create(
            tenant=self.tenant,
            recipient=self.owner,
            kind=OFFICE_ALERT_KIND_DATA_EXPORT_DUE,
            ref_key=f"export:{today.year - 1}-12",
            message=REMINDER_MESSAGE,
            day=datetime.date(today.year - 1, 12, 1),
        )

        self.export_full()

        self.assertFalse(
            self.export_alerts(day=today).filter(seen_at__isnull=True).exists(),
        )
        old.refresh_from_db()
        self.assertIsNone(old.seen_at)

    def test_the_bell_carries_the_new_kind_with_its_own_destination(self):
        self.refresh()

        res = self.client.get(f"{BASE}alerts/", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        row = next(
            item for item in res.data["rows"]
            if item["kind"] == OFFICE_ALERT_KIND_DATA_EXPORT_DUE
        )

        self.assertEqual(row["opens"], "operations")
        self.assertTrue(row["kind_label"])


class PdfLinkTest(OfficeExportsTestCase):
    """رابطُ PDF للنسخة: نوعُ مستندٍ جديد، وجداولُه التسعة على الصفحة."""

    def test_the_link_is_created_and_the_public_page_shows_the_nine_tables(self):
        from docshare.models import DOC_OFFICE_DATA_EXPORT, DocumentShare

        res = self.client.post(EXPORT_FULL_LINK, {}, format="json", **self.headers())
        self.assertEqual(res.status_code, 201, res.content)

        share = DocumentShare.objects.get(doc_type=DOC_OFFICE_DATA_EXPORT)
        self.assertIn(share.token, res.data["url"])

        page = self.client.get(f"/api/share/{share.token}/")
        self.assertEqual(page.status_code, 200)
        body = page.content.decode("utf-8")
        for title in SHEET_TITLES:
            self.assertIn(title, body, title)

    def test_the_link_is_owner_only(self):
        res = self.client.post(
            EXPORT_FULL_LINK, {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

        self.as_user(self.accountant)
        refused = self.client.post(
            EXPORT_FULL_LINK, {}, format="json", **self.headers(),
        )
        self.assertEqual(refused.status_code, 403)

    def test_switching_the_report_link_off_returns_400_and_keeps_the_file(self):
        services.set_office_setting(self.tenant, "office_report_pdf_link", False)

        res = self.client.post(EXPORT_FULL_LINK, {}, format="json", **self.headers())

        self.assertEqual(res.status_code, 400, res.content)
        # الرسالةُ تسمّي الإعدادَ بتسميته المعروضة في الشاشة لا بكوده.
        self.assertIn(
            "رابط PDF للتقارير", res.content.decode("utf-8"),
        )
        self.export_full()
