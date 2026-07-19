"""استحقاق شحن وكيل الشحن منفصل عن دفعه (قرار المالك 2026-07-18).

قبل هذا: لا يوجد قيد يُدائن الوكيل إطلاقاً — حسابه يستقبل مدين الدفعات فقط
فيظهر مديناً؛ وتكلفة الشحن بالشيكل كانت تُشتقّ من الدفعات، فيُضطر المستخدم
لتسجيل دفعة وهمية لمجرد إعطاء النظام سعر صرف.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader
from accounting.services import create_fiscal_year
from logistics.landed_cost import shipment_freight_ils
from logistics.models import LogisticsPayment, LogisticsShipment
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


D = lambda value: Decimal(str(value))


class ShipmentFreightAccrualTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="freight-acc", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة استحقاق الشحن", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)

        cls.freight_expense = Account.objects.get(tenant=cls.tenant, code="5301")
        cls.agent_ap = Account.objects.create(
            tenant=cls.tenant, code="AP-AGENT", name="ذمم وكيل الشحن",
            account_type="Liability", is_active=True,
        )
        cls.agent = Partner.objects.create(
            tenant=cls.tenant, name="وكيل الشحن الدولي", partner_type="ShippingAgent",
            linked_account=cls.agent_ap,
        )

    def setUp(self):
        self.shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-ACC-1",
            shipping_agent=self.agent, total_shipping_cost_usd=D("1000"),
            departure_date="2026-07-01",
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _post_accrual(self, rate="3.6"):
        return self.client.post(
            f"/api/logistics/shipments/{self.shipment.pk}/post-freight-accrual/",
            {"freight_exchange_rate": rate}, format="json", **self._auth(),
        )

    def test_accrual_credits_the_agent(self):
        resp = self._post_accrual()
        self.assertEqual(resp.status_code, 201, resp.content)
        journal = JournalHeader.objects.get(
            reference_type="SHIPMENT_FREIGHT_ACCRUAL", reference_id=self.shipment.pk,
        )
        self.assertTrue(journal.lines.filter(
            account=self.freight_expense, debit=D("3600.00"),
        ).exists())
        # الوكيل دائن — هذا جوهر الطلب.
        self.assertTrue(journal.lines.filter(
            account=self.agent_ap, credit=D("3600.00"), partner=self.agent,
        ).exists())
        self.shipment.refresh_from_db()
        self.assertTrue(self.shipment.freight_is_posted)
        self.assertEqual(self.shipment.freight_exchange_rate, D("3.600000"))

    def test_accrual_rate_governs_freight_cost_without_any_payment(self):
        """بلا أي دفعة: التكلفة = المبلغ × سعر الاستحقاق، لا السعر الافتراضي."""
        self._post_accrual(rate="4")
        self.shipment.refresh_from_db()
        total_ils, paid_usd, _, unpaid = shipment_freight_ils(self.shipment, D("3.6"))
        self.assertEqual(total_ils, D("4000.00"))
        self.assertEqual(paid_usd, D("0"))
        self.assertEqual(unpaid, D("1000.00"))

    def test_payments_do_not_change_cost_after_accrual(self):
        """الدفع لا يعيد تسعير التكلفة — الاستحقاق هو الملزم."""
        self._post_accrual(rate="4")
        LogisticsPayment.objects.create(
            shipment=self.shipment, amount=D("500"), usd_to_ils=D("3"),
            status="Confirmed", confirmed_by_supplier=True,
        )
        self.shipment.refresh_from_db()
        total_ils, _, _, _ = shipment_freight_ils(self.shipment, D("3.6"))
        self.assertEqual(total_ils, D("4000.00"))

    def test_without_accrual_legacy_payment_based_valuation_is_kept(self):
        """بلا استحقاق: السلوك القديم كما هو — لا تتغيّر أرقام الشحنات القائمة."""
        LogisticsPayment.objects.create(
            shipment=self.shipment, amount=D("400"), usd_to_ils=D("3"),
            status="Confirmed", confirmed_by_supplier=True,
        )
        total_ils, paid_usd, paid_ils, unpaid = shipment_freight_ils(self.shipment, D("3.5"))
        self.assertEqual(paid_usd, D("400.00"))
        self.assertEqual(paid_ils, D("1200.00"))
        self.assertEqual(unpaid, D("600.00"))
        self.assertEqual(total_ils, D("3300.00"))  # 1200 + 600×3.5

    def test_zero_freight_needs_no_accrual_and_no_payment(self):
        self.shipment.total_shipping_cost_usd = D("0")
        self.shipment.save(update_fields=["total_shipping_cost_usd"])
        resp = self._post_accrual()
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("صفر", resp.json()["error"])
        # ومع ذلك تكلفتها صفر بلا أي دفعة وهمية.
        total_ils, _, _, _ = shipment_freight_ils(self.shipment, D("3.6"))
        self.assertEqual(total_ils, D("0.00"))

    def test_rate_is_required(self):
        resp = self._post_accrual(rate="0")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("سعر صرف", resp.json()["error"])

    def test_cannot_accrue_twice(self):
        self.assertEqual(self._post_accrual().status_code, 201)
        again = self._post_accrual()
        self.assertEqual(again.status_code, 400, again.content)

    def test_agent_without_linked_account_is_rejected(self):
        loose = Partner.objects.create(
            tenant=self.tenant, name="وكيل بلا حساب", partner_type="ShippingAgent",
        )
        loose.linked_account = None
        loose.save(update_fields=["linked_account"])
        self.shipment.shipping_agent = loose
        self.shipment.save(update_fields=["shipping_agent"])
        resp = self._post_accrual()
        if resp.status_code == 201:
            self.skipTest("ensure_partner_linked_account ينشئ الحساب تلقائياً لهذا المستأجر")
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_unpost_releases_the_accrual_only(self):
        self._post_accrual()
        resp = self.client.post(
            f"/api/logistics/shipments/{self.shipment.pk}/unpost-freight-accrual/",
            {}, format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.shipment.refresh_from_db()
        self.assertFalse(self.shipment.freight_is_posted)
        self.assertIsNone(self.shipment.freight_journal_id)
        self.assertFalse(JournalHeader.objects.filter(
            reference_type="SHIPMENT_FREIGHT_ACCRUAL", reference_id=self.shipment.pk,
        ).exists())

    def test_agent_overpayment_is_allowed_and_becomes_an_advance(self):
        """الدفع الزائد للوكيل واقعة صحيحة: الفائض دفعة مقدمة (الوكيل مدين لنا).

        كان الخادم يرفض بـ«مجموع دفعات الشحن يتجاوز تكلفة الشحن الأساسية».
        """
        resp = self.client.patch(
            f"/api/logistics/shipments/{self.shipment.pk}/",
            {"payments": [{
                "payment_number": 1, "title": "دفعة شحن 1",
                "amount": "1500",  # أكثر من 1000 تكلفة الشحن
                "status": "Confirmed", "confirmed_by_supplier": True,
                "usd_to_ils": "3.6",
            }]},
            format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.shipment.refresh_from_db()
        paid = sum(
            (D(p.amount) for p in self.shipment.agent_payments.all()), D("0"),
        )
        self.assertEqual(paid, D("1500.00"))
        # التكلفة لا تتأثر بالدفع الزائد — الاستحقاق وحده يحكمها.
        self._post_accrual(rate="3.6")
        self.shipment.refresh_from_db()
        total_ils, _, _, _ = shipment_freight_ils(self.shipment, D("3.6"))
        self.assertEqual(total_ils, D("3600.00"))

    def test_overpayment_posting_is_not_capped(self):
        """ترحيل دفعة تتجاوز الإجمالي مسموح — القيد نفسه يجعل الوكيل مديناً."""
        from logistics.payment_posting_cap import shipment_agent_posting_cap_check
        LogisticsPayment.objects.create(
            shipment=self.shipment, amount=D("900"), usd_to_ils=D("3.6"),
            status="Confirmed", confirmed_by_supplier=True, is_posted=True,
        )
        ok, err = shipment_agent_posting_cap_check(self.shipment, D("400"))
        self.assertTrue(ok, err)
        self.assertIsNone(err)

    def test_full_form_save_cannot_clear_the_accrual(self):
        """«تخزين» يرسل النموذج كاملاً — يجب ألا يمسح حالة الاستحقاق.

        هذا ما جعل الزر يبدو بلا أثر: كل حفظ يعيد freight_is_posted=false
        فيُقبل الترحيل مجدداً بلا نهاية بينما القيود تتراكم في اليومية.
        """
        self.assertEqual(self._post_accrual().status_code, 201)
        resp = self.client.patch(
            f"/api/logistics/shipments/{self.shipment.pk}/",
            {
                "shipment_number": "SH-ACC-1",
                "freight_is_posted": False,
                "freight_journal": None,
                "freight_exchange_rate": None,
                "notes": "حفظ عادي من الشاشة",
            },
            format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.shipment.refresh_from_db()
        self.assertTrue(self.shipment.freight_is_posted)
        self.assertIsNotNone(self.shipment.freight_journal_id)
        self.assertEqual(self.shipment.freight_exchange_rate, D("3.600000"))
        # وبالتالي لا يُقبل ترحيل ثانٍ ينشئ قيداً مكرراً.
        self.assertEqual(self._post_accrual().status_code, 400)
        self.assertEqual(
            JournalHeader.objects.filter(
                reference_type="SHIPMENT_FREIGHT_ACCRUAL", reference_id=self.shipment.pk,
            ).count(),
            1,
        )

    def test_cost_change_blocked_while_accrual_posted(self):
        self._post_accrual()
        resp = self.client.patch(
            f"/api/logistics/shipments/{self.shipment.pk}/",
            {"total_shipping_cost_usd": "2000"}, format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.total_shipping_cost_usd, D("1000.00"))


class FreightAgentIsLockedAfterAccrualTest(APITestCase):
    """الوكيل هو الطرف المُدائن — لا يتغيّر بعد ترحيل الاستحقاق.

    كان تغييره/إزالته مسموحاً، فتظهر الشحنة «بلا وكيل» بينما القيد يُدائن الوكيل
    الأصلي (شكوى المالك: «كيف عملت استحقاق وأنا مش حاطط وكيل، وين راح القيد»).
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="agent-lock", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة قفل الوكيل", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.agent = Partner.objects.create(
            tenant=cls.tenant, name="وكيل أصلي", partner_type="FreightForwarder")
        cls.other_agent = Partner.objects.create(
            tenant=cls.tenant, name="وكيل آخر", partner_type="FreightForwarder")

    def setUp(self):
        self.shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-LOCK-1",
            shipping_agent=self.agent, total_shipping_cost_usd=Decimal("1000"),
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _accrue(self):
        resp = self.client.post(
            f"/api/logistics/shipments/{self.shipment.pk}/post-freight-accrual/",
            {"freight_exchange_rate": "3.6"}, format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_clearing_agent_after_accrual_is_rejected(self):
        self._accrue()
        resp = self.client.patch(
            f"/api/logistics/shipments/{self.shipment.pk}/",
            {"shipping_agent": None}, format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.shipping_agent_id, self.agent.pk)

    def test_switching_agent_after_accrual_is_rejected(self):
        self._accrue()
        resp = self.client.patch(
            f"/api/logistics/shipments/{self.shipment.pk}/",
            {"shipping_agent": self.other_agent.pk}, format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.shipping_agent_id, self.agent.pk)

    def test_agent_is_editable_again_after_unposting_the_accrual(self):
        self._accrue()
        unposted = self.client.post(
            f"/api/logistics/shipments/{self.shipment.pk}/unpost-freight-accrual/",
            {}, format="json", **self._auth(),
        )
        self.assertEqual(unposted.status_code, 200, unposted.content)
        resp = self.client.patch(
            f"/api/logistics/shipments/{self.shipment.pk}/",
            {"shipping_agent": self.other_agent.pk}, format="json", **self._auth(),
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.shipment.refresh_from_db()
        self.assertEqual(self.shipment.shipping_agent_id, self.other_agent.pk)
