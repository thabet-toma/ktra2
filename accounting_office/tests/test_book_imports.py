"""استيرادُ شجرة الدفتر وأرصدته من Excel — الجزء (ب-٢) من #288.

**ما يثبّته هذا الملفّ:**
- **الملفُّ المتوازن يُنتج الشجرةَ وحركةً افتتاحيةً واحدة**: صفٌّ لكل كود، وأرصدةٌ
  على بنود الحركة (الموجبُ مدينٌ والسالبُ دائن).
- **الملفُّ غيرُ المتوازن 400 برسالةٍ تسمّي الفرق** — لا صفرٌ مصطنع ولا كتابةُ شجرة.
- **الكودُ المكرَّر مرفوض**، و**صفٌّ فاسدٌ واحدٌ لا يُكتب معه شيء** (معاملةٌ واحدة):
  يُقاس ما في القاعدة لا الردُّ وحده.
- **القالبُ النموذجيّ**: ملفُّ xlsx فارغٌ بالترويسة الصحيحة، تنزّله الواجهةُ فيملؤه
  المكتب — والترويسةُ تُقرأ من الملفّ نفسه لا من نصٍّ في الاختبار.
- **الدفترُ المنتهي لا يستورد**: خدمةٌ موقوفة ⇒ 400 برسالةٍ مكتوبة.
- **الاستيرادُ بأرصدةٍ بدور المدير/صاحب المكتب** كالقيد اليدوي: الملفُّ يكتب رصيداً
  بيدٍ، ومن لا يملك الدور 403 — واستيرادُ شجرةٍ بلا أرصدةٍ يبقى لمن يملك الكتابة.
"""
import datetime
from decimal import Decimal
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import Sum
from openpyxl import Workbook, load_workbook

from accounting_office.models import (
    BOOK_KIND_DOUBLE,
    BOOK_KIND_SIMPLE,
    BookEntry,
    BookEntryLine,
    ClientBookAccount,
)
from accounting_office.tests.test_client_books import (
    THIS_YEAR,
    ClientBookTestCase,
    make_client,
)
from tenants.models import MemberPermission, UserCompanyMembership

BASE = "/api/accounting-office/"
BOOKS = f"{BASE}client-books/"

