"""لوحُ المدير لإدارة موظّفي التسويق (#69 — M3).

«ما في طريقة فلتره احترافية انو كل موظف شو الارقام الي ماسكها… لازم تفتح رقم
رقم». ثلاثةُ أشياء يحرسها هذا الملف:

1. `assigned_to` على قائمة العملاء: أرقامُ موظّفٍ بعينه، أو `none` للمخزن.
2. نتائجُ كلّ موظّفٍ في مدّة: محاولاتُ تواصلٍ فعليّة، وكم منها انردّ عليه،
   وكم رقماً صار زبوناً، وآخرُ نشاط — لا عددُ الحالات وحدَه.
3. نتيجةُ المكالمة/الواتساب إلزاميّةٌ من قائمةٍ ثابتة — وإلا صار «انردّ عليه»
   رقماً يُحسب من فراغ.
"""
import datetime as dt

from django.utils import timezone
from rest_framework.test import APITestCase

from core.date_ranges import local_day_start
from crm.models import Lead, LeadActivity, LeadPhone
from crm.services import change_lead_status, create_lead, log_activity
from platform_ops.models import PlatformEmployee

from ._helpers import make_manager, make_staff_employee

LEADS_URL = "/api/platform/crm/leads/"
OVERVIEW_URL = "/api/platform/crm/stats/overview/"


def _rows(response):
    return response.data["results"] if isinstance(response.data, dict) else response.data


class TeamViewTestBase(APITestCase):
    phone_seq = 0

    def setUp(self):
        self.manager = make_manager("team-manager")
        self.sami_user, self.sami = make_staff_employee("team-sami")
        self.rana_user, self.rana = make_staff_employee("team-rana")

    def _lead(self, name, employee=None):
        TeamViewTestBase.phone_seq += 1
        lead = create_lead(
            store_name=name,
            phones=[{"raw": f"05990{TeamViewTestBase.phone_seq:05d}", "kind": LeadPhone.Kind.PRIMARY}],
        )
        if employee is not None:
            lead.assigned_to = employee
            lead.save(update_fields=["assigned_to"])
        return lead


