"""T-PSIMPL — ما كان في جانب البيع وحده: نسخُ الفاتورة، الرقم التالي، توزيع FIFO.

ثلاثة فوارق صغيرة لكنها تُقاس يومياً: مشترٍ يعيد كتابة فاتورةٍ متكرّرة بندًا
بندًا، ومحرّرٌ يفتح بلا رقم حتى يُحفظ، وتوزيعُ سندٍ كبير على فواتير مورّد يُحسب
على ورقة.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class PurchaseParityExtrasTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="psimpl", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة التبسيط", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-S", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد متكرّر", partner_type="Supplier",
            linked_account=cls.ap)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="PS-1", name_ar="منتج متكرّر",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number, total="300.00", due_offset=None):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.partner,
            currency=self.ils, invoice_date=timezone.localdate(),
            due_date=(timezone.localdate() + datetime.timedelta(days=due_offset))
            if due_offset is not None else None,
            exchange_rate=Decimal("1"), grand_total=Decimal(total))
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="منتج متكرّر",
            quantity=Decimal("3"), unit_price=Decimal("100"),
            total_price=Decimal(total))
        return inv

    # ── الرقم التالي ───────────────────────────────────────────────────────
    def test_next_number_is_available_before_saving(self):
        res = self.client.get(
            "/api/logistics/purchase-invoices/next-number/", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()["invoice_number"], res.json()

    # ── النسخ ──────────────────────────────────────────────────────────────
    def test_duplicate_copies_the_purchase_not_its_history(self):
        source = self._invoice("PINV-DUP-1")
        self.client.post(
            f"/api/logistics/purchase-invoices/{source.pk}/post-to-accounting/",
            {"receive_on_post": True}, format="json", **self._auth())
        source.refresh_from_db()
        assert source.is_posted is True

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{source.pk}/duplicate/",
            {}, format="json", **self._auth())
        assert res.status_code == 201, res.content
        clone = PurchaseInvoice.objects.get(pk=res.json()["id"])

        # ما يصف الشراء نفسه يُنسَخ…
        assert clone.partner_id == source.partner_id
        assert clone.grand_total == source.grand_total
        assert clone.items.count() == source.items.count()
        assert clone.items.first().product_id == self.product.id
        # …وما يخصّ نسخةً بعينها لا يُنسَخ.
        assert clone.pk != source.pk
        assert clone.invoice_number != source.invoice_number
        assert clone.is_posted is False
        assert clone.journal_id is None
        assert clone.status == "draft"
        assert clone.receipt_status == PurchaseInvoice.RECEIPT_NOT
        assert clone.items.first().received_quantity == Decimal("0")
        assert clone.due_date is None, "الاستحقاق يُعاد حسابه للنسخة الجديدة"

    def test_duplicate_of_an_import_invoice_becomes_a_local_draft(self):
        """النسخة لا ترث ارتباط مسار الاستيراد — لا صفقة ولا شحنة تدّعيها.

        الفاتورة الدولية محجوبةٌ عمّن لا يملك وحدة الاستيراد (404 لا 403)،
        فتُفعَّل للشركة هنا كي يصل الاختبار إلى المستند أصلاً."""
        self.tenant.import_enabled = True
        self.tenant.save(update_fields=["import_enabled"])
        source = self._invoice("PINV-DUP-2")
        PurchaseInvoice.objects.filter(pk=source.pk).update(
            invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL)
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{source.pk}/duplicate/",
            {}, format="json", **self._auth())
        assert res.status_code == 201, res.content
        clone = PurchaseInvoice.objects.get(pk=res.json()["id"])
        assert clone.invoice_type == PurchaseInvoice.INVOICE_TYPE_LOCAL
        assert clone.deal_id is None and clone.shipment_id is None

    # ── اقتراح توزيع FIFO ──────────────────────────────────────────────────
    def test_fifo_suggestion_fills_the_earliest_due_first(self):
        older = self._invoice("PINV-FIFO-1", "300.00", due_offset=-10)
        newer = self._invoice("PINV-FIFO-2", "300.00", due_offset=5)
        for inv in (older, newer):
            self.client.post(
                f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
                {}, format="json", **self._auth())

        res = self.client.get(
            f"/api/logistics/supplier-payments/suggest-fifo-allocations/"
            f"?partner={self.partner.id}&amount=400",
            **self._auth())
        assert res.status_code == 200, res.content
        rows = res.json()["allocations"]
        assert [r["invoice"] for r in rows] == [older.pk, newer.pk], rows
        assert Decimal(rows[0]["amount"]) == Decimal("300.00")
        assert Decimal(rows[1]["amount"]) == Decimal("100.00"), "المبلغ يُقصّ عند نفاده"

    def test_fifo_suggestion_skips_settled_invoices(self):
        paid = self._invoice("PINV-FIFO-3", "300.00", due_offset=-20)
        cash = Account.objects.create(
            tenant=self.tenant, code="1110-S", name="صندوق",
            account_type="Asset", is_active=True)
        self.client.post(
            f"/api/logistics/purchase-invoices/{paid.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        settled = self.client.post(
            f"/api/logistics/purchase-invoices/{paid.pk}/pay/",
            {"cash": "300.00", "cash_account_id": cash.id},
            format="json", **self._auth())
        assert settled.status_code == 200, settled.content

        res = self.client.get(
            f"/api/logistics/supplier-payments/suggest-fifo-allocations/"
            f"?partner={self.partner.id}&amount=500", **self._auth())
        assert [r["invoice"] for r in res.json()["allocations"]] == []

    def test_fifo_suggestion_requires_a_partner(self):
        res = self.client.get(
            "/api/logistics/supplier-payments/suggest-fifo-allocations/?amount=100",
            **self._auth())
        assert res.status_code == 400, res.content
