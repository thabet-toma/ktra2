"""دفعة وكيل الشحن من الصندوق بكبسة واحدة: تُنشأ وتُرحَّل معاً، وفشلُ الترحيل لا يترك دفعة.

إنتاج (شركة 1): من 11 دفعة وكيل واحدةٌ مرحّلة — الشاشة كانت تحفظها بـPATCH قائمة
الدفعات «مؤكّدة» بلا قيد، وزرّ الترحيل بلا مستدعٍ منذ f1afc66b. وأمر
`post_pending_agent_payments` يعرض القديم ويرحّل المختار وحده.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.models import Account, CashBoxLedgerAccount, JournalHeader, JournalLine
from accounting.services import create_fiscal_year
from logistics.models import LogisticsPayment, LogisticsShipment
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class _AgentBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="agentbox", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة دفعة الوكيل", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)
        cls.usd_box_account = Account.objects.create(
            tenant=cls.tenant, code="BOX-USD", name="صندوق دولار", account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="usd-box", name="صندوق دولار",
            currency_code="USD", account=cls.usd_box_account)
        cls.agent = Partner.objects.create(tenant=cls.tenant, name="yoyo", partner_type="FreightForwarder")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}
        self.shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="S-0011", shipping_agent=self.agent,
            total_shipping_cost_usd=D("1000"))

    def _pay(self, shipment=None, **overrides):
        body = {"amount": "500", "usd_to_ils": "3.24", "cash_box_external_id": self.box.external_id,
                "payment_date": "2026-07-05", "notes": "حوالة", **overrides}
        return self.client.post(
            f"/api/logistics/shipments/{(shipment or self.shipment).pk}/pay_agent_from_cashbox/",
            body, format="json", **self.h)

    def _base(self, journal, account_id):
        agg = JournalLine.objects.filter(journal=journal, account_id=account_id).aggregate(
            d=Sum("base_debit"), c=Sum("base_credit"))
        return (agg["d"] or D(0)), (agg["c"] or D(0))


class AgentPaymentFromCashBoxTest(_AgentBase):
    def test_one_click_creates_and_posts_the_payment(self):
        res = self._pay()
        self.assertEqual(res.status_code, 201, res.content)
        pay = LogisticsPayment.objects.get(shipment=self.shipment, deal__isnull=True)
        self.assertTrue(pay.is_posted)
        self.assertEqual((pay.status, pay.amount, pay.usd_to_ils), ("Confirmed", D("500.00"), D("3.24")))
        self.assertEqual(pay.cash_box_external_id, "usd-box")
        self.assertEqual(res.data["journal_id"], pay.journal_id)
        self.assertEqual(res.data["payment"]["journal"], pay.journal_id)
        self.agent.refresh_from_db()
        journal = JournalHeader.objects.get(pk=pay.journal_id)
        self.assertEqual(self._base(journal, self.agent.linked_account_id), (D("1620.00"), D(0)))
        self.assertEqual(self._base(journal, self.usd_box_account.id), (D(0), D("1620.00")))
        self.assertTrue(JournalLine.objects.filter(
            journal=journal, account_id=self.agent.linked_account_id, partner=self.agent).exists())

    def test_numbers_follow_the_existing_agent_payments(self):
        LogisticsPayment.objects.create(
            tenant=self.tenant, shipment=self.shipment, payment_number=4, title="قديمة",
            amount=D("10"), status="Pending")
        self.assertEqual(self._pay().status_code, 201)
        self.assertEqual(
            LogisticsPayment.objects.get(shipment=self.shipment, is_posted=True).payment_number, 5)

    def test_failed_posting_leaves_no_payment(self):
        no_agent = LogisticsShipment.objects.create(tenant=self.tenant, shipment_number="SH-0013")
        deleted = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="S-DEL", shipping_agent=self.agent)
        deleted.delete()
        cases = [
            ("no agent", self._pay(no_agent)),
            ("no rate", self._pay(usd_to_ils="")),
            ("zero rate", self._pay(usd_to_ils="0")),
            ("no box", self._pay(cash_box_external_id="")),
            ("unlinked box", self._pay(cash_box_external_id="nope")),
            ("zero amount", self._pay(amount="0")),
            ("deleted shipment", self._pay(deleted)),
        ]
        for label, res in cases:
            with self.subTest(label):
                self.assertIn(res.status_code, (400, 404), res.content)
        self.assertFalse(LogisticsPayment.all_objects.filter(deal__isnull=True).exists())

    def test_posting_error_rolls_back_the_created_payment(self):
        """الترحيل نفسه يفشل (فترة مالية خارج السنة) ⇒ لا دفعة «مؤكّدة» بلا قيد."""
        res = self._pay(payment_date="2031-01-01")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(LogisticsPayment.all_objects.filter(shipment=self.shipment).exists())

    def test_legacy_post_button_still_posts_through_the_same_service(self):
        pay = LogisticsPayment.objects.create(
            tenant=self.tenant, shipment=self.shipment, title="قديمة", amount=D("100"),
            status="Confirmed", usd_to_ils=D("3.5"), transfer_date="2026-06-20")
        res = self.client.post(
            f"/api/logistics/shipments/{self.shipment.pk}/post_agent_payment/{pay.pk}/",
            {"cash_box_external_id": self.box.external_id}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        pay.refresh_from_db()
        self.assertTrue(pay.is_posted)
        again = self.client.post(
            f"/api/logistics/shipments/{self.shipment.pk}/post_agent_payment/{pay.pk}/",
            {"cash_box_external_id": self.box.external_id}, format="json", **self.h)
        self.assertEqual(again.status_code, 400)
        self.assertEqual(JournalHeader.objects.filter(reference_type="LOGISTICS_PAYMENT", reference_id=pay.pk).count(), 1)


class PostPendingAgentPaymentsCommandTest(_AgentBase):
    def _pending(self, amount, rate, shipment=None):
        return LogisticsPayment.objects.create(
            tenant=self.tenant, shipment=shipment or self.shipment, title=f"P{amount}",
            amount=D(amount), status="Confirmed", usd_to_ils=D(rate) if rate else None,
            transfer_date="2026-06-20")

    def _run(self, *args):
        out = StringIO()
        call_command("post_pending_agent_payments", "--tenant", str(self.tenant.TenantID), *args, stdout=out)
        return out.getvalue()

    def test_report_writes_nothing_and_flags_what_needs_review(self):
        supplier_agent = Partner.objects.create(tenant=self.tenant, name="مورد", partner_type="Supplier")
        other = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="S-0010", shipping_agent=supplier_agent)
        no_agent = LogisticsShipment.objects.create(tenant=self.tenant, shipment_number="SH-0013")
        suspect = self._pending("816.08", "3.6")
        tiny = self._pending("0.01", "3.24", other)
        blocked = self._pending("722", "3.24", no_agent)
        no_rate = self._pending("100", None)

        report = self._run()
        self.assertIn(f"#{suspect.pk}", report)
        self.assertIn("السعر 3.6", report)
        self.assertIn("أقل من 1$", report)
        self.assertIn("نوعه Supplier", report)
        self.assertIn("لا تملك وكيل", report)
        self.assertIn("سعر الدولار", report)
        self.assertFalse(LogisticsPayment.objects.filter(pk__in=[suspect.pk, tiny.pk, blocked.pk, no_rate.pk],
                                                         is_posted=True).exists())
        self.assertFalse(JournalHeader.objects.filter(reference_type="LOGISTICS_PAYMENT").exists())

    def test_apply_posts_only_the_chosen_ids(self):
        chosen = self._pending("578.52", "3.24")
        left = self._pending("781.10", "3.24")
        out = self._run("--apply", "--box", self.box.external_id, "--ids", str(chosen.pk))
        self.assertIn(f"✓ #{chosen.pk}", out)
        chosen.refresh_from_db()
        left.refresh_from_db()
        self.assertTrue(chosen.is_posted)
        self.assertFalse(left.is_posted)
        journal = JournalHeader.objects.get(reference_type="LOGISTICS_PAYMENT", reference_id=chosen.pk)
        self.assertEqual(self._base(journal, self.usd_box_account.id), (D(0), D("1874.40")))

    def test_apply_needs_explicit_box_and_ids(self):
        self._pending("100", "3.24")
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            self._run("--apply")
        self.assertFalse(LogisticsPayment.objects.filter(is_posted=True).exists())
