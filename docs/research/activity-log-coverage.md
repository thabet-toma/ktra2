# ما الذي يُعدّ «إنجازاً» في `ActivityLog` اليوم؟ — مسحُ تغطية (قضية #171 · خريطة #169)

حقائقُ مقروءةٌ من الكود على الفرع `newktra`. لا توصياتِ تصميم. كلُّ سطرٍ يشير بمسار الملف
والرمز (اسم الدالّة/الصنف) لا برقم السطر.

المصدر: مسحٌ آليٌّ (AST) لكلّ استدعاءات `log_activity`/`log_view` في المستودع، باستثناء
`venv/` و`node_modules/` و`.claude/worktrees/` ومجلّدات `tests/` و`migrations/`.
**النتيجة: ١٣٧ نقطة كتابة** في ١٢ تطبيقاً (‎`accounting` و`after_sales` و`store` و`tenants`
و`import_file` **صفر** نقاط).

---

## ١) الجدولُ المحوريّ — «مسجَّلٌ فعلاً» مقابل «غير مسجَّل»

الأحداثُ التي سألت عنها التذكرةُ بالاسم، متبوعةً بأبرزِ ما جاوَرها في المسح.

| ✅ مسجَّلٌ فعلاً (الملف · الرمز · `action`/`entity_type`) | ❌ غير مسجَّل (الملف · الرمز) |
|---|---|
| **إنشاء فاتورة بيع** — `sales/views.py` (`SalesInvoiceViewSet.perform_create`) · `create`/`sales_invoice`، ومعه لقطةُ المستند كاملةً في `metadata.changes` | **ترحيلُ الفاتورة تلقائياً عند الإنشاء** — `sales/views.py` (`SalesInvoiceViewSet.perform_create`) يستدعي `post_sales_invoice` عند `should_auto` ثمّ يسجّل `create` **وحده**؛ لا صفَّ `post`. و`sales/services/flow.py` (`post_sales_invoice`) لا يسجّل بنفسه |
| **ترحيل فاتورة بيع** (يدوياً) — `sales/views.py` (`SalesInvoiceViewSet.post_invoice`) · `post`/`sales_invoice` | **إنشاء عميل/مورّد من الواجهة** — `partners/views.py` (`PartnerViewSet`) **بلا أيّ استدعاء**؛ لا `create` ولا `update` ولا `delete` |
| **إلغاء ترحيل فاتورة بيع** — `sales/views.py` (`SalesInvoiceViewSet.unpost_invoice`) · `unpost`/`sales_invoice` | **حذف صنف** — `inventory/views.py` (`ProductViewSet.perform_destroy`) بلا تسجيل (الإنشاءُ والتعديلُ مسجَّلان، والحذفُ لا) |
| **سند قبض من عميل** — `sales/views.py` (`CustomerPaymentViewSet.perform_create`) · صفّان: `payment` ثمّ `post`/`customer_payment`؛ وكذلك `perform_update`/`destroy`/`post_payment`/`unpost_payment`/`allocate` | **كلُّ تطبيق `accounting`** — `accounting/views.py` و`accounting/services.py` صفرُ استدعاءات: `JournalViewSet` (القيود اليدوية)، `ChequeViewSet` (الشيكات)، `ExpenseVoucherViewSet` و`RevenueVoucherViewSet` (سندا المصروف والإيراد)، `CashTransferViewSet`، `CashCountViewSet`، `BankReconciliationViewSet`، `FiscalPeriodViewSet`، `OpeningBalanceViewSet`، `AccountViewSet` (شجرة الحسابات) |
| **سند صرف لمورّد** — `logistics/views/payments.py` (`SupplierPaymentViewSet.perform_create`) · `payment` ثمّ `post`/`supplier_payment`؛ وكذلك `perform_update`/`destroy`/`allocate`/`post_to_accounting`/`unpost_from_accounting` | **كلُّ تطبيق `after_sales`** — `after_sales/views.py` (`WarrantyCardViewSet`، `ServiceOrderViewSet`) صفرُ استدعاءات |
| **سدادُ فاتورةِ شراءٍ ودفعاتُها الآليّة** — `logistics/services.py` (`pay_purchase_invoice`، `settle_attached_purchase_intent`) و`logistics/views/invoices.py` (`_auto_settle_cash_purchase`) · `payment`+`post`/`supplier_payment` | **كلُّ تطبيق `store`** — `store/views.py` صفرُ استدعاءات |
| **تحصيلٌ من داخل الفاتورة** — `sales/views.py` (`SalesInvoiceViewSet.collect`, `payment_voucher`) · `payment`/`sales_invoice`، و`sales/services/flow.py` (`collect_invoice_payment`, `_auto_settle_cash_sale`, `_settle_attached_cheques`, `_process_sales_return_refund`) · `payment`+`post`/`customer_payment` | **الجردُ الفعليّ وترحيلُه** — `inventory/views.py` (`StocktakeViewSet.post_doc` و`perform_create`) بلا تسجيل |
| **إنشاء صنف** — `inventory/views.py` (`ProductViewSet.create`) · `create`/`product`، وعبر الوكيل `inventory/agent_api.py` (`agent_products`) | **التحويلُ بين المستودعات** — `post_warehouse_transfer`/`unpost_warehouse_transfer` المستدعاةُ من `inventory/views.py` بلا تسجيل |
| **تعديل صنف** — `inventory/views.py` (`ProductViewSet.update`) · `update`/`product` مع `metadata.changes`؛ و`add_brand`, `bulk_set_group`, `merge`, `merge_undo` (`product_family`) | **حركةُ المخزون نفسها** — `inventory.services.record_stock_movement` بلا تسجيل (الأثرُ يُستدلّ من المستند لا من الحركة) |
| **إنشاء عميل/مورّد عبر واجهة الوكيل الذكيّ فقط** — `partners/agent_api.py` (`agent_suppliers`, `agent_customers`) · `create`/`partner` — المسارُ `‎/api/agent/suppliers/‎` و`‎/api/agent/customers/‎` في `core/urls.py` | **إنشاءُ المستخدمين والعضويّات والشركات** — `tenants/` صفرُ استدعاءات |
| **تعديل مستند مرحَّل** — لا يقع أصلاً: `sales/views.py` (`SalesInvoiceViewSet.perform_update`) يرمي `POSTED_DOC_WARNING` لغير المسودّة، فالمسارُ الوحيد `unpost` ← `update` ← `post` وثلاثتُها مسجَّلة | **الاستيرادُ من الملفّات** — `import_file/` صفرُ استدعاءات |
| **تسجيل دخول** — `hr/auth_api.py` (`login_view` ← `_log_session_event`) · `login`/`session` | **تخليصٌ وشحنٌ محلّيٌّ وإعداداتُ شراءٍ وتقارير** — `logistics/views/clearance.py`, `transport.py`, `purchase_settings.py`, `reports.py` **تستورد** `log_activity`/`log_view` ولا تستدعيها ولا مرّة |
| **تسجيل خروج** — `hr/auth_api.py` (`logout_view` ← `_log_session_event`) · `logout`/`session`؛ وطردُ جهاز `hr/device_api.py` (`_log_device_eviction`) · `device_evict`/`session` | **`entity_type` يُقرأ ولا يُكتب** — `core/activity_views.py` (`_partner_activity_filter`) يفلتر على `clearance` و`local_shipment`، ولا نقطةَ كتابةٍ واحدةٍ تُنتجهما في المستودع كلّه |
| **مستنداتُ الشراء** — `logistics/views/invoices.py` (`PurchaseInvoiceViewSet`: `perform_create`/`perform_update`/`destroy`/`post_to_accounting`/`unpost`/`attach_payment`/`duplicate`/`attachments`)، و`procurement.py` (`SupplierQuotationViewSet`, `PurchaseRFQViewSet`, `PurchaseOrderViewSet.perform_create`, `PublicSupplierQuoteRequestViewSet`)، و`goods_receipts.py` (`_apply`, `destroy`)، و`shipments.py` (`perform_create`, `create_from_deals`) | **`PurchaseOrderViewSet` — الإنشاءُ وحده** (`logistics/views/procurement.py`): لا `perform_update` ولا `destroy` مسجَّلان |
| **الصفقات** — `logistics/views/deals.py` (`LogisticsDealViewSet`: `perform_create`/`perform_update`/`destroy`/`unpost`/`create_payment`/`update_payment`) | **إشعارُ التسليم للشراء** — لا مقابلَ لِـ`sales_delivery_note` في جانب الشراء |
| **طلبيّاتُ الزبون وعروضُ السعر** — `sales/services/orders.py` (`log_order_activity`, `cancel_quotation`) و`sales/views.py` (`SalesQuotationViewSet.convert`, `SalesOrderViewSet`) | |
| **إشعارُ التسليم** — `sales/views.py` (`DeliveryOrderViewSet._apply`, `destroy`) · `sales_delivery_note`؛ و`SalesInvoiceViewSet.deliver` · `deliver`/`sales_invoice` | |
| **الموارد البشرية** — `hr/contracts_api.py` (العقود، `PayrollRunViewSet.post_run`/`unpost_run`)، `hr/attendance_api.py` (البصمات والدوام)، `hr/org_api.py` (الأقسام والمسمّيات)، `hr/requests_api.py` (الطلبات والسُّلَف) | |
| **بوابةُ المحاسب** — `accountant_portal/services.py` (`_log_engagement`, `create/answer/close_review_query`, `record_package_export`, `_log_period`, `update_portal_settings`) | |
| **الأجهزةُ الحسّاسة** — `device_registry/views.py` (`_audit` عبر `_MIRRORED_ACTIONS`) · `create`/`update`/`delete`/`sensitive_device` | |
| **المشاركةُ العامة** — `docshare/services.py` (`create_share`, `revoke_share`, `record_decision`, `submit_quote`) | |
| **لوحةُ المنصّة** — `core/platform_admin_api.py` (`platform_company_modules`, `platform_company_limits`, `_log_company_changes`) | |
| **اقتراحاتُ إعادة الطلب** — `core/replenishment.py` (`apply_suggested_levels`) · `update`/`product` | |

