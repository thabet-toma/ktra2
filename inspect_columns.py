import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def describe_table():
    with connection.cursor() as cursor:
        try:
            print("--- DESCRIBING TABLE partners ---")
            cursor.execute("DESCRIBE partners")
            rows = cursor.fetchall()
            for row in rows:
                print(row)
            
            print("\n--- DESCRIBING TABLE tenants ---")
            cursor.execute("DESCRIBE tenants")
            rows = cursor.fetchall()
            for row in rows:
                print(row)
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    describe_table()
