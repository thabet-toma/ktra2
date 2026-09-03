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
| `inventory/models.py` | 13 موديل: المنتج (البراند)، المنتج الأب (`ProductFamily`)، الفئة، الوحدة، المستودع، الحركة، الشرائح، الوحدة المُرقَّمة، التحويل، الجرد، وسلسلة الطلب الأسبوعية المحسوبة (`ProductDemandForecast`، #32) | 465 |
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
| `ProductMerge` (task24) | `snapshot` (JSON: لكل براند مُضموم `family_id`/`brand`/`name_ar`/`name_en` قبل الضمّ), `undone_at` | سلّة محذوفات على نمط `accounting.VoidedJournal` — `target_family→ProductFamily` (لا يُحذف أبداً)؛ `undo_product_merge` يعكسها حرفياً من `snapshot` |
| `ProductDemandForecast` (#32) | `level`, `trend` (ستّ خانات عشرية)، `weeks_observed`, `mad`, `last_week_start`, `computed_at` | `product→Product` (`OneToOneField` — صفٌّ واحد لكل منتج). يكتبه حصراً `python manage.py recompute_demand_forecast` (`core/replenishment.py` — `holt_forecast`/`weekly_demand_series`)؛ يقرأه المسار `auto` (#33) في `core/replenishment.py` (`_product_row`) دفعةً واحدة للشركة (`_forecast_map`) |
| `SupplierProduct` | `supplier_sku`, `supplier_name`, `min_order_qty` (#34، اختياري) | `supplier→partners.Partner`، `product→Product`؛ فريد `(tenant, supplier, supplier_sku)` — **لا** على `(tenant, supplier, product)`: للمورّد أن يحمل أكثر من رقم للمنتج الواحد، والممنوع عكسُه (رقمٌ واحد لمنتجين يجعل المطابقة تخميناً). محايد مالياً بالكامل. `min_order_qty` خاصّية العلاقة لا الصنف — المورّد الصيني يفرض خمسين والمحلّي يبيع بالقطعة، للصنف نفسه |
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
def normalize_product_name(name) -> str:  # (task21) تطبيعٌ إملائي عربي — تشكيل/تطويل/مسافات/ألف-همزة، بلا مطابقة صوتية
def find_by_normalized_name(queryset, name, *, fields=('name_ar', 'name_en')):  # (task21) مطابقةٌ واحدة — شاشة التسجيل عبر `check-name`
def build_normalized_name_index(queryset, *, fields=('name_ar', 'name_en')) -> dict:  # (task21) فهرسٌ يُبنى مرّةً — تجسيد عرض المورّد داخل حلقة البنود
def add_brand_to_family(*, family, brand_name, tenant=None, sku=None):  # (task21) يلحق براندًا بأبٍ قائم — أوّل براندٍ صريح يُسمّي الضمنيّ (تحديث)، والثاني فصاعداً صفٌّ جديد
def merge_products(*, tenant, target_product_id, product_ids, brands=None, user=None):  # (task24) يضمّ براندات قائمة تحت أب واحد — بلا حركة مخزون ولا قيد؛ يطبّع الاسم على اسم الهدف ويسجّل `ProductMerge` للتراجع. `brands` يشمل الهدف نفسه (دلتا ٢) — منفصلٌ عن `moved` لكن في نفس `snapshot`
def undo_product_merge(*, tenant, merge_id):  # (task24) يعكس ضمّاً بالكامل من `ProductMerge.snapshot` — الأب والاسم والبراند كما كانوا حرفياً
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
كلها تحت البادئة `/api/inventory/` (`core/urls.py`)، عدا `/api/lookup/products/` (أسفله).

| Method | المسار | الـview |
|---|---|---|
| GET/POST | `products/` | `ProductViewSet` (`views.py`) |
| GET | `/api/lookup/products/` (خارج `/api/inventory/`، مركَّبة في `core/urls.py`) | `ProductLookupViewSet` (`views.py`) — ISSUE #88: فرعٌ من `ProductViewSet` يفرض عقد `?view=lookup` دائماً (`_is_lookup`)، بلا نسخة ثانية من الفلاتر أو السيريالايزر. يخدم منتقي المستندات كلَّه (`listPickerProducts`، `frontend_v2/services/inventoryApi.ts`) — بادئةٌ مستقلة كي لا يبتلعها قناع قالب `accounting_firm`/`client_book` (`TemplateSurfacePermission` يفحص بادئة المسار لا معاملات الاستعلام)، وإلا استحال على تلك القوالب اختيار بنودها الخدمية (#78) من شاشة الفاتورة. `GET` وحده — لا كتابة على هذه النقطة. العزل والصلاحية موروثان من `ProductViewSet` كأي نقطة أخرى (تصفية `tenant` + `DEFAULT_PERMISSION_CLASSES`) |
| GET | `products/{id}/profile/` · `products/{id}/stock-ledger/` · `products/{id}/cost-breakdown/` | (405) · (411) · (433) |
| GET | `products/{id}/stock-movements/` · `products/{id}/invoices/` | (398) · (426) |
| GET | `products/{id}/serials/` · POST `products/{id}/serials/register/` | (559) · (570) |
| **POST** | `products/bulk-set-group/` | تعيين «النوع» (`variant_group`) و/أو البراند على منتجاتٍ محدَّدة دفعةً واحدة — `ProductViewSet` (`bulk_set_group`). الحقل الغائب من الجسم لا يُمَسّ، والفارغ يُمحى. يشترط `inventory.item.manage` |
| **POST** | `products/apply-replenishment/` | تثبيت الحدّين المقترَحين على منتجاتٍ محدَّدة — `ProductViewSet` (`apply_replenishment`). كتابةٌ حقيقية: تشترط `inventory.item.manage` وليست في `read_only_post_actions`، والمحدِّد في **جسم** الطلب |
| **POST** | `products/add-brand/` | (task21) يضيف براندًا إلى منتجٍ قائم (`{family_id, brand, sku?}`) — `ProductViewSet` (`add_brand`)، عبر `services.add_brand_to_family`. الكتابة على جانب البراند عمداً — لا على `product-families/` القرائي |
| **POST** | `products/merge/` | (task24) ضمٌّ جماعي: `{target_product_id, product_ids: [...], brands?: {id: اسم}}` — `ProductViewSet` (`merge`)، عبر `services.merge_products`. المحدِّد في **جسم** الطلب (≥1500 معرّف)؛ يشترط `inventory.item.manage`؛ يطبّع اسم كل براندٍ مُضموم على اسم الهدف ويرفض اختلاف الوحدة أو التتبّع التسلسلي فقط — بلا حركة مخزون ولا قيد. `brands` يقبل مفتاح الهدف نفسه (دلتا ٢) — لا الإخوة المنقولين وحدهم |
| **POST** | `products/merge-undo/` | (task24) `{merge_id}` — `ProductViewSet` (`merge_undo`)، عبر `services.undo_product_merge`. يعيد كل براندٍ لأبيه واسمه وبراندِه كما كانوا حرفياً؛ سجلٌّ متراجَعٌ عنه لا يُقبل ثانيةً |
| GET | `product-families/check-name/?name=` | (task21) اقتراح «هذا موجود» — مطابقةٌ مطبَّعة لا حرفية (`services.find_by_normalized_name`)، اقتراحٌ لا منع. مجموعةٌ صريحة `brands__isnull=False` لا `get_queryset()` (تلك `select_related`، وهذه تستدعي `find_by_normalized_name` التي تستعمل `only` — جانغو يرفض الجمع)؛ الحجب نفسه: أبٌ يتيمٌ من ضمٍّ (task24) لا يُقترَح أبداً |
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
| GET | `product-families/` | `ProductFamilyViewSet` (task20) — «المنتج» الأب، **قراءةٌ فقط عمداً**: يُنشأ حصراً مع براندِه الضمنيّ عبر `products/` (`create_product_with_family`) فلا يوجد «منتج بلا براندات»، والكتابة عليه مباشرةً تفتح اتجاه كتابةٍ ثانياً يترك القرّاء الحاليين (وكلّهم يقرأ من صفّ البراند) على قيمةٍ قديمة. `get_queryset` (task24) يستثني الأب اليتيم (فقد كل برانداته بالضمّ، `brands__isnull=False`) — باقٍ في القاعدة للتراجع، محجوبٌ عن كل قراءة |

### الكرت المجمّع: المحدِّد في الجسم لا في العنوان
النقاط الثلاث تقبل `POST` بجسم JSON فيه أحد محدِّدَين:

| المحدِّد | المعنى |
|---|---|
| `{"category": 3}` | التصنيف **وكل أحفاده** — الخادم يشتقّ المنتجات (`category_descendant_product_ids`) |
| `{"family": 7}` | (#23) كل براندات منتجٍ (أب) بعينه — يشتقّها الخادم مباشرةً (`ProductViewSet._group_ids`)؛ كرت المنتج المفرد يفتح كرت إخوته به |
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
| المقترَح يصل شاشة الأصناف فعلاً — لا موضعاً واحداً (تقرير التجديد) يمرّره | `core/replenishment.py` (`suggested_min_maps`) عبر `ProductViewSet._suggested_min_maps` |
| الخدمة «متوفّرة» دائماً — بلا مخزونٍ يُقاس | `stock_status.py` (`stock_status_of`) |
| المعادلات (الصرف اليومي · مخزون الأمان · الحدّان) | `core/replenishment.py` (`suggest_levels`) |
| مهلة التوريد: وسيط (تاريخ أول وارد لفاتورة الطلبية − تاريخ الطلبية)، للمنتج ثم للمورّد ثم للشركة ثم إعداد | `core/replenishment.py` (`_lead_time_samples`, `_lead_for`) |
| قرار الطلب من المنتج **ونوعه** معاً: عاجل/مؤجَّل/راكد | `core/replenishment.py` (`_urgency_of`) |
| الكتابة الوحيدة — بفعلٍ صريح من المستخدم | `core/replenishment.py` (`apply_suggested_levels`) |

بارامترات الشركة على `logistics.PurchaseSettings` — التجديد قرارٌ شرائي، فإعداداته
حيث تعيش إعدادات الشراء: الثلاثة الأصلية (نافذة التحليل · المهلة الافتراضية · مدة
المراجعة) بالإضافة إلى خمسة مقابض هولت (#34 — `forecast_alpha/beta/history_weeks/
trend_cap_ratio/safety_factor`)، تُقرأ جميعاً عبر مُحمِّلٍ واحد
(`ReplenishmentParams`/`replenishment_params`) — لا قارئ إعداداتٍ ثانٍ.

**#32 — سلسلةٌ أسبوعية موازية.** المتوسط أعلاه (ADU) يدفن صنفاً باع أربعاً مرّتين
خلال شهرين تحت «أقلّ من قطعة بالأسبوع». `core/replenishment.py` (`holt_forecast`,
`weekly_demand_series`) يشتقّ رقمين موازيين — المستوى والاتجاه بتنعيمٍ أسّي مزدوج
(هولت) على نفس صافي `OUT − RETURN_IN`، وأسبوع الصفر جزءٌ من السلسلة لا فجوة —
ويكتبهما `python manage.py recompute_demand_forecast` أسبوعياً في
`inventory.ProductDemandForecast` (لا Celery؛ مجدول النظام).

**#33 — مفتاحٌ لكل صنف يقرأ الرقمين.** `Product.reorder_mode` (`manual` الافتراضي
على الكتالوج كلّه، `auto` باختيار المستخدم من كرت الصنف) يحكم فرعاً داخل نفس
`_product_row` — لا بانٍ ثانٍ. `manual` هو معادلة `suggest_levels` أعلاه حرفياً؛
`auto` يحوّل المستوى/الاتجاه المخزَّنين إلى حدٍّ وكميةٍ: أسابيع التغطية = مهلة
التوريد + فترة المراجعة، والاحتياج = `المستوى×W + الاتجاه المسقوف×W(W+1)/2`
(الاتجاه مسقوفٌ صعوداً بـ`المستوى/3` وبلا سقفٍ نازلاً)، ومخزون الأمان من خطأ
التوقّع (`1.28×1.25×MAD×√W`، وإلا قاعدة الذروة القديمة حين يغيب `MAD`)، وطرحُ
«قيد الطلب» قبل العرض. صفٌّ تلقائيٌّ لا يطلب شيئاً (`order_qty≤0`) يسقط من
العرض الافتراضي لـ`stock-replenishment` — لا من المحرّك — وفلتر «راكد» يبقى
يُظهره عمداً؛ المسار اليدوي لا يتأثر بهذا الإخفاء إطلاقاً.

**#34 — المقابض السبعة، حدّ المورّد الأدنى، وتحذير الأرقام القديمة.** الثوابت
التي كانت مطبوعةً في `core/replenishment.py` (`HOLT_ALPHA`, `HOLT_BETA`,
`FORECAST_HISTORY_WEEKS`, سقف الاتجاه، عامل الأمان) صارت الخمسة `forecast_*` في
`logistics.PurchaseSettings`، يقرأها `ReplenishmentParams` في مكانٍ واحد
وتصل إلى `holt_forecast` (α/β) و`weekly_demand_series` (عمق السلسلة) و`_product_row`
(سقف الاتجاه وعامل الأمان) — وأمر `recompute_demand_forecast` يحمّلها **لكل شركةٍ
يعالجها** لا افتراضاً ثابتاً. `SupplierProduct.min_order_qty` (اختياري) يرفع كمية
مقترحة دون حدّ المورّد الأدنى إليه ويُؤشِّر السطر بذلك (`_moq_map` — استعلامٌ واحد
للشركة)؛ فلتر المورّد في التقرير يختار حدّ ذاك المورّد، وغيابه يختار الأقلّ تقييداً
بين موردي الصنف. وتقرير `stock-replenishment` يحمل تنبيهاً (`ReportSpec.notice`)
حين يتجاوز عمر آخر تنبّؤٍ محفوظ عشرة أيام — قراءةٌ لـ`computed_at` بلا إعادة حساب.

**والمحرّك يسكن في `core/` لا هنا**: حسابه يحتاج `sales.services` (المحجوز) و
`logistics.models` (مهلة التوريد)، و`.importlinter` يمنع `inventory` من استيرادهما
(عقد «الاتجاه المعكوس»). ما بقي هنا هو `stock_status.py` وحده — قاعدةُ **حالة**
المخزون لا تحتاج غير `inventory`.

**«النوع» (`variant_group`) كان بلا مدخل**: الحقل والنقطة (`products/groups/`)
موجودان منذ task31، ولا شاشةَ تكتبه — فبقي فارغاً على **كل** منتجٍ في كل شركة،
وبفراغه يسقط `product_group_key` على مقاس الإطار المُستخرَج من الاسم ثم البراند
ثم الاسم. صار له مدخلان: حقلٌ في كرت المنتج (`ItemForm.tsx`)، وتعيينٌ جماعي
للمحدَّد من «أرصدة المخزون» (`StockLevelsPage.tsx` ← `products/bulk-set-group/`).

**#25: مفتاح الأب (`ProductFamily`) درجةٌ أولى فوق هذا السلّم كلّه** —
`product_group_key` يقرأ `product.family` أولاً (اسم الأب)، وإلا فالسلّم
القديم كاملاً بلا حذف درجة. بلا هذه الدرجة، برندان أُضيفا تحت **نفس** الأب
(`add_brand_to_family`، #21) يحملان مفتاحين مختلفين (اسميهما كبراند) فلا
يتجمّعان — وهو ما كان يُفرغ محور «البدائل» في محرّك التجديد من أي معنى لكل
منتجٍ متعدّد البراندات. وحالة المخزون (`stock_status_of`) تقبل الآن
`family_totals` اختيارية (من `family_available_map` — استعلامٌ واحدٌ للشركة
كلّها لا واحدٌ لكل صفّ) فتُحسب من **مجموع** أرصدة الإخوة مقابل حدّ **الأب** —
لا رصيد البراند وحده مقابل حدّه هو، وإلا ظهر كل براندٍ «منخفضاً» كذباً في
منتجٍ وفير. مُفعَّلةٌ في `ProductSerializer` (القائمة والبطاقة) وفي
`core/replenishment.py`.

**الضمّ يبدأ من الصفر: هدفٌ بلا أبٍ يكتسب أباً.** كل منتجٍ سُجّل قبل #20 يحمل
`family_id` فارغاً — وهي **كل** بيانات الإنتاج القائمة. وكانت `merge_products`
تشترط أباً للهدف سلفاً فترفض كل ضمٍّ على الكتالوج القديم («بلا منتجٍ أبٍ فوقه»)،
أي أن أداة التنظيف عجزت عن لمس ما بُنيت لتنظيفه. `inventory/services.py`
(`adopt_family_for_product`) تمنح المنتج القائم أباً مرآةً لصفّه — لا مسار آخر
في النظام يفعل ذلك (`create_product_with_family` تُنشئ الاثنين معاً لمنتجٍ
**جديد**). ولقطة الضمّ تسجّل `family_id` السابق (`None`) فيُرجع التراجعُ الهدفَ
إلى «بلا أب» حرفياً — وإلا بقي تحت أبٍ لم يكن له.

**«أضف براند» تسكن قسم «براندات هذا المنتج» لا طيّ «متقدم».** كانت في قائمة
حقول `ItemForm.tsx` خلف مِفصل «▸ متقدم» المغلق افتراضياً — فيبحث عنها المستخدم
ثم ييأس فيُنشئ صنفاً جديداً، وهو الخلل الذي جاء النموذج كلّه ليمنعه. صارت داخل
القسم الذي يعرض البراندات نفسها في «نظرة عامة» (`ProductInsightTabs.tsx` —
`FamilyBrandsSection`). ويُمرَّر الحقل **عنصراً جاهزاً** (`addBrandSlot`) عبر
`useProductInsights` و`ProductOverview` لا دالّةً: `ProductInsightTabs` لا يجوز
أن تستورد من `ItemForm` (تلك تستورد منها، فيصير الاستيراد دائرياً). والقسم كان
يصمت لمنتجٍ ببراندٍ واحد فصار يظهر متى وُجد المقبس — وهو بالضبط المنتج الذي
يريد صاحبه أن يضيف له ثانياً. و`ProductCardModal` لا تمرّره فتبقى كرتاً للقراءة.

**الخادم يُكمل عائلات الصفحة بعد التقسيم — شرط استقامة صفّ المنتج (#30).**
التجميع يقع عند الرسم (#23) على الصفوف الواصلة وحدها، والشاشة الجدولية تُرقَّم
عند 50. فمنتجٌ تتوزّع براندَاته على صفحتين كان يُرسَم صفَّ منتجٍ **بمجموعٍ
جزئي معروضٍ على أنه مجموع المنتج** — وليست حالة حدّ: الترتيب الافتراضي `-id`
ومعرّفات الإخوة متباعدة. الإصلاح لا ينقل التجميع بل يضمن اكتمال مدخلاته:
`inventory/views.py` (`_complete_families`) يجلب كل إخوة عائلات الصفحة في
**استعلامٍ واحد ثابت** لا واحدٍ لكل صفّ. **اختياري** (`complete_families=1`)
فشاشة الأصناف وحدها ترسله ولا يُمَسّ عقد `?view=lookup`، ولا يُخزَّن رقم —
جلبُ صفوفٍ لا حسابُ مجموع. وترتيب `-id` **يبقى**: الترتيب على الاسم كان حيلةً
تجعل الاكتمال مصادفةً، وقد صار مضموناً. والفلترة تتبع تفريق #26 حرفياً:
مرشِّحٌ يختار **أيّ البراندات** لا إكمالَ معه في الخادم ولا تجميعَ في الواجهة
(`GroupedItemsTable.tsx` — `brandFilterActive`) — صفوف براندٍ صريحة، وإلا
لأظهر إخوةً لا يطابقون في صفٍّ يدّعي أنه المنتج.

و**`stock_status` لم يعد منها بعد #28**: صار حكماً على **الأب** (مجموع
البراندات مقابل حدّ الأب) لا على البراند، فيُعيد الفلتر كل براندات المنتج
المطابق لا بعضها — فصفّ المنتج مكتملٌ ولا يدّعي، والإكمال يجمع ما فرّقه
التقسيم إلى صفحات. بقي **البحث** وحده مُسقِطاً للتجميع، وهو أيضاً مسار الضمّ:
تُكتب المقاس فتظهر النسخ المكرّرة صفّاً صفّاً لتُؤشَّر وتُضمّ، ومربّع التحديد
لا يعيش إلا على صفّ البراند.

وتصدير PDF من الشاشة نفسها (`ItemsManagement.tsx`) يطبع **منتجات** لا براندات،
من نفس دالّة التجميع (`utils/familyGrouping.ts`) لا نسخةٍ ثانية منها: كان يطبع
صفوف البراندات خاماً فيظهر المقاس الواحد مرّتين بكميةِ كلِّ براندٍ على حدة
بينما شارته حكمٌ على المنتج كلّه — رقمان لسؤالٍ واحد في الصفّ ذاته.

**صفٌّ واحد بلغةٍ واحدة: المنتج ببراندٍ واحد كإخوته.** كان `GroupedItemsTable.tsx`
(`renderGroupNodes`) يقطع مبكّراً عند `members.length <= 1` فيسقط المنتج ذا
البراند الواحد إلى **صفّ براندٍ عارٍ**، فيقرأ المستخدم في الجدول الواحد لغتين
(«205/70/15» بجانب «185/55/16 (دانتير تريستار)»). والحالة ليست نادرة — أكثر من
نصف كتالوجٍ مُهاجَر. وهي عابرة أيضاً: براندٌ ثانٍ غداً يقلب شكل الصفّ بلا سبب.
الآن كل منتجٍ **له أبٌ** صفُّ منتجٍ ومعه «إظهار البراندات (ن)»، و`ن = 1` عددٌ
مشروع. منتجٌ **بلا أبٍ** (قديمٌ لم يُضَمّ بعد) يبقى صفّاً مفرداً — ليس منتجاً
بالنموذج الجديد أصلاً. ويترتّب على ذلك قاعدةٌ واحدة بلا استثناء: **مربّع تحديد
الضمّ والتحرير المباشر للاسم يعيشان على صفّ البراند دائماً** ولا يحملهما صفّ
المنتج مهما كان عدد برانداته — معرّفه مرجعيٌّ لا يمثّل الكلّ، والاسم مشترك.

**#26: تقارير المنتجات تتجمّع على المنتج افتراضاً، لا على البراند.** `تقييم
المخزون`/`تحت حدّ الطلب`/`المبيعات حسب المنتج`/`المشتريات حسب المنتج`
(`core/reports/inventory.py`, `sales.py`, `purchases.py`) تصدر صفّاً واحداً
لكل عائلة (مجموع كمياتها، ومتوسط تكلفةٍ **مرجَّح بالكمية** — Σqty×cost ÷ Σqty،
لا متوسطاً بسيطاً)، وتنقّب إلى برانداتها عبر محرّك `ReportSpec.drill` القائم —
لا محرّك ثانٍ. `core/replenishment.py` (`_product_row`) يحمل الآن `family_id`/
`family_name`/`family_available` في كل صفّ لهذا الغرض وحده. واسم الأب المعروض
يُشتقّ من `inventory/services.py` (`family_display_name`) وحدها — كُتبت القاعدة
أربع مرات بثلاثة مآلاتٍ مختلفة عند الفراغ قبل أن تُوحَّد، وهو النمط الذي كلّف
#18 ثلاث صيغٍ لاسم البند؛ ليست هي `product_group_key` (تلك تُنتج **مفتاح**
تجميعٍ لا لافتةً تُقرأ). محور «الأنواع
المتبادلة» (`group_key`/`level=group`) لم يُمسّ. `stock-movements`/
`reserved-stock`/`stock-by-dimension`/`sales-by-brand`/`stock-replenishment`
تبقى عمداً على البراند — حركةٌ أو حجزٌ وقعا على براندٍ بعينه، و`stock-replenishment`
مجمَّعةٌ أصلاً عبر `group_key` (الأب درجتها الأولى منذ #25). منتجٌ بلا أبٍ يبقى
صفّاً بمفرده كسابق عهده تماماً.

**قاعدة صارمة تحكم صفّ العائلة: أرقامه مجموع كل أبنائها، أو لا يظهر أصلاً —
لا صفّ عائلةٍ منقوص.** `family_available` (لا مجموع الإخوة الظاهرين/المفلترين)
هو **نفس** المتاح الذي قاسته `stock_status_of` فعلاً عبر `family_totals`؛
فبلا فلترة الحالة قبل التجميع في `low-stock` (تجميعٌ ثم تصفية، لا العكس)
يظهر صفّ العائلة إن تأهّل **أيّ** ابنٍ، وينقّب على **كل** الإخوة — حتى
المتوفّرين — كي يطابق مجموع تنقيبه رقم الصفّ حرفياً. وفلتر `product`
(`?product=`) يختار **براندًا بعينه** لا حقيقةً عن العائلة، فتُلغى العائلة
تماماً وقتها ويُعاد صفّ براندٍ حقيقي (`sku`/`brand` كما هما) على التقارير
الأربعة كلّها — لا صفّ عائلةٍ فارغ الهويّة يحمل رقم برندٍ واحد.

و**منتقي المستندات (`view=lookup`) يبقى على حالة البراند وحده عمداً لا سهواً**:
البند يبيع براندًا بعينه، فبراندٌ رصيده صفرٌ داخل منتجٍ وفير «نفذ» حقيقةً لمن
يريد بيعه — «هل عندي من هذا المنتج شيء» سؤال شاشة الأصناف لا سؤال سطر الفاتورة.
اختلافُ دلالةٍ لا حقلٌ محذوف: العقد يعرض `stock_status` كما كان.

**#23: الشجرة في `GroupedItemsTable.tsx` تنتهي عند المنتج لا البراند.** صفوف
`family_id` المشتركة تتجمّع في صفٍّ واحدٍ يعرض **مجموع** أرصدة برانداته (مشتقٌّ
عند الرسم — `utils/familyGrouping.ts`، لا رقم مخزَّن)، وعنصر كشفٍ صغير داخل
الصفّ يُنزل كل براندٍ صفّاً مستقلاً تحته حين يُطلَب. منتجٌ بلا أبٍ (بياناتٌ
قديمة) يبقى صفّه الفردي كما كان. `product_has_explicit_group` (`has_group`)
كانت تقرأ `variant_group` وحده فتتجاهل الأب كلياً؛ صارت تقبل `family_sibling_counts`
اختيارية (من `services.family_brand_counts` — استعلامٌ واحدٌ للشركة كلّها،
`ProductViewSet._family_brand_counts`) فتُبلِّغ `True` أيضاً لمنتجٍ بأكثر من
براند. `ProductSerializer` يكسب `family_id`/`family_name` (كانا حصراً في
`ProductLookupSerializer`) لتقدر الشاشة على التجميع. وكرت المنتج المفرد
(`ProductInsightTabs.tsx` — `ProductOverview`) يعرض قسم «براندات هذا المنتج»
حين لأبيه أكثر من براند، عبر محدِّد `family` الجديد على نقاط الكرت المجمّع —
لا منطق تجميعٍ ثانٍ.

**#28: فلتر `?stock_status=` والداشبورد صارا يوافقان الشارة.** `filter_by_stock_status`
يقبل الآن `family_statuses` اختيارية (من `stock_status.family_status_map` —
استعلامان اثنان للشركة كلّها: `family_available_map` ثم حدود `ProductFamily`)؛
منتجٌ له أبٌ يُفلتَر بحالة **أبيه** فيتّفق تماماً مع الشارة على نفس الصفّ، لا
رصيد براندٍ وحده مقابل حدّه هو. غائبةً أو فارغةً (كما في `?view=lookup` — القرار
لم يتغيّر، انظر أعلاه) السلوك حرفياً كما قبل #28. «متوفّر» يُبنى من متمّم
الحالات الشاذّة لا تعداد كل عائلةٍ متوفّرة، فقائمة المعرّفات في SQL محدودةٌ
بعدد العائلات الشاذّة لا بحجم الكتالوج. `ProductViewSet._family_statuses`
(`inventory/views.py`) و`core/dashboard_api.py` يستهلكانها معاً — لا نسخة
ثانية من سلّم القرار؛ `stock_status.py` (`_status_for`) هو ما يستدعيه
`stock_status_of` و`family_status_map` كلاهما.

**#35: الرقم المعروض على صفّ المنتج صار نفس الرقم الذي حَكَم على شارته.**
`buildFamilyRow` (`utils/familyGrouping.ts`) كان يأخذ `min_stock_level`/
`max_stock_level` من البراند المرجعي (أصغر معرّف) خاماً، بينما الشارة
(`stock_status`) حُوكِمت بحدّ **الأب** (#25) — يتطابقان في المسار العادي
(كل كاتبٍ يصعد إلى الأب عبر `sync_family_from_product`) ويتباعدان بعد ضمٍّ
(#24) لا يمسّ حدود إخوته أصلاً. `stock_status.py` (`family_status_and_thresholds`)
تبني الحالة والحدّين معاً من نفس استعلام `ProductFamily` (`family_status_map`
غلافٌ رقيقٌ فوقها الآن، بنفس عدد الاستعلامات)؛ `ProductViewSet._family_thresholds`
تشارك الاستدعاء المخبوء مع `_family_statuses` (`_family_status_and_thresholds`،
استدعاءٌ واحدٌ لكلٍّ منهما، فلا يتضاعف الاستعلام)، وتُبطِله `update()` حين يُغيّر
الحفظ حقلاً أبوياً فعلاً — وإلا عرض ردّ الـPATCH حدّاً بائتاً من قبل المزامنة.
`ProductSerializer` يكسب `effective_min_stock_level`/`effective_max_stock_level`
(قراءةٌ فقط، بجانب `min_stock_level`/`max_stock_level` الكاتبين كما هما — لا
تبديل معنى حقلٍ يبعثه نموذج التحرير)، ومنتجٌ بلا أبٍ يعرض حدّه هو كما اليوم.
`view=lookup` خارج النطاق عمداً (لا يعرض الحدود أصلاً، #25/#28).

**#44: الحدّ المحسوب كان محبوساً في تقرير التجديد — الشاشة تحكم بحدٍّ صفريّ
بصمت.** `effective_min` تقبل `suggested_min` منذ اليوم الأول، لكن الموضع
الوحيد الذي مرّره كان `core/replenishment.py` (تقرير التجديد) — فأي منتجٍ بلا
حدٍّ يدوي (معظم الكتالوج) كان حدّه على شاشة الأصناف صفراً، و`_status_for` لا
تُرجع `low_stock` إلا حين `minimum > 0`، أي أن «منخفض» لا تظهر له إطلاقاً.
الإصلاح لا يمسّ `effective_min`/`effective_max`/`_status_for` — الناقص وصولُ
الرقم إليها لا صحّة القاعدة. `core/replenishment.py` (`suggested_min_maps`)
تعيد `(خريطة منتج، خريطة عائلة)` للشركة كلّها من **نفس** الخرائط المجمَّعة
التي يبنيها التقرير (`_demand_profiles`, `_lead_time_samples`, `_forecast_map`)
— لا مصدر حقيقةٍ ثانٍ، ولا نسخة على `ProductDemandForecast` (نسخةٌ مجمَّدة
أسبوعياً تنحرف عن حسابٍ حيٍّ عند أوّل تغيير في مهلة مورّد). خريطة العائلة
مجموع الحدود المحسوبة لإخوة كل أبٍ — نفس نمط الجمع الذي تجمعه `_group_rows`
(بمفتاح `family_id` بدل `group_key`)، لا قاعدةٌ ثانية. `ProductViewSet`
يخبّئها لكل طلب (`_suggested_min_maps` بنفس نمط `_reserved_map`/
`_family_available_map`) ويمرّرها إلى `stock_status_of` (الشارة) و
`filter_by_stock_status` (الفلتر، عبر `annotate_available`/
`_effective_min_expression` — حقنٌ بـ`Case` على معرّفات المنتجات بلا أبٍ، لا
عمود مخزَّن ولا استعلامٌ لكل صفّ). قيمةٌ مركّبة جديدة في الفلتر والتصدير
(`stock_status.FILTER_UNDER_MIN`، «تحت الحدّ الأدنى») تطابق `out_of_stock`
و`low_stock` معاً؛ حالة المخزون فلترٌ على مستوى **الأب** منذ #28 فلا تُسقط
التجميع (خلافاً لمرشِّحات اختيار البراند، #26/#30). `?view=lookup` بلا مساس:
لا يمرَّر إليه `suggested_min_map` إطلاقاً، فيبقى على `min_stock_level` الخام
حرفياً كما قبل #44.

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
- **إلحاق براندٍ بأبٍ قائم مختلفٌ عن إنشاء منتجٍ جديد** (task21، #21):
  `add_brand_to_family` — لا `create_product_with_family` — هي الأداة، لأن
  الأخيرة تصنع أباً **جديداً**. أوّل براندٍ صريح تحت أبٍ لا يزال بلا اسمٍ على
  برانده الضمني (`Product.brand` فارغ) **يُسمّيه بتحديث صفّه القائم**، فيرث
  رصيده وتكلفته وحركاته وفواتيره كاملةً — لا صفّاً جديداً فارغاً بجانب رصيدٍ
  قديم. الثاني فصاعداً يُنشئ صفّاً جديداً تحت **نفس** الأب برصيدٍ وتكلفةٍ
  مستقلَّين (صفر). بلا حركة مخزون ولا قيد محاسبي في الحالتين.
- **الضمّ الجماعي يعيد ربط `family` فقط — بلا حركة مخزون ولا قيد محاسبي، ولا نقل
  رصيدٍ بين براندات** (task24، #13/#24): `merge_products` يُمنع فقط عند اختلاف
  الوحدة أو `is_serialized` (مقارنةً عبر `resolve_family_field`) — هذان فقط،
  بلا موانع مخترَعة؛ الحقول الأخرى (التصنيف، السعر، التكلفة، SKU، الباركود)
  تبقى كما هي. **الاسم يُطبَّع لا يُترَك مختلفاً**: القرار المسجَّل على #24
  يعكس أن `_push_family_fields_to_siblings` (#23) كانت ستُطبّعه صامتاً في أول
  تعديلٍ لاحق أصلاً — فالتطبيع الفوري تحت نظر المستخدم أفضل من مفاجأةٍ لاحقة،
  والسبب الأصلي لمنع لمس الاسم في #13 (بند فاتورة البيع بلا لقطة اسم) ارتفع
  فعلاً بعد `SalesInvoiceLine.name_snapshot` (#18). `brand` يتغيّر فقط إن
  مرّره المستخدم صراحةً — بلا اقتراحٍ آلي إطلاقاً. كل ضمٍّ يسجَّل في
  `ProductMerge.snapshot` (الحالة قبل الضمّ لكل براند)، و`undo_product_merge`
  يعيدها حرفياً — الأب القديم لا يُحذف عند الضمّ فيبقى موجوداً للتراجع إليه،
  لكنه **يُحجب عن كل قراءة** (`ProductFamilyViewSet.get_queryset`/`check-name`،
  `brands__isnull=False`) — «منتجٌ بلا براندات» يبقى بلا مكانٍ في النموذج (#20)
  حتى وهو صفٌّ حيّ.
  **دلتا ٢ — الهدف براندٌ كباقي البراندات**: بعد أن يتوحّد الاسم، البراند وحده
  يميّز الصفوف في المنتقي («اسم المنتج (البراند)»، `product_display_name`) —
  فترك الهدف بلا وسيلةٍ لتسميته من داخل الضمّ كان يُنتج صفّاً بلا تمييز. لذلك
  `brands[target_product_id]` يُطبَّق على الهدف نفسه أيضاً (منفصلاً عن حلقة
  الإخوة `others` — الهدف لا يدخل `moved`/`merged_product_ids` لأن أباه لا
  يتغيّر، لكن لقطته قبل التعديل تدخل نفس `snapshot` العام فيعيدها `undo_product_merge`
  بلا أي كودٍ إضافي). **الواجهة**: `ItemsManagement.tsx` (زر «ضمّ منتجات») يفتح
  وضع تحديدٍ يُظهر عمود اختيارٍ في `GroupedItemsTable.tsx` (`selection` prop) —
  صفوف المنتج المفرد فقط، لا صفوف التصنيف ولا ملخّص مجموعةٍ مطويّ (معرّفه
  مرجعيٌّ لا يمثّل كل أعضائها). `MergeProductsModal.tsx` يعرض معاينةً كاملة قبل
  أي طلبٍ خادمي — من سينتقل تحت أيّ هدفٍ **يختاره المستخدم صراحةً بلا افتراضٍ
  مسبق**، وأن أسماءهم ستُطبَّع، ولكل مرفوضٍ سببه — عبر دالّةٍ خالصة
  (`utils/productMerge.ts` — `buildMergePreview`، مُختبَرة بـ`node --test`) لا
  منطقٍ داخل المكوّن. كل صفٍّ يحمل حقل براندٍ (الهدف كأي عضوٍ آخر) مُعبَّأً
  بالبراند الحالي وفارغاً غير ذلك — بلا أي تخمين؛ و`findBrandCollisions`
  (نفس الملف) تحذّر — لا تمنع — من صفوفٍ ستنتهي ببراندٍ واحدٍ لا يميّزها
  (فراغين معاً أيضاً) قبل أي طلبٍ للخادم. بعد النجاح بانرٌ يحمل زرّ «تراجع»
  يبقى ظاهراً حتى يُغلَق المستخدم أو يتراجع — لا توستاً عابراً كالباقي.
- **عقد المنتقي (`ProductLookupSerializer`، `view=lookup`) يحمل `family_id`/`family_name`** (#22):
  حقلان فقط — العقد الضيّق مقصود ومقيسٌ (609ك/331مِلّي على 1490 منتجاً). المنتج
  (الأب) نفسه **لا يظهر أبداً** كصفٍّ في هذا العقد بنيوياً — هو مبنيٌّ فوق `Product`
  (البراند) لا `ProductFamily`. «اسم المنتج (البراند)» في المنتقي والطباعة يأتي
  من `display_name` (`product_display_name`) الموجودة أصلاً — لم تُبنَ لهذه
  التذكرة. (#41 عمّم استعمالها لاحقاً خارج `inventory`: بند الإرسالية وفاتورة
  الشراء في `logistics`، بنود المبيعات والمرتجع والتسليم في `sales`، والكفالة
  وأمر الصيانة وتقاريرهما في `after_sales` — كلها كانت تعرض `str(product)`،
  وهي البراند وحده الذي يميّز إخوة الأب الواحد.) `family_name` يُقرأ عبر
  `select_related('family')` على queryset
  `ProductViewSet` — بلا هذا الجلب صار استعلاماً لكل صفّ.
- **قاعدة مطابقة اسمٍ واحدة لاقتراح «هذا موجود»** (task21): `find_by_normalized_name`
  (فوق `normalize_product_name`) — تطبيعٌ إملائي عربي (تشكيل/تطويل/مسافات/
  ألف-همزة/ألف مقصورة/تاء مربوطة) **بلا مطابقة صوتية** (سامسونج ≠ سامسونغ عمداً).
  موضعان يستدعيانها لا نسخةٌ ثانية: `product-families/check-name/` و
  `logistics.services.materialize_quotation_draft_parties`.
- **مطابقةٌ واحدة (شاشة التسجيل) تُمسَح بـ`find_by_normalized_name`، ومطابقاتٌ
  كثيرة داخل حلقة (تجسيد عرض المورّد) تُبنى فهرساً مرّةً بـ
  `build_normalized_name_index` قبل الحلقة لا داخلها** — التطبيع العربي
  بايثونيٌّ حتماً (لا SQL يوحّد الألف/الهمزة والتشكيل)، فمسحٌ لكل بند كان
  يحمّل أصناف الشركة كاملةً لكل سطر (74,500 صفّاً على عرضٍ بخمسين بنداً وشركةٍ
  بـ1490 صنفاً). يحرسه `logistics/tests/test_quotation_draft_parties.py`
  (`QuotationMaterializationScanTest`) بعدّ استعلامات المسح، لا بقياس زمن.
- **`product_profile` يكشف `family_id`** (task21): كرت المنتج في الواجهة
  (`ItemForm.tsx`) يحتاج أب المنتج المفتوح ليعرض «أضف براند إلى هذا المنتج» —
  `ProductSerializer` لا يحمل `family` أصلاً، فأُضيف الحقل لناتج `product_profile`
  بدل توسيع عقد المنتج الكامل (أثرٌ أضيق).

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `core/tests/test_reports_stock_dimension.py` | تقرير «حركة المخزون حسب بُعد»: المحاور الخمسة، والتنقيب الذي يطابق مجموعُه رقمَ الصفّ |
| `core/tests/test_reports_family_rollup.py` (#26 + دلتا) | صفٌّ واحد للمنتج في أربعة تقارير، متوسط تكلفةٍ مرجَّح يفشل مع البسيط، مجموع التنقيب = رقم الصفّ، منتجٌ بلا أبٍ بلا تغيير، ثبات عدد الاستعلامات، عزل الشركات؛ ودلتا: عائلةٌ بحدٍّ منحرفٍ بين الإخوة (متاح العائلة كاملاً لا نصيب البرند المُنذِر، والتنقيب يسرد المتوفّر أيضاً)، وفلتر `product` يعيد صفّ براندٍ حقيقياً لا عائلةً منقوصة |
| `inventory/tests/test_product_serials.py` | مصفوفة الأنماط (بدون/اختياري/إجباري) على الجانبين، دورة بيع ⇄ إلغاء ترحيل، تخصيص FIFO |
| `inventory/tests/test_serial_invoice_journey.py` | نفس الرحلة عبر HTTP بحمولة المحرِّرين (`items[].serials` / `lines[].serials`) |
| `inventory/tests/test_inventory_documents.py` | التحويل (أثر صفري، حركتان موسومتان) والجرد (تسوية + قيد الفرق) |
| `inventory/tests/test_product_profile.py` | بطاقة المنتج: المؤشرات، سجلّ الحركة (الرصيد الجاري يطابق on-hand)، الفواتير المرتبطة |
| `inventory/tests/test_item_aggregates.py` | التجميعات من `StockMovement` كمصدر وحيد (وارد تراكمي، متوسط مبيعات 90/28 يوماً) |
| `inventory/tests/test_account_overrides.py` | سلسلة الحسابات: تجاوز المنتج ← تجاوز الفئة ← الافتراضي |
| `inventory/tests/test_brand_grouping.py` · `test_group_card_performance.py` | تجميع البراندات بـ`group_key` (الأب درجةٌ أولى، #25)، حالة المخزون من مجموع الإخوة مقابل حدّ الأب، محور «البدائل»، وثبات عدد الاستعلامات (كان N+1) |
| `inventory/tests/test_product_api.py` | توليد SKU خادمي، ترتيب/بحث/ترقيم صفحات، عزل الشركات |
| `inventory/tests/test_product_lookup_endpoint.py` | ISSUE #88: `/api/inventory/products/` يبقى مقنَّعاً لقالب `accounting_firm`، `/api/lookup/products/` يتخطّى القناع ويحمل خدمات #78، تطابق حرفي مع عقد `?view=lookup` القديم لـ`general`، عزل الشركات، رفض الكتابة، ورحلةٌ كاملة عبر HTTP: اختيار «مسك دفاتر شهري» من المنتقي ← إنشاء الفاتورة ← ترحيلها على `4103` |
| `inventory/tests/test_product_family.py` | task20: الإنشاء الذرّي (الأب + البراند الضمني) من مساري التسجيل معاً، عزل الشركات على `ProductFamily`، وقاعدة التعايش (مع/بلا أب) |
| `inventory/tests/test_product_offer_and_brand.py` | task21: اقتراح «هذا موجود» مطبَّعاً لا حرفياً (وعدم منعه)، أوّل براندٍ يُسمّي الضمنيّ والثاني يُنشئ صفّاً تحت نفس الأب، بلا حركة مخزون ولا قيد محاسبي، وعزل الشركات على الاقتراح — والمطابقة نفسها من موضع تجسيد عرض المورّد |
| `inventory/tests/test_product_merge.py` | task24: ضمٌّ جماعي تحت أبٍ واحد بمحدِّدٍ في الجسم (≥1500 معرّف)، بلا حركة مخزون ولا قيد (عدّاً قبل/بعد)، منعٌ عند اختلاف الوحدة أو التتبّع التسلسلي فقط، تراجعٌ كامل بلا أثر (ولا يُقبل مرّتين)، وعزل الشركات على الهدف والمصدر معاً؛ `OrphanFamilyIsHiddenAfterMergeTest` — الأب اليتيم يبقى في القاعدة (تراجعٌ لاحقٌ سليم) ويغيب عن `product-families/` و`check-name/` معاً؛ (دلتا ٢) براندٌ مُمرَّرٌ للهدف وللأخ معاً يُطبَّق على كليهما (لا الأخ وحده)، والتراجع يعيد براند الهدف أيضاً ضمن `restored_product_ids` |
| `frontend_v2/utils/productMerge.test.ts` | task24: معاينة الضمّ الخالصة (`buildMergePreview`) — الهدف الغائب، التوافق الكامل مع تطبيع الاسم، منعا الوحدة/التتبّع التسلسلي وسببهما، عدم اختراع موانع أخرى، وخليط قابلٍ/مرفوضٍ في معاينةٍ واحدة؛ (دلتا ٢) `findBrandCollisions` — فراغان يتصادمان، براندٌ مكرَّر حرفياً، لا تصادم عند الاختلاف، القصّ يطابق ما يفعله الخادم، وتصادمٌ واحد وسط أعضاءَ فريدين |
| `inventory/tests/test_supplier_products.py` | أرقام الموردين: المنتج من مورّدين، ورقمان لمورّد، ومنع الرقم الواحد لمنتجين، والبحث بالرقم بلا تكرار صفّ |
