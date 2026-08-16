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

**الواجهة في المرحلة 0:** «تحويل إلى صفقة» (شاشة عروض الاستيراد ومودال «من عرض» في الصفقات) يقرأ العرض ثم يفتح محرّر الصفقة معبّأً وغير محفوظ عبر `frontend_v2/utils/quotationToDraftDeal.ts` (`quotationToDraftDeal`)؛ المورد المبدئي والصنف المكتوب يدوياً يصلان بلا معرّف فيلزمان المستخدم بحلّهما قبل «حفظ» — لا شريك ولا صنف يُنشأ تلقائياً في مسار الصفقة.

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
| `SupplierQuotation` (:11) | `scope` (local/import), `status` (9 حالات), `supplier_draft_name` | `supplier`→Partner (nullable), `import_deal`/`local_invoice` OneToOne |
| `LogisticsDeal` (:409) | `ref_number`, `stage`, `shipping_workflow_status`, `total_amount`, `total_cbm`, `total_weight_kg`, `payment_status` | `tenant`, `partner`, `currency`, `source_quotation` OneToOne, `shipments` M2M |
| `LogisticsShipment` (:846) | `shipment_number`, `chargeable_unit` (cbm/kg), `freight_rate`, `total_shipping_cost_usd`, `freight_is_posted` | `deals` M2M عبر `LogisticsShipmentDeal`, `freight_journal`, `transit_journal` |
| `LogisticsShipmentDeal` (:1046) | `allocated_shipping_cost`, `extra_costs` | `unique_together (shipment, deal)` |
| `LogisticsClearance` (:1077) | `declaration_number`, `grand_total`, `exchange_rate` | `shipment` **OneToOne**, `customs_broker`, `lines`, `payments` |
| `LogisticsClearanceLine` (:1177) | `line_type`, `debit`/`credit`, `vat_percent` | `clearance`, `account` |
| `LocalShipment` (:1210) | `shipment_number` (LS-XXXX), `capitalize_to_inventory`, `exchange_rate`, `status` | `clearance`, `shipment` (كلاهما اختياري) |
| `PurchaseInvoice` (:1435) | `invoice_number`, `invoice_type` (local/international), `grand_total`, `import_*_rate` | `deal`, `shipment`, `clearance`, `partner`, `source_quotation` |
| `PurchaseInvoiceItem/Fee/Payment` (:1629/:1730/:1699) · `GoodsReceipt`/`Line` (:1811/:1883) | البنود والرسوم والدفعات · سند الاستلام | `invoice` · `movement`→StockMovement |
| `LogisticsPayment` (:746) · `PurchaseOrder` (:248) · `PurchaseSettings` (:1926) | دفعات الصفقة/الشحنة · الطلبية · `receive_on_post` | `deal`/`shipment`/`journal` · `tenant` |

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
def receive_purchase_invoice(invoice, *, lines, branch=None, user=None, movement_date=None,
                             receipt_date=None, notes='', supplier_ref='',
                             existing_receipt=None):                    # استلام فاتورة محلية للمخزن + قيد الاستلام
def create_standalone_goods_receipt(tenant, *, partner, lines, branch=None, user=None,
                                    receipt_date=None, notes='', supplier_ref='', receipt=None):  # GR/IR: بضاعة قبل فاتورتها
def void_goods_receipt(receipt, *, user=None):                          # عكس إرسالية واحدة (حركاتها وقيدها فقط)
def create_purchase_return(tenant, *, original_invoice, partner, return_date, lines, notes='',
                           invoice_number=None, currency=None, exchange_rate=None, user=None):    # مرجع شراء كمسودة
def post_purchase_return(invoice, *, user=None):                        # ترحيل المرجع: RETURN_OUT + قيد عكسي
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
| POST | `purchase-invoices/{pk}/post-to-accounting/` · `receive/` · `unpost/` · `returns/` | views.py:3400 / 2991 / 4047 / 3027 |
| GET | `import-journey/` · `reports/landed-cost/?shipment_id=` | views.py:4557 / 4588 |
| GET/POST | `goods-receipts/` · `goods-receipts/outstanding/` · `purchase-settings/current/` | views.py:4783 / 4935 / 5038 |
| — | باقي الموارد بالـrouter: `supplier-quotations/`, `purchase-orders/`, `payments/`, `supplier-payments/`, `local-shipments/` | urls.py:16-28 |

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
- **الفاتورة المرحّلة مُجمَّدة على قيمها المحفوظة**؛ غير المرحّلة تُعاد حسابها حيّاً عند القراءة (`landed_cost.py`).
- **العزل بالشركة إلزامي** (كل ViewSet يرث `BaseTenantViewSet`، `core/mixins.py`)، و**إلغاء الترحيل يحتاج** `import.doc.unpost` (views.py:760, 2104, 2176, 2275, 2296, 2593).

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
| `tests/test_tenant_isolation.py` (75) | لا تسرّب صفقات بين الشركات؛ 400 بلا ترويسة الشركة |
