"""الأتعاب ٢/١ — فاتورةُ الأتعاب الورقية: النموذجُ والترقيمُ والإلغاءُ والشاشتان (#282).

**الخادمُ وحده** (الجزء أ٢/١): شاشةُ «المسودّات» وتبويبُ «الحساب» في الواجهة أ٢/٢،
وهذا الملفّ يقيس ما يُنتجه خادمُ الورقة: صفٌّ مرقَّمٌ لا يُمحى، وورقةٌ تُصيَّر
منه، ورابطٌ عامٌّ لا يكشف إلا فاتورته.

**والقواعدُ التي يسقط عندها الاختبار:**
1. **الاعتمادُ يولّد فاتورةً واحدة** — مرّتان لا تضيفان صفّاً (`get_or_create` على
   المسودّة)، والترقيمُ عدّادٌ مقفولٌ متسلسلٌ لا يتكرّر.
2. **الإشعارُ الدائنُ على سلسلةٍ منفصلة** والفاتورةُ التكميلية على السلسلة الرئيسية.
3. **«ليست فاتورة ضريبية» ثابتةٌ في الورقة**، ولا «فاتورة ضريبية» بلا نفيٍ في أيّ
   موضع.
4. **سطرُ الضريبة يغيب حين المكتبُ ليس مشتغلاً مرخّصاً** ويظهر حين يكون — بنسبةٍ
   مؤرَّخةٍ على الصفّ لا تُقرأ ساعةَ العرض.
5. **الحقولُ التسعة بترتيبها في فلسطين**، والنسختان «الأصل» ثم «نسخة»، وسبعةُ
   `§9א` في إسرائيل.
6. **لا نقطةَ API تحذف فاتورةً** — ولا تعدّلها: `DELETE`/`PUT`/`PATCH` ⇒ 405.
7. **الإلغاءُ قبل الإرسال وحده**: بعد إنشاء الرابط 400، والصفُّ يبقى في التاريخ.
8. **الرابطُ العامّ لا يكشف إلا فاتورته** (فاتورتان، توكنان).
9. **القناع**: محاسبٌ بلا `office.amounts.view` يقرأ `null` في المبالغ — والكتابة 403.
10. **«جاهز للإرسال»** يحمل رسالةَ الفاتورة: مبلغَها واستحقاقَها بعد سبعة أيامٍ
    ورابطَ ورقتها.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting_office import fee_invoices, fees, services
from accounting_office.models import (
    FEE_INVOICE_KIND_CREDIT_NOTE,
    FEE_INVOICE_KIND_INVOICE,
    FEE_INVOICE_KIND_SUPPLEMENTARY,
    FeeDraft,
    FeeInvoice,
    FeeSubscription,
    OfficeClient,
    TaxCard,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
INVOICES = f"{BASE}fees/invoices/"
DRAFTS = f"{BASE}fees/drafts/"
SHARES = "/api/document-shares/"

MARCH = datetime.date(2026, 3, 1)

#: السطرُ الثابت في كل صفحة — **لا يُطفأ ولا يُحذف بإعداد**.
NOT_TAX_PS = "ليست فاتورة ضريبية"
NOT_TAX_IL = "אינו חשבונית מס"

#: حقولُ م4/1 التسعة بترتيبها (السابع والثامن يغيبان حين لا مصدرَ لهما: لا
#: ضريبةً بالحروف ولا عملةً أجنبية — يُسمّيان في تقرير التسليم).
PS_ORDER = (
    "فاتورة أتعاب",
    "الأصل",
    "رقم الفاتورة",
    "تاريخ الإصدار",
    "الزبون",
    "البيان",
    "الإجمالي قبل الضريبة",
    "قيمة الضريبة",
    "الإجمالي شاملاً الضريبة",
    "توقيع المُصدِر",
)

#: عناصرُ `§9א` السبعة (תקנות מע"מ (ניהול פנקסי חשבונות) תשל"ו-1976،
#: وتعديلُها في تعليمات نיהול הפנקסים): رقمٌ سيدوري، تاريخ، هويةُ העוסק،
#: المקבל، وصفُ العملية، התמורה، التوقيع.
IL_MARKERS = (
    "מספר סידורי",
    "תאריך הוצאה",
    "עוסק",
    "שם המקבל",
    "תיאור הפעולה",
    "התמורה",
    "חתימת המוציא",
)


def decimal_of(value) -> Decimal:
    return Decimal(str(value))


class FeeInvoiceTestCase(APITestCase):
    """مكتبٌ مرخّصٌ برقم مشتغلٍ مرخّص — ومنه تُقاس الضريبةُ المؤرَّخة."""

    @classmethod
    def setUpTestData(cls):
        cls.currency = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )[0]
        cls.owner = User.objects.create_user(username="inv_owner", password="x")
        cls.tenant = create_company("مكتب الفواتير", cls.owner, template="accounting_office")
        invalidate_module_cache(cls.tenant.pk)
        services.set_office_setting(cls.tenant, "tax_system", "PS")
        services.set_office_setting(cls.tenant, "office_size", "small")
        #: رقمُ المشتغل المرخّص هو رقمُ تسجيل المكتب في الترويسة **وهو نفسه مصدرُ
        #: «المكتب مشتغل مرخّص»**: لا إعدادَ مستقلّ له في السجلّ (يُقاس شكله حرفياً
        #: في `test_settings.py`)، وورقةٌ بلا رقم تسجيلٍ لا تصلح فاتورةً أصلاً.
        cls.settings_row = cls.tenant.settings
        cls.settings_row.licensed_dealer_no = "512345678"
        cls.settings_row.company_name_primary = "مكتب الفواتير"
        cls.settings_row.address = "نابلس — شارع رفيديا"
        cls.settings_row.phone = "092345678"
        cls.settings_row.save()

        cls.accountant_user = User.objects.create_user(
            username="inv_accountant", password="x",
        )
        UserCompanyMembership.objects.create(
            user=cls.accountant_user, tenant=cls.tenant, role="accountant",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.owner)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def with_dealer_no(self, value):
        """يُبدّل رقمَ المشتغل المرخّص — «مشتغلٌ مرخّص» مفعلاً ومطفأً."""
        self.settings_row.licensed_dealer_no = value
        self.settings_row.save(update_fields=["licensed_dealer_no"])

    def make_client(self, name="زبون الفاتورة", *, responsible=None):
        client = OfficeClient.objects.create(
            tenant=self.tenant, name=name, responsible=responsible,
        )
        TaxCard.objects.create(client=client)
        return client

    def make_invoice(self, *, amount="1000.00", name="زبون الفاتورة", responsible=None,
                     day=MARCH, approve=True):
        """مسودّةٌ معتمدةٌ ثم فاتورتها — **من مسار الاعتماد الحقيقيّ لا بصفٍّ مزروع**."""
        client = self.make_client(name, responsible=responsible)
        FeeSubscription.objects.create(
            tenant=self.tenant, client=client, amount=Decimal(amount),
            currency=self.currency, starts_on=datetime.date(2026, 1, 1),
        )
        services.refresh_office(self.tenant, day=day)
        draft = FeeDraft.objects.get(client=client, year=day.year, month=day.month)
        if approve:
            fees.approve_fee_draft(draft, actor=self.owner)
        return FeeInvoice.objects.get(draft=draft)

    def page_of(self, invoice):
        """ورقةُ الفاتورة كما يراها الزبون — تُحلّ من رابطها العامّ."""
        share = services_create_share(self.tenant, invoice)
        response = self.client.get(f"/s/{share.token}")
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")


def services_create_share(tenant, invoice):
    """رابطٌ عامٌّ لفاتورة — من خدمة `docshare` وحدها بلا مسارٍ إداريّ."""
    from docshare import services as docshare_services
    from docshare.models import DOC_FEE_INVOICE

    return docshare_services.create_share(tenant, DOC_FEE_INVOICE, invoice.pk)


class IssueOnApprovalTest(FeeInvoiceTestCase):
    """الاعتمادُ هو المكانُ الوحيد الذي تصير فيه المسودّةُ فاتورةً مرقَّمة."""

    def test_the_approval_issues_exactly_one_invoice(self):
        invoice = self.make_invoice(amount="1000.00")

        self.assertEqual(invoice.kind, FEE_INVOICE_KIND_INVOICE)
        self.assertEqual(invoice.draft.status, FeeDraft.STATUS_APPROVED)
        self.assertEqual(invoice.number, "أتعاب-2026-00001")
        self.assertEqual(invoice.issued_by, self.owner)
        self.assertEqual(invoice.client, invoice.draft.client)
        self.assertEqual(decimal_of(invoice.total), Decimal("1160.00"))
        self.assertEqual(decimal_of(invoice.tax_total), Decimal("160.00"))
        self.assertIs(invoice.is_tax_invoice, False)

    def test_a_draft_cannot_grow_a_second_invoice(self):
        """**متكرِّرةُ الأمان**: إعادةُ النداء على المسودّة نفسها لا تُرقّم ثانيةً."""
        invoice = self.make_invoice()
        again = fee_invoices.issue_for_draft(invoice.draft, actor=self.owner)

        self.assertEqual(again.pk, invoice.pk)
        self.assertEqual(FeeInvoice.objects.filter(draft=invoice.draft).count(), 1)

    def test_approve_all_issues_its_invoices_too(self):
        """«اعتمد الكل» يمرّ بالمسار نفسه — وإلا خرجت مسودّاتٌ معتمدةٌ بلا ورقة."""
        first = self.make_client("زبون أول", responsible=self.owner)
        second = self.make_client("زبون ثانٍ", responsible=self.owner)
        for client in (first, second):
            FeeSubscription.objects.create(
                tenant=self.tenant, client=client, amount=Decimal("500.00"),
                currency=self.currency, starts_on=datetime.date(2026, 1, 1),
            )
        services.refresh_office(self.tenant, day=MARCH)

        res = self.client.post(f"{DRAFTS}approve-all/", {}, format="json", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            sorted(FeeInvoice.objects.values_list("number", flat=True)),
            ["أتعاب-2026-00001", "أتعاب-2026-00002"],
        )


class NumberingTest(FeeInvoiceTestCase):
    """الترقيمُ عدّادٌ مقفولٌ متسلسلٌ — لا `MAX+1` ولا `count+1`."""

    def test_two_invoices_get_two_consecutive_numbers(self):
        first = self.make_invoice(name="زبون أول")
        second = self.make_invoice(name="زبون ثانٍ")

        self.assertNotEqual(first.number, second.number)
        self.assertEqual(
            sorted([first.number, second.number]),
            ["أتعاب-2026-00001", "أتعاب-2026-00002"],
        )

    def test_the_credit_note_numbers_on_a_separate_series(self):
        invoice = self.make_invoice()
        res = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "160.00", "reason": "خصم اتفاق"},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["kind"], FEE_INVOICE_KIND_CREDIT_NOTE)
        self.assertEqual(res.data["number"], "إشعار-أتعاب-2026-00001")
        self.assertEqual(res.data["related_invoice"], invoice.pk)
        # والسلسلةُ الرئيسية لم تُستهلك بإشعارٍ دائن.
        self.assertEqual(FeeInvoice.objects.get(pk=invoice.pk).number, "أتعاب-2026-00001")

    def test_the_supplementary_stays_on_the_main_series(self):
        invoice = self.make_invoice()
        res = self.client.post(
            f"{INVOICES}{invoice.pk}/supplementary/",
            {"amount": "100.00", "reason": "خدمةٌ نُسيت"},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["kind"], FEE_INVOICE_KIND_SUPPLEMENTARY)
        self.assertEqual(res.data["number"], "أتعاب-2026-00002")


class TaxLineTest(FeeInvoiceTestCase):
    """سطرُ الضريبة مرتبطٌ بترخيص المكتب — ويغيب كاملاً حين يُطفأ."""

    def test_the_line_shows_when_the_office_is_a_licensed_dealer(self):
        html = self.page_of(self.make_invoice(amount="1000.00"))

        self.assertEqual(html.count(NOT_TAX_PS), 2)  # عنصرٌ متكرِّر + `@page`
        self.assertIn("قيمة الضريبة", html)
        self.assertIn("160", html.replace("\u200f", ""))
        self.assertIn("16", html)

    def test_the_line_disappears_entirely_when_the_office_is_not_licensed(self):
        self.with_dealer_no("")

        invoice = self.make_invoice(amount="1000.00")
        html = self.page_of(invoice)

        self.assertEqual(decimal_of(invoice.tax_total), Decimal("0.00"))
        self.assertEqual(decimal_of(invoice.total), Decimal("1000.00"))
        self.assertNotIn("قيمة الضريبة", html)
        self.assertNotIn("الإجمالي قبل الضريبة", html)
        # والنفيُ ثابتٌ في الحالين — إطفاءُ الترخيص لا يُخرج ورقةً تدّعي الرسمية.
        self.assertEqual(html.count(NOT_TAX_PS), 2)


class ShapeTest(FeeInvoiceTestCase):
    """الحقولُ القانونية بترتيبها — لا ترتيبَ آخر يقبله اختبارٌ آخر."""

    def test_palestine_prints_the_nine_fields_in_order_and_two_copies(self):
        html = self.page_of(self.make_invoice())

        positions = [html.index(marker) for marker in PS_ORDER]
        self.assertEqual(positions, sorted(positions), "الحقولُ التسعة خرجت بغير ترتيبها")
        # النسختان «الأصل» ثم «نسخة» — والحقلُ الأوّل «مطبوعٌ في الترويسة».
        self.assertEqual(html.count("الأصل"), 1)
        self.assertEqual(html.count("نسخة"), 1)
        self.assertLess(html.index("الأصل"), html.index("نسخة"))
        self.assertIn("512345678", html)
        self.assertIn("الأصل", html)

    def test_no_tax_invoice_word_ever_ships_without_its_negation(self):
        html = self.page_of(self.make_invoice())

        self.assertEqual(html.count(NOT_TAX_PS), 2)
        # البحثُ بعد حذف النفي: كلُّ ذكرٍ بلا نفيٍ يسقط الاختبار.
        self.assertNotIn("فاتورة ضريبية", html.replace(NOT_TAX_PS, ""))

    def test_israel_prints_the_seven_section_9a_elements(self):
        services.set_office_setting(self.tenant, "tax_system", "IL")
        html = self.page_of(self.make_invoice())

        for marker in IL_MARKERS:
            self.assertIn(marker, html)
        self.assertIn("חשבון עסקה", html)
        self.assertEqual(html.count(NOT_TAX_IL), 2)
        self.assertNotIn("חשבונית מס", html.replace(NOT_TAX_IL, ""))
        # ولا نسختين في إسرائيل ولا عنواناً عربياً لفاتورةٍ عبرية.
        self.assertNotIn("الأصل", html)
        self.assertNotIn("فاتورة أتعاب", html)


class NoDeleteTest(FeeInvoiceTestCase):
    """فاتورةٌ معتمدةٌ لا تُمحى من أيّ نقطة — ولا تُعدَّل تعديلاً جزئياً."""

    def test_every_destructive_verb_is_closed(self):
        invoice = self.make_invoice()

        for method in (self.client.delete, self.client.put, self.client.patch):
            res = method(f"{INVOICES}{invoice.pk}/", {}, format="json", **self.headers())
            self.assertEqual(res.status_code, 405, res.content)

        self.assertTrue(FeeInvoice.objects.filter(pk=invoice.pk).exists())

    def test_the_collection_refuses_a_manual_create(self):
        res = self.client.post(INVOICES, {}, format="json", **self.headers())
        self.assertEqual(res.status_code, 405, res.content)


class CancelTest(FeeInvoiceTestCase):
    """الإلغاءُ فعلٌ لا حذف — وقبل الإرسال وحده."""

    def test_cancel_before_sending_marks_the_row_and_keeps_it(self):
        invoice = self.make_invoice()

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {"reason": "شهرٌ خاطئ"},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["state"], "cancelled")
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.cancelled_at)
        self.assertEqual(invoice.cancel_reason, "شهرٌ خاطئ")
        self.assertEqual(invoice.cancelled_by, self.owner)
        self.assertTrue(FeeInvoice.objects.filter(pk=invoice.pk).exists())

    def test_cancel_after_the_link_exists_is_refused_with_an_arabic_message(self):
        invoice = self.make_invoice()
        services_create_share(self.tenant, invoice)

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.cancelled_at)
        self.assertIn("الرابط", str(res.content, "utf-8"))

    def test_a_cancelled_invoice_cannot_be_cancelled_twice(self):
        invoice = self.make_invoice()
        self.client.post(f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers())

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)


class CreditNoteRulesTest(FeeInvoiceTestCase):
    """الإشعارُ الدائن: مبلغٌ لا يتجاوز الإجمالي، وسببٌ غيرُ فارغ."""

    def test_an_amount_above_the_total_is_refused(self):
        invoice = self.make_invoice(amount="1000.00")

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "1160.01", "reason": "خطأ"},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(FeeInvoice.objects.filter(kind=FEE_INVOICE_KIND_CREDIT_NOTE).exists())

    def test_an_empty_reason_is_refused(self):
        invoice = self.make_invoice()

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "100.00", "reason": "   "},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)

    def test_a_zero_or_negative_amount_is_refused(self):
        invoice = self.make_invoice()

        for amount in ("0", "-5"):
            res = self.client.post(
                f"{INVOICES}{invoice.pk}/credit-note/",
                {"amount": amount, "reason": "خطأ"},
                format="json", **self.headers(),
            )
            self.assertEqual(res.status_code, 400, res.content)


class VisibilityTest(FeeInvoiceTestCase):
    """العزلُ والقناع: زبونُ زميلٍ 404، والمبلغُ `null` لمن لا يراه."""

    def test_the_list_hides_the_invoices_of_clients_the_member_cannot_see(self):
        self.make_invoice(name="زبون المالك", responsible=self.owner)
        self.client.force_authenticate(user=self.accountant_user)

        res = self.client.get(INVOICES, **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data, [])

    def test_the_accountant_without_amounts_reads_null_amounts(self):
        invoice = self.make_invoice(
            name="زبون المحاسب", responsible=self.accountant_user,
        )
        self.client.force_authenticate(user=self.accountant_user)

        listed = self.client.get(INVOICES, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(len(listed.data), 1, listed.content)
        row = listed.data[0]
        self.assertEqual(row["number"], invoice.number)
        self.assertIsNone(row["total"])
        self.assertIsNone(row["tax_total"])

        detail = self.client.get(f"{INVOICES}{invoice.pk}/", **self.headers())
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertIsNone(detail.data["total"])
        self.assertEqual(
            [line["amount"] for line in detail.data["lines"]], [None],
        )

    def test_the_accountant_cannot_write_a_credit_note_amount(self):
        invoice = self.make_invoice(
            name="زبون المحاسب", responsible=self.accountant_user,
        )
        self.client.force_authenticate(user=self.accountant_user)

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "10.00", "reason": "أي سبب"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 403, res.content)

    def test_the_owner_sees_the_amounts(self):
        invoice = self.make_invoice()

        res = self.client.get(f"{INVOICES}{invoice.pk}/", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(decimal_of(res.data["total"]), Decimal("1160.00"))
        self.assertEqual(decimal_of(res.data["tax_total"]), Decimal("160.00"))
        self.assertEqual(decimal_of(res.data["lines"][0]["amount"]), Decimal("1000.00"))

    def test_the_filters_narrow_by_client_kind_and_state(self):
        first = self.make_invoice(name="زبون أول")
        second = self.make_invoice(name="زبون ثانٍ")
        self.client.post(f"{INVOICES}{second.pk}/cancel/", {}, format="json", **self.headers())

        by_client = self.client.get(
            f"{INVOICES}?client={first.client_id}", **self.headers(),
        )
        self.assertEqual([row["id"] for row in by_client.data], [first.pk])

        cancelled = self.client.get(f"{INVOICES}?state=cancelled", **self.headers())
        self.assertEqual([row["id"] for row in cancelled.data], [second.pk])

        issued = self.client.get(f"{INVOICES}?state=issued", **self.headers())
        self.assertEqual([row["id"] for row in issued.data], [first.pk])

        by_kind = self.client.get(f"{INVOICES}?kind=credit_note", **self.headers())
        self.assertEqual(by_kind.data, [])


class PublicLinkTest(FeeInvoiceTestCase):
    """الرابطُ العامّ لا يكشف إلا فاتورته — لا فاتورةَ زميلٍ ولا شركةٍ أخرى."""

    def test_each_link_shows_only_its_own_invoice(self):
        first = self.make_invoice(name="زبون أول", amount="1000.00")
        second = self.make_invoice(name="زبون ثانٍ", amount="2000.00")

        first_html = self.page_of(first)
        second_html = self.page_of(second)

        self.assertIn(first.number, first_html)
        self.assertNotIn(second.number, first_html)
        self.assertNotIn("2160", first_html)
        self.assertIn(second.number, second_html)
        self.assertNotIn(first.number, second_html)

    def test_the_admin_surface_refuses_to_create_the_link_directly(self):
        """بابُ النوع «جاهز للإرسال» وحده — لا `POST /api/document-shares/`."""
        invoice = self.make_invoice()

        res = self.client.post(
            SHARES, {"doc_type": "fee_invoice", "doc_id": invoice.pk},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("جاهز للإرسال", str(res.content, "utf-8"))

    def test_the_share_list_is_scoped_to_visible_clients(self):
        invoice = self.make_invoice(name="زبون المالك", responsible=self.owner)
        share = services_create_share(self.tenant, invoice)
        self.client.force_authenticate(user=self.accountant_user)

        listed = self.client.get(
            f"{SHARES}?doc_type=fee_invoice", **self.headers(),
        )
        self.assertEqual(listed.status_code, 200, listed.content)
        rows = listed.data["results"] if isinstance(listed.data, dict) else listed.data
        self.assertEqual(rows, [])

        detail = self.client.get(f"{SHARES}{share.pk}/", **self.headers())
        self.assertEqual(detail.status_code, 404, detail.content)


class ReadyToSendTest(FeeInvoiceTestCase):
    """رسالةُ الفاتورة في «جاهز للإرسال»: مبلغٌ واستحقاقٌ بعد سبعة أيامٍ ورابط."""

    def ready_contact(self, client):
        from accounting_office.models import ClientContact, Contact

        contact = Contact.objects.create(
            tenant=self.tenant, name="مدير الزبون", phone="0599000000", language="ar",
        )
        ClientContact.objects.create(
            tenant=self.tenant, client=client, contact=contact, is_primary=True,
        )
        #: لا يومَ راحةٍ في الاختبار: اليومُ المحسوب معلوم، والحاجزُ له اختبارُه.
        services.set_client_setting(client, "rest_days", [])
        return contact

    def test_the_issued_invoice_appears_with_its_amount_due_date_and_link(self):
        invoice = self.make_invoice(amount="1000.00")
        self.ready_contact(invoice.client)
        issued_day = invoice.issued_at.date()

        payload = services.ready_to_send_payload(
            self.tenant, user=self.owner, day=issued_day + datetime.timedelta(days=7),
        )

        items = [item for message in payload["messages"] for item in message["items"]]
        self.assertEqual(len(items), 1, payload)
        item = items[0]
        self.assertEqual(item["reminder_type"], "balance")
        self.assertEqual(item["client_id"], invoice.client_id)
        self.assertEqual(
            item["due_date"],
            (issued_day + datetime.timedelta(days=7)).isoformat(),
        )
        self.assertEqual(item["invoice"]["number"], invoice.number)
        self.assertEqual(decimal_of(item["invoice"]["total"]), Decimal("1160.00"))
        self.assertIn("/s/", item["invoice"]["url"])

    def test_the_cancelled_invoice_is_not_offered(self):
        invoice = self.make_invoice()
        self.ready_contact(invoice.client)
        self.client.post(f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers())

        payload = services.ready_to_send_payload(
            self.tenant, user=self.owner,
            day=invoice.issued_at.date() + datetime.timedelta(days=7),
        )

        self.assertEqual(payload["messages"], [])
