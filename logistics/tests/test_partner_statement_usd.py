"""كشف حساب الطرف بالدولار: `JournalLine.amount_currency` مصدره، والشيكل كما كان.

الوكيل يُدائَن بالشيكل عند إثبات الشحن (سعر 3.6) ويُدفع له بالدولار (سعر 3.24): الذمة
الحقيقية بالدولار صفر، والشيكل يُظهر 360 ₪ — فرق صرفٍ لا دَين. وأمر التعبئة يعطي
رصيد yoyo على الإنتاج (3,384.59$) من القيود القديمة بلا تخمين.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from rest_framework.test import APITestCase

from accounting.models import Account, CashBoxLedgerAccount, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, partner_account_statement, post_journal
from logistics.accruals import post_freight_accrual
from logistics.models import LogisticsDeal, LogisticsPayment, LogisticsShipment
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class _UsdBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="usdstmt", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة كشف الدولار", cls.user)
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

    def _statement(self, currency=None):
        return partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=self.agent.id, is_supplier=True,
            ordering="oldest", limit=200, currency=currency)


class UsdStatementTest(_UsdBase):
    def test_payment_at_324_and_accrual_at_36_are_zero_in_dollars(self):
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-0020", shipping_agent=self.agent,
            total_shipping_cost_usd=D("1000"), departure_date="2026-06-01")
        post_freight_accrual(LogisticsShipment.objects.get(pk=shipment.pk), D("3.6"))
        paid = self.client.post(
            f"/api/logistics/shipments/{shipment.pk}/pay_agent_from_cashbox/",
            {"amount": "1000", "usd_to_ils": "3.24", "cash_box_external_id": self.box.external_id,
             "payment_date": "2026-07-05"}, format="json", **self.h)
        self.assertEqual(paid.status_code, 201, paid.content)

        ils = self._statement()
        self.assertEqual(D(ils["closing_balance"]), D("360.00"))
        self.assertEqual(ils["currencies"], ["USD"])

        usd = self._statement("USD")
        self.assertEqual(usd["currency"], "USD")
        self.assertEqual(D(usd["closing_balance"]), D("0"))
        self.assertEqual(usd["missing_count"], 0)
        self.assertEqual(
            [(r["reference_type"], r["debit"], r["credit"]) for r in usd["results"]],
            [("SHIPMENT_FREIGHT_ACCRUAL", "0.00", "1000.00"), ("LOGISTICS_PAYMENT", "1000.00", "0.00")])
        self.assertEqual([D(r["running_balance"]) for r in usd["results"]], [D("1000"), D("0")])
        # الفرق الختامي: 360 ₪ في الدفاتر مقابل 0$ — فرق صرفٍ لا دَين.
        fx = usd["fx"]
        self.assertEqual((D(fx["book_balance"]), D(fx["currency_balance"])), (D("360"), D("0")))
        self.assertEqual(D(fx["difference"]), D("360.00"))
        self.assertEqual((fx["rate_source"], D(fx["rate"])), ("last_entry", D("3.24")))

    def test_a_line_without_dollars_is_shown_and_warned_not_counted(self):
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-0021", shipping_agent=self.agent,
            total_shipping_cost_usd=D("500"), departure_date="2026-06-01")
        post_freight_accrual(LogisticsShipment.objects.get(pk=shipment.pk), D("3.5"))
        self.agent.refresh_from_db()
        cash = Account.objects.create(
            tenant=self.tenant, code="BOX-ILS", name="صندوق", account_type="Asset", is_active=True)
        post_journal(
            tenant_id=self.tenant.TenantID, transaction_date="2026-07-01",
            reference_type="SUPPLIER_PAYMENT", reference_id=900, description="سند بالشيكل",
            lines_data=[
                {"account": self.agent.linked_account_id, "debit": D("700"), "credit": D("0"),
                 "partner": self.agent.id},
                {"account": cash.id, "debit": D("0"), "credit": D("700")},
            ])

        usd = self._statement("USD")
        self.assertEqual(D(usd["closing_balance"]), D("500.00"))
        self.assertEqual(usd["missing_count"], 1)
        self.assertEqual(D(usd["missing_base_balance"]), D("-700.00"))
        voucher = next(r for r in usd["results"] if r["reference_type"] == "SUPPLIER_PAYMENT")
        self.assertTrue(voucher["currency_missing"])
        self.assertEqual((voucher["debit"], voucher["credit"], voucher["base_debit"]), ("", "", "700.00"))
        self.assertEqual(D(voucher["running_balance"]), D("500.00"))

    def test_fifo_box_payment_is_in_shekels_but_carries_its_dollars(self):
        from accounting.fx_fifo import fund_box_from_capital

        fund_box_from_capital(self.box, 2000, D("3.2"), date="2026-06-01")
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-0022", shipping_agent=self.agent,
            total_shipping_cost_usd=D("1000"))
        paid = self.client.post(
            f"/api/logistics/shipments/{shipment.pk}/pay_agent_from_cashbox/",
            {"amount": "1000", "usd_to_ils": "3.24", "cash_box_external_id": self.box.external_id,
             "payment_date": "2026-07-05"}, format="json", **self.h)
        self.assertEqual(paid.status_code, 201, paid.content)
        journal = JournalHeader.objects.get(pk=paid.data["journal_id"])
        self.assertEqual(journal.exchange_rate, D("1"))
        agent_line = journal.lines.get(partner=self.agent)
        self.assertEqual((agent_line.base_debit, agent_line.amount_currency, agent_line.currency_code),
                         (D("3240.00"), D("1000.00"), "USD"))
        # الصندوق وفرق الصرف بالشيكل وحده.
        self.assertFalse(journal.lines.filter(partner__isnull=True, amount_currency__isnull=False).exists())

    def test_statement_endpoint_takes_the_currency(self):
        res = self.client.get(f"/api/partners/{self.agent.id}/statement/?currency=USD", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["currency"], "USD")
        bad = self.client.get(f"/api/partners/{self.agent.id}/statement/?currency=US1", **self.h)
        self.assertEqual(bad.status_code, 400)
        # عملة الأساس = الكشف بالشيكل نفسه.
        base = self.client.get(f"/api/partners/{self.agent.id}/statement/?currency=ILS", **self.h)
        self.assertIsNone(base.data["currency"])


class PostJournalAmountCurrencyTest(_UsdBase):
    def _lines(self, **partner_line):
        self.agent.refresh_from_db()
        from accounting.api import ensure_partner_account
        ensure_partner_account(self.agent)
        self.agent.refresh_from_db()
        return [
            {"account": self.agent.linked_account_id, "debit": D("0"), "credit": D("360"),
             "partner": self.agent.id, **partner_line},
            {"account": self.usd_box_account.id, "debit": D("360"), "credit": D("0")},
        ]

    def test_explicit_amount_is_stored_and_its_sign_is_guarded(self):
        jh = post_journal(
            tenant_id=self.tenant.TenantID, transaction_date="2026-07-01",
            reference_type="TEST_USD", reference_id=1, description="t",
            lines_data=self._lines(amount_currency=D("-100"), currency_code="usd"))
        line = jh.lines.get(partner=self.agent)
        self.assertEqual((line.amount_currency, line.currency_code), (D("-100.00"), "USD"))
        self.assertIsNone(jh.lines.get(partner__isnull=True).amount_currency)
        with self.assertRaises(ValidationError):
            post_journal(tenant_id=self.tenant.TenantID, transaction_date="2026-07-01",
                         reference_type="TEST_USD", reference_id=2, description="t",
                         lines_data=self._lines(amount_currency=D("100"), currency_code="USD"))
        with self.assertRaises(ValidationError):
            post_journal(tenant_id=self.tenant.TenantID, transaction_date="2026-07-01",
                         reference_type="TEST_USD", reference_id=3, description="t",
                         lines_data=self._lines(amount_currency=D("-100")))

    def test_foreign_journal_fills_itself_and_its_manual_reversal_keeps_currency_and_rate(self):
        jh = post_journal(
            tenant_id=self.tenant.TenantID, transaction_date="2026-07-01",
            reference_type="TEST_USD", reference_id=4, description="t",
            lines_data=self._lines(), currency=self.usd, exchange_rate=D("3.24"))
        line = jh.lines.get(partner=self.agent)
        self.assertEqual((line.amount_currency, line.currency_code, line.base_credit),
                         (D("-360.00"), "USD", D("1166.40")))

        res = self.client.post(f"/api/accounting/journals/{jh.pk}/reverse/", {}, format="json", **self.h)
        self.assertIn(res.status_code, (200, 201), res.content)
        rev = JournalHeader.objects.get(reference_type="JOURNAL_REVERSAL", reference_id=jh.pk)
        rev_line = rev.lines.get(partner=self.agent)
        # كان يُعكس بسعر 1: 360 ₪ بدل 1,166.40 ₪.
        self.assertEqual((rev_line.base_debit, rev_line.amount_currency), (D("1166.40"), D("360.00")))


class BackfillYoyoTest(_UsdBase):
    """بيانات تشبه الإنتاج: قيود قديمة بلا مبلغ أجنبي، ورصيد yoyo 3,384.59$."""

    def _journal(self, *, ref_type, ref_id, date, amount, agent_side, rate=D("1"), currency=None):
        jh = JournalHeader.objects.create(
            tenant=self.tenant, transaction_date=date, is_posted=True, reference_type=ref_type,
            reference_id=ref_id, currency=currency, exchange_rate=rate,
            description=f"{ref_type} #{ref_id}")
        other = self.expense if agent_side == "credit" else self.usd_box_account
        amount = D(amount)
        JournalLine.objects.create(
            tenant=self.tenant, journal=jh, account=self.ap, partner=self.agent,
            debit=amount if agent_side == "debit" else 0, credit=amount if agent_side == "credit" else 0)
        JournalLine.objects.create(
            tenant=self.tenant, journal=jh, account=other,
            debit=amount if agent_side == "credit" else 0, credit=amount if agent_side == "debit" else 0)
        return jh

    def setUp(self):
        super().setUp()
        from accounting.api import ensure_partner_account
        ensure_partner_account(self.agent)
        self.agent.refresh_from_db()
        self.ap = self.agent.linked_account
        self.expense = Account.objects.get(tenant=self.tenant, code="5301")
        # الاستحقاقات: قيدٌ بالشيكل بسعر 1، وسعرها على الشحنة.
        shipments = {}
        for number, usd, rate in (
            ("S-0012", "4000", "3.48"), ("SH-0013", "1722.25", "3.5"), ("SH-0014", "1841.40", "3.6"),
            ("SH-0015", "543.99", "3.55"), ("SH-0016", "1276.95", "3.63"),
        ):
            sh = LogisticsShipment.objects.create(
                tenant=self.tenant, shipment_number=number, shipping_agent=self.agent,
                total_shipping_cost_usd=D(usd), freight_exchange_rate=D(rate), freight_is_posted=True)
            shipments[number] = sh
            self._journal(ref_type="SHIPMENT_FREIGHT_ACCRUAL", ref_id=sh.pk, date="2026-05-01",
                          amount=(D(usd) * D(rate)).quantize(D("0.01")), agent_side="credit")

        def payment(number, shipment, usd, rate):
            return LogisticsPayment.objects.create(
                tenant=self.tenant, shipment=shipments[shipment], payment_number=number,
                title=f"دفعة {number}", amount=D(usd), usd_to_ils=D(rate), status="Confirmed",
                is_posted=True)

        # #175 على S-0012: الخاطئ (دولار كشيكل مضاعف) وعكسه والمصحَّح بقيدٍ بالدولار.
        p175 = payment(175, "S-0012", "4000", "3.24")
        self._journal(ref_type="LOGISTICS_PAYMENT", ref_id=p175.pk, date="2026-05-10",
                      amount="13928.63", agent_side="debit")
        self._journal(ref_type="LOGISTICS_PAYMENT_UNPOST", ref_id=p175.pk, date="2026-05-10",
                      amount="13928.63", agent_side="credit")
        self._journal(ref_type="LOGISTICS_PAYMENT", ref_id=p175.pk, date="2026-05-10",
                      amount="4000", agent_side="debit", rate=D("3.24"), currency=self.usd)
        # SH-0013 بقيدٍ بالدولار، وSH-0016 من صندوق FIFO بالشيكل.
        p13 = payment(1, "SH-0013", "1000", "3.3")
        self._journal(ref_type="LOGISTICS_PAYMENT", ref_id=p13.pk, date="2026-06-01",
                      amount="1000", agent_side="debit", rate=D("3.3"), currency=self.usd)
        p16 = payment(2, "SH-0016", "1000", "3.4")
        self._journal(ref_type="LOGISTICS_PAYMENT", ref_id=p16.pk, date="2026-06-02",
                      amount="3400", agent_side="debit")
        # سند بالشيكل بلا مصدر دولاري: يُذكر ولا يُخمَّن.
        self._journal(ref_type="SUPPLIER_PAYMENT", ref_id=77, date="2026-06-03",
                      amount="0.01", agent_side="debit")
        # قديمٌ حقاً: ما ملأه `save` تلقائياً لقيود الدولار يُمسح.
        JournalLine.objects.filter(tenant=self.tenant).update(amount_currency=None, currency_code=None)

    def test_read_only_then_apply_gives_yoyo_3384_59_and_leaves_shekels_alone(self):
        before = self._statement()
        out = StringIO()
        call_command("backfill_foreign_party_currency", tenant=self.tenant.TenantID, stdout=out)
        self.assertFalse(JournalLine.objects.filter(amount_currency__isnull=False).exists())
        report = out.getvalue()
        self.assertIn("قراءة فقط", report)
        self.assertIn("SUPPLIER_PAYMENT: 1", report)
        self.assertIn(f"طرف #{self.agent.id}: -3384.59", report)

        call_command("backfill_foreign_party_currency", tenant=self.tenant.TenantID, apply=True,
                     stdout=StringIO())
        usd = self._statement("USD")
        self.assertEqual(D(usd["closing_balance"]), D("3384.59"))
        self.assertEqual(usd["missing_count"], 1)
        # الخاطئ وعكسه يتعادلان بالدولار أيضاً — لا أثر للزوج.
        wrong_pair = [
            r for r in usd["results"] if r["reference_type"].startswith("LOGISTICS_PAYMENT")
            and r["reference_id"] == LogisticsPayment.objects.get(payment_number=175).pk]
        self.assertEqual(len(wrong_pair), 3)
        self.assertEqual(sum(D(r["debit"]) - D(r["credit"]) for r in wrong_pair), D("4000"))

        # انحدار: كشف الشيكل لم يتغيّر ولا سطر.
        after = self._statement()
        keys = ("id", "debit", "credit", "balance_before", "running_balance", "reversal_pair_id")
        self.assertEqual([{k: r[k] for k in keys} for r in after["results"]],
                         [{k: r[k] for k in keys} for r in before["results"]])
        self.assertEqual(after["closing_balance"], before["closing_balance"])

        # مرّة ثانية لا تكتب شيئاً — لا يمسّ سطراً معبّأً.
        again = StringIO()
        call_command("backfill_foreign_party_currency", tenant=self.tenant.TenantID, apply=True,
                     stdout=again)
        self.assertIn("كُتب 0 سطراً", again.getvalue())


class BackfillDeletedPaymentsTest(_UsdBase):
    """الدفعة المحذوفة قيداها باقيان: المحذوفة ليّناً دولارها في صفّها، والمحذوفة نهائياً
    على صفقة أرشيف اسميُّها دولار (كقيد LOGISTICS_DEAL) — وغيرها بلا مصدر."""

    def _pair(self, partner, ref_id, amount, description):
        for ref_type, side in (("LOGISTICS_PAYMENT", "debit"), ("LOGISTICS_PAYMENT_UNPOST", "credit")):
            jh = JournalHeader.objects.create(
                tenant=self.tenant, transaction_date="2026-05-10", is_posted=True,
                reference_type=ref_type, reference_id=ref_id, description=description)
            JournalLine.objects.create(
                tenant=self.tenant, journal=jh, account=partner.linked_account, partner=partner,
                debit=D(amount) if side == "debit" else 0, credit=D(amount) if side == "credit" else 0)
            JournalLine.objects.create(
                tenant=self.tenant, journal=jh, account=self.usd_box_account,
                debit=D(amount) if side == "credit" else 0, credit=D(amount) if side == "debit" else 0)

    def _usd(self, ref_id):
        """[قيد الترحيل، قيد العكس]."""
        return list(JournalLine.objects.filter(
            tenant=self.tenant, partner__isnull=False, journal__reference_id=ref_id,
            journal__reference_type__startswith="LOGISTICS_PAYMENT",
        ).order_by("journal__reference_type").values_list("amount_currency", flat=True))

    def test_deleted_payments_are_filled_and_an_unknown_one_stays_empty(self):
        from accounting.api import ensure_partner_account

        supplier = Partner.objects.create(tenant=self.tenant, name="مورد أرشيف", partner_type="Supplier")
        for partner in (supplier, self.agent):
            ensure_partner_account(partner)
            partner.refresh_from_db()
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-0042", partner=supplier, order_date="2026-04-01",
            total_amount=D("5000"))
        # صفقة أرشيف: قيد LOGISTICS_DEAL مرحّل ولا فاتورة دولية.
        JournalHeader.objects.create(
            tenant=self.tenant, transaction_date="2026-04-01", is_posted=True,
            reference_type="LOGISTICS_DEAL", reference_id=deal.pk, description="صفقة D-0042")

        soft = LogisticsPayment.objects.create(
            deal=deal, amount=D("1000"), usd_to_ils=D("3.5"), status="Confirmed", is_posted=True)
        self._pair(supplier, soft.pk, "3500", "دفعة | صفقة: D-0042")
        soft.delete()
        self.assertTrue(LogisticsPayment.all_objects.get(pk=soft.pk).is_deleted)

        hard_id = soft.pk + 1000
        self._pair(supplier, hard_id, "1497.75", "دفعة قديمة | صفقة: D-0042 | المورد: مورد أرشيف")
        # محذوفة نهائياً لطرفٍ بلا صفقة أرشيف: لا مصدر ⇒ تبقى فارغة.
        unknown_id = soft.pk + 2000
        self._pair(self.agent, unknown_id, "800", "دفعة")
        JournalLine.objects.filter(tenant=self.tenant).update(amount_currency=None, currency_code=None)

        out = StringIO()
        call_command("backfill_foreign_party_currency", tenant=self.tenant.TenantID, apply=True,
                     stdout=out)
        self.assertEqual(self._usd(soft.pk), [D("1000.00"), D("-1000.00")])
        self.assertEqual(self._usd(hard_id), [D("1497.75"), D("-1497.75")])
        self.assertEqual(self._usd(unknown_id), [None, None])
        self.assertIn("كُتب 4 سطراً", out.getvalue())
