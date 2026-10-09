"""حركة الشيك الأجنبي بسعر سنده لا بافتراضي `post_journal` (1) — M5.

كان `post_cheque_movement_journal` يمرّر عملة الشيك بلا سعر: تحصيل شيك 500 دولار
يُرحَّل 500 شيكل في الدفاتر الأساسية.
"""
from decimal import Decimal

from rest_framework.test import APITestCase

from accounting.models import Cheque, ChequeMovement, JournalHeader
from accounting.tests import test_cheque_transfer_journals as base  # وحدةٌ لا صنف
from sales.models import CustomerPayment, SalesInvoice
from tenants.models import Currency


class ChequeMovementRateTest(APITestCase):
    setUpTestData = classmethod(base.ChequeTransferJournalTest.setUpTestData.__func__)
    _auth = base.ChequeTransferJournalTest._auth

    def _usd_cheque(self, voucher_rate=None):
        usd, _ = Currency.objects.get_or_create(Code="USD", defaults={"Name": "دولار"})
        voucher, invoice = None, None
        if voucher_rate is not None:
            voucher = CustomerPayment.objects.create(
                tenant=self.tenant, partner=self.customer, currency=usd,
                exchange_rate=Decimal(voucher_rate), amount=Decimal("500"),
                cash_or_bank_account=self.cash, payment_date="2026-06-11", is_posted=True)
        else:
            # مربوطٌ بفاتورة مرحّلة بلا سند — حركته لها قيد ولا سند يُؤخذ سعره منه.
            invoice = SalesInvoice.objects.create(
                tenant=self.tenant, invoice_number=f"USD-INV-{Cheque.objects.count()+1}",
                customer=self.customer, currency=usd, exchange_rate=Decimal("3.5"),
                invoice_date="2026-06-11", status=SalesInvoice.STATUS_POSTED,
                grand_total=Decimal("500.00"))
        return Cheque.objects.create(
            tenant=self.tenant, cheque_number=f"USD-{Cheque.objects.count()+1}",
            amount=Decimal("500.00"), currency=usd, partner=self.customer,
            status="Under_Collection", direction="Incoming", customer_payment=voucher,
            sales_invoice=invoice)

    def _collect(self, chq, **extra):
        return self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "collect", "movement_date": "2026-06-12", **extra},
            format="json", **self._auth())

    def _journal(self, chq):
        movement = ChequeMovement.objects.get(cheque=chq, movement_type="collect")
        return JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_COLLECT", reference_id=movement.pk)

    def test_foreign_cheque_moves_at_its_voucher_rate(self):
        chq = self._usd_cheque(voucher_rate="3.7")
        res = self._collect(chq)
        self.assertEqual(res.status_code, 200, res.content)
        jh = self._journal(chq)
        self.assertEqual(jh.exchange_rate, Decimal("3.7"))
        cash_line = jh.lines.get(account=self.cash)
        self.assertEqual(cash_line.base_debit, Decimal("1850.00"))

    def test_foreign_cheque_without_voucher_needs_the_rate_in_the_movement(self):
        """ولا يُؤخذ سعر الفاتورة (3.5) بصمت — سعر يوم الحركة من الطلب."""
        chq = self._usd_cheque()
        res = self._collect(chq)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("سعر صرف USD", str(res.json()))
        chq.refresh_from_db()
        self.assertEqual(chq.status, "Under_Collection")

        res = self._collect(chq, exchange_rate="3.65")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self._journal(chq).exchange_rate, Decimal("3.65"))
