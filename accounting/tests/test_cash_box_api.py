"""T-CASHBOX — عقد الـAPI: الإنشاء بنداء واحد، الكشف، الحركة، التحويل، الصلاحيات.

الاختبارات الوحدوية في `test_cash_box_treasury.py` تحرس الخدمات؛ هذه تحرس ما
يراه المتصفح فعلاً — لأن نقطةً غير مسجَّلة أو صلاحيةً غير مُنفَذة لا يكشفهما
اختبارُ خدمة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, CashBoxLedgerAccount, CashCount, JournalHeader
from accounting.services import (
    cash_box_adjustment, cash_box_balance, create_cash_box, create_fiscal_year,
)
from tenants.services import create_company

ACC = "/api/accounting"
D = lambda v: Decimal(str(v))


class CashBoxApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="api", password="x", email="a@x.co")
        cls.tenant = create_company("شركة الواجهة", cls.user)
        create_fiscal_year(cls.tenant, 2026)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_create_is_one_call_and_builds_the_tree_account(self):
        res = self.client.post(
            f"{ACC}/cash-box-accounts/",
            {"name": "صندوق الواجهة", "currency_code": "ILS"},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertTrue(body["account_code"].startswith("1110B"), body)
        self.assertTrue(body["external_id"])  # يولّده الخادم
        self.assertTrue(body["is_default"])   # أول صندوق يصير الافتراضي
        acc = Account.objects.get(pk=body["account_id"])
        self.assertEqual(acc.sub_type, "cash_box")
        self.assertEqual(acc.name, "صندوق الواجهة")

    def test_rename_via_patch_syncs_the_account(self):
        box = create_cash_box(tenant=self.tenant, name="قديم", user=self.user)
        res = self.client.patch(
            f"{ACC}/cash-box-accounts/{box.pk}/", {"name": "جديد"},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        box.account.refresh_from_db()
        self.assertEqual(box.account.name, "جديد")

    def test_set_default_moves_the_flag(self):
        a = create_cash_box(tenant=self.tenant, name="أ", user=self.user)
        b = create_cash_box(tenant=self.tenant, name="ب", user=self.user)
        res = self.client.post(
            f"{ACC}/cash-box-accounts/{b.pk}/set-default/", {},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertFalse(a.is_default)
        self.assertTrue(b.is_default)

    def test_my_default_round_trips(self):
        box = create_cash_box(tenant=self.tenant, name="صندوقي", user=self.user)
        res = self.client.put(
            f"{ACC}/cash-box-accounts/my-default/", {"cash_box": box.pk},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        got = self.client.get(f"{ACC}/cash-box-accounts/my-default/", **self._auth())
        self.assertEqual(got.json()["cash_box"], box.pk)
        # التفريغ يحذف التفضيل ولا يُبقيه معلَّقاً
        self.client.put(f"{ACC}/cash-box-accounts/my-default/", {"cash_box": None},
                        format="json", **self._auth())
        self.assertIsNone(
            self.client.get(f"{ACC}/cash-box-accounts/my-default/", **self._auth())
            .json()["cash_box"])

    def test_adjust_then_statement_reports_a_running_balance(self):
        box = create_cash_box(tenant=self.tenant, name="صندوق الكشف", user=self.user)
        for amount in (1000, 250):
            res = self.client.post(
                f"{ACC}/cash-box-accounts/{box.pk}/adjust/",
                {"direction": "in", "amount": amount, "date": "2026-06-10",
                 "memo": "إيداع"},
                format="json", **self._auth())
            self.assertEqual(res.status_code, 201, res.content)

        res = self.client.get(f"{ACC}/cash-box-accounts/{box.pk}/statement/", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(Decimal(data["closing_balance"]), D("1250.00"))
        self.assertEqual(Decimal(data["rows"][-1]["balance"]), D("1250.00"))
        self.assertEqual(data["currency_code"], box.currency_code)

    def test_withdraw_beyond_balance_is_refused_by_the_api(self):
        box = create_cash_box(tenant=self.tenant, name="صندوق ضيّق", user=self.user)
        res = self.client.post(
            f"{ACC}/cash-box-accounts/{box.pk}/adjust/",
            {"direction": "out", "amount": 50, "date": "2026-06-10", "memo": "سحب"},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 400, res.content)

    def test_transfer_endpoint_posts_one_journal(self):
        a = create_cash_box(tenant=self.tenant, name="من", user=self.user)
        b = create_cash_box(tenant=self.tenant, name="إلى", user=self.user)
        cash_box_adjustment(a, direction="in", amount=500, date="2026-06-01", user=self.user)
        res = self.client.post(
            f"{ACC}/cash-transfers/",
            {"transfer_date": "2026-06-05", "amount": "200",
             "from_cash_box": a.pk, "to_cash_box": b.pk},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        self.assertIsNotNone(res.json()["journal"])
        self.assertEqual(cash_box_balance(a), D("300.00"))
        self.assertEqual(cash_box_balance(b), D("200.00"))

    def test_count_endpoint_posts_the_difference(self):
        box = create_cash_box(tenant=self.tenant, name="صندوق الجرد", user=self.user)
        cash_box_adjustment(box, direction="in", amount=800, date="2026-06-01", user=self.user)
        created = self.client.post(
            f"{ACC}/cash-counts/",
            {"cash_box": box.pk, "count_date": "2026-06-02", "counted_total": "760",
             "denominations": {"100": 7, "50": 1, "10": 1}},
            format="json", **self._auth())
        self.assertEqual(created.status_code, 201, created.content)
        cid = created.json()["id"]
        posted = self.client.post(f"{ACC}/cash-counts/{cid}/post/", {},
                                  format="json", **self._auth())
        self.assertEqual(posted.status_code, 200, posted.content)
        body = posted.json()
        self.assertEqual(Decimal(body["difference"]), D("-40.00"))
        self.assertEqual(body["status"], CashCount.STATUS_POSTED)
        self.assertEqual(cash_box_balance(box), D("760.00"))
        jh = JournalHeader.objects.get(pk=body["journal"])
        self.assertTrue(jh.lines.filter(account__code="5206", debit=D("40.00")).exists())

    def test_tenant_isolation_hides_other_companies_boxes(self):
        other_user = User.objects.create_user(username="other", password="x", email="o@x.co")
        other = create_company("شركة أخرى", other_user)
        create_cash_box(tenant=other, name="صندوق الغير", user=other_user)
        create_cash_box(tenant=self.tenant, name="صندوقي أنا", user=self.user)
        res = self.client.get(f"{ACC}/cash-box-accounts/", **self._auth())
        names = {row["name"] for row in res.json()}
        self.assertIn("صندوقي أنا", names)
        self.assertNotIn("صندوق الغير", names)


class CashBoxPermissionTest(APITestCase):
    """المفاتيح الجديدة تُنفَّذ خادمياً — إخفاء الزرّ ليس حماية."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="owner2", password="x", email="ow@x.co")
        cls.tenant = create_company("شركة الصلاحيات", cls.owner)
        create_fiscal_year(cls.tenant, 2026)
        cls.box = create_cash_box(tenant=cls.tenant, name="صندوق محروس", user=cls.owner)
        cash_box_adjustment(cls.box, direction="in", amount=500,
                            date="2026-06-01", user=cls.owner)

    def _viewer(self):
        from tenants.models import UserCompanyMembership

        viewer = User.objects.create_user(username="viewer2", password="x", email="v@x.co")
        UserCompanyMembership.objects.create(
            user=viewer, tenant=self.tenant, role="viewer")
        self.client.force_authenticate(user=viewer)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_viewer_cannot_withdraw(self):
        res = self.client.post(
            f"{ACC}/cash-box-accounts/{self.box.pk}/adjust/",
            {"direction": "out", "amount": 10, "date": "2026-06-05", "memo": "سحب"},
            format="json", **self._viewer())
        self.assertEqual(res.status_code, 403, res.content)

    def test_viewer_cannot_transfer(self):
        other = create_cash_box(tenant=self.tenant, name="وجهة", user=self.owner)
        res = self.client.post(
            f"{ACC}/cash-transfers/",
            {"transfer_date": "2026-06-05", "amount": "10",
             "from_cash_box": self.box.pk, "to_cash_box": other.pk},
            format="json", **self._viewer())
        self.assertEqual(res.status_code, 403, res.content)

    def test_viewer_cannot_post_a_count(self):
        res = self.client.post(
            f"{ACC}/cash-counts/",
            {"cash_box": self.box.pk, "count_date": "2026-06-05", "counted_total": "1"},
            format="json", **self._viewer())
        self.assertEqual(res.status_code, 403, res.content)
