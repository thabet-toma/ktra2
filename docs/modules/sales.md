# sales — دورة البيع الكاملة: عرض سعر ← طلبية ← فاتورة ← تسليم ← تحصيل، مع سندات صرف المورّدين

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
يملك هذا الـapp مستندات الجانب البيعي ودورة حياتها المالية: عروض الأسعار، طلبيات
الزبائن (وحجز كمياتها)، فواتير البيع بأنواعها الأربعة (`invoice_kind`: بيع/مرجع بيع/
شراء/مرجع شراء)، إرساليات التسليم، إشعارات الدائن/المدين، وكشف ض.ق.م. الترحيل هنا هو
نقطة الالتقاء بين ثلاث طبقات: قيد اليومية (`accounting`)، حركة المخزون والأرقام
التسلسلية (`inventory`)، وذمم الشريك (`partners`). كما يستضيف — لأسباب تاريخية —
سندات صرف المورّدين (`SupplierPayment`) التي يستهلكها `logistics`.

## أهم الملفات
| الملف | الغرض | أسطر |
|---|---|---|
| `sales/services/` | **حزمة (المرحلة 3)** — 7 وحدات لا-دورية (foundation/pricing/numbering/calc/flow/orders/supplier_vat)؛ `__init__` يعيد تصدير كل الأسماء فـ`from sales.services import X` يبقى شغّالاً | ~4087 (كان services.py) |
| `sales/views.py` | ViewSets وإجراءات post/unpost/deliver/allocate | 1588 |
| `sales/models.py` | 15 موديل: الإعدادات، الفاتورة وبنودها، الإرسالية، السندات، العروض والطلبيات | 1500 |
| `sales/serializers.py` | تحقّق الحمولة وكتابة البنود المتداخلة | 1454 |
| `sales/urls.py` | تسجيل 8 routers + 3 مسارات تقارير (مركّبة على `/api/sales/`، `core/urls.py`) | 43 |
| `sales/agent_api.py` | نقاط بوت الفواتير: مسوّدات البيع وقائمة الفواتير و«آخر سعر» (`/api/agent/...`، مسجَّلة في `core/urls.py`). تسكن هنا لا في `core` لأن `.importlinter` يمنع `core` من استيراد `sales.serializers`؛ حارسها `X-Agent-Key` وحده | 300 |

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `SalesSettings` | `default_payment_type`, `stock_on_post_default`, `allow_negative_stock_default`, `use_moving_average_cost`, `block_loss_invoices`, `block_reserved_stock_sale`, `auto_post_payments`, `serial_entry_mode` | `OneToOne` مع `Tenant`؛ ~10 FKs على `accounting.Account` كحسابات افتراضية |
| `SalesInvoice` | `invoice_number`, `invoice_kind`, `invoice_type`, `status` (draft/posted/cancelled), `delivery_status`, `stock_on_post`, `grand_total`, `amount_paid`، و`attached_cash_amount`/`attached_cash_account` = **نيّة دفع على المسودة** تُكتب من نقطة `payment-voucher/` وحدها ويكنسها الترحيل في سند قبض | `customer→Partner` (PROTECT)، `journal→accounting.JournalHeader`، `original_invoice→self`، `branch→tenants.Branch`، `vat_statement` |
| `SalesInvoiceLine` | `quantity`, `delivered_quantity`, `unit_price`, `line_discount`, `line_total_excl_tax`, `serials` (JSON), `internal_note`, `customer_note`, `name_snapshot` = لقطة اسم المنتج تُكتب عند **الترحيل** لا الإنشاء ويمسحها إلغاء الترحيل (فارغة = اتبع اسم المنتج الحي، مشتقّاً حياً بـ`inventory.services.product_display_name` — «اسم المنتج (البراند)» لا `str(product)`، #22)، خادميّةٌ لا تُكتب من العقد — **لا تخلطها** بـ`NameSnapshot` على `logistics.PurchaseInvoiceItem`/`LogisticsDealItem`: تلك تُكتب وقت الإدخال ويعدّلها المستخدم | `product→inventory.Product` (PROTECT)، `tax_rate→accounting.TaxRate` |
| `DeliveryOrder` / `DeliveryOrderLine` | `delivery_number`, `status`, `auto_created`, `quantity` | `invoice` قابل لـNULL (سند تسليم مستقل، `is_standalone` سطر 694)؛ `movement→inventory.StockMovement` |
| `CustomerPayment` / `PaymentAllocation` | `amount`, `is_posted`, `auto_settled_invoice` | توزيع على `SalesInvoice` بمبلغ + `conversion_rate` |
| `SupplierPayment` / `SupplierPaymentAllocation` | `amount`, `is_posted` | `purchase_invoice→logistics.PurchaseInvoice` |
| `SalesQuotation` / `SalesOrder` (+ بنودهما) | `status`, `valid_until`, `reserved_until`, `deposit_amount` | سلسلة النَسَب: `quotation→order→invoice` |
| `CreditDebitNote`, `VatStatement`, `CustomerProductQuote` | `note_type`, `net_vat`, `unit_price` | `related_invoice`, `journal`, تسعير خاص بالعميل |

## دوال الـservices العامة
```python
# التوقيعات فقط — منسوخة حرفياً من sales/services.py
def sales_revenue_map(*, tenant_id, invoice_ids) -> dict[tuple[int, int], dict]:  # مرآة sales_cogs_map على جانب الإيراد: {(فاتورة، منتج): {net, qty, tax}} — الصافي بلا تقريب
def allocate_invoice_discount(net, discount, subtotal) -> Decimal:  # نصيب مبلغٍ من خصم الفاتورة — قاعدة واحدة يستهلكها كل من يقول «الإيراد»
def post_sales_invoice(invoice: SalesInvoice, *, user=None) -> SalesInvoice:  # الترحيل: قيد + مخزون + تسلسلات + تسوية نقدية (سطر 1193)
def get_or_create_sales_settings(tenant) -> SalesSettings:  # إعدادات الشركة مع ملء الحسابات الناقصة (161)
def recalculate_invoice_amounts(invoice: SalesInvoice, lines: list[SalesInvoiceLine] | None = None) -> None:  # إعادة حساب الإجماليات (305)
def post_customer_payment(payment: CustomerPayment, *, user=None) -> CustomerPayment:  # ترحيل سند قبض (2223)
def unpost_customer_payment(payment: CustomerPayment, *, user=None) -> dict:  # التراجع عن سند قبض (1029)
def allocate_customer_payment(payment: CustomerPayment, allocations: list[dict], *, user=None) -> CustomerPayment:  # (2557)
def post_supplier_payment(payment: 'SupplierPayment', *, user=None) -> 'SupplierPayment':  # يستدعيه logistics (3808)
def unpost_supplier_payment(payment: 'SupplierPayment', *, user=None) -> dict:  # التراجع عن سند صرف — مرآة unpost_customer_payment؛ «المدفوع» على فواتير الشراء مشتق فلا مبالغ تُعكس
def allocate_supplier_payment(payment: 'SupplierPayment', allocations: list[dict], *, user=None) -> 'SupplierPayment':  # (3896)
def collect_invoice_payment(invoice: SalesInvoice, *, cash=None, cash_account_id=None, cheques=None, from_on_account=None, post_invoice=False, payment_date=None, user=None) -> CustomerPayment | None:  # منسّق التحصيل: ترحيل + سند قبض واحد + خصم من رصيد العميل، ذرّياً
def attach_voucher_and_post(invoice: SalesInvoice, *, cash_amount=0, cash_account_id=None, cheques=None, user=None) -> SalesInvoice:  # غلاف فوق المنسّق — شكل قديم محفوظ
def confirm_sales_order(order, *, user=None):  # تأكيد الطلبية = حجز بلا قيد (3336)
def convert_quotation_to_order(quotation, *, user=None):  # (3401)
def convert_order_to_invoice(order, *, user=None):  # (3454)
def convert_quotation_to_invoice(quotation, user=None):  # (3616)
def last_month_invoice_for_customer(tenant_id, customer_id, today=None):  # آخر فاتورة بيع للعميل ضمن الشهر الميلادي السابق — أساس «كرّر فاتورة الشهر الماضي» (ISSUE #53) (`sales/services/orders.py`)
def duplicate_invoice_for_today(source: SalesInvoice, *, user=None, today=None) -> SalesInvoice:  # نسخ فاتورة إلى مسودة بتاريخ اليوم ورقمٍ جديد من نفس الدفتر — نفس مسار `convert_quotation_to_invoice` (`sales/services/orders.py`)
def reserved_quantity_map(tenant_id: int, product_ids=None, *, exclude_customer_id: int | None = None) -> dict:  # يستهلكها inventory (3166)
def reserved_stock_rows(tenant_id: int, *, product_id=None, customer_id=None, date_from=None, date_to=None) -> list[dict]:  # (3185)
def guard_reserved_stock(invoice, lines, products_by_id) -> None:  # (3244)
def guard_invoice_payments_before_unpost(invoice: SalesInvoice, *, action_label: str = "إلغاء ترحيل") -> None:  # (959)
def last_sale_price(*, tenant_id: int, product_id: int, customer_id: int | None = None) -> dict:  # (2806)
def customer_price_list(*, tenant_id: int, customer_id: int) -> list[dict]:  # (2841)
def sales_cogs_map(*, tenant_id: int, invoice_ids) -> dict[tuple[int, int], dict]:  # يستهلكها core.reports (2685)
def invoice_profits(*, tenant_id: int, branch=None, date_from=None, date_to=None, customer_id=None) -> dict:  # (2725)
def dormant_customers(*, tenant_id: int, days: int | None = None) -> list[dict]:  # (226)
def build_vat_statement(tenant_id: int, period_from, period_to, *, user=None):  # الأرقام من accounting.services.vat_period_totals وحدها — الدفتر لا الفواتير (issue #79)
def vat_statement_diff_report(tenant_id: int) -> list[dict]:  # تقرير فرقٍ للقراءة فقط: محفوظ كل كشف مقابل ما يحسبه vat_period_totals الآن — بلا كتابة (issue #79)
def next_invoice_number(tenant_id: int, book_number: int = 0, branch=None) -> str:  # (3059)
def resolve_default_account(tenant_id, code_prefixes=None, acc_type=None, name_kw=None, *, allow_any_of_type=True):  # (91)
def resolve_product_revenue_account(tenant_id: int) -> Account:  # «4101» من الشجرة أو يُنشئه ويُثبِّته — نظير resolve_service_revenue_account (ISSUE #59) (`sales/services/calc.py`)
def resolve_cheques_payable_account(tenant_id: int) -> Account:  # يستهلكها accounting.services (731)
```

## أهم الـAPI endpoints
كلها تحت البادئة `/api/sales/` (`core/urls.py`).

| Method | المسار | الـview |
|---|---|---|
| GET/POST | `invoices/` | `SalesInvoiceViewSet` (`views.py`) |
| POST | `invoices/{id}/post/` | `SalesInvoiceViewSet.post_invoice` (473) |
| POST | `invoices/{id}/unpost/` | `SalesInvoiceViewSet.unpost_invoice` (328) |
| POST | `invoices/{id}/deliver/` · `invoices/{id}/delivery-order/` | `deliver` (681) · `create_delivery_order` (655) |
| GET | `invoices/{id}/delivery-lines/` · `invoices/lookup/` · `invoices/next-number/` | (666) · (189) · (640) |
| GET | `invoices/last-price/` · `invoices/resolve-price/` · `invoices/profits/` · `invoices/credit-preview/` | (577) · (594) · (623) · (551) |
| POST | `invoices/{id}/collect/` | `collect` — التحصيل من داخل الفاتورة (نقد/شيكات/رصيد العميل)، صلاحية `sales.payment.create` (+`sales.invoice.post` مع `post_invoice`) |
| GET | `invoices/{id}/returnable-lines/` | `SalesInvoiceViewSet.returnable_lines` — المفوتر · المرتجع سابقاً · المتبقّي القابل للإرجاع (يقبل `?exclude_invoice=`) |
| GET | `invoices/{id}/stock-movements/` | `SalesInvoiceViewSet.stock_movements` → `inventory/services.py` (`document_stock_movements`) — أثر **هذه الفاتورة** على المخزون، ومعه **سبب الفراغ** (مسودّة؟ أم `stock_on_post=False` تنتظر التسليم؟) |
| GET | `invoices/{id}/customer-ledger/` | `SalesInvoiceViewSet.customer_ledger` → `accounting/services.py` (`partner_account_statement`) بمرساة الفاتورة — الرصيد قبلها وبعدها وأثرها |
| GET/POST · DELETE | `invoices/{id}/attachments/` · `attachments/{attachment_id}/` | `SalesInvoiceViewSet.attachments` · `delete_attachment` — تُحفظ **فوراً** لا مع الفاتورة، فيبقى الإرفاق ممكناً بعد الترحيل |
| POST | `invoices/{id}/payment-voucher/` · `invoices/{id}/duplicate/` | (498) · (400) — الأولى غلاف قديم فوق `collect` |
| POST | `invoices/repeat-last-month/` | `SalesInvoiceViewSet.repeat_last_month` (`views.py`) — «كرّر فاتورة الشهر الماضي» (ISSUE #53، قرار 22): يكتشف المصدر من `customer_id` في الجسم بدل pk صريح، ثم نفس آلية `duplicate` |
| POST | `payments/{id}/post/` · `payments/{id}/unpost/` · `payments/{id}/allocate/` | `CustomerPaymentViewSet` (1099/1074/1117) |
| POST | `quotations/{id}/convert/` · `orders/{id}/confirm/` · `orders/{id}/convert/` · `orders/{id}/deposit/` | (1396) · (1505) · (1526) · (1539) |
| GET/PUT | `settings/current/` · POST `settings/restore-defaults/` | `SalesSettingsViewSet` (1169/1183) |
| GET | `reports/aging/` · `reports/dormant-customers/` · `reports/reserved-stock/` | `SalesReportViewSet` (`urls.py:32-42`) |

## الاعتماديات
**يعتمد على:**
- `accounting` — **models مباشرةً كـFKs**: `sales/models.py` يستورد `Account, JournalHeader, TaxRate` على مستوى الوحدة (لا lazy). و`services` أيضاً: `sales/services.py:14-23` (`post_journal`, `unpost_document`, `validate_fiscal_period`, `convert_amount`…).
- `inventory` — models + services: `sales/models.py:6-7` (`Product`, `SERIAL_MODE_CHOICES`)، و`sales/services/` (`record_stock_movement`، `consume_sales_serials`, `release_sales_serials`, `restore_returned_sales_serials`).
- `partners` (`sales/services.py:31-32`: `Partner`, `PartnerGroup`, `ensure_partner_linked_account`)، `tenants` (Tenant/Currency/Branch)، و`after_sales` عبر استيراد كسول داخل الترحيل (`views.py`, `services.py` عند `create_auto_warranty_cards`).

**يعتمد عليه:** `logistics` (`views.py` + `post_supplier_payment` / `allocate_supplier_payment`)، `accounting` (`services.py`, `serializers.py`, `views.py`)، `inventory` (`services.py:742,748` و`views.py` و`serials.py`)، `core` (`reports.py:420,1061,1234`, `payments.py`)، `accountant_portal` (`services.py`)، `after_sales`، `tenants`.

## قواعد لا يجوز كسرها
- **لا تعديل ولا حذف لفاتورة غير مسودة**: `views.py` و`:306` يرفضان بـ`POSTED_DOC_WARNING` مع `can_unpost: True`؛ ونفس المنع في `serializers.py`. **والمرفقات استثناءٌ مقصود**: نقاطها الثلاث (`attachments`) تكتب في `core.SystemAttachment` لا في الفاتورة، فيبقى إرفاق الإيصال ممكناً بعد الترحيل — وهو أكثر وقت يُحتاج فيه. ربطُها بمسار PATCH كان يعني ألّا يُرفق شيء بفاتورة نهائية أبداً.
- **«رصيد العميل قبل/بعد» لا يُشتقّ من «المتبقّي»**: `customer_balance_before_invoice`/`after` في `serializers.py` (`SalesInvoiceSerializer`) **تقريبٌ لا يطابق كشف الحساب** — يطرح المتبقّي من رصيد **اليوم**، فالفاتورة المدفوعة بالكامل تُظهر أثراً صفرياً وهي دائنةُ ذمم بكامل إجماليها (قيدها يدين الذمم كلَّها، والتحصيل قيدٌ منفصل). المصدر الصحيح هو `invoices/{id}/customer-ledger/` من `partner_account_statement` نفسه الذي يبني كشف الحساب — المطابقة **بالبناء** لا بالمصادفة. لا تعرض الحقلين القديمين على أنهما «قبل/بعد». **والمرآة في جانب المورّد أُصلحت** (T-PCTX): `GET /api/logistics/purchase-invoices/{id}/supplier-ledger/` هي نظيرتها، و`document_partner_balance_summary` (`core/payments.py`) يبقى تقريباً موثَّقاً على الجانبين لعقد الـAPI وحده — لا يُعرض على أنه «قبل/بعد» في أيٍّ منهما.
- **قيد الفاتورة لا يُسوّي شيئاً ولا يزيد «المدفوع»**: `post_sales_invoice` (`sales/services/flow.py`) يدين الذمم بكامل الإجمالي ويدائن الإيراد/الضريبة فقط — لا سطر صندوق ولا سطر «شيكات برسم التحصيل» داخله، ولا لمسَ لـ`amount_paid`. ما وصل مرفقاً مع الفاتورة (شيكات، ونيّة النقد المحفوظة على المسودة، ونقد البيع النقدي) يُحصَّل داخل نفس المعاملة بسند قبض حقيقي: `_settle_attached_cheques` ثم `_auto_settle_cash_sale`، وكلاهما يمرّ من `post_customer_payment`. وحين يأتي التحصيل مفصَّلاً من `collect_invoice_payment` تُكبَت التسويتان معاً (`suppress_auto_settlement=True`) فيحلّ محلّهما سندٌ واحد — وإلّا خطفت التلقائيةُ كاملَ المتبقّي فخرج سندان. **والبيع النقدي بلا صندوق يُرفض ولا يُتخطّى** (T-PAYFULL): كان `_auto_settle_cash_sale` يكتفي بتحذيرٍ في اللوج حين يعجز `_resolve_settlement_cash_account_id`، فتُرحَّل فاتورةٌ «نقدية» بلا تسوية ويبقى العميل مديناً بكاملها — مطالبةٌ وهمية في كشف حسابه وفي أعمار الذمم، والشاشة تقول «تم الترحيل». صار يرفع `ValidationError` بجملةٍ إرشادية («اختر حساب الصندوق/البنك أو اجعلها فاتورة ذمم») مطابِقاً لما يفعله جانب الشراء منذ T-APPAID. يبقى التخطّي الصامت لحالةٍ واحدة مشروعة: قيدٌ قديم لا يَدين ذمماً أصلاً (`invoice_journal_debits_ar`) — سندٌ هناك يُدائن ذمّةً لم تُمدَّن.
- **تبويبات السياق مكوّنٌ واحد للجانبين**: انتقل
  `components/sales/InvoiceContextTabs.tsx` إلى
  `components/shared/DocumentContextTabs.tsx` وصار يخدم فاتورتَي البيع والشراء —
  الفارق بينهما شيئان فقط: من أين تُجلب البيانات (`api`) وبأيّ مفردات تُسمّى
  (`side`). ما عداهما مشترك، والكسلُ (لا جلبَ قبل فتح التبويب) شرطٌ فيهما معاً.
- **لوحة الدفع مكوّنٌ واحد للجانبين**: `frontend_v2/components/shared/DocumentPaymentPanel.tsx`
  — يخدم محرّر فاتورة البيع (`side="customer"`) ومحرّر فاتورة الشراء
  (`side="supplier"`)، وكلّ ما يُعرض مشتقٌّ من `deriveDocumentPayment` وحدها.
  نسختان من هذه الحسبة تعني «متبقّياً» يختلف بين شاشتين. الاختلاف بين الجانبين
  مفرداتٌ فقط (رصيد العميل ÷ سلفة المورّد)، والزرّ اسمُه **«تسجيل دفعة»** على
  الاثنين كما تفعل Odoo بـ*Register Payment*.
- **التحصيل من داخل الفاتورة نقطة واحدة**: `collect_invoice_payment` (`sales/services/flow.py`) — تركيبُ خدمات قائمة بلا أي منطق ترحيل جديد: `post_sales_invoice` ← `post_customer_payment` (نقد + شيكات في سند واحد، توزيعٌ مقصوص على المتبقّي وما زاد «على الحساب») ← `allocate_customer_payment` لكل خصمٍ من رصيد العميل (ربطٌ بلا قيد جديد). كلّه في `transaction.atomic` واحد: لا فاتورةٌ مرحّلة بسندٍ نصف مولود. `attach_payment_voucher` يقبل النقد على **المسودة** نيّةَ دفعٍ لا تحصيلاً (T-INTENT): لا قيد ولا سند ولا `amount_paid` ولا أثر على رصيد العميل، ويكنسها الترحيل في السند نفسه. و`attach_voucher_and_post` غلافٌ فوق المنسّق.
- **الفاتورة النقدية لا تبقى ناقصة التحصيل**: نقدٌ غير مذكور يُكمَّل تلقائياً في نفس السند، ونقصٌ بعد نقدٍ **مذكور** يَرفض العمليةَ كلَّها («اجعلها فاتورة ذمم أو أكمل المبلغ») — `collect_invoice_payment`.
- **نيّة الدفع على المسودة (T-INTENT)**: المسودة تحمل دفعةً مسجَّلة — نقدٌ في `attached_cash_amount` وشيكاتٌ `Draft` مربوطة بها — **بلا أثرٍ في الدفاتر إطلاقاً**: لا قيد، لا سند، لا `amount_paid`، ولا رصيد طرف. تُكتب بدلالة الاستبدال من `attach_payment_voucher` (نقطة `payment-voucher/`) والنيّة لا تتجاوز إجمالي الفاتورة (الفائض على الحساب يبقى من اختصاص `collect/`). عند الترحيل يكنسها `_settle_attached_cheques` في **سند قبض واحد** مقصوصاً على المتبقّي الفعلي (`min(intent, remaining)`) فلا تُدفع مرّتين بعد إلغاء ترحيلٍ وتحصيلٍ يدوي. `attached_cash_amount` **لا يُمسح** عند الترحيل: هو سجلّ النيّة الدائم، والتجسّد هو السند (`auto_settled_invoice`) الذي يُحرَّر مع إلغاء الترحيل وتعود شيكاته `Draft` — فتُعاد حالة المسودة كما كانت بلا كود إضافي. يكشفها المُسلسِل في `pending_payment_total` (تفصيلاً وقائمةً) خارج «المدفوع» وخارج `payment_status`.
- **`amount_paid` = مجموع توزيعات السندات المرحّلة**: كل زيادة عليه تأتي من `post_customer_payment` مقرونةً بصفّ `PaymentAllocation`، ويُثبته `posted_allocations_total` (`sales/services/flow.py`). الحقل مخزنٌ مُشتقّ عمداً — تقرأه التقارير وكشف الحساب والأعمار بجمع SQL — فثمنُه أن يُبرهَن لا أن يُفترض: `python manage.py audit_ar_integrity` (`sales/management/commands/audit_ar_integrity.py`) يمسح كل فاتورة مرحّلة عليها «مدفوع» أو توزيع، ويصنّف كل فرق إلى **قديم** (قيد الفاتورة نفسه يحمل التسوية — دائنُ ذمم داخله بدلالة `invoice_journal_settlement_credit`، أو نقديّةُ ما قبل الميزة 2 بقيدٍ بلا مدين ذمم: متوازنٌ وصحيح، يُبلَّغ ولا يُصلَح أبداً) أو **يتيم** (لا توزيع ولا تسوية داخل القيد — وحده ما يُعيده `--fix`/`--apply` إلى مجموع التوزيعات). الأمر عرضٌ فقط افتراضياً ولا يلمس قيداً إطلاقاً؛ والمنتج القديم يحرسه الحارسان معاً (المتبقي على `amount_paid` + `guard_invoice_allocation_total`) فلا يُحصَّل مرّتين.
- **لا إلغاء ترحيل (ولا حذف) لفاتورة عليها سند قبض مرحّل**: `guard_invoice_payments_before_unpost` (`services.py`) يُستدعى من `views.py` و`:314`. الاستثناء الوحيد هو السند الذي أنتجه الترحيل نفسه (الموسوم بـ`auto_settled_invoice`: التسوية النقدية التلقائية أو تحصيل الشيكات المرفقة) ويُحرَّر أولاً بـ`release_auto_cash_settlement` (`services.py`).
- **إلغاء الترحيل ذرّي وكامل**: داخل `transaction.atomic` واحد يُحرَّر السند التلقائي، تُعاد التسلسلات (`release_sales_serials`)، تُحذف بطاقات الكفالة التلقائية، ثم `unpost_document(journal_reference_types=["SALES_INVOICE","SALES_DELIVERY_COGS"], stock_reference_types=["SALE","STOCK_ISSUE"])`، وتُصفَّر `amount_paid` و`delivered_quantity` وتُحذف الإرساليات وتعود الشيكات `Under_Collection → Draft` (`views.py:340-379`).
- **الإيراد رقمٌ واحد في المنصة**: صافي (فاتورة، منتج) يُقرأ من `sales/services/pricing.py` (`sales_revenue_map`) وحدها — مرآةُ `sales_cogs_map` على الجانب الآخر. توزيع خصم الفاتورة قاعدةٌ مستخرَجة (`allocate_invoice_discount`) لأنها **خطّية** في الصافي، فيستوي تطبيقها على سطرٍ أو على مجموع أسطر نفس المنتج. يستهلكها «المبيعات حسب المنتج/الماركة» و«حركة المخزون حسب بُعد» — ونسخةٌ ثالثة تعني رقمَي إيرادٍ متنافسين، وهو ما تحرسه `core/tests/test_reports_stock_dimension.py`.
- **ملاحظتا البند حقلان لا حقل**: `internal_note` لا تخرج من قاعدة البيانات إلى أي مسار طباعة، و`customer_note` وحدها تُرسَم تحت اسم المنتج في `frontend_v2/components/sales/SalesInvoicePrintView.tsx`. الفصل بنيوي لا اتفاقي: حقلٌ واحد يعني أن ما كتبه البائع لنفسه سيُطبع للعميل يوماً، وخطأٌ في هذا الاتجاه لا يُستدرَك بعد التسليم. لا تدمجهما ولا تعرض الداخلية في أي مكوّن يُطبع.
- **«إجباري» في الأرقام التسلسلية يُرفض قبل الكتابة لا بعدها**: `post_sales_invoice` (`sales/services/flow.py`) يستدعي `inventory.serials.assert_sales_serials_declared` قبل `recalculate_invoice_amounts` — أي قبل القيد والمخزون والإرسالية. رفضٌ متأخّر داخل المعاملة الذرّية يُلغي كل ذلك بصمت ويعيد المستخدم لشاشة لا تقول ما ينقص. والبيع وحده معنيّ: المرجع يعيد وحدات فاتورته الأصلية بالترتيب ولا اختيار فيه.
- **مجموع التوزيعات المرحّلة لا يتجاوز إجمالي الفاتورة**: `guard_invoice_allocation_total` (`services.py`) يُستدعى دائماً داخل معاملة بعد `select_for_update` على الفاتورة.
- **خصم المخزون idempotent**: `_post_stock_out_for_invoice` (`services.py`) يعود مبكراً إن وُجدت حركة `reference_type="SALE"` لنفس الفاتورة؛ ومثله `issue_stock_from_invoice` لـ`STOCK_ISSUE`.
- **`delivery_status` مشتقّ لا يُحرَّر يدوياً**: `sync_invoice_delivery_status` (`services.py`) هو المصدر الوحيد، وبنود الخدمات تُستثنى.
- **الكمية المحجوزة لطلبية زبون آخر ليست متاحة**: `guard_reserved_stock` (`services.py`) بعد قفل المنتجات، ومفتاحه `block_reserved_stock_sale`.
- **رقم الفاتورة فريد داخل الشركة**: `UniqueConstraint(["tenant","invoice_number"])` (`models.py`).
- **حقل العميل في محرّر الفاتورة يُكتب فيه ويُنشئ**: `KitAutocomplete` لا حقلاً للقراءة، وسطرُ «إضافة «ما كُتب» كعميل جديد» يفتح `CustomerQuickAddModal` بالاسم معبّأً (الاسم وحده إلزامي؛ النوع محسوم `Customer`)، وفهرس الحسابات يبقى خلف زرّ «…» بسلوكه كما كان. وقبل الحفظ تسأل النافذةُ `partners/lookup/?search=` عن أطراف باسم قريب — **بأطول كلمة في الاسم** لا بالاسم كاملاً، لأن `name__icontains` يطابق احتواءً فيفوّت من يكتب اسماً أطول من المسجَّل، وهو الاتجاه الأخطر. **تحذيرٌ لا منع** (اسمان متطابقان لطرفين مختلفين واقعٌ)، والمطابق من غير نوع `Customer` يُعرض ولا يُختار — لا مكان له في قائمة عملاء الفاتورة. تفاصيل عودة المعرَّف إلى الحقل في `docs/modules/frontend.md` (القاعدة 13).
- **مرجعٌ مربوطٌ بأصلٍ يُقيَّد على مشتري الأصل**: `SalesInvoiceSerializer` (`_enforce_return_party`) يرفض عميلاً يخالف `original_invoice.customer` (إنشاءً وتعديلاً)، ويشتقّ العميل من الأصل حين يُغفَل — **قبل** أن يتدخّل «العميل الافتراضي» في الإعدادات. سببه أن شاشة «مرجع البيع» كانت تُعبّئ العميل تلقائياً وتتركه قابلاً للتغيير بلا أي حارس خادمي: مرجع فاتورة زيدٍ على ذمم عمرو يمرّ ويُرحَّل، فيَنقص دينُ من لم يُرجِع شيئاً. الحارس على النوعين (`sale_return` و`purchase_return`)، ولا يمسّ مرجعاً بلا فاتورة أصلية. والشاشة صارت تعرض العميل مشتقّاً للقراءة فقط (`SalesReturnEditor.tsx`) — فسقطت معه قائمةُ عملاءٍ بـ500 صفّ من إقلاع الشاشة.
- **الاستحقاق و«متأخرة» قاعدةٌ واحدة مع الشراء**: `payment_terms_days` أُضيف
  إلى `SalesInvoice` (كان `due_date` وحده)، ويشتقّ التاريخَ عبر
  `core/payments.py` (`resolve_due_date`). و«متأخرة» بُعدٌ فوق `payment_status`
  لا قيمةٌ فيه (`document_overdue_state`): شارةٌ ثانية بجانب الحالة، وخيار فلترة
  `?payment_status=overdue`. الحقلان `is_overdue`/`days_overdue` مُعرَّفان في
  الـmixin المشترك بين سيريالايزر القائمة والتفصيل، فالرقم واحدٌ في الشاشتين.
- **مرجعٌ لا يتجاوز الكمية القابلة للإرجاع**: `sales/services/flow.py`
  (`guard_sales_return_quantities` فوق `returnable_lines_for_invoice`) يُستدعى من
  `SalesInvoiceSerializer` (`_enforce_return_quantities`) إنشاءً وتعديلاً. كان
  `_enforce_return_party` يحرس **الطرف** ولا يحرس **الكمية**: مرجعُ فاتورةٍ بها 10
  يقبل 100، فتُدائن ذمم العميل بما لم يُبَع وتدخل المخزنَ كميةٌ لم تخرج. القياس
  **بالمنتج** لا بالسطر (منتجٌ تكرّر في سطرين يُرجَع مجموعه، وإلا فتح التكرارُ باباً
  للتجاوز بالتوزيع)، ومرجعٌ يُعدَّل يستثني كمياته هو (`exclude_invoice_id`) وإلا
  منَع نفسه. المرآة على جانب الشراء أقدم (`create_purchase_return`). ونقطة
  `invoices/{id}/returnable-lines/` تعرض على الشاشة **نفس** الأرقام التي يقيس بها
  الحارس، فلا يرى المستخدم رقماً ويُرفض بآخر.
- **خصم عرض السعر يسبق الضريبة ويعبر إلى فاتورته**: `SalesQuotationSerializer._apply_totals`
  (`sales/serializers.py`) يوزّع `discount_amount` على البنود بـ`allocate_invoice_discount`
  ثم يحسب الضريبة على الصافي المخصوم — نفس ترتيب `recalculate_invoice_amounts`. كان
  يطرحه **بعد** الضريبة (`subtotal + tax − discount`) فتُحسب ض.ق.م على أساسٍ لم
  يُدفع، وكان `convert_quotation_to_invoice` (`sales/services/orders.py`) يُسقط الخصم
  كلَّه — فيُفوتَر الزبون بأكثر ممّا عُرِض عليه وقَبِله (التحويل إلى **طلبية** كان
  يحمله منذ البداية). خصمٌ سالبٌ يُرفض، وخصمٌ يتجاوز مجموع البنود يُقصّ كما في
  الفاتورة. الواجهة تحسب بنفس الوحدة المشتركة (`utils/salesInvoiceMath.ts`)، فلا
  ينحرف رقم الشاشة عن رقم الخادم. **وشقيقه `SalesOrderSerializer` ما زال على
  القاعدة القديمة** (الخصم بعد الضريبة) — شاشة الطلبيات بلا حقل خصم اليوم.
- **العميل والمنتج يجب أن يتبعا نفس الـtenant** — يُفحص عند الترحيل (`services.py` للعميل، `:1597` للمنتج).
- **تجاوز حساب المنتج (`Product.sale_account_override`) يسري على الخدمة أيضاً (ISSUE #78)**: `_resolve_revenue_account_for_line` (`sales/services/calc.py`) كانت تحرس هذا التجاوز بـ`not is_service` — فأي بندٍ خدميّ يسقط حتماً إلى `_default_revenue_account(is_service=True)` (حساب الخدمات العام) ولو حمل المنتج حساب أتعابٍ خاص، وهو ما جعل `4103`-`4106` المزروعة مع قالب «مكتب محاسبة» حسابات ميتة. الآن: خدمةٌ بتجاوزٍ مضبوط تُرحَّل عليه مباشرةً (بلا استدعاء `inventory.services._resolve_line_account` كاملةً — سلسلتها الداخلية منتجيّة الطابع وتُسقط الخدمة إلى حساب البضاعة بدل العام)، وخدمةٌ بلا تجاوز تسقط إلى الحساب العام كما كانت. **تجاوزا الفاتورة والتصنيف يبقيان محروسَين بـ`not is_service` كما هما** — لا توسّع في الأثر خارج تجاوز المنتج نفسه.
- **حسابا إيراد المنتج والخدمة لا يُثبَّتان على رأس الشجرة أبداً**: `default_revenue_account_product`/`_service` (`SalesSettings`) يُتركان فارغين عند إنشاء الشركة (`get_or_create_sales_settings`) — `resolve_product_revenue_account`/`resolve_service_revenue_account` (`sales/services/calc.py`) وحدهما يملآنهما: تحلّان `4101`/`4102` من الشجرة أو تُنشئانهما وتُثبّتانهما. العيب (ISSUE #59، وقبله #53 على جانب الخدمة): أوّل حساب إيراد **بالكود** هو رأس الشجرة «4» (`'4' < '41' < '4101'`)، حسابٌ أب لا يصلح هدفاً للترحيل. `python manage.py fix_product_revenue_account_default` يُصلح صفوف `SalesSettings` القائمة **حيث كان المُثبَّت حساباً أباً فقط** (idempotent، `--dry-run`) — بلا مساس بحسابٍ أو قيدٍ مُرحَّل.

- **كشف ض.ق.م (issue #79)**: `build_vat_statement` (`sales/services/supplier_vat.py`) ما عاد يقرأ `tax_amount` على `SalesInvoice` — يستدعي `accounting.services.vat_period_totals` (الدفتر) وحدها، نفس الدالّة التي تستدعيها `VatReportView` (`accounting`) و`client_financial_summary` (`accountant_portal`)، فيتّفق الثلاثة دائماً. **فرادة (شركة، من، إلى) هي حارس الاحتساب المزدوج الآن** — سقط `vat_statement__isnull=True` كآلية اختيار (الحقل `SalesInvoice.vat_statement` يبقى للتاريخ/التتبّع لا للاحتساب). فكّ ترحيل مستندٍ مؤرَّخ داخل فترة كشف `VatStatement.status='final'` مرفوض من `accounting.services.unpost_document` — لا أثر رجعي على كشفٍ نهائي.

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `sales/tests/test_ar_integrity.py` | سلامة الذمم: منع ازدواج التحصيل وبقاء السندات معلّقة بعد إلغاء الترحيل، وتصنيف فرق «المدفوع» (قديمٌ لا يُمسّ ÷ يتيمٌ يُصلَح) |
| `sales/tests/test_sales_post_unpost_stock.py` | تماثل post → unpost → repost للمخزون والقيد معاً |
| `sales/tests/test_reserved_stock_guard.py` | حجز الطلبية يمنع بيع الكمية لزبون آخر (4 قواعد) |
| `sales/tests/test_invoice_delivery.py` | حالة التسليم والتسليم الجزئي ببنوده |
| `sales/tests/test_sales_orders.py` | الطلبية ليست قيداً، الحجز مشتقّ، الإلغاء لا يحذف، العربون سند حقيقي |
| `sales/tests/test_quotation_discount.py` | خصم العرض قبل الضريبة، تطابقه مع حساب الفاتورة، وعبوره عند التحويل |
| `sales/tests/test_subledger_routing.py` | قيد الفاتورة يدين الذمم بالكامل ولا يُسوّي النقدية |
| `sales/tests/test_block_loss_invoice.py` | رفض فاتورة فيها أي سطر بخسارة عند تفعيل المفتاح |
| `sales/tests/test_payment_cheques.py` · `test_voucher_atomicity.py` | الشيكات المرفقة وذرّية السند |
| `sales/tests/test_invoice_journal_purity.py` | قيد الفاتورة نقيّ من التسوية، و«المدفوع» لا يزيد بلا توزيع |
| `sales/tests/test_invoice_collect.py` | التحصيل من داخل الفاتورة: 60 نقداً + 40 شيكاً ⇒ سند واحد وذمم صفر، الفائض على الحساب، كبت التسوية التلقائية، والتراجع الكامل عند الفشل |
| `sales/tests/test_sale_return_quantity_guard.py` | المرجع لا يتجاوز القابل للإرجاع (تراكمياً)، ومنتجٌ خارج الفاتورة مرفوض، والتعديل لا يمنع نفسه |
| `sales/tests/test_invoice_context_tabs.py` | تبويبات سياق الفاتورة: حركاتها المخزنية وحدها وسببُ فراغها، ومطابقة «قبل/بعد» لكشف الحساب سطراً بسطر (وأن أثر المدفوعة بالكامل = إجماليها لا صفر)، ونافذةٌ ترسو على فاتورة قديمة، والمرفق يُضاف لفاتورة مرحّلة ويُحذف بنطاق فاتورته |
| `sales/tests/test_product_revenue_head_fix.py` | ISSUE #59: شركة بكر تُرحّل بضاعتها على `4101` لا رأس الشجرة، `resolve_product_revenue_account` تُثبِّت وتُعيد الاستعمال، وأمر `fix_product_revenue_account_default` يُصلح الصفّ الخاطئ (حساب أب) وحده، idempotent، و`--dry-run` لا يكتب |
| `sales/tests/test_office_service_fee_accounts.py` | ISSUE #78: قالب `accounting_firm` يزرع خمس خدمات مربوطة بحساباتها؛ بند «مسك دفاتر شهري» يُرحَّل على `4103` لا `4102`؛ خدمةٌ بلا حساب خاص تسقط إلى `4102` كالسابق؛ منتجٌ غير خدميّ (بتجاوزٍ أو بدونه) بلا تغيير — اختبار تراجعٍ صريح؛ و`general` صفر خدماتٍ مزروعة |
| `sales/tests/test_vat_statement_returns.py` | مراجيع البيع/الشراء تُخصم لا تُضاف في `build_vat_statement` — الفواتير هنا مرفقة بقيود حقيقية على حسابي الضريبة المشتقّين (issue #79) |
| `accounting/tests/test_vat_single_source.py` | issue #79 كاملةً: اتفاق العارضين الثلاثة، حارس فكّ الترحيل داخل فترة كشف `final`، غياب الأثر الرجعي، وتقرير الفرق للقراءة فقط |
