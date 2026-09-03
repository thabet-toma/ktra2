"""ISSUE #82 — المعجم: `term()`/`terms_payload()` والتسليم على `/api/permissions/me`."""
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from core.terminology import term, terms_payload
from tenants.services import create_company


class _StubTenant:
    """كائنٌ بسيط لاختبار `term()` بلا قاعدة بيانات — كل ما تقرأه `template`."""

    def __init__(self, template):
        self.template = template


class TermFunctionTest(SimpleTestCase):
    def test_general_template_matches_todays_wording(self):
        general = _StubTenant("general")
        self.assertEqual(term(general, "doc.sales_invoice"), "فاتورة مبيعات")
        self.assertEqual(term(general, "line.item"), "منتج")

    def test_accounting_firm_sees_fee_invoice_and_service(self):
        firm = _StubTenant("accounting_firm")
        self.assertEqual(term(firm, "doc.sales_invoice"), "فاتورة أتعاب")
        self.assertEqual(term(firm, "line.item"), "خدمة")

    def test_client_book_sees_service_but_no_sales_invoice_override(self):
        """`client_book` يخفي فاتورة المبيعات بالقناع الحيّ — لا حاجة لتجاوز اسمها."""
        book = _StubTenant("client_book")
        self.assertEqual(term(book, "line.item"), "خدمة")
        # بلا تجاوز خاص، تسقط لافتراضي البذرة التجارية بلا رمي.
        self.assertEqual(term(book, "doc.sales_invoice"), "فاتورة مبيعات")

    def test_missing_key_falls_back_to_the_key_itself_without_raising(self):
        general = _StubTenant("general")
        self.assertEqual(term(general, "doc.no-such-term"), "doc.no-such-term")

    def test_missing_tenant_falls_back_to_general(self):
        self.assertEqual(term(None, "doc.sales_invoice"), "فاتورة مبيعات")

    def test_unknown_template_falls_back_to_default_terms(self):
        weird = _StubTenant("not-a-real-template")
        self.assertEqual(term(weird, "doc.sales_invoice"), "فاتورة مبيعات")

    def test_terms_payload_carries_the_full_document_type_catalog(self):
        general = _StubTenant("general")
        payload = terms_payload(general)
        # التسعة عشر مفتاحاً — سبعة عشر نوع مستند + بند السطر — مصدرها الوحيد
        # `TenantBook.DOCUMENT_TYPES`، لا نسخة موازية مكتوبة هنا.
        self.assertEqual(payload["doc.receipt_voucher"], "سند قبض")
        self.assertEqual(payload["doc.payment_voucher"], "سند صرف")
        self.assertEqual(payload["line.item"], "منتج")

    def test_terms_payload_reflects_template_overrides(self):
        firm = _StubTenant("accounting_firm")
        payload = terms_payload(firm)
        self.assertEqual(payload["doc.sales_invoice"], "فاتورة أتعاب")
        self.assertEqual(payload["line.item"], "خدمة")
        # ما لا يتبدّل بالقالب يبقى كما هو — سند القبض واحد في كل القوالب.
        self.assertEqual(payload["doc.receipt_voucher"], "سند قبض")


class PermissionsMePayloadCarriesTermsTest(APITestCase):
    """المعجم يصل على حمولة `/api/permissions/me` نفسها — القرار 8 في #46: لا آلية ثالثة."""

    def _as(self, user, tenant):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(tenant.TenantID)}

    def test_general_company_sees_todays_wording_unchanged(self):
        user = User.objects.create_user(username="term-gen-owner", password="x")
        tenant = create_company("شركة عامة للمعجم", user)
        res = self.client.get("/api/permissions/me/", **self._as(user, tenant))
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertIn("terms", body)
        self.assertEqual(body["terms"]["doc.sales_invoice"], "فاتورة مبيعات")
        self.assertEqual(body["terms"]["line.item"], "منتج")

    def test_accounting_firm_company_sees_fee_invoice_and_service(self):
        user = User.objects.create_user(username="term-firm-owner", password="x")
        tenant = create_company("مكتب محاسبة للمعجم", user, template="accounting_firm")
        res = self.client.get("/api/permissions/me/", **self._as(user, tenant))
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual(body["terms"]["doc.sales_invoice"], "فاتورة أتعاب")
        self.assertEqual(body["terms"]["line.item"], "خدمة")
