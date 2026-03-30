import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def check():
    print("CHECKING TABLE chartofaccounts")
    with connection.cursor() as cursor:
        try:
            cursor.execute("SELECT COUNT(*) FROM chartofaccounts")
            count = cursor.fetchone()[0]
            print(f"COUNT: {count}")
            
            cursor.execute("SELECT * FROM chartofaccounts LIMIT 5")
            rows = cursor.fetchall()
            for row in rows:
                print(f"ROW: {row}")
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    check()
