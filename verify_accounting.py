import os
import django
import sys

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.db import connection, transaction
from accounting.models import Account, JournalHeader, JournalLine, AccountingAuditLog
from tenants.models import Tenant, Currency
from accounting.services import validate_journal_entry
from decimal import Decimal

def setup_db():
    print("Checking for accounting_audit_logs table...")
    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS `accounting_audit_logs` (
              `LogID` int NOT NULL AUTO_INCREMENT,
              `TenantID` int NOT NULL,
              `UserID` int DEFAULT NULL,
              `Action` varchar(20) NOT NULL,
              `ModelName` varchar(100) NOT NULL,
              `ObjectID` int NOT NULL,
              `ChangeDetails` text NOT NULL,
              `Timestamp` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY (`LogID`),
              KEY `TenantID` (`TenantID`),
              CONSTRAINT `fk_audit_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """)
    print("Table ensured.")

def test_accounting():
    print("\nRunning accounting tests...")
    
    # 1. Ensure a tenant and currency exist
    tenant = Tenant.objects.first()
    if not tenant:
        print("Creating dummy tenant...")
        tenant = Tenant.objects.create(CompanyName="Test Corp", SubscriptionPlan="Pro", Status="Active")
    
    currency = Currency.objects.first()
    if not currency:
        print("Creating dummy currency...")
        currency = Currency.objects.create(Code="USD", Name="US Dollar", Symbol="$", IsBaseCurrency=True)

    # 2. Create accounts
    print("Creating accounts...")
    assets, _ = Account.objects.get_or_create(
        Tenant=tenant, Code="1000", Name="Assets", Type="Asset", IsActive=True
    )
    cash, _ = Account.objects.get_or_create(
        Tenant=tenant, Code="1001", Name="Cash", Type="Asset", Parent=assets, IsActive=True
    )
    revenue, _ = Account.objects.get_or_create(
        Tenant=tenant, Code="4000", Name="Sales Revenue", Type="Revenue", IsActive=True
    )

    # 3. Test Balanced Journal Entry
    print("Testing balanced journal entry...")
    header = JournalHeader(Tenant=tenant, TransactionDate="2026-02-01", Description="Test Sale")
    # We don't save yet, validate_journal_entry takes lines_data
    lines_data = [
        {'AccountID': cash.AccountID, 'Debit': Decimal('100.00'), 'Credit': Decimal('0.00')},
        {'AccountID': revenue.AccountID, 'Debit': Decimal('0.00'), 'Credit': Decimal('100.00')},
    ]
    
    try:
        validate_journal_entry(header, lines_data)
        print("✅ Balanced entry validation passed.")
    except Exception as e:
        print(f"❌ Balanced entry validation failed: {e}")

    # 4. Test Unbalanced Journal Entry
    print("Testing unbalanced journal entry...")
    unbalanced_lines = [
        {'AccountID': cash.AccountID, 'Debit': Decimal('100.00'), 'Credit': Decimal('0.00')},
        {'AccountID': revenue.AccountID, 'Debit': Decimal('0.00'), 'Credit': Decimal('90.00')},
    ]
    try:
        validate_journal_entry(header, unbalanced_lines)
        print("❌ Unbalanced entry validation unexpectedly passed.")
    except Exception as e:
        print(f"✅ Unbalanced entry caught correctly: {e}")

    # 5. Test Inactive Account
    print("Testing inactive account...")
    cash.IsActive = False
    cash.save()
    try:
        validate_journal_entry(header, [lines_data[0]]) # Just one line to trigger inactive first
        print("❌ Inactive account validation unexpectedly passed.")
    except Exception as e:
        print(f"✅ Inactive account caught correctly: {e}")
    
    # Restore
    cash.IsActive = True
    cash.save()

    print("\nVerification complete.")

if __name__ == "__main__":
    try:
        setup_db()
        test_accounting()
    except Exception as e:
        print(f"Error during verification: {e}")
        sys.exit(1)
