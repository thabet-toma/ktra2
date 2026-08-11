from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, override_settings
from rest_framework.test import APITestCase

from tenants.models import Tenant, UserCompanyMembership


class PlatformAdminApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="platform-root", email="root@example.com", password="x",
        )
        cls.company_manager = User.objects.create_user(
            username="company-manager", password="x",
        )
        cls.configured_admin = User.objects.create_user(
            username="configured-admin", email="platform@example.com", password="x",
        )
        cls.active = Tenant.objects.create(
            CompanyName="شركة فعالة", SubscriptionPlan="Pro", Status="Active",
        )
        cls.trial = Tenant.objects.create(
            CompanyName="شركة تجريبية", SubscriptionPlan="Basic", Status="Trial",
        )
        UserCompanyMembership.objects.create(
            user=cls.company_manager, tenant=cls.active, role="manager",
        )

    def test_company_manager_cannot_access_platform_dashboard_or_notes(self):
        self.client.force_authenticate(self.company_manager)

        dashboard = self.client.get("/api/platform/dashboard/")
        notes = self.client.get("/api/platform/development-notes/")

        self.assertEqual(dashboard.status_code, 403)
        self.assertEqual(notes.status_code, 403)

    def test_superuser_dashboard_is_global_and_ignores_tenant_header(self):
        self.client.force_authenticate(self.superuser)

        response = self.client.get(
            "/api/platform/dashboard/", HTTP_X_TENANT_ID=str(self.active.TenantID),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["companies"]["total"], 2)
        self.assertEqual(response.data["companies"]["active"], 1)
        self.assertEqual(response.data["companies"]["trial"], 1)
        self.assertEqual(response.data["memberships"], 1)
        self.assertEqual(
            {row["name"] for row in response.data["company_rows"]},
            {"شركة فعالة", "شركة تجريبية"},
        )

    @override_settings(SUPER_ADMIN_EMAILS=["platform@example.com"])
    def test_configured_super_admin_email_uses_the_same_platform_guard(self):
        self.client.force_authenticate(self.configured_admin)
        response = self.client.get("/api/platform/dashboard/")
        self.assertEqual(response.status_code, 200, response.content)

    def test_development_notes_crud_stamps_the_authenticated_super_admin(self):
        self.client.force_authenticate(self.superuser)
        created = self.client.post(
            "/api/platform/development-notes/",
            {
                "title": "تحسين شاشة العروض",
                "description": "إضافة صورة معاينة قرب رقم المستند",
                "status": "todo",
                "priority": "high",
                "created_by": self.company_manager.id,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data["created_by"], self.superuser.id)
        self.assertNotIn("assignee", created.data)
        # `position` غادر العقد كلياً: الترتيب صار بـ`created_at` وحده، وإبقاء
        # حقلٍ يوحي بترتيب يدوي لا وجود له هو ما ولّد عشوائية مكان الملاحظة.
        self.assertNotIn("position", created.data)
        note_id = created.data["id"]

        updated = self.client.patch(
            f"/api/platform/development-notes/{note_id}/",
            {"status": "in_progress", "updated_by": self.company_manager.id},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.data["status"], "in_progress")
        self.assertEqual(updated.data["updated_by"], self.superuser.id)

        listed = self.client.get("/api/platform/development-notes/")
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual([row["id"] for row in listed.data], [note_id])

        deleted = self.client.delete(f"/api/platform/development-notes/{note_id}/")
        self.assertEqual(deleted.status_code, 204, deleted.content)

    def test_company_manager_cannot_list_or_grant_super_admin(self):
        self.client.force_authenticate(self.company_manager)
        listed = self.client.get("/api/platform/super-admins/")
        granted = self.client.post(
            "/api/platform/super-admins/",
            {"identifier": "company-manager"}, format="json",
        )
        self.assertEqual(listed.status_code, 403)
        self.assertEqual(granted.status_code, 403)
        self.company_manager.refresh_from_db()
        self.assertFalse(self.company_manager.is_superuser)

    def test_super_admin_grants_and_revokes_another_super_admin(self):
        self.client.force_authenticate(self.superuser)

        granted = self.client.post(
            "/api/platform/super-admins/",
            {"identifier": "company-manager"}, format="json",
        )
        self.assertEqual(granted.status_code, 201, granted.content)
        self.assertEqual(granted.data["username"], "company-manager")
        self.assertTrue(granted.data["removable"])
        self.company_manager.refresh_from_db()
        self.assertTrue(self.company_manager.is_superuser)

        # المرقّى الجديد يصل لوحة المنصة فعلاً — لا علم بلا وصول.
        self.client.force_authenticate(self.company_manager)
        self.assertEqual(self.client.get("/api/platform/dashboard/").status_code, 200)

        self.client.force_authenticate(self.superuser)
        listed = self.client.get("/api/platform/super-admins/")
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertIn("company-manager", [row["username"] for row in listed.data])

        revoked = self.client.delete(
            f"/api/platform/super-admins/{self.company_manager.pk}/")
        self.assertEqual(revoked.status_code, 204, revoked.content)
        self.company_manager.refresh_from_db()
        self.assertFalse(self.company_manager.is_superuser)

    def test_grant_rejects_unknown_identifier_and_existing_super_admin(self):
        self.client.force_authenticate(self.superuser)
        unknown = self.client.post(
            "/api/platform/super-admins/", {"identifier": "لا-أحد"}, format="json")
        already = self.client.post(
            "/api/platform/super-admins/", {"identifier": "platform-root"}, format="json")
        empty = self.client.post("/api/platform/super-admins/", {}, format="json")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(already.status_code, 400)
        self.assertEqual(empty.status_code, 400)

    def test_grant_accepts_email_as_identifier(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.post(
            "/api/platform/super-admins/",
            {"identifier": "platform@example.com"}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.configured_admin.refresh_from_db()
        self.assertTrue(self.configured_admin.is_superuser)

    def test_revoke_refuses_self_and_settings_configured_admin(self):
        self.client.force_authenticate(self.superuser)
        myself = self.client.delete(f"/api/platform/super-admins/{self.superuser.pk}/")
        self.assertEqual(myself.status_code, 400)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_superuser)

        self.configured_admin.is_superuser = True
        self.configured_admin.save(update_fields=["is_superuser"])
        with self.settings(SUPER_ADMIN_EMAILS=["platform@example.com"]):
            blocked = self.client.delete(
                f"/api/platform/super-admins/{self.configured_admin.pk}/")
        self.assertEqual(blocked.status_code, 400)
        self.configured_admin.refresh_from_db()
        self.assertTrue(self.configured_admin.is_superuser)

    @override_settings(SUPER_ADMIN_EMAILS=["platform@example.com"])
    def test_list_includes_settings_configured_admin_as_unremovable(self):
        self.client.force_authenticate(self.superuser)
        rows = {row["username"]: row for row in self.client.get(
            "/api/platform/super-admins/").data}
        self.assertEqual(rows["configured-admin"]["source"], "settings")
        self.assertFalse(rows["configured-admin"]["removable"])
        self.assertEqual(rows["platform-root"]["source"], "flag")

    def test_platform_company_endpoints_are_closed_to_a_company_manager(self):
        self.client.force_authenticate(self.company_manager)
        detail = self.client.get(f"/api/platform/companies/{self.active.pk}/")
        patched = self.client.patch(
            f"/api/platform/companies/{self.active.pk}/", {"status": "Suspended"}, format="json")
        members = self.client.get(f"/api/platform/companies/{self.active.pk}/members/")
        self.assertEqual(detail.status_code, 403)
        self.assertEqual(patched.status_code, 403)
        self.assertEqual(members.status_code, 403)

    def test_development_note_rejects_unknown_status_and_priority(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.post(
            "/api/platform/development-notes/",
            {
                "title": "قيمة غير صالحة",
                "description": "اختبار تحقق الحدود",
                "status": "hidden",
                "priority": "critical-secret",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.data)
        self.assertIn("priority", response.data)

    def _create_note(self, title, note_status, priority="medium"):
        response = self.client.post(
            "/api/platform/development-notes/",
            {"title": title, "status": note_status, "priority": priority},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.data["id"]

    def test_high_priority_note_precedes_an_older_low_priority_one(self):
        """الأولوية تسبق التاريخ داخل المجموعة غير المكتملة.

        الأقدم أولاً وحده كان يدفن ملاحظةً عاليةَ الأولوية خلف ملاحظات
        منخفضة سبقتها بالتاريخ — فصار المفتاح (المكتملة أخيراً ← الأولوية
        ← `created_at` ← `id`)، و`created_at` يبقى المرساة الثابتة داخل
        الأولوية الواحدة (لا `updated_at`).
        """
        self.client.force_authenticate(self.superuser)
        old_low = self._create_note("قديمة منخفضة", "todo", "low")
        old_medium = self._create_note("قديمة متوسطة", "todo", "medium")
        new_high = self._create_note("جديدة عالية", "todo", "high")
        older_high = self._create_note("أقدم عالية", "todo", "high")
        done_high = self._create_note("مكتملة عالية", "done", "high")

        listed = self.client.get("/api/platform/development-notes/")

        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(
            [row["id"] for row in listed.data],
            [new_high, older_high, old_medium, old_low, done_high],
        )

    def test_completed_notes_sink_to_the_end_of_the_sheet(self):
        """المكتملة تُزاح لآخر القائمة مهما كان تاريخها."""
        self.client.force_authenticate(self.superuser)
        done = self._create_note("منجزة قديمة", "done")
        todo = self._create_note("قيد الانتظار", "todo")
        in_progress = self._create_note("قيد التنفيذ", "in_progress")

        listed = self.client.get("/api/platform/development-notes/")

        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual([row["id"] for row in listed.data], [todo, in_progress, done])

    def test_notes_are_listed_oldest_first(self):
        """أول ملاحظة هي الأقدم — لا ترتيب يدوي يقرّر مكانها.

        الواجهة كانت ترسل `position=0` لأول ملاحظة تُضاف في كل جلسة و
        `notes.length + 1` لما بعدها، فتقفز الأولى للأعلى وتنزل أخواتها —
        وهذا مصدر «مرة بيسجلها في الأعلى ومرة بحطها في النص». الحقل حُذف.
        """
        self.client.force_authenticate(self.superuser)
        oldest = self._create_note("الأقدم", "todo")
        middle = self._create_note("الأوسط", "todo")
        newest = self._create_note("الأحدث", "todo")

        listed = self.client.get("/api/platform/development-notes/")

        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual([row["id"] for row in listed.data], [oldest, middle, newest])

    def test_editing_an_old_note_keeps_it_in_place(self):
        """تعديل ملاحظة قديمة لا يقفز بها للأعلى — `-updated_at` غادر الترتيب."""
        self.client.force_authenticate(self.superuser)
        oldest = self._create_note("الأقدم", "todo")
        middle = self._create_note("الأوسط", "todo")
        newest = self._create_note("الأحدث", "todo")

        edited = self.client.patch(
            f"/api/platform/development-notes/{oldest}/",
            {"description": "تعديل لاحق"}, format="json",
        )
        listed = self.client.get("/api/platform/development-notes/")

        self.assertEqual(edited.status_code, 200, edited.content)
        self.assertEqual([row["id"] for row in listed.data], [oldest, middle, newest])

    def test_completed_at_is_stamped_on_done_and_cleared_when_reopened(self):
        """«متى أُنجزت» ختمٌ يتبع الانتقال — لا يتجدّد بحفظة ولا يبقى بعد الفتح."""
        self.client.force_authenticate(self.superuser)
        note_id = self._create_note("قابلة للإنجاز", "todo")
        url = f"/api/platform/development-notes/{note_id}/"

        self.assertIsNone(self.client.get(url).data["completed_at"])

        done = self.client.patch(url, {"status": "done"}, format="json")
        self.assertEqual(done.status_code, 200, done.content)
        stamp = done.data["completed_at"]
        self.assertIsNotNone(stamp)

        resaved = self.client.patch(
            url, {"description": "تفصيل لاحق"}, format="json")
        self.assertEqual(resaved.status_code, 200, resaved.content)
        self.assertEqual(resaved.data["completed_at"], stamp)

        reopened = self.client.patch(url, {"status": "todo"}, format="json")
        self.assertEqual(reopened.status_code, 200, reopened.content)
        self.assertIsNone(reopened.data["completed_at"])

    def test_note_created_already_done_carries_its_stamp(self):
        self.client.force_authenticate(self.superuser)
        created = self.client.post(
            "/api/platform/development-notes/",
            {"title": "أُنجزت قبل تسجيلها", "status": "done"},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertIsNotNone(created.data["completed_at"])

    def test_note_comments_round_trip_add_list_and_delete(self):
        self.client.force_authenticate(self.superuser)
        note_id = self._create_note("ملاحظة عليها نقاش", "todo")
        comments_url = f"/api/platform/development-notes/{note_id}/comments/"

        first = self.client.post(comments_url, {"body": "  أول ردّ  "}, format="json")
        second = self.client.post(comments_url, {"body": "ثاني ردّ"}, format="json")

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.data["body"], "أول ردّ")
        self.assertEqual(first.data["created_by"], self.superuser.id)
        self.assertEqual(first.data["created_by_name"], "platform-root")
        self.assertEqual(second.status_code, 201, second.content)

        listed = self.client.get("/api/platform/development-notes/")
        self.assertEqual(
            [row["body"] for row in listed.data[0]["comments"]],
            ["أول ردّ", "ثاني ردّ"],
        )

        deleted = self.client.delete(f"{comments_url}{first.data['id']}/")
        self.assertEqual(deleted.status_code, 204, deleted.content)
        remaining = self.client.get(f"/api/platform/development-notes/{note_id}/")
        self.assertEqual(
            [row["id"] for row in remaining.data["comments"]], [second.data["id"]])

    def test_comment_rejects_blank_body_and_a_foreign_comment_id(self):
        self.client.force_authenticate(self.superuser)
        note_id = self._create_note("ملاحظة أولى", "todo")
        other_id = self._create_note("ملاحظة ثانية", "todo")
        comment = self.client.post(
            f"/api/platform/development-notes/{other_id}/comments/",
            {"body": "ردّ على الثانية"}, format="json",
        )

        blank = self.client.post(
            f"/api/platform/development-notes/{note_id}/comments/",
            {"body": "   "}, format="json",
        )
        foreign = self.client.delete(
            f"/api/platform/development-notes/{note_id}/comments/"
            f"{comment.data['id']}/"
        )

        self.assertEqual(blank.status_code, 400, blank.content)
        self.assertIn("body", blank.data)
        # ردّ ملاحظةٍ أخرى لا يُحذف من مسار هذه الملاحظة — الرقم وحده لا يكفي.
        self.assertEqual(foreign.status_code, 404, foreign.content)
        self.assertEqual(
            self.client.get(f"/api/platform/development-notes/{other_id}/")
            .data["comments"][0]["id"],
            comment.data["id"],
        )

    def test_company_manager_cannot_add_or_delete_note_comments(self):
        self.client.force_authenticate(self.superuser)
        note_id = self._create_note("ملاحظة محروسة", "todo")
        comment = self.client.post(
            f"/api/platform/development-notes/{note_id}/comments/",
            {"body": "ردّ سوبر أدمن"}, format="json",
        )

        self.client.force_authenticate(self.company_manager)
        added = self.client.post(
            f"/api/platform/development-notes/{note_id}/comments/",
            {"body": "ردّ متطفّل"}, format="json",
        )
        deleted = self.client.delete(
            f"/api/platform/development-notes/{note_id}/comments/"
            f"{comment.data['id']}/"
        )

        self.assertEqual(added.status_code, 403, added.content)
        self.assertEqual(deleted.status_code, 403, deleted.content)

    def test_note_list_query_count_does_not_grow_with_notes_or_comments(self):
        """الردود تُجلَب بـ`prefetch` — لا استعلام لكل ملاحظة (N+1)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.client.force_authenticate(self.superuser)
        note_id = self._create_note("ملاحظة وحيدة", "todo")
        self.client.post(
            f"/api/platform/development-notes/{note_id}/comments/",
            {"body": "ردّ"}, format="json",
        )

        with CaptureQueriesContext(connection) as one_note:
            self.client.get("/api/platform/development-notes/")

        for index in range(4):
            extra = self._create_note(f"ملاحظة {index}", "todo")
            self.client.post(
                f"/api/platform/development-notes/{extra}/comments/",
                {"body": f"ردّ {index}"}, format="json",
            )

        with CaptureQueriesContext(connection) as five_notes:
            listed = self.client.get("/api/platform/development-notes/")

        self.assertEqual(len(listed.data), 5)
        self.assertEqual(len(five_notes), len(one_note))

    def test_note_images_round_trip_and_drop_extra_keys(self):
        self.client.force_authenticate(self.superuser)
        created = self.client.post(
            "/api/platform/development-notes/",
            {
                "title": "ملاحظة بصور توضيحية",
                "images": [
                    {
                        "url": "https://res.cloudinary.com/demo/image/upload/v1/a.png",
                        "caption": "  قبل التعديل  ",
                        "secret": "يُهمَل",
                    },
                    {"url": "https://res.cloudinary.com/demo/image/upload/v1/b.png"},
                ],
            },
            format="json",
        )

        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data["images"], [
            {
                "url": "https://res.cloudinary.com/demo/image/upload/v1/a.png",
                "caption": "قبل التعديل",
            },
            {"url": "https://res.cloudinary.com/demo/image/upload/v1/b.png", "caption": ""},
        ])

    def test_note_images_reject_non_list_and_non_http_url(self):
        self.client.force_authenticate(self.superuser)
        not_a_list = self.client.post(
            "/api/platform/development-notes/",
            {"title": "شكل خاطئ", "images": {"url": "https://example.com/a.png"}},
            format="json",
        )
        bad_scheme = self.client.post(
            "/api/platform/development-notes/",
            {"title": "رابط خاطئ", "images": [{"url": "javascript:alert(1)"}]},
            format="json",
        )

        self.assertEqual(not_a_list.status_code, 400, not_a_list.content)
        self.assertIn("images", not_a_list.data)
        self.assertEqual(bad_scheme.status_code, 400, bad_scheme.content)
        self.assertIn("images", bad_scheme.data)


class PlatformCompanyControlTest(APITestCase):
    """لوحة تحكم السوبر أدمن: يدير أي شركة وأعضاءها دون أن يكون عضواً فيها."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="platform-root", email="root@example.com", password="x",
        )
        cls.manager = User.objects.create_user(username="mgr", email="mgr@example.com", password="x")
        cls.staff = User.objects.create_user(username="stf", email="stf@example.com", password="x")
        cls.outsider = User.objects.create_user(username="out", email="out@example.com", password="x")
        cls.company = Tenant.objects.create(
            CompanyName="شركة العميل", SubscriptionPlan="Basic", Status="Trial",
        )
        cls.mgr_membership = UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.company, role="manager",
        )
        cls.staff_membership = UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.company, role="staff",
        )

    def setUp(self):
        self.client.force_authenticate(self.superuser)

    def _member_url(self, membership):
        return f"/api/platform/companies/{self.company.pk}/members/{membership.pk}/"

    def test_detail_returns_company_with_its_members(self):
        response = self.client.get(f"/api/platform/companies/{self.company.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["name"], "شركة العميل")
        self.assertEqual(
            {row["username"] for row in response.data["members"]}, {"mgr", "stf"})
        self.assertTrue(all(row["is_active"] for row in response.data["members"]))

    def test_super_admin_edits_name_plan_status_and_import(self):
        response = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/",
            {"name": "شركة النور", "plan": "Enterprise", "status": "Suspended",
             "import_enabled": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.company.refresh_from_db()
        self.assertEqual(self.company.CompanyName, "شركة النور")
        self.assertEqual(self.company.SubscriptionPlan, "Enterprise")
        self.assertEqual(self.company.Status, "Suspended")
        self.assertTrue(self.company.import_enabled)

    def test_super_admin_assigns_exactly_one_example_company_with_staff_access_for_all(self):
        other = Tenant.objects.create(
            CompanyName="شركة المثال الثانية", SubscriptionPlan="Basic", Status="Active",
        )

        assigned = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/",
            {"is_example": True},
            format="json",
        )

        self.assertEqual(assigned.status_code, 200, assigned.content)
        self.assertTrue(assigned.data["is_example"])
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_example)
        for user in (self.superuser, self.outsider):
            membership = UserCompanyMembership.objects.get(user=user, tenant=self.company)
            self.assertEqual(membership.role, "staff")
            self.assertTrue(membership.is_example_access)
        self.mgr_membership.refresh_from_db()
        self.assertFalse(self.mgr_membership.is_example_access)

        moved = self.client.patch(
            f"/api/platform/companies/{other.pk}/",
            {"is_example": True},
            format="json",
        )

        self.assertEqual(moved.status_code, 200, moved.content)
        self.company.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(self.company.is_example)
        self.assertTrue(other.is_example)
        self.assertFalse(UserCompanyMembership.objects.filter(
            user=self.outsider, tenant=self.company,
        ).exists())
        self.assertTrue(UserCompanyMembership.objects.filter(
            user=self.outsider, tenant=other, role="staff", is_example_access=True,
        ).exists())
        self.assertTrue(UserCompanyMembership.objects.filter(
            pk=self.mgr_membership.pk,
        ).exists())

        dashboard = self.client.get("/api/platform/dashboard/")
        rows = {row["id"]: row for row in dashboard.data["company_rows"]}
        self.assertFalse(rows[self.company.pk]["is_example"])
        self.assertTrue(rows[other.pk]["is_example"])

        cleared = self.client.patch(
            f"/api/platform/companies/{other.pk}/",
            {"is_example": False},
            format="json",
        )
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertFalse(cleared.data["is_example"])
        self.assertFalse(Tenant.objects.filter(is_example=True).exists())
        self.assertFalse(UserCompanyMembership.objects.filter(
            is_example_access=True,
        ).exists())
        self.assertTrue(UserCompanyMembership.objects.filter(
            pk=self.mgr_membership.pk,
        ).exists())

    def test_edit_rejects_unknown_status_plan_and_empty_name(self):
        bad_status = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/", {"status": "Deleted"}, format="json")
        bad_plan = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/", {"plan": "Free"}, format="json")
        empty_name = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/", {"name": "  "}, format="json")
        self.assertEqual(bad_status.status_code, 400)
        self.assertEqual(bad_plan.status_code, 400)
        self.assertEqual(empty_name.status_code, 400)
        self.company.refresh_from_db()
        self.assertEqual(self.company.Status, "Trial")

    def test_super_admin_adds_changes_role_and_removes_a_member(self):
        added = self.client.post(
            f"/api/platform/companies/{self.company.pk}/members/",
            {"identifier": "out@example.com", "role": "accountant"}, format="json",
        )
        self.assertEqual(added.status_code, 201, added.content)
        membership = UserCompanyMembership.objects.get(user=self.outsider, tenant=self.company)
        self.assertEqual(membership.role, "accountant")

        changed = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/members/{membership.pk}/",
            {"role": "sales"}, format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        membership.refresh_from_db()
        self.assertEqual(membership.role, "sales")

        removed = self.client.delete(
            f"/api/platform/companies/{self.company.pk}/members/{membership.pk}/")
        self.assertEqual(removed.status_code, 204, removed.content)
        self.assertFalse(UserCompanyMembership.objects.filter(pk=membership.pk).exists())

    def test_add_member_rejects_unknown_user_and_duplicate(self):
        unknown = self.client.post(
            f"/api/platform/companies/{self.company.pk}/members/",
            {"identifier": "لا-أحد", "role": "staff"}, format="json")
        duplicate = self.client.post(
            f"/api/platform/companies/{self.company.pk}/members/",
            {"identifier": "stf", "role": "staff"}, format="json")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(duplicate.status_code, 400)

    def test_last_manager_is_protected_from_demotion_and_removal(self):
        demoted = self.client.patch(
            self._member_url(self.mgr_membership), {"role": "staff"}, format="json")
        removed = self.client.delete(self._member_url(self.mgr_membership))
        self.assertEqual(demoted.status_code, 400)
        self.assertEqual(removed.status_code, 400)
        self.mgr_membership.refresh_from_db()
        self.assertEqual(self.mgr_membership.role, "manager")

    def test_member_import_access_requires_the_company_to_be_enabled(self):
        blocked = self.client.patch(
            self._member_url(self.staff_membership), {"can_access_import": True}, format="json")
        self.assertEqual(blocked.status_code, 400)

        self.client.patch(
            f"/api/platform/companies/{self.company.pk}/",
            {"import_enabled": True}, format="json")
        granted = self.client.patch(
            self._member_url(self.staff_membership), {"can_access_import": True}, format="json")
        self.assertEqual(granted.status_code, 200, granted.content)
        self.staff_membership.refresh_from_db()
        self.assertTrue(self.staff_membership.can_access_import)

    def test_super_admin_suspends_and_restores_a_user_account(self):
        suspended = self.client.post(
            f"/api/platform/users/{self.staff.pk}/set-active/", {"is_active": False}, format="json")
        self.assertEqual(suspended.status_code, 200, suspended.content)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)

        restored = self.client.post(
            f"/api/platform/users/{self.staff.pk}/set-active/", {"is_active": True}, format="json")
        self.assertEqual(restored.status_code, 200, restored.content)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_super_admin_cannot_suspend_own_account(self):
        response = self.client.post(
            f"/api/platform/users/{self.superuser.pk}/set-active/",
            {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 400)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    @override_settings(SUPER_ADMIN_EMAILS=["mgr@example.com"])
    def test_settings_configured_super_admin_account_cannot_be_suspended(self):
        response = self.client.post(
            f"/api/platform/users/{self.manager.pk}/set-active/",
            {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 400)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_member_cannot_manage_members_through_the_platform_route(self):
        self.client.force_authenticate(self.manager)
        response = self.client.patch(
            self._member_url(self.staff_membership), {"role": "viewer"}, format="json")
        self.assertEqual(response.status_code, 403)


class SuspendedCompanyAccessTest(APITestCase):
    """إيقاف الشركة من لوحة المنصة يمنع أعضاءها فعلاً — لا حالة تزيينية."""

    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(username="member", password="x")
        cls.superuser = User.objects.create_superuser(
            username="root2", email="root2@example.com", password="x")
        cls.suspended = Tenant.objects.create(
            CompanyName="شركة موقوفة", SubscriptionPlan="Basic", Status="Suspended")
        cls.running = Tenant.objects.create(
            CompanyName="شركة عاملة", SubscriptionPlan="Basic", Status="Active")
        for tenant in (cls.suspended, cls.running):
            UserCompanyMembership.objects.create(user=cls.member, tenant=tenant, role="manager")

    def _request(self, user, tenant):
        request = RequestFactory().get("/api/anything/", HTTP_X_TENANT_ID=str(tenant.pk))
        request.user = user
        return request

    def test_member_is_blocked_from_a_suspended_company(self):
        from core.tenant_utils import get_tenant

        with self.assertRaises(PermissionDenied):
            get_tenant(self._request(self.member, self.suspended))

    def test_running_company_and_super_admin_are_unaffected(self):
        from core.tenant_utils import get_tenant

        self.assertEqual(
            get_tenant(self._request(self.member, self.running)).pk, self.running.pk)
        self.assertEqual(
            get_tenant(self._request(self.superuser, self.suspended)).pk, self.suspended.pk)
