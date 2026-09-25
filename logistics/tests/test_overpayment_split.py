"""دفعة تخليص/نقل أكبر من متبقّي مستحقّها: تُسجَّل بالمتبقّي، والزائد سند صرف
«دفعة تحت الحساب» تلقائي بنفس التاريخ والصندوق، بلا توزيع.

إنتاج: دفعة التخليص #4 (9,600 لحاييم) على تخليص مستحقّه 7,073 — الزائد 2,527
عالق على التخليص فيُظهره «مدفوعاً أكثر» ولا يُرى رصيداً للمخلّص يُوزَّع لاحقاً.
وأمرُ `split_logistics_overpayments` يصلح الموجود بعكس القيد لا حذفه.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APITestCase

from accounting.models import Account, AccountingAuditLog, CashBoxLedgerAccount, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, post_journal
from logistics.accruals import post_clearance_accrual, post_local_shipment_accrual
from logistics.models import (
    LocalShipment,
    LocalShipmentPayment,
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsClearancePayment,
    LogisticsShipment,
)
from partners.models import Partner
from sales.models import SupplierPayment
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class _Base(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username=f"split-{cls.__name__}", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company(f"شركة {cls.__name__}", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="BOX-SPL", name="صندوق شيكل", account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="spl-box", name="صندوق شيكل", currency_code="ILS", account=cls.cash)
        cls.broker = Partner.objects.create(tenant=cls.tenant, name="حاييم", partner_type="CustomsBroker")
        cls.carrier = Partner.objects.create(tenant=cls.tenant, name="اسامه", partner_type="LocalTransporter")
        cls.shipment = LogisticsShipment.objects.create(tenant=cls.tenant, shipment_number="SH-0013")
        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, customs_broker=cls.broker,
            clearance_date="2026-06-10", currency=cls.ils)
        LogisticsClearanceLine.objects.create(
            clearance=cls.clearance, seq=1, line_type="broker_commission",
            account=Account.objects.get(tenant=cls.tenant, code="5302"),
            description="رسوم تخليص", debit=D("7073"), credit=D("0"))
        cls.local = LocalShipment.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, carrier=cls.carrier, amount=D("400"),
            currency=cls.ils, exchange_rate=D("1"),
            expense_account=Account.objects.get(tenant=cls.tenant, code="5305"),
            delivery_date="2026-06-12")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        self.broker.refresh_from_db()
        self.carrier.refresh_from_db()

    def _accrue_clearance(self):
        post_clearance_accrual(LogisticsClearance.objects.get(pk=self.clearance.pk))

    def _net(self, account_id, partner_id=None):
        qs = JournalLine.objects.filter(tenant=self.tenant, account_id=account_id)
        if partner_id:
            qs = qs.filter(partner_id=partner_id)
        d = sum((l.debit for l in qs), D("0"))
        c = sum((l.credit for l in qs), D("0"))
        return d - c

    def _pay_clearance(self, amount, **extra):
        return self.client.post(
            f"/api/logistics/clearances/{self.clearance.pk}/pay_from_cashbox/",
            {"amount": str(amount), "cash_box_external_id": self.box.external_id,
             "payment_date": "2026-07-01", **extra},
            format="json", **self.h)

    def _vouchers(self, partner):
        return SupplierPayment.objects.filter(tenant=self.tenant, partner=partner)


class OverpaymentSplitAtPostingTest(_Base):
    def test_clearance_overpayment_is_recorded_at_remaining_plus_on_account_voucher(self):
        self._accrue_clearance()
        res = self._pay_clearance(9600)
        self.assertEqual(res.status_code, 201, res.content)
        pay = LogisticsClearancePayment.objects.get(clearance=self.clearance)
        self.assertEqual(pay.amount, D("7073.00"))
        voucher = self._vouchers(self.broker).get()
        self.assertEqual(voucher.amount, D("2527.00"))
        self.assertTrue(voucher.is_posted)
        self.assertEqual(str(voucher.payment_date), "2026-07-01")
        self.assertEqual(voucher.cash_or_bank_account_id, self.cash.id)
        self.assertIn("زيادة دفعة", voucher.notes)
        self.assertFalse(voucher.allocations.exists())
        self.assertFalse(voucher.logistics_allocations.exists())
        self.assertEqual(D(res.json()["on_account_voucher"]["amount"]), D("2527.00"))
        # الدفتر كما لو دُفع 9,600 دفعةً واحدة: المخلّص مدينٌ لنا بـ2,527 والصندوق نقص 9,600.
        self.assertEqual(self._net(self.broker.linked_account_id, self.broker.id), D("2527.00"))
        self.assertEqual(self._net(self.cash.id), D("-9600.00"))

    def test_second_payment_splits_only_what_exceeds_the_rest(self):
        self._accrue_clearance()
        self.assertEqual(self._pay_clearance(5000).status_code, 201)
        self.assertEqual(self._pay_clearance(3000).status_code, 201)
        amounts = sorted(LogisticsClearancePayment.objects.filter(clearance=self.clearance).values_list("amount", flat=True))
        self.assertEqual(amounts, [D("2073.00"), D("5000.00")])
        self.assertEqual(self._vouchers(self.broker).get().amount, D("927.00"))

    def test_payment_within_remaining_creates_no_voucher(self):
        self._accrue_clearance()
        self.assertEqual(self._pay_clearance(7073).status_code, 201)
        self.assertFalse(self._vouchers(self.broker).exists())

    def test_advance_before_the_accrual_is_not_split(self):
        self.assertEqual(self._pay_clearance(9600).status_code, 201)
        self.assertEqual(LogisticsClearancePayment.objects.get(clearance=self.clearance).amount, D("9600.00"))
        self.assertFalse(self._vouchers(self.broker).exists())

    def test_payment_on_a_settled_clearance_becomes_a_voucher_entirely(self):
        self._accrue_clearance()
        self.assertEqual(self._pay_clearance(7073).status_code, 201)
        res = self._pay_clearance(100)
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(LogisticsClearancePayment.objects.filter(clearance=self.clearance).count(), 1)
        self.assertEqual(self._vouchers(self.broker).get().amount, D("100.00"))
        self.assertEqual(self._net(self.cash.id), D("-7173.00"))

    def test_local_shipment_overpayment_splits_to_the_carrier(self):
        post_local_shipment_accrual(LocalShipment.objects.get(pk=self.local.pk))
        res = self.client.post(
            f"/api/logistics/local-shipments/{self.local.pk}/pay_from_cashbox/",
            {"amount": "450", "cash_box_external_id": self.box.external_id, "payment_date": "2026-07-02"},
            format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(LocalShipmentPayment.objects.get(local_shipment=self.local).amount, D("400.00"))
        self.assertEqual(self._vouchers(self.carrier).get().amount, D("50.00"))

    def test_accrual_status_endpoint_feeds_the_warning(self):
        self._accrue_clearance()
        self._pay_clearance(5000)
        res = self.client.get(
            f"/api/logistics/supplier-payments/accrual-status/?kind=clearance&id={self.clearance.pk}", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(D(res.json()["remaining"]), D("2073.00"))
        self.assertTrue(res.json()["accrual_posted"])


class SplitLogisticsOverpaymentsCommandTest(_Base):
    def _legacy_clearance_payment(self, amount):
        """دفعةٌ زائدة كما رحّلها النظام قبل الفصل: قيدٌ واحد بكامل المبلغ."""
        pay = LogisticsClearancePayment.objects.create(
            tenant=self.tenant, clearance=self.clearance, customs_broker=self.broker,
            amount=D(amount), currency=self.ils, payment_date="2026-07-01",
            payment_purpose="clearance_fee", cash_box_external_id=self.box.external_id)
        journal = post_journal(
            tenant_id=self.tenant.TenantID, transaction_date="2026-07-01",
            reference_type="CLEARANCE_PAYMENT", reference_id=pay.id, description="دفع تخليص",
            lines_data=[
                {"account": self.broker.linked_account_id, "partner": self.broker.id,
                 "debit": D(amount), "credit": D("0"), "description": "دفع تخليص"},
                {"account": self.cash.id, "debit": D("0"), "credit": D(amount), "description": "صندوق"},
            ])
        pay.journal = journal
        pay.is_posted = True
        pay.save(update_fields=["journal", "is_posted"])
        return pay

    def _run(self, *args):
        out = StringIO()
        call_command("split_logistics_overpayments", "--tenant", str(self.tenant.TenantID), *args, stdout=out)
        return out.getvalue()

    def test_report_then_apply_then_idempotent(self):
        self._accrue_clearance()
        pay = self._legacy_clearance_payment(9600)
        old_journal_id = pay.journal_id
        broker_before = self._net(self.broker.linked_account_id, self.broker.id)
        box_before = self._net(self.cash.id)

        report = self._run()
        self.assertIn(f"#{pay.id}", report)
        self.assertIn("2527", report)
        pay.refresh_from_db()
        self.assertEqual(pay.amount, D("9600.00"))
        self.assertFalse(self._vouchers(self.broker).exists())

        self._run("--apply")
        pay.refresh_from_db()
        self.assertEqual(pay.amount, D("7073.00"))
        self.assertNotEqual(pay.journal_id, old_journal_id)
        # عكسٌ لا حذف: القيد الأصلي باقٍ ومعه عكسه.
        self.assertTrue(JournalHeader.objects.filter(pk=old_journal_id).exists())
        self.assertTrue(JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="CLEARANCE_PAYMENT_SPLIT_REVERSAL", reference_id=pay.id).exists())
        voucher = self._vouchers(self.broker).get()
        self.assertEqual(voucher.amount, D("2527.00"))
        self.assertTrue(voucher.is_posted)
        self.assertEqual(str(voucher.payment_date), "2026-07-01")
        self.assertEqual(voucher.cash_or_bank_account_id, self.cash.id)
        self.assertEqual(self._net(self.broker.linked_account_id, self.broker.id), broker_before)
        self.assertEqual(self._net(self.cash.id), box_before)
        self.assertTrue(AccountingAuditLog.objects.filter(
            model_name="LogisticsClearancePayment", object_id=pay.id).exists())

        again = self._run("--apply")
        self.assertIn("0 دفعة زائدة", again)
        self.assertEqual(self._vouchers(self.broker).count(), 1)

    def test_unposting_the_clearance_removes_the_split_journals_too(self):
        """إلغاء ترحيل التخليص يحذف قيود دفعاته بمراجعها — وقيدا الفصل منها، وإلا بقي
        العكس وإعادة الترحيل بأثرٍ وهمي على المخلّص والصندوق."""
        self._accrue_clearance()
        pay = self._legacy_clearance_payment(9600)
        self._run("--apply")
        res = self.client.post(f"/api/logistics/clearances/{self.clearance.pk}/unpost/", {}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(JournalHeader.objects.filter(
            tenant=self.tenant, reference_id=pay.id, reference_type__startswith="CLEARANCE_PAYMENT").exists())
        # يبقى سند «تحت الحساب» وحده: خرج من الصندوق فعلاً.
        self.assertEqual(self._net(self.cash.id), D("-2527.00"))

    def test_local_shipment_payment_is_split_too(self):
        post_local_shipment_accrual(LocalShipment.objects.get(pk=self.local.pk))
        pay = LocalShipmentPayment.objects.create(
            tenant=self.tenant, local_shipment=self.local, amount=D("450"), currency=self.ils,
            exchange_rate=D("1"), payment_date="2026-07-02", cash_box_external_id=self.box.external_id)
        pay.journal = post_journal(
            tenant_id=self.tenant.TenantID, transaction_date="2026-07-02",
            reference_type="LOCAL_SHIPMENT_PAYMENT", reference_id=pay.id, description="دفع نقل",
            lines_data=[
                {"account": self.carrier.linked_account_id, "partner": self.carrier.id,
                 "debit": D("450"), "credit": D("0"), "description": "دفع للناقل"},
                {"account": self.cash.id, "debit": D("0"), "credit": D("450"), "description": "صندوق"},
            ])
        pay.is_posted = True
        pay.save(update_fields=["journal", "is_posted"])

        self._run("--apply")
        pay.refresh_from_db()
        self.assertEqual(pay.amount, D("400.00"))
        self.assertEqual(self._vouchers(self.carrier).get().amount, D("50.00"))
