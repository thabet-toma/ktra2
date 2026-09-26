"""نصوص المستند المرحَّل (`core.posted_text`): الملاحظة تُعدَّل بعد الترحيل — وحدها.

بلاغ المالك: المستند المرحَّل يرفض أيّ تعديل حتى الملاحظة التي لا أثر محاسبي لها.
والمسح وجد العكس في ثلاثة مسارات: سند الصرف وسند القبض ودفعة الصفقة/الوكيل تُعدَّل
مرحَّلةً **بلا حارس** — مبلغها يتغيّر وقيدها كما هو. القائمة الصريحة تسدّ الاثنين.
"""
from decimal import Decimal

from accounting.models import Account, AccountingAuditLog, JournalHeader, JournalLine
from accounting.services import partner_account_statement, post_journal
from core.models import ActivityLog
from logistics.models import (
    LocalShipment,
    LocalShipmentPayment,
    LogisticsAccrualAllocation,
    LogisticsClearancePayment,
    LogisticsPayment,
    PurchaseInvoice,
)
from logistics.accruals import post_local_shipment_accrual
from logistics.tests.test_shipment_labels import _LabelBase
from partners.models import Partner
from sales.models import CreditDebitNote, CustomerPayment, PaymentAllocation, SalesInvoice, SupplierPayment
from sales.services import post_customer_payment

D = lambda v: Decimal(str(v))


def _ledger(journal_ids):
    """ما لا يجوز أن يتغيّر: الحساب والطرف والمبلغ والتاريخ لكل سطر."""
    return sorted(JournalLine.objects.filter(journal_id__in=journal_ids).values_list(
        "journal_id", "account_id", "partner_id", "debit", "credit", "journal__transaction_date"))


