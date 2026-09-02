"""ISSUE #52 — مكتب المحاسبة: الدفتر المُدار، حصّة الخطة، والعزل.

الملاحظة على الأثر — صفوف `Tenant` الفعلية (`managed_by`)، وكود الاستجابة على
`X-Tenant-Id`/بلا ترويسة، وقائمة `my-companies` — لا على استدعاء `create_company`
مباشرة ولا على شكل `TenantViewSet.get_queryset` الداخلي.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.plans import invalidate_limit_cache
from tenants.models import Tenant, UserCompanyMembership

COMPANIES_URL = "/api/tenants/companies/"


def _managed_books_url(office_id):
    return f"{COMPANIES_URL}{office_id}/managed-books/"


class ManagedBookQuotaApiTest(APITestCase):
    """معيار القبول: مكتبٌ على Basic يفتح 3 دفاتر وينكسر عند الرابع."""

    @classmethod
    def setUpTestData(cls):
        cls.office = Tenant.objects.create(
            CompanyName="مكتب أساسي", SubscriptionPlan="Basic", Status="Active",
        )
        cls.manager = User.objects.create_user(username="office-mgr", password="x")
        UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.office, role="manager",
        )

    def setUp(self):
        invalidate_limit_cache(self.office.pk)
        self.client.force_authenticate(user=self.manager)

    def test_basic_office_opens_three_books_and_breaks_on_the_fourth(self):
        for i in range(3):
            res = self.client.post(
                _managed_books_url(self.office.pk),
                {"CompanyName": f"عميل {i + 1}"}, format="json",
            )
            self.assertEqual(res.status_code, 201, res.content)

        blocked = self.client.post(
            _managed_books_url(self.office.pk),
            {"CompanyName": "عميل رابع"}, format="json",
        )
        self.assertEqual(blocked.status_code, 400, blocked.content)
        self.assertIn("plan_limit", blocked.data)
        self.assertEqual(Tenant.objects.filter(managed_by=self.office).count(), 3)

    def test_created_book_is_flagged_managed_and_owned_by_the_office(self):
        res = self.client.post(
            _managed_books_url(self.office.pk), {"CompanyName": "عميل"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        book = Tenant.objects.get(pk=res.json()["TenantID"])
        self.assertEqual(book.managed_by_id, self.office.pk)
        self.assertEqual(res.json()["managed_by"], self.office.pk)


class ManagedBookNotInMyCompaniesApiTest(APITestCase):
    """معيار القبول: الدفاتر المُدارة لا تظهر في my-companies العادية."""

    @classmethod
    def setUpTestData(cls):
        cls.office = Tenant.objects.create(
            CompanyName="مكتب my-companies", SubscriptionPlan="Pro", Status="Active",
        )
        cls.manager = User.objects.create_user(username="mc-mgr", password="x")
        UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.office, role="manager",
        )

    def setUp(self):
        invalidate_limit_cache(self.office.pk)
        self.client.force_authenticate(user=self.manager)

    def test_managed_book_is_absent_from_my_companies_even_with_a_membership_row(self):
        created = self.client.post(
            _managed_books_url(self.office.pk), {"CompanyName": "عميل مُدار"}, format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        book_id = created.json()["TenantID"]
        # المدير نفسه صاحب عضوية صريحة على الدفتر (أنشأه) — الاستثناء بحسب
        # نوع الشركة (managed_by) لا بحسب وجود العضوية من عدمه.
        self.assertTrue(
            UserCompanyMembership.objects.filter(user=self.manager, tenant_id=book_id).exists()
        )

        res = self.client.get(f"{COMPANIES_URL}my-companies/")
        self.assertEqual(res.status_code, 200, res.content)
        ids = {row["tenant"]["TenantID"] for row in res.json()}
        self.assertNotIn(book_id, ids)
        self.assertIn(self.office.pk, ids)


class ManagedBookIsolationApiTest(APITestCase):
    """معياران: موظفٌ غير مُسند ← 404 لا 403، ومستخدمٌ من مكتبٍ آخر لا يرى الدفتر."""

    @classmethod
    def setUpTestData(cls):
        cls.office = Tenant.objects.create(
            CompanyName="مكتب العزل", SubscriptionPlan="Pro", Status="Active",
        )
        cls.manager = User.objects.create_user(username="iso-mgr", password="x")
        UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.office, role="manager",
        )
        cls.co_manager = User.objects.create_user(username="iso-co-mgr", password="x")
        UserCompanyMembership.objects.create(
            user=cls.co_manager, tenant=cls.office, role="manager",
        )
        cls.unassigned_staff = User.objects.create_user(username="iso-staff", password="x")
        UserCompanyMembership.objects.create(
            user=cls.unassigned_staff, tenant=cls.office, role="staff",
        )
        cls.other_office = Tenant.objects.create(
            CompanyName="مكتب آخر", SubscriptionPlan="Pro", Status="Active",
        )
        cls.other_manager = User.objects.create_user(username="other-mgr", password="x")
        UserCompanyMembership.objects.create(
            user=cls.other_manager, tenant=cls.other_office, role="manager",
        )

    def setUp(self):
        invalidate_limit_cache(self.office.pk)
        invalidate_limit_cache(self.other_office.pk)

    def _create_book(self):
        self.client.force_authenticate(user=self.manager)
        res = self.client.post(
            _managed_books_url(self.office.pk), {"CompanyName": "دفتر العزل"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()["TenantID"]

    def test_co_manager_sees_the_book_without_a_dedicated_membership(self):
        """قرار 7: مدير المكتب يرى كل الدفاتر — لا عضوية صريحة لكل واحد."""
        book_id = self._create_book()
        self.assertFalse(
            UserCompanyMembership.objects.filter(
                user=self.co_manager, tenant_id=book_id,
            ).exists()
        )
        self.client.force_authenticate(user=self.co_manager)
        res = self.client.get(f"{COMPANIES_URL}{book_id}/")
        self.assertEqual(res.status_code, 200, res.content)

    def test_unassigned_staff_gets_404_not_403(self):
        book_id = self._create_book()
        self.client.force_authenticate(user=self.unassigned_staff)
        res = self.client.get(f"{COMPANIES_URL}{book_id}/")
        self.assertEqual(res.status_code, 404, res.content)

    def test_explicitly_assigned_staff_gets_access(self):
        book_id = self._create_book()
        UserCompanyMembership.objects.create(
            user=self.unassigned_staff, tenant_id=book_id, role="staff",
        )
        self.client.force_authenticate(user=self.unassigned_staff)
        res = self.client.get(f"{COMPANIES_URL}{book_id}/")
        self.assertEqual(res.status_code, 200, res.content)

    def test_user_from_another_office_cannot_see_the_book_at_all(self):
        """اختبار تسريب: مستخدمٌ من مكتبٍ آخر — 404 لا كشف أي أثر للدفتر."""
        book_id = self._create_book()
        self.client.force_authenticate(user=self.other_manager)
        res = self.client.get(f"{COMPANIES_URL}{book_id}/")
        self.assertEqual(res.status_code, 404, res.content)

    def test_staff_of_another_office_cannot_open_via_managed_books_action_either(self):
        book_id = self._create_book()
        self.client.force_authenticate(user=self.other_manager)
        res = self.client.get(_managed_books_url(book_id))
        self.assertEqual(res.status_code, 404, res.content)


class ManagedBookRealDoorTest(APITestCase):
    """الرؤية في `TenantViewSet` ليست الباب الذي يُفتح منه الدفتر.

    كل نداء عملٍ داخل دفترٍ يمرّ بـ`X-Tenant-Id` ⇒ `core/tenant_utils.py`
    (`get_tenant` → `_validate_user_tenant_access`)، وهي تشترط صفّ عضوية.
    فحارسٌ يمنح الرؤية في `get_queryset` وحده يُنتج مديراً يرى دفتراً لا
    يستطيع فتحه. هذه الاختبارات تطرق الباب الفعلي لا قائمة الشركات.
    """

    @classmethod
    def setUpTestData(cls):
        cls.office = Tenant.objects.create(
            CompanyName="مكتب الباب الفعلي", SubscriptionPlan="Pro", Status="Active",
        )
        cls.manager = User.objects.create_user(username="door-mgr", password="x")
        cls.co_manager = User.objects.create_user(username="door-co-mgr", password="x")
        cls.staff = User.objects.create_user(username="door-staff", password="x")
        for user, role in ((cls.manager, "manager"), (cls.co_manager, "manager"),
                           (cls.staff, "staff")):
            UserCompanyMembership.objects.create(user=user, tenant=cls.office, role=role)
        cls.outsider_office = Tenant.objects.create(
            CompanyName="مكتب غريب", SubscriptionPlan="Pro", Status="Active",
        )
        cls.outsider = User.objects.create_user(username="door-outsider", password="x")
        UserCompanyMembership.objects.create(
            user=cls.outsider, tenant=cls.outsider_office, role="manager",
        )

    def setUp(self):
        invalidate_limit_cache(self.office.pk)
        self.client.force_authenticate(user=self.manager)
        res = self.client.post(
            _managed_books_url(self.office.pk), {"CompanyName": "دفتر الباب"}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.book_id = res.json()["TenantID"]

    def _work_inside_book(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get(
            "/api/accounting/accounts/", HTTP_X_TENANT_ID=str(self.book_id))

    def test_co_manager_can_actually_work_inside_the_book(self):
        self.assertFalse(
            UserCompanyMembership.objects.filter(
                user=self.co_manager, tenant_id=self.book_id).exists())
        self.assertEqual(self._work_inside_book(self.co_manager).status_code, 200)

    def test_unassigned_staff_cannot_work_inside_the_book(self):
        self.assertNotEqual(self._work_inside_book(self.staff).status_code, 200)

    def test_outsider_office_manager_cannot_work_inside_the_book(self):
        self.assertNotEqual(self._work_inside_book(self.outsider).status_code, 200)


class ManagedBookSubscriptionFollowsOfficeTest(APITestCase):
    """الدفتر المُدار لا يشترك — مكتبه هو المشترك.

    `create_company` تبدأ كل شركة تجريبيةً بأربعة عشر يوماً، فدفترٌ يرث ذلك
    يصير للقراءة فقط بعد أسبوعين — أي أن مكتباً مشترِكاً ودافعاً يعجز عن
    الكتابة في دفاتر عملائه.
    """

    @classmethod
    def setUpTestData(cls):
        cls.office = Tenant.objects.create(
            CompanyName="مكتب دائم", SubscriptionPlan="Pro", Status="Active",
            subscription_ends_at=None,  # اشتراك بلا تاريخ انتهاء
        )
        # شركةٌ ثانية عمداً: بشركةٍ واحدة في القاعدة يحلّ `get_tenant` الشركة
        # تلقائياً من كاشٍ على مستوى العملية يتسرّب بين الاختبارات.
        Tenant.objects.create(
            CompanyName="شركة أخرى", SubscriptionPlan="Pro", Status="Active")
        cls.manager = User.objects.create_user(username="sub-mgr", password="x")
        UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.office, role="manager")

    def setUp(self):
        invalidate_limit_cache(self.office.pk)
        self.client.force_authenticate(user=self.manager)
        self.hdr = {"HTTP_X_TENANT_ID": str(self.office.pk)}

    def _open_book(self, name):
        res = self.client.post(
            _managed_books_url(self.office.pk), {"CompanyName": name},
            format="json", **self.hdr)
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()["TenantID"]

    def _book_card(self, book_id):
        res = self.client.get(f"{COMPANIES_URL}{book_id}/", **self.hdr)
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_book_of_a_permanent_office_never_expires(self):
        """بلا هذا يرث الدفتر تجربة أربعة عشر يوماً ويقفل على مكتبٍ دائم."""
        card = self._book_card(self._open_book("دفتر دائم"))
        self.assertIsNone(card["subscription_days_left"])
        self.assertFalse(card["subscription_expired"])

    def test_book_expires_with_its_office_not_on_its_own_clock(self):
        from datetime import timedelta

        from django.utils import timezone

        book_id = self._open_book("دفتر تابع")
        self.office.subscription_ends_at = timezone.localdate() - timedelta(days=1)
        self.office.save(update_fields=["subscription_ends_at"])
        self.assertTrue(self._book_card(book_id)["subscription_expired"])
