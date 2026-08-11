"""task13 M2 — شركة جديدة جاهزة تشغيلياً بلا أي حساب يدوي.

قبل الإصلاح كانت الشجرة المبذورة تنقصها حسابات تتوقعها مسارات الترحيل:
- دورة الشيك كانت تلتقط «دفعات مقدمة للموردين» (1106) عبر بحث هش بالبادئة.
- أب صناديق النقدية (1110) غائب ⇒ السقوط لأول أصل بالشجرة.
- حسابات وكلاء الشحن/المخلصين/النقل المحلي كانت تُنشأ تحت
  قروض/مستحقات/ضريبة المخرجات (2102/2103/2104).
"""
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.cashbox import get_cash_box_parent_account
from accounting.models import Account, Cheque, JournalHeader, JournalLine
from accounting.services import create_fiscal_year, transfer_cheque
from logistics.services import (
    GR_IR_ACCOUNT_CODE,
    GR_IR_ACCOUNT_NAME,
    _resolve_gr_ir_account,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import COA_DATA, create_company, ensure_operational_accounts


class OperationalAccountsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="ops", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة جاهزة", cls.user)
        create_fiscal_year(cls.tenant, 2026)

    def test_seed_contains_operational_accounts(self):
        codes = set(Account.objects.filter(tenant=self.tenant).values_list("code", flat=True))
        assert {"1107", "1110", "2106", "2107", "2108"} <= codes

    def test_gr_ir_account_does_not_collide_with_seeded_freight_payables(self):
        freight_payables = Account.objects.get(tenant=self.tenant, code="2106")
        gr_ir = _resolve_gr_ir_account(self.tenant)
        seeded_codes = {code for code, _name, _type, _parent in COA_DATA}

        assert gr_ir != freight_payables
        assert gr_ir.code == GR_IR_ACCOUNT_CODE
        assert gr_ir.name == GR_IR_ACCOUNT_NAME
        assert gr_ir.code not in seeded_codes

    def test_gr_ir_data_migration_moves_only_clearing_references(self):
        freight_payables = Account.objects.get(tenant=self.tenant, code="2106")
        gr_ir_journal = JournalHeader.objects.create(
            tenant=self.tenant, reference_type="PURCHASE_INVOICE", reference_id=91,
        )
        freight_journal = JournalHeader.objects.create(
            tenant=self.tenant, reference_type="LOGISTICS_PAYMENT", reference_id=92,
        )
        gr_ir_line = JournalLine.objects.create(
            tenant=self.tenant, journal=gr_ir_journal, account=freight_payables,
            debit=Decimal("125.00"), credit=Decimal("0"),
        )
        freight_line = JournalLine.objects.create(
            tenant=self.tenant, journal=freight_journal, account=freight_payables,
            debit=Decimal("0"), credit=Decimal("80.00"),
        )

        migration = importlib.import_module("logistics.migrations.0068_split_gr_ir_account")
        migration.split_gr_ir_account(django_apps, None)

        gr_ir_line.refresh_from_db()
        freight_line.refresh_from_db()
        assert gr_ir_line.account.code == GR_IR_ACCOUNT_CODE
        assert freight_line.account.code == "2106"

    def test_cashbox_parent_resolves_to_dedicated_node(self):
        parent = get_cash_box_parent_account(self.tenant)
        assert parent is not None and parent.code == "1110"

    def test_cheque_collect_uses_cheques_account_not_supplier_advances(self):
        """تحصيل شيك على شركة جديدة بلا أي إعداد يدوي — مدين صندوق/دائن 1107."""
        from sales.models import SalesInvoice
        customer = Partner.objects.create(
            tenant=self.tenant, name="عميل", partner_type="Customer")
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="OPS-INV-1", customer=customer,
            currency=self.ils, invoice_date="2026-06-12",
            status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("300.00"),
        )
        chq = Cheque.objects.create(
            tenant=self.tenant, cheque_number="C-1", amount=Decimal("300.00"),
            currency=self.ils, partner=customer, sales_invoice=invoice,
            status="Under_Collection", direction="Incoming",
        )
        cash = Account.objects.get(tenant=self.tenant, code="1101")
        transfer_cheque(chq.id, "collect", account_id=cash.id)
        lines = JournalLine.objects.filter(
            journal__reference_type="CHEQUE_COLLECT", journal__reference_id=chq.id)
        assert lines.exists(), "no journal posted for cheque collection"
        credit_codes = {l.account.code for l in lines if l.credit > 0}
        assert credit_codes == {"1107"}, f"credited {credit_codes} instead of 1107"

    def test_logistics_partner_accounts_under_dedicated_parents(self):
        cases = {
            "FreightForwarder": "2106",
            "CustomsBroker": "2107",
            "LocalTransporter": "2108",
        }
        for ptype, parent_code in cases.items():
            p = Partner.objects.create(
                tenant=self.tenant, name=f"شريك {ptype}", partner_type=ptype)
            p.refresh_from_db()
            assert p.linked_account is not None, ptype
            assert p.linked_account.parent.code == parent_code, (
                f"{ptype} under {p.linked_account.parent.code} expected {parent_code}")

    def test_ensure_operational_accounts_idempotent_and_heals(self):
        """شجرة قديمة بلا الحسابات الجديدة — الدالة تكملها مرة واحدة فقط."""
        Account.objects.filter(
            tenant=self.tenant, code__in=["1107", "1110", "2106", "2107", "2108"]
        ).delete()
        created = ensure_operational_accounts(self.tenant)
        assert sorted(created) == ["1107", "1110", "2106", "2107", "2108"]
        assert ensure_operational_accounts(self.tenant) == []
