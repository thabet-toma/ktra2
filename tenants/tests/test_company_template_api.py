"""ISSUE #50 — قالب الشركة: الحقل والبذرة عند الإنشاء عبر HTTP.

الملاحظة على الأثر — أسطر شجرة الحسابات وأنواع الدفاتر المزروعة وقيمة
`Tenant.template` — لا على استدعاء `create_company` مباشرة أو `post_journal`.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account
from tenants.company_templates import ACCOUNTING_FIRM_DOCUMENT_TYPES, ACCOUNTING_FIRM_COA
from tenants.models import Tenant, TenantBook
from tenants.services import COA_DATA, create_company

URL = "/api/tenants/companies/"


class GeneralTemplateApiTest(APITestCase):
    """شركة جديدة بلا قالب صريح (أو `general`) مطابقة حرفياً لما يُنتَج اليوم."""

    def setUp(self):
        self.user = User.objects.create_user(username="gen-owner", password="x")
        self.client.force_authenticate(user=self.user)

    def test_default_template_matches_todays_output(self):
        res = self.client.post(URL, {"CompanyName": "شركة عامة"}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["template"], "general")

        tenant = Tenant.objects.get(pk=body["TenantID"])
        self.assertEqual(tenant.template, "general")
        self.assertEqual(Account.objects.filter(tenant=tenant).count(), len(COA_DATA))
        self.assertEqual(
            TenantBook.objects.filter(tenant=tenant).count(),
            len(TenantBook.DOCUMENT_TYPES) * 10,
        )

    def test_explicit_general_template_matches_todays_output(self):
        res = self.client.post(
            URL, {"CompanyName": "شركة عامة صراحة", "template": "general"}, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        tenant = Tenant.objects.get(pk=res.json()["TenantID"])
        self.assertEqual(Account.objects.filter(tenant=tenant).count(), len(COA_DATA))


class AccountingFirmTemplateApiTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="firm-owner", password="x")
        self.client.force_authenticate(user=self.user)

    def test_accounting_firm_seeds_the_stated_tree_and_drops_commercial_accounts(self):
        res = self.client.post(
            URL, {"CompanyName": "مكتب المحاسبة", "template": "accounting_firm"},
            format="json")
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual(body["template"], "accounting_firm")

        tenant = Tenant.objects.get(pk=body["TenantID"])
        codes = set(Account.objects.filter(tenant=tenant).values_list("code", flat=True))

        self.assertEqual(codes, {row[0] for row in ACCOUNTING_FIRM_COA})
        # Dropped commercial-only accounts must be absent.
        for dropped in (
            "1104", "1106", "1201", "1202", "1203",
            "2105", "2106", "2107", "2108", "2109",
            "5101", "5301", "5305", "4101",
        ):
            self.assertNotIn(dropped, codes)
        # 4102 must stay present under its fixed code (rule: never renumbered).
        self.assertIn("4102", codes)
        fees_account = Account.objects.get(tenant=tenant, code="4102")
        self.assertEqual(fees_account.account_type, "Revenue")

    def test_accounting_firm_seeds_only_its_seven_document_types(self):
        res = self.client.post(
            URL, {"CompanyName": "مكتب المحاسبة الثاني", "template": "accounting_firm"},
            format="json")
        self.assertEqual(res.status_code, 201, res.content)
        tenant = Tenant.objects.get(pk=res.json()["TenantID"])

        seeded_types = set(
            TenantBook.objects.filter(tenant=tenant).values_list("document_type", flat=True)
        )
        self.assertEqual(seeded_types, set(ACCOUNTING_FIRM_DOCUMENT_TYPES))
        self.assertEqual(
            TenantBook.objects.filter(tenant=tenant).count(),
            len(ACCOUNTING_FIRM_DOCUMENT_TYPES) * 10,
        )

    def test_unknown_template_key_is_rejected(self):
        res = self.client.post(
            URL, {"CompanyName": "شركة قالب مجهول", "template": "not-a-real-template"},
            format="json")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertFalse(Tenant.objects.filter(CompanyName="شركة قالب مجهول").exists())


class TenantTemplateDefaultBackfillTest(APITestCase):
    """اختبار تراجُع: كل صفٍّ قائم (مُنشأ بدالة الخدمة مباشرة، كما قبل التذكرة)
    يحمل `template='general'` — الشركات القائمة لا تُسأل شيئاً (قرار 16)."""

    def test_existing_style_row_defaults_to_general(self):
        user = User.objects.create_user(username="pre-existing", password="x")
        tenant = create_company("شركة قديمة الطراز", user)
        tenant.refresh_from_db()
        self.assertEqual(tenant.template, "general")

    def test_row_written_without_the_field_at_all_defaults_to_general(self):
        """الصفّ القائم قبل الهجرة لم يُكتب فيه `template` إطلاقاً.

        `create_company` تضبط الحقل صراحةً، فاختبارُها وحده لا يثبت الافتراضي.
        هنا يُنشأ الصفّ بلا الحقل — كما كانت الصفوف تُكتب قبل التذكرة — فيثبت
        أن الافتراضي هو ما يحمله الصفّ لا ما تضعه دالّة الإنشاء.
        """
        tenant = Tenant.objects.create(
            CompanyName="شركة ما قبل الهجرة",
            SubscriptionPlan="Trial",
            Status="Trial",
        )
        tenant.refresh_from_db()
        self.assertEqual(tenant.template, "general")
