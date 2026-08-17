"""T2 — تحصيل الفاتورة من داخلها: نقد + شيكات + رصيد العميل، بسند قبض واحد.

المعيار الملزِم (طلب المالك في THA-118): فاتورة بـ100 يُدفع منها 60 نقداً و40
شيكاً من نقطة واحدة تُنتج **سند قبض واحداً مرحّلاً**، ويصير رصيد ذمم العميل
صفراً، وكل قيد متوازن — **ولا سطر نقد ولا شيكات داخل قيد الفاتورة نفسها**
(البرهان أن السطح القديم مات لا أنه التُفَّ عليه).

`collect_invoice_payment` لا يبني قيداً واحداً بنفسه: يركّب الخدمات القائمة
(`post_sales_invoice` ← `post_customer_payment` ← `allocate_customer_payment`)
داخل معاملة واحدة، فإمّا تمّ كلّ شيء أو لم يتمّ شيء.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque, FiscalPeriod, JournalHeader, JournalLine
from inventory.models import Product
from partners.models import Partner
from sales.models import (
    CustomerPayment,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesSettings,
)
from sales.services import posted_allocations_total
from tenants.models import Currency, Tenant, UserCompanyMembership


class InvoiceCollectTest(APITestCase):
    """`POST /api/sales/invoices/{id}/collect/` — التحصيل من داخل الفاتورة."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="collector", password="x")
        cls.tenant = Tenant.objects.create(TenantID=174, CompanyName="تحصيل")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110", name="صندوق",
            account_type="Asset", is_active=True)
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1101", name="ذمم عملاء",
            account_type="Asset", is_active=True)
        cls.uc = Account.objects.create(
            tenant=cls.tenant, code="1106", name="شيكات برسم التحصيل",
            account_type="Asset", is_active=True)
        Account.objects.create(
            tenant=cls.tenant, code="4101", name="إيرادات",
            account_type="Revenue", is_active=True)
        Account.objects.create(
            tenant=cls.tenant, code="2101", name="ضريبة",
            account_type="Liability", is_active=True)
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant,
            defaults={
                "default_cheques_under_collection_account": cls.uc,
                "default_cash_account": cls.cash,
            },
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="زبون التحصيل", partner_type="Customer",
            linked_account=cls.ar)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="COLL-1", name_ar="خدمة", is_service=True)
        FiscalPeriod.objects.create(
            tenant=cls.tenant, name="2026", start_date="2026-01-01",
            end_date="2026-12-31", is_closed=False)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    # ── أدوات ────────────────────────────────────────────────────────────
    def _draft(self, number, total="100", invoice_type=SalesInvoice.INVOICE_CREDIT):
        inv = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, customer=self.partner,
            currency=self.currency, invoice_date="2026-07-01",
            invoice_type=invoice_type, stock_on_post=False,
            cash_or_bank_account=(
                self.cash if invoice_type == SalesInvoice.INVOICE_CASH else None
            ),
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=inv, product=self.product,
            quantity=1, unit_price=Decimal(total))
        return inv

    def _collect(self, invoice, payload):
        return self.client.post(
            f"/api/sales/invoices/{invoice.pk}/collect/", payload,
            format="json", **self.h,
        )

    def _invoice_journal_lines(self, invoice):
        return list(
            JournalLine.objects.filter(
                journal__reference_type="SALES_INVOICE",
                journal__reference_id=invoice.pk,
            )
        )

    def _ar_net(self):
        """صافي ذمم العميل عبر كل القيود (مدين − دائن)."""
        rows = JournalLine.objects.filter(account_id=self.ar.pk)
        return sum(
            (Decimal(str(r.debit)) - Decimal(str(r.credit)) for r in rows),
            Decimal("0"),
        )

    def _assert_every_journal_balanced(self):
        for jh in JournalHeader.objects.filter(tenant=self.tenant):
            lines = list(jh.lines.all())
            assert sum(l.debit for l in lines) == sum(l.credit for l in lines), \
                f"قيد غير متوازن #{jh.pk}"

    # ── معيار النجاح الملزِم ─────────────────────────────────────────────
    def test_collect_60_cash_40_cheque_settles_invoice(self):
        """60 نقداً + 40 شيكاً على فاتورة 100 ⇒ سند واحد، ذمم صفر، قيد نقيّ."""
        inv = self._draft("COLL-1")
        res = self._collect(inv, {
            "cash": "60",
            "cash_account_id": self.cash.pk,
            "cheques": [{"cheque_number": "CHQ-C-1", "amount": "40",
                         "due_date": "2026-09-01"}],
            "post_invoice": True,
        })
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        assert inv.status == SalesInvoice.STATUS_POSTED

        payments = list(CustomerPayment.objects.filter(partner=self.partner))
        assert len(payments) == 1, "سند قبض واحد لا أكثر"
        payment = payments[0]
        assert payment.is_posted
        assert payment.amount == Decimal("100.00")
        assert list(
            PaymentAllocation.objects.filter(payment=payment)
            .values_list("invoice_id", "amount")
        ) == [(inv.pk, Decimal("100.00"))]

        cheques = list(Cheque.objects.filter(customer_payment=payment))
        assert len(cheques) == 1
        assert cheques[0].amount == Decimal("40.00")
        assert cheques[0].status == "Under_Collection"

        assert inv.amount_paid == Decimal("100.00")
        assert inv.amount_paid == posted_allocations_total(inv.pk)

        # رصيد ذمم العميل صفر، وكل قيد متوازن
        assert self._ar_net() == Decimal("0.00")
        self._assert_every_journal_balanced()

        # قيد الفاتورة نفسه لا يُسوّي شيئاً — لا صندوق ولا شيكات برسم التحصيل
        lines = self._invoice_journal_lines(inv)
        assert lines, "الفاتورة يجب أن تُرحَّل بقيد"
        assert sum(
            l.debit for l in lines if l.account_id in (self.cash.pk, self.uc.pk)
        ) == Decimal("0"), "قيد الفاتورة لا يُسوّي نقداً ولا شيكات"
        assert sum(l.debit for l in lines if l.account_id == self.ar.pk) == \
            inv.grand_total

        # سطر الشيك في قيد السند لا في قيد الفاتورة
        pay_lines = JournalLine.objects.filter(
            journal__reference_type="CUSTOMER_PAYMENT",
            journal__reference_id=payment.pk,
        )
        assert {
            (l.account_id, l.debit, l.credit) for l in pay_lines
        } == {
            (self.cash.pk, Decimal("60.00"), Decimal("0.00")),
            (self.uc.pk, Decimal("40.00"), Decimal("0.00")),
            (self.ar.pk, Decimal("0.00"), Decimal("100.00")),
        }

    def test_surplus_beyond_remaining_is_posted_on_account(self):
        """دفع 120 على فاتورة 100: التوزيع 100 والفائض 20 دفعةً على الحساب."""
        inv = self._draft("COLL-2")
        res = self._collect(inv, {
            "cash": "120", "cash_account_id": self.cash.pk, "post_invoice": True,
        })
        assert res.status_code == 200, res.content
        inv.refresh_from_db()

        payment = CustomerPayment.objects.get(partner=self.partner)
        assert payment.amount == Decimal("120.00")
        assert inv.amount_paid == Decimal("100.00"), "التوزيع مقصوص على المتبقي"
        assert inv.amount_paid == posted_allocations_total(inv.pk)

        # قيدان للسند: تسديد الفاتورة (100) + «على الحساب» (20)
        on_account = [
            jh for jh in JournalHeader.objects.filter(
                reference_type="CUSTOMER_PAYMENT", reference_id=payment.pk)
            if sum(l.debit for l in jh.lines.all()) == Decimal("20.00")
        ]
        assert len(on_account) == 1, "قيد «على الحساب» للفائض"
        assert {
            (l.account_id, l.debit, l.credit) for l in on_account[0].lines.all()
        } == {
            (self.cash.pk, Decimal("20.00"), Decimal("0.00")),
            (self.ar.pk, Decimal("0.00"), Decimal("20.00")),
        }
        # الفائض رصيد لصالح العميل — ذمم دائنة بـ20
        assert self._ar_net() == Decimal("-20.00")
        self._assert_every_journal_balanced()

    def test_explicit_spec_suppresses_auto_settlement_on_cash_invoice(self):
        """فاتورة نقدية + تحصيل صريح ⇒ سند واحد لا سندان (التسوية التلقائية مكبوتة)."""
        inv = self._draft("COLL-3", invoice_type=SalesInvoice.INVOICE_CASH)
        res = self._collect(inv, {
            "cash": "60",
            "cash_account_id": self.cash.pk,
            "cheques": [{"cheque_number": "CHQ-C-3", "amount": "40",
                         "due_date": "2026-09-01"}],
            "post_invoice": True,
        })
        assert res.status_code == 200, res.content
        inv.refresh_from_db()

        payments = list(CustomerPayment.objects.filter(partner=self.partner))
        assert len(payments) == 1, "التسوية التلقائية لا تُنتج سنداً ثانياً"
        assert payments[0].amount == Decimal("100.00")
        assert inv.amount_paid == Decimal("100.00")
        assert inv.amount_paid == posted_allocations_total(inv.pk)
        assert self._ar_net() == Decimal("0.00")

    def test_collect_from_customer_on_account_credit(self):
        """رصيد العميل المرحّل يُخصم من الفاتورة ربطاً بلا قيد جديد."""
        advance = CustomerPayment.objects.create(
            tenant=self.tenant, partner=self.partner, payment_date="2026-06-01",
            amount=Decimal("40.00"), currency=self.currency,
            cash_or_bank_account=self.cash, notes="دفعة مقدمة",
        )
        from sales.services import post_customer_payment
        post_customer_payment(advance, user=self.user)
        journals_before = JournalHeader.objects.filter(tenant=self.tenant).count()

        inv = self._draft("COLL-4")
        res = self._collect(inv, {
            "cash": "60",
            "cash_account_id": self.cash.pk,
            "from_on_account": [{"payment_id": advance.pk, "amount": "40"}],
            "post_invoice": True,
        })
        assert res.status_code == 200, res.content
        inv.refresh_from_db()

        assert inv.amount_paid == Decimal("100.00")
        assert inv.amount_paid == posted_allocations_total(inv.pk)
        # قيد الفاتورة + قيد سند الـ60 فقط — التوزيع من الرصيد ربطٌ بلا قيد
        assert JournalHeader.objects.filter(tenant=self.tenant).count() == \
            journals_before + 2
        assert self._ar_net() == Decimal("0.00")
        self._assert_every_journal_balanced()

    def test_cash_invoice_rejects_explicit_under_collection(self):
        """فاتورة نقدية بنقدٍ صريح لا يغطّي الإجمالي ⇒ رفض وتراجع كامل."""
        inv = self._draft("COLL-5", invoice_type=SalesInvoice.INVOICE_CASH)
        res = self._collect(inv, {
            "cash": "60", "cash_account_id": self.cash.pk, "post_invoice": True,
        })
        assert res.status_code == 400, res.content
        assert "نقدية" in res.json()["error"]
        inv.refresh_from_db()
        assert inv.status == SalesInvoice.STATUS_DRAFT, "لا شيء يُحفظ عند الرفض"
        assert not CustomerPayment.objects.filter(partner=self.partner).exists()
        assert not JournalHeader.objects.filter(
            reference_type="SALES_INVOICE", reference_id=inv.pk).exists()

    def test_cheque_without_a_due_date_is_refused(self):
        """شيك بلا موعد ورقة لا تُدار — نفس قاعدة شاشة السند المستقلة."""
        inv = self._draft("COLL-7")
        res = self._collect(inv, {
            "cheques": [{"cheque_number": "CHQ-C-7", "amount": "100"}],
            "post_invoice": True,
        })
        assert res.status_code == 400, res.content
        assert "استحقاق" in res.json()["error"]
        inv.refresh_from_db()
        assert inv.status == SalesInvoice.STATUS_DRAFT

    def test_attach_endpoint_no_longer_swallows_cash(self):
        """الإرفاق بلا ترحيل يرفض النقد بدل تسجيله في عمود لا يُرحَّل."""
        from sales.services import attach_payment_voucher
        inv = self._draft("COLL-8")
        res = self.client.post(
            f"/api/sales/invoices/{inv.pk}/payment-voucher/",
            {"cash_amount": "60", "cash_account_id": self.cash.pk},
            format="json", **self.h,
        )
        assert res.status_code == 400, res.content
        inv.refresh_from_db()
        assert inv.attached_cash_amount == Decimal("0.00")
        assert inv.attached_cash_account_id is None
        # وحتى نداء الخدمة مباشرةً — المنع في القاعدة لا في الواجهة
        from django.core.exceptions import ValidationError
        try:
            attach_payment_voucher(inv, cash_amount=60, cash_account_id=self.cash.pk)
        except ValidationError:
            pass
        else:
            raise AssertionError("النقد على المسودة يجب أن يُرفض")

    def test_collect_on_a_posted_invoice(self):
        """الفاتورة المرحّلة تُحصَّل لاحقاً من نفس النقطة بلا إعادة ترحيل."""
        from sales.services import post_sales_invoice
        inv = self._draft("COLL-6")
        post_sales_invoice(inv, user=self.user)

        res = self._collect(inv, {"cash": "100", "cash_account_id": self.cash.pk})
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        assert inv.amount_paid == Decimal("100.00")
        assert inv.amount_paid == posted_allocations_total(inv.pk)
        payment = CustomerPayment.objects.get(partner=self.partner)
        # سند المستخدم على فاتورة مرحّلة سلفاً ليس مملوكاً للفاتورة — لا يُحذف
        # مع إلغاء ترحيلها بل يحرسه `guard_invoice_payments_before_unpost`.
        assert payment.auto_settled_invoice_id is None
        assert self._ar_net() == Decimal("0.00")


