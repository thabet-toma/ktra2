"""إيقاف الطرف وحذفه: الموقوف يختفي من القوائم والمنتقيات وتبقى حركاته، وحذف طرفٍ
عليه حركات يُرفض برسالة (كان 500 من `ProtectedError`، أو يمرّ بصمت ويمسح وسم الطرف
عن القيود عبر علاقات `SET_NULL`)، وحذف طرفٍ بلا حركات يحذف حسابه الفارغ من الشجرة.
"""
import datetime

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalLine
from partners.models import CustomerNote, Partner
from sales.models import SalesQuotation
from tenants.models import Currency
from tenants.services import create_company


class PartnerDeactivateDeleteTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="ppdel", password="x")
        cls.currency = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الإيقاف", cls.user)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _ids(self, url):
        res = self.client.get(url, **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        rows = res.data["results"] if isinstance(res.data, dict) else res.data
        return {r["id"] for r in rows}

    def test_inactive_partner_hidden_from_lists_and_pickers_but_still_opens(self):
        active = Partner.objects.create(tenant=self.tenant, name="نشط", partner_type="Supplier")
        stopped = Partner.objects.create(tenant=self.tenant, name="موقوف", partner_type="Supplier")
        res = self.client.patch(f"/api/partners/{stopped.id}/", {"is_active": False}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertFalse(res.data["is_active"])

        listed = self._ids("/api/partners/?partner_type=Supplier")
        self.assertIn(active.id, listed)
        self.assertNotIn(stopped.id, listed)
        self.assertNotIn(stopped.id, self._ids("/api/partners/lookup/?partner_type=Supplier"))
        self.assertIn(stopped.id, self._ids("/api/partners/?partner_type=Supplier&include_inactive=1"))

        card = self.client.get(f"/api/partners/{stopped.id}/", **self.h)
        self.assertEqual(card.status_code, 200)

    def test_delete_with_tagged_journal_lines_is_refused_not_silently_untagged(self):
        # علاقة القيد بالطرف SET_NULL: بلا الحارس يمرّ الحذف ويفقد القيد طرفه.
        partner = Partner.objects.create(
            tenant=self.tenant, name="مخلّص برصيد", partner_type="CustomsBroker",
            opening_balance=500, opening_balance_date=datetime.date(2026, 1, 1),
        )
        self.assertTrue(JournalLine.objects.filter(partner=partner).exists())

        res = self.client.delete(f"/api/partners/{partner.id}/", **self.h)
        self.assertEqual(res.status_code, 400, getattr(res, "data", None))
        self.assertIn("أوقفه بدل حذفه", str(res.data))
        self.assertTrue(Partner.objects.filter(pk=partner.pk).exists())

    def test_delete_with_protected_document_returns_message_not_500(self):
        customer = Partner.objects.create(tenant=self.tenant, name="زبون بعرض", partner_type="Customer")
        SalesQuotation.objects.create(
            tenant=self.tenant, quotation_number="QT-DEL-1", customer=customer,
            quotation_date=datetime.date(2026, 7, 1), currency=self.currency,
        )
        res = self.client.delete(f"/api/partners/{customer.id}/", **self.h)
        self.assertEqual(res.status_code, 400)
        self.assertIn("عليه حركات", str(res.data))
        self.assertTrue(Partner.objects.filter(pk=customer.pk).exists())

    def test_delete_without_movements_removes_its_empty_account(self):
        partner = Partner.objects.create(tenant=self.tenant, name="طرف فارغ", partner_type="Carrier")
        partner.refresh_from_db()
        account_id = partner.linked_account_id
        self.assertIsNotNone(account_id)
        CustomerNote.objects.create(tenant=self.tenant, partner=partner, title="ملاحظة تُحذف معه")

        res = self.client.delete(f"/api/partners/{partner.id}/", **self.h)
        self.assertEqual(res.status_code, 204, getattr(res, "data", None))
        self.assertFalse(Partner.objects.filter(pk=partner.pk).exists())
        self.assertFalse(Account.objects.filter(pk=account_id).exists())
