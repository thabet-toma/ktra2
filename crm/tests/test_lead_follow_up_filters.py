"""مرشح متابعة العملاء: لا يرى الموظف إلا المستحق من دفتره الشخصي.

وفي ذيل الملفّ صنفٌ يحرس أنّ **«متأخّر» كلمةٌ واحدةٌ لا ثلاث**: المرشِّحُ
وعدّادُ الموظّف وعدّادُ المدير يجيبون جواباً واحداً على الصفّ نفسِه.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from core.date_ranges import local_day_start
from crm.models import LeadPhone
from crm.services import create_lead

from ._helpers import make_manager, make_staff_employee


class LeadFollowUpFilterTest(APITestCase):
    def setUp(self):
        self.user, self.employee = make_staff_employee("follow-up-owner")
        _, self.colleague = make_staff_employee("follow-up-colleague")
        now = timezone.now()

        self.oldest_due = self._lead("المتابعة الأقدم", "0521000001", self.employee, now - timedelta(days=2))
        self.newer_due = self._lead("المتابعة الأحدث", "0521000002", self.employee, now - timedelta(days=1))
        self.upcoming = self._lead("المتابعة القادمة", "0521000003", self.employee, now + timedelta(days=7))
        self.colleague_due = self._lead("موعد زميل", "0521000004", self.colleague, now - timedelta(days=3))

        # ── موعدا **اليومِ** — وهما الحالةُ التي لا يفرّقها قياسُ اللحظة ─────
        #
        # الشاشةُ تكتب تاريخاً يختاره الموظّف وتُلحق به `T09:00:00`. فبقاعدةِ
        # `now` تكون نتيجةُ هذين الصفَّين **رهينةَ ساعةِ تشغيل الاختبار**: في
        # الثامنة صباحاً «قادمٌ» وفي العاشرة «متأخّر» — اختبارٌ يمرّ أو يسقط بحسب
        # متى شُغِّل. وبقاعدةِ اليوم الجوابُ واحدٌ على مدار الساعة: مستحقٌّ اليومَ،
        # وليس متأخّراً، وليس قادماً.
        start_of_today = local_day_start(timezone.localdate())
        self.today_morning = self._lead(
            "موعد اليوم صباحاً", "0521000005", self.employee,
            start_of_today + timedelta(hours=9),
        )
        self.today_late = self._lead(
            "موعد اليوم ليلاً", "0521000006", self.employee,
            start_of_today + timedelta(hours=23, minutes=30),
        )
        # وموعدٌ بلا تاريخٍ أصلاً: لا يجوز أن يظهر في أيّ مرشَّحٍ من الثلاثة.
        self.no_date = self._lead("بلا موعد", "0521000007", self.employee, None)

        self.client.force_authenticate(user=self.user)

    def _lead(self, store_name, phone, employee, follow_up_at):
        lead = create_lead(
            store_name=store_name,
            phones=[{"raw": phone, "kind": LeadPhone.Kind.PRIMARY}],
        )
        lead.assigned_to = employee
        lead.next_follow_up_at = follow_up_at
        lead.save(update_fields=["assigned_to", "next_follow_up_at"])
        return lead

    def _rows(self, follow_up):
        response = self.client.get("/api/platform/crm/leads/", {"follow_up": follow_up})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["results"] if isinstance(response.data, dict) else response.data

    def test_due_returns_only_my_due_leads_oldest_first(self):
        """«مستحقّة» = اليومَ أو قبلَه — فموعدُ اليوم فيها مهما كانت الساعة.

        وهذه علّةُ القاعدة: بقياس اللحظة كان الموظّفُ يفتح «متابعاتي» في الثامنة
        صباحاً **فلا يرى عملَ يومِه** (موعدُ التاسعة لم يحِن بعد)، ثمّ يراه في
        التاسعة وواحدةٍ مصنَّفاً «متأخّراً».
        """
        rows = self._rows("due")
        self.assertEqual(
            [row["id"] for row in rows],
            [self.oldest_due.pk, self.newer_due.pk, self.today_morning.pk, self.today_late.pk],
            "«مستحقّة» يجب أن تضمّ موعدَ اليوم، وبالأقدمِ أوّلاً.",
        )

    def test_upcoming_returns_only_my_future_leads(self):
        """«قادمة» = **بعد** اليوم — فموعدُ اليوم ليلاً ليس قادماً بل عملَ اليوم."""
        rows = self._rows("upcoming")
        self.assertEqual([row["id"] for row in rows], [self.upcoming.pk])

    def test_overdue_returns_only_my_past_due_leads(self):
        """«متأخّرة» = يومٌ **مضى** — فموعدُ اليوم ليس متأخّراً أبداً."""
        rows = self._rows("overdue")
        self.assertEqual([row["id"] for row in rows], [self.oldest_due.pk, self.newer_due.pk])

    def test_the_three_filters_are_three_different_things(self):
        """ثلاثةُ أسماءٍ يجب أن تعني ثلاثةَ أشياء.

        أوّلُ صيغةٍ لهذا المرشّح كانت `due = __lte=now` و`overdue = __lt=now`:
        **مجموعتان متطابقتان عمليّاً** (لا يفرّق بينهما إلا صفٌّ موعدُه اللحظةُ
        نفسُها). ومرّ اختبارا «مستحقّة» و«متأخّرة» أخضرَين وهما يؤكّدان القائمةَ
        **نفسَها** — تأكيدٌ لا يستطيع السقوطَ لأجلِ الفرقِ الذي يسمّيه.
        """
        due = {row["id"] for row in self._rows("due")}
        overdue = {row["id"] for row in self._rows("overdue")}
        upcoming = {row["id"] for row in self._rows("upcoming")}

        self.assertNotEqual(overdue, due, "«متأخّرة» و«مستحقّة» مجموعةٌ واحدة.")
        self.assertLess(overdue, due, "المتأخّرُ يجب أن يكون جزءاً من المستحقّ.")
        self.assertEqual(due & upcoming, set(), "صفٌّ مستحقٌّ وقادمٌ معاً.")
        self.assertEqual(overdue & upcoming, set(), "صفٌّ متأخّرٌ وقادمٌ معاً.")

    def test_a_lead_with_no_follow_up_date_is_in_none_of_them(self):
        """ولا يظهر في أيٍّ منها زبونٌ بلا موعد — `NULL` ليس «مستحقّاً»."""
        for name in ("due", "overdue", "upcoming"):
            self.assertNotIn(
                self.no_date.pk, [row["id"] for row in self._rows(name)],
                f"زبونٌ بلا موعدٍ ظهر في «{name}».",
            )

    def test_follow_up_filter_never_expands_the_staff_scope(self):
        rows = self._rows("due")
        self.assertNotIn(self.colleague_due.pk, [row["id"] for row in rows])

    def test_unknown_follow_up_filter_is_a_400(self):
        response = self.client.get("/api/platform/crm/leads/", {"follow_up": "tomorrow"})
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("follow_up", response.data)


class OverdueMeansOneThingEverywhereTest(APITestCase):
    """«متأخّر» يُقاس في ثلاثة مواضعَ — ويجب أن يعطيَ الثلاثةُ الجوابَ نفسَه.

    المواضعُ: مرشِّحُ القائمة (`crm.views._apply_lead_filters`)، وعدّادُ الموظّف
    (`employee_lead_stats`)، ولوحةُ المدير (`manager_lead_overview`). وكانت
    الثلاثةُ تقيس `timezone.now()` مستقلّةً، فيقرأ الموظّفُ «متأخّرة: ١» في
    الشريط بينما القائمةُ تحت الشريط تُظهر صفّاً واحداً «مستحقّاً» غيرَ متأخّر —
    رقمان متناقضان على الشاشة الواحدة.

    وفخُّ الاختبار هنا أنّ الموعدَ المعتاد (`now - 1 day`) **متأخّرٌ بالقاعدتين
    معاً** فلا يفرّق. فالمرساةُ صفٌّ موعدُه **منتصفُ ليلةِ اليوم**: ماضٍ بالساعة
    دائماً (فيُعَدُّ متأخّراً بقاعدةِ اللحظة) وليس متأخّراً بقاعدةِ اليوم — تفريقٌ
    لا يتعلّق بساعةِ تشغيل الاختبار إطلاقاً.
    """

    def setUp(self):
        self.user, self.employee = make_staff_employee("overdue-one-rule")
        self.manager = make_manager("overdue-one-rule-manager")
        start_of_today = local_day_start(timezone.localdate())
        self.today = self._lead("موعد اليوم", "0523000001", start_of_today)
        self.yesterday = self._lead("موعد أمس", "0523000002", start_of_today - timedelta(hours=1))

    def _lead(self, store_name, phone, follow_up_at):
        lead = create_lead(store_name=store_name, phones=[{"raw": phone, "kind": LeadPhone.Kind.PRIMARY}])
        lead.assigned_to = self.employee
        lead.next_follow_up_at = follow_up_at
        lead.save(update_fields=["assigned_to", "next_follow_up_at"])
        return lead

    def _get(self, url, user, params=None):
        self.client.force_authenticate(user=user)
        response = self.client.get(url, params or {})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_the_employee_counter_does_not_call_todays_follow_up_late(self):
        payload = self._get("/api/platform/crm/stats/me/", self.user)
        self.assertEqual(payload["overdue"], 1, "عدّادُ الموظّف عدَّ موعدَ اليومِ متأخّراً.")

    def test_the_manager_overview_agrees_with_the_employee_counter(self):
        payload = self._get("/api/platform/crm/stats/overview/", self.manager)
        mine = [row for row in payload["employees"] if row["employee_id"] == self.employee.pk]
        self.assertEqual(len(mine), 1, payload["employees"])
        self.assertEqual(mine[0]["overdue"], 1, "لوحةُ المدير تعدّ بقاعدةٍ أخرى.")

    def test_the_list_filter_agrees_with_both_counters(self):
        rows = self._get("/api/platform/crm/leads/", self.user, {"follow_up": "overdue"})
        rows = rows["results"] if isinstance(rows, dict) else rows
        self.assertEqual(
            [row["id"] for row in rows], [self.yesterday.pk],
            "المرشِّحُ يخالف العدّادَ في معنى «متأخّر».",
        )
