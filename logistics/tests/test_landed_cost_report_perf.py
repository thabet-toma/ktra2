"""P1-2 (SCALABILITY_AUDIT §2-3): حارس ثبات عدّ الاستعلامات لتقرير Landed Cost.

قبل الإصلاح كان التقرير يستعلم **لكل شحنة على حدة**: روابط صفقاتها (استعلام)،
ثم بنود كل صفقة (استعلام/رابط)، ثم فاتورة الشراء المطابقة بجلبها المسبق
(4 استعلامات/رابط) — أي ~6 استعلامات لكل رابط صفقة، و~4,000 استعلام للسقف
البالغ 200 شحنة. القيمة كانت صحيحة، فلا اختبار وظيفي كان يكشف الانفجار.

الحارس هنا يقيس ما لا يقيسه اختبار القيمة: أن التقرير على **ثلاث** شحنات
يُنفّذ نفس عدد استعلامات شحنة **واحدة**. أي عودة لاستعلام داخل الحلقة تكسره،
وهو نفس النمط الذي حرس به P0-9 تقرير أعمار الدائنين.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from inventory.models import Product
from logistics.models import (
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsShipment,
    LogisticsShipmentDeal,
    PurchaseInvoice,
    PurchaseInvoiceItem,
)
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class LandedCostReportQueryCountTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=982, CompanyName="Landed Perf")
        cls.currency = Currency.objects.create(
            Code="LCP", Symbol="$", IsBaseCurrency=False,
        )
        cls.user = User.objects.create_user(username="landed_perf", password="x")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager",
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="Landed Supplier", partner_type="Supplier",
        )
        cls.agent = Partner.objects.create(
            tenant=cls.tenant, name="Landed Forwarder", partner_type="FreightForwarder",
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="LCP-1", name_ar="صنف التكلفة المستوردة",
        )
        cls.shipments = [cls._make_shipment(idx) for idx in range(3)]

    @classmethod
    def _make_shipment(cls, idx):
        """شحنة كاملة: صفقتان مرتبطتان، لكل صفقة بنودها وفاتورة شرائها."""
        shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant,
            shipment_number=f"SH-LCP-{idx:02d}",
            shipping_agent=cls.agent,
            arrival_date=f"2026-07-{idx + 1:02d}",
            total_shipping_cost_usd=Decimal("500"),
        )
        # رابطان لكل شحنة: N+1 على مستوى الرابط لا الشحنة، فلا بد من أكثر من واحد.
        for sub in range(2):
            deal = LogisticsDeal.objects.create(
                tenant=cls.tenant,
                ref_number=f"D-LCP-{idx:02d}-{sub}",
                partner=cls.supplier,
                order_date=f"2026-06-{idx + 1:02d}",
                currency=cls.currency,
                total_amount=Decimal("1000"),
            )
            LogisticsDealItem.objects.create(
                deal=deal, product=cls.product, quantity=2, unit_price=Decimal("250"),
            )
            LogisticsShipmentDeal.objects.create(
                shipment=shipment, deal=deal,
                allocated_shipping_cost=Decimal("250"),
            )
            invoice = PurchaseInvoice.objects.create(
                tenant=cls.tenant,
                invoice_number=f"PI-LCP-{idx:02d}-{sub}",
                invoice_date=f"2026-07-{idx + 1:02d}",
                partner=cls.supplier,
                currency=cls.currency,
                shipment=shipment,
                deal=deal,
                grand_total=Decimal("500"),
            )
            PurchaseInvoiceItem.objects.create(
                invoice=invoice, product=cls.product, name=cls.product.name_ar,
                quantity=2, unit_price=Decimal("250"), total_price=Decimal("500"),
            )
        return shipment

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _report(self, path):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.content)
        return response, len(captured)

    def test_query_count_is_flat_across_shipments(self):
        one, one_count = self._report(
            f"/api/logistics/reports/landed-cost/?shipment_id={self.shipments[0].id}"
        )
        self.assertEqual(one.data["count"], 1)

        allshipments, all_count = self._report("/api/logistics/reports/landed-cost/")
        self.assertEqual(allshipments.data["count"], 3)

        # ثلاث شحنات (٦ روابط صفقات) يجب ألا تكلّف أكثر من شحنة واحدة (رابطان).
        # قبل P1-2 كان الفرق ~24 استعلاماً؛ الآن الجلب جماعي فالعدد لا يتحرّك.
        self.assertLessEqual(all_count, one_count)

    def test_values_survive_the_batched_prefetch(self):
        """الجلب الجماعي لا يغيّر أرقام التقرير — البضاعة والشحن والصفقات."""
        response, _ = self._report(
            f"/api/logistics/reports/landed-cost/?shipment_id={self.shipments[0].id}"
        )
        row = response.data["shipments"][0]
        self.assertEqual(len(row["deals"]), 2)
        # صفقتان × (بند واحد × كمية 2 × سعر 250) = 1000
        self.assertEqual(Decimal(str(row["total_merchandise"])), Decimal("1000"))
        self.assertEqual(Decimal(str(row["total_shipping_cost_usd"])), Decimal("500"))
        for deal_row in row["deals"]:
            self.assertEqual(deal_row["items_count"], 1)
            self.assertIsNotNone(deal_row["purchase_invoice"])
            self.assertEqual(deal_row["purchase_invoice"]["items_count"], 1)
