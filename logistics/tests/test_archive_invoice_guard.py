"""حارس فاتورة صفقة الأرشيف: قيد LOGISTICS_DEAL الحيّ يمنع ترحيل فاتورتها الدولية.

صفقة الأرشيف دُوئن موردها ودُيِّنت مصروفاتها بقيد الصفقة القديم، ودخلت بضاعتها
المخزون من الشحنة — فترحيل فاتورتها الدولية يدائن المورد ويُدخل التكلفة مرّةً ثانية.
القيد المعكوس بـJOURNAL_REVERSAL ليس حيّاً فلا يمنع.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
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
from logistics.payment_posting import deal_has_live_archive_journal, live_archive_deal_journals
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class ArchiveInvoiceGuardTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="archguard", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة الأرشيف", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)
        ap = Account.objects.filter(tenant=cls.tenant, code="2101").first() or Account.objects.create(
            tenant=cls.tenant, code="2101", name="ذمم الموردين", account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مصنع الأرشيف", partner_type="Supplier", linked_account=ap)
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-0014", total_shipping_cost_usd=Decimal("500"))
        LogisticsPayment.objects.create(
            shipment=cls.shipment, amount=Decimal("500"), usd_to_ils=Decimal("3.6"), status="Confirmed")
        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, declaration_number="CL-A")
        cls.archive = cls._deal("D-0103", Decimal("1000"))
        cls.modern = cls._deal("D-0200", Decimal("800"))

    @classmethod
    def _deal(cls, ref, usd):
        deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number=ref, partner=cls.partner, order_date="2026-06-01",
            total_amount=usd, total_cbm=Decimal("5"))
        LogisticsShipmentDeal.objects.create(shipment=cls.shipment, deal=deal)
        LogisticsPayment.objects.create(deal=deal, amount=usd, usd_to_ils=Decimal("3.7"), status="Confirmed")
        product = Product.objects.create(
            tenant=cls.tenant, sku=f"ARC-{ref}", name_ar=f"منتج {ref}",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        LogisticsDealItem.objects.create(deal=deal, product=product, quantity=Decimal("1"), unit_price=usd)
        return deal

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _import(self, *deals):
        resp = self.client.post(
            "/api/logistics/purchase-invoices/import-from-clearance/",
            {"clearance_id": self.clearance.id, "deal_ids": [d.id for d in deals],
             "deal_remaining_rate": "3.7", "shipment_remaining_rate": "3.6"},
            format="json", **self._auth())
        self.assertEqual(resp.status_code, 201, resp.content)
        return [PurchaseInvoice.objects.get(tenant=self.tenant, deal=d, is_return=False) for d in deals]

    def _post(self, invoice):
        return self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.id}/post-to-accounting/", {},
            format="json", **self._auth())

    def _deal_journal(self, deal):
        return JournalHeader.objects.create(
            tenant=self.tenant, transaction_date="2026-06-01", is_posted=True,
            reference_type="LOGISTICS_DEAL", reference_id=deal.pk, description="شراء بضاعة (Auto)")

    def _assert_archive_message(self, text, journal):
        self.assertIn("صفقة أرشيف D-0103", text)
        self.assertIn(f"قيد الصفقة #{journal.pk}", text)
        self.assertIn("للاطلاع فقط", text)

    def test_live_deal_journal_blocks_every_post_path(self):
        (invoice,) = self._import(self.archive)
        journal = self._deal_journal(self.archive)

        direct = self._post(invoice)
        self.assertEqual(direct.status_code, 400, direct.content)
        self._assert_archive_message(direct.json()["error"], journal)

        paid = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.id}/pay/",
            {"post_invoice": True, "cash": "10"}, format="json", **self._auth())
        self.assertEqual(paid.status_code, 400, paid.content)
        self._assert_archive_message(paid.json()["error"], journal)

        invoice.refresh_from_db()
        self.assertFalse(invoice.is_posted)
        self.assertFalse(JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="PURCHASE_INVOICE", reference_id=invoice.pk).exists())

    def test_reversed_deal_journal_is_not_live(self):
        (invoice,) = self._import(self.archive)
        journal = self._deal_journal(self.archive)
        JournalHeader.objects.create(
            tenant=self.tenant, transaction_date="2026-07-01", is_posted=True,
            reference_type="JOURNAL_REVERSAL", reference_id=journal.pk,
            description=f"عكس قيد #{journal.pk}")

        self.assertIsNone(deal_has_live_archive_journal(self.archive))
        resp = self._post(invoice)
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_new_deal_without_deal_journal_posts_as_before(self):
        (invoice,) = self._import(self.modern)
        self.assertEqual(live_archive_deal_journals(self.tenant.TenantID, [self.modern.pk]), {})
        resp = self._post(invoice)
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_live_journal_ignores_posted_invoice_unlike_archive_deal_ids(self):
        """`archive_deal_ids` تُسقط صفقةً لها فاتورة مرحّلة؛ الحارس لا: القيد حيّ."""
        from logistics.payment_posting import archive_deal_ids

        (invoice,) = self._import(self.archive)
        self.assertEqual(self._post(invoice).status_code, 201)
        journal = self._deal_journal(self.archive)
        self.assertNotIn(self.archive.pk, archive_deal_ids(self.tenant.TenantID, [self.archive.pk]))
        self.assertEqual(deal_has_live_archive_journal(self.archive), journal.pk)

    def test_shipment_repost_skips_archive_invoice_and_reposts_the_other(self):
        archive_inv, modern_inv = self._import(self.archive, self.modern)
        for invoice in (archive_inv, modern_inv):
            self.assertEqual(self._post(invoice).status_code, 201)
        archive_inv.refresh_from_db()
        archive_journal_id = archive_inv.journal_id
        deal_journal = self._deal_journal(self.archive)

        LocalShipment.objects.create(
            tenant=self.tenant, shipment=self.shipment, clearance=self.clearance,
            carrier=self.partner, amount=Decimal("450"), currency=self.ils,
            exchange_rate=Decimal("1"), status="delivered", capitalize_to_inventory=True)
        resp = self.client.post(
            "/api/logistics/purchase-invoices/recalculate-landed-cost/",
            {"shipment_id": self.shipment.id, "auto_repost": True}, format="json", **self._auth())
        self.assertEqual(resp.status_code, 200, resp.content)
        rec = resp.json()["reconciliation"]
        self.assertEqual(rec["reposted"], 1)
        (skipped,) = rec["skipped_archive"]
        self.assertEqual(skipped["invoice_number"], archive_inv.invoice_number)
        self._assert_archive_message(skipped["reason"], deal_journal)

        archive_inv.refresh_from_db()
        modern_inv.refresh_from_db()
        self.assertTrue(archive_inv.is_posted)
        self.assertEqual(archive_inv.journal_id, archive_journal_id, "فاتورة الأرشيف لم تُلمس")
        self.assertTrue(modern_inv.is_posted)

    def test_serializer_flags_lock_with_constant_queries(self):
        archive_inv, modern_inv = self._import(self.archive, self.modern)
        journal = self._deal_journal(self.archive)

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get("/api/logistics/purchase-invoices/", **self._auth())
        self.assertEqual(resp.status_code, 200, resp.content)
        rows = {r["id"]: r for r in resp.json()["results"]}
        self.assertTrue(rows[archive_inv.id]["is_archive_locked"])
        self._assert_archive_message(rows[archive_inv.id]["archive_lock_reason"], journal)
        self.assertFalse(rows[modern_inv.id]["is_archive_locked"])
        self.assertIsNone(rows[modern_inv.id]["archive_lock_reason"])
        deal_queries = [q for q in ctx.captured_queries if "LOGISTICS_DEAL" in q["sql"]]
        self.assertEqual(len(deal_queries), 1, "قيود الصفقات تُجلب للصفحة باستعلامٍ واحد")

        detail = self.client.get(f"/api/logistics/purchase-invoices/{archive_inv.id}/", **self._auth())
        self.assertTrue(detail.json()["is_archive_locked"])
