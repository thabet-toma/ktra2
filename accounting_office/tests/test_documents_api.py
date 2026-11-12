"""نقاطُ قائمة الأوراق وشبكة الأشهر — #278.

**ما يثبته هذا الملف:**

1. **كلُّ صفٍّ في الشبكة بعدد الأشهر نفسه**: خانةٌ `null` لبندٍ لا صفَّ له في شهر
   (معيار القبول ٥).
2. **الحالاتُ والقناة**: «وصلت» تحفظ الفاعل والتاريخ والقناة، والقناة الغائبة 400.
3. **الملفُّ كيانٌ منفصل**: يُرفع ويُحذف ولا يغيّر الحالة، ويُقدَّم بايتاتٍ من
   الخادم ولا يخرج رابطه في أيّ ردّ (معيار القبول ٤).
4. **الرؤيةُ من `visible_clients` وحدها**: زبونُ زميلٍ أو مكتبٍ آخر **404**.
5. **القالبُ والتخصيص**: قراءةُ بنود المنصّة لكل عضو، وكتابتُها بمفتاح
   `office.settings.manage`، وخيارُ الزبون بمفتاح `office.clients.write`.
6. **«اليوم»**: عدّادُ `missing_docs` وفلترُه و`docs` لكل صفّ، وعددُ الاستعلامات
   لا يكبر بعدد الصفوف.
"""
import datetime
import json
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.http import HttpResponse
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office import services
from accounting_office.models import (
    DOCUMENT_STATUS_NOT_NEEDED,
    DOCUMENT_STATUS_RECEIVED,
    DOCUMENT_STATUS_REQUIRED,
    ClientDocumentItemChoice,
    DeadlineRule,
    DocumentChecklistItem,
    DocumentFile,
    Obligation,
    OfficeClient,
    OfficeDocumentItem,
    OfficeDocumentItemChoice,
    PeriodTask,
    TaxCard,
)
from accounting_office.tests.test_documents import seed_document_catalog
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.media_views import MediaUploadError
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
CLIENTS = f"{BASE}clients/"
DOCUMENTS = f"{BASE}documents/"
DOCUMENT_FILES = f"{BASE}document-files/"
DOCUMENT_ITEMS = f"{BASE}document-items/"
TODAY = f"{BASE}today/"

JAN_START = datetime.date(2026, 1, 1)
JAN_END = datetime.date(2026, 1, 31)
FEB_START = datetime.date(2026, 2, 1)
FEB_END = datetime.date(2026, 2, 28)
MAR_FIRST = datetime.date(2026, 3, 1)
RECEIVED_ON = datetime.date(2026, 3, 2)

PDF_BYTES = b"%PDF-1.4\n% test document\n"


def pdf_file(name="scan.pdf"):
    return SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")


class ExplodingUpload:
    """ملفٌّ فوق السقف: قراءةٌ بلا طولٍ أو إعادةُ مؤشّرٍ تُسقط الاختبار.

    الحجمُ يُفحص قبل أي قراءة (#278 جولة ١)، فلا يصل إلى هنا `read()` أصلاً —
    ولو وصل لكُشف: `read()` بلا طولٍ يقرأ الملفَّ كلَّه في الذاكرة.
    """

    name = "big.pdf"
    content_type = "application/pdf"
    size = services.MAX_DOCUMENT_BYTES + 1

    def __init__(self):
        self.reads: list = []

    def read(self, num_bytes=None):
        self.reads.append(num_bytes)
        if num_bytes is None:
            raise AssertionError("قُرئ الملفُّ كاملاً في الذاكرة قبل فحص حجمه.")
        return PDF_BYTES

    def seek(self, *_args):
        raise AssertionError("أُعيد الملفُّ إلى أوّله قبل فحص حجمه.")



