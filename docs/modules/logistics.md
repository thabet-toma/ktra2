# logistics — مسار الاستيراد والمشتريات: من عرض المورّد إلى فاتورة الشراء وتكلفتها المستوردة

> مبني على قراءة الكود مباشرةً بتاريخ 2026-08-11. عند تعارض هذا الملف مع الكود، الكود هو المرجع.

## الغرض
أكبر app في المشروع (26,753 سطر Python بالـmigrations · 22,864 بدونها · 15,004 كوداً بلا اختبارات). يغطي شِقّين: **الشراء المحلي** (عرض مورّد → طلبية → فاتورة → إرسالية استلام → مرجع شراء) و**الاستيراد الدولي**
(صفقة → شحنة → تخليص → نقل محلي → فاتورة دولية). يملك أيضاً محرّك **Landed Cost** الذي يوزّع الشحن الدولي والتخليص والنقل على بنود كل صفقة بدقّة الأغورة،
ودفعات كل طرف (مورّد، وكيل شحن، مخلّص، ناقل) مع ترحيلها المحاسبي.

## رحلة الاستيراد (المسار الأهم)
المرحلة القانونية الموحّدة هي `LogisticsDeal.stage` (`models.py:534-556`)، وكل انتقال يمرّ عبر `advance_deal_stage` (`domain/stages.py`). الحقل القديم `shipping_workflow_status` ما زال يُكتب بالتوازي (نافذة إضافية).

| # | المرحلة | الـstage | ما يُنشئه الكود | المُشغِّل |
|---|---|---|---|---|
| 0 | عرض مورّد استيراد | — | `SupplierQuotation(scope='import')` | حفظ الصفقة ومعها `source_quotation` — `views/deals.py` (`LogisticsDealViewSet._save_deal_claiming_quotation`) |
| 1 | صفقة | `draft` → `ready_to_ship` | `LogisticsDeal` + `LogisticsDealItem` + `LogisticsPayment` | يدوي |
| 2 | شحنة | `in_shipment` | `LogisticsShipment` + `LogisticsShipmentDeal` (حصة الشحن USD) | `create_shipment_from_deals` (domain/shipment_builder.py:62) |
| 3 | تخليص | `at_clearance` | `LogisticsClearance` + `…Line` + `…Payment` | signal `sync_deal_workflow_on_clearance` (signals.py:200) |
| 4 | نقل محلي (اختياري) | `in_transport` | `LocalShipment` + `LocalShipmentPayment` | يدوي |
| 5 | فاتورة دولية | `invoiced` | `PurchaseInvoice(invoice_type='international')` + بنودها | `import_invoices_from_clearance` (landed_cost.py:962) |
| 6 | إغلاق/إلغاء | `closed` / `cancelled` | — | يدوي |

**الواجهة في المرحلة 0:** «تحويل إلى صفقة» (شاشة عروض الاستيراد ومودال «من عرض» في الصفقات) يقرأ العرض ثم يفتح محرّر الصفقة معبّأً وغير محفوظ عبر `frontend_v2/utils/quotationToDraftDeal.ts` (`quotationToDraftDeal`)؛ المورد المبدئي والمنتج المكتوب يدوياً يصلان بلا معرّف فيلزمان المستخدم بحلّهما قبل «حفظ» — لا شريك ولا منتج يُنشأ تلقائياً في مسار الصفقة.

بوّابات المرحلة 5 (كلها في `landed_cost.py`): تكلفة الشحن **مُثبتة** (استحقاق مرحّل أو دفع كامل أو صفر) وإلا `ValueError` (`:996`)؛ والصفقة **مكتملة الدفع بالدولار** (`:1029`)؛ ولا تُحوَّل صفقة مرتين (`:1018`). تجاوز شرط الشحن (`allow_unpaid_freight`) يتطلب صلاحية مدير (`views.py:3202-3208`).

## أهم الملفات
| الملف | الغرض | أسطر |
|---|---|---|
| `logistics/views/` | **حزمة (المرحلة 3)** — كل الـViewSets موزّعة على 10 وحدات دومين؛ `__init__` يعيد التصدير فـ`from logistics.views import X` يبقى شغّالاً | ~5000 (كان views.py) |
| `logistics/serializers/` | **حزمة (المرحلة 3)** — 10 وحدات بنفس تقسيم الviews | ~2466 (كان serializers.py) |
| `logistics/models.py` | 20 model + آلتا حالة (صفقة/شحنة) مفروضتان على `save()` | 2009 |
| `logistics/services.py` | التحويلات بين المستندات + الاستلام + المرجع + الإعدادات | 1797 |
| `logistics/landed_cost.py` | محرّك التكلفة المستوردة بالشيكل + التتبّع العكسي | 1423 |
| `logistics/accruals.py` · `signals.py` | قيود الاستحقاق (تخليص/شحن/نقل) · تقدّم المراحل تلقائياً وإعادة مزامنة إجماليات الشحنة | 300 · 261 |
| `logistics/domain/` | allocation 117 · shipment_builder 166 · stages 109 · inland 97 · invoice_gen 16 | 505 |

**`domain/` مقابل `services.py`:** `domain/` طبقة نقية ومركزية لمسار الاستيراد وحده — `allocation.py` حسابٌ Decimal بلا ORM (largest-remainder، `Σ allocated ≡ total`)، `stages.py` جدول الانتقالات الوحيد الذي **يتحقّق ويكتب** معاً، `shipment_builder.py` فعل «صفقات → شحنة» ذرّياً، `invoice_gen.py` مجرّد re-export لنقاط `landed_cost` (16 سطراً، الدمج مؤجَّل لـM5). أما `services.py` فطبقة تطبيقية عريضة تلمس ORM ومحاسبة ومخزون، وتخدم الشراء المحلي أساساً.

