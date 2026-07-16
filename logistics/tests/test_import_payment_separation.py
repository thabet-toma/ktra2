"""فصل استحقاق تكاليف الاستيراد عن دفعها (تخليص + نقل محلي)."""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, CashBoxLedgerAccount, JournalHeader
from accounting.services import create_fiscal_year
from logistics.models import (
    LocalShipment,
    LocalShipmentPayment,
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsShipment,
    PurchaseInvoice,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


D = lambda value: Decimal(str(value))


class ImportPaymentSeparationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="import-pay", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة فصل دفعات الاستيراد", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)

        cls.clearance_expense = Account.objects.get(tenant=cls.tenant, code="5302")
        cls.local_expense = Account.objects.get(tenant=cls.tenant, code="5305")
        cls.cash_account = Account.objects.create(
            tenant=cls.tenant, code="BOX-IMPORT", name="صندوق الاستيراد",
            account_type="Asset", is_active=True,
        )
        cls.broker_ap = Account.objects.create(
            tenant=cls.tenant, code="AP-BROKER", name="ذمم المخلص",
            account_type="Liability", is_active=True,
        )
        cls.carrier_ap = Account.objects.create(
            tenant=cls.tenant, code="AP-CARRIER", name="ذمم الناقل",
            account_type="Liability", is_active=True,
        )
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="import-box", name="صندوق الاستيراد",
            currency_code="ILS", account=cls.cash_account,
        )
        cls.broker = Partner.objects.create(
            tenant=cls.tenant, name="مخلص الاستيراد", partner_type="CustomsBroker",
            linked_account=cls.broker_ap,
        )
        cls.carrier = Partner.objects.create(
            tenant=cls.tenant, name="الناقل المحلي", partner_type="LocalTransporter",
            linked_account=cls.carrier_ap,
        )
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-SEP-1",
        )
        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, customs_broker=cls.broker,
            clearance_date="2026-07-01", currency=cls.ils,
        )
        LogisticsClearanceLine.objects.create(
            clearance=cls.clearance, seq=1, line_type="broker_commission",
            account=cls.clearance_expense, description="رسوم تخليص",
            debit=D("600"), credit=D("0"),
        )
        cls.local = LocalShipment.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, clearance=cls.clearance,
            carrier=cls.carrier, amount=D("400"), currency=cls.ils,
            exchange_rate=D("1"), payment_type="cash", expense_account=cls.local_expense,
            cash_or_bank_account=cls.cash_account, delivery_date="2026-07-02",
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_clearance_accrual_and_payment_are_two_distinct_journals(self):
        accrued = self.client.post(
            f"/api/logistics/clearances/{self.clearance.pk}/post-to-accounting/",
            {}, format="json", **self._auth(),
        )
        self.assertEqual(accrued.status_code, 201, accrued.content)
        accrual_journal = JournalHeader.objects.get(
            reference_type="LOGISTICS_CLEARANCE", reference_id=self.clearance.pk,
        )
        self.assertTrue(accrual_journal.lines.filter(
            account=self.clearance_expense, debit=D("600.00"),
        ).exists())
        self.assertTrue(accrual_journal.lines.filter(
            account=self.broker_ap, credit=D("600.00"), partner=self.broker,
        ).exists())

        paid = self.client.post(
            f"/api/logistics/clearances/{self.clearance.pk}/pay_from_cashbox/",
            {"amount": "250", "cash_box_external_id": self.box.external_id,
             "payment_date": "2026-07-03"},
            format="json", **self._auth(),
        )
        self.assertEqual(paid.status_code, 201, paid.content)
        payment_journal = JournalHeader.objects.get(reference_type="CLEARANCE_PAYMENT")
        self.assertNotEqual(payment_journal.pk, accrual_journal.pk)
        self.assertTrue(payment_journal.lines.filter(
            account=self.broker_ap, debit=D("250.00"), partner=self.broker,
        ).exists())
        self.assertTrue(payment_journal.lines.filter(
            account=self.cash_account, credit=D("250.00"),
        ).exists())
        detail = self.client.get(
            f"/api/logistics/clearances/{self.clearance.pk}/", **self._auth(),
        )
        self.assertEqual(D(detail.json()["amount_paid"]), D("250.00"))
        self.assertEqual(D(detail.json()["remaining_balance"]), D("350.00"))
        self.assertEqual(detail.json()["payment_status"], "partially_paid")

    def test_clearance_payment_alone_does_not_lock_cost_document(self):
        self.clearance.journal = None
        self.clearance.save(update_fields=["journal"])
        paid = self.client.post(
            f"/api/logistics/clearances/{self.clearance.pk}/pay_from_cashbox/",
            {"amount": "50", "cash_box_external_id": self.box.external_id,
             "payment_date": "2026-07-03"},
            format="json", **self._auth(),
        )
        self.assertEqual(paid.status_code, 201, paid.content)
        changed = self.client.patch(
            f"/api/logistics/clearances/{self.clearance.pk}/",
            {"notes": "دفعة مقدمة للمخلص لا تقفل المستند"},
            format="json", **self._auth(),
        )
        self.assertEqual(changed.status_code, 200, changed.content)

    def test_local_transport_accrual_then_partial_payment(self):
        accrued = self.client.post(
            f"/api/logistics/local-shipments/{self.local.pk}/post-to-accounting/",
            {}, format="json", **self._auth(),
        )
        self.assertEqual(accrued.status_code, 200, accrued.content)
        accrual_journal = JournalHeader.objects.get(
            reference_type="LOCAL_SHIPMENT", reference_id=self.local.pk,
        )
        self.assertTrue(accrual_journal.lines.filter(
            account=self.local_expense, debit=D("400.00"),
        ).exists())
        self.assertTrue(accrual_journal.lines.filter(
            account=self.carrier_ap, credit=D("400.00"), partner=self.carrier,
        ).exists())
        self.assertFalse(accrual_journal.lines.filter(account=self.cash_account).exists())

        paid = self.client.post(
            f"/api/logistics/local-shipments/{self.local.pk}/pay_from_cashbox/",
            {"amount": "150", "cash_box_external_id": self.box.external_id,
             "payment_date": "2026-07-04"},
            format="json", **self._auth(),
        )
        self.assertEqual(paid.status_code, 201, paid.content)
        payment = LocalShipmentPayment.objects.get(local_shipment=self.local)
        payment_journal = JournalHeader.objects.get(
            reference_type="LOCAL_SHIPMENT_PAYMENT", reference_id=payment.pk,
        )
        self.assertTrue(payment_journal.lines.filter(
            account=self.carrier_ap, debit=D("150.00"), partner=self.carrier,
        ).exists())
        self.assertTrue(payment_journal.lines.filter(
            account=self.cash_account, credit=D("150.00"),
        ).exists())

        detail = self.client.get(
            f"/api/logistics/local-shipments/{self.local.pk}/", **self._auth(),
        )
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(D(detail.json()["amount_paid"]), D("150.00"))
        self.assertEqual(D(detail.json()["remaining_balance"]), D("250.00"))
        self.assertEqual(detail.json()["payment_status"], "partially_paid")

    def test_local_transport_rejects_overpayment(self):
        LocalShipmentPayment.objects.create(
            tenant=self.tenant, local_shipment=self.local, amount=D("350"),
            currency=self.ils, payment_date="2026-07-03",
            cash_box_external_id=self.box.external_id, is_posted=True,
        )
        resp = self.client.post(
            f"/api/logistics/local-shipments/{self.local.pk}/pay_from_cashbox/",
            {"amount": "60", "cash_box_external_id": self.box.external_id},
            format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("المتبقي", resp.json()["error"])

    def test_international_invoice_persists_additional_fee_and_exposes_payable_total(self):
        created = self.client.post(
            "/api/logistics/purchase-invoices/",
            {
                "invoice_type": "international",
                "invoice_date": "2026-07-05",
                "partner": self.broker.pk,
                "currency": "ILS",
                "subtotal": "1000",
                "tax_amount": "0",
                "grand_total": "1000",
                "status": "draft",
                "items": [{
                    "name": "بضاعة مستوردة", "quantity": "1",
                    "unit_price": "1000", "total_price": "1000",
                }],
                "fees": [{
                    "description": "رسوم فحص إضافية", "amount": "100",
                    "expense_account": self.clearance_expense.pk,
                    "capitalize_to_inventory": False, "is_taxable": False,
                }],
            },
            format="json", **self._auth(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()
        self.assertEqual(len(body["fees"]), 1)
        self.assertEqual(D(body["fees_total"]), D("100.00"))
        self.assertEqual(D(body["payable_total"]), D("1100.00"))
        self.assertEqual(D(body["remaining_balance"]), D("1100.00"))

        updated = self.client.patch(
            f"/api/logistics/purchase-invoices/{body['id']}/",
            {"fees": [{
                "description": "رسوم فحص معدّلة", "amount": "125",
                "expense_account": self.clearance_expense.pk,
                "capitalize_to_inventory": True, "is_taxable": False,
            }]},
            format="json", **self._auth(),
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{body['id']}/", **self._auth(),
        )
        self.assertEqual(detail.status_code, 200, detail.content)
        saved_fee = detail.json()["fees"][0]
        self.assertEqual(saved_fee["description"], "رسوم فحص معدّلة")
        self.assertEqual(D(saved_fee["amount"]), D("125.00"))
        self.assertTrue(saved_fee["capitalize_to_inventory"])
        self.assertEqual(D(detail.json()["fees_total"]), D("125.00"))
        self.assertEqual(D(detail.json()["payable_total"]), D("1125.00"))

    def test_percentage_fee_persists_basis_and_calculates_amount_on_server(self):
        created = self.client.post(
            "/api/logistics/purchase-invoices/",
            {
                "invoice_type": "international",
                "invoice_date": "2026-07-05",
                "partner": self.broker.pk,
                "currency": "ILS",
                "subtotal": "1000",
                "tax_rate": "16",
                "tax_amount": "160",
                "grand_total": "1160",
                "status": "draft",
                "items": [{
                    "name": "بضاعة مستوردة", "quantity": "1",
                    "unit_price": "1000", "total_price": "1000",
                }],
                "fees": [{
                    "description": "رسم كترا", "amount": "999",
                    "calculation_type": "percentage",
                    "calculation_value": "10",
                    "percentage_basis": "after_main_vat",
                    "expense_account": self.clearance_expense.pk,
                    "capitalize_to_inventory": False, "is_taxable": False,
                }],
            },
            format="json", **self._auth(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        fee = created.json()["fees"][0]
        self.assertEqual(fee["calculation_type"], "percentage")
        self.assertEqual(D(fee["calculation_value"]), D("10.00"))
        self.assertEqual(fee["percentage_basis"], "after_main_vat")
        self.assertEqual(D(fee["amount"]), D("116.00"))
        self.assertEqual(D(created.json()["payable_total"]), D("1276.00"))

        updated = self.client.patch(
            f"/api/logistics/purchase-invoices/{created.json()['id']}/",
            {
                "subtotal": "2000", "tax_amount": "320", "grand_total": "2320",
                "fees": [{
                    "description": "رسم كترا", "amount": "999",
                    "calculation_type": "percentage", "calculation_value": "10",
                    "percentage_basis": "after_main_vat",
                    "expense_account": self.clearance_expense.pk,
                    "capitalize_to_inventory": False, "is_taxable": False,
                }],
            },
            format="json", **self._auth(),
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(D(updated.json()["fees"][0]["amount"]), D("232.00"))
        self.assertEqual(D(updated.json()["payable_total"]), D("2552.00"))

    def test_additional_fee_posts_balanced_on_top_of_invoice_total(self):
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="IMP-FEE-1",
            invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            invoice_date="2026-07-05", partner=self.broker, currency=self.ils,
            subtotal=D("1000"), grand_total=D("1000"),
        )
        invoice.items.create(
            name="بضاعة مستوردة", quantity=D("1"),
            unit_price=D("1000"), total_price=D("1000"),
        )
        invoice.fees.create(
            tenant=self.tenant, description="رسوم فحص إضافية", amount=D("100"),
            expense_account=self.clearance_expense, capitalize_to_inventory=False,
        )
        posted = self.client.post(
            f"/api/logistics/purchase-invoices/{invoice.pk}/post-to-accounting/",
            {}, format="json", **self._auth(),
        )
        self.assertEqual(posted.status_code, 201, posted.content)
        journal = JournalHeader.objects.get(
            reference_type="PURCHASE_INVOICE", reference_id=invoice.pk,
        )
        debit = sum((line.debit for line in journal.lines.all()), D("0"))
        credit = sum((line.credit for line in journal.lines.all()), D("0"))
        self.assertEqual(debit, D("1100.00"))
        self.assertEqual(credit, D("1100.00"))
        self.assertTrue(journal.lines.filter(
            account=self.clearance_expense, debit=D("100.00"),
        ).exists())
