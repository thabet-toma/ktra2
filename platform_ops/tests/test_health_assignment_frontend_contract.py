"""عقد الواجهة لفحص صحة الدفاتر والتشغيل والإسناد/الطاقة (التذكرة 210-B).

ملفٌ مستقلٌّ لا امتدادٌ لـ`SubscriptionFrontendContractTests` (خاصّةٌ باشتراك الخدمة نطاقاً) —
نفس نمط `test_hiring_frontend_contract.py`/`test_my_agent_frontend_contract.py` لكل تذكرةٍ ملفّها.
"""
import re
from pathlib import Path

from django.test import TestCase

from platform_ops.models import CompanyHealthCheck, CompanyHealthCheckItem, Engagement
from platform_ops.serializers import (
    CompanyHealthCheckItemSerializer,
    CompanyHealthCheckSerializer,
    CustomerAcquisitionSerializer,
    EngagementSerializer,
)
from platform_ops.tests.test_my_agent_frontend_contract import _interface_fields


class HealthAndAssignmentFrontendContractTest(TestCase):
    def setUp(self):
        repo_root = Path(__file__).resolve().parents[2]
        self.api_source = (repo_root / "frontend_v2" / "services" / "platformOpsApi.ts").read_text(encoding="utf-8")
        self.util_source = (repo_root / "frontend_v2" / "utils" / "platformHealthAssignment.ts").read_text(encoding="utf-8")

    def test_frontend_declares_the_health_and_assignment_contract(self):
        for name in (
            "CompanyHealthCheckRow", "CompanyHealthCheckItemRow", "EngagementRow", "CustomerAcquisitionRow",
            "AssignmentCandidateRow", "listHealthChecks", "createHealthCheckDraft", "updateHealthCheck",
            "refreshHealthCheckAutoItems", "approveHealthCheck", "updateHealthCheckItem",
            "convertHealthCheckItemToWorkOrder", "compareHealthBaseline", "listEngagements",
            "assignPlatformEmployee", "transferEngagement", "suspendEngagement", "resumeEngagement",
            "revokeEngagement", "listAssignmentCandidates", "getCustomerAcquisition", "setCustomerAcquisition",
        ):
            self.assertIn(name, self.api_source, name)
        for path in (
            "platform/ops/health-checks/",
            "create-draft/",
            "item-to-work-order/",
            "platform/ops/engagements/",
            "candidates/",
            "platform/ops/acquisition/",
        ):
            self.assertIn(path, self.api_source, path)

    def test_row_interfaces_match_serializer_fields_exactly(self):
        interfaces = {
            "CompanyHealthCheckRow": CompanyHealthCheckSerializer,
            "CompanyHealthCheckItemRow": CompanyHealthCheckItemSerializer,
            "EngagementRow": EngagementSerializer,
            "CustomerAcquisitionRow": CustomerAcquisitionSerializer,
        }
        for interface, serializer in interfaces.items():
            self.assertEqual(
                _interface_fields(self.api_source, interface),
                set(serializer.Meta.fields),
                f"واجهة {interface} يجب أن تطابق حقول {serializer.__name__} تماماً.",
            )

    def test_choice_labels_follow_server_choices_exactly(self):
        # التسمياتُ المعروضةُ وحدَها تُحرَس — ما لا يعرضه مكوّنٌ لا يُترك خريطةً ميّتة
        # يُبقيها اختبارُها حيّة (الحالاتُ الأخرى تُعرض من `*_display` الخادم).
        pairs = (
            ("HEALTH_CHECK_COMPLEXITY_LABEL", dict(CompanyHealthCheck.Complexity.choices) | {"": "لم يُقدَّر بعد"}),
            ("HEALTH_CHECK_ITEM_STATUS_LABEL", dict(CompanyHealthCheckItem.ItemStatus.choices)),
            ("ENGAGEMENT_STATUS_LABEL", dict(Engagement.Status.choices)),
            ("ENGAGEMENT_KIND_LABEL", dict(Engagement.Kind.choices)),
        )
        for name, server_labels in pairs:
            match = re.search(rf"{name}[^=]*=\s*\{{(.*?)\}};", self.util_source, re.DOTALL)
            self.assertIsNotNone(match, f"لم يُعثر على {name}.")
            frontend_labels = dict(re.findall(r'"?(\w*)"?:\s*"([^"]+)"', match.group(1)))
            self.assertEqual(frontend_labels, server_labels, name)

    def test_health_check_types_cover_every_server_choice_value(self):
        for type_name, choices in (
            ("HealthCheckKind", CompanyHealthCheck.Kind.values),
            ("HealthCheckStatus", CompanyHealthCheck.Status.values),
            ("HealthCheckItemStatus", CompanyHealthCheckItem.ItemStatus.values),
            ("HealthCheckItemSource", CompanyHealthCheckItem.Source.values),
            ("EngagementStatus", Engagement.Status.values),
            ("EngagementKind", Engagement.Kind.values),
        ):
            match = re.search(rf"export type {type_name} = ([^;]+);", self.api_source)
            self.assertIsNotNone(match, f"لم يُعثر على union {type_name}.")
            frontend_choices = set(re.findall(r'"([^"]+)"', match.group(1)))
            self.assertEqual(frontend_choices, set(choices), f"خيارات {type_name} لا تطابق choices الخادم.")
