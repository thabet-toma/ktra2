import os
import django
import sys

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ktra_erp.settings') # Verify settings module name

try:
    django.setup()
    from django.urls import resolve, reverse
    print("Django setup success.")
    
    # Try to import the accounting urls specifically
    import accounting.urls
    print("Accounting URLs imported successfully.")
    
    # Try to resolve the new endpoint
    try:
        match = resolve('/api/accounting/trial-balance/')
        print(f"Resolved /api/accounting/trial-balance/ to: {match.func.__name__} (Class: {match.func.cls.__name__})")
    except Exception as e:
        print(f"Resolution Failed: {e}")
        # Try without api prefix if that's how it's mounted
        try:
             # Assuming purely the app router part
             print("Trying to inspect router urls from accounting.urls...")
             print(accounting.urls.router.urls)
        except:
             pass

except Exception as e:
    print("CRITICAL ERROR during setup/import:")
    print(e)
    import traceback
    traceback.print_exc()
