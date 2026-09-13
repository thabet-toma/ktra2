"""لوحةُ نظرة المدير العامّة — عددُ استعلاماتٍ ثابتٌ بلا علاقةٍ بعدد الموظفين.

⚠️ **تحذيرٌ مسجَّلٌ في هذا المستودع:** مقارنةُ تشغيلَين بنفس عدد الصفوف تأكيدٌ لا
يستطيع السقوط. لذلك `assertNumQueries` هنا رقمٌ **ثابتٌ ومطلق** يُستعمل في
الحالتين معاً (موظّفٌ واحد، ثمّ خمسة) — إن كبر العددُ مع الموظفين تسقط الحالةُ
الثانية، وإن كبر مطلقاً تسقط الحالتان معاً.

تركيبُ الرقم (٣): استعلامٌ واحدٌ مجمَّعٌ على `Lead` (حالات الإسناد لكلّ موظف) +
استعلامٌ واحدٌ على `PlatformEmployee` بـ`select_related("user")` فلا N+1 على
الاسم المعروض + استعلامُ عدّ واحد على مخزن العملاء المتاح.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from crm.models import LeadPhone
from crm.services import create_lead

from ._helpers import make_manager, make_staff_employee

EXPECTED_QUERIES = 3


class LeadStatsQueryCountTest(TestCase):
    def _hit_overview(self, manager) -> dict:
        """يُصيب النقطةَ ويعيد جسمَها — **موضعٌ واحدٌ** لبوّابةِ عدّ الاستعلامات.

        كانت الحالةُ الأولى تنسخ هذا المساعِدَ حرفيّاً كي تقرأ الجسمَ بعده، فيصير
        للبوّابةِ موضعان: تعديلُ الرقم في أحدهما يترك الآخرَ يحرس رقماً قديماً.
        """
        client = APIClient()
        client.force_authenticate(user=manager)
        with self.assertNumQueries(EXPECTED_QUERIES):
            res = client.get("/api/platform/crm/stats/overview/")
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_query_count_with_one_employee(self):
        manager = make_manager("stats-manager-1")
        _, employee = make_staff_employee("stats-emp-solo")
        lead = create_lead(store_name="محل 1", phones=[{"raw": "0510000001", "kind": LeadPhone.Kind.PRIMARY}])
        lead.assigned_to = employee
        lead.next_follow_up_at = timezone.now() - timedelta(days=1)
        lead.save(update_fields=["assigned_to", "next_follow_up_at"])
        payload = self._hit_overview(manager)
        self.assertEqual(payload["employees"][0]["overdue"], 1)

    def test_query_count_with_five_employees_is_the_same_fixed_number(self):
        manager = make_manager("stats-manager-2")
        for i in range(5):
            _, employee = make_staff_employee(f"stats-emp-{i}")
            create_lead(
                store_name=f"محل {i}", phones=[{"raw": f"05120000{i:02d}", "kind": LeadPhone.Kind.PRIMARY}],
            )
        self._hit_overview(manager)
