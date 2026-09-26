"""بنود المخلّص من إعدادات الشركة، ورقم مطالبة المخلّص.

البند المتكرّر كان يُسجَّل «أخرى» على 5307؛ صار بنداً في الإعدادات باسمه وحسابه،
يحمله سطر التخليص إلى قيد الاستحقاق. ورقم المطالبة يصل بعد الإفراج غالباً، فيُعدَّل
وحده بعد ترحيل الاستحقاق.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from logistics.accruals import post_clearance_accrual
from logistics.models import ClearanceItemType, LogisticsClearance, LogisticsShipment
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class ClearanceItemsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="clr-items", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة البنود", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)
        cls.broker = Partner.objects.create(tenant=cls.tenant, name="حاييم", partner_type="CustomsBroker")
        cls.shipment = LogisticsShipment.objects.create(tenant=cls.tenant, shipment_number="SH-0020")
        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, customs_broker=cls.broker,
            clearance_date="2026-06-10", currency=cls.ils)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _items(self):
        resp = self.client.get("/api/logistics/clearance-item-types/", **self.h)
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def test_first_read_seeds_the_standard_items_with_their_accounts(self):
        rows = self._items()
        self.assertEqual(len(rows), 6)
        by_type = {r["legacy_type"]: r for r in rows}
        self.assertEqual(by_type["vat"]["account_code"], "1105")
        self.assertEqual(by_type["broker_commission"]["account_code"], "5302")
        self.assertEqual(len(self._items()), 6, "البذرة مرّة واحدة")

    def test_repeated_item_from_settings_carries_its_account_into_the_accrual(self):
        self._items()
        port = Account.objects.get(tenant=self.tenant, code="5307")
        created = self.client.post(
            "/api/logistics/clearance-item-types/",
            {"name": "رسوم الميناء", "account": port.id}, format="json", **self.h)
        self.assertEqual(created.status_code, 201, created.content)
        dup = self.client.post(
            "/api/logistics/clearance-item-types/", {"name": "رسوم الميناء"}, format="json", **self.h)
        self.assertEqual(dup.status_code, 400, dup.content)

        item_id = created.json()["id"]
        patched = self.client.patch(
            f"/api/logistics/clearances/{self.clearance.pk}/",
            {"cost_lines": [{"label": "", "amount": 350, "item_type": item_id}]},
            format="json", **self.h)
        self.assertEqual(patched.status_code, 200, patched.content)
        line = self.clearance.lines.get()
        self.assertEqual(line.item_type_id, item_id)
        self.assertEqual(line.account_id, port.id)
        self.assertEqual(line.description, "رسوم الميناء")
        self.assertEqual(patched.json()["cost_lines"][0]["item_type"], item_id)

        journal = post_clearance_accrual(LogisticsClearance.objects.get(pk=self.clearance.pk))
        debit = JournalLine.objects.get(journal=journal, debit__gt=0)
        self.assertEqual((debit.account_id, debit.debit), (port.id, Decimal("350.00")))

    def test_item_from_another_company_is_ignored(self):
        other_user = User.objects.create_user(username="clr-other", password="x")
        other = create_company("شركة أخرى", other_user)
        foreign = ClearanceItemType.objects.create(tenant=other, name="غريب")
        self.client.patch(
            f"/api/logistics/clearances/{self.clearance.pk}/",
            {"cost_lines": [{"label": "بند", "amount": 10, "item_type": foreign.pk}]},
            format="json", **self.h)
        self.assertIsNone(self.clearance.lines.get().item_type_id)

    def test_claim_number_is_editable_alone_after_the_accrual_is_posted(self):
        self.client.patch(
            f"/api/logistics/clearances/{self.clearance.pk}/",
            {"cost_lines": [{"label": "عمولة المخلص", "amount": 500}]}, format="json", **self.h)
        post_clearance_accrual(LogisticsClearance.objects.get(pk=self.clearance.pk))

        ok = self.client.patch(
            f"/api/logistics/clearances/{self.clearance.pk}/",
            {"broker_claim_number": "CLM-77"}, format="json", **self.h)
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json()["broker_claim_number"], "CLM-77")

        blocked = self.client.patch(
            f"/api/logistics/clearances/{self.clearance.pk}/",
            {"broker_claim_number": "CLM-78", "declaration_number": "X"}, format="json", **self.h)
        self.assertEqual(blocked.status_code, 400, blocked.content)
