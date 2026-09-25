"""«ربط الفاتورة بسندها» في كشف حساب الطرف يشمل المستحقّات اللوجستية.

إنتاج (شركة 1): في كشف المخلّص حاييم كل مستحق تخليص منفصلٌ عن دفعته، لأن الربط كان
يعرف `PURCHASE_INVOICE` ↔ `SUPPLIER_PAYMENT` وحدهما. وسند #2460 (19,000) موزَّع على
SH-0019 وSH-0014 وSH-0015 لا يظهر في أيٍّ من مجموعاتها.
"""
from decimal import Decimal

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import partner_account_statement
from logistics.accruals import post_local_shipment_accrual
from logistics.models import LocalShipment, PurchaseInvoice
from logistics.tests.test_shipment_labels import _LabelBase
from sales.models import SupplierPayment, SupplierPaymentAllocation

D = lambda v: Decimal(str(v))


class StatementAccrualLinksTest(_LabelBase):
    def _statement(self, partner):
        return partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=partner.id, is_supplier=True, limit=50)

    def _rows(self, partner, reference_type):
        return [r for r in self._statement(partner)["results"] if r["reference_type"] == reference_type]

    def _allocate(self, voucher, allocations):
        res = self.client.post(
            f"/api/logistics/supplier-payments/{voucher.id}/allocate-accruals/",
            {"allocations": allocations}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)

    def test_clearance_joins_its_direct_payment(self):
        clearance = self._clearance(self._shipment("SH-0017", "شحنة رقع"), "900")
        res = self.client.post(
            f"/api/logistics/clearances/{clearance.pk}/pay_from_cashbox/",
            {"amount": "400", "cash_box_external_id": self.box.external_id, "payment_date": "2026-07-01"},
            format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.content)

        key = f"LOGISTICS_CLEARANCE:{clearance.pk}"
        (accrual,) = self._rows(self.broker, "LOGISTICS_CLEARANCE")
        (payment,) = self._rows(self.broker, "CLEARANCE_PAYMENT")
        self.assertEqual((accrual["link_key"], accrual["link_label"]), (key, "SH-0017 — شحنة رقع"))
        self.assertEqual((payment["link_key"], payment["link_label"]), (key, "SH-0017 — شحنة رقع"))

    def test_local_shipment_joins_its_carrier_payment_under_its_own_label(self):
        local = LocalShipment.objects.create(
            tenant=self.tenant, carrier=self.carrier, amount=D("450"), currency=self.ils,
            exchange_rate=D("1"), shipment=self._shipment("SH-0019", deals=[("", "داتا لوجر")]),
            delivery_date="2026-06-20", pickup_date="2026-06-20",
            expense_account=Account.objects.get(tenant=self.tenant, code="5305"))
        post_local_shipment_accrual(LocalShipment.objects.get(pk=local.pk))
        res = self.client.post(
            f"/api/logistics/local-shipments/{local.pk}/pay_from_cashbox/",
            {"amount": "450", "cash_box_external_id": self.box.external_id, "payment_date": "2026-07-01"},
            format="json", **self.h)
        self.assertIn(res.status_code, (200, 201), res.content)

        local.refresh_from_db()
        label = local.display_label
        self.assertTrue(label.startswith(f"{local.shipment_number} · SH-0019 — داتا لوجر"))
        (accrual,) = self._rows(self.carrier, "LOCAL_SHIPMENT")
        (payment,) = self._rows(self.carrier, "LOCAL_SHIPMENT_PAYMENT")
        for row in (accrual, payment):
            self.assertEqual((row["link_key"], row["shipment_label"]), (f"LOCAL_SHIPMENT:{local.pk}", label))

    def test_money_tab_hides_the_accrual_itself(self):
        """تبويب «المال» (`only_payments`): المستحق «فاتورة» المخلّص — لا يُعرض بين حركات المال،
        والرصيد الختامي يبقى على الحساب كلّه."""
        clearance = self._clearance(self._shipment("SH-0017", "شحنة رقع"), "900")
        self.client.post(
            f"/api/logistics/clearances/{clearance.pk}/pay_from_cashbox/",
            {"amount": "400", "cash_box_external_id": self.box.external_id, "payment_date": "2026-07-01"},
            format="json", **self.h)
        full = self._statement(self.broker)
        money = partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=self.broker.id, is_supplier=True, only_payments=True)
        self.assertEqual([r["reference_type"] for r in money["results"]], ["CLEARANCE_PAYMENT"])
        self.assertEqual(money["closing_balance"], full["closing_balance"])

    def test_voucher_allocated_to_one_accrual_joins_it(self):
        clearance = self._clearance(self._shipment("SH-0017", "شحنة رقع"), "2500")
        voucher = self._voucher(2045)
        self._allocate(voucher, [{"kind": "clearance", "id": clearance.pk, "amount": "2045"}])

        (row,) = self._rows(self.broker, "SUPPLIER_PAYMENT")
        self.assertEqual(row["link_key"], f"LOGISTICS_CLEARANCE:{clearance.pk}")
        self.assertEqual(row["link_label"], "SH-0017 — شحنة رقع")
        self.assertEqual(row["link_targets"], [])

    def test_voucher_over_three_accruals_stays_one_row_with_a_subline_per_group(self):
        clearances = [
            self._clearance(self._shipment(number, deals=[("", name)]), amount)
            for number, name, amount in (
                ("SH-0019", "داتا لوجر", "9000"), ("SH-0014", "ثلاجات", "6000"), ("SH-0015", "تلفزيونات", "5000"))
        ]
        voucher = self._voucher(19000)
        before = self._statement(self.broker)
        self._allocate(voucher, [
            {"kind": "clearance", "id": clearances[0].pk, "amount": "9000"},
            {"kind": "clearance", "id": clearances[1].pk, "amount": "6000"},
            {"kind": "clearance", "id": clearances[2].pk, "amount": "4000"},
        ])
        after = self._statement(self.broker)

        # ربطٌ بلا قيد: لا صفّ زائد ولا رصيد يتكرّر.
        self.assertEqual(after["count"], before["count"])
        self.assertEqual(after["closing_balance"], before["closing_balance"])
        self.assertEqual(
            [r["running_balance"] for r in after["results"]],
            [r["running_balance"] for r in before["results"]])

        (row,) = [r for r in after["results"] if r["reference_type"] == "SUPPLIER_PAYMENT"]
        self.assertIsNone(row["link_key"])
        self.assertEqual(row["link_count"], 3)
        self.assertEqual(row["link_label"], "3 مستحقات: SH-0019، SH-0014، SH-0015")
        self.assertEqual(
            [(t["key"], t["amount"]) for t in row["link_targets"]],
            [(f"LOGISTICS_CLEARANCE:{c.pk}", amount)
             for c, amount in zip(clearances, ("9000.00", "6000.00", "4000.00"))])
        # كل مرساة موجودة في الكشف — السطر الفرعي يجد مجموعته.
        anchors = {r["link_key"] for r in after["results"] if r["reference_type"] == "LOGISTICS_CLEARANCE"}
        self.assertEqual({t["key"] for t in row["link_targets"]}, anchors)

    def test_purchase_voucher_over_two_invoices_lists_both(self):
        account = self.supplier.linked_account
        invoices = []
        for number, total in (("PI-1", 300), ("PI-2", 200)):
            inv = PurchaseInvoice.objects.create(
                tenant=self.tenant, invoice_number=number, partner=self.supplier,
                invoice_date="2026-06-01", currency=self.ils, exchange_rate=D(1),
                grand_total=D(total), is_posted=True)
            self._journal("PURCHASE_INVOICE", inv.pk, account, credit=total)
            invoices.append(inv)
        payment = SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.supplier, payment_date="2026-06-05", amount=D(500),
            currency=self.ils, exchange_rate=D(1), cash_or_bank_account=self.cash, is_posted=True)
        for inv, amount in zip(invoices, (300, 200)):
            SupplierPaymentAllocation.objects.create(
                tenant=self.tenant, payment=payment, invoice=inv, amount=D(amount),
                amount_in_invoice_currency=D(amount))
        self._journal("SUPPLIER_PAYMENT", payment.pk, account, debit=500)

        (row,) = self._rows(self.supplier, "SUPPLIER_PAYMENT")
        self.assertIsNone(row["link_key"])
        self.assertEqual(row["link_label"], "2 فواتير: PI-1، PI-2")
        self.assertEqual(
            [(t["key"], t["label"], t["amount"]) for t in row["link_targets"]],
            [(f"PURCHASE_INVOICE:{invoices[0].pk}", "PI-1", "300.00"),
             (f"PURCHASE_INVOICE:{invoices[1].pk}", "PI-2", "200.00")])

    def _journal(self, reference_type, reference_id, account, *, debit=0, credit=0):
        jh = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date="2026-06-01", is_posted=True, exchange_rate=D(1),
            reference_type=reference_type, reference_id=reference_id)
        JournalLine.objects.create(
            tenant=self.tenant, journal=jh, account=account,
            debit=D(debit), credit=D(credit), partner=self.supplier)
