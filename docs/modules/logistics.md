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
| `logistics/payment_posting.py` | قيد دفعة الاستيراد (صفقة/وكيل) بالشيكل من الدولار — بنّاءٌ واحد | 60 |
| `logistics/accruals.py` · `signals.py` | قيود الاستحقاق (تخليص/شحن/نقل) وإعادةُ حصّة الفاتورة الدولية إلى حساباتها · تقدّم المراحل تلقائياً وإعادة مزامنة إجماليات الشحنة | 434 · 261 |
| `logistics/domain/` | allocation 117 · shipment_builder 166 · stages 109 · inland 97 · invoice_gen 16 · import_settlement 155 | 660 |

**`domain/` مقابل `services.py`:** `domain/` طبقة نقية ومركزية لمسار الاستيراد وحده — `allocation.py` حسابٌ Decimal بلا ORM (largest-remainder، `Σ allocated ≡ total`)، `stages.py` جدول الانتقالات الوحيد الذي **يتحقّق ويكتب** معاً، `shipment_builder.py` فعل «صفقات → شحنة» ذرّياً، `invoice_gen.py` مجرّد re-export لنقاط `landed_cost` (16 سطراً، الدمج مؤجَّل لـM5)، و`import_settlement.py` تسويةُ الفاتورة الدولية: تكاليفها الأربع مقابل دفعاتها الأربع (3ب)، و`party_accruals.py` مستحقّاتُ المخلّص ووكيل الشحن والناقل ومتبقّيها من مصدرٍ واحد، و`overpayment_split.py` فصلُ الدفعة الزائدة عليها سندَ «تحت الحساب»، و`accrual_adjust.py` «تعديل الاستحقاق» بقيد فرق، و`landed_revaluation.py` تعديلُ تكلفة بضاعة الفواتير المرحّلة معه. أما `services.py` فطبقة تطبيقية عريضة تلمس ORM ومحاسبة ومخزون، وتخدم الشراء المحلي أساساً.

**ماذا يحسب `landed_cost.py`:** لكل صفقة على شحنة — قيمة البضاعة بالشيكل (دفعات مسدَّدة بأسعارها + المتبقي × سعر مُدخَل، `deal_total_ils:160`)، حصّتها من الشحن
الدولي (`deal_volume_share_on_shipment:438`، أساس CBM/KG)، حصّتها من حوض التخليص (`clearance_pool_ils:358`، أساس القيمة؛ **ضريبة الاستيراد خارجه** — مدخلاتٌ في 1105 يثبتها استحقاق التخليص، `is_vat_clearance_line`)، والنقل المحلي (`domain/inland.py:transport_pool_ils`).
ثم يوزّعها على بنود الصفقة (`compute_deal_invoice_lines:480`) بتسوية أغورة، ويبني الفاتورة (`build_purchase_invoice_row:785`)، ويعيد الحساب حيّاً عند قراءة الفواتير
غير المرحّلة (`compute_live_purchase_invoice_read_payload:1275`)، ويبني التتبّع العكسي بند→صفقة→شحنة→تخليص→نقل (`build_import_trace:1327`).