---

## ٢) قيمُ `entity_type` الفعليّة و`metadata` لكلّ نوع

### القائمةُ الكاملة (٣٧ قيمةً نصّيةً ثابتة)

`accountant_engagement` · `accountant_portal_settings` · `accountant_review_package` ·
`accountant_review_query` · `accountant_tax_period` · `customer_payment` · `deal` ·
`document_share` · `goods_receipt` · `hr_advance` · `hr_attendance_day` · `hr_check_event` ·
`hr_contract` · `hr_department` · `hr_job_title` · `hr_payroll_run` · `hr_request` ·
`partner` · `product` · `product_family` · `public_supplier_quote_request` ·
`purchase_invoice` · `purchase_order` · `purchase_rfq` · `sales_delivery_note` ·
`sales_invoice` · `sales_order` · `sales_quotation` · `sensitive_device` · `session` ·
`shipment` · `supplier_payment` · `supplier_quotation` · `tenant` · `tenant_limit` ·
`tenant_module` · `warehouse`

قيمتان تُحسمان وقت التشغيل ولا تخرجان عن القائمة أعلاه: `docshare/services.py`
(`record_decision`, `submit_quote`) تقرأ `decision_spec["entity_type"]` /
`quote_spec["entity_type"]` من `docshare/documents/` — والقيمُ المعرَّفةُ هناك هي
`purchase_order` (`purchase_docs.py`) و`purchase_rfq` (`purchase_docs.py`) و
`sales_quotation` (`sales_docs.py`) و`sales_order` (`voucher_docs.py`).

