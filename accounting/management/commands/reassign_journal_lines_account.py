"""
إعادة توجيه أسطر القيود من حساب خاطئ إلى حساب صندوق (أو أي حساب) مع التحقق من توازن كل قيد.

مثال (نقل كل الأسطر التي كانت على حساب أصول متداولة خاطئ إلى حساب صندوق الدولار المربوط بصندوق):

  python manage.py reassign_journal_lines_account \\
    --tenant-id 1 \\
    --from-account-id 12 \\
    --to-cash-box-external-id <firestore_cash_box_uuid> \\
    --dry-run

أو بمعرّف حساب صريح:

  python manage.py reassign_journal_lines_account \\
    --tenant-id 1 \\
    --from-account-id 12 \\
    --to-account-id 45
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from accounting.models import CashBoxLedgerAccount, JournalLine


class Command(BaseCommand):
    help = "Reassign journal lines from one GL account to another; verify each journal stays balanced."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, default=1)
        parser.add_argument("--from-account-id", type=int, required=True)
        parser.add_argument("--to-account-id", type=int, default=None)
        parser.add_argument("--to-cash-box-external-id", type=str, default="")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        tenant_id = opts["tenant_id"]
        from_id = opts["from_account_id"]
        to_id = opts["to_account_id"]
        ext = (opts["to_cash_box_external_id"] or "").strip()

        if to_id is None and not ext:
            self.stderr.write("Specify --to-account-id or --to-cash-box-external-id")
            return
        if to_id is not None and ext:
            self.stderr.write("Use only one of --to-account-id or --to-cash-box-external-id")
            return

        if ext:
            link = CashBoxLedgerAccount.objects.filter(
                tenant_id=tenant_id, external_id=ext[:128]
            ).first()
            if not link:
                self.stderr.write(f"No CashBoxLedgerAccount for tenant={tenant_id} external_id={ext!r}")
                return
            to_id = link.account_id

        lines = JournalLine.objects.filter(tenant_id=tenant_id, account_id=from_id).select_related(
            "journal"
        )
        count = lines.count()
        if count == 0:
            self.stdout.write(self.style.WARNING("No lines to update."))
            return

        journal_ids = sorted(set(lines.values_list("journal_id", flat=True)))
        self.stdout.write(f"Found {count} line(s) on account {from_id} in {len(journal_ids)} journal(s).")
        self.stdout.write(f"Target account id: {to_id}")

        if opts["dry_run"]:
            for jid in journal_ids[:50]:
                self._check_journal(jid)
            if len(journal_ids) > 50:
                self.stdout.write("... (dry-run: only first 50 journals balance-checked)")
            self.stdout.write(self.style.NOTICE("Dry run — no changes."))
            return

        with transaction.atomic():
            updated = lines.update(account_id=to_id)
            self.stdout.write(self.style.SUCCESS(f"Updated {updated} line(s)."))

        for jid in journal_ids:
            self._check_journal(jid)

    def _check_journal(self, journal_id):
        agg = JournalLine.objects.filter(journal_id=journal_id).aggregate(
            s_debit=Sum("debit"), s_credit=Sum("credit")
        )
        dr = agg["s_debit"] or Decimal("0")
        cr = agg["s_credit"] or Decimal("0")
        diff = dr - cr
        if abs(diff) > Decimal("0.02"):
            self.stderr.write(
                self.style.ERROR(f"Journal {journal_id} UNBALANCED after update: debit={dr} credit={cr}")
            )
        else:
            self.stdout.write(f"Journal {journal_id}: balanced (dr={dr}, cr={cr}).")
