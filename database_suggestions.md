# اقتراحات هيكلية لربط الموردين بالحسابات (Database Architecture)

بناءً على طلبك، إليك الهيكل الاحترافي (Enterprise Standard) الذي يجب إضافته لقاعدة البيانات لربط الموردين والعملاء بحساباتهم الرئيسية بشكل ديناميكي (بدلاً من الكود الثابت).

## المقترح: نظام مجموعات الترحيل (Posting Groups)

بدلاً من ربط كل مورد بـ "رقم حساب" يدوياً، نقوم بإنشاء جدول "مجموعات" يحدد الحسابات الرئيسية (Control Accounts).

### 1. إنشاء جدول مجموعات الشركاء (Partner Groups)
هذا الجدول يحدد الحساب الرئيسي لكل فئة (مثلاً: موردين محليين، موردين دوليين، عملاء جملة).

```sql
CREATE TABLE `partner_groups` (
    `GroupID` INT AUTO_INCREMENT PRIMARY KEY,
    `TenantID` INT NOT NULL,
    `Name` VARCHAR(100) NOT NULL COMMENT 'اسم المجموعة: موردين محليين، عملاء...',
    `Type` ENUM('Customer', 'Supplier') NOT NULL,
    `AccountReceivableID` INT NULL COMMENT 'حساب ذمم العملاء الرئيسي لهذه المجموعة',
    `AccountPayableID` INT NULL COMMENT 'حساب ذمم الموردين الرئيسي لهذه المجموعة',
    FOREIGN KEY (`AccountReceivableID`) REFERENCES `chartofaccounts`(`AccountID`),
    FOREIGN KEY (`AccountPayableID`) REFERENCES `chartofaccounts`(`AccountID`)
);
```

### 2. تعديل جدول الشركاء (Partners)
نربط كل شريك بمجموعة بدلاً من ربطه بحساب رئيسي مباشرة.

```sql
ALTER TABLE `partners` ADD COLUMN `GroupID` INT NULL;
ALTER TABLE `partners` ADD CONSTRAINT `fk_partner_group` 
FOREIGN KEY (`GroupID`) REFERENCES `partner_groups`(`GroupID`);
```

## كيف يعمل هذا النظام؟

1. **التكوين (Configuration):**
   - تنشئ صف في `partner_groups` اسمه "موردين بضاعة" وتربطه بحساب "2101 - الموردين".
   - تنشئ صف آخر اسمه "موردين خدمات" وتبرطه بحساب "2102 - أوراق دفع" أو حساب آخر.

2. **عند إضافة مورد (Runtime):**
   - يختار المستخدم "مجموعة المورد: موردين بضاعة".
   - النظام ينظر في جدول `partner_groups`.
   - يجد أن الحساب الرئيسي هو `2101`.
   - يقوم النظام بإنشاء الحساب الفرعي للمورد *تحت* هذا الحساب الرئيسي (2101005 مثلاً).

## فوائد هذا الهيكل (Why?)
1. **مرونة:** يمكنك تغيير الحساب الرئيسي لكل الموردين الجدد بتعديل سطر واحد في الداتابيس.
2. **تقارير:** يمكنك استخراج تقارير مسبقة حسب "المجموعة" (مثلاً ديون الموردين المحليين vs الدوليين).
3. **احترافية:** هذا هو الأسلوب المتبع في Odoo و SAP و Microsoft Dynamics.
