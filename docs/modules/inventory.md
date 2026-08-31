# inventory — المنتجات والمخزون: الحركة الوحيدة التي تغيّر الرصيد والتكلفة، والوحدات المُرقَّمة

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
يملك هذا الـapp بطاقة المنتج (`Product`)، تصنيفاته ووحداته وشرائح أسعاره، المستودعات،
وسجلّ حركة المخزون (`StockMovement`) الذي هو **المصدر الوحيد** لتغيير `quantity_on_hand`
و`avg_cost`. كل الأبواب — البيع، الشراء، الاستلام، التحويل بين المستودعات، الجرد —
تمرّ من `record_stock_movement()` الذي يحدّث الرصيد ومتوسط التكلفة ذرّياً ويحفظ لقطات
قبل/بعد على الحركة نفسها. ويستضيف كذلك تتبّع الوحدة المُرقَّمة (`ProductSerial`) في ملف
`serials.py` المستقل، ومستندَي `WarehouseTransfer` و`Stocktake`.

## أهم الملفات
| الملف | الغرض | أسطر |
|---|---|---|
| `inventory/services.py` | `record_stock_movement` + WAC، عكس الحركات، بطاقة المنتج، نماذج التكلفة، ترحيل التحويل والجرد | 1368 |
| `inventory/views.py` | ViewSets: المنتجات، الحركات، المستودعات، التحويلات، الجرد | 891 |
| `inventory/serials.py` | كل منطق الأرقام التسلسلية للشراء والبيع (وحدة مستقلة عن services) | 765 |
| `inventory/models.py` | 12 موديل: المنتج (البراند)، المنتج الأب (`ProductFamily`)، الفئة، الوحدة، المستودع، الحركة، الشرائح، الوحدة المُرقَّمة، التحويل، الجرد | 465 |
| `inventory/stock_status.py` | **مصدر الحقيقة الوحيد لحالة المخزون** (نفذ/منخفض/فائض/متوفّر): تعبير ORM ودالّة بايثون وفلتر — يستهلكها السيريالايزر والجدول والداشبورد والتقارير | 150 |

