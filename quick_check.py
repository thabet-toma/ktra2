import os
import django
import sys
from django.db import connection

# Set up Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def check():
    with connection.cursor() as cursor:
        cursor.execute("DESCRIBE logistics_deals")
        cols = [row[0] for row in cursor.fetchall()]
        print("DEALS:", cols)
        
        cursor.execute("DESCRIBE logistics_expenses")
        cols_exp = [row[0] for row in cursor.fetchall()]
        print("EXPENSES:", cols_exp)

if __name__ == "__main__":
    check()
