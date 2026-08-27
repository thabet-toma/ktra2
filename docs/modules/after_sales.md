# after_sales — خدمة ما بعد البيع: بطاقات الكفالة وأوامر الصيانة (وحدة مرخّصة)

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-12. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
وحدة مرخّصة (`after_sales` في `core/modules.py`) تحمل ما يحدث **بعد** خروج البضاعة:
نسخة الكفالة لكل وحدة مباعة (`WarrantyCard`)، وملف الصيانة الذي يوثّق كل شيء من
الشكوى حتى الحل (`ServiceOrder`) بقطع غياره وأحداثه. الوحدة **تفشل مغلقة**: كل
نقطة تمرّ من `require_module` **قبل** `require_perm`، فترد الشركة غير المرخّصة
**404 لا 403**، ولا يكتب النظام صفاً واحداً في جداولها لشركةٍ لا تراها.

قاعدتان تحكمان الوحدة كلها:
- **حالة الكفالة مشتقّة** من `end_date` مقابل اليوم — لا عمود حالة في أي جدول.
- **بند قطع الغيار يتجسّد في مستند واحد بالضبط**؛ `materialized_at` هو القفل،
  والخصم المزدوج ممنوع بالبناء لا بالانضباط.

## أهم الملفات
| الملف | الغرض | أسطر |
|---|---|---|
| `after_sales/service_orders.py` | مال أمر الصيانة ودورة حالته: FSM، صرف قطع الكفالة، توليد الفاتورة، البحث الموحّد | 560 |
| `after_sales/views.py` | `WarrantyCardViewSet` + `ServiceOrderViewSet` — البوابتان وكل الإجراءات | 560 |
| `after_sales/serializers.py` | عقود الـAPI والتحقق (رسائل الـ400 التي يقرأها المستخدم) | 400 |
| `after_sales/models.py` | الجداول الخمسة + `add_months` (أشهر تقويمية لا كتل 30 يوماً) | 380 |
| `after_sales/services.py` | محرّك الكفالة: الإنشاء التلقائي عند ترحيل البيع، والحذف عند التراجع، وفحص التغطية | 235 |
| `after_sales/urls.py` | `SimpleRouter` لا `DefaultRouter` — جذر الـAPI القابل للتصفح يكشف الوحدة | 11 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `WarrantyCard` | `serial`، `start_date`، `duration_months`، `end_date` (مخزَّن وقابل للتمديد)، `source ∈ {auto_sale, manual}`، `supplier_warranty_end_date` | `tenant`، `product`، `product_serial` → `inventory.ProductSerial`، `sales_invoice_line` → `sales.SalesInvoiceLine` (مرساة الحذف)، `partner`، `supplier` |
| `ServiceOrder` | `order_number`، `order_date`، `serial`، `complaint`/`diagnosis`/`resolution`، `status`، `outcome` (حقل منفصل)، `warranty_covered`، `estimated_amount`، `covered_posted_at`، `billing_waived_reason`، `photos` | `tenant`، `partner`، `product`، `technician`، `warranty_card`، `sales_invoice` (كلها SET_NULL) |
| `ServiceOrderPart` | `quantity`، `billing ∈ {billable, covered}`، `unit_price`، **`materialized_at`** | `order` (CASCADE)، `product` (PROTECT)، `sales_invoice_line` (SET_NULL) |
| `ServiceOrderEvent` | `event_type`، `from_status`/`to_status`، `text`، `created_at` | `order` (CASCADE)، `actor` |
| `AfterSalesSettings` | مثبِّت الافتراضيات لكل شركة | `tenant` (OneToOne)، `warranty_expense_account` → `accounting.Account`، `default_labour_product` → `inventory.Product` |

## دوال الـservices العامة
```python
# after_sales/services.py — محرّك الكفالة
def create_auto_warranty_cards(invoice) -> int:  # يستدعيه sales/services/flow.py عند ترحيل فاتورة بيع
def delete_auto_warranty_cards(invoice) -> int:  # عند إلغاء الترحيل — اليدوية لا تُمَسّ
def warranty_coverage(tenant_id: int, serial: str, today=None) -> dict:  # التغطية من البطاقة ومن نسب الوحدة

# after_sales/service_orders.py — أمر الصيانة
def transition_status(order, to_status, *, user=None, outcome="", note="") -> ServiceOrder:  # الحالة لا تنتقل إلا من هنا
def post_covered_parts(order, *, user=None) -> dict:  # حركات SERVICE_ISSUE + قيد مصروف الكفالة
def unpost_covered_parts(order, *, user=None) -> dict:  # المستند السابع في unpost_document
def generate_service_invoice(order, *, user=None, labour_amount=None):  # فاتورة بيع **مسودة**
def detach_service_invoice(order, *, user=None) -> dict:  # يفتح قفل البنود — للمسودة وحدها
def intake_lookup(tenant, term: str) -> dict:  # البحث الموحّد عند الاستقبال
def resolve_warranty_expense_account(tenant_id):  # «5206» تحت «52» — يُنشأ ويُثبَّت
def resolve_labour_product(tenant_id):  # منتج خدمة «أجرة صيانة» — يُنشأ ويُثبَّت
```

