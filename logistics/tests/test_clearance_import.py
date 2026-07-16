"""استيراد فواتير شراء من تخليص جمركي (مراجعة رحلة الاستيراد).

كان الاستيراد يفشل بـ TypeError لأن import_invoices_from_clearance ظل يمرّر
local_payments_json/conversion_metadata_json المحذوفين في هجرة 0035 (P-D-8)،
وكان GET للفاتورة الدولية غير المرحّلة يفشل بـ AttributeError للسبب نفسه.
تشغيل: python manage.py test logistics.tests.test_clearance_import --settings=core.test_settings
"""
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from inventory.models import Product
from logistics.models import (
    LogisticsClearance,
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsPayment,
    LogisticsShipment,
    LogisticsShipmentDeal,
    LocalShipment,
    PurchaseInvoice,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class ClearanceImportTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="impmgr", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة الاستيراد", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مصنع الكوابل", partner_type="Supplier")
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number="D-0042", partner=cls.partner,
            order_date="2026-06-01", total_amount=Decimal("1997"),
            currency=cls.usd, description="شحنة الكوابل الانفيرتر الاصفر",
            total_cbm=Decimal("5"))
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-0001",
            shipment_name="شحنة الكوابل الانفيرتر الاصفر",
            total_shipping_cost_usd=Decimal("1326.84"))
        LogisticsShipmentDeal.objects.create(shipment=cls.shipment, deal=cls.deal)
        # دفعة وكيل شحن مؤكّدة تغطي كامل تكلفة الشحن (شرط الاستيراد)
        LogisticsPayment.objects.create(
            shipment=cls.shipment, amount=Decimal("1326.84"),
            usd_to_ils=Decimal("3.6"), status="Confirmed")
        # دفعة صفقة تغطي قيمة الصفقة (شرط الاستيراد)
        LogisticsPayment.objects.create(
            deal=cls.deal, amount=Decimal("1997"),
            usd_to_ils=Decimal("3.7"), status="Confirmed")
        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, declaration_number="CL-1")

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _import(self):
        return self.client.post(
            "/api/logistics/purchase-invoices/import-from-clearance/",
            {"clearance_id": self.clearance.id, "deal_ids": [self.deal.id],
             "deal_remaining_rate": "3.7", "shipment_remaining_rate": "3.65"},
            format="json", **self._auth())

    def _second_deal(self):
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-0043", partner=self.partner,
            order_date="2026-06-02", total_amount=Decimal("1000"),
            currency=self.usd, description="الصفقة الثانية في نفس الشحنة",
            total_cbm=Decimal("5"),
        )
        LogisticsShipmentDeal.objects.create(shipment=self.shipment, deal=deal)
        LogisticsPayment.objects.create(
            deal=deal, amount=Decimal("1000"), usd_to_ils=Decimal("3.7"),
            status="Confirmed",
        )
        return deal

    def test_import_creates_international_invoice(self):
        resp = self._import()
        self.assertEqual(resp.status_code, 201, resp.content)
        inv = PurchaseInvoice.objects.get(tenant=self.tenant, deal=self.deal)
        self.assertEqual(inv.invoice_type, PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL)
        self.assertEqual(inv.clearance_id, self.clearance.id)
        self.assertEqual(inv.shipment_id, self.shipment.id)
        # معاملات الاستيراد محفوظة بأعمدة منمّطة (بديل JSON المحذوف في P-D-8)
        self.assertEqual(inv.import_deal_remaining_rate, Decimal("3.7"))
        self.assertEqual(inv.import_shipment_remaining_rate, Decimal("3.65"))
        self.assertGreater(inv.grand_total, 0)

    def test_detail_get_after_import(self):
        """GET للفاتورة الدولية غير المرحّلة يجب ألا ينهار على الحقول المحذوفة."""
        resp = self._import()
        self.assertEqual(resp.status_code, 201, resp.content)
        inv = PurchaseInvoice.objects.get(tenant=self.tenant, deal=self.deal)
        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.id}/", **self._auth())
        self.assertEqual(detail.status_code, 200, detail.content)
        body = detail.json()
        # الـpayload الحي يعيد بناء بيانات التحويل بنفس الأسعار المحفوظة
        conv = body.get("conversion_metadata_json") or {}
        self.assertEqual(conv.get("remaining_balance_rate_deal"), 3.7)
        self.assertEqual(conv.get("remaining_balance_rate_shipment"), 3.65)

    def test_recalculate_after_import(self):
        resp = self._import()
        self.assertEqual(resp.status_code, 201, resp.content)
        recalc = self.client.post(
            "/api/logistics/purchase-invoices/recalculate-landed-cost/",
            {"shipment_id": self.shipment.id,
             "deal_remaining_rate": "3.8", "shipment_remaining_rate": "3.8"},
            format="json", **self._auth())
        self.assertEqual(recalc.status_code, 200, recalc.content)
        self.assertEqual(recalc.json().get("updated"), 1)
        inv = PurchaseInvoice.objects.get(tenant=self.tenant, deal=self.deal)
        self.assertEqual(inv.import_deal_remaining_rate, Decimal("3.8"))

    def test_auto_recalculate_reposts_only_previously_posted_invoice(self):
        ap = Account.objects.filter(tenant=self.tenant, code="2101").first()
        if ap is None:
            ap = Account.objects.create(
                tenant=self.tenant, code="2101", name="ذمم الموردين",
                account_type="Liability", is_active=True,
            )
        self.partner.linked_account = ap
        self.partner.save(update_fields=["linked_account"])
        product = Product.objects.create(
            tenant=self.tenant, sku="IMP-RECALC-1", name_ar="صنف إعادة الاحتساب",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"),
        )
        LogisticsDealItem.objects.create(
            deal=self.deal, product=product, quantity=Decimal("1"),
            unit_price=Decimal("1997"),
        )

        imported = self._import()
        self.assertEqual(imported.status_code, 201, imported.content)
        invoice = PurchaseInvoice.objects.get(tenant=self.tenant, deal=self.deal)
        posted = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.id}/post-to-accounting/",
            {}, format="json", **self._auth(),
        )
        self.assertEqual(posted.status_code, 201, posted.content)
        invoice.refresh_from_db()
        old_subtotal = invoice.subtotal
        self.assertTrue(invoice.is_posted)

        LocalShipment.objects.create(
            tenant=self.tenant, shipment=self.shipment, clearance=self.clearance,
            carrier=self.partner, amount=Decimal("450"), currency=self.ils,
            exchange_rate=Decimal("1"), status="delivered",
            capitalize_to_inventory=True,
        )
        recalc = self.client.post(
            "/api/logistics/purchase-invoices/recalculate-landed-cost/",
            {"shipment_id": self.shipment.id, "auto_repost": True},
            format="json", **self._auth(),
        )
        self.assertEqual(recalc.status_code, 200, recalc.content)
        self.assertEqual(recalc.json()["reconciliation"]["reposted"], 1)
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_posted)
        self.assertGreater(invoice.subtotal, old_subtotal)
        self.assertEqual(
            JournalHeader.objects.filter(
                tenant=self.tenant, reference_type="PURCHASE_INVOICE",
                reference_id=invoice.id, is_posted=True,
            ).count(),
            1,
        )

    def test_import_does_not_require_clearance_or_local_transport_payment(self):
        LocalShipment.objects.create(
            tenant=self.tenant, shipment=self.shipment, clearance=self.clearance,
            carrier=self.partner, amount=Decimal("450"), currency=self.ils,
            exchange_rate=Decimal("1"), status="delivered",
        )
        resp = self._import()
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(PurchaseInvoice.objects.filter(
            tenant=self.tenant, deal=self.deal, clearance=self.clearance,
        ).exists())

    def test_local_transport_cost_is_allocated_into_import_invoice_before_payment(self):
        LocalShipment.objects.create(
            tenant=self.tenant, shipment=self.shipment, clearance=self.clearance,
            carrier=self.partner, amount=Decimal("2000"), currency=self.ils,
            exchange_rate=Decimal("1"), status="delivered",
            capitalize_to_inventory=True,
        )

        preview = self.client.post(
            "/api/logistics/purchase-invoices/preview-clearance-import/",
            {"clearance_id": self.clearance.id, "deal_ids": [self.deal.id],
             "deal_remaining_rate": "3.7", "shipment_remaining_rate": "3.65"},
            format="json", **self._auth(),
        )
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(
            Decimal(str(preview.json()["local_transport_total_ils"])),
            Decimal("2000.0"),
        )
        self.assertEqual(
            Decimal(str(preview.json()["deals"][0]["allocated_local_transport_ils"])),
            Decimal("2000.0"),
        )

        imported = self._import()
        self.assertEqual(imported.status_code, 201, imported.content)
        invoice = PurchaseInvoice.objects.get(tenant=self.tenant, deal=self.deal)
        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{invoice.id}/", **self._auth(),
        )
        metadata = detail.json()["conversion_metadata_json"]
        self.assertEqual(
            Decimal(str(metadata["deal_local_transport_ils"])), Decimal("2000.0"),
        )
        self.assertEqual(invoice.payments.count(), 0)

    def test_live_detail_reconciles_tax_and_payable_after_landed_cost_changes(self):
        LogisticsDeal.objects.filter(pk=self.deal.pk).update(
            tax_type="percentage", tax_rate=Decimal("16"), discount_amount=Decimal("0"),
        )
        self.deal.refresh_from_db()
        imported = self._import()
        self.assertEqual(imported.status_code, 201, imported.content)
        invoice = PurchaseInvoice.objects.get(tenant=self.tenant, deal=self.deal)

        LocalShipment.objects.create(
            tenant=self.tenant, shipment=self.shipment, clearance=self.clearance,
            carrier=self.partner, amount=Decimal("450"), currency=self.ils,
            exchange_rate=Decimal("1"), status="delivered",
            capitalize_to_inventory=True,
        )

        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{invoice.id}/", **self._auth(),
        )
        self.assertEqual(detail.status_code, 200, detail.content)
        body = detail.json()
        subtotal = Decimal(str(body["subtotal"]))
        expected_tax = (subtotal * Decimal("0.16")).quantize(Decimal("0.01"))
        expected_grand = (subtotal + expected_tax).quantize(Decimal("0.01"))
        self.assertEqual(Decimal(str(body["tax_amount"])), expected_tax)
        self.assertEqual(Decimal(str(body["grand_total"])), expected_grand)
        self.assertEqual(Decimal(str(body["payable_total"])), expected_grand)

    def test_partial_import_keeps_remaining_deal_available_and_rejects_duplicate(self):
        second = self._second_deal()

        first = self._import()
        self.assertEqual(first.status_code, 201, first.content)
        options = self.client.get(
            f"/api/logistics/purchase-invoices/clearance-import-options/"
            f"?clearance_id={self.clearance.id}",
            **self._auth(),
        )
        self.assertEqual(options.status_code, 200, options.content)
        by_deal = {row["deal_id"]: row for row in options.json()["deals"]}
        self.assertTrue(by_deal[self.deal.id]["is_converted"])
        self.assertFalse(by_deal[second.id]["is_converted"])
        self.assertIsNotNone(by_deal[self.deal.id]["invoice_id"])

        second_import = self.client.post(
            "/api/logistics/purchase-invoices/import-from-clearance/",
            {"clearance_id": self.clearance.id, "deal_ids": [second.id],
             "deal_remaining_rate": "3.7", "shipment_remaining_rate": "3.65"},
            format="json", **self._auth(),
        )
        self.assertEqual(second_import.status_code, 201, second_import.content)
        self.assertEqual(PurchaseInvoice.objects.filter(
            tenant=self.tenant, shipment=self.shipment, is_return=False,
        ).count(), 2)

        duplicate = self._import()
        self.assertEqual(duplicate.status_code, 400, duplicate.content)
        self.assertIn("محوّلة", duplicate.json()["error"])
        self.assertEqual(PurchaseInvoice.objects.filter(
            tenant=self.tenant, shipment=self.shipment, is_return=False,
        ).count(), 2)

    def test_import_journey_lists_filter_by_shipment(self):
        other_shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-OTHER",
        )
        other_clearance = LogisticsClearance.objects.create(
            tenant=self.tenant, shipment=other_shipment, declaration_number="CL-OTHER",
        )
        own_local = LocalShipment.objects.create(
            tenant=self.tenant, shipment=self.shipment, clearance=self.clearance,
            carrier=self.partner, amount=Decimal("10"), currency=self.ils,
        )
        LocalShipment.objects.create(
            tenant=self.tenant, shipment=other_shipment, clearance=other_clearance,
            carrier=self.partner, amount=Decimal("20"), currency=self.ils,
        )

        clearances = self.client.get(
            f"/api/logistics/clearances/?shipment={self.shipment.id}", **self._auth(),
        )
        local_shipments = self.client.get(
            f"/api/logistics/local-shipments/?shipment={self.shipment.id}", **self._auth(),
        )

        self.assertEqual(clearances.status_code, 200, clearances.content)
        self.assertEqual([row["id"] for row in clearances.json()], [self.clearance.id])
        self.assertEqual(local_shipments.status_code, 200, local_shipments.content)
        self.assertEqual([row["id"] for row in local_shipments.json()], [own_local.id])


