# after_sales — خدمة ما بعد البيع: بطاقات الكفالة وأوامر الصيانة (وحدة مرخّصة)

> مبني على قراءة الكود مباشرةً بتاريخ 2026-09-28 (#232). عند تعارض هذا الملف مع الكود، الكود هو المرجع.

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
| `after_sales/models.py` | الجداول الخمسة + `add_months` (أشهر تقويمية لا كتل 30 يوماً) | 380 |
| `after_sales/services.py` | محرّك الكفالة: الإنشاء/الإحياء التلقائي عند ترحيل البيع، والتعليق عند إلغائه أو حذف المسودّة، وإنهاء بطاقة الوحدة المرتجعة، وفحص التغطية | 470 |
| `after_sales/management/commands/repair_warranty_lifecycle.py` | إصلاح بيانات ما قبل #222 — `--tenant <id> [--apply]`، dry-run افتراضياً. يقيس (أ)/(ب) بفاتورة البطاقة (`sales_invoice` أو بندها) لا برقم بندها — بطاقةٌ بلا أيّ مرساة تُبلَّغ لا تُخمَّن | 243 |
| `after_sales/urls.py` | `SimpleRouter` لا `DefaultRouter` — جذر الـAPI القابل للتصفح يكشف الوحدة | 11 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `WarrantyCard` | `serial`، `start_date`، `duration_months`، `end_date` (مخزَّن وقابل للتمديد)، `source ∈ {auto_sale, manual}`، `supplier_warranty_end_date`، `ended_on`/`end_reason ∈ {returned, invoice_unposted, sale_cancelled, superseded}` (#222)، `terms_text` (#231 — تُجمَّد من سياسة البراند أو شروط الشركة عند الإنشاء، لا تتغيّر بتعديل السياسة لاحقاً، والطباعة #238 غير مبنيّة هنا)، **طبقة كفالة المصنع** (#232): `manufacturer_start_date`/`manufacturer_duration_months`/`manufacturer_end_date` مجمَّدةٌ عند الإنشاء — البداية وحدها قابلة للتعديل فتُعيد احتساب النهاية من المدة المجمَّدة نفسها (`manufacturer_warrantor` الفارغ = «لا يوجد»)، `objects` من `WarrantyCardQuerySet` (`active_on`/`expired_on`/`ended`، #229) | `tenant`، `product`، `product_serial` → `inventory.ProductSerial`، `sales_invoice` → `sales.SalesInvoice` (مرساة الإحياء)، `sales_invoice_line` → `sales.SalesInvoiceLine` (تُفرَّغ إن حُذف البند من المسودّة)، `end_return_line` → `sales.SalesInvoiceLine` (بند مرجع البيع الذي أنهاها)، `partner`، `supplier`، `manufacturer_warrantor` → `ManufacturerWarrantor` (PROTECT، اختياري، #232) |
| `WarrantyCardEvent` (#229) | `event_type ∈ {void, unvoid, extend, ended, revived, issued, referred, coverage_refused, coverage_restored, replacement}` (هذه التذكرة تكتب `extend` وحده — الباقي لتذاكر لاحقة)، `reason_code` (نصٌّ حرّ بلا `choices` — مفردات التمديد `courtesy`/`shop_days`/`shop_days_reversed`)، `text`، `old_end_date`/`new_end_date`، `quantity` (لحدثٍ جزئي، غير مستعمل بعد) | `tenant`، `card` → `WarrantyCard` (**PROTECT** — بطاقةٌ لها حدثٌ لا تُحذف)، `service_order` → `ServiceOrder` (SET_NULL)، `actor` → `auth.User` (SET_NULL). سجلٌّ إلحاقي: لا تحديث ولا حذف عبر الـAPI |
| `ServiceOrder` | `order_number`، `order_date`، `serial`، `complaint`/`diagnosis`/`resolution`، `status`، `outcome` (حقل منفصل)، `warranty_covered`، `estimated_amount`، `covered_posted_at`، `billing_waived_reason`، `photos` | `tenant`، `partner`، `product`، `technician`، `warranty_card`، `sales_invoice` (كلها SET_NULL) |
| `ServiceOrderPart` | `quantity`، `billing ∈ {billable, covered}`، `unit_price`، **`serials`** (JSON، على نمط `SalesInvoiceLine.serials`، #223)، **`issued_cost`** (كلفة FIFO الفعلية لحركة `SERVICE_ISSUE`، تُفرَّغ عند التراجع)، **`materialized_at`** | `order` (CASCADE)، `product` (PROTECT)، `sales_invoice_line` (SET_NULL) |
| `ServiceOrderEvent` | `event_type`، `from_status`/`to_status`، `text`، `created_at` | `order` (CASCADE)، `actor` |
| `ManufacturerWarrantor` (#230) | الاسم (**فريد للشركة**، `UniqueConstraint(tenant, name)`)، `service_center_address`، `phone`، `notes`، `is_active` | `tenant`. كل من يشير إليها لاحقاً (السياسة #231، بند الشراء #235، البطاقة #232) يفعل ذلك بـPROTECT — لا حذف لجهة مرتبطة، أرشفة (`is_active=False`) بدلاً منه؛ العنوان والهاتف يُقرآن حيّاً في الطباعة لا يُجمَّدان |
| `AfterSalesSettings` | مثبِّت الافتراضيات لكل شركة، ومنذ #230: `default_terms`/`repair_terms` (سقف 2000 حرف)، `extend_for_shop_days` (افتراضه مفعَّل)، `repair_warranty_days` (افتراضه 90، صفرٌ يطفئه، وإلا 1–730) | `tenant` (OneToOne)، `warranty_expense_account` → `accounting.Account`، `default_labour_product` → `inventory.Product` |
| `WarrantyPolicy` (#231) | صفٌّ واحد لكل براند (`OneToOneField` على `inventory.Product`) — **لا سياسة = لا بطاقة تلقائية عند البيع**. `method ∈ {serial, invoice}` (`serial` يُرفض لمنتج خدمة `is_service`)، `dealer_months`/`manufacturer_months`/`supplier_months` (0–600، `manufacturer_months>0` ⇔ وجود `manufacturer_warrantor`)، `terms_override` (سقف 2000 حرف، فارغٌ = شروط الشركة العامة)؛ التحقّق يفرض مدّة التاجر أو المصنع > 0 على الأقل — كفالة المورّد وحدها داخلية لا تُصدر للزبون بطاقة | `tenant`، `product` (CASCADE، مثل `inventory.ProductDemandForecast.product`)، `manufacturer_warrantor` → `ManufacturerWarrantor` (PROTECT، اختياري) |

## دوال الـservices العامة
```python
# after_sales/services.py — محرّك الكفالة (#222: خمس نقاط التحام من sales)
def create_auto_warranty_cards(invoice) -> int:  # ترحيل البيع: يُحيي المعلَّق على هذه الفاتورة ثم يُنشئ الناقص — بسؤال WarrantyPolicy لكل منتج (#231)؛ لا سياسة = لا بطاقة، وterms_text يُجمَّد من السياسة أو من إعدادات الشركة. طبقة المصنع (#232، method=serial وحده) عبر _resolve_manufacturer_layer دفعة واحدة: آخر بطاقة سابقة للوحدة (إعادة بيع، تُنسخ كما هي) وإلا السياسة — سَمٌّ لخطوة PurchaseLineWarranty (#235)
def on_sale_unposted(invoice) -> int:  # إلغاء ترحيل البيع: تعليقٌ بـinvoice_unposted — لا حذف
def on_sale_cancelled(invoice) -> int:  # حذف مسودّة الفاتورة: المعلَّق يصير sale_cancelled بلا رجعة
def on_sales_return_posted(return_invoice) -> int:  # مرجع البيع: يُنهي بطاقات الوحدات المرتجعة وحدها بـreturned
def on_sales_return_unposted(return_invoice) -> int:  # إلغاء ترحيل المرجع: يُحيي ما أنهاه هو وحده
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
| POST | `warranty-policies/bulk/` | `WarrantyPolicyViewSet.bulk` (#231) — يطبّق سياسةً واحدة على كل براندات منتجٍ أبٍ (`family`) أو تصنيف (`category`، عبر `inventory.services.category_descendant_product_ids`) — upsert بصفٍّ واحد لكل براند داخل `transaction.atomic`، **كلٌّ أو لا شيء**: فشل أيّ براند (منتج خدمة تحت `serial` مثلاً) يتراجع عن الدفعة كاملة |
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
| `frontend_v2/components/aftersales/WarrantyCardsScreen.tsx` | قائمة بطاقات الكفالة والبحث والبطاقة اليدوية، وزر «الإعدادات» (#230) الذي يفتح `WarrantySettingsScreen` |
| `frontend_v2/components/aftersales/WarrantySettingsScreen.tsx` (#230/#231) | إعدادات الوحدة: قسم «جهات كفالة المصنع» (قائمة/إضافة/تعديل/أرشفة)، قسم «سياسات الكفالة» (#231 — قائمة/إنشاء/تعديل/حذف لكل براند، وزر «تطبيق جماعي» يفتح `WarrantyPolicyBulkModal`)، وقسم «الشروط والإعدادات» (شروط الشركة وشروط الإصلاح بعدّاد حروف وتنبيه فوق 1200، وتمديد أيام الصيانة، ومدة كفالة الإصلاح). `GET` يُعرض للجميع، والتعديل خلف `aftersales.settings.manage` |
| `frontend_v2/components/aftersales/ManufacturerWarrantorModal.tsx` (#230) | إنشاء/تعديل جهة كفالة مصنع واحدة — لا حذف من الواجهة، الأرشفة عبر خانة `is_active` |
| `frontend_v2/components/aftersales/WarrantyPolicyModal.tsx` (#231) | سياسة براندٍ واحد: عند الإنشاء منتقي براند (`SalesProductPickerModal`، يعرض براندات بلا سياسة قائمة فقط)، الطريقة، المدد الثلاث، جهة المصنع، والشروط الخاصة. المنتج مقفلٌ عند التعديل |
| `frontend_v2/components/aftersales/WarrantyPolicyBulkModal.tsx` (#231) | تطبيق سياسة واحدة على كل براندات منتجٍ أب أو كل منتجات تصنيف — نفس حقول السياسة المفردة |
| `frontend_v2/components/aftersales/ProductWarrantyPolicyLine.tsx` (#231) | خلاصة سياسة البراند للقراءة فقط على كرت المنتج (`ItemForm.tsx`)، خلف ترخيص الوحدة **و** `aftersales.warranty.view` معاً — لا تُبنى من حقول المنتج (حُذفا)، بل من `warranty-policies/?product=` المحروسة بالبوابة نفسها |
| `frontend_v2/components/aftersales/WarrantyCardModal.tsx` | بطاقة واحدة: إنشاء/تعديل/حذف/تمديد، ومنذ #229 سجل أحداثها (`GET .../events/`) بدل قراءة تاريخ التمديد من الملاحظات. ومنذ #232: قسم «كفالة المصنع» بحالتها المستقلة — الجهة والمدة مجمَّدتان على البطاقة التلقائية، والبداية وحدها قابلة للتعديل خلف `aftersales.warranty.manage` |
| `frontend_v2/components/aftersales/ServiceOrdersScreen.tsx` | قائمة أوامر الصيانة، وفتح المستند، وزر الاستقبال |
| `frontend_v2/components/aftersales/ServiceOrderDocument.tsx` | المستند: الملف · قطع الغيار (ترحيل/فوترة) · السجل الزمني — يملأ `sale_price` عند إضافة قطعة مفوترة وعند تحويل قطعة مغطاة إليها؛ عمود «الأرقام» في جدول القطع يفتح `SerialEntryModal` نفسه (`mode="pick"`، مصدره «في المخزن») لقطعةٍ مغطاة من منتجٍ مرقّم لم تتجسّد بعد — على البند الجديد وعلى القائم سواء، لا حقل نصّ عند الإضافة فقط؛ النمط `required` من إعدادات المبيعات (`serial_entry_mode`) نفس مصدر `SalesInvoiceEditor` (#223 مراجعة) |
| `frontend_v2/components/aftersales/ServiceOrderIntakeModal.tsx` | الاستقبال بالبحث الموحّد والتعبئة من نتائجه |
| `frontend_v2/utils/serviceOrder.ts` · `frontend_v2/utils/warranty.ts` | القواعد الصرفة (بلا React) — مرآة قواعد الخادم. `warranty.ts` منذ #232: `manufacturerWarrantyStatusLabel`/`manufacturerWarrantyRemainingText` — `null` من الخادم يعني «لا يوجد» صراحةً |
| `frontend_v2/services/afterSalesApi.ts` | عميل REST الوحيد للوحدة |

شاشتان في خريطة الشاشات: `after-sales` (الكفالات) و`service-orders` (أوامر الصيانة)،
لكلٍّ مفتاح صلاحية مستقل وكلتاهما خلف وحدة `after_sales` في `frontend_v2/utils/viewPermissions.ts`.

## الاعتماديات
**يعتمد على:**
- `accounting` — **api فقط**: `after_sales/service_orders.py` (`post_document`، `unpost_document`، `ensure_account`). لا استيراد لـ`accounting.models` إطلاقاً — يحرسه `.importlinter`.
- `inventory` — **services**: `record_stock_movement` (حركة `SERVICE_ISSUE`)، و`inventory.serials` (`assert_issue_serials_declared`/`issue_serials`/`unissue_serials`، #223)، و**models** كسولة للمنتجات والوحدات المتسلسلة.
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
- **القطعة المغطاة المرقّمة تستهلك رقمها (#223)**: `post_covered_parts` يستدعي `inventory.serials` (`assert_issue_serials_declared` قبل أي كتابة تحت «إجباري»، ثم `issue_serials` بعد بناء الحركات) — الوحدة تصير `ProductSerial.STATUS_ISSUED` ومرجعها `issued_to` هو بند القطعة، لا `STATUS_SOLD`: بيعٌ لاحق بـFIFO (`consume_sales_serials` يستعلم `in_stock` وحدها) لا يخصّصها أبداً. `unpost_covered_parts` يستدعي `unissue_serials` فتعود `in_stock`. الفرض يتبع `sales_serial_mode` للشركة نفسه الذي يحكم البيع — لا سياسة كفالة مستقلة (تلك #233).
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
| `after_sales/tests/test_warranty_policies.py` | #231: التحقّق (مدّةٌ واحدة > 0، `serial` مرفوضة لمنتج خدمة، `manufacturer_months` مرتبطة بوجود الجهة اتجاهين، سقف الشروط)، CRUD وتكرار البراند (400)، عزل المنتج/الجهة/السياسة عبر الشركات، البوابة (`require_module` قبل `require_perm`، `warranty.view` للقراءة و`settings.manage` للكتابة)، `bulk/` (صفٌّ لكل براند تحت أبٍ أو تصنيف، upsert، كلٌّ أو لا شيء)، تجميد `terms_text`/المدّة على بطاقةٍ صدرت رغم تعديل السياسة لاحقاً، ودالّة التحويل النقية في هجرة `0008_backfill_warranty_policies` |
| `after_sales/tests/test_warranty_manufacturer_layer.py` | #232: سياسةٌ بجهة تعطي طبقة مصنع بنهايتها، بلا جهة = `None`/«لا يوجد» صراحةً، استقلال حالتي الطبقتين (تاجرٌ منتهٍ ومصنعٌ سارٍ معاً)، المشتري الثاني لوحدةٍ مرتجعة يأخذ تاجراً كاملاً من تاريخ بيعه الثاني ومصنعاً منسوخاً حرفياً من البطاقة الأولى رغم تغيّر السياسة بينهما، تعديل بداية المصنع يعيد احتساب نهايتها ولا يمسّ طبقة التاجر، ورفض تعديل الجهة/المدة على بطاقةٍ تلقائية، وتحقّق البطاقة اليدوية والعزل عبر الشركات |
