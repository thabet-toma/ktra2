"""
إعادة توجيه سطر «الصندوق» (دائن) في قيود الدفعات اللوجستية من حساب أصول عام خاطئ
إلى حساب صندوق الدولار (أو أي حساب مربوط بـ CashBoxLedgerAccount).

يشمل:
  - reference_type = LOGISTICS_PAYMENT (صفقة)
  - reference_type = LOGISTICS_CLEARANCE_PAYMENT (تخليص)

لا يمس قيوداً أخرى (مخزون، مصاريف شحن، يدوية…).

افتراضياً: يُعاد توجيه الأسطر التي **ليست** على أي حساب مربوط بصندوق آخر
(حتى لا ننقل دفعات كانت مقصودة على صندوق الشيكل مثلاً إلا إذا مرّرت --include-linked-cash).

بعد التحديث:
  - يتحقق من توازن كل قيد متأثر
  - يحدّث LogisticsPayment.bank_account للدفعات المرتبطة بنفس القيود

الاستخدام:
  python manage.py rewire_logistics_payment_cash_lines --tenant-id 1 --list-ledgers
  python manage.py rewire_logistics_payment_cash_lines --tenant-id 1 --to-external-id "<uuid_حقيقي_من_Firestore>" --dry-run
  python manage.py rewire_logistics_payment_cash_lines --tenant-id 1 --to-account-id 42 --dry-run

ملاحظة: «UUID_صندوق_الدولار» نص توضيحي فقط — المعرف يجب أن يطابق حقل ExternalID في جدول
cash_box_ledger_accounts (نفس id مستند cashBoxes في Firestore).
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from accounting.cashbox import resolve_default_cash_box_account
from accounting.models import Account, CashBoxLedgerAccount, JournalHeader, JournalLine
from logistics.models import LogisticsPayment


PAYMENT_REF_TYPES = ("LOGISTICS_PAYMENT", "LOGISTICS_CLEARANCE_PAYMENT")


class Command(BaseCommand):
    help = "Rewire logistics payment journal credit (cash) lines to the dollar cash box GL account."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, default=1)
        parser.add_argument("--to-external-id", type=str, default="", help="CashBoxLedgerAccount.external_id (Firestore)")
        parser.add_argument("--to-account-id", type=int, default=None, help="GL AccountID of the cash box (optional)")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print plan only; no DB writes.",
        )
        parser.add_argument(
            "--include-linked-cash",
            action="store_true",
            help="Also rewire lines already on another CashBoxLedgerAccount (dangerous).",
        )
        parser.add_argument(
            "--use-resolver-default",
            action="store_true",
            help="Resolve target via resolve_default_cash_box_account (DEFAULT_CASH_BOX_EXTERNAL_ID / USD link).",
        )
        parser.add_argument(
            "--list-ledgers",
            action="store_true",
            help="Print all cash-box ↔ GL links for this tenant and exit (no rewire).",
        )

    def _print_ledgers(self, tenant):
        rows = (
            CashBoxLedgerAccount.objects.filter(tenant=tenant)
            .select_related("account")
            .order_by("id")
        )
        if not rows.exists():
            self.stdout.write(
                self.style.WARNING(
                    "لا يوجد أي ربط صندوق في المحاسبة. أنشئ الربط من الواجهة (قائمة الصناديق) "
                    "أو POST /api/accounting/cash-box-accounts/"
                )
            )
            return
        self.stdout.write(self.style.NOTICE("روابط الصناديق — انسخ ExternalID كما هو لـ --to-external-id:\n"))
        for r in rows:
            a = r.account
            self.stdout.write(
                f"  external_id={r.external_id!r}\n"
                f"    name={r.name!r}  currency={r.currency_code!r}\n"
                f"    GL AccountID={a.pk}  code={a.code!r}  name={a.name!r}\n"
            )

    def handle(self, *args, **opts):
        from tenants.models import Tenant

        tenant_id = opts["tenant_id"]
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if not tenant:
            self.stderr.write(self.style.ERROR(f"Tenant {tenant_id} not found."))
            return

        if opts.get("list_ledgers"):
            self._print_ledgers(tenant)
            return

        target: Account | None = None
        if opts["use_resolver_default"]:
            target = resolve_default_cash_box_account(tenant)
        elif opts["to_account_id"]:
            target = Account.objects.filter(pk=opts["to_account_id"], tenant=tenant).first()
        else:
            ext = (opts["to_external_id"] or "").strip()
            if not ext:
                self.stderr.write(
                    self.style.ERROR(
                        "Provide --to-external-id or --to-account-id or --use-resolver-default."
                    )
                )
                return
            link = CashBoxLedgerAccount.objects.filter(
                tenant=tenant, external_id=ext[:128]
            ).select_related("account").first()
            if not link:
                self.stderr.write(
                    self.style.ERROR(
                        f"لا يوجد ربط صندوق بهذا المعرف: external_id={ext!r}\n"
                        f"«UUID_صندوق_الدولار» مثال فقط — يجب لصق معرّف Firestore الحقيقي لمستند cashBoxes/…\n"
                    )
                )
                self.stdout.write("\n")
                self._print_ledgers(tenant)
                self.stdout.write(
                    "\nأو استخدم: --to-account-id <رقم_AccountID> أو --use-resolver-default (مع DEFAULT_CASH_BOX_EXTERNAL_ID في .env)\n"
                )
                return
            target = link.account

        if not target:
            self.stderr.write(self.style.ERROR("Could not resolve target cash GL account."))
            self._print_ledgers(tenant)
            return

        self.stdout.write(
            f"Target account: id={target.pk} code={target.code!r} name={target.name!r}"
        )

        cash_linked_ids = set(
            CashBoxLedgerAccount.objects.filter(tenant=tenant).values_list("account_id", flat=True)
        )

        qs = (
            JournalLine.objects.filter(
                tenant_id=tenant_id,
                journal__reference_type__in=PAYMENT_REF_TYPES,
                journal__is_posted=True,
                credit__gt=0,
                debit=0,
            )
            .exclude(account_id=target.pk)
            .select_related("journal", "account")
        )

        if not opts["include_linked_cash"]:
            qs = qs.exclude(account_id__in=cash_linked_ids)

        ids = list(qs.values_list("pk", flat=True))
        if not ids:
            self.stdout.write(self.style.WARNING("No journal lines matched filters."))
            return

        self.stdout.write(f"Matched {len(ids)} line(s).")

        journal_ids = sorted(set(qs.values_list("journal_id", flat=True)))
        for jid in journal_ids[:30]:
            self._preview_journal(jid)
        if len(journal_ids) > 30:
            self.stdout.write(f"... ({len(journal_ids)} journals total, preview first 30)")

        if opts["dry_run"]:
            self.stdout.write(self.style.NOTICE("Dry run — no changes."))
            return

        with transaction.atomic():
            updated = JournalLine.objects.filter(pk__in=ids).update(account_id=target.pk)
            self.stdout.write(self.style.SUCCESS(f"Updated {updated} journal line(s)."))

            pay_upd = LogisticsPayment.objects.filter(
                journal_id__in=journal_ids,
                is_posted=True,
            ).update(bank_account_id=target.pk)
            self.stdout.write(f"Synced LogisticsPayment.bank_account on {pay_upd} row(s).")

        for jid in journal_ids:
            self._assert_balanced(jid)

    def _preview_journal(self, journal_id):
        lines = JournalLine.objects.filter(journal_id=journal_id).select_related("account")
        parts = []
        for ln in lines:
            parts.append(
                f"{ln.account.code}:{ln.account.name} dr={ln.debit} cr={ln.credit}"
            )
        self.stdout.write(f"  Journal {journal_id}: " + " | ".join(parts))

    def _assert_balanced(self, journal_id):
        agg = JournalLine.objects.filter(journal_id=journal_id).aggregate(
            s_debit=Sum("debit"), s_credit=Sum("credit")
        )
        dr = agg["s_debit"] or Decimal("0")
        cr = agg["s_credit"] or Decimal("0")
        diff = dr - cr
        if abs(diff) > Decimal("0.02"):
            self.stderr.write(
                self.style.ERROR(
                    f"Journal {journal_id} UNBALANCED: debit={dr} credit={cr} diff={diff}"
                )
            )
        else:
            self.stdout.write(f"OK journal {journal_id} balanced.")
