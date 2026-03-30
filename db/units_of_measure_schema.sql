-- ==========================================
-- إنشاء جدول وحدات القياس (Units of Measure)
-- ==========================================

USE `global_erp_pro`;

-- إنشاء الجدول
CREATE TABLE IF NOT EXISTS `units_of_measure` (
  `UOMID` int NOT NULL AUTO_INCREMENT,
  `Code` varchar(10) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'رمز الوحدة مثل: PCS, KG, CTN',
  `Name_AR` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'الاسم بالعربي',
  `Name_EN` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'الاسم بالإنجليزية',
  `IsActive` tinyint(1) DEFAULT 1,
  PRIMARY KEY (`UOMID`),
  UNIQUE KEY `idx_uom_code` (`Code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='جدول وحدات القياس للمنتجات';

-- إدراج بيانات أولية
INSERT INTO `units_of_measure` (`Code`, `Name_AR`, `Name_EN`) VALUES
('PCS', 'حبة', 'Piece'),
('CTN', 'كرتونة', 'Carton'),
('BOX', 'صندوق', 'Box'),
('KG', 'كيلوجرام', 'Kilogram'),
('M', 'متر', 'Meter'),
('L', 'لتر', 'Liter'),
('M2', 'متر مربع', 'Square Meter'),
('M3', 'متر مكعب', 'Cubic Meter'),
('TON', 'طن', 'Ton'),
('SET', 'طقم', 'Set'),
('PAIR', 'زوج', 'Pair'),
('ROLL', 'لفة', 'Roll'),
('BAG', 'كيس', 'Bag'),
('PKG', 'عبوة', 'Package');

-- ==========================================
-- تعديل جدول Products
-- ==========================================

-- إضافة عمود جديد للربط مع جدول وحدات القياس
ALTER TABLE `products` 
  ADD COLUMN `UOMID` int DEFAULT NULL AFTER `CategoryID`,
  ADD CONSTRAINT `fk_products_uom` FOREIGN KEY (`UOMID`) REFERENCES `units_of_measure` (`UOMID`);

-- نقل البيانات الموجودة من UOM القديم إلى UOMID (إن وجدت)
UPDATE `products` 
SET `UOMID` = (
  SELECT `UOMID` FROM `units_of_measure` WHERE `Code` = `products`.`UOM` LIMIT 1
) 
WHERE `UOM` IS NOT NULL AND `UOM` != '';

-- ملاحظة: لا نحذف عمود UOM القديم حالياً للحفاظ على التوافق مع البيانات القديمة
-- يمكن حذفه لاحقاً بعد التأكد من نقل كل البيانات:
-- ALTER TABLE `products` DROP COLUMN `UOM`;
