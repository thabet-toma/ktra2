
import os
import django
import sys

# Set up Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection

def check_table_columns(table_name):
    with connection.cursor() as cursor:
        cursor.execute(f"DESCRIBE {table_name}")
        columns = [row[0] for row in cursor.fetchall()]
        print(f"Columns in {table_name}: {columns}")
        return columns

if __name__ == "__main__":
    try:
        check_table_columns('logistics_deals')
    except Exception as e:
        print(f"Error: {e}")
