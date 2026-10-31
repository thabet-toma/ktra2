"""زبون المكتب وبطاقته الضريبية — #271.

**زبون المكتب منشأة بملف ضريبي واحد**، سجلٌّ يملكه المكتب: ليس `Partner`، ولا
شركةً على المنصّة، ولا صفّاً من طبقة المكتب القديمة. أبو أحمد بمحلّين = **زبونان**.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office.models import (
    ClientContact,
    ClientSettingOverride,
    Contact,
    OfficeClient,
    TaxCard,
)
from accounting_office.services import (
    create_office_client,
    set_client_setting,
    set_office_setting,
    update_tax_card,
)
from core.models import ActivityLog
from core.modules import invalidate_module_cache
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
CLIENTS = f"{BASE}clients/"


def ready_office(tenant):
    """يُكمل أول تشغيل للشركة — الإنشاء مرفوضٌ قبله (قرار #271)."""
    set_office_setting(tenant, "tax_system", "PS")
    set_office_setting(tenant, "office_size", "solo")


class OfficeClientTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.manager = User.objects.create_user(username="clients_mgr", password="x")
        cls.tenant = create_company("مكتب الخليل", cls.manager, template="accounting_office")
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant)

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def create_client(self, name="سوبرماركت الأمل", **overrides):
        payload = {"name": name, **overrides}
        res = self.client.post(CLIENTS, payload, format="json", **self.headers())
        self.assertEqual(res.status_code, 201, res.content)
        return res.data


class OfficeClientCreateTest(OfficeClientTestCase):
    def test_creating_a_client_creates_its_tax_card_in_the_same_write(self):
        row = self.create_client(tax_file_number="2026-0147", notes="يفضّل واتساب")

        self.assertEqual(row["tax_card"]["entity_type"], "")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["status_label"], "نشط")
        self.assertEqual(row["tax_file_number"], "2026-0147")
        self.assertIsNone(row["ended_on"])
        stored = OfficeClient.objects.get(pk=row["id"])
        self.assertTrue(TaxCard.objects.filter(client=stored).exists())
        self.assertEqual(stored.tenant_id, self.tenant.pk)

    def test_the_tax_file_number_is_optional(self):
        row = self.create_client(name="بقالة أبو أحمد")
        self.assertEqual(row["tax_file_number"], "")

    def test_the_client_is_not_a_partner_and_not_a_tenant(self):
        """القرار المحسوم: لا `Partner` ولا شركةً على المنصّة خلف زبون المكتب."""
        tenants_before = Tenant.objects.count()
        partners_before = Partner.objects.count()
        self.create_client()

        self.assertEqual(Tenant.objects.count(), tenants_before)
        self.assertEqual(Partner.objects.count(), partners_before)

    def test_the_name_is_required(self):
        res = self.client.post(CLIENTS, {"name": "   "}, format="json", **self.headers())
        self.assertEqual(res.status_code, 400)


