"""212-R4 — ستاتستكس الرقم: ماذا تعدّ، ومن يراها، وبكم استعلام.

ثلاثةُ أسئلةٍ لا يُغني أحدُها عن الآخر:

1. **ماذا تعدّ؟** «كم مرّةً كُلِّم» ليست «كم صفّاً في سجلّه»: التحويلُ والإسنادُ
   وتغييرُ الحالة صفوفٌ يكتبها النظامُ عن نفسِه، والملاحظةُ ليست مكالمة.
2. **من يراها؟** النقطةُ قراءةٌ على صفٍّ واحد، فتلبس تضييقَ `retrieve` نفسَه —
   وإلّا صارت بابَ تجسّسٍ على شغل الزميل. وذلك مُثبَتٌ في `test_lead_lock.py`
   حيث يعيش تعدادُ الملكيّة كلُّه.
3. **بكم استعلام؟** الرقمُ ثابتٌ مطلقٌ يُستعمل في الحالتين معاً (سجلٌّ قصيرٌ ثمّ
   أطولُ من صفحة) — مقارنةُ تشغيلَين بنفس عدد الصفوف تأكيدٌ لا يستطيع السقوط.
"""
import re
from datetime import timedelta
from pathlib import Path

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from crm.models import Lead, LeadActivity, LeadPhone
from crm.services import change_lead_status, create_lead, lead_contact_stats, log_activity

from ._helpers import make_manager, make_staff_employee

REPO = Path(__file__).resolve().parents[2]
PANEL = REPO / "frontend_v2" / "components" / "platform" / "staff" / "crm" / "CrmPanel.tsx"
PROFILE = REPO / "frontend_v2" / "components" / "platform" / "staff" / "crm" / "CrmLeadProfile.tsx"

#: عددُ استعلامات `lead_contact_stats` — تجميعتان لا أكثر، مهما طال السجلّ.
EXPECTED_QUERIES = 2


def _backdate(activity, days: int) -> None:
    """`created_at` حقلُ `auto_now_add` فلا يُكتَب بالحفظ — يُزاح بـ`update` مباشرةً."""
    LeadActivity.objects.filter(pk=activity.pk).update(created_at=timezone.now() - timedelta(days=days))


