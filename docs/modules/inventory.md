# inventory — الأصناف والمخزون: الحركة الوحيدة التي تغيّر الرصيد والتكلفة، والوحدات المُرقَّمة

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
يملك هذا الـapp بطاقة الصنف (`Product`)، تصنيفاته ووحداته وشرائح أسعاره، المستودعات،
وسجلّ حركة المخزون (`StockMovement`) الذي هو **المصدر الوحيد** لتغيير `quantity_on_hand`
و`avg_cost`. كل الأبواب — البيع، الشراء، الاستلام، التحويل بين المستودعات، الجرد —
تمرّ من `record_stock_movement()` الذي يحدّث الرصيد ومتوسط التكلفة ذرّياً ويحفظ لقطات
قبل/بعد على الحركة نفسها. ويستضيف كذلك تتبّع الوحدة المُرقَّمة (`ProductSerial`) في ملف
`serials.py` المستقل، ومستندَي `WarehouseTransfer` و`Stocktake`.

## أهم الملفات
| الملف | الغرض | أسطر |
|---|---|---|
| `inventory/services.py` | `record_stock_movement` + WAC، عكس الحركات، بطاقة الصنف، نماذج التكلفة، ترحيل التحويل والجرد | 1368 |
| `inventory/views.py` | ViewSets: المنتجات، الحركات، المستودعات، التحويلات، الجرد | 891 |
| `inventory/serials.py` | كل منطق الأرقام التسلسلية للشراء والبيع (وحدة مستقلة عن services) | 765 |
| `inventory/models.py` | 11 موديل: الصنف، الفئة، الوحدة، المستودع، الحركة، الشرائح، الوحدة المُرقَّمة، التحويل، الجرد | 465 |
| `inventory/serializers.py` | تمثيل الصنف والحركة والمستندات | 353 |
| `inventory/urls.py` | 8 routers مركّبة على `/api/inventory/` (`core/urls.py`) | 21 |
| `inventory/agent_api.py` | نقطة بوت الفواتير للأصناف (`/api/agent/products/`، مسجَّلة في `core/urls.py`). تسكن هنا لا في `core` لأن `.importlinter` يمنع `core` من استيراد `inventory.serializers`؛ ولا تستورد `sales`/`logistics` (عقد الاتجاه المعكوس) | 115 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `Product` | `sku`, `barcode`, `variant_group`, `brand`, `quantity_on_hand`, `avg_cost`, `sale_price`, `is_serialized`, `is_service`, `allow_negative_stock`, `warranty_months` | `category→ProductCategory`, `uom→UnitOfMeasure`، و6 FKs تجاوز حسابات على `accounting.Account` (`models.py:122-151`)؛ فريد `(tenant, sku)` (`:156`) |
| `StockMovement` | `movement_type` (IN/OUT/ADJUST_IN/ADJUST_OUT/RETURN_IN/RETURN_OUT), `quantity`, `unit_cost`, `total_cost`, `reference_type`, `reference_id`, `quantity_before/after`, `avg_cost_before/after` | `product` (PROTECT)، `warehouse` (PROTECT)، `branch→tenants.Branch`، `partner→partners.Partner`؛ خاصية `origin` (`:270`) |
| `ProductCategory` | `name`, `parent` | `revenue_account`, `cogs_account`, `inventory_account` → `accounting.Account` |
| `Warehouse` | `code`, `is_default`, `is_active` | `branch→tenants.Branch` (اختياري)؛ فريد `(tenant, code)` لغير الفارغ |
| `ProductSerial` | `serial`, `status` (`in_stock`/`sold`) | `purchase_item→logistics.PurchaseInvoiceItem`، `sales_line→sales.SalesInvoiceLine`؛ فريد `(tenant, product, serial)` (`:362`) |
| `ProductPriceTier` | `tier_type` (sale/purchase), `tier_number`, `price`, `tax_inclusive` | فريد `(product, tier_type, tier_number)` |
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
) -> StockMovement:  # القلب: يقفل الصنف، يطبّق WAC، يُنشئ الحركة ويحدّث الرصيد ذرّياً (سطر 154)
def reverse_stock_movements(*, tenant_id, reference_id, reference_types) -> int:  # حذف حركات مستند + إعادة احتساب (302)
def find_stock_dependents(*, tenant_id, reference_id, reference_types) -> list[dict]:  # من بنى على هذه البضاعة (371)
def receive_shipment_stock(shipment, movement_date=None):  # استلام شحنة استيراد (431)
def product_profile(*, tenant_id: int, product_id: int) -> dict:  # بطاقة الصنف (710)
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
| POST | `products/generate_barcode/` · `products/generate_serials/` | (522) · (541) |
| GET | `products/groups/` · `products/brands/` · `products/group-profile/` · `products/group-ledger/` · `products/group-invoices/` | (468) · (460) · (485) · (494) · (512) |
| GET | `serials/` | `ProductSerialViewSet` (598) |
| GET/POST | `stock-movements/` · GET `stock-movements/summary/` | `StockMovementViewSet` (689) · (792) |
| GET | `warehouses/` · `warehouses/{id}/stock/` | `WarehouseViewSet` (615) · (662) |
| POST | `warehouse-transfers/{id}/post/` · `warehouse-transfers/{id}/unpost/` | `WarehouseTransferViewSet` (844) · (856) |
| POST | `stocktakes/{id}/post/` | `StocktakeViewSet` (881) |
| GET | `categories/` · `uom/` | `CategoryViewSet` (38) · `UnitOfMeasureViewSet` (77) |

