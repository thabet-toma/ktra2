"""مستخرجاتُ دفتر الزبون — الجزء (ب-١) من #288: Excel، وورقةُ طباعة، ورابطُ مشاركة.

**ما يثبّته هذا الملفّ:**
- **xlsx حقيقيٌّ لا نصٌّ بامتداد**: يُفتح بـ`openpyxl`، والأرقامُ فيه **أرقامٌ**
  بخانتين عشريتين (لا `"300.00"` نصّاً)، والعلامةُ المائيةُ واسمُ الزبون والفترة
  على صفوفه العليا.
- **الدفترُ كاملاً**: مصنَّفٌ فيه ورقةٌ لكل تقريرٍ متاحٍ لنوع الدفتر، **وكشفُ
  حسابٍ لكل حسابٍ له حركة** — وورقةُ طباعةٍ واحدةٌ صفيحةٌ لكل تقريرٍ بفاصل صفحات.
- **ورقةُ الطباعة**: HTMLٌ مصيَّرٌ من الخادم يحمل «نسخة عمل» واسمَ الزبون والفترة
  وقيمَ التقرير — يُقاس **نصُّ المُخرَج** لا وجودُ وسمِ قالب.
- **رابط المشاركة**: يُنشأ صفُّ `ClientBookReport` ونوعُ مستندٍ `client_book_report`،
  ويُفتح الرابطُ العامُّ فيحمّل الحمولة نفسها — **ولا يُنشئه عضوٌ لا يرى المبالغ**
  (403، والصفحةُ العامة بلا قناع) ولا يقرؤه من سطح الإدارة.
- **إعدادُ «رابط PDF للتقارير»**: مطفأً يردّ `share` 400 برسالةٍ واضحة، ويبقى
  التصديرُ المباشر (Excel والطباعة) عاملاً.
- **العزل**: دفترُ مكتبٍ آخر **404** في كل نقطة.
- **نوعٌ غيرُ متاحٍ لنوع الدفتر 400**، و**ميزانٌ لا يتوازن يبقى 409**.
- **القناعُ يسري على الملفّ والورق**: عضوٌ بلا `office.amounts.view` لا يجد رقماً
  في xlsx ولا في ورقة الطباعة.
- **الدفترُ بعد إنهاء الزبون**: لا كتابةَ فيه (400) والقراءةُ والتصديرُ يعملان.
- **بندُ رابط التقرير في «جاهز للإرسال»** (#288/هـ): يظهر بعد إنشاء الرابط
  ويغيب قبله، ولا يُعاد بعد إرساله، ولا رابطَ فيه لمن لا يرى المبالغ.

كلُّ نقطةٍ تُقرأ بالـAPI كما تقرؤها الواجهة: `client-books/<client_id>/…`.
"""
import datetime
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import load_workbook

from accounting_office import services
from accounting_office.book_reports import WATERMARK
from accounting_office.models import (
    BOOK_KIND_DOUBLE,
    BOOK_KIND_SIMPLE,
    ClientBookReport,
    ClientContact,
    Contact,
    ReminderLog,
)
from accounting_office.tests.test_book_reports import (
    BookReportsTestCase,
    THIS_YEAR,
    reports_url,
)
from accounting_office.tests.test_client_books import make_client
from docshare.models import DOC_CLIENT_BOOK_REPORT, DocumentShare

BASE = "/api/accounting-office/"
BOOKS = f"{BASE}client-books/"
CLIENTS = f"{BASE}clients/"

#: الفترةُ المطلوبة في الاختبارات — داخل السنة الجارية، فحركاتُ `setUp` داخلها.
PERIOD_FROM = datetime.date(THIS_YEAR, 1, 1)
PERIOD_TO = datetime.date(THIS_YEAR, 12, 31)
DAY = datetime.date(THIS_YEAR, 5, 12)


def export_url(client, kind=None):
    """مستخرجُ تقريرٍ واحد (`…/reports/<kind>/export.xlsx`) أو الدفترِ كاملاً."""
    root = f"{BOOKS}{client.pk}/"
    return f"{root}export.xlsx" if kind is None else f"{root}reports/{kind}/export.xlsx"


def print_url(client, kind):
    return f"{BOOKS}{client.pk}/reports/{kind}/print/"


