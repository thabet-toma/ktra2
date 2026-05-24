from django.db import migrations
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


def backfill_pi_payments(apps, schema_editor):
    PurchaseInvoice = apps.get_model('logistics', 'PurchaseInvoice')
    PurchaseInvoicePayment = apps.get_model('logistics', 'PurchaseInvoicePayment')
    Currency = apps.get_model('tenants', 'Currency')
    Account = apps.get_model('accounting', 'Account')

    count = 0
    for pi in PurchaseInvoice.objects.iterator():
        if pi.payments.exists():
            continue
        raw = pi.local_payments_json
        if not raw:
            continue
        payments_list = raw if isinstance(raw, list) else [raw]
        ilses = Currency.objects.filter(Code__iexact='ILS')
        ils = ilses.first() if ilses.exists() else None
        for item in payments_list:
            if not isinstance(item, dict):
                continue
            try:
                amt = Decimal(str(item.get('amount', 0) or 0))
            except (ValueError, TypeError):
                amt = Decimal('0')
            if amt <= 0:
                continue
            currency = None
            cur_id = item.get('currency')
            if cur_id:
                try:
                    currency = Currency.objects.get(pk=int(cur_id))
                except Exception:
                    currency = ils
            else:
                currency = ils
            account = None
            acct_id = item.get('account') or item.get('cash_or_bank_account')
            if acct_id:
                try:
                    account = Account.objects.get(pk=int(acct_id))
                except Exception:
                    pass
            method = str(item.get('method') or item.get('payment_method') or 'bank_transfer')
            ref = str(item.get('reference') or item.get('reference_number') or '')
            pdate = item.get('date') or item.get('payment_date') or pi.invoice_date
            PurchaseInvoicePayment.objects.create(
                tenant=pi.tenant,
                invoice=pi,
                payment_date=pdate,
                amount=amt,
                currency=currency or ils,
                exchange_rate=Decimal(str(item.get('exchange_rate', 1) or 1)),
                payment_method=method,
                cash_or_bank_account=account,
                reference_number=ref,
                notes=str(item.get('notes', '') or ''),
            )
            count += 1
    if count:
        logger.info("Backfilled %d PI payments from local_payments_json", count)


def reverse_backfill(apps, schema_editor):
    PurchaseInvoicePayment = apps.get_model('logistics', 'PurchaseInvoicePayment')
    PurchaseInvoicePayment.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('logistics', '0033_pi_payment_model'),
    ]
    operations = [
        migrations.RunPython(backfill_pi_payments, reverse_backfill),
    ]
