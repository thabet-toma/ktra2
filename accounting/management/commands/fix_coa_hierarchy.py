from django.core.management.base import BaseCommand
from accounting.models import Account
from django.db import transaction

class Command(BaseCommand):
    help = 'Fixes the Chart of Accounts hierarchy based on account codes.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate the hierarchy fix without making changes.',
        )
        parser.add_argument(
            '--tenant',
            type=int,
            help='Specific Tenant ID to process.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        target_tenant = options['tenant']
        
        accounts_query = Account.objects.filter(is_active=True).order_by('code')
        if target_tenant is not None:
             accounts_query = accounts_query.filter(tenant_id=target_tenant)
        
        accounts = list(accounts_query)
        # Create a lookup for potential parents (code -> account)
        # We need to handle multi-tenancy: (tenant_id, code) -> account
        account_map = {(acc.tenant_id, acc.code): acc for acc in accounts}
        
        updated_count = 0
        
        self.stdout.write(f"Processing {len(accounts)} accounts...")

        for account in accounts:
            if not account.code:
                continue
                
            # Try to find a parent
            # Logic: Match longest prefix
            # E.g. Code 1101 -> Try 110, then 11, then 1
            
            code = account.code
            parent_found = None
            
            for i in range(len(code) - 1, 0, -1):
                potential_parent_code = code[:i]
                key = (account.tenant_id, potential_parent_code)
                if key in account_map:
                    parent_found = account_map[key]
                    break
            
            if parent_found:
                if account.parent != parent_found:
                    self.stdout.write(f"[{'DRY-RUN' if dry_run else 'FIX'}] Mapping {account.code} -> Parent {parent_found.code}")
                    if not dry_run:
                        account.parent = parent_found
                        account.save()
                    updated_count += 1
            else:
                # Top level or orphan
                pass

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Dry run complete. found {updated_count} updates needed."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully updated hierarchy for {updated_count} accounts."))
