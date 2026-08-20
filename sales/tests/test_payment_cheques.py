"""سند القبض يحمل نقداً وشيكات معاً — الطريق الوحيد لتحصيل فاتورة بيع.

قبل هذا: شبكة الشيكات داخل نافذة السند كانت تزيد مبلغ السند فقط ولا تُرسل أي
شيك للخادم، فيُقيَّد مال الشيكات على الصندوق كأنه نقد، ولا يُنشأ شيك برسم
التحصيل. هنا العقد الصحيح:

    Dr صندوق (الجزء النقدي) + Dr شيكات في المحفظة (جزء الشيكات) = Cr ذمم العميل

CHQ-2: حساب الشيكات صار «في المحفظة» (1109) لا «برسم التحصيل» (1107) — الورقة
في اليد لم تُودَع بعد، والإيداع صار حدثاً مستقلاً له قيده (1107 ÷ 1109).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque, FiscalPeriod, JournalLine
from inventory.models import Product
from partners.models import Partner
from sales.models import CustomerPayment, SalesInvoice, SalesInvoiceLine
from sales.services import post_sales_invoice
from tenants.models import Currency, Tenant, UserCompanyMembership

URL = "/api/sales/payments/"


class PaymentChequesTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pay-cheq", password="x")
        cls.tenant = Tenant.objects.create(TenantID=151, CompanyName="Cheque Co")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110", name="صندوق", account_type="Asset", is_active=True)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101", name="ذمم عملاء", account_type="Asset", is_active=True)
        cls.uc = Account.objects.create(
            tenant=cls.tenant, code="1106", name="شيكات برسم التحصيل",
            account_type="Asset", is_active=True)
        Account.objects.create(
            tenant=cls.tenant, code="4101", name="إيرادات", account_type="Revenue", is_active=True)
        Account.objects.create(
            tenant=cls.tenant, code="2101", name="ضريبة", account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="زبون", partner_type="Customer", linked_account=cls.ar)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="CHQ-1", name_ar="خدمة", is_service=True)
        FiscalPeriod.objects.create(
            tenant=cls.tenant, name="2026", start_date="2026-01-01",
            end_date="2026-12-31", is_closed=False)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        self.invoice = self._posted_invoice()

    def _posted_invoice(self, total="1000"):
        inv = SalesInvoice.objects.create(
            tenant=self.tenant, customer=self.partner, currency=self.currency,
            invoice_date="2026-07-01", stock_on_post=False, invoice_type="credit")
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=inv, product=self.product,
            quantity=1, unit_price=Decimal(total))
        post_sales_invoice(inv, user=self.user)
        inv.refresh_from_db()
        return inv

    def _body(self, **over):
        body = {
            "partner": self.partner.pk,
            "payment_date": "2026-07-05",
            "amount": "500",
            "currency": self.currency.CurrencyID,
            "cash_or_bank_account": self.cash.pk,
            "allocations": [{"invoice": self.invoice.pk, "amount": "500"}],
            "cheques": [{
                "cheque_number": "CHQ-1",
                "amount": "200",
                "due_date": "2026-09-01",
                "bank_name": "بنك",
                "account_number": "0012300456",
                "bank_branch": "رام الله",
                "payee_name": "شركة الزبون",
            }],
        }
        body.update(over)
        return body

    def _lines(self, payment):
        return {
            (line.account.code, str(line.debit), str(line.credit))
            for line in JournalLine.objects.filter(
                journal__reference_type="CUSTOMER_PAYMENT",
                journal__reference_id=payment.pk,
            ).select_related("account")
        }

    def test_cheque_rows_are_created_and_linked_to_the_payment(self):
        res = self.client.post(URL, self._body(auto_post=False), format="json", **self.h)
        assert res.status_code == 201, res.content
        payment = CustomerPayment.objects.get(pk=res.json()["id"])
        cheque = Cheque.objects.get(customer_payment=payment)
        assert cheque.cheque_number == "CHQ-1"
        assert cheque.amount == Decimal("200.00")
        assert cheque.partner_id == self.partner.pk
        assert cheque.direction == "Incoming"
        assert cheque.status == "Draft"
        assert cheque.account_number == "0012300456"
        assert cheque.bank_branch == "رام الله"
        assert cheque.payee_name == "شركة الزبون"

    def test_posting_splits_debit_between_cash_and_cheques(self):
        res = self.client.post(URL, self._body(), format="json", **self.h)
        assert res.status_code == 201, res.content
        payment = CustomerPayment.objects.get(pk=res.json()["id"])
        assert payment.is_posted

        assert self._lines(payment) == {
            ("1110", "300.00", "0.00"),   # النقد فقط
            ("1109", "200.00", "0.00"),   # CHQ-2: الشيكات في المحفظة
            ("1101", "0.00", "500.00"),   # ذمم العميل بالمجموع
        }
        self.invoice.refresh_from_db()
        assert self.invoice.amount_paid == Decimal("500.00")
        assert Cheque.objects.get(customer_payment=payment).status == "Received"

    def test_cheque_only_payment_debits_no_cash(self):
        res = self.client.post(
            URL,
            self._body(
                amount="200",
                allocations=[{"invoice": self.invoice.pk, "amount": "200"}],
            ),
            format="json", **self.h,
        )
        assert res.status_code == 201, res.content
        payment = CustomerPayment.objects.get(pk=res.json()["id"])
        assert self._lines(payment) == {
            ("1109", "200.00", "0.00"),
            ("1101", "0.00", "200.00"),
        }

    def test_on_account_payment_splits_too(self):
        """سند بلا توزيع (على الحساب) يفصل الشيكات عن النقد أيضاً."""
        res = self.client.post(
            URL, self._body(allocations=[]), format="json", **self.h)
        assert res.status_code == 201, res.content
        payment = CustomerPayment.objects.get(pk=res.json()["id"])
        assert self._lines(payment) == {
            ("1110", "300.00", "0.00"),
            ("1109", "200.00", "0.00"),
            ("1101", "0.00", "500.00"),
        }

    def test_cheques_may_not_exceed_the_voucher_amount(self):
        res = self.client.post(
            URL,
            self._body(cheques=[{"cheque_number": "CHQ-BIG", "amount": "900",
                                 "due_date": "2026-09-01"}]),
            format="json", **self.h,
        )
        assert res.status_code == 400, res.content

    def test_cheque_needs_a_number_and_a_positive_amount(self):
        assert self.client.post(
            URL, self._body(cheques=[{"cheque_number": "", "amount": "100",
                                     "due_date": "2026-09-01"}]),
            format="json", **self.h,
        ).status_code == 400
        assert self.client.post(
            URL, self._body(cheques=[{"cheque_number": "CHQ-0", "amount": "0",
                                     "due_date": "2026-09-01"}]),
            format="json", **self.h,
        ).status_code == 400

    def test_payment_without_cheques_is_unchanged(self):
        """عدم الانحدار: السند النقدي الصِّرف يبقى Dr صندوق / Cr ذمم."""
        res = self.client.post(
            URL, self._body(cheques=[]), format="json", **self.h)
        assert res.status_code == 201, res.content
        payment = CustomerPayment.objects.get(pk=res.json()["id"])
        assert self._lines(payment) == {
            ("1110", "500.00", "0.00"),
            ("1101", "0.00", "500.00"),
        }

    def test_cheque_needs_a_due_date(self):
        """قرار المالك: دورة الشيك كلها مبنية على «لما يجي موعده».

        وقبل هذا الشرط كان الفراغ يصطدم بعمود `DueDate` في القاعدة فيرتدّ
        بـ500 غامض بدل رسالة تقول للمستخدم ما ينقصه.
        """
        res = self.client.post(
            URL,
            self._body(cheques=[{"cheque_number": "CHQ-NODUE", "amount": "200"}]),
            format="json", **self.h,
        )
        assert res.status_code == 400, res.content
        assert "استحقاق" in str(res.json()), res.content

    def test_cheque_with_a_due_date_passes(self):
        res = self.client.post(
            URL,
            self._body(
                auto_post=False,
                cheques=[{
                    "cheque_number": "CHQ-DUE", "amount": "200",
                    "due_date": "2026-09-01",
                }],
            ),
            format="json", **self.h,
        )
        assert res.status_code == 201, res.content