class AssignedToFilterTest(TeamViewTestBase):
    def test_manager_sees_one_employees_numbers(self):
        mine = [self._lead("سامي ١", self.sami), self._lead("سامي ٢", self.sami)]
        self._lead("رنا ١", self.rana)
        self._lead("في المخزن")
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(LEADS_URL, {"scope": "all", "assigned_to": self.sami.pk})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertCountEqual([row["id"] for row in _rows(response)], [lead.pk for lead in mine])

    def test_none_means_unassigned(self):
        pool = self._lead("في المخزن")
        self._lead("سامي ١", self.sami)
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(LEADS_URL, {"scope": "all", "assigned_to": "none"})
        self.assertEqual([row["id"] for row in _rows(response)], [pool.pk])

    def test_garbage_is_rejected_not_ignored(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(LEADS_URL, {"scope": "all", "assigned_to": "abc"})
        self.assertEqual(response.status_code, 400)

    def test_an_employee_cannot_read_a_colleagues_numbers_through_the_filter(self):
        self._lead("رنا ١", self.rana)
        own = self._lead("سامي ١", self.sami)
        self.client.force_authenticate(user=self.sami_user)
        response = self.client.get(LEADS_URL, {"scope": "all", "assigned_to": self.rana.pk})
        self.assertEqual([row["id"] for row in _rows(response)], [])
        response = self.client.get(LEADS_URL, {"assigned_to": self.sami.pk})
        self.assertEqual([row["id"] for row in _rows(response)], [own.pk])


class CallOutcomeTest(TeamViewTestBase):
    def setUp(self):
        super().setUp()
        self.lead = self._lead("محل سامي", self.sami)
        self.url = f"{LEADS_URL}{self.lead.pk}/activities/"
        self.client.force_authenticate(user=self.sami_user)

    def test_a_call_without_an_outcome_is_refused(self):
        response = self.client.post(self.url, {"kind": "call", "body": "حكيت معه"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.lead.activities.count(), 0)

    def test_an_outcome_outside_the_list_is_refused(self):
        response = self.client.post(self.url, {"kind": "whatsapp", "outcome": "ممتاز"}, format="json")
        self.assertEqual(response.status_code, 400, response.data)

    def test_a_call_with_an_outcome_is_stored(self):
        response = self.client.post(self.url, {"kind": "call", "outcome": "no_answer"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.lead.activities.get().outcome, LeadActivity.Outcome.NO_ANSWER)

    def test_a_note_needs_no_outcome(self):
        response = self.client.post(self.url, {"kind": "note", "body": "يفضّل المساء"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_the_rule_lives_in_the_service_too(self):
        from crm.services import CrmValidationError
        with self.assertRaises(CrmValidationError):
            log_activity(lead=self.lead, employee=self.sami, kind=LeadActivity.Kind.CALL, actor=self.sami_user)


class OverviewResultsTest(TeamViewTestBase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.lead_a = self._lead("أ", self.sami)
        self.lead_b = self._lead("ب", self.sami)
        # داخل المدّة (هذا الشهر): محاولتان، واحدةٌ انردّ عليها، وأخرى «اتصل لاحقاً» (ردّ أيضاً)
        # وثالثةٌ بلا ردّ — وملاحظةٌ لا تُعدّ تواصلاً.
        for lead, outcome in ((self.lead_a, "answered"), (self.lead_a, "callback"), (self.lead_b, "no_answer")):
            log_activity(lead=lead, employee=self.sami, kind=LeadActivity.Kind.CALL,
                         actor=self.sami_user, outcome=outcome)
        log_activity(lead=self.lead_b, employee=self.sami, kind=LeadActivity.Kind.NOTE, actor=self.sami_user)
        change_lead_status(lead=self.lead_a, employee=self.sami, status=Lead.Status.CUSTOMER, actor=self.sami_user)
        # خارج المدّة: مكالمةٌ قبل سنتين.
        old = log_activity(lead=self.lead_b, employee=self.sami, kind=LeadActivity.Kind.CALL,
                           actor=self.sami_user, outcome="answered")
        LeadActivity.objects.filter(pk=old.pk).update(
            created_at=local_day_start(self.today.replace(year=self.today.year - 2)))
        self.client.force_authenticate(user=self.manager)

    def _row(self, payload, employee):
        return next(row for row in payload["employees"] if row["employee_id"] == employee.pk)

    def test_results_inside_the_period(self):
        payload = self.client.get(OVERVIEW_URL, {"period": "month"}).data
        sami = self._row(payload, self.sami)
        self.assertEqual(sami["attempts"], 3)
        self.assertEqual(sami["reached"], 2)
        self.assertEqual(sami["converted"], 1)
        self.assertIsNotNone(sami["last_activity_at"])
        self.assertEqual(sami["total"], 2)
        self.assertEqual(payload["period"]["date_from"], self.today.replace(day=1).isoformat())

    def test_all_time_counts_the_old_call_too(self):
        sami = self._row(self.client.get(OVERVIEW_URL, {"period": "all"}).data, self.sami)
        self.assertEqual((sami["attempts"], sami["reached"]), (4, 3))

    def test_a_managers_status_change_is_credited_to_the_holder(self):
        # المديرُ بلا صفِّ موظّف يكتب `employee=None` — التحويلُ يُحسب لصاحب الرقم.
        lead = self._lead("ج", self.rana)
        change_lead_status(lead=lead, employee=None, status=Lead.Status.CUSTOMER,
                           actor=self.manager, is_manager=True)
        rana = self._row(self.client.get(OVERVIEW_URL, {"period": "month"}).data, self.rana)
        self.assertEqual(rana["converted"], 1)

    def test_offboarded_employee_without_numbers_or_activity_is_hidden(self):
        user, gone = make_staff_employee("team-gone")
        gone.status = PlatformEmployee.Status.OFFBOARDED
        gone.save(update_fields=["status"])
        ids = [row["employee_id"] for row in self.client.get(OVERVIEW_URL).data["employees"]]
        self.assertNotIn(gone.pk, ids)
        self.assertIn(self.rana.pk, ids)  # نشطٌ بلا أرقام: يظهر بصفر، فهو قابلٌ للإسناد.

    def test_offboarded_employee_still_holding_numbers_stays_visible(self):
        _, gone = make_staff_employee("team-gone-holding")
        self._lead("عالق", gone)
        gone.status = PlatformEmployee.Status.OFFBOARDED
        gone.save(update_fields=["status"])
        ids = [row["employee_id"] for row in self.client.get(OVERVIEW_URL).data["employees"]]
        self.assertIn(gone.pk, ids)

    def test_bad_dates_are_rejected(self):
        response = self.client.get(OVERVIEW_URL, {"date_from": "2026-13-40"})
        self.assertEqual(response.status_code, 400)

    def test_explicit_range(self):
        start = self.today.replace(year=self.today.year - 2) - dt.timedelta(days=1)
        end = self.today.replace(year=self.today.year - 2) + dt.timedelta(days=1)
        sami = self._row(self.client.get(
            OVERVIEW_URL, {"date_from": start.isoformat(), "date_to": end.isoformat()}).data, self.sami)
        self.assertEqual((sami["attempts"], sami["reached"], sami["converted"]), (1, 1, 0))
