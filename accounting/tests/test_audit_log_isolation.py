"""سطر التدقيق لا يجوز أن يُسقط عملية المستدعي (سبب «تم بنجاح» بلا أي أثر).

عمود `Action` هو varchar(20) وMySQL في وضع STRICT يرفض الأطول (خطأ 1406).
كان `create_audit_log` يبتلع الاستثناء، لكن Django يكون قد وسم المعاملة
`needs_rollback` ⇒ عند خروج `atomic` يُلغى كل شيء بصمت: القيد المحاسبي وحفظ
المستند — بينما الـview يرجّع 201. (لا يظهر في الاختبارات لأن SQLite لا يفرض
أطوال varchar، لذا نختبر القصّ والعزل مباشرةً.)
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase

from accounting.models import Account, AccountingAuditLog
from accounting.services import create_audit_log
from tenants.models import Tenant


class AuditLogIsolationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=960, CompanyName='Audit Co')
        cls.user = User.objects.create_user(username='audit-u', password='x')

    def test_long_action_is_truncated_to_column_length(self):
        max_length = AccountingAuditLog._meta.get_field('action').max_length
        create_audit_log(
            tenant=self.tenant, user=self.user,
            action='shipment_freight_accrued_and_then_some_more',
            model_name='LogisticsShipment', object_id=9,
            change_details='x',
        )
        row = AccountingAuditLog.objects.latest('id')
        self.assertLessEqual(len(row.action), max_length)
        self.assertTrue(row.action.startswith('shipment_freight'))

    def test_audit_failure_does_not_roll_back_caller_transaction(self):
        """جوهر الخلل: فشل التدقيق كان يُلغي عمل المستدعي داخل نفس atomic."""
        with transaction.atomic():
            account = Account.objects.create(
                tenant=self.tenant, code='AUD-1', name='حساب اختبار',
                account_type='Expense', is_active=True,
            )
            with patch.object(
                AccountingAuditLog.objects, 'create',
                side_effect=Exception('audit table exploded'),
            ):
                create_audit_log(
                    tenant=self.tenant, user=self.user, action='POST',
                    model_name='Account', object_id=account.pk, change_details='x',
                )
        # العمل الأساسي محفوظ رغم فشل التدقيق.
        self.assertTrue(Account.objects.filter(code='AUD-1').exists())
