from django.contrib.auth.models import User
from django.db import connection, transaction
from django.test import TransactionTestCase

from accountant_portal.audit import AUDIT_ACTION_CODES, write_financial_audit
from accounting.models import AccountingAuditLog
from tenants.models import Tenant


class MySQLAuditActionPersistenceTest(TransactionTestCase):
    def test_all_portal_actions_survive_a_strict_mysql_commit(self):
        if connection.vendor != "mysql":
            self.skipTest("بوابة الحفظ الفعلي هذه مخصصة لـ MySQL")

        with connection.cursor() as cursor:
            cursor.execute("SELECT @@sql_mode")
            sql_mode = cursor.fetchone()[0]
        self.assertIn("STRICT", sql_mode.upper())

        tenant = Tenant.objects.create(CompanyName="شركة اختبار تدقيق MySQL")
        user = User.objects.create_user("mysql-audit-accountant")

        with transaction.atomic():
            for index, action in enumerate(sorted(AUDIT_ACTION_CODES), start=1):
                write_financial_audit(
                    tenant=tenant,
                    user=user,
                    action=action,
                    model_name="AccountantPortalGate",
                    object_id=index,
                    change_details="{}",
                )

        persisted = set(
            AccountingAuditLog.objects.filter(
                tenant=tenant,
                model_name="AccountantPortalGate",
            ).values_list("action", flat=True)
        )
        self.assertEqual(persisted, AUDIT_ACTION_CODES)
        self.assertLessEqual(max(map(len, persisted)), 20)
