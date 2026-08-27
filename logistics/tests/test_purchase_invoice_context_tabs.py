"""T-PCTX — تبويبات سياق فاتورة الشراء: أثر المخزون · حساب المورّد · المرفقات.

المستند مركز سياق لا نموذج إدخال. كان جانب البيع وحده يملك هذه التبويبات الثلاث
(THA-132)، وجانب الشراء يعرض فاتورةً لا تقول ماذا فعلت بالمخزن ولا بحساب المورّد،
ولا يقبل إرفاق إيصالٍ بعد الترحيل (`_sync_attachments` معلّقٌ بمسار PATCH الذي
ترفضه الفاتورة المرحّلة) ولا حذفَ مرفقٍ أصلاً.

ويثبت الملف أيضاً أن «رصيد المورّد قبل/بعد» الصحيح يأتي من كشف الحساب لا من
الحقلين التقريبيين في السيريالايزر — وهو الدين الذي كان موثّقاً في
`docs/modules/sales.md` على أنه غير مُصلَح في جانب المورّد.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from core.models import SystemAttachment
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class PurchaseInvoiceContextTabsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pctx", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة سياق الشراء", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-X", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد السياق", partner_type="Supplier",
            linked_account=cls.ap)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110-X", name="الصندوق",
            account_type="Asset", is_active=True)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="PCTX-1", name_ar="منتج السياق",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number="PINV-CTX-1", total="500.00"):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.partner,
            currency=self.ils, invoice_date="2026-06-20",
            exchange_rate=Decimal("1"), grand_total=Decimal(total))
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="منتج السياق",
            quantity=Decimal("5"), unit_price=Decimal("100.00"),
            total_price=Decimal(total))
        return inv

    # ── 1) أثر المخزون ─────────────────────────────────────────────────────
    def test_stock_tab_says_why_it_is_empty_on_a_draft(self):
        """جدولٌ فارغ بلا تفسير يُقرأ كعطل — الحمولة تحمل سببها."""
        inv = self._invoice()
        res = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/stock-movements/", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()["results"] == []
        assert res.json()["is_posted"] is False
        assert res.json()["receipt_status"] == PurchaseInvoice.RECEIPT_NOT

    def test_stock_tab_shows_this_invoice_movements_after_receiving(self):
        inv = self._invoice("PINV-CTX-2")
        posted = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {"receive_on_post": True}, format="json", **self._auth())
        assert posted.status_code == 201, posted.content

        res = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/stock-movements/", **self._auth())
        assert res.status_code == 200, res.content
        rows = res.json()["results"]
        assert rows, "الاستلام مع الترحيل يجب أن يترك حركة على الفاتورة"
        assert all(r["reference_type"] in ("PURCHASE_INVOICE", "PURCHASE_RETURN")
                   for r in rows)
        assert any(Decimal(str(r["qty_in"])) == Decimal("5") for r in rows), rows

    def test_stock_tab_is_scoped_to_the_invoice_not_the_product(self):
        """تبويب المستند يقول ما فعلته **هذه** الفاتورة لا تاريخ المنتج."""
        first = self._invoice("PINV-CTX-3")
        self.client.post(
            f"/api/logistics/purchase-invoices/{first.pk}/post-to-accounting/",
            {"receive_on_post": True}, format="json", **self._auth())
        second = self._invoice("PINV-CTX-4")

        res = self.client.get(
            f"/api/logistics/purchase-invoices/{second.pk}/stock-movements/",
            **self._auth())
        assert res.json()["results"] == [], "حركات فاتورة أخرى لا تظهر هنا"

    # ── 2) كشف حساب المورّد ────────────────────────────────────────────────
    def test_supplier_ledger_anchors_on_this_invoice(self):
        """الرصيد قبل الفاتورة وبعدها من كشف الحساب نفسه — لا حساب ثانٍ ينحرف."""
        inv = self._invoice("PINV-CTX-5")
        posted = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        assert posted.status_code == 201, posted.content

        res = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/supplier-ledger/", **self._auth())
        assert res.status_code == 200, res.content
        data = res.json()
        assert data["supplier_name"] == "مورد السياق"
        assert data["anchor"] is not None, "الفاتورة المرحّلة لها مرساة في الكشف"
        anchor = data["anchor"]
        # الفاتورة تدائن ذمم المورد بكامل إجماليها ⇒ أثرها 500 لا صفر.
        assert Decimal(str(anchor["balance_after"])) - Decimal(str(anchor["balance_before"])) \
            == Decimal("500.00")

    def test_supplier_ledger_on_a_draft_declares_no_anchor(self):
        """فاتورة بلا قيد لم تمسّ الحساب — حالةٌ معلنة لا صفرٌ ولا خطأ."""
        inv = self._invoice("PINV-CTX-6")
        res = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/supplier-ledger/", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()["anchor"] is None

    def test_paid_invoice_effect_is_its_total_not_zero(self):
        """الحقل التقريبي في السيريالايزر يقول صفراً للمسدَّدة — والكشف يقول
        الحقيقة: قيد الفاتورة دائنُ ذمم بكامل الإجمالي والدفع قيدٌ منفصل."""
        inv = self._invoice("PINV-CTX-7")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        paid = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/pay/",
            {"cash": "500.00", "cash_account_id": self.cash.id},
            format="json", **self._auth())
        assert paid.status_code == 200, paid.content

        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth()).json()
        approx = (Decimal(str(detail["supplier_balance_after_invoice"]))
                  - Decimal(str(detail["supplier_balance_before_invoice"])))
        assert approx == Decimal("0.00"), "التقريب القديم يقول صفراً (موثَّق)"

        ledger = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/supplier-ledger/",
            **self._auth()).json()
        anchor = ledger["anchor"]
        assert Decimal(str(anchor["balance_after"])) - Decimal(str(anchor["balance_before"])) \
            == Decimal("500.00"), "الكشف يقول أثرها الحقيقي"

    # ── 3) المرفقات ────────────────────────────────────────────────────────
    def test_attachment_can_be_added_to_a_posted_invoice_and_removed(self):
        """أكثر وقتٍ يُحتاج فيه إرفاق إيصال المورّد هو ما بعد الترحيل."""
        inv = self._invoice("PINV-CTX-8")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        inv.refresh_from_db()
        assert inv.is_posted is True

        added = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/attachments/",
            {"url": "https://files.test/receipt.pdf"}, format="json", **self._auth())
        assert added.status_code == 201, added.content
        assert added.json()["file_type"] == "PDF"
        assert added.json()["filename"] == "receipt.pdf"

        listed = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/attachments/", **self._auth())
        assert [r["id"] for r in listed.json()] == [added.json()["id"]]

        gone = self.client.delete(
            f"/api/logistics/purchase-invoices/{inv.pk}/attachments/{added.json()['id']}/",
            **self._auth())
        assert gone.status_code == 204, gone.content
        assert SystemAttachment.objects.filter(
            related_table="purchase_invoices", related_id=inv.pk).count() == 0

    def test_attachment_of_another_invoice_is_not_deletable_from_here(self):
        """الحذف مُنطاقٌ بالفاتورة وشركتها — لا بالمعرّف وحده."""
        mine = self._invoice("PINV-CTX-9")
        other = self._invoice("PINV-CTX-10")
        att = SystemAttachment.objects.create(
            tenant=self.tenant, related_table="purchase_invoices",
            related_id=other.pk, file_type="Image", file_path="https://files.test/x.png")

        res = self.client.delete(
            f"/api/logistics/purchase-invoices/{mine.pk}/attachments/{att.pk}/",
            **self._auth())
        assert res.status_code == 404, res.content
        assert SystemAttachment.objects.filter(pk=att.pk).exists()

    def test_invalid_attachment_url_is_refused(self):
        inv = self._invoice("PINV-CTX-11")
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/attachments/",
            {"url": "javascript:alert(1)"}, format="json", **self._auth())
        assert res.status_code == 400, res.content
