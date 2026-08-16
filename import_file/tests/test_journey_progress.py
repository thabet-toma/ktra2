"""مؤشّر اكتمال الملف داخل مرشد رحلة الاستيراد — وأثره الصفري بلا ترخيص.

أربع قواعد يثبتها هذا الملف:

1. **الأرقام أرقام الملف نفسه** — `file_progress` على صفّ الصفقة وصفّ الشحنة
   يطابق البنود المزروعة فعلاً ومرفوعاتها، لا مجرد وجود المفتاح.
2. **المرشد لا يخالف الملف** — مرحلة الشحنة في الشارة **تساوي** ما تقوله لوحة
   الملف لنفس الصفقة. لا حسابان يتصادفان اليوم ثم ينحرفان غداً: الصفّ المشتقّ
   (سعر الشحن) يدخل المقام في الاثنين لأن الدالة واحدة.
3. **الشركة غير المرخّصة لا تدفع شيئاً** — حمولتها **مطابقة حرفياً** لما يبنيه
   `build_import_journey_summary` وحده. الاختبار يقارن بالبناء المجرَّد لا بغياب
   مفتاح، فيسقط إن سرّب السطر المحروس أي شيء يوماً.
4. **لا استعلام لكل صفّ** — ثلاث صفقات بشحناتها تكلّف ما تكلّفه واحدة. الشاشة
   تُحمَّل في كل صفحة استيراد، وN+1 هنا يهبط على كل مستخدم في كل مرة.
"""
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from core.models import TenantModule
from import_file.models import ImportFileDocument, ImportFileItem
from import_file.services import ensure_file_items
from logistics.import_journey import build_import_journey_summary
from logistics.models import LogisticsDeal, LogisticsShipment, LogisticsShipmentDeal
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

JOURNEY = "/api/logistics/import-journey/"
FILE_OF_DEAL = "/api/import-file/deals/{pk}/file/"

MODULE_KEY = "import_file"

#: بنود الشحنة المطلوبة الثلاثة + الصفّ المشتقّ (سعر الشحن) = مقام مرحلة الشحنة.
SHIPMENT_TOTAL = 4


class JourneyFileProgressTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="journey-file", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة مرشد الملف", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="المصنع الصيني", partner_type="Supplier",
        )
        cls.deal = cls.make_deal("D-JF")
        cls.shipment = cls.make_shipment("SH-JF", cls.deal)

    @classmethod
    def make_deal(cls, ref):
        return LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number=ref, partner=cls.supplier,
            order_date="2026-07-01", total_amount=1000, currency=cls.usd,
            shipping_workflow_status="sw_mfg_start",
        )

    @classmethod
    def make_shipment(cls, number, deal):
        shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number=number,
        )
        LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
        return shipment

    def setUp(self):
        self.license = TenantModule.objects.create(
            tenant=self.tenant, module_key=MODULE_KEY, enabled=True,
        )
        self.client.force_authenticate(user=self.user)

    # ── أدوات ─────────────────────────────────────────────────────────────
    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def journey(self):
        response = self.client.get(JOURNEY, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def open_file(self, deal=None):
        response = self.client.get(
            FILE_OF_DEAL.format(pk=(deal or self.deal).pk), **self.headers(),
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def deal_row(self, payload, deal=None):
        return next(
            row for row in payload["deals"]["rows"] if row["id"] == (deal or self.deal).pk
        )

    def shipment_row(self, payload, shipment=None):
        return next(
            row for row in payload["shipments"]
            if row["id"] == (shipment or self.shipment).pk
        )

    def attach(self, kind, *, deal=None, shipment=None):
        anchor = (
            {"shipment": shipment} if shipment is not None
            else {"deal": deal or self.deal}
        )
        item = ImportFileItem.objects.get(tenant=self.tenant, kind=kind, **anchor)
        return ImportFileDocument.objects.create(
            tenant=self.tenant, item=item, url=f"https://res.cloudinary.com/{kind}.pdf",
        )

    # ══════════════════════════════════════════════════════════════════════
    # 1. الأرقام
    # ══════════════════════════════════════════════════════════════════════

    def test_the_rows_carry_the_progress_of_the_items_actually_seeded(self):
        self.open_file()  # التزريع يقع عند فتح الملف
        self.attach("proforma_invoice")
        self.attach("bill_of_lading", shipment=self.shipment)
        self.shipment.freight_rate = 12
        self.shipment.save(update_fields=["freight_rate"])

        payload = self.journey()

        # صفّ الصفقة يجمع بنودها وبنود شحنتها — كما يفعل ملفّها تماماً
        self.assertEqual(
            self.deal_row(payload)["file_progress"],
            {
                "offer": {"done": 0, "total": 2},
                "deal": {"done": 1, "total": 2},
                "shipment": {"done": 2, "total": SHIPMENT_TOTAL},
                "clearance": {"done": 0, "total": 2},
            },
        )
        # وصفّ الشحنة يحمل وثائق الشحنة وحدها — لا مستندات صفقاتها
        self.assertEqual(
            self.shipment_row(payload)["file_progress"],
            {
                "shipment": {"done": 2, "total": SHIPMENT_TOTAL},
                "clearance": {"done": 0, "total": 2},
            },
        )

    def test_a_deal_whose_file_was_never_opened_reports_no_stored_items(self):
        """المرشد يعرض ما هو مسجَّل — لا يزرع ملفاً في كل تحميل صفحة."""
        solo = self.make_deal("D-SOLO")

        row = self.deal_row(self.journey(), deal=solo)

        self.assertEqual(row["file_progress"], {})
        self.assertFalse(ImportFileItem.objects.filter(deal=solo).exists())

    # ══════════════════════════════════════════════════════════════════════
    # 2. الشارة لا تخالف الملف
    # ══════════════════════════════════════════════════════════════════════

    def test_the_shipment_stage_equals_what_the_file_endpoint_reports(self):
        """المصدر واحد: `stage_progress` نفسها بالشحنة نفسها ممرَّرةً.

        بلا تمرير الشحنة يسقط الصفّ المشتقّ من المقام هنا وحده، فتقول الشارة
        ٢/٣ وتقول اللوحة ٢/٤ عن الشيء نفسه في الشاشة نفسها.
        """
        self.open_file()
        self.attach("bill_of_lading", shipment=self.shipment)
        self.shipment.freight_rate = 12
        self.shipment.save(update_fields=["freight_rate"])

        from_file = next(
            stage for stage in self.open_file()["stages"] if stage["stage"] == "shipment"
        )["progress"]
        from_guide = self.deal_row(self.journey())["file_progress"]["shipment"]

        self.assertEqual(from_guide, from_file)
        self.assertEqual(from_file, {"done": 2, "total": SHIPMENT_TOTAL})

    # ══════════════════════════════════════════════════════════════════════
    # 3. بلا ترخيص: حمولة مطابقة حرفياً
    # ══════════════════════════════════════════════════════════════════════

    def test_an_unlicensed_company_gets_the_untouched_payload(self):
        self.open_file()
        self.attach("proforma_invoice")
        self.license.delete()

        payload = self.journey()

        self.assertEqual(payload, build_import_journey_summary(self.tenant))
        for row in payload["deals"]["rows"] + payload["shipments"]:
            self.assertNotIn("file_progress", row)

    # ══════════════════════════════════════════════════════════════════════
    # 4. لا استعلام لكل صفّ
    # ══════════════════════════════════════════════════════════════════════

    def test_the_query_count_does_not_grow_with_the_rows(self):
        ensure_file_items(self.deal)

        with CaptureQueriesContext(connection) as one:
            self.journey()

        for index in range(2):
            extra = self.make_deal(f"D-MORE-{index}")
            self.make_shipment(f"SH-MORE-{index}", extra)
            ensure_file_items(extra)

        with CaptureQueriesContext(connection) as three:
            payload = self.journey()

        self.assertEqual(len(payload["deals"]["rows"]), 3)
        self.assertEqual(len(payload["shipments"]), 3)
        self.assertEqual(
            len(three), len(one),
            "الإثراء استعلم لكل صفّ — الشاشة تُحمَّل في كل صفحة استيراد",
        )
