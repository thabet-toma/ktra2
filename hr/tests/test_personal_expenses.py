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
SHEETS_URL = "/api/hr/personal-expense-sheets/"
CATEGORIES_URL = "/api/hr/personal-expense-categories/"


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


class PersonalExpenseSheetApiTest(APITestCase):
    """أوراق المصاريف — تبويبات بأسلوب إكسل، بالعزل نفسه المفروض على المصاريف."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="sheet-owner", password="x")
        cls.other = User.objects.create_user(username="sheet-other", password="x")

    def _as(self, user):
        self.client.force_authenticate(user=user)

    def _sheets(self, user):
        self._as(user)
        res = self.client.get(SHEETS_URL)
        assert res.status_code == 200, res.content
        return res.json()

    def _add_sheet(self, user, name):
        self._as(user)
        res = self.client.post(SHEETS_URL, {"name": name}, format="json")
        assert res.status_code == 201, res.content
        return res.json()

    def test_first_visit_seeds_one_default_sheet(self):
        sheets = self._sheets(self.owner)
        assert [s["name"] for s in sheets] == ["الورقة 1"]
        assert len(self._sheets(self.owner)) == 1  # لا تتكاثر بالزيارات

    def test_sheets_are_added_renamed_and_isolated_per_user(self):
        added = self._add_sheet(self.owner, "سفر")
        self._as(self.owner)
        renamed = self.client.patch(
            f"{SHEETS_URL}{added['id']}/", {"name": "رحلات"}, format="json")
        assert renamed.status_code == 200, renamed.content
        assert renamed.json()["name"] == "رحلات"

        self._as(self.other)
        assert self.client.get(f"{SHEETS_URL}{added['id']}/").status_code == 404
        assert self.client.patch(
            f"{SHEETS_URL}{added['id']}/", {"name": "سرقة"}, format="json"
        ).status_code == 404
        assert [s["name"] for s in self._sheets(self.other)] == ["الورقة 1"]

    def test_duplicate_sheet_name_is_refused(self):
        self._add_sheet(self.owner, "سفر")
        self._as(self.owner)
        res = self.client.post(SHEETS_URL, {"name": "سفر"}, format="json")
        assert res.status_code == 400, res.content

    def test_expenses_are_scoped_to_the_selected_sheet(self):
        first = self._sheets(self.owner)[0]
        travel = self._add_sheet(self.owner, "سفر")
        self._as(self.owner)
        for sheet_id, title in ((first["id"], "بقالة"), (travel["id"], "تذكرة")):
            res = self.client.post(
                URL,
                {"date": "2026-07-05", "title": title, "category": "other",
                 "amount": "10", "is_paid": True, "sheet": sheet_id},
                format="json",
            )
            assert res.status_code == 201, res.content

        rows = self.client.get(f"{URL}?sheet={travel['id']}").json()
        assert [r["title"] for r in rows] == ["تذكرة"]
        summary = self.client.get(f"{URL}summary/?sheet={travel['id']}").json()
        assert summary["count"] == 1

    def test_expense_without_sheet_lands_in_the_first_sheet(self):
        self._as(self.owner)
        res = self.client.post(
            URL,
            {"date": "2026-07-05", "title": "بلا ورقة", "category": "other",
             "amount": "3", "is_paid": True},
            format="json",
        )
        assert res.status_code == 201, res.content
        assert res.json()["sheet"] == self._sheets(self.owner)[0]["id"]

    def test_expense_cannot_be_filed_into_another_users_sheet(self):
        foreign = self._add_sheet(self.other, "ورقة الغير")
        self._as(self.owner)
        res = self.client.post(
            URL,
            {"date": "2026-07-05", "title": "تسلل", "category": "other",
             "amount": "5", "is_paid": True, "sheet": foreign["id"]},
            format="json",
        )
        assert res.status_code == 400, res.content

    def test_only_sheet_cannot_be_deleted_but_extra_sheets_can(self):
        first = self._sheets(self.owner)[0]
        self._as(self.owner)
        assert self.client.delete(f"{SHEETS_URL}{first['id']}/").status_code == 400

        travel = self._add_sheet(self.owner, "سفر")
        self._as(self.owner)
        self.client.post(
            URL,
            {"date": "2026-07-05", "title": "تذكرة", "category": "other",
             "amount": "10", "is_paid": True, "sheet": travel["id"]},
            format="json",
        )
        assert self.client.delete(f"{SHEETS_URL}{travel['id']}/").status_code == 204
        assert self.client.get(URL).json() == []  # مصاريف الورقة رحلت معها


class PersonalExpenseCategoryApiTest(APITestCase):
    """كتالوج الفئات لكل مستخدم — إعادة تسمية وإضافة بلا فقد ارتباط المصاريف."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="cat-owner", password="x")
        cls.other = User.objects.create_user(username="cat-other", password="x")

    def _as(self, user):
        self.client.force_authenticate(user=user)

    def _categories(self, user):
        self._as(user)
        res = self.client.get(CATEGORIES_URL)
        assert res.status_code == 200, res.content
        return res.json()

    def _expense(self, category, title="مصروف"):
        res = self.client.post(
            URL,
            {"date": "2026-07-05", "title": title, "category": category,
             "amount": "20", "is_paid": True},
            format="json",
        )
        assert res.status_code == 201, res.content
        return res.json()

    def test_first_visit_seeds_the_eight_defaults(self):
        rows = self._categories(self.owner)
        assert [r["key"] for r in rows[:3]] == ["food", "transport", "bills"]
        assert len(rows) == 8
        assert dict((r["key"], r["label"]) for r in rows)["food"] == "طعام وشراب"
        assert len(self._categories(self.owner)) == 8  # لا تُزرع مرتين

    def test_renaming_a_category_keeps_its_expenses_and_updates_labels(self):
        rows = self._categories(self.owner)
        food = next(r for r in rows if r["key"] == "food")
        self._as(self.owner)
        expense = self._expense("food", title="غداء")

        renamed = self.client.patch(
            f"{CATEGORIES_URL}{food['id']}/", {"label": "أكل وشرب"}, format="json")
        assert renamed.status_code == 200, renamed.content

        listed = self.client.get(f"{URL}{expense['id']}/").json()
        assert listed["category"] == "food"
        assert listed["category_label"] == "أكل وشرب"
        summary = self.client.get(f"{URL}summary/?month=2026-07").json()
        assert summary["by_category"][0]["label"] == "أكل وشرب"

    def test_key_is_server_owned_and_cannot_be_rewritten(self):
        food = next(r for r in self._categories(self.owner) if r["key"] == "food")
        self._as(self.owner)
        res = self.client.patch(
            f"{CATEGORIES_URL}{food['id']}/", {"key": "hacked"}, format="json")
        assert res.status_code == 200, res.content
        assert res.json()["key"] == "food"

    def test_added_category_gets_a_key_and_accepts_expenses(self):
        self._categories(self.owner)
        self._as(self.owner)
        created = self.client.post(
            CATEGORIES_URL, {"label": "هوايات"}, format="json")
        assert created.status_code == 201, created.content
        key = created.json()["key"]
        assert key and key not in ("food", "other")
        assert len(key) <= 20

        expense = self._expense(key, title="أدوات رسم")
        assert expense["category_label"] == "هوايات"

    def test_unknown_category_key_is_refused(self):
        self._as(self.owner)
        res = self.client.post(
            URL,
            {"date": "2026-07-05", "title": "مجهول", "category": "nope",
             "amount": "5", "is_paid": True},
            format="json",
        )
        assert res.status_code == 400, res.content

    def test_used_category_is_not_deleted_but_unused_is(self):
        rows = self._categories(self.owner)
        food = next(r for r in rows if r["key"] == "food")
        health = next(r for r in rows if r["key"] == "health")
        self._as(self.owner)
        self._expense("food")

        assert self.client.delete(f"{CATEGORIES_URL}{food['id']}/").status_code == 400
        assert self.client.delete(f"{CATEGORIES_URL}{health['id']}/").status_code == 204

    def test_catalogs_are_isolated_per_user(self):
        food = next(r for r in self._categories(self.owner) if r["key"] == "food")
        self._as(self.owner)
        self.client.patch(
            f"{CATEGORIES_URL}{food['id']}/", {"label": "أكل وشرب"}, format="json")

        others = self._categories(self.other)
        assert dict((r["key"], r["label"]) for r in others)["food"] == "طعام وشراب"
        self._as(self.other)
        assert self.client.patch(
            f"{CATEGORIES_URL}{food['id']}/", {"label": "تخريب"}, format="json"
        ).status_code == 404
