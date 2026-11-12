"""الأتعاب ٢/١ — فاتورةُ الأتعاب الورقية: النموذجُ والترقيمُ والإلغاءُ والورقة (#282).

**الخادمُ وحده** (الجزء أ٢/١): شاشةُ «المسودّات» وتبويبُ «الحساب» في الواجهة أ٢/٢،
وهذا الملفّ يقيس ما يُنتجه خادمُ الورقة: صفٌّ مرقَّمٌ لا يُمحى، وورقةٌ تُصيَّر
منه، ورابطٌ عامٌّ لا يكشف إلا فاتورته.

**والقواعدُ التي يسقط عندها الاختبار:**
1. **الاعتمادُ يولّد فاتورةً واحدة** — مرّتان لا تضيفان صفّاً حيّاً، والترقيمُ
   عدّادٌ مقفولٌ متسلسلٌ لا يتكرّر.
2. **الإلغاءُ يعيد المسودّةَ مسودّةً** فتُعتمد ثانيةً وتُصدر ورقةً جديدةً برقمٍ
   جديد — فلا شهرٌ لا يُفاتر أبداً، **وقبل الإرسال وحده** (تذكيرٌ صادرٌ أو
   مشاهدةٌ على الرابط — لا مجرّدُ فتح «جاهز للإرسال»)، و**لا يُلغى أصلٌ لإشعارٍ
   دائنٍ حيّ** (409 قبل أي كتابة).
3. **الإشعارُ الدائنُ على سلسلةٍ منفصلة** بسقفٍ **تراكميّ**، والتكميليةُ على
   السلسلة الرئيسية **بلا سقفِ الأصل**.
4. **«ليست فاتورة ضريبية» ثابتةٌ تحت العنوان وفي التذييل**، ولا «فاتورة ضريبية»
   بلا نفيٍ في أيّ موضع.
5. **سطرُ الضريبة يتبع إعدادَ «المكتب مشتغل مرخّص»** — ويغيب كاملاً حين يُطفأ؛
   والنظامُ والنسبةُ والعنوانُ **لقطاتٌ على الصفّ** لا قراءةً حيّة.
6. **حقولُ م4/1 الثمانيةُ المبنيّةُ من التسعة بترتيبها في فلسطين** (سعرُ الصرف
   مؤجَّل)، والنسختان «الأصل» ثم «نسخة»، وسبعةُ `§9א` في إسرائيل.
7. **لا نقطةَ API تحذف فاتورةً** — ولا تعدّلها: `DELETE`/`PUT`/`PATCH` ⇒ 405.
8. **الرابطُ العامّ لا يكشف إلا فاتورته** (فاتورتان، توكنان).
9. **القناع**: محاسبٌ بلا `office.amounts.view` يقرأ `null` في المبالغ — والكتابة 403.
10. **«جاهز للإرسال»**: الفاتورةُ مطالبةٌ (`balance`) من **يوم إصدارها** واستحقاقُها
    بعد سبعة أيام، والإشعارُ الدائنُ مستندٌ **غيرُ مطالِب** (`documents`) ونصُّه
    يسمّي أصله، وشهرُ نصوصه من **المسودّة** لا من يوم الإصدار.
11. **تعليقُ القالب لا يصل إلى ورقة الزبون** — `{# … #}` يُقلَّم على سطرٍ واحد.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office import deadlines, fee_invoices, fees, services
from accounting_office.models import (
    FEE_INVOICE_KIND_CREDIT_NOTE,
    FEE_INVOICE_KIND_INVOICE,
    FEE_INVOICE_KIND_SUPPLEMENTARY,
    ClientContact,
    Contact,
    FeeDraft,
    FeeInvoice,
    FeeInvoiceSequence,
    FeeSubscription,
    OfficeClient,
    ReminderLog,
    TaxCard,
    fee_invoice_credit_series,
    fee_invoice_number,
    fee_invoice_series,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
INVOICES = f"{BASE}fees/invoices/"
DRAFTS = f"{BASE}fees/drafts/"
SHARES = "/api/document-shares/"

MARCH = datetime.date(2026, 3, 1)

#: شارةُ النسخة كما تُصيَّر — **العنصرُ لا الكلمة**: كلمة «نسخة» ترد في تعليقات
#: CSS المشحونة مع الصفحة، والعدُّ بالكلمة يقيس التعليقَ لا الورقة.
COPY_ORIGINAL = 'class="fi-copy">الأصل<'
COPY_DUPLICATE = 'class="fi-copy">نسخة<'

#: السطرُ الثابت في كل صفحة — **لا يُطفأ ولا يُحذف بإعداد**.
NOT_TAX_PS = "ليست فاتورة ضريبية"
NOT_TAX_IL = "אינו חשבונית מס"
#: عددُ ظهوره في ورقةٍ فلسطينية: نسختان (واحدٌ تحت عنوان كلٍّ منهما) + تذييلُ
#: الصفحة + محتوى `@page` في CSS الطباعة.
PS_NOT_TAX_COUNT = 4
IL_NOT_TAX_COUNT = 3

#: حقولُ م4/1 **كما بُنيت فعلاً** بترتيبها بعد العنوان: الثاني تاريخُ الإصدار،
#: والرابعُ البند، والخامسُ قبل الضريبة، والسادسُ الضريبةُ رقمًا وحرفاً، والسابعُ
#: شاملها. **(1) الترويسةُ** (الاسمُ ورقمُ التسجيل والاسمُ التجاري والعنوان والهاتف
#: وعبارةُ «الأصل») تُقاس قبل العنوان، و**(9) التوقيعُ** آخِرٌ. والثامن (سعرُ
#: الصرف) **مؤجَّل**: `FeeDraft` بلا عملةٍ منذ أ١، ولا حقلَ عملةٍ في هذا الجزء.
PS_ORDER = (
    "فاتورة أتعاب",
    "رقم الفاتورة",
    "تاريخ الإصدار",
    "الزبون",
    "البيان",
    "الإجمالي قبل الضريبة",
    "قيمة الضريبة",
    "قيمة الضريبة بالحروف",
    "الإجمالي شاملاً الضريبة",
    "توقيع المُصدِر",
)

#: عناصرُ `§9א` السبعة (תקנות מע"מ (ניהול פנקסי חשבונות) תשל"ו-1976). هويةُ
#: העוסק تُطبع في الترويسة قبل العنوان، والباقي بعده بترتيبه.
IL_HEADER_MARKER = "עוסק"
IL_MARKERS = (
    "מספר סידורי",
    "תאריך הוצאה",
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
        #: رقمُ تسجيل المكتب في الترويسة (الحقلُ الأوّل من م4/1) — **وليس مصدرَ
        #: «مشتغل مرخّص»**: ذاك إعدادٌ مستقلّ يُبدَّل في اختباراته.
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

    def set_setting(self, key, value):
        """إعدادُ مكتبٍ داخل الاختبار — وكلُّ اختبارٍ يُلفّ في معاملةٍ فتُرجَع."""
        services.set_office_setting(self.tenant, key, value)

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
        return FeeInvoice.objects.get(source_draft=draft, cancelled_at__isnull=True)

    def page_of(self, invoice):
        """ورقةُ الفاتورة كما يراها الزبون — تُحلّ من رابطها العامّ."""
        share = create_share(self.tenant, invoice)
        response = self.client.get(f"/s/{share.token}")
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    def card_of(self, invoice):
        """نسخةٌ من الصفّ بعلاقاتها — بعد تعديلٍ خارج الـAPI."""
        return (
            FeeInvoice.objects
            .select_related("tenant", "client", "related_invoice")
            .get(pk=invoice.pk)
        )


def create_share(tenant, invoice):
    """رابطٌ عامٌّ لفاتورة — من خدمة `docshare` وحدها بلا مسارٍ إداريّ."""
    from docshare import services as docshare_services
    from docshare.models import DOC_FEE_INVOICE

    return docshare_services.create_share(tenant, DOC_FEE_INVOICE, invoice.pk)


def local_day(moment):
    """تاريخُ اللحظة **بتوقيت الخادم** لا UTC.

    `moment.date()` على لحظةٍ مقروءةٍ من القاعدة يعطي تاريخَ UTC (القاعدةُ تُخزّن
    UTC)، فهو يسبق تاريخَ المكتب بين 21:00 و24:00 UTC فيسقط الاختبارُ ليلاً.
    """
    return timezone.localtime(moment).date()


class IssueOnApprovalTest(FeeInvoiceTestCase):
    """الاعتمادُ هو المكانُ الوحيد الذي تصير فيه المسودّةُ فاتورةً مرقَّمة."""

    def test_the_approval_issues_exactly_one_invoice(self):
        invoice = self.make_invoice(amount="1000.00")

        self.assertEqual(invoice.kind, FEE_INVOICE_KIND_INVOICE)
        self.assertEqual(invoice.source_draft.status, FeeDraft.STATUS_APPROVED)
        self.assertEqual(
            invoice.number,
            fee_invoice_number(fee_invoice_series(invoice.issued_at.year), 1),
        )
        self.assertEqual(invoice.issued_by, self.owner)
        self.assertEqual(invoice.client, invoice.source_draft.client)
        self.assertEqual(decimal_of(invoice.total), Decimal("1160.00"))
        self.assertEqual(decimal_of(invoice.tax_total), Decimal("160.00"))
        self.assertEqual(decimal_of(invoice.tax_percent), Decimal("16.00"))
        self.assertEqual(invoice.tax_system, "PS")
        self.assertIs(invoice.is_tax_invoice, False)

    def test_a_draft_cannot_grow_a_second_live_invoice(self):
        """**متكرِّرةُ الأمان**: إعادةُ النداء على المسودّة نفسها لا تُرقّم ثانيةً."""
        invoice = self.make_invoice()
        again = fee_invoices.issue_for_draft(invoice.source_draft, actor=self.owner)

        self.assertEqual(again.pk, invoice.pk)
        self.assertEqual(
            FeeInvoice.objects.filter(source_draft=invoice.source_draft).count(), 1,
        )

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
        # سنةُ السلسلة من **تاريخ اليوم المحلّيّ** لا من ساعة الحائط: الفاتورةُ
        # صدرت الآن، و`date.today()` في عمليّةٍ بتوقيتٍ آخر تنقلب على الحدّ.
        year = timezone.localdate().year
        series = fee_invoice_series(year)
        self.assertEqual(
            sorted(FeeInvoice.objects.values_list("number", flat=True)),
            [fee_invoice_number(series, 1), fee_invoice_number(series, 2)],
        )


class NumberingTest(FeeInvoiceTestCase):
    """الترقيمُ عدّادٌ مقفولٌ متسلسلٌ — لا `MAX+1` ولا `count+1`."""

    def test_two_invoices_get_two_consecutive_numbers(self):
        first = self.make_invoice(name="زبون أول")
        second = self.make_invoice(name="زبون ثانٍ")
        series = fee_invoice_series(first.issued_at.year)

        self.assertNotEqual(first.number, second.number)
        self.assertEqual(
            sorted([first.number, second.number]),
            [fee_invoice_number(series, 1), fee_invoice_number(series, 2)],
        )

    def test_the_credit_note_numbers_on_a_separate_series(self):
        """**سلسلتان مختلفتان فعلاً** — لا مقارنةُ دالّةٍ بدالّتها.

        كان المتوقَّعُ يُبنى بـ`fee_invoice_credit_series` نفسِها التي يقرؤها
        الخادم، فلو صارت السلسلتان واحدة لمرّ الاختبارُ وهو يقيس نفسَه. الصيغةُ
        الآن من **النصّ الحرفيّ** لبادئة كل سلسلة.
        """
        invoice = self.make_invoice()
        res = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "160.00", "reason": "خصم اتفاق"},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["kind"], FEE_INVOICE_KIND_CREDIT_NOTE)
        year = local_day(invoice.issued_at).year
        self.assertNotEqual(fee_invoice_credit_series(year), fee_invoice_series(year))
        self.assertTrue(
            res.data["number"].startswith(f"إشعار-أتعاب-{year}-"), res.data["number"],
        )
        self.assertEqual(
            res.data["number"],
            fee_invoice_number(fee_invoice_credit_series(year), 1),
        )
        self.assertEqual(res.data["related_invoice"], invoice.pk)
        # والسلسلةُ الرئيسية لم تُستهلك بإشعارٍ دائن.
        fee_invoices_row = FeeInvoice.objects.get(pk=invoice.pk)
        self.assertTrue(
            fee_invoices_row.number.startswith(f"أتعاب-{year}-"),
            fee_invoices_row.number,
        )
        self.assertFalse(fee_invoices_row.number.startswith("إشعار-"))

    def test_the_supplementary_stays_on_the_main_series(self):
        invoice = self.make_invoice()
        res = self.client.post(
            f"{INVOICES}{invoice.pk}/supplementary/",
            {"amount": "100.00", "reason": "خدمةٌ نُسيت"},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["kind"], FEE_INVOICE_KIND_SUPPLEMENTARY)
        self.assertEqual(
            res.data["number"],
            fee_invoice_number(fee_invoice_series(invoice.issued_at.year), 2),
        )


class TaxLineTest(FeeInvoiceTestCase):
    """سطرُ الضريبة يتبع إعداد «المكتب مشتغل مرخّص» — ويغيب كاملاً حين يُطفأ."""

    def test_the_line_shows_when_the_office_is_a_licensed_dealer(self):
        """السطرُ **بمبلغه ونسبته** لا بوجود كلمةٍ ما.

        **وكان لا يستطيع السقوط**: `"160"` توجد في الإجمالي `1,160`، و`"16"`
        في `16px` من CSS، فتمرّ التأكيداتُ ولو كان مبلغُ سطر الضريبة نفسِه خطأً.
        الفحصُ الآن على صفّ السطر كما يُصيَّر.
        """
        html = self.page_of(self.make_invoice(amount="1000.00"))

        self.assertIn(
            '<span>قيمة الضريبة (16%)</span><span class="num">160</span>', html,
        )
        self.assertIn("قيمة الضريبة بالحروف: مئة وستون", html)

    def test_the_line_disappears_entirely_when_the_office_is_not_licensed(self):
        self.set_setting("office_licensed_dealer", False)

        invoice = self.make_invoice(amount="1000.00")
        html = self.page_of(invoice)

        self.assertEqual(decimal_of(invoice.tax_total), Decimal("0.00"))
        self.assertEqual(decimal_of(invoice.total), Decimal("1000.00"))
        self.assertEqual(decimal_of(invoice.tax_percent), Decimal("0.00"))
        self.assertNotIn("قيمة الضريبة", html)
        self.assertNotIn("الإجمالي قبل الضريبة", html)
        # والنفيُ ثابتٌ في الحالين — إطفاءُ الترخيص لا يُخرج ورقةً تدّعي الرسمية.
        self.assertEqual(html.count(NOT_TAX_PS), PS_NOT_TAX_COUNT)

    def test_the_registration_number_is_not_what_makes_the_office_licensed(self):
        """عوسيك بطور يحمل رقماً وهو غير مرخّص — فلا سطرَ ضريبة (#266)."""
        self.set_setting("office_licensed_dealer", False)
        # الرقمُ باقٍ في الترويسة (الحقلُ الأوّل)، والضريبةُ لا تُحصَّل.
        self.assertEqual(
            self.tenant.settings.licensed_dealer_no, "512345678",
        )

        invoice = self.make_invoice(amount="500.00")

        self.assertEqual(decimal_of(invoice.tax_total), Decimal("0.00"))
        self.assertEqual(decimal_of(invoice.total), Decimal("500.00"))

    def test_the_rate_and_the_system_are_snapshots_not_live_reads(self):
        """تغييرُ نسبة الشركة أو نظامها بعد الإصدار لا يعيد كتابة ورقةٍ خرجت."""
        invoice = self.make_invoice(amount="1000.00")
        self.set_setting("tax_system", "IL")
        self.settings_row.default_vat_rate = Decimal("18.00")
        self.settings_row.save(update_fields=["default_vat_rate"])

        fresh = self.card_of(invoice)
        html = self.page_of(fresh)

        self.assertEqual(fresh.tax_system, "PS")
        self.assertEqual(decimal_of(fresh.tax_percent), Decimal("16.00"))
        self.assertEqual(decimal_of(fresh.tax_total), Decimal("160.00"))
        self.assertIn("فاتورة أتعاب", html)
        self.assertEqual(html.count(COPY_ORIGINAL), 1)
        self.assertEqual(html.count(COPY_DUPLICATE), 1)


class TitleTest(FeeInvoiceTestCase):
    """عنوانُ الورقة: إعدادُ المكتب، وإلا الافتراضيّ بحسب نظام المُصدِر."""

    def test_the_default_follows_the_office_tax_system(self):
        ps_invoice = self.make_invoice(name="زبون فلسطينيّ")
        self.set_setting("tax_system", "IL")
        il_invoice = self.make_invoice(name="زبون إسرائيليّ")

        self.assertEqual(ps_invoice.title, "فاتورة أتعاب")
        self.assertEqual(il_invoice.title, "חשבון עסקה")
        self.assertEqual(il_invoice.tax_system, "IL")

    def test_the_office_may_set_its_own_title(self):
        self.set_setting("fee_invoice_title", "فاتورة خدمات محاسبية")

        invoice = self.make_invoice()

        self.assertEqual(invoice.title, "فاتورة خدمات محاسبية")
        self.assertIn("فاتورة خدمات محاسبية", self.page_of(invoice))

    def test_the_credit_note_has_its_own_title_not_the_invoice_title(self):
        invoice = self.make_invoice()
        res = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "100.00", "reason": "خصم"},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["title"], "إشعار دائن أتعاب")
        note = FeeInvoice.objects.get(pk=res.data["id"])
        self.assertIn("إشعار دائن أتعاب", self.page_of(note))


