"""الأدوار والصلاحيات والموظف المسؤول — #272.

**الأدوار الأربعة على الكتالوج القائم لا محرّكٍ موازياً:**
مالك = `manager` (كل شيء، ولا يُقفل بتجاوز) · مدير = `office_manager` (جديد،
يختفي بلا ترخيص الوحدة) · محاسب = `accountant` + `office.clients.write` وحده ·
قارئ = `viewer` (بلا كتابة).

**والإنفاذ خادمي:** دون `office.clients.all` تُقتصر كلُّ قائمةٍ ونقطةٍ تُرجع
زبوناً على `responsible=user` — والتفصيل المغلق **404 لا 403**. ودون
`office.amounts.view` كلُّ مبلغٍ في الردّ `null`، وكتابتُه 403.

**والموظف المسؤول** عضوٌ في شركة الزبون، يُسجَّل تحويله في سجلّ النشاط (من ← إلى).
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office.models import Contact, OfficeClient, TaxCard
from accounting_office.services import set_office_setting
from core.access import visible_role_labels
from core.models import ActivityLog, SupportAccessGrant
from core.modules import invalidate_module_cache
from tenants.models import Currency, MemberPermission, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
CLIENTS = f"{BASE}clients/"
CONTACTS = f"{BASE}contacts/"
SETTINGS = f"{BASE}settings/"

AMOUNT = Decimal("1500.00")


def ready_office(tenant):
    """يُكمل أول تشغيل — الإنشاء مرفوضٌ قبله (قرار #271)."""
    set_office_setting(tenant, "tax_system", "PS")
    set_office_setting(tenant, "office_size", "small")


def make_client(tenant, name, responsible=None, annual_sales=AMOUNT):
    """زبونٌ وبطاقته مباشرةً — بلا مرور النقاط، لبناء حالةٍ بعينها."""
    client = OfficeClient.objects.create(
        tenant=tenant, name=name, responsible=responsible,
    )
    TaxCard.objects.create(client=client, annual_sales=annual_sales)
    return client


class OfficeRolesTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.owner = User.objects.create_user(username="roles_owner", password="x")
        cls.tenant = create_company(
            "مكتب الأدوار", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant)

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            membership = UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role,
            )
            return user, membership

        cls.accountant_user, cls.accountant = member("roles_accountant", "accountant")
        cls.colleague_user, cls.colleague = member("roles_colleague", "accountant")
        cls.viewer_user, cls.viewer = member("roles_viewer", "viewer")
        cls.office_manager_user, cls.office_manager = member(
            "roles_office_manager", "office_manager",
        )

        cls.mine = make_client(cls.tenant, "زبون المحاسب", cls.accountant_user)
        cls.other = make_client(cls.tenant, "زبون الزميل", cls.colleague_user)
        cls.viewed = make_client(cls.tenant, "زبون القارئ", cls.viewer_user)

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def ids(self, response):
        return sorted(row["id"] for row in response.data)

    def detail(self, client_id, suffix=""):
        return self.client.get(f"{CLIENTS}{client_id}/{suffix}", **self.headers())


