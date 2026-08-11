"""P1-5: منطق تعبئة شركة دفعات اللوجستيات + اشتقاقها عند الحفظ.

`core.test_settings` يعطّل الهجرات (الجداول تُبنى من النماذج مباشرةً)، فدالة
الهجرة **لا يمسّها أي اختبار** رغم أنها هي ما سيُشغَّل على بيانات الإنتاج.
اختُبرت هنا مباشرةً كما فُعل مع هجرة نسب bridge.

ما تحرسه:
  • دفعة صفقة → شركة الصفقة · دفعة شحنة → شركة الشحنة (مطابق لما كان الـOR
    القديم يُرجعه، فلا صفٌّ يختفي من القوائم بعد تحويل الفلترة).
  • الاشتقاق عند `save()` — وهو ما يجعل الحقل جديراً بالثقة بلا تعديل كل
    موضع إنشاء.
"""
from decimal import Decimal

from django.test import TestCase

from logistics.models import (
    LogisticsDeal,
    LogisticsPayment,
    LogisticsShipment,
)
from partners.models import Partner
from tenants.models import Currency, Tenant


def _load_backfill():
    import importlib
    module = importlib.import_module(
        "logistics.migrations.0073_backfill_logistics_payment_tenant"
    )
    return module.backfill_tenant


class _Apps:
    _MODELS = {
        ("logistics", "LogisticsPayment"): LogisticsPayment,
        ("logistics", "LogisticsDeal"): LogisticsDeal,
        ("logistics", "LogisticsShipment"): LogisticsShipment,
    }

    def get_model(self, app_label, model_name):
        return self._MODELS[(app_label, model_name)]


class LogisticsPaymentTenantTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(CompanyName="دفعات أ")
        cls.tenant_b = Tenant.objects.create(CompanyName="دفعات ب")
        cls.currency = Currency.objects.create(
            Code="LPT", Symbol="$", IsBaseCurrency=False,
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant_a, name="مورد الدفعات", partner_type="Supplier",
        )
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant_a, ref_number="D-LPT-1", partner=cls.supplier,
            order_date="2026-07-01", currency=cls.currency,
            total_amount=Decimal("1000"),
        )
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant_b, shipment_number="SH-LPT-1",
        )

    def test_save_derives_tenant_from_deal(self):
        payment = LogisticsPayment.objects.create(
            deal=self.deal, amount=Decimal("100"), payment_number=1,
        )
        self.assertEqual(payment.tenant_id, self.tenant_a.TenantID)

    def test_save_derives_tenant_from_shipment(self):
        payment = LogisticsPayment.objects.create(
            shipment=self.shipment, amount=Decimal("50"), payment_number=1,
        )
        self.assertEqual(payment.tenant_id, self.tenant_b.TenantID)

    def test_explicit_tenant_is_not_overwritten(self):
        payment = LogisticsPayment.objects.create(
            deal=self.deal, amount=Decimal("10"), payment_number=2,
            tenant=self.tenant_b,
        )
        self.assertEqual(payment.tenant_id, self.tenant_b.TenantID)

    def test_backfill_fills_from_parent_documents(self):
        """الهجرة نفسها — الصفوف القائمة التي وُلدت قبل وجود الحقل."""
        from_deal = LogisticsPayment.objects.create(
            deal=self.deal, amount=Decimal("7"), payment_number=3,
        )
        from_shipment = LogisticsPayment.objects.create(
            shipment=self.shipment, amount=Decimal("8"), payment_number=3,
        )
        # محاكاة حالة ما قبل الهجرة: الحقل فارغ رغم وجود الأب.
        LogisticsPayment.objects.filter(
            pk__in=[from_deal.pk, from_shipment.pk],
        ).update(tenant=None)

        _load_backfill()(_Apps(), None)

        from_deal.refresh_from_db()
        from_shipment.refresh_from_db()
        self.assertEqual(from_deal.tenant_id, self.tenant_a.TenantID)
        self.assertEqual(from_shipment.tenant_id, self.tenant_b.TenantID)

    def test_backfill_leaves_parentless_rows_null(self):
        """دفعة بلا صفقة وبلا شحنة كانت خارج نتيجة الـOR القديم أيضاً."""
        orphan = LogisticsPayment.objects.create(
            amount=Decimal("3"), payment_number=9,
        )
        self.assertIsNone(orphan.tenant_id)
        _load_backfill()(_Apps(), None)
        orphan.refresh_from_db()
        self.assertIsNone(orphan.tenant_id)