## أهم الـAPI endpoints
كلها تحت البادئة `/api/after-sales/` (`core/urls.py`).

| Method | المسار | الـview |
|---|---|---|
| GET/POST | `warranties/` | `WarrantyCardViewSet` (فلاتر `q`، `status`، `source`، `expiring_within_days`) |
| POST | `warranties/{id}/extend/` | `WarrantyCardViewSet.extend` — يُوثَّق التمديد في الملاحظات بتاريخ الخادم |
| GET | `warranties/check/?serial=` | `WarrantyCardViewSet.check` |
| GET/POST | `service-orders/` | `ServiceOrderViewSet` (فلاتر `q`، `status`، `open`، `partner`، `date_from/to`) |
| POST | `service-orders/{id}/transition/` | `ServiceOrderViewSet.transition` — البوابة الوحيدة لتغيير الحالة |
| POST | `service-orders/{id}/parts/` · PATCH/DELETE `service-orders/{id}/parts/{part_id}/` | `add_part` · `part_detail` |
| POST | `service-orders/{id}/post-covered/` · `unpost-covered/` | `post_covered` · `unpost_covered` |
| POST | `service-orders/{id}/generate-invoice/` · `detach-invoice/` | `generate_invoice` · `detach_invoice` |
| POST | `service-orders/{id}/note/` · `approve/` | `add_note` · `approve` |
| GET | `service-orders/lookup/?serial=` | `ServiceOrderViewSet.lookup` |

## التقارير
ثلاثة في `core/reports/after_sales.py` تحت فئة «خدمة ما بعد البيع»، تُعرض في
شاشة التقارير العامّة بلا شاشة خاصة:

| المفتاح | ما يجيبه | الصلاحية |
|---|---|---|
| `after-sales-warranties-expiring` | كفالات سارية تنتهي خلال نافذة (`days`، افتراضها 30) | `aftersales.warranty.view` |
| `after-sales-open-orders` | كل جهاز ما زال عندنا بعمره بالأيام وما ينقص لإغلاقه | `aftersales.order.view` |
| `after-sales-warranty-cost` | ما صُرف على الكفالة من حركات `SERVICE_ISSUE` بتكلفته التاريخية | `aftersales.order.view` |

الثلاثة تحمل `module="after_sales"` — الحقل الذي أُضيف لـ`ReportSpec` في هذا
المعلم — فيردّ `core/reports_api.py` (`report_run`) **404 لا 403** لشركةٍ غير
مرخّصة، وتختفي من الفهرس أصلاً لأن مفاتيح صلاحياتها تسقط من كتالوجها.

## الواجهة (`frontend_v2/`)
| الملف | الغرض |
|---|---|
| `frontend_v2/components/aftersales/WarrantyCardsScreen.tsx` | قائمة بطاقات الكفالة والبحث والبطاقة اليدوية |
| `frontend_v2/components/aftersales/ServiceOrdersScreen.tsx` | قائمة أوامر الصيانة، وفتح المستند، وزر الاستقبال |
| `frontend_v2/components/aftersales/ServiceOrderDocument.tsx` | المستند: الملف · قطع الغيار (ترحيل/فوترة) · السجل الزمني |
| `frontend_v2/components/aftersales/ServiceOrderIntakeModal.tsx` | الاستقبال بالبحث الموحّد والتعبئة من نتائجه |
| `frontend_v2/utils/serviceOrder.ts` · `frontend_v2/utils/warranty.ts` | القواعد الصرفة (بلا React) — مرآة قواعد الخادم |
| `frontend_v2/services/afterSalesApi.ts` | عميل REST الوحيد للوحدة |

شاشتان في خريطة الشاشات: `after-sales` (الكفالات) و`service-orders` (أوامر الصيانة)،
لكلٍّ مفتاح صلاحية مستقل وكلتاهما خلف وحدة `after_sales` في `frontend_v2/utils/viewPermissions.ts`.

