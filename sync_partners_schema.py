import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def sync_schema():
    sql_commands = [
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS ImageURL VARCHAR(512) NULL;",
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS ImagePublicID VARCHAR(255) NULL;",
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS DocumentURL VARCHAR(512) NULL;",
        "ALTER TABLE partners ADD COLUMN IF NOT EXISTS DocumentPublicID VARCHAR(255) NULL;"
    ]
    
    with connection.cursor() as cursor:
        for sql in sql_commands:
            try:
                print(f"Executing: {sql}")
                cursor.execute(sql)
                print("   ✓ Success")
            except Exception as e:
                print(f"   × Error: {e}")

if __name__ == "__main__":
    sync_schema()
