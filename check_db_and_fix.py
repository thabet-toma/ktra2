import os
import django
from django.db import connection

# Setup Django Environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def log(msg):
    with open('db_fix_log.txt', 'a', encoding='utf-8') as f:
        f.write(msg + '\\n')
    print(msg)

def check_and_fix_db():
    log("Starting DB Check...")
    
    with connection.cursor() as cursor:
        # 1. Check if 'cheques' table exists
        try:
            cursor.execute("SELECT 1 FROM cheques LIMIT 1")
            log("Table 'cheques' exists.")
        except Exception as e:
            log(f"Table 'cheques' missing or error: {e}")
            log("Attempting to create 'cheques' table...")
            create_cheques_sql = """
            CREATE TABLE IF NOT EXISTS `cheques` (
              `ChequeID` int NOT NULL AUTO_INCREMENT,
              `TenantID` int NOT NULL,
              `ChequeNumber` varchar(50) NOT NULL,
              `BankName` varchar(100),
              `Amount` decimal(18,2) NOT NULL,
              `CurrencyID` int NOT NULL DEFAULT 1,
              `DueDate` date NOT NULL,
              `IssueDate` date DEFAULT NULL,
              `PayeeName` varchar(150) DEFAULT NULL,
              `PartnerID` int DEFAULT NULL,
              `Status` enum('Draft','Under_Collection','Collected','Bounced','Returned') NOT NULL DEFAULT 'Draft',
              `Direction` enum('Incoming','Outgoing') NOT NULL COMMENT 'Incoming from Customer, Outgoing to Supplier',
              `CreatedBy_UserID` int DEFAULT NULL,
              `CreatedAt` datetime DEFAULT CURRENT_TIMESTAMP,
              `Notes` mediumtext,
              PRIMARY KEY (`ChequeID`),
              KEY `TenantID` (`TenantID`),
              KEY `PartnerID` (`PartnerID`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
            """
            try:
                # We use a fresh cursor for DDL if the previous one errored
                with connection.cursor() as cursor2:
                    cursor2.execute(create_cheques_sql)
                log("Table 'cheques' created successfully.")
            except Exception as e2:
                log(f"Failed to create table cheques: {e2}")

        # 2. Check 'cost_centers'
        try:
             cursor.execute("SELECT 1 FROM cost_centers LIMIT 1")
             log("Table 'cost_centers' exists.")
        except Exception as e:
             log(f"Table 'cost_centers' missing: {e}")
             log("Attempting to create 'cost_centers'...")
             create_cc_sql = """
             CREATE TABLE IF NOT EXISTS `cost_centers` (
               `id` int NOT NULL AUTO_INCREMENT,
               `name` varchar(100) NOT NULL,
               `code` varchar(50),
               `tenant_id` int NOT NULL,
               PRIMARY KEY (`id`)
             ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
             """
             try:
                 with connection.cursor() as cursor3:
                     cursor3.execute(create_cc_sql)
                 log("Table 'cost_centers' created.")
             except Exception as e3:
                 log(f"Failed to create cost_centers: {e3}")

if __name__ == "__main__":
    check_and_fix_db()

