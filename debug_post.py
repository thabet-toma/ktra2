import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ktra_erp.settings')
django.setup()

from accounting.models import JournalHeader
from accounting.services import post_journal_entry

try:
    # Get the latest journal
    latest_journal = JournalHeader.objects.last()
    if not latest_journal:
        print("No journals found.")
        exit()

    print(f"Latest Journal ID: {latest_journal.id}")
    print(f"Current Status: {'Posted' if latest_journal.is_posted else 'Draft'}")
    print(f"Transaction Date: {latest_journal.transaction_date}")

    if latest_journal.is_posted:
        print("Journal is already posted.")
    else:
        print("Attempting to post...")
        try:
            post_journal_entry(latest_journal.id, user=None)
            print("SUCCESS: Journal posted successfully.")
        except Exception as e:
            print(f"FAILURE: Could not post. Error: {e}")
            import traceback
            traceback.print_exc()

except Exception as e:
    print(f"Script Error: {e}")
