-- MySQL dump 10.13  Distrib 8.0.44, for Win64 (x86_64)
--
-- Host: localhost    Database: global_erp_pro
-- ------------------------------------------------------
-- Server version	8.0.44

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `auth_group`
--

DROP TABLE IF EXISTS `auth_group`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_group` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(150) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_group`
--

LOCK TABLES `auth_group` WRITE;
/*!40000 ALTER TABLE `auth_group` DISABLE KEYS */;
/*!40000 ALTER TABLE `auth_group` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_group_permissions`
--

DROP TABLE IF EXISTS `auth_group_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_group_permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `group_id` int NOT NULL,
  `permission_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` (`group_id`,`permission_id`),
  KEY `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` (`permission_id`),
  CONSTRAINT `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  CONSTRAINT `auth_group_permissions_group_id_b120cbf9_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_group_permissions`
--

LOCK TABLES `auth_group_permissions` WRITE;
/*!40000 ALTER TABLE `auth_group_permissions` DISABLE KEYS */;
/*!40000 ALTER TABLE `auth_group_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_permission`
--

DROP TABLE IF EXISTS `auth_permission`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_permission` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL,
  `content_type_id` int NOT NULL,
  `codename` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_permission_content_type_id_codename_01ab375a_uniq` (`content_type_id`,`codename`),
  CONSTRAINT `auth_permission_content_type_id_2f476e4b_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=49 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_permission`
--

LOCK TABLES `auth_permission` WRITE;
/*!40000 ALTER TABLE `auth_permission` DISABLE KEYS */;
INSERT INTO `auth_permission` VALUES (1,'Can add log entry',1,'add_logentry'),(2,'Can change log entry',1,'change_logentry'),(3,'Can delete log entry',1,'delete_logentry'),(4,'Can view log entry',1,'view_logentry'),(5,'Can add permission',3,'add_permission'),(6,'Can change permission',3,'change_permission'),(7,'Can delete permission',3,'delete_permission'),(8,'Can view permission',3,'view_permission'),(9,'Can add group',2,'add_group'),(10,'Can change group',2,'change_group'),(11,'Can delete group',2,'delete_group'),(12,'Can view group',2,'view_group'),(13,'Can add user',4,'add_user'),(14,'Can change user',4,'change_user'),(15,'Can delete user',4,'delete_user'),(16,'Can view user',4,'view_user'),(17,'Can add content type',5,'add_contenttype'),(18,'Can change content type',5,'change_contenttype'),(19,'Can delete content type',5,'delete_contenttype'),(20,'Can view content type',5,'view_contenttype'),(21,'Can add session',6,'add_session'),(22,'Can change session',6,'change_session'),(23,'Can delete session',6,'delete_session'),(24,'Can view session',6,'view_session'),(25,'Can add partner',7,'add_partner'),(26,'Can change partner',7,'change_partner'),(27,'Can delete partner',7,'delete_partner'),(28,'Can view partner',7,'view_partner'),(29,'Can add account',8,'add_account'),(30,'Can change account',8,'change_account'),(31,'Can delete account',8,'delete_account'),(32,'Can view account',8,'view_account'),(33,'Can add journal header',11,'add_journalheader'),(34,'Can change journal header',11,'change_journalheader'),(35,'Can delete journal header',11,'delete_journalheader'),(36,'Can view journal header',11,'view_journalheader'),(37,'Can add journal line',12,'add_journalline'),(38,'Can change journal line',12,'change_journalline'),(39,'Can delete journal line',12,'delete_journalline'),(40,'Can view journal line',12,'view_journalline'),(41,'Can add accounting audit log',9,'add_accountingauditlog'),(42,'Can change accounting audit log',9,'change_accountingauditlog'),(43,'Can delete accounting audit log',9,'delete_accountingauditlog'),(44,'Can view accounting audit log',9,'view_accountingauditlog'),(45,'Can add fiscal period',10,'add_fiscalperiod'),(46,'Can change fiscal period',10,'change_fiscalperiod'),(47,'Can delete fiscal period',10,'delete_fiscalperiod'),(48,'Can view fiscal period',10,'view_fiscalperiod');
/*!40000 ALTER TABLE `auth_permission` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_user`
--

DROP TABLE IF EXISTS `auth_user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_user` (
  `id` int NOT NULL AUTO_INCREMENT,
  `password` varchar(128) NOT NULL,
  `last_login` datetime(6) DEFAULT NULL,
  `is_superuser` tinyint(1) NOT NULL,
  `username` varchar(150) NOT NULL,
  `first_name` varchar(150) NOT NULL,
  `last_name` varchar(150) NOT NULL,
  `email` varchar(254) NOT NULL,
  `is_staff` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `date_joined` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_user`
--

LOCK TABLES `auth_user` WRITE;
/*!40000 ALTER TABLE `auth_user` DISABLE KEYS */;
/*!40000 ALTER TABLE `auth_user` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_user_groups`
--

DROP TABLE IF EXISTS `auth_user_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_user_groups` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `group_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_user_groups_user_id_group_id_94350c0c_uniq` (`user_id`,`group_id`),
  KEY `auth_user_groups_group_id_97559544_fk_auth_group_id` (`group_id`),
  CONSTRAINT `auth_user_groups_group_id_97559544_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`),
  CONSTRAINT `auth_user_groups_user_id_6a12ed8b_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_user_groups`
--

LOCK TABLES `auth_user_groups` WRITE;
/*!40000 ALTER TABLE `auth_user_groups` DISABLE KEYS */;
/*!40000 ALTER TABLE `auth_user_groups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `auth_user_user_permissions`
--

DROP TABLE IF EXISTS `auth_user_user_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `auth_user_user_permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `permission_id` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `auth_user_user_permissions_user_id_permission_id_14a6b632_uniq` (`user_id`,`permission_id`),
  KEY `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` (`permission_id`),
  CONSTRAINT `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  CONSTRAINT `auth_user_user_permissions_user_id_a95ead1b_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `auth_user_user_permissions`
--

LOCK TABLES `auth_user_user_permissions` WRITE;
/*!40000 ALTER TABLE `auth_user_user_permissions` DISABLE KEYS */;
/*!40000 ALTER TABLE `auth_user_user_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `bank_accounts`
--

DROP TABLE IF EXISTS `bank_accounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bank_accounts` (
  `BankAccountID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `BankName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `AccountNumber` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `IBAN` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `CurrencyID` int NOT NULL,
  `IsActive` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`BankAccountID`),
  UNIQUE KEY `idx_tenant_account` (`TenantID`,`AccountNumber`),
  KEY `CurrencyID` (`CurrencyID`),
  CONSTRAINT `bank_accounts_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `bank_accounts_ibfk_2` FOREIGN KEY (`CurrencyID`) REFERENCES `currencies` (`CurrencyID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `bank_accounts`
--

LOCK TABLES `bank_accounts` WRITE;
/*!40000 ALTER TABLE `bank_accounts` DISABLE KEYS */;
/*!40000 ALTER TABLE `bank_accounts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `bom`
--

DROP TABLE IF EXISTS `bom`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bom` (
  `BOM_ID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ProductID` int NOT NULL COMMENT 'المنتج النهائي الذي يتم تصنيعه',
  `Description` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`BOM_ID`),
  UNIQUE KEY `idx_tenant_product_bom` (`TenantID`,`ProductID`),
  KEY `ProductID` (`ProductID`),
  CONSTRAINT `bom_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `bom_ibfk_2` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `bom`
--

LOCK TABLES `bom` WRITE;
/*!40000 ALTER TABLE `bom` DISABLE KEYS */;
/*!40000 ALTER TABLE `bom` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `bom_lines`
--

DROP TABLE IF EXISTS `bom_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `bom_lines` (
  `BOM_LineID` int NOT NULL AUTO_INCREMENT,
  `BOM_ID` int NOT NULL,
  `ComponentID` int NOT NULL COMMENT 'المنتج المكون (المادة الخام)',
  `Quantity` decimal(18,4) NOT NULL COMMENT 'الكمية المطلوبة من المكون لإنتاج قطعة واحدة من المنتج النهائي',
  PRIMARY KEY (`BOM_LineID`),
  KEY `BOM_ID` (`BOM_ID`),
  KEY `ComponentID` (`ComponentID`),
  CONSTRAINT `bom_lines_ibfk_1` FOREIGN KEY (`BOM_ID`) REFERENCES `bom` (`BOM_ID`) ON DELETE CASCADE,
  CONSTRAINT `bom_lines_ibfk_2` FOREIGN KEY (`ComponentID`) REFERENCES `products` (`ProductID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `bom_lines`
--

LOCK TABLES `bom_lines` WRITE;
/*!40000 ALTER TABLE `bom_lines` DISABLE KEYS */;
/*!40000 ALTER TABLE `bom_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `chargetypes`
--

DROP TABLE IF EXISTS `chargetypes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chargetypes` (
  `ChargeTypeID` int NOT NULL AUTO_INCREMENT,
  `TypeName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`ChargeTypeID`),
  UNIQUE KEY `TypeName` (`TypeName`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `chargetypes`
--

LOCK TABLES `chargetypes` WRITE;
/*!40000 ALTER TABLE `chargetypes` DISABLE KEYS */;
INSERT INTO `chargetypes` VALUES (3,'Handling Charges'),(2,'Insurance Fees'),(4,'Other Fees'),(1,'Shipping Cost');
/*!40000 ALTER TABLE `chargetypes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `chartofaccounts`
--

DROP TABLE IF EXISTS `chartofaccounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `chartofaccounts` (
  `AccountID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `Code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ParentID` int DEFAULT NULL,
  `Type` enum('Asset','Liability','Equity','Revenue','Expense') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `IsActive` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`AccountID`),
  UNIQUE KEY `idx_tenant_account_code` (`TenantID`,`Code`),
  CONSTRAINT `fk_coa_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB AUTO_INCREMENT=38 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `chartofaccounts`
--

LOCK TABLES `chartofaccounts` WRITE;
/*!40000 ALTER TABLE `chartofaccounts` DISABLE KEYS */;
INSERT INTO `chartofaccounts` VALUES (1,1,'1','الأصول',NULL,'Asset',1),(2,1,'2','الخصوم',NULL,'Liability',1),(3,1,'3','حقوق الملكية',NULL,'Equity',1),(4,1,'4','الإيرادات',NULL,'Revenue',1),(5,1,'5','المصروفات',NULL,'Expense',1),(6,1,'11','الأصول المتداولة',1,'Asset',1),(7,1,'1101','النقدية',6,'Asset',1),(8,1,'1102','البنوك',6,'Asset',1),(9,1,'1103','ذمم العملاء',6,'Asset',1),(10,1,'1104','المخزون',6,'Asset',1),(14,1,'21','الخصوم المتداولة',2,'Liability',1),(15,1,'2101','ذمم الموردين',14,'Liability',1),(16,1,'11030002','احمر',9,'Asset',1),(17,1,'53','مصاريف لوجستية (Logistics Expenses)',5,'Expense',1),(18,1,'5301','مصاريف شركات الشحن',17,'Expense',1),(19,1,'5302','مصاريف تخليص جمركي',17,'Expense',1),(20,1,'5303','مصاريف نقل محلي',17,'Expense',1),(21,1,'2101-L','ذمم موردين - خدمات لوجستية',15,'Liability',1),(22,1,'2101-L0001','ففف',21,'Liability',1),(23,1,'3300','أرصدة افتتاحية (Opening Balances)',3,'Equity',1),(24,1,'2101-L0003','يويو',21,'Liability',1),(25,1,'2101-L0004','ةة',21,'Liability',1),(26,1,'21010005','تكفاين',15,'Liability',1),(27,1,'2102','وكلاء شحن (Freight Forwarders)',14,'Liability',1),(28,1,'2103','مخلصين جمركيين (Customs Brokers)',14,'Liability',1),(29,1,'2104','ناقل محلي (Local Carriers)',14,'Liability',1),(30,1,'21020006','المورد',27,'Liability',1),(31,1,'21010007','مورد اختبار',15,'Liability',1),(32,1,'11030008','عميل اختبار',9,'Asset',1),(33,1,'21030009','مخلص اختبار',28,'Liability',1),(34,1,'21030010','مخلص اختبار',28,'Liability',1),(35,1,'21010011','مجموع 15',15,'Liability',1),(36,1,'21020012','يويو',27,'Liability',1),(37,1,'11030013','تراد',9,'Asset',1);
/*!40000 ALTER TABLE `chartofaccounts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cheques`
--

DROP TABLE IF EXISTS `cheques`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cheques` (
  `ChequeID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ChequeNumber` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `BankName` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Amount` decimal(18,2) NOT NULL,
  `CurrencyID` int NOT NULL DEFAULT '1',
  `DueDate` date NOT NULL,
  `IssueDate` date DEFAULT NULL,
  `PayeeName` varchar(150) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `PartnerID` int DEFAULT NULL,
  `Status` enum('Draft','Under_Collection','Collected','Bounced','Returned') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Draft',
  `Direction` enum('Incoming','Outgoing') COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Incoming from Customer, Outgoing to Supplier',
  `CreatedBy_UserID` int DEFAULT NULL,
  `CreatedAt` datetime DEFAULT CURRENT_TIMESTAMP,
  `Notes` mediumtext COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`ChequeID`),
  KEY `TenantID` (`TenantID`),
  KEY `PartnerID` (`PartnerID`),
  CONSTRAINT `fk_cheque_partner` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`),
  CONSTRAINT `fk_cheque_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cheques`
--

LOCK TABLES `cheques` WRITE;
/*!40000 ALTER TABLE `cheques` DISABLE KEYS */;
/*!40000 ALTER TABLE `cheques` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cost_centers`
--

DROP TABLE IF EXISTS `cost_centers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cost_centers` (
  `CostCenterID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `Name` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Description` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`CostCenterID`),
  UNIQUE KEY `idx_tenant_costcenter_name` (`TenantID`,`Name`),
  CONSTRAINT `cost_centers_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cost_centers`
--

LOCK TABLES `cost_centers` WRITE;
/*!40000 ALTER TABLE `cost_centers` DISABLE KEYS */;
/*!40000 ALTER TABLE `cost_centers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `credit_note_lines`
--

DROP TABLE IF EXISTS `credit_note_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `credit_note_lines` (
  `CreditNoteLineID` int NOT NULL AUTO_INCREMENT,
  `CreditNoteID` int NOT NULL,
  `ProductID` int NOT NULL,
  `Quantity` decimal(18,2) NOT NULL,
  `UnitPrice` decimal(18,2) NOT NULL,
  `TotalLine` decimal(18,2) NOT NULL,
  PRIMARY KEY (`CreditNoteLineID`),
  KEY `CreditNoteID` (`CreditNoteID`),
  KEY `ProductID` (`ProductID`),
  CONSTRAINT `credit_note_lines_ibfk_1` FOREIGN KEY (`CreditNoteID`) REFERENCES `credit_notes` (`CreditNoteID`) ON DELETE CASCADE,
  CONSTRAINT `credit_note_lines_ibfk_2` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `credit_note_lines`
--

LOCK TABLES `credit_note_lines` WRITE;
/*!40000 ALTER TABLE `credit_note_lines` DISABLE KEYS */;
/*!40000 ALTER TABLE `credit_note_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `credit_notes`
--

DROP TABLE IF EXISTS `credit_notes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `credit_notes` (
  `CreditNoteID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `CustomerID` int NOT NULL,
  `CreditNoteDate` date NOT NULL,
  `OriginalInvoiceID` int DEFAULT NULL COMMENT 'الفاتورة الأصلية للمرتجع',
  `Reason` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `Subtotal_Local` decimal(18,2) NOT NULL,
  `TotalTax_Local` decimal(18,2) NOT NULL,
  `TotalAmount_Local` decimal(18,2) NOT NULL,
  `JournalID` int DEFAULT NULL,
  PRIMARY KEY (`CreditNoteID`),
  KEY `CustomerID` (`CustomerID`),
  KEY `OriginalInvoiceID` (`OriginalInvoiceID`),
  KEY `JournalID` (`JournalID`),
  KEY `credit_notes_ibfk_1` (`TenantID`),
  CONSTRAINT `credit_notes_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `credit_notes_ibfk_2` FOREIGN KEY (`CustomerID`) REFERENCES `partners` (`PartnerID`),
  CONSTRAINT `credit_notes_ibfk_3` FOREIGN KEY (`OriginalInvoiceID`) REFERENCES `salesinvoices` (`InvoiceID`),
  CONSTRAINT `credit_notes_ibfk_4` FOREIGN KEY (`JournalID`) REFERENCES `journal_headers` (`JournalID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `credit_notes`
--

LOCK TABLES `credit_notes` WRITE;
/*!40000 ALTER TABLE `credit_notes` DISABLE KEYS */;
/*!40000 ALTER TABLE `credit_notes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `crm_activities`
--

DROP TABLE IF EXISTS `crm_activities`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `crm_activities` (
  `ActivityID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `LeadID` int DEFAULT NULL,
  `OpportunityID` int DEFAULT NULL,
  `ContactID` int DEFAULT NULL,
  `ActivityType` enum('Call','Email','Meeting','Task') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Subject` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `ActivityDate` datetime NOT NULL,
  `Notes` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `DoneBy_UserID` int NOT NULL,
  PRIMARY KEY (`ActivityID`),
  KEY `LeadID` (`LeadID`),
  KEY `OpportunityID` (`OpportunityID`),
  KEY `ContactID` (`ContactID`),
  KEY `DoneBy_UserID` (`DoneBy_UserID`),
  KEY `crm_activities_ibfk_1` (`TenantID`),
  CONSTRAINT `crm_activities_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `crm_activities_ibfk_2` FOREIGN KEY (`LeadID`) REFERENCES `crm_leads` (`LeadID`),
  CONSTRAINT `crm_activities_ibfk_3` FOREIGN KEY (`OpportunityID`) REFERENCES `crm_opportunities` (`OpportunityID`),
  CONSTRAINT `crm_activities_ibfk_4` FOREIGN KEY (`ContactID`) REFERENCES `crm_contacts` (`ContactID`),
  CONSTRAINT `crm_activities_ibfk_5` FOREIGN KEY (`DoneBy_UserID`) REFERENCES `users` (`UserID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `crm_activities`
--

LOCK TABLES `crm_activities` WRITE;
/*!40000 ALTER TABLE `crm_activities` DISABLE KEYS */;
/*!40000 ALTER TABLE `crm_activities` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `crm_contacts`
--

DROP TABLE IF EXISTS `crm_contacts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `crm_contacts` (
  `ContactID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `PartnerID` int NOT NULL COMMENT 'العميل/الشركة التي يتبع لها هذا الشخص',
  `FullName` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Position` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`ContactID`),
  KEY `PartnerID` (`PartnerID`),
  KEY `crm_contacts_ibfk_1` (`TenantID`),
  CONSTRAINT `crm_contacts_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `crm_contacts_ibfk_2` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `crm_contacts`
--

LOCK TABLES `crm_contacts` WRITE;
/*!40000 ALTER TABLE `crm_contacts` DISABLE KEYS */;
/*!40000 ALTER TABLE `crm_contacts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `crm_leads`
--

DROP TABLE IF EXISTS `crm_leads`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `crm_leads` (
  `LeadID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `LeadName` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'اسم الشخص أو الشركة المهتمة',
  `Source` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'مصدر العميل (مثال: فيسبوك، مؤتمر، توصية)',
  `Status` enum('New','Contacted','Qualified','Unqualified') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'New',
  `AssignedTo_UserID` int DEFAULT NULL,
  `Email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Phone` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`LeadID`),
  KEY `TenantID` (`TenantID`),
  KEY `AssignedTo_UserID` (`AssignedTo_UserID`),
  CONSTRAINT `crm_leads_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `crm_leads_ibfk_2` FOREIGN KEY (`AssignedTo_UserID`) REFERENCES `users` (`UserID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `crm_leads`
--

LOCK TABLES `crm_leads` WRITE;
/*!40000 ALTER TABLE `crm_leads` DISABLE KEYS */;
/*!40000 ALTER TABLE `crm_leads` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `crm_notes`
--

DROP TABLE IF EXISTS `crm_notes`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `crm_notes` (
  `NoteID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `Note` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `CreatedAt` datetime DEFAULT CURRENT_TIMESTAMP,
  `CreatedBy_UserID` int NOT NULL,
  `LeadID` int DEFAULT NULL,
  `OpportunityID` int DEFAULT NULL,
  `ContactID` int DEFAULT NULL,
  PRIMARY KEY (`NoteID`),
  KEY `TenantID` (`TenantID`),
  KEY `CreatedBy_UserID` (`CreatedBy_UserID`),
  CONSTRAINT `crm_notes_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `crm_notes_ibfk_2` FOREIGN KEY (`CreatedBy_UserID`) REFERENCES `users` (`UserID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `crm_notes`
--

LOCK TABLES `crm_notes` WRITE;
/*!40000 ALTER TABLE `crm_notes` DISABLE KEYS */;
/*!40000 ALTER TABLE `crm_notes` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `crm_opportunities`
--

DROP TABLE IF EXISTS `crm_opportunities`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `crm_opportunities` (
  `OpportunityID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `OpportunityName` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'اسم الفرصة (مثال: توريد أجهزة لشركة X)',
  `PartnerID` int NOT NULL COMMENT 'العميل المرتبطة به الفرصة',
  `StageID` int NOT NULL COMMENT 'المرحلة الحالية للفرصة',
  `EstimatedValue` decimal(18,2) DEFAULT '0.00',
  `ExpectedCloseDate` date DEFAULT NULL,
  `Status` enum('Open','Won','Lost') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Open',
  PRIMARY KEY (`OpportunityID`),
  KEY `TenantID` (`TenantID`),
  KEY `PartnerID` (`PartnerID`),
  KEY `StageID` (`StageID`),
  CONSTRAINT `crm_opportunities_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `crm_opportunities_ibfk_2` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`),
  CONSTRAINT `crm_opportunities_ibfk_3` FOREIGN KEY (`StageID`) REFERENCES `crm_pipeline_stages` (`StageID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `crm_opportunities`
--

LOCK TABLES `crm_opportunities` WRITE;
/*!40000 ALTER TABLE `crm_opportunities` DISABLE KEYS */;
/*!40000 ALTER TABLE `crm_opportunities` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `crm_pipeline_stages`
--

DROP TABLE IF EXISTS `crm_pipeline_stages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `crm_pipeline_stages` (
  `StageID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `StageName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `StageOrder` int NOT NULL COMMENT 'ترتيب ظهور المرحلة في المسار',
  PRIMARY KEY (`StageID`),
  KEY `TenantID` (`TenantID`),
  CONSTRAINT `crm_pipeline_stages_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `crm_pipeline_stages`
--

LOCK TABLES `crm_pipeline_stages` WRITE;
/*!40000 ALTER TABLE `crm_pipeline_stages` DISABLE KEYS */;
/*!40000 ALTER TABLE `crm_pipeline_stages` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `currencies`
--

DROP TABLE IF EXISTS `currencies`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `currencies` (
  `CurrencyID` int NOT NULL AUTO_INCREMENT,
  `Code` char(3) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Symbol` varchar(5) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `IsBaseCurrency` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`CurrencyID`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `currencies`
--

LOCK TABLES `currencies` WRITE;
/*!40000 ALTER TABLE `currencies` DISABLE KEYS */;
INSERT INTO `currencies` VALUES (1,'ILS','Israeli New Shekel','₪',1),(2,'USD','United States Dollar','$',0),(3,'EUR','Euro','€',0),(4,'JOD','Jordanian Dinar','د.أ',0);
/*!40000 ALTER TABLE `currencies` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `customer_assets`
--

DROP TABLE IF EXISTS `customer_assets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `customer_assets` (
  `CustomerAssetID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `PartnerID` int NOT NULL COMMENT 'العميل الذي يملك الأصل',
  `ProductID` int NOT NULL COMMENT 'نوع المنتج/الموديل',
  `SerialNumber` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `SalesInvoiceLineID` int DEFAULT NULL COMMENT 'بند الفاتورة الذي تم بيع الأصل منه',
  `InstallationDate` date DEFAULT NULL,
  `WarrantyExpiryDate` date DEFAULT NULL,
  `Status` enum('Active','Under-Maintenance','Retired') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Active',
  PRIMARY KEY (`CustomerAssetID`),
  UNIQUE KEY `idx_tenant_serial` (`TenantID`,`SerialNumber`),
  KEY `fk_ca_tenant` (`TenantID`),
  KEY `fk_ca_partner` (`PartnerID`),
  KEY `fk_ca_product` (`ProductID`),
  KEY `fk_ca_salesline` (`SalesInvoiceLineID`),
  CONSTRAINT `fk_ca_partner` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`) ON DELETE CASCADE,
  CONSTRAINT `fk_ca_product` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`),
  CONSTRAINT `fk_ca_salesline` FOREIGN KEY (`SalesInvoiceLineID`) REFERENCES `salesinvoice_lines` (`LineID`) ON DELETE SET NULL,
  CONSTRAINT `fk_ca_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `customer_assets`
--

LOCK TABLES `customer_assets` WRITE;
/*!40000 ALTER TABLE `customer_assets` DISABLE KEYS */;
/*!40000 ALTER TABLE `customer_assets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `customer_receipts`
--

DROP TABLE IF EXISTS `customer_receipts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `customer_receipts` (
  `ReceiptID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `CustomerID` int NOT NULL,
  `ReceiptDate` date NOT NULL,
  `Amount_Local` decimal(18,2) NOT NULL,
  `PaymentMethod` enum('BankTransfer','Cash','Check','CreditCard') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `BankAccountID` int DEFAULT NULL COMMENT 'الحساب البنكي الذي استلم المبلغ',
  `Notes` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`ReceiptID`),
  KEY `TenantID` (`TenantID`),
  KEY `CustomerID` (`CustomerID`),
  KEY `BankAccountID` (`BankAccountID`),
  CONSTRAINT `customer_receipts_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `customer_receipts_ibfk_2` FOREIGN KEY (`CustomerID`) REFERENCES `partners` (`PartnerID`),
  CONSTRAINT `customer_receipts_ibfk_3` FOREIGN KEY (`BankAccountID`) REFERENCES `bank_accounts` (`BankAccountID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `customer_receipts`
--

LOCK TABLES `customer_receipts` WRITE;
/*!40000 ALTER TABLE `customer_receipts` DISABLE KEYS */;
/*!40000 ALTER TABLE `customer_receipts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `django_admin_log`
--

DROP TABLE IF EXISTS `django_admin_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_admin_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `action_time` datetime(6) NOT NULL,
  `object_id` longtext,
  `object_repr` varchar(200) NOT NULL,
  `action_flag` smallint unsigned NOT NULL,
  `change_message` longtext NOT NULL,
  `content_type_id` int DEFAULT NULL,
  `user_id` int NOT NULL,
  PRIMARY KEY (`id`),
  KEY `django_admin_log_content_type_id_c4bce8eb_fk_django_co` (`content_type_id`),
  KEY `django_admin_log_user_id_c564eba6_fk_auth_user_id` (`user_id`),
  CONSTRAINT `django_admin_log_content_type_id_c4bce8eb_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`),
  CONSTRAINT `django_admin_log_user_id_c564eba6_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`),
  CONSTRAINT `django_admin_log_chk_1` CHECK ((`action_flag` >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `django_admin_log`
--

LOCK TABLES `django_admin_log` WRITE;
/*!40000 ALTER TABLE `django_admin_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `django_admin_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `django_content_type`
--

DROP TABLE IF EXISTS `django_content_type`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_content_type` (
  `id` int NOT NULL AUTO_INCREMENT,
  `app_label` varchar(100) NOT NULL,
  `model` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `django_content_type_app_label_model_76bd3d3b_uniq` (`app_label`,`model`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `django_content_type`
--

LOCK TABLES `django_content_type` WRITE;
/*!40000 ALTER TABLE `django_content_type` DISABLE KEYS */;
INSERT INTO `django_content_type` VALUES (8,'accounting','account'),(9,'accounting','accountingauditlog'),(10,'accounting','fiscalperiod'),(11,'accounting','journalheader'),(12,'accounting','journalline'),(1,'admin','logentry'),(2,'auth','group'),(3,'auth','permission'),(4,'auth','user'),(5,'contenttypes','contenttype'),(7,'partners','partner'),(6,'sessions','session');
/*!40000 ALTER TABLE `django_content_type` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `django_migrations`
--

DROP TABLE IF EXISTS `django_migrations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_migrations` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `app` varchar(255) NOT NULL,
  `name` varchar(255) NOT NULL,
  `applied` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `django_migrations`
--

LOCK TABLES `django_migrations` WRITE;
/*!40000 ALTER TABLE `django_migrations` DISABLE KEYS */;
INSERT INTO `django_migrations` VALUES (1,'contenttypes','0001_initial','2026-01-31 13:13:37.038353'),(2,'auth','0001_initial','2026-01-31 13:13:37.434123'),(3,'admin','0001_initial','2026-01-31 13:13:37.534584'),(4,'admin','0002_logentry_remove_auto_add','2026-01-31 13:13:37.543578'),(5,'admin','0003_logentry_add_action_flag_choices','2026-01-31 13:13:37.550772'),(6,'contenttypes','0002_remove_content_type_name','2026-01-31 13:13:37.630906'),(7,'auth','0002_alter_permission_name_max_length','2026-01-31 13:13:37.677906'),(8,'auth','0003_alter_user_email_max_length','2026-01-31 13:13:37.703181'),(9,'auth','0004_alter_user_username_opts','2026-01-31 13:13:37.709941'),(10,'auth','0005_alter_user_last_login_null','2026-01-31 13:13:37.760529'),(11,'auth','0006_require_contenttypes_0002','2026-01-31 13:13:37.762396'),(12,'auth','0007_alter_validators_add_error_messages','2026-01-31 13:13:37.771044'),(13,'auth','0008_alter_user_username_max_length','2026-01-31 13:13:37.831370'),(14,'auth','0009_alter_user_last_name_max_length','2026-01-31 13:13:37.877678'),(15,'auth','0010_alter_group_name_max_length','2026-01-31 13:13:37.898241'),(16,'auth','0011_update_proxy_permissions','2026-01-31 13:13:37.907617'),(17,'auth','0012_alter_user_first_name_max_length','2026-01-31 13:13:37.958866'),(18,'sessions','0001_initial','2026-01-31 13:13:37.985470'),(19,'partners','0001_initial','2026-02-02 08:32:42.241761'),(20,'tenants','0001_initial','2026-02-02 08:32:42.244675');
/*!40000 ALTER TABLE `django_migrations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `django_session`
--

DROP TABLE IF EXISTS `django_session`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `django_session` (
  `session_key` varchar(40) NOT NULL,
  `session_data` longtext NOT NULL,
  `expire_date` datetime(6) NOT NULL,
  PRIMARY KEY (`session_key`),
  KEY `django_session_expire_date_a5c62663` (`expire_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `django_session`
--

LOCK TABLES `django_session` WRITE;
/*!40000 ALTER TABLE `django_session` DISABLE KEYS */;
/*!40000 ALTER TABLE `django_session` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `ecomm_orderlines`
--

DROP TABLE IF EXISTS `ecomm_orderlines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ecomm_orderlines` (
  `OrderLineID` int NOT NULL AUTO_INCREMENT,
  `OrderID` int NOT NULL,
  `ProductID` int NOT NULL,
  `Quantity` int NOT NULL,
  `UnitPrice` decimal(18,2) NOT NULL,
  `TotalLine` decimal(18,2) NOT NULL,
  PRIMARY KEY (`OrderLineID`),
  KEY `OrderID` (`OrderID`),
  KEY `ProductID` (`ProductID`),
  CONSTRAINT `ecomm_orderlines_ibfk_1` FOREIGN KEY (`OrderID`) REFERENCES `ecomm_orders` (`OrderID`) ON DELETE CASCADE,
  CONSTRAINT `ecomm_orderlines_ibfk_2` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `ecomm_orderlines`
--

LOCK TABLES `ecomm_orderlines` WRITE;
/*!40000 ALTER TABLE `ecomm_orderlines` DISABLE KEYS */;
/*!40000 ALTER TABLE `ecomm_orderlines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `ecomm_orders`
--

DROP TABLE IF EXISTS `ecomm_orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ecomm_orders` (
  `OrderID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ShopperID` int NOT NULL,
  `OrderDate` datetime DEFAULT CURRENT_TIMESTAMP,
  `Status` enum('PendingPayment','Processing','Shipped','Delivered','Cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'PendingPayment',
  `ShippingAddressID` int NOT NULL,
  `Subtotal` decimal(18,2) NOT NULL,
  `ShippingCost` decimal(18,2) DEFAULT '0.00',
  `TotalAmount` decimal(18,2) NOT NULL,
  `TrackingNumber` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`OrderID`),
  KEY `ShopperID` (`ShopperID`),
  KEY `ShippingAddressID` (`ShippingAddressID`),
  KEY `ecomm_orders_ibfk_1` (`TenantID`),
  CONSTRAINT `ecomm_orders_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `ecomm_orders_ibfk_2` FOREIGN KEY (`ShopperID`) REFERENCES `ecomm_shoppers` (`ShopperID`),
  CONSTRAINT `ecomm_orders_ibfk_3` FOREIGN KEY (`ShippingAddressID`) REFERENCES `ecomm_shopper_addresses` (`AddressID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `ecomm_orders`
--

LOCK TABLES `ecomm_orders` WRITE;
/*!40000 ALTER TABLE `ecomm_orders` DISABLE KEYS */;
/*!40000 ALTER TABLE `ecomm_orders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `ecomm_shopper_addresses`
--

DROP TABLE IF EXISTS `ecomm_shopper_addresses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ecomm_shopper_addresses` (
  `AddressID` int NOT NULL AUTO_INCREMENT,
  `ShopperID` int NOT NULL,
  `AddressType` enum('Shipping','Billing') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Shipping',
  `StreetAddress` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `City` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Country` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `PostalCode` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `IsDefault` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`AddressID`),
  KEY `ShopperID` (`ShopperID`),
  CONSTRAINT `ecomm_shopper_addresses_ibfk_1` FOREIGN KEY (`ShopperID`) REFERENCES `ecomm_shoppers` (`ShopperID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `ecomm_shopper_addresses`
--

LOCK TABLES `ecomm_shopper_addresses` WRITE;
/*!40000 ALTER TABLE `ecomm_shopper_addresses` DISABLE KEYS */;
/*!40000 ALTER TABLE `ecomm_shopper_addresses` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `ecomm_shoppers`
--

DROP TABLE IF EXISTS `ecomm_shoppers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ecomm_shoppers` (
  `ShopperID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `FirstName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `LastName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `PasswordHash` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `CreatedAt` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`ShopperID`),
  UNIQUE KEY `idx_tenant_shopper_email` (`TenantID`,`Email`),
  CONSTRAINT `ecomm_shoppers_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `ecomm_shoppers`
--

LOCK TABLES `ecomm_shoppers` WRITE;
/*!40000 ALTER TABLE `ecomm_shoppers` DISABLE KEYS */;
/*!40000 ALTER TABLE `ecomm_shoppers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `employees`
--

DROP TABLE IF EXISTS `employees`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `employees` (
  `EmployeeID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `UserID` int DEFAULT NULL COMMENT 'ربط الموظف بحساب مستخدم للنظام',
  `FullName` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `HireDate` date DEFAULT NULL,
  `Position` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `BasicSalary` decimal(18,2) DEFAULT '0.00',
  PRIMARY KEY (`EmployeeID`),
  KEY `UserID` (`UserID`),
  KEY `employees_ibfk_1` (`TenantID`),
  CONSTRAINT `employees_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `employees_ibfk_2` FOREIGN KEY (`UserID`) REFERENCES `users` (`UserID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `employees`
--

LOCK TABLES `employees` WRITE;
/*!40000 ALTER TABLE `employees` DISABLE KEYS */;
/*!40000 ALTER TABLE `employees` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `fiscal_periods`
--

DROP TABLE IF EXISTS `fiscal_periods`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `fiscal_periods` (
  `PeriodID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `PeriodName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `StartDate` date NOT NULL,
  `EndDate` date NOT NULL,
  `Status` enum('Open','Closed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Open',
  PRIMARY KEY (`PeriodID`),
  KEY `TenantID` (`TenantID`),
  CONSTRAINT `fiscal_periods_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `fiscal_periods`
--

LOCK TABLES `fiscal_periods` WRITE;
/*!40000 ALTER TABLE `fiscal_periods` DISABLE KEYS */;
INSERT INTO `fiscal_periods` VALUES (1,1,'FY 2026 (Auto-Created)','2026-01-01','2026-12-31','Open');
/*!40000 ALTER TABLE `fiscal_periods` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `fixed_asset_depreciation`
--

DROP TABLE IF EXISTS `fixed_asset_depreciation`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `fixed_asset_depreciation` (
  `DepreciationEntryID` int NOT NULL AUTO_INCREMENT,
  `AssetID` int NOT NULL,
  `DepreciationDate` date NOT NULL COMMENT 'تاريخ تسجيل الإهلاك',
  `Amount` decimal(18,2) NOT NULL COMMENT 'مبلغ الإهلاك لهذه الفترة',
  `JournalID` int DEFAULT NULL,
  PRIMARY KEY (`DepreciationEntryID`),
  KEY `AssetID` (`AssetID`),
  KEY `JournalID` (`JournalID`),
  CONSTRAINT `fixed_asset_depreciation_ibfk_1` FOREIGN KEY (`AssetID`) REFERENCES `fixed_assets` (`AssetID`) ON DELETE CASCADE,
  CONSTRAINT `fixed_asset_depreciation_ibfk_2` FOREIGN KEY (`JournalID`) REFERENCES `journal_headers` (`JournalID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `fixed_asset_depreciation`
--

LOCK TABLES `fixed_asset_depreciation` WRITE;
/*!40000 ALTER TABLE `fixed_asset_depreciation` DISABLE KEYS */;
/*!40000 ALTER TABLE `fixed_asset_depreciation` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `fixed_assets`
--

DROP TABLE IF EXISTS `fixed_assets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `fixed_assets` (
  `AssetID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `AssetCode` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'رمز فريد للأصل',
  `AssetName` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'اسم الأصل (مثال: لابتوب ديل)',
  `PurchaseDate` date NOT NULL,
  `PurchaseCost` decimal(18,2) NOT NULL COMMENT 'تكلفة الشراء الأصلية',
  `DepreciationMethod` enum('Straight-Line','None') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Straight-Line' COMMENT 'طريقة الإهلاك',
  `UsefulLife_Years` decimal(5,2) NOT NULL COMMENT 'العمر الإنتاجي بالسنوات',
  `SalvageValue` decimal(18,2) NOT NULL DEFAULT '0.00' COMMENT 'القيمة التخريدية في نهاية عمره',
  `Asset_GL_AccountID` int NOT NULL COMMENT 'حساب الأصل في شجرة الحسابات',
  `AccumulatedDepreciation_GL_AccountID` int NOT NULL COMMENT 'حساب مجمع الإهلاك',
  `DepreciationExpense_GL_AccountID` int NOT NULL COMMENT 'حساب مصروف الإهلاك',
  `Status` enum('In-Service','Sold','Disposed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'In-Service',
  PRIMARY KEY (`AssetID`),
  UNIQUE KEY `idx_tenant_asset_code` (`TenantID`,`AssetCode`),
  KEY `Asset_GL_AccountID` (`Asset_GL_AccountID`),
  KEY `AccumulatedDepreciation_GL_AccountID` (`AccumulatedDepreciation_GL_AccountID`),
  KEY `DepreciationExpense_GL_AccountID` (`DepreciationExpense_GL_AccountID`),
  CONSTRAINT `fixed_assets_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `fixed_assets_ibfk_2` FOREIGN KEY (`Asset_GL_AccountID`) REFERENCES `chartofaccounts` (`AccountID`),
  CONSTRAINT `fixed_assets_ibfk_3` FOREIGN KEY (`AccumulatedDepreciation_GL_AccountID`) REFERENCES `chartofaccounts` (`AccountID`),
  CONSTRAINT `fixed_assets_ibfk_4` FOREIGN KEY (`DepreciationExpense_GL_AccountID`) REFERENCES `chartofaccounts` (`AccountID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `fixed_assets`
--

LOCK TABLES `fixed_assets` WRITE;
/*!40000 ALTER TABLE `fixed_assets` DISABLE KEYS */;
/*!40000 ALTER TABLE `fixed_assets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `general_expense_vouchers`
--

DROP TABLE IF EXISTS `general_expense_vouchers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `general_expense_vouchers` (
  `VoucherID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `VoucherDate` date NOT NULL,
  `PayeeName` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'اسم المستفيد (مثال: شركة الكهرباء)',
  `Amount_Local` decimal(18,2) NOT NULL,
  `PaymentMethod` enum('BankTransfer','Cash','Check','CreditCard') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `BankAccountID` int DEFAULT NULL COMMENT 'الحساب البنكي الذي تم الدفع منه',
  `Description` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'وصف المصروف (مثال: فاتورة كهرباء شهر 5)',
  `Expense_GL_AccountID` int NOT NULL COMMENT 'حساب المصروف في شجرة الحسابات',
  `JournalID` int DEFAULT NULL,
  PRIMARY KEY (`VoucherID`),
  KEY `TenantID` (`TenantID`),
  KEY `BankAccountID` (`BankAccountID`),
  KEY `Expense_GL_AccountID` (`Expense_GL_AccountID`),
  KEY `JournalID` (`JournalID`),
  CONSTRAINT `general_expense_vouchers_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `general_expense_vouchers_ibfk_2` FOREIGN KEY (`BankAccountID`) REFERENCES `bank_accounts` (`BankAccountID`),
  CONSTRAINT `general_expense_vouchers_ibfk_3` FOREIGN KEY (`Expense_GL_AccountID`) REFERENCES `chartofaccounts` (`AccountID`),
  CONSTRAINT `general_expense_vouchers_ibfk_4` FOREIGN KEY (`JournalID`) REFERENCES `journal_headers` (`JournalID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `general_expense_vouchers`
--

LOCK TABLES `general_expense_vouchers` WRITE;
/*!40000 ALTER TABLE `general_expense_vouchers` DISABLE KEYS */;
/*!40000 ALTER TABLE `general_expense_vouchers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `incoterms`
--

DROP TABLE IF EXISTS `incoterms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `incoterms` (
  `IncotermID` int NOT NULL AUTO_INCREMENT,
  `Code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Description` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`IncotermID`),
  UNIQUE KEY `Code` (`Code`)
) ENGINE=InnoDB AUTO_INCREMENT=25 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `incoterms`
--

LOCK TABLES `incoterms` WRITE;
/*!40000 ALTER TABLE `incoterms` DISABLE KEYS */;
INSERT INTO `incoterms` VALUES (1,'EXW','Ex Works - ??????? ?? ??????'),(2,'FOB','Free On Board - ??????? ??? ??? ???????'),(3,'CFR','Cost and Freight - ??????? ??????'),(4,'CIF','Cost, Insurance, and Freight - ??????? ???????? ??????'),(5,'DAP','Delivered at Place - ??????? ?? ?????? ??????'),(6,'DDP','Delivered Duty Paid - ????? ???? ??????');
/*!40000 ALTER TABLE `incoterms` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `journal_headers`
--

DROP TABLE IF EXISTS `journal_headers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `journal_headers` (
  `JournalID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `TransactionDate` date DEFAULT NULL,
  `ReferenceType` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ReferenceID` int DEFAULT NULL,
  `Description` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `IsPosted` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`JournalID`),
  KEY `idx_journal_headers_date` (`TenantID`,`TransactionDate`),
  CONSTRAINT `fk_journal_headers_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `journal_headers`
--

LOCK TABLES `journal_headers` WRITE;
/*!40000 ALTER TABLE `journal_headers` DISABLE KEYS */;
INSERT INTO `journal_headers` VALUES (1,1,'2026-01-31','PARTNER_OPENING',1,'Opening Balance for ففف',1),(2,1,'2026-02-03',NULL,NULL,'',0);
/*!40000 ALTER TABLE `journal_headers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `journal_lines`
--

DROP TABLE IF EXISTS `journal_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `journal_lines` (
  `JLineID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `JournalID` int DEFAULT NULL,
  `AccountID` int DEFAULT NULL,
  `Debit` decimal(18,2) DEFAULT '0.00',
  `Credit` decimal(18,2) DEFAULT '0.00',
  `PartnerID` int DEFAULT NULL,
  `CostCenterID` int DEFAULT NULL,
  `ProjectID` int DEFAULT NULL,
  PRIMARY KEY (`JLineID`),
  KEY `JournalID` (`JournalID`),
  KEY `AccountID` (`AccountID`),
  KEY `fk_journal_lines_tenants` (`TenantID`),
  KEY `fk_journal_projects` (`ProjectID`),
  KEY `fk_journal_costcenters` (`CostCenterID`),
  KEY `fk_jline_partner` (`PartnerID`),
  CONSTRAINT `fk_jline_partner` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`) ON DELETE SET NULL,
  CONSTRAINT `fk_journal_costcenters` FOREIGN KEY (`CostCenterID`) REFERENCES `cost_centers` (`CostCenterID`),
  CONSTRAINT `fk_journal_lines_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `fk_journal_projects` FOREIGN KEY (`ProjectID`) REFERENCES `projects` (`ProjectID`),
  CONSTRAINT `journal_lines_ibfk_1` FOREIGN KEY (`JournalID`) REFERENCES `journal_headers` (`JournalID`),
  CONSTRAINT `journal_lines_ibfk_2` FOREIGN KEY (`AccountID`) REFERENCES `chartofaccounts` (`AccountID`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `journal_lines`
--

LOCK TABLES `journal_lines` WRITE;
/*!40000 ALTER TABLE `journal_lines` DISABLE KEYS */;
INSERT INTO `journal_lines` VALUES (7,1,2,9,0.00,2000.00,NULL,NULL,NULL),(8,1,2,10,2000.00,0.00,NULL,NULL,NULL);
/*!40000 ALTER TABLE `journal_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `landed_cost_transactions`
--

DROP TABLE IF EXISTS `landed_cost_transactions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `landed_cost_transactions` (
  `CostID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ShipmentID` int DEFAULT NULL,
  `PartnerID` int DEFAULT NULL,
  `CostType` enum('Freight','Customs','Insurance','Handling','InlandTransport','Other') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `CurrencyID` int DEFAULT NULL,
  `Amount_Foreign` decimal(18,2) DEFAULT NULL,
  `ExchangeRate` decimal(18,6) DEFAULT NULL,
  `Amount_Local` decimal(18,2) DEFAULT NULL,
  `AllocationMethod` enum('ByValue','ByVolume','ByWeight','Manual') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `InvoiceDate` date DEFAULT NULL,
  `Notes` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`CostID`),
  KEY `ShipmentID` (`ShipmentID`),
  KEY `PartnerID` (`PartnerID`),
  KEY `fk_landed_cost_tenants` (`TenantID`),
  CONSTRAINT `fk_landed_cost_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `landed_cost_transactions_ibfk_1` FOREIGN KEY (`ShipmentID`) REFERENCES `shipments` (`ShipmentID`),
  CONSTRAINT `landed_cost_transactions_ibfk_2` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `landed_cost_transactions`
--

LOCK TABLES `landed_cost_transactions` WRITE;
/*!40000 ALTER TABLE `landed_cost_transactions` DISABLE KEYS */;
/*!40000 ALTER TABLE `landed_cost_transactions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `letters_of_credit`
--

DROP TABLE IF EXISTS `letters_of_credit`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `letters_of_credit` (
  `LC_ID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `LC_Number` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `IssuingBankID` int NOT NULL COMMENT 'حسابنا البنكي الذي أصدر الاعتماد',
  `BeneficiaryID` int NOT NULL COMMENT 'المورد المستفيد',
  `LC_Amount` decimal(18,2) NOT NULL,
  `CurrencyID` int NOT NULL,
  `IssueDate` date DEFAULT NULL,
  `ExpiryDate` date DEFAULT NULL,
  `Status` enum('Draft','Issued','Amended','Closed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Draft',
  PRIMARY KEY (`LC_ID`),
  UNIQUE KEY `LC_Number` (`LC_Number`),
  KEY `TenantID` (`TenantID`),
  KEY `IssuingBankID` (`IssuingBankID`),
  KEY `BeneficiaryID` (`BeneficiaryID`),
  KEY `CurrencyID` (`CurrencyID`),
  CONSTRAINT `letters_of_credit_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `letters_of_credit_ibfk_2` FOREIGN KEY (`IssuingBankID`) REFERENCES `bank_accounts` (`BankAccountID`),
  CONSTRAINT `letters_of_credit_ibfk_3` FOREIGN KEY (`BeneficiaryID`) REFERENCES `partners` (`PartnerID`),
  CONSTRAINT `letters_of_credit_ibfk_4` FOREIGN KEY (`CurrencyID`) REFERENCES `currencies` (`CurrencyID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `letters_of_credit`
--

LOCK TABLES `letters_of_credit` WRITE;
/*!40000 ALTER TABLE `letters_of_credit` DISABLE KEYS */;
/*!40000 ALTER TABLE `letters_of_credit` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `logistics_clearance`
--

DROP TABLE IF EXISTS `logistics_clearance`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `logistics_clearance` (
  `ClearanceID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ShipmentID` int NOT NULL,
  `CustomsBrokerID` int DEFAULT NULL COMMENT 'المخلص الجمركي',
  `DeclarationNumber` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'رقم البيان الجمركي',
  `ClearanceDate` date DEFAULT NULL,
  `Status` enum('Processing','Cleared','Hold') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Processing',
  `Notes` mediumtext COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`ClearanceID`),
  UNIQUE KEY `idx_shipment_clearance` (`ShipmentID`),
  KEY `fk_clearance_tenant` (`TenantID`),
  KEY `fk_clearance_broker` (`CustomsBrokerID`),
  CONSTRAINT `fk_clearance_broker` FOREIGN KEY (`CustomsBrokerID`) REFERENCES `partners` (`PartnerID`),
  CONSTRAINT `fk_clearance_shipment` FOREIGN KEY (`ShipmentID`) REFERENCES `logistics_shipments` (`ShipmentID`),
  CONSTRAINT `fk_clearance_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `logistics_clearance`
--

LOCK TABLES `logistics_clearance` WRITE;
/*!40000 ALTER TABLE `logistics_clearance` DISABLE KEYS */;
/*!40000 ALTER TABLE `logistics_clearance` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `logistics_deal_items`
--

DROP TABLE IF EXISTS `logistics_deal_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `logistics_deal_items` (
  `DealItemID` int NOT NULL AUTO_INCREMENT,
  `DealID` int NOT NULL,
  `ProductID` int NOT NULL,
  `Quantity` decimal(18,4) NOT NULL,
  `UnitPrice` decimal(18,4) NOT NULL,
  `Notes` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`DealItemID`),
  KEY `idx_deal_item` (`DealID`),
  KEY `fk_dealitem_product` (`ProductID`),
  CONSTRAINT `fk_dealitem_deal` FOREIGN KEY (`DealID`) REFERENCES `logistics_deals` (`DealID`) ON DELETE CASCADE,
  CONSTRAINT `fk_dealitem_product` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `logistics_deal_items`
--

LOCK TABLES `logistics_deal_items` WRITE;
/*!40000 ALTER TABLE `logistics_deal_items` DISABLE KEYS */;
INSERT INTO `logistics_deal_items` VALUES (1,1,1,1.0000,5.0000,'');
/*!40000 ALTER TABLE `logistics_deal_items` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `logistics_deals`
--

DROP TABLE IF EXISTS `logistics_deals`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `logistics_deals` (
  `DealID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `RefNumber` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'رقم مرجعي للصفقة',
  `PartnerID` int NOT NULL COMMENT 'المورد - Supplier',
  `OrderDate` date NOT NULL,
  `TotalAmount` decimal(18,2) NOT NULL DEFAULT '0.00',
  `CurrencyID` int NOT NULL,
  `Status` enum('Open','Shipped','Cleared','Closed','Cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Open',
  `Notes` mediumtext COLLATE utf8mb4_unicode_ci,
  `CreatedAt` datetime DEFAULT CURRENT_TIMESTAMP,
  `CreatedBy_UserID` int DEFAULT NULL,
  `pi_number` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Supplier Proforma Invoice Number',
  `description` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Short description of the deal payload',
  `shipping_method` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'Sea' COMMENT 'Sea, Air, Land',
  `incoterms` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT 'FOB' COMMENT 'FOB, EXW, CIF, etc.',
  `payment_method` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'T/T' COMMENT 'T/T 30%, LC, etc.',
  `production_days` int DEFAULT '0' COMMENT 'Estimated manufacturing time',
  `delivery_days` int DEFAULT '0' COMMENT 'Estimated shipping time',
  `total_cbm` decimal(10,3) DEFAULT '0.000' COMMENT 'Total Volume in CBM',
  `total_weight` decimal(10,3) DEFAULT '0.000' COMMENT 'Total Weight in KG',
  `certificates` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Comma separated list: CE, ISO, etc.',
  `shipping_cost_estimate` decimal(18,2) DEFAULT '0.00' COMMENT 'Estimated shipping cost',
  `discount_amount` decimal(18,2) DEFAULT '0.00' COMMENT 'Discount on products',
  `fees_percentage` decimal(5,2) DEFAULT '0.00' COMMENT 'Additional Tax/Customs Estimate %',
  `is_shipping_included` tinyint(1) DEFAULT '0',
  `alibaba_link` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Link to Alibaba or Supplier Website',
  `IsPosted` tinyint(1) DEFAULT '0',
  `JournalID` int DEFAULT NULL,
  PRIMARY KEY (`DealID`),
  KEY `idx_tenant_deal` (`TenantID`),
  KEY `fk_deal_partner` (`PartnerID`),
  CONSTRAINT `fk_deal_partner` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`),
  CONSTRAINT `fk_deal_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `logistics_deals`
--

LOCK TABLES `logistics_deals` WRITE;
/*!40000 ALTER TABLE `logistics_deals` DISABLE KEYS */;
INSERT INTO `logistics_deals` VALUES (1,1,'5',11,'2026-02-05',5.00,1,'Open','','2026-02-05 12:47:02',NULL,'','','Sea','FOB','T/T 30%',0,0,0.000,0.000,'',0.00,0.00,0.00,0,'',0,NULL);
/*!40000 ALTER TABLE `logistics_deals` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `logistics_expenses`
--

DROP TABLE IF EXISTS `logistics_expenses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `logistics_expenses` (
  `ExpenseID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `RelatedType` enum('Deal','Shipment','Clearance') COLLATE utf8mb4_unicode_ci NOT NULL,
  `RelatedID` int NOT NULL,
  `ExpenseAccountID` int NOT NULL COMMENT 'FK to chartofaccounts (Expense)',
  `PayableAccountID` int NOT NULL COMMENT 'FK to chartofaccounts (Liability/Bank)',
  `Description` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `Amount` decimal(18,2) NOT NULL,
  `CurrencyID` int NOT NULL DEFAULT '1',
  `InvoiceNumber` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `InvoiceDate` date DEFAULT NULL,
  `IsPosted` tinyint(1) DEFAULT '0' COMMENT 'Posted to Accounting?',
  `JournalID` int DEFAULT NULL COMMENT 'Link to the generated Journal Entry',
  PRIMARY KEY (`ExpenseID`),
  KEY `idx_related` (`RelatedType`,`RelatedID`),
  KEY `idx_journal` (`JournalID`),
  KEY `fk_expense_tenant` (`TenantID`),
  KEY `fk_expense_debit_account` (`ExpenseAccountID`),
  KEY `fk_expense_credit_account` (`PayableAccountID`),
  CONSTRAINT `fk_expense_acc_credit` FOREIGN KEY (`PayableAccountID`) REFERENCES `chartofaccounts` (`AccountID`),
  CONSTRAINT `fk_expense_acc_debit` FOREIGN KEY (`ExpenseAccountID`) REFERENCES `chartofaccounts` (`AccountID`),
  CONSTRAINT `fk_expense_credit_account` FOREIGN KEY (`PayableAccountID`) REFERENCES `chartofaccounts` (`AccountID`),
  CONSTRAINT `fk_expense_debit_account` FOREIGN KEY (`ExpenseAccountID`) REFERENCES `chartofaccounts` (`AccountID`),
  CONSTRAINT `fk_expense_journal` FOREIGN KEY (`JournalID`) REFERENCES `journal_headers` (`JournalID`) ON DELETE SET NULL,
  CONSTRAINT `fk_expense_journal_link` FOREIGN KEY (`JournalID`) REFERENCES `journal_headers` (`JournalID`) ON DELETE SET NULL,
  CONSTRAINT `fk_expense_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `logistics_expenses`
--

LOCK TABLES `logistics_expenses` WRITE;
/*!40000 ALTER TABLE `logistics_expenses` DISABLE KEYS */;
/*!40000 ALTER TABLE `logistics_expenses` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `logistics_shipment_deals`
--

DROP TABLE IF EXISTS `logistics_shipment_deals`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `logistics_shipment_deals` (
  `LinkID` int NOT NULL AUTO_INCREMENT,
  `ShipmentID` int NOT NULL,
  `DealID` int NOT NULL,
  PRIMARY KEY (`LinkID`),
  UNIQUE KEY `idx_shipment_deal_unique` (`ShipmentID`,`DealID`),
  KEY `fk_link_deal` (`DealID`),
  CONSTRAINT `fk_link_deal` FOREIGN KEY (`DealID`) REFERENCES `logistics_deals` (`DealID`),
  CONSTRAINT `fk_link_shipment` FOREIGN KEY (`ShipmentID`) REFERENCES `logistics_shipments` (`ShipmentID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `logistics_shipment_deals`
--

LOCK TABLES `logistics_shipment_deals` WRITE;
/*!40000 ALTER TABLE `logistics_shipment_deals` DISABLE KEYS */;
/*!40000 ALTER TABLE `logistics_shipment_deals` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `logistics_shipments`
--

DROP TABLE IF EXISTS `logistics_shipments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `logistics_shipments` (
  `ShipmentID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ShipmentNumber` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `ShippingAgentID` int DEFAULT NULL COMMENT 'وكيل الشحن',
  `BillOfLading` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'رقم البوليصة',
  `ContainerNumber` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `DepartureDate` date DEFAULT NULL,
  `ArrivalDate` date DEFAULT NULL,
  `Status` enum('Pending','In-Transit','Arrived','Clearing','Cleared') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Pending',
  `Notes` mediumtext COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`ShipmentID`),
  KEY `idx_tenant_shipment` (`TenantID`),
  KEY `fk_shipment_agent` (`ShippingAgentID`),
  CONSTRAINT `fk_shipment_agent` FOREIGN KEY (`ShippingAgentID`) REFERENCES `partners` (`PartnerID`),
  CONSTRAINT `fk_shipment_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `logistics_shipments`
--

LOCK TABLES `logistics_shipments` WRITE;
/*!40000 ALTER TABLE `logistics_shipments` DISABLE KEYS */;
/*!40000 ALTER TABLE `logistics_shipments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `maintenance_spare_parts_usage`
--

DROP TABLE IF EXISTS `maintenance_spare_parts_usage`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `maintenance_spare_parts_usage` (
  `UsageID` int NOT NULL AUTO_INCREMENT,
  `WorkOrderID` int NOT NULL,
  `ProductID` int NOT NULL COMMENT 'قطعة الغيار (معرفة كمنتج في المخزون)',
  `QuantityUsed` decimal(18,2) NOT NULL,
  PRIMARY KEY (`UsageID`),
  KEY `WorkOrderID` (`WorkOrderID`),
  KEY `ProductID` (`ProductID`),
  CONSTRAINT `maintenance_spare_parts_usage_ibfk_1` FOREIGN KEY (`WorkOrderID`) REFERENCES `maintenance_work_orders` (`WorkOrderID`) ON DELETE CASCADE,
  CONSTRAINT `maintenance_spare_parts_usage_ibfk_2` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `maintenance_spare_parts_usage`
--

LOCK TABLES `maintenance_spare_parts_usage` WRITE;
/*!40000 ALTER TABLE `maintenance_spare_parts_usage` DISABLE KEYS */;
/*!40000 ALTER TABLE `maintenance_spare_parts_usage` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `maintenance_tasks`
--

DROP TABLE IF EXISTS `maintenance_tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `maintenance_tasks` (
  `TaskID` int NOT NULL AUTO_INCREMENT,
  `WorkOrderID` int NOT NULL,
  `Description` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'مثل: تغيير زيت المحرك',
  `IsCompleted` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`TaskID`),
  KEY `WorkOrderID` (`WorkOrderID`),
  CONSTRAINT `maintenance_tasks_ibfk_1` FOREIGN KEY (`WorkOrderID`) REFERENCES `maintenance_work_orders` (`WorkOrderID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `maintenance_tasks`
--

LOCK TABLES `maintenance_tasks` WRITE;
/*!40000 ALTER TABLE `maintenance_tasks` DISABLE KEYS */;
/*!40000 ALTER TABLE `maintenance_tasks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `maintenance_work_orders`
--

DROP TABLE IF EXISTS `maintenance_work_orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `maintenance_work_orders` (
  `WorkOrderID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `AssetID` int NOT NULL COMMENT 'الأصل الذي تتم صيانته',
  `Title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'مثل: صيانة دورية للسيارة 123',
  `MaintenanceType` enum('Corrective','Preventive') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `ScheduledDate` date DEFAULT NULL,
  `CompletionDate` date DEFAULT NULL,
  `Status` enum('Draft','Scheduled','InProgress','Done','Cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Draft',
  `AssignedTo_EmployeeID` int DEFAULT NULL,
  PRIMARY KEY (`WorkOrderID`),
  KEY `TenantID` (`TenantID`),
  KEY `AssetID` (`AssetID`),
  KEY `AssignedTo_EmployeeID` (`AssignedTo_EmployeeID`),
  CONSTRAINT `maintenance_work_orders_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `maintenance_work_orders_ibfk_2` FOREIGN KEY (`AssetID`) REFERENCES `fixed_assets` (`AssetID`),
  CONSTRAINT `maintenance_work_orders_ibfk_3` FOREIGN KEY (`AssignedTo_EmployeeID`) REFERENCES `employees` (`EmployeeID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `maintenance_work_orders`
--

LOCK TABLES `maintenance_work_orders` WRITE;
/*!40000 ALTER TABLE `maintenance_work_orders` DISABLE KEYS */;
/*!40000 ALTER TABLE `maintenance_work_orders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `manufacturing_orders`
--

DROP TABLE IF EXISTS `manufacturing_orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manufacturing_orders` (
  `MO_ID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ProductID_To_Manufacture` int NOT NULL COMMENT 'المنتج المراد تصنيعه',
  `BOM_ID_Used` int NOT NULL COMMENT 'قائمة المواد التي تم استخدامها',
  `Quantity_To_Produce` decimal(18,2) NOT NULL,
  `OrderDate` date DEFAULT NULL,
  `CompletionDate` date DEFAULT NULL,
  `Status` enum('Draft','Confirmed','InProgress','Done','Cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Draft',
  PRIMARY KEY (`MO_ID`),
  KEY `TenantID` (`TenantID`),
  KEY `ProductID_To_Manufacture` (`ProductID_To_Manufacture`),
  KEY `BOM_ID_Used` (`BOM_ID_Used`),
  CONSTRAINT `manufacturing_orders_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `manufacturing_orders_ibfk_2` FOREIGN KEY (`ProductID_To_Manufacture`) REFERENCES `products` (`ProductID`),
  CONSTRAINT `manufacturing_orders_ibfk_3` FOREIGN KEY (`BOM_ID_Used`) REFERENCES `bom` (`BOM_ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `manufacturing_orders`
--

LOCK TABLES `manufacturing_orders` WRITE;
/*!40000 ALTER TABLE `manufacturing_orders` DISABLE KEYS */;
/*!40000 ALTER TABLE `manufacturing_orders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `partner_bank_accounts`
--

DROP TABLE IF EXISTS `partner_bank_accounts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `partner_bank_accounts` (
  `PartnerBankAccountID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `PartnerID` int NOT NULL,
  `BankName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `AccountNumber` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `IBAN` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `SwiftCode` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `BankAddress` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `BeneficiaryName` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `CurrencyID` int NOT NULL,
  `IsActive` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`PartnerBankAccountID`),
  UNIQUE KEY `idx_tenant_partner_account` (`TenantID`,`PartnerID`,`AccountNumber`),
  KEY `PartnerID` (`PartnerID`),
  KEY `CurrencyID` (`CurrencyID`),
  CONSTRAINT `partner_bank_accounts_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `partner_bank_accounts_ibfk_2` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`) ON DELETE CASCADE,
  CONSTRAINT `partner_bank_accounts_ibfk_3` FOREIGN KEY (`CurrencyID`) REFERENCES `currencies` (`CurrencyID`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `partner_bank_accounts`
--

LOCK TABLES `partner_bank_accounts` WRITE;
/*!40000 ALTER TABLE `partner_bank_accounts` DISABLE KEYS */;
INSERT INTO `partner_bank_accounts` VALUES (5,1,1,'بنك','111','55','555','قفين','فادي',1,1);
/*!40000 ALTER TABLE `partner_bank_accounts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `partner_groups`
--

DROP TABLE IF EXISTS `partner_groups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `partner_groups` (
  `GroupID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `Name` varchar(100) NOT NULL COMMENT 'اسم المجموعة: موردين محليين، عملاء جملة...',
  `Type` enum('Customer','Supplier') NOT NULL,
  `AccountReceivableID` int DEFAULT NULL COMMENT 'حساب الذمم المدينة الرئيسي لهذه المجموعة',
  `AccountPayableID` int DEFAULT NULL COMMENT 'حساب الذمم الدائنة الرئيسي لهذه المجموعة',
  PRIMARY KEY (`GroupID`),
  KEY `TenantID` (`TenantID`),
  KEY `AccountReceivableID` (`AccountReceivableID`),
  KEY `AccountPayableID` (`AccountPayableID`),
  CONSTRAINT `partner_groups_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `partner_groups_ibfk_2` FOREIGN KEY (`AccountReceivableID`) REFERENCES `chartofaccounts` (`AccountID`),
  CONSTRAINT `partner_groups_ibfk_3` FOREIGN KEY (`AccountPayableID`) REFERENCES `chartofaccounts` (`AccountID`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `partner_groups`
--

LOCK TABLES `partner_groups` WRITE;
/*!40000 ALTER TABLE `partner_groups` DISABLE KEYS */;
INSERT INTO `partner_groups` VALUES (1,1,'شركات شحن (Freight Forwarders)','Supplier',NULL,27),(2,1,'مخلصين جمركيين (Customs Brokers)','Supplier',NULL,28),(3,1,'ناقلين محليين (Local Transporters)','Supplier',NULL,29);
/*!40000 ALTER TABLE `partner_groups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `partners`
--

DROP TABLE IF EXISTS `partners`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `partners` (
  `PartnerID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `Name` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `LegalName` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `StreetAddress` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'عنوان الشارع',
  `City` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'المدينة',
  `StateOrProvince` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'المنطقة أو المحافظة',
  `PostalCode` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'الرمز البريدي',
  `Type` enum('Customer','Supplier','FreightForwarder','CustomsBroker','LocalTransporter') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `TaxNumber` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Country` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `CreditLimit` decimal(18,2) DEFAULT NULL,
  `ImagePath` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'مسار صورة الشعار أو الملف الشخصي',
  `CreatedAt` datetime DEFAULT CURRENT_TIMESTAMP,
  `OpeningBalance` decimal(18,2) DEFAULT '0.00' COMMENT 'الرصيد الافتتاحي',
  `OpeningBalanceDate` date DEFAULT NULL COMMENT 'تاريخ الرصيد الافتتاحي',
  `CurrencyID` int DEFAULT NULL COMMENT 'عملة الرصيد',
  `GroupID` int DEFAULT NULL,
  `LinkedAccountID` int DEFAULT NULL,
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`PartnerID`),
  KEY `fk_partners_tenants` (`TenantID`),
  KEY `partners_ibfk_currency` (`CurrencyID`),
  KEY `fk_partner_group` (`GroupID`),
  KEY `fk_partners_linked_account` (`LinkedAccountID`),
  KEY `idx_is_deleted` (`is_deleted`),
  CONSTRAINT `fk_partner_group` FOREIGN KEY (`GroupID`) REFERENCES `partner_groups` (`GroupID`),
  CONSTRAINT `fk_partners_linked_account` FOREIGN KEY (`LinkedAccountID`) REFERENCES `chartofaccounts` (`AccountID`) ON DELETE SET NULL,
  CONSTRAINT `fk_partners_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `partners_ibfk_currency` FOREIGN KEY (`CurrencyID`) REFERENCES `currencies` (`CurrencyID`)
) ENGINE=InnoDB AUTO_INCREMENT=14 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='يستخدم لتخزين الاسم الرسمي/القانوني الكامل للشريك (مورد أو عميل)';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `partners`
--

LOCK TABLES `partners` WRITE;
/*!40000 ALTER TABLE `partners` DISABLE KEYS */;
INSERT INTO `partners` VALUES (1,1,'ففف','ؤءرء','رءؤ','لاب','لال','55','FreightForwarder','55','059','thapet64@gmail.com','صين',1000.00,NULL,'2026-01-31 18:03:06',5.00,'2026-01-31',NULL,NULL,22,0),(2,1,'احمر','red','','','','','FreightForwarder','','','','',0.00,NULL,'2026-02-02 09:08:10',0.00,'2026-02-02',NULL,NULL,16,0),(3,1,'يويو',NULL,NULL,NULL,NULL,NULL,'FreightForwarder',NULL,NULL,NULL,NULL,NULL,NULL,'2026-02-02 09:25:08',0.00,'2026-02-02',NULL,NULL,24,0),(4,1,'ةة',NULL,NULL,NULL,NULL,NULL,'FreightForwarder',NULL,NULL,NULL,NULL,NULL,NULL,'2026-02-02 09:31:35',0.00,'2026-02-02',NULL,NULL,25,0),(5,1,'تكفاين',NULL,NULL,NULL,NULL,NULL,'Supplier',NULL,NULL,NULL,NULL,NULL,NULL,'2026-02-02 09:32:20',0.00,'2026-02-02',NULL,NULL,26,0),(6,1,'المورد',NULL,NULL,NULL,NULL,NULL,'FreightForwarder',NULL,NULL,NULL,NULL,NULL,NULL,'2026-02-02 09:45:31',0.00,'2026-02-02',NULL,NULL,30,0),(7,1,'مورد اختبار',NULL,NULL,NULL,NULL,NULL,'Supplier',NULL,NULL,NULL,NULL,NULL,NULL,'2026-02-02 10:22:48',0.00,'2026-02-02',NULL,NULL,31,0),(8,1,'عميل اختبار',NULL,NULL,NULL,NULL,NULL,'Customer',NULL,NULL,NULL,NULL,NULL,NULL,'2026-02-02 10:22:58',0.00,'2026-02-02',NULL,NULL,32,0),(9,1,'مخلص اختبار',NULL,NULL,NULL,NULL,NULL,'CustomsBroker',NULL,NULL,NULL,NULL,NULL,NULL,'2026-02-02 10:23:14',0.00,'2026-02-02',NULL,NULL,33,0),(10,1,'مخلص اختبار',NULL,NULL,NULL,NULL,NULL,'CustomsBroker',NULL,NULL,NULL,NULL,NULL,NULL,'2026-02-02 10:23:15',0.00,'2026-02-02',NULL,NULL,34,0),(11,1,'مجموع15','','','','','','Supplier','','','','',0.00,NULL,'2026-02-02 16:33:20',0.00,'2026-02-02',NULL,NULL,35,0),(12,1,'يويو',NULL,NULL,NULL,NULL,NULL,'FreightForwarder',NULL,NULL,NULL,NULL,NULL,NULL,'2026-02-02 16:33:31',0.00,'2026-02-02',NULL,NULL,36,0),(13,1,'تراد','','','','','','Customer','','','','',0.00,NULL,'2026-02-02 16:33:43',0.00,'2026-02-02',NULL,NULL,37,0);
/*!40000 ALTER TABLE `partners` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `payroll_runs`
--

DROP TABLE IF EXISTS `payroll_runs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payroll_runs` (
  `RunID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `PayPeriodName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'مثل: راتب شهر يناير 2026',
  `PayPeriodStartDate` date DEFAULT NULL,
  `PayPeriodEndDate` date DEFAULT NULL,
  `Status` enum('Draft','Confirmed','Paid') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Draft',
  PRIMARY KEY (`RunID`),
  KEY `TenantID` (`TenantID`),
  CONSTRAINT `payroll_runs_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payroll_runs`
--

LOCK TABLES `payroll_runs` WRITE;
/*!40000 ALTER TABLE `payroll_runs` DISABLE KEYS */;
/*!40000 ALTER TABLE `payroll_runs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `payroll_slips`
--

DROP TABLE IF EXISTS `payroll_slips`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `payroll_slips` (
  `SlipID` int NOT NULL AUTO_INCREMENT,
  `RunID` int NOT NULL,
  `EmployeeID` int NOT NULL,
  `BaseSalary` decimal(18,2) DEFAULT '0.00',
  `Deductions` decimal(18,2) DEFAULT '0.00',
  `Bonuses` decimal(18,2) DEFAULT '0.00',
  `NetPay` decimal(18,2) NOT NULL,
  `JournalID` int DEFAULT NULL,
  PRIMARY KEY (`SlipID`),
  KEY `RunID` (`RunID`),
  KEY `EmployeeID` (`EmployeeID`),
  CONSTRAINT `payroll_slips_ibfk_1` FOREIGN KEY (`RunID`) REFERENCES `payroll_runs` (`RunID`) ON DELETE CASCADE,
  CONSTRAINT `payroll_slips_ibfk_2` FOREIGN KEY (`EmployeeID`) REFERENCES `employees` (`EmployeeID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `payroll_slips`
--

LOCK TABLES `payroll_slips` WRITE;
/*!40000 ALTER TABLE `payroll_slips` DISABLE KEYS */;
/*!40000 ALTER TABLE `payroll_slips` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `po_lines`
--

DROP TABLE IF EXISTS `po_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `po_lines` (
  `LineID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `PO_ID` int DEFAULT NULL,
  `LineType` enum('Product','Charge') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Product',
  `ProductID` int DEFAULT NULL,
  `ChargeTypeID` int DEFAULT NULL,
  `Quantity` decimal(18,2) DEFAULT NULL,
  `UnitPrice_Foreign` decimal(18,2) DEFAULT NULL,
  `Total_Foreign` decimal(18,2) GENERATED ALWAYS AS ((coalesce(`Quantity`,1) * `UnitPrice_Foreign`)) STORED,
  `TaxRateID` int DEFAULT NULL,
  `TaxAmount_Foreign` decimal(18,2) DEFAULT '0.00',
  PRIMARY KEY (`LineID`),
  KEY `PO_ID` (`PO_ID`),
  KEY `ProductID` (`ProductID`),
  KEY `fk_po_lines_chargetypes` (`ChargeTypeID`),
  KEY `fk_po_lines_tax` (`TaxRateID`),
  KEY `idx_po_lines_product` (`TenantID`,`ProductID`),
  CONSTRAINT `fk_po_lines_chargetypes` FOREIGN KEY (`ChargeTypeID`) REFERENCES `chargetypes` (`ChargeTypeID`),
  CONSTRAINT `fk_po_lines_tax` FOREIGN KEY (`TaxRateID`) REFERENCES `tax_rates` (`TaxRateID`),
  CONSTRAINT `fk_po_lines_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `po_lines_ibfk_1` FOREIGN KEY (`PO_ID`) REFERENCES `purchaseorders` (`PO_ID`),
  CONSTRAINT `po_lines_ibfk_2` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `po_lines`
--

LOCK TABLES `po_lines` WRITE;
/*!40000 ALTER TABLE `po_lines` DISABLE KEYS */;
/*!40000 ALTER TABLE `po_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `pos_payments`
--

DROP TABLE IF EXISTS `pos_payments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `pos_payments` (
  `PaymentID` int NOT NULL AUTO_INCREMENT,
  `SaleID` int NOT NULL,
  `PaymentMethod` enum('Cash','CreditCard','Other') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Amount` decimal(18,2) NOT NULL,
  PRIMARY KEY (`PaymentID`),
  KEY `SaleID` (`SaleID`),
  CONSTRAINT `pos_payments_ibfk_1` FOREIGN KEY (`SaleID`) REFERENCES `pos_sales` (`SaleID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pos_payments`
--

LOCK TABLES `pos_payments` WRITE;
/*!40000 ALTER TABLE `pos_payments` DISABLE KEYS */;
/*!40000 ALTER TABLE `pos_payments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `pos_sale_lines`
--

DROP TABLE IF EXISTS `pos_sale_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `pos_sale_lines` (
  `SaleLineID` int NOT NULL AUTO_INCREMENT,
  `SaleID` int NOT NULL,
  `ProductID` int NOT NULL,
  `Quantity` decimal(18,2) NOT NULL,
  `UnitPrice` decimal(18,2) NOT NULL,
  PRIMARY KEY (`SaleLineID`),
  KEY `SaleID` (`SaleID`),
  KEY `ProductID` (`ProductID`),
  CONSTRAINT `pos_sale_lines_ibfk_1` FOREIGN KEY (`SaleID`) REFERENCES `pos_sales` (`SaleID`) ON DELETE CASCADE,
  CONSTRAINT `pos_sale_lines_ibfk_2` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pos_sale_lines`
--

LOCK TABLES `pos_sale_lines` WRITE;
/*!40000 ALTER TABLE `pos_sale_lines` DISABLE KEYS */;
/*!40000 ALTER TABLE `pos_sale_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `pos_sales`
--

DROP TABLE IF EXISTS `pos_sales`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `pos_sales` (
  `SaleID` int NOT NULL AUTO_INCREMENT,
  `SessionID` int NOT NULL,
  `SaleDate` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `TotalAmount` decimal(18,2) NOT NULL,
  PRIMARY KEY (`SaleID`),
  KEY `SessionID` (`SessionID`),
  CONSTRAINT `pos_sales_ibfk_1` FOREIGN KEY (`SessionID`) REFERENCES `pos_sessions` (`SessionID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pos_sales`
--

LOCK TABLES `pos_sales` WRITE;
/*!40000 ALTER TABLE `pos_sales` DISABLE KEYS */;
/*!40000 ALTER TABLE `pos_sales` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `pos_sessions`
--

DROP TABLE IF EXISTS `pos_sessions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `pos_sessions` (
  `SessionID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `TerminalID` int NOT NULL,
  `UserID` int NOT NULL COMMENT 'المستخدم (الكاشير) الذي فتح الجلسة',
  `OpeningTime` datetime NOT NULL,
  `ClosingTime` datetime DEFAULT NULL,
  `OpeningBalance` decimal(18,2) NOT NULL COMMENT 'المبلغ النقدي في الدرج عند الفتح',
  `ClosingBalance` decimal(18,2) DEFAULT NULL COMMENT 'المبلغ النقدي في الدرج عند الإغلاق',
  `Status` enum('Open','Closed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Open',
  PRIMARY KEY (`SessionID`),
  KEY `TenantID` (`TenantID`),
  KEY `TerminalID` (`TerminalID`),
  KEY `UserID` (`UserID`),
  CONSTRAINT `pos_sessions_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `pos_sessions_ibfk_2` FOREIGN KEY (`TerminalID`) REFERENCES `pos_terminals` (`TerminalID`),
  CONSTRAINT `pos_sessions_ibfk_3` FOREIGN KEY (`UserID`) REFERENCES `users` (`UserID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pos_sessions`
--

LOCK TABLES `pos_sessions` WRITE;
/*!40000 ALTER TABLE `pos_sessions` DISABLE KEYS */;
/*!40000 ALTER TABLE `pos_sessions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `pos_terminals`
--

DROP TABLE IF EXISTS `pos_terminals`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `pos_terminals` (
  `TerminalID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `TerminalName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'مثل: كاشير 1 - الفرع الرئيسي',
  `WarehouseID` int NOT NULL COMMENT 'المخزن الذي يسحب منه هذا الكاشير',
  PRIMARY KEY (`TerminalID`),
  UNIQUE KEY `idx_tenant_terminal_name` (`TenantID`,`TerminalName`),
  KEY `WarehouseID` (`WarehouseID`),
  CONSTRAINT `pos_terminals_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `pos_terminals_ibfk_2` FOREIGN KEY (`WarehouseID`) REFERENCES `warehouses` (`WarehouseID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `pos_terminals`
--

LOCK TABLES `pos_terminals` WRITE;
/*!40000 ALTER TABLE `pos_terminals` DISABLE KEYS */;
/*!40000 ALTER TABLE `pos_terminals` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `product_categories`
--

DROP TABLE IF EXISTS `product_categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `product_categories` (
  `CategoryID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `Name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ParentID` int DEFAULT NULL,
  PRIMARY KEY (`CategoryID`),
  KEY `fk_prod_categories_tenants` (`TenantID`),
  CONSTRAINT `fk_prod_categories_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `product_categories`
--

LOCK TABLES `product_categories` WRITE;
/*!40000 ALTER TABLE `product_categories` DISABLE KEYS */;
INSERT INTO `product_categories` VALUES (1,1,'انفيرترات',NULL),(2,1,'انفيرتر 6.2',1),(3,1,'بطاريات',NULL),(4,1,'بطاريات ليثيوم BMS',3);
/*!40000 ALTER TABLE `product_categories` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `product_serials`
--

DROP TABLE IF EXISTS `product_serials`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `product_serials` (
  `SerialNumberID` int NOT NULL AUTO_INCREMENT,
  `ProductID` int NOT NULL,
  `SerialNumber` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `WarehouseID` int NOT NULL,
  `Status` enum('In-Stock','Sold','Returned','Damaged') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'In-Stock',
  `PO_LineID` int DEFAULT NULL COMMENT 'بند الشراء الذي أدخل هذا السيريال',
  `SalesInvoice_LineID` int DEFAULT NULL COMMENT 'بند البيع الذي أخرج هذا السيريال',
  PRIMARY KEY (`SerialNumberID`),
  UNIQUE KEY `idx_product_serial` (`ProductID`,`SerialNumber`),
  KEY `WarehouseID` (`WarehouseID`),
  CONSTRAINT `product_serials_ibfk_1` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`),
  CONSTRAINT `product_serials_ibfk_2` FOREIGN KEY (`WarehouseID`) REFERENCES `warehouses` (`WarehouseID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `product_serials`
--

LOCK TABLES `product_serials` WRITE;
/*!40000 ALTER TABLE `product_serials` DISABLE KEYS */;
/*!40000 ALTER TABLE `product_serials` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `products`
--

DROP TABLE IF EXISTS `products`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `products` (
  `ProductID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `SKU` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Barcode` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Name_AR` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Name_EN` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `CategoryID` int DEFAULT NULL,
  `UOMID` int DEFAULT NULL,
  `UOM` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Weight_KG` decimal(12,4) DEFAULT NULL,
  `Volume_CBM` decimal(12,6) DEFAULT NULL,
  `HS_Code` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `MinStockLevel` int DEFAULT NULL,
  `IsSerialized` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'هل هذا المنتج يتطلب تتبع بالرقم التسلسلي؟',
  `IsForSaleOnline` tinyint(1) NOT NULL DEFAULT '0' COMMENT 'هل المنتج معروض للبيع أونلاين؟',
  `OnlinePrice` decimal(18,2) DEFAULT NULL COMMENT 'السعر للبيع أونلاين (قد يختلف عن سعر الجملة)',
  `OnlineDescription` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'وصف تسويقي للمنتج يظهر في المتجر',
  PRIMARY KEY (`ProductID`),
  UNIQUE KEY `idx_tenant_sku` (`TenantID`,`SKU`),
  KEY `CategoryID` (`CategoryID`),
  KEY `fk_products_uom` (`UOMID`),
  CONSTRAINT `fk_products_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `fk_products_uom` FOREIGN KEY (`UOMID`) REFERENCES `units_of_measure` (`UOMID`),
  CONSTRAINT `products_ibfk_1` FOREIGN KEY (`CategoryID`) REFERENCES `product_categories` (`CategoryID`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `products`
--

LOCK TABLES `products` WRITE;
/*!40000 ALTER TABLE `products` DISABLE KEYS */;
INSERT INTO `products` VALUES (1,1,'55','','فادس','Fadi',2,NULL,'5',NULL,NULL,'',1,0,0,NULL,'');
/*!40000 ALTER TABLE `products` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_tasks`
--

DROP TABLE IF EXISTS `project_tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_tasks` (
  `TaskID` int NOT NULL AUTO_INCREMENT,
  `ProjectID` int NOT NULL,
  `TaskName` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `AssignedTo_EmployeeID` int DEFAULT NULL,
  `Status` enum('ToDo','InProgress','Done') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'ToDo',
  PRIMARY KEY (`TaskID`),
  KEY `ProjectID` (`ProjectID`),
  KEY `AssignedTo_EmployeeID` (`AssignedTo_EmployeeID`),
  CONSTRAINT `project_tasks_ibfk_1` FOREIGN KEY (`ProjectID`) REFERENCES `projects` (`ProjectID`) ON DELETE CASCADE,
  CONSTRAINT `project_tasks_ibfk_2` FOREIGN KEY (`AssignedTo_EmployeeID`) REFERENCES `employees` (`EmployeeID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_tasks`
--

LOCK TABLES `project_tasks` WRITE;
/*!40000 ALTER TABLE `project_tasks` DISABLE KEYS */;
/*!40000 ALTER TABLE `project_tasks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `projects`
--

DROP TABLE IF EXISTS `projects`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `projects` (
  `ProjectID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ProjectName` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `StartDate` date DEFAULT NULL,
  `EndDate` date DEFAULT NULL,
  `Status` enum('NotStarted','InProgress','Completed','OnHold') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`ProjectID`),
  KEY `TenantID` (`TenantID`),
  CONSTRAINT `projects_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `projects`
--

LOCK TABLES `projects` WRITE;
/*!40000 ALTER TABLE `projects` DISABLE KEYS */;
/*!40000 ALTER TABLE `projects` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `purchaseorders`
--

DROP TABLE IF EXISTS `purchaseorders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `purchaseorders` (
  `PO_ID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `PartnerID` int DEFAULT NULL,
  `Title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `PODate` date DEFAULT NULL,
  `ReferenceNumber` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `CurrencyID` int DEFAULT NULL,
  `IncotermID` int DEFAULT NULL,
  `PaymentStatus` enum('Unpaid','Partial','Paid') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'Unpaid',
  `LogisticsStatus` enum('Draft','Confirmed','Production','ReadyToShip','Shipped','Closed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'Draft',
  `Notes` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `LC_ID` int DEFAULT NULL COMMENT 'الاعتماد المستندي الذي يغطي هذه الصفقة',
  PRIMARY KEY (`PO_ID`),
  KEY `PartnerID` (`PartnerID`),
  KEY `CurrencyID` (`CurrencyID`),
  KEY `fk_po_lc` (`LC_ID`),
  KEY `idx_purchaseorders_status` (`TenantID`,`LogisticsStatus`,`PaymentStatus`),
  CONSTRAINT `fk_po_lc` FOREIGN KEY (`LC_ID`) REFERENCES `letters_of_credit` (`LC_ID`),
  CONSTRAINT `fk_po_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `purchaseorders_ibfk_1` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`),
  CONSTRAINT `purchaseorders_ibfk_2` FOREIGN KEY (`CurrencyID`) REFERENCES `currencies` (`CurrencyID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='عنوان وصفي للصفقة/أمر الشراء لسهولة التمييز والبحث';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `purchaseorders`
--

LOCK TABLES `purchaseorders` WRITE;
/*!40000 ALTER TABLE `purchaseorders` DISABLE KEYS */;
/*!40000 ALTER TABLE `purchaseorders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role_permissions`
--

DROP TABLE IF EXISTS `role_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `role_permissions` (
  `PermissionID` int NOT NULL AUTO_INCREMENT,
  `RoleID` int NOT NULL,
  `PermissionResource` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `PermissionAction` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`PermissionID`),
  UNIQUE KEY `idx_role_resource_action` (`RoleID`,`PermissionResource`,`PermissionAction`),
  CONSTRAINT `role_permissions_ibfk_1` FOREIGN KEY (`RoleID`) REFERENCES `roles` (`RoleID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_permissions`
--

LOCK TABLES `role_permissions` WRITE;
/*!40000 ALTER TABLE `role_permissions` DISABLE KEYS */;
/*!40000 ALTER TABLE `role_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `RoleID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `RoleName` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Description` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`RoleID`),
  UNIQUE KEY `idx_tenant_rolename` (`TenantID`,`RoleName`),
  CONSTRAINT `roles_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `salesinvoice_lines`
--

DROP TABLE IF EXISTS `salesinvoice_lines`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `salesinvoice_lines` (
  `LineID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `InvoiceID` int DEFAULT NULL,
  `ProductID` int DEFAULT NULL,
  `Quantity` decimal(18,2) DEFAULT NULL,
  `UnitPrice` decimal(18,2) DEFAULT NULL,
  `TotalLine` decimal(18,2) DEFAULT NULL,
  `TaxRateID` int DEFAULT NULL,
  `TaxAmount_Local` decimal(18,2) DEFAULT '0.00',
  PRIMARY KEY (`LineID`),
  KEY `InvoiceID` (`InvoiceID`),
  KEY `ProductID` (`ProductID`),
  KEY `fk_sales_lines_tax` (`TaxRateID`),
  KEY `idx_salesinvoice_lines_product` (`TenantID`,`ProductID`),
  CONSTRAINT `fk_sales_lines_tax` FOREIGN KEY (`TaxRateID`) REFERENCES `tax_rates` (`TaxRateID`),
  CONSTRAINT `fk_sales_lines_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `salesinvoice_lines_ibfk_1` FOREIGN KEY (`InvoiceID`) REFERENCES `salesinvoices` (`InvoiceID`),
  CONSTRAINT `salesinvoice_lines_ibfk_2` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `salesinvoice_lines`
--

LOCK TABLES `salesinvoice_lines` WRITE;
/*!40000 ALTER TABLE `salesinvoice_lines` DISABLE KEYS */;
/*!40000 ALTER TABLE `salesinvoice_lines` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `salesinvoices`
--

DROP TABLE IF EXISTS `salesinvoices`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `salesinvoices` (
  `InvoiceID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `SO_ID` int DEFAULT NULL,
  `CustomerID` int DEFAULT NULL,
  `InvoiceDate` datetime DEFAULT NULL,
  `DueDate` datetime DEFAULT NULL,
  `CurrencyID` int DEFAULT NULL,
  `ExchangeRate` decimal(18,6) DEFAULT NULL,
  `TotalAmount_Foreign` decimal(18,2) DEFAULT NULL,
  `TotalAmount_Local` decimal(18,2) DEFAULT NULL,
  `IsPaid` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`InvoiceID`),
  KEY `CustomerID` (`CustomerID`),
  KEY `idx_salesinvoices_paid` (`TenantID`,`IsPaid`),
  KEY `idx_salesinvoices_date` (`TenantID`,`InvoiceDate`),
  CONSTRAINT `fk_sales_invoices_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `salesinvoices_ibfk_1` FOREIGN KEY (`CustomerID`) REFERENCES `partners` (`PartnerID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `salesinvoices`
--

LOCK TABLES `salesinvoices` WRITE;
/*!40000 ALTER TABLE `salesinvoices` DISABLE KEYS */;
/*!40000 ALTER TABLE `salesinvoices` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `salesorders`
--

DROP TABLE IF EXISTS `salesorders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `salesorders` (
  `SO_ID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `CustomerID` int DEFAULT NULL,
  `Title` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `OrderDate` datetime DEFAULT NULL,
  `Status` enum('Draft','Confirmed','Invoiced','Cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `TotalAmount_Local` decimal(18,2) DEFAULT NULL,
  PRIMARY KEY (`SO_ID`),
  KEY `CustomerID` (`CustomerID`),
  KEY `fk_so_tenants` (`TenantID`),
  CONSTRAINT `fk_so_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `salesorders_ibfk_1` FOREIGN KEY (`CustomerID`) REFERENCES `partners` (`PartnerID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='عنوان وصفي للصفقة/طلب البيع لسهولة التمييز والبحث';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `salesorders`
--

LOCK TABLES `salesorders` WRITE;
/*!40000 ALTER TABLE `salesorders` DISABLE KEYS */;
/*!40000 ALTER TABLE `salesorders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `service_logs`
--

DROP TABLE IF EXISTS `service_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `service_logs` (
  `ServiceLogID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ServiceRequestID` int DEFAULT NULL,
  `ServiceWorkOrderID` int DEFAULT NULL,
  `LogDateTime` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `UserID` int DEFAULT NULL COMMENT 'المستخدم الذي قام بالإجراء',
  `LogDescription` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'وصف الإجراء',
  PRIMARY KEY (`ServiceLogID`),
  KEY `fk_sl_tenant` (`TenantID`),
  KEY `fk_sl_request` (`ServiceRequestID`),
  KEY `fk_sl_workorder` (`ServiceWorkOrderID`),
  KEY `fk_sl_user` (`UserID`),
  CONSTRAINT `fk_sl_request` FOREIGN KEY (`ServiceRequestID`) REFERENCES `service_requests` (`ServiceRequestID`) ON DELETE CASCADE,
  CONSTRAINT `fk_sl_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`),
  CONSTRAINT `fk_sl_user` FOREIGN KEY (`UserID`) REFERENCES `users` (`UserID`) ON DELETE SET NULL,
  CONSTRAINT `fk_sl_workorder` FOREIGN KEY (`ServiceWorkOrderID`) REFERENCES `service_work_orders` (`ServiceWorkOrderID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `service_logs`
--

LOCK TABLES `service_logs` WRITE;
/*!40000 ALTER TABLE `service_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `service_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `service_requests`
--

DROP TABLE IF EXISTS `service_requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `service_requests` (
  `ServiceRequestID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `CustomerAssetID` int NOT NULL,
  `PartnerID` int NOT NULL,
  `RequestDate` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `ProblemDescription` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Status` enum('New','Assigned','WorkOrder-Created','Closed','Cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'New',
  `Priority` enum('Low','Medium','High','Urgent') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Medium',
  PRIMARY KEY (`ServiceRequestID`),
  KEY `fk_sr_tenant` (`TenantID`),
  KEY `fk_sr_asset` (`CustomerAssetID`),
  KEY `fk_sr_partner` (`PartnerID`),
  CONSTRAINT `fk_sr_asset` FOREIGN KEY (`CustomerAssetID`) REFERENCES `customer_assets` (`CustomerAssetID`) ON DELETE CASCADE,
  CONSTRAINT `fk_sr_partner` FOREIGN KEY (`PartnerID`) REFERENCES `partners` (`PartnerID`) ON DELETE CASCADE,
  CONSTRAINT `fk_sr_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `service_requests`
--

LOCK TABLES `service_requests` WRITE;
/*!40000 ALTER TABLE `service_requests` DISABLE KEYS */;
/*!40000 ALTER TABLE `service_requests` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `service_tasks`
--

DROP TABLE IF EXISTS `service_tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `service_tasks` (
  `ServiceTaskID` int NOT NULL AUTO_INCREMENT,
  `ServiceWorkOrderID` int NOT NULL,
  `Description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'وصف المهمة المطلوبة',
  `IsCompleted` tinyint(1) NOT NULL DEFAULT '0',
  `SparePartProductID` int DEFAULT NULL COMMENT 'قطعة الغيار المستخدمة',
  `QuantityUsed` decimal(18,2) DEFAULT '0.00',
  PRIMARY KEY (`ServiceTaskID`),
  KEY `fk_st_workorder` (`ServiceWorkOrderID`),
  KEY `fk_st_sparepart` (`SparePartProductID`),
  CONSTRAINT `fk_st_sparepart` FOREIGN KEY (`SparePartProductID`) REFERENCES `products` (`ProductID`),
  CONSTRAINT `fk_st_workorder` FOREIGN KEY (`ServiceWorkOrderID`) REFERENCES `service_work_orders` (`ServiceWorkOrderID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `service_tasks`
--

LOCK TABLES `service_tasks` WRITE;
/*!40000 ALTER TABLE `service_tasks` DISABLE KEYS */;
/*!40000 ALTER TABLE `service_tasks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `service_visits`
--

DROP TABLE IF EXISTS `service_visits`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `service_visits` (
  `ServiceVisitID` int NOT NULL AUTO_INCREMENT,
  `ServiceWorkOrderID` int NOT NULL,
  `TechnicianID` int NOT NULL,
  `VisitDate` date NOT NULL,
  `CheckInTime` datetime DEFAULT NULL,
  `CheckOutTime` datetime DEFAULT NULL,
  `Notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'ما تم عمله خلال الزيارة',
  PRIMARY KEY (`ServiceVisitID`),
  KEY `fk_sv_workorder` (`ServiceWorkOrderID`),
  KEY `fk_sv_technician` (`TechnicianID`),
  CONSTRAINT `fk_sv_technician` FOREIGN KEY (`TechnicianID`) REFERENCES `technicians` (`TechnicianID`) ON DELETE CASCADE,
  CONSTRAINT `fk_sv_workorder` FOREIGN KEY (`ServiceWorkOrderID`) REFERENCES `service_work_orders` (`ServiceWorkOrderID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `service_visits`
--

LOCK TABLES `service_visits` WRITE;
/*!40000 ALTER TABLE `service_visits` DISABLE KEYS */;
/*!40000 ALTER TABLE `service_visits` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `service_work_orders`
--

DROP TABLE IF EXISTS `service_work_orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `service_work_orders` (
  `ServiceWorkOrderID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ServiceRequestID` int DEFAULT NULL,
  `CustomerAssetID` int NOT NULL,
  `WorkOrderDate` date NOT NULL,
  `Status` enum('Draft','Scheduled','In-Progress','Completed','Billed','Cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Draft',
  `ScheduledStartDate` datetime DEFAULT NULL,
  `ScheduledEndDate` datetime DEFAULT NULL,
  `ActualStartDate` datetime DEFAULT NULL,
  `ActualEndDate` datetime DEFAULT NULL,
  `BillingNotes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'ملاحظات لإضافتها للفاتورة',
  PRIMARY KEY (`ServiceWorkOrderID`),
  KEY `fk_swo_tenant` (`TenantID`),
  KEY `fk_swo_request` (`ServiceRequestID`),
  KEY `fk_swo_asset` (`CustomerAssetID`),
  CONSTRAINT `fk_swo_asset` FOREIGN KEY (`CustomerAssetID`) REFERENCES `customer_assets` (`CustomerAssetID`) ON DELETE CASCADE,
  CONSTRAINT `fk_swo_request` FOREIGN KEY (`ServiceRequestID`) REFERENCES `service_requests` (`ServiceRequestID`) ON DELETE SET NULL,
  CONSTRAINT `fk_swo_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `service_work_orders`
--

LOCK TABLES `service_work_orders` WRITE;
/*!40000 ALTER TABLE `service_work_orders` DISABLE KEYS */;
/*!40000 ALTER TABLE `service_work_orders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `shipment_items`
--

DROP TABLE IF EXISTS `shipment_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `shipment_items` (
  `ShipmentItemID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ShipmentID` int DEFAULT NULL,
  `PO_LineID` int DEFAULT NULL,
  `QuantityShipped` decimal(18,2) DEFAULT NULL,
  `UnitWeight_KG` decimal(12,4) DEFAULT NULL,
  `UnitVolume_CBM` decimal(12,6) DEFAULT NULL,
  PRIMARY KEY (`ShipmentItemID`),
  KEY `ShipmentID` (`ShipmentID`),
  KEY `PO_LineID` (`PO_LineID`),
  KEY `fk_shipment_items_tenants` (`TenantID`),
  CONSTRAINT `fk_shipment_items_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `shipment_items_ibfk_1` FOREIGN KEY (`ShipmentID`) REFERENCES `shipments` (`ShipmentID`),
  CONSTRAINT `shipment_items_ibfk_2` FOREIGN KEY (`PO_LineID`) REFERENCES `po_lines` (`LineID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `shipment_items`
--

LOCK TABLES `shipment_items` WRITE;
/*!40000 ALTER TABLE `shipment_items` DISABLE KEYS */;
/*!40000 ALTER TABLE `shipment_items` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `shipments`
--

DROP TABLE IF EXISTS `shipments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `shipments` (
  `ShipmentID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ShipmentRef` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `BillOfLading` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `FreightForwarderID` int DEFAULT NULL,
  `CustomsBrokerID` int DEFAULT NULL,
  `ETD` date DEFAULT NULL,
  `ETA` date DEFAULT NULL,
  `ActualArrivalDate` date DEFAULT NULL,
  `Status` enum('Booking','OnWater','Port','Customs','Transport','Received') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'Booking',
  PRIMARY KEY (`ShipmentID`),
  UNIQUE KEY `idx_tenant_shipment_ref` (`TenantID`,`ShipmentRef`),
  KEY `FreightForwarderID` (`FreightForwarderID`),
  KEY `CustomsBrokerID` (`CustomsBrokerID`),
  KEY `idx_shipments_status` (`TenantID`,`Status`),
  KEY `idx_shipments_eta` (`TenantID`,`ETA`),
  CONSTRAINT `fk_shipments_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `shipments_ibfk_1` FOREIGN KEY (`FreightForwarderID`) REFERENCES `partners` (`PartnerID`),
  CONSTRAINT `shipments_ibfk_2` FOREIGN KEY (`CustomsBrokerID`) REFERENCES `partners` (`PartnerID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `shipments`
--

LOCK TABLES `shipments` WRITE;
/*!40000 ALTER TABLE `shipments` DISABLE KEYS */;
/*!40000 ALTER TABLE `shipments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `stock_ledger`
--

DROP TABLE IF EXISTS `stock_ledger`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `stock_ledger` (
  `EntryID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ProductID` int DEFAULT NULL,
  `WarehouseID` int DEFAULT NULL,
  `LocationID` int DEFAULT NULL,
  `TransactionDate` datetime DEFAULT NULL,
  `Type` enum('Purchase_Receive','Sales_Delivery','Return_In','Return_Out','Transfer_In','Transfer_Out','Adjustment') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `Quantity` decimal(18,4) DEFAULT NULL,
  `UnitCost` decimal(18,4) DEFAULT NULL,
  `TotalValue` decimal(18,4) DEFAULT NULL,
  `RelatedShipmentID` int DEFAULT NULL,
  PRIMARY KEY (`EntryID`),
  KEY `ProductID` (`ProductID`),
  KEY `WarehouseID` (`WarehouseID`),
  KEY `fk_stock_location` (`LocationID`),
  KEY `idx_stock_ledger_product_warehouse` (`TenantID`,`ProductID`,`WarehouseID`),
  CONSTRAINT `fk_stock_ledger_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `fk_stock_location` FOREIGN KEY (`LocationID`) REFERENCES `warehouse_locations` (`LocationID`),
  CONSTRAINT `stock_ledger_ibfk_1` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`),
  CONSTRAINT `stock_ledger_ibfk_2` FOREIGN KEY (`WarehouseID`) REFERENCES `warehouses` (`WarehouseID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `stock_ledger`
--

LOCK TABLES `stock_ledger` WRITE;
/*!40000 ALTER TABLE `stock_ledger` DISABLE KEYS */;
/*!40000 ALTER TABLE `stock_ledger` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `stock_reservations`
--

DROP TABLE IF EXISTS `stock_reservations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `stock_reservations` (
  `ReservationID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `ProductID` int NOT NULL,
  `SalesOrderLineID` int NOT NULL,
  `WarehouseID` int NOT NULL,
  `ReservedQuantity` decimal(18,4) NOT NULL,
  `Status` enum('Active','Fulfilled','Cancelled') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Active',
  PRIMARY KEY (`ReservationID`),
  KEY `TenantID` (`TenantID`),
  KEY `ProductID` (`ProductID`),
  KEY `SalesOrderLineID` (`SalesOrderLineID`),
  KEY `WarehouseID` (`WarehouseID`),
  CONSTRAINT `stock_reservations_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `stock_reservations_ibfk_2` FOREIGN KEY (`ProductID`) REFERENCES `products` (`ProductID`),
  CONSTRAINT `stock_reservations_ibfk_3` FOREIGN KEY (`SalesOrderLineID`) REFERENCES `salesinvoice_lines` (`LineID`),
  CONSTRAINT `stock_reservations_ibfk_4` FOREIGN KEY (`WarehouseID`) REFERENCES `warehouses` (`WarehouseID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `stock_reservations`
--

LOCK TABLES `stock_reservations` WRITE;
/*!40000 ALTER TABLE `stock_reservations` DISABLE KEYS */;
/*!40000 ALTER TABLE `stock_reservations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `system_attachments`
--

DROP TABLE IF EXISTS `system_attachments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `system_attachments` (
  `AttachmentID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `RelatedTable` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `RelatedID` int DEFAULT NULL,
  `FileType` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `FilePath` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `UploadedAt` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`AttachmentID`),
  KEY `fk_attachments_tenants` (`TenantID`),
  CONSTRAINT `fk_attachments_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `system_attachments`
--

LOCK TABLES `system_attachments` WRITE;
/*!40000 ALTER TABLE `system_attachments` DISABLE KEYS */;
/*!40000 ALTER TABLE `system_attachments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tax_rates`
--

DROP TABLE IF EXISTS `tax_rates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tax_rates` (
  `TaxRateID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `TaxName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'مثل: ضريبة القيمة المضافة 16%',
  `Rate` decimal(10,4) NOT NULL COMMENT 'معدل الضريبة (مثال: 16.00)',
  `IsActive` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`TaxRateID`),
  UNIQUE KEY `idx_tenant_tax_name` (`TenantID`,`TaxName`),
  CONSTRAINT `tax_rates_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tax_rates`
--

LOCK TABLES `tax_rates` WRITE;
/*!40000 ALTER TABLE `tax_rates` DISABLE KEYS */;
/*!40000 ALTER TABLE `tax_rates` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `technician_assignments`
--

DROP TABLE IF EXISTS `technician_assignments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `technician_assignments` (
  `AssignmentID` int NOT NULL AUTO_INCREMENT,
  `ServiceWorkOrderID` int NOT NULL,
  `TechnicianID` int NOT NULL,
  `AssignedDate` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`AssignmentID`),
  UNIQUE KEY `idx_workorder_technician` (`ServiceWorkOrderID`,`TechnicianID`),
  KEY `fk_ta_workorder` (`ServiceWorkOrderID`),
  KEY `fk_ta_technician` (`TechnicianID`),
  CONSTRAINT `fk_ta_technician` FOREIGN KEY (`TechnicianID`) REFERENCES `technicians` (`TechnicianID`) ON DELETE CASCADE,
  CONSTRAINT `fk_ta_workorder` FOREIGN KEY (`ServiceWorkOrderID`) REFERENCES `service_work_orders` (`ServiceWorkOrderID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `technician_assignments`
--

LOCK TABLES `technician_assignments` WRITE;
/*!40000 ALTER TABLE `technician_assignments` DISABLE KEYS */;
/*!40000 ALTER TABLE `technician_assignments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `technicians`
--

DROP TABLE IF EXISTS `technicians`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `technicians` (
  `TechnicianID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `EmployeeID` int NOT NULL COMMENT 'يرتبط بجدول الموظفين العام',
  `Specialization` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'تخصص الفني (مثال: تبريد، إلكترونيات)',
  `IsActive` tinyint(1) NOT NULL DEFAULT '1',
  PRIMARY KEY (`TechnicianID`),
  UNIQUE KEY `idx_tenant_employee` (`TenantID`,`EmployeeID`),
  KEY `fk_tech_employee` (`EmployeeID`),
  CONSTRAINT `fk_tech_employee` FOREIGN KEY (`EmployeeID`) REFERENCES `employees` (`EmployeeID`) ON DELETE CASCADE,
  CONSTRAINT `fk_tech_tenant` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `technicians`
--

LOCK TABLES `technicians` WRITE;
/*!40000 ALTER TABLE `technicians` DISABLE KEYS */;
/*!40000 ALTER TABLE `technicians` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tenants`
--

DROP TABLE IF EXISTS `tenants`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tenants` (
  `TenantID` int NOT NULL AUTO_INCREMENT,
  `CompanyName` varchar(150) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `SubscriptionPlan` enum('Basic','Pro','Enterprise') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Status` enum('Active','Suspended','Trial') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'Trial',
  `CreatedAt` datetime DEFAULT CURRENT_TIMESTAMP,
  `DomainName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`TenantID`),
  UNIQUE KEY `DomainName` (`DomainName`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tenants`
--

LOCK TABLES `tenants` WRITE;
/*!40000 ALTER TABLE `tenants` DISABLE KEYS */;
INSERT INTO `tenants` VALUES (1,'Default Company','Basic','Trial','2026-01-31 17:58:22','default.com');
/*!40000 ALTER TABLE `tenants` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `units_of_measure`
--

DROP TABLE IF EXISTS `units_of_measure`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `units_of_measure` (
  `UOMID` int NOT NULL AUTO_INCREMENT,
  `Code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'رمز الوحدة مثل: PCS, KG, CTN',
  `Name_AR` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'الاسم بالعربي',
  `Name_EN` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'الاسم بالإنجليزية',
  `IsActive` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`UOMID`),
  UNIQUE KEY `idx_uom_code` (`Code`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='جدول وحدات القياس للمنتجات';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `units_of_measure`
--

LOCK TABLES `units_of_measure` WRITE;
/*!40000 ALTER TABLE `units_of_measure` DISABLE KEYS */;
INSERT INTO `units_of_measure` VALUES (1,'PCS','حبة','Piece',1),(2,'CTN','كرتونة','Carton',1),(3,'BOX','صندوق','Box',1),(4,'KG','كيلوجرام','Kilogram',1),(5,'M','متر','Meter',1),(6,'L','لتر','Liter',1),(7,'M2','متر مربع','Square Meter',1),(8,'M3','متر مكعب','Cubic Meter',1),(9,'TON','طن','Ton',1),(10,'SET','طقم','Set',1),(11,'PAIR','زوج','Pair',1),(12,'ROLL','لفة','Roll',1),(13,'BAG','كيس','Bag',1),(14,'PKG','عبوة','Package',1);
/*!40000 ALTER TABLE `units_of_measure` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_roles`
--

DROP TABLE IF EXISTS `user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_roles` (
  `UserID` int NOT NULL,
  `RoleID` int NOT NULL,
  PRIMARY KEY (`UserID`,`RoleID`),
  KEY `RoleID` (`RoleID`),
  CONSTRAINT `user_roles_ibfk_1` FOREIGN KEY (`UserID`) REFERENCES `users` (`UserID`) ON DELETE CASCADE,
  CONSTRAINT `user_roles_ibfk_2` FOREIGN KEY (`RoleID`) REFERENCES `roles` (`RoleID`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_roles`
--

LOCK TABLES `user_roles` WRITE;
/*!40000 ALTER TABLE `user_roles` DISABLE KEYS */;
/*!40000 ALTER TABLE `user_roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_tenant_access`
--

DROP TABLE IF EXISTS `user_tenant_access`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_tenant_access` (
  `UserID` int NOT NULL,
  `TenantID` int NOT NULL,
  PRIMARY KEY (`UserID`,`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_tenant_access`
--

LOCK TABLES `user_tenant_access` WRITE;
/*!40000 ALTER TABLE `user_tenant_access` DISABLE KEYS */;
/*!40000 ALTER TABLE `user_tenant_access` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `UserID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `FullName` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `PasswordHash` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `IsActive` tinyint(1) DEFAULT '1',
  `LastLogin` datetime DEFAULT NULL,
  `CreatedAt` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`UserID`),
  UNIQUE KEY `idx_tenant_email` (`TenantID`,`Email`),
  CONSTRAINT `users_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `vendor_payments`
--

DROP TABLE IF EXISTS `vendor_payments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vendor_payments` (
  `PaymentID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `PO_ID` int DEFAULT NULL,
  `PaymentDate` datetime DEFAULT NULL,
  `CurrencyID` int DEFAULT NULL,
  `Amount_Foreign` decimal(18,2) DEFAULT NULL,
  `ExchangeRate` decimal(18,6) DEFAULT NULL,
  `Amount_Local` decimal(18,2) DEFAULT NULL,
  `PaymentMethod` enum('BankTransfer','Cash','Check','CreditCard') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `ReferenceTransactionID` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `BankAccountID` int DEFAULT NULL COMMENT 'الحساب البنكي الذي تم الدفع منه',
  PRIMARY KEY (`PaymentID`),
  KEY `PO_ID` (`PO_ID`),
  KEY `fk_vendor_payments_tenants` (`TenantID`),
  KEY `fk_vendor_payments_bank` (`BankAccountID`),
  CONSTRAINT `fk_vendor_payments_bank` FOREIGN KEY (`BankAccountID`) REFERENCES `bank_accounts` (`BankAccountID`),
  CONSTRAINT `fk_vendor_payments_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `vendor_payments_ibfk_1` FOREIGN KEY (`PO_ID`) REFERENCES `purchaseorders` (`PO_ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `vendor_payments`
--

LOCK TABLES `vendor_payments` WRITE;
/*!40000 ALTER TABLE `vendor_payments` DISABLE KEYS */;
/*!40000 ALTER TABLE `vendor_payments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Temporary view structure for view `vw_product_stock_balance`
--

DROP TABLE IF EXISTS `vw_product_stock_balance`;
/*!50001 DROP VIEW IF EXISTS `vw_product_stock_balance`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `vw_product_stock_balance` AS SELECT 
 1 AS `TenantID`,
 1 AS `ProductID`,
 1 AS `SKU`,
 1 AS `Name_AR`,
 1 AS `Name_EN`,
 1 AS `WarehouseID`,
 1 AS `WarehouseName`,
 1 AS `QuantityOnHand`*/;
