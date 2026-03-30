import os
import django
import sys
import datetime

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from accounting.models import JournalLine
from django.db.models import Sum

print("--- DEBUG TRIAL BALANCE ---")
try:
    start_date = "2020-01-01"
    end_date = "2030-12-31"
    
    filters = {
        'journal__transaction_date__range': [start_date, end_date],
        #'journal__is_posted': True 
    }
    
    # Replicate View Query exactly
    qs = JournalLine.objects.filter(**filters).values(
        'account__id', 'account__code', 'account__name'
    ).annotate(
        total_debit=Sum('debit'),
        total_credit=Sum('credit')
    ).order_by('account__code')
    
    print(f"Query generated. Count: {qs.count()}")
    
    for entry in qs:
        print(f" - {entry['account__name']}: {entry['total_debit']} / {entry['total_credit']}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("--- END ---")
