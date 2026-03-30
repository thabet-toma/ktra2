import os
import django
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def apply_schema():
    sql_commands = [
        # 1. Create Partner Groups Table
        """
        CREATE TABLE IF NOT EXISTS `partner_groups` (
            `GroupID` INT AUTO_INCREMENT PRIMARY KEY,
            `TenantID` INT NOT NULL,
            `Name` VARCHAR(100) NOT NULL COMMENT 'اسم المجموعة',
            `Type` ENUM('Customer', 'Supplier') NOT NULL,
            `AccountReceivableID` INT NULL,
            `AccountPayableID` INT NULL,
            FOREIGN KEY (`AccountReceivableID`) REFERENCES `chartofaccounts`(`AccountID`),
            FOREIGN KEY (`AccountPayableID`) REFERENCES `chartofaccounts`(`AccountID`)
        );
        """,
        
        # 2. Update Partners Table
        """
        ALTER TABLE `partners` 
        ADD COLUMN `GroupID` INT NULL,
        ADD COLUMN `is_deleted` TINYINT(1) DEFAULT 0;
        """,
        
        """
        ALTER TABLE `partners` 
        ADD CONSTRAINT `fk_partner_group` 
        FOREIGN KEY (`GroupID`) REFERENCES `partner_groups`(`GroupID`);
        """,

        # 3. Soft Delete for Accounting Tables
        "ALTER TABLE `chartofaccounts` ADD COLUMN IF NOT EXISTS `is_deleted` TINYINT(1) DEFAULT 0;",
        "ALTER TABLE `journal_headers` ADD COLUMN IF NOT EXISTS `is_deleted` TINYINT(1) DEFAULT 0;",
        "ALTER TABLE `journal_lines` ADD COLUMN IF NOT EXISTS `is_deleted` TINYINT(1) DEFAULT 0;"
    ]

    with connection.cursor() as cursor:
        for sql in sql_commands:
            try:
                print(f"Executing: {sql[:50]}...")
                cursor.execute(sql)
                print("Success.")
            except Exception as e:
                print(f"Error executing SQL: {e}")

if __name__ == "__main__":
    apply_schema()
