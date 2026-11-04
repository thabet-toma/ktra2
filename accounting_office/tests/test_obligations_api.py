"""نقاطُ الالتزامات والشغلات وشاشة «اليوم» — #275.

**ما يثبته هذا الملف:**

1. **الرؤيةُ من `visible_clients` وحدها**: المحاسبُ يرى زبائنه ومن حُوِّلت له
   شغلتُه، وزبونُ غيره **404** على كل فعل — لا 403 يُثبت وجوده.
2. **المبلغُ مبلغ**: بلا `office.amounts.view` يصل `null`، وكتابتُه **403**.
3. **العدّاداتُ قبل الفلتر**: تُحسب على كل الميل المحفوظ المُنتظِر، ثم يقصّ الفلتر.
4. **عزلُ المكاتب** في كل كائنٍ مرجعيّ، والترخيصُ 404 (يحرسه الحارسُ المعمَّم).
5. **قراءةٌ ثابتة الكلفة**: عددُ استعلامات `today/` لا يكبر بعدد الصفوف.
6. **التشغيلُ اليوميّ مرّة**: `GET today/` مرّتين في اليوم نفسه ⇒ سجلُّ تحديثٍ واحد.
"""
import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office import services
from accounting_office.models import (
    DeadlineRule,
    Obligation,
    OfficeClient,
    OfficeRefreshRun,
    PeriodTask,
    TaxCard,
)
from accounting_office.tests.test_obligations import (
    catalog,
    ready_office,
    seed_deadline_schedules,
    seed_published_thresholds,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency, MemberPermission, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
TODAY = f"{BASE}today/"
OBLIGATIONS = f"{BASE}obligations/"
TASKS = f"{BASE}tasks/"
CLIENTS = f"{BASE}clients/"

JAN_START = datetime.date(2026, 1, 1)
JAN_END = datetime.date(2026, 1, 31)
FEB_START = datetime.date(2026, 2, 1)
FEB_END = datetime.date(2026, 2, 28)
TODAY_DAY = timezone.localdate()


class ObligationApiTestCase(APITestCase):
    """مكتبٌ مرخَّص بمالكه ومحاسبَين، وزبونٌ لكل محاسب، ومكتبٌ ثانٍ للعزل."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        seed_published_thresholds()
        seed_deadline_schedules()
        cls.owner = User.objects.create_user(username="oa_owner", password="x")
        cls.tenant = create_company(
            "مكتب يوم الـAPI", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        ready_office(cls.tenant, "IL")
        cls.catalog = catalog(cls.tenant)

        def member(username, role):
            user = User.objects.create_user(username=username, password="x")
            UserCompanyMembership.objects.create(
                user=user, tenant=cls.tenant, role=role,
            )
            return user

        cls.accountant = member("oa_accountant", "accountant")
        cls.colleague = member("oa_colleague", "accountant")

        def make(name, responsible):
            client = OfficeClient.objects.create(
                tenant=cls.tenant, name=name, responsible=responsible,
            )
            TaxCard.objects.create(
                client=client, vat_classification="authorized",
                annual_sales=Decimal("0"),
            )
            services.add_client_service(
                client=client, service=cls.catalog["vat"],
                starts_on=JAN_START, responsible_from=JAN_START, frequency="monthly",
            )
            return client

        cls.mine = make("زبون المحاسب", cls.accountant)
        cls.other = make("زبون الزميل", cls.colleague)
        cls.rule = DeadlineRule.objects.get(
            schedule__tax_system="IL", schedule__year=2026, code="il_vat_periodic",
        )

        # مكتبٌ ثانٍ مرخَّص — لعزل الكائنات المرجعية.
        cls.outside_owner = User.objects.create_user(username="oa_outside", password="x")
        cls.outside = create_company(
            "مكتب آخر", cls.outside_owner, template="accounting_office",
        )
        invalidate_module_cache(cls.outside.pk)
        ready_office(cls.outside, "IL")
        outside_catalog = catalog(cls.outside)
        cls.outside_client = OfficeClient.objects.create(
            tenant=cls.outside, name="زبون المكتب الآخر", responsible=cls.outside_owner,
        )
        TaxCard.objects.create(
            client=cls.outside_client, vat_classification="authorized",
            annual_sales=Decimal("0"),
        )
        services.add_client_service(
            client=cls.outside_client, service=outside_catalog["vat"],
            starts_on=JAN_START, responsible_from=JAN_START, frequency="monthly",
        )

    def setUp(self):
        # سجلُّ تحديث اليوم يُثبَّت أوّلاً ثم تُمحى صفوفُه: كلُّ اختبارٍ يبني ما
        # يفحصه بيومه الصريح، ولا يضيف محرّكُ «اليوم» صفوفاً تحت قدميه.
        Obligation.objects.all().delete()
        PeriodTask.objects.all().delete()
        OfficeRefreshRun.objects.all().delete()
        services.ensure_office_refreshed(self.tenant, day=TODAY_DAY)
        Obligation.objects.all().delete()
        PeriodTask.objects.all().delete()

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def add_obligation(
        self, client, *, actual, status=Obligation.STATUS_PENDING,
        amount=None, direction="", rule_code="il_vat_periodic",
        name="דוח תקופתי למע\"מ", internal=None, assignee=None,
        period_start=JAN_START, period_end=JAN_END,
    ):
        """صفٌّ محفوظٌ بيومه الصريح — لا ساعةَ ولا محرّك."""
        task = PeriodTask.objects.create(
            tenant=client.tenant,
            client=client,
            client_service=client.services.get(),
            period_start=period_start,
            period_end=period_end,
            internal_deadline=internal or actual,
            assignee=assignee,
        )
        return Obligation.objects.create(
            tenant=client.tenant,
            client=client,
            client_service_id=task.client_service_id,
            task=task,
            rule=self.rule,
            rule_code=rule_code,
            name=name,
            period_start=period_start,
            period_end=period_end,
            legal_date=actual,
            official_date=actual,
            actual_deadline=actual,
            internal_deadline=internal or actual,
            status=status,
            amount=amount,
            direction=direction,
        )

    def today(self, **query):
        return self.client.get(TODAY, dict(query), **self.headers())


class TodayApiTest(ObligationApiTestCase):
    def test_an_accountant_sees_only_his_clients_rows(self):
        self.add_obligation(self.mine, actual=TODAY_DAY - datetime.timedelta(days=10))
        self.add_obligation(self.other, actual=TODAY_DAY - datetime.timedelta(days=9))
        self.as_user(self.accountant)

        res = self.today()

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            {row["client"]["id"] for row in res.data["rows"]}, {self.mine.pk},
        )

    def test_the_amount_arrives_null_without_the_amounts_key_and_writing_is_403(self):
        obligation = self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=10),
            amount=Decimal("620"), direction="due",
        )
        self.as_user(self.accountant)

        res = self.today()

        self.assertIsNone(res.data["rows"][0]["amount"])
        write = self.client.post(
            f"{OBLIGATIONS}{obligation.pk}/amount/",
            {"amount": "50", "direction": "due"}, format="json", **self.headers(),
        )
        self.assertEqual(write.status_code, 403, write.content)
        obligation.refresh_from_db()
        self.assertEqual(obligation.amount, Decimal("620"))

    def test_the_amount_is_written_by_a_member_who_sees_it(self):
        obligation = self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=10),
        )
        self.as_user(self.owner)

        res = self.client.post(
            f"{OBLIGATIONS}{obligation.pk}/amount/",
            {"amount": "620", "direction": "due"}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["amount"], "620.00")
        self.assertEqual(res.data["direction"], "due")
        self.assertEqual(res.data["direction_label"], "عليه")

    def test_submit_and_not_required_and_reopen_from_the_api(self):
        obligation = self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=10),
        )
        self.as_user(self.owner)
        url = f"{OBLIGATIONS}{obligation.pk}"

        submitted = self.client.post(
            f"{url}/submit/",
            {"submitted_on": JAN_END.isoformat(), "number": "9"},
            format="json", **self.headers(),
        )
        self.assertEqual(submitted.status_code, 200, submitted.content)
        self.assertEqual(submitted.data["status"], Obligation.STATUS_SUBMITTED)
        self.assertEqual(submitted.data["status_label"], "انقدّم")
        obligation.refresh_from_db()
        self.assertEqual(obligation.submitted_on, JAN_END)
        self.assertEqual(obligation.submission_number, "9")

        # «انقدّم» لا يُتراجَع عنه — 400 من الـAPI لا 500.
        for path in ("reopen/", "not-required/"):
            res = self.client.post(f"{url}/{path}", {}, format="json", **self.headers())
            self.assertEqual(res.status_code, 400, res.content)

        other = self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=8),
            period_start=FEB_START, period_end=FEB_END,
        )
        not_required = self.client.post(
            f"{OBLIGATIONS}{other.pk}/not-required/", {}, format="json",
            **self.headers(),
        )
        self.assertEqual(not_required.status_code, 200, not_required.content)
        self.assertEqual(not_required.data["status"], Obligation.STATUS_NOT_REQUIRED)
        reopened = self.client.post(
            f"{OBLIGATIONS}{other.pk}/reopen/", {}, format="json", **self.headers(),
        )
        self.assertEqual(reopened.status_code, 200, reopened.content)
        self.assertEqual(reopened.data["status"], Obligation.STATUS_PENDING)

    def test_the_amount_is_locked_after_submit_and_client_paid_still_moves(self):
        obligation = self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=10),
            amount=Decimal("620"), direction="due",
        )
        self.as_user(self.owner)

        submitted = self.client.post(
            f"{OBLIGATIONS}{obligation.pk}/submit/", {}, format="json",
            **self.headers(),
        )
        self.assertEqual(submitted.status_code, 200, submitted.content)

        locked = self.client.post(
            f"{OBLIGATIONS}{obligation.pk}/amount/",
            {"amount": "10", "direction": "due"}, format="json", **self.headers(),
        )
        self.assertEqual(locked.status_code, 400, locked.content)
        obligation.refresh_from_db()
        self.assertEqual(obligation.amount, Decimal("620"))

        paid = self.client.post(
            f"{OBLIGATIONS}{obligation.pk}/client-paid/", {"paid": True},
            format="json", **self.headers(),
        )
        self.assertEqual(paid.status_code, 200, paid.content)
        obligation.refresh_from_db()
        self.assertTrue(obligation.client_paid)

    def test_a_missing_amount_key_is_400_and_leaves_the_row_untouched(self):
        obligation = self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=10),
            amount=Decimal("620"), direction="due",
        )
        self.as_user(self.owner)

        res = self.client.post(
            f"{OBLIGATIONS}{obligation.pk}/amount/", {}, format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        obligation.refresh_from_db()
        self.assertEqual(obligation.amount, Decimal("620"))
        self.assertEqual(obligation.direction, "due")

    def test_client_paid_is_writable_in_every_status(self):
        self.as_user(self.owner)
        for month, status in enumerate(
            (
                Obligation.STATUS_PENDING,
                Obligation.STATUS_SUBMITTED,
                Obligation.STATUS_NOT_REQUIRED,
            ),
            start=1,
        ):
            with self.subTest(status=status):
                # فترةٌ لكل حالة: للشغلة قيدٌ فريدٌ على (الخدمة، الفترة).
                obligation = self.add_obligation(
                    self.mine, actual=TODAY_DAY - datetime.timedelta(days=10),
                    status=status, period_start=datetime.date(2026, month, 1),
                    period_end=datetime.date(2026, month, 28),
                )

                res = self.client.post(
                    f"{OBLIGATIONS}{obligation.pk}/client-paid/", {"paid": True},
                    format="json", **self.headers(),
                )

                self.assertEqual(res.status_code, 200, res.content)
                self.assertTrue(res.data["client_paid"])
                obligation.refresh_from_db()
                self.assertTrue(obligation.client_paid)

    def test_counters_precede_the_filter_and_an_unknown_filter_is_400(self):
        self.add_obligation(self.mine, actual=TODAY_DAY - datetime.timedelta(days=10))
        self.add_obligation(
            self.mine, actual=TODAY_DAY + datetime.timedelta(days=3),
            period_start=FEB_START, period_end=FEB_END,
        )
        self.as_user(self.owner)

        everything = self.today()
        week = self.today(filter="week")
        late = self.today(filter="late")
        owner_mine = self.today(filter="mine")

        self.assertEqual(
            everything.data["counters"],
            {"late": 1, "late_internal": 0, "week": 1, "all": 2},
        )
        self.assertEqual(len(everything.data["rows"]), 2)
        self.assertEqual(len(week.data["rows"]), 1)
        self.assertEqual(len(late.data["rows"]), 1)
        self.assertEqual(
            len(owner_mine.data["rows"]), 0,
            "«شغلي» تتبع المسؤول الفعليّ (مسؤولُ الزبون) لا مالكَ المكتب",
        )
        self.as_user(self.accountant)
        self.assertEqual(len(self.today(filter="mine").data["rows"]), 2)
        self.assertEqual(
            self.today(filter="someday").status_code, 400,
            "فلترٌ مجهولٌ يجب أن يكون 400 لا كلَّ الصفوف",
        )

    def test_someone_elses_obligation_task_and_client_are_404(self):
        obligation = self.add_obligation(
            self.other, actual=TODAY_DAY - datetime.timedelta(days=10),
        )
        self.as_user(self.accountant)

        self.assertEqual(
            self.client.post(
                f"{OBLIGATIONS}{obligation.pk}/submit/", {}, format="json",
                **self.headers(),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"{TASKS}{obligation.task_id}/assign/", {"assignee": None},
                format="json", **self.headers(),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                f"{CLIENTS}{self.other.pk}/obligations/", **self.headers(),
            ).status_code,
            404,
        )

    def test_another_office_obligation_is_404(self):
        services.refresh_office(self.outside, day=datetime.date(2026, 2, 10))
        obligation = Obligation.objects.get(client__tenant=self.outside)
        self.as_user(self.owner)

        res = self.client.post(
            f"{OBLIGATIONS}{obligation.pk}/submit/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 404)

    @mock.patch(
        "accounting_office.services.refresh_office", wraps=services.refresh_office,
    )
    def test_two_requests_in_one_day_run_the_refresh_once(self, refresh):
        """`refresh_office` نفسُها تُسجّل الصفَّ، فعدُّ الصفوف وحده لا يثبت `ensure`."""
        OfficeRefreshRun.objects.all().delete()
        self.as_user(self.owner)

        self.today()
        self.today()

        self.assertEqual(refresh.call_count, 1)
        self.assertEqual(
            OfficeRefreshRun.objects.filter(
                tenant=self.tenant, day=TODAY_DAY,
            ).count(),
            1,
        )

    def test_the_query_count_does_not_grow_with_the_rows(self):
        self.add_obligation(self.mine, actual=TODAY_DAY - datetime.timedelta(days=10))
        self.as_user(self.owner)

        with CaptureQueriesContext(connection) as one:
            self.assertEqual(len(self.today().data["rows"]), 1)
        for offset, (start, end) in enumerate(
            (
                (FEB_START, FEB_END),
                (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)),
                (datetime.date(2026, 4, 1), datetime.date(2026, 4, 30)),
                (datetime.date(2026, 5, 1), datetime.date(2026, 5, 31)),
            ),
            start=6,
        ):
            self.add_obligation(
                self.mine, actual=TODAY_DAY - datetime.timedelta(days=offset),
                period_start=start, period_end=end,
            )
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(len(self.today().data["rows"]), 5)

        self.assertEqual(
            len(many.captured_queries), len(one.captured_queries),
            "عددُ استعلامات `today/` كبر بعدد الصفوف",
        )


class ClientObligationsApiTest(ObligationApiTestCase):
    def test_the_client_tasks_are_newest_first_with_every_status(self):
        old = self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=10),
            status=Obligation.STATUS_SUBMITTED,
        )
        new = self.add_obligation(
            self.mine, actual=TODAY_DAY + datetime.timedelta(days=1),
            period_start=FEB_START, period_end=FEB_END,
        )
        self.as_user(self.owner)

        res = self.client.get(
            f"{CLIENTS}{self.mine.pk}/obligations/", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(
            [task["period_end"] for task in res.data["tasks"]],
            [new.period_end.isoformat(), old.period_end.isoformat()],
        )
        statuses = [
            row["status"]
            for task in res.data["tasks"]
            for row in task["obligations"]
        ]
        self.assertEqual(
            sorted(statuses),
            [Obligation.STATUS_PENDING, Obligation.STATUS_SUBMITTED],
        )
        self.assertEqual(set(res.data["tasks"][0]), {
            "id", "service", "period_start", "period_end", "period_label",
            "internal_deadline", "assignee", "obligations",
        })
        # #275: شغلتا كانون الثاني — لق.م وللرواتب — لا تُميَّزان بغير اسم الخدمة.
        self.assertEqual(res.data["tasks"][0]["service"]["name"], "قيمة مضافة")
        self.assertEqual(set(res.data), {"client", "day", "tasks", "direction_choices"})

    def test_close_prior_closes_the_pending_of_that_client_only(self):
        self.add_obligation(self.mine, actual=TODAY_DAY - datetime.timedelta(days=10))
        self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=5),
            period_start=FEB_START, period_end=FEB_END,
        )
        other = self.add_obligation(
            self.other, actual=TODAY_DAY - datetime.timedelta(days=10),
        )
        self.as_user(self.owner)

        res = self.client.post(
            f"{CLIENTS}{self.mine.pk}/obligations/close-prior/",
            {"before": TODAY_DAY.isoformat()}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["closed"], 2)
        other.refresh_from_db()
        self.assertEqual(other.status, Obligation.STATUS_PENDING)

    def test_assigning_a_task_through_the_api_requires_the_assign_key(self):
        obligation = self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=10),
        )
        self.as_user(self.accountant)

        forbidden = self.client.post(
            f"{TASKS}{obligation.task_id}/assign/",
            {"assignee": self.accountant.pk}, format="json", **self.headers(),
        )
        self.assertEqual(forbidden.status_code, 403, forbidden.content)

        self.as_user(self.owner)
        assigned = self.client.post(
            f"{TASKS}{obligation.task_id}/assign/",
            {"assignee": self.colleague.pk}, format="json", **self.headers(),
        )
        self.assertEqual(assigned.status_code, 200, assigned.content)
        self.assertEqual(assigned.data["assignee"]["id"], self.colleague.pk)

    def test_an_empty_assign_body_is_400_and_keeps_the_assignment(self):
        obligation = self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=10),
            assignee=self.colleague,
        )
        self.as_user(self.owner)

        res = self.client.post(
            f"{TASKS}{obligation.task_id}/assign/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)
        obligation.task.refresh_from_db()
        self.assertEqual(obligation.task.assignee_id, self.colleague.pk)

        cleared = self.client.post(
            f"{TASKS}{obligation.task_id}/assign/", {"assignee": None},
            format="json", **self.headers(),
        )
        self.assertEqual(cleared.status_code, 200, cleared.content)
        obligation.task.refresh_from_db()
        self.assertIsNone(obligation.task.assignee_id)

    def test_a_non_member_assignee_is_400(self):
        obligation = self.add_obligation(
            self.mine, actual=TODAY_DAY - datetime.timedelta(days=10),
        )
        outsider = User.objects.create_user(username="oa_outsider", password="x")
        self.as_user(self.owner)

        res = self.client.post(
            f"{TASKS}{obligation.task_id}/assign/",
            {"assignee": outsider.pk}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 400, res.content)


class WriteVisibilityTest(ObligationApiTestCase):
    """الترتيبُ في أفعال الالتزام: `get_object` أوّلاً (404) ثم المفتاح (403).

    والقارئُ (`viewer`) لا يصل إلى هنا أصلاً: `TenantRolePermission` يرفض كلَّ
    كتابةٍ لدورٍ للقراءة قبل النقطة (وهو سلوكٌ قائم لا يُمسّ). فالحالةُ المقيسة
    محاسبٌ يمرّ من ذلك الحارس وتُسحب منه `office.clients.write` بتجاوز العضو
    القائم (`MemberPermission(allowed=False)`) — وهي آليةُ الموديول نفسُه.
    """

    def make_limited_client(self):
        member = User.objects.create_user(username="oa_limited", password="x")
        membership = UserCompanyMembership.objects.create(
            user=member, tenant=self.tenant, role="accountant",
        )
        MemberPermission.objects.create(
            membership=membership,
            permission_key="office.clients.write",
            allowed=False,
        )
        client = OfficeClient.objects.create(
            tenant=self.tenant, name="زبون المحاسب المحدود", responsible=member,
        )
        TaxCard.objects.create(
            client=client, vat_classification="authorized",
            annual_sales=Decimal("0"),
        )
        services.add_client_service(
            client=client, service=self.catalog["vat"],
            starts_on=JAN_START, responsible_from=JAN_START, frequency="monthly",
        )
        return member, self.add_obligation(
            client, actual=TODAY_DAY - datetime.timedelta(days=10),
        )

    def test_a_member_without_the_write_key_gets_404_for_others_and_403_for_his(self):
        member, own = self.make_limited_client()
        others = self.add_obligation(
            self.other, actual=TODAY_DAY - datetime.timedelta(days=9),
            period_start=FEB_START, period_end=FEB_END,
        )
        self.as_user(member)

        for action in ("submit/", "not-required/", "reopen/", "client-paid/"):
            payload = {"paid": True} if action == "client-paid/" else {}
            self.assertEqual(
                self.client.post(
                    f"{OBLIGATIONS}{others.pk}/{action}", payload, format="json",
                    **self.headers(),
                ).status_code,
                404,
                action,
            )
            self.assertEqual(
                self.client.post(
                    f"{OBLIGATIONS}{own.pk}/{action}", payload, format="json",
                    **self.headers(),
                ).status_code,
                403,
                action,
            )
        self.assertEqual(
            self.client.post(
                f"{OBLIGATIONS}{others.pk}/amount/",
                {"amount": "10", "direction": "due"}, format="json", **self.headers(),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"{OBLIGATIONS}{own.pk}/amount/",
                {"amount": "10", "direction": "due"}, format="json", **self.headers(),
            ).status_code,
            403,
        )