الحقلُ `entity_type = CharField(max_length=40)` في `core/models.py` (`ActivityLog`)؛
أطولُ قيمةٍ مستعملةٌ `public_supplier_quote_request` (٢٩ حرفاً) فلا اقتطاعَ صامتاً اليوم.

### ما يوضَع في `metadata`

الأغلبيّةُ الساحقةُ من نقاط الكتابة **لا تمرّر `metadata` إطلاقاً** فتُخزَّن `{}` (الافتراض في
`core/activity.py` · `log_activity`). المرَّرُ فعلاً ٣٢ نقطةً فقط:

| `entity_type` | محتوى `metadata` | الملف · الرمز |
|---|---|---|
| `sales_invoice` | `{"changes": [...]}` — فروقاتُ الترويسة والبنود المبنيّةُ بـ`build_document_snapshot_changes`/`build_activity_changes`/`build_line_changes`؛ و`None` إن لم تتغيّر | `sales/views.py` (`perform_create`, `perform_update`, `destroy`) |
| `purchase_invoice` | `{"changes": [...]}` بنفس الشكل | `logistics/views/invoices.py` (`perform_create`, `perform_update`, `destroy`) |
| `product` | `{"changes": [...]}` عند التعديل · `{"product_ids": [...], **fields}` في `bulk_set_group` · `{"applied": [...], "skipped_count": n}` في إعادة الطلب | `inventory/views.py` (`update`, `bulk_set_group`) · `core/replenishment.py` (`apply_suggested_levels`) |
| `product_family` | `{"merge_id": n, "product_ids": [...]}` / `{"merge_id": n}` | `inventory/views.py` (`merge`, `merge_undo`) |
| `warehouse` | `{"name_changed": bool}` | `inventory/views.py` (`WarehouseViewSet.perform_update`) |
| `supplier_quotation` | `{"deal_id", "deal_ref_number"}` · `{"status"}` · `{"purchase_order_id"}` · `{"purchase_invoice_id"}` | `logistics/views/deals.py` (`perform_create`) · `logistics/views/procurement.py` (`perform_update`, `convert_to_purchase_order`, `convert_to_purchase_invoice`) |
| `public_supplier_quote_request` | `{"quotation_id"}` | `logistics/views/procurement.py` (`approve`) |
| `document_share` | `{"doc_type", "doc_id", "expiry_days"}` / `{"doc_type", "doc_id", "event": "revoked"}` | `docshare/services.py` (`create_share`, `revoke_share`) |
| `purchase_order`/`purchase_rfq`/`sales_quotation`/`sales_order` (من الرابط العام) | `{"source": "public_share", "doc_type", "decision"/"submitted_by_name", "decided_by_name", "note", "ip", "share_id"}` | `docshare/services.py` (`record_decision`, `submit_quote`) |
| `sensitive_device` | `details or {}` — يحمل `{"changes": {...}}` عند التعديل، و`{"imei": ...}` عند الحذف | `device_registry/views.py` (`_audit`) |
| `tenant_module` | `{"event_code": "MODULE_TOGGLED", "module", "previous_enabled", ...}` | `core/platform_admin_api.py` (`platform_company_modules`) |
| `tenant_limit` | `{"event_code": "LIMIT_CHANGED", "limit", "previous_limit", ...}` | `core/platform_admin_api.py` (`platform_company_limits`) |
| `tenant` | `{"event_code", "field", "previous", ...}` | `core/platform_admin_api.py` (`_log_company_changes`) |
| `accountant_*` (خمسةُ أنواع) | دائماً `{"module": "accountant_portal"}` + مفتاحٌ واحدٌ حسب النوع: `severity` / `rows` / `status` / `fields` | `accountant_portal/services.py` |

