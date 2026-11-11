"""الدفعات و«اللي عليه» وكشف الحساب (#283، الجزء أ — الخادم).

**القواعدُ التي يسقط عندها الاختبار:**
1. التخصيصُ **الأقدمُ أوّلَاً** (`year, month, id`) على المعتمدة وحدها.
2. الجزئيُّ يظهر «مدفوعة جزئياً» **مشتقّاً** لا بتغيير `FeeDraft.status`.
3. الزيادةُ رصيدٌ دائنٌ مشتقٌّ لا مخزَّن، يُستهلك بتخصيصٍ جديدٍ على الفاتورة القادمة.
4. `client_due` الصيغةُ الوحيدة: `due = Σ remaining − credit`، و`draft`/`cancelled`
   لا تدخلان الحساب.
5. الشطبُ سطرٌ إلحاقيٌّ يخفّض `remaining`، وبيد صاحب المكتب وحده، وبسببٍ مكتوب.
6. رقمُ الإشعار من عدّادٍ مقفولٍ متسلسل — **لا `MAX+1`**.
7. القناعُ: من لا يرى المبالغ لا يقرأ `amount`/`due`/`remaining`/`credit`.
8. العزل: دفعةُ مكتبٍ آخر لا تظهر، وتخصيصٌ على مسودّة غيره لا يمرّ.

**والقرارُ المثبَّت:** `due` **سالبٌ** حين يكون للزبون رصيدٌ دائن (`due = Σ remaining −
credit`) — لا يُقصّ إلى صفر. فالدفعةُ الزائدة 700 على 650 تعطي `credit = 50` و
`due = -50`، ورقمٌ سالبٌ يقول «له عندنا» بلا حقلٍ ثانٍ يُقرأ معه.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from accounting_office import payments, services
from accounting_office.models import (
    ClientService,
    FeeDraft,
    FeePayment,
    FeePaymentAllocation,
    FeeReceiptSequence,
    FeeWriteOff,
    Obligation,
    OfficeClient,
    OfficeCustomRule,
    OfficeService,
    PeriodTask,
    TaxCard,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
PAYMENTS = f"{BASE}fees/payments/"
DRAFTS = f"{BASE}fees/drafts/"
LEDGER = f"{BASE}fees/ledger/"
CLIENTS = f"{BASE}clients/"

WRITE_OFF = "write-off/"


def decimal_of(value) -> Decimal:
    """المبلغُ كما يصل من الـAPI — عشريٌّ أو نصٌّ، لا فرق."""
    return Decimal(str(value))


class PaymentsTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.currency = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )[0]
        cls.owner = User.objects.create_user(username="pay_owner", password="x")
        cls.tenant = create_company("مكتب الدفعات", cls.owner, template="accounting_office")
        invalidate_module_cache(cls.tenant.pk)
        services.set_office_setting(cls.tenant, "tax_system", "PS")
        services.set_office_setting(cls.tenant, "office_size", "small")

        cls.office_manager_user = User.objects.create_user(
            username="pay_office_manager", password="x",
        )
        UserCompanyMembership.objects.create(
            user=cls.office_manager_user, tenant=cls.tenant, role="office_manager",
        )
        cls.accountant_user = User.objects.create_user(
            username="pay_accountant", password="x",
        )
        UserCompanyMembership.objects.create(
            user=cls.accountant_user, tenant=cls.tenant, role="accountant",
        )

    def as_user(self, user):
        self.client.force_authenticate(user=user)

    def setUp(self):
        self.as_user(self.owner)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def make_client(self, name="زبون الدفعات", *, tenant=None, responsible=None):
        client = OfficeClient.objects.create(
            tenant=tenant or self.tenant, name=name, responsible=responsible,
        )
        TaxCard.objects.create(client=client)
        return client

    def make_draft(self, client, total, *, year=2026, month=3,
                   status=FeeDraft.STATUS_APPROVED):
        return FeeDraft.objects.create(
            tenant=client.tenant,
            client=client,
            year=year,
            month=month,
            subtotal=Decimal(str(total)),
            total=Decimal(str(total)),
            status=status,
            approved_by=self.owner if status == FeeDraft.STATUS_APPROVED else None,
        )

    def post_payment(self, payload):
        return self.client.post(PAYMENTS, payload, format="json", **self.headers())

    def payment_of(self, client, amount, paid_at="2026-05-01", **extra):
        payload = {
            "client": client.pk,
            "amount": amount,
            "method": extra.pop("method", "cash"),
            "paid_at": paid_at,
        }
        payload.update(extra)
        res = self.post_payment(payload)
        self.assertEqual(res.status_code, 201, res.content)
        return FeePayment.objects.get(pk=res.data["id"])

    def allocations_of(self, payment):
        return {
            row.draft_id: decimal_of(row.amount)
            for row in payment.allocations.all()
        }


class OldestFirstAllocationTest(PaymentsTestCase):
    def test_500_on_300_and_350_pays_the_older_one_and_partially_the_newer(self):
        client = self.make_client()
        march = self.make_draft(client, "300", month=3)
        april = self.make_draft(client, "350", month=4)

        payment = self.payment_of(client, "500.00")

        self.assertEqual(payment.receipt_number, "2026-00001")
        self.assertEqual(
            self.allocations_of(payment), {march.pk: Decimal("300.00"), april.pk: Decimal("200.00")},
        )
        self.assertEqual(decimal_of(march.total), Decimal("300.00"))
        self.assertEqual(march.status, FeeDraft.STATUS_APPROVED, "الجزئيُّ لا يغيّر حالةَ المسودّة")

        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.due, Decimal("150.00"))
        self.assertEqual(due.invoices_total, Decimal("650.00"))
        self.assertEqual(due.paid_total, Decimal("500.00"))
        self.assertEqual(due.credit, Decimal("0.00"))
        self.assertEqual(due.unpaid_count, 1)

        self.assertEqual(payments.invoice_summary(march).remaining, Decimal("0.00"))
        self.assertEqual(payments.invoice_summary(march).state, "paid")
        self.assertEqual(payments.invoice_summary(april).remaining, Decimal("150.00"))
        self.assertEqual(payments.invoice_summary(april).state, "partial")


class CreditIsDerivedTest(PaymentsTestCase):
    def test_an_overpayment_is_credit_and_the_due_goes_negative(self):
        client = self.make_client()
        draft = self.make_draft(client, "650")

        payment = self.payment_of(client, "700.00")

        self.assertEqual(self.allocations_of(payment), {draft.pk: Decimal("650.00")})
        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.credit, Decimal("50.00"))
        self.assertEqual(due.due, Decimal("-50.00"))
        self.assertEqual(due.paid_total, Decimal("650.00"))
        self.assertEqual(due.unpaid_count, 0)

    def test_the_credit_is_consumed_by_the_next_invoice_with_a_new_allocation(self):
        client = self.make_client()
        first = self.make_draft(client, "650", month=3)
        payment = self.payment_of(client, "700.00")
        self.assertEqual(payment.allocations.count(), 1)

        later = self.make_draft(client, "300", month=4, status=FeeDraft.STATUS_DRAFT)
        approved = self.client.post(
            f"{DRAFTS}{later.pk}/approve/", {}, format="json", **self.headers(),
        )
        self.assertEqual(approved.status_code, 200, approved.content)

        payment.refresh_from_db()
        self.assertEqual(
            self.allocations_of(payment),
            {first.pk: Decimal("650.00"), later.pk: Decimal("50.00")},
            "الرصيدُ الدائن لم يُستهلك بتخصيصٍ جديدٍ على الفاتورة القادمة",
        )
        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.credit, Decimal("0.00"))
        self.assertEqual(due.invoices_total, Decimal("950.00"))
        self.assertEqual(due.due, Decimal("250.00"))
        self.assertEqual(
            payments.invoice_summary(later).state, "partial",
        )


class DueExcludesUnapprovedTest(PaymentsTestCase):
    def test_draft_and_cancelled_invoices_do_not_enter_the_due(self):
        client = self.make_client()
        self.make_draft(client, "300", month=3)
        self.make_draft(client, "500", month=4, status=FeeDraft.STATUS_DRAFT)
        self.make_draft(client, "400", month=5, status=FeeDraft.STATUS_CANCELLED)

        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.due, Decimal("300.00"))
        self.assertEqual(due.invoices_total, Decimal("300.00"))
        self.assertEqual(due.unpaid_count, 1)

        listed = self.client.get(LEDGER, {"client": client.pk}, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(
            [row["month"] for row in listed.data["invoices"]["results"]], [3],
            "كشفُ الحساب عرض مسودّةً أو ملغاة",
        )

    def test_an_allocation_on_a_draft_invoice_is_refused(self):
        client = self.make_client()
        pending = self.make_draft(client, "300", status=FeeDraft.STATUS_DRAFT)

        res = self.post_payment({
            "client": client.pk,
            "amount": "100.00",
            "method": "cash",
            "paid_at": "2026-05-01",
            "allocations": [{"draft": pending.pk, "amount": "100.00"}],
        })

        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(FeePayment.objects.count(), 0)
        self.assertEqual(FeePaymentAllocation.objects.count(), 0)


class ExplicitAllocationTest(PaymentsTestCase):
    def test_the_employee_may_choose_the_invoice_and_the_rest_becomes_credit(self):
        client = self.make_client()
        march = self.make_draft(client, "300", month=3)
        april = self.make_draft(client, "350", month=4)

        payment = self.payment_of(client, "400.00", allocations=[
            {"draft": april.pk, "amount": "350.00"},
        ])

        self.assertEqual(
            self.allocations_of(payment), {april.pk: Decimal("350.00")},
            "الأقدمُ أولاً افتراضٌ يُلغيه التخصيصُ الصريح",
        )
        due = payments.client_due(self.tenant, client)
        self.assertEqual(due.credit, Decimal("50.00"))
        self.assertEqual(due.due, Decimal("250.00"))
        self.assertEqual(payments.invoice_summary(march).remaining, Decimal("300.00"))

    def test_allocations_above_the_payment_or_the_remaining_are_refused(self):
        client = self.make_client()
        draft = self.make_draft(client, "300")

        over_draft = self.post_payment({
            "client": client.pk, "amount": "500.00", "method": "cash",
            "paid_at": "2026-05-01",
            "allocations": [{"draft": draft.pk, "amount": "400.00"}],
        })
        self.assertEqual(over_draft.status_code, 400, over_draft.content)

        over_payment = self.post_payment({
            "client": client.pk, "amount": "100.00", "method": "cash",
            "paid_at": "2026-05-01",
            "allocations": [{"draft": draft.pk, "amount": "150.00"}],
        })
        self.assertEqual(over_payment.status_code, 400, over_payment.content)

        not_positive = self.post_payment({
            "client": client.pk, "amount": "100.00", "method": "cash",
            "paid_at": "2026-05-01",
            "allocations": [{"draft": draft.pk, "amount": "0.00"}],
        })
        self.assertEqual(not_positive.status_code, 400, not_positive.content)
        self.assertEqual(FeePayment.objects.count(), 0)

    def test_a_zero_payment_is_refused(self):
        client = self.make_client()
        res = self.post_payment({
            "client": client.pk, "amount": "0.00", "method": "cash",
            "paid_at": "2026-05-01",
        })
        self.assertEqual(res.status_code, 400, res.content)
        self.assertEqual(FeePayment.objects.count(), 0)


class WriteOffTest(PaymentsTestCase):
    def test_a_write_off_lowers_the_remaining_and_deletes_nothing(self):
        client = self.make_client()
        draft = self.make_draft(client, "300")
        payment = self.payment_of(client, "100.00")

        res = self.client.post(
            f"{DRAFTS}{draft.pk}/{WRITE_OFF}",
            {"amount": "50.00", "reason": "خصمٌ اتُّفق عليه مع الزبون"},
            format="json", **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content)

        self.assertEqual(payments.invoice_summary(draft).remaining, Decimal("150.00"))
        self.assertEqual(payments.client_due(self.tenant, client).due, Decimal("150.00"))
        self.assertEqual(FeePayment.objects.count(), 1)
        self.assertEqual(FeePaymentAllocation.objects.count(), 1)
        self.assertEqual(FeeWriteOff.objects.count(), 1)
        payment.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(decimal_of(payment.amount), Decimal("100.00"))
        self.assertEqual(decimal_of(draft.total), Decimal("300.00"))
        self.assertEqual(draft.status, FeeDraft.STATUS_APPROVED)

    def test_a_write_off_needs_a_reason_and_a_positive_amount(self):
        client = self.make_client()
        draft = self.make_draft(client, "300")

        blank = self.client.post(
            f"{DRAFTS}{draft.pk}/{WRITE_OFF}", {"amount": "10.00", "reason": "  "},
            format="json", **self.headers(),
        )
        self.assertEqual(blank.status_code, 400, blank.content)

        zero = self.client.post(
            f"{DRAFTS}{draft.pk}/{WRITE_OFF}",
            {"amount": "0.00", "reason": "سبب"},
            format="json", **self.headers(),
        )
        self.assertEqual(zero.status_code, 400, zero.content)
        self.assertEqual(FeeWriteOff.objects.count(), 0)

    def test_above_the_remaining_and_on_a_draft_invoice_are_refused(self):
        client = self.make_client()
        draft = self.make_draft(client, "300")
        pending = self.make_draft(client, "100", month=4, status=FeeDraft.STATUS_DRAFT)

        too_much = self.client.post(
            f"{DRAFTS}{draft.pk}/{WRITE_OFF}",
            {"amount": "301.00", "reason": "سبب"},
            format="json", **self.headers(),
        )
        self.assertEqual(too_much.status_code, 400, too_much.content)

        not_approved = self.client.post(
            f"{DRAFTS}{pending.pk}/{WRITE_OFF}",
            {"amount": "10.00", "reason": "سبب"},
            format="json", **self.headers(),
        )
        self.assertEqual(not_approved.status_code, 400, not_approved.content)
        self.assertEqual(FeeWriteOff.objects.count(), 0)

    def test_anyone_but_the_office_owner_is_refused(self):
        # لكل مستخدمٍ زبونُه المسؤولُ عنه: الرؤيةُ تسبق الدور، فزبونُ غيره 404
        # لا 403 — والقاعدةُ على الدور تُقاس على مسودّةٍ يراها فعلاً.
        for user in (self.office_manager_user, self.accountant_user):
            client = self.make_client(f"زبون {user.username}", responsible=user)
            draft = self.make_draft(client, "300")
            self.as_user(user)
            res = self.client.post(
                f"{DRAFTS}{draft.pk}/{WRITE_OFF}",
                {"amount": "10.00", "reason": "سبب"},
                format="json", **self.headers(),
            )
            self.assertEqual(
                res.status_code, 403, f"{user.username}: {res.content}",
            )
        self.assertEqual(FeeWriteOff.objects.count(), 0)


class ReceiptNumberTest(PaymentsTestCase):
    def test_receipt_numbers_are_sequential_and_unique_per_tenant_and_year(self):
        client = self.make_client()
        first = self.payment_of(client, "10.00", paid_at="2026-05-01")
        second = self.payment_of(client, "10.00", paid_at="2026-05-02")
        next_year = self.payment_of(client, "10.00", paid_at="2027-01-02")

        self.assertEqual(first.receipt_number, "2026-00001")
        self.assertEqual(second.receipt_number, "2026-00002")
        self.assertEqual(next_year.receipt_number, "2027-00001")

        with self.assertRaises(IntegrityError), transaction.atomic():
            FeePayment.objects.create(
                tenant=self.tenant,
                client=client,
                method="cash",
                amount=Decimal("10"),
                paid_at=datetime.date(2026, 5, 3),
                receipt_number=first.receipt_number,
            )

    def test_the_counter_does_not_read_the_maximum_stored_receipt(self):
        """لو صار الرقم `MAX+1` لأعطى 09778 — العدّادُ المقفول وحده يعطي 00002."""
        client = self.make_client()
        FeeReceiptSequence.objects.create(
            tenant=self.tenant, year=2026, last_number=1,
        )
        FeePayment.objects.create(
            tenant=self.tenant,
            client=client,
            method="cash",
            amount=Decimal("5"),
            paid_at=datetime.date(2026, 4, 1),
            receipt_number="2026-09777",
        )

        payment = payments.create_payment(
            self.tenant, client,
            amount="10.00", method="cash", paid_at=datetime.date(2026, 5, 1),
            actor=self.owner,
        )

        self.assertEqual(payment.receipt_number, "2026-00002")
        sequence = FeeReceiptSequence.objects.get(tenant=self.tenant, year=2026)
        self.assertEqual(sequence.last_number, 2)


class PaymentListTest(PaymentsTestCase):
    def test_filters_client_method_and_date_range(self):
        client = self.make_client()
        other = self.make_client("زبون آخر")
        self.payment_of(client, "10.00", paid_at="2026-05-01", method="cash")
        self.payment_of(client, "20.00", paid_at="2026-06-01", method="transfer")
        self.payment_of(other, "30.00", paid_at="2026-05-15")

        by_client = self.client.get(PAYMENTS, {"client": client.pk}, **self.headers())
        self.assertEqual(len(by_client.data), 2)

        by_method = self.client.get(PAYMENTS, {"method": "transfer"}, **self.headers())
        self.assertEqual(
            [decimal_of(row["amount"]) for row in by_method.data], [Decimal("20.00")],
        )

        by_date = self.client.get(
            PAYMENTS, {"date_from": "2026-05-01", "date_to": "2026-05-31"},
            **self.headers(),
        )
        self.assertEqual(
            sorted(decimal_of(row["amount"]) for row in by_date.data),
            [Decimal("10.00"), Decimal("30.00")],
        )

    def test_no_update_and_no_delete_on_payments(self):
        client = self.make_client()
        payment = self.payment_of(client, "10.00")
        # الجمعُ يردّ 405 لطريقةٍ غير مدرَجة، والتفصيلُ لا مسارَ له أصلاً (404):
        # لا قراءةً لسندٍ واحد ولا كتابةً فوق سند قبضٍ صدر.
        self.assertEqual(
            self.client.delete(PAYMENTS, **self.headers()).status_code, 405,
        )
        self.assertEqual(
            self.client.patch(
                PAYMENTS, {"note": "x"}, format="json", **self.headers(),
            ).status_code,
            405,
        )
        detail = f"{PAYMENTS}{payment.pk}/"
        self.assertEqual(self.client.get(detail, **self.headers()).status_code, 404)
        self.assertEqual(
            self.client.delete(detail, **self.headers()).status_code, 404,
        )


class MaskTest(PaymentsTestCase):
    def test_a_member_without_the_amounts_key_reads_no_money_anywhere(self):
        client = self.make_client("زبون المحاسب", responsible=self.accountant_user)
        draft = self.make_draft(client, "300")
        self.payment_of(client, "100.00")

        self.as_user(self.accountant_user)

        listed = self.client.get(PAYMENTS, **self.headers())
        self.assertEqual(listed.status_code, 200, listed.content)
        row = listed.data[0]
        self.assertIsNone(row["amount"])
        self.assertIsNone(row["due"])
        self.assertIsNone(row["credit"])
        self.assertIsNone(row["allocations"][0]["amount"])

        drafts = self.client.get(DRAFTS, **self.headers())
        self.assertEqual(drafts.status_code, 200, drafts.content)
        draft_row = drafts.data[0]
        self.assertIsNone(draft_row["paid_amount"])
        self.assertIsNone(draft_row["remaining"])
        # والحالةُ ليست مبلغاً: تُقرأ لتُعرض «مدفوعة جزئياً» ولو حُجب المال.
        self.assertIsNotNone(draft_row["state"])

        clients = self.client.get(CLIENTS, **self.headers())
        self.assertEqual(clients.status_code, 200, clients.content)
        self.assertIsNone(clients.data[0]["due"])

        ledger = self.client.get(LEDGER, {"client": client.pk}, **self.headers())
        self.assertEqual(ledger.status_code, 200, ledger.content)
        self.assertIsNone(ledger.data["invoices"]["results"][0]["remaining"])
        self.assertIsNone(ledger.data["invoices"]["results"][0]["total"])
        self.assertIsNone(ledger.data["payments"]["results"][0]["amount"])
        self.assertIsNone(ledger.data["client_due"]["due"])

        self.assertIsNone(payments.client_due_payload(
            self.tenant, client, user=self.accountant_user,
        )["due"], "الحمولةُ المباشرة للدالة تمرّ بالقناع كذلك")

    def test_the_owner_sees_the_numbers(self):
        client = self.make_client()
        self.make_draft(client, "300")
        self.payment_of(client, "100.00")
        listed = self.client.get(PAYMENTS, **self.headers())
        self.assertEqual(decimal_of(listed.data[0]["amount"]), Decimal("100.00"))
        self.assertEqual(decimal_of(listed.data[0]["due"]), Decimal("200.00"))


class IsolationTest(PaymentsTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other_owner = User.objects.create_user(username="pay_other_owner", password="x")
        cls.other_tenant = create_company(
            "مكتب آخر", cls.other_owner, template="accounting_office",
        )
        invalidate_module_cache(cls.other_tenant.pk)
        services.set_office_setting(cls.other_tenant, "tax_system", "PS")
        services.set_office_setting(cls.other_tenant, "office_size", "small")
        cls.other_client = OfficeClient.objects.create(
            tenant=cls.other_tenant, name="زبون المكتب الآخر",
        )
        TaxCard.objects.create(client=cls.other_client)
        cls.other_draft = FeeDraft.objects.create(
            tenant=cls.other_tenant,
            client=cls.other_client,
            year=2026,
            month=3,
            subtotal=Decimal("300"),
            total=Decimal("300"),
            status=FeeDraft.STATUS_APPROVED,
        )
        cls.other_payment = FeePayment.objects.create(
            tenant=cls.other_tenant,
            client=cls.other_client,
            method="cash",
            amount=Decimal("90"),
            paid_at=datetime.date(2026, 5, 1),
            receipt_number="2026-00001",
        )

    def test_a_payment_of_another_office_is_neither_listed_nor_allocated(self):
        client = self.make_client()

        res = self.post_payment({
            "client": self.other_client.pk,
            "amount": "10.00",
            "method": "cash",
            "paid_at": "2026-05-01",
        })
        self.assertEqual(res.status_code, 404, res.content)

        listed = self.client.get(PAYMENTS, **self.headers())
        self.assertEqual([row["id"] for row in listed.data], [])

        foreign_draft = self.post_payment({
            "client": client.pk,
            "amount": "10.00",
            "method": "cash",
            "paid_at": "2026-05-01",
            "allocations": [{"draft": self.other_draft.pk, "amount": "10.00"}],
        })
        self.assertEqual(foreign_draft.status_code, 400, foreign_draft.content)
        self.assertEqual(
            FeePaymentAllocation.objects.filter(draft=self.other_draft).count(), 0,
        )

    def test_the_other_office_keeps_its_own_payment(self):
        self.as_user(self.other_owner)
        listed = self.client.get(PAYMENTS, **self.headers(self.other_tenant))
        self.assertEqual([row["id"] for row in listed.data], [self.other_payment.pk])

        self.as_user(self.owner)
        self.assertEqual(
            self.client.get(PAYMENTS, **self.headers()).status_code, 200,
        )
        self.assertEqual(
            FeePayment.objects.filter(tenant=self.tenant).count(), 0,
        )


class LedgerTest(PaymentsTestCase):
    def test_state_filters_and_name_search_are_answered_by_the_query(self):
        paid_client = self.make_client("منشأة الأمل")
        partial_client = self.make_client("منشأة النور")
        paid = self.make_draft(paid_client, "300", month=3)
        partial = self.make_draft(partial_client, "350", month=4)
        self.payment_of(paid_client, "300.00")
        self.payment_of(partial_client, "100.00")

        paid_res = self.client.get(LEDGER, {"state": "paid"}, **self.headers())
        self.assertEqual(paid_res.status_code, 200, paid_res.content)
        self.assertEqual(
            [row["id"] for row in paid_res.data["invoices"]["results"]], [paid.pk],
        )

        partial_res = self.client.get(LEDGER, {"state": "partial"}, **self.headers())
        self.assertEqual(
            [row["id"] for row in partial_res.data["invoices"]["results"]], [partial.pk],
        )
        self.assertEqual(
            decimal_of(partial_res.data["invoices"]["results"][0]["remaining"]),
            Decimal("250.00"),
        )

        unpaid_res = self.client.get(LEDGER, {"state": "unpaid"}, **self.headers())
        self.assertEqual(unpaid_res.data["invoices"]["results"], [])

        searched = self.client.get(LEDGER, {"q": "النور"}, **self.headers())
        self.assertEqual(
            [row["client"]["id"] for row in searched.data["invoices"]["results"]],
            [partial_client.pk],
        )
        self.assertEqual(
            [row["client"]["id"] for row in searched.data["payments"]["results"]],
            [partial_client.pk],
        )

    def test_the_filtered_client_carries_his_due_and_a_foreign_one_is_404(self):
        client = self.make_client()
        self.make_draft(client, "300")
        self.payment_of(client, "100.00")

        res = self.client.get(LEDGER, {"client": client.pk}, **self.headers())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(decimal_of(res.data["client_due"]["due"]), Decimal("200.00"))
        self.assertIsNone(
            self.client.get(LEDGER, **self.headers()).data["client_due"],
            "بلا فلترٍ لا زبونَ واحدٌ يُقال عنه «اللي عليه»",
        )
        self.assertEqual(
            self.client.get(LEDGER, {"client": 999999}, **self.headers()).status_code,
            404,
        )

    def test_pagination_slices_the_queryset(self):
        client = self.make_client()
        for index in range(3):
            self.make_draft(client, "100", month=index + 1)
            self.payment_of(client, "10.00", paid_at=f"2026-0{index + 5}-01")

        res = self.client.get(
            LEDGER, {"page": 2, "page_size": 2}, **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        invoices = res.data["invoices"]
        self.assertEqual(invoices["count"], 3)
        self.assertEqual(len(invoices["results"]), 1)
        payments_page = res.data["payments"]
        self.assertEqual(payments_page["count"], 3)
        self.assertEqual(len(payments_page["results"]), 1)


class TaxNoteTest(PaymentsTestCase):
    """سطرُ العلم الضريبيّ: مجموعُ الالتزامات غير المدفوعة — **خارجَ «اللي عليه»**.

    `Obligation` لا يحمل حقلاً خاصّاً بمبلغ ضريبة؛ فالسطرُ مجموعُ `amount` في
    الالتزامات غير المعلَّمة `client_paid` — ولا حقلَ جديدٌ يُخترَع له.
    """

    def test_the_tax_note_sums_unpaid_obligations_and_stays_out_of_the_due(self):
        client = self.make_client()
        self.make_draft(client, "300")
        client_service, task = self._scaffold(client)
        self._obligation(client, client_service, task, "120", client_paid=False)
        self._obligation(client, client_service, task, "80", client_paid=False)
        self._obligation(client, client_service, task, "50", client_paid=True)

        self.assertEqual(
            payments.client_due_tax_note(self.tenant, client), Decimal("200.00"),
        )
        self.assertEqual(
            payments.client_due(self.tenant, client).due, Decimal("300.00"),
            "سطرُ العلم لا يدخل «اللي عليه»",
        )

        preview = payments.client_due_payload(self.tenant, client, user=self.owner)
        self.assertEqual(decimal_of(preview["tax_note"]), Decimal("200.00"))

    def _scaffold(self, client):
        """خدمةُ زبونٍ وشغلةٌ للفترة — سندُ الالتزام الإلزاميّ."""
        service = OfficeService.objects.filter(tenant=self.tenant).first()
        if service is None:
            service = OfficeService.objects.create(
                tenant=self.tenant, code="bookkeeping", name="مسك دفاتر",
            )
        client_service = ClientService.objects.create(
            client=client, service=service,
            starts_on=datetime.date(2026, 1, 1),
            responsible_from=datetime.date(2026, 1, 1),
        )
        task = PeriodTask.objects.create(
            tenant=self.tenant, client=client, client_service=client_service,
            period_start=datetime.date(2026, 3, 1),
            period_end=datetime.date(2026, 3, 31),
            internal_deadline=datetime.date(2026, 4, 10),
        )
        return client_service, task

    def _obligation(self, client, client_service, task, amount, *, client_paid):
        rule = OfficeCustomRule.objects.create(
            tenant=self.tenant, name=f"قاعدة {amount}", service=client_service.service,
            cadence="monthly", rule_kind="end_of_period",
        )
        return Obligation.objects.create(
            tenant=self.tenant,
            client=client,
            client_service=client_service,
            task=task,
            custom_rule=rule,
            rule_code=rule.code,
            name="ضريبة القيمة المضافة",
            origin="office",
            period_start=datetime.date(2026, 3, 1),
            period_end=datetime.date(2026, 3, 31),
            legal_date=datetime.date(2026, 4, 15),
            official_date=datetime.date(2026, 4, 15),
            actual_deadline=datetime.date(2026, 4, 15),
            internal_deadline=datetime.date(2026, 4, 10),
            amount=Decimal(amount),
            client_paid=client_paid,
        )
