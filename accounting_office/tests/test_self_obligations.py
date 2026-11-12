"""التزامُ المكتب «من المنصة» وبيانُ أسماء الزبائن (م111) — #290 (§ج).

**ما يثبّته هذا الملفّ:**

- **لائحةٌ ثابتةٌ في الكود لا صفوفُ منصّة**: مكتبٌ نظامُه `PS` يُولَّد له بندٌ واحد
  `client-names-report` موعدُه **31 آذار من السنة اللاحقة**، وفترتُه سنةٌ ميلادية
  كاملة. ومكتبُ `IL` **لا صفَّ له** — البندُ فلسطينيٌّ بنصّه.
- **`get_or_create` على المفتاح الطبيعيّ**: تشغيلُ اليوم نفسه مرّتين لا يُكرّر.
- **«قُدِّم» نهائيٌّ**: يسجّل التاريخ والحالة، والثاني يُرفض 400 برسالته.
- **الكتابةُ لدورٍ في `ENTRY_APPROVER_ROLES` وحدها**: المحاسبُ والمراقبُ 403،
  وكذلك التصديرُ الكاملُ وبيانُ الأسماء (حارسُ المالك نفسه).
- **ولا يمسّ شيئاً قائماً**: عدّاداتُ الزبائن والأوراق و«للإدخال» تتغيّر بصفر —
  القرارُ المحسوم: **سجلٌّ مستقلّ**، ولا يتحوّل المكتب زبوناً عند نفسه.
- **بيانُ الأسماء لمكتب `PS` وحده**: `IL` يردّ 400 برسالته، والرابطُ يعرض أسماء
  الزبائن وأرقام ملفاتهم وعناوين أطرافهم.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office import client_books, services
from accounting_office.models import (
    DocumentChecklistItem,
    OfficeClient,
    OfficeSelfObligation,
    TaxCard,
)
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.modules import invalidate_module_cache
from partners.models import Partner
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
SELF_OBLIGATIONS = f"{BASE}self-obligations/"
EXPORT_FULL = f"{BASE}exports/full/"
EXPORT_CLIENT_NAMES = f"{BASE}exports/client-names/"

THIS_YEAR = timezone.localdate().year
DAY = datetime.date(THIS_YEAR, 6, 10)
#: الفترةُ التي يتوقّعها الاختبار: سنةُ اليوم كاملةً، وموعدُها آذارُ اللاحقة.
PERIOD_START = datetime.date(THIS_YEAR, 1, 1)
PERIOD_END = datetime.date(THIS_YEAR, 12, 31)
DUE_ON = datetime.date(THIS_YEAR + 1, 3, 31)

RULE_CODE = "client-names-report"
RULE_NAME = "أسماء زبائن المكتب وعناوينهم (م111)"


class SelfObligationsTestCase(APITestCase):
    """مكتبٌ فلسطينيٌّ بمالكٍ ومديرِ مكتبٍ ومحاسبٍ ومراقب، ومكتبٌ إسرائيليٌّ ثانٍ."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()

        cls.owner = User.objects.create_user(username="so_owner", password="x")
        cls.tenant = create_company(
            "مكتب بيان الأسماء", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "PS")
        cls.catalog = catalog(cls.tenant)

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role,
            )
            return user

        cls.office_manager = member("so_office_manager", "office_manager")
        cls.accountant = member("so_accountant", "accountant")
        cls.viewer = member("so_viewer", "viewer")

        cls.owner_il = User.objects.create_user(username="so_owner_il", password="x")
        cls.tenant_il = create_company(
            "مكتب إسرائيليّ للبيان", cls.owner_il, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant_il.pk)
        ready_office(cls.tenant_il, "IL")
        cls.catalog_il = catalog(cls.tenant_il)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.client_record = self.make_client(self.tenant, "زبون البيان")

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    # ── أفعالٌ مشتركة ────────────────────────────────────────────────────
    def make_client(self, tenant, name, *, tax_file_number="", partner=None, responsible=None):
        client = OfficeClient.objects.create(
            tenant=tenant, name=name,
            responsible=responsible or self.owner,
            tax_file_number=tax_file_number, partner=partner,
        )
        TaxCard.objects.create(
            client=client, vat_classification="authorized",
            annual_sales=Decimal("0"),
        )
        return client

    def refresh(self, *, tenant=None, day=DAY):
        return services.refresh_office(tenant or self.tenant, day=day)

    def rows(self):
        res = self.client.get(SELF_OBLIGATIONS, **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        return res.data["rows"]

    def only_row(self):
        row, = OfficeSelfObligation.objects.filter(tenant=self.tenant)
        return row

    def submit(self, pk, *, body=None, expect=200, user=None, tenant=None):
        if user is not None:
            self.as_user(user)
        res = self.client.post(
            f"{SELF_OBLIGATIONS}{pk}/submit/", body or {}, format="json",
            **self.headers(tenant=tenant),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res

    def dismiss(self, pk, *, body=None, expect=200, user=None):
        if user is not None:
            self.as_user(user)
        res = self.client.post(
            f"{SELF_OBLIGATIONS}{pk}/dismiss/", body or {}, format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, expect, res.content)
        return res


class GenerationTest(SelfObligationsTestCase):
    """لائحةٌ ثابتة: بندٌ واحد لمكتب `PS`، ولا شيء لمكتب `IL`. """

    def test_a_palestinian_office_gets_one_row_due_on_march_31_of_next_year(self):
        result = self.refresh()
        row = self.only_row()

        self.assertEqual(result["created_self_obligations"], 1)
        self.assertEqual(row.rule_code, RULE_CODE)
        self.assertEqual(row.name, RULE_NAME)
        self.assertEqual(row.period_start, PERIOD_START)
        self.assertEqual(row.period_end, PERIOD_END)
        self.assertEqual(row.due_on, DUE_ON)
        self.assertEqual(row.status, OfficeSelfObligation.STATUS_PENDING)

    def test_an_israeli_office_gets_no_row_at_all(self):
        self.refresh(tenant=self.tenant_il)

        self.assertEqual(
            OfficeSelfObligation.objects.filter(tenant=self.tenant_il).count(), 0,
        )

    def test_running_the_refresh_twice_does_not_duplicate_the_row(self):
        self.refresh()
        self.refresh()
        self.refresh(day=DAY + datetime.timedelta(days=1))

        self.assertEqual(
            OfficeSelfObligation.objects.filter(tenant=self.tenant).count(), 1,
        )

    def test_the_due_date_moves_to_the_next_year_after_march_ends(self):
        """موعدُ 31/3 من السنة اللاحقة: بعد انقضائه تُولَّد سنةٌ جديدة، لا تُعاد."""
        self.refresh()
        next_april = datetime.date(THIS_YEAR + 1, 4, 1)

        self.refresh(day=next_april)

        rows = OfficeSelfObligation.objects.filter(tenant=self.tenant)
        self.assertEqual(rows.count(), 2)
        self.assertIn(
            datetime.date(THIS_YEAR + 1, 1, 1),
            set(rows.values_list("period_start", flat=True)),
        )

    def test_the_row_is_served_to_every_member_with_its_derived_fields(self):
        self.refresh()
        self.as_user(self.accountant)
        row, = self.rows()

        self.assertEqual(row["rule_code"], RULE_CODE)
        self.assertEqual(row["source"], "platform")
        self.assertEqual(row["source_label"], "المنصة")
        self.assertEqual(row["status_label"], "بالانتظار")
        self.assertEqual(row["due_on"], DUE_ON.isoformat())
        self.assertEqual(row["days_left"], (DUE_ON - timezone.localdate()).days)
        self.assertIs(row["is_late"], False)

    def test_a_passed_due_date_is_late_and_never_stored(self):
        self.refresh()
        row = self.only_row()
        row.due_on = timezone.localdate() - datetime.timedelta(days=2)
        row.save(update_fields=["due_on"])

        payload_row, = self.rows()

        self.assertIs(payload_row["is_late"], True)
        self.assertEqual(payload_row["days_left"], -2)


class StatusTest(SelfObligationsTestCase):
    """«قُدِّم» و«غير مطلوب» — والثاني يمكن ثمّ يُعاد؟ لا: الحالةُ نهائيةٌ كالالتزام."""

    def setUp(self):
        super().setUp()
        self.refresh()
        self.row = self.only_row()

    def test_submitting_records_the_date_and_the_status_once(self):
        self.submit(
            self.row.pk,
            body={"submitted_on": "2027-03-15", "note": "سُلِّم في الدائرة"},
        )

        self.row.refresh_from_db()
        self.assertEqual(self.row.status, OfficeSelfObligation.STATUS_SUBMITTED)
        self.assertEqual(self.row.submitted_on, datetime.date(2027, 3, 15))
        self.assertEqual(self.row.note, "سُلِّم في الدائرة")

        again = self.submit(self.row.pk, expect=400)
        self.assertIn("قُدِّم", again.content.decode("utf-8"))

    def test_dismissing_marks_it_not_required_without_a_submission_date(self):
        res = self.dismiss(self.row.pk, body={"note": "لا زبائنَ في هذه السنة"})

        self.row.refresh_from_db()
        self.assertEqual(self.row.status, OfficeSelfObligation.STATUS_NOT_REQUIRED)
        self.assertIsNone(self.row.submitted_on)
        self.assertEqual(self.row.note, "لا زبائنَ في هذه السنة")
        self.assertEqual(res.data["status_label"], "غير مطلوب")

    def test_an_empty_body_is_accepted_and_leaves_the_note_empty(self):
        self.submit(self.row.pk, body={"submitted_on": None, "note": ""})

        self.row.refresh_from_db()
        self.assertEqual(self.row.status, OfficeSelfObligation.STATUS_SUBMITTED)
        self.assertEqual(self.row.note, "")
        self.assertEqual(self.row.submitted_on, timezone.localdate())


class WritePermissionTest(SelfObligationsTestCase):
    """الكتابةُ لدورٍ في `ENTRY_APPROVER_ROLES` وحدها — 403 لغيره، والقراءةُ للجميع."""

    def setUp(self):
        super().setUp()
        self.refresh()
        self.row = self.only_row()

    def test_a_plain_accountant_cannot_write(self):
        self.submit(self.row.pk, expect=403, user=self.accountant)
        self.dismiss(self.row.pk, expect=403, user=self.accountant)

        self.row.refresh_from_db()
        self.assertEqual(self.row.status, OfficeSelfObligation.STATUS_PENDING)

    def test_a_viewer_cannot_write(self):
        self.submit(self.row.pk, expect=403, user=self.viewer)

    def test_the_office_manager_can_write(self):
        self.submit(self.row.pk, user=self.office_manager)

        self.row.refresh_from_db()
        self.assertEqual(self.row.status, OfficeSelfObligation.STATUS_SUBMITTED)

    def test_the_write_permission_does_not_open_the_full_export(self):
        self.submit(self.row.pk, user=self.office_manager)

        self.as_user(self.accountant)
        res = self.client.post(
            EXPORT_FULL, {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 403, res.content)


class UntouchedSurfacesTest(SelfObligationsTestCase):
    """**لا يتحوّل المكتب زبوناً عند نفسه**: العدّاداتُ القائمةُ تتغيّر بصفر."""

    def counters(self):
        accountant = self.accountant
        return {
            "clients": services.visible_clients(self.tenant, accountant).count(),
            "documents": DocumentChecklistItem.objects.filter(
                tenant=self.tenant,
            ).count(),
            "pending": client_books.pending_entry_payload(
                self.tenant, accountant, day=DAY,
            )["total"],
        }

    def test_generating_and_submitting_changes_no_existing_counter(self):
        before = self.counters()

        self.refresh()
        self.submit(self.only_row().pk, user=self.office_manager)

        self.assertEqual(self.counters(), before)

    def test_the_office_never_becomes_a_client_of_itself(self):
        self.refresh()
        self.submit(self.only_row().pk)

        self.assertEqual(
            list(
                OfficeClient.objects.filter(tenant=self.tenant)
                .values_list("name", flat=True),
            ),
            ["زبون البيان"],
        )


class ClientNamesReportTest(SelfObligationsTestCase):
    """بيانُ الأسماء (م111): مكتبٌ فلسطينيٌّ وحده، وحارسُ المالك نفسه."""

    def share_of(self, doc_type):
        from docshare.models import DocumentShare

        return DocumentShare.objects.get(tenant=self.tenant, doc_type=doc_type)

    def test_a_palestinian_office_gets_a_link_with_names_and_addresses(self):
        from docshare.models import DOC_OFFICE_CLIENT_NAMES

        partner = Partner.objects.create(
            tenant=self.tenant, name="شركة البيان", street_address="شارع النصر 12",
            city="نابلس",
        )
        self.make_client(
            self.tenant, "زبون بعنوان", tax_file_number="512345678", partner=partner,
        )

        res = self.client.post(
            EXPORT_CLIENT_NAMES, {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

        share = self.share_of(DOC_OFFICE_CLIENT_NAMES)
        page = self.client.get(f"/api/share/{share.token}/")
        self.assertEqual(page.status_code, 200)
        body = page.content.decode("utf-8")

        self.assertIn("زبون البيان", body)
        self.assertIn("زبون بعنوان", body)
        self.assertIn("512345678", body)
        self.assertIn("نابلس", body)

    def test_the_names_report_leaks_no_client_of_another_office(self):
        from docshare.models import DOC_OFFICE_CLIENT_NAMES

        self.make_client(
            self.tenant_il, "زبون المكتب الثاني", responsible=self.owner_il,
        )

        res = self.client.post(
            EXPORT_CLIENT_NAMES, {}, format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

        share = self.share_of(DOC_OFFICE_CLIENT_NAMES)
        page = self.client.get(f"/api/share/{share.token}/")

        self.assertNotIn("زبون المكتب الثاني", page.content.decode("utf-8"))

    def test_an_israeli_office_is_refused_with_400(self):
        self.as_user(self.owner_il)

        res = self.client.post(
            EXPORT_CLIENT_NAMES, {}, format="json",
            **self.headers(tenant=self.tenant_il),
        )

        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("فلسطيني", res.content.decode("utf-8"))

    def test_the_names_report_is_owner_only(self):
        first = self.client.post(
            EXPORT_CLIENT_NAMES, {}, format="json", **self.headers(),
        )
        self.assertEqual(first.status_code, 201, first.content)

        self.as_user(self.office_manager)
        # مديرُ المكتب يملكه — الحارسُ دورٌ لا مفتاح (كالتصدير الكامل).
        allowed = self.client.post(
            EXPORT_CLIENT_NAMES, {}, format="json", **self.headers(),
        )
        self.assertEqual(allowed.status_code, 201, allowed.content)
        self.assertEqual(allowed.data["url"], first.data["url"])

        self.as_user(self.accountant)
        refused = self.client.post(
            EXPORT_CLIENT_NAMES, {}, format="json", **self.headers(),
        )
        self.assertEqual(refused.status_code, 403)