## الـModels
| Model | الحقول المفتاحية | العلاقات المهمة |
|---|---|---|
| `SupplierQuotation` (:11) | `scope` (local/import), `status` (9 حالات), `supplier_draft_name`, `entry_source` (`supplier_link`/`manual`/`public_link` — **ISSUE #122**، مختومٌ خادمياً وقراءةٌ فقط في المُسلسِل؛ **`public_link` هو «المسار الثالث» الذي تنبّأ به تعليق الحقل** وجاء مع مواصفة #147: عرضٌ وُلِد من اعتماد ردٍّ مجهولٍ على رابطٍ عامّ، وثقتُه ليست ثقةَ مورّدٍ مسمّى فلا يُدمَج فيه)، `general_note` (ملاحظة المورّد العامة على الطلبية كلّها — ISSUE #133) | `supplier`→Partner (nullable), `rfq`→`PurchaseRFQ` (nullable، #112 — **قابلٌ للكتابة منذ #122**)، `import_deal` OneToOne، `local_order`/`local_invoice` FK عكسي (بعد #112 — كانا OneToOne) |
| `SupplierQuotationLine` (`logistics/models.py`) | `seq`، `unit_of_measure`، `unit_price`، `line_total`، `supplier_note` (نصّ المورّد — `read_only_fields` يقفله عن كتابة المكتب، ISSUE #133)، `internal_note`/`internal_note_by`/`internal_note_at` (تعليقنا نحن، مسارٌ مستقلّ) | `quotation`، `product` (nullable) + `name_snapshot`، `rfq_line`→`PurchaseRFQLine` (nullable، **ISSUE #122**: نَسَبُ السطر إلى بند الطلبية — عليه تطابق المصفوفة لا على `seq`) |
| `PurchaseRFQ` (`logistics/models.py`) | `rfq_number` (NULL حتى أوّل إرسال)، `scope`، `status` (draft/sent/awarded/cancelled)، `reply_deadline` | `tenant`، `lines`، `recipients`، `quotations` (عكسي من `SupplierQuotation.rfq`) — **ISSUE #112**، مواصفة #108 |
| `PurchaseRFQLine` (`logistics/models.py`) | `quantity`، `unit_of_measure`، `specs`، `estimated_price` (داخليّ، nullable) — **بلا `unit_price` وبلا كود HS** | `rfq`، `product` (nullable) + `name_snapshot` (نمط `SupplierQuotationLine`) |
| `PublicSupplierQuoteRequest` (`logistics/models.py`) | **مواصفة #147** — منطقةُ انتظارٍ لردّ مجهولٍ على رابطٍ عامّ: `supplier_name` (حرٌّ **كما كُتب**، بلا تطبيع للتخزين ولا للعرض)، `supplier_email` (**إلزاميّ**)، `supplier_phone`، `email_verified_at` (يُخلَق فارغاً ولا يُكتَب — كي يُضاف رمزُ توثيقٍ لاحقاً بلا هجرةٍ ثانية)، `general_note`، `submitted_ip`، `status` (pending/approved/rejected). **لا يمسّ الدفاتر:** لا `Partner` ولا `SupplierQuotation` حتى الاعتماد | `rfq`→`PurchaseRFQ`، `share`→`docshare.DocumentShare` (SET_NULL — إبطالُ الرابط لا يحذف ردّاً وصل عبره)، `currency` (nullable = الأساس)، `approved_partner`/`approved_quotation` (SET_NULL، يُملآن معاً عند الاعتماد) |
| `PublicSupplierQuoteRequestLine` (`logistics/models.py`) | `unit_price`، `supplier_note`، و**لقطتان إلزاميّتان** `name_snapshot`/`seq_snapshot` | `request`، `rfq_line`→`PurchaseRFQLine` (**SET_NULL**): بندٌ يُحذَف بعد وصول الردّ لا يجوز أن يمحو سعراً أرسله إنسانٌ حقيقيّ — السطر يبقى **ظاهراً** ولا يُحوَّل عند الاعتماد وحسب |
| `PurchaseRFQRecipient` (`logistics/models.py`) | `sent_at`، `replied_at` | `rfq`، `supplier`→Partner، `share`→`docshare.DocumentShare` (nullable، **مسلوكة — ISSUE #115**: `_wire_rfq_recipient_shares` في `send/`/`recipients/`)، `quotation` OneToOne (nullable). المُسلسِل يكشف `share_url` (من `docshare.services.public_url`) و`share_is_live`/`share_expires_at`/`share_revoked_at` — **بلا `token` خام**؛ و`get_queryset` يجلب `recipients__share` مسبقاً |
| `LogisticsDeal` (:409) | `ref_number`, `stage`, `shipping_workflow_status`, `total_amount`, `total_cbm`, `total_weight_kg`, `payment_status` | `tenant`, `partner`, `currency`, `source_quotation` OneToOne, `shipments` M2M |
| `LogisticsShipment` (:846) | `shipment_number`, `chargeable_unit` (cbm/kg), `freight_rate`, `total_shipping_cost_usd`, `freight_is_posted` | `deals` M2M عبر `LogisticsShipmentDeal`, `freight_journal`, `transit_journal` |
| `LogisticsShipmentDeal` (:1046) | `allocated_shipping_cost`, `extra_costs` | `unique_together (shipment, deal)` |
| `LogisticsClearance` (:1077) | `declaration_number`, `grand_total`, `exchange_rate`, `broker_claim_number` (رقم مطالبة المخلّص — غير فاتورة المقاصة، ويُعدَّل وحده بعد ترحيل الاستحقاق: `views/clearance.py` — `POSTED_EDITABLE_FIELDS`) | `shipment` **OneToOne**, `customs_broker`, `lines`, `payments` |
| `LogisticsClearanceLine` (:1177) | `line_type`, `debit`/`credit`, `vat_percent` | `clearance`, `account`, `item_type` |
| `ClearanceItemType` (`logistics/models.py`) | `name`، `legacy_type` (`vat` ضريبة مدخلات، وغيره حسابُه الافتراضي إن لم يُحدَّد)، `is_active`، `sort_order` | `tenant`، `account` — **بنود المخلّص في إعدادات الشراء** (`clearance-item-types/`، التعديل بـ`purchase.settings.manage`؛ البذرة الستّة القياسية عند أوّل قراءة: `domain/clearance_items.py` — `ensure_clearance_item_types`). سطر التخليص الحامل له يأخذ نوعه وحسابه (`serializers/clearance.py` — `_sync_lines_from_cost_lines`، مفلتراً بشركة التخليص) |
| `LocalShipment` (:1210) | `shipment_number` (LS-XXXX), `capitalize_to_inventory`, `exchange_rate`, `status` | `clearance`, `shipment` (كلاهما اختياري) |
| `PurchaseInvoice` (:1435) | `invoice_number`, `invoice_type` (local/international), `grand_total`, `import_*_rate` | `deal`, `shipment`, `clearance`, `partner`, `source_quotation` **FK** (كان OneToOne — #112) |
| `PurchaseInvoiceItem/Fee/Payment` (:1629/:1730/:1699) · `GoodsReceipt`/`Line` (:1811/:1883) | البنود والرسوم والدفعات · سند الاستلام | `invoice` · `movement`→StockMovement |
| `LogisticsAccrualAllocation` (`logistics/models.py`) | `amount` (بعملة السند)، `amount_base` (بالأساس) | `payment`→`sales.SupplierPayment` (`logistics_allocations`)، وواحدٌ فقط (CheckConstraint) من `clearance` / `shipment` (استحقاق الشحن) / `local_shipment` |
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
def purchase_invoice_payment_summary(invoice):                          # ملخص الدفع من السندات المرحّلة فقط (+ الإشعارات المربوطة)
def purchase_invoice_note_totals(invoice) -> tuple[Decimal, Decimal]:    # (مدينة، دائنة) مرحّلة مربوطة — المدين مع المدفوع، والدائن على المستحق
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
def import_invoice_cost_shares(inv) -> Optional[Dict[str, Any]]:          # حصص الفاتورة من الشحن/التخليص/المحلي وأحواضها

# logistics/accruals.py — حصّة الفاتورة الدولية تعود إلى حسابات الاستحقاق
def import_invoice_accrual_credits(invoice, shares) -> List[dict]:     # أسطر دائن 5301/بنود التخليص/مصروف النقل

# logistics/domain/party_accruals.py — مستحقّات المخلّص/وكيل الشحن/الناقل (مصدرٌ واحد للمتبقّي)
def accrual_status(kind, obj, *, exclude_payment_journal_id=None) -> dict:  # {due, paid, allocated, noted, remaining, overpaid} بالأساس — noted: الإشعارات المدينة المربوطة، والدائنة تزيد due
def party_open_accruals(tenant_id, partner_id) -> list[dict]:            # FIFO بتاريخ قيد الاستحقاق
def suggest_accrual_fifo(tenant_id, partner_id, amount) -> list[dict]
def allocate_voucher_to_accruals(payment, allocations, *, user=None)     # ربطٌ بلا قيد، سندٌ مرحَّل فقط
def document_settlement(kind, obj, *, draft_due, draft_paid, rate=None)  # مدفوع/متبقّي/مقدَّم مسلسلَي التخليص والإرسالية
def document_voucher_rows(kind, obj, *, rate=None) -> list[dict]         # السندات الموزَّعة صفوفاً لتبويب «الدفعات» بعملة المستند
def shipment_label_of(kind, obj) -> str                                  # وسم الشحنة الدولية للمستحق
def journal_reference_shipment_labels(tenant_id, refs) -> dict           # (reference_type, reference_id) ← وسم الشحنة الحيّ — كشف الحساب
def journal_reference_accrual_links(tenant_id, refs) -> dict             # مرساة كل مستحق (LOGISTICS_CLEARANCE:<id> · LOCAL_SHIPMENT:<id> · SHIPMENT_FREIGHT_ACCRUAL:<shipment>) لقيده ودفعاته، والسندات الموزَّعة بمبالغها، ودفعة الصفقة ← فاتورتها — «ربط الفاتورة بسندها»
def allocated_base(kind, objs) -> Decimal                                # يضيفه 3ب إلى كل حوض
def accrual_journal_ids(kind, obj) -> list[int]                          # قيد الاستحقاق الأصلي + قيود تعديله (ACCRUAL_ADJUST_TYPE)
def note_journal_ids(kind, obj) -> list[int]                             # قيود الإشعارات المدينة/الدائنة المرحّلة المربوطة بالمستند
def party_on_account_summary(tenant_id, partner_id) -> dict              # {on_account, surplus} — مربّعا رأس كشف الدائن

# logistics/domain/accrual_adjust.py — «تعديل الاستحقاق» (بدل «تراجع عن الاستحقاق»)
def adjust_accrual(kind, obj, *, apply_changes, adjust_date=None, freight_rate=None, user=None, preview=False) -> dict
def difference_lines(current, target, description) -> list[dict]         # الهدف (بنّاؤو accruals.py) − الحالي (صافي القيد الأصلي وتعديلاته) لكل (حساب، طرف)

# logistics/domain/landed_revaluation.py — تكلفة بضاعة الشحنة تتبع تعديل الاستحقاق
def capture(tenant_id, shipment_id) -> list[InvoiceSnapshot]             # قبل تعديل المستند؛ يرفض فاتورةً مرحّلة متأخّرة أصلاً عن تكاليفها
def plan(snapshots) -> list[InvoicePlan]                                 # الفرق لكل بند ← مخزون / ت.ب.م / وسيط الاستلام
def apply(snapshots, *, adjust_date, user=None) -> list[InvoicePlan]     # قيد PURCHASE_INVOICE_LANDED_ADJ + تكلفة الطبقات والاستهلاك وحركات البيع

# logistics/payment_posting.py — دفعة وكيل الشحن (بلا صفقة)
def post_shipment_agent_payment(payment, *, box_account, user=None)      # Dr ذمّة الوكيل / Cr الصندوق — ذرّية، ValidationError ولا كتابة
def agent_payment_blockers(payment) -> list[str]                         # موانع الترحيل قراءةً (الأمر)

# logistics/domain/overpayment_split.py — الدفعة الزائدة على مستحقٍّ ← سند «تحت الحساب»
def split_incoming(kind, obj, amount) -> tuple[Decimal, Decimal]:       # (على المستند، الزائد) — لا فصل قبل ترحيل الاستحقاق
def create_on_account_voucher(*, tenant, partner, amount, ...)          # سند صرف مرحَّل بلا توزيع
def split_posted_overpayment(kind, obj, *, apply=False, user=None)       # للموجود: عكسٌ + إعادة ترحيل + سند (الأمر)

# logistics/domain/import_settlement.py — 3ب
def import_invoice_payment_breakdown(invoice) -> Optional[Dict[str, Any]]:  # {supplier|freight|clearance|local} + الحالة
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
| GET/POST · DELETE | `clearances/{pk}/attachments/` · `shipments/{pk}/attachments/` · `local-shipments/{pk}/attachments/` (و`…/attachments/{id}/`) | مرفقٌ اختياري (صورة أو PDF): مطالبة المخلّص · الشحن الدولي · الناقل — `core.mixins.DocumentAttachmentsMixin`، ويُرفق بعد الترحيل أيضاً |
| POST | `clearances/{pk}/adjust-accrual/` · `local-shipments/{pk}/adjust-accrual/` · `shipments/{pk}/adjust-freight-accrual/` | «تعديل الاستحقاق» — `{preview, date}` مع `cost_lines` / `amount` / `freight_rate`+`freight_exchange_rate`؛ المعاينة لا تكتب شيئاً (`domain/accrual_adjust.py`) |
| POST | `clearances/{pk}/post-to-accounting/` · `pay_from_cashbox/` | views.py:2249 / 2338 |
| POST | `purchase-invoices/preview-clearance-import/` · `import-from-clearance/` | views.py:3103 / 3179 |
| GET | `purchase-invoices/{pk}/trace/` | `trace` (views.py:3245) |
| POST · GET | `purchase-invoices/recalculate-landed-cost/` · `shipment-cost-drift/?shipment_id=` | **B-1**: الأوّل يحدّث مسودات الشحنة، ومع `auto_repost` يلغي ترحيل كل فاتورةٍ دولية مرحّلة عليها ويعيد احتسابها ويرحّلها **في معاملةٍ واحدة** — كلُّها مرحّلةٌ بأرقامها الجديدة أو 409 ولا يتغيّر شيء. الثاني قراءةٌ تسمّي الفواتير المرحّلة التي تأخّرت عن تكاليف شحنتها (`landed_cost.py` — `posted_invoices_cost_drift`) |
| GET | `purchase-invoices/{pk}/stock-movements/` · `supplier-ledger/` | تبويبا السياق — أثر الفاتورة على المخزن، وكشف حساب المورّد مرسوّاً عليها |
| GET/POST · DELETE | `purchase-invoices/{pk}/attachments/` · `attachments/{id}/` | تُحفظ **فوراً** لا مع الفاتورة، فيبقى الإرفاق ممكناً بعد الترحيل |
| GET · POST | `purchase-invoices/next-number/` · `purchase-invoices/{pk}/duplicate/` | الرقم التالي قبل الحفظ · نسخُ الفاتورة مسودّةً بلا ترحيلٍ ولا استلام — **والدولية لا تُنسخ (400)**: سعر بندها محمَّل ولا سعر مورّدٍ على البند، فنسخُها محليةً شراءٌ بسعرٍ لم يبعه المورد؛ والمحرّر يُخفي الزرّ |
| GET | `purchase-invoices/check-supplier-invoice-number/` (`partner`، `supplier_invoice_number`، `exclude`) | `check_supplier_invoice_number` (A2-2) — نفس الشركة والمورد والرقم (بلا حساسية حالة)، بلا المراجيع ولا الفاتورة نفسها. **تحذيرٌ قابل للتجاوز لا قيد**: `InvoiceForm` يسأل قبل الحفظ ويحفظ إن أكّد المستخدم |
| GET | `supplier-payments/suggest-fifo-allocations/?partner=&amount=` | اقتراح توزيع سند صرف على فواتير المورّد (الأقدم استحقاقاً أولاً) |
| GET | `supplier-payments/logistics-accruals/?partner=` · `suggest-fifo-accruals/?partner=&amount=` | مستحقّات الطرف اللوجستية المفتوحة (FIFO) · اقتراح توزيع مبلغ عليها |
| GET | `clearances/{pk}/payments/` · `local-shipments/{pk}/payments/` | دفعات المستند المباشرة **ومعها** سندات الصرف المرحّلة الموزَّعة عليه (`row_type: voucher_allocation`، `voucher_id`، `kind_label` «سند صرف — توزيع»، المبلغ بعملة المستند) — مجموعها = `amount_paid`. واستحقاق الشحن: `freight_voucher_rows` في `GET shipments/{pk}/` (بالدولار) |
| POST | `shipments/{pk}/pay_agent_from_cashbox/` | دفعة وكيل الشحن من الصندوق بكبسة: `amount` ($)، `usd_to_ils` و`cash_box_external_id` إلزاميان، `payment_date`، `notes` — تُنشأ مؤكّدةً وتُرحَّل في معاملة واحدة (`post_shipment_agent_payment`)، وفشلُ الترحيل لا يترك دفعة |
| GET | `supplier-payments/accrual-status/?kind=&id=` | حالة مستحقٍّ واحد (`accrual_posted`، `remaining`…) — مصدر تنبيه «سيُفصل X كدفعة تحت الحساب» في `ImportDocumentScreen` |
| POST | `supplier-payments/{pk}/allocate-accruals/` · `deallocate-accrual/` | توزيع سند صرف مرحَّل على `{kind: clearance\|freight\|local, id, amount}` · فكّ توزيعٍ واحد — ربطٌ بلا قيد |
| POST | `supplier-payments/{pk}/allocate/` · `deallocate/` | توزيع سند صرف على فواتير شراء · فكّ توزيعٍ واحد (`{"allocation": id}`) — ربطٌ بلا قيد، والمبلغ يعود «على الحساب» (`sales.services.deallocate_supplier_payment`) |
| POST | `purchase-invoices/{pk}/pay/` | `pay` — الدفع من داخل الفاتورة (نقد/شيكات/سلف المورّد)، صلاحية `purchase.payment.create` (+`purchase.invoice.post` مع `post_invoice`) |
| POST | `purchase-invoices/{pk}/post-to-accounting/` · `receive/` · `unpost/` · `returns/` | views.py:3400 / 2991 / 4047 / 3027 |
| GET | `import-journey/` · `reports/landed-cost/?shipment_id=` | views.py:4557 / 4588 |
| GET/POST | `goods-receipts/` · `goods-receipts/outstanding/` · `purchase-settings/current/` | views.py:4783 / 4935 / 5038 |
| POST | `purchase-rfqs/{pk}/send/` · `cancel/` · `award/` · `recipients/` · `duplicate/` | **ISSUE #112**: أوّل إرسال يقفل البنود ويخصّص الرقم؛ `recipients/` وحده مسموحٌ بعد الإرسال. **`award/`** (ISSUE #116) يحمل `supplier` إلزامياً — يقبل عرض الفائز دائماً، لكن ما بعده نطاقيٌّ (ISSUE #133): **شراءٌ محلّي** ينتج أمر شراء أو فاتورة بحسب `use_purchase_orders`، أمّا **الاستيراد** فيقبل العرض ويُغلق الطلبية **ويتوقّف** — `awarded_document` يعود `null`، والتحويل إلى صفقة يمرّ لاحقاً بمسار «تحويل إلى صفقة» على العرض المقبول (`PurchaseRFQViewSet`، `logistics/views/procurement.py`). **`duplicate/`** (ISSUE #112، فجوةٌ مُعادةُ الفتح) تنسخ طلبيةً مقفلةً مسودّةً جديدة — بنودُها كلُّها بما فيها `estimated_price`، **بلا مستقبِلين ولا روابط ولا رقم** (`TenantBook` لا يتحرّك حتى أوّل إرسال)، والأصلُ لا يُمَسّ؛ النَّسبُ سطرٌ في `notes` لا حقلٌ جديد |
| GET | `purchase-rfqs/{pk}/comparison/` | **ISSUE #116**: مصفوفة الموردين — صفٌّ لكل بند وعمودٌ لكل موردٍ ردّ فعلياً، بالعملة الأساسية، بلا حقل شحن. خطُّ الأساس `estimated_price` لا «أقل سعر» (ذاك داخل العرض الواحد وحده، #113). داخليّةٌ بحتة — لا `doc_type` لها في `docshare`. **ISSUE #122**: كلُّ عمودٍ يحمل `entry_source` (سعّره المورّد أم أدخلناه عنه)، والمطابقةُ صارت على `SupplierQuotationLine.rfq_line` — و`seq` سقوطٌ لعروضٍ لا نَسَبَ في أيٍّ من سطورها وحدها |
| — | باقي الموارد بالـrouter: `supplier-quotations/`, `purchase-rfqs/`, `purchase-orders/`, `payments/`, `supplier-payments/`, `local-shipments/` | urls.py |

## الاعتماديات
**يعتمد على:**
- `tenants` (models مباشرة) — `logistics/models.py` `from tenants.models import Tenant, Currency`؛ كل model يحمل `tenant` FK.
- `accounting` (models **و** services) — `logistics/views.py:47-55`: `post_journal`, `unpost_document`, `validate_fiscal_period`, `next_document_number`, `get_exchange_rate`, `create_audit_log`.
- `sales` (models) — `logistics/serializers/` يستورد `SupplierPayment`, `SupplierPaymentAllocation` من `sales.models`؛ و`logistics/views/` يستورد `SupplierPayment` ويعرضه عبر `SupplierPaymentViewSet`. **لا استيراد لداخليات `sales.serializers`/`partners.serializers` بعد اليوم** (عقد `no-cross-app-internals` بلا استثناء لـ`logistics` منذ 2026-09-17): رسالة شرط تاريخ استحقاق الشيك المشتركة بين سندي القبض والصرف تسكن `core/payments.py` (`CHEQUE_DUE_DATE_REQUIRED`).
- `partners` (models + signals): `models.py`, `views.py:42-43` · `inventory` (models + services): `models.py:4-5`, `views.py` · `core` (access/mixins/tenant_utils/activity/plans): `views.py:60-74`.
**يعتمد عليه:** `sales/services.py:3817,3906-3907` · `accounting/services.py:931,1013,1522` · `accounting/views.py:313,342,1355` · `accounting/serializers.py:75,129` · `inventory/services.py:447,681,941,997` · `inventory/serials.py` · `partners/views.py:75,142-144` · `after_sales` (اختبارات) · `import_file` (وحدة مرخّصة تقرأ الصفقة والشحنة اتجاهاً أُحادياً — لا FK ولا عمود منها في أي جدول هنا).

**الاستثناء الوحيد في الاتجاه المعاكس** — `logistics/views/reports.py` (`ImportJourneyViewSet.list`) يستورد `import_file.services` (`attach_file_progress`) **استيراداً كسولاً داخل حارس الترخيص**، فيُثري ملخّص رحلة الاستيراد بـ`file_progress` للشركة المرخّصة وحدها. بلا ترخيص الحمولة مطابقة حرفياً لما كانت عليه، و`logistics/import_journey.py` يبقى جاهلاً بالوحدة تماماً. تفصيل الوحدة في `docs/modules/import_file.md`.

## قواعد لا يجوز كسرها
- **كل انتقال مرحلة عبر `advance_deal_stage`** — لا `.update(stage=…)` مباشراً؛ حتى الـsignals تمرّ عبره (`signals.py:180-188`). جدول الانتقالات الوحيد في `domain/stages.py:24-34`.
- **الصفقة على شحنة واحدة كحد أقصى**: رفض صريح في `domain/shipment_builder.py:103-109` + `unique_together (shipment, deal)` (`models.py`).
- **`Σ allocated ≡ total` بدقّة الأغورة** في أي توزيع — استخدم `domain/allocation.py:reconcile` (:44) ولا تُقرِّب يدوياً.
- **سعر شحن > 0 على صفقة بلا CBM/KG مرفوض** (وإلا حصّتها صفر صامتة): `domain/shipment_builder.py:43-59`، ونفس الحارس في `views.py:1582-1588`.
- **لا فاتورة استيراد قبل**: إثبات تكلفة الشحن (`landed_cost.py`) + اكتمال دفع الصفقة بالدولار (`:1029`) + عدم تحويلها سابقاً (`:1018`).
- **المستند المرحّل لا يُعدَّل ولا يُحذف**: `_shipment_is_posted` (views.py:2044)، `_clearance_is_posted` (views.py:2228)، وحارس `transit_journal` في `set_freight` (views.py:1558-1562). **استثناءان للشحنة المرحّلة** (`views/shipments.py` — `perform_update`): دفعاتُ الوكيل، و**الوكيلُ نفسه ما دام استحقاقُ الشحن غير مرحّل** — شحنةٌ دخلت بضاعتُها قديماً (حركة `SHIPMENT`) بلا وكيل لا يُرحَّل استحقاقُها بغيره، و«إلغاء الترحيل» ليتاح يُخرج البضاعة (إنتاج SH-0013). بعد ترحيل الاستحقاق يقفله الحارسُ التالي.
- **بنود الفاتورة تُطابَق بالمعرّف لا تُحذف وتُعاد**: `PurchaseInvoiceSerializer._sync_items` — بندٌ بمعرّف يُعدَّل في مكانه، وبلا معرّف بندٌ جديد، والغائب عن الحمولة يُحذف؛ ومعرّفٌ من فاتورة أخرى يُرفض. الحذف الشامل السابق كان يُصفّر `received_quantity` (حقل للقراءة فقط فلا يعود في الحمولة) ويُسقط أسطر الإرسالية بالـCASCADE (`GoodsReceiptLine.item`) بينما تبقى حركات المخزون. **والواجهة شريكةٌ في العقد**: `InvoiceForm` يرسل `id` من `serverId` (`utils/mapPurchaseInvoiceDto.ts`) — بلا إرساله تعود المطابقة حذفاً وإعادة إنشاء بصمت.
- **البند المستلَم مُجمَّد فيما يعتمد عليه سند الاستلام**: `_guard_received_items` يرفض حذفه، أو إنقاص كميته عن المستلَم، أو تبديل منتجه أو سعره أو أرقامه التسلسلية — الحركة سُجّلت بمنتجه وسعره والوحدات تجسّدت به. الباقي مسموح (ملاحظات، بنود جديدة، زيادة الكمية) لأن الاستلام الجزئي حالة مشروعة، والمخرج عند اللزوم إلغاءُ الإرسالية (`DELETE goods-receipts/{id}` ⇐ `void_goods_receipt`, و`allow_edit_receipt=True` افتراضاً) — ما لم تكن بضاعتُها قد بيعت: `void_goods_receipt` يمرّ بحارس `inventory.services` (`_assert_layers_not_consumed_elsewhere`) نفسِه الذي يحرس إلغاءَ ترحيل الفاتورة، لأن حذفَ حركة الوارد يمحو طبقتها وصفوفَ استهلاك مبيعاتٍ لاحقة (CASCADE). ولا داخل فترةٍ مقفلة أو إقرارٍ ضريبيٍّ نهائيّ (`accounting.services` — `assert_dates_open_for_unpost`): الإلغاءُ يحذف القيدَ والحركات، فهو تعديلٌ على الفترة كإلغاء الترحيل. الفاتورة المرحّلة يمنعها حارس `perform_update`؛ وهذا يغطّي النافذة المتبقية — فاتورة صفرية القيمة استُلمت بلا قيد فبقيت غير مرحّلة (`services.py` — `gross > 0` وحده يُرحّل).
- **الفاتورة المرحّلة مُجمَّدة على قيمها المحفوظة**؛ غير المرحّلة تُعاد حسابها حيّاً عند القراءة (`landed_cost.py`).
- **B-1 — لا إلغاءَ ترحيلٍ ضمنيّ عند حفظ تكلفة**: حفظُ حقلٍ في شاشة الشحنة (CBM/KG/الحصة/سعر الشحن/التخليص/النقل/دفعات الوكيل) يحدّث المسودات وحدها ثم يقرأ `shipment-cost-drift/`؛ الفرقُ مع المرحّل لافتةٌ «تغيّرت تكاليف الشحنة» وزرٌّ صريح «أعد الاحتساب والترحيل» (`ImportDocumentScreen.tsx` — `handleRecalculateAndRepost`)، وحفظُ الصفقة (`DealForm.tsx`) ينبّه ولا يرحّل. **وإعادة الترحيل ذرّية ولا تترك نقديةً مسودة** (`views/invoices.py` — `recalculate_landed_cost`): إلغاء الترحيل يحرّر سند التسوية النقدية التلقائي، وإعادة الترحيل تبنيه مرّةً واحدة بالمبلغ الجديد؛ وأيُّ رفضٍ (فترة مقفلة، ضريبة، سندٌ يدويّ على الفاتورة) يعيد كلَّ شيءٍ إلى حاله المرحّل الأصلي.
- **«الاستلام مع الترحيل» يحكمه الإعدادُ العام، والفاتورةُ الواحدة تستثني منه** — `views/invoices.py` (`post_to_accounting`) يقبل `receive_on_post` في جسم الطلب فيتقدّم على `PurchaseSettings.receive_on_post`. إغفاله يُبقي السلوك القديم حرفياً. **ولا تسأل الواجهةُ إلّا حين يكون الإعدادُ مطفأً** — `receiveOnPostPrompt.tsx` (`receiveOnPostApplies`) يشترط `autoReceiveSetting` مطفأً؛ فمن ضبط شركته على الاستلام التلقائي أجاب مرّةً في الإعدادات، وسؤالُه عند كل ترحيلٍ يطلب تأكيدَ قرارٍ لا اتّخاذَه. والحوارُ للاستثناء (الاستلامُ على دفعات عادةً وهذه الفاتورةُ وصلت كاملة) لا للقاعدة. الخيار لحظةُ ترحيلٍ لا حقلٌ محفوظ: ما بعده تقوله `receipt_status` والإرساليات. **ويسري على `pay/` كذلك** (T-PAYFULL2): تلك النقطة ترحّل الفاتورة داخلها (`post_invoice`) بنداء `post_to_accounting` نفسها، فيمرّ الحقل من جسمها — ولولا ذلك لاختلف الأثر المخزنيّ باختلاف الزرّ الذي أطلق الترحيل، وصار الإعداد العام يقرّر وحده لأن المستخدم دفع بدل أن يرحّل.
- **الطلبية تتحوّل كاملةً مرّةً واحدة** (`PurchaseOrder.invoice` علاقةُ واحد-لواحد) — والتجزئة على مستوى **الاستلام** لا التحويل: طلبيةٌ واحدة ← فاتورةٌ واحدة ← إرساليات متعددة. هذا ما تفعله Odoo (backorder على سند الاستلام) وZoho (عدّة Purchase Receives للطلبية). ولذلك تحمل `PurchaseOrderSerializer` تقدّم استلام فاتورتها (`invoice_receipt_progress`) فلا تنتهي الطلبية عند «محوّلة إلى فاتورة» طريقاً مسدوداً. **لا تُدخِل «كمية محوَّلة» على سطر الطلبية** — تخلق معنىً ثانياً لـ«الباقي» (للفوترة مقابل للاستلام) وتعيد الالتباس الذي أُزيل.
- **الفاتورة الدولية تُستلَم كالمحلية** — `services.py` (`receive_purchase_invoice`) يقبلها **بعد ترحيلها** وحده (تكلفتها المستوردة تثبت به)، وترحيلُها يمرّ بوسيط GR/IR كالمحلية (`views/invoices.py` — `post_to_accounting`) فيسري عليها «الاستلام مع الترحيل» وسؤالُه ونافذةُ الاستلام والإرسالية؛ وتوزيعُ تكلفة الوسيط على بنودها بـ`landed_line_total_ils` لا بسعر الصفقة (`goods_clearing_unit_costs`). **الشحنة لا تُدخل مخزوناً عند «Cleared» بعد الآن** (أُزيلت إشارة `signals.py`)؛ حركاتُ `SHIPMENT` القديمة تُعدّ استلاماً للفاتورة عبر `sync_import_receipt_from_shipment_stock` (عند الإنشاء من التخليص، وبعد إلغاء الترحيل، وفي الهجرتين 0088/0089) — وحدُّ الصفقة في الملاحظة « |» بعدها **أو نهايةُ النصّ** (`legacy_shipment_deal_notes_q`): `backfill_stock` كتبها بلا فاصل ختامي، وفاتورةٌ كهذه تُرحَّل على المخزون مباشرةً بلا وسيط ويُستلَم باقيها بلا قيد. وإعادةُ الحساب مع إعادة الترحيل (`recalculate_landed_cost`) تحفظ الإرساليات بالمنتج قبل الإلغاء وتعيدها بتواريخها ومستودعاتها — لا بالإعداد.
- **ترحيل الفاتورة الدولية يُدائن المورد بحصّته وحدها** — `views/invoices.py` (`post_to_accounting`): حصّتها من الشحن الدولي والتخليص والنقل المحلي (`landed_cost.py` — `import_invoice_cost_shares`) دُيِّنت في مصاريفها عند الإفراج ودُوئن بها الوكيلُ والمخلّص والناقل، فتُدائَن تلك الحسابات بالحصّة موزَّعةً على أسطر الاستحقاق (`accruals.py` — `import_invoice_accrual_credits`) وتنتقل التكلفة إلى البضاعة مرّةً واحدة. مكوّنٌ بلا استحقاقٍ مرحّل يبقى على المورد كما كان (تحذيرٌ في السجل)، وفاتورةٌ تغيّرت تكاليف شحنتها بعد بنائها تُرفض حتى «إعادة حساب التكلفة» — بمقارنة التكاليف (الإجمالي الفرعي وكلفة كل سطر) لا الإجمالي، وهي نفسُها مقارنة لافتة التأخّر (`landed_cost.py` — `_import_row_drifted`)؛ فضريبة الفاتورة وخصمها لا يُقرآن «تغيّراً». **الفواتير المرحّلة قبل هذا لم يُعَد ترحيلها** — مورّدها ما زال دائناً بالإجمالي المحمَّل.
- **سند صرف المخلّص/وكيل الشحن/الناقل يُوزَّع على مستحقّاتهم اللوجستية** — `domain/party_accruals.py` + `LogisticsAccrualAllocation`: التخليص للمخلّص، استحقاق الشحن (`freight_journal`) للوكيل، الإرسالية للناقل؛ FIFO بتاريخ قيد الاستحقاق أو يدوياً من `VoucherAllocationModal` («توزيع تلقائي»). **المتبقّي مصدرٌ واحد من أسطر القيود الموسومة بالطرف بالأساس** (`accounting/api.py` (`journal_lines_party_net`)): المستحق = دائن الطرف في قيد الاستحقاق، والمدفوع = مدينه في قيود دفعات المستند نفسه المرحّلة، ثم يُطرح الموزَّع من سنداتٍ مرحّلة — فلا فرق عملة ولا تمييز للناقل بملاحظة الدفعة. التوزيع لسندٍ مرحَّل فقط، ويبقى عند إلغاء ترحيل السند ويُحتسب ما دام مرحَّلاً (كتوزيع الفواتير). وسقف السند واحد: `allocate_supplier_payment` تحسب الموزَّع على المستحقّات أيضاً فلا يُوزَّع السند مرّتين. سندٌ بلا توزيع = «دفعة تحت الحساب». 3ب يضيف `allocated_base` إلى حوض كل مكوّن.
- **«المتبقّي» على التخليص والإرسالية من الخادم** — `amount_paid`/`remaining_balance`/`advance_balance`/`payment_status` في `serializers/clearance.py` و`serializers/transport.py` من `party_accruals.document_settlement`: بعد ترحيل الاستحقاق من `accrual_status` (القيود **وسندات الصرف الموزَّعة**)، وقبله بنود المستند ناقص دفعاته المرحّلة. `ImportDocumentScreen` يقرؤها (`utils/voucherAllocation.ts` — `docSettlement`) للحقل والملخّصات وتعبئة مبلغ الدفع، ويعيد جلب التخليص بعد كل دفعة. كانت البنود ناقص الدفعات دائماً — في المتصفح والمسلسلين — فسندُ مخلّصٍ موزَّع على التخليص لا يُنقص «المتبقّي».
- **الشحنة تُعرف باسمها مع رقمها — وسمٌ واحد من الخادم** — `models.py` (`LogisticsShipment.display_label`): «SH-0017 — شحنة رقع»؛ الاسم (`display_name`) = `shipment_name`، وإلّا وصف صفقاتها المختصر (`short_name` ثم أول سطر من `description`، بـ«،»، ≤60 حرفاً)، وإلّا اسم مورّدها. والإرسالية `LocalShipment.display_label` = «LS-0003 · وسم شحنتها». يحمله `shipment_label` في مسلسلات الشحنة والتخليص والإرسالية والفاتورة الدولية ودفعات الوكيل/المخلّص/الناقل وتوزيعات السند (`logistics_allocations[].label`)، وتقارير الاستيراد وتكلفة الواردات — **الواجهة لا تركّبه**. أوصاف القيود **الجديدة** تحمله («استحقاق تخليص SH-0017 — شحنة رقع | حاييم»)، والقديمة لا تُعدَّل: كشف حساب الطرف يضيف لكل حركة `shipment_label` الحيّ من مستندها (`accounting/services.py` — `_attach_statement_shipment_labels` ← `party_accruals.journal_reference_shipment_labels`). القوائم تجلب الصفقات ومورّدها مسبقاً (`prefetch_related('deals__partner')`) — استعلامٌ ثابت للصفحة لا لكل صفّ؛ والبحث في قائمة الشحنات يطابق وصف الصفقات أيضاً.
- **تبويب «الدفعات» يعرض السندات الموزَّعة** — `views/clearance.py` و`views/transport.py` (`payments`) يُلحقان `party_accruals.document_voucher_rows` بالدفعات المباشرة، والشحنة `freight_voucher_rows`؛ كان التبويب يقرأ `LogisticsClearancePayment` وحدها فيبدو فارغاً تحت رأسٍ يقول «مدفوع» (سند #2459 على الإنتاج). صفّ السند لا يُحتسب لزرّ «تراجع عن ترحيل دفعات التخليص» ويفتح السند برابطه.
- **دفعة وكيل الشحن تُسجَّل وتُرحَّل بكبسة واحدة** كالمخلّص والناقل — `views/shipments.py` (`pay_agent_from_cashbox`) → `payment_posting.py` (`post_shipment_agent_payment`)، الخدمةُ نفسها وراء زرّ `post_agent_payment` القديم وأمر `post_pending_agent_payments`. الشاشة لا تحفظ دفعة وكيل بـPATCH قائمة الدفعات بعد الآن ولا خانة «مؤكّدة»، وصندوقها الافتراضي أوّلُ صندوقٍ نشط بالدولار (الافتراضي العام صندوق شيكل). **القديم** (مؤكَّدة بلا قيد — 9 على الإنتاج) يعرضه `management/commands/post_pending_agent_payments.py` (`--tenant N` قراءةً مع الموانع وتنبيهات السعر 3.6 والمبلغ < 1$ والوكيل الذي نوعه مورد) ويرحّل `--apply --box <external_id> --ids …` المختارَ وحده، كلٌّ في معاملته. **لا مسار لإلغاء ترحيل دفعة وكيل**: `unpost_payment_from_accounting` لدفعات الصفقة وحدها.
- **الدفعة الزائدة على تخليصٍ أو إرساليةٍ تُفصل «تحت الحساب»** — `domain/overpayment_split.py` من `pay_from_cashbox` (`views/clearance.py` لدفعة المخلّص، `views/transport.py` للناقل): إن كان الاستحقاق مرحَّلاً والدفعة بالعملة الأساسية، تُسجَّل على المستند بمتبقّيه (`party_accruals.accrual_status`) والزائد سند صرفٍ مرحَّل للطرف نفسه «دفعة تحت الحساب — زيادة دفعة <المستند>» بنفس التاريخ والصندوق، **بلا توزيع ولا استهلاك تلقائي** — يوزّعه المستخدم لاحقاً. مستندٌ مسدَّد ⇒ الدفعة كلّها سند (`payment: null` في الردّ). الدفتر نفسه: Dr ذمّة الطرف / Cr الصندوق بالمبلغ كلّه على قيدين. الدفعة المقدّمة **قبل** ترحيل الاستحقاق تبقى على مستندها (قرار 2026-07-19)، والعملة الأجنبية ودفعات الوكيل بالدولار خارج الفصل (فرق الصرف يجعل الزائد رقماً غير مستقرّ). الواجهة تسأل قبل الحفظ بالمتبقّي من `accrual-status/`. **والموجود** يُصلحه `management/commands/split_logistics_overpayments.py` (`--tenant N`، تقرير افتراضاً، `--apply`): يعكس قيد أحدث دفعة (`reverse_journal` بمرجع `*_SPLIT_REVERSAL` — لا حذف) ويعيد ترحيلها بالمستحق (`*_SPLIT`) وينشئ السند بالزائد، ذرّياً لكل دفعة مع `AccountingAuditLog`؛ idempotent لأنّ لا زائد بعده. يترك ويذكر: قيداً مركّباً (صندوق FIFO)، أو زائداً أكبر من أحدث دفعة، أو استحقاق شحن. **و`unpost` التخليص يحذف قيدَي الفصل مع قيد الدفعة** — حذفُ الأصل وحده كان سيُبقي عكسه وإعادة ترحيله بأثرٍ وهمي.
- **حالة دفع الفاتورة الدولية = تكاليفها الأربع مقابل دفعاتها الأربع** — `domain/import_settlement.py` (`import_invoice_payment_breakdown`)، حقل `import_payment` في قائمة الفواتير وتفصيلها: المورد ← دفعات الصفقة المرحّلة + سندات الفاتورة؛ الشحن ← دفعات الوكيل؛ التخليص ← دفعات التخليص؛ المحلي ← دفعات الإرساليات (ودفعات الناقل على التخليص حين يكون مصدرَ النقل). المشتركة تُوزَّع على **كل** صفقات الشحنة بأوزان تكلفتها عبر `distribute_by_weights` فتُنسب الدفعة مرّةً واحدة؛ ومكوّنٌ سُدِّد حوضُه كلُّه مسدَّدٌ في كل فاتورة (لا «جزئية» بأغورة). **أمّا ملخّص الدفع المعتاد (`purchase_invoice_payment_summary` ونسخته SQL) فجانبُ المورد وحده** للدولية: المستحقّ ما دائنه به قيدُها (`import_invoice_ap_credit`) والمدفوعُ يشمل دفعات صفقتها (`import_deal_payments_ap_debit`) — فسندُ المورد وأعمارُ الذمم لا تتجاوز حصّته. **وكلاهما بالأساس (`base_debit`/`base_credit`) لا الاسمي**: قيد دفعة الصفقة دولارٌ اسمي بسعرها، فالاسميّ يُظهر «مدفوع 690» لصفقةٍ سُدِّدت كاملةً بـ2,235.60 ₪. فلترُ «حالة الدفع» في الخادم يقرأ جانب المورد.
- **كل سطر ذمّةٍ لطرفٍ أجنبيّ يحمل دولاره (`JournalLine.amount_currency`)** — دفعة الاستيراد (`payment_posting.py` — `build_usd_payment_journal`: قيدٌ بالدولار يملؤه `save`، وفرعا صندوق FIFO والأرشيف بالشيكل يمرّرانه صراحةً)، واستحقاق الشحن (`accruals.py` — `post_freight_accrual`: `total_shipping_cost_usd`)، وسطر مورد الدولية (`views/invoices.py`: مبلغ الصفقة `total_amount`) ومرتجعها بنسبته (`services.py` — `_international_return_split`). منه كشف الطرف بالدولار. **القديم**: `management/commands/backfill_foreign_party_currency.py` — قراءةٌ افتراضاً (ما سيُعبَّأ لكل نوع، وما بلا مصدر، ورصيد كل طرفٍ بالدولار)، و`--apply` يكتب ذرّياً عبر `accounting.services.set_lines_amount_currency` بلا مسّ سطرٍ معبّأ. المصادر: قيدٌ بعملةٍ أجنبية ⇒ الاسميّ؛ `LOGISTICS_PAYMENT(_UNPOST)` ⇒ دولار الدفعة بإشارة السطر (الخاطئ وعكسه والمصحَّح يتعادلون) — **والمحذوفة ليّناً** (`all_objects`: قيداها باقيان)، والمحذوفة نهائياً بلا صفّ ⇒ الاسميّ دولاراً بشرط قيدٍ بعملة الأساس بسعر 1 على صفقة أرشيف (`payment_posting.archive_deal_ids`: المسمّاة في وصف القيد «صفقة: …»، وإلّا فكلّ صفقات الطرف أرشيف)؛ `SHIPMENT_FREIGHT_ACCRUAL` ⇒ الشيكل ÷ `freight_exchange_rate`؛ الدولية ومرتجعها ⇒ مبلغ الصفقة بالنسبة؛ `LOGISTICS_DEAL` ⇒ الرقم نفسه؛ `JOURNAL_REVERSAL` ⇒ سالب الأصل. غيرها يبقى NULL ويُذكر (لأطرافٍ لها نشاطٌ دولاريّ وحدها). **يُطبَّق على الإنتاج بموافقة المالك وبعد نسخة احتياطية.**
- **دفعة الاستيراد (`LogisticsPayment`) بالدولار دائماً وتُرحَّل بـ`amount × usd_to_ils`** — `payment_posting.py` (`build_usd_payment_journal`) بنّاءٌ واحد لدفعة الصفقة (`views/deals.py` — `post_payment`) ودفعة الوكيل (`payment_posting.py` — `post_shipment_agent_payment`)، وقيمتها بالشيكل من `landed_cost.py` (`payment_ils`) التي تحسب بها الفاتورةُ الدولية تكلفةَ البضاعة. السطر دولارٌ اسمي بسعر الدفعة (أو أسطر شيكل بسعر 1 من صندوق FIFO) — لأن `JournalLine.save` يضرب السطر بسعر القيد فتمريرُ الشيكل مع سعر الدولار يحوّل مرّتين. **لا حقل عملة على الصفقة**: `currency` و`currency_rate` أُزيلا من `LogisticsDeal` (`migrations/0092_remove_deal_currency.py`) — كانا ILS على كل صفقات الإنتاج وهي بالدولار؛ **والعرضُ كذلك** (قرار المالك: الخيار ٢): `models.py` (`DEAL_CURRENCY_CODE`) مصدرُ عملة الصفقة في ورقة المورّد (`docshare/documents/purchase_docs.py` — `build_logistics_deal`) وتقرير التكلفة المستوردة (`views/reports.py` — `_build_landed_cost_summary`) ومرشد الاستيراد (`import_journey.py`). القديم يُكشف ويُصحَّح بـ`management/commands/audit_deal_payment_currency.py` (قراءة افتراضاً؛ `--apply --groups a,c,agent` يصحّح المختار — صفقاتٌ بفاتورة دولية مرحّلة، وبلا فاتورة، ودفعات الوكيل — بقيدٍ عكسي ثم إعادة ترحيل على نفس الحسابين؛ الأرشيف `b` ممنوع). **صفقات الأرشيف** (`payment_posting.py` — `archive_deal_ids`: قيد LOGISTICS_DEAL مرحّل بلا فاتورة دولية مرحّلة، تعريفٌ واحد يقرؤه الأمر والترحيل): قيد الصفقة ودفعاتها بالرقم الدولاري بسعر 1، فـ`build_usd_payment_journal` يعيد ترحيل دفعتها بنفس الوحدة (`_archive_payment_journal`) — إلغاء ترحيلٍ ثم إعادته يعيد القيد كما كان — ويرفض دفعةً لم تُرحَّل قط عليها (`ARCHIVE_FIRST_POST_MESSAGE`). **وفاتورتها الدولية للاطلاع فقط**: `payment_posting.py` (`live_archive_deal_journals`) — قيد LOGISTICS_DEAL مرحّل لم يعكسه JOURNAL_REVERSAL، **أيّاً كانت فاتورتها** (بخلاف `archive_deal_ids`) — يقفل ترحيلها في نقطةٍ واحدة (`assert_invoice_not_archive_locked` في `views/invoices.py` — `post_to_accounting`، ومنها `pay/`)؛ وإعادةُ ترحيل فواتير الشحنة (`recalculate_landed_cost`) تتخطّاها قبل إلغاء ترحيلها وتعيد السبب في `reconciliation.skipped_archive`. والسيريالايزر يعرض `is_archive_locked`/`archive_lock_reason` للصفحة باستعلامين (`serializers/invoices.py` — `ArchiveLockListSerializer`)، فزرّا «ترحيل» و«حفظ وترحيل» معطّلان بتلميح السبب وشارة «أرشيف — للاطلاع» في القائمة. المرتجع والتعديل والطباعة كما هي. وسعر دفعتها المرحّلة (`usd_to_ils` وحده) يُصحَّح بلا إلغاء ترحيل (`views/deals.py` — `update_payment`، بصلاحية إلغاء الترحيل وسجلّ تدقيق)؛ القيد ورصيد المورد لا يتغيّران، ويتغيّر ما يُحسب من السعر: قيمة البضاعة بالشيكل لفاتورة دولية تُنشأ لاحقاً (`landed_cost.py` — `preview_landed_import`، `build_purchase_invoice_row`)، وعمولات التحويل بالشيكل، وأوزان توزيع النقل المحلي (`domain/inland.py`)، وتقرير التكلفة المستوردة؛ وعمود الفرق في المجموعة (ب) من الأمر. الواجهة: زرّ «تعديل السعر» في سجل مدفوعات صفقة أرشيف (`frontend_v2/components/forms/deal-parts/DealPaymentList.tsx`، والحقل `is_archive` على الصفقة). **والسعر إلزاميٌّ عند الترحيل**: `usd_to_ils` بلا قيمة افتراضية (NULL = لم يُدخِله أحد؛ كانت 3.5 تُحفظ صامتةً — 101 من 137 على الإنتاج)، و`build_usd_payment_journal` ترفض الدفعة بلا سعر موجب (`usd_rate_entered`) وتُدرجها `payment_posting_diagnostics.py` (`collect_auto_posting_blockers`) مانعاً. أمّا `landed_cost.py` (`payment_usd_rate`) فتُبقي 3.5 احتياطاً للعرض والتقديرات وحدها — لا تُرحِّل. الواجهة لا ترسل سعراً لم يُدخَل: `frontend_v2/utils/paymentRate.ts` (`usdRateForPayload`) يحذف المفتاح في مُحوِّلَي الصفقة والشحنة و`ImportDocumentScreen`، وحقلُ سعر استحقاق الشحن فيها يبدأ فارغاً (كان 3.6 معبّأة) ولا يُرحَّل قبل إدخاله، وبعد الترحيل يعرض السعرَ المرحَّل من الشحنة. والأسعار المشبوهة (بلا سعر، 3.5 بالزبط، خارج 3–4.5) يعرضها `audit_deal_payment_currency --rates` قراءةً فقط.
- **الاستيراد من التخليص يمرّ بحرّاس الإنشاء نفسها** — `views/invoices.py` (`import_from_clearance`): صلاحية `purchase.invoice.create` وحدّ الخطة والوصول للاستيراد، وسجلّ نشاطٍ لكل فاتورة عبر `_log_invoice_created` التي يقرؤها `perform_create` أيضاً؛ وتخليصٌ من شركةٍ أخرى 404 لا 500. كانت كلّها تُتخطّى.
- **«ما يخصّ المورد» من الفاتورة الدولية حصّتُه لا إجماليها** — `services.py` (`annotate_purchase_supplier_share`، و`_import_ap_credit_subquery` التي تقرؤها القائمة أيضاً): ما دائن به قيدُها المورد، ولغيرها `grand_total`. منها «المشتريات حسب المورد» و«سجل فواتير الشراء» (`core/reports/purchases.py`، وفيه عمود «التكلفة المحمَّلة» مستقلّاً) و«إجمالي المشتريات» في كرت الطرف، و«آخر سعر شراء» (`core/pricing.py` — `_international_supplier_ratios`: المحمَّل × الحصّة ÷ الإجمالي، لأن `landed_cost.py` يوزّع البضاعة واللوجستيات على البنود بالأوزان نفسها). «أقل شراء»/السعر التقديري ما زالا من السعر المحمَّل.
- **«تعديل الاستحقاق» لا يلغي قيداً** — `domain/accrual_adjust.py` من `adjust-accrual/` (التخليص والإرسالية) و`adjust-freight-accrual/` (شحن الوكيل): المستند يُعدَّل، ثم يُبنى استحقاقه من جديد ببنّائي الترحيل الأوّل نفسيهما (`accruals.py` — `clearance_accrual_lines` · `local_shipment_accrual_lines` · `freight_accrual_lines`) ويُطرح منه صافي القيد الأصلي وكل تعديلٍ سابق لكل (حساب، طرف)، والفرق وحده قيدٌ بنوع `ACCRUAL_ADJUST_TYPE` (`LOGISTICS_CLEARANCE_ADJUST` · `SHIPMENT_FREIGHT_ACCRUAL_ADJUST` · `LOCAL_SHIPMENT_ADJUST`) بالعملة الأساسية ومرجعُه المستند، و`amount_currency` بفرقه — وحين يعاكس فرقُ الدولار فرقَ الشيكل (سعر صرفٍ جديد) يُرحَّل للمفتاح سطرا عكسٍ وإعادة. لا فرق ⇒ رفض. المستحق في كل مكان = الأصلي + تعديلاته (`party_accruals.accrual_journal_ids`)، و«إلغاء الترحيل» الكامل يحذف التعديلات معه. **سعر الشحن بعد ترحيل استحقاقه لا يُغيَّر من `freight/`** (`set_freight` يرفض) — من «تعديل الاستحقاق» وحده، والواجهة تقفل حقوله.
- **تكلفة البضاعة تتبع تعديل الاستحقاق** — `domain/landed_revaluation.py` (سابقةُ Odoo landed costs: الباقي على المخزون والمبيع على التكلفة، بقيدٍ لا بحذف): قبل التعديل تُلتقط حصص الفواتير الدولية المرحّلة على الشحنة (`import_invoice_accrual_credits`)، وبعده فرقُ كل بند (`landed_line_total_ils` الجديد − المخزَّن) يُقسَم لكل منتج: **الباقي في المخزن** على حساب المخزون وتكلفة الطبقة (تتبع التحويل بين المستودعات إلى طبقة الوجهة)، و**المبيع** على تكلفة المبيعات مع تكلفة صفّ الاستهلاك وحركة البيع (قيدٌ واحد، لا عكس لفواتير البيع)، و**غير المستلَم** على وسيط الاستلام إن كانت الفاتورة تستعمله فيُستلَم لاحقاً بالتكلفة الجديدة. قيدٌ بنوع `PURCHASE_INVOICE_LANDED_ADJ` مرجعه الفاتورة، ثم تُحدَّث أرقام الفاتورة المخزَّنة و`avg_cost`، وتُعاد المسودات (`recalculate_landed_for_shipment`). فاتورةٌ متأخّرة أصلاً عن تكاليفها تمنع التعديل (أعد احتسابها أولاً)، وفاتورة الأرشيف تُتخطّى. `open_goods_clearing` يحسب قيد التعديل، وإلغاء ترحيل الفاتورة يحذفه معها. **حدّ معروف:** إلغاء ترحيل بيعٍ بعد التعديل يُرجع الكمية بتكلفة الطبقة الجديدة وقيدُ التكلفة الأصلي بالقديمة. والصرف غير البيعي (إتلاف، مرتجع شراء) يُحمَّل على تكلفة المبيعات، وبضاعةٌ دخلت بحركات `SHIPMENT` القديمة يُعدَّل حسابها لا طبقاتها.
- **«فائض» غير «تحت الحساب»** — `accrual_status`: `due_original` (القيد الأصلي وحده) و`surplus = min(overpaid, max(due_original − due, 0))` — ما دُفع زائداً **لأن الاستحقاق نزل**؛ والباقي من الزائد دفعة تحت الحساب (`overpayment_split` يفصل `overpaid − surplus` وحده). `party_on_account_summary` يجمع لكل دائن: السندات غير الموزَّعة + الزائد غير الفائض = «دفعات تحت الحساب»، والفائض وحده — يعرضهما كرت الطرف (`partners/views.py` — `on_account_payments` · `accrual_surplus`) مربّعين فوق كشف الحساب، والرصيد الكلّي لا يتغيّر.
- **مستحقّات المخلّص والوكيل والناقل في التقارير والكرت** — `domain/party_accruals.py`: `tenant_open_accruals` (متبقّي كل مستحقٍّ مرحّل في الشركة) يغذّي أعمار الذمم الدائنة فيطابق مجموعُها الدفترَ، و`party_accrued_total` (مجموع دائن الطرف في قيود الاستحقاق باستعلامٍ واحد) «إجمالي المستحقّات» في كرته، و`shipment_id_of` رابطُ صفّ المستحق إلى شحنته.
- **صفقةٌ على شحنةٍ واحدة، ففاتورةٌ واحدة تحمل دفعاتها** — `import_deal_payments_ap_debit` و`list_deal_paid` ينسبان دفعات الصفقة كلّها لفاتورتها؛ لا ازدواج لأن الربط الثاني مرفوض (`views/shipments.py` — `add_deal`، و`shipment_builder.py`) والاستيراد الثاني للصفقة مرفوض (`landed_cost.py` — `import_invoices_from_clearance`).
- **مرتجع الفاتورة الدولية يعكس قيدها بنسبته لا بالإجمالي المحمَّل** — `services.py` (`_international_return_split`): سعر بند الدولية محمَّلٌ (`landed_unit_price_ils`) والفاتورة دائنت المورد بحصّته وحدها وحساباتِ الشحن والتخليص والنقل بحصصها؛ فالمرتجع بالنسبة f = قيمته المحمَّلة ÷ بضاعة الفاتورة يدين كلَّ سطرٍ دائنٍ في قيدها بـf× (المورد وحسابات الاستحقاق) ويدين المخزونَ وض.المدخلات بـf×. نوعُه نوعُ الأصل (دولية)، وسعرُ البند سعرُ الأصل مهما أُرسل، و`grand_total` حصّةُ المورد، ويُرفض قبل ترحيل الأصل. كان يدين ذمّة المورد بالمحمَّل كاملاً — حصص الوكيل والمخلّص ليست دَيناً عليه. المحرّر يشرح ذلك (`frontend_v2/components/sales/PurchaseReturnEditor.tsx`، `international-return-note`).
- **حذف الشحنة يفكّ صفقاتها أو يُرفض** — `domain/shipment_builder.py` (`release_shipment_for_delete`) من `destroy` الشحنة: يرفض إن كان عليها استحقاق شحن أو دفعة وكيل مرحّلة، أو تخليصٌ باستحقاق أو دفعة مرحّلة، أو صفقةٌ تجاوزت التخليص؛ وإلا يحذف التخليص غير المرحّل (حذفاً فعلياً كشاشة التخليص — النموذج بلا حذف ناعم) ويفكّ الروابط. **وفكّ أي ربط** (`remove_deal` أو الحذف) يعيد الصفقة `in_shipment` بلا ربطٍ حيّ إلى `ready_to_ship` (`signals.py` — `return_unlinked_deal_to_ready`). والشحنة المحذوفة لا تقبل استحقاقاً ولا دفعة (`accruals.py` — `assert_shipment_alive`، ودفعة التخليص في `views/clearance.py` — `pay_from_cashbox`): التخليص لا يُخفى مع شحنته.
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
  بالكامل لا يدخلها، والمستوردة غير المرحّلة لا تُعبَّأ (تُستلَم بعد ترحيلها).
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
- **الإشعار المدين/الدائن المربوط تسويةٌ على المستحق** (`sales.CreditDebitNote`، القاعدة في `docs/modules/sales.md`): مرحَّلاً على تخليصٍ أو إرساليةٍ أو استحقاق شحن يدخل `accrual_status` بقيوده (`note_journal_ids`) — صافي سطر الطرف موجبٌ (مدين: خصمٌ أو مطالبة) يُطفئ المتبقّي كالدفع (`noted`)، وسالبٌ (دائن: مبلغٌ إضافيّ له) يزيد `due` — فالكرت والتوزيع وFIFO والأعمار وفصل الزائد تقرؤه كلّها من الموضع الواحد، وكشف الحساب يُرسيه على المستحق (`journal_reference_accrual_links`). وعلى فاتورة الشراء: `purchase_invoice_note_totals` في الملخّص وتوأمه SQL (`note_total` في `annotate_purchase_invoice_payment_summary`) — المدين مع المدفوع والدائن على المستحق، والقاعدتان لا تفترقان.
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
- **وثلاثةُ حقولٍ وهميّةٍ في وجه مستند الشراء** (نفسُ العطب من الجهة المقابلة):
  لوحةُ `KitDocumentView` في `InvoiceForm.tsx` كانت تقرأ `formData.supplierName`
  و`formData.journalId` و`formData.exchangeRate` — **ولا واحدٌ منها حقلٌ على
  `Invoice`**. فسطرُ «المورد ← الاسم» يعرض «—» في كلّ فاتورة، وصفّا «قيد اليومية»
  و«سعر الصرف» لا يُرسَمان أبداً. صار الاسمُ `headerSupplierName` (نفسُ ما يعرضه
  حقلُ المورّد في المحرِّر) والقيدُ `glPurchaseReceiptJournalId` (يكتبه المُحوِّلان
  من `journal_id_display`). **و`tsc` لا تحرس هذا الباب أصلاً**: `formData` تعود
  `any` لأنّ `@types/react` غيرُ مثبَّتةٍ في المستودع، فقراءةُ حقلٍ وهميٍّ تمرّ
  كما تمرّ الحقيقيّة — والحراسةُ صارت في
  `core/tests/test_purchase_invoice_form_fields.py` يقارن كلَّ قراءةٍ بحقول
  `types/invoice.ts` نفسِها.
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
- **استحقاقُ النقل المحلي يَسِم ذمّةَ الناقل وحدها** — `accruals.py` (`post_local_shipment_accrual`): سطرُ المصروف (5305) كان يحمل الناقل فيُلغي دائنَه في كشفه (إنتاج: قيد #10961). القديمُ تُصلحه الهجرة `0090_untag_local_shipment_expense_partner`. استحقاقا التخليص والشحن الدولي سليمان أصلاً.
- **دفعُ الاستيراد يَسِم سطرَ الذمة وحده**: `partner_posted_balance` يجمع كلَّ أسطر
  الطرف بلا فلتر حساب، فسطرُ الصندوق/البنك موسوماً يُلغي مدينَ الذمة — الدفعُ لا
  يُنقص الرصيد، بل تنقلب إشارتُه فيظهر المورّدُ مديناً للشركة. كان يقع في
  `logistics/views/clearance.py` (`pay_from_cashbox`) وفي فرع الحساب العاديّ من
  `logistics/views/shipments.py` (`post_agent_payment`) — وفرعُ FIFO فيه سليمٌ
  أصلاً فصار الفرعان مرآةً واحدة. القديم يُصلحه
  `python manage.py fix_purchase_partner_tags` (يشمل أنواعَ الاستيراد منذ
  2b5693e؛ التفصيل في `docs/modules/accounting.md`).
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
  حتى فعل `send/` — مسودّة مهجورة لا تحرق رقماً). **وتسلسلٌ مستقلّ بادئةً
  ورقماً للاستيراد** (ISSUE #133): `IRFQ-` بدل `RFQ-` — كانا يتشاركان
  عدّاداً واحداً فتُسقط طلبيةُ استيرادٍ واحدة تُرسَل بين طلبيتين محلّيّتين
  رقمَ الثانية منهما؛ الشراء المحلّي يبقى على مفتاحه وبادئته القديمين
  حرفياً بلا إعادة ترقيم. «وردت عروض» عدّادٌ مشتقّ
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
  النهائية). **`award/` يحمل `supplier` إلزامياً** — يحسم أيّ ردّ
  (`SupplierQuotation`) فائزٌ ويقبله (`STATUS_ACCEPTED`) دائماً، ثم يتفرّع
  بحسب نطاق الطلبية (ISSUE #133، قرار المالك 2026-09-04): **شراءٌ محلّي**
  يمرّ حرفياً بمسار قبول عرضٍ محلّيّ يدويّ
  (`convert_local_quotation_to_order`/`_invoice`) — **لا منطق ترحيل جديد**،
  تركيبُ خدمات قائمة وراء مفتاح `use_purchase_orders` (#117) وحده؛
  **استيرادٌ** يقبل العرض ويُغلق الطلبية **ويتوقّف هنا بلا تحويل** — كلتا
  دالّتَي التحويل محلّيّتان فقط بحكم `SupplierQuotation.scope`، وكانت
  المكالمة قبل هذه التذكرة تُرفَض 400 بعد تأكيدٍ يقول «لا رجعة» — زرٌّ ميتٌ
  بلا اختبارٍ واحد يغطّيه. التحويل إلى صفقة استيراد يمرّ لاحقاً بمسار
  «تحويل إلى صفقة» القائم أصلاً على العرض المقبول — صفقةٌ تحتاج شحناً
  وتخليصاً وتكلفةً مستوردة لا تُولَد من ضغطة واحدة. مورّدٌ لم يردّ بعد لا
  عمود له في المصفوفة أصلاً (فراغٌ لا يُفسَّر خطأً كرفض).
- **ISSUE #122 — المورّدُ الذي سعّر هاتفياً: عرضٌ يُولَد من الطلبية لا نافذةٌ
  ثانية** (قرار المالك 2026-09-04). لا نقطةَ API جديدة ولا نموذجَ تسعيرٍ
  مستقلّ: يُفتَح **محرِّرُ العروض نفسُه** عرضاً جديداً غيرَ محفوظ، مُعبَّأً
  ببنود الطلبية وكمياتها وبأسعارٍ فارغة — فالتسعيرُ الجزئيّ (يُحذَف سطرُ ما
  لا يحمله المورّد) واختيارُ العملة وسعرِ الصرف والتصحيحُ اللاحق كلُّها تسقط
  من المحرِّر القائم. الذي كسبته القاعدةُ شيئان لا ثالث لهما: **`rfq` صار
  قابلاً للكتابة** على `SupplierQuotationSerializer` ومعه `rfq_recipient`
  (كتابةٌ عند الإنشاء وحده) — والنَسَبُ يُولَد مع العرض ولا يُلحَق به بعد حين
  (ربطُ عرضٍ **قائمٍ** بطلبيةٍ لاحقاً يبقى خارج النطاق: مطابقةُ بنودٍ كُتبت
  بحرّية ببنودِ طلبيةٍ مقفلة مطابقةٌ بالاسم تكذب)؛ **و`SupplierQuotationLine
  .rfq_line`** يحمل بند الطلبية الأبّ لكلّ سطر. الحرّاسُ على الإنشاء: الطلبيةُ
  من هذه الشركة، وحالتُها `sent` وحدها (المسودّةُ مرفوضةٌ قصداً — بنودُها لم
  تُقفَل ورقمُها لم يُخصَّص)، والمستقبِلُ من تلك الطلبية ولم يردّ بعرضٍ سلفاً
  (`PurchaseRFQRecipient.quotation` OneToOne، وقفلُ الصفّ في
  `SupplierQuotationSerializer._bind_rfq_recipient` لا في التحقّق وحده)،
  وسطرٌ لا يشير إلى بندٍ في طلبيةٍ أخرى. وعند الربط: `recipient.quotation`
  و`replied_at` (وقتُ **أوّل** ردّ لا آخره) و`entry_source='manual'`
  و`created_by` من `perform_create` كأيّ مستند. **ومسارُ الرابط العامّ لم
  يتغيّر بحرف بهذه التذكرة**: `submit_rfq_supplier_quote` تبقى نقطةَ كتابته
  الوحيدة وتفرض سعراً لكلّ بند، وكسبت هنا ختمَين فقط (`entry_source='supplier_link'`
  و`rfq_line` على كلّ سطر). **وتذكرةٌ لاحقة (#133) وسّعتها ثلاثاً**: عملةٌ
  اختياريّة للمورّد الأجنبي — عملةٌ لا سعر صرف لها للشركة تُرفَض لا تُخزَّن
  بسعر 1 (إغلاقٌ للثغرة نفسها التي أغلقها #111 عائدةً من باب ثالث)؛ وملاحظةٌ
  عامة على الطلبية كلّها (`SupplierQuotation.general_note`) وملاحظةٌ لكلّ
  بند (`SupplierQuotationLine.supplier_note`) — نفس نقطة الكتابة الوحيدة
  لـ`entry_source`/`rfq_line` أعلاه. يحرس الثلاثة معاً `docshare/tests/test_purchase_rfq_quote.py`.
- **ISSUE #133 — فجوة رؤية لا تسريب: افتراض النطاق المحلّي مقصورٌ على `list`
  وحده** — `SupplierQuotationViewSet.get_queryset` و`PurchaseRFQViewSet.get_queryset`
  بلا `?scope=` صريح يعودان بالشراء المحلّي وحده، لكن على فعل **القائمة
  فقط**؛ تطبيقه شاملاً كان يكسر `get_object()` على مستندٍ استيراديّ فيحجب
  `send/`، `award/`، `comparison/`، `recipients/` عنه بحجّة افتراضٍ لا علاقة
  له بها. هذه فجوةُ **رؤيةٍ داخل الشركة نفسها** بين شاشتَي الشراء المحلّي
  والاستيراد لا سهواً في العزل — عزل الـtenant عبر `TenantQuerySetMixin`
  سليمٌ ولم يمسّه هذا التغيير، وكل مستدعٍ في الواجهة يرسل `scope` صراحةً على
  قوائمه اليوم.
- **B-3 — قراءةُ الطلبية وعرض المورّد تشترط صلاحيةَ عرض نطاقها**
  (`views/procurement.py` — `ProcurementScopeViewPermissionMixin`، على
  `PurchaseRFQViewSet` و`SupplierQuotationViewSet`): المحلّي على
  `purchase.invoice.view`، والاستيراد على `import.procurement.view`
  (`core/access.py`). القائمة تُفحَص بـ`?scope=` (غيابه = المحلّي)، وكلُّ قراءةٍ
  تفصيلية (`retrieve`، `comparison/`) بنطاق **المستند نفسه** عبر `get_object` —
  وإلا قرأ من مُنح الاستيراد وحده طلبيةً محلّيةً بمعرّفها. الكتابة خارج هذا
  الحارس على فحوصها القائمة. المفتاح الجديد افتراضيٌّ للمشتريات والمحاسب
  (والمدير بـ"*")، و`tenants/migrations/0035_grant_import_procurement_view.py`
  يمنحه لكل دورٍ أو عضوٍ مُنح مفتاحَ استيرادٍ صراحةً. **خارج الحارس**:
  `PublicSupplierQuoteRequestViewSet` (ردود الروابط العامة).
- **ISSUE #133 — ملاحظتان لا واحدة على سطر العرض**: نصّ المورّد
  (`SupplierQuotationLine.supplier_note`) دليلٌ لا يُعدَّل — `read_only_fields`
  يقفله أمام أيّ كتابةٍ من سطح المكتب، ويُحمَل حرفياً عبر مسار حفظ العرض
  الذي يحذف كل سطورها ويعيد إنشاءها؛ الكاتبُ الوحيد له `submit_rfq_supplier_quote`
  من الرابط العام. وتعليقنا عليه (`internal_note`/`internal_note_by`/`internal_note_at`)
  مسارٌ آخر تماماً: نقطةٌ جديدة (`SupplierQuotationViewSet` (`set_line_internal_note`)،
  `POST supplier-quotations/{pk}/lines/{line_id}/internal-note/`) تكتب سطراً
  واحداً بعينه بلا لمس بقية العرض، ومحرّرُ العروض القائم يقبله أيضاً في
  حمولة الحفظ. **يُقرآن معاً في موضعين** — مصفوفةُ المقارنة
  (`comparison/`)، وملاحظةُ المورّد سببُ وجودها («هذا ما عندي بدل ما طلبت»)
  وتعليقنا يُكتب منها بالنقطة المفردة؛ ومحرِّرُ العرض الواحد
  (`frontend_v2/components/procurement/price-offers/PriceOfferForm.tsx`، عمود
  «ملاحظات») حيث يُقرأ نصّ المورّد ويُكتب تعليقنا ضمن حمولة الحفظ نفسها. **ولا يخرج تعليقنا الداخليّ إلى صفحة المشاركة العامة أبداً** —
  حمولة `purchase_rfq` التي يراها المورّد لا تحمل غير حقوله هو
  (`docshare/documents/purchase_docs.py`).

## إلغاء ترحيل الدفعات (وُحِّد في المرحلة 2 + معالجتها 2026-08-11)
إلغاء ترحيل دفعة صفقة (`unpost_payment_from_accounting`) ودفعة تخليص (`unpost_payment`)
كلاهما عبر `accounting.api.reverse_journal(..., copy_currency=True)`: **الأصل يبقى مرحّلاً**
ويعادله قيد عكس بعملته وسعره ⇒ صافي الأثر صفر اسمياً وبالعملة الأساسية، وتقارير الفترة
الأصلية لا تتغيّر بأثر رجعي. إعادة ترحيل دفعة صفقة تنشئ قيداً جديداً دائماً
(`post_payment` يمرّر `idempotent=False` — قيود المرجع السابقة تبقى في الدفاتر، وحارس
التكرار هو قفل صف الدفعة + فحص `is_posted`). الاختبار المرجعي:
`tests/test_deal_payment_unpost_cycle.py`. **بيانات تاريخية:** دورات إلغاء قديمة
(أصل غير مرحّل + عكس مرحّل) أثرها معكوس الإشارة في التقارير المرحّلة — كشفها وتصحيحها
بالأمر `fix_logistics_unpost_cycles` (يسكن في accounting — انظر `docs/modules/accounting.md`).
أما `payment_posting_diagnostics.py` فيشخّص موانع الترحيل التلقائي لدفعةٍ لم تُرحَّل فقط،
ولا يرى هذه الدورات.

## الاختبارات المهمة
| الملف | ما يغطيه |
|---|---|
| `tests/test_stage_machine.py` (133) | `stage` هو المصدر الوحيد؛ كل تقدّم آلي عبر الخدمة المحروسة |
| `tests/test_shipment_from_deals.py` (249) | صفقات → شحنة: تجميع CBM/KG، الشحن = rate×Σunit، التوزيع، الحواجز |
| `tests/test_freight_allocation.py` (134) | وحدة CBM/KG صريحة، إعادة الحساب عند التبديل، تسوية الأغورة |
| `tests/test_landed_cost.py` (344) | ثبات: Σ أسطر الفاتورة = قيمة الصفقة + الشحن المخصَّص + التخليص المخصَّص |
| `tests/test_clearance_import.py` (393) · `test_deal_total_and_freight_gate.py` (208) | استيراد الفواتير من التخليص (وحرّاس الإنشاء: 403 بلا صلاحية أو بلا استيراد، سجلّ النشاط، 404 للتخليص الغريب، وصفقةٌ على شحنةٍ واحدة) · بوّابة «تكلفة الشحن مُثبتة» قبل الفوترة |
| `tests/test_party_accrual_allocation.py` | FIFO على مستحقّات المخلّص صافيةً من دفعات التخليص نفسه، سقف المتبقّي وسقف السند، رفض مستحق طرفٍ آخر وسندٍ غير مرحَّل، سقفٌ مشترك مع توزيع الفواتير، فكّ التوزيع وإلغاء ترحيل السند، الوكيل على الشحن والناقل على الإرسالية |
| `tests/test_shipment_labels.py` | `display_label` بمصادره الثلاثة وحدّ الطول، `shipment_label` في المسلسلات وبحث القائمة بوصف الصفقة، وصف القيد الجديد بالوسم، تبويب دفعات التخليص/الإرسالية/الشحن بالسند الموزَّع ومجموعه = `amount_paid`، وكشف حساب الطرف بالوسم الحيّ بعد تغيير الاسم |
| `tests/test_agent_payment_from_cashbox.py` | دفعة الوكيل بكبسة: إنشاء وترحيل بالأساس = المبلغ × السعر، الترقيم بعد القائمة، لا دفعة عند أي مانع أو فشل ترحيل، الزرّ القديم عبر الخدمة نفسها، والأمر: تقرير بلا كتابة وتنبيهاته و`--apply` للمختار وحده |
| `tests/test_overpayment_split.py` | الفصل عند الترحيل (تخليص وإرسالية، دفعة ثانية، مستند مسدَّد، لا فصل قبل الاستحقاق)، ثبات رصيد الطرف والصندوق، الأمر: تقرير ثم تنفيذ ثم idempotent، و`unpost` التخليص بعد الفصل |
| `tests/test_accrual_adjust.py` | قيد الفرق للتخليص وتعديلٌ ثانٍ فوقه، رفض «لا فرق» والمعاينة لا تكتب، الإرسالية وإلغاء ترحيلها يحذف تعديلاتها، الشحن بسعر صرفٍ معاكس وقفل `freight/`، الفاتورة المرحّلة: مخزون/تكلفة مبيعات والطبقة وحركة البيع بلا انجراف، التحويل بين المستودعات، غير المستلَم على الوسيط ثم يُستلم بالجديدة، الفاتورة المتأخّرة تمنع، إعادة المسودة، والفائض مقابل تحت الحساب في الكرت |
| `tests/test_shipment_attachments.py` | مرفقٌ صورة أو PDF على التخليص والشحنة والإرسالية، الرابط نفسه مرّةً واحدة، الإرفاق بعد الترحيل، رفض رابطٍ غير http، الحذف مُنطاقٌ بالمستند، والشركة الأخرى لا تقرأ ولا تُضيف ولا تحذف |
| `tests/test_import_payment_separation.py` (556) | فصل الاستحقاق عن الدفع (تخليص + نقل محلي) |
| `tests/test_shipment_freight_accrual.py` (307) · `test_receive_on_post_setting.py` (466) | استحقاق شحن الوكيل مستقلاً عن دفعاته · الاستلام عند الترحيل و GR/IR |
| `tests/test_purchase_receipt_visibility.py` | الباقي على البند وملخّص رأس الفاتورة — وتكافؤ رقمهما مع تقرير `outstanding` (وكان بلا اختبار) |
| `tests/test_receive_on_post_per_invoice.py` | خيار «الاستلام مع الترحيل» لكل فاتورة يتقدّم على الإعداد العام في الاتجاهين — ويعبر نقطة `pay/` كما يعبر الترحيل المجرّد |
| `tests/test_local_invoice_receive.py` | استلام الفاتورة المحلية للمخزن · مطابقة البنود بالمعرّف وحرّاس البند المستلَم |
| `tests/test_purchase_invoice_context_tabs.py` | التبويبات الثلاث؛ ومطابقة «قبل/بعد» لكشف الحساب (وأن أثر المسدَّدة = إجماليها لا صفر) |
| `tests/test_due_date_and_overdue.py` | الاستحقاق يُشتقّ من المهلة، و«متأخرة» بُعدٌ لا حالة، وأعمار الدائنة بالاستحقاق — على الجانبين |
| `tests/test_purchase_parity_extras.py` | الرقم التالي · النسخ لا ينسخ تاريخ المستند · توزيع FIFO يبدأ بالأقدم استحقاقاً |
| `tests/test_archive_deal_payments.py` | صفقة الأرشيف: إلغاء ترحيل دفعتها ثم تعديل السعر ثم إعادة ترحيلها يُبقي رصيد المورد والبنك؛ أول ترحيل لدفعةٍ عليها مرفوض؛ سعر دفعتها المرحّلة يُعدَّل بلا مسّ القيد وبسجلّ تدقيق وبصلاحية إلغاء الترحيل، وغيرُ الأرشيف يبقى مقفلاً؛ التعريف = مجموعة (ب) |
| `tests/test_partner_statement_usd.py` | كشف الطرف بالدولار من `amount_currency` وأمر `backfill_foreign_party_currency` (انظر `docs/modules/accounting.md`) |
| `tests/test_deal_payment_currency.py` | دفعة الصفقة والوكيل تُرحَّلان بـamount × usd_to_ils بلا تحويلٍ مزدوج؛ `audit_deal_payment_currency` يقرأ ثم يصحّح (أ) وحدها |
| `tests/test_shipment_delete_releases_deals.py` | حذف الشحنة/فكّ الصفقة يعيدها «جاهزة للشحن»، ويُرفض على المرحّل؛ لا استحقاق ولا دفعة على شحنة محذوفة |
| `tests/test_pi_cheque_voucher.py` | النقطة القديمة صارت تُنتج سند صرف مرحّلاً — لا `attached_cash_amount` بلا قيد |
| `tests/test_purchase_unpost_payment_guard.py` | سندٌ مرحّل يمنع إلغاء الترحيل، والسند النقدي التلقائي يُحرَّر معه بلا ازدواج عند إعادته |
| `tests/test_purchase_paid_is_computed.py` | «المدفوع» من السندات والقيد لا من نوع الفاتورة؛ والقائمة والتفصيل يتفقان |
| `tests/test_purchase_invoice_pay.py` | الدفع من داخل الفاتورة: سندٌ واحد، الفائض سلفة، التراجع الكامل عند الفشل |
| `tests/test_international_supplier_share.py` | الدولية بحصّة المورد في «المشتريات حسب المورد» وسجلّ الفواتير (مع المحمَّل) وكرت الطرف و«آخر سعر شراء» |
| `tests/test_purchase_return_posting.py` | مرتجع الشراء: القيد والمخزون والترقيم؛ ومرتجع الدولية يعكس قيدها بنسبته (المورد وحسابات الاستحقاق بحصصها) ويُرفض قبل ترحيلها |
| `tests/test_tenant_isolation.py` (75) | لا تسرّب صفقات بين الشركات؛ 400 بلا ترويسة الشركة |
| `tests/test_purchase_rfq.py` (ISSUE #112 · #122) | بندٌ بلا سعر ولا HS · قفل البنود عند أوّل إرسال (400) وقبول مستقبِل جديد · الحالات المسموحة/الممنوعة · عدّاد الردود المشتقّ · ترقيمٌ عند أوّل إرسال بلا حرق مسودّة مهجورة · عزل الشركة · **#122**: حرّاسُ العرض المولود من الطلبية — مستقبِلٌ ردّ سلفاً، طلبيةُ شركةٍ أخرى، مسودّة/مُرساة/ملغاة، مستقبِلٌ من طلبيةٍ أخرى، سطرٌ يشير إلى بند طلبيةٍ أخرى |
| `tests/test_use_purchase_orders_setting.py` (ISSUE #117) | مطفأً: الإنشاء المباشر و«تحويل عرض إلى طلبية» يُرفضان (400)، وقراءة/فتح أمرٍ قائم مقبولة بلا حجب · هجرة `0082` تُشعله لشركةٍ لها أمرٌ قائم فقط (وتتجاهل المحذوف ناعماً) وتترك غيرها مطفأً |
| `tests/test_purchase_rfq_award_and_comparison.py` (ISSUE #116 · #122 · #133) | بالشراء المحلّي `award/` ينتج فاتورة أو أمر شراء بحسب `use_purchase_orders` · يُرفض بلا `supplier` أو لموردٍ لم يردّ أو مرّتين · **بالاستيراد يقبل العرض ويتوقّف بلا تحويل** — لا صفقة ولا فاتورة ولا أمر شراء (`test_award_on_import_scope_accepts_offer_and_stops_no_conversion`)، وحارسُ انحدارٍ يثبّت أن الشراء المحلّي لم يتأثّر بالتفريع (`test_award_on_purchase_scope_still_produces_invoice_regression_guard`) · `comparison/`: بندٌ بلا تقديريّ يعود `None`، بندٌ لم يُسعّره موردٌ لا يُحتسَب صفراً في إجماليّه، توحيد العملات بسعر صرفٍ صريح، مورّدٌ لم يردّ بلا عمود، لا حقل شحنٍ في الاستجابة، عزل الشركة · **#122**: عرضٌ مولودٌ من مستقبِلٍ يصير عمودَه وتصحّ الترسيةُ عليه · **عرضٌ حُذف سطرُه الأوسط تبقى أسعارُه تحت بنودها** (يسقط بلا `rfq_line`) · `entry_source` يميّز العمودَين · عملةٌ غير الأساس تُحوَّل |
| `docshare/tests/test_purchase_rfq_quote.py` (ISSUE #133) | تسعير المورّد على الرابط العام: خيارُ عملةٍ افتراضُه الأساس ويستبعد عملةً بلا سعر صرفٍ مُعرَّف (`test_currency_options_exclude_a_currency_with_no_configured_rate`)، وتقديمُ عملةٍ كذلك يُرفض لا يُخزَّن بسعر 1 (`test_submitting_a_currency_with_no_configured_rate_is_refused_not_defaulted`)، وتسعيرٌ بعملةٍ أجنبية يُحفَظ بها ويُحوَّل في المصفوفة (`test_supplier_priced_in_a_foreign_currency_is_stored_in_that_currency` · `test_foreign_currency_quote_is_converted_in_the_comparison_matrix`) · ملاحظةُ السطر وملاحظةُ الطلبية العامة تُخزَّنان وتعودان (`test_supplier_line_note_is_stored_and_comes_back_on_read` · `test_supplier_general_note_for_the_whole_rfq_is_stored_and_returned`)، وتعليقنا الداخليّ لا يمسّ نصّ المورّد ولا يُكتب من أي مسارٍ منصّة (`test_internal_note_never_alters_the_suppliers_text_and_no_platform_path_can_edit_it`)، ولا يتسرّب إلى الصفحة العامة (`test_comparison_matrix_carries_the_suppliers_note_and_our_reply_never_leaks_to_the_public_page`) · رسالةُ خطأٍ يقدر المورّد أن يستحضرها فعلياً تُعرض عربياً وإنجليزياً معاً (`test_a_validation_error_the_supplier_can_actually_trigger_is_shown_bilingually`) · عنوان الصفحة يتبع نطاق الطلبية (`test_page_title_follows_the_rfq_scope`) |
| `tests/test_purchase_price_resolver.py` (ISSUE #111 · #133) | «السعر التقديري» (`core.pricing.indicative_purchase_prices`): يستبعد ما تحت أرضية النافذة (`test_indicative_price_excludes_old_floor_outside_window`)، ويستعمل ما هو موجود إن كان تاريخ الشراء أقصر من النافذة (`test_indicative_price_fewer_than_window_uses_what_exists`)، يغيب كلّياً بلا شراء مرحَّل (`test_indicative_price_absent_when_no_purchase_history`)، فاتورةٌ بسطرين لنفس المنتج تُحتسَب مرّةً واحدة (`test_indicative_price_counts_multi_line_invoice_once`)، وكلّ فاتورةٍ تُحوَّل بسعر صرفها هي لا سعر اليوم — حالةُ عملتين مختلفتين (`test_indicative_price_normalizes_each_invoice_at_its_own_rate`)، واستعلامٌ واحد للمجموعة كلّها (`test_indicative_price_bulk_computation_is_single_query`) |