class ShapeTest(FeeInvoiceTestCase):
    """الحقولُ القانونية بترتيبها — لا ترتيبَ آخر يقبله اختبارٌ آخر."""

    def test_palestine_prints_its_fields_in_order_and_two_copies(self):
        html = self.page_of(self.make_invoice())
        # **بعد أوّل `fi-sheet`**: عنوانُ الصفحة `<title>` في الرأس يحمل العنوان
        # نفسه، وترتيبُ الحقول يُقاس على الورقة لا على وسوم الرأس.
        body = html[html.index('class="sheet fi-sheet"'):]
        head = body[:body.index('class="fi-title"')]

        # (1) الترويسة: عبارةُ «الأصل» ورقمُ تسجيل المشتغل — قبل العنوان.
        self.assertIn(COPY_ORIGINAL, head)
        self.assertIn("512345678", head)

        positions = [body.index(marker) for marker in PS_ORDER]
        self.assertEqual(positions, sorted(positions), "الحقولُ خرجت بغير ترتيبها")
        self.assertEqual(html.count(COPY_ORIGINAL), 1)
        self.assertEqual(html.count(COPY_DUPLICATE), 1)
        self.assertLess(html.index(COPY_ORIGINAL), html.index(COPY_DUPLICATE))

    def test_no_template_comment_prints_on_the_customer_sheet(self):
        """تعليقُ القالب لا يُطبع حرفاً — و`{# … #}` متعدّدُ الأسطر يُخرج نصَّه.

        تعليقُ Django ذو السطر الواحد وحده يُقلَّم؛ فتعليقٌ على سطرين يمرّ نصّاً
        على الورقة التي يقرؤها الزبون.
        """
        html = self.page_of(self.make_invoice())

        self.assertNotIn("{#", html)
        self.assertNotIn("#}", html)
        self.assertNotIn("المجموعَ ولا التوقيع", html)
        self.assertNotIn("تدّعي الرسمية", html)

    def test_the_negation_sits_under_the_title_in_every_copy(self):
        html = self.page_of(self.make_invoice())

        self.assertIn('class="fi-not-tax"', html)
        # نسختان: سطرُ نفيٍ تحت كلّ عنوان + التذييلُ + محتوى `@page`.
        self.assertEqual(html.count(NOT_TAX_PS), PS_NOT_TAX_COUNT)
        self.assertEqual(html.count('class="fi-not-tax"'), 2)

    def test_no_tax_invoice_word_ever_ships_without_its_negation(self):
        html = self.page_of(self.make_invoice())

        self.assertNotIn("فاتورة ضريبية", html.replace(NOT_TAX_PS, ""))

    def test_israel_prints_the_seven_section_9a_elements(self):
        self.set_setting("tax_system", "IL")
        html = self.page_of(self.make_invoice())
        body = html[html.index('class="sheet fi-sheet"'):]
        head = body[:body.index('class="fi-title"')]

        # هويةُ העוסק (الاسمُ والرقمُ والعنوان) في الترويسة قبل العنوان.
        self.assertIn(IL_HEADER_MARKER, head)
        positions = [body.index(marker) for marker in IL_MARKERS]
        self.assertEqual(positions, sorted(positions), "عناصرُ §9א بغير ترتيبها")
        self.assertIn("חשבון עסקה", html)
        self.assertEqual(html.count(NOT_TAX_IL), IL_NOT_TAX_COUNT)
        self.assertNotIn("חשבונית מס", html.replace(NOT_TAX_IL, ""))
        # ولا نسختين في إسرائيل ولا عنواناً عربياً لفاتورةٍ عبرية.
        self.assertNotIn("الأصل", html)
        self.assertNotIn("فاتورة أتعاب", html)

    def test_the_amount_in_words_is_arabic_and_pure(self):
        self.assertEqual(fee_invoices.amount_in_words(0), "صفر")
        self.assertEqual(fee_invoices.amount_in_words(160), "مئة وستون")
        self.assertEqual(fee_invoices.amount_in_words(116), "مئة وستة عشر")
        self.assertEqual(fee_invoices.amount_in_words(1160), "ألف ومئة وستون")
        self.assertIn("أغورة", fee_invoices.amount_in_words(Decimal("10.50")))


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
    """الإلغاءُ فعلٌ لا حذف، وبمستوى المعتمِد، وقبل الإرسال وحده."""

    def test_cancel_before_sending_marks_the_row_and_reopens_the_draft(self):
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
        # **والمسودّةُ تعود مسودّةً**: شهرٌ لا يُفاتر أبداً ليس تصحيحاً.
        draft = FeeDraft.objects.get(pk=invoice.source_draft_id)
        self.assertEqual(draft.status, FeeDraft.STATUS_DRAFT)
        self.assertIsNone(draft.approved_at)

    def test_a_cancelled_invoice_can_be_approved_again_with_a_new_number(self):
        invoice = self.make_invoice(name="زبون الإلغاء")
        self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        again = self.client.post(
            f"{DRAFTS}{invoice.source_draft_id}/approve/", {}, format="json",
            **self.headers(),
        )

        self.assertEqual(again.status_code, 200, again.content)
        series = fee_invoice_series(invoice.issued_at.year)
        live = FeeInvoice.objects.get(
            source_draft_id=invoice.source_draft_id, cancelled_at__isnull=True,
        )
        self.assertEqual(live.number, fee_invoice_number(series, 2))
        # والملغاةُ باقيةٌ أثراً في التاريخ.
        self.assertTrue(FeeInvoice.objects.filter(pk=invoice.pk).exists())
        self.assertEqual(
            FeeInvoice.objects.filter(source_draft_id=invoice.source_draft_id).count(), 2,
        )

    def test_cancel_after_the_message_was_sent_is_refused(self):
        invoice = self.make_invoice()
        create_share(self.tenant, invoice)
        issued_on, due_on = fee_invoices.reminder_period(invoice)
        ReminderLog.objects.create(
            tenant=self.tenant,
            client=invoice.client,
            reminder_type="balance",
            kind="sent",
            body="نصّ",
            period_start=issued_on,
            period_end=due_on,
            created_by=self.owner,
        )

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.cancelled_at)
        self.assertIn("أُرسلت", str(res.content, "utf-8"))

    def test_a_sibling_item_with_the_same_key_is_not_the_invoice_sent(self):
        """المفتاحُ (issued_on, due_on) مشتركٌ بين ورقتَي اليوم — **النوعُ يفصل**.

        إشعارٌ دائنٌ صدر في يوم الفاتورة نفسِه يشاركها المفتاح، فلو قِيس الإرسالُ
        بكلّ الأنواع المحسوبة لصار إرسالُ الإشعار مسوّغاً لرفض إلغاء الفاتورة —
        والعكس. يُقاس بنوع بند الورقة نفسه (`invoice_reminder_type`).

        ** وكان لا يستطيع السقوط**: يسجّل صفَّ *نوع الفاتورة نفسِه* بحالة تنحية،
        فيمرّ حتى لو حُذف فصلُ الأنواع من `invoice_was_sent`. أُعيد ليصنع الشقيقَ
        فعلاً — إشعارٌ دائنٌ صادرٌ (`sent`) بمفتاح الفاتورة نفسِه.
        """
        invoice = self.make_invoice()
        created = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "160.00", "reason": "خصم"},
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        note = FeeInvoice.objects.get(pk=created.data["id"])
        # الشقيقُ بمفتاح الفاتورة نفسه: تاريخُ الإصدار وحدَه يفصل الورقتين.
        self.assertEqual(
            fee_invoices.reminder_period(note),
            fee_invoices.reminder_period(invoice),
        )
        self.assertNotEqual(
            fee_invoices.invoice_reminder_type(note),
            fee_invoices.invoice_reminder_type(invoice),
        )
        # الشقيقُ الحيّ يمنع الإلغاء بسببٍ آخر (409، اختبارُه فوق) — يُلغى أوّلًا،
        # ثم تُسجَّل رسالتُه **صادرة**: إرسالُ بند الإشعار لا يُوقف إلغاء الفاتورة.
        with_note_cancelled = self.client.post(
            f"{INVOICES}{note.pk}/cancel/", {}, format="json", **self.headers(),
        )
        self.assertEqual(
            with_note_cancelled.status_code, 200, with_note_cancelled.content,
        )
        issued_on, due_on = fee_invoices.reminder_period(note)
        ReminderLog.objects.create(
            tenant=self.tenant,
            client=note.client,
            reminder_type=fee_invoices.invoice_reminder_type(note),
            kind="sent",
            body="نصّ",
            period_start=issued_on,
            period_end=due_on,
            created_by=self.owner,
        )

        self.assertIs(fee_invoices.invoice_was_sent(invoice), False)
        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)

    def test_a_live_credit_note_blocks_the_cancellation(self):
        """إلغاءُ فاتورةٍ صدر لها إشعارٌ دائنٌ حيّ **409 قبل أيّ كتابة**.

        تعارضٌ مع حالةٍ قائمة لا خطأُ مدخلات (400): الصفُّ والمسودّةُ وسطرُ
        الترقيم لا تُمَسّ، والإشعارُ يبقى حيّاً — وإلا صار الشهرُ ملغىً وإشعارُه
        الدائنُ حيّاً على ورقةٍ لم تصدر.
        """
        invoice = self.make_invoice()
        created = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "160.00", "reason": "خصم"},
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        year = local_day(invoice.issued_at).year
        sequence = FeeInvoiceSequence.objects.get(
            tenant=self.tenant, year=year,
            series=fee_invoice_series(year),
        )
        counter_before = sequence.last_number

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 409, res.content)
        body = res.content.decode("utf-8")
        self.assertIn(created.data["number"], body)
        self.assertIn("إشعار", body)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.cancelled_at)
        self.assertIsNone(
            FeeInvoice.objects.get(pk=created.data["id"]).cancelled_at,
        )
        draft = FeeDraft.objects.get(pk=invoice.source_draft_id)
        self.assertEqual(draft.status, FeeDraft.STATUS_APPROVED)
        sequence.refresh_from_db()
        self.assertEqual(sequence.last_number, counter_before)

    def test_the_invoice_is_cancellable_after_its_credit_note_is_cancelled(self):
        """الطريقُ ليس مسدوداً: إلغاءُ الإشعار الدائن يفتح إلغاء الأصل بعده."""
        invoice = self.make_invoice()
        created = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "160.00", "reason": "خصم"},
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        note = FeeInvoice.objects.get(pk=created.data["id"])
        cancelled_note = self.client.post(
            f"{INVOICES}{note.pk}/cancel/", {}, format="json", **self.headers(),
        )
        self.assertEqual(cancelled_note.status_code, 200, cancelled_note.content)

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)

    def test_cancel_after_the_link_was_viewed_is_refused(self):
        from docshare.models import DocumentShare

        invoice = self.make_invoice()
        share = create_share(self.tenant, invoice)
        DocumentShare.objects.filter(pk=share.pk).update(view_count=1)

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)

    def test_opening_ready_to_send_is_not_sending(self):
        """الرابطُ يُنشأ من مجرّد القراءة — فوجودُه وحده لا يمنع الإلغاء."""
        invoice = self.make_invoice()
        contact = Contact.objects.create(
            tenant=self.tenant, name="مدير الزبون", phone="0599000000", language="ar",
        )
        ClientContact.objects.create(
            tenant=self.tenant, client=invoice.client, contact=contact, is_primary=True,
        )
        services.set_client_setting(invoice.client, "rest_days", [])

        payload = services.ready_to_send_payload(
            self.tenant, user=self.owner, day=local_day(invoice.issued_at),
        )
        self.assertTrue(payload["messages"])
        self.assertTrue(invoice_urls_created(self.tenant, invoice))

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)

    def test_the_accountant_may_not_cancel(self):
        """الإلغاءُ بمستوى المعتمِد: دورٌ لا مفتاح."""
        invoice = self.make_invoice(
            name="زبون المحاسب", responsible=self.accountant_user,
        )
        self.client.force_authenticate(user=self.accountant_user)

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 403, res.content)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.cancelled_at)

    def test_a_cancelled_invoice_cannot_be_cancelled_twice(self):
        invoice = self.make_invoice()
        self.client.post(f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers())

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)


