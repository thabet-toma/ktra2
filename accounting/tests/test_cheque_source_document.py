"""CHQ-4 — المستند المصدر للشيك: الخروج من الطريق المسدود.

قبل الإصلاح: شيك داخل سند **غير مرحّل** يُعرض له ثلاث حركات من
`INCOMING_TRANSITIONS['Draft']` — وكلّها يرفضها `transfer_cheque` بالحارس
«لا يمكن تحريك الشيك قبل ترحيل السند». والشاشة بلا عمود سند ولا رابط ولا زر،
فالمستخدم يقف أمام قائمة كاذبة بلا مخرج.

بعده: `allowed_movements` تصمت (فارغة)، و`needs_document_post` تشرح الصمت،
و`source_document` يقول أيّ سند يُرحَّل وأين هو. الورقة اليتيمة (legacy، بلا
مستند) لا تُمسّ إطلاقاً — مسارها القديم حرفياً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import CustomerPayment, SalesSettings, SupplierPayment
from sales.services import post_customer_payment
from tenants.models import Currency
from tenants.services import create_company


class ChequeSourceDocumentTest(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chq_src", password="x")
        cls.ils = Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة المستند المصدر", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل المصدر", partner_type="Customer")
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد المصدر", partner_type="Supplier")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash},
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _draft_payment_with_cheque(self):
        payment = CustomerPayment.objects.create(
            tenant=self.tenant, partner=self.customer, currency=self.ils,
            payment_date="2026-08-20", amount=Decimal("300.00"),
            cash_or_bank_account=self.cash,
        )
        cheque = Cheque.objects.create(
            tenant=self.tenant, cheque_number="SRC-1", amount=Decimal("300.00"),
            currency=self.ils, partner=self.customer, status="Draft",
            direction="Incoming", customer_payment=payment,
            bank_name="بنك القدس", due_date="2026-09-30",
        )
        return payment, cheque

    def _row_for(self, cheque_id):
        resp = self.client.get("/api/accounting/cheques/")
        self.assertEqual(resp.status_code, 200, resp.data)
        rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        return next(r for r in rows if r["id"] == cheque_id)

    def test_unposted_voucher_yields_no_movements_and_names_its_document(self):
        payment, cheque = self._draft_payment_with_cheque()
        row = self._row_for(cheque.id)

        self.assertEqual(row["allowed_movements"], [])
        self.assertTrue(row["needs_document_post"])
        self.assertEqual(row["source_document"]["type"], "customer_payment")
        self.assertEqual(row["source_document"]["id"], payment.id)
        self.assertFalse(row["source_document"]["is_posted"])

    def test_the_silenced_movements_were_the_ones_the_server_refuses(self):
        """الصمت ليس إخفاءً: كل حركة كانت تُعرض كان الخادم يردّها بـ400."""
        _payment, cheque = self._draft_payment_with_cheque()
        resp = self.client.post(
            f"/api/accounting/cheques/{cheque.id}/transfer/",
            {"movement_type": "deposit"}, format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("رحّل المستند أولاً", str(resp.data))

    def test_posting_the_voucher_restores_the_movements(self):
        payment, cheque = self._draft_payment_with_cheque()
        post_customer_payment(payment, user=self.user)

        row = self._row_for(cheque.id)
        self.assertFalse(row["needs_document_post"])
        self.assertTrue(row["source_document"]["is_posted"])
        # الورقة صارت «مستلَمة» بترحيل السند، فحركاتها حركات المحفظة.
        self.assertEqual(
            {m["value"] for m in row["allowed_movements"]},
            {"deposit", "collect", "endorse", "return_to_customer"},
        )

    def test_outgoing_cheque_points_at_its_supplier_payment(self):
        payment = SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.supplier, currency=self.ils,
            payment_date="2026-08-20", amount=Decimal("200.00"),
            cash_or_bank_account=self.cash,
        )
        cheque = Cheque.objects.create(
            tenant=self.tenant, cheque_number="SRC-OUT", amount=Decimal("200.00"),
            currency=self.ils, partner=self.supplier, status="Draft",
            direction="Outgoing", supplier_payment=payment,
            bank_name="بنك القدس", due_date="2026-09-30",
        )
        row = self._row_for(cheque.id)
        self.assertTrue(row["needs_document_post"])
        self.assertEqual(row["source_document"]["type"], "supplier_payment")
        self.assertEqual(row["source_document"]["id"], payment.id)

    def test_orphan_legacy_cheque_keeps_its_old_path(self):
        """ورقة بلا مستند: لا تنتظر ترحيلاً، وحركاتها كما كانت حرفياً."""
        cheque = Cheque.objects.create(
            tenant=self.tenant, cheque_number="SRC-ORPHAN",
            amount=Decimal("50.00"), currency=self.ils, partner=self.customer,
            status="Received", direction="Incoming",
            bank_name="بنك القدس", due_date="2026-09-30",
        )
        row = self._row_for(cheque.id)
        self.assertFalse(row["needs_document_post"])
        self.assertIsNone(row["source_document"])
        self.assertTrue(row["allowed_movements"])

    def test_listing_cheques_does_not_query_per_row(self):
        """عدد الاستعلامات لا يتبع عدد الشيكات.

        `source_document` يقرأ أربعة مستندات لكل صفّ، و`requires_bank_account`
        يسأل عن بنوك الشركة — وكلاهما كان سيصير استعلاماً لكل ورقة. المعيار
        هنا **الثبات** لا رقمٌ بعينه: نقيسه على ستّ أوراق ثم على اثنتي عشرة.
        """
        def _add(prefix, count):
            for i in range(count):
                payment = CustomerPayment.objects.create(
                    tenant=self.tenant, partner=self.customer, currency=self.ils,
                    payment_date="2026-08-20", amount=Decimal("10.00"),
                    cash_or_bank_account=self.cash,
                )
                Cheque.objects.create(
                    tenant=self.tenant, cheque_number=f"{prefix}-{i}",
                    amount=Decimal("10.00"), currency=self.ils,
                    partner=self.customer, status="Draft", direction="Incoming",
                    customer_payment=payment, bank_name="بنك القدس",
                    due_date="2026-09-30",
                )

        def _count_queries():
            with CaptureQueriesContext(connection) as ctx:
                resp = self.client.get("/api/accounting/cheques/?page=1&page_size=50")
                self.assertEqual(resp.status_code, 200)
            return len(ctx)

        _add("N1", 6)
        with_six = _count_queries()
        _add("N2", 6)
        with_twelve = _count_queries()

        self.assertEqual(
            with_six, with_twelve,
            f"عدد الاستعلامات تبع عدد الصفوف: {with_six} ← {with_twelve}",
        )