def whole_print_url(client):
    """ورقةُ الدفتر كاملاً للطباعة (#288/هـ) — كلُّ تقريرٍ صفيحةٌ بفاصل صفحات."""
    return f"{BOOKS}{client.pk}/print/"


def share_url(client, kind):
    return f"{BOOKS}{client.pk}/reports/{kind}/share/"


def period_params():
    return {"from": PERIOD_FROM.isoformat(), "to": PERIOD_TO.isoformat()}


def sheet_texts(sheet):
    """كلُّ نصٍّ على الورقة — للبحث عن العلامة المائية والاسم في المُخرَج."""
    return [
        cell.value
        for row in sheet.iter_rows()
        for cell in row
        if isinstance(cell.value, str)
    ]


def sheet_numbers(sheet):
    """كلُّ خليّةٍ رقميّةٍ على الورقة — لا نصوصٌ تشبه الأرقام."""
    return [
        cell
        for row in sheet.iter_rows()
        for cell in row
        if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
    ]


class SimpleBookOutputsTest(BookReportsTestCase):
    """دفترٌ بسيط: قبضٌ نقديٌّ 300 ودفعٌ نقديٌّ 120 — كلُّ مستخرجٍ يُقاس عليه."""

    def setUp(self):
        super().setUp()
        self.create_book(
            self.mine, kind=BOOK_KIND_SIMPLE,
            opened_on=datetime.date(THIS_YEAR - 1, 1, 5),
        )
        self.add_entry(
            self.mine, entry_date=DAY,
            lines=[{"account_code": "1100", "debit": "300.00"}],
        )
        self.add_entry(
            self.mine, entry_date=DAY, kind="expense",
            lines=[{"account_code": "1100", "credit": "120.00"}],
        )

    def export(self, kind=None, *, params=None, expect=200, tenant=None, user=None):
        if user is not None:
            self.as_user(user)
        res = self.client.get(
            export_url(self.mine, kind), params or period_params(),
            **self.headers(tenant=tenant),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res

    # ── Excel ─────────────────────────────────────────────────────────────
    def test_the_report_xlsx_opens_with_numbers_and_the_watermark(self):
        """الملفُّ يُفتح بـ`openpyxl`، والأرقامُ أرقامٌ بخانتين، والعلامةُ عليه.

        والفحصُ يقف على **نوع الخليّة** لا على قيمتها وحدها: كاتبٌ يضع `"300.00"`
        نصّاً يمرّ من اختبارٍ يبحث عن النصّ، ولا يمرّ من هنا.
        """
        res = self.export("cash")

        self.assertIn("spreadsheetml", res["Content-Type"])
        self.assertIn("attachment", res["Content-Disposition"])

        sheet = load_workbook(BytesIO(res.content)).active
        texts = sheet_texts(sheet)
        self.assertIn(WATERMARK, texts)
        self.assertIn("زبوني", texts)
        self.assertIn("قبض ودفع", texts)
        self.assertIn(PERIOD_FROM.isoformat(), texts)
        self.assertIn(PERIOD_TO.isoformat(), texts)
        # ولا عمودَ نصوصٍ بدل الأرقام.
        self.assertNotIn("300.00", texts)
        self.assertNotIn("120.00", texts)

        money_cells = [cell for cell in sheet_numbers(sheet) if cell.value in (300, 120)]
        # صفُّ الحركة ومجاميعُ القبض/الدفع معاً — والعددُ لا يُثبَّت: الإضافةُ
        # المرغوبة (صفُّ مجموعٍ ثالث) لا يجوز أن تُسقِط الاختبار.
        self.assertGreaterEqual(len(money_cells), 2)
        for cell in money_cells:
            self.assertEqual(cell.number_format, "#,##0.00")

    def test_the_whole_book_xlsx_has_a_sheet_per_available_report(self):
        res = self.export()

        book = load_workbook(BytesIO(res.content))
        self.assertEqual(
            book.sheetnames,
            ["قبض ودفع", "إيرادات ومصاريف", "ذمم", "ض.ق.م للفترة"],
        )
        for sheet in book.worksheets:
            self.assertIn(WATERMARK, sheet_texts(sheet))

    def test_the_whole_book_xlsx_carries_the_same_numbers_as_the_reports(self):
        res = self.export()

        book = load_workbook(BytesIO(res.content))
        cash = book["قبض ودفع"]
        self.assertTrue(
            any(cell.value == 300 for cell in sheet_numbers(cash)),
            "مستخرجُ الدفتر لا يحمل قبضَ 300 من حمولة التقرير",
        )

    def test_a_masked_member_gets_no_amounts_in_the_file(self):
        """القناعُ يسري على الملفّ كما يسري على الردّ — لا رقمَ لعضوٍ بلا صلاحية."""
        res = self.export("cash", user=self.accountant)

        sheet = load_workbook(BytesIO(res.content)).active
        self.assertFalse(
            [cell for cell in sheet_numbers(sheet) if cell.value in (300, 120)],
            "مبلغٌ خرج في ملفٍّ لعضوٍ لا يرى المبالغ",
        )
        self.assertIn(WATERMARK, sheet_texts(sheet))

    # ── ورقة الطباعة ──────────────────────────────────────────────────────
    def test_the_print_page_is_a_rendered_sheet_with_watermark_and_period(self):
        """نصُّ المُخرَج لا وجودُ `{%`: الصفحةُ تُقاس بما يراه من يطبعها."""
        res = self.client.get(
            print_url(self.mine, "cash"), period_params(), **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn("text/html", res["Content-Type"])
        html = res.content.decode("utf-8")
        self.assertIn(WATERMARK, html)
        self.assertIn("زبوني", html)
        self.assertIn("قبض ودفع", html)
        self.assertIn(PERIOD_FROM.isoformat(), html)
        self.assertIn(PERIOD_TO.isoformat(), html)
        self.assertIn("فاتورة بيع", html)
        self.assertIn(">300<", html)
        self.assertNotIn("{%", html)
        self.assertNotIn("{{", html)
        # والطباعةُ من المتصفح لا مكتبة PDF: زرُّ الطباعة على الصفحة.
        self.assertIn("window.print()", html)

    def test_the_single_report_print_shares_the_sheet_but_not_the_page_break(self):
        """صفحةُ تقريرٍ واحد تقرأ القالبَ والأنماطَ المشتركة — وبلا فاصلِ صفحات.

        فاصلُ الصفحات يخصّ الدفترَ كاملاً: ورقةُ تقريرٍ واحد بفاصلٍ تُخرج صفحةً
        بيضاءَ في الطباعة. والأنماطُ المشتركة (`_client_book_report_style.html`)
        يجب أن تصل هنا أيضاً — وإلا خرجت الصفحةُ بلا تنسيق.
        """
        html = self.client.get(
            print_url(self.mine, "cash"), period_params(), **self.headers(),
        ).content.decode("utf-8")

        self.assertIn(".cb-table{width:100%", html)
        self.assertNotIn(".cb-sheet{", html)

    # ── رابط المشاركة ─────────────────────────────────────────────────────
    def share(self, kind="cash", *, expect=201, user=None, data=None):
        if user is not None:
            self.as_user(user)
        res = self.client.post(
            share_url(self.mine, kind), data if data is not None else period_params(),
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res

    def test_the_share_link_opens_and_carries_the_payload(self):
        res = self.share()

        self.assertTrue(res.data["url"])
        self.assertTrue(res.data["expires_at"])
        report = ClientBookReport.objects.get(client_book__client=self.mine)
        self.assertEqual(report.kind, "cash")
        self.assertEqual(report.period_from, PERIOD_FROM)
        self.assertEqual(report.period_to, PERIOD_TO)
        self.assertEqual(report.tenant_id, self.tenant.pk)
        self.assertEqual(report.created_by_id, self.owner.pk)
        self.assertTrue(
            DocumentShare.objects.filter(
                tenant=self.tenant, doc_type=DOC_CLIENT_BOOK_REPORT,
                doc_id=report.pk,
            ).exists(),
        )

        token = res.data["url"].rsplit("/", 1)[-1]
        page = self.client.get(f"/s/{token}")

        self.assertEqual(page.status_code, 200, page.content)
        html = page.content.decode("utf-8")
        self.assertIn(WATERMARK, html)
        self.assertIn("زبوني", html)
        self.assertIn("قبض ودفع", html)
        self.assertIn(PERIOD_FROM.isoformat(), html)
        self.assertIn(">300<", html)

    def test_sharing_the_same_period_twice_keeps_one_report_and_one_link(self):
        first = self.share()
        second = self.share()

        self.assertEqual(ClientBookReport.objects.count(), 1)
        self.assertEqual(first.data["url"], second.data["url"])

    def test_the_share_endpoint_is_refused_when_the_setting_is_off(self):
        """الإعدادُ المطفأ يمنع الرابط وحدَه — التصديرُ المباشر يبقى عاملاً."""
        services.set_office_setting(self.tenant, "office_report_pdf_link", False)

        res = self.share(expect=400)

        self.assertIn("رابط PDF للتقارير", str(res.data["detail"]))
        self.assertFalse(ClientBookReport.objects.exists())
        self.assertEqual(self.export("cash").status_code, 200)
        self.assertEqual(
            self.client.get(
                print_url(self.mine, "cash"), period_params(), **self.headers(),
            ).status_code,
            200,
        )

    def test_the_share_endpoint_needs_the_write_key(self):
        """إنشاءُ رابطٍ عامٍّ فعلُ كتابة — لا يملكه عضوُ قراءة (نمط #285).

        **والمحاسبُ يملكه**: `_ACCOUNTANT` يحمل `office.clients.write` وحده من
        مفاتيح المكتب (`core/access.py`)، فهو يوزّع مستخرجَ زبونِه. أمّا المستعرضُ
        فلا — هو من يقرأ ولا يكتب.
        """
        mine = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون المستعرض", responsible=self.viewer,
        )
        self.create_book(mine, kind=BOOK_KIND_SIMPLE)
        self.as_user(self.viewer)

        res = self.client.post(
            share_url(mine, "cash"), period_params(), format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 403, res.content)
        self.assertFalse(ClientBookReport.objects.exists())

    def test_a_masked_member_cannot_create_a_public_link(self):
        """عضوٌ بلا `office.amounts.view` لا يُنشئ رابطاً — **الورقةُ بلا قناع**.

        الصفحةُ العامة تُبنى بـ`user=None` (ورقةُ زبونٍ لا شاشةُ موظف)، فمن أنشأ
        الرابطَ يقرأ كلَّ رقمٍ حُجِب عنه: الملفُّ والطباعةُ يمرّان بالقناع، والرابطُ
        كان البابَ الثالث. والمنعُ **403** لا 400 (صلاحيةٌ ناقصة لا حمولةٌ فاسدة)،
        ولا يُنشَأ صفُّ تقريرٍ ولا صفُّ مشاركة — لا رابطَ يُبطل بعدها.
        """
        res = self.share(user=self.accountant, expect=403)

        self.assertIn("المبالغ", res.content.decode("utf-8"))
        self.assertFalse(ClientBookReport.objects.exists())
        self.assertFalse(
            DocumentShare.objects.filter(
                doc_type=DOC_CLIENT_BOOK_REPORT,
            ).exists(),
        )

    # ── الدفترُ كاملاً للطباعة ────────────────────────────────────────────
    def test_the_whole_book_prints_one_paged_sheet_per_available_report(self):
        """ورقةُ «كل التقارير»: صفيحةٌ لكل تقريرٍ بفاصل صفحات، والعلامةُ والشعارُ.

        و«PDF» من حوار الطباعة في المتصفح (نمط `utils/printReport.ts`)، فلا
        مكتبةَ PDF على الخادم: الصفحةُ تُقاس بنصِّها وبتخطيطها لا بوجود وسم.
        """
        res = self.client.get(
            whole_print_url(self.mine), period_params(), **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn("text/html", res["Content-Type"])
        html = res.content.decode("utf-8")
        self.assertIn(WATERMARK, html)
        self.assertIn("زبوني", html)
        # الشعارُ ترويسةُ المنشأة على الورقة (بطاقةُ الشركة لا اسمٌ مخترَع).
        self.assertIn(self.tenant.CompanyName, html)
        for title in ("قبض ودفع", "إيرادات ومصاريف", "ذمم", "ض.ق.م للفترة"):
            with self.subTest(title=title):
                self.assertIn(title, html)
        # صفيحةٌ لكل تقريرٍ وبينها فاصلُ صفحاتٍ في الطباعة.
        self.assertEqual(html.count('class="sheet cb-sheet"'), 4)
        self.assertIn(".cb-sheet{page-break-after:always}", html)
        # والأرقامُ هي أرقامُ التقرير نفسِه.
        self.assertIn(">300<", html)
        self.assertNotIn("{%", html)

    def test_the_whole_book_print_respects_the_amounts_mask(self):
        """القناعُ يسري على ورقة الطباعة كالملفّ: لا رقمَ لعضوٍ لا يراه."""
        self.as_user(self.accountant)

        res = self.client.get(
            whole_print_url(self.mine), period_params(), **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        html = res.content.decode("utf-8")
        self.assertIn(WATERMARK, html)
        self.assertNotIn(">300<", html)
        self.assertNotIn(">120<", html)

    # ── شروطٌ عامّة ───────────────────────────────────────────────────────
    def test_a_stopped_service_refuses_writes_and_keeps_exporting(self):
        """«صدّر الدفتر كامل» بعد ترك الزبون (#288/ب-٢): قراءةٌ لا كتابة.

        الخدمةُ الموقوفة تُخرج الدفتر من «الحيّ» فلا إدخالَ ولا استيراد — والملفُّ
        يبقى: هو ما يُسلَّم للزبون عند فراقه.
        """
        service = self.mine.services.get(service__code="bookkeeping")
        service.ends_on = datetime.date(THIS_YEAR - 1, 1, 4)
        service.save(update_fields=["ends_on"])

        entry = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": DAY.isoformat(),
                "kind": "expense",
                "lines": [{"account_code": "1100", "credit": "5.00"}],
            },
            format="json",
            **self.headers(),
        )
        upload = self.client.post(
            f"{BOOKS}{self.mine.pk}/import/",
            {"file": SimpleUploadedFile("tree.xlsx", b"not an xlsx at all")},
            format="multipart",
            **self.headers(),
        )

        self.assertEqual(entry.status_code, 400, entry.content)
        self.assertIn("للقراءة فقط", str(entry.data))
        self.assertEqual(upload.status_code, 400, upload.content)
        self.assertIn("للقراءة فقط", str(upload.data))

        res = self.export()

        self.assertEqual(res.status_code, 200, res.content)
        book = load_workbook(BytesIO(res.content))
        self.assertEqual(book.sheetnames[-1], "ض.ق.م للفترة")
        self.assertIn(WATERMARK, sheet_texts(book.active))

    def test_ending_the_client_stops_the_writes_and_keeps_the_book_readable(self):
        """«أنهِ الزبون» يمنع الكتابة — **وخدمةُ مسك الدفاتر تبقى نشطة**.

        الحالةُ على `OfficeClient` وحدها هي ما يتغيّر (`services.end_office_client`)
        ولا يمسّ صفَّ الخدمة؛ فسؤالُ الخدمة وحدها كان يترك دفترَ زبونٍ منتهٍ
        قابلاً للكتابة إلى الأبد — يكتب فيه المحاسبُ بعد أن صُفّي الحساب وسُلّم
        للزبون نسختُه. والقراءةُ تبقى كاملةً: التقاريرُ والمستخرج.
        """
        ended = self.client.post(
            f"{CLIENTS}{self.mine.pk}/end/", {}, format="json", **self.headers(),
        )
        self.assertEqual(ended.status_code, 200, ended.content)
        self.assertTrue(
            self.mine.services.filter(service__code="bookkeeping").exists(),
            "أنهِ الزبون يجب ألّا يمسّ صفَّ خدمة مسك الدفاتر",
        )

        entry = self.client.post(
            f"{BOOKS}{self.mine.pk}/entries/",
            {
                "entry_date": DAY.isoformat(),
                "kind": "expense",
                "lines": [{"account_code": "1100", "credit": "5.00"}],
            },
            format="json",
            **self.headers(),
        )

        self.assertEqual(entry.status_code, 400, entry.content)
        self.assertIn("للقراءة فقط", str(entry.data))
        # والرسالةُ تسمّي السببَ الحقّ: الزبونُ منتهٍ — لا «خدمةٌ موقوفة» تُرسل
        # المحاسبَ إلى شاشة الخدمات.
        self.assertIn("منتهٍ", str(entry.data))
        listing = self.client.get(BOOKS, **self.headers())
        row = next(
            item for item in listing.data if item["client_id"] == self.mine.pk
        )
        self.assertFalse(row["writable"])

        # والدفترُ يبقى مقروءاً: تقريرٌ ومصنَّفٌ وطباعة.
        self.assertEqual(
            self.client.get(
                reports_url(self.mine, "cash"), {}, **self.headers(),
            ).status_code,
            200,
        )
        self.assertEqual(self.export("cash").status_code, 200)
        self.assertEqual(
            self.client.get(
                print_url(self.mine, "cash"), period_params(), **self.headers(),
            ).status_code,
            200,
        )

    def test_another_tenants_book_is_404_on_every_output(self):
        paths = (
            export_url(self.outside, "cash"),
            export_url(self.outside),
            print_url(self.outside, "cash"),
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.get(path, period_params(), **self.headers()).status_code,
                    404,
                )

        res = self.client.post(
            share_url(self.outside, "cash"), period_params(),
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 404, res.content)
        self.assertFalse(ClientBookReport.objects.exists())

    def test_a_report_that_the_book_kind_does_not_offer_is_400(self):
        for path in (
            export_url(self.mine, "trial_balance"),
            print_url(self.mine, "trial_balance"),
        ):
            with self.subTest(path=path):
                res = self.client.get(path, period_params(), **self.headers())
                self.assertEqual(res.status_code, 400, res.content)

        self.share("trial_balance", expect=400)

    def test_a_client_without_a_book_is_404(self):
        """زبونٌ بلا دفتر: لا مستخرجَ على لا شيء — 404 كمسار التقارير نفسِه."""
        bookless = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبون بلا دفتر", responsible=self.owner,
        )

        res = self.client.get(
            f"{BOOKS}{bookless.pk}/reports/cash/export.xlsx",
            period_params(), **self.headers(),
        )

        self.assertEqual(res.status_code, 404, res.content)


class DoubleBookOutputsTest(BookReportsTestCase):
    """دفترٌ مزدوجٌ متوازن — **كشفُ حسابٍ لكل حسابٍ له حركة** في الدفتر كاملاً.

    ورقةُ الملاحظة وحدها («كشفُ الحساب يحتاج تحديدَ حساب») كانت تُخرج المصنَّفَ
    ناقصاً: من صدّر دفترَه كاملاً لم يرَ حركاتِ حسابٍ واحداً فيه. والكشفُ الآن
    يُبنى **لكل حسابٍ له حركةٌ حيّة في الفترة**، ومن لا حركةَ له لا ورقةَ له
    (ورقةٌ بلا صفوف تُقرأ «لا بيانات» فتُوهم بخلل).
    """

    def setUp(self):
        super().setUp()
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)
        self.add_entry(
            self.mine, entry_date=DAY,
            lines=[
                {"account_code": "1100", "debit": "200.00"},
                {"account_code": "4100", "credit": "200.00"},
            ],
        )

    def whole_book(self):
        res = self.client.get(export_url(self.mine), period_params(), **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        return load_workbook(BytesIO(res.content))

    def test_the_whole_book_has_a_statement_sheet_per_account_with_movement(self):
        book = self.whole_book()

        self.assertIn("كشف حساب 1100", book.sheetnames)
        self.assertIn("كشف حساب 4100", book.sheetnames)
        self.assertNotIn("كشف حساب 1300", book.sheetnames)

        sheet = book["كشف حساب 1100"]
        self.assertIn(WATERMARK, sheet_texts(sheet))
        self.assertIn("زبوني", sheet_texts(sheet))
        self.assertTrue(any(cell.value == 200 for cell in sheet_numbers(sheet)))

    def test_the_whole_book_print_carries_the_statement_pages_too(self):
        res = self.client.get(
            whole_print_url(self.mine), period_params(), **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        html = res.content.decode("utf-8")

        self.assertIn("كشف حساب 1100", html)
        self.assertIn("كشف حساب 4100", html)
        self.assertNotIn("كشف حساب 1300", html)

    def test_the_statements_themselves_respect_the_amounts_mask(self):
        """كشوفُ الدفتر كاملاً تمرّ بالقناع — في الورق والملفّ معاً.

        **والتقريرُ على الكشف وحده**: الصفحةُ تحمل تقاريرَ أخرى مقنَّعةً كذلك،
        فاختبارٌ يقرأ الصفحة كلَّها يمرّ ولو أُسقط `user` من بناء الكشوف وحدها —
        وهذه هي الحالةُ التي يطلبها المنع (كشفُ حسابٍ لكل حساب).
        """
        self.as_user(self.accountant)

        res = self.client.get(
            whole_print_url(self.mine), period_params(), **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        html = res.content.decode("utf-8")
        self.assertIn("كشف حساب 1100", html)
        self.assertNotIn(">200<", html)

        file = self.client.get(
            export_url(self.mine), period_params(), **self.headers(),
        )
        self.assertEqual(file.status_code, 200, file.content)
        sheet = load_workbook(BytesIO(file.content))["كشف حساب 1100"]
        self.assertFalse(
            [cell for cell in sheet_numbers(sheet) if cell.value == 200],
            "مبلغُ حركةٍ خرج في كشف حسابٍ لعضوٍ لا يرى المبالغ",
        )
        self.assertIn(WATERMARK, sheet_texts(sheet))


class UnbalancedBookOutputsTest(BookReportsTestCase):
    """دفترٌ مزدوجٌ متوازن ثم مكسورٌ بقيدٍ مدسوس — 409 يبقى 409 في كل مستخرج."""

    def setUp(self):
        super().setUp()
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE)
        self.add_entry(
            self.mine, entry_date=DAY,
            lines=[
                {"account_code": "1100", "debit": "200.00"},
                {"account_code": "4100", "credit": "200.00"},
            ],
        )
        self.break_the_balance()

    def test_an_unbalanced_trial_balance_is_409_on_the_export(self):
        res = self.client.get(
            export_url(self.mine, "trial_balance"), period_params(), **self.headers(),
        )

        self.assertEqual(res.status_code, 409, res.content)
        self.assertIn("متوازن", str(res.data["detail"]))

    def test_an_unbalanced_trial_balance_is_409_on_the_print_and_the_share(self):
        res = self.client.get(
            print_url(self.mine, "trial_balance"), period_params(), **self.headers(),
        )
        self.assertEqual(res.status_code, 409, res.content)

        res = self.client.post(
            share_url(self.mine, "trial_balance"), period_params(),
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 409, res.content)
        self.assertFalse(ClientBookReport.objects.exists())


class BookReportReminderTest(BookReportsTestCase):
    """رابطُ التقرير يظهر في «جاهز للإرسال» — **بعد إنشائه لا قبله** (#288/هـ).

    الشاشةُ تقول «انسخه وأرسله للزبون» ولا سجلَّ يُذكّر به: رابطٌ يُنشأ اليوم
    ويُنسى بعد أسبوع. المولّدُ يقرأ صفوفَ `ClientBookReport` القائمة بنوع
    `documents`، فتمرّ في حواجز «جاهز للإرسال» نفسِها بلا محرّكٍ موازٍ.
    """

    def setUp(self):
        super().setUp()
        self.create_book(
            self.mine, kind=BOOK_KIND_SIMPLE,
            opened_on=datetime.date(THIS_YEAR - 1, 1, 5),
        )

    def share(self):
        res = self.client.post(
            share_url(self.mine, "cash"), period_params(),
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.data

    def ready_contact(self):
        """جهةٌ رئيسيةٌ للزبون بكل الأنواع والإذن، وبلا يوم راحةٍ يُحجب به الحساب."""
        contact = Contact.objects.create(
            tenant=self.tenant, name="مدير الزبون", phone="0599000000", language="ar",
        )
        ClientContact.objects.create(
            tenant=self.tenant, client=self.mine, contact=contact, is_primary=True,
        )
        services.set_client_setting(self.mine, "rest_days", [])
        return contact

    def items_of(self, day, *, user=None):
        payload = services.ready_to_send_payload(
            self.tenant, user=user or self.owner, day=day,
        )
        return [item for message in payload["messages"] for item in message["items"]]

    def report_items(self, day, *, user=None):
        return [
            item for item in self.items_of(day, user=user)
            if item.get("client_book_report") is not None
        ]

    def test_the_report_link_is_offered_only_after_it_exists(self):
        self.ready_contact()
        day = timezone.localdate()

        self.assertEqual(self.report_items(day), [])
        self.share()
        item = self.report_items(day)

        self.assertEqual(len(item), 1, item)
        self.assertEqual(item[0]["reminder_type"], "documents")
        self.assertEqual(item[0]["client_id"], self.mine.pk)
        self.assertIn("قبض ودفع", item[0]["period_label"])
        self.assertEqual(item[0]["client_book_report"]["kind"], "cash")
        self.assertIn("/s/", item[0]["client_book_report"]["url"])

    def test_the_report_item_is_not_a_demand_for_money(self):
        """نوعُه `documents` لا `balance` — ورقةٌ تُسلَّم لا مطالبةٌ بمبلغ."""
        self.ready_contact()
        self.share()

        item = self.report_items(timezone.localdate())[0]

        self.assertEqual(item["reminder_type"], "documents")
        # ولا مركَّبَ ماليٌّ على البند: لا فاتورةً ولا إشعاراً ولا قبضاً يُنطق رقماً.
        self.assertIsNone(item["invoice"])
        self.assertIsNone(item["notice"])
        self.assertIsNone(item["receipt"])

    def test_the_message_text_is_the_report_not_a_missing_papers_note(self):
        """نصُّ البند سطرُ الرابط وحده — لا نصُّ «أوراقٌ ناقصةٌ ننتظرها منك».

        نوعُه `documents` لِتُسلَّم الورقةُ لا لِتُطالَب، ونصُّ نوع الأوراق في
        القوالب يتحدّث عن **ما ننتظره من الزبون**؛ تقديمُه على رابط تقريرٍ كان
        يقول له «ناقصنا منك: ولا شي» ثم يعطيه رابطاً.
        """
        self.ready_contact()
        self.share()
        self.as_user(self.owner)

        payload = services.ready_to_send_payload(
            self.tenant, user=self.owner, day=timezone.localdate(),
        )
        body = "\n\n".join(message["body"] for message in payload["messages"])

        self.assertTrue(body.startswith("قبض ودفع"), body)
        self.assertIn("الرابط: ", body)
        # ونصُّ نوع الأوراق لا يُقدَّم على السطر: رمزُه `{missing_list}` لا يظهر
        # منطوقاً بقيمةٍ، ولا كلمةُ «ناقصنا» التي تصف مطالبةً من الزبون.
        self.assertNotIn("ناقصنا", body)
        self.assertNotIn("{", body)

    def test_a_masked_reader_sees_the_item_without_the_link(self):
        """من لا يرى المبالغ يصله البندُ بلا رابط: الصفحةُ العامة بلا قناع."""
        self.ready_contact()
        self.share()
        day = timezone.localdate()

        item = self.report_items(day, user=self.accountant)[0]

        self.assertEqual(item["client_book_report"]["kind"], "cash")
        self.assertEqual(item["client_book_report"]["url"], "")
        payload = services.ready_to_send_payload(
            self.tenant, user=self.accountant, day=day,
        )
        self.assertNotIn(
            "/s/", "\n\n".join(message["body"] for message in payload["messages"]),
        )

    def test_a_sent_link_stops_being_offered(self):
        """بندٌ أُرسل مرّةً لا يُعاد إرسالُه من نفسه — السقفُ واحدٌ كالإشعار الدائن."""
        self.ready_contact()
        self.share()
        day = timezone.localdate()
        report = ClientBookReport.objects.get()
        # البندُ ظاهرٌ ما دام لم يُرسل — وإلا مرّ الاختبار على مولّدٍ غائب.
        self.assertEqual(len(self.report_items(day)), 1)

        ReminderLog.objects.create(
            tenant=self.tenant,
            client=self.mine,
            reminder_type="documents",
            kind="sent",
            body="نصّ",
            period_start=report.period_from,
            period_end=report.period_to,
            created_by=self.owner,
        )

        self.assertEqual(self.report_items(day), [])