class DocumentsApiTestCase(APITestCase):
    """مكتبٌ مرخَّص بمالكه ومحاسبَين، وزبونٌ لكل محاسب، ومكتبٌ ثانٍ للعزل."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        seed_document_catalog()
        cls.owner = User.objects.create_user(username="da_owner", password="x")
        cls.tenant = create_company(
            "مكتب أوراق الـAPI", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role,
            )
            return user

        cls.accountant = member("da_accountant", "accountant")
        cls.colleague = member("da_colleague", "accountant")

        def make(name, responsible):
            client = OfficeClient.objects.create(
                tenant=cls.tenant, name=name, responsible=responsible,
            )
            TaxCard.objects.create(
                client=client,
                vat_classification="authorized",
                entity_type="company",
                annual_sales=Decimal("0"),
            )
            services.add_client_service(
                client=client, service=cls.catalog["vat"],
                starts_on=JAN_START, responsible_from=JAN_START, frequency="monthly",
            )
            return client

        cls.mine = make("زبون المحاسب", cls.accountant)
        cls.other = make("زبون الزميل", cls.colleague)
        cls.rule = DeadlineRule.objects.filter(
            schedule__tax_system="IL", schedule__year=2026,
        ).first()

        cls.outside_owner = User.objects.create_user(username="da_outside", password="x")
        cls.outside = create_company(
            "مكتب آخر للأوراق", cls.outside_owner, template="accounting_office",
        )
        invalidate_module_cache(cls.outside.pk)
        ready_office(cls.outside, "IL")
        outside_catalog = catalog(cls.outside)
        cls.outside_client = OfficeClient.objects.create(
            tenant=cls.outside, name="زبون المكتب الآخر", responsible=cls.outside_owner,
        )
        TaxCard.objects.create(
            client=cls.outside_client, vat_classification="authorized",
            annual_sales=Decimal("0"),
        )
        services.add_client_service(
            client=cls.outside_client, service=outside_catalog["vat"],
            starts_on=JAN_START, responsible_from=JAN_START, frequency="monthly",
        )

    def setUp(self):
        DocumentFile.objects.all().delete()
        DocumentChecklistItem.objects.all().delete()
        OfficeDocumentItem.objects.all().delete()
        OfficeDocumentItemChoice.objects.all().delete()
        ClientDocumentItemChoice.objects.all().delete()
        Obligation.objects.all().delete()
        PeriodTask.objects.all().delete()

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    # ── البناء ────────────────────────────────────────────────────────────
    def make_rows(self, client, *, status=DOCUMENT_STATUS_REQUIRED, codes=None,
                  period_start=JAN_START, period_end=JAN_END, service_codes=None):
        codes = codes or ["vat"]
        return [
            DocumentChecklistItem.objects.create(
                tenant=client.tenant,
                client=client,
                item_code=code,
                name=f"ورقة {code}",
                service_codes=list(service_codes if service_codes is not None else ["vat"]),
                cadence="monthly",
                period_start=period_start,
                period_end=period_end,
                status=status,
            )
            for code in codes
        ]

    def add_obligation(self, client, *, period_start=JAN_START, period_end=JAN_END,
                       status=Obligation.STATUS_PENDING):
        task, _created = PeriodTask.objects.get_or_create(
            client_service=client.services.first(),
            period_start=period_start,
            period_end=period_end,
            defaults={
                "tenant": client.tenant,
                "client": client,
                "internal_deadline": period_end,
            },
        )
        # `update_or_create` لأن المحرّكَ قد يكون ولّد التزامَ الفترة نفسها.
        obligation, _created = Obligation.objects.update_or_create(
            client_service_id=task.client_service_id,
            rule_code=self.rule.code,
            period_end=period_end,
            defaults={
                "tenant": client.tenant,
                "client": client,
                "task": task,
                "rule": self.rule,
                "name": self.rule.name,
                "period_start": period_start,
                "legal_date": period_end,
                "official_date": period_end,
                "actual_deadline": period_end,
                "internal_deadline": period_end,
                "status": status,
            },
        )
        return obligation

    def documents(self, client, year=2026):
        return self.client.get(
            f"{CLIENTS}{client.pk}/documents/", {"year": year}, **self.headers(),
        )


class GridApiTest(DocumentsApiTestCase):
    """شبكةُ الأشهر × البنود — عددُ الخانات مطابقٌ لعدد الأشهر."""

    def test_every_grid_row_has_one_cell_per_month(self):
        self.as_user(self.accountant)
        services.refresh_office(self.tenant, day=MAR_FIRST)
        removed = DocumentChecklistItem.objects.filter(
            client=self.mine, period_start=FEB_START, item_code="il_input_invoices",
        )
        self.assertTrue(removed.exists())
        removed.delete()

        response = self.documents(self.mine)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["months"], ["2026-01-01", "2026-02-01"])
        self.assertTrue(response.data["items"])
        for item in response.data["items"]:
            self.assertEqual(
                len(item["cells"]),
                len(response.data["months"]),
                item["item_code"],
            )
        gap = next(
            item for item in response.data["items"]
            if item["item_code"] == "il_input_invoices"
        )
        self.assertEqual(gap["cells"][1]["month"], "2026-02-01")
        self.assertIsNone(gap["cells"][1]["row_id"])
        self.assertIsNotNone(gap["cells"][0]["row_id"])

    def test_the_payload_carries_labels_and_retention_of_the_system(self):
        self.as_user(self.accountant)
        services.refresh_office(self.tenant, day=MAR_FIRST)

        payload = self.documents(self.mine).data

        self.assertEqual(
            {row["value"] for row in payload["status_choices"]},
            {"required", "partial", "received", "not_needed"},
        )
        self.assertEqual(
            [row["value"] for row in payload["channel_choices"]],
            ["whatsapp", "paper", "email"],
        )
        self.assertEqual(len(payload["retention"]), 2)
        self.assertIn(2026, payload["available_years"])
        cell = payload["items"][0]["cells"][0]
        self.assertEqual(cell["status_label"], "مطلوبة")

    def test_the_annual_list_holds_the_year_rows(self):
        self.as_user(self.accountant)
        services.add_client_service(
            client=self.mine, service=self.catalog["annual_accounts"],
            starts_on=datetime.date(2025, 1, 1),
            responsible_from=datetime.date(2025, 1, 1),
            frequency="annual",
        )
        services.refresh_office(self.tenant, day=datetime.date(2026, 1, 1))

        payload = self.client.get(
            f"{CLIENTS}{self.mine.pk}/documents/", {"year": 2025}, **self.headers(),
        ).data

        self.assertEqual(payload["year"], 2025)
        self.assertTrue(payload["annual"])
        self.assertEqual(payload["annual"][0]["period_end"], "2025-12-31")
        self.assertIn("files", payload["annual"][0])


class PaperAmountsPayloadTest(DocumentsApiTestCase):
    """حقولُ مبلغ الورقة في الحمولة — #286/ج: القائمةُ السنوية وشبكةُ الأشهر.

    **الفرقُ الذي يثبته هذا الصنف:** المبلغان (`amount`/`tax_amount`) يخرجان
    بقيمتهما لمن يملك `office.amounts.view` و`null` لمن لا يملكه، ويبقى للناظر
    بلا مفتاحٍ النسبةُ والطرف («نسبةٌ واسمٌ لا مال»)، ولا مفتاحَ قائمٍ يختفي أو
    يتغيّر شكلُه. بلا هذه الحقول لا تقرأ الواجهةُ مبلغَ الورقة أصلاً، فلا تدخل
    حركةً من ورقها (#286/ج).
    """

    #: مفاتيحُ سطر الورقة قبل #286/ج — تبقى كلُّها كما هي.
    ROW_KEYS = frozenset({
        "row_id", "client_id", "item_code", "name", "service_codes", "cadence",
        "period_start", "period_end", "period_label", "status", "status_label",
        "received_on", "received_by_name", "channel", "channel_label",
        "files_count",
    })

    #: مفاتيحُ خانة الشهر قبل #286/ج.
    CELL_KEYS = frozenset({
        "month", "row_id", "status", "status_label", "received_on",
        "received_by_name", "channel", "channel_label", "files_count",
    })

    #: الحقولُ الأربعة — عقدُ `client_books.DOCUMENT_VALUE_FIELDS`.
    VALUE_KEYS = frozenset({"amount", "tax_amount", "vat_rate", "side_party"})

    def setUp(self):
        super().setUp()
        # الورقتان تُكتبان مباشرةً: كتابةُ القيم من الـAPI لها اختباراتُها في
        # `test_book_entry_generation`، والمقصودُ هنا شكلُ ما يخرج للقارئ.
        self.monthly = self.paper(
            cadence="monthly", period_start=JAN_START, period_end=JAN_END,
            code="il_bank_statements",
        )
        self.annual = self.paper(
            cadence="annual",
            period_start=datetime.date(2025, 1, 1),
            period_end=datetime.date(2025, 12, 31),
            code="il_audited_statements",
        )

    def paper(self, *, cadence, period_start, period_end, code):
        return DocumentChecklistItem.objects.create(
            tenant=self.tenant,
            client=self.mine,
            item_code=code,
            name=f"ورقة {code}",
            service_codes=["vat"],
            cadence=cadence,
            period_start=period_start,
            period_end=period_end,
            status=DOCUMENT_STATUS_RECEIVED,
            channel="paper",
            amount=Decimal("100.00"),
            tax_amount=Decimal("17.00"),
            vat_rate=Decimal("17.00"),
            side_party="شركة الأمل",
        )

    def annual_row(self):
        payload = self.documents(self.mine, year=2025).data
        return next(row for row in payload["annual"] if row["row_id"] == self.annual.pk)

    def month_cell(self):
        payload = self.documents(self.mine, year=2026).data
        return next(
            cell
            for item in payload["items"]
            for cell in item["cells"]
            if cell["row_id"] == self.monthly.pk
        )

    def test_the_annual_row_carries_the_paper_amounts_for_the_owner(self):
        self.as_user(self.owner)

        row = self.annual_row()

        self.assertEqual(Decimal(row["amount"]), Decimal("100.00"))
        self.assertEqual(Decimal(row["tax_amount"]), Decimal("17.00"))
        self.assertEqual(Decimal(row["vat_rate"]), Decimal("17.00"))
        self.assertEqual(row["side_party"], "شركة الأمل")

    def test_the_month_cell_carries_the_paper_amounts_for_the_owner(self):
        self.as_user(self.owner)

        cell = self.month_cell()

        self.assertEqual(Decimal(cell["amount"]), Decimal("100.00"))
        self.assertEqual(Decimal(cell["tax_amount"]), Decimal("17.00"))
        self.assertEqual(Decimal(cell["vat_rate"]), Decimal("17.00"))
        self.assertEqual(cell["side_party"], "شركة الأمل")

    def test_the_amounts_are_masked_for_a_member_without_the_amounts_key(self):
        """المبلغان `null` والنسبةُ والطرفُ باقيان — عقدُ #272 في الورقة."""
        self.as_user(self.accountant)

        row = self.annual_row()

        self.assertIsNone(row["amount"])
        self.assertIsNone(row["tax_amount"])
        self.assertEqual(Decimal(row["vat_rate"]), Decimal("17.00"))
        self.assertEqual(row["side_party"], "شركة الأمل")

    def test_the_cell_amounts_are_masked_for_a_member_without_the_amounts_key(self):
        self.as_user(self.accountant)

        cell = self.month_cell()

        self.assertIsNone(cell["amount"])
        self.assertIsNone(cell["tax_amount"])
        self.assertEqual(Decimal(cell["vat_rate"]), Decimal("17.00"))
        self.assertEqual(cell["side_party"], "شركة الأمل")

    def test_the_row_and_cell_shapes_keep_their_existing_keys(self):
        self.as_user(self.owner)

        row = self.annual_row()
        cell = self.month_cell()

        self.assertLessEqual(self.ROW_KEYS, set(row))
        self.assertLessEqual(self.CELL_KEYS, set(cell))
        self.assertLessEqual(self.VALUE_KEYS, set(row))
        self.assertLessEqual(self.VALUE_KEYS, set(cell))

    def test_a_paper_without_an_amount_reads_none_not_zero(self):
        """الفراغُ `None` لا `"0.00"`: ورقةٌ بلا مبلغٍ ليست ورقةً بمبلغ صفر."""
        self.as_user(self.owner)
        DocumentChecklistItem.objects.filter(pk=self.annual.pk).update(
            amount=None, tax_amount=None, vat_rate=None, side_party="",
        )

        row = self.annual_row()

        self.assertIsNone(row["amount"])
        self.assertIsNone(row["tax_amount"])
        self.assertIsNone(row["vat_rate"])
        self.assertEqual(row["side_party"], "")

    def test_the_payload_function_masks_by_the_reader_and_hides_without_one(self):
        """النداءُ المباشر: الطالبُ يُترجَم إلى قرار، وغيابُه يُقنّع لا يكشف."""
        for user, expected in (
            (self.owner, Decimal("100.00")),
            (self.accountant, None),
            (None, None),
        ):
            with self.subTest(user=user):
                row = services.document_row_payload(self.annual, user=user)
                if expected is None:
                    self.assertIsNone(row["amount"])
                    self.assertIsNone(row["tax_amount"])
                else:
                    self.assertEqual(Decimal(row["amount"]), expected)
                # النسبةُ والطرفُ لا يُقنَّعان — نسبةٌ واسمٌ لا مال.
                self.assertEqual(Decimal(row["vat_rate"]), Decimal("17.00"))
                self.assertEqual(row["side_party"], "شركة الأمل")


class StatusApiTest(DocumentsApiTestCase):
    """تسجيلُ الوصول: مَن ومتى وكيف — والقناةُ إلزامية."""

    def test_received_stores_actor_date_and_channel(self):
        self.as_user(self.accountant)
        row = self.make_rows(self.mine, codes=["il_bank_statements"])[0]

        response = self.client.post(
            f"{DOCUMENTS}{row.pk}/status/",
            {"status": "received", "channel": "whatsapp"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "received")
        self.assertEqual(response.data["received_by_name"], self.accountant.username)
        row.refresh_from_db()
        self.assertEqual(row.status, DOCUMENT_STATUS_RECEIVED)
        self.assertEqual(row.received_by_id, self.accountant.pk)
        self.assertEqual(row.channel, "whatsapp")
        self.assertEqual(row.received_on, timezone.localdate())

    def test_a_missing_channel_is_400(self):
        self.as_user(self.accountant)
        row = self.make_rows(self.mine, codes=["il_bank_statements"])[0]

        response = self.client.post(
            f"{DOCUMENTS}{row.pk}/status/", {"status": "received"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("channel", response.data)
        row.refresh_from_db()
        self.assertEqual(row.status, DOCUMENT_STATUS_REQUIRED)

    def test_an_unknown_status_is_400(self):
        self.as_user(self.accountant)
        row = self.make_rows(self.mine, codes=["il_bank_statements"])[0]

        response = self.client.post(
            f"{DOCUMENTS}{row.pk}/status/",
            {"status": "maybe", "channel": "paper"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("status", response.data)

    def test_another_members_row_is_404(self):
        self.as_user(self.accountant)
        row = self.make_rows(self.other, codes=["il_bank_statements"])[0]

        response = self.client.post(
            f"{DOCUMENTS}{row.pk}/status/",
            {"status": "received", "channel": "paper"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 404, response.data)

    def test_another_tenants_row_is_404(self):
        self.as_user(self.owner)
        row = self.make_rows(self.outside_client, codes=["il_bank_statements"])[0]

        response = self.client.post(
            f"{DOCUMENTS}{row.pk}/status/",
            {"status": "received", "channel": "paper"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 404, response.data)

    def test_another_members_client_documents_are_404(self):
        self.as_user(self.accountant)

        response = self.documents(self.other)

        self.assertEqual(response.status_code, 404, response.data)


class FileApiTest(DocumentsApiTestCase):
    """الملفُّ الاختياريّ: يُرفع ويُحذف ولا يمسّ الحالة، ورابطُه لا يخرج."""

    def setUp(self):
        super().setUp()
        self.as_user(self.accountant)
        self.row = self.make_rows(self.mine, codes=["il_bank_statements"])[0]
        self.url = "https://res.cloudinary.com/test/raw/upload/doc.pdf"

    def _upload(self):
        patcher = mock.patch(
            "accounting_office.views.upload_media_file", return_value=self.url,
        )
        upload = patcher.start()
        self.addCleanup(patcher.stop)
        response = self.client.post(
            f"{DOCUMENTS}{self.row.pk}/files/",
            {
                "file": pdf_file(),
                "document_type": "كشف البنك",
                "document_number": "4411",
                "issuer_registration": "512345678",
            },
            format="multipart", **self.headers(),
        )
        return response, upload

    def test_upload_and_delete_leave_the_status_unchanged_and_the_url_hidden(self):
        response, upload = self._upload()

        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(upload.called)
        self.assertEqual(upload.call_args.args[0].name, "scan.pdf")
        self.assertEqual(upload.call_args.kwargs["tenant"], self.tenant)
        self.assertNotIn("file_url", response.data)
        self.assertNotIn("res.cloudinary.com", json.dumps(response.data, default=str))

        self.row.refresh_from_db()
        self.assertEqual(self.row.status, DOCUMENT_STATUS_REQUIRED)

        listing = self.client.get(
            f"{DOCUMENTS}{self.row.pk}/files/", **self.headers(),
        )
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(len(listing.data), 1)
        self.assertNotIn("file_url", listing.data[0])
        self.assertNotIn(
            "res.cloudinary.com", json.dumps(listing.data, default=str),
        )
        self.assertTrue(listing.data[0]["is_copy"])
        self.assertEqual(listing.data[0]["document_type"], "كشف البنك")
        self.assertEqual(listing.data[0]["document_number"], "4411")
        self.assertTrue(listing.data[0]["uid"])

        file_id = listing.data[0]["id"]
        patcher = mock.patch(
            "accounting_office.views.stream_stored_asset",
            return_value=HttpResponse(PDF_BYTES, content_type="application/pdf"),
        )
        stream = patcher.start()
        self.addCleanup(patcher.stop)
        download = self.client.get(
            f"{DOCUMENT_FILES}{file_id}/download/", **self.headers(),
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, PDF_BYTES)
        self.assertEqual(stream.call_args.args[0], self.url)

        destroy = mock.patch(
            "accounting_office.views.destroy_cloudinary_asset", return_value=True,
        )
        destroy_asset = destroy.start()
        self.addCleanup(destroy.stop)
        removed = self.client.delete(
            f"{DOCUMENT_FILES}{file_id}/", **self.headers(),
        )
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(destroy_asset.call_args.args[0], self.url)
        self.assertFalse(DocumentFile.objects.filter(pk=file_id).exists())

        self.row.refresh_from_db()
        self.assertEqual(self.row.status, DOCUMENT_STATUS_REQUIRED)

    def test_an_empty_file_is_400(self):
        response = self.client.post(
            f"{DOCUMENTS}{self.row.pk}/files/",
            {"file": SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")},
            format="multipart", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("file", response.data)
        self.assertFalse(DocumentFile.objects.exists())

    def test_an_over_cap_upload_is_rejected_before_the_stream_is_read(self):
        """#278 جولة ١: `upload.size` يُفحص قبل قراءة البايتات، فلا ١٠MB في الذاكرة."""
        upload = ExplodingUpload()
        serializer = mock.Mock()
        serializer.validated_data = {"file": upload}
        serializer.is_valid.return_value = True

        with mock.patch(
            "accounting_office.views.upload_media_file",
        ) as media_upload, mock.patch(
            "accounting_office.views.DocumentFileUploadSerializer",
            return_value=serializer,
        ):
            response = self.client.post(
                f"{DOCUMENTS}{self.row.pk}/files/",
                {"file": pdf_file()}, format="multipart", **self.headers(),
            )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("file", response.data)
        self.assertIn("١٠ ميجابايت", str(response.data["file"]))
        self.assertEqual(upload.reads, [])
        self.assertFalse(media_upload.called)
        self.assertFalse(DocumentFile.objects.exists())

    def test_a_failed_row_creation_destroys_the_uploaded_asset(self):
        """#278 جولة ١: فشلُ حفظ الصفّ لا يُبقي أصلاً يتيماً في التخزين."""
        with mock.patch(
            "accounting_office.views.upload_media_file", return_value=self.url,
        ), mock.patch(
            "accounting_office.views.destroy_cloudinary_asset", return_value=True,
        ) as destroy_asset, mock.patch(
            "accounting_office.services.create_document_file",
            side_effect=RuntimeError("تعذّر حفظ الصفّ"),
        ):
            response = self.client.post(
                f"{DOCUMENTS}{self.row.pk}/files/",
                {"file": pdf_file()}, format="multipart", **self.headers(),
            )

        self.assertEqual(response.status_code, 500, response.data)
        destroy_asset.assert_called_once_with(self.url)
        self.assertFalse(DocumentFile.objects.exists())

    def _upload_failing(self, error):
        with mock.patch(
            "accounting_office.views.upload_media_file", side_effect=error,
        ):
            return self.client.post(
                f"{DOCUMENTS}{self.row.pk}/files/",
                {"file": pdf_file()}, format="multipart", **self.headers(),
            )

    def test_a_quota_failure_keeps_its_status_and_company_facing_text(self):
        """#278 جولة ٢: 400 من سقف الخطّة نصُّه للمستخدم — لا يُستبدل بالعامّ."""
        quota = "تجاوزت حدّ التخزين في خطّتك."

        response = self._upload_failing(MediaUploadError(quota, 400))

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["file"], quota)
        self.assertFalse(DocumentFile.objects.exists())

    def test_a_provider_failure_is_502_with_a_generic_sentence(self):
        """#278 جولة ٢: نصُّ المزوّد يذهب للسجلّ لا للردّ، والحالةُ تبقى 502."""
        with self.assertLogs("accounting_office.views", level="WARNING") as logs:
            response = self._upload_failing(
                MediaUploadError("Cloudinary account ktra-prod rejected the upload", 502),
            )

        self.assertEqual(response.status_code, 502, response.data)
        self.assertEqual(response.data["file"], "تعذّر رفع الملف. حاول مرة أخرى.")
        self.assertNotIn("Cloudinary", json.dumps(response.data, default=str))
        self.assertIn("Cloudinary", "\n".join(logs.output))
        self.assertFalse(DocumentFile.objects.exists())

    def test_a_forbidden_type_is_400(self):
        response = self.client.post(
            f"{DOCUMENTS}{self.row.pk}/files/",
            {"file": SimpleUploadedFile(
                "script.exe", b"MZ\x90\x00", content_type="application/octet-stream",
            )},
            format="multipart", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("file", response.data)
        self.assertFalse(DocumentFile.objects.exists())

    def test_deleting_a_file_of_an_invisible_row_is_404(self):
        row = self.make_rows(self.other, codes=["il_bank_statements"])[0]
        file_row = DocumentFile.objects.create(
            tenant=self.tenant, client=self.other, checklist_item=row,
            file_url="https://res.cloudinary.com/test/raw/upload/x.pdf",
            file_name="x.pdf", document_type="ورقة",
        )
        response = self.client.delete(
            f"{DOCUMENT_FILES}{file_row.pk}/", **self.headers(),
        )

        self.assertEqual(response.status_code, 404, response.data)
        self.assertTrue(DocumentFile.objects.filter(pk=file_row.pk).exists())


class TemplateApiTest(DocumentsApiTestCase):
    """قالبُ المكتب: قراءةٌ لكل عضو، وكتابةٌ بمفتاح الإعدادات."""

    def test_the_item_list_is_readable_by_an_accountant(self):
        self.as_user(self.accountant)

        response = self.client.get(
            f"{DOCUMENT_ITEMS}?system=IL", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["items"]), 19)
        self.assertTrue(all(row["included"] for row in response.data["items"]))
        self.assertTrue(response.data["services"])
        self.assertEqual(
            {row["value"] for row in response.data["cadence_choices"]},
            {"monthly", "annual"},
        )

    def test_a_bad_system_is_400(self):
        self.as_user(self.owner)

        response = self.client.get(
            f"{DOCUMENT_ITEMS}?system=XX", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.data)

    def test_platform_items_have_no_office_id(self):
        """#278 جولة ١: `id` فضاءُ بنود المكتب وحدها، وبندُ المنصّة `null`.

        `OfficeDocumentItemViewSet.get_object` يحلّ المعرّف في بنود المكتب فقط،
        فمعرّفُ بند منصّةٍ في الحمولة دعوةٌ إلى `PATCH` على صفٍّ آخر أو 404.
        """
        self.as_user(self.owner)
        custom = OfficeDocumentItem.objects.create(
            tenant=self.tenant, tax_system="IL", name="عقد إيجار المكتب",
            cadence="monthly", service_codes=[], card_conditions={},
            created_by=self.owner,
        )

        response = self.client.get(f"{DOCUMENT_ITEMS}?system=IL", **self.headers())

        self.assertEqual(response.status_code, 200, response.data)
        platform = [row for row in response.data["items"] if not row["is_custom"]]
        self.assertTrue(platform)
        self.assertTrue(all(row["id"] is None for row in platform))
        office = next(row for row in response.data["items"] if row["is_custom"])
        self.assertEqual(office["id"], custom.pk)
        self.assertEqual(office["item_code"], f"office_doc_{custom.pk}")

    def test_the_client_panel_lists_only_active_office_items(self):
        """#278 جولة ٢: بندٌ معطَّل لا يولّد، فخيارُ الزبون عليه مفتاحٌ ميّت."""
        self.as_user(self.owner)
        custom = OfficeDocumentItem.objects.create(
            tenant=self.tenant, tax_system="IL", name="عقد إيجار المكتب",
            cadence="monthly", service_codes=[], card_conditions={},
            is_active=False, created_by=self.owner,
        )
        code = f"office_doc_{custom.pk}"

        panel = self.client.get(
            f"{DOCUMENT_ITEMS}?system=IL&client={self.mine.pk}", **self.headers(),
        )
        settings_list = self.client.get(
            f"{DOCUMENT_ITEMS}?system=IL", **self.headers(),
        )

        self.assertEqual(panel.status_code, 200, panel.data)
        self.assertNotIn(code, {row["item_code"] for row in panel.data["items"]})
        self.assertEqual(settings_list.status_code, 200, settings_list.data)
        self.assertIn(code, {row["item_code"] for row in settings_list.data["items"]})

    def test_an_office_item_code_cannot_be_toggled_as_a_template_choice(self):
        """#278 جولة ١: بندُ المكتب «مفعَّل/معطَّل» بـ`is_active` لا بخيار القالب."""
        self.as_user(self.owner)
        custom = OfficeDocumentItem.objects.create(
            tenant=self.tenant, tax_system="IL", name="عقد إيجار المكتب",
            cadence="monthly", service_codes=[], card_conditions={},
            created_by=self.owner,
        )
        code = f"office_doc_{custom.pk}"

        response = self.client.post(
            f"{DOCUMENT_ITEMS}choice/", {"item_code": code, "included": False},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("item_code", response.data)
        self.assertIn(
            "بندُ المكتب يُفعَّل ويُعطَّل من قائمته", str(response.data["item_code"]),
        )
        self.assertFalse(
            OfficeDocumentItemChoice.objects.filter(
                tenant=self.tenant, item_code=code,
            ).exists(),
        )

    def test_excluding_an_item_needs_the_settings_key(self):
        self.as_user(self.accountant)
        body = {"item_code": "il_bank_statements", "included": False}

        denied = self.client.post(
            f"{DOCUMENT_ITEMS}choice/", body, format="json", **self.headers(),
        )
        self.assertEqual(denied.status_code, 403, denied.data)

        self.as_user(self.owner)
        allowed = self.client.post(
            f"{DOCUMENT_ITEMS}choice/", body, format="json", **self.headers(),
        )
        self.assertEqual(allowed.status_code, 200, allowed.data)
        included = {
            row["item_code"]: row["included"] for row in allowed.data["items"]
        }
        self.assertFalse(included["il_bank_statements"])
        self.assertTrue(
            OfficeDocumentItemChoice.objects.get(
                tenant=self.tenant, item_code="il_bank_statements",
            ).included is False,
        )

    def test_an_office_item_is_created_and_disabled_by_its_id(self):
        self.as_user(self.owner)

        created = self.client.post(
            f"{DOCUMENT_ITEMS}",
            {
                "system": "IL",
                "name": "عقد إيجار المكتب",
                "cadence": "monthly",
                "service_codes": ["bookkeeping"],
            },
            format="json", **self.headers(),
        )

        self.assertEqual(created.status_code, 201, created.data)
        custom = next(row for row in created.data["items"] if row["is_custom"])
        self.assertEqual(custom["item_code"], f"office_doc_{custom['id']}")
        self.assertEqual(custom["service_codes"], ["bookkeeping"])

        disabled = self.client.patch(
            f"{DOCUMENT_ITEMS}{custom['id']}/", {"is_active": False},
            format="json", **self.headers(),
        )

        self.assertEqual(disabled.status_code, 200, disabled.data)
        self.assertFalse(
            OfficeDocumentItem.objects.get(pk=custom["id"]).is_active,
        )

    def test_creating_an_item_needs_the_settings_key(self):
        self.as_user(self.accountant)

        response = self.client.post(
            f"{DOCUMENT_ITEMS}",
            {"system": "IL", "name": "ورقة", "cadence": "monthly"},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 403, response.data)

    def test_client_choice_wins_over_the_office_template(self):
        self.as_user(self.accountant)
        services.add_client_service(
            client=self.mine, service=self.catalog["annual_accounts"],
            starts_on=datetime.date(2025, 1, 1),
            responsible_from=datetime.date(2025, 1, 1),
            frequency="annual",
        )
        OfficeDocumentItemChoice.objects.create(
            tenant=self.tenant, item_code="il_audited_statements", included=False,
        )

        response = self.client.post(
            f"{CLIENTS}{self.mine.pk}/document-choice/",
            {"item_code": "il_audited_statements", "included": True},
            format="json", **self.headers(),
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            ClientDocumentItemChoice.objects.filter(
                client=self.mine, item_code="il_audited_statements", included=True,
            ).exists(),
        )

        services.refresh_office(self.tenant, day=datetime.date(2026, 1, 1))

        self.assertTrue(
            DocumentChecklistItem.objects.filter(
                client=self.mine, item_code="il_audited_statements",
            ).exists(),
        )


class TodayApiTest(DocumentsApiTestCase):
    """عدّادُ «ناقصه أوراق» وفلترُه و`docs` — بقراءةٍ ثابتة الكلفة."""

    def setUp(self):
        super().setUp()
        # خدمةُ الزبون تنتهي مع كانون الثاني: المحرّكُ يولّد التزاماً واحداً
        # وقائمةَ شهرٍ واحد (٥ بنودٍ لخدمة القيمة المضافة)، فيكون العدّادُ
        # قابلاً للقياس (١ لا ١٠).
        services.stop_client_service(
            self.mine.services.first(), ends_on=JAN_END,
        )
        services.refresh_office(self.tenant, day=timezone.localdate())
        self.rows = list(
            DocumentChecklistItem.objects.filter(
                client=self.mine, period_start=JAN_START,
            ).order_by("item_code"),
        )
        self.obligation = Obligation.objects.get(
            client=self.mine, status=Obligation.STATUS_PENDING,
        )
        services.set_document_status(
            self.rows[0], status=DOCUMENT_STATUS_RECEIVED, channel="paper",
            actor=self.owner, day=RECEIVED_ON,
        )

    def test_the_counter_the_filter_and_the_docs_field(self):
        self.as_user(self.accountant)

        response = self.client.get(TODAY, **self.headers())

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["counters"]["missing_docs"], 1)
        row = next(
            entry for entry in response.data["rows"]
            if entry["id"] == self.obligation.pk
        )
        self.assertEqual(row["docs"], {"received": 1, "required": 5})
        self.assertIn(
            "missing_docs", [badge["key"] for badge in row["badges"]],
        )
        self.assertEqual(
            next(
                badge["label"] for badge in row["badges"]
                if badge["key"] == "missing_docs"
            ),
            "ناقصه أوراق",
        )

        filtered = self.client.get(TODAY, {"filter": "missing_docs"}, **self.headers())
        self.assertEqual(filtered.status_code, 200, filtered.data)
        self.assertEqual([row["id"] for row in filtered.data["rows"]], [self.obligation.pk])

    def test_an_unknown_filter_is_400(self):
        self.as_user(self.accountant)

        response = self.client.get(TODAY, {"filter": "nope"}, **self.headers())

        self.assertEqual(response.status_code, 400, response.data)

    def test_a_received_or_not_needed_list_clears_the_badge_and_the_counter(self):
        self.as_user(self.accountant)
        for row in self.rows[1:]:
            services.set_document_status(
                row, status=DOCUMENT_STATUS_NOT_NEEDED, actor=self.owner,
                day=RECEIVED_ON,
            )

        response = self.client.get(TODAY, **self.headers())

        self.assertEqual(response.data["counters"]["missing_docs"], 0)
        row = next(
            entry for entry in response.data["rows"]
            if entry["id"] == self.obligation.pk
        )
        self.assertNotIn(
            "missing_docs", [badge["key"] for badge in row["badges"]],
        )
        # «مش لازمة» تُخرج الصفوف من العدّ: بقيّةُ القائمة صفٌّ واحد وصل.
        self.assertEqual(row["docs"], {"received": 1, "required": 1})

    def test_the_query_count_does_not_grow_with_the_rows(self):
        self.as_user(self.accountant)

        def count_queries():
            with CaptureQueriesContext(connection) as captured:
                services.today_payload(
                    self.tenant, user=self.accountant, day=RECEIVED_ON,
                )
            return len(captured)

        baseline = count_queries()
        for index in range(6):
            self.make_rows(
                self.mine, codes=[f"extra{index}", f"more{index}"],
            )
        after = count_queries()

        self.assertEqual(after, baseline)
