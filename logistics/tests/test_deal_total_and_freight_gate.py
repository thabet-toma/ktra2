"""إجمالي الصفقة مشتق دائماً + بوابة الاستيراد تقبل استحقاق الشحن.

عَرَضان أبلغ عنهما المالك على نفس الشحنة:
1. «دافع المبلغ كلّه ومع ذلك يقول رصيد لصالحك عند المورد» — نسبة إنجاز 101.7%
   ورصيد وهمي = «شحن داخل الصين» بالضبط.
2. «يقول مش مدفوع ومبيّن دافع» — بوابة الاستيراد تطلب دفع وكيل الشحن بالكامل
   بينما شاشة الرحلة تعتبر الاستحقاق كافياً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.services import create_fiscal_year
from inventory.models import Product
from logistics.models import LogisticsDeal, LogisticsDealItem, LogisticsShipment
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class DealTotalIsAlwaysDerivedTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="deal-total", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة إجمالي الصفقة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد صيني", partner_type="Supplier")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="SKU-TOT-1", name_ar="بطارية",
            quantity_on_hand=0, avg_cost=D("0"),
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _deal_with_goods(self, goods="20140"):
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-TOT-1", partner=self.supplier,
            currency=Currency.objects.get(Code="ILS"), order_date="2026-07-01",
            total_amount=D(goods), subtotal=D(goods),
        )
        LogisticsDealItem.objects.create(
            deal=deal, product=self.product, quantity=D("1"), unit_price=D(goods),
        )
        return deal

    def test_editing_only_shipping_recomputes_total(self):
        deal = self._deal_with_goods()
        resp = self.client.patch(
            f"/api/logistics/deals/{deal.pk}/",
            {"shipping_cost_estimate": "339"},
            format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        deal.refresh_from_db()
        # 20140 بضاعة + 339 شحن داخل الصين — لا 20140 وحدها
        self.assertEqual(deal.total_amount, D("20479.00"))

    def test_shipping_included_is_not_added_twice(self):
        deal = self._deal_with_goods()
        resp = self.client.patch(
            f"/api/logistics/deals/{deal.pk}/",
            {"shipping_cost_estimate": "339", "is_shipping_included": True},
            format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        deal.refresh_from_db()
        self.assertEqual(deal.total_amount, D("20140.00"))

    def test_editing_only_discount_recomputes_total(self):
        deal = self._deal_with_goods()
        resp = self.client.patch(
            f"/api/logistics/deals/{deal.pk}/",
            {"discount_amount": "140"},
            format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        deal.refresh_from_db()
        self.assertEqual(deal.total_amount, D("20000.00"))


class FreightGateAcceptsAccrualTest(APITestCase):
    """بوابة الاستيراد: الاستحقاق يثبّت التكلفة فلا يلزم دفع الوكيل."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="freight-gate", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة بوابة الشحن", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.agent = Partner.objects.create(
            tenant=cls.tenant, name="وكيل الشحن", partner_type="FreightForwarder")

    def test_unpaid_freight_with_posted_accrual_is_established(self):
        from logistics.landed_cost import shipment_freight_ils

        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-GATE-1",
            shipping_agent=self.agent, total_shipping_cost_usd=D("1280.4"),
            freight_is_posted=True, freight_exchange_rate=D("3.6"),
        )
        total_ils, _, _, unpaid = shipment_freight_ils(shipment, D("3.6"))
        # غير مدفوع فعلاً، لكن الاستحقاق حكم التكلفة
        self.assertEqual(unpaid, D("1280.40"))
        self.assertEqual(total_ils, D("4609.44"))
        established = (
            shipment.freight_is_posted
            or unpaid <= D("0.02")
            or D(shipment.total_shipping_cost_usd) <= 0
        )
        self.assertTrue(established)

    def test_unpaid_freight_without_accrual_is_not_established(self):
        from logistics.landed_cost import shipment_freight_ils

        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-GATE-2",
            shipping_agent=self.agent, total_shipping_cost_usd=D("1280.4"),
        )
        _, _, _, unpaid = shipment_freight_ils(shipment, D("3.6"))
        established = (
            shipment.freight_is_posted
            or unpaid <= D("0.02")
            or D(shipment.total_shipping_cost_usd) <= 0
        )
        self.assertFalse(established)


class SupplierOverpaymentBecomesAdvanceTest(APITestCase):
    """الدفع الزائد للمورد مسموح — الفائض دفعة مقدمة تجعله مديناً لنا.

    شكوى المالك: «شو مشكلتك تمنعني ادفع أكثر للمورد، ليش ما تحطني دائن بالمبلغ
    اللي ضايل». كان السقف يرفض أي مجموع يتجاوز إجمالي الصفقة.
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="sup-over", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة دفع زائد", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="SKU-OVER-1", name_ar="منتج",
            quantity_on_hand=0, avg_cost=D("0"),
        )

    def setUp(self):
        self.deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-OVER-1", partner=self.supplier,
            currency=self.ils, order_date="2026-07-01",
            total_amount=D("1000"), subtotal=D("1000"),
        )
        LogisticsDealItem.objects.create(
            deal=self.deal, product=self.product, quantity=D("1"), unit_price=D("1000"),
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_payment_exceeding_deal_total_is_accepted(self):
        resp = self.client.post(
            f"/api/logistics/deals/{self.deal.pk}/payments/",
            {"amount": "1200", "transfer_date": "2026-07-02"},
            format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_supplier_advance_is_reported_on_the_deal(self):
        created = self.client.post(
            f"/api/logistics/deals/{self.deal.pk}/payments/",
            {"amount": "1200", "transfer_date": "2026-07-02"},
            format="json", **self._auth(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        # الرصيد يُحتسب من الدفعات المرحّلة وحدها
        self.deal.payments.update(is_posted=True)

        detail = self.client.get(
            f"/api/logistics/deals/{self.deal.pk}/", **self._auth())
        self.assertEqual(detail.status_code, 200, detail.content)
        body = detail.json()
        # لا متبقٍ، والفائض 200 يظهر كرصيد لصالحنا عند المورد
        self.assertEqual(D(body["amount_outstanding"]), D("0"))
        self.assertEqual(D(body["supplier_advance"]), D("200.00"))

    def test_posting_cap_no_longer_blocks_overpayment(self):
        from logistics.payment_posting_cap import posting_cap_check

        ok, err = posting_cap_check(self.deal, D("5000"))
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_deal_without_total_still_requires_a_value_before_posting(self):
        from logistics.payment_posting_cap import posting_cap_check

        self.deal.total_amount = D("0")
        ok, err = posting_cap_check(self.deal, D("100"))
        self.assertFalse(ok)
        self.assertIn("إجمالي الصفقة", err)
