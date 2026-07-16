"""دفع صفقة بالدولار من صندوق FIFO + فرق الصرف المحقّق (المرحلة 3).

عند الدفع: مدين ذمم المورد بقيمة الذمة (مبلغ × سعر الدفع)، دائن صندوق الدولار
بتكلفة FIFO، والفرق = ربح/خسارة فرق صرف محقّق.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.fx_fifo import fund_box_from_capital, get_realized_fx_account
from accounting.models import Account, CashBoxLedgerAccount, JournalHeader
from accounting.cashbox import get_cash_box_parent_account
from accounting.services import create_fiscal_year
from logistics.models import LogisticsDeal, LogisticsPayment
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class DealPaymentFifoTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dp", password="x", email="dp@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة الدفع", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        parent = get_cash_box_parent_account(cls.tenant)
        ap = Account.objects.create(tenant=cls.tenant, code="AP-S1", name="ذمم مورد",
            parent=parent, account_type="Liability", is_active=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد دولي", partner_type="Supplier", linked_account=ap)
        usd_acc = Account.objects.create(tenant=cls.tenant, code="USDBOX", name="صندوق الدولار",
            parent=parent, account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="usd1", name="صندوق الدولار",
            currency_code="USD", account=usd_acc)
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number="D-9001", partner=cls.partner,
            order_date="2026-06-20", total_amount=D("10000"), currency=cls.usd,
            currency_rate=D("3.5"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _payment(self):
        return LogisticsPayment.objects.create(
            deal=self.deal, title="P1", amount=D("1000"), status="Confirmed",
            usd_to_ils=D("3.5"), transfer_date="2026-06-20")

    def _post(self, payment):
        return self.client.post(
            f"/api/logistics/deals/{self.deal.pk}/post_payment/{payment.pk}/",
            {"cash_box_external_id": "usd1"}, format="json", **self._auth())

    def test_fifo_payment_books_realized_fx_gain(self):
        # صندوق ممول 1000$ بسعر 3 ⇒ تكلفة FIFO = 3000؛ الدفع بسعر 3.5 ⇒ ذمة 3500
        fund_box_from_capital(self.box, 1000, 3, date="2026-06-19", user=self.user)
        pay = self._payment()
        resp = self._post(pay)
        self.assertEqual(resp.status_code, 200, resp.content)
        jh = JournalHeader.objects.get(reference_type="LOGISTICS_PAYMENT", reference_id=pay.id)
        fx = get_realized_fx_account(self.tenant)
        self.assertTrue(jh.lines.filter(account=self.partner.linked_account, debit=D("3500.00")).exists())
        self.assertTrue(jh.lines.filter(account=self.box.account, credit=D("3000.00")).exists())
        self.assertTrue(jh.lines.filter(account=fx, credit=D("500.00")).exists())  # ربح
        # تأكيد التوازن
        from django.db.models import Sum
        agg = jh.lines.aggregate(d=Sum("debit"), c=Sum("credit"))
        self.assertEqual(agg["d"], agg["c"])

    def test_fifo_payment_books_realized_fx_loss(self):
        # صندوق ممول 1000$ بسعر 4 ⇒ تكلفة FIFO = 4000؛ الدفع بسعر 3.5 ⇒ ذمة 3500 ⇒ خسارة 500
        fund_box_from_capital(self.box, 1000, 4, date="2026-06-19", user=self.user)
        pay = self._payment()
        resp = self._post(pay)
        self.assertEqual(resp.status_code, 200, resp.content)
        jh = JournalHeader.objects.get(reference_type="LOGISTICS_PAYMENT", reference_id=pay.id)
        fx = get_realized_fx_account(self.tenant)
        self.assertTrue(jh.lines.filter(account=self.box.account, credit=D("4000.00")).exists())
        self.assertTrue(jh.lines.filter(account=fx, debit=D("500.00")).exists())  # خسارة

    def test_non_fifo_box_keeps_legacy_behavior(self):
        # صندوق بلا طبقات ⇒ السلوك القديم: دائن الصندوق بنفس قيمة الذمة، بلا فرق صرف
        pay = self._payment()
        resp = self._post(pay)
        self.assertEqual(resp.status_code, 200, resp.content)
        jh = JournalHeader.objects.get(reference_type="LOGISTICS_PAYMENT", reference_id=pay.id)
        self.assertTrue(jh.lines.filter(account=self.box.account, credit=D("3500.00")).exists())
        self.assertIsNone(jh.lines.get(account=self.box.account).partner_id)
        self.assertEqual(jh.lines.get(account=self.partner.linked_account).partner_id, self.partner.id)
        self.assertEqual(jh.lines.count(), 2)


class AgentPaymentFifoTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from logistics.models import LogisticsShipment
        cls.user = User.objects.create_user(username="agf", password="x", email="agf@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة الوكيل", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        parent = get_cash_box_parent_account(cls.tenant)
        ap = Account.objects.create(tenant=cls.tenant, code="AP-AG", name="ذمم وكيل",
            parent=parent, account_type="Liability", is_active=True)
        cls.agent = Partner.objects.create(
            tenant=cls.tenant, name="وكيل شحن", partner_type="Supplier", linked_account=ap)
        usd_acc = Account.objects.create(tenant=cls.tenant, code="USDBOX", name="صندوق الدولار",
            parent=parent, account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="usd1", name="صندوق الدولار",
            currency_code="USD", account=usd_acc)
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-AG1", shipping_agent=cls.agent,
            total_shipping_cost_usd=D("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_agent_payment_fifo_gain(self):
        fund_box_from_capital(self.box, 1000, 3, date="2026-06-19", user=self.user)
        pay = LogisticsPayment.objects.create(
            shipment=self.shipment, title="AP1", amount=D("1000"), status="Confirmed",
            usd_to_ils=D("3.5"), transfer_date="2026-06-20")
        resp = self.client.post(
            f"/api/logistics/shipments/{self.shipment.pk}/post_agent_payment/{pay.pk}/",
            {"cash_box_external_id": "usd1"}, format="json", **self._auth())
        self.assertEqual(resp.status_code, 200, resp.content)
        jh = JournalHeader.objects.get(reference_type="LOGISTICS_PAYMENT", reference_id=pay.id)
        fx = get_realized_fx_account(self.tenant)
        self.assertTrue(jh.lines.filter(account=self.agent.linked_account, debit=D("3500.00")).exists())
        self.assertTrue(jh.lines.filter(account=self.box.account, credit=D("3000.00")).exists())
        self.assertTrue(jh.lines.filter(account=fx, credit=D("500.00")).exists())

    def test_posted_shipment_accepts_new_payment_for_increased_freight(self):
        self.shipment.total_shipping_cost_usd = D("540")
        self.shipment.save(update_fields=["total_shipping_cost_usd"])
        old_payment = LogisticsPayment.objects.create(
            shipment=self.shipment,
            title="دفعة شحن 1",
            payment_number=1,
            amount=D("270"),
            status="Confirmed",
            confirmed_by_supplier=True,
            is_posted=True,
            usd_to_ils=D("3.24"),
            transfer_date="2026-07-14",
        )
        JournalHeader.objects.create(
            tenant=self.tenant,
            transaction_date="2026-07-14",
            reference_type="LOGISTICS_SHIPMENT",
            reference_id=self.shipment.pk,
            description="قيد تكلفة شحن سابق",
            is_posted=True,
        )

        response = self.client.patch(
            f"/api/logistics/shipments/{self.shipment.pk}/",
            {
                "payments": [
                    {
                        "id": old_payment.pk,
                        "payment_number": 1,
                        "title": "دفعة شحن 1",
                        "amount": "270",
                        "status": "Confirmed",
                        "confirmed_by_supplier": True,
                        "usd_to_ils": "3.24",
                        "transfer_date": "2026-07-14",
                    },
                    {
                        "payment_number": 2,
                        "title": "دفعة شحن 2",
                        "amount": "270",
                        "status": "Confirmed",
                        "confirmed_by_supplier": True,
                        "usd_to_ils": "3.6",
                        "transfer_date": "2026-07-16",
                    },
                ],
            },
            format="json",
            **self._auth(),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.shipment.agent_payments.count(), 2)
        old_payment.refresh_from_db()
        self.assertTrue(old_payment.is_posted)
        self.assertTrue(
            self.shipment.agent_payments.filter(
                payment_number=2,
                amount=D("270"),
                is_posted=False,
            ).exists()
        )
        blocked = self.client.patch(
            f"/api/logistics/shipments/{self.shipment.pk}/",
            {"shipment_name": "تعديل غير مالي"},
            format="json",
            **self._auth(),
        )
        self.assertEqual(blocked.status_code, 400)


class ClearancePaymentFifoTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        from logistics.models import LogisticsShipment, LogisticsClearance
        from accounting.models import ExchangeRate
        cls.user = User.objects.create_user(username="clf", password="x", email="clf@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة التخليص", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        ExchangeRate.objects.create(
            tenant=cls.tenant, from_currency=cls.usd, to_currency=cls.ils,
            rate=D("3.5"), effective_date="2026-01-01")
        parent = get_cash_box_parent_account(cls.tenant)
        ap = Account.objects.create(tenant=cls.tenant, code="AP-BR", name="ذمم مخلّص",
            parent=parent, account_type="Liability", is_active=True)
        cls.broker = Partner.objects.create(
            tenant=cls.tenant, name="مخلّص", partner_type="Supplier", linked_account=ap)
        usd_acc = Account.objects.create(tenant=cls.tenant, code="USDBOX", name="صندوق الدولار",
            parent=parent, account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="usd1", name="صندوق الدولار",
            currency_code="USD", account=usd_acc)
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-CL1")
        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, customs_broker=cls.broker)

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_clearance_payment_fifo_gain(self):
        fund_box_from_capital(self.box, 1000, 3, date="2026-06-19", user=self.user)
        resp = self.client.post(
            f"/api/logistics/clearances/{self.clearance.pk}/pay_from_cashbox/",
            {"payment_kind": "clearance", "amount": "1000", "currency_id": self.usd.pk,
             "cash_box_external_id": "usd1", "payment_date": "2026-06-20"},
            format="json", **self._auth())
        self.assertEqual(resp.status_code, 201, resp.content)
        jh = JournalHeader.objects.get(reference_type="CLEARANCE_PAYMENT")
        fx = get_realized_fx_account(self.tenant)
        self.assertTrue(jh.lines.filter(account=self.broker.linked_account, debit=D("3500.00")).exists())
        self.assertTrue(jh.lines.filter(account=self.box.account, credit=D("3000.00")).exists())
        self.assertTrue(jh.lines.filter(account=fx, credit=D("500.00")).exists())
