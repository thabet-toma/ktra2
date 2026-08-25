"""CHQ-4 — «حُفظ السند كمسودة — تعذّر الترحيل» على سندٍ فيه شيك.

الشكوى: زرّ «حفظ وترحيل» في نافذة سند القبض/الصرف يعيد 201 ومعه
`auto_post_error`، فيبقى السند مسودة وشيكه `Draft` — ثم لا تُرحَّل المسودة من
شاشة الشيكات إطلاقاً (M1-03/04 يعالجان الشقّ الثاني).

هذا الملف يغلق المسار الأول بالبرهان بدل الافتراض: **شركةٌ لا تحمل 1109 ولا
1107 في شجرتها** (كل شركة بُذرت قبل CHQ-1) تُنشئ سند قبض بشيك بـ`auto_post`.
الترحيل يمرّ بـ`_resolve_cheque_in_hand_account` الذي يُنشئ الحساب من الشجرة
المعيارية بدل أن يردّ المستخدم — وإن انكسر ذلك المسار يوماً فهنا يُكشف، لا في
رسالة `auto_post_error` مبتلَعة عند المستخدم.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import CustomerPayment, SalesSettings, SupplierPayment
from tenants.models import Currency
from tenants.services import create_company


class ChequeVoucherAutoPostTest(APITestCase):
    """سند بشيك يُرحَّل من أول ضغطة — ولو نقصت الشركة حسابات الشيكات."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chq_autopost", password="x")
        cls.ils = Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة سند الشيك", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل السند", partner_type="Customer")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد السند", partner_type="Supplier")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash},
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _strip_cheque_accounts(self):
        """يحاكي شركةً بُذرت قبل CHQ-1: بلا 1109 وبلا 1107 وبلا إعداد يشير إليهما."""
        SalesSettings.objects.filter(tenant=self.tenant).update(
            default_cheques_in_hand_account=None,
            default_cheques_under_collection_account=None,
        )
        Account.objects.filter(
            tenant=self.tenant, code__in=["1107", "1109"]).delete()

    def _cheque_payload(self, number, amount):
        return {
            "cheque_number": number,
            "amount": amount,
            "bank_name": "بنك فلسطين",
            "account_number": "123456",
            "bank_branch": "رام الله",
            "payee_name": "شركة سند الشيك",
            "due_date": "2026-09-15",
            "issue_date": "2026-08-15",
        }

    def test_customer_payment_with_cheque_auto_posts_without_the_in_hand_account(self):
        """سند قبض بشيك على شركة بلا 1109 — يُرحَّل، والحساب يُنشأ في الطريق."""
        self._strip_cheque_accounts()
        resp = self.client.post("/api/sales/payments/", {
            "partner": self.customer.id,
            "payment_date": "2026-08-20",
            "amount": "750.00",
            "currency": self.ils.CurrencyID,
            "cash_or_bank_account": self.cash.id,
            "auto_post": True,
            "cheques": [self._cheque_payload("AP-1", "750.00")],
        }, format="json")

        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertIsNone(
            resp.data.get("auto_post_error"),
            f"الترحيل التلقائي فشل: {resp.data.get('auto_post_error')}",
        )
        payment = CustomerPayment.objects.get(pk=resp.data["id"])
        self.assertTrue(payment.is_posted)
        self.assertIsNotNone(payment.journal_id)

        cheque = Cheque.objects.get(customer_payment=payment)
        # ترحيل السند ينقل الورقة الواردة إلى «مستلَم في المحفظة»، وحركتها
        # مربوطة بقيد السند (لا `.update()` أخرس).
        self.assertEqual(cheque.status, "Received")
        movement = cheque.movements.get()
        self.assertEqual(movement.movement_type, "receive")
        self.assertEqual(movement.journal_id, payment.journal_id)

        in_hand = Account.objects.get(tenant=self.tenant, code="1109")
        line = payment.journal.lines.get(account=in_hand)
        self.assertEqual(Decimal(str(line.debit)), Decimal("750.00"))

    def test_supplier_payment_with_cheque_auto_posts_without_the_payable_account(self):
        """مرآة الصادر: سند صرف بشيك على شركة بلا 2111 — يُرحَّل بلا خطأ."""
        # لا إعداد لحساب «شيكات برسم الدفع» — `resolve_cheques_payable_account`
        # يحلّه بالكود ثم بالاسم ثم يُنشئه، فحذف الحساب وحده يحاكي الشجرة القديمة.
        Account.objects.filter(tenant=self.tenant, code="2111").delete()

        resp = self.client.post("/api/logistics/supplier-payments/", {
            "partner": self.supplier.id,
            "payment_date": "2026-08-20",
            "amount": "400.00",
            "currency": self.ils.CurrencyID,
            "cash_or_bank_account": self.cash.id,
            "auto_post": True,
            "cheques": [self._cheque_payload("AP-OUT-1", "400.00")],
        }, format="json")

        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertIsNone(
            resp.data.get("auto_post_error"),
            f"الترحيل التلقائي فشل: {resp.data.get('auto_post_error')}",
        )
        payment = SupplierPayment.objects.get(pk=resp.data["id"])
        self.assertTrue(payment.is_posted)

        cheque = Cheque.objects.get(supplier_payment=payment)
        self.assertEqual(cheque.status, "Under_Collection")
        self.assertEqual(cheque.movements.get().movement_type, "issue")

    def test_schema_gap_is_reported_as_a_pending_migration_not_raw_sql(self):
        """عمودٌ مفقود من قاعدة الإنتاج يصل المستخدم باسمه ودوائه، لا بنصّ MySQL.

        هذا هو المشتبه الأول في شكوى «تعذّر الترحيل» على الخادم الحي: الكود
        يحمل هجرة `0037_cheque_cycle_v2` (عمودا `EndorsedToPartnerID` و
        `JournalID`) ولم تُطبَّق. نحاكيه بحقن الاستثناء نفسه في مسار الترحيل.
        """
        from unittest.mock import patch

        from django.db import OperationalError

        boom = OperationalError(
            1054, "Unknown column 'JournalID' in 'field list'")
        with patch("sales.views.post_customer_payment", side_effect=boom):
            resp = self.client.post("/api/sales/payments/", {
                "partner": self.customer.id,
                "payment_date": "2026-08-20",
                "amount": "100.00",
                "currency": self.ils.CurrencyID,
                "cash_or_bank_account": self.cash.id,
                "auto_post": True,
                "cheques": [self._cheque_payload("AP-SCHEMA", "100.00")],
            }, format="json")

        # السند لا يضيع — يبقى مسودة والرسالة تسمّي السبب والدواء.
        self.assertEqual(resp.status_code, 201, resp.data)
        message = resp.data.get("auto_post_error") or ""
        self.assertIn("قاعدة البيانات متأخّرة عن الكود", message)
        self.assertIn("migrate", message)
        self.assertFalse(CustomerPayment.objects.get(pk=resp.data["id"]).is_posted)
