"""T-AUTOPOST: سند القبض وسند الصرف يُرحَّلان فور الحفظ (لا مسودة).

الافتراضي `SalesSettings.auto_post_payments = True`، والراية الصريحة `auto_post`
في جسم الطلب تسمو على الإعداد (زرّا «حفظ» و«حفظ وترحيل» في الواجهة).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.services import get_or_create_sales_settings
from tenants.models import Currency
from tenants.services import create_company


class PaymentAutoPostTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="autopost", password="x")
        cls.currency, _ = Currency.objects.get_or_create(
            Code="APT", defaults={"Name": "AutoPost", "Symbol": "A"})
        cls.tenant = create_company("شركة الترحيل التلقائي", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101-C", name="ذمم مدينة", account_type="Asset", is_active=True)
        cls.ap = Account.objects.create(
            tenant=cls.tenant, code="2101-C", name="ذمم دائنة", account_type="Liability", is_active=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1000-C", name="صندوق", account_type="Asset", is_active=True)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الترحيل", partner_type="Customer", linked_account=cls.ar)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الترحيل", partner_type="Supplier", linked_account=cls.ap)

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _receipt_body(self, **over):
        body = {
            "partner": self.customer.id,
            "payment_date": "2026-06-20",
            "amount": "100",
            "currency": self.currency.CurrencyID,
            "exchange_rate": "1",
            "cash_or_bank_account": self.cash.id,
        }
        body.update(over)
        return body

    def _voucher_body(self, **over):
        body = {
            "partner": self.supplier.id,
            "payment_date": "2026-06-20",
            "amount": "70",
            "currency": self.currency.CurrencyID,
            "exchange_rate": "1",
            "cash_or_bank_account": self.cash.id,
        }
        body.update(over)
        return body

    def _set_auto(self, value: bool):
        ss = get_or_create_sales_settings(self.tenant)
        ss.auto_post_payments = value
        ss.save(update_fields=["auto_post_payments"])

    # ── سند قبض العميل ──
    def test_receipt_posts_on_save_by_default(self):
        res = self.client.post("/api/sales/payments/", self._receipt_body(), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["is_posted"])
        self.assertIsNotNone(res.data["journal"])

    def test_receipt_stays_draft_when_flag_false(self):
        res = self.client.post(
            "/api/sales/payments/", self._receipt_body(auto_post=False), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertFalse(res.data["is_posted"])

    def test_receipt_setting_off_keeps_draft_and_flag_overrides(self):
        self._set_auto(False)
        draft = self.client.post("/api/sales/payments/", self._receipt_body(), format="json")
        self.assertFalse(draft.data["is_posted"])
        posted = self.client.post(
            "/api/sales/payments/", self._receipt_body(auto_post=True), format="json")
        self.assertTrue(posted.data["is_posted"])

    def test_receipt_auto_post_failure_keeps_draft_and_reports(self):
        """فشل الترحيل التلقائي (تاريخ خارج السنة المالية) لا يُضيع السند."""
        res = self.client.post(
            "/api/sales/payments/", self._receipt_body(payment_date="2019-06-20"), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertFalse(res.data["is_posted"])
        self.assertIn("auto_post_error", res.data)

    # ── سند صرف المورد ──
    def test_supplier_voucher_posts_on_save_by_default(self):
        res = self.client.post(
            "/api/logistics/supplier-payments/", self._voucher_body(), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["is_posted"])
        self.assertIsNotNone(res.data["journal"])

    def test_supplier_voucher_stays_draft_when_flag_false(self):
        res = self.client.post(
            "/api/logistics/supplier-payments/", self._voucher_body(auto_post=False), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertFalse(res.data["is_posted"])
        # يبقى قابلاً للترحيل يدوياً من زر «ترحيل» في القائمة
        posted = self.client.post(
            f"/api/logistics/supplier-payments/{res.data['id']}/post/", {}, format="json")
        self.assertEqual(posted.status_code, 200, posted.data)
        self.assertTrue(posted.data["is_posted"])

    def test_supplier_voucher_setting_off_keeps_draft(self):
        self._set_auto(False)
        res = self.client.post(
            "/api/logistics/supplier-payments/", self._voucher_body(), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertFalse(res.data["is_posted"])
        self.assertEqual(Decimal(str(res.data["amount"])), Decimal("70"))
