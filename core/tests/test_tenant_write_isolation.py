"""المرحلة 5 / P1-6 + P1-7 + P1-8: سدّ الثغرات النمطية في عزل الشركة.

- P1-7: ‎get_queryset‎ بلا ‎.none()‎ عند غياب الشركة كان يُرجِع صفوف كل الشركات
  (إعدادات الشركة، الدفاتر، الإرساليات، الإشعارات، وعقارات realestate).
- P1-8: ‎PrimaryKeyRelatedField(queryset=X.objects.all())‎ يقبل pk من أي شركة
  عند الكتابة — ‎get_queryset‎ يحمي القراءة فقط. الحقل المشترك
  ‎TenantScopedPrimaryKeyRelatedField‎ (core/api_defaults.py) يقيّد الحلّ
  بشركة الطلب.
- P1-6 (فلتر tenant في فحص عكس القيد) مُختبَر وظيفياً هنا عبر التصادم:
  reference_id متطابق في شركة أخرى يجب ألا يمنع عكس قيد مشروع.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class _TwoTenantBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="iso-a", password="x")
        cls.other_user = User.objects.create_user(username="iso-b", password="x")
        cls.currency, _ = Currency.objects.get_or_create(
            Code="ISO", defaults={"Name": "Iso", "Symbol": "I"})
        cls.tenant = create_company("شركة العزل أ", cls.user)
        cls.other_tenant = create_company("شركة العزل ب", cls.other_user)
        create_fiscal_year(cls.tenant, 2026)
        create_fiscal_year(cls.other_tenant, 2026)
        cls.token = Token.objects.create(user=cls.user)

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _h(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}


class WriteScopedPKFieldTest(_TwoTenantBase):
    """P1-8: الكتابة بحساب/شريك من شركة أخرى تُرفض كأنّ الكائن غير موجود."""

    def test_customer_payment_rejects_foreign_cash_account(self):
        customer = Partner.objects.create(
            tenant=self.tenant, name="زبون العزل", partner_type="Customer")
        foreign_account = Account.objects.filter(
            tenant=self.other_tenant).first()
        self.assertIsNotNone(foreign_account)  # شجرة الحسابات تُزرع مع الشركة
        res = self.client.post(
            "/api/sales/payments/",
            {
                "partner": customer.id, "amount": "50",
                "payment_date": "2026-06-01",
                "currency": self.currency.CurrencyID,
                "cash_or_bank_account": foreign_account.id,
            },
            format="json", **self._h(),
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("cash_or_bank_account", res.json())

    def test_manual_journal_rejects_foreign_partner_on_line(self):
        foreign_partner = Partner.objects.create(
            tenant=self.other_tenant, name="شريك أجنبي", partner_type="Customer")
        acc = Account.objects.filter(tenant=self.tenant, is_active=True).first()
        res = self.client.post(
            "/api/accounting/journals/",
            {
                "transaction_date": "2026-06-01",
                "description": "قيد اختبار عزل",
                "lines": [
                    {"account": acc.id, "debit": "10", "credit": "0",
                     "partner": foreign_partner.id},
                    {"account": acc.id, "debit": "0", "credit": "10"},
                ],
            },
            format="json", **self._h(),
        )
        self.assertEqual(res.status_code, 400, res.content[:300])

    def test_account_create_rejects_foreign_parent(self):
        """THA-292: أبٌ من شركة أخرى يعلّق الحساب تحت شجرة لا تراها شركته."""
        foreign_parent = Account.objects.filter(tenant=self.other_tenant).first()
        self.assertIsNotNone(foreign_parent)
        res = self.client.post(
            "/api/accounting/accounts/",
            {
                "code": "9971", "name": "حساب بأبٍ أجنبي",
                "account_type": "Asset", "parent": foreign_parent.id,
            },
            format="json", **self._h(),
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("parent", res.json())

    def test_account_update_rejects_foreign_parent(self):
        """THA-292: نفس الحارس على التعديل — لا يكفي حماية الإنشاء."""
        mine = Account.objects.filter(tenant=self.tenant).first()
        foreign_parent = Account.objects.filter(tenant=self.other_tenant).first()
        res = self.client.patch(
            f"/api/accounting/accounts/{mine.id}/",
            {"parent": foreign_parent.id}, format="json", **self._h(),
        )
        self.assertEqual(res.status_code, 400, res.content[:300])
        self.assertIn("parent", res.json())

    def test_account_accepts_parent_from_same_tenant(self):
        """الحارس لا يكسر الاستخدام المشروع — أب من شركة الطلب يمرّ."""
        parent = Account.objects.filter(tenant=self.tenant).first()
        res = self.client.post(
            "/api/accounting/accounts/",
            {
                "code": "9972", "name": "حساب بأبٍ محلي",
                "account_type": "Asset", "parent": parent.id,
            },
            format="json", **self._h(),
        )
        self.assertIn(res.status_code, (200, 201), res.content[:300])
        self.assertEqual(res.json()["parent"], parent.id)

    def test_same_tenant_partner_still_accepted_on_line(self):
        """الحارس لا يكسر الاستخدام المشروع — شريك الشركة نفسها يمرّ."""
        partner = Partner.objects.create(
            tenant=self.tenant, name="شريك محلي", partner_type="Customer")
        acc = Account.objects.filter(tenant=self.tenant, is_active=True).first()
        res = self.client.post(
            "/api/accounting/journals/",
            {
                "transaction_date": "2026-06-01",
                "description": "قيد مشروع",
                "lines": [
                    {"account": acc.id, "debit": "10", "credit": "0",
                     "partner": partner.id},
                    {"account": acc.id, "debit": "0", "credit": "10"},
                ],
            },
            format="json", **self._h(),
        )
        self.assertIn(res.status_code, (200, 201), res.content[:300])


class NoneOnMissingTenantTest(_TwoTenantBase):
    """P1-7: غياب سياق الشركة = قائمة فارغة، لا بيانات كل الشركات."""

    ENDPOINTS = [
        "/api/tenants/settings/",
        "/api/tenants/books/",
        "/api/sales/delivery-orders/",
        "/api/sales/credit-debit-notes/",
    ]

    def test_no_tenant_header_returns_empty_not_everything(self):
        for url in self.ENDPOINTS:
            with self.subTest(url=url):
                res = self.client.get(url)  # بلا X-Tenant-Id
                if res.status_code != 200:
                    # بعض النقاط ترفض الطلب كلياً بلا شركة — سلوك أشدّ، مقبول.
                    self.assertIn(res.status_code, (400, 403), url)
                    continue
                data = res.json()
                rows = data.get("results", data) if isinstance(data, dict) else data
                self.assertEqual(rows, [], f"{url} سرّب صفوفاً بلا شركة")


class ReversalTenantScopeTest(_TwoTenantBase):
    """P1-6: تصادم reference_id بين شركتين لا يمنع عكس قيد مشروع."""

    def _post_journal(self, tenant, amount="25"):
        acc = Account.objects.filter(tenant=tenant, is_active=True).first()
        j = JournalHeader.objects.create(
            tenant=tenant, transaction_date="2026-06-01",
            description="قيد للعكس", is_posted=True,
        )
        JournalLine.objects.create(
            tenant=tenant, journal=j, account=acc,
            debit=Decimal(amount), credit=0,
            base_debit=Decimal(amount), base_credit=0)
        JournalLine.objects.create(
            tenant=tenant, journal=j, account=acc,
            debit=0, credit=Decimal(amount),
            base_debit=0, base_credit=Decimal(amount))
        return j

    def test_foreign_reversal_with_same_reference_id_does_not_block(self):
        mine = self._post_journal(self.tenant)
        # شركة أخرى لديها قيد عكسي reference_id يساوي id قيدي — قبل P1-6 كان
        # فحص «عُكس مسبقاً» بلا tenant فيلتقطه ويمنع عكس قيدي المشروع.
        JournalHeader.objects.create(
            tenant=self.other_tenant, transaction_date="2026-06-01",
            description="عكس أجنبي متصادم",
            reference_type="JOURNAL_REVERSAL", reference_id=mine.id,
        )
        res = self.client.post(
            f"/api/accounting/journals/{mine.id}/reverse/",
            {"transaction_date": "2026-06-02"}, format="json", **self._h(),
        )
        self.assertIn(res.status_code, (200, 201), res.content[:300])

    def test_double_reversal_within_tenant_still_rejected(self):
        mine = self._post_journal(self.tenant)
        first = self.client.post(
            f"/api/accounting/journals/{mine.id}/reverse/",
            {"transaction_date": "2026-06-02"}, format="json", **self._h(),
        )
        self.assertIn(first.status_code, (200, 201), first.content[:300])
        second = self.client.post(
            f"/api/accounting/journals/{mine.id}/reverse/",
            {"transaction_date": "2026-06-03"}, format="json", **self._h(),
        )
        self.assertEqual(second.status_code, 400, second.content[:300])
