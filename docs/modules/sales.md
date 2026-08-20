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
| `SalesInvoice` | `invoice_number`, `invoice_kind`, `invoice_type`, `status` (draft/posted/cancelled), `delivery_status`, `stock_on_post`, `grand_total`, `amount_paid`، و`attached_cash_amount` **عمود قديم للقراءة فقط** (لم يعد يُكتب ولا يُرحَّل — التحصيل صار سنداً حقيقياً) | `customer→Partner` (PROTECT)، `journal→accounting.JournalHeader`، `original_invoice→self`، `branch→tenants.Branch`، `vat_statement` |
| `SalesInvoiceLine` | `quantity`, `delivered_quantity`, `unit_price`, `line_discount`, `line_total_excl_tax`, `serials` (JSON) | `product→inventory.Product` (PROTECT)، `tax_rate→accounting.TaxRate` |
| `DeliveryOrder` / `DeliveryOrderLine` | `delivery_number`, `status`, `auto_created`, `quantity` | `invoice` قابل لـNULL (سند تسليم مستقل، `is_standalone` سطر 694)؛ `movement→inventory.StockMovement` |
| `CustomerPayment` / `PaymentAllocation` | `amount`, `is_posted`, `auto_settled_invoice` | توزيع على `SalesInvoice` بمبلغ + `conversion_rate` |
| `SupplierPayment` / `SupplierPaymentAllocation` | `amount`, `is_posted` | `purchase_invoice→logistics.PurchaseInvoice` |
| `SalesQuotation` / `SalesOrder` (+ بنودهما) | `status`, `valid_until`, `reserved_until`, `deposit_amount` | سلسلة النَسَب: `quotation→order→invoice` |
| `CreditDebitNote`, `VatStatement`, `CustomerProductQuote` | `note_type`, `net_vat`, `unit_price` | `related_invoice`, `journal`, تسعير خاص بالعميل |