class LeadContactStatsServiceTest(TestCase):
    def setUp(self):
        self.user, self.employee = make_staff_employee("r4-owner")
        self.lead = create_lead(
            store_name="محل الأرقام", phones=[{"raw": "0561110001", "kind": LeadPhone.Kind.PRIMARY}],
        )
        self.lead.assigned_to = self.employee
        self.lead.save(update_fields=["assigned_to"])

    def _log(self, kind, days_ago=0):
        activity = log_activity(lead=self.lead, employee=self.employee, kind=kind, actor=self.user)
        if days_ago:
            _backdate(activity, days_ago)
        return activity

    def test_a_note_and_a_transfer_are_not_a_phone_call(self):
        """العدُّ الخامُّ للسجلّ يجعل رقماً لم تُرفع له سمّاعةٌ يبدو مُكلَّماً ثلاثاً."""
        self._log(LeadActivity.Kind.CALL)
        self._log(LeadActivity.Kind.NOTE)
        LeadActivity.objects.create(lead=self.lead, employee=self.employee, kind=LeadActivity.Kind.TRANSFER)
        change_lead_status(
            lead=self.lead, employee=self.employee, status=Lead.Status.CONTACTED, actor=self.user,
        )

        stats = lead_contact_stats(self.lead)
        self.assertEqual(self.lead.activities.count(), 4)
        self.assertEqual(stats["contact_attempts"], 1)
        self.assertEqual(stats["by_kind"], {"call": 1, "whatsapp": 0, "visit": 0})

    def test_the_three_contact_channels_are_counted_apart(self):
        self._log(LeadActivity.Kind.CALL)
        self._log(LeadActivity.Kind.CALL)
        self._log(LeadActivity.Kind.WHATSAPP)
        self._log(LeadActivity.Kind.VISIT)

        stats = lead_contact_stats(self.lead)
        self.assertEqual(stats["contact_attempts"], 4)
        self.assertEqual(stats["by_kind"], {"call": 2, "whatsapp": 1, "visit": 1})

    def test_the_last_contact_ignores_a_newer_note(self):
        """ملاحظةُ اليوم لا تجعل مكالمةَ الأسبوع الماضي «اليومَ»."""
        self._log(LeadActivity.Kind.CALL, days_ago=6)
        self._log(LeadActivity.Kind.NOTE)

        stats = lead_contact_stats(self.lead)
        self.assertEqual(stats["days_since_last_contact"], 6)

    def test_a_number_never_called_says_so_instead_of_saying_zero(self):
        """صفرُ أيّامٍ يعني «كُلِّم اليوم» — و`None` وحدَها تعني «لم يُكلَّم قطّ»."""
        self._log(LeadActivity.Kind.NOTE)
        stats = lead_contact_stats(self.lead)
        self.assertIsNone(stats["last_contact_at"])
        self.assertIsNone(stats["days_since_last_contact"])
        self.assertEqual(stats["contact_attempts"], 0)

    def test_days_in_status_runs_from_the_last_status_change(self):
        change_lead_status(
            lead=self.lead, employee=self.employee, status=Lead.Status.INTERESTED, actor=self.user,
        )
        change_row = self.lead.activities.filter(kind=LeadActivity.Kind.STATUS_CHANGE).first()
        _backdate(change_row, 9)

        stats = lead_contact_stats(self.lead)
        self.assertEqual(stats["days_in_status"], 9)

    def test_a_lead_that_never_moved_counts_its_status_from_birth_not_from_today(self):
        """صفرٌ هنا كذبٌ مريح: رقمٌ راكدٌ منذ أسبوعين يبدو كأنّه تحرّك اليوم."""
        Lead.objects.filter(pk=self.lead.pk).update(created_at=timezone.now() - timedelta(days=12))
        self.lead.refresh_from_db()

        stats = lead_contact_stats(self.lead)
        self.assertEqual(stats["days_in_status"], 12)
        self.assertEqual(stats["age_days"], 12)

    def test_handlers_counts_distinct_employees_not_rows(self):
        _, second = make_staff_employee("r4-second-hand")
        self._log(LeadActivity.Kind.CALL)
        self._log(LeadActivity.Kind.CALL)
        LeadActivity.objects.create(lead=self.lead, employee=second, kind=LeadActivity.Kind.NOTE)

        self.assertEqual(lead_contact_stats(self.lead)["handlers"], 2)

    def test_the_follow_up_state_reads_the_one_day_boundary(self):
        """«متأخّرة» يومٌ مضى لا لحظةٌ مضت — نفسُ تعريف `follow_up_day_bounds`."""
        now = timezone.now()
        cases = [
            (None, "none"),
            (now - timedelta(days=2), "overdue"),
            (now, "due_today"),
            (now + timedelta(days=3), "upcoming"),
        ]
        for moment, expected in cases:
            with self.subTest(expected=expected):
                Lead.objects.filter(pk=self.lead.pk).update(next_follow_up_at=moment)
                self.lead.refresh_from_db()
                self.assertEqual(lead_contact_stats(self.lead)["follow_up_state"], expected)


class LeadContactStatsQueryCountTest(TestCase):
    """رقمٌ ثابتٌ مطلقٌ في الحالتين: إن كبر مع السجلّ سقطت الثانية، وإن كبر مطلقاً سقطتا."""

    def _stats_of(self, lead) -> dict:
        with self.assertNumQueries(EXPECTED_QUERIES):
            return lead_contact_stats(lead)

    def _lead_with(self, username, phone, activity_count):
        user, employee = make_staff_employee(username)
        lead = create_lead(store_name=f"محل {phone}", phones=[{"raw": phone, "kind": LeadPhone.Kind.PRIMARY}])
        lead.assigned_to = employee
        lead.save(update_fields=["assigned_to"])
        LeadActivity.objects.bulk_create([
            LeadActivity(lead=lead, employee=employee, actor=user, kind=LeadActivity.Kind.CALL)
            for _ in range(activity_count)
        ])
        return lead

    def test_query_count_with_a_short_log(self):
        lead = self._lead_with("r4-count-short", "0562220001", 3)
        self.assertEqual(self._stats_of(lead)["contact_attempts"], 3)

    def test_query_count_with_a_log_longer_than_one_page_is_the_same_fixed_number(self):
        """أطولُ من صفحة الخمسين: هذا بالضبط ما يجعل العدَّ في الشاشة يكذب."""
        lead = self._lead_with("r4-count-long", "0562220002", 60)
        self.assertEqual(self._stats_of(lead)["contact_attempts"], 60)


