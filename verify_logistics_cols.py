import os
import django
import sys
from django.db import connection

# Set up Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def verify_columns():
    tables = ['logistics_deals', 'logistics_expenses']
    required_cols = ['IsPosted', 'JournalID']
    all_ok = True

    with connection.cursor() as cursor:
        for table in tables:
            print(f"Checking table: {table}")
            cursor.execute(f"DESCRIBE {table}")
            existing_cols = [row[0] for row in cursor.fetchall()]
            
            for col in required_cols:
                if col in existing_cols:
                    print(f"  [OK] Column '{col}' exists.")
                else:
                    print(f"  [FAIL] Column '{col}' is MISSING!")
                    all_ok = False
            print("-" * 20)
    
    return all_ok

if __name__ == "__main__":
    try:
        success = verify_columns()
        if success:
            print("\nVERIFICATION SUCCESSFUL: All required columns are present.")
            sys.exit(0)
        else:
            print("\nVERIFICATION FAILED: Some columns are still missing.")
            sys.exit(1)
    except Exception as e:
        print(f"\nERROR during verification: {e}")
        sys.exit(1)
