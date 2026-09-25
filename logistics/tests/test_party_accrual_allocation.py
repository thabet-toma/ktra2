"""توزيع سند الصرف على مستحقّات الأطراف اللوجستية (FIFO أو يدوي) — المخلّص على
التخليصات، وكيل الشحن على استحقاق الشحن، الناقل على الإرساليات المحلية.

كان التوزيع (`allocate/`) يعرف فواتير الشراء وحدها، فسند المخلّص يبقى «تحت الحساب»
أبداً ولا يُعرف أيّ تخليصٍ سدّده. المتبقّي من مصدرٍ واحد
(`logistics/domain/party_accruals.py`): أسطر القيود الموسومة بالطرف.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounting.models import Account, CashBoxLedgerAccount
from accounting.services import create_fiscal_year
from logistics.accruals import (
    post_clearance_accrual,
    post_freight_accrual,
    post_local_shipment_accrual,
)
from logistics.domain.party_accruals import accrual_status, party_open_accruals
from logistics.models import (
    LocalShipment,
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsShipment,
)
from partners.models import Partner
from sales.models import SupplierPayment
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class PartyAccrualAllocationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="accralloc", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة توزيع المستحقات", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)

        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="BOX-ACC", name="صندوق شيكل",
            account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="acc-box", name="صندوق شيكل",
            currency_code="ILS", account=cls.cash)
        cls.broker = Partner.objects.create(tenant=cls.tenant, name="حاييم", partner_type="CustomsBroker")
        cls.agent = Partner.objects.create(tenant=cls.tenant, name="yoyo", partner_type="FreightForwarder")
        cls.carrier = Partner.objects.create(tenant=cls.tenant, name="اسامه", partner_type="LocalTransporter")
        expense = Account.objects.get(tenant=cls.tenant, code="5302")

        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-0013", shipping_agent=cls.agent,
            total_shipping_cost_usd=D("1000"), departure_date="2026-06-01")
        cls.old = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, customs_broker=cls.broker,
            clearance_date="2026-06-10", currency=cls.ils)
        cls.new = LogisticsClearance.objects.create(
            tenant=cls.tenant, customs_broker=cls.broker,
            shipment=LogisticsShipment.objects.create(tenant=cls.tenant, shipment_number="SH-0014"),
            clearance_date="2026-07-10", currency=cls.ils)
        for clearance, amount in ((cls.old, "600"), (cls.new, "400")):
            LogisticsClearanceLine.objects.create(
                clearance=clearance, seq=1, line_type="broker_commission", account=expense,
                description="رسوم تخليص", debit=D(amount), credit=D("0"))
        cls.local = LocalShipment.objects.create(
            tenant=cls.tenant, carrier=cls.carrier, amount=D("450"), currency=cls.ils,
            exchange_rate=D("1"), expense_account=Account.objects.get(tenant=cls.tenant, code="5305"),
            delivery_date="2026-06-20", pickup_date="2026-06-20")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        for clearance in (self.old, self.new):
            post_clearance_accrual(LogisticsClearance.objects.get(pk=clearance.pk))

    def _voucher(self, party, amount, date="2026-08-01"):
        res = self.client.post("/api/logistics/supplier-payments/", {
            "partner": party.id, "payment_date": date, "amount": str(amount),
            "currency": self.ils.CurrencyID, "exchange_rate": "1",
            "cash_or_bank_account": self.cash.id,
        }, format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["is_posted"])
        return SupplierPayment.objects.get(pk=res.data["id"])

    def _allocate(self, voucher, rows):
        return self.client.post(
            f"/api/logistics/supplier-payments/{voucher.id}/allocate-accruals/",
            {"allocations": rows}, format="json", **self.h)

    def _remaining(self, kind, obj):
        model = type(obj)
        return accrual_status(kind, model.objects.get(pk=obj.pk))["remaining"]

    def test_open_accruals_are_fifo_and_net_of_the_documents_own_payments(self):
        paid = self.client.post(
            f"/api/logistics/clearances/{self.old.pk}/pay_from_cashbox/",
            {"amount": "250", "cash_box_external_id": self.box.external_id, "payment_date": "2026-06-15"},
            format="json", **self.h)
        self.assertEqual(paid.status_code, 201, paid.content)

        res = self.client.get(
            f"/api/logistics/supplier-payments/logistics-accruals/?partner={self.broker.id}", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        rows = res.data["accruals"]
        self.assertEqual([(r["kind"], r["id"]) for r in rows], [("clearance", self.old.pk), ("clearance", self.new.pk)])
        self.assertEqual(D(rows[0]["due"]), D("600.00"))
        self.assertEqual(D(rows[0]["paid"]), D("250.00"))
        self.assertEqual(D(rows[0]["remaining"]), D("350.00"))
        self.assertIn("SH-0013", rows[0]["label"])

    def test_fifo_suggestion_then_allocation_settles_oldest_first(self):
        voucher = self._voucher(self.broker, 800)
        sug = self.client.get(
            f"/api/logistics/supplier-payments/suggest-fifo-accruals/?partner={self.broker.id}&amount=800",
            **self.h)
        self.assertEqual(sug.status_code, 200, sug.data)
        rows = sug.data["allocations"]
        self.assertEqual([(r["id"], D(r["amount"])) for r in rows],
                         [(self.old.pk, D("600.00")), (self.new.pk, D("200.00"))])

        res = self._allocate(voucher, [{"kind": r["kind"], "id": r["id"], "amount": r["amount"]} for r in rows])
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(D(res.data["unallocated_amount"]), D("0.00"))
        self.assertEqual(len(res.data["logistics_allocations"]), 2)
        self.assertEqual(self._remaining("clearance", self.old), D("0.00"))
        self.assertEqual(self._remaining("clearance", self.new), D("200.00"))
        # سدّد الأقدم فخرج من القائمة المفتوحة.
        self.assertEqual([r["id"] for r in party_open_accruals(self.tenant.TenantID, self.broker.id)], [self.new.pk])

    def test_manual_allocation_is_capped_by_remaining_and_by_the_voucher(self):
        voucher = self._voucher(self.broker, 500)
        over_doc = self._allocate(voucher, [{"kind": "clearance", "id": self.new.pk, "amount": "450"}])
        self.assertEqual(over_doc.status_code, 400)
        self.assertIn("يتجاوز المتبقّي", str(over_doc.data))
        over_voucher = self._allocate(voucher, [
            {"kind": "clearance", "id": self.old.pk, "amount": "300"},
            {"kind": "clearance", "id": self.new.pk, "amount": "300"},
        ])
        self.assertEqual(over_voucher.status_code, 400)
        ok = self._allocate(voucher, [{"kind": "clearance", "id": self.new.pk, "amount": "150"}])
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(D(ok.data["unallocated_amount"]), D("350.00"))
        self.assertEqual(self._remaining("clearance", self.new), D("250.00"))

    def test_accrual_of_another_party_is_refused(self):
        post_local_shipment_accrual(LocalShipment.objects.get(pk=self.local.pk))
        voucher = self._voucher(self.broker, 100)
        res = self._allocate(voucher, [{"kind": "local", "id": self.local.pk, "amount": "100"}])
        self.assertEqual(res.status_code, 400)
        self.assertIn("لا يخصّ طرف السند", str(res.data))

    def test_invoice_allocation_sees_the_accrual_allocations(self):
        """سندٌ واحد لا يُوزَّع مرّتين: مرةً على المستحقّات ومرةً على فواتير الشراء."""
        from sales.services import allocate_supplier_payment

        voucher = self._voucher(self.broker, 500)
        self.assertEqual(self._allocate(voucher, [{"kind": "clearance", "id": self.old.pk, "amount": "500"}]).status_code, 200)
        with self.assertRaises(ValidationError) as ctx:
            allocate_supplier_payment(voucher, [{"invoice": 999999, "amount": "100"}])
        self.assertIn("يتجاوز مبلغ السند", str(ctx.exception))

    def test_deallocate_and_unpost_return_the_amount_on_account(self):
        voucher = self._voucher(self.broker, 300)
        res = self._allocate(voucher, [{"kind": "clearance", "id": self.old.pk, "amount": "300"}])
        alloc_id = res.data["logistics_allocations"][0]["id"]
        self.assertEqual(self._remaining("clearance", self.old), D("300.00"))

        unposted = self.client.post(f"/api/logistics/supplier-payments/{voucher.id}/unpost/", {}, format="json", **self.h)
        self.assertEqual(unposted.status_code, 200, unposted.content)
        self.assertEqual(self._remaining("clearance", self.old), D("600.00"))
        reposted = self.client.post(f"/api/logistics/supplier-payments/{voucher.id}/post/", {}, format="json", **self.h)
        self.assertEqual(reposted.status_code, 200, reposted.content)
        self.assertEqual(self._remaining("clearance", self.old), D("300.00"))

        freed = self.client.post(
            f"/api/logistics/supplier-payments/{voucher.id}/deallocate-accrual/",
            {"allocation": alloc_id}, format="json", **self.h)
        self.assertEqual(freed.status_code, 200, freed.data)
        self.assertEqual(D(freed.data["unallocated_amount"]), D("300.00"))
        self.assertEqual(self._remaining("clearance", self.old), D("600.00"))

    def test_unposted_voucher_cannot_be_allocated(self):
        voucher = self._voucher(self.broker, 100)
        SupplierPayment.objects.filter(pk=voucher.pk).update(is_posted=False)
        res = self._allocate(voucher, [{"kind": "clearance", "id": self.old.pk, "amount": "100"}])
        self.assertEqual(res.status_code, 400)
        self.assertIn("رحّل", str(res.data))

    def test_agent_voucher_on_freight_and_carrier_voucher_on_local_shipment(self):
        post_freight_accrual(LogisticsShipment.objects.get(pk=self.shipment.pk), D("3.6"))
        post_local_shipment_accrual(LocalShipment.objects.get(pk=self.local.pk))

        agent_rows = party_open_accruals(self.tenant.TenantID, self.agent.id)
        self.assertEqual([(r["kind"], D(r["remaining"])) for r in agent_rows], [("freight", D("3600.00"))])
        agent_voucher = self._voucher(self.agent, 1000)
        self.assertEqual(self._allocate(agent_voucher, [{"kind": "freight", "id": self.shipment.pk, "amount": "1000"}]).status_code, 200)
        self.assertEqual(self._remaining("freight", self.shipment), D("2600.00"))

        carrier_voucher = self._voucher(self.carrier, 450)
        self.assertEqual(self._allocate(carrier_voucher, [{"kind": "local", "id": self.local.pk, "amount": "450"}]).status_code, 200)
        self.assertEqual(self._remaining("local", self.local), D("0.00"))

    def test_document_screens_read_remaining_from_the_same_source(self):
        """شاشة الاستيراد تقرأ `remaining_balance` من مسلسل التخليص/الإرسالية — كان
        بنوده ناقص دفعاته فيغفل سند المخلّص الموزَّع عليه ويعرض متبقّياً أكبر من الحقيقي."""
        voucher = self._voucher(self.broker, 500)
        self.assertEqual(self._allocate(voucher, [{"kind": "clearance", "id": self.old.pk, "amount": "500"}]).status_code, 200)
        row = self.client.get(f"/api/logistics/clearances/{self.old.pk}/", **self.h).data
        self.assertEqual((D(row["amount_paid"]), D(row["remaining_balance"])), (D("500.00"), D("100.00")))
        self.assertEqual(row["payment_status"], "partially_paid")

        # قبل ترحيل الاستحقاق: تقدير الإرسالية (مبلغها ناقص دفعاتها) — لا قيد يُقرأ.
        draft = self.client.get(f"/api/logistics/local-shipments/{self.local.pk}/", **self.h).data
        self.assertEqual(D(draft["remaining_balance"]), D("450.00"))
        post_local_shipment_accrual(LocalShipment.objects.get(pk=self.local.pk))
        carrier_voucher = self._voucher(self.carrier, 450)
        self.assertEqual(self._allocate(carrier_voucher, [{"kind": "local", "id": self.local.pk, "amount": "450"}]).status_code, 200)
        posted = self.client.get(f"/api/logistics/local-shipments/{self.local.pk}/", **self.h).data
        self.assertEqual((D(posted["remaining_balance"]), posted["payment_status"]), (D("0.00"), "paid"))
