"""إشعارُ القبض وكشفُ الحساب — رابطُهما وطباعتُهما (#283، الجزء ب).

**القواعدُ التي يسقط عندها الاختبار:**

1. **رقمُ الإشعار لا يُولَّد مرّةً ثانية عند العرض**: الطباعةُ تقرأ
   `FeePayment.receipt_number` المخزَّن، وتكرارُها لا يزيد `FeeReceiptSequence`.
2. **الترقيمُ متتابعٌ بلا فجوةٍ على سنتين** (`{year}-{n:05d}` من العدّاد المقفول).
3. **كشفُ الحساب**: الرصيدُ الجاري = مجموعُ الحركات، والختاميُّ = «اللي عليه» من
   الدالّة الواحدة (`payments.client_due`) حين تغطّي الفترةُ كلَّ الحركات.
4. **الدفعةُ تُقترح مرّةً واحدة** في «جاهز للإرسال» ثم لا تعود بعد تعليمها.
5. **العزل**: دفعةٌ أو زبونٌ من مكتبٍ آخر **404** لا 403.
6. **ولا حذفَ لدفعةٍ ولا شطب**: لا نقطةَ `DELETE` ولا مسارَ تفصيل.
7. **التواريخُ تُشتقّ من `timezone.localdate()`** لا من ساعة الحائط.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accounting_office import payments, services
from accounting_office.models import (
    FeeDraft,
    FeePayment,
    FeeReceiptSequence,
    FeeStatement,
    OfficeClient,
    TaxCard,
)
from core.modules import invalidate_module_cache
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company

BASE = "/api/accounting-office/"
PAYMENTS = f"{BASE}fees/payments/"
LEDGER = f"{BASE}fees/ledger/"
READY = f"{BASE}ready-to-send/"

TODAY = None  # يُضبط في `setUp` من `timezone.localdate()`


def money(value) -> Decimal:
    """المبلغُ كما يصل من الـAPI — نصٌّ بخانتين أو `None` تحت القناع."""
    return None if value is None else Decimal(str(value))


class FeeDocumentsTestCase(APITestCase):
    """مكتبٌ كاملٌ: المالكُ يرى ويخصّص، ومحاسبٌ بلا «يرى المبالغ»، ومكتبٌ آخر."""

    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True},
        )
        cls.owner = User.objects.create_user(username="feedoc_owner", password="x")
        cls.tenant = create_company(
            "مكتب مستندات الأتعاب", cls.owner, template="accounting_office",
        )
        invalidate_module_cache(cls.tenant.pk)
        services.set_office_setting(cls.tenant, "tax_system", "PS")
        services.set_office_setting(cls.tenant, "office_size", "small")
        # يومُ راحةٍ لا يحجب اقتراح اليوم — الاختبارُ يُشتقّ من يوم القراءة.
        services.set_office_setting(cls.tenant, "rest_days", [])

        cls.accountant = User.objects.create_user(username="feedoc_acc", password="x")
        UserCompanyMembership.objects.create(
            user=cls.accountant, tenant=cls.tenant, role="accountant",
        )
        cls.viewer = User.objects.create_user(username="feedoc_viewer", password="x")
        UserCompanyMembership.objects.create(
            user=cls.viewer, tenant=cls.tenant, role="viewer",
        )

        cls.other_owner = User.objects.create_user(username="feedoc_other", password="x")
        cls.other_tenant = create_company(
            "مكتب آخر للأتعاب", cls.other_owner, template="accounting_office",
        )
        invalidate_module_cache(cls.other_tenant.pk)
        services.set_office_setting(cls.other_tenant, "tax_system", "PS")

    def setUp(self):
        global TODAY
        TODAY = timezone.localdate()
        self.client.force_authenticate(user=self.owner)

    # ── أدواتٌ مشتركة ────────────────────────────────────────────────────
    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def make_client(self, name="زبون المستندات", *, tenant=None, responsible=None):
        client = OfficeClient.objects.create(
            tenant=tenant or self.tenant, name=name, responsible=responsible,
        )
        TaxCard.objects.create(client=client)
        return client

    def make_draft(self, client, total, *, year=2026, month=3, status="approved"):
        return FeeDraft.objects.create(
            tenant=client.tenant,
            client=client,
            year=year,
            month=month,
            subtotal=Decimal(str(total)),
            total=Decimal(str(total)),
            status=status,
            approved_by=self.owner if status == "approved" else None,
        )

    def pay(self, client, amount, *, paid_at=None, method="cash", tenant=None):
        res = self.client.post(
            PAYMENTS,
            {
                "client": client.pk,
                "amount": amount,
                "method": method,
                "paid_at": (paid_at or TODAY).isoformat(),
            },
            format="json",
            **self.headers(tenant),
        )
        self.assertEqual(res.status_code, 201, res.content)
        return FeePayment.objects.get(pk=res.data["id"])

    def make_contact(self, client, name="جهة الزبون"):
        contact = services.create_contact(
            self.tenant, name=name, phone="0599000000", language="ar",
        )
        services.link_client_contact(client=client, contact=contact, is_primary=True)
        return contact


# ── ١ و٢: الترقيم والإشعار ───────────────────────────────────────────────────
class ReceiptNumberGapTest(FeeDocumentsTestCase):
    def test_two_years_run_in_sequence_without_a_gap_and_without_a_second_number(self):
        client = self.make_client()
        first = self.pay(client, "10.00", paid_at=datetime.date(2026, 3, 1))
        second = self.pay(client, "10.00", paid_at=datetime.date(2026, 12, 31))
        # السنةُ الثانية تُفتح برقمها الأوّل — والعدّادُ لكل سنةٍ صفٌّ مستقلّ.
        FeeReceiptSequence.objects.create(
            tenant=self.tenant, year=2025, last_number=0,
        )
        before = {
            row.year: row.last_number
            for row in FeeReceiptSequence.objects.filter(tenant=self.tenant)
        }

        print_res = self.client.get(
            f"{PAYMENTS}{second.pk}/print/", **self.headers(),
        )

        self.assertEqual(print_res.status_code, 200, print_res.content[:300])
        self.assertEqual(print_res.data["number"], "2026-00002")
        self.assertEqual((first.receipt_number, second.receipt_number), ("2026-00001", "2026-00002"))
        after = {
            row.year: row.last_number
            for row in FeeReceiptSequence.objects.filter(tenant=self.tenant)
        }
        self.assertEqual(after, before, "الطباعةُ استهلكت رقماً — والرقمُ يُولَّد عند الدفع وحده")

    def test_repeating_the_print_returns_the_same_stored_number(self):
        client = self.make_client()
        payment = self.pay(client, "25.00")

        numbers = {
            self.client.get(f"{PAYMENTS}{payment.pk}/print/", **self.headers()).data["number"]
            for _ in range(3)
        }

        self.assertEqual(numbers, {payment.receipt_number})


class ReceiptPayloadTest(FeeDocumentsTestCase):
    def test_the_receipt_carries_the_client_the_amount_the_method_and_the_allocations(self):
        client = self.make_client("زبون الإشعار")
        draft = self.make_draft(client, "300.00", year=2026, month=3)
        payment = self.pay(client, "120.00", method="cheque")

        row = self.client.get(f"{PAYMENTS}{payment.pk}/print/", **self.headers()).data

        self.assertEqual(row["title"], "إشعار قبض")
        self.assertEqual(row["number"], payment.receipt_number)
        self.assertEqual(row["date"], payment.paid_at.isoformat())
        self.assertEqual(row["client"]["name"], "زبون الإشعار")
        self.assertEqual(money(row["amount"]), Decimal("120.00"))
        self.assertEqual(row["method"], "cheque")
        self.assertEqual(row["method_label"], "شيك")
        self.assertEqual(
            [(line["draft"], money(line["amount"])) for line in row["allocations"]],
            [(draft.pk, Decimal("120.00"))],
        )
        # «اللي عليه» من الدالّة الواحدة لا حساباً ثانياً.
        due = payments.client_due(self.tenant, client)
        self.assertEqual(money(row["due"]), due.due)
        self.assertEqual(money(row["credit"]), due.credit)
        self.assertEqual(due.due, Decimal("180.00"))

    def test_a_cheque_payment_reads_its_cheque_from_the_books(self):
        """«والشيك إن وُجد»: `FeePayment` لا يحمل حقولَ شيك، والورقةُ تُقرأ من دفاتره.

        الورقةُ تُنشَأ هنا بـ`accounting.api.ensure_incoming_cheque` — المسارُ
        الوحيد لإنشاء شيكٍ من خارج `accounting` — بمفتاح `(الشركة، رقم الإشعار)`
        نفسه الذي يكتبه `office_journal.post_payment_journal`.
        """
        from accounting.api import ensure_incoming_cheque

        client = self.make_client()
        self.make_draft(client, "300.00", year=2026, month=3)
        payment = self.pay(client, "120.00", method="cheque")
        ensure_incoming_cheque(
            tenant=self.tenant,
            cheque_number=payment.receipt_number,
            amount=payment.amount,
            user=self.owner,
        )

        row = self.client.get(f"{PAYMENTS}{payment.pk}/print/", **self.headers()).data

        self.assertEqual(row["cheque"]["number"], payment.receipt_number)
        self.assertIsNone(row["cheque"]["due_date"])
        cash = self.pay(client, "10.00", method="cash")
        cash_row = self.client.get(f"{PAYMENTS}{cash.pk}/print/", **self.headers()).data
        self.assertIsNone(cash_row["cheque"], "دفعةٌ نقديّةٌ لا سطرَ شيكٍ لها")

    def test_a_member_without_the_amounts_key_reads_no_money_on_the_receipt(self):
        client = self.make_client(responsible=self.accountant)
        self.make_draft(client, "300.00", year=2026, month=3)
        payment = self.pay(client, "120.00")

        self.client.force_authenticate(user=self.accountant)
        row = self.client.get(f"{PAYMENTS}{payment.pk}/print/", **self.headers()).data

        self.assertEqual(row["number"], payment.receipt_number)
        self.assertIsNone(row["amount"])
        self.assertIsNone(row["due"])
        self.assertIsNone(row["allocations"][0]["amount"])

    def test_print_and_share_need_the_write_key(self):
        client = self.make_client(responsible=self.viewer)
        payment = self.pay(client, "10.00")

        self.client.force_authenticate(user=self.viewer)

        print_res = self.client.get(f"{PAYMENTS}{payment.pk}/print/", **self.headers())
        share_res = self.client.post(
            f"{PAYMENTS}{payment.pk}/share/", {}, format="json", **self.headers(),
        )

        self.assertEqual(print_res.status_code, 403, print_res.content[:300])
        self.assertEqual(share_res.status_code, 403, share_res.content[:300])


class ReceiptShareTest(FeeDocumentsTestCase):
    def test_sharing_returns_a_live_url_and_an_expiry_and_the_page_carries_the_number(self):
        client = self.make_client("زبون المشاركة")
        self.make_draft(client, "300.00", year=2026, month=3)
        payment = self.pay(client, "100.00")

        res = self.client.post(
            f"{PAYMENTS}{payment.pk}/share/", {}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content[:300])
        self.assertTrue(res.data["url"])
        self.assertTrue(res.data["expires_at"])

        token = res.data["url"].rsplit("/", 1)[-1]
        page = self.client.get(f"/s/{token}")
        self.assertEqual(page.status_code, 200, page.content[:400])
        html = page.content.decode("utf-8")
        self.assertIn(payment.receipt_number, html)
        self.assertIn("إشعار قبض", html)
        self.assertIn("زبون المشاركة", html)

    def test_a_second_share_reuses_the_live_link(self):
        client = self.make_client()
        payment = self.pay(client, "10.00")

        first = self.client.post(
            f"{PAYMENTS}{payment.pk}/share/", {}, format="json", **self.headers(),
        )
        second = self.client.post(
            f"{PAYMENTS}{payment.pk}/share/", {}, format="json", **self.headers(),
        )

        self.assertEqual(first.data["url"], second.data["url"])


# ── ٣: كشفُ الحساب ──────────────────────────────────────────────────────────
class StatementTest(FeeDocumentsTestCase):
    def build_history(self, client):
        """فاتورة ٣٠٠ (آذار) · دفعة ١٢٠ (نيسان) · شطب ٥٠ — والرصيد ١٣٠."""
        draft = self.make_draft(client, "300.00", year=2026, month=3)
        payment = self.pay(client, "120.00", paid_at=datetime.date(2026, 4, 10))
        self.client.post(
            f"{BASE}fees/drafts/{draft.pk}/write-off/",
            {"amount": "50.00", "reason": "تنازل"},
            format="json",
            **self.headers(),
        )
        return draft, payment

    def statement(self, client, **params):
        res = self.client.get(
            f"{LEDGER}print/", {"client": client.pk, **params}, **self.headers(),
        )
        self.assertEqual(res.status_code, 200, res.content[:400])
        return res.data

    def test_the_running_balance_is_the_sum_of_movements_and_the_closing_is_the_due(self):
        client = self.make_client()
        self.build_history(client)

        row = self.statement(client, **{"period_to": TODAY.isoformat()})

        running = Decimal(row["opening_balance"])
        for movement in row["rows"]:
            running += money(movement["amount"])
            self.assertEqual(money(movement["balance"]), running)
        self.assertEqual(money(row["rows"][-1]["balance"]), money(row["closing_balance"]))
        # الرصيدُ الختاميُّ هو «اللي عليه» من الدالّة الواحدة — لا حساباً ثانياً.
        self.assertEqual(money(row["closing_balance"]), payments.client_due(self.tenant, client).due)
        self.assertEqual(money(row["due"]), Decimal("130.00"))
        self.assertEqual(money(row["totals"]["invoices"]), Decimal("300.00"))
        self.assertEqual(money(row["totals"]["payments"]), Decimal("120.00"))
        self.assertEqual(money(row["totals"]["write_offs"]), Decimal("50.00"))

    def test_the_three_groups_are_read_from_the_ledger_rows_themselves(self):
        client = self.make_client()
        draft, payment = self.build_history(client)

        row = self.statement(client, **{"period_to": TODAY.isoformat()})

        self.assertEqual([item["id"] for item in row["groups"]["invoices"]], [draft.pk])
        self.assertEqual([item["id"] for item in row["groups"]["payments"]], [payment.pk])
        self.assertEqual(len(row["groups"]["write_offs"]), 1)
        self.assertEqual(
            money(row["groups"]["invoices"][0]["remaining"]), Decimal("130.00"),
        )

    def test_the_period_scopes_the_rows_and_carries_what_came_before_it(self):
        client = self.make_client()
        self.build_history(client)

        row = self.statement(
            client, **{"period_from": "2026-04-01", "period_to": TODAY.isoformat()},
        )

        # الفاتورةُ (آذار) قبل الفترة: رصيدٌ افتتاحيٌّ لا صفّاً.
        self.assertEqual(money(row["opening_balance"]), Decimal("300.00"))
        self.assertEqual(
            [movement["kind"] for movement in row["rows"]], ["payment", "write_off"],
        )
        self.assertEqual(money(row["closing_balance"]), Decimal("130.00"))

    def test_a_foreign_client_is_404(self):
        foreign = self.make_client("زبون مكتب آخر", tenant=self.other_tenant)

        res = self.client.get(
            f"{LEDGER}print/", {"client": foreign.pk}, **self.headers(),
        )

        self.assertEqual(res.status_code, 404, res.content[:300])

    def test_a_member_without_the_amounts_key_reads_no_money_in_the_statement(self):
        client = self.make_client(responsible=self.accountant)
        self.build_history(client)

        self.client.force_authenticate(user=self.accountant)
        row = self.statement(client, **{"period_to": TODAY.isoformat()})

        self.assertIsNone(row["opening_balance"])
        self.assertIsNone(row["closing_balance"])
        self.assertIsNone(row["due"])
        self.assertIsNone(row["rows"][0]["amount"])
        self.assertIsNone(row["rows"][0]["balance"])


class StatementShareTest(FeeDocumentsTestCase):
    def test_sharing_records_one_statement_row_and_returns_a_live_url(self):
        client = self.make_client("زبون الكشف")
        self.make_draft(client, "300.00", year=2026, month=3)
        self.pay(client, "100.00", paid_at=datetime.date(2026, 4, 10))

        res = self.client.post(
            f"{LEDGER}share/",
            {"client": client.pk, "from": "2026-01-01", "to": TODAY.isoformat()},
            format="json",
            **self.headers(),
        )

        self.assertEqual(res.status_code, 201, res.content[:400])
        self.assertTrue(res.data["url"])
        self.assertTrue(res.data["expires_at"])
        statement = FeeStatement.objects.get(tenant=self.tenant)
        self.assertEqual(statement.client_id, client.pk)
        self.assertEqual(statement.period_from, datetime.date(2026, 1, 1))
        self.assertEqual(statement.period_to, TODAY)

        token = res.data["url"].rsplit("/", 1)[-1]
        page = self.client.get(f"/s/{token}")
        self.assertEqual(page.status_code, 200, page.content[:400])
        html = page.content.decode("utf-8")
        self.assertIn("كشف حساب", html)
        self.assertIn("زبون الكشف", html)
        self.assertIn("200", html)  # المتبقّي بعد الدفعة

    def test_a_foreign_client_is_404_and_nothing_is_written(self):
        foreign = self.make_client("زبون مكتب آخر", tenant=self.other_tenant)

        res = self.client.post(
            f"{LEDGER}share/", {"client": foreign.pk}, format="json", **self.headers(),
        )

        self.assertEqual(res.status_code, 404, res.content[:300])
        self.assertEqual(FeeStatement.objects.count(), 0)


# ── ٤: «جاهز للإرسال» ───────────────────────────────────────────────────────
class ReceiptSuggestionTest(FeeDocumentsTestCase):
    def suggestions(self, day=None):
        payload = services.ready_to_send_payload(
            self.tenant, user=self.owner, day=day or TODAY,
        )
        return [
            item
            for message in payload["messages"]
            for item in message["items"]
            if item["reminder_type"] == "fee_receipt"
        ]

    def test_a_todays_payment_is_suggested_once_then_gone_after_marking_it_sent(self):
        client = self.make_client()
        contact = self.make_contact(client)
        payment = self.pay(client, "150.00")
        self.make_draft(client, "400.00", year=2026, month=3)

        items = self.suggestions()

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["client_id"], client.pk)
        self.assertEqual(item["period_start"], payment.paid_at.isoformat())
        self.assertEqual(item["period_end"], payment.paid_at.isoformat())

        body = next(
            message["body"]
            for message in services.ready_to_send_payload(
                self.tenant, user=self.owner, day=TODAY,
            )["messages"]
            if any(row["reminder_type"] == "fee_receipt" for row in message["items"])
        )
        self.assertIn(payment.receipt_number, body)
        self.assertIn("150.00", body)
        # الباقي بعد الدفعة: 400 − 150.
        self.assertIn("250.00", body)

        res = self.client.post(
            f"{READY}sent/",
            {
                "contact_id": contact.pk,
                "body": body,
                "items": [{
                    "client_id": item["client_id"],
                    "reminder_type": item["reminder_type"],
                    "period_start": item["period_start"],
                    "period_end": item["period_end"],
                }],
            },
            format="json",
            **self.headers(),
        )
        self.assertEqual(res.status_code, 201, res.content[:400])

        self.assertEqual(self.suggestions(), [])

    def test_each_payment_gets_its_own_item_key(self):
        first = self.make_client("زبون أول")
        second = self.make_client("زبون ثانٍ")
        self.make_contact(first)
        self.make_contact(second)
        self.pay(first, "60.00")
        self.pay(second, "70.00")

        items = self.suggestions()
        keys = {
            (item["client_id"], item["reminder_type"], item["period_start"], item["period_end"])
            for item in items
        }

        self.assertEqual(len(items), 2)
        self.assertEqual(len(keys), 2, "مفتاحُ بندٍ لكل دفعة — لا مفتاحَ مشترك")

    def test_a_payment_from_another_day_is_not_suggested(self):
        client = self.make_client()
        self.make_contact(client)
        self.pay(client, "150.00", paid_at=TODAY - datetime.timedelta(days=1))

        self.assertEqual(self.suggestions(), [])


# ── ٥ و٦: العزل ولا حذف ─────────────────────────────────────────────────────
class IsolationAndNoDeleteTest(FeeDocumentsTestCase):
    def test_a_payment_of_another_office_is_404_on_print_and_share(self):
        foreign = self.make_client("زبون المكتب الآخر", tenant=self.other_tenant)

        self.client.force_authenticate(user=self.other_owner)
        payment = FeePayment.objects.create(
            tenant=self.other_tenant,
            client=foreign,
            method="cash",
            amount=Decimal("40.00"),
            paid_at=TODAY,
            receipt_number="2026-00001",
        )

        self.client.force_authenticate(user=self.owner)
        print_res = self.client.get(f"{PAYMENTS}{payment.pk}/print/", **self.headers())
        share_res = self.client.post(
            f"{PAYMENTS}{payment.pk}/share/", {}, format="json", **self.headers(),
        )

        self.assertEqual(print_res.status_code, 404, print_res.content[:300])
        self.assertEqual(share_res.status_code, 404, share_res.content[:300])

    def test_no_delete_and_no_receipt_for_a_payment_or_a_statement(self):
        client = self.make_client()
        payment = self.pay(client, "10.00")

        detail = f"{PAYMENTS}{payment.pk}/"
        self.assertEqual(self.client.get(detail, **self.headers()).status_code, 404)
        self.assertEqual(self.client.delete(detail, **self.headers()).status_code, 404)
        self.assertEqual(
            self.client.delete(f"{LEDGER}print/", **self.headers()).status_code, 405,
        )
        self.assertEqual(
            self.client.delete(f"{LEDGER}share/", **self.headers()).status_code, 405,
        )
