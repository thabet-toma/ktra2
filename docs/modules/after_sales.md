# after_sales — خدمة ما بعد البيع: بطاقات الكفالة وأوامر الصيانة (وحدة مرخّصة)

> مبني على قراءة الكود مباشرةً بتاريخ 2026-09-28 (#229). عند تعارض هذا الملف مع الكود، الكود هو المرجع.

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
| `WarrantyCard` | `serial`، `start_date`، `duration_months`، `end_date` (مخزَّن وقابل للتمديد)، `source ∈ {auto_sale, manual}`، `supplier_warranty_end_date`، `ended_on`/`end_reason ∈ {returned, invoice_unposted, sale_cancelled, superseded}` (#222)، `objects` من `WarrantyCardQuerySet` (`active_on`/`expired_on`/`ended`، #229) | `tenant`، `product`، `product_serial` → `inventory.ProductSerial`، `sales_invoice` → `sales.SalesInvoice` (مرساة الإحياء)، `sales_invoice_line` → `sales.SalesInvoiceLine` (تُفرَّغ إن حُذف البند من المسودّة)، `end_return_line` → `sales.SalesInvoiceLine` (بند مرجع البيع الذي أنهاها)، `partner`، `supplier` |
| `WarrantyCardEvent` (#229) | `event_type ∈ {void, unvoid, extend, ended, revived, issued, referred, coverage_refused, coverage_restored, replacement}` (هذه التذكرة تكتب `extend` وحده — الباقي لتذاكر لاحقة)، `reason_code` (نصٌّ حرّ بلا `choices` — مفردات التمديد `courtesy`/`shop_days`/`shop_days_reversed`)، `text`، `old_end_date`/`new_end_date`، `quantity` (لحدثٍ جزئي، غير مستعمل بعد) | `tenant`، `card` → `WarrantyCard` (**PROTECT** — بطاقةٌ لها حدثٌ لا تُحذف)، `service_order` → `ServiceOrder` (SET_NULL)، `actor` → `auth.User` (SET_NULL). سجلٌّ إلحاقي: لا تحديث ولا حذف عبر الـAPI |
| `ServiceOrder` | `order_number`، `order_date`، `serial`، `complaint`/`diagnosis`/`resolution`، `status`، `outcome` (حقل منفصل)، `warranty_covered`، `estimated_amount`، `covered_posted_at`، `billing_waived_reason`، `photos` | `tenant`، `partner`، `product`، `technician`، `warranty_card`، `sales_invoice` (كلها SET_NULL) |
| `ServiceOrderPart` | `quantity`، `billing ∈ {billable, covered}`، `unit_price`، **`serials`** (JSON، على نمط `SalesInvoiceLine.serials`، #223)، **`issued_cost`** (كلفة FIFO الفعلية لحركة `SERVICE_ISSUE`، تُفرَّغ عند التراجع)، **`materialized_at`** | `order` (CASCADE)، `product` (PROTECT)، `sales_invoice_line` (SET_NULL) |
| `ServiceOrderEvent` | `event_type`، `from_status`/`to_status`، `text`، `created_at` | `order` (CASCADE)، `actor` |
| `AfterSalesSettings` | مثبِّت الافتراضيات لكل شركة | `tenant` (OneToOne)، `warranty_expense_account` → `accounting.Account`، `default_labour_product` → `inventory.Product` |

## دوال الـservices العامة
```python
# after_sales/services.py — محرّك الكفالة (#222: خمس نقاط التحام من sales)
def create_auto_warranty_cards(invoice) -> int:  # ترحيل البيع: يُحيي المعلَّق على هذه الفاتورة ثم يُنشئ الناقص
def on_sale_unposted(invoice) -> int:  # إلغاء ترحيل البيع: تعليقٌ بـinvoice_unposted — لا حذف
def on_sale_cancelled(invoice) -> int:  # حذف مسودّة الفاتورة: المعلَّق يصير sale_cancelled بلا رجعة
def on_sales_return_posted(return_invoice) -> int:  # مرجع البيع: يُنهي بطاقات الوحدات المرتجعة وحدها بـreturned
def on_sales_return_unposted(return_invoice) -> int:  # إلغاء ترحيل المرجع: يُحيي ما أنهاه هو وحده
def warranty_coverage(tenant_id: int, serial: str, today=None) -> dict:  # التغطية من البطاقة غير المنتهية ومن نسب الوحدة
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
| `frontend_v2/components/aftersales/WarrantyCardsScreen.tsx` | قائمة بطاقات الكفالة والبحث والبطاقة اليدوية |
| `frontend_v2/components/aftersales/WarrantyCardModal.tsx` | بطاقة واحدة: إنشاء/تعديل/حذف/تمديد، ومنذ #229 سجل أحداثها (`GET .../events/`) بدل قراءة تاريخ التمديد من الملاحظات |
| `frontend_v2/components/aftersales/ServiceOrdersScreen.tsx` | قائمة أوامر الصيانة، وفتح المستند، وزر الاستقبال |
| `frontend_v2/components/aftersales/ServiceOrderDocument.tsx` | المستند: الملف · قطع الغيار (ترحيل/فوترة) · السجل الزمني — يملأ `sale_price` عند إضافة قطعة مفوترة وعند تحويل قطعة مغطاة إليها؛ عمود «الأرقام» في جدول القطع يفتح `SerialEntryModal` نفسه (`mode="pick"`، مصدره «في المخزن») لقطعةٍ مغطاة من منتجٍ مرقّم لم تتجسّد بعد — على البند الجديد وعلى القائم سواء، لا حقل نصّ عند الإضافة فقط؛ النمط `required` من إعدادات المبيعات (`serial_entry_mode`) نفس مصدر `SalesInvoiceEditor` (#223 مراجعة) |
| `frontend_v2/components/aftersales/ServiceOrderIntakeModal.tsx` | الاستقبال بالبحث الموحّد والتعبئة من نتائجه |
| `frontend_v2/utils/serviceOrder.ts` · `frontend_v2/utils/warranty.ts` | القواعد الصرفة (بلا React) — مرآة قواعد الخادم |
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
