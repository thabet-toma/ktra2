import threading
from unittest import skipUnless

from django.contrib.auth.models import User
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from accountant_portal.models import AccountantProfile
from accountant_portal.services import (
    EngagementConflict,
    accept_company_invitation,
    create_company_invitation,
)
from core.models import TenantModule
from tenants.models import Tenant, UserCompanyMembership


@skipUnless(connection.vendor == "mysql", "اختبار قفل الصف الحقيقي يعمل على MySQL فقط")
class MySQLInvitationConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.manager = User.objects.create_user("mysql-m2-manager")
        self.accountant = User.objects.create_user("mysql-m2-accountant", email="mysql-m2@example.com")
        self.tenant = Tenant.objects.create(CompanyName="شركة تزامن M2")
        UserCompanyMembership.objects.create(user=self.manager, tenant=self.tenant, role="manager")
        TenantModule.objects.create(tenant=self.tenant, module_key="accountant_portal", enabled=True)
        AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="accountant",
            tax_registration_number="TAX-MYSQL-M2",
            business_address="رام الله",
            email_verified_at=timezone.now(),
        )
        _, self.token = create_company_invitation(
            tenant=self.tenant,
            manager=self.manager,
            accountant=self.accountant,
            scope=["sales.invoice.view"],
        )

    def test_two_simultaneous_accepts_create_one_membership(self):
        barrier = threading.Barrier(2)
        results = []
        lock = threading.Lock()

        def accept():
            close_old_connections()
            user = User.objects.get(pk=self.accountant.pk)
            barrier.wait()
            try:
                accept_company_invitation(accountant=user, token=self.token)
                result = "accepted"
            except EngagementConflict as exc:
                result = exc.code
            finally:
                close_old_connections()
            with lock:
                results.append(result)

        threads = [threading.Thread(target=accept), threading.Thread(target=accept)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        self.assertEqual(sorted(results), ["accepted", "invitation_used"])
        self.assertEqual(
            UserCompanyMembership.objects.filter(user=self.accountant, tenant=self.tenant).count(),
            1,
        )
