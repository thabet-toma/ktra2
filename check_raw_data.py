import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def check_raw():
    with connection.cursor() as cursor:
        cursor.execute("SELECT CategoryID, Name, ParentID FROM product_categories")
        rows = cursor.fetchall()
        print(f"Categories found: {len(rows)}")
        for row in rows:
            print(f"ID: {row[0]}, Name: {row[1]}, ParentID: {row[2]}")

if __name__ == "__main__":
    check_raw()