**ماذا يحسب `landed_cost.py`:** لكل صفقة على شحنة — قيمة البضاعة بالشيكل (دفعات مسدَّدة بأسعارها + المتبقي × سعر مُدخَل، `deal_total_ils:160`)، حصّتها من الشحن
الدولي (`deal_volume_share_on_shipment:438`، أساس CBM/KG)، حصّتها من حوض التخليص (`clearance_pool_ils:358`، أساس القيمة)، والنقل المحلي (`domain/inland.py:transport_pool_ils`).
ثم يوزّعها على بنود الصفقة (`compute_deal_invoice_lines:480`) بتسوية أغورة، ويبني الفاتورة (`build_purchase_invoice_row:785`)، ويعيد الحساب حيّاً عند قراءة الفواتير
غير المرحّلة (`compute_live_purchase_invoice_read_payload:1275`)، ويبني التتبّع العكسي بند→صفقة→شحنة→تخليص→نقل (`build_import_trace:1327`).

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `SupplierQuotation` (:11) | `scope` (local/import), `status` (9 حالات), `supplier_draft_name` | `supplier`→Partner (nullable), `rfq`→`PurchaseRFQ` (nullable، #112)، `import_deal` OneToOne، `local_order`/`local_invoice` FK عكسي (بعد #112 — كانا OneToOne) |
| `PurchaseRFQ` (`logistics/models.py`) | `rfq_number` (NULL حتى أوّل إرسال)، `scope`، `status` (draft/sent/awarded/cancelled)، `reply_deadline` | `tenant`، `lines`، `recipients`، `quotations` (عكسي من `SupplierQuotation.rfq`) — **ISSUE #112**، مواصفة #108 |
| `PurchaseRFQLine` (`logistics/models.py`) | `quantity`، `unit_of_measure`، `specs`، `estimated_price` (داخليّ، nullable) — **بلا `unit_price` وبلا كود HS** | `rfq`، `product` (nullable) + `name_snapshot` (نمط `SupplierQuotationLine`) |
| `PurchaseRFQRecipient` (`logistics/models.py`) | `sent_at`، `replied_at` | `rfq`، `supplier`→Partner، `share`→`docshare.DocumentShare` (nullable، **مسلوكة — ISSUE #115**: `_wire_rfq_recipient_shares` في `send/`/`recipients/`)، `quotation` OneToOne (nullable) |
| `LogisticsDeal` (:409) | `ref_number`, `stage`, `shipping_workflow_status`, `total_amount`, `total_cbm`, `total_weight_kg`, `payment_status` | `tenant`, `partner`, `currency`, `source_quotation` OneToOne, `shipments` M2M |
| `LogisticsShipment` (:846) | `shipment_number`, `chargeable_unit` (cbm/kg), `freight_rate`, `total_shipping_cost_usd`, `freight_is_posted` | `deals` M2M عبر `LogisticsShipmentDeal`, `freight_journal`, `transit_journal` |
| `LogisticsShipmentDeal` (:1046) | `allocated_shipping_cost`, `extra_costs` | `unique_together (shipment, deal)` |
| `LogisticsClearance` (:1077) | `declaration_number`, `grand_total`, `exchange_rate` | `shipment` **OneToOne**, `customs_broker`, `lines`, `payments` |
| `LogisticsClearanceLine` (:1177) | `line_type`, `debit`/`credit`, `vat_percent` | `clearance`, `account` |
| `LocalShipment` (:1210) | `shipment_number` (LS-XXXX), `capitalize_to_inventory`, `exchange_rate`, `status` | `clearance`, `shipment` (كلاهما اختياري) |
| `PurchaseInvoice` (:1435) | `invoice_number`, `invoice_type` (local/international), `grand_total`, `import_*_rate` | `deal`, `shipment`, `clearance`, `partner`, `source_quotation` **FK** (كان OneToOne — #112) |
| `PurchaseInvoiceItem/Fee/Payment` (:1629/:1730/:1699) · `GoodsReceipt`/`Line` (:1811/:1883) | البنود والرسوم والدفعات · سند الاستلام | `invoice` · `movement`→StockMovement |
| `LogisticsPayment` (:746) · `PurchaseOrder` (:248) · `PurchaseSettings` (:1926) | دفعات الصفقة/الشحنة · الطلبية · `receive_on_post`، `use_purchase_orders` (#117) | `deal`/`shipment`/`journal` · `tenant`، `PurchaseOrder.quotation` **FK** (كان OneToOne — #112) |

## دوال الـservices العامة
```python
# logistics/services.py — التحويلات وسير الشراء المحلي
# ملاحظة: لا توجد دالة تحويل «عرض استيراد → صفقة». المسار ينتقل عبر الواجهة:
# «تحويل إلى صفقة» يفتح محرّر صفقة **غير محفوظ** معبّأً من العرض (قراءات فقط:
# تفاصيل العرض + `deals/next-ref/`)، والحفظ وحده يُنشئ الصفقة ويطالب بالعرض —
# انظر `views/deals.py` (`LogisticsDealViewSet._save_deal_claiming_quotation`).
def convert_local_quotation_to_order(quotation, *, user=None):          # عرض محلي مقبول → طلبية شراء
def convert_local_quotation_to_invoice(quotation, *, user=None):        # عرض محلي → فاتورة مسودة مباشرةً (بلا طلبية)
def convert_purchase_order_to_invoice(order, *, user=None):             # طلبية → فاتورة شراء مسودة
def get_or_create_purchase_settings(tenant):                            # إعدادات الشراء للشركة بقيم افتراضية
def purchase_invoice_payment_summary(invoice):                          # ملخص الدفع من السندات المرحّلة فقط
def purchase_item_receipt_quantities(item):                             # (المطلوب، المستلَم، الباقي) لبند — القاعدة الوحيدة
def purchase_invoice_receipt_summary(invoice, items=None):              # «استُلم X من Y — باقي Z» للفاتورة كلها
def receive_purchase_invoice(invoice, *, lines, branch=None, user=None, movement_date=None,
                             receipt_date=None, notes='', supplier_ref='',
                             existing_receipt=None):                    # استلام فاتورة محلية للمخزن + قيد الاستلام
def create_standalone_goods_receipt(tenant, *, partner, lines, branch=None, user=None,
                                    receipt_date=None, notes='', supplier_ref='', receipt=None):  # GR/IR: بضاعة قبل فاتورتها
def void_goods_receipt(receipt, *, user=None):                          # عكس إرسالية واحدة (حركاتها وقيدها فقط)
def create_purchase_return(tenant, *, original_invoice, partner, return_date, lines, notes='',
                           invoice_number=None, currency=None, exchange_rate=None, user=None):    # مرجع شراء كمسودة
def post_purchase_return(invoice, *, user=None):                        # ترحيل المرجع: RETURN_OUT + قيد عكسي
def suggest_supplier_fifo_allocations(*, tenant_id, partner_id, amount) -> list[dict]:  # اقتراح توزيع سند صرف من الأقدم استحقاقاً
def pay_purchase_invoice(invoice, *, cash=None, cash_account_id=None, cheques=None,
                        from_on_account=None, payment_date=None, user=None):        # منسّق الدفع: سند صرف واحد + سلف المورّد، ذرّياً
def guard_purchase_invoice_payments_before_unpost(invoice, *, action_label='إلغاء ترحيل'):  # سندٌ مرحّل يمنع حذف قيد الفاتورة
def release_auto_cash_purchase_settlement(invoice, *, user=None) -> list[int]:       # سند الشراء النقدي التلقائي يُحرَّر مع إلغاء الترحيل
def purchase_journal_settlement_debit(invoice) -> Decimal:                           # ما سُوّي داخل قيد الفاتورة نفسه (ما قبل Feature 2)
def create_supplier_payment_cheques(payment, cheques) -> None:                       # عقد شيك سند الصرف — نقطة كتابة واحدة
def attach_pi_payment_voucher(invoice, *, cash_amount=0, cash_account_id=None,
                              cheques=None, user=None):                 # ربط سند (نقد + شيكات) قبل الترحيل

# logistics/domain/ — محرّك الاستيراد
def advance_deal_stage(deal, target: str, *, force: bool = False, save: bool = True) -> str:      # الانتقال الوحيد المحروس
def create_shipment_from_deals(*, tenant, deal_ids, chargeable_unit, freight_rate=0,
                               header=None, user=None) -> LogisticsShipment:                      # صفقات → شحنة ذرّياً
def reconcile(total, weights: List[Decimal]) -> List[Decimal]:          # توزيع بأغورة مضبوطة (Σ ≡ total)
def resolve_chargeable_unit(shipment) -> str:                           # وحدة تسعير الشحن: 'cbm' أو 'kg'

# logistics/landed_cost.py — التكلفة المستوردة
def preview_landed_import(*, clearance, deal_ids, deal_remaining_rate,
                          shipment_remaining_rate, use_cost_lines) -> Dict[str, Any]:              # معاينة بلا كتابة
def import_invoices_from_clearance(*, tenant, clearance_id, deal_ids, deal_remaining_rate,
                                   shipment_remaining_rate, use_cost_lines,
                                   next_invoice_number_cb, allow_unpaid_freight=False) -> List[PurchaseInvoice]:
def recalculate_landed_for_shipment(*, tenant, shipment_id, deal_remaining_rate=None,
                                    shipment_remaining_rate=None, use_cost_lines=None) -> Dict[str, Any]:
def build_import_trace(invoice: PurchaseInvoice) -> Dict[str, Any]:     # تتبّع عكسي: بند → صفقة → شحنة → تخليص → نقل
```

## أهم الـAPI endpoints
كل ما يلي تحت `/api/logistics/` (`core/urls.py`) — الـrouter في `logistics/urls.py:15-28`.

| Method | المسار | الـview |
|---|---|---|
| GET | `deals/ready-to-ship/` | `LogisticsDealViewSet.ready_to_ship` (views.py:536) |
| POST | `deals/{pk}/payments/` · `post_payment/{id}` · `unpost_payment/{id}` | views.py:618 / 883 / 1124 |
| POST/PATCH | `shipments/create-from-deals/` · `shipments/{pk}/freight/` | `create_from_deals` (:1505) · `set_freight` (:1549) |
| POST | `shipments/{pk}/post-freight-accrual/` · `unpost-freight-accrual/` | views.py:2139 / 2177 |
| POST | `clearances/{pk}/post-to-accounting/` · `pay_from_cashbox/` | views.py:2249 / 2338 |
| POST | `purchase-invoices/preview-clearance-import/` · `import-from-clearance/` | views.py:3103 / 3179 |
| GET | `purchase-invoices/{pk}/trace/` | `trace` (views.py:3245) |
| GET | `purchase-invoices/{pk}/stock-movements/` · `supplier-ledger/` | تبويبا السياق — أثر الفاتورة على المخزن، وكشف حساب المورّد مرسوّاً عليها |
| GET/POST · DELETE | `purchase-invoices/{pk}/attachments/` · `attachments/{id}/` | تُحفظ **فوراً** لا مع الفاتورة، فيبقى الإرفاق ممكناً بعد الترحيل |
| GET · POST | `purchase-invoices/next-number/` · `purchase-invoices/{pk}/duplicate/` | الرقم التالي قبل الحفظ · نسخُ الفاتورة مسودّةً بلا ترحيلٍ ولا استلام |
| GET | `supplier-payments/suggest-fifo-allocations/?partner=&amount=` | اقتراح توزيع سند صرف على فواتير المورّد (الأقدم استحقاقاً أولاً) |
| POST | `purchase-invoices/{pk}/pay/` | `pay` — الدفع من داخل الفاتورة (نقد/شيكات/سلف المورّد)، صلاحية `purchase.payment.create` (+`purchase.invoice.post` مع `post_invoice`) |
| POST | `purchase-invoices/{pk}/post-to-accounting/` · `receive/` · `unpost/` · `returns/` | views.py:3400 / 2991 / 4047 / 3027 |
| GET | `import-journey/` · `reports/landed-cost/?shipment_id=` | views.py:4557 / 4588 |
| GET/POST | `goods-receipts/` · `goods-receipts/outstanding/` · `purchase-settings/current/` | views.py:4783 / 4935 / 5038 |
| POST | `purchase-rfqs/{pk}/send/` · `cancel/` · `award/` · `recipients/` | **ISSUE #112**: أوّل إرسال يقفل البنود ويخصّص الرقم؛ `recipients/` وحده مسموحٌ بعد الإرسال. **`award/`** (ISSUE #116) يحمل `supplier` إلزامياً — يقبل عرض الفائز وينتج أمر شراء أو فاتورة بحسب `use_purchase_orders` (`PurchaseRFQViewSet`، `logistics/views/procurement.py`) |
| GET | `purchase-rfqs/{pk}/comparison/` | **ISSUE #116**: مصفوفة الموردين — صفٌّ لكل بند وعمودٌ لكل موردٍ ردّ فعلياً، بالعملة الأساسية، بلا حقل شحن. خطُّ الأساس `estimated_price` لا «أقل سعر» (ذاك داخل العرض الواحد وحده، #113). داخليّةٌ بحتة — لا `doc_type` لها في `docshare` |
| — | باقي الموارد بالـrouter: `supplier-quotations/`, `purchase-rfqs/`, `purchase-orders/`, `payments/`, `supplier-payments/`, `local-shipments/` | urls.py |

## الاعتماديات
**يعتمد على:**
- `tenants` (models مباشرة) — `logistics/models.py` `from tenants.models import Tenant, Currency`؛ كل model يحمل `tenant` FK.
- `accounting` (models **و** services) — `logistics/views.py:47-55`: `post_journal`, `unpost_document`, `validate_fiscal_period`, `next_document_number`, `get_exchange_rate`, `create_audit_log`.
- `sales` (models + serializers) — `logistics/serializers/` يستورد `SupplierPayment`, `SupplierPaymentAllocation` والثابت `CHEQUE_DUE_DATE_REQUIRED` من `sales.serializers`؛ و`logistics/views/` يستورد `SupplierPayment` ويعرضه عبر `SupplierPaymentViewSet`. أي تغيير في عقد `sales` للشيكات يكسر فواتير الشراء.
- `partners` (models + signals): `models.py`, `views.py:42-43` · `inventory` (models + services): `models.py:4-5`, `views.py` · `core` (access/mixins/tenant_utils/activity/plans): `views.py:60-74`.
**يعتمد عليه:** `sales/services.py:3817,3906-3907` · `accounting/services.py:931,1013,1522` · `accounting/views.py:313,342,1355` · `accounting/serializers.py:75,129` · `inventory/services.py:447,681,941,997` · `inventory/serials.py` · `partners/views.py:75,142-144` · `after_sales` (اختبارات) · `import_file` (وحدة مرخّصة تقرأ الصفقة والشحنة اتجاهاً أُحادياً — لا FK ولا عمود منها في أي جدول هنا).

**الاستثناء الوحيد في الاتجاه المعاكس** — `logistics/views/reports.py` (`ImportJourneyViewSet.list`) يستورد `import_file.services` (`attach_file_progress`) **استيراداً كسولاً داخل حارس الترخيص**، فيُثري ملخّص رحلة الاستيراد بـ`file_progress` للشركة المرخّصة وحدها. بلا ترخيص الحمولة مطابقة حرفياً لما كانت عليه، و`logistics/import_journey.py` يبقى جاهلاً بالوحدة تماماً. تفصيل الوحدة في `docs/modules/import_file.md`.

## قواعد لا يجوز كسرها
- **كل انتقال مرحلة عبر `advance_deal_stage`** — لا `.update(stage=…)` مباشراً؛ حتى الـsignals تمرّ عبره (`signals.py:180-188`). جدول الانتقالات الوحيد في `domain/stages.py:24-34`.
- **الصفقة على شحنة واحدة كحد أقصى**: رفض صريح في `domain/shipment_builder.py:103-109` + `unique_together (shipment, deal)` (`models.py`).
- **`Σ allocated ≡ total` بدقّة الأغورة** في أي توزيع — استخدم `domain/allocation.py:reconcile` (:44) ولا تُقرِّب يدوياً.
- **سعر شحن > 0 على صفقة بلا CBM/KG مرفوض** (وإلا حصّتها صفر صامتة): `domain/shipment_builder.py:43-59`، ونفس الحارس في `views.py:1582-1588`.
- **لا فاتورة استيراد قبل**: إثبات تكلفة الشحن (`landed_cost.py`) + اكتمال دفع الصفقة بالدولار (`:1029`) + عدم تحويلها سابقاً (`:1018`).
- **المستند المرحّل لا يُعدَّل ولا يُحذف**: `_shipment_is_posted` (views.py:2044)، `_clearance_is_posted` (views.py:2228)، وحارس `transit_journal` في `set_freight` (views.py:1558-1562).
- **بنود الفاتورة تُطابَق بالمعرّف لا تُحذف وتُعاد**: `PurchaseInvoiceSerializer._sync_items` — بندٌ بمعرّف يُعدَّل في مكانه، وبلا معرّف بندٌ جديد، والغائب عن الحمولة يُحذف؛ ومعرّفٌ من فاتورة أخرى يُرفض. الحذف الشامل السابق كان يُصفّر `received_quantity` (حقل للقراءة فقط فلا يعود في الحمولة) ويُسقط أسطر الإرسالية بالـCASCADE (`GoodsReceiptLine.item`) بينما تبقى حركات المخزون. **والواجهة شريكةٌ في العقد**: `InvoiceForm` يرسل `id` من `serverId` (`utils/mapPurchaseInvoiceDto.ts`) — بلا إرساله تعود المطابقة حذفاً وإعادة إنشاء بصمت.
- **البند المستلَم مُجمَّد فيما يعتمد عليه سند الاستلام**: `_guard_received_items` يرفض حذفه، أو إنقاص كميته عن المستلَم، أو تبديل منتجه أو سعره أو أرقامه التسلسلية — الحركة سُجّلت بمنتجه وسعره والوحدات تجسّدت به. الباقي مسموح (ملاحظات، بنود جديدة، زيادة الكمية) لأن الاستلام الجزئي حالة مشروعة، والمخرج عند اللزوم إلغاءُ الإرسالية (`DELETE goods-receipts/{id}` ⇐ `void_goods_receipt`, و`allow_edit_receipt=True` افتراضاً). الفاتورة المرحّلة يمنعها حارس `perform_update`؛ وهذا يغطّي النافذة المتبقية — فاتورة صفرية القيمة استُلمت بلا قيد فبقيت غير مرحّلة (`services.py` — `gross > 0` وحده يُرحّل).
- **الفاتورة المرحّلة مُجمَّدة على قيمها المحفوظة**؛ غير المرحّلة تُعاد حسابها حيّاً عند القراءة (`landed_cost.py`).
- **«الاستلام مع الترحيل» خيارُ الفاتورة الواحدة، والإعداد العام افتراضُه** — `views/invoices.py` (`post_to_accounting`) يقبل `receive_on_post` في جسم الطلب فيتقدّم على `PurchaseSettings.receive_on_post`. إغفاله يُبقي السلوك القديم حرفياً. الخيار لحظةُ ترحيلٍ لا حقلٌ محفوظ: ما بعده تقوله `receipt_status` والإرساليات. **ويسري على `pay/` كذلك** (T-PAYFULL2): تلك النقطة ترحّل الفاتورة داخلها (`post_invoice`) بنداء `post_to_accounting` نفسها، فيمرّ الحقل من جسمها — ولولا ذلك لاختلف الأثر المخزنيّ باختلاف الزرّ الذي أطلق الترحيل، وصار الإعداد العام يقرّر وحده لأن المستخدم دفع بدل أن يرحّل.
- **الطلبية تتحوّل كاملةً مرّةً واحدة** (`PurchaseOrder.invoice` علاقةُ واحد-لواحد) — والتجزئة على مستوى **الاستلام** لا التحويل: طلبيةٌ واحدة ← فاتورةٌ واحدة ← إرساليات متعددة. هذا ما تفعله Odoo (backorder على سند الاستلام) وZoho (عدّة Purchase Receives للطلبية). ولذلك تحمل `PurchaseOrderSerializer` تقدّم استلام فاتورتها (`invoice_receipt_progress`) فلا تنتهي الطلبية عند «محوّلة إلى فاتورة» طريقاً مسدوداً. **لا تُدخِل «كمية محوَّلة» على سطر الطلبية** — تخلق معنىً ثانياً لـ«الباقي» (للفوترة مقابل للاستلام) وتعيد الالتباس الذي أُزيل.
- **«الباقي على البند» قاعدةٌ واحدة لا نسخ** — `services.py` (`purchase_item_receipt_quantities`): الكمية − المستلَم مقصوصاً عند الصفر وبدقّة العمود (أربع خانات). تستدعيها المواضع الستّة كلّها: تقرير البواقي (`views/goods_receipts.py` — `outstanding`)، وبنود الاستلام (`views/invoices.py` — `receivable_lines`)، وبند الإرسالية ومجموعها (`serializers/goods_receipts.py`)، وحارس `receive_purchase_invoice`، وقراءة الفاتورة (`serializers/invoices.py` — `remaining_quantity` على البند و`receipt_progress` على الرأس). **الواجهة تعرض ولا تطرح** — أيّ طرحٍ فيها نسخةٌ سابعة تفترق غداً.
- **اسم المنتج المعروض يمرّ عبر `inventory/services.py` (`product_display_name`)
  لا `str(product)`** (#41/#42): بند الإرسالية (`serializers/goods_receipts.py` —
  `get_product_name`)، صفوف «المتبقّي للاستلام» في `views/goods_receipts.py`
  (`outstanding`) و`views/invoices.py` (`receivable_lines`) كلّها تشتقّه حياً
  عند القراءة — البراند حقلٌ على نفس صفّ المنتج فلا استعلام إضافي. **القيمة
  المجمَّدة مختلفة**: `PurchaseInvoiceItem.name` يُكتب من موضعين — `services.py`
  (`_draft_purchase_invoice_from_document`، تحويل طلبية/عرض سعر) و`services.py`
  (`create_purchase_return`، بند مرتجع الشراء) — يكتبان `product_display_name`
  من الآن فصاعداً فقط؛ بنودٌ حُوِّلت **قبل** هذا التاريخ تحمل المقاس عارياً بلا
  براند، وما بعده يحمل البراند بين قوسين؛ **تعايش صيغتين في العمود الواحد
  مقبولٌ ومُعلَن**، لا عطبٌ ولا يُصلَح بأمر backfill. **وكلا الموضعين يقصّ عند
  الكتابة بحدّ العمود نفسه** (`PurchaseInvoiceItem._meta.get_field('name')
  .max_length`، لا رقماً مطبوعاً) — الاسم المركَّب قد يبلغ ٣٠٣ محرفاً والعمود
  حدّه ٢٥٥؛ الفيض هنا لا يُرمى خطأً بل يُلغي القيد بصمت في MySQL (#42).
- **الإرسالية تُفتح مملوءة لا فارغة**: ربطُ فاتورةٍ بمحرّر الإرسالية
  (`frontend_v2/components/procurement/receipts/GoodsReceiptsPage.tsx` —
  `pickInvoice` بخيار `autofillWarehouse`) يبني بنودها من `receivable-lines`
  بالكمية المتبقّية لكل بند والمستودع الافتراضي — الحالة الغالبة أن تصل الشحنة
  تامّة، وكان المستخدم يبنيها بنداً بنداً بعد أن كانت البنود بيده. المستلَم
  بالكامل لا يدخلها، والمستوردة لا تُعبَّأ (بضاعتها من تخليص الشحنة).
  التعبئة **بالمعامل لا بـeffect**: حذفُ صفٍّ يبقى محذوفاً، وإعادةُ البناء
  بزرّ **«استلام الكل»** صريحاً بتأكيد. المستودع يُمرَّر بالقيمة من `loadRefs`
  لا من الحالة — عند الفتح لم تكن قد وصلت بعد. وإرسالية البيع
  (`frontend_v2/components/sales/DeliveryNotesPage.tsx` — `deliverableToLines`
  و«تسليم الكل») مرآةٌ حرفية، وفيها الاستثناء `stock_on_post` بدل «المستوردة»:
  فاتورةٌ تخصم المخزون عند ترحيلها مسلَّمةٌ أصلاً فلا تُعبَّأ.
- **لا إلغاء ترحيل لفاتورة شراء عليها سند صرف مرحّل**: `services.py`
  (`guard_purchase_invoice_payments_before_unpost`) يُستدعى من `views/invoices.py`
  (`unpost`) في مسارَي الفاتورة والمرجع. كان الحذف يطال قيود الفاتورة وحدها
  (`PURCHASE_INVOICE`/`GRN`/`RECEIPT`) ولا يرى السندات إطلاقاً، فيبقى قيد السند
  **يدين ذمم المورد بلا مقابل** — رصيدٌ وهميّ لصالح الشركة عند مورّد لم يُدفع له
  زائد. مرآة `guard_invoice_payments_before_unpost` على جانب البيع. الاستثناء
  الوحيد سندُ التسوية النقدية التلقائي (الموسوم بـ`auto_settled_invoice`) —
  يُحرَّر بالحذف أولاً عبر `release_auto_cash_purchase_settlement` لأن الترحيل
  نفسه أنشأه، فلا يبقى معلّقاً ولا يتضاعف عند إعادة الترحيل.
- **«المدفوع» يُحسب ولا يُفترض**: `purchase_invoice_payment_summary` (وتوأمها
  الـSQL `annotate_purchase_invoice_payment_summary`) كانتا تعطيان كل فاتورة
  **نقدية مرحّلة** `paid = payable` بغضّ النظر عن وجود سند، وتسقطان عند غيابه على
  `attached_cash_amount` — وهو اليوم **نيّة دفعٍ على المسودة** لا مدفوعاً
  (T-INTENT، انظر أدناه). فكانت الشاشة تقول «مدفوعة بالكامل» وذمم المورد دائنة (يكفي إلغاء ترحيل
  السند التلقائي ليظهر الكذب). ما يُحتسب اليوم شيئان، كلاهما قيدٌ فعليّ: سنداتٌ
  مرحّلة، و**تسويةٌ داخل قيد الفاتورة نفسه** لفواتير ما قبل Feature 2
  (`purchase_journal_settlement_debit` — مدينُ حساب ذمم المورد المرتبط داخل قيدها،
  والمرجع مستثنى لأنه يدين الذمم بحكم تعريفه). **القاعدة في موضعين ولا يجوز أن
  يفترقا** — القائمة والتفصيل يقولان الرقم نفسه، ويحرسه
  `tests/test_purchase_paid_is_computed.py`. ومعها: الشراء النقدي بلا حساب صندوق
  (ولا افتراضي للشركة) صار **يُرفض ترحيله** بدل التخطّي الصامت الذي كان يُنتج
  فاتورةً «نقدية» بلا تسوية.
- **`cash_or_bank_account` كان حقلاً ميّتاً في محرّر الشراء** (T-PAYFULL2):
  المُسلسِل يشترطه على `payment_type='cash'`، وبناءُ الحمولة يقرؤه، والمُطابِق
  يملأه من الخادم — ولا **موضعَ واحد** في `InvoiceForm.tsx` يكتبه. فعلامة
  «نقدي» في الرأس كانت طريقاً مسدوداً: رفضٌ من الخادم لا حقلَ على الشاشة
  يُصلحه. صار يُملأ بسلّم `utils/cashBox` نفسه ويُعرض بجوار العلامة (مرآة
  `SalesInvoiceEditor` منذ T-CASHBOX)، وحارسٌ في الواجهة يقول الشرط قبل
  الرحلة. الترحيل نفسه كان يحلّ الصندوق الافتراضي بنفسه، فالعطل كان في
  **الحفظ** لا في المحاسبة.
- **الدفع من داخل الفاتورة نقطة واحدة**: `services.py` (`pay_purchase_invoice`) خلف
  `purchase-invoices/{id}/pay/` — تركيبُ خدمات قائمة بلا أي منطق ترحيل جديد: سند
  صرف واحد بنقده وشيكاته (`post_supplier_payment`) بتوزيعٍ مقصوص على المتبقّي وما
  زاد يبقى سلفةً «على الحساب»، ثم `allocate_supplier_payment` لكل صفّ من سلف
  المورّد (ربطٌ بلا قيد جديد). الترحيل يبقى مملوكاً لـ`post_to_accounting`،
  والنقطة تجمع الاثنين في `transaction.atomic` واحد فلا تُترك فاتورةٌ مرحّلة
  بسندٍ نصفِ مولود؛ وسندُ التسوية التلقائي يُكبَت حين يتولّاها الدفع الصريح
  (`_suppress_auto_settlement`) وإلّا خطف كاملَ المتبقّي فخرج سندان. الفاتورة
  النقدية مدفوعةٌ بالتعريف: نقدٌ غير مذكور يُكمَّل، ونقصٌ بعد نقدٍ مذكور يَرفض
  العملية كلَّها. مرآة `collect_invoice_payment`.
  > والنقطة القديمة `payment-voucher` غلافٌ فوق `pay/` (ترحيلٌ + سند فوراً).

- **الفاتورة مركز سياق لا نموذج إدخال**: ثلاث نقاط تجيب من داخلها —
  `stock-movements/` (ما فعلته **هي** بالمخزن، ومعه سبب الفراغ: مسودّة؟ أم لم
  تُستلَم؟) · `supplier-ledger/` (كشف حساب المورّد مرسوّاً عليها من
  `partner_account_statement` نفسه) · `attachments/` GET/POST وDELETE. المرفقات
  **تُحفظ فوراً** لا مع الفاتورة: `perform_update` يرفض المرحّلة، فكان
  `_sync_attachments` المعلّق بمسار PATCH يعني ألّا يُرفق إيصال مورّد بعد الترحيل
  أبداً — وهو أكثر وقت يُحتاج فيه — ولا حذفَ أصلاً. الواجهة تستهلكها بمكوّن
  `DocumentContextTabs` المشترك مع البيع (`side="supplier"`).
  > وبـ`supplier-ledger/` أُغلق الدين الموثَّق في `docs/modules/sales.md`:
  > `supplier_balance_before_invoice`/`after` تقريبٌ يطرح المتبقّي من رصيد
  > **اليوم** فتظهر المسدَّدةُ بأثرٍ صفريّ وهي دائنةُ ذمم بكامل إجماليها. الحقلان
  > باقيان لعقد الـAPI، ولا يُعرضان على أنهما «قبل/بعد» — الشاشة تعرض الرصيد
  > الحالي وتُحيل إلى التبويب.
- **الاستحقاق حقلٌ ومهلةُ السداد تشتقّه**: `due_date` + `payment_terms_days` على
  `PurchaseInvoice` (كانا على فاتورة البيع وحدها). القاعدة في
  `core/payments.py` (`resolve_due_date`) — الصريح يسمو على المشتقّ فلا يمحو حفظٌ
  لاحق تاريخاً كتبه المستخدم. وأعمار الذمم **الدائنة** صارت تُعمَّر بالاستحقاق
  كنظيرتها المدينة (`core/reports/financial.py`)، بعد أن كانت تُعمَّر بتاريخ
  الفاتورة فتضع فاتورةً مهلتها 60 يوماً في خانة «31–60» وهي لم تستحقّ بعد.
- **«متأخرة» بُعدٌ فوق حالة الدفع لا قيمةٌ رابعة فيها**: `document_overdue_state`
  (`core/payments.py`) — عليها متبقٍّ **و**استحقاقها مضى؛ وبلا تاريخ استحقاق لا
  تخمين. تُعرض شارةً ثانيةً بجانب «مدفوعة جزئياً» لا بدلاً منها، ولها خيار فلترة
  `?payment_status=overdue` على الجانبين. إدخالها في `payment_status` كان يكسر
  الفلاتر والشارات القائمة على القيم الثلاث ويخفي «كم بقي» خلف «تأخّر».
- **نيّة الدفع على المسودة (T-INTENT)** — مرآة جانب البيع حرفياً: المسودة تحمل
  دفعةً مسجَّلة (`attached_cash_amount`/`attached_cash_account` + شيكات `Draft`
  مربوطة بالفاتورة) **بلا قيد ولا سند صرف ولا أثرٍ على رصيد المورّد**. تُكتب من
  `attach_purchase_payment_voucher` عبر النقطة `attach-payment/` بدلالة
  الاستبدال، ولا تتجاوز إجمالي الفاتورة. عند الترحيل يكنسها
  `settle_attached_purchase_intent` في **سند صرف واحد** مقصوصاً على المتبقّي
  (`min(intent, remaining)`)، **قبل** التسوية النقدية التلقائية التي صارت تكمّل
  ما بقي وحده — بلا هذا القصّ يخرج سندان مجموعهما يتجاوز الفاتورة. العمود لا
  يُمسح بالترحيل: التجسّد هو السند (`auto_settled_invoice`) الذي يُحرَّر مع
  إلغاء الترحيل وتعود شيكاته `Draft`، فتُعاد حالة المسودة كما كانت. يكشفها
  `pending_payment_total` في الزوج الواجب اتفاقه (Python + SQL) وفي المُسلسِلين
  معاً، خارج «المدفوع» وخارج `payment_status`.
- **العزل بالشركة إلزامي** (كل ViewSet يرث `BaseTenantViewSet`، `core/mixins.py`)، و**إلغاء الترحيل يحتاج** `import.doc.unpost` (views.py:760, 2104, 2176, 2275, 2296, 2593).
- **ISSUE #112 — الطلبية تسبق عرض المورّد**: `PurchaseRFQ` أبٌ يجمع ردود
  `SupplierQuotation` تحته (`rfq` FK اختياري على العرض — عروضٌ مستقلّة قائمة
  تبقى صحيحة بلا ربط). **بنودها تُقفل عند أوّل إرسال لا عند الترسية** —
  `PurchaseRFQSerializer.validate` يرفض أيّ حقل غير `notes`/`reply_deadline`
  على طلبية ليست `draft` (400 على تعديل بند). المسموح بعد الإرسال: إضافة
  مستقبِل (`POST .../recipients/`) والإلغاء والملاحظات والمهلة وحدها.
  **الرقم يُخصَّص عند أوّل إرسال لا عند الإنشاء** (`rfq_number` يبقى `NULL`
  حتى فعل `send/` — مسودّة مهجورة لا تحرق رقماً). «وردت عروض» عدّادٌ مشتقّ
  (`recipients_count`/`replies_count`) لا حقلٌ مخزَّن. **ولا كود HS على بندها
  إطلاقاً** — مورّدٌ يُسعّر لا يُسأل عن الرمز الجمركي (قرار المالك #108 §4).
  السعر التقديريّ (`estimated_price`) رقمٌ داخليّ فقط؛ مسار خروجه المحروس
  (رابط المورد/الطباعة/Excel) خارج هذه التذكرة — أما **الأساس الذي يبنيه**
  (مصفوفة الأعمدة بقائمة سماح) فبُني في ISSUE #113، انظر
  `docs/modules/frontend.md` (`utils/procurementColumns.ts`).
- **`PurchaseOrder.quotation` و`PurchaseInvoice.source_quotation` صارا
  `ForeignKey` لا `OneToOneField`** (ISSUE #112 — الترسية المجزّأة تحتاج بنيةً
  تسمح بأكثر من مستند لاحق لعرضٍ واحد، خارج نطاق هذه التذكرة لكن القيد رُفع
  الآن قبل أن تمتلئ الجداول). **الاستدعاء تغيّر لا الحقل**: `quotation.local_order`
  و`quotation.local_invoice` صارا مديرَي علاقة عكسية (querysets) — `.first()`
  لا وصولاً مباشراً و`except DoesNotExist` (`logistics/services.py`،
  `logistics/serializers/procurement.py`).
- **ISSUE #117 — أمر الشراء خطوة اختيارية**: `PurchaseSettings.use_purchase_orders`
  (افتراضه `False` — السلسلة الجديدة طلبية ← عروض ← فاتورة بلا أمر شراء؛ هجرة
  `0082` تُشعله لكل شركةٍ لها أمرُ شراءٍ قائم فعلاً). **المفتاح يحكم الإنشاء لا
  الرؤية**: نقطتا الإنشاء الوحيدتان — `PurchaseOrderViewSet.perform_create`
  (`logistics/views/procurement.py`) و`convert_local_quotation_to_order`
  (`logistics/services.py`، مسار «تحويل عرض سعر إلى طلبية») — ترفضان مطفأً؛
  القراءة والفتح والاستلام (`GoodsReceipt.invoice` مربوطٌ بالفاتورة لا بأمر
  الشراء) بلا تغيير، ولا قيدَ محاسبياً لأمر الشراء أصلاً فلا أثر في الدفاتر.
- **ISSUE #116 — المقارنة والترسية: مستويان لا يجوز خلطهما** (مواصفة #108 §٨،
  قرار المالك 2026-09-03). داخل عرضٍ واحد يبقى خطُّ الأساس «أقل سعر» (#113)؛
  مصفوفة الموردين (`comparison/`) وحدها تحاكم إلى `PurchaseRFQLine.estimated_price`
  — **لا يُجمَع العمودان في شاشةٍ واحدة**. المصفوفة **داخليّةٌ بحتة**: لا
  `doc_type` لها في `docshare.documents` (`docshare/tests/test_purchase_rfq_comparison_not_shareable.py`
  يحرس غيابها صراحةً). **حساب الفارق المئوي دالّةٌ واحدة** —
  `frontend_v2/utils/purchasePriceHint.ts` (`computeDeltaPercent`) تخدم عمود
  العرض والمصفوفة معاً بخطّي أساس مختلفين؛ الخادم لا يحسب نسبةً أبداً، يعيد
  الأرقام الخام (تقديريّ وسعرَ كلّ موردٍ بالعملة الأساسية) فقط. **إجماليٌّ
  واحد**: `goods_total_base` = Σ(كمية × سعر) للبنود المسعَّرة وحدها — بندٌ لم
  يُسعّره موردٌ بعينه لا يدخل الإجمالي صفراً، و**لا حقل شحنٍ في الاستجابة
  إطلاقاً** (ناسخاً إجمالي #107 الشامل؛ الشحن باقٍ في الصفقة والتكلفة
  النهائية). **`award/` يحمل `supplier` إلزامياً** الآن — يحسم أيّ ردّ
  (`SupplierQuotation`) فائزٌ، يقبله (`STATUS_ACCEPTED`) ثم يمرّ حرفياً بمسار
  قبول عرضٍ محلّيّ يدويّ (`convert_local_quotation_to_order`/`_invoice`) —
  **لا منطق ترحيل جديد**، تركيبُ خدمات قائمة وراء مفتاح `use_purchase_orders`
  (#117) وحده. مورّدٌ لم يردّ بعد لا عمود له في المصفوفة أصلاً (فراغٌ لا
  يُفسَّر خطأً كرفض).

## إلغاء ترحيل الدفعات (وُحِّد في المرحلة 2 + معالجتها 2026-08-11)
إلغاء ترحيل دفعة صفقة (`unpost_payment_from_accounting`) ودفعة تخليص (`unpost_payment`)
كلاهما عبر `accounting.api.reverse_journal(..., copy_currency=True)`: **الأصل يبقى مرحّلاً**
ويعادله قيد عكس بعملته وسعره ⇒ صافي الأثر صفر اسمياً وبالعملة الأساسية، وتقارير الفترة
الأصلية لا تتغيّر بأثر رجعي. إعادة ترحيل دفعة صفقة تنشئ قيداً جديداً دائماً
(`post_payment` يمرّر `idempotent=False` — قيود المرجع السابقة تبقى في الدفاتر، وحارس
التكرار هو قفل صف الدفعة + فحص `is_posted`). الاختبار المرجعي:
`tests/test_deal_payment_unpost_cycle.py`. **بيانات تاريخية:** دورات إلغاء قديمة
(أصل غير مرحّل + عكس مرحّل) أثرها معكوس الإشارة في التقارير المرحّلة — فحصها عبر
`payment_posting_diagnostics.py`.

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `tests/test_stage_machine.py` (133) | `stage` هو المصدر الوحيد؛ كل تقدّم آلي عبر الخدمة المحروسة |
| `tests/test_shipment_from_deals.py` (249) | صفقات → شحنة: تجميع CBM/KG، الشحن = rate×Σunit، التوزيع، الحواجز |
| `tests/test_freight_allocation.py` (134) | وحدة CBM/KG صريحة، إعادة الحساب عند التبديل، تسوية الأغورة |
| `tests/test_landed_cost.py` (344) | ثبات: Σ أسطر الفاتورة = قيمة الصفقة + الشحن المخصَّص + التخليص المخصَّص |
| `tests/test_clearance_import.py` (393) · `test_deal_total_and_freight_gate.py` (208) | استيراد الفواتير من التخليص · بوّابة «تكلفة الشحن مُثبتة» قبل الفوترة |
| `tests/test_import_payment_separation.py` (556) | فصل الاستحقاق عن الدفع (تخليص + نقل محلي) |
| `tests/test_shipment_freight_accrual.py` (307) · `test_receive_on_post_setting.py` (466) | استحقاق شحن الوكيل مستقلاً عن دفعاته · الاستلام عند الترحيل و GR/IR |
| `tests/test_purchase_receipt_visibility.py` | الباقي على البند وملخّص رأس الفاتورة — وتكافؤ رقمهما مع تقرير `outstanding` (وكان بلا اختبار) |
| `tests/test_receive_on_post_per_invoice.py` | خيار «الاستلام مع الترحيل» لكل فاتورة يتقدّم على الإعداد العام في الاتجاهين — ويعبر نقطة `pay/` كما يعبر الترحيل المجرّد |
| `tests/test_local_invoice_receive.py` | استلام الفاتورة المحلية للمخزن · مطابقة البنود بالمعرّف وحرّاس البند المستلَم |
| `tests/test_purchase_invoice_context_tabs.py` | التبويبات الثلاث؛ ومطابقة «قبل/بعد» لكشف الحساب (وأن أثر المسدَّدة = إجماليها لا صفر) |
| `tests/test_due_date_and_overdue.py` | الاستحقاق يُشتقّ من المهلة، و«متأخرة» بُعدٌ لا حالة، وأعمار الدائنة بالاستحقاق — على الجانبين |
| `tests/test_purchase_parity_extras.py` | الرقم التالي · النسخ لا ينسخ تاريخ المستند · توزيع FIFO يبدأ بالأقدم استحقاقاً |
| `tests/test_pi_cheque_voucher.py` | النقطة القديمة صارت تُنتج سند صرف مرحّلاً — لا `attached_cash_amount` بلا قيد |
| `tests/test_purchase_unpost_payment_guard.py` | سندٌ مرحّل يمنع إلغاء الترحيل، والسند النقدي التلقائي يُحرَّر معه بلا ازدواج عند إعادته |
| `tests/test_purchase_paid_is_computed.py` | «المدفوع» من السندات والقيد لا من نوع الفاتورة؛ والقائمة والتفصيل يتفقان |
| `tests/test_purchase_invoice_pay.py` | الدفع من داخل الفاتورة: سندٌ واحد، الفائض سلفة، التراجع الكامل عند الفشل |
| `tests/test_tenant_isolation.py` (75) | لا تسرّب صفقات بين الشركات؛ 400 بلا ترويسة الشركة |
| `tests/test_purchase_rfq.py` (ISSUE #112) | بندٌ بلا سعر ولا HS · قفل البنود عند أوّل إرسال (400) وقبول مستقبِل جديد · الحالات المسموحة/الممنوعة · عدّاد الردود المشتقّ · ترقيمٌ عند أوّل إرسال بلا حرق مسودّة مهجورة · عزل الشركة |
| `tests/test_use_purchase_orders_setting.py` (ISSUE #117) | مطفأً: الإنشاء المباشر و«تحويل عرض إلى طلبية» يُرفضان (400)، وقراءة/فتح أمرٍ قائم مقبولة بلا حجب · هجرة `0082` تُشعله لشركةٍ لها أمرٌ قائم فقط (وتتجاهل المحذوف ناعماً) وتترك غيرها مطفأً |
| `tests/test_purchase_rfq_award_and_comparison.py` (ISSUE #116) | `award/` ينتج فاتورة أو أمر شراء بحسب `use_purchase_orders` · يُرفض بلا `supplier` أو لموردٍ لم يردّ أو مرّتين · `comparison/`: بندٌ بلا تقديريّ يعود `None`، بندٌ لم يُسعّره موردٌ لا يُحتسَب صفراً في إجماليّه، توحيد العملات بسعر صرفٍ صريح، مورّدٌ لم يردّ بلا عمود، لا حقل شحنٍ في الاستجابة، عزل الشركة |