class FirstRunRefusesANewClientTest(APITestCase):
    """زبونٌ قبل اكتمال أول تشغيل = بطاقةٌ بلا اختيارات، ثم ملفٌّ على خطوة ناقصة."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.manager = User.objects.create_user(username="first_run_mgr", password="x")
        cls.fresh = create_company(
            "مكتب بلا اختيار", cls.manager, template="accounting_office",
        )
        invalidate_module_cache(cls.fresh.pk)

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.fresh).pk)}

    def test_the_service_refuses_before_the_office_is_configured(self):
        with self.assertRaises(DjangoValidationError) as caught:
            create_office_client(tenant=self.fresh, name="زبون مبكّر")
        self.assertIn("اختر نظام مكتبك الضريبي وحجمه أولاً", str(caught.exception))
        self.assertFalse(OfficeClient.objects.filter(tenant=self.fresh).exists())

    def test_the_api_answers_400_with_the_same_reason(self):
        res = self.client.post(
            CLIENTS, {"name": "زبون مبكّر"}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("اختر نظام مكتبك الضريبي وحجمه أولاً", str(res.data))

    def test_creating_is_allowed_once_both_are_chosen(self):
        set_office_setting(self.fresh, "tax_system", "IL")
        self.assertEqual(
            self.client.post(
                CLIENTS, {"name": "لسا ناقص"}, format="json", **self.headers(),
            ).status_code,
            400,
        )
        set_office_setting(self.fresh, "office_size", "small")
        self.assertEqual(
            self.client.post(
                CLIENTS, {"name": "جاهز"}, format="json", **self.headers(),
            ).status_code,
            201,
        )


class OfficeClientListAndSearchTest(OfficeClientTestCase):
    def test_search_matches_the_name_and_the_tax_file_number(self):
        self.create_client(name="سوبرماركت الأمل", tax_file_number="2026-0147")
        self.create_client(name="بقالة النور", tax_file_number="2025-0001")

        by_name = self.client.get(f"{CLIENTS}?q=الأمل", **self.headers())
        self.assertEqual([r["name"] for r in by_name.data], ["سوبرماركت الأمل"])

        by_number = self.client.get(f"{CLIENTS}?q=0001", **self.headers())
        self.assertEqual([r["name"] for r in by_number.data], ["بقالة النور"])

    def test_the_status_filter_splits_active_from_ended(self):
        keep = self.create_client(name="نشط")
        gone = self.create_client(name="منتهي")
        self.client.post(f"{CLIENTS}{gone['id']}/end/", {}, format="json", **self.headers())

        active = self.client.get(f"{CLIENTS}?status=active", **self.headers())
        ended = self.client.get(f"{CLIENTS}?status=ended", **self.headers())
        every = self.client.get(f"{CLIENTS}?status=all", **self.headers())

        self.assertEqual([r["id"] for r in active.data], [keep["id"]])
        self.assertEqual([r["id"] for r in ended.data], [gone["id"]])
        self.assertEqual(len(every.data), 2)

    def test_the_list_is_light_and_its_query_count_does_not_grow_with_clients(self):
        """صفُّ القائمة بلا بطاقة، ونظامُه من استعلامين لا من المحلّل لكل صف."""
        self.create_client(name="الأول")
        self.create_client(name="الثاني")
        self.client.get(CLIENTS, **self.headers())  # إحماءُ الكاشات

        with CaptureQueriesContext(connection) as small:
            first = self.client.get(CLIENTS, **self.headers())
        self.assertEqual(len(first.data), 2)
        self.assertNotIn("tax_card", first.data[0])
        # نظامُ الصفّ الفعليّ يُحسب — والحساب الجماعيّ لا يُلغي القيمة.
        self.assertEqual(first.data[0]["tax_system"], "PS")
        self.assertEqual(first.data[0]["tax_system_label"], "فلسطيني")

        for index in range(8):
            self.create_client(name=f"زبون {index}")

        with CaptureQueriesContext(connection) as big:
            many = self.client.get(CLIENTS, **self.headers())
        self.assertEqual(len(many.data), 10)
        self.assertEqual(
            len(big.captured_queries), len(small.captured_queries),
            f"عدد استعلامات القائمة كبر مع عدد الزبائن: "
            f"{len(small.captured_queries)} ⇒ {len(big.captured_queries)}",
        )
        # سقفٌ مطلقٌ أيضاً: نموٌّ ثابتٌ لكن كبير (استعلامان لكل صف) يمرّ من المقارنة.
        self.assertLessEqual(len(small.captured_queries), 12)


class OfficeClientLifecycleTest(OfficeClientTestCase):
    def test_ending_keeps_the_client_its_card_and_its_contacts(self):
        row = self.create_client()
        contact = self.client.post(
            f"{BASE}contacts/", {"name": "أحمد يوسف", "phone": "0599123456", "language": "ar"},
            format="json", **self.headers(),
        ).data
        self.client.post(
            f"{CLIENTS}{row['id']}/contacts/", {"contact": contact["id"], "is_primary": True},
            format="json", **self.headers(),
        )

        res = self.client.post(f"{CLIENTS}{row['id']}/end/", {}, format="json", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["status"], "ended")
        self.assertEqual(res.data["status_label"], "منتهي")
        self.assertIsNotNone(res.data["ended_on"])

        stored = OfficeClient.objects.get(pk=row["id"])
        self.assertEqual(stored.status, OfficeClient.STATUS_ENDED)
        self.assertEqual(stored.ended_on, timezone.localdate())
        self.assertTrue(TaxCard.objects.filter(client=stored).exists())
        self.assertEqual(stored.contact_links.count(), 1)

    def test_reactivating_clears_the_end_date(self):
        row = self.create_client()
        self.client.post(f"{CLIENTS}{row['id']}/end/", {}, format="json", **self.headers())

        res = self.client.post(f"{CLIENTS}{row['id']}/reactivate/", {}, format="json", **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["status"], "active")
        self.assertIsNone(res.data["ended_on"])
        self.assertIsNone(OfficeClient.objects.get(pk=row["id"]).ended_on)

    def test_both_transitions_are_written_to_the_activity_log(self):
        """حالةٌ تتبدّل بلا أثرٍ في السجلّ تجعل «متى توقّف» سؤالاً بلا جواب."""
        row = self.create_client()
        self.client.post(f"{CLIENTS}{row['id']}/end/", {}, format="json", **self.headers())
        self.client.post(f"{CLIENTS}{row['id']}/reactivate/", {}, format="json", **self.headers())

        events = ActivityLog.objects.filter(
            entity_type="office_client", entity_id=row["id"],
        ).order_by("id")
        self.assertEqual(events.count(), 2)
        self.assertEqual(
            [entry.description for entry in events],
            ["إنهاء زبون مكتب", "إعادة زبون مكتب نشطاً"],
        )
        self.assertTrue(all(entry.user_id == self.manager.pk for entry in events))
        self.assertTrue(all(entry.tenant_id == self.tenant.pk for entry in events))
        self.assertEqual(events[0].metadata["ended_on"], timezone.localdate().isoformat())
        self.assertEqual(events[1].metadata["ended_on"], timezone.localdate().isoformat())

    def test_there_is_no_delete_route_for_a_client(self):
        """«منتهي» يبقى بكل بياناته — لا حذف في هذه الطبقة إطلاقاً."""
        row = self.create_client()

        res = self.client.delete(f"{CLIENTS}{row['id']}/", **self.headers())
        self.assertEqual(res.status_code, 405)
        self.assertTrue(OfficeClient.objects.filter(pk=row["id"]).exists())


class TaxCardTest(OfficeClientTestCase):
    def patch_card(self, client_id, payload):
        return self.client.patch(
            f"{CLIENTS}{client_id}/tax-card/", payload, format="json", **self.headers(),
        )

    def test_the_card_is_also_written_with_the_client_itself(self):
        """«تُقرأ/تُعدَّل مع الزبون أو بنقطتها» — المساران يكتبان البطاقة نفسها."""
        row = self.create_client()

        res = self.client.patch(
            f"{CLIENTS}{row['id']}/",
            {"name": "اسم جديد", "tax_card": {"entity_type": "partnership", "annual_sales": "5000.50"}},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["name"], "اسم جديد")
        self.assertEqual(res.data["tax_card"]["entity_type"], "partnership")
        self.assertEqual(Decimal(res.data["tax_card"]["annual_sales"]), Decimal("5000.50"))

        reread = self.client.get(f"{CLIENTS}{row['id']}/tax-card/", **self.headers())
        self.assertEqual(reread.data["entity_type"], "partnership")

    def test_the_card_is_read_and_patched_through_its_own_point(self):
        row = self.create_client()

        read = self.client.get(f"{CLIENTS}{row['id']}/tax-card/", **self.headers())
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.data["entity_type"], "")
        self.assertEqual(Decimal(read.data["annual_sales"]), Decimal("0"))

        res = self.patch_card(row["id"], {
            "entity_type": "company",
            "vat_classification": "licensed",
            "annual_sales": "120000.00",
            "has_employees": True,
            "employees_count": 4,
            "is_self_employed": True,
        })
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["entity_type"], "company")
        self.assertEqual(res.data["vat_classification"], "licensed")
        self.assertEqual(res.data["entity_type_label"], "شركة مساهمة")
        self.assertEqual(res.data["vat_classification_label"], "مشتغل مرخّص")
        self.assertTrue(res.data["has_employees"])
        self.assertEqual(res.data["employees_count"], 4)
        self.assertTrue(res.data["is_self_employed"])
        self.assertEqual(Decimal(res.data["annual_sales"]), Decimal("120000.00"))

    def test_choices_are_the_ones_of_the_client_tax_system(self):
        """تصنيف ق.م اختياراتُ نظام الزبون — `authorized` إسرائيليّ لا فلسطينيّ."""
        ps_row = self.create_client(name="زبون فلسطيني")
        self.assertEqual(
            self.patch_card(ps_row["id"], {"vat_classification": "authorized"}).status_code, 400,
        )
        self.assertEqual(
            self.patch_card(ps_row["id"], {"vat_classification": "licensed"}).status_code, 200,
        )

        il_row = self.create_client(name="زبون إسرائيلي")
        set_client_setting(OfficeClient.objects.get(pk=il_row["id"]), "tax_system", "IL")
        self.assertEqual(
            self.patch_card(il_row["id"], {"vat_classification": "licensed"}).status_code, 400,
        )
        self.assertEqual(
            self.patch_card(il_row["id"], {"vat_classification": "authorized"}).status_code, 200,
        )
        # مفتاحٌ مشتركٌ بين النظامين يبقى مقبولاً في كليهما.
        self.assertEqual(
            self.patch_card(il_row["id"], {"vat_classification": "exempt"}).status_code, 200,
        )
        self.assertEqual(
            self.patch_card(ps_row["id"], {"vat_classification": "exempt"}).status_code, 200,
        )

    def test_all_four_entity_types_are_offered_by_both_systems(self):
        """المفاتيحُ مشتركة — والقائمة تُفحص **لكل نظامٍ**، وإلا سقط نصفُها صامتاً."""
        expected = ["individual", "partnership", "company", "nonprofit"]

        ps_row = self.create_client(name="زبون فلسطيني")
        ps_card = self.client.get(f"{CLIENTS}{ps_row['id']}/tax-card/", **self.headers()).data
        self.assertEqual(
            [choice["value"] for choice in ps_card["entity_type_choices"]], expected,
        )

        il_row = self.create_client(name="زبون إسرائيلي")
        set_client_setting(OfficeClient.objects.get(pk=il_row["id"]), "tax_system", "IL")
        il_card = self.client.get(f"{CLIENTS}{il_row['id']}/tax-card/", **self.headers()).data
        self.assertEqual(il_card["tax_system"], "IL")
        self.assertEqual(
            [choice["value"] for choice in il_card["entity_type_choices"]], expected,
        )
        # وتسمياتٌ إسرائيليّةٌ فعلاً — لا تسميات النظام الفلسطيني.
        self.assertEqual(
            [choice["label"] for choice in il_card["entity_type_choices"]],
            ["יחיד — فرد", "שותפות — شراكة", 'חברה בע"מ — شركة', 'מלכ"ר — غير ربحية'],
        )

    def test_the_card_keeps_its_payload_for_an_ended_client(self):
        row = self.create_client()
        self.patch_card(row["id"], {"entity_type": "individual", "vat_classification": "exempt"})
        self.client.post(f"{CLIENTS}{row['id']}/end/", {}, format="json", **self.headers())

        read = self.client.get(f"{CLIENTS}{row['id']}/tax-card/", **self.headers())
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.data["entity_type"], "individual")
        self.assertEqual(read.data["vat_classification"], "exempt")

    def test_one_card_per_client_is_a_database_rule(self):
        row = self.create_client()
        stored = OfficeClient.objects.get(pk=row["id"])
        with self.assertRaises(IntegrityError):
            TaxCard.objects.create(client=stored, entity_type="company")

    def test_annual_sales_are_validated_by_the_service_not_only_by_the_api(self):
        """الخدمة تُنادَى مباشرةً أيضاً — فلا `InvalidOperation` من القاعدة (500)."""
        row = self.create_client()
        client = OfficeClient.objects.get(pk=row["id"])

        for bad in ("-1", "abc", "10.999", "1000000000000", None):
            with self.subTest(value=bad):
                with self.assertRaises(DjangoValidationError):
                    update_tax_card(client, annual_sales=bad)

        card = update_tax_card(client, annual_sales=Decimal("999999999999.99"))
        self.assertEqual(card.annual_sales, Decimal("999999999999.99"))


class ChildTenantGuardTest(TestCase):
    """شركةٌ مخالفةٌ تُرفض — لا تُكتب بصمت (كان التعليق يقول القاعدة بلا تنفيذ)."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="guard_owner", password="x")
        cls.mine = Tenant.objects.create(CompanyName="مكتبي")
        cls.other = Tenant.objects.create(CompanyName="مكتب آخر")

    def setUp(self):
        self.client = OfficeClient.objects.create(tenant=self.mine, name="زبون")
        self.contact = Contact.objects.create(tenant=self.mine, name="جهة", language="ar")
        self.link = ClientContact.objects.create(
            client=self.client, contact=self.contact,
        )

    def test_a_foreign_tenant_is_refused_on_every_child_model(self):
        factories = {
            "TaxCard": lambda: TaxCard(client=self.client, tenant=self.other),
            "ClientContact": lambda: ClientContact(
                client=self.client, tenant=self.other,
                contact=Contact.objects.create(
                    tenant=self.mine, name="جهة ثانية", language="ar",
                ),
            ),
            "ClientSettingOverride": lambda: ClientSettingOverride(
                client=self.client, tenant=self.other,
                key="tax_system", value="IL",
            ),
        }
        for label, factory in factories.items():
            with self.subTest(model=label):
                with self.assertRaises(ValueError):
                    factory().save()
        # الصفوف المشروعة بقيت — الحارس لا يرمي على الملء التلقائي.
        self.assertEqual(self.link.tenant_id, self.mine.pk)

    def test_the_tenant_is_filled_from_the_client_when_absent(self):
        card = TaxCard.objects.create(client=self.client, entity_type="company")
        self.assertEqual(card.tenant_id, self.mine.pk)


