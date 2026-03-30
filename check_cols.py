import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def describe_table(table_name):
    print(f"--- Columns for {table_name} ---")
    with connection.cursor() as cursor:
        cursor.execute(f"DESCRIBE {table_name}")
        for row in cursor.fetchall():
            print(row)

if __name__ == "__main__":
    try:
        describe_table('partners')
        describe_table('products')
    except Exception as e:
        print(f"Error: {e}")