## دوال الـservices العامة
```python
# التوقيعات فقط — منسوخة حرفياً من sales/services.py
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
def reserved_quantity_map(tenant_id: int, product_ids=None, *, exclude_customer_id: int | None = None) -> dict:  # يستهلكها inventory (3166)
def reserved_stock_rows(tenant_id: int, *, product_id=None, customer_id=None, date_from=None, date_to=None) -> list[dict]:  # (3185)
def guard_reserved_stock(invoice, lines, products_by_id) -> None:  # (3244)
def guard_invoice_payments_before_unpost(invoice: SalesInvoice, *, action_label: str = "إلغاء ترحيل") -> None:  # (959)
def last_sale_price(*, tenant_id: int, product_id: int, customer_id: int | None = None) -> dict:  # (2806)
def customer_price_list(*, tenant_id: int, customer_id: int) -> list[dict]:  # (2841)
def sales_cogs_map(*, tenant_id: int, invoice_ids) -> dict[tuple[int, int], dict]:  # يستهلكها core.reports (2685)
def invoice_profits(*, tenant_id: int, branch=None, date_from=None, date_to=None, customer_id=None) -> dict:  # (2725)
def dormant_customers(*, tenant_id: int, days: int | None = None) -> list[dict]:  # (226)
def build_vat_statement(tenant_id: int, period_from, period_to, *, user=None):  # (4000)
def next_invoice_number(tenant_id: int, book_number: int = 0, branch=None) -> str:  # (3059)
def resolve_default_account(tenant_id, code_prefixes=None, acc_type=None, name_kw=None, *, allow_any_of_type=True):  # (91)
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
| GET | `invoices/{id}/stock-movements/` | `SalesInvoiceViewSet.stock_movements` → `inventory/services.py` (`document_stock_movements`) — أثر **هذه الفاتورة** على المخزون، ومعه **سبب الفراغ** (مسودّة؟ أم `stock_on_post=False` تنتظر التسليم؟) |
| GET | `invoices/{id}/customer-ledger/` | `SalesInvoiceViewSet.customer_ledger` → `accounting/services.py` (`partner_account_statement`) بمرساة الفاتورة — الرصيد قبلها وبعدها وأثرها |
| GET/POST · DELETE | `invoices/{id}/attachments/` · `attachments/{attachment_id}/` | `SalesInvoiceViewSet.attachments` · `delete_attachment` — تُحفظ **فوراً** لا مع الفاتورة، فيبقى الإرفاق ممكناً بعد الترحيل |
| POST | `invoices/{id}/payment-voucher/` · `invoices/{id}/duplicate/` | (498) · (400) — الأولى غلاف قديم فوق `collect` |
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
- **«رصيد العميل قبل/بعد» لا يُشتقّ من «المتبقّي»**: `customer_balance_before_invoice`/`after` في `serializers.py` (`SalesInvoiceSerializer`) **تقريبٌ لا يطابق كشف الحساب** — يطرح المتبقّي من رصيد **اليوم**، فالفاتورة المدفوعة بالكامل تُظهر أثراً صفرياً وهي دائنةُ ذمم بكامل إجماليها (قيدها يدين الذمم كلَّها، والتحصيل قيدٌ منفصل). المصدر الصحيح هو `invoices/{id}/customer-ledger/` من `partner_account_statement` نفسه الذي يبني كشف الحساب — المطابقة **بالبناء** لا بالمصادفة. لا تعرض الحقلين القديمين على أنهما «قبل/بعد». **والمرآة في جانب المورّد لم تُصلَح** (`core/payments.py` — `document_partner_balance_summary` يخدم الطرفين): دينٌ معروف موثَّق، خارج نطاق THA-132.
- **قيد الفاتورة لا يُسوّي شيئاً ولا يزيد «المدفوع»**: `post_sales_invoice` (`sales/services/flow.py`) يدين الذمم بكامل الإجمالي ويدائن الإيراد/الضريبة فقط — لا سطر صندوق ولا سطر «شيكات برسم التحصيل» داخله، ولا لمسَ لـ`amount_paid`. ما وصل مرفقاً مع الفاتورة (شيكات، ونقد البيع النقدي) يُحصَّل داخل نفس المعاملة بسند قبض حقيقي: `_settle_attached_cheques` ثم `_auto_settle_cash_sale`، وكلاهما يمرّ من `post_customer_payment`. وحين يأتي التحصيل مفصَّلاً من `collect_invoice_payment` تُكبَت التسويتان معاً (`suppress_auto_settlement=True`) فيحلّ محلّهما سندٌ واحد — وإلّا خطفت التلقائيةُ كاملَ المتبقّي فخرج سندان.
- **التحصيل من داخل الفاتورة نقطة واحدة**: `collect_invoice_payment` (`sales/services/flow.py`) — تركيبُ خدمات قائمة بلا أي منطق ترحيل جديد: `post_sales_invoice` ← `post_customer_payment` (نقد + شيكات في سند واحد، توزيعٌ مقصوص على المتبقّي وما زاد «على الحساب») ← `allocate_customer_payment` لكل خصمٍ من رصيد العميل (ربطٌ بلا قيد جديد). كلّه في `transaction.atomic` واحد: لا فاتورةٌ مرحّلة بسندٍ نصف مولود. `attach_payment_voucher` لم يعد يقبل نقداً (كان يُسجَّل ولا يُرحَّل)، و`attach_voucher_and_post` والنقطة `payment-voucher` غلافان فوق المنسّق.
- **الفاتورة النقدية لا تبقى ناقصة التحصيل**: نقدٌ غير مذكور يُكمَّل تلقائياً في نفس السند، ونقصٌ بعد نقدٍ **مذكور** يَرفض العمليةَ كلَّها («اجعلها فاتورة ذمم أو أكمل المبلغ») — `collect_invoice_payment`.
- **`amount_paid` = مجموع توزيعات السندات المرحّلة**: كل زيادة عليه تأتي من `post_customer_payment` مقرونةً بصفّ `PaymentAllocation`، ويُثبته `posted_allocations_total` (`sales/services/flow.py`). الحقل مخزنٌ مُشتقّ عمداً — تقرأه التقارير وكشف الحساب والأعمار بجمع SQL — فثمنُه أن يُبرهَن لا أن يُفترض: `python manage.py audit_ar_integrity` (`sales/management/commands/audit_ar_integrity.py`) يمسح كل فاتورة مرحّلة عليها «مدفوع» أو توزيع، ويصنّف كل فرق إلى **قديم** (قيد الفاتورة نفسه يحمل التسوية — دائنُ ذمم داخله بدلالة `invoice_journal_settlement_credit`، أو نقديّةُ ما قبل الميزة 2 بقيدٍ بلا مدين ذمم: متوازنٌ وصحيح، يُبلَّغ ولا يُصلَح أبداً) أو **يتيم** (لا توزيع ولا تسوية داخل القيد — وحده ما يُعيده `--fix`/`--apply` إلى مجموع التوزيعات). الأمر عرضٌ فقط افتراضياً ولا يلمس قيداً إطلاقاً؛ والصنف القديم يحرسه الحارسان معاً (المتبقي على `amount_paid` + `guard_invoice_allocation_total`) فلا يُحصَّل مرّتين.
- **لا إلغاء ترحيل (ولا حذف) لفاتورة عليها سند قبض مرحّل**: `guard_invoice_payments_before_unpost` (`services.py`) يُستدعى من `views.py` و`:314`. الاستثناء الوحيد هو السند الذي أنتجه الترحيل نفسه (الموسوم بـ`auto_settled_invoice`: التسوية النقدية التلقائية أو تحصيل الشيكات المرفقة) ويُحرَّر أولاً بـ`release_auto_cash_settlement` (`services.py`).
- **إلغاء الترحيل ذرّي وكامل**: داخل `transaction.atomic` واحد يُحرَّر السند التلقائي، تُعاد التسلسلات (`release_sales_serials`)، تُحذف بطاقات الكفالة التلقائية، ثم `unpost_document(journal_reference_types=["SALES_INVOICE","SALES_DELIVERY_COGS"], stock_reference_types=["SALE","STOCK_ISSUE"])`، وتُصفَّر `amount_paid` و`delivered_quantity` وتُحذف الإرساليات وتعود الشيكات `Under_Collection → Draft` (`views.py:340-379`).
- **مجموع التوزيعات المرحّلة لا يتجاوز إجمالي الفاتورة**: `guard_invoice_allocation_total` (`services.py`) يُستدعى دائماً داخل معاملة بعد `select_for_update` على الفاتورة.
- **خصم المخزون idempotent**: `_post_stock_out_for_invoice` (`services.py`) يعود مبكراً إن وُجدت حركة `reference_type="SALE"` لنفس الفاتورة؛ ومثله `issue_stock_from_invoice` لـ`STOCK_ISSUE`.
- **`delivery_status` مشتقّ لا يُحرَّر يدوياً**: `sync_invoice_delivery_status` (`services.py`) هو المصدر الوحيد، وبنود الخدمات تُستثنى.
- **الكمية المحجوزة لطلبية زبون آخر ليست متاحة**: `guard_reserved_stock` (`services.py`) بعد قفل الأصناف، ومفتاحه `block_reserved_stock_sale`.
- **رقم الفاتورة فريد داخل الشركة**: `UniqueConstraint(["tenant","invoice_number"])` (`models.py`).
- **العميل والصنف يجب أن يتبعا نفس الـtenant** — يُفحص عند الترحيل (`services.py` للعميل، `:1597` للصنف).

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `sales/tests/test_ar_integrity.py` | سلامة الذمم: منع ازدواج التحصيل وبقاء السندات معلّقة بعد إلغاء الترحيل، وتصنيف فرق «المدفوع» (قديمٌ لا يُمسّ ÷ يتيمٌ يُصلَح) |
| `sales/tests/test_sales_post_unpost_stock.py` | تماثل post → unpost → repost للمخزون والقيد معاً |
| `sales/tests/test_reserved_stock_guard.py` | حجز الطلبية يمنع بيع الكمية لزبون آخر (4 قواعد) |
| `sales/tests/test_invoice_delivery.py` | حالة التسليم والتسليم الجزئي ببنوده |
| `sales/tests/test_sales_orders.py` | الطلبية ليست قيداً، الحجز مشتقّ، الإلغاء لا يحذف، العربون سند حقيقي |
| `sales/tests/test_subledger_routing.py` | قيد الفاتورة يدين الذمم بالكامل ولا يُسوّي النقدية |
| `sales/tests/test_block_loss_invoice.py` | رفض فاتورة فيها أي سطر بخسارة عند تفعيل المفتاح |
| `sales/tests/test_payment_cheques.py` · `test_voucher_atomicity.py` | الشيكات المرفقة وذرّية السند |
| `sales/tests/test_invoice_journal_purity.py` | قيد الفاتورة نقيّ من التسوية، و«المدفوع» لا يزيد بلا توزيع |
| `sales/tests/test_invoice_collect.py` | التحصيل من داخل الفاتورة: 60 نقداً + 40 شيكاً ⇒ سند واحد وذمم صفر، الفائض على الحساب، كبت التسوية التلقائية، والتراجع الكامل عند الفشل |
| `sales/tests/test_invoice_context_tabs.py` | تبويبات سياق الفاتورة: حركاتها المخزنية وحدها وسببُ فراغها، ومطابقة «قبل/بعد» لكشف الحساب سطراً بسطر (وأن أثر المدفوعة بالكامل = إجماليها لا صفر)، ونافذةٌ ترسو على فاتورة قديمة، والمرفق يُضاف لفاتورة مرحّلة ويُحذف بنطاق فاتورته |
