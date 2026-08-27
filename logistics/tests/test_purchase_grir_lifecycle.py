"""GR/IR — فاتورة شراء محلية: الترحيل يُنشئ قيدين (وسيط) + يستلم البضاعة،
وإلغاء الترحيل يمسح القيدين والمخزون، وإعادة الترحيل تُعيد كل شيء بنفس رقم القيد.

يثبت تماثل دورة post → unpost → repost للمحاسبة والمخزون معاً (idempotent).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine, VoidedJournal
from inventory.models import Product, StockMovement, Warehouse
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import GR_IR_ACCOUNT_CODE
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company
from accounting.services import create_fiscal_year


class PurchaseGrIrLifecycleTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="grir", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الوسيط", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.ap = Account.objects.get(tenant=cls.tenant, code="2101")
        cls.inv_acc = Account.objects.get(tenant=cls.tenant, code="1104")
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد محلي", partner_type="Supplier",
            linked_account=cls.ap)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="GRIR-1", name_ar="منتج",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _make_local_invoice(self, qty="10", price="500"):
        grand = Decimal(qty) * Decimal(price)
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=f"INV-{PurchaseInvoice.objects.count()+1:04d}",
            partner=self.partner, currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), grand_total=grand)
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="منتج",
            quantity=Decimal(qty), unit_price=Decimal(price), total_price=grand)
        return inv

    def _grir_account(self):
        return Account.objects.get(tenant=self.tenant, code=GR_IR_ACCOUNT_CODE)

    def _grir_net(self):
        """صافي رصيد الوسيط = مدين − دائن (يجب أن يكون صفراً عند ترحيل كامل)."""
        agg = JournalLine.objects.filter(
            tenant=self.tenant, account=self._grir_account()).aggregate(
            d=Sum("debit"), c=Sum("credit"))
        return (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))

    def _assert_posted_state(self, inv):
        """قيدان متّزنان + الوسيط صفر + المخزون داخل."""
        inv_j = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="PURCHASE_INVOICE", reference_id=inv.pk)
        grn_j = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="PURCHASE_GRN", reference_id=inv.pk)
        grir = self._grir_account()
        # قيد الفاتورة: مدين الوسيط / دائن المورّد
        assert inv_j.lines.filter(account=grir, debit=Decimal("5000.00")).exists()
        assert inv_j.lines.filter(account=self.ap, credit=Decimal("5000.00")).exists()
        # قيد الاستلام: مدين المخزون / دائن الوسيط
        assert grn_j.lines.filter(account=self.inv_acc, debit=Decimal("5000.00")).exists()
        assert grn_j.lines.filter(account=grir, credit=Decimal("5000.00")).exists()
        # الوسيط يُصفَّر
        assert self._grir_net() == Decimal("0.00")
        return inv_j.id

    def test_post_unpost_repost_symmetric_and_idempotent(self):
        inv = self._make_local_invoice(qty="10", price="500")
        headers = self._auth()

        # ── ترحيل: قيدان + استلام ──
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **headers)
        assert res.status_code == 201, res.content
        first_journal_id = self._assert_posted_state(inv)
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("10.0000")
        assert self.product.avg_cost == Decimal("500.0000")
        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL
        assert inv.is_posted

        # ── إلغاء الترحيل: يمسح القيدين + المخزون + يحجز الرقم ──
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/", {},
            format="json", **headers)
        assert res.status_code == 200, res.content
        assert not JournalHeader.objects.filter(
            tenant=self.tenant, reference_id=inv.pk,
            reference_type__in=["PURCHASE_INVOICE", "PURCHASE_GRN"]).exists()
        assert not StockMovement.objects.filter(
            reference_type="PURCHASE_INVOICE", reference_id=inv.pk).exists()
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("0.0000")
        assert self._grir_net() == Decimal("0.00")  # لا رصيد عالق في الوسيط
        inv.refresh_from_db()
        assert not inv.is_posted
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_NOT
        # الرقم محجوز لإعادة الاستخدام
        assert VoidedJournal.objects.get(
            tenant=self.tenant, reference_type="PURCHASE_INVOICE",
            reference_id=inv.pk).original_journal_id == first_journal_id

        # ── إعادة الترحيل: كل شيء يعود + نفس رقم قيد الفاتورة ──
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **headers)
        assert res.status_code == 201, res.content
        reposted_id = self._assert_posted_state(inv)
        assert reposted_id == first_journal_id  # نفس الرقم بالضبط
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("10.0000")
        assert not VoidedJournal.objects.filter(
            tenant=self.tenant, reference_id=inv.pk).exists()  # الحجز استُهلِك

        # ── تكرار الدورة (idempotent) ──
        self.client.post(f"/api/logistics/purchase-invoices/{inv.pk}/unpost/", {},
                         format="json", **headers)
        self.client.post(f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
                         format="json", **headers)
        again_id = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="PURCHASE_INVOICE", reference_id=inv.pk).id
        assert again_id == first_journal_id
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("10.0000")  # لا انجراف
        assert self._grir_net() == Decimal("0.00")