def invoice_urls_created(tenant, invoice) -> bool:
    return bool(fee_invoices.live_invoice_url(invoice))


class CreditNoteRulesTest(FeeInvoiceTestCase):
    """الإشعارُ الدائن: سقفٌ **تراكميّ**، وسببٌ غيرُ فارغ."""

    def test_two_credit_notes_may_not_exceed_the_invoice_in_total(self):
        invoice = self.make_invoice(amount="1000.00")  # 1160 إجمالاً

        first = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "1000.00", "reason": "خصم أول"},
            format="json", **self.headers(),
        )
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "200.00", "reason": "خصم ثانٍ"},
            format="json", **self.headers(),
        )
        self.assertEqual(second.status_code, 400, second.content)
        self.assertEqual(
            FeeInvoice.objects.filter(kind=FEE_INVOICE_KIND_CREDIT_NOTE).count(), 1,
        )

        rest = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "160.00", "reason": "الباقي"},
            format="json", **self.headers(),
        )
        self.assertEqual(rest.status_code, 201, rest.content)

    def test_the_remaining_cap_is_exposed_for_the_screen(self):
        invoice = self.make_invoice(amount="1000.00")
        self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "160.00", "reason": "خصم"},
            format="json", **self.headers(),
        )

        detail = self.client.get(f"{INVOICES}{invoice.pk}/", **self.headers())

        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(
            decimal_of(detail.data["credit_note_remaining"]), Decimal("1000.00"),
        )

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

    def test_the_supplementary_is_not_capped_by_the_original(self):
        """النقصُ قد يتجاوز إجماليَ الأصل — خدمةٌ نُسيت كلُّها."""
        invoice = self.make_invoice(amount="1000.00")

        res = self.client.post(
            f"{INVOICES}{invoice.pk}/supplementary/",
            {"amount": "5000.00", "reason": "خدمةٌ نُسيت"},
            format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(decimal_of(res.data["total"]), Decimal("5000.00"))


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
        share = create_share(self.tenant, invoice)
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
    """رسالةُ الفاتورة: تظهر من **يوم الإصدار**، واستحقاقُها بعد سبعة أيام، ورابطُها."""

    def ready_contact(self, client, *, types=None):
        contact = Contact.objects.create(
            tenant=self.tenant, name="مدير الزبون", phone="0599000000", language="ar",
        )
        if types is not None:
            contact.consent_types = list(types)
            contact.save(update_fields=["consent_types"])
        ClientContact.objects.create(
            tenant=self.tenant, client=client, contact=contact, is_primary=True,
        )
        #: لا يومَ راحةٍ في الاختبار: اليومُ المحسوب معلوم، والحاجزُ له اختبارُه.
        services.set_client_setting(client, "rest_days", [])
        return contact

    def items_of(self, day):
        payload = services.ready_to_send_payload(
            self.tenant, user=self.owner, day=day,
        )
        return [item for message in payload["messages"] for item in message["items"]]

    def test_the_invoice_is_offered_from_its_issue_day_with_a_seven_day_due(self):
        invoice = self.make_invoice(amount="1000.00")
        self.ready_contact(invoice.client)
        issued_on = local_day(invoice.issued_at)
        due_on = issued_on + datetime.timedelta(days=7)

        items = self.items_of(issued_on)

        self.assertEqual(len(items), 1, items)
        item = items[0]
        self.assertEqual(item["reminder_type"], "balance")
        self.assertEqual(item["client_id"], invoice.client_id)
        self.assertEqual(item["due_date"], due_on.isoformat())
        self.assertEqual(item["period_start"], issued_on.isoformat())
        self.assertEqual(item["period_end"], due_on.isoformat())
        self.assertEqual(item["invoice"]["number"], invoice.number)
        self.assertEqual(decimal_of(item["invoice"]["total"]), Decimal("1160.00"))
        self.assertIn("/s/", item["invoice"]["url"])

    def test_the_credit_note_is_a_non_demanding_item(self):
        invoice = self.make_invoice(amount="1000.00")
        self.ready_contact(invoice.client)
        created = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "160.00", "reason": "خصم"},
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        note = FeeInvoice.objects.get(pk=created.data["id"])

        items = self.items_of(local_day(note.issued_at))

        credit_items = [
            item for item in items
            if item["invoice"] and item["invoice"]["kind"] == FEE_INVOICE_KIND_CREDIT_NOTE
        ]
        self.assertEqual(len(credit_items), 1, items)
        # **غيرُ مطالِب**: نوعُ «الأوراق» لا «اللي عليه»، ومبلغُه نصيبُ الإشعار.
        self.assertEqual(credit_items[0]["reminder_type"], "documents")
        self.assertEqual(
            decimal_of(credit_items[0]["invoice"]["total"]), Decimal("160.00"),
        )
        self.assertIn("/s/", credit_items[0]["invoice"]["url"])
        self.assertIn(
            "إشعار دائن أتعاب", credit_items[0]["invoice"]["title"],
        )

    def test_the_message_names_the_draft_month_not_the_issue_month(self):
        """شهرُ الرسالة من **المسودّة** لا من يوم الإصدار (#282/أ٢/١).

        نصُّ النوع يقول «على حساب {period}»، والورقةُ تخصّ شهرَ مسودّتها. أخذُ
        الفترة من يوم الإصدار يذكر شهراً لا تخصّه الورقة: مسودّةٌ لشهرٍ قادم
        تُصدر الآن فتُقرأ «شهر اليوم».
        """
        # شهرٌ **غيرُ الشهر الجاري** بيقين: أوّلُ الشهر بعد شهرين.
        draft_day = (
            timezone.localdate().replace(day=1) + datetime.timedelta(days=62)
        ).replace(day=1)
        invoice = self.make_invoice(day=draft_day)
        self.ready_contact(invoice.client)

        payload = services.ready_to_send_payload(
            self.tenant, user=self.owner, day=timezone.localdate(),
        )
        body = "\n\n".join(message["body"] for message in payload["messages"])
        draft_label = deadlines.period_label(
            draft_day,
            deadlines.month_start_after(draft_day, 1) - datetime.timedelta(days=1),
        )
        issued_on, due_on = fee_invoices.reminder_period(invoice)

        self.assertIn(draft_label, body)
        self.assertNotIn(deadlines.period_label(issued_on, due_on), body)
        self.assertEqual(
            [
                item["period_label"]
                for message in payload["messages"]
                for item in message["items"]
            ],
            [draft_label],
        )

    def test_the_credit_note_message_text_describes_a_credit_note_of_its_original(self):
        """نصُّ الإشعار يصف **دائناً** ويسمّي الأصل — لا فاتورةً مطلوبة.

        نصُّ الفاتورة يقول «المبلغ: … — الاستحقاق: …»، وهو على إشعارٍ دائنٍ
        يقرأ مطالبةً. الإشعارُ يقول «لصالحك» و«عن الفاتورة <رقم الأصل>».
        """
        invoice = self.make_invoice(amount="1000.00")
        self.ready_contact(invoice.client)
        created = self.client.post(
            f"{INVOICES}{invoice.pk}/credit-note/",
            {"amount": "160.00", "reason": "خصم اتفاق"},
            format="json", **self.headers(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        note = FeeInvoice.objects.get(pk=created.data["id"])

        payload = services.ready_to_send_payload(
            self.tenant, user=self.owner, day=local_day(note.issued_at),
        )
        body = "\n\n".join(message["body"] for message in payload["messages"])

        self.assertIn(f"{note.title} {note.number}", body)
        self.assertIn(f"عن الفاتورة {invoice.number}", body)
        self.assertIn(f"المبلغ: {note.total:.2f} — لصالحك", body)
        self.assertNotIn(
            f"{note.title} {note.number}\nالمبلغ: {note.total:.2f} — الاستحقاق:",
            body,
        )

    def test_the_cancelled_invoice_is_not_offered(self):
        invoice = self.make_invoice()
        self.ready_contact(invoice.client)
        self.client.post(f"{INVOICES}{invoice.pk}/cancel/", {}, format="json", **self.headers())

        self.assertEqual(self.items_of(local_day(invoice.issued_at)), [])

    def test_the_office_may_turn_the_invoice_item_type_off(self):
        invoice = self.make_invoice()
        self.ready_contact(invoice.client)
        services.set_office_setting(self.tenant, "reminder_types_enabled", ["documents"])

        self.assertEqual(self.items_of(local_day(invoice.issued_at)), [])
