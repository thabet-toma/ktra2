"""
Backfill currency and exchange_rate on existing JournalHeader rows.

- Journals without currency are set to ILS (base currency) with rate=1.
- Journals linked to logistics payments (LOGISTICS_PAYMENT) are checked:
  if the payment's deal currency is foreign, the journal is flagged for
  manual review (may have been posted in foreign currency without conversion).

Usage:
  python manage.py backfill_journal_currency          # dry run
  python manage.py backfill_journal_currency --apply  # actually update
"""
import logging
from django.core.management.base import BaseCommand
from accounting.models import JournalHeader
from tenants.models import Currency

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Backfill currency=ILS on journals missing currency; flag foreign-currency anomalies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually apply changes (default is dry-run).",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        base = Currency.objects.filter(IsBaseCurrency=True).first()
        if not base:
            self.stderr.write("No base currency found (IsBaseCurrency=True). Aborting.")
            return

        self.stdout.write(f"Base currency: {base.Code} (ID={base.pk})")

        missing = JournalHeader.objects.filter(currency__isnull=True)
        count_missing = missing.count()
        self.stdout.write(f"Journals without currency: {count_missing}")

        if apply and count_missing:
            updated = missing.update(currency=base, exchange_rate=1)
            self.stdout.write(self.style.SUCCESS(f"Updated {updated} journals to {base.Code} / rate=1"))
        elif count_missing:
            self.stdout.write("(dry run — pass --apply to update)")

        from logistics.models import LogisticsPayment
        payment_journals = JournalHeader.objects.filter(
            reference_type="LOGISTICS_PAYMENT",
            reference_id__isnull=False,
        )
        flagged = 0
        for jh in payment_journals.iterator():
            pay = (
                LogisticsPayment.objects
                .select_related("deal", "deal__currency")
                .filter(pk=jh.reference_id)
                .first()
            )
            if not pay or not pay.deal:
                continue
            deal_cur = pay.deal.currency
            if deal_cur and deal_cur.pk != base.pk:
                rate = pay.usd_to_ils or pay.deal.currency_rate or 1
                expected_local = float(pay.amount) * float(rate)
                lines_total = sum(
                    float(l.debit) for l in jh.lines.all()
                )
                if abs(lines_total - expected_local) > 1.0:
                    flagged += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ANOMALY: Journal #{jh.id} | payment #{pay.id} "
                            f"| deal currency={deal_cur.Code} "
                            f"| payment amount={pay.amount} "
                            f"| rate={rate} "
                            f"| expected ILS={expected_local:.2f} "
                            f"| actual debit total={lines_total:.2f}"
                        )
                    )

        if flagged:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{flagged} journal(s) may have been posted in foreign currency "
                    f"without conversion. Review manually."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("No foreign-currency anomalies detected."))