class VisibilityTest(OfficeRolesTestCase):
    def test_an_accountant_without_the_key_sees_only_their_own_clients(self):
        self.as_user(self.accountant_user)
        res = self.client.get(CLIENTS, **self.headers())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.ids(res), [self.mine.pk])

    def test_someone_elses_client_is_404_not_403_on_every_nested_point(self):
        """403 كان يقول «هذا موجودٌ لكن لا يخصّك» — و404 لا يقول شيئاً."""
        self.as_user(self.accountant_user)
        foreign = self.other.pk
        for path in (
            "", "tax-card/", "contacts/", "settings/", "reminders/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.detail(foreign, path).status_code, 404)
        self.assertEqual(
            self.client.post(
                f"{CLIENTS}{foreign}/end/", {}, format="json", **self.headers(),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"{CLIENTS}{foreign}/contacts/", {"contact": 1},
                format="json", **self.headers(),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"{CLIENTS}{foreign}/contacts/1/primary/", {},
                format="json", **self.headers(),
            ).status_code,
            404,
        )
        # كتابةُ إعداد الزبون: الصلاحيةُ أوّلاً (المحاسب يملكها) ثم `get_object`
        # فيحجبها الغياب — 404.
        self.assertEqual(
            self.client.put(
                f"{CLIENTS}{foreign}/settings/rest_days/", {"value": ["sat"]},
                format="json", **self.headers(),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(
                f"{CLIENTS}{foreign}/settings/rest_days/", **self.headers(),
            ).status_code,
            404,
        )
        # والتحويلُ استثناءٌ مقصود: صلاحيته (`office.clients.assign`) تُفحص
        # **قبل** `get_object`، فيأخذ المحاسب بلا مفتاحها 403 لأيّ معرّف —
        # وهو الصواب: رفضُ الفعل لا الكشفُ عن وجود الزبون.
        self.assertEqual(
            self.client.post(
                f"{CLIENTS}{foreign}/assign/", {"user": self.accountant_user.pk},
                format="json", **self.headers(),
            ).status_code,
            403,
        )

    def test_a_member_override_grants_the_key_and_shows_everything(self):
        MemberPermission.objects.create(
            membership=self.accountant, permission_key="office.clients.all", allowed=True,
        )
        self.as_user(self.accountant_user)
        res = self.client.get(CLIENTS, **self.headers())
        self.assertEqual(
            self.ids(res), sorted([self.mine.pk, self.other.pk, self.viewed.pk]),
        )

    def test_the_customizers_list_is_filtered_by_the_same_rule(self):
        """`settings/<key>/clients/` تُرجع زبائن — فتمرّ بـ`visible_clients`."""
        from accounting_office.services import set_client_setting

        set_client_setting(self.other, "rest_days", ["fri"])
        self.as_user(self.accountant_user)
        hidden = self.client.get(f"{SETTINGS}rest_days/clients/", **self.headers())
        self.assertEqual(hidden.data, [])

        set_client_setting(self.mine, "rest_days", ["sat"])
        mine = self.client.get(f"{SETTINGS}rest_days/clients/", **self.headers())
        self.assertEqual([row["id"] for row in mine.data], [self.mine.pk])

    def test_the_customization_count_counts_only_what_the_member_sees(self):
        """عدّادُ «مخصَّص عند N زبون» رقمٌ عن الزبائن — فيمرّ بالقاعدة نفسها.

        كان يُحسب على كل المكتب، فيقرأ عضوٌ بلا `office.clients.all` عددَ زبائن
        غيره، ويختلف العدد عن قائمة `settings/<key>/clients/` المفلترة تحته.
        """
        from accounting_office.services import set_client_setting

        set_client_setting(self.other, "rest_days", ["fri"])
        set_client_setting(self.mine, "rest_days", ["sat"])

        self.as_user(self.accountant_user)
        mine = self.client.get(SETTINGS, **self.headers())
        self.assertEqual(mine.status_code, 200)
        row = next(item for item in mine.data["settings"] if item["key"] == "rest_days")
        self.assertEqual(row["client_customization_count"], 1)

        self.as_user(self.owner)
        every = self.client.get(SETTINGS, **self.headers())
        row = next(item for item in every.data["settings"] if item["key"] == "rest_days")
        self.assertEqual(row["client_customization_count"], 2)


class ContactsVisibilityTest(OfficeRolesTestCase):
    """دفترُ الجهات كاملاً لعضوٍ مقيّد = أسماءُ وهواتفُ زبائن لا يراها."""

    def setUp(self):
        super().setUp()
        from accounting_office.models import ClientContact, Contact

        self.own_contact = Contact.objects.create(tenant=self.tenant, name="جهة زبوني")
        ClientContact.objects.create(client=self.mine, contact=self.own_contact)

        self.foreign_contact = Contact.objects.create(tenant=self.tenant, name="جهة الزميل")
        ClientContact.objects.create(client=self.other, contact=self.foreign_contact)

        self.free_contact = Contact.objects.create(tenant=self.tenant, name="جهة غير مربوطة")

    def names(self, response):
        return sorted(row["name"] for row in response.data)

    def test_the_list_hides_contacts_of_clients_the_member_cannot_see(self):
        self.as_user(self.accountant_user)
        res = self.client.get(CONTACTS, **self.headers())
        self.assertEqual(self.names(res), ["جهة زبوني", "جهة غير مربوطة"])

    def test_a_hidden_contact_is_404_on_detail_edit_and_delete(self):
        self.as_user(self.accountant_user)
        path = f"{CONTACTS}{self.foreign_contact.pk}/"
        self.assertEqual(self.client.get(path, **self.headers()).status_code, 404)
        self.assertEqual(
            self.client.patch(path, {"name": "مسروقة"}, format="json", **self.headers()).status_code,
            404,
        )
        self.assertEqual(self.client.delete(path, **self.headers()).status_code, 404)
        self.assertEqual(
            Contact.objects.get(pk=self.foreign_contact.pk).name, "جهة الزميل",
        )

    def test_an_unlinked_contact_stays_visible_for_the_picker(self):
        """بلا هذا لا يجد المنتقي جهةً جديدة أصلاً فيُنشئها مكرَّرة."""
        self.as_user(self.accountant_user)
        res = self.client.get(f"{CONTACTS}{self.free_contact.pk}/", **self.headers())
        self.assertEqual(res.status_code, 200)

    def test_the_owner_sees_every_contact(self):
        self.as_user(self.owner)
        res = self.client.get(CONTACTS, **self.headers())
        self.assertEqual(
            self.names(res), ["جهة الزميل", "جهة زبوني", "جهة غير مربوطة"],
        )


class AmountsTest(OfficeRolesTestCase):
    def test_the_amount_is_null_for_an_accountant_without_the_key(self):
        self.as_user(self.accountant_user)
        detail = self.detail(self.mine.pk)
        self.assertEqual(detail.status_code, 200)
        self.assertIsNone(detail.data["tax_card"]["annual_sales"])
        card = self.detail(self.mine.pk, "tax-card/")
        self.assertIsNone(card.data["annual_sales"])
        # والباقي يبقى كاملاً — الإخفاء على المبلغ وحده.
        self.assertEqual(card.data["tax_system"], "PS")

    def test_writing_an_amount_without_the_key_is_refused(self):
        self.as_user(self.accountant_user)
        res = self.client.patch(
            f"{CLIENTS}{self.mine.pk}/tax-card/", {"annual_sales": "99.00"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 403, res.content)
        nested = self.client.patch(
            f"{CLIENTS}{self.mine.pk}/",
            {"tax_card": {"annual_sales": "99.00"}},
            format="json", **self.headers(),
        )
        self.assertEqual(nested.status_code, 403, nested.content)
        self.assertEqual(
            TaxCard.objects.get(client_id=self.mine.pk).annual_sales, AMOUNT,
        )

    def test_saving_another_field_leaves_the_stored_amount_untouched(self):
        self.as_user(self.accountant_user)
        res = self.client.patch(
            f"{CLIENTS}{self.mine.pk}/tax-card/",
            {"entity_type": "company", "has_employees": True},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        stored = TaxCard.objects.get(client_id=self.mine.pk)
        self.assertEqual(stored.annual_sales, AMOUNT)
        self.assertEqual(stored.entity_type, "company")

    def test_the_owner_and_the_office_manager_see_the_amounts(self):
        for user in (self.owner, self.office_manager_user):
            with self.subTest(user=user.username):
                self.as_user(user)
                card = self.detail(self.mine.pk, "tax-card/")
                self.assertEqual(card.status_code, 200)
                self.assertEqual(Decimal(card.data["annual_sales"]), AMOUNT)
                detail = self.detail(self.mine.pk)
                self.assertEqual(
                    Decimal(detail.data["tax_card"]["annual_sales"]), AMOUNT,
                )


class OwnerAndManagerSeeEverythingTest(OfficeRolesTestCase):
    def test_the_owner_sees_all_clients(self):
        self.as_user(self.owner)
        res = self.client.get(CLIENTS, **self.headers())
        self.assertEqual(
            self.ids(res), sorted([self.mine.pk, self.other.pk, self.viewed.pk]),
        )

    def test_the_office_manager_sees_all_clients(self):
        self.as_user(self.office_manager_user)
        res = self.client.get(CLIENTS, **self.headers())
        self.assertEqual(
            self.ids(res), sorted([self.mine.pk, self.other.pk, self.viewed.pk]),
        )

    def test_the_office_manager_manages_the_office_settings(self):
        self.as_user(self.office_manager_user)
        res = self.client.put(
            f"{SETTINGS}rest_days/", {"value": ["sat"]}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_the_reader_cannot_write_anything_but_reads(self):
        self.as_user(self.viewer_user)
        self.assertEqual(self.client.get(CLIENTS, **self.headers()).status_code, 200)
        self.assertEqual(self.detail(self.viewed.pk).status_code, 200)
        self.assertEqual(self.detail(self.viewed.pk, "tax-card/").status_code, 200)

        writes = (
            ("post", CLIENTS, {"name": "زبون جديد"}),
            ("patch", f"{CLIENTS}{self.viewed.pk}/", {"name": "مسروق"}),
            ("patch", f"{CLIENTS}{self.viewed.pk}/tax-card/", {"entity_type": "company"}),
            ("post", f"{CLIENTS}{self.viewed.pk}/contacts/", {"contact": 1}),
            ("post", f"{CLIENTS}{self.viewed.pk}/end/", {}),
            ("post", CONTACTS, {"name": "جهة"}),
            ("put", f"{SETTINGS}rest_days/", {"value": ["sat"]}),
        )
        for method, path, payload in writes:
            with self.subTest(method=method, path=path):
                res = getattr(self.client, method)(
                    path, payload, format="json", **self.headers(),
                )
                self.assertEqual(res.status_code, 403, res.content)


class AssignmentTest(OfficeRolesTestCase):
    def assign(self, client_id, user_id):
        return self.client.post(
            f"{CLIENTS}{client_id}/assign/", {"user": user_id},
            format="json", **self.headers(),
        )

    def test_creating_a_client_makes_its_creator_responsible(self):
        self.as_user(self.accountant_user)
        res = self.client.post(
            CLIENTS, {"name": "زبون جديد"}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["responsible_id"], self.accountant_user.pk)
        self.assertEqual(
            OfficeClient.objects.get(pk=res.data["id"]).responsible_id,
            self.accountant_user.pk,
        )

    def test_a_non_member_creator_creates_a_client_without_a_responsible(self):
        """سوبر أدمن (أو جلسة دعم) يمرّ `require_write` ولا عضويّة له: لا يُسنَد إليه."""
        root = User.objects.create_superuser(
            username="roles_root", password="x", email="root@example.com",
        )
        self.assertFalse(
            UserCompanyMembership.objects.filter(user=root, tenant=self.tenant).exists(),
        )
        # سوبر أدمن بلا عضويّة لا يدخل الشركة إلا بإذن دعمٍ ساري (SA-2).
        SupportAccessGrant.objects.create(
            tenant=self.tenant, requested_by=root, reason="اختبار", requested_hours=24,
            requested_scope="full", status="active", scope="full",
            expires_at=timezone.now() + timedelta(hours=24),
        )
        self.as_user(root)
        res = self.client.post(
            CLIENTS, {"name": "زبون السوبر"}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertIsNone(res.data["responsible_id"])
        self.assertIsNone(OfficeClient.objects.get(pk=res.data["id"]).responsible_id)

    def test_an_explicit_non_member_responsible_is_still_rejected(self):
        from accounting_office import services

        outsider = User.objects.create_user(username="roles_outsider_create", password="x")
        with self.assertRaises(ValidationError):
            services.create_office_client(
                tenant=self.tenant, name="زبون", actor=self.owner, responsible=outsider,
            )

    def test_the_transfer_changes_the_owner_and_is_logged(self):
        self.as_user(self.owner)
        res = self.assign(self.mine.pk, self.colleague_user.pk)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["responsible_id"], self.colleague_user.pk)
        self.assertEqual(
            OfficeClient.objects.get(pk=self.mine.pk).responsible_id,
            self.colleague_user.pk,
        )

        event = ActivityLog.objects.filter(
            entity_type="office_client", entity_id=self.mine.pk,
        ).order_by("-id").first()
        self.assertIsNotNone(event)
        self.assertEqual(event.user_id, self.owner.pk)
        self.assertEqual(event.metadata["from"], self.accountant_user.pk)
        self.assertEqual(event.metadata["to"], self.colleague_user.pk)
        self.assertEqual(event.metadata["from_label"], "roles_accountant")

    def test_the_transfer_reports_the_row_it_relocks_not_a_stale_copy(self):
        """«من» في السجلّ هو المسؤول **المقروء تحت القفل** لا نسخةً قديمة.

        التحويلان المتزامنان على نسختين قديمتين كانا يُسجّلان مسؤولاً لم يعد
        مسؤولاً — والسجلُّ يقول «من ← إلى» فيكذب.
        """
        from accounting_office import services

        stale = OfficeClient.objects.get(pk=self.mine.pk)
        # تحويلٌ سبق هذا (وصل بين قراءة النسخة وكتابتها).
        OfficeClient.objects.filter(pk=self.mine.pk).update(
            responsible=self.colleague_user,
        )
        services.assign_office_client(
            stale, user=self.viewer_user, actor=self.owner,
        )
        event = ActivityLog.objects.filter(
            entity_type="office_client", entity_id=self.mine.pk,
        ).order_by("-id").first()
        self.assertEqual(event.metadata["from"], self.colleague_user.pk)
        self.assertEqual(event.metadata["to"], self.viewer_user.pk)

    def test_the_transfer_needs_its_own_key(self):
        """المحاسب يكتب الزبائن ولا يسندهم — مفتاحان لا واحد."""
        self.as_user(self.accountant_user)
        res = self.assign(self.mine.pk, self.colleague_user.pk)
        self.assertEqual(res.status_code, 403, res.content)
        self.assertEqual(
            OfficeClient.objects.get(pk=self.mine.pk).responsible_id,
            self.accountant_user.pk,
        )

    def test_the_office_manager_can_transfer(self):
        self.as_user(self.office_manager_user)
        self.assertEqual(self.assign(self.mine.pk, self.colleague_user.pk).status_code, 200)

    def test_a_user_outside_the_company_cannot_be_responsible(self):
        outsider = User.objects.create_user(username="roles_outsider", password="x")
        self.as_user(self.owner)
        res = self.assign(self.mine.pk, outsider.pk)
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(
            OfficeClient.objects.get(pk=self.mine.pk).responsible_id,
            self.accountant_user.pk,
        )

    def test_the_model_guard_covers_every_save_path(self):
        """`OfficeClient.save()` يغلق الطرق التي لا تمرّ بالخدمة.

        و`QuerySet.update()` لا يمرّ بـ`save` فلا يحرسه شيء — إصلاحٌ جماعيٌّ
        مباشر على الجدول يبقى مسؤوليةَ من يكتبه، والمقصودُ هنا مسارُ النموذج.
        """
        outsider = User.objects.create_user(username="roles_outsider_model", password="x")
        with self.assertRaises(ValueError):
            OfficeClient.objects.create(
                tenant=self.tenant, name="زبونٌ برمجة", responsible=outsider,
            )

        # موظّفٌ خرج من المكتب (حُذفت عضويّته) وبقيت زبائنه عليه: لا يُمنع
        # إنهاءُ زبونه ولا تعديلُه بالحارس.
        self.colleague.delete()
        self.as_user(self.owner)
        res = self.client.post(
            f"{CLIENTS}{self.other.pk}/end/", {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(OfficeClient.objects.get(pk=self.other.pk).status, "ended")


class OfficeManagerRoleTest(APITestCase):
    """دورٌ جديدُ على الكتالوج القائم — ويختفي مع وحدته."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.owner = User.objects.create_user(username="role_labels_owner", password="x")
        cls.office_tenant = create_company(
            "مكتب مرخّص", cls.owner, template="accounting_office",
        )
        cls.plain_tenant = create_company("شركة عامة", cls.owner)
        invalidate_module_cache(cls.office_tenant.pk)
        invalidate_module_cache(cls.plain_tenant.pk)

    def roles(self, tenant):
        return [role for role, _label in visible_role_labels(tenant)]

    def test_the_role_is_registered_with_its_label(self):
        self.assertIn("office_manager", self.roles(self.office_tenant))
        from core.access import ROLE_LABELS

        self.assertEqual(dict(ROLE_LABELS)["office_manager"], "مدير مكتب")

    def test_the_role_disappears_without_the_module_licence(self):
        self.assertNotIn("office_manager", self.roles(self.plain_tenant))

    def test_the_same_role_can_be_assigned_through_the_existing_endpoint(self):
        membership = UserCompanyMembership.objects.get(
            user=self.owner, tenant=self.office_tenant,
        )
        worker = User.objects.create_user(username="role_change_worker", password="x")
        worker_membership = UserCompanyMembership.objects.create(
            user=worker, tenant=self.office_tenant, role="staff",
        )
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            f"/api/tenants/companies/{self.office_tenant.pk}/members/change-role/",
            {"membership_id": worker_membership.pk, "role": "office_manager"},
            format="json", HTTP_X_TENANT_ID=str(self.office_tenant.pk),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            UserCompanyMembership.objects.get(pk=worker_membership.pk).role,
            "office_manager",
        )
        self.assertEqual(membership.role, "manager")

    def test_the_accountant_key_set_is_the_write_key_only(self):
        from core.access import ROLE_DEFAULTS, user_permissions

        accountant = User.objects.create_user(username="role_defaults_acct", password="x")
        UserCompanyMembership.objects.create(
            user=accountant, tenant=self.office_tenant, role="accountant",
        )
        office_keys = {
            "office.clients.write", "office.clients.all", "office.amounts.view",
            "office.clients.assign", "office.settings.manage",
        }
        granted = user_permissions(accountant, self.office_tenant) & office_keys
        self.assertEqual(granted, {"office.clients.write"})
        manager_defaults = ROLE_DEFAULTS["office_manager"]
        self.assertNotEqual(manager_defaults, "*")
        self.assertTrue(office_keys <= set(manager_defaults))

    def test_a_role_the_company_is_not_licensed_for_cannot_be_assigned(self):
        """دورُ مكتبٍ لشركةٍ بلا الوحدة: 400 لا عضويّةٌ بمفاتيح غائبة.

        `change-role` كان يفحص `ROLE_CHOICES` وحدها فيقبل `office_manager` في
        شركةٍ لا ترخيصَ لها — والدورُ يختفي من كل شاشةٍ ولا يعمل مفتاحٌ من مفاتيحه.
        """
        worker = User.objects.create_user(username="role_change_plain", password="x")
        worker_membership = UserCompanyMembership.objects.create(
            user=worker, tenant=self.plain_tenant, role="staff",
        )
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(
            f"/api/tenants/companies/{self.plain_tenant.pk}/members/change-role/",
            {"membership_id": worker_membership.pk, "role": "office_manager"},
            format="json", HTTP_X_TENANT_ID=str(self.plain_tenant.pk),
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(
            UserCompanyMembership.objects.get(pk=worker_membership.pk).role, "staff",
        )
        # ودورٌ مقيَّدٌ بوحدةٍ أخرى يُرفض أيضاً في الشركة نفسها (`ess` مع hr_suite).
        self.assertEqual(
            self.client.post(
                f"/api/tenants/companies/{self.plain_tenant.pk}/members/change-role/",
                {"membership_id": worker_membership.pk, "role": "ess"},
                format="json", HTTP_X_TENANT_ID=str(self.plain_tenant.pk),
            ).status_code,
            400,
        )


class MembershipHelperTest(APITestCase):
    """قاعدةُ «عضوٌ في الشركة» مكتوبة مرّةً واحدة — يقرؤها النموذج والخدمة."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="member_rule_owner", password="x")
        cls.tenant = create_company("مكتب قاعدة العضوية", cls.owner)
        cls.outsider = User.objects.create_user(username="member_rule_outsider", password="x")

    def test_the_helper_answers_for_members_and_outsiders(self):
        from accounting_office.models import is_tenant_member

        self.assertTrue(is_tenant_member(self.tenant.pk, self.owner.pk))
        self.assertFalse(is_tenant_member(self.tenant.pk, self.outsider.pk))
        self.assertFalse(is_tenant_member(self.tenant.pk, None))
        self.assertFalse(is_tenant_member(None, self.owner.pk))


class ActivityHistoryGuardTest(OfficeRolesTestCase):
    """سجلُّ الزبون رسالةٌ لكل عضو — فتاريخُ زبونٍ لا تراه ليس لك."""

    def seed_history(self):
        from core.activity import log_activity

        for client in (self.mine, self.other):
            log_activity(
                action="create", entity_type="office_client", entity_id=client.pk,
                entity_label=client.name, tenant=self.tenant, user=self.owner,
            )

    def history(self, client_id):
        return self.client.get(
            f"/api/activity/?entity_type=office_client&entity_id={client_id}",
            **self.headers(),
        )

    def test_a_member_reads_the_history_of_their_own_client_only(self):
        self.seed_history()
        self.as_user(self.accountant_user)
        own = self.history(self.mine.pk)
        self.assertEqual(own.status_code, 200, own.content)
        self.assertEqual(len(own.data.get("results", own.data)), 1)

        foreign = self.history(self.other.pk)
        self.assertEqual(foreign.status_code, 404, foreign.content)

    def test_the_owner_reads_every_history(self):
        self.seed_history()
        self.as_user(self.owner)
        for client in (self.mine, self.other):
            with self.subTest(client=client.pk):
                self.assertEqual(self.history(client.pk).status_code, 200)

    def test_a_missing_client_is_404_too(self):
        self.as_user(self.owner)
        self.assertEqual(self.history(self.mine.pk + 5000).status_code, 404)
