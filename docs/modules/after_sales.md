# after_sales — خدمة ما بعد البيع: بطاقات الكفالة وأوامر الصيانة (وحدة مرخّصة)

> مبني على قراءة الكود مباشرةً بتاريخ 2026-09-28 (#234). عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
وحدة مرخّصة (`after_sales` في `core/modules.py`) تحمل ما يحدث **بعد** خروج البضاعة:
نسخة الكفالة لكل وحدة مباعة (`WarrantyCard`)، وملف الصيانة الذي يوثّق كل شيء من
الشكوى حتى الحل (`ServiceOrder`) بقطع غياره وأحداثه. الوحدة **تفشل مغلقة**: كل
نقطة تمرّ من `require_module` **قبل** `require_perm`، فترد الشركة غير المرخّصة
**404 لا 403**، ولا يكتب النظام صفاً واحداً في جداولها لشركةٍ لا تراها.

أربع قواعد تحكم الوحدة كلها:
- **حالة الكفالة مشتقّة**: `WarrantyCard.status_on` تعيد `ended` أولاً إن
  وُجدت واقعةُ انتهاء (`ended_on`)، وإلا فمشتقّةٌ من `end_date` مقابل اليوم —
  لا عمود حالة يُخزَّن (#222). وكل فلترة على `end_date` تمرّ من
  `WarrantyCardQuerySet` (`active_on`/`expired_on`/`ended`، #229) — لا مقارنة
  حرّة في مكان آخر.
- **تعطيلٌ لا حذف**: البطاقة التلقائية لا تُحذف أبداً — هويّتها (`id`) مرساةُ
  أوامر الصيانة ورمزِ التحقّق المطبوع. إلغاءُ الترحيل والمرجع وحذفُ المسودّة
  كلها تُسجِّل واقعة انتهاء مؤرَّخة، وإعادةُ الترحيل تُحيي البطاقة بنفسها.
- **البطاقة التي لها حدث لا تُحذف** (#229): `WarrantyCardEvent.card` بـPROTECT،
  والحذف اليدوي يُفحص أولاً (`instance.events.exists()`) فيردّ 400 مقروءاً —
  الاعتماد على `PROTECT` وحده كان يرتدّ 500.
- **بند قطع الغيار يتجسّد في مستند واحد بالضبط**؛ `materialized_at` هو القفل،
  والخصم المزدوج ممنوع بالبناء لا بالانضباط.

## أهم الملفات
| الملف | الغرض | أسطر |
|---|---|---|
| `after_sales/service_orders.py` | مال أمر الصيانة ودورة حالته: FSM، صرف قطع الكفالة، توليد الفاتورة، البحث الموحّد | 560 |
| `after_sales/views.py` | `WarrantyCardViewSet` + `ServiceOrderViewSet` — البوابتان وكل الإجراءات | 560 |
| `after_sales/serializers.py` | عقود الـAPI والتحقق (رسائل الـ400 التي يقرأها المستخدم) | 400 |
| `after_sales/models.py` | جداول الوحدة (بما فيها `PurchaseLineWarranty` #235) + `add_months` (أشهر تقويمية لا كتل 30 يوماً) | 380 |
| `after_sales/services.py` | محرّك الكفالة: الإنشاء/الإحياء التلقائي عند ترحيل البيع، والتعليق عند إلغائه أو حذف المسودّة، وإنهاء بطاقة الوحدة المرتجعة، وفحص التغطية | 470 |
| `after_sales/management/commands/repair_warranty_lifecycle.py` | إصلاح بيانات ما قبل #222 — `--tenant <id> [--apply]`، dry-run افتراضياً. يقيس (أ)/(ب) بفاتورة البطاقة (`sales_invoice` أو بندها) لا برقم بندها — بطاقةٌ بلا أيّ مرساة تُبلَّغ لا تُخمَّن | 243 |
| `after_sales/urls.py` | `SimpleRouter` لا `DefaultRouter` — جذر الـAPI القابل للتصفح يكشف الوحدة | 11 |
| `after_sales/hooks.py` (#233/#235) | جسور الوحدة إلى `core.hooks` — تُسجَّل عند `AppConfig.ready()` وتفشل مغلقةً لشركةٍ غير مرخّصة. (#233) مزوّد `register_serial_requirement`: يقرأ `WarrantyPolicy(method=serial)` فيصل `inventory`. (#235) امتداد سطر الشراء `register_purchase_line_extension("manufacturer_warranty", …)`: قراءةٌ بنداءٍ واحد للفاتورة وكتابةٌ داخل معاملة حفظها، فتحمل `logistics` كفالة السطر دون أن تعرف اسمها. هذان وحدهما مدخل الوحدات الأخرى عليها — لا استيراد `after_sales` من `inventory`/`sales`/`logistics` |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `WarrantyCard` | `serial`، `start_date`، `duration_months`، `end_date` (مخزَّن وقابل للتمديد)، `source ∈ {auto_sale, manual}`، `supplier_warranty_end_date`، `ended_on`/`end_reason ∈ {returned, invoice_unposted, sale_cancelled, superseded}` (#222)، `terms_text` (#231 — تُجمَّد من سياسة البراند أو شروط الشركة عند الإنشاء، لا تتغيّر بتعديل السياسة لاحقاً، والطباعة #238 غير مبنيّة هنا)، **طبقة كفالة المصنع** (#232): `manufacturer_start_date`/`manufacturer_duration_months`/`manufacturer_end_date` مجمَّدةٌ عند الإنشاء — البداية وحدها قابلة للتعديل فتُعيد احتساب النهاية من المدة المجمَّدة نفسها (`manufacturer_warrantor` الفارغ = «لا يوجد»)، **بطاقة «كفالة على الفاتورة»** (#234، `method=invoice` — بلا `product_serial`): `quantity`/`returned_quantity` (`PositiveIntegerField`، صفرٌ على بطاقة وحدة مُرقَّمة)، و`covered_quantity` **خاصيةٌ محسوبة لا مخزَّنة** (`quantity − returned_quantity`)، `objects` من `WarrantyCardQuerySet` (`active_on`/`expired_on`/`ended`، #229) | `tenant`، `product`، `product_serial` → `inventory.ProductSerial` (فارغ لبطاقة الفاتورة، #234)، `sales_invoice` → `sales.SalesInvoice` (مرساة الإحياء — **المرساة الوحيدة** لبطاقة الفاتورة، لا `sales_invoice_line`)، `sales_invoice_line` → `sales.SalesInvoiceLine` (تُفرَّغ إن حُذف البند من المسودّة؛ فارغة دوماً على بطاقة الفاتورة لأنها قد تلخّص عدة بنود)، `end_return_line` → `sales.SalesInvoiceLine` (بند مرجع البيع الذي أنهاها — لا يُستعمَل لبطاقة الفاتورة، انظر §قواعد)، `partner`، `supplier`، `manufacturer_warrantor` → `ManufacturerWarrantor` (PROTECT، اختياري، #232) |
| `WarrantyCardEvent` (#229) | `event_type ∈ {void, unvoid, extend, ended, revived, issued, referred, coverage_refused, coverage_restored, replacement}` (هذه التذكرة تكتب `extend` وحده — الباقي لتذاكر لاحقة)، `reason_code` (نصٌّ حرّ بلا `choices` — مفردات التمديد `courtesy`/`shop_days`/`shop_days_reversed`)، `text`، `old_end_date`/`new_end_date`، `quantity` (لحدثٍ جزئي، غير مستعمل بعد) | `tenant`، `card` → `WarrantyCard` (**PROTECT** — بطاقةٌ لها حدثٌ لا تُحذف)، `service_order` → `ServiceOrder` (SET_NULL)، `actor` → `auth.User` (SET_NULL). سجلٌّ إلحاقي: لا تحديث ولا حذف عبر الـAPI |
| `ServiceOrder` | `order_number`، `order_date`، `serial`، `complaint`/`diagnosis`/`resolution`، `status`، `outcome` (حقل منفصل)، `warranty_covered`، `estimated_amount`، `covered_posted_at`، `billing_waived_reason`، `photos` | `tenant`، `partner`، `product`، `technician`، `warranty_card`، `sales_invoice` (كلها SET_NULL) |
| `ServiceOrderPart` | `quantity`، `billing ∈ {billable, covered}`، `unit_price`، **`serials`** (JSON، على نمط `SalesInvoiceLine.serials`، #223)، **`issued_cost`** (كلفة FIFO الفعلية لحركة `SERVICE_ISSUE`، تُفرَّغ عند التراجع)، **`materialized_at`** | `order` (CASCADE)، `product` (PROTECT)، `sales_invoice_line` (SET_NULL) |
| `ServiceOrderEvent` | `event_type`، `from_status`/`to_status`، `text`، `created_at` | `order` (CASCADE)، `actor` |
| `ManufacturerWarrantor` (#230) | الاسم (**فريد للشركة**، `UniqueConstraint(tenant, name)`)، `service_center_address`، `phone`، `notes`، `is_active` | `tenant`. كل من يشير إليها (السياسة #231، سطر الشراء `PurchaseLineWarranty` #235، البطاقة #232) يفعل ذلك بـPROTECT — لا حذف لجهة مرتبطة، أرشفة (`is_active=False`) بدلاً منه؛ العنوان والهاتف يُقرآن حيّاً في الطباعة لا يُجمَّدان |
| `AfterSalesSettings` | مثبِّت الافتراضيات لكل شركة، ومنذ #230: `default_terms`/`repair_terms` (سقف 2000 حرف)، `extend_for_shop_days` (افتراضه مفعَّل)، `repair_warranty_days` (افتراضه 90، صفرٌ يطفئه، وإلا 1–730) | `tenant` (OneToOne)، `warranty_expense_account` → `accounting.Account`، `default_labour_product` → `inventory.Product` |
| `WarrantyPolicy` (#231) | صفٌّ واحد لكل براند (`OneToOneField` على `inventory.Product`) — **لا سياسة = لا بطاقة تلقائية عند البيع**. `method ∈ {serial, invoice}` (`serial` يُرفض لمنتج خدمة `is_service`)، `dealer_months`/`manufacturer_months`/`supplier_months` (0–600، `manufacturer_months>0` ⇔ وجود `manufacturer_warrantor`)، `terms_override` (سقف 2000 حرف، فارغٌ = شروط الشركة العامة)؛ التحقّق يفرض مدّة التاجر أو المصنع > 0 على الأقل — كفالة المورّد وحدها داخلية لا تُصدر للزبون بطاقة | `tenant`، `product` (CASCADE، مثل `inventory.ProductDemandForecast.product`)، `manufacturer_warrantor` → `ManufacturerWarrantor` (PROTECT، اختياري) |

## دوال الـservices العامة
```python
# after_sales/services.py — محرّك الكفالة (#222: خمس نقاط التحام من sales)
def create_auto_warranty_cards(invoice) -> int:  # ترحيل البيع: يُحيي المعلَّق على هذه الفاتورة ثم يُنشئ الناقص — بسؤال WarrantyPolicy لكل منتج (#231)؛ لا سياسة = لا بطاقة، وterms_text يُجمَّد من السياسة أو من إعدادات الشركة. طبقة المصنع (#232، method=serial وحده) عبر _resolve_manufacturer_layer دفعة واحدة: آخر بطاقة سابقة للوحدة (إعادة بيع، تُنسخ كما هي) ثم كفالة سطر الشراء الذي وردت به الوحدة (PurchaseLineWarranty، #235) وإلا السياسة؛ وطبقة المورّد من `supplier_months` السطر إن وُجد. منتجات method=invoice (#234) تأخذ بطاقة كميةٍ واحدة لكل (فاتورة، منتج) بلا product_serial — طبقة المصنع لها من السياسة وحدها (_policy_manufacturer_layer، خطوة ٣ نفسها بلا وحدة سابقة تُنسخ منها)
def on_sale_unposted(invoice) -> int:  # إلغاء ترحيل البيع: تعليقٌ بـinvoice_unposted — لا حذف (يشمل بطاقة الفاتورة #234، مطابقةٌ عامة بلا فرق عن بطاقة الوحدة)
def on_sale_cancelled(invoice) -> int:  # حذف مسودّة الفاتورة: المعلَّق يصير sale_cancelled بلا رجعة
def on_sales_return_posted(return_invoice) -> int:  # مرجع البيع: يُنهي بطاقات الوحدات المرتجعة وحدها بـreturned، وينقص الكمية المكفولة على بطاقة الفاتورة (#234، _apply_invoice_card_return) بحدث ended جزئي — الصفر يُنهيها returned
def on_sales_return_unposted(return_invoice) -> int:  # إلغاء ترحيل المرجع: يُحيي ما أنهاه هو وحده، وينقص الكمية المُرجَعة على بطاقة الفاتورة بحدث revived جزئي (#234) — يعيد فتحها إن رجعت التغطية
def warranty_coverage(tenant_id: int, serial: str, today=None) -> dict:  # التغطية من البطاقة غير المنتهية ومن نسب الوحدة — unit_info يحمل الآن dealer_months/supplier_months من WarrantyPolicy (#231) لا من عمودَي المنتج المحذوفين، وكل بطاقة تحمل طبقتيها معاً (#232: manufacturer_warrantor_name/manufacturer_end_date/manufacturer_status …)
def get_or_create_after_sales_settings(tenant_id: int) -> AfterSalesSettings:  # صفّ الإعدادات — نقطة `settings/` (#230) تستعمله للقراءة والتعديل معاً
def log_warranty_event(card, *, event_type, reason_code="", text="", service_order=None, user=None, old_end_date=None, new_end_date=None, quantity=None) -> WarrantyCardEvent:  # كتابة حدثٍ واحد على سجل البطاقة (#229) — نقطة كتابةٍ واحدة تعيد استعمالها تذاكر لاحقة (الإلغاء، الإصدار، الإحالة…)

# after_sales/service_orders.py — أمر الصيانة
def transition_status(order, to_status, *, user=None, outcome="", note="") -> ServiceOrder:  # الحالة لا تنتقل إلا من هنا
def post_covered_parts(order, *, user=None) -> dict:  # حركات SERVICE_ISSUE (بتاريخ اليوم، #223) + قيد مصروف الكفالة + استهلاك أرقام القطع المرقّمة
def unpost_covered_parts(order, *, user=None) -> dict:  # المستند السابع في unpost_document + إعادة الأرقام المستهلكة `in_stock`
def generate_service_invoice(order, *, user=None, labour_amount=None):  # فاتورة بيع **مسودة**
def detach_service_invoice(order, *, user=None) -> dict:  # يفتح قفل البنود — للمسودة وحدها
def intake_lookup(tenant, term: str) -> dict:  # البحث الموحّد عند الاستقبال
def resolve_warranty_expense_account(tenant_id):  # «5206» تحت «52» — يُنشأ ويُثبَّت
def resolve_labour_product(tenant_id):  # منتج خدمة «أجرة صيانة» — يُنشأ ويُثبَّت

# after_sales/hooks.py — مزوّد فرض الرقم التسلسلي (#233)
def serial_requirement_provider(tenant_id, product_ids) -> dict:  # `{product_id: سبب}` لمنتجات عليها سياسة `serial` — يُنادى دفعةً واحدة من `inventory.serials.effective_serial_mode` عبر `core.hooks.serial_requirements`؛ `{}` لشركةٍ غير مرخّصة
def purchase_line_warranty_read(tenant_id, items) -> dict:  # (#235) `{item_id: {manufacturer_warrantor, manufacturer_months, supplier_months}}` بنداءٍ واحد للفاتورة؛ `{}` للوحدة المطفأة
def purchase_line_warranty_write(tenant_id, item, payload, user) -> None:  # (#235) يحفظ كفالة السطر داخل معاملة حفظ الفاتورة، والخطأ يُسقط الحفظ كلَّه (400 يسمّي السطر)؛ الوحدة المطفأة تُهمل الحمولة بصمت
def register_hooks() -> None:  # يسجّل المزوّد والامتداد أعلاه في `core.hooks` — يُنادى مرّةً واحدة من `AfterSalesConfig.ready()`

# after_sales/services.py — كفالة سطر الشراء (#235)
def clean_purchase_line_warranty(tenant_id, payload, label) -> dict:  # يتحقّق: جهة نشطة من الشركة، أشهر المصنع 0–600 ولا أشهر بلا جهة ولا جهة بلا أشهر، أشهر المورّد 0–600؛ `label` يسمّي السطر في رسالة الـ400
def save_purchase_line_warranty(tenant_id, item, payload, user, label) -> PurchaseLineWarranty:  # upsert لصفٍّ واحد لكل بند شراء — تنادي به نقطة التصحيح وخطّاف الحفظ معاً
def latest_purchase_line_warranties(tenant_id, product_ids) -> dict:  # آخر شراءٍ مرحَّل لكل منتج بنداءٍ واحد — يغذّي تلميح «آخر شراء» في شاشة السياسات (لا مسودّات)
```

## أهم الـAPI endpoints
كلها تحت البادئة `/api/after-sales/` (`core/urls.py`).

| Method | المسار | الـview |
|---|---|---|
| GET/POST | `warranties/` | `WarrantyCardViewSet` (فلاتر `q`، `status ∈ {active,expired,ended}`، `source`، `expiring_within_days` — الأخيران يستثنيان المنتهية، وكلها عبر `WarrantyCardQuerySet` منذ #229) |
| POST | `warranties/{id}/extend/` | `WarrantyCardViewSet.extend` — يكتب حدث `extend` على سجل البطاقة (`reason_code=courtesy` + التاريخين + السبب الحرّ) **بدل** إلحاق سطرٍ بالملاحظات (#229؛ كان كذلك حتى #222). **يرفض التقصير** (`new_end` يجب أن يتجاوز `end_date` الحالي) **ويرفض بطاقةً منتهية بواقعة** (#222 §٨) |
| GET | `warranties/{id}/events/` | `WarrantyCardViewSet.events` — سجل أحداث البطاقة، للقراءة فقط (#229) |
| GET | `warranties/check/?serial=` | `WarrantyCardViewSet.check` |
| GET/POST/PATCH/DELETE | `manufacturer-warrantors/` | `ManufacturerWarrantorViewSet` (#230) — CRUD كامل خلف `aftersales.settings.manage`. الحذف يمرّ بـ`try/except ProtectedError` عامّ فيردّ 400 مقروءاً لجهةٍ مرتبطة، لا 500؛ الأرشفة (`PATCH {is_active:false}`) هي أداة الإيقاف الطبيعية |
| GET | `manufacturer-warrantors/lookup/` | `ManufacturerWarrantorViewSet.lookup` — الجهات المفعَّلة وحدها، بصلاحية `purchase.invoice.edit` **أو** `aftersales.warranty.view` (أوسع من الإدارة الكاملة؛ تغذّي منتقي كفالة المصنع على بند الشراء لاحقاً #235) |
| GET/PATCH | `settings/` | `AfterSalesSettingsView` (#230) — صفٌّ واحد لكل شركة؛ `GET` يقرأه كل من يملك ترخيص الوحدة بلا صلاحيةٍ إضافية (نمط `SalesSettingsViewSet.current`)، و`PATCH` خلف `aftersales.settings.manage` وحدها |
| GET/POST/PATCH/DELETE | `warranty-policies/` | `WarrantyPolicyViewSet` (#231) — CRUD صفٍّ واحد لكل براند؛ `list`/`retrieve` خلف `aftersales.warranty.view`، والكتابة خلف `aftersales.settings.manage`. فلاتر `product`/`family`/`category` على `list`. المنتج وجهة المصنع من شركةٍ أخرى يُرفضان بـ400 |
| POST | `warranty-policies/bulk/` | `WarrantyPolicyViewSet.bulk` (#231) — يطبّق سياسةً واحدة على كل براندات منتجٍ أبٍ (`family`) أو تصنيف (`category`، عبر `inventory.services.category_descendant_product_ids`) — upsert بصفٍّ واحد لكل براند داخل `transaction.atomic`، **كلٌّ أو لا شيء**: فشل أيّ براند (منتج خدمة تحت `serial` مثلاً) يتراجع عن الدفعة كاملة. سياسة `serial` (فردية أو جماعية) ترفع `is_serialized` على كل براند طُبِّقت عليه (`inventory.services.ensure_product_is_serialized`/`ensure_products_are_serialized`، #233) |
| PATCH | `purchase-line-warranties/` | `PurchaseLineWarrantyView.patch` (#235) — تصحيح كفالة المصنع لسطور **فاتورة شراء مرحَّلة** دفعةً واحدة (`{invoice, lines:[{item, manufacturer_warrantor, manufacturer_months, supplier_months}]}`) عبر `save_purchase_line_warranty` داخل `transaction.atomic` (كلٌّ أو لا شيء). `require_module` قبل `require_perm(aftersales.warranty.manage)`: الوحدة مطفأة أو فاتورة شركةٍ أخرى ⇒ 404؛ مسودة أو بندٌ من فاتورةٍ أخرى ⇒ 400. **البطاقات الصادرة لا تُمسّ** — التصحيح يسري على مبيعاتٍ لاحقة. المسودة لا تمرّ من هنا بل من خطّاف حفظ الفاتورة (`purchase_line_warranty_write`) |
| GET | `warranty-policies/serial-impact/?product=\|family=\|category=` | `WarrantyPolicyViewSet.serial_impact` (#233) — معاينة قبل الحفظ: البراندات الشقيقة غير المتتبَّعة التي سترتفع (`sibling_brands`)، وعدد الوحدات غير المرقَّمة الآن لكل منتج (`unnumbered_units`، عبر `inventory.serials.unnumbered_serial_balance`). قراءةٌ فقط خلف `aftersales.settings.manage` (تسبق حفظاً لا قراءة سياسة قائمة). يستهلكها `WarrantyPolicyModal.tsx`/`WarrantyPolicyBulkModal.tsx` قبل حفظ/تطبيق طريقة `serial` |
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
| `after-sales-warranties-expiring` | كفالات سارية تنتهي خلال نافذة (`days`، افتراضها 30) — المنتهية بواقعة خارجها (#222) | `aftersales.warranty.view` |
| `after-sales-open-orders` | كل جهاز ما زال عندنا بعمره بالأيام وما ينقص لإغلاقه | `aftersales.order.view` |
| `after-sales-warranty-cost` | ما صُرف على الكفالة من حركات `SERVICE_ISSUE` بتكلفته التاريخية | `aftersales.order.view` |

الثلاثة تحمل `module="after_sales"` — الحقل الذي أُضيف لـ`ReportSpec` في هذا
المعلم — فيردّ `core/reports_api.py` (`report_run`) **404 لا 403** لشركةٍ غير
مرخّصة، وتختفي من الفهرس أصلاً لأن مفاتيح صلاحياتها تسقط من كتالوجها.

## الواجهة (`frontend_v2/`)
| الملف | الغرض |
|---|---|
| `frontend_v2/components/aftersales/WarrantyCardsScreen.tsx` | قائمة بطاقات الكفالة والبحث والبطاقة اليدوية، وزر «الإعدادات» (#230) الذي يفتح `WarrantySettingsScreen`. عمود المنتج/الجهاز يعرض «الكمية المغطاة N من Q» (#234) لبطاقة الفاتورة بلا رقم تسلسلي |
| `frontend_v2/components/aftersales/WarrantySettingsScreen.tsx` (#230/#231) | إعدادات الوحدة: قسم «جهات كفالة المصنع» (قائمة/إضافة/تعديل/أرشفة)، قسم «سياسات الكفالة» (#231 — قائمة/إنشاء/تعديل/حذف لكل براند، وزر «تطبيق جماعي» يفتح `WarrantyPolicyBulkModal`)، وقسم «الشروط والإعدادات» (شروط الشركة وشروط الإصلاح بعدّاد حروف وتنبيه فوق 1200، وتمديد أيام الصيانة، ومدة كفالة الإصلاح). `GET` يُعرض للجميع، والتعديل خلف `aftersales.settings.manage` |
| `frontend_v2/components/aftersales/ManufacturerWarrantorModal.tsx` (#230) | إنشاء/تعديل جهة كفالة مصنع واحدة — لا حذف من الواجهة، الأرشفة عبر خانة `is_active` |
| `frontend_v2/components/aftersales/WarrantyPolicyModal.tsx` (#231) | سياسة براندٍ واحد: عند الإنشاء منتقي براند (`SalesProductPickerModal`، يعرض براندات بلا سياسة قائمة فقط)، الطريقة، المدد الثلاث، جهة المصنع، والشروط الخاصة. المنتج مقفلٌ عند التعديل. **(#233)** الحفظ بطريقة `serial` يستدعي أولاً `GET warranty-policies/serial-impact/` — وُجد أخٌ سيُتتبَّع معه أو وحدةٌ غير مرقَّمة، يعرض تأكيداً (`useConfirm`) يسمّيهما قبل المتابعة؛ الإلغاء يبقي النافذة مفتوحة بلا حفظ |
| `frontend_v2/components/aftersales/WarrantyPolicyBulkModal.tsx` (#231) | تطبيق سياسة واحدة على كل براندات منتجٍ أب أو كل منتجات تصنيف — نفس حقول السياسة المفردة. **(#233)** نفس معاينة/تأكيد `serial-impact` قبل `bulk/`، مبنيةً على تحديد الأب/التصنيف نفسه لا براندٍ واحد |
| `frontend_v2/components/aftersales/ProductWarrantyPolicyLine.tsx` (#231) | خلاصة سياسة البراند للقراءة فقط على كرت المنتج (`ItemForm.tsx`)، خلف ترخيص الوحدة **و** `aftersales.warranty.view` معاً — لا تُبنى من حقول المنتج (حُذفا)، بل من `warranty-policies/?product=` المحروسة بالبوابة نفسها |
| `frontend_v2/components/aftersales/WarrantyCardModal.tsx` | بطاقة واحدة: إنشاء/تعديل/حذف/تمديد، ومنذ #229 سجل أحداثها (`GET .../events/`) بدل قراءة تاريخ التمديد من الملاحظات. ومنذ #232: قسم «كفالة المصنع» بحالتها المستقلة — الجهة والمدة مجمَّدتان على البطاقة التلقائية، والبداية وحدها قابلة للتعديل خلف `aftersales.warranty.manage`. ومنذ #234: شارة «الكمية المغطاة N من Q» في الترويسة لبطاقة الفاتورة بلا رقم تسلسلي |
| `frontend_v2/components/aftersales/ServiceOrdersScreen.tsx` | قائمة أوامر الصيانة، وفتح المستند، وزر الاستقبال |
| `frontend_v2/components/aftersales/ServiceOrderDocument.tsx` | المستند: الملف · قطع الغيار (ترحيل/فوترة) · السجل الزمني — يملأ `sale_price` عند إضافة قطعة مفوترة وعند تحويل قطعة مغطاة إليها؛ عمود «الأرقام» في جدول القطع يفتح `SerialEntryModal` نفسه (`mode="pick"`، مصدره «في المخزن») لقطعةٍ مغطاة من منتجٍ مرقّم لم تتجسّد بعد — على البند الجديد وعلى القائم سواء، لا حقل نصّ عند الإضافة فقط؛ النمط `required` من إعدادات المبيعات (`serial_entry_mode`) نفس مصدر `SalesInvoiceEditor` (#223 مراجعة) |
| `frontend_v2/components/aftersales/ServiceOrderIntakeModal.tsx` | الاستقبال بالبحث الموحّد والتعبئة من نتائجه |
| `frontend_v2/utils/serviceOrder.ts` · `frontend_v2/utils/warranty.ts` | القواعد الصرفة (بلا React) — مرآة قواعد الخادم. `warranty.ts` منذ #232: `manufacturerWarrantyStatusLabel`/`manufacturerWarrantyRemainingText` — `null` من الخادم يعني «لا يوجد» صراحةً. ومنذ #234: `warrantyCoveredQuantityLabel(covered, quantity)` — «الكمية المغطاة N من Q» لبطاقة الفاتورة، بحالات `node --test` في `warranty.test.ts` |
| `frontend_v2/services/afterSalesApi.ts` | عميل REST الوحيد للوحدة |

شاشتان في خريطة الشاشات: `after-sales` (الكفالات) و`service-orders` (أوامر الصيانة)،
لكلٍّ مفتاح صلاحية مستقل وكلتاهما خلف وحدة `after_sales` في `frontend_v2/utils/viewPermissions.ts`.

## الاعتماديات
**يعتمد على:**
- `accounting` — **api فقط**: `after_sales/service_orders.py` (`post_document`، `unpost_document`، `ensure_account`). لا استيراد لـ`accounting.models` إطلاقاً — يحرسه `.importlinter`.
- `inventory` — **services**: `record_stock_movement` (حركة `SERVICE_ISSUE`)، و`inventory.serials` (`assert_issue_serials_declared`/`issue_serials`/`unissue_serials`، #223)، و`inventory.services` (`ensure_product_is_serialized`/`ensure_products_are_serialized`، #233)، و**models** كسولة للمنتجات والوحدات المتسلسلة.
  عكس الاتجاه: `inventory` لا يستورد `after_sales` مطلقاً — فرض الرقم التسلسلي وحظر إلغاء التتبّع يصلان `inventory` عبر مزوّدٍ في `core.hooks` (`after_sales/hooks.py`، #233) لا استيراداً مباشراً.
- `sales` — **services**: `get_or_create_sales_settings`، `next_invoice_number`، `recalculate_invoice_amounts`، `get_or_create_default_customer`، و**models** (`SalesInvoice`, `SalesInvoiceLine`) لتوليد الفاتورة.
- `core` — `modules` (`require_module`, `module_enabled`)، `access` (`require_perm`)، `api_defaults`.
- `device_registry` — **models للقراءة فقط** داخل `intake_lookup`، وخلف فحص ترخيص الوحدة. **لا FK في أي اتجاه**.

**يعتمد عليه:** `sales` (#222 — نقطة ربطٍ واحدة، كلها كسولة ومحروسة بـ`module_enabled`):
`sales/services/flow.py` (`post_sales_invoice`) ينادي `create_auto_warranty_cards` بعد استهلاك الوحدات على البيع، و`on_sales_return_posted` بعد `restore_returned_sales_serials` على المرجع؛ `sales/views.py` (`unpost_invoice`) ينادي `on_sale_unposted` أو `on_sales_return_unposted` حسب نوع الفاتورة، و(`destroy`) ينادي `on_sale_cancelled` عند حذف مسودّة.

## قواعد لا يجوز كسرها
- **`require_module` قبل `require_perm` في `initial()`** (`after_sales/views.py`) — عكس الترتيب يردّ 403 فيُثبت وجود الوحدة لشركة غير مرخّصة.
- **بطاقة الكفالة تُنشأ بتاريخ الفاتورة** لا تاريخ الترحيل ولا التسليم (`after_sales/services.py` (`create_auto_warranty_cards`)) — تاريخ المستند هو ما تُقيَّد به الدفاتر، وحالة التسليم مشتقّة وقد تغيب.
- **تعطيلٌ لا حذف (#222)**: `on_sale_unposted` يُعلِّق البطاقات الحيّة (`ended_on`/`end_reason=invoice_unposted`) ولا يحذف صفاً واحداً — الـ`id` هو ما تتعلّق به أوامر الصيانة ورمزُ التحقّق المطبوع. إعادةُ الترحيل (`create_auto_warranty_cards`) تُحييها بمطابقة `(sales_invoice, product_serial)` **لا** بالبند: تعديل المسودّة يحذف بنوداً بلا `id` (`sales/serializers.py` (`SalesInvoiceSerializer.update`))، والفاتورة هي المرساة الصامدة. بطاقةٌ منتهية بمرجعٍ (`end_reason=returned`) **لا تُحيا أبداً** بترحيل بيع.
- **مرجع البيع يحدّد الوحدة المرتجعة من `ProductSerial.return_line`** لا من ترتيب `id`: `inventory/serials.py` (`restore_returned_sales_serials`) يقرأ `line.serials` (إجباري تحت `required`، بمرآة `assert_sales_return_serials_declared`)، و`after_sales/services.py` (`on_sales_return_posted`) يقرأ ما كتبته لينهي بطاقة الوحدة بعينها.
- **المشتري الثاني يأخذ بطاقة جديدة**: `already_carded` (داخل `create_auto_warranty_cards`) يسأل «بطاقة غير منتهية لهذه الوحدة على **هذه الفاتورة**» لا مطلقاً — ومعه شفاءٌ ذاتي: أي بطاقة `auto_sale` حيّة للوحدة على فاتورة أخرى تُنهى `superseded` بتاريخ الفاتورة الجديدة. اليدوية لا تُمَسّ أبداً.
- **لا فرادة شرطية على MySQL**: «بطاقة حيّة واحدة لكل وحدة **على فاتورة واحدة**» محصورة في الكود، ورقم أمر الصيانة عليه فهرس لا قيد — تفرّده من `next_document_number` بقفل الدفتر.
- **التمديد لا يقصّر (#222 §٨)**: `WarrantyExtendSerializer.resolved_end_date` يرفض `new_end <= card.end_date`، و`WarrantyCardViewSet.extend` يرفض بطاقةً منتهية بواقعة. تقصيرٌ موثَّق بصلاحية `aftersales.warranty.void` مستقبلٌ في #236.
- **التمديد يكتب حدثاً لا سطر ملاحظات (#229)**: `WarrantyCardViewSet.extend` ينادي `after_sales/services.py` (`log_warranty_event`) بـ`event_type=extend`، `reason_code=courtesy`، والتاريخين — `card.notes` لا يُمَسّ. تذاكر لاحقة (الإلغاء #218، الإصدار #217، تمديد أيام الصيانة #227…) تكتب على السجل نفسه بأنواع حدثٍ أخرى من الشكل النهائي (`WarrantyCardEvent.TYPE_CHOICES`) — هذه التذكرة لا تنشئ إلا `extend`.
- **الصفحة العامة لا تنشر ملاحظات البطاقة ولا سبب انتهائها**: `docshare/documents/aftersales_docs.py` (`build_warranty_card`) يُفرِغ `notes` دائماً، وحالتها من `WarrantyCard.status_on` (عبر `warranty_card_expired`) لا من مقارنة `end_date` باليوم.
- **قفل التجسّد**: `post_covered_parts` يلتقط `covered` غير المقفول، و`generate_service_invoice` يلتقط `billable` غير المقفول، والبند المقفول لا يُعدَّل ولا يُحذف ولا يُعاد تصنيفه (`after_sales/views.py` (`part_detail`)). كسر أيٍّ من هذه يفتح باب الخصم المزدوج (THA-65).
- **وجود فاتورة لا يعني حسم الفوترة (#223)**: `billing_is_resolved`/`delivery_blockers` (`after_sales/service_orders.py`) يفحصان كل قطعة `billable` بلا `materialized_at` — لا وجود `sales_invoice` وحده. قطعةٌ أُضيفت **بعد** توليد الفاتورة (الإضافة تبقى مسموحة ما دام الأمر غير مُسلَّم ولا ملغى) تمنع التسليم برسالة تسمّيها، ما لم يُكتب `billing_waived_reason`.
- **القطعة المغطاة المرقّمة تستهلك رقمها (#223)**: `post_covered_parts` يستدعي `inventory.serials` (`assert_issue_serials_declared` قبل أي كتابة تحت «إجباري»، ثم `issue_serials` بعد بناء الحركات) — الوحدة تصير `ProductSerial.STATUS_ISSUED` ومرجعها `issued_to` هو بند القطعة، لا `STATUS_SOLD`: بيعٌ لاحق بـFIFO (`consume_sales_serials` يستعلم `in_stock` وحدها) لا يخصّصها أبداً. `unpost_covered_parts` يستدعي `unissue_serials` فتعود `in_stock`. الفرض يمرّ من `inventory.serials.effective_serial_mode` بجانب `sale` (صرف الأمر = بيعٌ من منظور النمط، #233): `sales_serial_mode` للشركة، أو `required` إن كانت القطعة على منتجٍ عليه سياسة كفالة `serial` — أيّهما فرض.
- **سعرٌ صفري على قطعة مفوترة يُرفض لا يُخصَم مجاناً (#223)**: `generate_service_invoice` يرفض (400) وجود قطعة `billable` سعرها ≤ 0، ويسمّيها؛ و`billing` يُفحص مقابل `BILLING_CHOICES` صراحةً في `ServiceOrderPartSerializer` (`validate_billing`) عند الإضافة والتعديل معاً — قيمة عشوائية كانت تُسقط القطعة من كل المسارات بصمت.
- **الصرف يُؤرَّخ بيوم الترحيل لا يوم الاستقبال (#223)**: `post_covered_parts` يستعمل `timezone.localdate()` لحركة `SERVICE_ISSUE` وقيدها — لا `order.order_date`، فلا يقع الصرف في فترةٍ أُقفلت بعد الاستقبال ولا قبل شراء القطعة نفسها. **والفحص يسبق الكتابة ولو كانت الكلفة صفرية**: `validate_fiscal_period` يُستدعى صراحةً قبل أي حركة، فلا يفلت صرفٌ بلا قيدٍ من فترةٍ مقفلة بحجة أنه بلا قيد.
- **`SERVICE_ISSUE` نوع مرجع مستقل** لا يدخل `sales_cogs_map` (تفلتر `SALE`/`STOCK_ISSUE`) — مصروف الكفالة تشغيلي لا COGS. لا تُعِد استعمال `STOCK_ISSUE` هنا.
- **الحالة لا تُغيَّر بـPATCH**: `status`/`outcome`/`covered_posted_at`/`sales_invoice` كلها `read_only` في السيريالايزر، والانتقال من `transition` وحدها فتمرّ من بواباتها.
- **لا حذف لأمر صيانة** — الإلغاء بديل الحذف، والإلغاء ممنوع ما دام في الأمر ترحيلٌ قائم أو فاتورة مرتبطة.
- **الأمر المُسلَّم مجمَّد**: لا تعديل ولا نقل حالة ولا تراجع عن صرف قطعه.
- **صرف بكلفة صفرية يُسجَّل حركةً بلا قيد** — البضاعة خرجت فعلاً، والقيد الصفري مرفوض من `post_journal` أصلاً.
- **`device_registry` بلا FK**: الرابط معرّفٌ نصي وحده — أي مفتاح أجنبي يكسر إطفاء الوحدتين المستقل ويهدم برهان حياد سجل الأجهزة مالياً (THA-45).
- **حذف جهة كفالة المصنع فحصٌ عامٌّ لا قائمة مسمّاة (#230)**: `ManufacturerWarrantorViewSet.perform_destroy` يكتفي بـ`try/except ProtectedError` — لا شيء يشير إلى `ManufacturerWarrantor` بـPROTECT في هذا المعلم، لكن كل مرجعٍ لاحق (السياسة #231، بند الشراء #235، البطاقة #232) يُحمى تلقائياً بمجرد أن يُعرَّف بـ`on_delete=models.PROTECT` — لا تذكرة لاحقة تحتاج لمس هذا الملف.
- **لا سياسة = لا بطاقة (#231)**: `create_auto_warranty_cards` يقرأ `WarrantyPolicy` بسؤالٍ واحد لكل منتجات الفاتورة؛ منتجٌ بلا صفّ سياسة لا يأخذ بطاقةً مطلقاً، بصرف النظر عن `is_serialized`. وجودُ السياسة وحده هو الشرط — `dealer_months=0` صالحٌ وينتج بطاقةً بمدّة صفر (طبقة التاجر فقط، ولا يمنع صرف طبقتي المصنع/المورّد لاحقاً في #232/#235).
- **`WarrantyCard.terms_text` يُجمَّد عند الإنشاء ولا يتبع تعديلات السياسة اللاحقة (#231)**: تعديل `terms_override` على سياسة براند بعد صدور بطاقاتٍ منه لا يغيّر نصّها المحفوظ — البطاقة وثيقةُ لحظة الإصدار، لا مرآةً حيّة للسياسة.
- **حقلا الكفالة على `inventory.Product` (`warranty_months`/`supplier_warranty_months`) لم يعودا موجودين (#231)**: أي قارئٍ جديد لمدّة كفالة براند يذهب إلى `after_sales.WarrantyPolicy` عبر `product_id` — لا إلى المنتج. الهجرة `inventory/migrations/0039_remove_warranty_months_fields.py` تعتمد صراحةً على `after_sales/migrations/0008_backfill_warranty_policies.py` كي يسبقها نقل البيانات.
- **`warranty-policies/bulk/` كلٌّ أو لا شيء (#231)**: فشل أيّ براند واحد (مثل منتج خدمة تحت `method=serial`) يُرجع 400 ولا يكتب صفاً واحداً من الدفعة — لا تصفية صامتة للبراندات الفاشلة.
- **طبقة كفالة المصنع مجمَّدة إلا البداية (#232)**: `manufacturer_warrantor`/`manufacturer_duration_months` لا يُعدَّلان على بطاقةٍ تلقائية بعد إنشائها — `WarrantyCardViewSet._AUTO_CARD_EDITABLE` يفتح `manufacturer_start_date` وحدها، و`WarrantyCardSerializer.validate` يُعيد احتساب `manufacturer_end_date` منها ومن المدة المجمَّدة دائماً (قيمة العميل فيها تُتجاهَل). و`manufacturer_status_on` دالةٌ مستقلة عن `status_on` — `None` صراحةً حين لا جهة («لا يوجد»)، لا حالة رابعة.
- **مصدر طبقة المصنع عند البيع: دالةٌ واحدة (#232)**: `_resolve_manufacturer_layer` (`after_sales/services.py`) تحسم كل وحدات الفاتورة الجديدة باستعلامٍ واحد — آخر بطاقة `auto_sale` سابقة لنفس `product_serial` **وقف بيعها فعلاً** (حيّة، أو انتهت `returned`/`superseded`؛ تُنسخ حرفياً)، وإلا `WarrantyPolicy`. **بطاقةٌ بيعها لم يقف تُستبعَد من الاستعلام نفسه لا تُفحص بعده**: `end_reason ∈ {sale_cancelled, invoice_unposted}` (مسودّةٌ حُذفت أو ترحيلٌ معلَّق) تسقط إلى الصفّ الأقدم المؤهَّل التالي لنفس الوحدة تلقائياً، ثم للسياسة إن لم يبقَ شيء. خطوة `PurchaseLineWarranty` (#235) بين الاثنتين لم تُبنَ بعد — هذا هو السَّم الذي يُدخِلها بلا لمس الدالتين الأخريين.
- **سياسة `serial` تفرض الرقم على `inventory`/`sales`/`logistics` عبر خطّافٍ لا استيراد (#233)**: `after_sales/hooks.py` (`register_hooks`) يسجّل مزوّده في `core.hooks` عند `AppConfig.ready()`؛ `inventory.serials.effective_serial_mode` هو المستهلك الوحيد. الاتجاه معكوسٌ عمداً عن بقية الوحدة — `inventory` لا يستورد `after_sales` مطلقاً، فمن يضيف حاجةً جديدة يضيف مزوّداً هنا لا استيراداً هناك. نفس الخطّاف يمنع إلغاء تتبّع منتجٍ عليه سياسة `serial` قائمة (`inventory.serializers.ProductSerializer._validate_serial_tracking_toggle`) — **والحارس يسأل الخطّاف عن المنتج وكل إخوته تحت الأب في نداءٍ واحد لا عن الصفّ المعدَّل وحده**: `is_serialized` حقلٌ أبويّ تُنزِله مزامنة العائلة على كل الإخوة بعد كل حفظ، فبراندٌ شقيقٌ بلا سياسة يستطيع إطفاء تتبّع أخيه المفروض دون أن يمرّ طلبه من حارس الأخ أصلاً لولا هذا الفحص الجماعي.
- **حفظ سياسة `serial` يرفع `is_serialized` ولا يخفضه أبداً (#233)**: `_sync_serial_tracking` (`perform_create`/`perform_update`/`bulk`) ينادي `inventory.services.ensure_product_is_serialized`/`ensure_products_are_serialized` — يرتفع على البراند **وإخوته** عبر مزامنة العائلة (`is_serialized` من `FAMILY_FIELD_NAMES` أصلاً)، وحذف السياسة لا يمسّ القيمة المرتفعة.
- **بطاقة «كفالة على الفاتورة» بلا `product_serial` مطلقاً (#234)**: `method=invoice` ينتج بطاقةً واحدة لكل `(sales_invoice, product)` بالكمية — لا مطابقة على وحدة، ولا `end_return_line`/`_supersede_stale_cards` (كلاهما يفترض وحدةً مُرقَّمة). المرجع الجزئي يمسّها عبر `_apply_invoice_card_return` وحدها: يزيد/ينقص `returned_quantity` بحدث `WarrantyCardEvent` جزئي (`ended`/`revived`، `quantity`)، وبلوغ الصفر ينهيها `returned` مباشرةً على الحقول (لا عبر `end_return_line`). **كل قارئٍ للرقم التسلسلي في الوحدة (`warranty_coverage`، `_supersede_stale_cards`، `repair_warranty_lifecycle.py`، الصفحة العامة) يستبعد بطاقة الفاتورة تلقائياً**: الأول والصفحة العامة يبحثان بـ`serial` غير الفارغ (بطاقة الفاتورة `serial=""`)، والثاني يعمل على `product_serial` مباشرة (`None` لا يطابق)، وأمر الإصلاح يفلتر `product_serial__isnull=False` صراحةً — لا حاجة لاستثناءٍ إضافي في أيٍّ منها.
- **مطابقة بطاقة الفاتورة بمرساة الفاتورة وحدها، لا بسياسة المنتج الحالية (#234-review)**: `_apply_invoice_card_return` يطلب البطاقات أولاً بـ`sales_invoice_id=original_id` (ثم يحسب الكمية من بنود مرجع البيع لهذه المنتجات)، و`create_auto_warranty_cards` يبحث عن بطاقةٍ قائمة لكل منتجٍ على الفاتورة بصرف النظر عن `WarrantyPolicy` الحالية — **السياسة الحالية تقرّر إنشاء بطاقةٍ جديدة وحده، لا إحياء القائم ولا إنقاصه بمرجع**. سياسةٌ عُدِّلت إلى `serial` أو حُذفت بعد البيع لا تُسقط بطاقة فاتورةٍ صُرفت أيام كانت `invoice`. لا قصّ (`min`) على زيادة `returned_quantity` عند المرجع: `guard_sales_return_quantities` (`sales/services/flow.py`، T-RETQTY) يمنع أي مرجعٍ من تجاوز القابل للإرجاع من الفاتورة الأصلية عند كل حفظ لبنوده عبر كل مراجيعها الشقيقة معاً، فتجاوز `quantity` هنا مستحيلٌ بالبناء. `quantity`/`returned_quantity`/`WarrantyCardEvent.quantity` كلها `PositiveIntegerField` (هجرتا `0010`/`0011`) — ومنتجٌ `method=invoice` بكميةٍ كسرية (كيلوغرامات مثلاً) على فاتورة بيعٍ أو مرجعها يُرفض بـ400 يسمّي المنتج والكمية بدل أن يُقصّ كسره صامتاً.
- **`WarrantyCard.device_name` التلقائي والبحث بالرقم التسلسلي يمرّان عبر
  `inventory/services.py` (`product_display_name`) لا `str(product)`** (#42):
  بطاقةٌ من إخوةٍ تحت أبٍ واحد كانت تحمل المقاس عارياً بلا براند مميِّز.
  **قيمةٌ مجمَّدة من الآن فصاعداً فقط** — بطاقاتٌ تلقائية أُنشئت قبل هذا
  التاريخ تبقى على صيغتها القديمة حرفاً، بلا backfill. الكتابة تُقصّ بحدّ
  العمود نفسه (`WarrantyCard._meta.get_field('device_name').max_length`، لا
  رقماً مطبوعاً) لأن الاسم المركَّب قد يبلغ ٣٠٣ محرفاً والعمود حدّه ٢٠٠.

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `after_sales/tests/test_warranty.py` | الدورة التلقائية للبطاقة (إنشاء/تعليق/إحياء بنفس الـ`id`)، اشتقاق الحالة، جانب المورد من نسب الشراء، 404 بلا ترخيص، العزل |
| `after_sales/tests/test_warranty_lifecycle.py` | #222 كاملةً: المرجع (كلي/جزئي بالوحدة المسمّاة) ينهي البطاقة، المشتري الثاني يأخذ بطاقة جديدة والشفاء الذاتي، ثبات الهوية عبر إلغاء/إعادة الترحيل مع تعديل المسودّة (والحدث نفسه يبقى عليها)، فاتورة الصيانة تكفل قطعتها المفوترة، والتمديد لا يقصّر |
| `after_sales/tests/test_warranty_events.py` | #229: التمديد يكتب حدث `extend` (التاريخين والسبب) لا سطر ملاحظات، `GET .../events/` للقراءة فقط، بطاقةٌ لها حدث تُرفض حذفها بـ400 لا 500، `WarrantyCardQuerySet` (`active_on`/`expired_on`/`ended`)، والبوابة والعزل على النقطة الجديدة |
| `after_sales/tests/test_warranty_repair.py` | أمر `repair_warranty_lifecycle` — dry-run لا يكتب، `--apply` يُصلح (أ)/(ب) وتقرير (ج)، إعادة التشغيل بلا أثر، عزل الشركات، رفض غير المرخّصة |
| `after_sales/tests/test_service_orders.py` | صرف القطع المغطاة بتكلفة FIFO وقيد متوازن بتاريخ اليوم، **حارس التجسّد المزدوج بالاتجاهين**، ثبات `sales_cogs_map`، إيراد الأجرة في حساب الخدمات، بوابتا التسليم والإلغاء، البحث الموحّد، البوابة والعزل، ومنذ #223: قطعة مفوترة أُضيفت بعد الفاتورة تمنع التسليم، القطعة المغطاة المرقّمة تستهلك رقمها (وتحت `optional` لا يخصّصها بيعٌ لاحق FIFO) والتراجع يعيده `in_stock`، سعرٌ صفري على قطعة مفوترة يُرفض، `billing` خارج `BILLING_CHOICES` يُرفض، وشهرٌ مقفل عند الاستقبال لا يمنع الترحيل اليوم بينما فترة اليوم المقفلة ترفض حتى الصرف الصفري |
| `logistics/tests/test_issued_serial_purchase_guards.py` | وحدةٌ تسلسلية `issued` (صُرفت خارج البيع) تمنع حذفها في إلغاء ترحيل فاتورة الشراء، وإلغاء سند الاستلام، ومرتجع الشراء — الثلاثة عبر `release_purchase_serials`/`release_returned_purchase_serials` (#223) |
| `docshare/tests/test_voucher_and_aftersales.py` | الصفحة العامة لا تنشر ملاحظات البطاقة، وحالتها من `status_on` لا من تاريخ الانتهاء وحده |
| `after_sales/tests/test_manufacturer_warrantors_and_settings.py` | #230: CRUD جهات كفالة المصنع، الأرشفة عبر `is_active=False`، الاسم الفريد للشركة، حذف جهةٍ مرتبطة يُرفض بـ400 لا 500، `lookup/` بصلاحية `purchase.invoice.edit` أو `aftersales.warranty.view`، إعدادات شركة جديدة (تمديد مفعَّل وكفالة إصلاح 90 يوماً)، رفض الشروط فوق 2000 حرف وكفالة الإصلاح خارج 0/1–730، `aftersales.settings.manage` تحصر الكتابة، والبوابة والعزل |
| `after_sales/tests/test_warranty_policies.py` | #231: التحقّق (مدّةٌ واحدة > 0، `serial` مرفوضة لمنتج خدمة، `manufacturer_months` مرتبطة بوجود الجهة اتجاهين، سقف الشروط)، CRUD وتكرار البراند (400)، عزل المنتج/الجهة/السياسة عبر الشركات، البوابة (`require_module` قبل `require_perm`، `warranty.view` للقراءة و`settings.manage` للكتابة)، `bulk/` (صفٌّ لكل براند تحت أبٍ أو تصنيف، upsert، كلٌّ أو لا شيء)، تجميد `terms_text`/المدّة على بطاقةٍ صدرت رغم تعديل السياسة لاحقاً، ودالّة التحويل النقية في هجرة `0008_backfill_warranty_policies`. ومنذ #233: منتجٌ مفروضٌ يُلزَم برقمٍ حتى بنمط شركة «بدون» ويُقبل بمجرّد إدخاله، رقمٌ جديد ضمن الرصيد غير المرقَّم يُسجَّل ويُستهلك وتجاوزه يُرفض (بما فيها حدّ الرصيد الفاصل: رصيدٌ = 1 يُباع منه رقمٌ جديد واحد يُقبل)، الشراء لا يُفرض إلى «إجباري» إلا بنمط الشركة نفسه، إلغاء التتبّع يُرفض ما دامت السياسة قائمة ولو عبر PATCH براندٍ شقيقٍ بلا سياسة (مزامنة العائلة)، تعطيل الوحدة يُسقط الفرض، حفظ/تطبيقٌ جماعي لسياسة `serial` يرفع `is_serialized` على البراند وإخوته ولا يخفضه الحذف، و`serial-impact/` (البراندات الشقيقة والرصيد غير المرقَّم) |
| `after_sales/tests/test_warranty_manufacturer_layer.py` | #232: سياسةٌ بجهة تعطي طبقة مصنع بنهايتها، بلا جهة = `None`/«لا يوجد» صراحةً، استقلال حالتي الطبقتين (تاجرٌ منتهٍ ومصنعٌ سارٍ معاً)، المشتري الثاني لوحدةٍ مرتجعة يأخذ تاجراً كاملاً من تاريخ بيعه الثاني ومصنعاً منسوخاً حرفياً من البطاقة الأولى رغم تغيّر السياسة بينهما، تعديل بداية المصنع يعيد احتساب نهايتها ولا يمسّ طبقة التاجر، ورفض تعديل الجهة/المدة على بطاقةٍ تلقائية، وتحقّق البطاقة اليدوية والعزل عبر الشركات |
| `after_sales/tests/test_purchase_line_warranty.py` | #235: بيعٌ من دفعتَي شراء بكفالتين مختلفتين ⇒ بطاقتان بطبقتَي مصنع مختلفتين؛ أولوية البطاقة السابقة ثم سطر الشراء ثم السياسة؛ سطرٌ بلا جهة يغلب سياسةً بجهة؛ جهة مؤرشفة/أشهر بلا جهة/جهة بلا أشهر/أشهر > 600 ⇒ 400 يسمّي السطر والفاتورة لا تُحفظ (ذرّية)؛ الوحدة مطفأة ⇒ الحمولة مُتجاهَلة وPATCH يردّ 404؛ PATCH على مرحَّلة لا يمسّ البطاقات الصادرة؛ عزل الشركة؛ تلميح «آخر شراء» باستعلامٍ واحد للصفحة |
| `after_sales/tests/test_warranty_invoice_cards.py` | #234: بندان لنفس المنتج ⇒ بطاقة واحدة بمجموع الكمية، مرتجع 3 من 4 ⇒ تغطية 1 بحدث `ended` جزئي ثم مرتجع الرابع ⇒ `returned`، إلغاء ترحيل المرجع يعيد التغطية بحدث `revived` جزئي ويفتح البطاقة المنتهية `returned`، إلغاء ترحيل الفاتورة وإعادته يحفظ الـ`id` ويعيد حساب الكمية بعد تعديل بند، منتجٌ حُذف من الفاتورة قبل إعادة الترحيل ⇒ `sale_cancelled`، منتج `method=serial` على الفاتورة نفسها يأخذ بطاقةً لكل وحدة كما كان، والعزل عبر الشركات. **#234-review:** مرجعٌ بعد تغيير السياسة إلى `serial` ينقص البطاقة القائمة كما لو لم تتغيّر، وإعادة الترحيل بعد نفس التغيير تُحيي البطاقة بنفس الـ`id` لا تُلغيها، وكميةٌ كسرية لمنتج `method=invoice` تُرفض بـ400 عند الترحيل |