class LeadContactStatsEndpointTest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner_user, self.owner = make_staff_employee("r4-endpoint-owner")
        self.lead = create_lead(
            store_name="محل النقطة", phones=[{"raw": "0563330001", "kind": LeadPhone.Kind.PRIMARY}],
        )
        self.lead.assigned_to = self.owner
        self.lead.save(update_fields=["assigned_to"])
        log_activity(
            lead=self.lead, employee=self.owner, kind=LeadActivity.Kind.CALL, actor=self.owner_user,
        )
        self.url = f"/api/platform/crm/leads/{self.lead.pk}/stats/"

    def test_the_owner_reads_the_numbers_of_his_own_number(self):
        self.client.force_authenticate(user=self.owner_user)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body["contact_attempts"], 1)
        self.assertEqual(body["days_since_last_contact"], 0)
        self.assertEqual(body["handlers"], 1)

    def test_the_manager_reads_them_too_because_he_reads_every_row(self):
        self.client.force_authenticate(user=make_manager("r4-endpoint-manager"))
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["contact_attempts"], 1)

    def test_a_pool_number_is_readable_before_anyone_claims_it(self):
        """المخزنُ المتاحُ مقروءٌ بالتصميم — والستاتستكس جزءٌ ممّا يُقرَّر به الاستلام."""
        pool = create_lead(
            store_name="محل المخزن", phones=[{"raw": "0563330002", "kind": LeadPhone.Kind.PRIMARY}],
        )
        stranger_user, _ = make_staff_employee("r4-pool-reader")
        self.client.force_authenticate(user=stranger_user)
        res = self.client.get(f"/api/platform/crm/leads/{pool.pk}/stats/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertIsNone(res.json()["days_since_last_contact"])

    def test_the_endpoint_is_read_only(self):
        self.client.force_authenticate(user=self.owner_user)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 405)


def _mounted_stats_section() -> str:
    """جسمُ قسم الستاتستكس في `CrmLeadProfile.tsx` — بمطابقةِ أقواسٍ لا بقصٍّ أعمى.

    والسببُ أنّ التأكيدَ المطلوبَ «كلُّ رقمٍ معروضٍ **هنا** مصدرُه الخادم»، فلا
    يصحّ قياسُه على الملفّ كلِّه: سجلُّ التواصل تحته يعدّ صفوفَه المحمَّلة بحقّ.
    """
    text = PROFILE.read_text(encoding="utf-8")
    anchor = text.index("{stats && attention &&")
    depth = 0
    for index in range(anchor, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[anchor:index + 1]
    raise AssertionError("قسمُ الستاتستكس مفتوحُ الأقواس — لم يُغلَق.")


class LeadStatsSurfaceContractTest(TestCase):
    """حرّاسٌ ساكنون: `tsc` لا يفحص خاصيّةَ JSX، و`npm test` لا يُصيّر مكوّناً."""

    def test_the_section_reader_returns_a_real_body(self):
        """حارسٌ ضدّ حارسٍ ميّت: لو عاد المقتطَعُ فارغاً لمرّ ما بعده كذباً."""
        section = _mounted_stats_section()
        self.assertGreater(len(section), 400, "المقتطَعُ أقصرُ من أن يكون القسمَ كلَّه.")
        self.assertIn("ستاتستكس الرقم", section)

    def test_the_panel_asks_the_server_for_the_numbers_and_hands_them_over(self):
        """نقطةٌ بلا نداءٍ بابٌ ميّت، ونداءٌ بلا تمريرٍ رقمٌ يُجلَب ولا يُرى."""
        panel = PANEL.read_text(encoding="utf-8")
        self.assertIn("getCrmLeadStats(id)", panel)
        self.assertIn("stats={leadStats}", panel)

    def test_a_failed_stats_call_does_not_close_the_lead_file(self):
        """`Promise.all` يسقط كلُّه بسقوط واحد — فنداءٌ عارٍ يُقفل الملفَّ بفشل زينته."""
        panel = PANEL.read_text(encoding="utf-8")
        self.assertIn("getCrmLeadStats(id).catch(() => null)", panel)

    def test_every_number_in_the_section_comes_from_the_server_aggregate(self):
        """العدُّ من `activities` المحمَّلة يقول «خمسون» عن رقمٍ كُلِّم ثمانين."""
        section = _mounted_stats_section()
        arguments = re.findall(r"(?:formatNumber|arabicDayCount|contactRecencyLabel|formatDateTimeValue)\(([^)]*)", section)
        self.assertGreaterEqual(len(arguments), 7, f"أرقامٌ أقلُّ من المتوقَّع في القسم: {arguments}")
        strays = [argument for argument in arguments if not argument.strip().startswith("stats.")]
        self.assertEqual(
            strays, [],
            f"رقمٌ في قسم الستاتستكس لا يأتي من تجميعة الخادم: {strays}",
        )

    def test_the_verdict_is_computed_by_the_shared_pure_function(self):
        """عتبةُ الركود قاعدةٌ واحدةٌ في `utils/leadContactStats.ts` لا شرطٌ مكرَّرٌ في الشاشة."""
        profile = PROFILE.read_text(encoding="utf-8")
        self.assertIn("leadAttentionBadge(stats)", profile)
