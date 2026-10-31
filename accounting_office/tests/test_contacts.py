"""جهات الاتصال وربطها بالزبائن ومستلِم كل نوع تذكير — #271.

**جهة الاتصال شخص** يملكه المكتب، **لا الزبون**: الجهة الواحدة تُربط بأكثر من
زبون (أبو أحمد بمحلّين له جهةٌ واحدة مربوطة بالاثنين). ولكل زبون **جهة رئيسية
واحدة على الأكثر** — قيدُ قاعدة بياناتٍ شرطي لا عُرفُ كود — ولكل **نوع تذكير
مستلِم**، وغياب التعيين يعني الرئيسية.
"""
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from accounting_office.models import (
    ClientContact,
    ClientReminderRecipient,
    Contact,
    OfficeClient,
)
from accounting_office.services import (
    link_client_contact,
    set_office_setting,
    set_primary_client_contact,
    set_reminder_recipient,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency
from tenants.services import create_company

BASE = "/api/accounting-office/"
CLIENTS = f"{BASE}clients/"
CONTACTS = f"{BASE}contacts/"


class ContactTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.manager = User.objects.create_user(username="contacts_mgr", password="x")
        cls.tenant = create_company("مكتب جهات الاتصال", cls.manager, template="accounting_office")
        invalidate_module_cache(cls.tenant.pk)
        # أول تشغيل — إنشاء زبون مرفوضٌ قبله (قرار #271).
        set_office_setting(cls.tenant, "tax_system", "PS")
        set_office_setting(cls.tenant, "office_size", "solo")

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def make_client(self, name):
        res = self.client.post(CLIENTS, {"name": name}, format="json", **self.headers())
        self.assertEqual(res.status_code, 201, res.content)
        return res.data

    def make_contact(self, name="أحمد يوسف", phone="0599123456", language="ar"):
        res = self.client.post(
            CONTACTS,
            {"name": name, "phone": phone, "language": language},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        return res.data


class ContactCrudTest(ContactTestCase):
    def test_the_contact_carries_its_language_and_phone(self):
        row = self.make_contact()
        self.assertEqual(row["language"], "ar")
        self.assertEqual(row["phone"], "0599123456")
        self.assertEqual(Contact.objects.get(pk=row["id"]).tenant_id, self.tenant.pk)

    def test_a_hebrew_speaking_contact_is_allowed(self):
        row = self.make_contact(name="דוד כהן", language="he")
        self.assertEqual(row["language"], "he")

    def test_an_unknown_language_is_rejected(self):
        res = self.client.post(
            CONTACTS, {"name": "جهة", "phone": "0599", "language": "en"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400)

    def test_the_name_is_required(self):
        res = self.client.post(
            CONTACTS, {"name": "", "phone": "0599", "language": "ar"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400)

    def test_a_contact_is_edited_and_deleted(self):
        row = self.make_contact()
        patched = self.client.patch(
            f"{CONTACTS}{row['id']}/", {"phone": "0500000000"},
            format="json", **self.headers(),
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.data["phone"], "0500000000")

        deleted = self.client.delete(f"{CONTACTS}{row['id']}/", **self.headers())
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Contact.objects.filter(pk=row["id"]).exists())

    def test_a_linked_contact_cannot_be_deleted(self):
        """حذفُها تحت الزبون يقطع صامتاً «من نكلّمه» — يُفكّ الربط أولاً."""
        shop = self.make_client("محل")
        row = self.make_contact()
        self.client.post(
            f"{CLIENTS}{shop['id']}/contacts/", {"contact": row["id"]},
            format="json", **self.headers(),
        )

        res = self.client.delete(f"{CONTACTS}{row['id']}/", **self.headers())
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("افكّ ربطها", str(res.data))
        self.assertTrue(Contact.objects.filter(pk=row["id"]).exists())

        self.client.delete(f"{CLIENTS}{shop['id']}/contacts/{row['id']}/", **self.headers())
        self.assertEqual(
            self.client.delete(f"{CONTACTS}{row['id']}/", **self.headers()).status_code, 204,
        )

    def test_the_contact_list_is_searchable_by_name_and_phone(self):
        self.make_contact(name="أحمد يوسف", phone="0599123456")
        self.make_contact(name="דוד כהן", phone="0522000111")

        by_name = self.client.get(f"{CONTACTS}?q=أحمد", **self.headers())
        self.assertEqual([row["name"] for row in by_name.data], ["أحمد يوسف"])

        by_phone = self.client.get(f"{CONTACTS}?q=0522", **self.headers())
        self.assertEqual([row["name"] for row in by_phone.data], ["דוד כהן"])

        self.assertEqual(len(self.client.get(CONTACTS, **self.headers()).data), 2)


class TwoShopsOneContactTest(ContactTestCase):
    def test_abu_ahmad_with_two_shops_is_two_clients_sharing_one_contact(self):
        shop = self.make_client("محل أبو أحمد")
        second_shop = self.make_client("محل أبو أحمد الثاني")
        contact = self.make_contact()

        first = self.client.post(
            f"{CLIENTS}{shop['id']}/contacts/",
            {"contact": contact["id"], "is_primary": True},
            format="json", **self.headers(),
        )
        second = self.client.post(
            f"{CLIENTS}{second_shop['id']}/contacts/",
            {"contact": contact["id"], "is_primary": True},
            format="json", **self.headers(),
        )

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(OfficeClient.objects.filter(tenant=self.tenant).count(), 2)
        self.assertEqual(Contact.objects.get(pk=contact["id"]).client_links.count(), 2)

    def test_the_primary_contact_is_unique_per_client_in_the_database(self):
        """القيد شرطيٌّ في القاعدة — لا عُرفُ خدمةٍ قد يُنسى في مسارٍ جديد."""
        shop = self.make_client("محل")
        stored = OfficeClient.objects.get(pk=shop["id"])
        first = self.make_contact(name="الأولى")
        second = self.make_contact(name="الثانية")

        link_client_contact(
            client=stored, contact=Contact.objects.get(pk=first["id"]), is_primary=True,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClientContact.objects.create(
                    client=stored,
                    contact=Contact.objects.get(pk=second["id"]),
                    is_primary=True,
                )

    def test_promoting_a_second_primary_demotes_the_first(self):
        shop = self.make_client("محل")
        first = self.make_contact(name="الأولى")
        second = self.make_contact(name="الثانية")
        for row in (first, second):
            self.client.post(
                f"{CLIENTS}{shop['id']}/contacts/",
                {"contact": row["id"]},
                format="json", **self.headers(),
            )

        res = self.client.post(
            f"{CLIENTS}{shop['id']}/contacts/{second['id']}/primary/",
            {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)

        stored = OfficeClient.objects.get(pk=shop["id"])
        primaries = list(
            stored.contact_links.filter(is_primary=True).values_list("contact_id", flat=True),
        )
        self.assertEqual(primaries, [second["id"]])

    def test_unlinking_removes_only_that_link(self):
        shop = self.make_client("محل")
        other = self.make_client("محل آخر")
        contact = self.make_contact()
        for target in (shop, other):
            self.client.post(
                f"{CLIENTS}{target['id']}/contacts/",
                {"contact": contact["id"]},
                format="json", **self.headers(),
            )

        res = self.client.delete(
            f"{CLIENTS}{shop['id']}/contacts/{contact['id']}/", **self.headers(),
        )
        self.assertEqual(res.status_code, 204)
        self.assertEqual(Contact.objects.get(pk=contact["id"]).client_links.count(), 1)

    def test_linking_the_same_contact_twice_is_a_400_not_a_duplicate_row(self):
        shop = self.make_client("محل")
        contact = self.make_contact()
        url = f"{CLIENTS}{shop['id']}/contacts/"
        self.assertEqual(
            self.client.post(url, {"contact": contact["id"]}, format="json",
                             **self.headers()).status_code, 201,
        )
        again = self.client.post(url, {"contact": contact["id"]}, format="json", **self.headers())
        self.assertEqual(again.status_code, 400)
        self.assertEqual(ClientContact.objects.filter(client_id=shop["id"]).count(), 1)


class ReminderRecipientTest(ContactTestCase):
    def test_a_type_without_an_assignment_falls_back_to_the_primary(self):
        shop = self.make_client("محل")
        self.make_contact(name="ليست رئيسية", phone="0500000001")
        primary = self.make_contact(name="الرئيسية", phone="0500000002")
        stored = OfficeClient.objects.get(pk=shop["id"])
        link_client_contact(
            client=stored, contact=Contact.objects.get(pk=primary["id"]),
        )
        set_primary_client_contact(
            client=stored, contact=Contact.objects.get(pk=primary["id"]),
        )

        payload = self.client.get(f"{CLIENTS}{shop['id']}/reminders/", **self.headers())
        self.assertEqual(payload.status_code, 200)
        by_type = {row["reminder_type"]: row for row in payload.data}
        self.assertEqual(set(by_type), {"documents", "deadline", "balance", "appointment"})
        for row in by_type.values():
            self.assertEqual(row["recipient"]["contact_id"], primary["id"])
            self.assertTrue(row["is_fallback"])

    def test_an_assignment_beats_the_primary_for_that_type_only(self):
        shop = self.make_client("محل")
        primary = self.make_contact(name="الرئيسية", phone="0500000002")
        accountant = self.make_contact(name="المحاسب", phone="0500000003")
        stored = OfficeClient.objects.get(pk=shop["id"])
        for row in (primary, accountant):
            link_client_contact(
                client=stored, contact=Contact.objects.get(pk=row["id"]),
            )
        set_primary_client_contact(
            client=stored, contact=Contact.objects.get(pk=primary["id"]),
        )

        res = self.client.post(
            f"{CLIENTS}{shop['id']}/reminders/",
            {"reminder_type": "balance", "contact": accountant["id"]},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)

        by_type = {
            row["reminder_type"]: row
            for row in self.client.get(f"{CLIENTS}{shop['id']}/reminders/", **self.headers()).data
        }
        self.assertEqual(by_type["balance"]["recipient"]["contact_id"], accountant["id"])
        self.assertFalse(by_type["balance"]["is_fallback"])
        self.assertEqual(by_type["documents"]["recipient"]["contact_id"], primary["id"])

    def test_clearing_an_assignment_returns_the_type_to_the_primary(self):
        shop = self.make_client("محل")
        primary = self.make_contact(name="الرئيسية")
        other = self.make_contact(name="أخرى")
        stored = OfficeClient.objects.get(pk=shop["id"])
        for row in (primary, other):
            link_client_contact(
                client=stored, contact=Contact.objects.get(pk=row["id"]),
            )
        set_primary_client_contact(
            client=stored, contact=Contact.objects.get(pk=primary["id"]),
        )
        set_reminder_recipient(
            client=stored,
            reminder_type="documents",
            contact=Contact.objects.get(pk=other["id"]),
        )

        res = self.client.post(
            f"{CLIENTS}{shop['id']}/reminders/",
            {"reminder_type": "documents", "contact": None},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(ClientReminderRecipient.objects.filter(client=stored).exists())

        by_type = {
            row["reminder_type"]: row
            for row in self.client.get(f"{CLIENTS}{shop['id']}/reminders/", **self.headers()).data
        }
        self.assertEqual(by_type["documents"]["recipient"]["contact_id"], primary["id"])
        self.assertTrue(by_type["documents"]["is_fallback"])

    def test_an_unknown_reminder_type_is_rejected(self):
        shop = self.make_client("محل")
        res = self.client.post(
            f"{CLIENTS}{shop['id']}/reminders/",
            {"reminder_type": "newsletter", "contact": None},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400)

    def test_the_recipient_must_be_linked_to_that_client(self):
        shop = self.make_client("محل")
        stranger = self.make_contact(name="غير مربوطة")
        res = self.client.post(
            f"{CLIENTS}{shop['id']}/reminders/",
            {"reminder_type": "balance", "contact": stranger["id"]},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 400)

    def test_a_contact_of_another_office_cannot_be_linked(self):
        """كائنٌ مرجعيّ من شركةٍ أخرى يُرفض — لا يُنشأ رابطٌ عابر للشركات."""
        shop = self.make_client("محل")

        other_manager = User.objects.create_user(username="contacts_other", password="x")
        other_tenant = create_company(
            "مكتب آخر", other_manager, template="accounting_office",
        )
        invalidate_module_cache(other_tenant.pk)
        foreign_contact = Contact.objects.create(
            tenant=other_tenant, name="جهة مكتب آخر", phone="0599", language="ar",
        )

        res = self.client.post(
            f"{CLIENTS}{shop['id']}/contacts/",
            {"contact": foreign_contact.pk},
            format="json", **self.headers(),
        )
        # 404: `_contact` يبحث في جهات شركة الطلب وحدها، فجهةُ مكتبٍ آخر «غير موجودة».
        self.assertEqual(res.status_code, 404)
        self.assertEqual(ClientContact.objects.filter(client_id=shop["id"]).count(), 0)
