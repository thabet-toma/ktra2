"""إشعار مدين/دائن على أيّ طرف — عميلٍ أو دائنٍ (مورد، مخلّص، وكيل شحن، ناقل).

الدلالة واحدة من منظور ذمّة الطرف: المدين Dr ذمّته (يزيد ما عليه أو ينقص ما له)،
والدائن Cr ذمّته. كان الإشعار للعميل وحده والمقابل إيراداته إجبارياً؛ الآن المقابل
يختاره المستخدم (افتراضيٌّ حسب نوع الطرف أو المستند المربوط)، والمربوط بتخليصٍ أو
إرساليةٍ أو استحقاق شحنٍ أو فاتورة شراء يُطفئ متبقّيها، وإلغاء الترحيل يعيد كل شيء.
"""
import importlib
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import migrations
from rest_framework.test import APITestCase

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from core.reports.financial import _aging
from logistics.accruals import post_clearance_accrual
from logistics.domain.party_accruals import accrual_status, journal_reference_accrual_links
from logistics.models import (
    LogisticsAccrualAllocation,
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsShipment,
    PurchaseInvoice,
)
from logistics.services import annotate_purchase_invoice_payment_summary, purchase_invoice_payment_summary
from partners.models import Partner
from sales.models import CreditDebitNote, CreditDebitNoteAllocation, SalesInvoice
from sales.services.calc import _default_revenue_account
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

D = lambda v: Decimal(str(v))
URL = "/api/sales/credit-debit-notes/"


class CreditDebitNoteAnyPartyTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="cdn-owner", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة الإشعارات", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)
        cls.parties = {
            kind: Partner.objects.create(tenant=cls.tenant, name=f"طرف {kind}", partner_type=kind)
            for kind in ("Customer", "Supplier", "CustomsBroker", "FreightForwarder",
                         "LocalTransporter", "Carrier")
        }
        cls.broker = cls.parties["CustomsBroker"]

        cls.seller = User.objects.create_user(username="cdn-seller", password="x")
        UserCompanyMembership.objects.create(user=cls.seller, tenant=cls.tenant, role="sales")
        cls.accountant = User.objects.create_user(username="cdn-keeper", password="x")
        UserCompanyMembership.objects.create(user=cls.accountant, tenant=cls.tenant, role="accountant")

        cls.other_user = User.objects.create_user(username="cdn-other", password="x")
        cls.other = create_company("شركة أخرى", cls.other_user)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    # ── مساعدات ─────────────────────────────────────────────────────────────
    def _acc(self, code):
        return Account.objects.get(tenant=self.tenant, code=code)

    def _create(self, partner, note_type="debit", amount="100", **extra):
        res = self.client.post(URL, {
            "note_date": "2026-07-10", "note_type": note_type, "partner": partner.pk,
            "amount": amount, "reason": "تسوية", **extra,
        }, format="json", **self.h)
        return res

    def _note(self, partner, note_type="debit", amount="100", **extra):
        res = self._create(partner, note_type, amount, **extra)
        self.assertEqual(res.status_code, 201, res.content)
        return res.data

    def _post(self, note_id):
        return self.client.post(f"{URL}{note_id}/post/", {}, format="json", **self.h)

    def _posted(self, partner, note_type="debit", amount="100", **extra):
        note = self._note(partner, note_type, amount, **extra)
        res = self._post(note["id"])
        self.assertEqual(res.status_code, 200, res.content)
        return res.data

    def _balance(self, partner):
        res = self.client.get(f"/api/partners/{partner.pk}/balance/", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        return D(res.data["open_balance"])

    def _lines(self, note_id):
        journal = CreditDebitNote.objects.get(pk=note_id).journal
        return list(JournalLine.objects.filter(journal=journal).select_related("account"))

    def _posted_clearance(self, amount="600"):
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number=f"SH-CDN-{LogisticsShipment.objects.count()}",
            chargeable_unit="cbm")
        clearance = LogisticsClearance.objects.create(
            tenant=self.tenant, shipment=shipment, customs_broker=self.broker,
            clearance_date="2026-07-05", currency=self.ils)
        LogisticsClearanceLine.objects.create(
            clearance=clearance, seq=1, line_type="broker_commission",
            description="عمولة المخلص", debit=D(amount), credit=D("0"))
        post_clearance_accrual(LogisticsClearance.objects.get(pk=clearance.pk))
        return LogisticsClearance.objects.get(pk=clearance.pk)

    # ── اتجاه الرصيد لكل نوع طرف × نوع إشعار ───────────────────────────────
    def test_every_party_type_moves_its_balance_in_the_note_direction(self):
        # العميل: open_balance = مدين − دائن (ما عليه). الدائن: دائن − مدين (ما له).
        for kind, partner in self.parties.items():
            creditor = kind != "Customer"
            for note_type in ("debit", "credit"):
                with self.subTest(kind=kind, note_type=note_type):
                    before = self._balance(partner)
                    note = self._posted(partner, note_type, "100")
                    moved = self._balance(partner) - before
                    # مدين: يزيد ما على العميل / ينقص ما للدائن؛ والدائن عكسه.
                    expected = D("100") if (note_type == "debit") != creditor else D("-100")
                    self.assertEqual(moved, expected)
                    party_line = next(l for l in self._lines(note["id"]) if l.partner_id == partner.pk)
                    self.assertEqual(party_line.debit if note_type == "debit" else party_line.credit, D("100"))
                    self.assertEqual(party_line.account_id, Partner.objects.get(pk=partner.pk).linked_account_id)

    def test_the_default_counter_account_follows_the_party_type(self):
        expected = {
            "CustomsBroker": "5307", "FreightForwarder": "5301",
            "LocalTransporter": "5305", "Carrier": "5305",
        }
        for kind, code in expected.items():
            with self.subTest(kind=kind):
                note = self._posted(self.parties[kind])
                self.assertEqual(note["counter_account_code"], code)
        customer_note = self._posted(self.parties["Customer"])
        self.assertEqual(customer_note["counter_account"], _default_revenue_account(self.tenant.TenantID).id)
        supplier_note = self._posted(self.parties["Supplier"])
        self.assertEqual(self._acc(supplier_note["counter_account_code"]).account_type, "Expense")

    def test_haim_case_broker_becomes_our_debtor(self):
        # المخلّص بلا مستحقّ: إشعار مدين 250 ⇒ رصيده «له» يصير −250 (مدينٌ لنا).
        self._posted(self.broker, "debit", "250")
        self.assertEqual(self._balance(self.broker), D("-250"))
        lines = {l.account.code: l for l in self._lines(CreditDebitNote.objects.get(partner=self.broker).pk)}
        self.assertEqual(lines["5307"].credit, D("250"))

    def test_the_chosen_counter_account_is_used(self):
        chosen = self._acc("5301")
        note = self._posted(self.broker, "debit", "80", counter_account=chosen.pk)
        counter = next(l for l in self._lines(note["id"]) if l.partner_id is None)
        self.assertEqual((counter.account_id, counter.credit), (chosen.pk, D("80")))

    def test_control_parent_and_inventory_accounts_are_refused_as_counter(self):
        parent = Account.objects.filter(tenant=self.tenant, children__isnull=False).first()
        inventory = Account.objects.filter(tenant=self.tenant, sub_type="inventory", children__isnull=True).first()
        payable = Partner.objects.get(pk=self.parties["Supplier"].pk).linked_account \
            or self._acc("2101")
        for label, account in (("parent", parent), ("inventory", inventory), ("payable", payable),
                               ("receivable", self._acc("1103"))):
            with self.subTest(label=label):
                self.assertIsNotNone(account, label)
                res = self._create(self.broker, counter_account=account.pk)
                self.assertEqual(res.status_code, 400, res.content)

    def test_cash_bank_and_cheque_accounts_are_refused_as_counter(self):
        # DN-0001 على الإنتاج: Dr ذمّة المخلّص / Cr «صندوق شيكل» 1B0001 — سندُ صرفٍ بلا نقد.
        prod_box = Account.objects.create(tenant=self.tenant, code="1B0001", name="صندوق شيكل",
                                          account_type="Asset", is_active=True)
        bank = Account.objects.create(tenant=self.tenant, code="1102999", name="بنك المعاينة",
                                      account_type="Asset", is_active=True, sub_type="bank")
        cheques = Account.objects.filter(tenant=self.tenant, code__in=("1107", "1109", "2111")).first() \
            or Account.objects.create(tenant=self.tenant, code="1107", name="شيكات برسم التحصيل",
                                      account_type="Asset", is_active=True)
        for label, account in (("cash", prod_box), ("bank", bank), ("cheques", cheques)):
            with self.subTest(label=label):
                res = self._create(self.broker, counter_account=account.pk)
                self.assertEqual(res.status_code, 400, res.content)
                self.assertIn("الإشعار ليس دفعاً", str(res.content.decode()))

    def test_report_command_lists_posted_notes_with_a_cash_counter(self):
        from io import StringIO

        from django.core.management import call_command

        box = Account.objects.create(tenant=self.tenant, code="1B0001", name="صندوق شيكل",
                                     account_type="Asset", is_active=True)
        clean = self._posted(self.broker, "debit", "30")
        dirty = self._posted(self.broker, "debit", "2942.96")
        # ما رُحِّل قبل الحارس: يُحاكى بالكتابة المباشرة على الحقل.
        CreditDebitNote.objects.filter(pk=dirty["id"]).update(counter_account=box)
        before = list(JournalLine.objects.order_by("id").values_list("id", "debit", "credit"))
        out = StringIO()
        call_command("list_notes_with_cash_counter", tenant=self.tenant.TenantID, stdout=out)
        text = out.getvalue()
        self.assertIn(dirty["note_number"], text)
        self.assertNotIn(clean["note_number"], text)
        self.assertIn("1B0001", text)
        self.assertIn("المجموع: 1", text)
        # تقريرٌ فقط: لا قيد ولا إشعار تغيّر.
        self.assertEqual(list(JournalLine.objects.order_by("id").values_list("id", "debit", "credit")), before)
        self.assertEqual(CreditDebitNote.objects.get(pk=dirty["id"]).status, "posted")

    def test_vat_goes_to_output_for_customers_and_input_for_creditors(self):
        cust = self._posted(self.parties["Customer"], "debit", "117", tax_amount="17")
        codes = {l.account.code: (l.debit, l.credit) for l in self._lines(cust["id"])}
        self.assertEqual(codes["2104"], (D("0"), D("17")))
        cred = self._posted(self.broker, "credit", "117", tax_amount="17")
        codes = {l.account.code: (l.debit, l.credit) for l in self._lines(cred["id"])}
        self.assertEqual(codes["1105"], (D("17"), D("0")))
        self.assertEqual(codes["5307"], (D("100"), D("0")))

    def test_foreign_currency_fills_amount_currency(self):
        note = self._posted(self.broker, "debit", "100", currency=self.usd.pk, exchange_rate="3.5")
        party = next(l for l in self._lines(note["id"]) if l.partner_id == self.broker.pk)
        self.assertEqual(party.base_debit, D("350.00"))
        self.assertEqual(party.amount_currency, D("100"))
        self.assertEqual(self._balance(self.broker), D("-350"))

    # ── دورة الحياة ─────────────────────────────────────────────────────────
    def test_unpost_restores_the_balance_and_returns_a_draft(self):
        before = self._balance(self.broker)
        note = self._posted(self.broker, "debit", "90")
        self.assertEqual(self.client.patch(f"{URL}{note['id']}/", {"amount": "5"}, format="json",
                                           **self.h).status_code, 400)
        self.assertEqual(self.client.delete(f"{URL}{note['id']}/", **self.h).status_code, 400)
        res = self.client.post(f"{URL}{note['id']}/unpost/", {}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual((res.data["status"], res.data["journal"]), ("draft", None))
        self.assertEqual(self._balance(self.broker), before)
        # المسودة تُعدَّل ثم تُرحَّل من جديد، وتُلغى.
        self.assertEqual(self.client.patch(f"{URL}{note['id']}/", {"amount": "40"}, format="json",
                                           **self.h).status_code, 200)
        self.assertEqual(self._post(note["id"]).status_code, 200)
        self.assertEqual(self._balance(self.broker), before - D("40"))
        self.client.post(f"{URL}{note['id']}/unpost/", {}, format="json", **self.h)
        res = self.client.post(f"{URL}{note['id']}/cancel/", {}, format="json", **self.h)
        self.assertEqual(res.data["status"], "cancelled")
        self.assertEqual(self._post(note["id"]).status_code, 400)

    def test_numbering_keeps_one_book_per_type(self):
        d1, c1, d2 = (self._note(self.broker, t)["note_number"] for t in ("debit", "credit", "debit"))
        self.assertTrue(d1.startswith("DN-") and d2.startswith("DN-") and c1.startswith("CN-"))
        self.assertEqual(int(d2.split("-")[1]), int(d1.split("-")[1]) + 1)

    # ── الربط والتسوية ──────────────────────────────────────────────────────
    def test_debit_note_linked_to_a_clearance_settles_its_remaining(self):
        clearance = self._posted_clearance("600")
        self.assertEqual(accrual_status("clearance", clearance)["remaining"], D("600"))
        note = self._posted(self.broker, "debit", "200", related_clearance=clearance.pk)
        # الترحيل وزّعه على مستنده المربوط تلقائياً — كالسند.
        status = accrual_status("clearance", clearance)
        self.assertEqual((status["allocated"], status["remaining"]), (D("200"), D("400")))
        self.assertEqual((note["allocated_amount"], note["unallocated_amount"], note["settles"]),
                         ("200.00", "0.00", True))
        self.assertEqual(note["linked_document"]["kind"], "clearance")
        # كشف الحساب: الإشعار يرسو على ما وُزِّع عليه.
        links = journal_reference_accrual_links(self.tenant.TenantID, [("CREDIT_DEBIT_NOTE", note["id"])])
        self.assertEqual([t["key"] for t in links["notes"][note["id"]]], [f"LOGISTICS_CLEARANCE:{clearance.pk}"])
        # الافتراضي من حساب مصروف التخليص نفسه.
        self.assertEqual(self._acc(note["counter_account_code"]).account_type, "Expense")
        # إشعارٌ أكبر من المتبقّي يُرحَّل: يُطفئ المتبقّي والزائد يبقى تحت الحساب.
        big = self._posted(self.broker, "debit", "401", related_clearance=clearance.pk)
        self.assertEqual((big["allocated_amount"], big["unallocated_amount"]), ("400.00", "1.00"))
        self.assertEqual(accrual_status("clearance", clearance)["remaining"], D("0"))
        # إلغاء الترحيل يفكّ توزيعاته في المعاملة نفسها وينبّه.
        res = self.client.post(f"{URL}{note['id']}/unpost/", {}, format="json", **self.h)
        self.assertIn("فُكّ توزيع الإشعار", res.data["notice"])
        self.assertFalse(LogisticsAccrualAllocation.objects.filter(note_id=note["id"]).exists())
        self.assertEqual(accrual_status("clearance", clearance)["remaining"], D("200"))

    def test_credit_note_linked_to_a_clearance_raises_what_is_due(self):
        clearance = self._posted_clearance("600")
        note = self._posted(self.broker, "credit", "50", related_clearance=clearance.pk)
        status = accrual_status("clearance", clearance)
        self.assertEqual((status["due"], status["remaining"], status["allocated"]), (D("650"), D("650"), D("0")))
        # يزيد ما للطرف فلا يُوزَّع ولا يُحسب تحت الحساب.
        self.assertEqual((note["settles"], note["unallocated_amount"]), (False, "0.00"))
        res = self.client.post(f"{URL}{note['id']}/allocate/", {"fifo": True}, format="json", **self.h)
        self.assertEqual(res.status_code, 400, res.content)

    def test_link_must_be_the_partners_own_single_posted_document(self):
        clearance = self._posted_clearance()
        res = self._create(self.parties["LocalTransporter"], related_clearance=clearance.pk)
        self.assertEqual(res.status_code, 400, res.content)
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SH-UNPOSTED", chargeable_unit="cbm",
            shipping_agent=self.parties["FreightForwarder"])
        res = self._create(self.parties["FreightForwarder"], related_shipment=shipment.pk)
        self.assertEqual(res.status_code, 400, res.content)  # استحقاق الشحن غير مرحّل
        res = self._create(self.broker, related_clearance=clearance.pk, related_shipment=shipment.pk)
        self.assertEqual(res.status_code, 400, res.content)
        # مستندٌ من شركة أخرى غير موجودٍ أصلاً.
        foreign = LogisticsShipment.objects.create(
            tenant=self.other, shipment_number="SH-X", chargeable_unit="cbm")
        foreign_clearance = LogisticsClearance.objects.create(
            tenant=self.other, shipment=foreign, currency=self.ils)
        res = self._create(self.broker, related_clearance=foreign_clearance.pk)
        self.assertEqual(res.status_code, 400, res.content)

    def test_debit_note_linked_to_a_purchase_invoice_settles_it_in_both_twins(self):
        supplier = self.parties["Supplier"]
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, partner=supplier, invoice_number="PI-CDN", invoice_date="2026-07-01",
            currency=self.ils, exchange_rate=D("1"), grand_total=D("1000"),
            is_posted=True, status="posted")
        debit = self._posted(supplier, "debit", "300", related_purchase_invoice=invoice.pk)
        self._posted(supplier, "credit", "50", related_purchase_invoice=invoice.pk)
        self.assertEqual(list(CreditDebitNoteAllocation.objects.filter(note_id=debit["id"]).values_list(
            "purchase_invoice_id", "amount")), [(invoice.pk, D("300"))])
        summary = purchase_invoice_payment_summary(PurchaseInvoice.objects.get(pk=invoice.pk))
        listed = annotate_purchase_invoice_payment_summary(PurchaseInvoice.objects.filter(pk=invoice.pk)).get()
        self.assertEqual((summary["payable_total"], summary["remaining_balance"]), (D("1050"), D("750")))
        self.assertEqual((listed.list_payable_total, listed.list_remaining_balance), (D("1050"), D("750")))
        # عملةٌ غير عملة الفاتورة تُرفض.
        res = self._create(supplier, related_purchase_invoice=invoice.pk, currency=self.usd.pk,
                           exchange_rate="3.5")
        self.assertEqual(res.status_code, 400, res.content)

    def test_unlinked_notes_show_in_aging_as_signed_rows(self):
        self._posted(self.broker, "debit", "70")
        self._posted(self.parties["Customer"], "credit", "40")
        supplier_side = {r["partner_id"]: r for r in _aging(self.tenant.TenantID, {}, side="supplier")}
        customer_side = {r["partner_id"]: r for r in _aging(self.tenant.TenantID, {}, side="customer")}
        self.assertEqual(D(supplier_side[self.broker.pk]["total"]), D("-70"))
        self.assertEqual(D(customer_side[self.parties["Customer"].pk]["total"]), D("-40"))

    # ── الإشعار المسوّي رصيدٌ يُوزَّع كالسند ─────────────────────────────────
    def _profile(self, partner):
        res = self.client.get(f"/api/partners/{partner.pk}/profile/", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        return res.data

    def _aging_total(self, partner, side="supplier"):
        rows = {r["partner_id"]: r for r in _aging(self.tenant.TenantID, {}, side=side)}
        return D(rows[partner.pk]["total"]) if partner.pk in rows else D("0")

    def test_broker_debit_note_is_surplus_until_allocated_to_a_clearance(self):
        # حالة حاييم: إشعارٌ مدينٌ بلا ربط = رصيدٌ لنا عنده، ظاهرٌ تحت الحساب.
        clearance = self._posted_clearance("600")
        note = self._posted(self.broker, "debit", "250")
        self.assertEqual(note["unallocated_amount"], "250.00")
        # إشعارٌ لا دفعة: «فائض تحت الحساب» لا «دفعات تحت الحساب».
        self.assertEqual(D(self._profile(self.broker)["accrual_surplus"]), D("250"))
        self.assertEqual(D(self._profile(self.broker)["on_account_payments"]), D("0"))
        self.assertEqual(self._aging_total(self.broker), D("350"))  # 600 − 250

        url = f"{URL}{note['id']}/"
        targets = self.client.get(f"{url}allocation-targets/", **self.h).data
        self.assertEqual([(t["kind"], t["id"], t["remaining"]) for t in targets["targets"]],
                         [("clearance", clearance.pk, "600.00")])
        self.assertEqual(targets["fifo"], [{"kind": "clearance", "id": clearance.pk,
                                            "label": targets["targets"][0]["label"], "amount": "250.00"}])
        # أكثر من غير الموزَّع يُرفض.
        res = self.client.post(f"{url}allocate/", {"allocations": [
            {"kind": "clearance", "id": clearance.pk, "amount": "251"}]}, format="json", **self.h)
        self.assertEqual(res.status_code, 400, res.content)

        res = self.client.post(f"{url}allocate/", {"fifo": True}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["unallocated"], "0.00")
        self.assertEqual(accrual_status("clearance", clearance)["remaining"], D("350"))
        self.assertEqual(D(self._profile(self.broker)["accrual_surplus"]), D("0"))
        self.assertEqual(self._aging_total(self.broker), D("350"))
        # تبويب «الدفعات» في التخليص يعرضه بجانب السندات.
        rows = self.client.get(f"/api/logistics/clearances/{clearance.pk}/payments/", **self.h)
        self.assertEqual(rows.status_code, 200, rows.content)
        self.assertIn(note["note_number"], [r.get("note_number") for r in rows.data])

        # فكّ التوزيع يعيده تحت الحساب ويعيد المتبقّي.
        alloc = res.data["allocations"][0]
        self.assertEqual((alloc["allocation_kind"], alloc["kind"]), ("accrual", "clearance"))
        res = self.client.post(f"{url}deallocate/", {"allocation_kind": "accrual",
                                                     "allocation_id": alloc["allocation_id"]},
                               format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["unallocated"], "250.00")
        self.assertEqual(accrual_status("clearance", clearance)["remaining"], D("600"))

    def test_customer_credit_note_settles_its_sales_invoice_without_touching_the_cash_cap(self):
        from sales.services import (
            guard_invoice_payments_before_unpost, posted_allocations_total, posted_invoice_settled_total,
        )
        from django.core.exceptions import ValidationError

        customer = self.parties["Customer"]
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="SI-CDN", customer=customer, currency=self.ils,
            invoice_date="2026-07-01", status=SalesInvoice.STATUS_POSTED, grand_total=D("500"))
        SalesInvoice.objects.filter(pk=invoice.pk).update(grand_total=D("500"), amount_paid=D("0"))
        note = self._posted(customer, "credit", "200", related_invoice=invoice.pk, currency=self.ils.pk)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, D("200"))
        self.assertEqual((posted_invoice_settled_total(invoice.pk), posted_allocations_total(invoice.pk)),
                         (D("200"), D("0")))  # سقف الردّ النقدي للمرتجع نقدٌ وحده
        self.assertEqual(self._aging_total(customer, "customer"), D("300"))
        # فاتورةٌ أطفأها إشعارٌ لا يُلغى ترحيلها قبل فكّ توزيعه.
        with self.assertRaisesMessage(ValidationError, note["note_number"]):
            guard_invoice_payments_before_unpost(invoice)
        self.client.post(f"{URL}{note['id']}/unpost/", {}, format="json", **self.h)
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, D("0"))
        guard_invoice_payments_before_unpost(invoice)

    def test_backfill_turns_linked_debit_notes_into_allocations(self):
        from django.apps import apps

        clearance = self._posted_clearance("600")
        note = self._posted(self.broker, "debit", "120", related_clearance=clearance.pk)
        LogisticsAccrualAllocation.objects.filter(note_id=note["id"]).delete()
        self.assertEqual(accrual_status("clearance", clearance)["remaining"], D("600"))
        module = importlib.import_module("sales.migrations.0046_note_allocations")
        module.backfill_linked_debit_notes(apps, None)
        self.assertEqual(accrual_status("clearance", clearance)["remaining"], D("480"))

    # ── الاسترداد النقدي للفائض ────────────────────────────────────────────
    def _cash_box(self):
        return Account.objects.get_or_create(
            tenant=self.tenant, code="1B0009",
            defaults={"name": "صندوق الاسترداد", "account_type": "Asset", "is_active": True},
        )[0]

    def _refund(self, partner, kind, amount, sources):
        return self.client.post("/api/sales/payments/", {
            "partner": partner.pk, "payment_date": "2026-07-20", "amount": amount,
            "currency": self.ils.pk, "exchange_rate": "1", "cash_or_bank_account": self._cash_box().pk,
            "kind": kind, "auto_post": True, "refund_sources": sources,
        }, format="json", **self.h)

    def _surplus(self, partner):
        res = self.client.get(f"/api/partners/{partner.pk}/surplus/", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        return res.data["rows"]

    def test_cash_refund_from_broker_clears_the_note_surplus_and_the_balance(self):
        before = self._balance(self.broker)
        note = self._posted(self.broker, "debit", "250", currency=self.ils.pk)
        self.assertEqual(self._balance(self.broker), before - D("250"))
        rows = self._surplus(self.broker)
        self.assertEqual([(r["source"], r["id"], r["unallocated"]) for r in rows],
                         [("note", note["id"], "250.00")])
        # أكثر من الفائض يُرفض، وسند صرفٍ (ردّ) لدائنٍ اتجاهٌ خاطئ.
        res = self._refund(self.broker, "receipt", "300", [{"source": "note", "id": note["id"], "amount": "300"}])
        self.assertEqual(res.status_code, 400, res.content)
        res = self._refund(self.broker, "refund", "250", [{"source": "note", "id": note["id"], "amount": "250"}])
        self.assertEqual(res.status_code, 400, res.content)

        res = self._refund(self.broker, "receipt", "250", [{"source": "note", "id": note["id"], "amount": "250"}])
        self.assertEqual(res.status_code, 201, res.content)
        self.assertTrue(res.data["is_posted"], res.data)
        # Dr صندوق / Cr ذمّة المخلّص — الفائض والرصيد صفرٌ معاً.
        self.assertEqual(self._surplus(self.broker), [])
        self.assertEqual(self._balance(self.broker), before)
        self.assertEqual(D(self._profile(self.broker)["accrual_surplus"]), D("0"))
        self.assertEqual(self._aging_total(self.broker), D("0"))
        self.assertEqual(self.client.get(f"{URL}{note['id']}/", **self.h).data["unallocated_amount"], "0.00")
        # إلغاء ترحيل الإشعار يفكّ الاسترداد أيضاً ويسمّيه في التنبيه.
        res = self.client.post(f"{URL}{note['id']}/unpost/", {}, format="json", **self.h)
        self.assertIn("سند استرداد", res.data["notice"])
        self.assertIn("يبقى السند مرحَّلاً «تحت الحساب»", res.data["notice"])

    def test_customer_credit_note_surplus_is_returned_by_a_refund_voucher(self):
        customer = self.parties["Customer"]
        note = self._posted(customer, "credit", "80", currency=self.ils.pk)
        self.assertEqual([(r["source"], r["unallocated"]) for r in self._surplus(customer)], [("note", "80.00")])
        res = self._refund(customer, "receipt", "80", [{"source": "note", "id": note["id"], "amount": "80"}])
        self.assertEqual(res.status_code, 400, res.content)  # العميل يُردّ له بسند صرف
        res = self._refund(customer, "refund", "80", [{"source": "note", "id": note["id"], "amount": "80"}])
        self.assertEqual(res.status_code, 201, res.content)
        # سند الردّ نفسه أطفأ الفائض فلا يبقى «على الحساب».
        self.assertEqual(res.data["unallocated_amount"], "0.00")
        self.assertEqual(self._surplus(customer), [])
        self.assertEqual(self._aging_total(customer, "customer"), D("0"))

    # ── خانتا رأس الكشف بتعريف المالك: الدفعة سند، والفائض إشعار أو خفض مستحق ─────
    def _buckets(self, partner):
        profile = self._profile(partner)
        return D(profile["on_account_payments"]), D(profile["accrual_surplus"]), profile

    def _closing(self, partner):
        res = self.client.get(f"/api/partners/{partner.pk}/statement/", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        return D(res.data["closing_balance"])

    def _voucher(self, partner, amount):
        from sales.models import SupplierPayment
        from sales.services import post_supplier_payment

        voucher = SupplierPayment.objects.create(
            tenant=self.tenant, partner=partner, payment_date="2026-07-12", amount=D(amount),
            currency=self.ils, exchange_rate=D("1"), cash_or_bank_account=self._cash_box())
        post_supplier_payment(voucher, user=self.user)
        return voucher

    def test_voucher_is_on_account_and_note_is_surplus_each_allocation_shrinks_its_own(self):
        from logistics.domain.party_accruals import allocate_voucher_to_accruals

        clearance = self._posted_clearance("600")
        voucher = self._voucher(self.broker, "100")
        note = self._posted(self.broker, "debit", "80", currency=self.ils.pk)
        on_account, surplus, profile = self._buckets(self.broker)
        self.assertEqual((on_account, surplus), (D("100"), D("80")))
        self.assertEqual([(r["source"], r["id"], r["amount"]) for r in profile["on_account_items"]],
                         [("voucher", voucher.pk, "100.00")])
        self.assertEqual([(r["source"], r["id"], r["amount"]) for r in profile["surplus_items"]],
                         [("note", note["id"], "80.00")])
        closing = self._closing(self.broker)
        self.assertEqual(closing, D("600") - D("100") - D("80"))

        # السند على التخليص يُنقص «الدفعات» وحدها؛ والإشعار يُنقص «الفائض» وحده.
        allocate_voucher_to_accruals(voucher, [{"kind": "clearance", "id": clearance.pk, "amount": "60"}])
        self.assertEqual(self._buckets(self.broker)[:2], (D("40"), D("80")))
        res = self.client.post(f"{URL}{note['id']}/allocate/", {"allocations": [
            {"kind": "clearance", "id": clearance.pk, "amount": "30"}]}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self._buckets(self.broker)[:2], (D("40"), D("50")))
        # التوزيع لا يمسّ الدفتر: الرصيد الختامي كما هو.
        self.assertEqual(self._closing(self.broker), closing)

    def test_one_note_can_be_partly_allocated_and_partly_refunded(self):
        # إشعار حاييم: 2,000 على تخليص و942.96 استرداد — المتاح = المبلغ − الموزَّع − المسترَدّ.
        clearance = self._posted_clearance("5000")
        note = self._posted(self.broker, "debit", "2942.96", currency=self.ils.pk)
        closing = self._closing(self.broker)
        self.assertEqual(self._buckets(self.broker)[:2], (D("0"), D("2942.96")))
        res = self.client.post(f"{URL}{note['id']}/allocate/", {"allocations": [
            {"kind": "clearance", "id": clearance.pk, "amount": "2000"}]}, format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self._buckets(self.broker)[:2], (D("0"), D("942.96")))
        self.assertEqual(self._closing(self.broker), closing)
        # أكثر من الباقي يُرفض.
        res = self._refund(self.broker, "receipt", "943", [{"source": "note", "id": note["id"], "amount": "943"}])
        self.assertEqual(res.status_code, 400, res.content)
        res = self._refund(self.broker, "receipt", "942.96",
                           [{"source": "note", "id": note["id"], "amount": "942.96"}])
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(self._buckets(self.broker)[:2], (D("0"), D("0")))
        self.assertEqual(self.client.get(f"{URL}{note['id']}/", **self.h).data["unallocated_amount"], "0.00")
        # سند القبض حركةٌ نقدية حقيقية: Cr ذمّة المخلّص بالمسترَدّ.
        self.assertEqual(self._closing(self.broker), closing + D("942.96"))
        # وفي كشفه يقول ممّ استُردّ.
        rows = self.client.get(f"/api/partners/{self.broker.pk}/statement/", **self.h).data["results"]
        (receipt,) = [r for r in rows if r["reference_type"] == "CUSTOMER_PAYMENT"]
        self.assertEqual(receipt["details"], [f"استرداد من إشعار {note['note_number']}: 942.96"])

    # ── الصلاحيات والعزل ───────────────────────────────────────────────────
    def test_finance_permissions_gate_the_notes(self):
        # صلاحيات دفتر اليومية: موظف المبيعات بلا `accounting.journal.*` خارجها كلّها،
        # والمحاسب يُنشئ ويرحّل ويلغي الترحيل.
        note = self._note(self.broker)
        self.client.force_authenticate(user=self.seller)
        self.assertEqual(self.client.get(URL, **self.h).status_code, 403)
        self.assertEqual(self._create(self.broker).status_code, 403)
        self.assertEqual(self._post(note["id"]).status_code, 403)
        self.client.force_authenticate(user=self.accountant)
        self.assertEqual(self.client.get(URL, **self.h).status_code, 200)
        own = self._note(self.broker)
        self.assertEqual(self._post(own["id"]).status_code, 200)
        self.assertEqual(self.client.post(f"{URL}{own['id']}/unpost/", {}, format="json",
                                          **self.h).status_code, 200)

    def test_foreign_partner_is_not_accepted(self):
        foreign = Partner.objects.create(tenant=self.other, name="غريب", partner_type="CustomsBroker")
        self.assertEqual(self._create(foreign).status_code, 400)


def test_migration_renames_customer_to_partner_without_dropping_data():
    """`customer` ← `partner` بإعادة تسمية الحقل والعمود — لا حذفٌ ثم إضافة يفقد الصفوف."""
    module = importlib.import_module("sales.migrations.0045_credit_debit_note_any_partner")
    ops = module.Migration.operations
    rename = ops[0]
    assert isinstance(rename, migrations.RenameField)
    assert (rename.model_name, rename.old_name, rename.new_name) == ("creditdebitnote", "customer", "partner")
    assert not any(isinstance(op, migrations.RemoveField) for op in ops)
    alter = next(op for op in ops if isinstance(op, migrations.AlterField) and op.name == "partner")
    assert alter.field.db_column == "PartnerID"
