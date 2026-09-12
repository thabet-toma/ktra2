"""عقد الواجهة لمفاتيح قنوات الإدخال (التذكرة 210-E، القصة ٣١).

ملفٌ مستقلٌّ خاصٌّ بهذا السطح — نفس نمط `test_health_assignment_frontend_contract.py`
و`test_hiring_frontend_contract.py`: كلُّ حقلٍ تعلنه أنواع الواجهة موجودٌ فعلاً في
حمولة الخادم، لأنّ `tsc` لا يفحص شكل ما يصل من الشبكة.
"""
from pathlib import Path

from django.test import TestCase

from platform_ops.models import IntegrationKey
from platform_ops.serializers import IntegrationKeySerializer
from platform_ops.tests.test_my_agent_frontend_contract import _interface_fields


class IntegrationKeysFrontendContractTest(TestCase):
    def setUp(self):
        repo_root = Path(__file__).resolve().parents[2]
        self.api_source = (
            repo_root / "frontend_v2" / "services" / "platformIntegrationKeysApi.ts"
        ).read_text(encoding="utf-8")

    def test_frontend_declares_the_integration_keys_contract(self):
        for name in (
            "IntegrationKeyRow", "IntegrationKeyIssuedRow", "listIntegrationKeys",
            "issueIntegrationKey", "rotateIntegrationKey", "revokeIntegrationKey",
        ):
            self.assertIn(name, self.api_source, name)
        for path in (
            "platform/ops/integration-keys/",
            "integration-keys/issue/",
            "/rotate/",
            "/revoke/",
        ):
            self.assertIn(path, self.api_source, path)

    def test_row_interface_matches_serializer_fields_exactly(self):
        self.assertEqual(
            _interface_fields(self.api_source, "IntegrationKeyRow"),
            set(IntegrationKeySerializer.Meta.fields),
            "واجهة IntegrationKeyRow يجب أن تطابق حقول IntegrationKeySerializer تماماً.",
        )

    def test_channel_options_cover_every_server_choice_value(self):
        import re

        match = re.search(r"export const INTEGRATION_CHANNELS: IntegrationChannel\[\] = \[(.*?)\];", self.api_source, re.DOTALL)
        self.assertIsNotNone(match, "لم يُعثر على INTEGRATION_CHANNELS.")
        frontend_channels = set(re.findall(r'"([^"]+)"', match.group(1)))
        self.assertEqual(frontend_channels, set(IntegrationKey.Channel.values))

    def test_raw_token_never_appears_on_the_persisted_row_interface(self):
        # السرُّ الخامُّ يظهر في `IntegrationKeyIssuedRow` وحدَها (ردّ اللحظة)، لا في
        # `IntegrationKeyRow` القائمة المُخزَّنة — وإلا كان يُعاد كشفه في كل استعلامٍ لاحق.
        self.assertNotIn("raw_token", _interface_fields(self.api_source, "IntegrationKeyRow"))
