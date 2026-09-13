"""دليلُ الزملاء — النقطةُ التي بلا وجودِها لا يوجد «تحويلٌ إلى زميل» أصلاً.

قرارُ المالك صريح: «الموظف يقدر يحول للزميل الخط». والنقطةُ القائمةُ
`/api/platform/ops/employees/` تُضيَّق لغير المدير على صفّه هو وحدَه بالتصميم،
فمنتقي «تحويل إلى» كان سيعرض على الموظّف **نفسَه فقط**. فهذه نقطةٌ ثانيةٌ
ضيّقةُ الحمولة، لا توسيعٌ للأولى التي تحمل التقييمَ والمحفظة.

ويحرس هذا الملفُّ ثلاثةَ أشياء: أنّ الموظّفَ يرى زميلَه فعلاً · أنّ الحمولةَ لا
تتجاوز ما يلزم المنتقي · وأنّ غيرَ النشط لا يُقترَح لتسليمِ خطٍّ يُنتظَر عليه
اتّصالٌ اليوم.
"""
from rest_framework.test import APITestCase

from platform_ops.models import PlatformEmployee

from ._helpers import make_manager, make_plain_user, make_staff_employee

URL = "/api/platform/crm/colleagues/"

#: كلُّ مفتاحٍ مسموحٍ في صفّ الدليل — والزيادةُ عليه تسريبٌ لا ميزة.
ALLOWED_KEYS = {"id", "name", "job_title", "is_me"}


class ColleagueDirectoryTest(APITestCase):
    def setUp(self):
        self.me_user, self.me = make_staff_employee("dir-me", job_title="مسوّق")
        self.mate_user, self.mate = make_staff_employee("dir-mate", job_title="مسوّق أوّل")

    def test_an_employee_sees_a_colleague_not_only_himself(self):
        """الغرضُ كلُّه: بلا هذا لا يوجد لمنتقي التحويل ما يعرضه."""
        self.client.force_authenticate(user=self.me_user)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 200, res.content)
        ids = [row["id"] for row in res.json()]
        self.assertIn(self.mate.pk, ids, "الموظّفُ لا يرى زميلَه — منتقي التحويل بلا خيارات.")
        self.assertIn(self.me.pk, ids)

    def test_the_caller_is_flagged_so_the_picker_can_exclude_him(self):
        self.client.force_authenticate(user=self.me_user)
        rows = {row["id"]: row for row in self.client.get(URL).json()}
        self.assertTrue(rows[self.me.pk]["is_me"])
        self.assertFalse(rows[self.mate.pk]["is_me"])

    def test_the_payload_carries_nothing_beyond_what_the_picker_needs(self):
        """‏`PlatformEmployeeSerializer` يحمل التقييمَ والمستهدفاتِ والمحفظة.

        استعمالُه هنا كان سيُسلّم كلَّ ذلك لكلِّ زميل. فالحمولةُ مكتوبةٌ باليد،
        وهذا التأكيدُ هو ما يمنع أن تُستبدَل غداً بالمُسلسِل الكامل «لتوفير كود».
        """
        self.client.force_authenticate(user=self.me_user)
        for row in self.client.get(URL).json():
            extra = set(row) - ALLOWED_KEYS
            self.assertEqual(
                extra, set(),
                f"حمولةُ دليل الزملاء تسرّب حقولاً زائدة: {sorted(extra)}",
            )

    def test_an_offboarded_colleague_is_not_offered_for_a_transfer(self):
        gone_user, gone = make_staff_employee("dir-gone")
        gone.status = PlatformEmployee.Status.OFFBOARDED
        gone.save(update_fields=["status"])
        self.client.force_authenticate(user=self.me_user)
        ids = [row["id"] for row in self.client.get(URL).json()]
        self.assertNotIn(
            gone.pk, ids,
            "خارجُ الخدمة مُقترَحٌ لتسليم خطٍّ — تحويلٌ إلى من لا يتّصل بأحد.",
        )

    def test_a_manager_sees_the_directory_too(self):
        self.client.force_authenticate(user=make_manager("dir-manager"))
        self.assertEqual(self.client.get(URL).status_code, 200)

    def test_a_user_with_no_platform_standing_is_refused(self):
        self.client.force_authenticate(user=make_plain_user("dir-outsider"))
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_an_anonymous_caller_is_refused(self):
        self.assertIn(self.client.get(URL).status_code, (401, 403))
