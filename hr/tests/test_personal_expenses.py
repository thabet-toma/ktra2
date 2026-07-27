"""مصاريف شخصية — دفتر جيب لكل مستخدم، معزول تماماً وبلا أثر محاسبي.

الثوابت التي يحرسها هذا الملف:
1. **العزل**: لا أحد يرى مصاريف غيره — ولا حتى مدير الشركة (لا قائمة ولا تفصيل
   ولا تعديل ولا حذف).
2. **لا علاقة بشجرة الحسابات**: التسجيل لا يُنشئ قيداً ولا يلمس أي حساب.
3. **ليست بيانات شركة**: حتى «مستعرض» (قراءة فقط على دفاتر الشركة) يسجّل
   مصاريفه الشخصية، والمصاريف تتبع صاحبها لا الشركة النشطة.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import JournalHeader
from tenants.models import UserCompanyMembership
from tenants.services import create_company

URL = "/api/hr/personal-expenses/"


class PersonalExpenseApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="pe-boss", password="x")
        cls.staff = User.objects.create_user(username="pe-staff", password="x")
        cls.watcher = User.objects.create_user(username="pe-watcher", password="x")
        cls.tenant = create_company("شركة المصاريف", cls.boss)
        for user, role in ((cls.staff, "staff"), (cls.watcher, "viewer")):
            UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role)

    def _as(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create(self, user, **overrides):
        payload = {
            "date": "2026-07-10",
            "title": "قهوة",
            "category": "food",
            "amount": "12.50",
            "is_paid": True,
        }
        payload.update(overrides)
        res = self.client.post(URL, payload, format="json", **self._as(user))
        assert res.status_code == 201, res.content
        return res.json()

    def test_create_records_owner_from_request(self):
        row = self._create(self.staff, title="غداء")
        assert row["title"] == "غداء"
        assert row["amount"] == "12.50"
        assert row["is_paid"] is True
        assert row["category_label"] == "طعام وشراب"

    def test_owner_cannot_be_forged_by_payload(self):
        """إرسال user في الجسم لا يمنح مصروفاً لمستخدم آخر."""
        res = self.client.post(
            URL,
            {"date": "2026-07-10", "title": "محاولة", "category": "other",
             "amount": "5", "is_paid": False, "user": self.boss.pk},
            format="json", **self._as(self.staff),
        )
        assert res.status_code == 201, res.content
        assert self.client.get(URL, **self._as(self.boss)).json() == []

    def test_list_shows_only_my_expenses(self):
        self._create(self.staff, title="مصروفي")
        self._create(self.boss, title="مصروف المدير")
        mine = self.client.get(URL, **self._as(self.staff)).json()
        assert [r["title"] for r in mine] == ["مصروفي"]

    def test_manager_cannot_reach_another_users_expense(self):
        row = self._create(self.staff)
        h = self._as(self.boss)
        assert self.client.get(f"{URL}{row['id']}/", **h).status_code == 404
        assert self.client.patch(
            f"{URL}{row['id']}/", {"title": "تعديل"}, format="json", **h
        ).status_code == 404
        assert self.client.delete(f"{URL}{row['id']}/", **h).status_code == 404

    def test_owner_edits_and_deletes_own_expense(self):
        row = self._create(self.staff)
        h = self._as(self.staff)
        res = self.client.patch(
            f"{URL}{row['id']}/", {"is_paid": False}, format="json", **h)
        assert res.status_code == 200, res.content
        assert res.json()["is_paid"] is False
        assert self.client.delete(f"{URL}{row['id']}/", **h).status_code == 204
        assert self.client.get(URL, **h).json() == []

    def test_viewer_role_still_records_own_expenses(self):
        """«مستعرض» قراءة فقط على دفاتر الشركة — لكن جيبه جيبه."""
        row = self._create(self.watcher, title="مواصلات")
        assert row["title"] == "مواصلات"

    def test_expense_creates_no_journal(self):
        before = JournalHeader.objects.count()
        self._create(self.staff, amount="900")
        assert JournalHeader.objects.count() == before

    def test_filters_by_month_category_and_paid_state(self):
        self._create(self.staff, date="2026-07-01", title="يوليو مدفوع",
                     category="food", is_paid=True)
        self._create(self.staff, date="2026-07-20", title="يوليو غير مدفوع",
                     category="bills", is_paid=False)
        self._create(self.staff, date="2026-06-15", title="يونيو",
                     category="food", is_paid=True)
        h = self._as(self.staff)

        month = self.client.get(f"{URL}?month=2026-07", **h).json()
        assert {r["title"] for r in month} == {"يوليو مدفوع", "يوليو غير مدفوع"}

        food = self.client.get(f"{URL}?category=food", **h).json()
        assert {r["title"] for r in food} == {"يوليو مدفوع", "يونيو"}

        unpaid = self.client.get(f"{URL}?is_paid=false", **h).json()
        assert [r["title"] for r in unpaid] == ["يوليو غير مدفوع"]

    def test_summary_totals_are_mine_only(self):
        self._create(self.staff, date="2026-07-01", amount="100",
                     category="food", is_paid=True)
        self._create(self.staff, date="2026-07-02", amount="40",
                     category="bills", is_paid=False)
        self._create(self.boss, date="2026-07-03", amount="999",
                     category="food", is_paid=True)

        summary = self.client.get(
            f"{URL}summary/?month=2026-07", **self._as(self.staff)).json()
        assert summary["count"] == 2
        assert summary["total"] == "140.00"
        assert summary["paid_total"] == "100.00"
        assert summary["unpaid_total"] == "40.00"
        by_cat = {c["category"]: c["total"] for c in summary["by_category"]}
        assert by_cat == {"food": "100.00", "bills": "40.00"}

    def test_anonymous_is_rejected(self):
        assert self.client.get(URL).status_code in (401, 403)
