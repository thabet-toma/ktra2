# تعلّمات من برنامج «الأصيل / Account5» (Algorithm)

> المصدر: `D:\Program Files\Algorithm\Account5` — المالك أكّد أنه free source بلا قيود حقوق نشر.
> هذا التوثيق **يلتقط نموذج البيانات والمنطق والتصميم** للتعلّم والمطابقة — لا نسخ كود مترجَم.
> المحرّك: قاعدة **InterBase/Firebird** (`Data/*.IB`، عبر `FIRIDLLU.dll`). استُخرجت السكيمة من ميتاداتا القاعدة (~2110 معرّف).

## 1) المعمارية المحاسبية الجوهرية (أهم درس)
- **`BILL` موحّد لكل المستندات** + `BILL_ITEM` للأسطر، مع مميِّز نوع `BILL_TYPE_ID`. (نطابقه عبر `invoice_kind`.)
- كل فاتورة تحمل **`DEBIT_ACC_ID` و`CREDIT_ACC_ID` مباشرة**، وجدول **`BILL_TYPE` + `BILL_TYPE_ENTRY`** يربط كل نوع مستند بحساباته وقالب قيده.
  - **المعنى:** القيد المحاسبي **مشتقّ من إعداد نوع المستند** (مدين/دائن + قالب)، لا كود ترحيل مكتوب يدوياً لكل نوع. (حقول «المدين/الدائن/نوع الفاتورة» في الشاشات.)
  - **عندنا:** ترحيل مكتوب بـ Python لكل نوع (`post_sales_invoice`...). الدرس: جدول `DocumentType` قابل للتهيئة يحوّل إضافة نوع مستند إلى **إعداد لا برمجة**.
- **`COMPLEX_ENTRY_TEMPLATE` + `COMPLEX_ENTRY_TEMPLATE_DETAILS`**: قوالب قيود مركّبة/متكررة (تُنشئ `COMPLEX_ENTRY` بضغطة).
- **`CLOSING_PERCENTAGE` + `FINAL_ACCOUNT_ID`**: ربط الحساب بحسابات ختامية بنِسَب (شاشة «إقفال الحساب 100%»).
- **`ACC_CATEG` / `ACCOUNT` / `LEDGER` / `DAILY`**: تصنيفات → حسابات → أستاذ → يومية.

## 2) البحث العربي الاحترافي (`ABS_*`) — درس عالي القيمة
- لكل كيان قابل للبحث عمود **`ABS_…`** (مثل `ABS_PRODUCT_NAME`, `ABS_ACCOUNT_NAME`, `ABS_CATEG_NAME`, `ABS_CONTACT_NAME`, `ABS_DEAL_NAME`, `ABS_TAX_NAME`) = نسخة **مُطبَّعة** من الاسم (بلا همزات/تشكيل/تطويل/تباعد).
- البحث والفرز يجريان على `ABS_` فيطابق رغم اختلاف الإملاء («انفيرتر/إنفرتر/أنفيرتر»).
- **التطبيق المقترح عندنا:** عمود `name_normalized` على Product/Partner/Account + تطبيع عند الحفظ + بحث/إكمال تلقائي عليه (يحسّن `AseelAutocomplete`).

## 3) المخزون والتسعير
- **`PRODUCT` + `PRODUCT_ITEM`** (متغيّرات/وحدات للصنف) + `BASE_UNIT_ID` (وحدات متعددة).
- `BASE_COST_PRICE` / `BASE_PRICE` / `BASE_BEGIN_BALANCE` / `BASE_BEGIN_PRICE`.
- `ADDITION_PERCENTAGE` (نسبة إضافة/هامش)، `BASE_BOONS` (كمية مجانية/بونص)، `BALANCE_LIMIT` (حد ائتمان)، `BARCODE_TEMPLATE`/`BARCODE_PRINTLIST` (طباعة باركود).
- **`MAKING_TEMPLATE`**: تصنيع/تجميع (BOM) — إنتاج صنف من مكوّنات.

## 4) المالية والوكلاء والصرافة
- **`CHECKS`** (شيكات بدورة حالات)، **`TRANSFER_MONEY`** (تحويلات بين الصناديق/الحسابات).
- **`AGENT_COMMISSION` + `COMMISSION_DEBIT_ID`/`COMMISSION_CREDIT_ID`**: عمولة المندوب/الوكيل تُقيَّد محاسبياً على الفاتورة.
- **`CURRENCY_EXCHANGE` (+ DEBIT/CREDIT_ACCOUNT) + `CURRENCY_RATE`**: صرافة وحوالات متعددة العملات (قائمة «حوالات وصرافة»).
- **`AGENT_TRANSFER_CURRENCY/RATE`**: حوالات بعملات مختلفة بسعر صرف.

## 5) اللوجستيات/الاستيراد
- `DELIVERY_CARGO`, `FREIGHTS`, `MANIFEST_DETAIL`, `ARRIVAL_PORT_ID`, `PURCHASE_ORDERS` + `PURCHASE_ORDER_ITEM`, `QUOTATION_ITEM`, `POS_ORDER` + `POS_ORDER_ITEM` (نقطة بيع).

## 6) أنماط هندسية عامة (تصميم)
- **سلّة محذوفات بدل الحذف:** `*_TRASH` (`BILL_TRASH`, `BILL_ITEM_TRASH`, `ENTRY_TRASH`) — يُنقل المحذوف لا يُمحى. (عندنا unpost/status.)
- **سجل تدقيق شامل:** `DATACHANGELOG`. (عندنا `AccountingAuditLog`.)
- **مولّدات أرقام:** `*_GENID` لكل تسلسل (ترقيم ذرّي لكل مستند).
- **`POLICIES` / `SYSTEM_FLAG`:** صلاحيات وأعلام نظام مركزية.
- **تطبيع الأسماء (`ABS_`)** كنمط متبادل عبر كل الكيانات.
- **UI كثيف بنافذة واحدة:** كل العمل من شاشة واحدة (شجرة أصناف جانبية، إضافة حساب/صنف/فئة inline، شبكة دفعات مدمجة، كشف حساب الطرف فور اختياره، شريط إجراءات سفلي ثابت). هذا أساس بريف «مساحة العمل الموحّدة».

## 7) فجوات عندنا مقابل الأصيل (مرشّحة للتنفيذ، بالأولوية)
1. **بحث `name_normalized`** (سريع، أثر فوري). 
2. **`DocumentType` يقود القيد** (أكبر تحسين معماري).
3. **قوالب قيود مركّبة** (`COMPLEX_ENTRY_TEMPLATE`).
4. **عمولة المندوب** على الفواتير.
5. **الصرافة والحوالات** (`CURRENCY_EXCHANGE`/`TRANSFER_MONEY`).
6. **التصنيع/التجميع** (`MAKING_TEMPLATE` / BOM).
7. **متغيّرات/وحدات متعددة للصنف** (`PRODUCT_ITEM`/`BASE_UNIT`).

> ملاحظة: هذا توثيق مرجعي للمطابقة. التنفيذ يتم بأسلوبنا (Django/DRF + React) دون نسخ بنية الأصيل حرفياً.
