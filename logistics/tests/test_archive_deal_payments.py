"""دفعات صفقات الأرشيف (مجموعة (ب) في `audit_deal_payment_currency`).

صفقة الأرشيف لها قيد LOGISTICS_DEAL قديم يدائن المورد بالرقم الدولاري كأنه شيكل
(سعر 1)، ودفعاتها مرحّلة بنفس الوحدة — فرصيد المورد متوازن. إنتاج D-0091: قيد
الصفقة دائن 1,535.42 والدفعة #24 (1,115.39$ بسعر 2.0) مدينة 1,115.39.

الترحيل الجديد بالشيكل (amount × usd_to_ils) صحيح للصفقات الجديدة، لكن إلغاء ترحيل
دفعة أرشيف ثم إعادتها كان يدين المورد ~4,015 مقابل دائن 1,535.42 — فيظهر مديناً لنا
وهو غير مدين. والسعر نفسه مقفل على الدفعة المرحّلة، فلم يكن لتصحيحه طريقٌ آمن.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.models import Account, AccountingAuditLog, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, post_journal
from logistics.models import LogisticsDeal, LogisticsPayment, PurchaseInvoice
from logistics.payment_posting import archive_deal_ids, is_archive_deal
from partners.models import Partner
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class ArchiveDealPaymentTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="arch", password="x", email="arch@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة الأرشيف", cls.user)
        create_fiscal_year(cls.tenant, 2025)
        create_fiscal_year(cls.tenant, 2026)
        ap = Account.objects.create(tenant=cls.tenant, code="AP-AR", name="ذمم مورد الأرشيف",
                                    account_type="Liability", is_active=True)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الأرشيف", partner_type="Supplier", linked_account=ap)
        cls.bank = Account.objects.create(tenant=cls.tenant, code="BANK-AR", name="بنك",
                                          account_type="Asset", is_active=True)
        cls.expense = Account.objects.create(tenant=cls.tenant, code="EXP-AR", name="مشتريات",
                                             account_type="Expense", is_active=True)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    # ── بناء الحالة كما على الإنتاج ────────────────────────────────────────

    def _archive_deal(self, ref="D-0091", total="1535.42"):
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number=ref, partner=self.supplier,
            order_date="2025-08-01", total_amount=D(total))
        post_journal(
            tenant_id=self.tenant.pk, transaction_date="2025-08-01",
            reference_type="LOGISTICS_DEAL", reference_id=deal.pk, description="شراء بضاعة (Auto)",
            currency=self.ils, exchange_rate=D(1),
            lines_data=[
                {"account": self.expense.pk, "debit": D(total), "credit": D(0), "description": "أرشيف"},
                {"account": self.supplier.linked_account_id, "debit": D(0), "credit": D(total),
                 "partner": self.supplier.pk, "description": "أرشيف"},
            ])
        return deal

    def _payment(self, deal, amount="1115.39", rate="3.5", date="2025-10-15"):
        return LogisticsPayment.objects.create(
            deal=deal, title=f"P{amount}", amount=D(amount), status="Confirmed",
            usd_to_ils=D(rate), transfer_date=date)

    def _legacy_posted(self, deal, amount="1115.39", rate="3.5"):
        """دفعة مرحّلة كما رحّلها الكود القديم: الرقم الدولاري كشيكل بسعر 1."""
        pay = self._payment(deal, amount, rate)
        jh = post_journal(
            tenant_id=self.tenant.pk, transaction_date="2025-10-15",
            reference_type="LOGISTICS_PAYMENT", reference_id=pay.pk,
            description="قديم", currency=self.ils, exchange_rate=D(1), idempotent=False,
            lines_data=[
                {"account": self.supplier.linked_account_id, "debit": D(amount), "credit": D(0),
                 "partner": self.supplier.pk, "description": "قديم"},
                {"account": self.bank.pk, "debit": D(0), "credit": D(amount), "description": "قديم"},
            ])
        LogisticsPayment.objects.filter(pk=pay.pk).update(
            is_posted=True, journal=jh, bank_account=self.bank)
        pay.refresh_from_db()
        return pay

    def _net(self, account):
        agg = JournalLine.objects.filter(
            tenant=self.tenant, account=account, journal__is_posted=True,
        ).aggregate(d=Sum("base_debit"), c=Sum("base_credit"))
        return (agg["d"] or D(0)) - (agg["c"] or D(0))

    def _post(self, deal, pay):
        return self.client.post(
            f"/api/logistics/deals/{deal.pk}/post_payment/{pay.pk}/",
            {"bank_account_id": self.bank.pk}, format="json", **self.h)

    def _unpost(self, deal, pay):
        return self.client.post(
            f"/api/logistics/deals/{deal.pk}/unpost_payment/{pay.pk}/", {}, format="json", **self.h)

    def _patch(self, deal, pay, body):
        return self.client.patch(
            f"/api/logistics/deals/{deal.pk}/payments/{pay.pk}/", body, format="json", **self.h)

    # ── (1) حارس الترحيل ───────────────────────────────────────────────────

    def test_unpost_edit_rate_repost_keeps_archive_supplier_balance(self):
        deal = self._archive_deal()
        pay = self._legacy_posted(deal)
        supplier_before = self._net(self.supplier.linked_account)
        bank_before = self._net(self.bank)

        self.assertEqual(self._unpost(deal, pay).status_code, 200)
        # إلغاء الترحيل يعيد الحالة Pending — المستخدم يؤكّدها مع السعر الجديد.
        self.assertEqual(self._patch(
            deal, pay, {"usd_to_ils": "3.6", "status": "Confirmed"}).status_code, 200)
        resp = self._post(deal, pay)
        self.assertEqual(resp.status_code, 200, resp.content)

        # إعادة الترحيل تعيد قيد الأرشيف بوحدته (الرقم الدولاري بسعر 1) — لا 4,015.40.
        self.assertEqual(self._net(self.supplier.linked_account), supplier_before)
        self.assertEqual(self._net(self.bank), bank_before)
        pay.refresh_from_db()
        self.assertEqual(pay.usd_to_ils, D("3.6"))

    def test_first_post_of_a_payment_on_an_archive_deal_is_refused(self):
        # دفعةٌ لم تُرحَّل قط: بالشيكل تكسر رصيد المورد، وبوحدة الأرشيف تكتب في
        # الصندوق مبلغاً غير حقيقي — فترفض بسبب مقروء بدل أن تختار خطأً بصمت.
        deal = self._archive_deal()
        pay = self._payment(deal)
        resp = self._post(deal, pay)
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("أرشيف", resp.json()["error"])
        self.assertFalse(JournalHeader.objects.filter(
            reference_type="LOGISTICS_PAYMENT", reference_id=pay.pk).exists())

    def test_new_deal_payment_still_posts_in_shekels(self):
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-NEW", partner=self.supplier,
            order_date="2026-06-20", total_amount=D("10000"))
        pay = self._payment(deal, "1000", "3.6", date="2026-06-20")
        resp = self._post(deal, pay)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._net(self.supplier.linked_account), D("3600.00"))

    def test_archive_definition_matches_audit_group_b(self):
        archive = self._archive_deal("D-ARC")
        invoiced = self._archive_deal("D-INV")
        PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-AR", partner=self.supplier,
            currency=self.ils, invoice_date="2026-06-25", deal=invoiced,
            invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL, is_posted=True)
        plain = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-PLAIN", partner=self.supplier,
            order_date="2026-06-20", total_amount=D("1"))
        # صفقةٌ بفاتورة دولية مرحّلة مجموعة (أ) ولو كان لها قيد صفقة — كما يصنّفها الأمر.
        self.assertEqual(archive_deal_ids(self.tenant.pk), {archive.pk})
        self.assertTrue(is_archive_deal(archive))
        self.assertFalse(is_archive_deal(invoiced))
        self.assertFalse(is_archive_deal(plain))

    # ── (2) تصحيح سعر دفعة الأرشيف المرحّلة ───────────────────────────────

    def test_posted_archive_payment_rate_is_editable_and_journal_untouched(self):
        deal = self._archive_deal()
        pay = self._legacy_posted(deal, rate="2.0")
        journal_id = pay.journal_id
        lines_before = list(JournalLine.objects.filter(journal_id=journal_id).order_by("id")
                            .values_list("account_id", "base_debit", "base_credit"))

        resp = self._patch(deal, pay, {"usd_to_ils": "3.62"})
        self.assertEqual(resp.status_code, 200, resp.content)

        pay.refresh_from_db()
        self.assertEqual(pay.usd_to_ils, D("3.62"))
        self.assertTrue(pay.is_posted)
        self.assertEqual(pay.journal_id, journal_id)
        self.assertEqual(
            list(JournalLine.objects.filter(journal_id=journal_id).order_by("id")
                 .values_list("account_id", "base_debit", "base_credit")),
            lines_before)
        log = AccountingAuditLog.objects.filter(
            model_name="LogisticsPayment", object_id=str(pay.pk)).latest("id")
        self.assertIn("2", log.change_details)
        self.assertIn("3.62", log.change_details)
        self.assertEqual(log.user_id, self.user.pk)

    def test_posted_archive_payment_other_fields_stay_locked(self):
        deal = self._archive_deal()
        pay = self._legacy_posted(deal)
        resp = self._patch(deal, pay, {"usd_to_ils": "3.6", "amount": "999"})
        self.assertEqual(resp.status_code, 400, resp.content)
        pay.refresh_from_db()
        self.assertEqual((pay.amount, pay.usd_to_ils), (D("1115.39"), D("3.5")))

    def test_posted_non_archive_payment_rate_stays_locked(self):
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-NEW", partner=self.supplier,
            order_date="2026-06-20", total_amount=D("10000"))
        pay = self._payment(deal, "1000", "3.6", date="2026-06-20")
        self.assertEqual(self._post(deal, pay).status_code, 200)
        resp = self._patch(deal, pay, {"usd_to_ils": "3.7"})
        self.assertEqual(resp.status_code, 400, resp.content)
        pay.refresh_from_db()
        self.assertEqual(pay.usd_to_ils, D("3.6"))

    def test_archive_rate_edit_needs_the_unpost_permission(self):
        clerk = User.objects.create_user(username="arch-clerk", password="x")
        UserCompanyMembership.objects.create(user=clerk, tenant=self.tenant, role="procurement")
        deal = self._archive_deal()
        pay = self._legacy_posted(deal)
        self.client.force_authenticate(user=clerk)
        resp = self._patch(deal, pay, {"usd_to_ils": "3.6"})
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertIn("إلغاء ترحيلها", resp.json()["error"])
        pay.refresh_from_db()
        self.assertEqual(pay.usd_to_ils, D("3.5"))

    def test_deal_detail_exposes_archive_flag(self):
        deal = self._archive_deal()
        resp = self.client.get(f"/api/logistics/deals/{deal.pk}/", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIs(resp.json()["is_archive"], True)