**كلُّ ما عداها `{}`** — ومنه `customer_payment` و`supplier_payment` و`deal` و`shipment`
و`goods_receipt` و`sales_order` و`sales_delivery_note` و`partner` و`session` وكلُّ
`hr_*`. أي أنّ **مبلغَ سندِ القبض/الصرف لا يوجد في `metadata`**، بل في `description`
نصّاً حرّاً إن وُجد.

---

## ٣) اتّساقُ `is_view`

`is_view` مضبوطٌ باتّساق، والاتّساقُ آتٍ من البنية لا من الانضباط: القيمةُ `True` لا
تُمرَّر يدوياً في أيّ نقطةِ كتابةٍ واحدة — مصدرُها الوحيدُ الغلافُ `log_view` في
`core/activity.py`، وهو يثبّت `action="view"` و`is_view=True` معاً. وبالمقابل **لا توجد ولا
نقطةُ كتابةٍ واحدةٍ تمرّر `action="view"` بـ`log_activity` مباشرةً** (تحقّقٌ آليّ على ١٣٧
نقطة). فلا يوجد حدثُ عرضٍ «نسي» تعليمَ نفسِه.

نقاطُ `log_view` الأربعُ الوحيدة:

| الملف · الرمز | `entity_type` |
|---|---|
| `sales/views.py` (`SalesInvoiceViewSet.retrieve`) | `sales_invoice` |
| `logistics/views/invoices.py` (`PurchaseInvoiceViewSet.retrieve`) | `purchase_invoice` |
| `logistics/views/deals.py` (`LogisticsDealViewSet.retrieve`) | `deal` |
| `inventory/views.py` (`WarehouseViewSet.stock`) | `warehouse` |

`device_registry/views.py` (`_MIRRORED_ACTIONS`) يحسم الأمرَ صراحةً في الاتّجاه الصحيح:
حدثا `view` و`search` **مستثنيان من القاموس** فلا يُعكسان إلى `ActivityLog` أصلاً — يبقيان
في `DeviceAuditLog` وحده.

### الاستثناءُ الوحيدُ الذي يلوّث «الإنجاز»

