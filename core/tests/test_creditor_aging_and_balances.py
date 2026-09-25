"""أعمار الذمم الدائنة وأرصدة الموردين تشمل المخلّص والوكيل والناقل.

إنتاج (شركة 1): «أعمار الذمم الدائنة» كان يُبنى من فواتير الشراء وحدها، فدَين المخلّص
حاييم (7,551.50) غائبٌ عنه كلّه ومجموعه أقلّ من الدفتر؛ و«أرصدة الموردين» يفلتر
`partner_type="Supplier"` فلا يظهر فيه مخلّصٌ ولا وكيلٌ ولا ناقل.
"""
from decimal import Decimal

from django.db.models import Sum

from accounting.models import Account, JournalLine
from core.reports import run_report
from logistics.accruals import post_local_shipment_accrual
from logistics.models import LocalShipment
from logistics.tests.test_shipment_labels import _LabelBase

D = lambda v: Decimal(str(v))


class CreditorAgingAndBalancesTest(_LabelBase):
    def _ledger_balance(self, partner) -> Decimal:
        agg = JournalLine.objects.filter(
            tenant=self.tenant, journal__is_posted=True, partner=partner,
        ).aggregate(c=Sum("base_credit"), d=Sum("base_debit"))
        return D(agg["c"] or 0) - D(agg["d"] or 0)

    def _seed(self):
        paid_direct = self._clearance(self._shipment("SH-0017", "شحنة رقع"), "900")
        res = self.client.post(
            f"/api/logistics/clearances/{paid_direct.pk}/pay_from_cashbox/",
            {"amount": "400", "cash_box_external_id": self.box.external_id, "payment_date": "2026-07-01"},
            format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.content)

        by_voucher = self._clearance(self._shipment("SH-0019", "داتا لوجر"), "2500")
        voucher = self._voucher(2045)
        res = self.client.post(
            f"/api/logistics/supplier-payments/{voucher.id}/allocate-accruals/",
            {"allocations": [{"kind": "clearance", "id": by_voucher.pk, "amount": "2045"}]},
            format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)

        local = LocalShipment.objects.create(
            tenant=self.tenant, carrier=self.carrier, amount=D("450"), currency=self.ils,
            exchange_rate=D("1"), shipment=self._shipment("SH-0020", "ثلاجات"),
            delivery_date="2026-06-20", pickup_date="2026-06-20",
            expense_account=Account.objects.get(tenant=self.tenant, code="5305"))
        post_local_shipment_accrual(LocalShipment.objects.get(pk=local.pk))

    def test_payables_aging_total_matches_each_creditor_ledger_balance(self):
        self._seed()
        report = run_report("payables-aging", self.tenant.TenantID, {"as_of": "2026-12-31"})
        totals = {row["partner_id"]: D(row["total"]) for row in report["rows"]}

        # حاييم: (900 − 400) + (2,500 − 2,045) = 955؛ اسامه: 450 — كما في الدفتر بالضبط.
        self.assertEqual(totals.get(self.broker.id), D("955.00"))
        self.assertEqual(totals.get(self.carrier.id), D("450.00"))
        for partner in (self.broker, self.carrier):
            self.assertEqual(totals[partner.id], self._ledger_balance(partner), partner.name)

    def test_supplier_balances_lists_every_creditor_type_with_a_type_filter(self):
        self._seed()
        report = run_report("supplier-balances", self.tenant.TenantID, {})
        self.assertIn("partner_type", [c["key"] for c in report["columns"]])
        types = {row["partner_id"]: row["partner_type"] for row in report["rows"]}
        self.assertEqual(types.get(self.broker.id), "مخلّص جمركي")
        self.assertEqual(types.get(self.carrier.id), "ناقل محلي")
        broker_row = next(r for r in report["rows"] if r["partner_id"] == self.broker.id)
        self.assertEqual((D(broker_row["balance"]), broker_row["side"]), (D("955.00"), "دائن"))

        only_brokers = run_report("supplier-balances", self.tenant.TenantID, {"partner_type": "CustomsBroker"})
        self.assertEqual([r["partner_id"] for r in only_brokers["rows"]], [self.broker.id])

    def test_broker_card_lists_its_accruals_and_totals_them(self):
        """كرت المخلّص: «الفواتير» كانت فارغة و«إجمالي المشتريات» صفراً — مستحقّاته غائبة."""
        self._seed()
        rows = self.client.get(f"/api/partners/{self.broker.id}/invoices/", **self.h).json()
        self.assertEqual(
            sorted((r["document_type"], D(r["grand_total"]), D(r["amount_paid"]), D(r["remaining_balance"]))
                   for r in rows),
            [("LOGISTICS_CLEARANCE", D("900.00"), D("400.00"), D("500.00")),
             ("LOGISTICS_CLEARANCE", D("2500.00"), D("2045.00"), D("455.00"))])
        self.assertTrue(all(r["shipment_id"] and "SH-00" in r["document_number"] for r in rows), rows)

        profile = self.client.get(f"/api/partners/{self.broker.id}/profile/", **self.h).json()
        self.assertEqual(D(profile["total_purchases"]), D("3400.00"))
        self.assertIsNotNone(profile["last_transaction_date"])

    def test_customer_balances_keep_customers_only(self):
        self._seed()
        report = run_report("customer-balances", self.tenant.TenantID, {})
        self.assertNotIn(self.broker.id, [r["partner_id"] for r in report["rows"]])