## الاعتماديات
**يعتمد على:** (كل الاستيرادات عبر أبواب أخرى **كسولة داخل الدوال** — الملف يستورد على مستوى الوحدة من `tenants` و`partners` فقط، `models.py:2-3`)
- `sales.models.SalesSettings` — لقرار السماح بالمخزون السالب داخل `record_stock_movement` (`inventory/services.py`)، ولنمط الأرقام التسلسلية (`inventory/serials.py`)، ولنموذج التكلفة (`inventory/services.py`).
- `sales.services` — `reserved_quantity_map` و`last_sale_price` في بطاقة الصنف (`inventory/services.py` و`:748`)، و`reserved_quantity_map` في العرض (`inventory/views.py`).
- `logistics.models` — `PurchaseInvoice/PurchaseInvoiceItem/PurchaseSettings` (`inventory/services.py:447,681,941` و`serials.py`)؛ و`accounting.services.post_journal` لقيد الجرد والتحويل (`services.py`, `:1281`).
- `accounting.models.Account` عبر FKs بسلسلة نصية (`'accounting.Account'`) في `ProductCategory` و`Product` — لا استيراد مباشر.

**يعتمد عليه:** `sales` (`models.py:6-7`, `services.py:26-30`)، `logistics` (`models.py:4-5`, `services.py:996-998,1278-1281,1697-1698`, `views.py:3455-4123`)، `accounting` (`services.py`)، `core` (`dashboard_api.py`, `reports.py`, `pricing.py`, `plans.py`)، `after_sales` (`services.py:57,177`)، `bridge`.

