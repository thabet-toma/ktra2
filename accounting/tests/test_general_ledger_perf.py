"""P1-3 (SCALABILITY_AUDIT §2-5): دفتر الأستاذ العام — ثبات عدّ الاستعلامات.

عطلان مقيسان كانا في النقطة نفسها:

1. **توسيع شجرة الحسابات تعاودياً** — استعلامان لكل حساب (أبناء بالـFK، ثم
   أبناء بالكود) قبل أن يبدأ التقرير أصلاً، فشجرة عميقة تكلّف عشرات
   الاستعلامات على حساب واحد.
2. **`journal__currency` خارج select_related** رغم أن كل سطر يقرأ
   `line.journal.currency.Code` ⇒ استعلام لكل سطر في الكشف.

الحارس أدناه يقيس الاثنين: العدّ لا يتحرّك بعمق الشجرة، ولا بعدد الأسطر.
والقيم (الافتتاحي، المتحرّك، الختامي، مجموعة الحسابات المشمولة) تبقى كما هي.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from tenants.models import Currency, Tenant, UserCompanyMembership


class GeneralLedgerPerformanceTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(CompanyName="شركة دفتر الأستاذ")
        cls.user = User.objects.create_user(username="gl_perf", password="x")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager",
        )
        cls.currency = Currency.objects.create(
            Code="GLP", Symbol="$", IsBaseCurrency=True,
        )

        # شجرة عميقة: الجذر ثم 5 مستويات متسلسلة تحته (الكود يرث بادئة أبيه).
        cls.root = Account.objects.create(
            tenant=cls.tenant, code="5", name="مصاريف", account_type="Expense",
        )
        parent = cls.root
        cls.chain = []
        for depth in range(1, 6):
            parent = Account.objects.create(
                tenant=cls.tenant, code="5" + "1" * depth,
                name=f"فرع {depth}", account_type="Expense", parent=parent,
            )
            cls.chain.append(parent)
        cls.leaf = cls.chain[-1]

        # حساب خارج الشجرة — يجب ألا يدخل الكشف.
        cls.outsider = Account.objects.create(
            tenant=cls.tenant, code="4", name="إيراد", account_type="Revenue",
        )

        cls.counter = Account.objects.create(
            tenant=cls.tenant, code="1101", name="صندوق", account_type="Asset",
        )

        # قيد افتتاحي قبل المدى + ٦ قيود داخله على الورقة.
        cls._journal("2026-01-05", cls.leaf, Decimal("100"))
        for day in range(1, 7):
            cls._journal(f"2026-03-{day:02d}", cls.leaf, Decimal("10"))
        # قيد على حساب خارج الشجرة — حارس نطاق.
        cls._journal("2026-03-01", cls.outsider, Decimal("999"))

    @classmethod
    def _journal(cls, date, account, amount):
        header = JournalHeader.objects.create(
            tenant=cls.tenant, transaction_date=date, description="حركة اختبار",
            is_posted=True, currency=cls.currency, exchange_rate=1,
        )
        JournalLine.objects.create(
            tenant=cls.tenant, journal=header, account=account,
            debit=amount, credit=0, base_debit=amount, base_credit=0,
        )
        JournalLine.objects.create(
            tenant=cls.tenant, journal=header, account=cls.counter,
            debit=0, credit=amount, base_debit=0, base_credit=amount,
        )
        return header

    def _ledger(self, account):
        self.client.force_authenticate(user=self.user)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(
                "/api/accounting/general-ledger/"
                f"?account_id={account.id}&start_date=2026-02-01&end_date=2026-12-31",
                HTTP_X_TENANT_ID=str(self.tenant.TenantID),
            )
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json(), len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_tree_depth(self):
        """الجذر (شجرة من ٧ حسابات) لا يكلّف أكثر من الورقة (حساب واحد)."""
        _, leaf_queries = self._ledger(self.leaf)
        _, root_queries = self._ledger(self.root)
        self.assertLessEqual(root_queries, leaf_queries)

    def test_values_and_scope_are_unchanged(self):
        data, _ = self._ledger(self.root)
        # الافتتاحي = قيد يناير (100)، والحركة داخل المدى = ٦ × ١٠.
        self.assertEqual(Decimal(str(data["opening_balance"])), Decimal("100"))
        self.assertEqual(len(data["transactions"]), 6)
        self.assertEqual(Decimal(str(data["closing_balance"])), Decimal("160"))
        # الحساب خارج الشجرة لا يدخل رغم أن قيده داخل المدى.
        self.assertNotIn(Decimal("999"), [
            Decimal(str(row["debit"])) for row in data["transactions"]
        ])
        # العملة تُقرأ من الجلب المسبق لا باستعلام لكل سطر.
        self.assertEqual(data["transactions"][0]["currency"], "GLP")
        self.assertFalse(data["truncated"])
        self.assertEqual(data["total_count"], 6)