`accountant_portal/services.py` (`record_package_export`) يسجّل `action="export"` بـ
`is_view=False`. وهو **تصديرُ قراءةٍ لا فعلٌ على مستند**، لكنّه يمرّ في كلّ حسابٍ يفلتر
`is_view=False` — بما فيه الصفحةُ العامة و`platform_company_activity`.

### ملاحظتان مرافقتان (حقائق، لا أحكام)

1. **`action` تتجاوز `choices` النموذج.** `core/models.py` (`ActivityLog.ACTIONS`) يعرّف
   عشرَ قيم: `create` `update` `delete` `post` `unpost` `duplicate` `payment` `view`
   `login` `logout`. والمستعملُ فعلاً يضيف **خمساً خارجَها**: `convert`
   (`logistics/views/procurement.py`, `sales/views.py`, `sales/services/orders.py`) ·
   `deliver` (`sales/views.py` · `SalesInvoiceViewSet.deliver`) · `cancel`
   (`sales/services/orders.py` · `cancel_quotation`, `log_order_activity`) · `export`
   (`accountant_portal/services.py`) · `device_evict` (`hr/device_api.py`). Django لا
   يفرض `choices` على مستوى قاعدة البيانات، و`get_action_display()` — المصدرُ الوحيدُ لِـ
   `action_label` في `core/activity_views.py` (`ActivityLogSerializer`) — يعيد القيمةَ الخام
   لها. طولُ العمود `max_length=20` وأطولُ قيمةٍ `device_evict` (١٢ حرفاً).
2. **صفوفٌ بلا مستخدم.** `docshare/services.py` (`record_decision`, `submit_quote`) تمرّر
   `user=None` صراحةً (كاتبُها زائرٌ مجهولٌ من رابطٍ عام) مع `tenant=share.tenant`. فهي
   `is_view=False` وتدخل أيَّ تجميعٍ لا يشترط `user__isnull=False`.

---

## ٤) الفهارس على `core.ActivityLog`

معرَّفةٌ في `core/models.py` (`ActivityLog.Meta.indexes`) ومهاجَرةٌ في
`core/migrations/0001_initial.py`:

| الفهرس | الأعمدة | ما يغطّيه |
|---|---|---|
| `act_tenant_ts_idx` | `(tenant, -timestamp)` | مدًى زمنيٌّ لشركةٍ كاملة |
| `act_tenant_user_ts_idx` | `(tenant, user, -timestamp)` | مستخدمٌ واحدٌ داخل شركة، بمدًى زمنيّ |
| `act_tenant_entity_idx` | `(tenant, entity_type, entity_id)` | سجلُّ مستندٍ واحد |

وفهرسان مفردان ضمنيّان من `db_index=True` على الحقلين: `is_view` و`timestamp`.

- **«كلّ نشاط مستخدمٍ واحد في يومٍ واحد داخل شركة»** يخدمه `act_tenant_user_ts_idx`
  مباشرةً وكاملاً: مساواةٌ على `tenant` و`user` ثمّ مدًى على `timestamp` — وهو ترتيبُ
  الأعمدة نفسُه، فالشرطُ كلُّه يُحلّ داخل الفهرس. وهذا هو المسارُ الذي تسلكه
  `core/activity_views.py` (`ActivityLogViewSet.get_queryset`) حين يُمرَّر `user` مع `date`.
- **لا يوجد فهرسٌ يخدم تجميعاً يومياً لكلّ موظّفي الشركة.** أقربُ ما يُستعمل
  `act_tenant_ts_idx` وهو يحصر النطاق الزمنيّ فقط؛ التجميعُ على `user` بعده يلزمه قراءةُ
  الصفوف وفرزُها. ولا يحمل أيُّ فهرسٍ مركّبٍ العمودَ `user` بعد `timestamp` ولا العمودَ
  `is_view` أصلاً — ففلترُ `is_view=False` (الافتراضيّ في الصفحة العامة) يُطبَّق على
  الصفوف بعد حصر النطاق، لا داخل فهرس.

### تنبيهُ `__date` — لا يُخالَف

