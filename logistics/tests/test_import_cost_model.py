"""متوسط تكلفة الاستيراد (`Product.avg_cost`) مشتقٌّ من طبقات FIFO المفتوحة فقط.

استلام الشحنة (`receive_shipment_stock`) وإلغاء ترحيلها يعكسان طبقات FIFO المفتوحة:
- عند وجود طبقات مفتوحة (بما فيها بعد تسوية طبقة مؤقتة سالبة) يساوي `avg_cost`
  متوسط الطبقات المفتوحة (`derived_avg_cost`).
- عند إفراغ المخزون إلى صفر (مثل إلغاء الترحيل) يصبح `avg_cost` صفراً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.services import create_fiscal_year
from inventory.models import Product, StockMovement
from inventory.services import receive_shipment_stock, record_stock_movement
from logistics.models import (
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsShipment,
    LogisticsShipmentDeal,
    PurchaseInvoice,
    PurchaseInvoiceItem,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class ImportCostModelTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="imp", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الاستيراد", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مصنع صيني", partner_type="Supplier")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="IMP-1", name_ar="إطار",
            quantity_on_hand=D("0"), avg_cost=D("0"))

    def _make_flow(self, *, qty="10", deal_price="500", landed_total="6000",
                   invoice_posted=True):
        """صفقة + شحنة + فاتورة دولية بلاندد كوست (تشمل حصة التخليص)."""
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number=f"D-{LogisticsDeal.objects.count()+1:04d}",
            partner=self.partner, order_date="2026-07-01", total_amount=D("5000"))
        LogisticsDealItem.objects.create(
            deal=deal, product=self.product, quantity=D(qty), unit_price=D(deal_price))
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant,
            shipment_number=f"SH-{LogisticsShipment.objects.count()+1:04d}",
            status="Clearing")
        LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
        landed_unit = (D(landed_total) / D(qty)).quantize(D("0.0001"))
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"IMP-{PurchaseInvoice.objects.count()+1:04d}",
            partner=self.partner, currency=self.ils, invoice_date="2026-07-02",
            exchange_rate=D("1"), grand_total=D(landed_total),
            deal=deal, shipment=shipment, is_posted=invoice_posted)
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="إطار",
            quantity=D(qty), unit_price=D(deal_price),
            total_price=D(qty) * D(deal_price),
            landed_unit_price_ils=landed_unit,
            landed_line_total_ils=D(landed_total))
        return deal, shipment, inv

    def test_shipment_receive_sets_avg_cost_to_open_layers_not_moving_wac(self):
        """بيع قبل وصول الشحنة (رصيد سالب) ثم استلام — يجب أن يثبت avg_cost على
        متوسط الطبقات المفتوحة (landed 600) لا على WAC المنحرف (6000÷5=1200)."""
        # بيع 5 قبل الشراء ⇒ رصيد −5 بتكلفة 0 (الانحراف الكلاسيكي)
        record_stock_movement(
            product=self.product, movement_type="OUT", quantity=D("5"),
            unit_cost=D("0"), reference_type="SALE", reference_id=999,
            movement_date="2026-06-30", tenant=self.tenant)
        _, shipment, _ = self._make_flow()

        created = receive_shipment_stock(shipment)
        self.assertEqual(len(created), 1)
        # تكلفة الحركة نفسها = landed للوحدة
        self.assertEqual(created[0].unit_cost, D("600.0000"))

        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, D("5.0000"))
        # متوسط الطبقات المفتوحة (5 متبقية @ 600) = 600 — وليس 6000 ÷ 5 = 1200
        self.assertEqual(self.product.avg_cost, D("600.0000"))

    def test_shipment_receive_without_posted_invoice_sets_avg_cost_from_layer(self):
        """لا فاتورة مرحّلة ⇒ تبقى تكلفة الطبقة المفتوحة من حركة الاستلام (600)."""
        _, shipment, inv = self._make_flow(invoice_posted=False)
        receive_shipment_stock(shipment)
        self.product.refresh_from_db()
        # متوسط الطبقة المفتوحة (10 @ 600 على رصيد 0) = 600
        self.assertEqual(self.product.avg_cost, D("600.0000"))

    def test_shipment_unpost_zeros_avg_cost_when_no_open_layers(self):
        """إلغاء ترحيل الشحنة يعكس المخزون ويصفّر avg_cost عند غياب طبقات مفتوحة (qoh=0)."""
        _, shipment, _ = self._make_flow()
        receive_shipment_stock(shipment)
        # شوّه المتوسط عمداً لنتأكد أن unpost يعيده لمتوسط الطبقات المفتوحة (صفر عند qoh=0)
        Product.objects.filter(pk=self.product.pk).update(avg_cost=D("999"))

        self.client.force_authenticate(user=self.user)
        res = self.client.post(
            f"/api/logistics/shipments/{shipment.pk}/unpost/", {},
            format="json", HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        self.assertEqual(res.status_code, 200, res.content)

        self.assertFalse(StockMovement.objects.filter(
            reference_type="SHIPMENT", reference_id=shipment.pk).exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, D("0.0000"))
        self.assertEqual(self.product.avg_cost, D("0.0000"))
