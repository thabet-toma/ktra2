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

    def test_review_request_interface_matches_serializer_fields_exactly(self):
        from platform_ops.serializers import PerformanceReviewRequestSerializer

        self.assertEqual(
            _interface_fields(self.api_source, "PerformanceReviewRequestRow"),
            set(PerformanceReviewRequestSerializer.Meta.fields),
            "واجهة PerformanceReviewRequestRow يجب أن تطابق حقول المُسلسِل تماماً.",
        )

    def test_engaged_company_row_declares_over_quota_separately_from_remaining(self):
        declared = _interface_fields(self.api_source, "EmployeeEngagedCompanyRow")
        for field in ("included_quota", "consumed_quota", "remaining_quota", "over_quota", "health_items"):
            self.assertIn(field, declared, field)
        # **رقمان لا رقمٌ واحدٌ بإشارة**: «-٧ متبقّية» ليست كميّةً متبقّيةً بل زيادةً
        # مستهلَكة، والخلطُ بينهما هو ما تمنعه القصة ٤٠ («لا أعد العميل بما يتجاوز خطته»).
        self.assertIn("over_quota", declared)

    def test_health_item_interface_covers_every_key_the_service_emits(self):
        service_keys = {
            "id", "code", "status", "status_display", "mandatory",
            "action", "evidence_note", "due_date", "work_order_id",
        }
        self.assertEqual(
            _interface_fields(self.api_source, "EmployeeCompanyHealthItem"),
            service_keys,
        )