## الاعتماديات
**يعتمد على:**
- `accounting` — **api فقط**: `after_sales/service_orders.py` (`post_document`، `unpost_document`، `ensure_account`). لا استيراد لـ`accounting.models` إطلاقاً — يحرسه `.importlinter`.
- `inventory` — **services**: `record_stock_movement` (حركة `SERVICE_ISSUE`)، و**models** كسولة للمنتجات والوحدات المتسلسلة.
- `sales` — **services**: `get_or_create_sales_settings`، `next_invoice_number`، `recalculate_invoice_amounts`، `get_or_create_default_customer`، و**models** (`SalesInvoice`, `SalesInvoiceLine`) لتوليد الفاتورة.
- `core` — `modules` (`require_module`, `module_enabled`)، `access` (`require_perm`)، `api_defaults`.
- `device_registry` — **models للقراءة فقط** داخل `intake_lookup`، وخلف فحص ترخيص الوحدة. **لا FK في أي اتجاه**.

**يعتمد عليه:** `sales` (`sales/services/flow.py` ينادي `create_auto_warranty_cards` بعد استهلاك الوحدات، ومسار إلغاء الترحيل ينادي `delete_auto_warranty_cards`).

## قواعد لا يجوز كسرها
- **`require_module` قبل `require_perm` في `initial()`** (`after_sales/views.py`) — عكس الترتيب يردّ 403 فيُثبت وجود الوحدة لشركة غير مرخّصة.
- **بطاقة الكفالة تُنشأ بتاريخ الفاتورة** لا تاريخ الترحيل ولا التسليم (`after_sales/services.py` (`create_auto_warranty_cards`)) — تاريخ المستند هو ما تُقيَّد به الدفاتر، وحالة التسليم مشتقّة وقد تغيب.
- **مرساة حذف البطاقة التلقائية هي بند الفاتورة** لا رابط الوحدة: إلغاء الترحيل يُفرِّغ `ProductSerial.sales_line` فيضيع الأثر لو اعتمدنا عليه (`after_sales/services.py` (`delete_auto_warranty_cards`)).
- **لا فرادة شرطية على MySQL**: «بطاقة حيّة واحدة لكل وحدة» محصورة في الكود، ورقم أمر الصيانة عليه فهرس لا قيد — تفرّده من `next_document_number` بقفل الدفتر.
- **قفل التجسّد**: `post_covered_parts` يلتقط `covered` غير المقفول، و`generate_service_invoice` يلتقط `billable` غير المقفول، والبند المقفول لا يُعدَّل ولا يُحذف ولا يُعاد تصنيفه (`after_sales/views.py` (`part_detail`)). كسر أيٍّ من هذه يفتح باب الخصم المزدوج (THA-65).
- **`SERVICE_ISSUE` نوع مرجع مستقل** لا يدخل `sales_cogs_map` (تفلتر `SALE`/`STOCK_ISSUE`) — مصروف الكفالة تشغيلي لا COGS. لا تُعِد استعمال `STOCK_ISSUE` هنا.
- **الحالة لا تُغيَّر بـPATCH**: `status`/`outcome`/`covered_posted_at`/`sales_invoice` كلها `read_only` في السيريالايزر، والانتقال من `transition` وحدها فتمرّ من بواباتها.
- **لا حذف لأمر صيانة** — الإلغاء بديل الحذف، والإلغاء ممنوع ما دام في الأمر ترحيلٌ قائم أو فاتورة مرتبطة.
- **الأمر المُسلَّم مجمَّد**: لا تعديل ولا نقل حالة ولا تراجع عن صرف قطعه.
- **صرف بكلفة صفرية يُسجَّل حركةً بلا قيد** — البضاعة خرجت فعلاً، والقيد الصفري مرفوض من `post_journal` أصلاً.
- **`device_registry` بلا FK**: الرابط معرّفٌ نصي وحده — أي مفتاح أجنبي يكسر إطفاء الوحدتين المستقل ويهدم برهان حياد سجل الأجهزة مالياً (THA-45).

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `after_sales/tests/test_warranty.py` | الدورة التلقائية للبطاقة (إنشاء/حذف/إعادة)، اشتقاق الحالة، جانب المورد من نسب الشراء، 404 بلا ترخيص، العزل |
| `after_sales/tests/test_service_orders.py` | صرف القطع المغطاة بتكلفة تاريخية وقيد متوازن، **حارس التجسّد المزدوج بالاتجاهين**، ثبات `sales_cogs_map`، إيراد الأجرة في حساب الخدمات، بوابتا التسليم والإلغاء، البحث الموحّد، البوابة والعزل |
