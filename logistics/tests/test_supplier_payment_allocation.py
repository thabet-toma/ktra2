"""T-ONACC (جانب المورد): سند صرف «على الحساب» يُوزَّع لاحقاً على فواتير الشراء.

مرآة `PaymentAllocation` للعميل: سند واحد يُوزَّع بمبالغ جزئية على عدّة فواتير،
والباقي يبقى رصيداً لنا عند المورد. التوزيع بعد الترحيل **ربط فقط بلا قيد جديد**
(ذمم المورد دُينت وقت الترحيل).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import purchase_invoice_payment_summary
from partners.models import Partner
from sales.models import SupplierPayment, SupplierPaymentAllocation
from sales.services import allocate_supplier_payment, post_supplier_payment
from tenants.models import Currency
from tenants.services import create_company


class SupplierPaymentAllocationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="spalloc", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة توزيع الصرف", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-AL", name="ذمم المورد",
            account_type="Liability", is_active=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110-AL", name="الصندوق",
            account_type="Asset", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد التوزيع", partner_type="Supplier",
            linked_account=cls.ap)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="SPA-1", name_ar="منتج",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _invoice(self, number, total):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.partner,
            currency=self.ils, invoice_date="2026-06-11", exchange_rate=Decimal("1"),
            grand_total=Decimal(str(total)),
            payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT)
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="منتج",
            quantity=Decimal("1"), unit_price=Decimal(str(total)),
            total_price=Decimal(str(total)))
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/",
            {}, format="json", **self._auth())
        assert res.status_code == 201, res.content
        inv.refresh_from_db()
        return inv

    def _payment(self, amount, invoice=None):
        pay = SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.partner, currency=self.ils,
            exchange_rate=Decimal("1"), amount=Decimal(str(amount)),
            cash_or_bank_account=self.cash, payment_date="2026-06-20",
            purchase_invoice=invoice, is_posted=False)
        post_supplier_payment(pay)
        pay.refresh_from_db()
        return pay

    @staticmethod
    def _summary(invoice):
        invoice = PurchaseInvoice.objects.get(pk=invoice.pk)  # يتجاوز كاش الملخص
        return purchase_invoice_payment_summary(invoice)

    def test_unlinked_payment_leaves_invoices_untouched(self):
        inv = self._invoice("PINV-AL-1", 600)
        self._payment(1000)
        self.assertEqual(self._summary(inv)["amount_paid"], Decimal("0.00"))

    def test_allocation_marks_invoice_paid_without_new_journal(self):
        inv = self._invoice("PINV-AL-2", 600)
        pay = self._payment(1000)
        journals_before = JournalHeader.objects.filter(
            tenant_id=self.tenant.TenantID, reference_type="SUPPLIER_PAYMENT",
            reference_id=pay.id).count()

        allocate_supplier_payment(pay, [{"invoice": inv.id, "amount": "600"}])

        self.assertEqual(self._summary(inv)["amount_paid"], Decimal("600.00"))
        self.assertEqual(self._summary(inv)["payment_status"], "paid")
        after = JournalHeader.objects.filter(
            tenant_id=self.tenant.TenantID, reference_type="SUPPLIER_PAYMENT",
            reference_id=pay.id).count()
        self.assertEqual(after, journals_before)
        # المتبقّي على الحساب = 400 يُوزَّع على فاتورة أخرى لاحقاً
        inv2 = self._invoice("PINV-AL-3", 900)
        allocate_supplier_payment(pay, [{"invoice": inv2.id, "amount": "400"}])
        self.assertEqual(self._summary(inv2)["amount_paid"], Decimal("400.00"))
        self.assertEqual(self._summary(inv2)["payment_status"], "partially_paid")

    def test_allocation_beyond_payment_amount_rejected(self):
        inv = self._invoice("PINV-AL-4", 900)
        pay = self._payment(500)
        with self.assertRaises(ValidationError):
            allocate_supplier_payment(pay, [{"invoice": inv.id, "amount": "600"}])
        self.assertEqual(SupplierPaymentAllocation.objects.filter(payment=pay).count(), 0)

    def test_allocation_beyond_invoice_remaining_rejected(self):
        inv = self._invoice("PINV-AL-5", 300)
        pay = self._payment(1000)
        with self.assertRaises(ValidationError):
            allocate_supplier_payment(pay, [{"invoice": inv.id, "amount": "400"}])

    def test_legacy_linked_payment_still_counts_fully(self):
        """السندات القديمة المرتبطة بالحقل المفرد تبقى محسوبة كما هي."""
        inv = self._invoice("PINV-AL-6", 500)
        self._payment(500, invoice=inv)
        self.assertEqual(self._summary(inv)["amount_paid"], Decimal("500.00"))

    def test_list_annotation_matches_detail_after_allocation(self):
        """قائمة الفواتير (SQL) يجب أن توافق التفصيل بعد التوزيع — لا تناقض."""
        inv = self._invoice("PINV-AL-8", 700)
        pay = self._payment(700)
        allocate_supplier_payment(pay, [{"invoice": inv.id, "amount": "700"}])

        res = self.client.get(
            f"/api/logistics/purchase-invoices/?partner={self.partner.id}", **self._auth())
        self.assertEqual(res.status_code, 200)
        rows = res.data["results"] if isinstance(res.data, dict) else res.data
        row = next(r for r in rows if r["id"] == inv.id)
        self.assertEqual(Decimal(str(row["amount_paid"])), Decimal("700.00"))
        self.assertEqual(row["payment_status"], "paid")

    def test_allocate_endpoint_and_partner_filter(self):
        inv = self._invoice("PINV-AL-7", 400)
        pay = self._payment(1000)

        res = self.client.post(
            f"/api/logistics/supplier-payments/{pay.id}/allocate/",
            {"allocations": [{"invoice": inv.id, "amount": "400"}]},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["unallocated_amount"], "600.00")
        self.assertEqual(self._summary(inv)["amount_paid"], Decimal("400.00"))

        listed = self.client.get(
            f"/api/logistics/supplier-payments/?partner={self.partner.id}", **self._auth())
        self.assertEqual(listed.status_code, 200)
        rows = listed.data["results"] if isinstance(listed.data, dict) else listed.data
        self.assertTrue(rows)
        self.assertTrue(all(r["partner"] == self.partner.id for r in rows))
        self.assertIn("unallocated_amount", rows[0])

    def test_deallocate_restores_invoice_status_and_voucher(self):
        """A1-3 (مرآة المورد): فكّ توزيعٍ واحد — المدفوع مشتقّ من التوزيعات فيعود
        وحده، والمبلغ يرجع «على الحساب» بلا قيد جديد."""
        inv = self._invoice("PINV-AL-D1", 400)
        inv2 = self._invoice("PINV-AL-D2", 300)
        pay = self._payment(1000)
        allocate_supplier_payment(pay, [
            {"invoice": inv.id, "amount": "400"}, {"invoice": inv2.id, "amount": "300"}])
        self.assertEqual(self._summary(inv)["payment_status"], "paid")
        journals = JournalHeader.objects.filter(
            tenant_id=self.tenant.TenantID, reference_type="SUPPLIER_PAYMENT",
            reference_id=pay.id).count()
        alloc = SupplierPaymentAllocation.objects.get(payment=pay, invoice=inv)

        res = self.client.post(
            f"/api/logistics/supplier-payments/{pay.id}/deallocate/",
            {"allocation": alloc.id}, format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["unallocated_amount"], "700.00")
        self.assertEqual([a["invoice"] for a in res.data["allocations"]], [inv2.id])
        self.assertEqual(self._summary(inv)["amount_paid"], Decimal("0.00"))
        self.assertEqual(self._summary(inv)["payment_status"], "unpaid")
        self.assertEqual(self._summary(inv2)["amount_paid"], Decimal("300.00"))
        self.assertEqual(
            JournalHeader.objects.filter(
                tenant_id=self.tenant.TenantID, reference_type="SUPPLIER_PAYMENT",
                reference_id=pay.id).count(),
            journals)

    def test_deallocate_other_tenant_allocation_is_404(self):
        other_user = User.objects.create_user(username="spalloc2", password="x")
        other = create_company("شركة صرف أخرى", other_user)
        create_fiscal_year(other, 2026)
        oap = Account.objects.create(
            tenant=other, code="2101-OA", name="ذمم", account_type="Liability", is_active=True)
        ocash = Account.objects.create(
            tenant=other, code="1110-OA", name="صندوق", account_type="Asset", is_active=True)
        osup = Partner.objects.create(
            tenant=other, name="موردهم", partner_type="Supplier", linked_account=oap)
        oinv = PurchaseInvoice.objects.create(
            tenant=other, invoice_number="PINV-O-1", partner=osup, currency=self.ils,
            invoice_date="2026-06-11", exchange_rate=Decimal("1"),
            grand_total=Decimal("100"), is_posted=True,
            payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT)
        opay = SupplierPayment.objects.create(
            tenant=other, partner=osup, currency=self.ils, exchange_rate=Decimal("1"),
            amount=Decimal("100"), cash_or_bank_account=ocash,
            payment_date="2026-06-20", is_posted=False)
        oalloc = SupplierPaymentAllocation.objects.create(
            tenant=other, payment=opay, invoice=oinv, amount=Decimal("100"))
        mine = self._payment(50)

        for pay in (opay, mine):
            res = self.client.post(
                f"/api/logistics/supplier-payments/{pay.id}/deallocate/",
                {"allocation": oalloc.id}, format="json", **self._auth())
            self.assertEqual(res.status_code, 404, res.data)
        self.assertTrue(SupplierPaymentAllocation.objects.filter(pk=oalloc.pk).exists())
