"""نقاطُ الجرس — #276.

**ما يثبته هذا الملف:**

1. **كلُّ عضوٍ يرى تنبيهاته هو فقط** — لا مفتاحَ إضافياً ولا `?user=`.
2. **تنبيهُ غيرك 404** على `alerts/<id>/seen/`، وتنبيهُ مكتبٍ آخر 404 كذلك.
3. **«شفته» يُنقص العدّاد، و«شفتهم كلهم» يُصفّره** ويُرجع العددَ المكتوب.
4. **قراءةٌ ثابتةُ الكلفة**: عددُ استعلامات `GET alerts/` لا يكبر بعدد الصفوف.
"""
import datetime
from unittest import mock

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting_office import services
from accounting_office.models import (
    DeadlineRule,
    Obligation,
    OfficeAlert,
    OfficeRefreshRun,
)
from accounting_office.tests.test_alerts import add_obligation_row, office_client_without_periods
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
ALERTS = f"{BASE}alerts/"

DAY = datetime.date(2026, 2, 12)


class AlertsApiTestCase(APITestCase):
    """مكتبٌ بلائحته: صاحبُ المكتب، ومحاسبان بزبونٍ لكلٍّ، ومكتبٌ ثانٍ للعزل."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="aa_owner", password="x")
        cls.tenant = create_company(
            "مكتب الجرس", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        catalog(cls.tenant)

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role,
            )
            return user

        cls.accountant = member("aa_accountant", "accountant")
        cls.colleague = member("aa_colleague", "accountant")
        cls.mine = office_client_without_periods(
            cls.tenant, "زبون المحاسب", responsible=cls.accountant,
        )
        cls.other = office_client_without_periods(
            cls.tenant, "زبون الزميل", responsible=cls.colleague,
        )
        cls.rule = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_periodic",
        )

        # مكتبٌ ثانٍ مرخَّص — لعزل الكائنات المرجعية. وصاحبُ هذا المكتب **عضوٌ فيه
        # أيضاً** ومستلِمُ تنبيهاته، فلا يفصل بين الجرسين إلا شركةُ الصفّ.
        cls.outside_owner = User.objects.create_user(username="aa_outside", password="x")
        cls.outside = create_company(
            "مكتب الجرس الآخر", cls.outside_owner, template="accounting_office",
        )
        invalidate_module_cache(cls.outside.pk)
        ready_office(cls.outside, "IL")
        catalog(cls.outside)
        UserCompanyMembership.objects.create(
            user=cls.owner, tenant=cls.outside, role="accountant",
        )
        cls.outside_client = office_client_without_periods(
            cls.outside, "زبون المكتب الآخر", responsible=cls.owner,
        )

    def setUp(self):
        OfficeAlert.objects.all().delete()
        Obligation.objects.all().delete()
        # «اليوم» الذي تقرؤه الـviews هو `DAY` لا يومُ الساعة: وإلا ولّد فتحُ الجرس
        # فتراتِ الأشهر الماضية كلَّها فتكبر الصفوفُ بما لم يُزرَع في الاختبار.
        patcher = mock.patch(
            "accounting_office.views.timezone.localdate", return_value=DAY,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # ويومُ الاختبار مسجَّلٌ مُسبقاً: فتحُ الجرس فيه استعلامُ وجودٍ واحد لا تشغيلٌ
        # كامل، فيقيس اختبارُ الكلفة القراءةَ وحدَها. (اختبارُ التشغيل يمسح السجلّ.)
        services.ensure_office_refreshed(self.tenant, day=DAY)

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def add_overdue(self, client, rule=None, offset=3, internal_offset=10):
        return add_obligation_row(
            tenant=self.tenant,
            client=client,
            rule=rule or self.rule,
            actual=DAY - datetime.timedelta(days=offset),
            internal=DAY - datetime.timedelta(days=internal_offset),
        )

    def generate(self, tenant=None):
        return services._generate_late_alerts(tenant or self.tenant, day=DAY)

    def bell(self, tenant=None):
        return self.client.get(ALERTS, **self.headers(tenant))


class AlertsListTest(AlertsApiTestCase):
    def test_the_bell_returns_only_my_alerts_with_the_agreed_shape(self):
        self.add_overdue(self.mine)
        self.add_overdue(self.other)
        self.generate()
        self.as_user(self.accountant)

        res = self.bell()

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(set(res.data), {"unseen", "rows"})
        mine = OfficeAlert.objects.filter(recipient=self.accountant)
        self.assertEqual(len(res.data["rows"]), mine.count())
        self.assertEqual(res.data["unseen"], mine.count())
        row = res.data["rows"][0]
        self.assertEqual(
            set(row),
            {
                "id", "kind", "kind_label", "badge", "message", "client",
                "task_id", "obligation_id", "day", "seen", "created_at",
            },
        )
        self.assertFalse(row["seen"])

    def test_an_anonymous_request_is_401(self):
        self.assertEqual(self.client.get(ALERTS).status_code, 401)

    def test_an_unlicensed_office_is_404(self):
        plain_owner = User.objects.create_user(username="aa_plain", password="x")
        plain = create_company("شركة عامة", plain_owner)
        invalidate_module_cache(plain.pk)
        self.client.force_authenticate(user=plain_owner)

        res = self.bell(plain)

        self.assertEqual(res.status_code, 404, res.content)

    def test_opening_the_bell_refreshes_the_office_without_the_today_screen(self):
        """الجرسُ لا يعتمد على أن يفتح أحدٌ «اليوم»: cron فاتَه يومٌ ⇒ يلحقه الفتح."""
        OfficeRefreshRun.objects.filter(tenant=self.tenant).delete()
        obligation = self.add_overdue(self.mine)
        self.as_user(self.accountant)
        self.assertFalse(OfficeAlert.objects.exists())

        res = self.bell()

        self.assertEqual(res.status_code, 200, res.content)
        self.assertIn(
            obligation.pk, {row["obligation_id"] for row in res.data["rows"]},
            "فتحُ الجرس لم يولّد تنبيهَ التزامٍ متأخّر — التوليدُ معلّقٌ بشاشة «اليوم»",
        )
        self.assertTrue(
            OfficeRefreshRun.objects.filter(tenant=self.tenant, day=DAY).exists(),
        )

    def test_the_query_count_does_not_grow_with_the_rows(self):
        self.add_overdue(self.mine)
        self.generate()
        self.as_user(self.accountant)

        with CaptureQueriesContext(connection) as one:
            self.assertEqual(len(self.bell().data["rows"]), 2)
        for index in range(4):
            add_obligation_row(
                tenant=self.tenant,
                client=self.mine,
                rule=self.rule,
                actual=DAY - datetime.timedelta(days=5 + index),
                internal=DAY - datetime.timedelta(days=12 + index),
                period_start=datetime.date(2025, 1, 1) + datetime.timedelta(days=31 * index),
                period_end=datetime.date(2025, 1, 28) + datetime.timedelta(days=31 * index),
            )
        self.generate()
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(len(self.bell().data["rows"]), 10)

        self.assertEqual(
            len(many.captured_queries), len(one.captured_queries),
            "عددُ استعلامات `GET alerts/` كبر بعدد الصفوف",
        )


class SeenTest(AlertsApiTestCase):
    def setUp(self):
        super().setUp()
        self.add_overdue(self.mine)
        self.generate()
        self.as_user(self.accountant)

    def test_seen_marks_the_row_and_lowers_the_counter(self):
        before = self.bell().data
        alert = before["rows"][0]

        res = self.client.post(
            f"{ALERTS}{alert['id']}/seen/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.data["seen"])
        self.assertEqual(res.data["id"], alert["id"])
        after = self.bell().data
        self.assertEqual(after["unseen"], before["unseen"] - 1)

        again = self.client.post(
            f"{ALERTS}{alert['id']}/seen/", {}, format="json", **self.headers(),
        )
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(self.bell().data["unseen"], before["unseen"] - 1)

    def test_seen_all_returns_the_count_and_zeroes_the_counter(self):
        total = self.bell().data["unseen"]

        res = self.client.post(f"{ALERTS}seen-all/", {}, format="json", **self.headers())

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data, {"seen": total})
        self.assertEqual(self.bell().data["unseen"], 0)

    def test_someone_elses_alert_is_404(self):
        owners_alert = OfficeAlert.objects.filter(recipient=self.owner).first()

        res = self.client.post(
            f"{ALERTS}{owners_alert.pk}/seen/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 404, res.content)
        owners_alert.refresh_from_db()
        self.assertIsNone(owners_alert.seen_at, "«شفته» على تنبيه غيري كتب فيه")

    def test_another_office_alert_is_404_and_never_listed(self):
        """تنبيهُ المكتب الآخر **للمستخدم نفسِه وبلا زبون** — فالفاصلُ `tenant` وحده.

        `SeenTest` يفتح بالمسؤول (المحاسب)، فيُبدَّل هنا إلى صاحب المكتب لأنّه هو
        مستلِمُ التنبيهِ الأجنبيّ: مطابقةُ `recipient` وحدها كانت تُمرّر التنبيهَ لو
        غاب فلترُ `tenant`. والتنبيهُ بلا زبون يمرّ من شرط `client__isnull=True`
        في `_visible_alerts`، ونوعُه خارج `RESOLVED_ALERT_KINDS` فلا يُسقطه المحسوم.
        """
        self.as_user(self.owner)
        foreign = OfficeAlert.objects.create(
            tenant=self.outside,
            recipient=self.owner,
            kind="future_kind",
            ref_key="future:1",
            message="نوعٌ لاحقٌ بلا زبون",
            day=DAY,
        )

        listed = self.bell().data
        seen = self.client.post(
            f"{ALERTS}{foreign.pk}/seen/", {}, format="json", **self.headers(),
        )

        self.assertEqual(seen.status_code, 404, seen.content)
        self.assertNotIn(
            foreign.pk, {row["id"] for row in listed["rows"]},
            "تنبيهُ مكتبٍ آخر ظهر في هذا الجرس",
        )
        foreign.refresh_from_db()
        self.assertIsNone(foreign.seen_at)


class ResolvedRowsTest(AlertsApiTestCase):
    def test_a_submitted_obligation_leaves_the_bell_at_read_time(self):
        obligation = self.add_overdue(self.mine)
        self.generate()
        self.as_user(self.owner)
        # الأصفرُ للمسؤول (المحاسب) وحده، والأحمرُ يبلغ صاحبَ المكتب أيضاً.
        self.assertEqual(len(self.bell().data["rows"]), 1)

        submitted = self.client.post(
            f"{BASE}obligations/{obligation.pk}/submit/", {}, format="json",
            **self.headers(),
        )
        self.assertEqual(submitted.status_code, 200, submitted.content)

        res = self.bell()
        self.assertEqual(res.data["rows"], [])
        self.assertEqual(res.data["unseen"], 0)
        self.assertEqual(OfficeAlert.objects.count(), 3)
        self.assertEqual(
            Obligation.objects.filter(pk=obligation.pk).values_list("status", flat=True)[0],
            Obligation.STATUS_SUBMITTED,
        )
