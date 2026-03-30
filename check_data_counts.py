import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def check_data():
    with connection.cursor() as cursor:
        tables = ['tenants', 'partners', 'partner_groups', 'chartofaccounts', 'products', 'categories']
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"Table '{table}': {count} records")
            except Exception as e:
                print(f"Table '{table}': ERROR ({e})")

if __name__ == "__main__":
    check_data()
