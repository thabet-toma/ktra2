"""دفعة الاستيراد بالدولار تُرحَّل بقيمتها بالشيكل (amount × usd_to_ils) — مصدر واحد مع
تكلفة البضاعة في الفاتورة الدولية — وأمر audit_deal_payment_currency يصحّح القديم.

إنتاج (شركة 1، D-0105): صفقة عملتها ILS، دفعتان 1,650$ و3,850$ بسعر 3.24 = 17,820 ₪،
والقيدان يُدينان المورد 5,500 فقط. وفرعٌ آخر (عملة USD بلا طبقات FIFO) يحوّل مرتين.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.models import Account, AccountingAuditLog, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, post_journal
from logistics.models import LogisticsDeal, LogisticsPayment, LogisticsShipment, PurchaseInvoice
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class DealPaymentCurrencyTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dpc", password="x", email="dpc@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة العملة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        ap = Account.objects.create(tenant=cls.tenant, code="AP-JT", name="ذمم جوتو",
            account_type="Liability", is_active=True)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="جوتو", partner_type="Supplier", linked_account=ap)
        cls.bank = Account.objects.create(
            tenant=cls.tenant, code="BANK-ILS", name="بنك شيكل",
            account_type="Asset", is_active=True)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _deal(self, ref):
        return LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number=ref, partner=self.supplier,
            order_date="2026-06-20", total_amount=D("10000"))

    def _payment(self, deal, amount, rate="3.24"):
        return LogisticsPayment.objects.create(
            deal=deal, title=f"P{amount}", amount=D(amount), status="Confirmed",
            usd_to_ils=D(rate), transfer_date="2026-06-20")

    def _base(self, journal, account):
        agg = JournalLine.objects.filter(journal=journal, account=account).aggregate(
            d=Sum("base_debit"), c=Sum("base_credit"))
        return (agg["d"] or D(0)), (agg["c"] or D(0))

    def test_ils_labelled_deal_payment_posts_amount_times_rate(self):
        deal = self._deal("D-0105")
        pay = self._payment(deal, "1650")
        resp = self.client.post(
            f"/api/logistics/deals/{deal.pk}/post_payment/{pay.pk}/",
            {"bank_account_id": self.bank.pk}, format="json", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        jh = JournalHeader.objects.get(reference_type="LOGISTICS_PAYMENT", reference_id=pay.id)
        self.assertEqual(self._base(jh, self.supplier.linked_account), (D("5346.00"), D(0)))
        self.assertEqual(self._base(jh, self.bank), (D(0), D("5346.00")))

    def test_usd_deal_non_fifo_payment_converts_once(self):
        deal = self._deal("D-USD")
        pay = self._payment(deal, "1000", rate="3.5")
        resp = self.client.post(
            f"/api/logistics/deals/{deal.pk}/post_payment/{pay.pk}/",
            {"bank_account_id": self.bank.pk}, format="json", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        jh = JournalHeader.objects.get(reference_type="LOGISTICS_PAYMENT", reference_id=pay.id)
        self.assertEqual(self._base(jh, self.supplier.linked_account), (D("3500.00"), D(0)))

    def test_agent_payment_non_fifo_converts_once(self):
        agent = Partner.objects.create(
            tenant=self.tenant, name="وكيل", partner_type="Supplier",
            linked_account=self.supplier.linked_account)
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-CUR", shipping_agent=agent,
            total_shipping_cost_usd=D("1000"))
        pay = LogisticsPayment.objects.create(
            shipment=shipment, title="AP", amount=D("100"), status="Confirmed",
            usd_to_ils=D("3.5"), transfer_date="2026-06-20")
        resp = self.client.post(
            f"/api/logistics/shipments/{shipment.pk}/post_agent_payment/{pay.pk}/",
            {"bank_account_id": self.bank.pk}, format="json", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        jh = JournalHeader.objects.get(reference_type="LOGISTICS_PAYMENT", reference_id=pay.id)
        self.assertEqual(self._base(jh, self.bank), (D(0), D("350.00")))

    # ── أمر التصحيح ────────────────────────────────────────────────────────

    def _legacy_posted(self, deal, amount):
        """دفعة مرحّلة كما رحّلها الكود القديم: الرقم الدولاري كشيكل بسعر 1."""
        pay = self._payment(deal, amount)
        jh = post_journal(
            tenant_id=self.tenant.pk, transaction_date="2026-06-20",
            reference_type="LOGISTICS_PAYMENT", reference_id=pay.pk,
            description="قديم", currency=self.ils, exchange_rate=D(1), idempotent=False,
            lines_data=[
                {"account": self.supplier.linked_account_id, "debit": D(amount),
                 "credit": D(0), "partner": self.supplier.pk, "description": "قديم"},
                {"account": self.bank.pk, "debit": D(0), "credit": D(amount), "description": "قديم"},
            ])
        LogisticsPayment.objects.filter(pk=pay.pk).update(
            is_posted=True, journal=jh, bank_account=self.bank)
        pay.refresh_from_db()
        return pay

    def _supplier_net(self):
        agg = JournalLine.objects.filter(
            tenant=self.tenant, account=self.supplier.linked_account, journal__is_posted=True,
        ).aggregate(d=Sum("base_debit"), c=Sum("base_credit"))
        return (agg["d"] or D(0)) - (agg["c"] or D(0))

    def test_audit_reports_then_apply_fixes_group_a_only(self):
        invoiced = self._deal("D-0105")
        PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-0002", partner=self.supplier,
            currency=self.ils, invoice_date="2026-06-25", deal=invoiced,
            invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL, is_posted=True)
        p1 = self._legacy_posted(invoiced, "1650")
        p2 = self._legacy_posted(invoiced, "3850")
        archived = self._deal("D-0001")
        post_journal(
            tenant_id=self.tenant.pk, transaction_date="2026-06-20",
            reference_type="LOGISTICS_DEAL", reference_id=archived.pk, description="أرشيف",
            lines_data=[
                {"account": self.bank.pk, "debit": D(700), "credit": D(0), "description": "أرشيف"},
                {"account": self.supplier.linked_account_id, "debit": D(0), "credit": D(700),
                 "partner": self.supplier.pk, "description": "أرشيف"},
            ])
        p3 = self._legacy_posted(archived, "700")
        before = self._supplier_net()

        out = StringIO()
        call_command("audit_deal_payment_currency", "--tenant", str(self.tenant.pk), stdout=out)
        text = out.getvalue()
        self.assertIn("(أ)", text)
        self.assertIn("(ب)", text)
        self.assertIn("3696.00", text)   # 1650 × 3.24 − 1650
        self.assertIn("غير دولاري", text)  # صندوق الشيكل خاطئ أيضاً
        self.assertEqual(self._supplier_net(), before)  # قراءة فقط

        call_command("audit_deal_payment_currency", "--tenant", str(self.tenant.pk),
                     "--apply", stdout=StringIO())
        # 17,820 − 5,500 = 12,320 مدين إضافي للمورد؛ الأرشيف (ب) لم يُلمس.
        self.assertEqual(self._supplier_net() - before, D("12320.00"))
        for pay, ils in ((p1, "5346.00"), (p2, "12474.00")):
            old_journal = pay.journal
            pay.refresh_from_db()
            self.assertNotEqual(pay.journal_id, old_journal.pk)
            self.assertEqual(self._base(pay.journal, self.supplier.linked_account), (D(ils), D(0)))
            self.assertTrue(JournalHeader.objects.filter(
                reference_type="LOGISTICS_PAYMENT_UNPOST", reference_id=pay.pk).exists())
            self.assertTrue(AccountingAuditLog.objects.filter(
                model_name="LogisticsPayment", object_id=pay.pk).exists())
        old3 = p3.journal_id
        p3.refresh_from_db()
        self.assertEqual(p3.journal_id, old3)

        # تشغيل ثانٍ: لا فرق باقٍ في (أ) ⇒ لا قيود جديدة.
        count = JournalHeader.objects.count()
        call_command("audit_deal_payment_currency", "--tenant", str(self.tenant.pk),
                     "--apply", stdout=StringIO())
        self.assertEqual(JournalHeader.objects.count(), count)

    # ── --groups ────────────────────────────────────────────────────────────

    def _run(self, *args):
        call_command("audit_deal_payment_currency", "--tenant", str(self.tenant.pk),
                     *args, stdout=StringIO())

    def test_group_c_corrected_only_when_selected(self):
        uninvoiced = self._deal("D-0107")
        pay = self._legacy_posted(uninvoiced, "1000")
        self._run("--apply")  # الافتراضي a: (ج) لا تُمسّ
        old = pay.journal_id
        pay.refresh_from_db()
        self.assertEqual(pay.journal_id, old)

        self._run("--apply", "--groups", "c")
        pay.refresh_from_db()
        self.assertNotEqual(pay.journal_id, old)
        self.assertEqual(self._base(pay.journal, self.supplier.linked_account), (D("3240.00"), D(0)))
        self.assertEqual(self._base(pay.journal, self.bank), (D(0), D("3240.00")))

    def test_group_agent_fixes_double_conversion_on_agent_account(self):
        agent_ap = Account.objects.create(tenant=self.tenant, code="AP-YOYO", name="ذمم yoyo",
            account_type="Liability", is_active=True)
        agent = Partner.objects.create(
            tenant=self.tenant, name="yoyo", partner_type="Supplier", linked_account=agent_ap)
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="S-0012", shipping_agent=agent)
        pay = LogisticsPayment.objects.create(
            shipment=shipment, title="AP", amount=D("100"), status="Confirmed",
            usd_to_ils=D("3.5"), transfer_date="2026-06-20")
        # الكود القديم: أسطر بالشيكل (350) بعملة الدولار وسعره ⇒ أساس 1,225.
        jh = post_journal(
            tenant_id=self.tenant.pk, transaction_date="2026-06-20",
            reference_type="LOGISTICS_PAYMENT", reference_id=pay.pk, description="قديم",
            currency=self.usd, exchange_rate=D("3.5"), idempotent=False,
            lines_data=[
                {"account": agent_ap.pk, "debit": D(350), "credit": D(0), "partner": agent.pk,
                 "description": "قديم"},
                {"account": self.bank.pk, "debit": D(0), "credit": D(350), "description": "قديم"},
            ])
        LogisticsPayment.objects.filter(pk=pay.pk).update(is_posted=True, journal=jh, bank_account=self.bank)
        self.assertEqual(self._base(jh, agent_ap), (D("1225.00"), D(0)))

        self._run("--apply", "--groups", "agent")
        pay.refresh_from_db()
        self.assertNotEqual(pay.journal_id, jh.pk)
        self.assertEqual(self._base(pay.journal, agent_ap), (D("350.00"), D(0)))
        self.assertIn("شحنة: S-0012", pay.journal.description)
        net = JournalLine.objects.filter(
            tenant=self.tenant, account=agent_ap, journal__is_posted=True,
        ).aggregate(d=Sum("base_debit"), c=Sum("base_credit"))
        self.assertEqual(net["d"] - net["c"], D("350.00"))

    def test_group_b_is_refused_and_never_touched(self):
        from django.core.management.base import CommandError

        archived = self._deal("D-0001")
        post_journal(
            tenant_id=self.tenant.pk, transaction_date="2026-06-20",
            reference_type="LOGISTICS_DEAL", reference_id=archived.pk, description="أرشيف",
            lines_data=[
                {"account": self.bank.pk, "debit": D(700), "credit": D(0), "description": "أرشيف"},
                {"account": self.supplier.linked_account_id, "debit": D(0), "credit": D(700),
                 "partner": self.supplier.pk, "description": "أرشيف"},
            ])
        pay = self._legacy_posted(archived, "700")
        with self.assertRaisesMessage(CommandError, "b"):
            self._run("--apply", "--groups", "a,b")
        with self.assertRaisesMessage(CommandError, "x"):
            self._run("--apply", "--groups", "x")
        self._run("--apply", "--groups", "a,c,agent")
        old = pay.journal_id
        pay.refresh_from_db()
        self.assertEqual(pay.journal_id, old)
        self.assertFalse(JournalHeader.objects.filter(
            reference_type="LOGISTICS_PAYMENT_UNPOST", reference_id=pay.pk).exists())

    # ── سعر الدولار إلزامي عند الترحيل ─────────────────────────────────────
    # إنتاج: 101 من 137 دفعة سعرها 3.500000 بالزبط — القيمة الافتراضية للحقل، لا سعرٌ
    # أدخله أحد. الحقل صار بلا قيمة افتراضية، والترحيل يرفض الدفعة بلا سعر.

    def _create_via_api(self, deal, body):
        resp = self.client.post(f"/api/logistics/deals/{deal.pk}/payments/",
                                {"title": "P", "status": "Confirmed", **body},
                                format="json", **self.h)
        self.assertEqual(resp.status_code, 201, resp.content)
        return LogisticsPayment.objects.get(pk=resp.data["id"])

    def _post(self, deal, pay):
        return self.client.post(f"/api/logistics/deals/{deal.pk}/post_payment/{pay.pk}/",
                                {"bank_account_id": self.bank.pk}, format="json", **self.h)

    def test_payment_without_rate_is_refused_at_posting(self):
        deal = self._deal("D-NORATE")
        pay = self._create_via_api(deal, {"amount": "1000"})
        self.assertIsNone(pay.usd_to_ils)
        resp = self._post(deal, pay)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("سعر الدولار", str(resp.content.decode()))
        self.assertFalse(JournalHeader.objects.filter(
            reference_type="LOGISTICS_PAYMENT", reference_id=pay.pk).exists())

    def test_rate_entered_through_api_posts_at_that_rate(self):
        deal = self._deal("D-324")
        pay = self._create_via_api(deal, {"amount": "1000", "usd_to_ils": "3.24"})
        resp = self._post(deal, pay)
        self.assertEqual(resp.status_code, 200, resp.content)
        jh = JournalHeader.objects.get(reference_type="LOGISTICS_PAYMENT", reference_id=pay.pk)
        self.assertEqual(self._base(jh, self.supplier.linked_account), (D("3240.00"), D(0)))

    def test_agent_payment_without_rate_is_refused(self):
        agent = Partner.objects.create(
            tenant=self.tenant, name="وكيل بلا سعر", partner_type="Supplier",
            linked_account=self.supplier.linked_account)
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-NR", shipping_agent=agent,
            total_shipping_cost_usd=D("1000"))
        resp = self.client.patch(
            f"/api/logistics/shipments/{shipment.pk}/",
            {"payments": [{"payment_number": 1, "title": "دفعة", "amount": "100",
                           "status": "Confirmed"}]}, format="json", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        pay = shipment.agent_payments.get()
        self.assertIsNone(pay.usd_to_ils)
        resp = self.client.post(
            f"/api/logistics/shipments/{shipment.pk}/post_agent_payment/{pay.pk}/",
            {"bank_account_id": self.bank.pk}, format="json", **self.h)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("سعر الدولار", str(resp.content.decode()))

    def test_blockers_name_the_missing_rate(self):
        from logistics.payment_posting_diagnostics import collect_auto_posting_blockers
        deal = self._deal("D-BLK")
        pay = self._create_via_api(deal, {"amount": "500"})
        self.assertTrue(any("سعر الدولار" in b for b in collect_auto_posting_blockers(deal, pay)))

    def test_rates_report_lists_suspect_rates_and_writes_nothing(self):
        deal = self._deal("D-RATES")
        self._payment(deal, "100", rate="3.5")
        self._payment(deal, "200", rate="2.0")
        self._payment(deal, "300", rate="4.8")
        self._payment(deal, "400", rate="3.62")
        LogisticsPayment.objects.create(deal=deal, title="بلا سعر", amount=D("50"),
                                        status="Pending", transfer_date="2026-06-20")
        before = list(LogisticsPayment.objects.values_list("id", "usd_to_ils"))
        out = StringIO()
        call_command("audit_deal_payment_currency", "--tenant", str(self.tenant.pk),
                     "--rates", stdout=out)
        report = out.getvalue()
        for amount in ("100", "200", "300", "50"):
            self.assertIn(f"| {amount}.", report)
        self.assertNotIn("| 400.", report)
        self.assertIn("D-RATES", report)
        self.assertEqual(list(LogisticsPayment.objects.values_list("id", "usd_to_ils")), before)
