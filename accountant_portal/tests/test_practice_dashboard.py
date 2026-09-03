"""ISSUE #58 — لوحة المكتب: ثلاثة عناصر لا رابع، بعدد استعلامات ثابت.

قائمة العملاء وحالة كل دفتر، الاستحقاقات القريبة، والأتعاب غير المحصّلة —
معاً في نداء واحد. الملاحظة هنا على **الأثر** فوق HTTP: صفوف الرد وعددُ
الاستعلامات الفعلي (`CaptureQueriesContext`) — لا استدعاء دوالّ الخدمة مباشرة.

قاعدة الأداء (§الأداء): عدد الاستعلامات لا يكبر بعدد العملاء — مكتبٌ بستّين
عميلاً يقع في نفس عطب «الكرت المجمّع» (30 ثانية على 1490 صنفاً) إن كُتبت
اللوحة صفّاً صفّاً.

ISSUE #86: عملاء المكتب صاروا أطراف شركة المكتب (`partners.Partner`) — كل
عميلٍ هنا صفٌّ في `Partner` بـ`tenant=` شركة المكتب نفسها، لا `PracticeClient`.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from accountant_portal.models import AccountantEngagement, AccountantProfile
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accountant/practice/dashboard/"


def make_office(username, tax_number):
    user = User.objects.create_user(username, email=f"{username}@example.com")
    AccountantProfile.objects.create(
        user=user,
        professional_type="licensed_auditor",
        tax_registration_number=tax_number,
        business_address="رام الله",
    )
    return user


def make_client(tenant, name, **extra):
    return Partner.objects.create(tenant=tenant, partner_type="Customer", name=name, **extra)


def api_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=user).key}")
    return client


def _fee_invoice(tenant, currency, number, *, grand_total, amount_paid=Decimal("0")):
    customer = Partner.objects.create(
        tenant=tenant, name=f"زبون أتعاب {number}", partner_type="Customer",
    )
    return SalesInvoice.objects.create(
        tenant=tenant,
        invoice_number=number,
        customer=customer,
        invoice_date=date(2026, 6, 15),
        currency=currency,
        status=SalesInvoice.STATUS_POSTED,
        invoice_type=SalesInvoice.INVOICE_CREDIT,
        invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        subtotal_excl_tax=grand_total,
        tax_amount=Decimal("0"),
        grand_total=grand_total,
        amount_paid=amount_paid,
    )


class PracticeDashboardQueryCountTest(APITestCase):
    """اختبار الأداء الإلزامي: العدد ثابتٌ من 3 عملاء إلى 60."""

    @classmethod
    def setUpTestData(cls):
        cls.currency = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )[0]
        cls.office_manager = make_office("office-58-scale", "TAX-58-SCALE")
        cls.office = create_company("مكتب المحاسبة ٥٨", cls.office_manager)
        for i in range(3):
            make_client(cls.office, f"زبون {i}")
        # ISSUE #86: عميل الفاتورة نفسه طرفٌ في نفس شركة المكتب فيُحتسَب زبوناً —
        # هذا هو الاندماج المقصود، فيدخل في عدّ «الزبائن» أيضاً (+1).
        _fee_invoice(cls.office, cls.currency, "FEE-1", grand_total=Decimal("500.00"))

    def setUp(self):
        self.api = api_for(self.office_manager)

    def test_query_count_does_not_grow_with_client_count(self):
        self.api.get(BASE)  # إحماء أي كاش لكل عملية
        with CaptureQueriesContext(connection) as small:
            small_response = self.api.get(BASE)
        self.assertEqual(small_response.status_code, 200, small_response.content)
        # +1: عميل فاتورة الأتعاب طرفٌ في الشركة نفسها فيُحسَب زبوناً (انظر الملاحظة أعلاه).
        self.assertEqual(len(small_response.json()["clients"]), 4)

        for i in range(3, 60):
            make_client(self.office, f"زبون {i}")

        with CaptureQueriesContext(connection) as big:
            big_response = self.api.get(BASE)
        self.assertEqual(big_response.status_code, 200, big_response.content)
        self.assertEqual(len(big_response.json()["clients"]), 61)

        self.assertEqual(
            len(big.captured_queries), len(small.captured_queries),
            f"عدد الاستعلامات كبر مع عدد العملاء: {len(small.captured_queries)} ⇒ "
            f"{len(big.captured_queries)}",
        )


class PracticeDashboardIsolationTest(APITestCase):
    """موظفٌ مُسنَد إلى ثلاثة عملاء يرى ثلاثة لا ستّين، ولا يظهر عميل مكتب آخر."""

    @classmethod
    def setUpTestData(cls):
        cls.office_a = make_office("office-58-a", "TAX-58-A")
        cls.tenant_a = create_company("مكتب أ ٥٨", cls.office_a)
        cls.office_b = make_office("office-58-b", "TAX-58-B")
        cls.tenant_b = create_company("مكتب ب ٥٨", cls.office_b)
        for i in range(60):
            make_client(cls.tenant_a, f"زبون أ {i}")
        for i in range(3):
            make_client(cls.tenant_b, f"زبون ب {i}")

    def test_each_office_sees_only_its_own_client_count(self):
        response_a = api_for(self.office_a).get(BASE)
        response_b = api_for(self.office_b).get(BASE)
        self.assertEqual(response_a.status_code, 200, response_a.content)
        self.assertEqual(response_b.status_code, 200, response_b.content)
        self.assertEqual(len(response_a.json()["clients"]), 60)
        self.assertEqual(len(response_b.json()["clients"]), 3)

    def test_another_offices_client_never_appears(self):
        response_b = api_for(self.office_b).get(BASE)
        names = {row["trade_name"] for row in response_b.json()["clients"]}
        self.assertTrue(names.issubset({"زبون ب 0", "زبون ب 1", "زبون ب 2"}))
        self.assertFalse(any(name.startswith("زبون أ") for name in names))


class PracticeDashboardContentTest(APITestCase):
    """العناصر الثلاثة: حالة الدفتر، الأتعاب غير المحصّلة من دفتر المكتب لا دفتر العميل."""

    @classmethod
    def setUpTestData(cls):
        cls.currency = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )[0]
        cls.office_manager = make_office("office-58-content", "TAX-58-CONTENT")
        cls.office = create_company("مكتب المحاسبة ٥٨-٢", cls.office_manager)
        cls.managed_book = create_company(
            "دفتر عميل مُدار ٥٨", cls.office_manager, managed_by=cls.office,
        )
        cls.unlinked_client = make_client(cls.office, "زبون خارجي")
        cls.managed_client = make_client(cls.office, "زبون مُدار", managed_tenant=cls.managed_book)
        other_company = create_company("شركة مرتبطة ٥٨", cls.office_manager)
        cls.engagement = AccountantEngagement.objects.create(
            accountant=cls.office_manager, tenant=other_company,
            status="active", initiated_by="accountant",
        )
        cls.engaged_client = make_client(cls.office, "زبون مرتبط", engagement=cls.engagement)
        # أتعاب في دفتر المكتب نفسه — غير محصّلة جزئياً.
        _fee_invoice(cls.office, cls.currency, "FEE-58-1", grand_total=Decimal("500.00"),
                     amount_paid=Decimal("200.00"))
        # فاتورة مبيعات داخل دفتر العميل **المُدار** — ليست أتعاباً للمكتب، ويجب ألّا تظهر.
        _fee_invoice(cls.managed_book, cls.currency, "BOOK-SALE-1", grand_total=Decimal("9000.00"))

    def test_client_list_reports_derived_book_state(self):
        response = api_for(self.office_manager).get(BASE)
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["id"]: row for row in response.json()["clients"]}
        self.assertEqual(rows[self.unlinked_client.pk]["client_type"], "unlinked")
        self.assertEqual(rows[self.managed_client.pk]["client_type"], "managed")
        self.assertEqual(rows[self.engaged_client.pk]["client_type"], "engaged")

    def test_deadlines_section_present(self):
        response = api_for(self.office_manager).get(BASE)
        self.assertIn("deadlines", response.json())
        self.assertIn("items", response.json()["deadlines"])

    def test_unpaid_fees_come_from_the_offices_own_book_only(self):
        response = api_for(self.office_manager).get(BASE)
        fees = response.json()["unpaid_fees"]
        numbers = {row["invoice_number"] for row in fees["invoices"]}
        self.assertIn("FEE-58-1", numbers)
        self.assertNotIn("BOOK-SALE-1", numbers)
        self.assertEqual(fees["total"], "300.00")


class PracticeDashboardStaffAccessTest(APITestCase):
    """القرار 7: موظفٌ بلا ملف محاسب يرى عملاءه المُسنَدين فقط — لا 404، ولا الكل.

    الإسناد بعضوية `UserCompanyMembership` على دفتر العميل **المُدار** نفسه —
    نفس آلية ISSUE #52، لا حقل تعيين ثالث. زبونٌ بلا دفتر مُدار لا سبيل
    لإسناده هكذا، فيبقى ظاهراً لصاحب المكتب وحده.
    """

    @classmethod
    def setUpTestData(cls):
        cls.office_manager = make_office("office-58-staff-mgr", "TAX-58-STAFF-MGR")
        cls.office = create_company("مكتب المحاسبة ٥٨-٣", cls.office_manager)

        cls.managed_books = [
            create_company(f"دفتر عميل مُدار ٥٨-{i}", cls.office_manager, managed_by=cls.office)
            for i in range(3)
        ]
        cls.managed_clients = [
            make_client(cls.office, f"زبون مُدار {i}", managed_tenant=cls.managed_books[i])
            for i in range(3)
        ]
        # ثلاثة زبائن بلا دفترٍ مُدار — لا سبيل لإسنادهم لموظف عبر عضوية دفتر.
        cls.unlinked_clients = [
            make_client(cls.office, f"زبون خارجي {i}") for i in range(3)
        ]

        cls.staff = User.objects.create_user("office-58-staff", email="staff58@example.com")
        # الموظف عضوٌ في اثنين من الدفاتر الثلاثة المُدارة — أُسنِد إليهما فقط.
        for book in cls.managed_books[:2]:
            UserCompanyMembership.objects.create(user=cls.staff, tenant=book, role="staff")

        cls.unassigned_staff = User.objects.create_user(
            "office-58-unassigned", email="unassigned58@example.com",
        )

        # مكتب آخر تماماً — موظفه لا يرى شيئاً من مكتبنا رغم عضويته على دفترٍ مُدار.
        cls.other_office_manager = make_office("office-58-other-mgr", "TAX-58-OTHER-MGR")
        cls.other_office = create_company("مكتب آخر ٥٨", cls.other_office_manager)
        cls.other_book = create_company(
            "دفتر مكتبٍ آخر ٥٨", cls.other_office_manager, managed_by=cls.other_office,
        )
        cls.other_staff = User.objects.create_user(
            "office-58-other-staff", email="otherstaff58@example.com",
        )
        UserCompanyMembership.objects.create(user=cls.other_staff, tenant=cls.other_book, role="staff")

    def test_assigned_staff_sees_exactly_their_assigned_clients(self):
        response = api_for(self.staff).get(BASE)
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()["clients"]
        self.assertEqual(
            {row["id"] for row in rows},
            {client.pk for client in self.managed_clients[:2]},
        )

    def test_unassigned_staff_sees_none(self):
        response = api_for(self.unassigned_staff).get(BASE)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["clients"], [])

    def test_manager_still_sees_all_six(self):
        response = api_for(self.office_manager).get(BASE)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["clients"]), 6)

    def test_staff_of_another_office_sees_nothing_from_this_office(self):
        response = api_for(self.other_staff).get(BASE)
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()["clients"]
        ids = {client.pk for client in self.managed_clients + self.unlinked_clients}
        self.assertFalse(any(row["id"] in ids for row in rows))

    def test_staff_query_count_does_not_grow_with_assigned_client_count(self):
        api = api_for(self.staff)
        api.get(BASE)  # إحماء أي كاش لكل عملية
        with CaptureQueriesContext(connection) as small:
            small_response = api.get(BASE)
        self.assertEqual(len(small_response.json()["clients"]), 2)

        extra_books = [
            create_company(f"دفتر إضافي ٥٨-{i}", self.office_manager, managed_by=self.office)
            for i in range(7)
        ]
        for i, book in enumerate(extra_books):
            make_client(self.office, f"زبون إضافي {i}", managed_tenant=book)
            UserCompanyMembership.objects.create(user=self.staff, tenant=book, role="staff")

        with CaptureQueriesContext(connection) as big:
            big_response = api.get(BASE)
        self.assertEqual(len(big_response.json()["clients"]), 9)
        self.assertEqual(
            len(big.captured_queries), len(small.captured_queries),
            f"عدد استعلامات لوحة الموظف كبر بعدد عملائه: {len(small.captured_queries)} ⇒ "
            f"{len(big.captured_queries)}",
        )
