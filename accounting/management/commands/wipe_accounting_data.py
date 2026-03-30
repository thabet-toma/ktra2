from django.core.management.base import BaseCommand
from django.db import connection, transaction
from accounting.models import Account, JournalHeader, JournalLine, AccountingAuditLog

class Command(BaseCommand):
    help = 'Wipes all accounting data to allow a clean start with expert COA'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Wiping all accounting data...'))
        
        with transaction.atomic():
            # Truncate tables to reset IDs and clear everything
            with connection.cursor() as cursor:
                # Disable foreign key checks for truncation
                cursor.execute('SET FOREIGN_KEY_CHECKS = 0;')
                
                tables = [
                    'accounting_audit_log',
                    'journal_lines',
                    'journal_headers',
                    'chartofaccounts'
                ]
                
                for table in tables:
                    self.stdout.write(f'Truncating {table}...')
                    cursor.execute(f'TRUNCATE TABLE {table};')
                
                cursor.execute('SET FOREIGN_KEY_CHECKS = 1;')

        self.stdout.write(self.style.SUCCESS('Successfully wiped all accounting data.'))
