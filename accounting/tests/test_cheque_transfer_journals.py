"""task11 R2-A3 — تحويل الشيك يرحّل قيداً محاسبياً ويمنع PATCH الخام.

قبل الإصلاح: «تحويل» الواجهة كان PATCH خاماً على status — بلا فحص انتقال
وبلا قيد، فتبقى المبالغ في «شيكات برسم التحصيل» للأبد حتى بعد التحصيل
أو الارتداد.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque, ChequeMovement, JournalHeader
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import SalesInvoice, SalesSettings
from tenants.models import Currency, Tenant, UserCompanyMembership
from tenants.services import create_company


class ChequeTransferJournalTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chq", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الشيكات", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل شيكات", partner_type="Customer")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        # حساب شيكات برسم التحصيل صريح في الإعدادات
        cls.uc_acc = Account.objects.create(
            tenant=cls.tenant, code="1108", name="شيكات برسم التحصيل",
            account_type="Asset", is_active=True)
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant,
            defaults={
                "default_cheques_under_collection_account": cls.uc_acc,
                "default_cash_account": cls.cash,
            },
        )
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="CHQ-INV-1", customer=cls.customer,
            currency=cls.ils, invoice_date="2026-06-11",
            status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("500.00"),
        )

    def _cheque(self, status="Under_Collection"):
        return Cheque.objects.create(
            tenant=self.tenant, cheque_number=f"C-{Cheque.objects.count()+1}",
            amount=Decimal("500.00"), currency=self.ils,
            partner=self.customer, status=status, direction="Incoming",
            sales_invoice=self.invoice,
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_collect_posts_journal_cash_dr_uc_cr(self):
        chq = self._cheque()
        res = self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "collect", "movement_date": "2026-06-11"},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        chq.refresh_from_db()
        assert chq.status == "Collected"

        movement = ChequeMovement.objects.get(cheque=chq, movement_type="collect")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_COLLECT",
            reference_id=movement.pk)
        lines = {l.account_id: (l.debit, l.credit) for l in jh.lines.all()}
        assert lines[self.cash.pk] == (Decimal("500.00"), Decimal("0.00"))
        assert lines[self.uc_acc.pk] == (Decimal("0.00"), Decimal("500.00"))
        assert ChequeMovement.objects.filter(cheque=chq, movement_type="collect").exists()

    def test_bounce_posts_ar_restoration(self):
        chq = self._cheque()
        res = self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "bounce", "movement_date": "2026-06-11"},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        chq.refresh_from_db()
        assert chq.status == "Bounced"

        movement = ChequeMovement.objects.get(cheque=chq, movement_type="bounce")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_BOUNCE",
            reference_id=movement.pk)
        # دائن: شيكات برسم التحصيل · مدين: ذمم العميل (linked_account أنشأه signal)
        self.customer.refresh_from_db()
        lines = {l.account_id: (l.debit, l.credit) for l in jh.lines.all()}
        assert lines[self.uc_acc.pk] == (Decimal("0.00"), Decimal("500.00"))
        assert lines[self.customer.linked_account_id] == (Decimal("500.00"), Decimal("0.00"))

    def test_bounce_tags_only_the_receivable_line_with_the_customer(self):
        """T-CHQ2: كان الشريك يُوسَم على سطرَي القيد، فيتعادلان داخل كشف
        العميل ولا يعود دين الشيك المرتد يظهر عليه (نفس عطل task32)."""
        chq = self._cheque()
        self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "bounce"}, format="json", **self._auth())
        movement = ChequeMovement.objects.get(cheque=chq, movement_type="bounce")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_BOUNCE",
            reference_id=movement.pk)
        self.customer.refresh_from_db()
        partners = {l.account_id: l.partner_id for l in jh.lines.all()}
        assert partners[self.customer.linked_account_id] == self.customer.pk
        assert partners[self.uc_acc.pk] is None

    def test_invalid_transition_rejected(self):
        chq = self._cheque(status="Collected")
        res = self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "collect"}, format="json", **self._auth())
        assert res.status_code == 400

    def test_raw_status_patch_blocked(self):
        chq = self._cheque()
        res = self.client.patch(
            f"/api/accounting/cheques/{chq.pk}/",
            {"status": "Collected"}, format="json", **self._auth())
        assert res.status_code == 400
        chq.refresh_from_db()
        assert chq.status == "Under_Collection"
        # تعديل حقول أخرى بلا تغيير الحالة يبقى مسموحاً
        res = self.client.patch(
            f"/api/accounting/cheques/{chq.pk}/",
            {"notes": "ملاحظة"}, format="json", **self._auth())
        assert res.status_code == 200

    def test_standalone_cheque_transfers_without_journal(self):
        """شيك غير مربوط بفاتورة/سند (legacy) — تتغير حالته بلا قيد."""
        chq = Cheque.objects.create(
            tenant=self.tenant, cheque_number="C-STANDALONE",
            amount=Decimal("100.00"), currency=self.ils,
            partner=self.customer, status="Under_Collection", direction="Incoming",
        )
        res = self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "collect"}, format="json", **self._auth())
        assert res.status_code == 200, res.content
        chq.refresh_from_db()
        assert chq.status == "Collected"
        assert not JournalHeader.objects.filter(
            reference_type="CHEQUE_COLLECT",
            reference_id__in=ChequeMovement.objects.filter(cheque=chq)
                                                   .values_list("pk", flat=True),
        ).exists()
