"""سعر صرف الدفعة من الطلب في سندات الصرف والقبض والمصروف والإيراد (M2).

كان كلٌّ منها يسقط إلى 1 بصمت لعملةٍ أجنبية: سند الصرف لأن الواجهة لا ترسل السعر
والنموذج افتراضيّه 1، وسند القبض لأن الخانة تبدأ «1»، والمصروف والإيراد بـ`or 1`.
الشيكل لا يتغيّر فيه شيء: لا خانة ولا خطأ.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, ExpenseVoucher, JournalLine, RevenueVoucher
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import CustomerPayment, SalesSettings, SupplierPayment
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class PaymentRateFromRequestTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="rate_paths", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة أسعار الدفعات", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.electricity = Account.objects.get(tenant=cls.tenant, code="5203")
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الدولار", partner_type="Customer")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد الدولار", partner_type="Supplier")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash})

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    # ── المسارات الأربعة: (المسار، الحمولة، النموذج) ───────────────────
    def _routes(self):
        voucher = {"date": "2026-06-10", "amount": "100.00", "payment_method": "cash",
                   "cash_or_bank_account": self.cash.pk}
        payment = {"payment_date": "2026-06-10", "amount": "100.00",
                   "cash_or_bank_account": self.cash.pk, "auto_post": True}
        return [
            ("/api/logistics/supplier-payments/", {**payment, "partner": self.supplier.pk},
             SupplierPayment),
            ("/api/sales/payments/", {**payment, "partner": self.customer.pk}, CustomerPayment),
            ("/api/accounting/expense-vouchers/",
             {**voucher, "expense_account": self.electricity.pk}, ExpenseVoucher),
            ("/api/accounting/revenue-vouchers/",
             {**voucher, "revenue_account_name": "عمولات دولار"}, RevenueVoucher),
        ]

    def test_foreign_currency_without_a_real_rate_is_400_on_exchange_rate(self):
        for url, body, _model in self._routes():
            for sent in (None, "0", "1"):
                with self.subTest(url=url, sent=sent):
                    payload = {**body, "currency": self.usd.pk}
                    if sent is not None:
                        payload["exchange_rate"] = sent
                    res = self.client.post(url, payload, format="json")
                    self.assertEqual(res.status_code, 400, res.content)
                    # السندان باسم الحقل؛ المصروف والإيراد بـ`error` كعادة عرضهما —
                    # والرسالة نفسها تسمّي الخانة والعملة.
                    body_text = str(res.json().get("exchange_rate") or res.json().get("error"))
                    self.assertIn("سعر صرف USD", body_text, res.content)

    def test_foreign_currency_posts_at_exactly_the_entered_rate(self):
        for url, body, model in self._routes():
            with self.subTest(url=url):
                res = self.client.post(
                    url, {**body, "currency": self.usd.pk, "exchange_rate": "3.7125"},
                    format="json")
                self.assertIn(res.status_code, (200, 201), res.content)
                doc = model.objects.get(pk=res.json()["id"])
                self.assertEqual(D(doc.exchange_rate), D("3.7125"))
                self.assertIsNotNone(doc.journal_id, res.content)
                self.assertEqual(D(doc.journal.exchange_rate), D("3.7125"))
                cash_line = JournalLine.objects.get(journal=doc.journal, account=self.cash)
                moved = D(cash_line.base_debit) + D(cash_line.base_credit)
                self.assertEqual(moved, D("371.25"))

    def test_shekel_needs_no_rate_and_posts_at_one(self):
        for url, body, model in self._routes():
            with self.subTest(url=url):
                res = self.client.post(url, {**body, "currency": self.ils.pk}, format="json")
                self.assertIn(res.status_code, (200, 201), res.content)
                doc = model.objects.get(pk=res.json()["id"])
                self.assertEqual(D(doc.exchange_rate), D("1"))

    def test_shekel_ignores_a_stray_rate(self):
        """عملة الأساس سعرها 1 حتماً — سعرٌ عالق من اختيار دولارٍ سابق لا يُضاعف الشيكل."""
        url, body, model = self._routes()[2]
        res = self.client.post(
            url, {**body, "currency": self.ils.pk, "exchange_rate": "3.7"}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(D(model.objects.get(pk=res.json()["id"]).exchange_rate), D("1"))

    def test_batch_save_rejects_the_foreign_row_and_keeps_the_shekel_row(self):
        row = {"direction": "expense", "date": "2026-06-10", "amount": "50.00",
               "payment_method": "cash", "cash_or_bank_account": self.cash.pk,
               "account": self.electricity.pk}
        res = self.client.post("/api/accounting/vouchers/batch-save/", {"rows": [
            {**row, "currency": self.usd.pk},
            {**row, "currency": self.ils.pk},
        ]}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        rows = sorted(res.json()["rows"], key=lambda r: r["index"])
        self.assertFalse(rows[0]["success"])
        self.assertIn("USD", rows[0]["error"])
        self.assertTrue(rows[1]["success"], rows[1])
