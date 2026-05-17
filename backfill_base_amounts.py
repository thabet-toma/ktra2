"""
Backfill base_debit / base_credit for existing JournalLine records.

Usage:
  cd c:\\Users\\asus\\Desktop\\ktra
  python manage.py shell < backfill_base_amounts.py

This script reads the exchange_rate from each JournalHeader and updates
all its JournalLine rows with:
  base_debit  = debit  × exchange_rate
  base_credit = credit × exchange_rate

Records where exchange_rate is NULL or 1.0 will have base == original,
so no harm done.
"""
import os, sys, django

# Ensure Django settings are loaded
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
# Add project root to sys.path if needed
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
django.setup()

from decimal import Decimal
from accounting.models import JournalHeader, JournalLine

DEC = Decimal('0.01')

headers = JournalHeader.objects.all().only('id', 'exchange_rate')
total_headers = headers.count()
print(f"[Backfill] Found {total_headers} JournalHeader records to process.")

updated_count = 0
batch_size = 500

for i, hdr in enumerate(headers.iterator(chunk_size=200), 1):
    rate = Decimal(str(hdr.exchange_rate or 1))
    if rate <= 0:
        rate = Decimal('1')

    lines = JournalLine.objects.filter(journal_id=hdr.id)
    to_update = []
    for line in lines:
        new_base_debit = (Decimal(str(line.debit or 0)) * rate).quantize(DEC)
        new_base_credit = (Decimal(str(line.credit or 0)) * rate).quantize(DEC)
        if line.base_debit != new_base_debit or line.base_credit != new_base_credit:
            line.base_debit = new_base_debit
            line.base_credit = new_base_credit
            to_update.append(line)

    if to_update:
        JournalLine.objects.bulk_update(to_update, ['base_debit', 'base_credit'], batch_size=batch_size)
        updated_count += len(to_update)

    if i % 100 == 0 or i == total_headers:
        print(f"  [{i}/{total_headers}] headers processed, {updated_count} lines updated so far.")

print(f"\n[Backfill] DONE. Total lines updated: {updated_count}")
