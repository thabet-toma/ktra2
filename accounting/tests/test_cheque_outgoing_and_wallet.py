"""T-CHQ2 — إغلاق دورة الشيك الصادر + محفظة الشيكات.

قبل الإصلاح: `transfer_cheque` كان يشترط `direction == 'Incoming'` للقيد، وكان
«داخل الدفاتر» يعني فاتورة بيع أو سند قبض فقط. فالشيك الصادر داخل سند الصرف
يُدائن «شيكات برسم الدفع» عند الترحيل ثم **لا يُدين أبداً** — يبقى الالتزام
في الميزانية للأبد حتى بعد أن يصرفه المورد من حسابنا.

وقبل الإصلاح أيضاً: لا تجميعة واحدة تُظهر أين مال الشيكات الآن — «المحفظة».
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, Cheque, ChequeMovement, JournalHeader
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import SalesInvoice, SalesSettings, SupplierPayment
from tenants.models import Currency, Tenant
from tenants.services import create_company


class OutgoingChequeCycleTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chqout", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الشيكات الصادرة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد شيكات", partner_type="Supplier")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        # 2111 «شيكات برسم الدفع» صار جزءاً من الشجرة المعيارية (T-CHQ2).
        cls.payable_acc = Account.objects.get(tenant=cls.tenant, code="2111")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash},
        )

    def setUp(self):
        # CHQ-1: السند مُرحَّل — وهو شرط أي حركة على شيكه الآن. الشيك يبلغ
        # `Under_Collection` أصلاً بترحيل السند، فسندٌ غير مرحّل بشيك متحرك
        # حالةٌ لا وجود لها في الإنتاج، وكانت هذه التهيئة تصنعها.
        self.payment = SupplierPayment.objects.create(
            tenant=self.tenant, partner=self.supplier, currency=self.ils,
            payment_date="2026-06-11", amount=Decimal("400.00"),
            cash_or_bank_account=self.cash, is_posted=True,
        )

    def _cheque(self, status="Under_Collection"):
        return Cheque.objects.create(
            tenant=self.tenant, cheque_number=f"OUT-{Cheque.objects.count() + 1}",
            amount=Decimal("400.00"), currency=self.ils,
            partner=self.supplier, status=status, direction="Outgoing",
            supplier_payment=self.payment,
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_withdraw_clears_the_payable_against_cash(self):
        chq = self._cheque()
        res = self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "collect", "movement_date": "2026-06-11"},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        chq.refresh_from_db()
        assert chq.status == "Collected"

        movement = ChequeMovement.objects.get(
            cheque=chq, movement_type="collect")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_COLLECT",
            reference_id=movement.pk)
        lines = {l.account_id: (l.debit, l.credit) for l in jh.lines.all()}
        assert lines[self.payable_acc.pk] == (Decimal("400.00"), Decimal("0.00"))
        assert lines[self.cash.pk] == (Decimal("0.00"), Decimal("400.00"))
        assert ChequeMovement.objects.filter(cheque=chq, movement_type="collect").exists()

    def test_bounce_returns_the_debt_to_the_supplier(self):
        chq = self._cheque()
        res = self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "bounce", "movement_date": "2026-06-11"},
            format="json", **self._auth())
        assert res.status_code == 200, res.content

        movement = ChequeMovement.objects.get(
            cheque=chq, movement_type="bounce")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_BOUNCE",
            reference_id=movement.pk)
        self.supplier.refresh_from_db()
        lines = {l.account_id: (l.debit, l.credit) for l in jh.lines.all()}
        assert lines[self.payable_acc.pk] == (Decimal("400.00"), Decimal("0.00"))
        assert lines[self.supplier.linked_account_id] == (Decimal("0.00"), Decimal("400.00"))

    def test_settle_pays_the_bounced_cheque_in_cash(self):
        chq = self._cheque(status="Bounced")
        res = self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "settle", "movement_date": "2026-06-11"},
            format="json", **self._auth())
        assert res.status_code == 200, res.content

        movement = ChequeMovement.objects.get(
            cheque=chq, movement_type="settle")
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_SETTLE",
            reference_id=movement.pk)
        self.supplier.refresh_from_db()
        lines = {l.account_id: (l.debit, l.credit) for l in jh.lines.all()}
        assert lines[self.supplier.linked_account_id] == (Decimal("400.00"), Decimal("0.00"))
        assert lines[self.cash.pk] == (Decimal("0.00"), Decimal("400.00"))

    def test_standalone_outgoing_cheque_transfers_without_journal(self):
        chq = Cheque.objects.create(
            tenant=self.tenant, cheque_number="OUT-LEGACY",
            amount=Decimal("90.00"), currency=self.ils, partner=self.supplier,
            status="Under_Collection", direction="Outgoing",
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

    def test_movements_endpoint_lists_the_cheque_history(self):
        chq = self._cheque()
        self.client.post(
            f"/api/accounting/cheques/{chq.pk}/transfer/",
            {"movement_type": "collect", "notes": "صُرف من البنك"},
            format="json", **self._auth())
        res = self.client.get(
            f"/api/accounting/cheques/{chq.pk}/movements/", **self._auth())
        assert res.status_code == 200, res.content
        rows = res.json()
        assert [r["movement_type"] for r in rows] == ["collect"]
        assert rows[0]["notes"] == "صُرف من البنك"
        assert rows[0]["movement_type_display"] == "تحصيل"


class ChequeWalletTest(APITestCase):
    """محفظة الشيكات: أين مال الشيكات الآن، وما الذي يستحق قريباً."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="wallet", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة المحفظة", cls.user)
        cls.other = create_company("شركة أخرى", cls.user)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل", partner_type="Customer")

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _cheque(self, *, amount, status, direction="Incoming", due_date=None, tenant=None):
        return Cheque.objects.create(
            tenant=tenant or self.tenant,
            cheque_number=f"W-{Cheque.objects.count() + 1}",
            amount=Decimal(amount), currency=self.ils, status=status,
            direction=direction, due_date=due_date,
        )

    def test_wallet_groups_open_cheques_by_direction_and_status(self):
        self._cheque(amount="100.00", status="Under_Collection")
        self._cheque(amount="250.00", status="Under_Collection")
        self._cheque(amount="70.00", status="Draft", direction="Outgoing")
        # المحصّلة خرجت من المحفظة — لم تعد ورقة في اليد
        self._cheque(amount="999.00", status="Collected")

        res = self.client.get("/api/accounting/cheques/wallet/", **self._auth())
        assert res.status_code == 200, res.content
        data = res.json()
        incoming = {b["status"]: b for b in data["incoming"]["buckets"]}
        assert incoming["Under_Collection"]["count"] == 2
        assert Decimal(incoming["Under_Collection"]["amount"]) == Decimal("350.00")
        assert Decimal(data["incoming"]["open_total"]) == Decimal("350.00")
        assert Decimal(data["outgoing"]["open_total"]) == Decimal("70.00")
        assert Decimal(data["net_open"]) == Decimal("280.00")

    def test_wallet_splits_due_dates_into_overdue_and_upcoming(self):
        import datetime as dt
        today = dt.date.today()
        self._cheque(amount="10.00", status="Under_Collection",
                     due_date=today - dt.timedelta(days=3))
        self._cheque(amount="20.00", status="Under_Collection",
                     due_date=today + dt.timedelta(days=3))
        self._cheque(amount="40.00", status="Under_Collection",
                     due_date=today + dt.timedelta(days=20))
        self._cheque(amount="80.00", status="Under_Collection",
                     due_date=today + dt.timedelta(days=200))
        self._cheque(amount="5.00", status="Under_Collection", due_date=None)

        data = self.client.get("/api/accounting/cheques/wallet/", **self._auth()).json()
        due = {b["key"]: b for b in data["incoming"]["due_buckets"]}
        assert Decimal(due["overdue"]["amount"]) == Decimal("10.00")
        assert Decimal(due["due_7"]["amount"]) == Decimal("20.00")
        assert Decimal(due["due_30"]["amount"]) == Decimal("40.00")
        assert Decimal(due["later"]["amount"]) == Decimal("80.00")
        assert Decimal(due["no_due_date"]["amount"]) == Decimal("5.00")

    def test_wallet_never_leaks_another_company(self):
        self._cheque(amount="100.00", status="Under_Collection")
        self._cheque(amount="5000.00", status="Under_Collection", tenant=self.other)
        data = self.client.get("/api/accounting/cheques/wallet/", **self._auth()).json()
        assert Decimal(data["incoming"]["open_total"]) == Decimal("100.00")