SET character_set_client = @saved_cs_client;

--
-- Table structure for table `warehouse_locations`
--

DROP TABLE IF EXISTS `warehouse_locations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `warehouse_locations` (
  `LocationID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `WarehouseID` int NOT NULL,
  `LocationCode` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'مثل: A-01-R03',
  `Description` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`LocationID`),
  UNIQUE KEY `idx_tenant_warehouse_location` (`TenantID`,`WarehouseID`,`LocationCode`),
  KEY `WarehouseID` (`WarehouseID`),
  CONSTRAINT `warehouse_locations_ibfk_1` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`) ON DELETE CASCADE,
  CONSTRAINT `warehouse_locations_ibfk_2` FOREIGN KEY (`WarehouseID`) REFERENCES `warehouses` (`WarehouseID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `warehouse_locations`
--

LOCK TABLES `warehouse_locations` WRITE;
/*!40000 ALTER TABLE `warehouse_locations` DISABLE KEYS */;
/*!40000 ALTER TABLE `warehouse_locations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `warehouses`
--

DROP TABLE IF EXISTS `warehouses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `warehouses` (
  `WarehouseID` int NOT NULL AUTO_INCREMENT,
  `TenantID` int NOT NULL,
  `Name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  `Address` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
  `IsBonded` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`WarehouseID`),
  KEY `fk_warehouses_tenants` (`TenantID`),
  CONSTRAINT `fk_warehouses_tenants` FOREIGN KEY (`TenantID`) REFERENCES `tenants` (`TenantID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `warehouses`
--

LOCK TABLES `warehouses` WRITE;
/*!40000 ALTER TABLE `warehouses` DISABLE KEYS */;
/*!40000 ALTER TABLE `warehouses` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Final view structure for view `vw_product_stock_balance`
--

/*!50001 DROP VIEW IF EXISTS `vw_product_stock_balance`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_general_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `vw_product_stock_balance` AS select `p`.`TenantID` AS `TenantID`,`p`.`ProductID` AS `ProductID`,`p`.`SKU` AS `SKU`,`p`.`Name_AR` AS `Name_AR`,`p`.`Name_EN` AS `Name_EN`,`w`.`WarehouseID` AS `WarehouseID`,`w`.`Name` AS `WarehouseName`,coalesce(sum(`sl`.`Quantity`),0) AS `QuantityOnHand` from ((`products` `p` join `warehouses` `w` on((`p`.`TenantID` = `w`.`TenantID`))) left join `stock_ledger` `sl` on(((`p`.`ProductID` = `sl`.`ProductID`) and (`w`.`WarehouseID` = `sl`.`WarehouseID`)))) group by `p`.`TenantID`,`p`.`ProductID`,`p`.`SKU`,`p`.`Name_AR`,`p`.`Name_EN`,`w`.`WarehouseID`,`w`.`Name` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-02-05 15:51:19