class OfficeClientIsolationTest(APITestCase):
    """مكتبٌ لا يرى زبائن مكتبٍ آخر — قائمةً وقراءةً وتعديلاً."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.manager_a = User.objects.create_user(username="iso_mgr_a", password="x")
        cls.manager_b = User.objects.create_user(username="iso_mgr_b", password="x")
        cls.tenant_a = create_company("مكتب أ", cls.manager_a, template="accounting_office")
        cls.tenant_b = create_company("مكتب ب", cls.manager_b, template="accounting_office")
        invalidate_module_cache(cls.tenant_a.pk)
        invalidate_module_cache(cls.tenant_b.pk)
        ready_office(cls.tenant_a)
        ready_office(cls.tenant_b)

    def headers(self, tenant):
        return {"HTTP_X_TENANT_ID": str(tenant.pk)}

    def setUp(self):
        self.client.force_authenticate(user=self.manager_a)
        self.mine = self.client.post(
            CLIENTS, {"name": "زبوني"}, format="json", **self.headers(self.tenant_a),
        ).data

    def test_the_other_office_sees_none_of_my_clients(self):
        self.client.force_authenticate(user=self.manager_b)
        listing = self.client.get(CLIENTS, **self.headers(self.tenant_b))
        self.assertEqual(listing.data, [])

    def test_the_other_office_cannot_read_my_client(self):
        self.client.force_authenticate(user=self.manager_b)
        res = self.client.get(f"{CLIENTS}{self.mine['id']}/", **self.headers(self.tenant_b))
        self.assertEqual(res.status_code, 404)

    def test_the_other_office_cannot_edit_my_client(self):
        self.client.force_authenticate(user=self.manager_b)
        res = self.client.patch(
            f"{CLIENTS}{self.mine['id']}/", {"name": "مسروق"},
            format="json", **self.headers(self.tenant_b),
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(OfficeClient.objects.get(pk=self.mine["id"]).name, "زبوني")

    def test_the_other_office_cannot_open_my_tax_card(self):
        self.client.force_authenticate(user=self.manager_b)
        res = self.client.get(
            f"{CLIENTS}{self.mine['id']}/tax-card/", **self.headers(self.tenant_b),
        )
        self.assertEqual(res.status_code, 404)

    def test_a_supplied_tenant_id_in_the_body_is_ignored(self):
        """الشركة من الطلب لا من جسمه — وإلا كان كل عزلٍ زينة."""
        res = self.client.post(
            CLIENTS, {"name": "زبوني الآخر", "tenant": self.tenant_b.pk},
            format="json", **self.headers(self.tenant_a),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(OfficeClient.objects.get(pk=res.data["id"]).tenant_id, self.tenant_a.pk)

    def test_contacts_are_isolated_too(self):
        contact = self.client.post(
            f"{BASE}contacts/", {"name": "جهة مكتب أ", "phone": "0599", "language": "ar"},
            format="json", **self.headers(self.tenant_a),
        ).data
        self.client.force_authenticate(user=self.manager_b)

        listing = self.client.get(f"{BASE}contacts/", **self.headers(self.tenant_b))
        self.assertEqual(listing.data, [])

        detail = self.client.get(f"{BASE}contacts/{contact['id']}/", **self.headers(self.tenant_b))
        self.assertEqual(detail.status_code, 404)


class TenantMembershipTest(OfficeClientTestCase):
    def test_a_member_of_the_office_reaches_the_list(self):
        member = User.objects.create_user(username="office_member", password="x")
        UserCompanyMembership.objects.create(
            user=member, tenant=self.tenant, role="employee",
        )
        self.client.force_authenticate(user=member)
        self.assertEqual(self.client.get(CLIENTS, **self.headers()).status_code, 200)

    def test_nobody_without_authentication_reaches_it(self):
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(CLIENTS).status_code, (401, 403))

class ClientUpdateIsAtomicTest(OfficeClientTestCase):
    """الاسمُ والبطاقةُ في كتابةٍ واحدة: بطاقةٌ مرفوضة تُبقي الاسمَ كما كان."""

    def test_an_invalid_card_rolls_back_the_name(self):
        row = self.create_client(name="الاسم قبل")
        res = self.client.patch(
            f"{CLIENTS}{row['id']}/",
            {"name": "الاسم بعد", "tax_card": {"vat_classification": "authorized"}},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(OfficeClient.objects.get(pk=row["id"]).name, "الاسم قبل")

    def test_a_valid_pair_is_saved_together(self):
        row = self.create_client(name="الاسم قبل")
        res = self.client.patch(
            f"{CLIENTS}{row['id']}/",
            {"name": "الاسم بعد", "tax_card": {"vat_classification": "licensed"}},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        stored = OfficeClient.objects.get(pk=row["id"])
        self.assertEqual(stored.name, "الاسم بعد")
        self.assertEqual(stored.tax_card.vat_classification, "licensed")


class EmployeesCountCapTest(OfficeClientTestCase):
    def test_a_count_beyond_the_field_range_is_refused_by_the_service(self):
        row = self.create_client()
        client = OfficeClient.objects.get(pk=row["id"])

        for bad in (32768, 100000, -1, "3", 3.5, True):
            with self.subTest(value=bad):
                with self.assertRaises(DjangoValidationError):
                    update_tax_card(client, employees_count=bad)

        self.assertEqual(update_tax_card(client, employees_count=32767).employees_count, 32767)


class ChildCrossLinkGuardTest(TestCase):
    """الرابط يحمل زبوناً وشخصاً: اختلافُ مكتبيهما يفسد «من نكلّم» بلا أثر."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="cross_owner", password="x")
        cls.mine = Tenant.objects.create(CompanyName="مكتب الرابط")
        cls.other = Tenant.objects.create(CompanyName="مكتب آخر")

    def test_a_contact_from_another_office_cannot_be_linked(self):
        client = OfficeClient.objects.create(tenant=self.mine, name="زبون")
        foreign = Contact.objects.create(tenant=self.other, name="جهة غيري", language="ar")

        with self.assertRaises(ValueError):
            ClientContact.objects.create(client=client, contact=foreign)

    def test_a_reminder_recipient_must_point_at_this_client_link(self):
        from accounting_office.models import ClientReminderRecipient

        first = OfficeClient.objects.create(tenant=self.mine, name="الأول")
        second = OfficeClient.objects.create(tenant=self.mine, name="الثاني")
        contact = Contact.objects.create(tenant=self.mine, name="جهة", language="ar")
        foreign_link = ClientContact.objects.create(client=second, contact=contact)

        with self.assertRaises(ValueError):
            ClientReminderRecipient.objects.create(
                client=first, reminder_type="balance", client_contact=foreign_link,
            )