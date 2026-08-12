"""سلامة ذمم الموردين — التراجع عن ترحيل سند الصرف (مرآة الجانب الوارد).

الجذر المُصلَح: `SupplierPaymentViewSet` لم يكن يملك `unpost`، و`destroy` كان
يحذف سنداً مرحّلاً دون التراجع عن قيوده — قيود يتيمة (مدين ذمم المورد بلا
مقابل) وفواتير شراء تبقى «مدفوعة» لأن التوزيعات تُحذف بالتتابع بينما القيد باقٍ.

قاعدة الاحتساب في مكانين يجب أن تتفقا (memory: supplier payment parity):
`purchase_invoice_payment_summary` و`annotate_purchase_invoice_payment_summary`
كلتاهما تفلتران على `is_posted=True` — فالتراجع يقلب الراية ويكفي المكانين.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque, FiscalPeriod, JournalHeader
from logistics.models import PurchaseInvoice
from logistics.services import (
    annotate_purchase_invoice_payment_summary,
    purchase_invoice_payment_summary,
)
from partners.models import Partner
from sales.models import SupplierPayment, SupplierPaymentAllocation
from sales.services import allocate_supplier_payment
from tenants.models import Currency, Tenant, UserCompanyMembership

URL = "/api/logistics/supplier-payments/"


class SupplierPaymentUnpostTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="sup-unpost", password="x")
        cls.limited = User.objects.create_user(username="sup-unpost-proc", password="x")
        cls.tenant = Tenant.objects.create(TenantID=154, CompanyName="Supplier Unpost Co")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager")
        # موظف مشتريات: يملك purchase.payment.post لكن ليس unpost.
        UserCompanyMembership.objects.create(
            user=cls.limited, tenant=cls.tenant, role="procurement")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110", name="صندوق", account_type="Asset", is_active=True)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101", name="ذمم موردين", account_type="Liability", is_active=True)
        cls.payable = Account.objects.create(
            tenant=cls.tenant, code="2106", name="شيكات برسم الدفع",
            account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier", linked_account=cls.ap)
        FiscalPeriod.objects.create(
            tenant=cls.tenant, name="2026", start_date="2026-01-01",
            end_date="2026-12-31", is_closed=False)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create_posted(self, *, amount="500", cheques=None):
        body = {
            "partner": self.partner.pk,
            "payment_date": "2026-07-05",
            "amount": amount,
            "currency": self.currency.CurrencyID,
            "cash_or_bank_account": self.cash.pk,
            "cheques": cheques or [],
        }
        res = self.client.post(URL, body, format="json", **self.h)
        assert res.status_code == 201, res.content
        payment = SupplierPayment.objects.get(pk=res.json()["id"])
        assert payment.is_posted, res.content
        return payment

    def _journals(self, payment):
        return JournalHeader.objects.filter(
            reference_type="SUPPLIER_PAYMENT", reference_id=payment.pk)

    def _posted_invoice(self, *, total="500", number="PI-UNPOST-1"):
        return PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, partner=self.partner,
            currency=self.currency, invoice_date="2026-07-01",
            grand_total=Decimal(total), is_posted=True)

    def test_unpost_reverts_journal_and_cheques(self):
        payment = self._create_posted(
            cheques=[{"cheque_number": "OUT-U1", "amount": "200", "bank_name": "بنك",
                      "due_date": "2026-09-01"}])
        assert self._journals(payment).exists()
        assert Cheque.objects.get(supplier_payment=payment).status == "Under_Collection"

        res = self.client.post(f"{URL}{payment.pk}/unpost/", {}, format="json", **self.h)

        assert res.status_code == 200, res.content
        assert res.json()["unpost_result"]["journals_deleted"] == 1
        payment.refresh_from_db()
        assert payment.is_posted is False
        assert payment.journal_id is None
        assert not self._journals(payment).exists()
        # الشيك الصادر يعود مسودةً — عكسُ ما فعله الترحيل تماماً.
        assert Cheque.objects.get(supplier_payment=payment).status == "Draft"

    def test_unpost_draft_payment_rejected(self):
        res = self.client.post(
            URL,
            {"partner": self.partner.pk, "payment_date": "2026-07-05", "amount": "100",
             "currency": self.currency.CurrencyID, "cash_or_bank_account": self.cash.pk,
             "auto_post": False},
            format="json", **self.h)
        assert res.status_code == 201, res.content
        pid = res.json()["id"]

        res = self.client.post(f"{URL}{pid}/unpost/", {}, format="json", **self.h)
        assert res.status_code == 400, res.content
        assert "غير مرحّل" in res.json()["error"]

    def test_deleting_a_posted_payment_removes_its_journals(self):
        """مرآة الجانب الوارد: الحذف كان يترك القيد (مدين ذمم المورد) يتيماً."""
        payment = self._create_posted()
        assert self._journals(payment).exists()

        res = self.client.delete(f"{URL}{payment.pk}/", **self.h)

        assert res.status_code == 204, res.content
        assert not SupplierPayment.objects.filter(pk=payment.pk).exists()
        assert not self._journals(payment).exists()

    def test_allocated_invoices_return_unpaid_in_both_summaries(self):
        """قاعدة الاحتساب في مكانين (summary + SQL annotate) يجب أن تتفقا."""
        inv = self._posted_invoice()
        payment = self._create_posted(amount="500")
        allocate_supplier_payment(
            payment, [{"invoice": inv.pk, "amount": "500"}], user=self.user)

        fresh = PurchaseInvoice.objects.get(pk=inv.pk)
        assert purchase_invoice_payment_summary(fresh)["remaining_balance"] == Decimal("0.00")
        annotated = annotate_purchase_invoice_payment_summary(
            PurchaseInvoice.objects.filter(pk=inv.pk)).get()
        assert annotated.list_amount_paid == Decimal("500.00")

        res = self.client.post(f"{URL}{payment.pk}/unpost/", {}, format="json", **self.h)
        assert res.status_code == 200, res.content

        # الفاتورة تعود «غير مسدَّدة» في المصدرين معاً — بلا أي كتابة عليها.
        fresh = PurchaseInvoice.objects.get(pk=inv.pk)
        assert purchase_invoice_payment_summary(fresh)["remaining_balance"] == Decimal("500.00")
        annotated = annotate_purchase_invoice_payment_summary(
            PurchaseInvoice.objects.filter(pk=inv.pk)).get()
        assert annotated.list_amount_paid == Decimal("0.00")
        # التوزيع يبقى (ربط بلا قيد) فيُحتسب من جديد عند إعادة الترحيل.
        assert SupplierPaymentAllocation.objects.filter(payment=payment).count() == 1

    def test_unpost_and_posted_delete_require_permission(self):
        """موظف المشتريات يرحّل لكن لا يتراجع ولا يحذف مرحّلاً."""
        payment = self._create_posted()

        self.client.force_authenticate(user=self.limited)
        res = self.client.post(f"{URL}{payment.pk}/unpost/", {}, format="json", **self.h)
        assert res.status_code == 403, res.content

        res = self.client.delete(f"{URL}{payment.pk}/", **self.h)
        assert res.status_code == 403, res.content
        payment.refresh_from_db()
        assert payment.is_posted is True
        assert self._journals(payment).exists()