| `inventory/serializers.py` | تمثيل المنتج والحركة والمستندات | 353 |
| `inventory/urls.py` | 9 routers مركّبة على `/api/inventory/` (`core/urls.py`) | 21 |
| `inventory/agent_api.py` | نقطة بوت الفواتير للمنتجات (`/api/agent/products/`، مسجَّلة في `core/urls.py`). تسكن هنا لا في `core` لأن `.importlinter` يمنع `core` من استيراد `inventory.serializers`؛ ولا تستورد `sales`/`logistics` (عقد الاتجاه المعكوس) | 115 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `Product` | `sku`, `barcode`, `variant_group`, `brand`, `quantity_on_hand`, `avg_cost`, `sale_price`, `is_serialized`, `is_service`, `allow_negative_stock`, `warranty_months`, `min_stock_level`/`max_stock_level` (ثنائي إعادة الطلب: الأدنى **هو** نقطة الطلب، والأقصى هو المستوى الذي يُطلَب حتى بلوغه) | `category→ProductCategory`, `uom→UnitOfMeasure`، و6 FKs تجاوز حسابات على `accounting.Account`؛ فريد `(tenant, sku)`. `family→ProductFamily` **قابلٌ للفراغ** (task20) — البراند هذا هو `Product` الكلاسيكي بلا حذف حقل |
| `ProductFamily` (task20) | `name_ar`, `name_en`, `min_stock_level`/`max_stock_level`, `is_serialized`, `is_service`, `allow_negative_stock` | «المنتج» — الأب فوق `Product` (الشكل أ، #17). **بلا رقم إطلاقاً**: لا رصيد ولا تكلفة ولا FK من حركة؛ كل مجموعٍ يُشتقّ عند القراءة من `brands` (`Product.family` معكوساً). `category→ProductCategory`, `uom→UnitOfMeasure`، و6 FKs تجاوز حسابات على `accounting.Account` — نفس الأعمدة فيزيائياً موجودة أيضاً على `Product` (قاعدة التعايش، `inventory.services.resolve_family_field`) |
| `StockMovement` | `movement_type` (IN/OUT/ADJUST_IN/ADJUST_OUT/RETURN_IN/RETURN_OUT), `quantity`, `unit_cost`, `total_cost`, `reference_type`, `reference_id`, `quantity_before/after`, `avg_cost_before/after` | `product` (PROTECT)، `warehouse` (PROTECT)، `branch→tenants.Branch`، `partner→partners.Partner`؛ خاصية `origin` (`:270`) |
| `ProductCategory` | `name`, `parent` | `revenue_account`, `cogs_account`, `inventory_account` → `accounting.Account` |
| `Warehouse` | `code`, `is_default`, `is_active` | `branch→tenants.Branch` (اختياري)؛ فريد `(tenant, code)` لغير الفارغ |
| `ProductSerial` | `serial`, `status` (`in_stock`/`sold`) | `purchase_item→logistics.PurchaseInvoiceItem`، `sales_line→sales.SalesInvoiceLine`؛ فريد `(tenant, product, serial)`، وفهرس `(tenant, serial)` لبحث المسح الذي لا يعرف المنتج (`prodserial_tenant_serial`) |
| `ProductPriceTier` | `tier_type` (sale/purchase), `tier_number`, `price`, `tax_inclusive` | فريد `(product, tier_type, tier_number)` |
| `SupplierProduct` | `supplier_sku`, `supplier_name` | `supplier→partners.Partner`، `product→Product`؛ فريد `(tenant, supplier, supplier_sku)` — **لا** على `(tenant, supplier, product)`: للمورّد أن يحمل أكثر من رقم للمنتج الواحد، والممنوع عكسُه (رقمٌ واحد لمنتجين يجعل المطابقة تخميناً). محايد مالياً بالكامل |
| `WarehouseTransfer` / `WarehouseTransferLine` | `transfer_number`, `is_posted`, `quantity` | `source_warehouse` / `dest_warehouse` (PROTECT) — بلا قيد محاسبي (`:384`) |
| `Stocktake` / `StocktakeLine` | `is_posted`, `counted_quantity`, `system_quantity`, `variance` | `journal→accounting.JournalHeader` — قيد فرق الجرد |

## دوال الـservices العامة
```python
# التوقيعات فقط — منسوخة حرفياً من inventory/services.py
def record_stock_movement(
    *,
    product: Product,
    movement_type: str,
    quantity: Decimal,
    unit_cost: Decimal = Decimal('0'),
    reference_type: str = 'MANUAL',
    reference_id: int | None = None,
    partner=None,
    movement_date,
    notes: str = '',
    tenant=None,
    branch=None,
    warehouse=None,
) -> StockMovement:  # القلب: يقفل المنتج، يطبّق WAC، يُنشئ الحركة ويحدّث الرصيد ذرّياً (سطر 154)
def reverse_stock_movements(*, tenant_id, reference_id, reference_types) -> int:  # حذف حركات مستند + إعادة احتساب (302)
def find_stock_dependents(*, tenant_id, reference_id, reference_types) -> list[dict]:  # من بنى على هذه البضاعة (371)
def receive_shipment_stock(shipment, movement_date=None):  # استلام شحنة استيراد (431)
def product_profile(*, tenant_id: int, product_id: int) -> dict:  # بطاقة المنتج (710)
def category_descendant_ids(*, tenant_id: int, category_id: int) -> list[int]:  # التصنيف وكل أحفاده — نسخة واحدة يقرؤها الكرت المجمّع وفلتر `?category=` معاً
def category_descendant_product_ids(*, tenant_id: int, category_id: int) -> list[int]:  # منتجات تصنيفٍ وأحفاده — الخادم يشتقّها بدل تعدادها في الطلب
def product_group_profile(*, tenant_id: int, product_ids: list[int]) -> dict:  # الكرت المجمّع (823)
def product_stock_ledger(*, tenant_id, product_id=None, product_ids=None, limit=50, offset=0) -> dict:  # (887)
def partner_stock_movements(*, tenant_id, partner_id, limit=50, offset=0) -> dict:  # حركات مخزون الشريك مجمَّعةً تحت المستند المسبِّب (تبويب «المال» في كرته)
def document_stock_movements(*, tenant_id, reference_types, reference_id) -> dict:  # المحور الثالث: حركات **مستندٍ واحد** — أثر الفاتورة على المخزون داخل شاشتها، بلقطتَي `quantity_before`/`quantity_after` المخزَّنتين. بلا ترقيم: بنود المستند محدودة بطبعها
def product_linked_invoices(*, tenant_id, product_id=None, product_ids=None) -> list[dict]:  # (929)
def product_cost_breakdown(*, tenant_id: int, product_id: int) -> dict:  # (986)
def set_avg_cost_from_purchases(product) -> Decimal:  # النموذج الدوري: متوسط كل المشتريات (1070)
def apply_purchase_cost_model(product) -> None:  # يختار WAC المتحرك أو الدوري حسب SalesSettings (1087)
def reconcile_product_cogs(*, tenant_id: int, product_id: int, apply: bool = False, user=None) -> dict:  # (1107)
def warehouse_stock_summary(*, tenant_id: int, warehouse_id: int) -> dict:  # (78)
def generate_next_sku(tenant) -> str:  # (140)
def create_product_with_family(*, tenant=None, tenant_id=None, **fields) -> tuple[ProductFamily, Product]:  # نقطة الإنشاء الموحّدة الوحيدة (task20) — أربعة مسارات حيّة تمرّ من هنا: واجهة المنتجات، وتجسيد عرض المورّد، ومنتج الأجرة في `after_sales`، وجسر المزامنة `bridge`
def sync_family_from_product(product) -> bool:  # (task20) الأب مرآةٌ تتبع صفّ البراند — اتجاه الكتابة واحدٌ لا اثنان أثناء الانتقال
def resolve_family_field(product, field_name: str):  # قاعدة التعايش (task20) — من الأب إن وُجد، وإلا من صفّ البراند نفسه
def post_warehouse_transfer(transfer, user=None):  # (1208)
def unpost_warehouse_transfer(transfer, user=None):  # (1248)
def post_stocktake(stocktake, user=None):  # (1274)
```
```python
# inventory/serials.py — الأرقام التسلسلية (نيّة على البند ← حالة في ProductSerial)
SERIAL_MODE_OFF = 'off'; SERIAL_MODE_OPTIONAL = 'optional'; SERIAL_MODE_REQUIRED = 'required'  # (23-25)
def product_tracks_serials(product) -> bool:  # (41)
def normalize_serials(raw, *, label: str = '') -> list[str]:  # تنظيف + منع التكرار (50)
def generate_serial_range(start: str, count) -> list[str]:  # يحفظ البادئة وخانات الصفر (93)
def purchase_serial_mode(tenant_id) -> str:  # من logistics.PurchaseSettings (148)
def sales_serial_mode(tenant_id) -> str:  # من sales.SalesSettings.serial_entry_mode (160)
def assert_purchase_serials_declared(invoice) -> None:  # حارس «إجباري» قبل ترحيل الشراء (176)
def apply_purchase_serials(*, tenant, rows) -> int:  # الاستلام يُنشئ الوحدات in_stock (275)
def register_existing_serials(*, tenant_id, product, serials) -> int:  # ترقيم مخزون قائم، سقفه الرصيد (228)
def release_purchase_serials(*, tenant_id, quantities_by_item, document_label='', action_label='التراجع عن') -> int:  # (357)
def consume_sales_serials(invoice, lines) -> int:  # ترحيل البيع: المختار صريحاً ثم FIFO للباقي (507)
def release_sales_serials(invoice) -> int:  # إلغاء ترحيل البيع: عودة in_stock مع تفريغ الرابط (596)
def restore_returned_sales_serials(return_invoice, lines) -> int:  # مرجع البيع يُعيد وحدات الفاتورة الأصلية FIFO (613)
def product_serials(*, tenant_id, product_id, status=None, limit=500) -> list[dict]:  # (704)
def search_serials(*, tenant_id, q='', status=None, product_id=None, limit=100) -> list[dict]:  # (712)
def generate_product_barcode(tenant_id, *, attempts: int = 40) -> str:  # EAN-13 (747)
```

## أهم الـAPI endpoints
كلها تحت البادئة `/api/inventory/` (`core/urls.py`).

| Method | المسار | الـview |
|---|---|---|
| GET/POST | `products/` | `ProductViewSet` (`views.py`) |
| GET | `products/{id}/profile/` · `products/{id}/stock-ledger/` · `products/{id}/cost-breakdown/` | (405) · (411) · (433) |
| GET | `products/{id}/stock-movements/` · `products/{id}/invoices/` | (398) · (426) |
| GET | `products/{id}/serials/` · POST `products/{id}/serials/register/` | (559) · (570) |
| **POST** | `products/bulk-set-group/` | تعيين «النوع» (`variant_group`) و/أو البراند على منتجاتٍ محدَّدة دفعةً واحدة — `ProductViewSet` (`bulk_set_group`). الحقل الغائب من الجسم لا يُمَسّ، والفارغ يُمحى. يشترط `inventory.item.manage` |
| **POST** | `products/apply-replenishment/` | تثبيت الحدّين المقترَحين على منتجاتٍ محدَّدة — `ProductViewSet` (`apply_replenishment`). كتابةٌ حقيقية: تشترط `inventory.item.manage` وليست في `read_only_post_actions`، والمحدِّد في **جسم** الطلب |
| POST | `products/generate_barcode/` · `products/generate_serials/` | (522) · (541) |
| GET | `products/groups/` · `products/brands/` | (468) · (460) |
| GET/**POST** | `products/group-profile/` · `products/group-ledger/` · `products/group-invoices/` | الكرت المجمّع — المحدِّد في **جسم** الطلب |
| GET | `serials/` | `ProductSerialViewSet` (598) |
| GET/POST/DELETE | `supplier-products/?product=&supplier=&sku=` | `SupplierProductViewSet` |
| GET/POST | `stock-movements/` · GET `stock-movements/summary/` | `StockMovementViewSet` (689) · (792) |
| GET | `warehouses/` · `warehouses/{id}/stock/` | `WarehouseViewSet` (615) · (662) |
| POST | `warehouse-transfers/{id}/post/` · `warehouse-transfers/{id}/unpost/` | `WarehouseTransferViewSet` (844) · (856) |
| POST | `stocktakes/{id}/post/` | `StocktakeViewSet` (881) |
| GET | `categories/` · `uom/` | `CategoryViewSet` (38) · `UnitOfMeasureViewSet` (77) |
| GET | `product-families/` | `ProductFamilyViewSet` (task20) — «المنتج» الأب، **قراءةٌ فقط عمداً**: يُنشأ حصراً مع براندِه الضمنيّ عبر `products/` (`create_product_with_family`) فلا يوجد «منتج بلا براندات»، والكتابة عليه مباشرةً تفتح اتجاه كتابةٍ ثانياً يترك القرّاء الحاليين (وكلّهم يقرأ من صفّ البراند) على قيمةٍ قديمة |

### الكرت المجمّع: المحدِّد في الجسم لا في العنوان
النقاط الثلاث تقبل `POST` بجسم JSON فيه أحد محدِّدَين:

| المحدِّد | المعنى |
|---|---|
| `{"category": 3}` | التصنيف **وكل أحفاده** — الخادم يشتقّ المنتجات (`category_descendant_product_ids`) |
| `{"ids": [1, 2, 3]}` | تعدادٌ صريح — مجموعات `group_key`، أو أسطر جردٍ بعينها |

(و`group-ledger` يقبل `limit`/`offset` في الجسم نفسه.)

**لماذا POST لقراءة؟** كان التعداد يسافر في سطر الطلب (`?ids=1,2,3…`): تصنيفُ
جذرٍ فيه ~1500 منتج ⇒ عنوانٌ ~7.5KB، فوق `large_client_header_buffers 8k` في
nginx ⇒ **414/400 في الإنتاج بينما التطوير يمرّ**. `GET` مع `?ids=`/`?category=`
يبقى مفهوماً لتوافق الروابط القديمة (`/product-group?ids=…`).

هذه الـPOST **قراءة لا كتابة**: الـview يعلنها في `read_only_post_actions`،
فيفحصها `core/permissions.py` (`is_read_only_post`) كأنها `GET` — «مستعرض»
يبقى يراها، والمسار يبقى مقيَّداً على المحاسب القانوني الخارجي كما كان — ولا
يُبطل `store/cache.py` كاش الكتالوج عندها.

## الاعتماديات
**يعتمد على:** (كل الاستيرادات عبر أبواب أخرى **كسولة داخل الدوال** — الملف يستورد على مستوى الوحدة من `tenants` و`partners` فقط، `models.py:2-3`)
- `sales.models.SalesSettings` — لقرار السماح بالمخزون السالب داخل `record_stock_movement` (`inventory/services.py`)، ولنمط الأرقام التسلسلية (`inventory/serials.py`)، ولنموذج التكلفة (`inventory/services.py`).
- `sales.services` — `reserved_quantity_map` و`last_sale_price` في بطاقة المنتج (`inventory/services.py` و`:748`)، و`reserved_quantity_map` في العرض (`inventory/views.py`).
- `logistics.models` — `PurchaseInvoice/PurchaseInvoiceItem/PurchaseSettings` (`inventory/services.py:447,681,941` و`serials.py`)؛ و`accounting.services.post_journal` لقيد الجرد والتحويل (`services.py`, `:1281`).
- `accounting.models.Account` عبر FKs بسلسلة نصية (`'accounting.Account'`) في `ProductCategory` و`Product` — لا استيراد مباشر.

**يعتمد عليه:** `sales` (`models.py:6-7`, `services.py:26-30`)، `logistics` (`models.py:4-5`, `services.py:996-998,1278-1281,1697-1698`, `views.py:3455-4123`)، `accounting` (`services.py`)، `core` (`dashboard_api.py`, `reports.py`, `pricing.py`, `plans.py`)، `after_sales` (`services.py:57,177`)، `bridge`.

## حالة المخزون والتجديد (T-REORDER)

**قاعدة الحالة تعيش في `inventory/stock_status.py` وحدها.** كانت مكتوبة ستّ مرّات
(السيريالايزر · فلتر الجدول · الداشبورد · تقرير تحت حدّ الطلب · `StockLevelsPage` ·
`ItemsManagement`) وتباعدت فعلاً: الداشبورد كان يشترط حدّاً أدنى **قبل** أن يعدّ
منتجاً نافداً فيخفي أغلب النافد، والشاشة كانت تصبغ كلّ رصيدٍ صفر «منخفضاً» بينما
الخادم يسمّيه «نفذ».

| القرار | أين يعيش |
|---|---|
| الحالة تُقاس على **المتاح** (الرصيد − المحجوز) لا على الرصيد | `stock_status.py` (`available_of`, `available_expression`) |
| «نفذ» **لا يشترط** حدّاً أدنى — المتاح ≤ 0 نفادٌ سواء ضُبط حدّ أم لا | `stock_status.py` (`stock_status_of`) |
| الحدّ الفعّال = اليدوي إن ضُبط، وإلّا المقترَح المحسوب | `stock_status.py` (`effective_min`) |
| الخدمة «متوفّرة» دائماً — بلا مخزونٍ يُقاس | `stock_status.py` (`stock_status_of`) |
| المعادلات (الصرف اليومي · مخزون الأمان · الحدّان) | `core/replenishment.py` (`suggest_levels`) |
| مهلة التوريد: وسيط (تاريخ أول وارد لفاتورة الطلبية − تاريخ الطلبية)، للمنتج ثم للمورّد ثم للشركة ثم إعداد | `core/replenishment.py` (`_lead_time_samples`, `_lead_for`) |
| قرار الطلب من المنتج **ونوعه** معاً: عاجل/مؤجَّل/راكد | `core/replenishment.py` (`_urgency_of`) |
| الكتابة الوحيدة — بفعلٍ صريح من المستخدم | `core/replenishment.py` (`apply_suggested_levels`) |

بارامترات الشركة الثلاثة (نافذة التحليل · المهلة الافتراضية · مدة المراجعة) على
`logistics.PurchaseSettings` — التجديد قرارٌ شرائي، فإعداداته حيث تعيش إعدادات الشراء.

**والمحرّك يسكن في `core/` لا هنا**: حسابه يحتاج `sales.services` (المحجوز) و
`logistics.models` (مهلة التوريد)، و`.importlinter` يمنع `inventory` من استيرادهما
(عقد «الاتجاه المعكوس»). ما بقي هنا هو `stock_status.py` وحده — قاعدةُ **حالة**
المخزون لا تحتاج غير `inventory`.

**«النوع» (`variant_group`) كان بلا مدخل**: الحقل والنقطة (`products/groups/`)
موجودان منذ task31، ولا شاشةَ تكتبه — فبقي فارغاً على **كل** منتجٍ في كل شركة،
وبفراغه يسقط `product_group_key` على اسم المنتج: كل منتجٍ نوعٌ بذاته، فلا بدائل في
الفاتورة ولا قرار «مؤجَّل». صار له مدخلان: حقلٌ في كرت المنتج
(`ItemForm.tsx`)، وتعيينٌ جماعي للمحدَّد من «أرصدة المخزون»
(`StockLevelsPage.tsx` ← `products/bulk-set-group/`).

## قواعد لا يجوز كسرها
- **لا يُعدَّل `quantity_on_hand` أو `avg_cost` إلا عبر `record_stock_movement`** (أو `_recompute_product_stock` بعد حذف حركات). هي الدالة الوحيدة التي تقفل المنتج بـ`select_for_update` داخل `transaction.atomic` (`services.py:187-188`) وتحفظ لقطات before/after على الحركة.
- **الكمية موجبة دائماً**: `record_stock_movement` يرفض `quantity <= 0` (`services.py`) — الاتجاه يأتي من `movement_type` لا من إشارة الكمية.
- **معادلة WAC**: الوارد يعدّل المتوسط `new_avg = (old_qty*old_avg + qty*cost) / new_qty`؛ **الصادر لا يغيّر `avg_cost` إطلاقاً** ويأخذ تكلفته من المتوسط الحالي (`services.py:226-229`). و`_recompute_product_stock` يعيد تطبيق نفس المعادلة بالترتيب الزمني (`:287-296`).
- **المخزون السالب**: يُرفض الصرف إن `qty_before < quantity` إلا إذا سمح `SalesSettings.allow_negative_stock_default` أو `Product.allow_negative_stock` (`services.py:206-224`) — أي أن قرار مخزون يعيش في `sales` لا هنا.
- **لا تُكتب قاعدة «منخفض/نفذ» في أي مكان آخر** — استورد من `inventory/stock_status.py`.
  ستّ نسخٍ متباعدة هي ما استدعى الوحدة، والسابعة ستتباعد كما تباعدت أخواتها.
- **الاقتراح يُعرَض ولا يُكتب.** `min_stock_level` اليدوي يسبق المقترَح دائماً
  (`effective_min`)، والكتابة لا تحدث إلا عبر `apply_suggested_levels` بفعلٍ صريح.
  ومنتجٌ بلا اقتراح (سجلّ أقصر من `MIN_HISTORY_DAYS` أو بلا مبيعات) **لا يُكتب عليه
  صفر**: «لا أعرف بعد» ليست «لا تطلب أبداً».
- **أرقام «النوع» مجاميعُ أرقام أفراده** لا حسابٌ ثانٍ عليها — كي يساوي مجموع
  التنقيب رقمَ الصفّ (`docs/modules/core.md` — 6.1.1).
- **المنتج يُحفَظ تحت التصنيف المختار حرفياً — بلا اختراع تصنيفٍ فرعي.** كان
  كرت المنتج يُنشئ عند كل حفظٍ يحمل `variant_group` تصنيفاً باسمه ويجعل
  المختارَ أباً له (`_auto_create_group_category`) — إنشاءٌ صامت بمطابقةٍ نصّية
  على الشركة كلها. **حُذفت بلا بديل في task20** (#20): التصنيف الآن **اختياري**
  دائماً، والتجميع وظيفة `variant_group` وحدها كحقلٍ ظاهر يُكتب بقصد — لا صلة له
  بالتصنيف بعد الحذف.
- **لا حقلَ يُعرض ولا يُحفظ.** كان في كرت المنتج نحو 25 حقلاً تُملأ ويُقال
  «تم الحفظ» ولا أثر لها: لا وجود لها في `ProductSerializer.Meta.fields` فيرميها
  DRF بصمت. القاعدة الآن: ما تعرضه الشاشة يصل الخادم، وما لا مكان له يُحذف من
  الشاشة. الحكم بمعيار المنتجات الاحترافية لا بما يسهل: الوحدات المتعدّدة
  والوصف وموقع التخزين وشرائح الأسعار وتجاوزات الحسابات **وُصلت** (بهجرة حين
  لزم)، و«رقم الكتلوج» (بديله `SupplierProduct`) والكميات المجانية ومعادلات
  التصنيع (موديول تصنيعٍ كامل في Odoo لا حقل) **حُذفت**.
- **شرائح الأسعار ليست حقلاً مخزَّناً فحسب**: `core/pricing.py`
  (`resolve_sales_price`) يقرأ شريحة البيع الأولى كمصدره الخامس، فحفظُها من
  الكرت يُدخلها تسعير الفواتير فعلياً. الكتابة المتداخلة تصف **الحالة النهائية**:
  ما ورد يُنشأ أو يُحدَّث بمفتاح `(tier_type, tier_number)` — وهو نفسه قيد
  التفرّد — وما غاب يُحذف. وغيابُ المفتاح كلّه ≠ قائمةٌ فارغة: الأول «لا تمسّ»
  والثاني «امسح»، وبلا هذا التمييز كان كل PATCH لاسمٍ يمسح الشرائح.
- **تجاوز الحساب على المنتج يُفحص بالشركة** (`_validate_account_overrides`)
  كالتصنيف تماماً: الـFK لا يعرف الشركة، فمعرّفٌ من شركةٍ أخرى يُرحّل بيع المنتج
  على دفترٍ ليس دفترها.
- **خوارزمية شجرة التصنيفات نسخةٌ واحدة في الواجهة**:
  `frontend_v2/utils/categoryTree.ts` (`buildCategoryIndex`، `sortCategoryRows`،
  `descendantIds`، `categoryPathLabel`، `eligibleParents`). أربع نسخ متباعدة هي
  ما استدعى الوحدة، واختلافها كان يظهر عند الحالة الحدّية: التصنيف اليتيم يبقى
  جذراً قابلاً للاختيار في واحدة ويختفي من الشجرة في أخرى.
- **المصطلح — ثلاث طبقات لا اثنتان (T-PRODUCT، يَنسخ قرار T-ITEMS M2)**:
  «تصنيف» = فئةٌ في الشجرة (`Category`) · «صنف» = العائلة/الموديل
  (`Product.variant_group`) · «منتج» = السجلّ القابل للبيع (`Product`). كان
  «صنف» يسمّي السجلَّ نفسه و«النوع» يسمّي عائلته، فلم يبقَ اسمٌ للطبقة الوسطى
  وصار كلُّ حديثٍ عن الهرمية غامضاً. الترتيب الآن يطابق فصل Odoo بين
  `product.template` والمتغيّرات.
- **تعديل المنتج من المستند: معالِجٌ واحد بنصفين.** لكل محرّر مستندٍ
  `applyProductUpdate` واحدة تُمرَّر بنفس المرجع إلى `ItemQuickEditModal`
  و`ProductCardModal` (عبر `onProductSaved`) — فالقلم والبطاقة يسلّمان نفس
  الحمولة لنفس المعالِج. النصفان: **الكتالوج** (تجاوزُ الصفّ لا إلحاقُه — إلحاقٌ
  مشروطٌ بالغياب يُسقط كلَّ منتجٍ موجود، أي كلَّ ما يمسّه التعديل) و**السطور**
  (إعادة تطبيق الاسم حيث يكون ملتقَطاً نسخةً على السطر: الشراء وعرض السعر؛
  محرّر البيع يقرأ من `productsById` فلا يحتاجه).
  حرّاسه: `frontend_v2/e2e/product-quick-edit-propagation.spec.ts` — ويُثبِّت
  مسارَ جلب الكتالوج على الاسم القديم كي يقيس الآلية المحلية لا الجلب الثقيل.
- **اسم المنتج في جدول المنتجات يُحرَّر في مكانه** (`ItemsManagement`): نقرتان
  أو F2، حفظٌ متشائم عبر `dirtySimplePayload` نفسها (لا مسار حفظٍ ثانٍ)،
  والنقرة المفردة لا تنقُل — وإلّا كان قولُ «ليس رابطاً» كذباً.
- **ولا اسمَ منتجٍ بشكل الرابط في شاشةٍ أخرى** (`StockLevelsPage`): «أرصدة
  المخزون» كانت تعرض الاسم زرّاً أزرقَ مسطَّراً يَعِد بالانتقال ولا يفتح طريقاً
  للتعديل. صار نصّاً، ووجهتاه أيقونتان صريحتان بجانبه — قلمٌ يفتح
  `ItemQuickEditModal` (نفس نافذة المستند والبطاقة، لا مسار ثالث) وسهمٌ يفتح
  حركة المخزون في تبويب مستقل. والترقيع بعد الحفظ **حقول الاسم وحدها**: صفّ هذه
  الشاشة يحمل الرصيد والمحجوز والقيمة، وهي محسوبةٌ لا يعيدها ردّ التعديل.
- **تعريف «الوضع البسيط» نسخةٌ واحدة**: `frontend_v2/utils/itemSimpleFields.ts`
  (`simplePayload`، `dirtySimplePayload`) يتشاركه الكرت الكامل والإنشاء السريع
  والتحرير السريع. ثلاث شاشات تبني حمولتها بيدها = ثلاث حمولات متباعدة، وقد كان
  ذلك حاصلاً: الإنشاء السريع يرسل وحدة القياس باسمٍ ليس في العقد فتُبتلع.
- **شجرة التصنيفات لا تقبل حلقة**: `CategorySerializer` (`_validate_parent`) يرفض
  أن يكون الأب العقدةَ نفسها أو أحدَ أحفادها أو تصنيفاً من شركة أخرى، ويرفض الاسم
  الفارغ. الحلقة تُدوِّر كلّ من يمشي الشجرة، ومجموعةُ `seen` في القارئ الناجي
  تُخفيها ولا تمنعها — فالمنع عند الكتابة.
- **التصنيف محدِّدٌ يعني شجرته** أينما ظهر: فلتر `?category=` وكرت المجموعة كلاهما
  يمرّ بـ`category_descendant_ids`. كان الأول exact-id والثاني شجرةً، فتصنيفُ أبٍ
  يعرض «لا منتجات» بينما كرته المجمّع يعدّ المئات.
- **`RETURN_IN` بلا تكلفة يأخذ المتوسط الحالي** كي لا ينحرف WAC (`services.py:195-196`).
- **عكس الحركات محصور بالمستند**: `reverse_stock_movements` يفلتر بـ`(tenant, reference_id, reference_type ∈ types)` ثم يُعيد احتساب كل منتج متأثر (`services.py:311-324`) — فلا تُمَسّ حركات مستند آخر.
- **نموذج التكلفة قرارٌ في مكان واحد**: `apply_purchase_cost_model` (`services.py`) — إن كانت الشركة على WAC المتحرك فلا يُدهَس `avg_cost` الذي بناه `record_stock_movement`؛ وإلا يُضبط من متوسط المشتريات.
- **الوحدة المُرقَّمة تُستهلَك بترحيل البيع لا بخروجها**: `consume_sales_serials` يتخطّى البند الذي استُهلكت وحداته فعلاً فإعادة الترحيل idempotent؛ والمختار صريحاً يجب أن يكون `in_stock` ولنفس المنتج وإلا رُفض (`serials.py` — `consume_sales_serials`).
- **«إجباري» في البيع يعني الاختيار لا التخصيص**: التخصيص التلقائي FIFO حكرٌ على `optional`؛ تحت `required` يجب أن يحمل كل بند تسلسليٍّ أرقاماً بعدد كميته، وإلّا رُفض الترحيل **قبل أي كتابة** (`serials.py` — `assert_sales_serials_declared`، مُستدعى من `sales/services/flow.py` — `post_sales_invoice`)، و`consume_sales_serials` خط الدفاع الثاني. السبب: FIFO يقول «خرجت أقدم وحدة» لا «خرجت هذه الوحدة»، فمطالبةُ كفالةٍ لاحقة تُطابَق برقمٍ لم يره أحد على العلبة. مخرج المخزون القديم بلا أرقام هو `register_existing_serials` من كرت المنتج، والرسالة تسمّيه.
- **`_serial_row` هو المصدر الواحد لرحلة الوحدة** (`serials.py`): بطاقة المنتج
  وشاشة الوحدات وحلّال المسح (`core/scan.py`) يقرؤونه جميعاً، والمسح **يُثريه**
  بالكفالة والصيانات وسعر الشراء ولا ينسخه — استعلامٌ ثانٍ هنا كان سيتباعد عنه
  بعد أول حقلٍ يُضاف هناك. والإثراء يُحسب **مرّةً للرقم لا مرّةً لكل وحدة**: كل
  الوحدات المطابقة تحمل الرقم نفسه (به طابقت)، فحسابُه داخل الحلقة كان N+1.
- **رقم المنتج عند المورّد جدولُ ربط لا حقل على المنتج** (`SupplierProduct`): المنتج الواحد يأتي من أكثر من مورّد ولكلٍّ ترقيمه — وهو ما استقرّ عليه Odoo (`product.supplierinfo.product_code`) وNetSuite (`itemvendor.vendorCode`). **ولا يُحشَر رقمٌ في `name_en`** (معناه اسم المنتج بالإنجليزية)؛ النقل من الحشوة القديمة عبر `migrate_supplier_sku_from_name_en` وهو معاينةٌ بلا `--commit`. البحث يشمل الرقم (`ProductViewSet.search_fields`)، ويصل منتقي بنود المستندات عبر `supplier_codes_text` في عقد `view=lookup` وحده — العقد الكامل لا يحمله. و**لقطةُ الرقم على المستند تبقى في `logistics.PurchaseInvoiceItem.catalog_number`**: البيانات الرئيسية تتغيّر والمستند المرحّل لا يتغيّر معها.
- **الترقيم يصف مخزوناً قائماً ولا يخلقه**: `register_existing_serials` سقفه رصيد المنتج ولا يُنشئ حركة مخزون ولا قيداً (`serials.py:247-259`).
- **التحويل بين المستودعات بلا قيد محاسبي** — صافي أثره على إجمالي الشركة صفر (`models.py:382-384`).
- **`ProductFamily` (المنتج، الأب) لا يحمل رقماً أبداً** (task20، #17): لا رصيد،
  لا تكلفة، لا FK من حركةٍ أو بند مستند. أي مجموعٍ على مستوى المنتج (رصيدٌ كلي،
  تكلفةٌ مرجَّحة…) يُشتقّ عند القراءة من `brands` (`Product.family` معكوساً) —
  تخزينُ رقمٍ هنا يكرّر العطب الذي بُني هذا النموذج ليمنعه.
- **كل مسار إنشاء منتجٍ في الخادم يمرّ بـ`create_product_with_family` وحدها**
  (`inventory/services.py`): تُنشئ الأب وبراندَه الضمنيّ معاً ذرّياً. مسارا
  اليوم — `ProductSerializer.create` و`logistics.services.materialize_quotation_draft_parties`
  — كلاهما يستدعيها؛ مسارٌ ثالثٌ ينشئ `Product` مباشرةً يُسرّب براندًا بلا أبٍ فوقه.
- **قاعدة التعايش الانتقالية** (`resolve_family_field`): حقول #9 «على المنتج»
  (التصنيف، الوحدة، حدّا التجديد، طبيعة الصنف، الحسابات الستّة) فيزيائياً لا
  تزال أعمدةً على صفّ `Product` أيضاً — تُنسَخ إليه دفاعياً عند الإنشاء عبر
  `create_product_with_family` كي لا ينكسر مستهلكٌ قائم يقرأ منها مباشرةً. لا
  تُحذف تلك الأعمدة، ولا تُبنَ فرادةُ `(family, brand)` على فهرسٍ شرطي (MySQL
  لا يدعمه) — لا فرادة من هذا النوع في هذا النطاق أصلاً.

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `core/tests/test_reports_stock_dimension.py` | تقرير «حركة المخزون حسب بُعد»: المحاور الخمسة، والتنقيب الذي يطابق مجموعُه رقمَ الصفّ |
| `inventory/tests/test_product_serials.py` | مصفوفة الأنماط (بدون/اختياري/إجباري) على الجانبين، دورة بيع ⇄ إلغاء ترحيل، تخصيص FIFO |
| `inventory/tests/test_serial_invoice_journey.py` | نفس الرحلة عبر HTTP بحمولة المحرِّرين (`items[].serials` / `lines[].serials`) |
| `inventory/tests/test_inventory_documents.py` | التحويل (أثر صفري، حركتان موسومتان) والجرد (تسوية + قيد الفرق) |
| `inventory/tests/test_product_profile.py` | بطاقة المنتج: المؤشرات، سجلّ الحركة (الرصيد الجاري يطابق on-hand)، الفواتير المرتبطة |
| `inventory/tests/test_item_aggregates.py` | التجميعات من `StockMovement` كمصدر وحيد (وارد تراكمي، متوسط مبيعات 90/28 يوماً) |
| `inventory/tests/test_account_overrides.py` | سلسلة الحسابات: تجاوز المنتج ← تجاوز الفئة ← الافتراضي |
| `inventory/tests/test_brand_grouping.py` · `test_group_card_performance.py` | تجميع البراندات بـ`group_key`، وثبات عدد الاستعلامات (كان N+1) |
| `inventory/tests/test_product_api.py` | توليد SKU خادمي، ترتيب/بحث/ترقيم صفحات، عزل الشركات |
| `inventory/tests/test_product_family.py` | task20: الإنشاء الذرّي (الأب + البراند الضمني) من مساري التسجيل معاً، عزل الشركات على `ProductFamily`، وقاعدة التعايش (مع/بلا أب) |
| `inventory/tests/test_supplier_products.py` | أرقام الموردين: المنتج من مورّدين، ورقمان لمورّد، ومنع الرقم الواحد لمنتجين، والبحث بالرقم بلا تكرار صفّ |
