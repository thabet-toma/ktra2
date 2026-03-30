import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def apply_sql():
    sql_commands = [
        "ALTER TABLE partners ADD COLUMN LinkedAccountID INT NULL;",
        "ALTER TABLE partners ADD CONSTRAINT fk_partner_account FOREIGN KEY (LinkedAccountID) REFERENCES chartofaccounts(AccountID);"
    ]
    
    with connection.cursor() as cursor:
        for sql in sql_commands:
            try:
                print(f"Executing: {sql}")
                cursor.execute(sql)
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    apply_sql()
