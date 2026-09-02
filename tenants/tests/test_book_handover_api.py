"""ISSUE #54 — مكتب المحاسبة: تسليم الدفاتر للعميل (نمط Xero).

الملاحظة على الأثر — صفوف `Tenant.managed_by`، عضويات الدفتر، قائمة
`managed-books`، وأسطر القيد/أرصدة الحسابات قبل التسليم وبعده — لا على
استدعاء `create_handover_request`/`accept_handover_request` مباشرة ولا على
شكلهما الداخلي.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from core.plans import invalidate_limit_cache
from partners.models import Partner
from sales.models import SalesSettings
from tenants.models import BookHandoverRequest, Currency, Tenant, UserCompanyMembership

COMPANIES_URL = "/api/tenants/companies/"
HANDOVER_URL = "/api/tenants/handover-requests/"


def _managed_books_url(office_id):
    return f"{COMPANIES_URL}{office_id}/managed-books/"


def _accept_url(request_id):
    return f"{HANDOVER_URL}{request_id}/accept/"


class BookHandoverApiTestBase(APITestCase):
    """قاعدة مشتركة: مكتبٌ ودفترٌ مُدار وعميلٌ مسجَّل مسبقاً — بشركةٍ ثالثة
    عمداً (كما في `ManagedBookSubscriptionFollowsOfficeTest`) لإبطال
    الحلّ التلقائي أحادي الشركة في `get_tenant`."""

    @classmethod
    def setUpTestData(cls):
        cls.office = Tenant.objects.create(
            CompanyName="مكتب التسليم", SubscriptionPlan="Pro", Status="Active",
        )
        cls.office_manager = User.objects.create_user(username="ho-office-mgr", password="x")
        UserCompanyMembership.objects.create(
            user=cls.office_manager, tenant=cls.office, role="manager",
        )
        cls.client_user = User.objects.create_user(username="ho-client", password="x")
        cls.outsider = User.objects.create_user(username="ho-outsider", password="x")
        # شركة ثالثة تمنع الحلّ التلقائي أحادي الشركة.
        Tenant.objects.create(CompanyName="شركة أخرى — تسليم", SubscriptionPlan="Pro", Status="Active")

    def setUp(self):
        invalidate_limit_cache(self.office.pk)
        self.client.force_authenticate(user=self.office_manager)
        created = self.client.post(
            _managed_books_url(self.office.pk),
            {"CompanyName": "دفتر العميل"}, format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.book_id = created.json()["TenantID"]
        self.book = Tenant.objects.get(pk=self.book_id)

    def _create_handover(self, **over):
        body = {"book_id": self.book_id, "client_username_or_email": self.client_user.username}
        body.update(over)
        self.client.force_authenticate(user=self.office_manager)
        return self.client.post(HANDOVER_URL, body, format="json")

    def _seed_journal_activity(self):
        """قيدٌ محاسبي حقيقي عبر مسار الإنتاج (سند قبض يُرحَّل تلقائياً) —
        كي تُقاس أرصدة الحسابات قبل التسليم وبعده على قيدٍ فعلي لا فراغ."""
        create_fiscal_year(self.book, 2026)
        ils = Currency.objects.filter(Code="ILS").first() or Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        customer = Partner.objects.create(
            tenant=self.book, name="عميل الدفتر", partner_type="Customer")
        cash = Account.objects.get(tenant=self.book, code="1101")
        SalesSettings.objects.update_or_create(
            tenant=self.book, defaults={"default_cash_account": cash},
        )
        res = self.client.post(
            "/api/sales/payments/",
            {
                "partner": customer.pk,
                "payment_date": "2026-08-20",
                "amount": "500.00",
                "currency": ils.pk,
                "cash_or_bank_account": cash.pk,
                "auto_post": True,
            },
            format="json", HTTP_X_TENANT_ID=str(self.book_id),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertIsNone(res.data.get("auto_post_error"), res.data)

    def _balance_snapshot(self):
        return list(
            JournalLine.objects.filter(tenant_id=self.book_id)
            .values("account_id")
            .order_by("account_id")
            .annotate(total_debit=Sum("debit"), total_credit=Sum("credit"))
        )


class HandoverPendingRequestChangesNothingTest(BookHandoverApiTestBase):
    """معيار: طلبٌ بلا قبول لا يغيّر شيئاً، وينتهي بانتهاء صلاحيته."""

    def test_creating_a_request_does_not_touch_managed_by(self):
        self._seed_journal_activity()
        before = self._balance_snapshot()

        res = self._create_handover()
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["status"], "pending")

        self.book.refresh_from_db()
        self.assertEqual(self.book.managed_by_id, self.office.pk)
        self.assertFalse(
            UserCompanyMembership.objects.filter(
                user=self.client_user, tenant_id=self.book_id).exists()
        )
        self.assertEqual(self._balance_snapshot(), before)

    def test_expired_request_cannot_be_accepted_and_changes_nothing(self):
        res = self._create_handover()
        req_id = res.json()["id"]
        BookHandoverRequest.objects.filter(pk=req_id).update(
            expires_at=timezone.now() - timedelta(seconds=1))

        self.client.force_authenticate(user=self.client_user)
        accept_res = self.client.post(_accept_url(req_id))
        self.assertEqual(accept_res.status_code, 400, accept_res.content)

        self.book.refresh_from_db()
        self.assertEqual(self.book.managed_by_id, self.office.pk)
        self.assertFalse(
            UserCompanyMembership.objects.filter(
                user=self.client_user, tenant_id=self.book_id).exists()
        )
        self.assertEqual(
            BookHandoverRequest.objects.get(pk=req_id).status, "expired")


class HandoverAcceptanceEffectsTest(BookHandoverApiTestBase):
    """معايير: بعد القبول — ملكية العميل، خروج من قائمة الدفاتر المُدارة،
    تحرّر الحصّة، بقاء وصول المكتب، وتطابق أرصدة دليل الحسابات حرفياً."""

    def setUp(self):
        super().setUp()
        self._seed_journal_activity()
        self.before_balances = self._balance_snapshot()
        res = self._create_handover()
        self.assertEqual(res.status_code, 201, res.content)
        self.request_id = res.json()["id"]

    def _accept(self):
        self.client.force_authenticate(user=self.client_user)
        res = self.client.post(_accept_url(self.request_id))
        self.assertEqual(res.status_code, 200, res.content)
        return res

    def test_client_becomes_manager_and_book_leaves_managed_flag(self):
        self._accept()
        self.book.refresh_from_db()
        self.assertIsNone(self.book.managed_by_id)
        self.assertTrue(
            UserCompanyMembership.objects.filter(
                user=self.client_user, tenant_id=self.book_id, role="manager").exists()
        )

    def test_book_leaves_the_office_managed_books_list_and_quota_frees(self):
        self._accept()
        self.client.force_authenticate(user=self.office_manager)
        res = self.client.get(_managed_books_url(self.office.pk))
        self.assertEqual(res.status_code, 200, res.content)
        ids = {row["TenantID"] for row in res.json()}
        self.assertNotIn(self.book_id, ids)
        self.assertEqual(Tenant.objects.filter(managed_by=self.office).count(), 0)

    def test_office_access_survives_acceptance_until_explicitly_revoked(self):
        self._accept()
        office_membership = UserCompanyMembership.objects.filter(
            user=self.office_manager, tenant_id=self.book_id).first()
        self.assertIsNotNone(office_membership)

        # الإلغاء إجراءٌ منفصل صريح — مسار «إزالة عضو» القائم أصلاً، والمدير
        # الجديد (العميل) هو من يستدعيه.
        self.client.force_authenticate(user=self.client_user)
        revoke = self.client.post(
            f"{COMPANIES_URL}{self.book_id}/members/remove/",
            {"membership_id": office_membership.pk}, format="json",
        )
        self.assertEqual(revoke.status_code, 200, revoke.content)
        self.assertFalse(
            UserCompanyMembership.objects.filter(pk=office_membership.pk).exists()
        )

    def test_chart_of_accounts_balances_are_byte_identical_after_handover(self):
        self._accept()
        self.assertEqual(self._balance_snapshot(), self.before_balances)

    def test_handed_over_book_is_not_expired_the_moment_it_arrives(self):
        """«بلا لحظة انقطاعٍ واحدة» شرطُ قبولٍ لا تفصيلُ واجهة.

        الدفتر أُنشئ بـ`create_company` فحمل تجربةً تبدأ **يوم فتحه المكتب**،
        وطالما كان مُداراً قرأ اشتراكه من مكتبه (`core/plans.py` —
        `_billing_tenant`) فلم يظهر الأثر. لحظةَ سقوط `managed_by` يعود إلى
        ساعته هو — وهي ساعةٌ بدأت قبل شهور. فيستلم العميل شركةً للقراءة فقط:
        نفس فجوة QuickBooks التي رفضتها التذكرة نصّاً.
        """
        book = Tenant.objects.get(pk=self.book_id)
        book.subscription_ends_at = timezone.localdate() - timedelta(days=60)
        book.save(update_fields=["subscription_ends_at"])

        self._accept()

        self.client.force_authenticate(user=self.client_user)
        card = self.client.get(
            f"{COMPANIES_URL}{self.book_id}/",
            HTTP_X_TENANT_ID=str(self.book_id),
        )
        self.assertEqual(card.status_code, 200, card.content)
        self.assertFalse(card.json()["subscription_expired"], card.content)


class HandoverIsolationTest(BookHandoverApiTestBase):
    """معايير عزل: فقط مدير المكتب يبدأ التسليم، وفقط العميل المدعوّ يقبله."""

    def test_non_office_manager_cannot_create_a_handover_request(self):
        self.client.force_authenticate(user=self.outsider)
        res = self.client.post(
            HANDOVER_URL,
            {"book_id": self.book_id, "client_username_or_email": self.client_user.username},
            format="json",
        )
        self.assertEqual(res.status_code, 400, res.content)
        self.book.refresh_from_db()
        self.assertEqual(self.book.managed_by_id, self.office.pk)

    def test_only_the_invited_client_can_accept(self):
        res = self._create_handover()
        req_id = res.json()["id"]

        self.client.force_authenticate(user=self.outsider)
        accept_res = self.client.post(_accept_url(req_id))
        self.assertEqual(accept_res.status_code, 400, accept_res.content)

        self.book.refresh_from_db()
        self.assertEqual(self.book.managed_by_id, self.office.pk)
        self.assertFalse(
            UserCompanyMembership.objects.filter(
                user=self.outsider, tenant_id=self.book_id).exists()
        )

    def test_cannot_open_a_second_pending_request_on_the_same_book(self):
        first = self._create_handover()
        self.assertEqual(first.status_code, 201, first.content)
        second = self._create_handover()
        self.assertEqual(second.status_code, 400, second.content)

    def test_unknown_client_identifier_is_rejected(self):
        res = self._create_handover(client_username_or_email="no-such-user-xyz")
        self.assertEqual(res.status_code, 400, res.content)
