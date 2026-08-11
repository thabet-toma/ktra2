"""T-CHQ3/هـ — حسابا الشيكات يُنشآن من الكود عند غيابهما.

قرار المالك: «إذا فش حساب تحصيل شيكات اعمل واحد افتراضي من الكود». كان
`resolve_cheques_under_collection_account` يرفض الترحيل ويطلب من المستخدم أن
يعيّن الحساب بنفسه — فيقف عمله عند أول شيك في شركة شجرتها ناقصة (وهو بالضبط
ما رآه المالك: «تعذّر الترحيل… عيّن default_cheques_under_collection_account»).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import CustomerPayment, SalesSettings, SupplierPayment
from sales.services import (
    post_customer_payment,
    post_supplier_payment,
    resolve_cheques_payable_account,
    resolve_cheques_under_collection_account,
)
from tenants.models import Currency
from tenants.services import create_company


class ChequeAccountsAutoCreateTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chqacc", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة بلا حسابات شيكات", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون", partner_type="Customer")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash},
        )

    def setUp(self):
        # شجرة ناقصة: لا حساب شيكات وارد ولا صادر ولا إعداد يشير إليهما.
        Account.objects.filter(
            tenant=self.tenant, name__icontains="شيكات").delete()
        SalesSettings.objects.filter(tenant=self.tenant).update(
            default_cheques_under_collection_account=None)

    def test_under_collection_account_is_created_when_missing(self):
        acc = resolve_cheques_under_collection_account(self.tenant.TenantID)
        self.assertEqual(acc.code, "1107")
        self.assertEqual(acc.account_type, "Asset")
        self.assertIn("شيكات", acc.name)

    def test_created_account_is_pinned_into_settings_so_it_can_be_changed(self):
        """يُعيَّن في الإعدادات كي يراه المالك ويغيّره إن أراد."""
        acc = resolve_cheques_under_collection_account(self.tenant.TenantID)
        ss = SalesSettings.objects.get(tenant=self.tenant)
        self.assertEqual(ss.default_cheques_under_collection_account_id, acc.pk)

    def test_payable_account_is_created_when_missing(self):
        acc = resolve_cheques_payable_account(self.tenant.TenantID)
        self.assertEqual(acc.code, "2111")
        self.assertEqual(acc.account_type, "Liability")

    def test_resolvers_are_idempotent(self):
        first = resolve_cheques_under_collection_account(self.tenant.TenantID)
        second = resolve_cheques_under_collection_account(self.tenant.TenantID)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Account.objects.filter(tenant=self.tenant, code="1107").count(), 1)

    def test_account_is_created_even_without_the_standard_parent(self):
        """شجرة غير معيارية: `ensure_operational_accounts` كان يتخطّى الحساب."""
        Account.objects.filter(tenant=self.tenant, code="11").delete()
        acc = resolve_cheques_under_collection_account(self.tenant.TenantID)
        self.assertIn("شيكات", acc.name)

    def test_reuses_a_disabled_or_mistyped_account_instead_of_duplicating(self):
        """حساب الشيكات موجود لكن معطَّل/بنوع آخر — يُعاد استعماله لا يُستنسخ.

        البحث يقتصر على الأصول النشطة، فبدون هذا الحارس نُدرج حساباً ثانياً
        بنفس الاسم — وفي القواعد المُرحَّلة من 0001 (قيد فريد على
        `(tenant, name)`) يصير الإدراج خطأ 500 في وجه المستخدم وهو يحفظ سنداً.
        """
        stale = Account.objects.create(
            tenant=self.tenant, code="9107",
            name="شيكات برسم التحصيل (Cheques Under Collection)",
            account_type="Liability", is_active=False,
        )
        acc = resolve_cheques_under_collection_account(self.tenant.TenantID)
        self.assertEqual(acc.pk, stale.pk)
        self.assertEqual(
            Account.objects.filter(
                tenant=self.tenant,
                name="شيكات برسم التحصيل (Cheques Under Collection)").count(),
            1,
        )

    def test_customer_payment_with_cheque_posts_without_manual_setup(self):
        payment = CustomerPayment.objects.create(
            tenant=self.tenant, partner=self.customer, currency=self.ils,
            payment_date="2026-08-07", amount=Decimal("444.00"),
            cash_or_bank_account=self.cash,
        )
        from accounting.models import Cheque
        Cheque.objects.create(
            tenant=self.tenant, customer_payment=payment, partner=self.customer,
            direction="Incoming", status="Draft", cheque_number="C-1",
            amount=Decimal("444.00"), currency=self.ils,
        )
        post_customer_payment(payment)
        payment.refresh_from_db()
        self.assertTrue(payment.is_posted)
        debit = next(ln for ln in payment.journal.lines.select_related("account")
                     if ln.debit > 0)
        self.assertIn("شيكات", debit.account.name)

    def test_supplier_payment_with_cheque_posts_without_manual_setup(self):
        payment = SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.supplier, currency=self.ils,
            payment_date="2026-08-07", amount=Decimal("444.00"),
            cash_or_bank_account=self.cash,
        )
        from accounting.models import Cheque
        Cheque.objects.create(
            tenant=self.tenant, supplier_payment=payment, partner=self.supplier,
            direction="Outgoing", status="Draft", cheque_number="C-2",
            amount=Decimal("444.00"), currency=self.ils,
        )
        post_supplier_payment(payment)
        payment.refresh_from_db()
        self.assertTrue(payment.is_posted)
        credit = next(ln for ln in payment.journal.lines.select_related("account")
                      if ln.credit > 0)
        self.assertIn("شيكات", credit.account.name)