`core/date_ranges.py` يوثّق العطبَ بنصّه: جانغو يترجم `timestamp__date = X` إلى
`DATE(CONVERT_TZ(timestamp,'UTC','Asia/Hebron'))`، و`CONVERT_TZ` بمنطقةٍ مُسمّاة تحتاج
جداول `mysql.time_zone` **وهي فارغةٌ على خادم الإنتاج**، فتعيد `NULL` ⇒ صفرُ صفوفٍ بلا
خطأٍ ولا أثرٍ في اللوج. وقد أخفى هذا سجلَّ النشاط بالكامل من قبل. وفوق ذلك
`DATE(CONVERT_TZ(...))` **يُلغي الفهرسَ على العمود** ويفرض مسحاً كاملاً.

**ما يجب استعماله:** `core.date_ranges.filter_local_date_range(qs, "timestamp",
date_from=..., date_to=...)` — يحسب حدودَ اليوم المحلّي في بايثون ويقارن
`timestamp >= بداية اليوم` و`timestamp < بداية الغد` (`__lt` لا `__lte` عمداً، لأنّ
`<= 23:59:59` يُسقط كسورَ `datetime(6)`). ومعه `resolve_preset(name)` لأسماء المدى الجاهزة
`RANGE_PRESETS = (today, yesterday, week, month, quarter, year, all)` — والأسبوعُ يبدأ
**السبت**. `core/activity_views.py` يستعملهما بالفعل ويحمل التحذيرَ في تعليقه.

---

## ٥) نقاطُ الـAPI القائمةُ التي تقرأ `ActivityLog`

| المسار | الرمز · الملف | ما تفلتره |
|---|---|---|
| `/api/activity/` | `ActivityLogViewSet` · `core/activity_views.py` | `tenant` إلزاميّ (فارغٌ بلا شركة). صلاحيّة: سجلُّ مستندٍ (`entity_type`+`entity_id`) أو سجلُّ جهةٍ (`partner_id`) متاحٌ للعضو؛ وأيُّ استعلامٍ غيرِ مقيَّدٍ بهما يتطلّب `user_is_admin`. فلاتر: `entity_type`, `entity_id`, `partner_id`, `user`, `action`, `search` (على `entity_label`/`description`/اسم المستخدم). `is_view=False` مفروضٌ تلقائياً إلّا مع `include_views=true` أو داخل سجلّ مستند. المدى: `range` جاهز، أو `date`، أو `date_from`/`date_to`؛ والافتراضُ للصفحة العامة **اليوم** (وسجلُّ مستندٍ أو جهةٍ بلا حدٍّ زمنيّ). ترقيمٌ ٥٠/صفحة بسقف ٢٠٠. سجلُّ المستندِ وحدَه يُطوى بـ`_fold_view_events`. |
| `/api/activity/users/` | `ActivityLogViewSet.users` · `core/activity_views.py` | المستخدمون الذين لهم نشاطٌ في الشركة (`user__isnull=False`, `distinct`) — **للمدير فقط**. بلا مدًى زمنيّ. |
| `/api/activity/{pk}/` | `ActivityLogViewSet` · `core/activity_views.py` | صفٌّ واحدٌ بنفس حرّاس `get_queryset`. |
| `/api/accountant/activity/` | `AccountantActivityView` · `accountant_portal/views.py` | مقصورٌ على الشركة. دورُ `legal_accountant` يرى صفوفَه هو فقط؛ غيرُه يحتاج `admin.activity.view` ويرى صفوفَ **المحاسبين المرتبطين وحدهم** (`AccountantEngagement.accountant_id`). **لا يفلتر `is_view`** ولا يقبل مدًى زمنيّاً؛ `page_size` بسقف ٢٠٠ بلا ترقيمٍ حقيقيّ. |
| `/api/platform/companies/<int:pk>/activity/` | `platform_company_activity` · `core/platform_admin_api.py` | `IsPlatformAdmin`. شركةٌ واحدةٌ بالمعرّف، `is_view=False` صراحةً، آخرُ `COMPANY_ACTIVITY_LIMIT` صفّاً. بلا مدًى زمنيّ وبلا فلترِ مستخدم. |

المسارات مأخوذةٌ من `docs/API_INDEX.md` ومطابَقةٌ بقراءة الملفّات.

---

## ما لم يُتحقَّق منه

- لم يُقَس أداءُ أيّ استعلام (لا `EXPLAIN` ولا توقيت) — الفقرةُ ٤ تصفُ تعريفَ الفهارس وما
  تغطّيه بنيوياً فقط، كما طلبت التذكرة.
- لم تُفحَص الواجهةُ (`frontend_v2/`): هذا المسحُ لجانب الخادم وحده.