class InvoiceCollectFailureTest(APITestCase):
    """الفشل لا يترك نصف حالة: شركة بلا صندوق قابل للحلّ ⇒ لا شيء يحدث."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="collector-fail", password="x")
        cls.tenant = Tenant.objects.create(TenantID=175, CompanyName="بلا صندوق")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True)
        # لا حساب بكود 1101/1102/1110 ولا اسم فيه «صندوق/نقد/بنك» ⇒
        # `resolve_default_cash_account` تُعيد None.
        cls.ar = Account.objects.create(
            tenant=cls.tenant, code="1201", name="ذمم عملاء",
            account_type="Asset", is_active=True)
        cls.uc = Account.objects.create(
            tenant=cls.tenant, code="1206", name="شيكات برسم التحصيل",
            account_type="Asset", is_active=True)
        Account.objects.create(
            tenant=cls.tenant, code="4101", name="إيرادات",
            account_type="Revenue", is_active=True)
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant,
            defaults={"default_cheques_under_collection_account": cls.uc},
        )
        # اسم الزبون ينتقل إلى اسم حسابه (`ensure_partner_account`)، وتسمية فيها
        # «صندوق/نقد/بنك» تجعل حسابَ ذممه يُلتقط كصندوق افتراضي بالاسم.
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="زبون الشركة الفقيرة", partner_type="Customer",
            linked_account=cls.ar)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="COLLF-1", name_ar="خدمة", is_service=True)
        FiscalPeriod.objects.create(
            tenant=cls.tenant, name="2026", start_date="2026-01-01",
            end_date="2026-12-31", is_closed=False)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_missing_cash_account_rolls_everything_back(self):
        """شيك بلا صندوق لتحرير السند: الفاتورة تبقى مسودة والرسالة تُسمّي الإعداد."""
        inv = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="COLLF-1", customer=self.partner,
            currency=self.currency, invoice_date="2026-07-01",
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=inv, product=self.product,
            quantity=1, unit_price=Decimal("100"))

        res = self.client.post(
            f"/api/sales/invoices/{inv.pk}/collect/",
            {"cheques": [{"cheque_number": "CHQ-F-1", "amount": "40",
                          "due_date": "2026-09-01"}],
             "post_invoice": True},
            format="json", **self.h,
        )
        assert res.status_code == 400, res.content
        assert "default_cash_account" in res.json()["error"]

        inv.refresh_from_db()
        assert inv.status == SalesInvoice.STATUS_DRAFT
        assert inv.amount_paid == Decimal("0.00")
        assert not CustomerPayment.objects.filter(tenant=self.tenant).exists()
        assert not Cheque.objects.filter(tenant=self.tenant).exists()
        assert not JournalHeader.objects.filter(tenant=self.tenant).exists()