#: الترويسةُ المعروفة — **نفسُها في القالب وفي المُستورِد**، وترتيبُها حرّ.
HEADERS = ["الكود", "الاسم", "النوع", "الأب", "الرصيد"]

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def workbook_bytes(rows, headers=None):
    """مصنَّفٌ بترويسةٍ وصفوف — كما يملؤه المكتب بعد تنزيل القالب."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class BookImportTest(ClientBookTestCase):
    """دفترٌ مزدوجٌ فُتح السنة الماضية — الاستيرادُ يُقاس على شجرته القائمة."""

    OPENED = datetime.date(THIS_YEAR - 1, 1, 1)

    def setUp(self):
        super().setUp()
        self.create_book(self.mine, kind=BOOK_KIND_DOUBLE, opened_on=self.OPENED)

    def upload(
        self, rows, *, client=None, content=None, entry_date=None, expect=201,
        tenant=None,
    ):
        data = {
            "file": SimpleUploadedFile(
                "tree.xlsx",
                content if content is not None else workbook_bytes(rows),
                content_type=XLSX_TYPE,
            ),
        }
        if entry_date is not None:
            data["entry_date"] = entry_date.isoformat()
        res = self.client.post(
            f"{BOOKS}{(client or self.mine).pk}/import/", data, format="multipart",
            **self.headers(tenant=tenant),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res.data

    def grant(self, user, *keys):
        membership = UserCompanyMembership.objects.get(user=user, tenant=self.tenant)
        for key in keys:
            MemberPermission.objects.get_or_create(
                membership=membership, permission_key=key,
                defaults={"allowed": True},
            )

    def balanced_rows(self):
        """كودان جديدان تحت أبوين قائمين، ورصيدٌ يتقاصّ: 300 مديناً و−300 دائناً."""
        return [
            ["1310", "ذممٌ قديمة", "أصول", "1300", 300],
            ["2110", "موردون قدامى", "خصوم", "2100", -300],
        ]

    # ── الشجرة والأرصدة ───────────────────────────────────────────────────
    def test_a_balanced_file_creates_the_tree_and_one_opening_entry(self):
        payload = self.upload(self.balanced_rows(), entry_date=self.OPENED)

        self.assertEqual(payload["accounts_created"], 2)
        self.assertEqual(payload["accounts_updated"], 0)
        self.assertEqual(
            ClientBookAccount.objects.get(client=self.mine, code="1310").parent.code,
            "1300",
        )
        self.assertEqual(
            ClientBookAccount.objects.get(client=self.mine, code="2110").parent.code,
            "2100",
        )
        entry = BookEntry.objects.get(client=self.mine, kind="opening")
        self.assertEqual(entry.entry_date, self.OPENED)
        self.assertEqual(payload["opening_entry"]["id"], entry.pk)
        self.assertEqual(payload["opening_entry"]["total_debit"], "300.00")
        self.assertEqual(payload["opening_entry"]["total_credit"], "300.00")
        lines = {
            line.account.code: (line.debit, line.credit) for line in entry.lines.all()
        }
        self.assertEqual(lines["1310"], (Decimal("300.00"), Decimal("0.00")))
        self.assertEqual(lines["2110"], (Decimal("0.00"), Decimal("300.00")))

    def test_the_imported_opening_shows_in_the_trial_balance(self):
        self.upload(self.balanced_rows(), entry_date=self.OPENED)

        res = self.client.get(
            f"{BOOKS}{self.mine.pk}/reports/trial_balance/",
            {
                "from": self.OPENED.isoformat(),
                "to": datetime.date(THIS_YEAR, 12, 31).isoformat(),
            },
            **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        rows = {row["account_code"]: row for row in res.data["rows"]}
        self.assertEqual(rows["1310"]["debit"], "300.00")
        self.assertEqual(rows["2110"]["credit"], "300.00")

    def test_an_existing_code_is_updated_not_duplicated(self):
        """الكودُ القائم (شجرةُ المنصّة) يُحدَّث اسمُه ولا يُستنسخ صفٌّ ثانٍ."""
        payload = self.upload([
            ["1300", "ذمم العملاء (منقول)", "أصول", "1000", 0],
        ])

        self.assertEqual(payload["accounts_created"], 0)
        self.assertEqual(payload["accounts_updated"], 1)
        self.assertEqual(
            ClientBookAccount.objects.filter(client=self.mine, code="1300").count(), 1,
        )
        self.assertEqual(
            ClientBookAccount.objects.get(client=self.mine, code="1300").name,
            "ذمم العملاء (منقول)",
        )
        self.assertIsNone(payload["opening_entry"])

    def test_an_account_type_is_accepted_as_a_label_or_a_value(self):
        self.upload([
            ["1320", "بالعربي", "أصول", "1300", 0],
            ["1330", "بالقيمة", "asset", "1300", 0],
        ])

        self.assertEqual(
            ClientBookAccount.objects.get(client=self.mine, code="1320").account_type,
            "asset",
        )
        self.assertEqual(
            ClientBookAccount.objects.get(client=self.mine, code="1330").account_type,
            "asset",
        )

    # ── الرفض: لا كتابةَ جزئية ────────────────────────────────────────────
    def test_an_unbalanced_file_is_refused_with_the_difference(self):
        error = self.upload([
            ["1310", "ذممٌ قديمة", "أصول", "1300", 300],
            ["2110", "موردون قدامى", "خصوم", "2100", -250],
        ], expect=400)

        self.assertIn("50.00", str(error))
        self.assertIn("الفرق", str(error))
        self.assertFalse(
            ClientBookAccount.objects.filter(client=self.mine, code="1310").exists(),
        )
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_a_duplicate_code_is_refused_by_name(self):
        error = self.upload([
            ["1310", "ذممٌ قديمة", "أصول", "1300", 150],
            ["1310", "ذممٌ ثانية", "أصول", "1300", -150],
        ], expect=400)

        self.assertIn("1310", str(error))
        self.assertFalse(
            ClientBookAccount.objects.filter(client=self.mine, code="1310").exists(),
        )
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_one_bad_row_rolls_the_whole_file_back(self):
        """شجرةٌ صحيحة وصفٌّ واحدٌ بنوعٍ مخترَع: لا كودَ ولا حركة."""
        error = self.upload([
            ["1310", "ذممٌ قديمة", "أصول", "1300", 300],
            ["2110", "موردون قدامى", "خصوم", "2100", -300],
            ["2120", "نوعٌ خياليّ", "خيال", "2100", 0],
        ], expect=400)

        self.assertIn("2120", str(error))
        self.assertFalse(
            ClientBookAccount.objects.filter(
                client=self.mine, code__in=["1310", "2110", "2120"],
            ).exists(),
        )
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_an_unknown_parent_code_is_400(self):
        self.upload([
            ["1310", "ذممٌ قديمة", "أصول", "9999", 0],
        ], expect=400)

        self.assertFalse(
            ClientBookAccount.objects.filter(client=self.mine, code="1310").exists(),
        )

    def test_a_cycle_in_the_file_is_400(self):
        error = self.upload([
            ["1400", "أ", "أصول", "1401", 0],
            ["1401", "ب", "أصول", "1400", 0],
        ], expect=400)

        self.assertIn("1400", str(error))
        self.assertFalse(
            ClientBookAccount.objects.filter(
                client=self.mine, code__in=["1400", "1401"],
            ).exists(),
        )

    def test_a_file_without_the_known_headers_is_400(self):
        error = self.upload(
            [], content=workbook_bytes([["x"]], headers=["كود", "اسم"]), expect=400,
        )

        self.assertIn("الترويسة", str(error))

    def test_a_broken_file_is_400_not_500(self):
        self.upload([], content=b"not an xlsx at all", expect=400)

    # ── القالب ────────────────────────────────────────────────────────────
    def test_the_template_downloads_empty_with_the_known_headers(self):
        res = self.client.get(
            f"{BOOKS}{self.mine.pk}/import/template.xlsx", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn("spreadsheetml", res["Content-Type"])
        sheet = load_workbook(BytesIO(res.content)).active
        self.assertEqual([cell.value for cell in sheet[1]], HEADERS)
        self.assertEqual(sheet.max_row, 1)

    # ── الدور والحالة والعزل ──────────────────────────────────────────────
    def test_a_balance_import_needs_the_approver_role(self):
        """الملفُّ يكتب رصيداً بيدٍ — كالقيد اليدوي والافتتاحيّ سواء."""
        self.grant(self.accountant, "office.clients.write", "office.amounts.view")
        self.as_user(self.accountant)

        error = self.upload(self.balanced_rows(), expect=403)

        self.assertIn("المدير", str(error))
        self.assertFalse(BookEntry.objects.filter(client=self.mine).exists())

    def test_a_tree_only_import_keeps_the_plain_write_key(self):
        self.grant(self.accountant, "office.clients.write", "office.amounts.view")
        self.as_user(self.accountant)

        payload = self.upload([["1310", "ذممٌ قديمة", "أصول", "1300", 0]])

        self.assertEqual(payload["accounts_created"], 1)
        self.assertIsNone(payload["opening_entry"])

    def test_a_stopped_book_does_not_import(self):
        service = self.mine.services.get(service__code="bookkeeping")
        service.ends_on = datetime.date(2020, 12, 31)
        service.save(update_fields=["ends_on"])

        error = self.upload(self.balanced_rows(), expect=400)

        self.assertIn("للقراءة فقط", str(error))
        self.assertFalse(
            ClientBookAccount.objects.filter(client=self.mine, code="1310").exists(),
        )

    def test_another_office_book_is_404(self):
        self.as_user(self.manager_b)

        self.upload(self.balanced_rows(), expect=404, tenant=self.tenant_b)

        self.assertFalse(
            ClientBookAccount.objects.filter(client=self.mine, code="1310").exists(),
        )

    def test_a_simple_book_imports_a_balanced_file_too(self):
        other = make_client(
            tenant=self.tenant, catalog=self.catalog,
            name="زبونٌ بسيط", responsible=self.accountant,
        )
        self.create_book(other, kind=BOOK_KIND_SIMPLE, opened_on=self.OPENED)

        payload = self.upload(
            [
                ["1310", "ذممٌ قديمة", "أصول", "1000", 100],
                ["5110", "مصروفٌ قديم", "مصاريف", "5000", -100],
            ],
            client=other,
            entry_date=self.OPENED,
        )

        entry = BookEntry.objects.get(client=other, kind="opening")
        self.assertEqual(payload["opening_entry"]["id"], entry.pk)
        self.assertEqual(
            BookEntryLine.objects.filter(entry=entry).aggregate(
                total=Sum("debit"),
            )["total"],
            Decimal("100.00"),
        )
