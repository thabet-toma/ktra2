"""لوحةُ نظرة المدير العامّة — عددُ استعلاماتٍ ثابتٌ بلا علاقةٍ بعدد الموظفين.

⚠️ **تحذيرٌ مسجَّلٌ في هذا المستودع:** مقارنةُ تشغيلَين بنفس عدد الصفوف تأكيدٌ لا
يستطيع السقوط. لذلك `assertNumQueries` هنا رقمٌ **ثابتٌ ومطلق** يُستعمل في
الحالتين معاً (موظّفٌ واحد، ثمّ خمسة) — إن كبر العددُ مع الموظفين تسقط الحالةُ
الثانية، وإن كبر مطلقاً تسقط الحالتان معاً.

تركيبُ الرقم (٣): استعلامٌ واحدٌ مجمَّعٌ على `Lead` (حالات الإسناد لكلّ موظف) +
استعلامٌ واحدٌ على `PlatformEmployee` بـ`select_related("user")` فلا N+1 على
الاسم المعروض + استعلامُ عدّ واحد على مخزن العملاء المتاح.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from crm.models import LeadPhone
from crm.services import create_lead

from ._helpers import make_manager, make_staff_employee

EXPECTED_QUERIES = 3


class LeadStatsQueryCountTest(TestCase):
    def _hit_overview(self, manager):
        client = APIClient()
        client.force_authenticate(user=manager)
        with self.assertNumQueries(EXPECTED_QUERIES):
            res = client.get("/api/platform/crm/stats/overview/")
        self.assertEqual(res.status_code, 200, res.content)

    def test_query_count_with_one_employee(self):
        manager = make_manager("stats-manager-1")
        make_staff_employee("stats-emp-solo")
        create_lead(store_name="محل 1", phones=[{"raw": "0510000001", "kind": LeadPhone.Kind.PRIMARY}])
        self._hit_overview(manager)

    def test_query_count_with_five_employees_is_the_same_fixed_number(self):
        manager = make_manager("stats-manager-2")
        for i in range(5):
            _, employee = make_staff_employee(f"stats-emp-{i}")
            create_lead(
                store_name=f"محل {i}", phones=[{"raw": f"05120000{i:02d}", "kind": LeadPhone.Kind.PRIMARY}],
            )
        self._hit_overview(manager)