## قواعد لا يجوز كسرها
- **لا يُعدَّل `quantity_on_hand` أو `avg_cost` إلا عبر `record_stock_movement`** (أو `_recompute_product_stock` بعد حذف حركات). هي الدالة الوحيدة التي تقفل الصنف بـ`select_for_update` داخل `transaction.atomic` (`services.py:187-188`) وتحفظ لقطات before/after على الحركة.
- **الكمية موجبة دائماً**: `record_stock_movement` يرفض `quantity <= 0` (`services.py`) — الاتجاه يأتي من `movement_type` لا من إشارة الكمية.
- **معادلة WAC**: الوارد يعدّل المتوسط `new_avg = (old_qty*old_avg + qty*cost) / new_qty`؛ **الصادر لا يغيّر `avg_cost` إطلاقاً** ويأخذ تكلفته من المتوسط الحالي (`services.py:226-229`). و`_recompute_product_stock` يعيد تطبيق نفس المعادلة بالترتيب الزمني (`:287-296`).
- **المخزون السالب**: يُرفض الصرف إن `qty_before < quantity` إلا إذا سمح `SalesSettings.allow_negative_stock_default` أو `Product.allow_negative_stock` (`services.py:206-224`) — أي أن قرار مخزون يعيش في `sales` لا هنا.
- **`RETURN_IN` بلا تكلفة يأخذ المتوسط الحالي** كي لا ينحرف WAC (`services.py:195-196`).
- **عكس الحركات محصور بالمستند**: `reverse_stock_movements` يفلتر بـ`(tenant, reference_id, reference_type ∈ types)` ثم يُعيد احتساب كل صنف متأثر (`services.py:311-324`) — فلا تُمَسّ حركات مستند آخر.
- **نموذج التكلفة قرارٌ في مكان واحد**: `apply_purchase_cost_model` (`services.py`) — إن كانت الشركة على WAC المتحرك فلا يُدهَس `avg_cost` الذي بناه `record_stock_movement`؛ وإلا يُضبط من متوسط المشتريات.
- **الوحدة المُرقَّمة تُستهلَك بترحيل البيع لا بخروجها**: `consume_sales_serials` يتخطّى البند الذي استُهلكت وحداته فعلاً فإعادة الترحيل idempotent؛ والمختار صريحاً يجب أن يكون `in_stock` ولنفس الصنف وإلا رُفض (`serials.py` — `consume_sales_serials`).
- **«إجباري» في البيع يعني الاختيار لا التخصيص**: التخصيص التلقائي FIFO حكرٌ على `optional`؛ تحت `required` يجب أن يحمل كل بند تسلسليٍّ أرقاماً بعدد كميته، وإلّا رُفض الترحيل **قبل أي كتابة** (`serials.py` — `assert_sales_serials_declared`، مُستدعى من `sales/services/flow.py` — `post_sales_invoice`)، و`consume_sales_serials` خط الدفاع الثاني. السبب: FIFO يقول «خرجت أقدم وحدة» لا «خرجت هذه الوحدة»، فمطالبةُ كفالةٍ لاحقة تُطابَق برقمٍ لم يره أحد على العلبة. مخرج المخزون القديم بلا أرقام هو `register_existing_serials` من كرت الصنف، والرسالة تسمّيه.
- **الترقيم يصف مخزوناً قائماً ولا يخلقه**: `register_existing_serials` سقفه رصيد الصنف ولا يُنشئ حركة مخزون ولا قيداً (`serials.py:247-259`).
- **التحويل بين المستودعات بلا قيد محاسبي** — صافي أثره على إجمالي الشركة صفر (`models.py:382-384`).

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `core/tests/test_reports_stock_dimension.py` | تقرير «حركة المخزون حسب بُعد»: المحاور الخمسة، والتنقيب الذي يطابق مجموعُه رقمَ الصفّ |
| `inventory/tests/test_product_serials.py` | مصفوفة الأنماط (بدون/اختياري/إجباري) على الجانبين، دورة بيع ⇄ إلغاء ترحيل، تخصيص FIFO |
| `inventory/tests/test_serial_invoice_journey.py` | نفس الرحلة عبر HTTP بحمولة المحرِّرين (`items[].serials` / `lines[].serials`) |
| `inventory/tests/test_inventory_documents.py` | التحويل (أثر صفري، حركتان موسومتان) والجرد (تسوية + قيد الفرق) |
| `inventory/tests/test_product_profile.py` | بطاقة الصنف: المؤشرات، سجلّ الحركة (الرصيد الجاري يطابق on-hand)، الفواتير المرتبطة |
| `inventory/tests/test_item_aggregates.py` | التجميعات من `StockMovement` كمصدر وحيد (وارد تراكمي، متوسط مبيعات 90/28 يوماً) |
| `inventory/tests/test_account_overrides.py` | سلسلة الحسابات: تجاوز الصنف ← تجاوز الفئة ← الافتراضي |
| `inventory/tests/test_brand_grouping.py` · `test_group_card_performance.py` | تجميع البراندات بـ`group_key`، وثبات عدد الاستعلامات (كان N+1) |
| `inventory/tests/test_product_api.py` | توليد SKU خادمي، ترتيب/بحث/ترقيم صفحات، عزل الشركات |
