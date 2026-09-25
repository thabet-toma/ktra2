"""F-1 — أمر `fix_logistics_unpost_cycles`: تصحيح دورات إلغاء ترحيل قديمة.

النمط القديم لإلغاء ترحيل دفعة صفقة (قبل `3358bf7`) كان يُنشئ عكساً مرحّلاً
`LOGISTICS_PAYMENT_UNPOST` ويُلغي ترحيل الأصل ويسِمه «[ملغى ترحيل — عكس مرحّل #R]»
⇒ الدفاتر تحمل العكس وحده (أثرٌ معكوس الإشارة). نبني هذه الحالة هنا بنفس المساعد
(`reverse_journal(..., unpost_original=True)`) الذي نُقل إليه النمط القديم حرفياً.
"""
import datetime
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone

from accounting.api import reverse_journal
from accounting.cashbox import get_cash_box_parent_account
from accounting.models import Account, FiscalPeriod, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, post_journal
from logistics.models import LogisticsDeal, LogisticsPayment
from partners.models import Partner
from sales.models import VatStatement
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))
PAYMENT_TYPES = ["LOGISTICS_PAYMENT", "LOGISTICS_PAYMENT_UNPOST"]


class FixLogisticsUnpostCyclesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="f1_cycles", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.today = timezone.localdate()
        # السنة الماضية كاملةً — الدورة القديمة فيها، و«اليوم» في فترة مفتوحة دائماً.
        cls.old_date = datetime.date(cls.today.year - 1, 6, 20)
        cls.rev_date = datetime.date(cls.today.year - 1, 6, 25)
        cls.t1 = cls._tenant("شركة دورات قديمة 1", "F1A")
        cls.t2 = cls._tenant("شركة دورات قديمة 2", "F1B")

    @classmethod
    def _tenant(cls, name, code):
        tenant = create_company(name, cls.user)
        create_fiscal_year(tenant, cls.today.year - 1)
        create_fiscal_year(tenant, cls.today.year)
        parent = get_cash_box_parent_account(tenant)
        ap = Account.objects.create(
            tenant=tenant, code=f"AP-{code}", name=f"ذمم {name}",
            parent=parent, account_type="Liability", is_active=True)
        box = Account.objects.create(
            tenant=tenant, code=f"BOX-{code}", name=f"صندوق {name}",
            parent=parent, account_type="Asset", is_active=True)
        partner = Partner.objects.create(
            tenant=tenant, name=f"مورد {name}", partner_type="Supplier",
            linked_account=ap)
        deal = LogisticsDeal.objects.create(
            tenant=tenant, ref_number=f"D-{code}", partner=partner,
            order_date=cls.old_date, total_amount=D("10000"))
        tenant._f1 = {"ap": ap, "box": box, "partner": partner, "deal": deal}
        return tenant

    # ── بناء الحالة القديمة ─────────────────────────────────────────
    def _payment(self, tenant, **kw):
        kw.setdefault("title", "P1")
        return LogisticsPayment.objects.create(
            deal=tenant._f1["deal"], amount=D("1000"), status="Pending",
            transfer_date=self.old_date, **kw)

    def _original(self, tenant, pay, *, amount="1000", currency=None, rate="1"):
        f = tenant._f1
        return post_journal(
            tenant_id=tenant.pk, transaction_date=self.old_date,
            reference_type="LOGISTICS_PAYMENT", reference_id=pay.id,
            description=f"دفعة {pay.title}",
            lines_data=[
                {"account": f["ap"].id, "debit": D(amount), "credit": D("0"),
                 "partner": f["partner"].id, "description": "دفعة"},
                {"account": f["box"].id, "debit": D("0"), "credit": D(amount),
                 "description": "دفعة"},
            ],
            currency=currency, exchange_rate=D(rate), idempotent=False)

    def _old_cycle(self, tenant, pay, **kw):
        """دورة ترحيل ← إلغاء بالنمط القديم: أصلٌ غير مرحّل موسوم + عكسٌ مرحّل."""
        orig = self._original(tenant, pay, **kw)
        rev = reverse_journal(
            orig, reference_type="LOGISTICS_PAYMENT_UNPOST", reference_id=pay.id,
            transaction_date=self.rev_date, description=f"عكس القيد #{orig.id}",
            unpost_original=True)
        orig.refresh_from_db()
        self.assertFalse(orig.is_posted)
        self.assertIn(f"عكس مرحّل #{rev.id}", orig.description)
        return orig, rev

    def _run(self, *args):
        out = StringIO()
        call_command("fix_logistics_unpost_cycles", *args, stdout=out)
        return out.getvalue()

    def _net(self, pay, account):
        agg = JournalLine.objects.filter(
            journal__reference_id=pay.id, journal__reference_type__in=PAYMENT_TYPES,
            journal__is_posted=True, account=account,
        ).aggregate(d=Sum("debit"), c=Sum("credit"),
                    bd=Sum("base_debit"), bc=Sum("base_credit"))
        return ((agg["d"] or 0) - (agg["c"] or 0), (agg["bd"] or 0) - (agg["bc"] or 0))

    def _assert_net_zero(self, tenant, pay):
        for account in (tenant._f1["ap"], tenant._f1["box"]):
            self.assertEqual(self._net(pay, account), (0, 0), account.code)

    def _close_old_period(self, tenant):
        FiscalPeriod.objects.filter(
            tenant=tenant, start_date__lte=self.old_date, end_date__gte=self.old_date,
        ).update(status="Closed", is_closed=True)

    # ── (a) فترة مفتوحة ────────────────────────────────────────────
    def test_open_period_reposts_original_and_rerun_is_noop(self):
        pay = self._payment(self.t1)
        orig, rev = self._old_cycle(self.t1, pay)
        self.assertEqual(self._net(pay, self.t1._f1["ap"]), (D("-1000"), D("-1000")))

        report = self._run()
        self.assertIn(f"orig=#{orig.id}", report)
        self.assertIn(f"rev=#{rev.id}", report)
        self.assertIn("action=repost", report)
        orig.refresh_from_db()
        self.assertFalse(orig.is_posted, "الوضع الافتراضي تقريرٌ فقط")

        before = JournalHeader.objects.count()
        self._run("--apply")
        orig.refresh_from_db()
        self.assertTrue(orig.is_posted)
        self.assertEqual(orig.transaction_date, self.old_date)
        self.assertEqual(JournalHeader.objects.count(), before, "إعادة ترحيل لا قيد جديد")
        self._assert_net_zero(self.t1, pay)

        rerun = self._run("--apply")
        self.assertNotIn(f"orig=#{orig.id}", rerun)
        self.assertEqual(JournalHeader.objects.count(), before)
        self._assert_net_zero(self.t1, pay)

    # ── (b) فترة مقفلة ─────────────────────────────────────────────
    def test_closed_period_posts_one_adjusting_journal_dated_today(self):
        pay = self._payment(self.t1)
        orig, rev = self._old_cycle(self.t1, pay)
        self._close_old_period(self.t1)

        self.assertIn("action=adjust", self._run())
        self._run("--apply")

        orig.refresh_from_db()
        self.assertFalse(orig.is_posted, "الأصل في فترة مقفلة لا يُمسّ ترحيلُه")
        adjusting = JournalHeader.objects.filter(
            tenant=self.t1, reference_type="LOGISTICS_PAYMENT", reference_id=pay.id,
            is_posted=True)
        self.assertEqual(adjusting.count(), 1)
        adj = adjusting.get()
        self.assertEqual(adj.transaction_date, self.today)
        self.assertIn(f"#{orig.id}", adj.description)
        self.assertEqual(
            sorted((l.account_id, l.debit, l.credit, l.partner_id) for l in adj.lines.all()),
            sorted((l.account_id, l.debit, l.credit, l.partner_id) for l in orig.lines.all()),
        )
        self._assert_net_zero(self.t1, pay)

        count = JournalHeader.objects.count()
        rerun = self._run("--apply")
        self.assertNotIn(f"orig=#{orig.id}", rerun)
        self.assertEqual(JournalHeader.objects.count(), count)

    def test_reversal_tagging_cash_line_with_supplier_is_negated_line_by_line(self):
        """شكلُ الإنتاج (دفعات D-0042 وD-0101 المحذوفة): العكسُ القديم وسم سطرَ
        النقدية بالمورّد والأصلُ لم يَسِمه — يتعاكسان حساباً ومبلغاً لا طرفاً. كان
        يُتخطّى «مراجعة يدوية» والعكسُ المرحّل يُضخّم رصيدَ المورّد والصندوق. التسوية
        تنفي أسطرَ العكس نفسها فيعود كلُّ (حساب، طرف) صفراً — وإعادةُ ترحيل الأصل
        كانت ستترك وسمَ النقدية في رصيد المورّد."""
        pay = self._payment(self.t1)
        orig, rev = self._old_cycle(self.t1, pay)
        partner = self.t1._f1["partner"]
        JournalLine.objects.filter(journal=rev, account=self.t1._f1["box"]).update(partner=partner)

        report = self._run()
        self.assertIn("action=adjust", report)
        self.assertIn("وسم الطرف", report)
        self._run("--apply")

        self._assert_net_zero(self.t1, pay)
        tagged = JournalLine.objects.filter(
            journal__reference_id=pay.id, journal__reference_type__in=PAYMENT_TYPES,
            journal__is_posted=True, partner=partner,
        ).aggregate(d=Sum("debit"), c=Sum("credit"))
        self.assertEqual((tagged["d"] or 0) - (tagged["c"] or 0), 0)
        orig.refresh_from_db()
        self.assertFalse(orig.is_posted)

        count = JournalHeader.objects.count()
        self._run("--apply")
        self.assertEqual(JournalHeader.objects.count(), count)

    def test_final_vat_statement_counts_as_locked(self):
        pay = self._payment(self.t1)
        orig, _ = self._old_cycle(self.t1, pay)
        VatStatement.objects.create(
            tenant=self.t1, statement_number="VAT-F1",
            period_from=datetime.date(self.old_date.year, 6, 1),
            period_to=datetime.date(self.old_date.year, 6, 30),
            status=VatStatement.STATUS_FINAL)
        self.assertIn("action=adjust", self._run())

    def test_base_currency_mismatch_adjusts_at_reversal_rate(self):
        """العكس القديم لم ينسخ العملة (سعر 1) والأصل بسعر 3.5: إعادة ترحيل الأصل
        تصفّر الاسمي وتترك فرقاً بالعملة الأساسية — فالتسوية بسعر العكس بدلاً منها."""
        pay = self._payment(self.t1)
        orig, rev = self._old_cycle(self.t1, pay, currency=self.usd, rate="3.5")
        self.assertIn("action=adjust", self._run())
        self._run("--apply")
        orig.refresh_from_db()
        self.assertFalse(orig.is_posted)
        self._assert_net_zero(self.t1, pay)

    # ── (c) أصلان لعكسٍ واحد ────────────────────────────────────────
    def test_duplicate_originals_for_one_reversal_repairs_only_one(self):
        pay = self._payment(self.t1)
        orig, rev = self._old_cycle(self.t1, pay)
        dup = self._original(self.t1, pay)
        JournalHeader.objects.filter(pk=dup.pk).update(
            is_posted=False,
            description=f"دفعة مكررة [ملغى ترحيل — عكس مرحّل #{rev.id}]")

        report = self._run()
        self.assertIn(f"orig=#{orig.id}", report)
        self.assertIn(f"orig=#{dup.id}", report)
        dup_line = next(l for l in report.splitlines() if f"orig=#{dup.id}" in l)
        self.assertIn("action=skip", dup_line)
        self.assertIn(f"#{orig.id}", dup_line)

        self._run("--apply")
        orig.refresh_from_db(); dup.refresh_from_db()
        self.assertTrue(orig.is_posted)
        self.assertFalse(dup.is_posted)
        self._assert_net_zero(self.t1, pay)

        count = JournalHeader.objects.count()
        rerun = self._run("--apply")
        self.assertNotIn("action=repost", rerun)
        self.assertNotIn("action=adjust", rerun)
        self.assertEqual(JournalHeader.objects.count(), count)
        self._assert_net_zero(self.t1, pay)

    # ── (d) فلتر الشركة ────────────────────────────────────────────
    def test_tenant_filter_limits_report_and_apply(self):
        p1 = self._payment(self.t1)
        o1, _ = self._old_cycle(self.t1, p1)
        p2 = self._payment(self.t2)
        o2, _ = self._old_cycle(self.t2, p2)

        report = self._run("--tenant", str(self.t1.pk))
        self.assertIn(f"orig=#{o1.id}", report)
        self.assertNotIn(f"orig=#{o2.id}", report)

        self._run("--tenant", str(self.t1.pk), "--apply")
        o1.refresh_from_db(); o2.refresh_from_db()
        self.assertTrue(o1.is_posted)
        self.assertFalse(o2.is_posted)

    # ── الشكل الثاني: دفعة مرحّلة وقيدها غير مرحّل ───────────────────
    def test_posted_payment_with_unposted_journal_is_report_only(self):
        pay = self._payment(self.t1)
        orig, rev = self._old_cycle(self.t1, pay)
        # إعادة الترحيل القديمة أعادت استخدام قيد الدورة السابقة (البحث الـidempotent)
        LogisticsPayment.objects.filter(pk=pay.pk).update(is_posted=True, journal=orig)

        report = self._run()
        shape2 = [l for l in report.splitlines() if "shape=posted_payment_unposted_journal" in l]
        self.assertEqual(len(shape2), 1, report)
        self.assertIn(f"payment=#{pay.id}", shape2[0])
        self.assertIn("action=report", shape2[0])
        cycle = next(l for l in report.splitlines() if f"orig=#{orig.id}" in l
                     and "shape=reversed_cycle" in l)
        self.assertIn("action=skip", cycle)

        count = JournalHeader.objects.count()
        self._run("--apply")
        orig.refresh_from_db()
        self.assertFalse(orig.is_posted)
        self.assertEqual(JournalHeader.objects.count(), count)