class PostedTextEditTest(_LabelBase):
    def _patch(self, url, data):
        return self.client.patch(url, data, format="json", **self.h)

    def _allocated_voucher(self):
        clearance = self._clearance(self._shipment("SH-0014", "شحنة ثانية"), "3000")
        voucher = self._voucher(2045)
        res = self.client.post(
            f"/api/logistics/supplier-payments/{voucher.id}/allocate-accruals/",
            {"allocations": [{"kind": "clearance", "id": clearance.pk, "amount": "2045"}]},
            format="json", **self.h)
        self.assertEqual(res.status_code, 200, res.content)
        voucher.refresh_from_db()
        self.assertTrue(voucher.is_posted)
        return voucher

    # ── سند الصرف ───────────────────────────────────────────────────────────
    def test_posted_allocated_voucher_note_changes_and_nothing_else(self):
        voucher = self._allocated_voucher()
        ledger = _ledger([voucher.journal_id])
        header = JournalHeader.objects.get(pk=voucher.journal_id).description
        allocations = list(LogisticsAccrualAllocation.objects.filter(payment=voucher).values_list("clearance_id", "amount"))

        res = self._patch(f"/api/logistics/supplier-payments/{voucher.id}/", {"notes": "حوالة بنكية 77"})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["notes"], "حوالة بنكية 77")
        voucher.refresh_from_db()
        self.assertEqual((voucher.notes, voucher.amount, voucher.is_posted), ("حوالة بنكية 77", D("2045"), True))
        self.assertEqual(_ledger([voucher.journal_id]), ledger)
        self.assertEqual(JournalHeader.objects.get(pk=voucher.journal_id).description, header)
        self.assertEqual(
            list(LogisticsAccrualAllocation.objects.filter(payment=voucher).values_list("clearance_id", "amount")),
            allocations)
        # سجلّ النشاط: قبل/بعد والمستخدم.
        log = ActivityLog.objects.filter(entity_type="supplier_payment", entity_id=voucher.id, action="update").latest("id")
        self.assertEqual(log.user_id, self.user.id)
        self.assertEqual(log.metadata["changes"], [
            {"field": "notes", "label": "الملاحظات", "old": "", "new": "حوالة بنكية 77"}])

    def test_posted_voucher_rejects_the_amount_even_beside_the_note(self):
        """كان مسار التعديل بلا حارس: المبلغ يتغيّر والقيد كما هو."""
        voucher = self._allocated_voucher()
        for data in ({"amount": "1"}, {"notes": "مع مبلغ", "amount": "1"}, {"payment_date": "2026-01-01"}):
            res = self._patch(f"/api/logistics/supplier-payments/{voucher.id}/", data)
            self.assertEqual(res.status_code, 400, res.content)
            self.assertIn("مرحَّل", str(res.data["detail"]))
        voucher.refresh_from_db()
        self.assertEqual((voucher.amount, voucher.notes or "", str(voucher.payment_date)), (D("2045"), "", "2026-08-01"))

    def test_draft_voucher_note_alone_is_still_a_normal_edit(self):
        res = self.client.post("/api/logistics/supplier-payments/", {
            "partner": self.broker.id, "payment_date": "2026-08-01", "amount": "50", "auto_post": False,
            "currency": self.ils.CurrencyID, "exchange_rate": "1", "cash_or_bank_account": self.cash.id,
        }, format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.content)
        self.assertFalse(res.data["is_posted"])
        res = self._patch(f"/api/logistics/supplier-payments/{res.data['id']}/", {"notes": "مسودة"})
        self.assertEqual((res.status_code, res.data.get("notes")), (200, "مسودة"), res.content)

    def test_split_voucher_keeps_its_origin_after_its_note_is_edited(self):
        clearance = self._clearance(self._shipment("SH-0013", "شحنة جوتو"), "7073")
        res = self.client.post(
            f"/api/logistics/clearances/{clearance.pk}/pay_from_cashbox/",
            {"amount": "9600", "cash_box_external_id": self.box.external_id, "payment_date": "2026-07-14"},
            format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.content)
        voucher_id = res.data["on_account_voucher"]["id"]
        closing = partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=self.broker.id, is_supplier=True)["closing_balance"]

        res = self._patch(f"/api/logistics/supplier-payments/{voucher_id}/", {"notes": "ملاحظة المستخدم"})
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.data["split_origin"]["label"], "تخليص SH-0013 — شحنة جوتو")
        statement = partner_account_statement(
            tenant_id=self.tenant.TenantID, partner_id=self.broker.id, is_supplier=True)
        (row,) = [r for r in statement["results"] if r["reference_type"] == "SUPPLIER_PAYMENT"]
        self.assertEqual((row["split_origin"]["paid"], row["split_origin"]["due"]), ("9600.00", "7073.00"))
        self.assertEqual(statement["closing_balance"], closing)

    # ── سند القبض: أوّل وصف قيده ملاحظته ────────────────────────────────────
    def test_customer_receipt_note_is_the_head_of_its_journal_description(self):
        customer = Partner.objects.create(tenant=self.tenant, name="زبون", partner_type="Customer")
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="SI-PT-1", customer=customer, currency=self.ils,
            invoice_date="2026-06-15", invoice_type=SalesInvoice.INVOICE_CREDIT,
            grand_total=D("100"), status=SalesInvoice.STATUS_POSTED)
        payment = CustomerPayment.objects.create(
            tenant=self.tenant, partner=customer, currency=self.ils, exchange_rate=D("1"), amount=D("100"),
            cash_or_bank_account=self.cash, payment_date="2026-06-20", is_posted=False)
        PaymentAllocation.objects.create(tenant=self.tenant, payment=payment, invoice=invoice, amount=D("100"))
        post_customer_payment(payment)
        payment.refresh_from_db()
        journal = JournalHeader.objects.get(reference_type="CUSTOMER_PAYMENT", reference_id=payment.pk)
        self.assertEqual(journal.description, "تحصيل عميل زبون — فاتورة SI-PT-1")
        ledger = _ledger([journal.pk])

        url = f"/api/sales/payments/{payment.pk}/"
        self.assertEqual(self._patch(url, {"notes": "شيك 55"}).status_code, 200)
        journal.refresh_from_db()
        self.assertEqual(journal.description, "شيك 55 — فاتورة SI-PT-1")
        self.assertEqual(self._patch(url, {"notes": ""}).status_code, 200)
        journal.refresh_from_db()
        self.assertEqual(journal.description, "تحصيل عميل زبون — فاتورة SI-PT-1")
        self.assertEqual(_ledger([journal.pk]), ledger)
        self.assertTrue(AccountingAuditLog.objects.filter(
            model_name="JournalHeader", object_id=journal.pk, action="UPDATE").exists())
        res = self._patch(url, {"amount": "1"})
        self.assertEqual(res.status_code, 400, res.content)
        payment.refresh_from_db()
        self.assertEqual(payment.amount, D("100"))

    # ── الإشعار: سببه وصفُ سطر الحساب المقابل ───────────────────────────────
    def test_note_reason_edits_the_counter_line_only(self):
        url = "/api/sales/credit-debit-notes/"
        res = self.client.post(url, {"note_date": "2026-07-10", "note_type": "debit", "partner": self.broker.pk,
                                     "amount": "100", "reason": "تسوية"}, format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.content)
        note_id = res.data["id"]
        self.assertEqual(self.client.post(f"{url}{note_id}/post/", {}, format="json", **self.h).status_code, 200)
        note = CreditDebitNote.objects.get(pk=note_id)
        ledger = _ledger([note.journal_id])
        header = note.journal.description

        res = self._patch(f"{url}{note_id}/", {"reason": "خصم متّفق عليه"})
        self.assertEqual(res.status_code, 200, res.content)
        counter = JournalLine.objects.get(journal_id=note.journal_id, account_id=note.counter_account_id)
        self.assertEqual(counter.description, "خصم متّفق عليه")
        self.assertEqual(JournalHeader.objects.get(pk=note.journal_id).description, header)
        self.assertEqual(_ledger([note.journal_id]), ledger)
        self.assertEqual(self._patch(f"{url}{note_id}/", {"amount": "5"}).status_code, 400)

    # ── فاتورة البيع: ذيل وصف قيدها ─────────────────────────────────────────
    def test_sales_invoice_note_is_the_tail_of_its_journal_description(self):
        customer = Partner.objects.create(tenant=self.tenant, name="زبون", partner_type="Customer")
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="SI-PT-2", customer=customer, currency=self.ils,
            invoice_date="2026-06-15", grand_total=D("40"), status=SalesInvoice.STATUS_POSTED, notes="قديمة")
        revenue = Account.objects.create(tenant=self.tenant, code="REV-PT", name="إيراد", account_type="Revenue")
        journal = post_journal(
            tenant_id=self.tenant.TenantID, transaction_date="2026-06-15", reference_type="SALES_INVOICE",
            reference_id=invoice.pk, description="فاتورة SI-PT-2 — زبون · قديمة",
            lines_data=[{"account": self.cash.id, "debit": D("40"), "credit": D("0")},
                        {"account": revenue.id, "debit": D("0"), "credit": D("40")}])
        SalesInvoice.objects.filter(pk=invoice.pk).update(journal=journal)
        # قيدُ «تحصيل نقدي» قديمٌ على المرجع نفسه — ليس قيدَ الفاتورة فلا يُمسّ. (`post_journal`
        # يعيد استعمال قيد المرجع، فيُنشأ على غيره ثم يُنقل كما هو في البيانات القديمة.)
        legacy = post_journal(
            tenant_id=self.tenant.TenantID, transaction_date="2026-06-15", reference_type="LEGACY_CASH",
            reference_id=invoice.pk, description="تحصيل نقدي — فاتورة SI-PT-2",
            lines_data=[{"account": self.cash.id, "debit": D("40"), "credit": D("0")},
                        {"account": revenue.id, "debit": D("0"), "credit": D("40")}])
        JournalHeader.objects.filter(pk=legacy.pk).update(reference_type="SALES_INVOICE")
        url = f"/api/sales/invoices/{invoice.pk}/"
        self.assertEqual(self._patch(url, {"notes": "جديدة"}).status_code, 200)
        journal.refresh_from_db()
        self.assertEqual(journal.description, "فاتورة SI-PT-2 — زبون · جديدة")
        self.assertEqual(self._patch(url, {"notes": ""}).status_code, 200)
        journal.refresh_from_db()
        self.assertEqual(journal.description, "فاتورة SI-PT-2 — زبون")
        # فاتورةٌ بلا ملاحظة تكسبها: ذيلٌ على قيدها وحده.
        self.assertEqual(self._patch(url, {"notes": "ثالثة"}).status_code, 200)
        journal.refresh_from_db()
        legacy.refresh_from_db()
        self.assertEqual(journal.description, "فاتورة SI-PT-2 — زبون · ثالثة")
        self.assertEqual(legacy.description, "تحصيل نقدي — فاتورة SI-PT-2")
        res = self._patch(url, {"notes": "x", "invoice_date": "2026-01-01"})
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(res.data["locked_fields"], ["invoice_date"])

    # ── فاتورة الشراء: الملاحظة ورقم فاتورة المورد ──────────────────────────
    def test_posted_purchase_invoice_takes_notes_and_supplier_number_only(self):
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="PI-PT-1", partner=self.supplier, currency=self.ils,
            invoice_date="2026-06-18", exchange_rate=D("1"), grand_total=D("100"),
            payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT, is_posted=True)
        url = f"/api/logistics/purchase-invoices/{invoice.pk}/"
        res = self._patch(url, {"notes": "وصلت ناقصة", "supplier_invoice_number": "INV-889"})
        self.assertEqual(res.status_code, 200, res.content)
        invoice.refresh_from_db()
        self.assertEqual((invoice.notes, invoice.supplier_invoice_number), ("وصلت ناقصة", "INV-889"))
        res = self._patch(url, {"grand_total": "1"})
        self.assertEqual(res.status_code, 400, res.content)
        self.assertTrue(res.data.get("can_unpost"))

    # ── دفعات التخليص والإرسالية والوكيل ───────────────────────────────────
    def test_clearance_and_local_payment_notes(self):
        clearance = self._clearance(self._shipment("SH-0017", "شحنة رقع"), "900")
        self.client.post(f"/api/logistics/clearances/{clearance.pk}/pay_from_cashbox/",
                         {"amount": "400", "cash_box_external_id": self.box.external_id,
                          "payment_date": "2026-07-01"}, format="json", **self.h)
        payment = LogisticsClearancePayment.objects.get(clearance=clearance)
        url = f"/api/logistics/clearances/{clearance.pk}/payments/{payment.pk}/"
        res = self._patch(url, {"notes": "مطالبة CLM-9"})
        self.assertEqual((res.status_code, res.data.get("notes")), (200, "مطالبة CLM-9"), res.content)
        self.assertEqual(self._patch(url, {"amount": "1"}).status_code, 400)
        payment.refresh_from_db()
        self.assertEqual(payment.amount, D("400"))

        local = LocalShipment.objects.create(
            tenant=self.tenant, carrier=self.carrier, amount=D("450"), currency=self.ils, exchange_rate=D("1"),
            delivery_date="2026-06-20", pickup_date="2026-06-20",
            expense_account=Account.objects.get(tenant=self.tenant, code="5305"))
        post_local_shipment_accrual(LocalShipment.objects.get(pk=local.pk))
        self.client.post(f"/api/logistics/local-shipments/{local.pk}/pay_from_cashbox/",
                         {"amount": "450", "cash_box_external_id": self.box.external_id,
                          "payment_date": "2026-07-01"}, format="json", **self.h)
        local_payment = LocalShipmentPayment.objects.get(local_shipment=local)
        res = self._patch(f"/api/logistics/local-shipments/{local.pk}/payments/{local_payment.pk}/", {"notes": "سائق 2"})
        self.assertEqual((res.status_code, res.data.get("notes")), (200, "سائق 2"), res.content)
        # دفعةٌ من إرساليةٍ أخرى لا تُعدَّل عبر هذه.
        other = self._clearance(self._shipment("SH-0018"), "100")
        self.assertEqual(self._patch(f"/api/logistics/clearances/{other.pk}/payments/{payment.pk}/",
                                     {"notes": "x"}).status_code, 404)

    def test_posted_agent_payment_amount_is_locked(self):
        shipment = self._shipment("SH-0020")
        payment = LogisticsPayment.objects.create(
            tenant=self.tenant, shipment=shipment, amount=D("500"), is_posted=True, status="Confirmed")
        url = f"/api/logistics/payments/{payment.pk}/"
        self.assertEqual(self._patch(url, {"amount": "1"}).status_code, 400)
        res = self._patch(url, {"notes": "حوالة"})
        self.assertEqual(res.status_code, 200, res.content)
        payment.refresh_from_db()
        self.assertEqual((payment.amount, payment.notes), (D("500"), "حوالة"))

    def test_other_company_cannot_touch_the_note(self):
        voucher = self._allocated_voucher()
        from django.contrib.auth.models import User
        from tenants.services import create_company

        stranger = User.objects.create_user(username="posted-text-stranger", password="x")
        other = create_company("شركة غريبة", stranger)
        self.client.force_authenticate(user=stranger)
        res = self.client.patch(f"/api/logistics/supplier-payments/{voucher.id}/", {"notes": "x"},
                                format="json", HTTP_X_TENANT_ID=str(other.TenantID))
        self.assertEqual(res.status_code, 404, res.content)
        self.assertEqual(SupplierPayment.objects.get(pk=voucher.pk).notes or "", "")
