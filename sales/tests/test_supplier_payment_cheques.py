"""سند الصرف مرآة سند القبض: نقد + شيكات في سند واحد.

الجانب الدائن ينقسم: ما دُفع نقداً يخرج من الصندوق، وما دُفع بشيكات يصير
التزاماً على «شيكات برسم الدفع» حتى تُصرف — لا يُحسب نقداً خارجاً من الصندوق.

    Dr ذمم المورد (المجموع) = Cr صندوق (نقد) + Cr شيكات برسم الدفع (شيكات)
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque, FiscalPeriod, JournalLine
from partners.models import Partner
from sales.models import SupplierPayment
from tenants.models import Currency, Tenant, UserCompanyMembership

URL = "/api/logistics/supplier-payments/"


class SupplierPaymentChequesTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="sup-cheq", password="x")
        cls.tenant = Tenant.objects.create(TenantID=152, CompanyName="Supplier Cheque Co")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager")
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

    def _body(self, **over):
        body = {
            "partner": self.partner.pk,
            "payment_date": "2026-07-05",
            "amount": "500",
            "currency": self.currency.CurrencyID,
            "cash_or_bank_account": self.cash.pk,
            "cheques": [{"cheque_number": "OUT-1", "amount": "200", "bank_name": "بنك",
                         "due_date": "2026-09-01"}],
        }
        body.update(over)
        return body

    def _lines(self, payment):
        return {
            (line.account.code, str(line.debit), str(line.credit))
            for line in JournalLine.objects.filter(
                journal__reference_type="SUPPLIER_PAYMENT",
                journal__reference_id=payment.pk,
            ).select_related("account")
        }

    def test_cheque_rows_are_created_outgoing_and_linked(self):
        res = self.client.post(URL, self._body(auto_post=False), format="json", **self.h)
        assert res.status_code == 201, res.content
        payment = SupplierPayment.objects.get(pk=res.json()["id"])
        cheque = Cheque.objects.get(supplier_payment=payment)
        assert cheque.cheque_number == "OUT-1"
        assert cheque.amount == Decimal("200.00")
        assert cheque.direction == "Outgoing"
        assert cheque.partner_id == self.partner.pk
        assert cheque.status == "Draft"

    def test_posting_splits_credit_between_cash_and_cheques(self):
        res = self.client.post(URL, self._body(), format="json", **self.h)
        assert res.status_code == 201, res.content
        payment = SupplierPayment.objects.get(pk=res.json()["id"])
        assert payment.is_posted
        assert self._lines(payment) == {
            ("2101", "500.00", "0.00"),   # ذمم المورد بالمجموع
            ("1110", "0.00", "300.00"),   # النقد فقط من الصندوق
            ("2106", "0.00", "200.00"),   # شيكات برسم الدفع
        }
        assert Cheque.objects.get(supplier_payment=payment).status == "Under_Collection"

    def test_cheque_only_payment_credits_no_cash(self):
        res = self.client.post(URL, self._body(amount="200"), format="json", **self.h)
        assert res.status_code == 201, res.content
        payment = SupplierPayment.objects.get(pk=res.json()["id"])
        assert self._lines(payment) == {
            ("2101", "200.00", "0.00"),
            ("2106", "0.00", "200.00"),
        }

    def test_cheques_may_not_exceed_the_voucher_amount(self):
        res = self.client.post(
            URL,
            self._body(cheques=[{"cheque_number": "OUT-BIG", "amount": "900",
                                 "due_date": "2026-09-01"}]),
            format="json", **self.h,
        )
        assert res.status_code == 400, res.content

    def test_cheque_needs_a_due_date(self):
        """مرآة الجانب الوارد: لا شيك بلا موعد استحقاق."""
        res = self.client.post(
            URL,
            self._body(cheques=[{"cheque_number": "OUT-NODUE", "amount": "200"}]),
            format="json", **self.h,
        )
        assert res.status_code == 400, res.content
        assert "استحقاق" in str(res.json()), res.content

    def test_payment_without_cheques_is_unchanged(self):
        res = self.client.post(URL, self._body(cheques=[]), format="json", **self.h)
        assert res.status_code == 201, res.content
        payment = SupplierPayment.objects.get(pk=res.json()["id"])
        assert self._lines(payment) == {
            ("2101", "500.00", "0.00"),
            ("1110", "0.00", "500.00"),
        }


class ChequeAccountResolutionTest(APITestCase):
    """حساب الشيكات لا يُخمَّن بالكود: 1106 في الشجرة الاحترافية = «دفعات مقدمة
    للموردين»، فقبولُه كان يُهبِط أموال الشيكات في حساب لا علاقة له بها.

    T-CHQ3/هـ: بلا حساب «شيكات» كان الترحيل يفشل ويطلب من المستخدم تعيينه —
    والآن يُنشأ الحساب المعياري من الكود (قرار المالك). الحارس الأصلي قائم:
    الحساب الناتج حساب شيكات حقيقي، لا 1106 ولا أي حساب مصادف.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=153, CompanyName="No Cheque Acct")
        cls.advances = Account.objects.create(
            tenant=cls.tenant, code="1106", name="دفعات مقدمة للموردين",
            account_type="Asset", is_active=True)

    def test_advances_account_is_not_mistaken_for_cheques(self):
        from sales.services import (
            resolve_cheques_payable_account,
            resolve_cheques_under_collection_account,
        )

        uc = resolve_cheques_under_collection_account(self.tenant.TenantID)
        self.assertNotEqual(uc.pk, self.advances.pk)
        self.assertEqual(uc.code, "1107")
        self.assertIn("شيكات", uc.name)

        payable = resolve_cheques_payable_account(self.tenant.TenantID)
        self.assertNotEqual(payable.pk, self.advances.pk)
        self.assertEqual(payable.code, "2111")
        self.assertEqual(payable.account_type, "Liability")
