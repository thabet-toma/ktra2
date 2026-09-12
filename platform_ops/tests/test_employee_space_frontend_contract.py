"""عقدُ مساحة موظّف المنصّة (التذكرة 210-E، §١).

**العزلُ الخادميُّ سليم، والهويّةُ هي ما كان يَضيع.** `PlatformEmployeeViewSet`
يضيّق `get_queryset` على `user=request.user` **لغيرِ المدير وحدَه**؛ أمّا مديرُ
العمليات فيعود له كلُّ الموظفين مرتَّبين بـ`-created_at`. فأخذُ `rows[0]` يعني أنّ
مديراً يفتح «مساحتي» فيقرأ راتبَ زميلٍ عشوائيٍّ وعمولاتِه تحت عنوان «محفظتي».
"""
import re
from pathlib import Path

from django.test import TestCase

from platform_ops.serializers import PlatformEmployeeSerializer
from platform_ops.tests.test_my_agent_frontend_contract import _interface_fields


class EmployeeSpaceFrontendContractTest(TestCase):
    def setUp(self):
        repo_root = Path(__file__).resolve().parents[2]
        self.api_source = (
            repo_root / "frontend_v2" / "services" / "platformEmployeeSpaceApi.ts"
        ).read_text(encoding="utf-8")

    def test_profile_interface_matches_serializer_fields_exactly(self):
        self.assertEqual(
            _interface_fields(self.api_source, "MyPlatformEmployeeProfile"),
            set(PlatformEmployeeSerializer.Meta.fields),
            "واجهة MyPlatformEmployeeProfile يجب أن تطابق حقول PlatformEmployeeSerializer تماماً.",
        )

    def test_profile_is_matched_by_user_identity_not_by_first_row(self):
        # الصفُّ يُنتقى بمطابقة هويّة المستخدم، ولا يُؤخذ أوّلُ صفٍّ بحالٍ.
        self.assertRegex(
            self.api_source,
            r"rows\.find\(\s*\(row\)\s*=>\s*String\(row\.user\)\s*===\s*String\(currentUserId\)\s*\)",
            "يجب انتقاءُ الصفّ بمطابقة `row.user` بهويّة المستخدم الحاليّ.",
        )
        self.assertNotRegex(
            re.sub(r"/\*.*?\*/", "", self.api_source, flags=re.DOTALL),
            r"return\s+rows\[0\]",
            "أخذُ `rows[0]` يُعطي المديرَ محفظةَ زميلٍ عشوائيّ تحت عنوان «محفظتي».",
        )

    def test_the_loader_requires_a_user_id_argument(self):
        self.assertIn("currentUserId: string | number | undefined", self.api_source)
