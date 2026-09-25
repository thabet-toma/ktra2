"""اسم الشحنة مع رقمها في كل مكان، وتبويب «الدفعات» يعرض السندات الموزَّعة.

إنتاج (شركة 1): سند صرف #2459 لحاييم وُزِّع 2,045 على تخليص SH-0017 و482 على
SH-0019؛ رأس التخليص صحيح (amount_paid) لكن `/clearances/{id}/payments/` كان يقرأ
`LogisticsClearancePayment` وحدها فيرجع [] — تبويبٌ فارغ تحت رأسٍ يقول «مدفوع».
وكشف الحساب والقوائم تعرض «SH-0017» وحده فلا يُعرف ما هي.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, CashBoxLedgerAccount, JournalHeader
from accounting.services import create_fiscal_year
from logistics.accruals import post_clearance_accrual, post_freight_accrual, post_local_shipment_accrual
from logistics.models import (
    LocalShipment,
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsDeal,
    LogisticsShipment,
    LogisticsShipmentDeal,
)
from partners.models import Partner
from sales.models import SupplierPayment
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class _LabelBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="shiplabel", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة اسم الشحنة", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="BOX-LBL", name="صندوق شيكل", account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="lbl-box", name="صندوق شيكل", currency_code="ILS", account=cls.cash)
        cls.broker = Partner.objects.create(tenant=cls.tenant, name="حاييم", partner_type="CustomsBroker")
        cls.carrier = Partner.objects.create(tenant=cls.tenant, name="اسامه", partner_type="LocalTransporter")
        cls.supplier = Partner.objects.create(tenant=cls.tenant, name="جوتو", partner_type="Supplier")
        cls.expense = Account.objects.get(tenant=cls.tenant, code="5302")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _shipment(self, number, name=None, deals=()):
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number=number, shipment_name=name)
        for i, (short_name, description) in enumerate(deals, start=1):
            deal = LogisticsDeal.objects.create(
                tenant=self.tenant, ref_number=f"{number}-D{i}", partner=self.supplier,
                order_date="2026-05-01", short_name=short_name, description=description)
            LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
        return shipment

    def _clearance(self, shipment, amount):
        clearance = LogisticsClearance.objects.create(
            tenant=self.tenant, shipment=shipment, customs_broker=self.broker,
            clearance_date="2026-06-10", currency=self.ils)
        LogisticsClearanceLine.objects.create(
            clearance=clearance, seq=1, line_type="broker_commission", account=self.expense,
            description="رسوم تخليص", debit=D(amount), credit=D("0"))
        post_clearance_accrual(LogisticsClearance.objects.get(pk=clearance.pk))
        return LogisticsClearance.objects.get(pk=clearance.pk)

    def _voucher(self, amount):
        res = self.client.post("/api/logistics/supplier-payments/", {
            "partner": self.broker.id, "payment_date": "2026-08-01", "amount": str(amount),
            "currency": self.ils.CurrencyID, "exchange_rate": "1", "cash_or_bank_account": self.cash.id,
        }, format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.data)
        return SupplierPayment.objects.get(pk=res.data["id"])


class ShipmentDisplayLabelTest(_LabelBase):
    def test_name_then_deal_descriptions_then_supplier(self):
        named = self._shipment("SH-0017", "شحنة رقع", deals=[("", "لا يُقرأ")])
        self.assertEqual(named.display_label, "SH-0017 — شحنة رقع")

        by_deals = self._shipment("SH-0015", deals=[
            ("", "تلفزيونات 32 انش و 43 انش\nتفاصيل السطر الثاني"), ("داتا لوجر", "وصف طويل")])
        self.assertEqual(by_deals.display_label, "SH-0015 — تلفزيونات 32 انش و 43 انش، داتا لوجر")

        long_one = self._shipment("SH-0020", deals=[("س" * 80, "")])
        name = long_one.display_label.split(" — ", 1)[1]
        self.assertLessEqual(len(name), 60)
        self.assertTrue(name.endswith("…"))

        by_supplier = self._shipment("SH-0019", deals=[("", "")])
        self.assertEqual(by_supplier.display_label, "SH-0019 — جوتو")

        bare = self._shipment("SH-0021")
        self.assertEqual(bare.display_label, "SH-0021")

    def test_serializers_carry_the_label_and_the_list_searches_deal_names(self):
        shipment = self._shipment("SH-0019", deals=[("", "داتا لوجر")])
        clearance = self._clearance(shipment, "500")
        local = LocalShipment.objects.create(
            tenant=self.tenant, carrier=self.carrier, amount=D("100"), currency=self.ils,
            exchange_rate=D("1"), shipment=shipment,
            expense_account=Account.objects.get(tenant=self.tenant, code="5305"))
        expected = "SH-0019 — داتا لوجر"
        self.assertEqual(self.client.get(f"/api/logistics/shipments/{shipment.pk}/", **self.h).data["shipment_label"], expected)
        self.assertEqual(self.client.get(f"/api/logistics/clearances/{clearance.pk}/", **self.h).data["shipment_label"], expected)
        self.assertEqual(self.client.get(f"/api/logistics/local-shipments/{local.pk}/", **self.h).data["shipment_label"], expected)

        listed = self.client.get("/api/logistics/shipments/?search=داتا", **self.h).data
        rows = listed["results"] if isinstance(listed, dict) else listed
        self.assertEqual([(r["id"], r["shipment_label"]) for r in rows], [(shipment.pk, expected)])

    def test_new_journals_describe_the_shipment_by_its_label(self):
        clearance = self._clearance(self._shipment("SH-0017", "شحنة رقع"), "300")
        journal = JournalHeader.objects.get(pk=clearance.journal_id)
        self.assertEqual(journal.description, "استحقاق تخليص SH-0017 — شحنة رقع | حاييم")


class PaymentsTabShowsAllocatedVouchersTest(_LabelBase):
    def test_clearance_payments_include_the_allocated_voucher_and_sum_to_amount_paid(self):
        clearance = self._clearance(self._shipment("SH-0017", "شحنة رقع"), "2500")
        direct = self.client.post(
            f"/api/logistics/clearances/{clearance.pk}/pay_from_cashbox/",
            {"amount": "455", "cash_box_external_id": self.box.external_id, "payment_date": "2026-07-01"},
            format="json", **self.h)
        self.assertEqual(direct.status_code, 201, direct.content)
        voucher = self._voucher(2527)
        allocated = self.client.post(
            f"/api/logistics/supplier-payments/{voucher.id}/allocate-accruals/",
            {"allocations": [{"kind": "clearance", "id": clearance.pk, "amount": "2045"}]},
            format="json", **self.h)
        self.assertEqual(allocated.status_code, 200, allocated.content)

        rows = self.client.get(f"/api/logistics/clearances/{clearance.pk}/payments/", **self.h).data
        head = self.client.get(f"/api/logistics/clearances/{clearance.pk}/", **self.h).data
        by_type = {r.get("row_type", "payment"): r for r in rows}
        self.assertEqual(set(by_type), {"payment", "voucher_allocation"})
        alloc = by_type["voucher_allocation"]
        self.assertEqual((alloc["voucher_id"], D(alloc["amount"]), alloc["kind_label"]),
                         (voucher.id, D("2045.00"), "سند صرف — توزيع"))
        self.assertEqual(alloc["payment_date"], "2026-08-01")
        self.assertEqual(alloc["journal"], voucher.journal_id)
        self.assertEqual(alloc["shipment_label"], "SH-0017 — شحنة رقع")
        self.assertEqual(sum(D(r["amount"]) for r in rows), D(head["amount_paid"]))
        self.assertEqual(D(head["amount_paid"]), D("2500.00"))

        # السند نفسه يسمّي ما وُزِّع عليه.
        shown = self.client.get(f"/api/logistics/supplier-payments/{voucher.id}/", **self.h).data
        self.assertEqual(shown["logistics_allocations"][0]["shipment_label"], "SH-0017 — شحنة رقع")
        self.assertIn("SH-0017 — شحنة رقع", shown["logistics_allocations"][0]["label"])

    def test_local_shipment_payments_include_allocations_in_its_currency(self):
        shipment = self._shipment("SH-0019", deals=[("", "داتا لوجر")])
        local = LocalShipment.objects.create(
            tenant=self.tenant, carrier=self.carrier, amount=D("450"), currency=self.ils,
            exchange_rate=D("1"), shipment=shipment, delivery_date="2026-06-20", pickup_date="2026-06-20",
            expense_account=Account.objects.get(tenant=self.tenant, code="5305"))
        post_local_shipment_accrual(LocalShipment.objects.get(pk=local.pk))
        res = self.client.post("/api/logistics/supplier-payments/", {
            "partner": self.carrier.id, "payment_date": "2026-08-01", "amount": "300",
            "currency": self.ils.CurrencyID, "exchange_rate": "1", "cash_or_bank_account": self.cash.id,
        }, format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(self.client.post(
            f"/api/logistics/supplier-payments/{res.data['id']}/allocate-accruals/",
            {"allocations": [{"kind": "local", "id": local.pk, "amount": "300"}]},
            format="json", **self.h).status_code, 200)
        rows = self.client.get(f"/api/logistics/local-shipments/{local.pk}/payments/", **self.h).data
        head = self.client.get(f"/api/logistics/local-shipments/{local.pk}/", **self.h).data
        self.assertEqual([(r["row_type"], D(r["amount"])) for r in rows], [("voucher_allocation", D("300.00"))])
        self.assertEqual(D(head["amount_paid"]), D("300.00"))

    def test_freight_accrual_shows_the_agents_allocated_voucher_in_dollars(self):
        agent = Partner.objects.create(tenant=self.tenant, name="yoyo", partner_type="FreightForwarder")
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="S-0012", shipment_name="شحنة رقع", shipping_agent=agent,
            total_shipping_cost_usd=D("1000"), departure_date="2026-06-01")
        post_freight_accrual(LogisticsShipment.objects.get(pk=shipment.pk), D("3.6"))
        res = self.client.post("/api/logistics/supplier-payments/", {
            "partner": agent.id, "payment_date": "2026-08-01", "amount": "720",
            "currency": self.ils.CurrencyID, "exchange_rate": "1", "cash_or_bank_account": self.cash.id,
        }, format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(self.client.post(
            f"/api/logistics/supplier-payments/{res.data['id']}/allocate-accruals/",
            {"allocations": [{"kind": "freight", "id": shipment.pk, "amount": "720"}]},
            format="json", **self.h).status_code, 200)
        rows = self.client.get(f"/api/logistics/shipments/{shipment.pk}/", **self.h).data["freight_voucher_rows"]
        self.assertEqual([(r["voucher_id"], D(r["amount"]), r["shipment_label"]) for r in rows],
                         [(res.data["id"], D("200.00"), "S-0012 — شحنة رقع")])


class PartnerStatementShowsShipmentNameTest(_LabelBase):
    def test_statement_rows_carry_the_live_label_of_their_document(self):
        shipment = self._shipment("SH-0019", deals=[("", "داتا لوجر")])
        clearance = self._clearance(shipment, "482")
        voucher = self._voucher(482)
        self.client.post(
            f"/api/logistics/supplier-payments/{voucher.id}/allocate-accruals/",
            {"allocations": [{"kind": "clearance", "id": clearance.pk, "amount": "482"}]},
            format="json", **self.h)
        # الاسم يتغيّر بعد الترحيل: الكشف يقرأ الحيّ من المستند لا نصّ القيد القديم.
        LogisticsShipment.objects.filter(pk=shipment.pk).update(shipment_name="شحنة داتا")

        rows = self.client.get(f"/api/partners/{self.broker.id}/statement/", **self.h).data["results"]
        labels = {r["reference_type"]: r["shipment_label"] for r in rows}
        self.assertEqual(labels["LOGISTICS_CLEARANCE"], "SH-0019 — شحنة داتا")
        self.assertEqual(labels["SUPPLIER_PAYMENT"], "SH-0019 — شحنة داتا")