class DealTitlePriorityTest(SimpleTestCase):
    """توحيد عنوان الصفقة (شكوى «مرة إنجليزي مرة رقم مرة عربي» في ملخص الشحنة):
    - نص إنجليزي أطول من 80 حرفاً ليس اسم صفقة (فقرات شروط/شهادات).
    - الاسم العربي المخزّن قديماً في «رقم العرض» يتقدم على الوصف الإنجليزي.
    """

    @staticmethod
    def _deal(description=None, notes=None, offer=None, ref="D-0091"):
        return SimpleNamespace(
            description=description, notes=notes,
            original_offer_number=offer, ref_number=ref,
        )

    def test_long_english_blob_loses_to_arabic_offer(self):
        from logistics.landed_cost import invoice_title_from_deal
        blob = (
            "f the goods fail to ship from China, we will refund you the money 2. "
            "Provide UN38.3, MSDS, and dangerous goods packaging certificate…"
        )
        deal = self._deal(description=blob, offer="بطاريتين 15 كيلو", ref="D-0091")
        self.assertEqual(invoice_title_from_deal(deal), "بطاريتين 15 كيلو")

    def test_bare_ref_with_arabic_offer_uses_offer(self):
        from logistics.landed_cost import invoice_title_from_deal
        deal = self._deal(offer="طلبية سماعات ايفون كوبي 2025", ref="D-0085")
        self.assertEqual(invoice_title_from_deal(deal), "طلبية سماعات ايفون كوبي 2025")

    def test_short_english_name_still_allowed(self):
        from logistics.landed_cost import invoice_title_from_deal
        deal = self._deal(description="Yellow inverter cable 6.2m", ref="D-0096")
        self.assertEqual(invoice_title_from_deal(deal), "Yellow inverter cable 6.2m")

    def test_arabic_description_beats_arabic_offer(self):
        from logistics.landed_cost import invoice_title_from_deal
        deal = self._deal(description="شحنة الكوابل", offer="بطاريتين 15 كيلو")
        self.assertEqual(invoice_title_from_deal(deal), "شحنة الكوابل")

    def test_long_english_is_boilerplate(self):
        from logistics.text_utils import is_english_payment_or_legal_boilerplate
        self.assertTrue(is_english_payment_or_legal_boilerplate("x" * 81))
        self.assertFalse(is_english_payment_or_legal_boilerplate("Yellow inverter cable 6.2m"))

    def test_list_preview_prefers_arabic_offer(self):
        from logistics.serializers import _deal_title_for_list_preview
        deal = SimpleNamespace(
            short_name="", description="Terms paragraph " + "y" * 80,
            notes="", ref_number="D-0085",
            original_offer_number="طلبية سماعات ايفون كوبي 2025",
        )
        self.assertEqual(_deal_title_for_list_preview(deal), "طلبية سماعات ايفون كوبي 2025")
