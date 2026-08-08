"""T-CHQ3 — الشيك يدخل الدفاتر ضمن سنده لا وحده.

عطلان متتاليان كشفهما المالك:
  1. `ChequeSerializer` بـ`fields='__all__'` يجعل `tenant`/`created_by` (مفتاحان
     أجنبيان بلا `blank=True`) **مطلوبَين**، والواجهة لا ترسلهما ⇒ كل إنشاء شيك
     يرتدّ بـ400 قبل أن يصل `perform_create` الذي يحقن الشركة أصلاً.
  2. وحتى بعد نجاح الحفظ بقي الشيك **خارج الدفاتر**: لا قيد له، وضغط «تحويل»
     لا يرحّل شيئاً لأن `transfer_cheque` يتخطّى الشيك غير المربوط بمستند.

القرار (كما في الأنظمة المهنية): الشيك ليس مستنداً مستقلاً — يُسجَّل داخل سند
قبض/صرف، بلا توزيع = دفعة على الحساب، وبتوزيع = تسوية فاتورة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Bank, Cheque, JournalHeader
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import CustomerPayment, SalesSettings
from tenants.models import Currency
from tenants.services import create_company


class ChequeCreateApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chqcreate", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة إنشاء الشيكات", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون الشيك", partner_type="Customer")
        cls.bank = Bank.objects.create(tenant=cls.tenant, name="بنك فلسطين")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        cls.uc_acc = Account.objects.get(tenant=cls.tenant, code="1107")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant,
            defaults={
                "default_cheques_under_collection_account": cls.uc_acc,
                "default_cash_account": cls.cash,
            },
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _payload(self, **over):
        body = {
            "cheque_number": "1233",
            "bank": self.bank.pk,
            "account_number": "565656",
            "amount": "4444",
            "issue_date": "2026-08-07",
            "due_date": "2026-08-07",
            "payee_name": "صاحب الشيك",
            "direction": "Incoming",
            "status": "Draft",
            "partner": self.customer.pk,
            "currency": self.ils.pk,
            "notes": "",
        }
        body.update(over)
        return body

    def _voucher(self, **over):
        """سند قبض بشيك — المسار الوحيد لإدخال شيك (بلا توزيع = على الحساب)."""
        body = {
            "partner": self.customer.pk,
            "payment_date": "2026-08-07",
            "amount": "4444",
            "currency": self.ils.pk,
            "cash_or_bank_account": self.cash.pk,
            "cheques": [{
                "cheque_number": "1233",
                "amount": "4444",
                "bank_name": "بنك فلسطين",
                "due_date": "2026-09-07",
                "payee_name": "صاحب الشيك",
            }],
        }
        body.update(over)
        res = self.client.post(
            "/api/sales/payments/", body, format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        return CustomerPayment.objects.get(pk=res.json()["id"])

    # ── العطل الأول: الحفظ كان مستحيلاً ──────────────────────────────────
    def test_tenant_and_user_are_not_required_from_the_client(self):
        """الشركة من الترويسة والمستخدم من التوكن — لا يُطلبان في الجسم."""
        payment = self._voucher()
        res = self.client.post(
            "/api/accounting/cheques/",
            self._payload(customer_payment=payment.pk, cheque_number="EXTRA-1"),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 201, res.content)
        chq = Cheque.objects.get(pk=res.json()["id"])
        self.assertEqual(chq.tenant_id, self.tenant.TenantID)
        self.assertEqual(chq.created_by_id, self.user.pk)

    def test_missing_drawn_on_bank_is_rejected(self):
        """البنك المسحوب عليه أهمّ ما في الورقة — لا يُقبل شيك بلا بنك."""
        payment = self._voucher()
        res = self.client.post(
            "/api/accounting/cheques/",
            self._payload(customer_payment=payment.pk, bank=None, bank_name=""),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("bank", res.json())

    # ── العطل الثاني: الشيك السائب خارج الدفاتر ──────────────────────────
    def test_standalone_cheque_is_refused_with_the_voucher_route(self):
        res = self.client.post(
            "/api/accounting/cheques/", self._payload(),
            format="json", **self._auth())
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("سند قبض", str(res.json()))
        self.assertFalse(Cheque.objects.filter(cheque_number="1233").exists())

    def test_voucher_without_allocation_posts_on_account(self):
        """بلا توزيع: مدين «شيكات برسم التحصيل» ÷ دائن ذمم العميل."""
        payment = self._voucher()
        payment.refresh_from_db()
        self.assertTrue(payment.is_posted)
        chq = payment.cheques.get()
        self.assertEqual(chq.status, "Under_Collection")
        lines = list(payment.journal.lines.select_related("account"))
        debit = next(ln for ln in lines if ln.debit > 0)
        self.assertEqual(debit.account.code, "1107")
        self.assertEqual(debit.debit, Decimal("4444.00"))

    def test_cheque_inside_a_voucher_can_close_its_cycle(self):
        """كان «تحويل» لا يرحّل شيئاً للشيك السائب — الآن الشيك داخل الدفاتر."""
        payment = self._voucher()
        chq = payment.cheques.get()
        res = self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "collect", "movement_date": "2026-08-07"},
            format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="CHEQUE_COLLECT",
            reference_id=chq.pk).exists())

    def test_legacy_cheque_without_bank_stays_editable(self):
        """شيكات قديمة بلا بنك — شرط البنك لا يمنع تعديل حقولها الأخرى."""
        legacy = Cheque.objects.create(
            tenant=self.tenant, cheque_number="LEGACY-1",
            amount=Decimal("100.00"), currency=self.ils,
            partner=self.customer, status="Draft", direction="Incoming",
        )
        res = self.client.patch(
            f"/api/accounting/cheques/{legacy.pk}/",
            {"notes": "ملاحظة"}, format="json", **self._auth())
        self.assertEqual(res.status_code, 200, res.content)
