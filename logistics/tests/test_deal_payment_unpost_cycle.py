"""قرار 2026-08-11 — توحيد نمط عكس دفعات الصفقات (معالجة ديون المرحلة 2).

إلغاء ترحيل دفعة صفقة يُبقي القيد الأصلي مرحّلاً وينشئ عكساً مرحّلاً بعملة
الأصل وسعره ⇒ صافي الأثر صفر اسمياً وبالعملة الأساسية، وتقارير الفترة
الأصلية لا تتغيّر بأثر رجعي (نفس نمط دفعات التخليص). إعادة الترحيل تنشئ
قيداً جديداً (post_journal بـidempotent=False على هذا المرجع) فلا يُعاد
استخدام قيد دورة سابقة — كان البحث الـidempotent يعيد القيد القديم فتُوسم
الدفعة مرحّلة بلا أثر جديد في الدفاتر.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.cashbox import get_cash_box_parent_account
from accounting.models import Account, CashBoxLedgerAccount, JournalHeader, JournalLine
from accounting.services import create_fiscal_year
from logistics.models import LogisticsDeal, LogisticsPayment
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class DealPaymentUnpostCycleTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="unpost_cycle", password="x", is_staff=True)
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة دورة العكس", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        parent = get_cash_box_parent_account(cls.tenant)
        ap = Account.objects.create(
            tenant=cls.tenant, code="AP-U1", name="ذمم مورد الدورة",
            parent=parent, account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد الدورة", partner_type="Supplier",
            linked_account=ap)
        usd_acc = Account.objects.create(
            tenant=cls.tenant, code="USDBOX-U", name="صندوق دولار الدورة",
            parent=parent, account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="usd-u1", name="صندوق دولار الدورة",
            currency_code="USD", account=usd_acc)
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number="D-9100", partner=cls.partner,
            order_date="2026-06-20", total_amount=D("10000"), currency=cls.usd,
            currency_rate=D("3.5"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _payment(self):
        return LogisticsPayment.objects.create(
            deal=self.deal, title="P1", amount=D("1000"), status="Confirmed",
            usd_to_ils=D("3.5"), transfer_date="2026-06-20")

    def _post(self, payment):
        return self.client.post(
            f"/api/logistics/deals/{self.deal.pk}/post_payment/{payment.pk}/",
            {"cash_box_external_id": "usd-u1"}, format="json", **self._auth())

    def _unpost(self, payment):
        return self.client.post(
            f"/api/logistics/deals/{self.deal.pk}/unpost_payment/{payment.pk}/",
            {"reversal_date": "2026-06-25"}, format="json", **self._auth())

    def test_unpost_keeps_original_posted_with_zero_net_effect(self):
        pay = self._payment()
        self.assertEqual(self._post(pay).status_code, 200)
        orig = JournalHeader.objects.get(
            reference_type="LOGISTICS_PAYMENT", reference_id=pay.id)

        resp = self._unpost(pay)
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertTrue(body["voided_journal_posted"])
        self.assertTrue(body["reversal_journal_posted"])

        # الأصل يبقى مرحّلاً — تقارير فترته لا تتغيّر بأثر رجعي
        orig.refresh_from_db()
        self.assertTrue(orig.is_posted)
        rev = JournalHeader.objects.get(pk=body["reversal_journal_id"])
        self.assertTrue(rev.is_posted)
        self.assertEqual(rev.reference_type, "LOGISTICS_PAYMENT_UNPOST")

        # العكس بعملة الأصل وسعره ⇒ صافي صفر اسمياً وبالعملة الأساسية
        self.assertEqual(rev.currency_id, orig.currency_id)
        self.assertEqual(D(rev.exchange_rate), D(orig.exchange_rate))
        agg = JournalLine.objects.filter(
            journal_id__in=[orig.id, rev.id],
            account=self.partner.linked_account,
        ).aggregate(d=Sum("debit"), c=Sum("credit"),
                    bd=Sum("base_debit"), bc=Sum("base_credit"))
        self.assertEqual(agg["d"], agg["c"])
        self.assertEqual(agg["bd"], agg["bc"])

        pay.refresh_from_db()
        self.assertFalse(pay.is_posted)
        self.assertIsNone(pay.journal_id)
        self.assertEqual(pay.status, "Pending")

    def test_repost_creates_fresh_journal_not_stale_reuse(self):
        pay = self._payment()
        self.assertEqual(self._post(pay).status_code, 200)
        first = JournalHeader.objects.get(
            reference_type="LOGISTICS_PAYMENT", reference_id=pay.id)
        self.assertEqual(self._unpost(pay).status_code, 200)

        pay.refresh_from_db()
        pay.status = "Confirmed"  # إلغاء الترحيل أعادها Pending
        pay.save(update_fields=["status"])
        resp = self._post(pay)
        self.assertEqual(resp.status_code, 200, resp.content)

        journals = JournalHeader.objects.filter(
            reference_type="LOGISTICS_PAYMENT", reference_id=pay.id).order_by("id")
        self.assertEqual(journals.count(), 2)  # قيد جديد — لا إعادة استخدام قديم
        pay.refresh_from_db()
        self.assertEqual(pay.journal_id, journals.last().id)
        self.assertNotEqual(pay.journal_id, first.id)
        self.assertTrue(pay.journal.is_posted)

        # الدفاتر المرحّلة: الدفعة محسوبة مرة واحدة بالضبط (أصل + عكس + إعادة)
        agg = JournalLine.objects.filter(
            journal__reference_id=pay.id,
            journal__reference_type__in=[
                "LOGISTICS_PAYMENT", "LOGISTICS_PAYMENT_UNPOST"],
            journal__is_posted=True,
            account=self.partner.linked_account,
        ).aggregate(d=Sum("debit"), c=Sum("credit"))
        self.assertEqual(agg["d"] - agg["c"], D("3500.00"))

    def test_deal_unpost_after_cycle_leaves_no_dangling_reversal(self):
        """مراجعة 2026-08-11: إلغاء ترحيل الصفقة بعد دورة (ترحيل→إلغاء→إعادة)
        يجب أن يحذف القيد العكسي LOGISTICS_PAYMENT_UNPOST أيضاً، وإلا بقي
        معلّقاً وحده بأثر وهمي على الدفاتر المرحّلة."""
        pay = self._payment()
        self.assertEqual(self._post(pay).status_code, 200)
        self.assertEqual(self._unpost(pay).status_code, 200)
        pay.refresh_from_db(); pay.status = "Confirmed"
        pay.save(update_fields=["status"])
        self.assertEqual(self._post(pay).status_code, 200)
        # الآن: LOGISTICS_PAYMENT ×2 مرحّلان + LOGISTICS_PAYMENT_UNPOST ×1 مرحّل
        self.assertTrue(JournalHeader.objects.filter(
            reference_type="LOGISTICS_PAYMENT_UNPOST", reference_id=pay.id).exists())

        resp = self.client.post(
            f"/api/logistics/deals/{self.deal.pk}/unpost/", {}, format="json", **self._auth())
        self.assertEqual(resp.status_code, 200, resp.content)

        # لا يبقى أي قيد للدفعة — لا أصلي ولا عكسي معلّق
        self.assertFalse(JournalHeader.objects.filter(
            reference_id=pay.id,
            reference_type__in=["LOGISTICS_PAYMENT", "LOGISTICS_PAYMENT_UNPOST"],
        ).exists())
        pay.refresh_from_db()
        self.assertFalse(pay.is_posted)
