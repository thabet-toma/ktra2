# TASK6 — KTRA Deep Audit + Data-Model Normalization + Business-Logic Completion

> **الدور:** Staff SWE / Tech Lead. خطّة يُنفّذها موديل أرخص بعد موافقة المالك.
> **التاريخ:** 2026-05-23. **المرجع:** مراجع الأصيل في
> `docs/aseel_reference/full/` + لقطات المالك + PROJECT_MAP.md.
> **القاعدة الذهبية:** قبل أي tasks، اقرأ هذا الملف **كاملاً** + قسم
> «الاوديت الحقيقي» أدناه. لا تَختصر.

---

## مقدّمة: لماذا الاوديت السابق فَشل (مرَّتَيْن)

**النسخة 1** ركّزت فقط على 6 أخطاء console من الـPDF. سطحي.

**النسخة 2** فَهمت «معلومات محشورة» على أنها «JSON/text-encoded data
في الـDB». هذا جزء من القصّة لكن **ليس الجزء الأكبر** الذي يَقصده
المالك.

**ما يَقصده المالك فعلاً (مَفهوم بعد رسالته الثالثة):**

الـ«حشر» هو في **الشاشة نفسها** — كل المعلومات موجودة لكنّها مَوزَّعة
على ~8 sections مكدّسة عمودياً، كل section بـpadding+gaps ضخمَيْن،
فتُجبَر على scroll تدريجي لرؤية كل قسم. _البرنامج لا يَعرض المعلومات
دفعة واحدة._

**أمثلة موثَّقة من الشاشة (`ShipmentForm.tsx` بطول 620 سطر JSX):**

1. **Header band** يَعرض 16 حقل ضمن `AseelDocumentShell` (السطور 415-465).
2. ثم **مكوّن `ShipmentStatusVisualizer`** كَشريط 8 مراحل (يَأكل ~100px).
3. ثم **جدول النقل المحلي** (السطور 498-530) — حتى لو فارغ يَعرض
   «لا توجد سجلات» بـpadding كبير.
4. ثم **`ShipmentBasicInfo` + `ShipmentShippingDetails` في grid 2 أعمدة**
   (السطور 532-544) — **يُكرِّر حقول الـheader band** (بوليصة، حاوية،
   مغادرة، وصول، نوع الشحن).
5. ثم **`ShipmentDealsTable`** (السطر 547) — جدول الصفقات + التوزيع.
6. ثم **`CollapsibleSection "المالية"`** بـ`p-4 space-y-6` يَحوي
   `InstallmentManager` + `PaymentProgress` (السطور 555-585).
7. ثم **زر «تكوين فاتورة»** (السطور 588-597).
8. ثم **modal للـSupplier + DealSelector** (خارج المحور).

**النتيجة:** المستخدم يَفتح شحنة، يَرى الـheader band، ثم يَجب يَنزل
بالـscroll **6 مرّات على الأقل** ليَصل لـ«تكوين فاتورة». الأصيل (الذي
هذا المشروع يُحاكيه) كان يَعرض كل هذا في شاشة **1024×768 واحدة بدون
scroll** عبر كَثافة فائقة.

**علاوةً على ذلك**، المالك طَلَب صراحةً: «ادمج الواجهات سواء بتفاصيل
الشحنات ولا التخليص». أي:

- شاشة الشحنة (`ShipmentForm`) + شاشة التخليص الجمركي
  (`CustomsClearanceManagement`) + النقل المحلي (`LocalShippingPage`)
  يَجب يَكونوا **مَدمَجَين في شاشة واحدة موحَّدة** تَعرض رحلة الاستيراد
  كاملةً (الشحنة الدولية → التخليص → النقل → الفاتورة) بـtabs أفقية
  داخل نفس الـdocument shell.

---

**جوهر المرض (المُحَدَّث 2026-05-23):**

1. **كَثافة شاشة منخفضة فاضحة** — 8 sections × scroll = الموت.
2. **شاشات مُنفصلة لما يَجب أن يَكون شاشة واحدة** — رحلة الاستيراد
   موزَّعة على 4 routes.
3. **معلومات أعمال مُهيكَلة تَعيش في حقول نَصّ حرّ**
   (`notes`/`JSONField`) — Part of the story, لكن أصغر من الأوّلَيْن.

**أمثلة حيّة من الكود (مُؤكَّدة بـfile:line):**

1. `frontend_v2/components/procurement/clearance/CustomsClearanceManagement.tsx:51-54`:
   ```ts
   function notesMeanShippingPayment(notes: string | null): boolean {
     const n = String(notes ?? "").trimStart();
     return n.startsWith("[شحن]") || n.startsWith("شحن");
   }
   ```
   نوع الدفعة (شحن vs تخليص) مُرَمَّز في **بادئة نَصّ** في حقل `notes`.
   لا عمود `payment_type` صريح. لا فلتر SQL. لا integrity.

2. `frontend_v2/components/procurement/clearance/CustomsClearanceManagement.tsx:48-49`:
   ```ts
   const SHIPPING_COST_LINE_LABEL = "دفعة الشحن (الناقل)";
   const LUMP_CLEARANCE_LINE_LABEL = "إجمالي تكلفة التخليص";
   ```
   نوع بَند التكلفة مُحدَّد بـ**مطابقة نصّية كاملة لـlabel عربي**. تَغيير
   حرف واحد يَكسر المنطق.

3. `logistics/models.py:450-454` `LogisticsClearance.cost_lines = JSONField`:
   بنود التخليص الكاملة (الأصيل يَنصّ على جدول بـ8 أعمدة) محشورة في
   JSON بشكل `[{"label":"...", "amount":0}]` — لا account FK، لا
   debit/credit، لا VAT column، لا cost_center.

4. `logistics/models.py:774-775` `PurchaseInvoice.local_payments_json`
   و `conversion_metadata_json`: الدفعات وميتاداتا التحويل في JSON بدل
   جداول علاقاتية.

5. `logistics/models.py:62` `LogisticsDeal.shipment_notes = TextField` —
   حقل ثانٍ بنفس اسم `notes` تقريباً، استخدام غامض.

6. `logistics/models.py:241` `LogisticsDealItem.notes = CharField(255)`:
   الأصيل يُلزم على البَند: رقم خلطة/مسلسل، تاريخ انتهاء، بيان مفصَّل،
   كمية إضافية، خصم سطر، نسبة ضريبة لكل بَند، عملة بَند، مخزن بَند.
   كلّها مفقودة عَموداً، محشورة في `notes` نصّياً (أو غير مُدخَلة أبداً).

**النتيجة:** فاتورة شراء لا يُمكنها أن تَعرف بدقة:
- من أي مخزن استلمت أي بَند (الكل في `Default Warehouse`).
- ما رقم batch البَند (إذا أُدخل، فهو في `notes` بحرّية).
- ما تاريخ انتهاء البَند (نفس الشيء).
- ما خصم البَند (الخصم على header فقط).
- ما VAT% البَند (VAT على header، بـrate موحَّد).

تَقرير «المخزون قَيد الانتهاء» مستحيل. عملية الـreturn حسب batch
مستحيلة. تَقرير VAT متعدّد النِسَب مستحيل.

---

## الاوديت الحقيقي — 9 فئات أمراض

### الفئة 0: كَثافة الشاشة + دمج الواجهات (الأهمّ — الذي فَوَّتُّه)

| # | الموقع | الخلل | المطلوب |
|---|--------|------|---------|
| **0-1** | `ShipmentForm.tsx` (620 سطر JSX) | 8 sections عمودياً + scroll مستمر | layout أحادي viewport (≤ 1080px) |
| **0-2** | `ShipmentForm.tsx:532-544` | `ShipmentBasicInfo` + `ShipmentShippingDetails` **تُكرِّر** حقول الـheader band (بوليصة/حاوية/مغادرة/وصول/نوع شحن) | احذف هذَيْن المكوِّنَيْن، اعتمد على header band كمصدر وحيد |
| **0-3** | `ShipmentForm.tsx:498-530` | جدول النقل المحلي يَعرض دائماً قسماً كاملاً حتى لو فارغ بـ«لا توجد سجلات» + padding كبير | يَنطوي تحت tab «النقل المحلي»، يَختفي إن فارغ، يَظهر كـrow مَطوي |
| **0-4** | `ShipmentForm.tsx:491-496` | `ShipmentStatusVisualizer` (8 مراحل) يَأكل ~100px قبل المحتوى الأساسي | يَنتقل لـsingle-line compact timeline أعلى المحتوى (~32px) أو يَنتقل لـstatus bar |
| **0-5** | `ShipmentForm.tsx:555-585` | `CollapsibleSection` بـ`p-4 space-y-6` + `space-y-6` داخلية = ~80px فجوات | استبدال بـAseel tab بسيط بدون padding مبالغ |
| **0-6** | شاشات منفصلة: `ShipmentForm` / `CustomsClearanceManagement` / `LocalShippingPage` / `InvoiceForm` (purchase) | الرحلة موزَّعة على 4 routes | **شاشة موحَّدة `ImportDocumentScreen`** بـtabs أفقية: الإرسالية / التخليص / النقل المحلي / فاتورة الشراء |
| **0-7** | `DealForm.tsx` (آخر مرَّة 580+ سطر) | نفس نمط 0-1 — sections عمودية | نفس fix density |
| **0-8** | `InvoiceForm.tsx` (purchase) | نفس النمط | نفس fix density |
| **0-9** | `CustomsClearanceManagement.tsx` (راجع المَلَفّ) | يَعرض list + form في نفس الصفحة بـscroll | فَصل master/detail عبر split-view أو drill-in |
| **0-10** | Modals (Supplier/DealSelector/Picker) | كلّها fullscreen أو centered overlays تَحجُب الشاشة | استبدال بـside-panel على اليمين بـwidth 380px (لا تَحجب الـform) |

**ملاحظة معمارية:** الأصيل (المرجع) كان برنامج Windows 1024×768 بدون
scroll. كل نموذج كان شاشة واحدة كثيفة جداً. الترجمة لـweb يَجب تَحافظ
على نفس الفلسفة، لا تَنحاز للـ«modern web spacing» بـcards وفجوات
كبيرة. _Information density first; whitespace second._

---

### الفئة I: المعلومات المحشورة في JSON / Text (الأخطر)

| # | الموقع | الحالة الحالية | يَجب أن يَكون |
|---|--------|-----------------|----------------|
| **I-1** | `logistics/models.py:450` `LogisticsClearance.cost_lines: JSONField` | `[{label, amount}]` JSON | جدول `LogisticsClearanceLine` بأعمدة: seq, account FK, description, debit, credit, vat_percent, cost_center FK |
| **I-2** | `logistics/models.py:774` `PurchaseInvoice.local_payments_json: JSONField` | JSON دفعات | جدول `PurchaseInvoicePayment` (مرآة `CustomerPayment`) |
| **I-3** | `logistics/models.py:775` `PurchaseInvoice.conversion_metadata_json` | JSON ميتاداتا | حقول صريحة على الفاتورة + جدول `DocumentConversion` للتاريخ |
| **I-4** | clearance UI: payment-type في `notes` بـprefix `[شحن]` | regex parse | عمود `payment_purpose` choice: `clearance_fee/shipping/broker_fee/customs` |
| **I-5** | clearance UI: cost-line label matching by Arabic string | exact-string match | `LogisticsClearanceLine.line_type` choice مُعرَّف عَلمياً |
| **I-6** | `LogisticsDealItem.notes (255)` يَختزن batch/serial/expiry/مخزن | نص حرّ | أعمدة: `batch_number`, `serial_number`, `manufacture_number`, `expiry_date`, `warehouse FK`, `unit FK`, `extra_qty`, `catalog_number` |
| **I-7** | `PurchaseInvoiceItem.notes (500)` نفس الشيء | نص حرّ | نفس الأعمدة + `discount_percent`, `discount_amount`, `vat_percent`, `second_date`, `currency`, `exchange_rate` |
| **I-8** | `LogisticsDeal.shipment_notes` + `LogisticsDeal.notes` | حقلان TextField بنفس المعنى تقريباً | احذف `shipment_notes`؛ أو نَقِّحه لِغرض محدَّد (مثلاً `customs_special_instructions`) |
| **I-9** | `default_clearance_cost_lines()` في `logistics/models.py:419-428` يَرجع نصوصاً عربية كقيم default | hardcoded labels | seed `LogisticsClearanceLineTemplate` لكل tenant + FK من line إلى template |
| **I-10** | `LogisticsExpense.related_type/related_id` (line 514-515) بـCharField + IntegerField | polymorphism بدون GFK | إمّا `GenericForeignKey` صريح، أو 3 FK مُنفصلة (deal/shipment/clearance) مع check constraint |

### الفئة II: حقول مفقودة (يجب أن تُضاف للموديلات)

#### II-A. LogisticsDeal — مفقود

| # | الحقل | الـRef في الأصيل |
|---|------|-----------------|
| **II-A-1** | `transaction_time` (الساعة على الصفقة) | الإرساليات.txt:17-18 |
| **II-A-2** | `second_date` (تاريخ ثاني) | الإرساليات.txt:19-20 |
| **II-A-3** | `licensed_dealer_no` (مشتغل مرخص للمورد) | الإرساليات.txt:32-34 |
| **II-A-4** | `editable` (قابل للتعديل — قفل المحاسب) | الإرساليات.txt:87-88 |
| **II-A-5** | `book_number` موجود لكن لا helper مَوحَّد يستخدم `TenantBook` (مذكور كَـthin wrapper في N0-T3 لكن غير مُحقَّق في `LogisticsDeal.save()`) | الأدوات.txt:62-100 |

#### II-B. LogisticsShipment — مفقود

| # | الحقل | الـRef |
|---|------|--------|
| **II-B-1** | `transaction_time` | الإرساليات.txt:17-18 |
| **II-B-2** | `transit_journal` FK لـJournalHeader (رقم القيد الناشئ من ترحيل الإرسالية) | الإرساليات.txt:108-109 |
| **II-B-3** | `editable` flag | الإرساليات.txt:87-88 |
| **II-B-4** | `vat_statement` FK | الإرساليات.txt:176-178 |
| **II-B-5** | `journal_no_display` (read-only computed from `journal`) | الإرساليات.txt:21-22 |
| **II-B-6** | الـ`amount_*` على header level (`subtotal/vat_total/grand_total`) — حالياً موجود `total_shipping_cost_usd` فقط (شحن، ليس قيمة البضاعة) | الإرساليات.txt:208-214 |

#### II-C. LogisticsClearance — مفقود (خطير)

| # | الحقل | الـRef |
|---|------|--------|
| **II-C-1** | `transaction_time` (الساعة) | الإرساليات.txt:169-170 |
| **II-C-2** | `second_date` | الإرساليات.txt:171-172 |
| **II-C-3** | `licensed_dealer_no` للمخلِّص | الإرساليات.txt:186-187 |
| **II-C-4** | `settlement_invoice_number` (رقم فاتورة المقاصة) | الإرساليات.txt:188-190 |
| **II-C-5** | `currency` FK + `exchange_rate` (الأصيل يُحدِّد عملة البيان) | الإرساليات.txt:203-207 |
| **II-C-6** | `vat_statement` FK | الإرساليات.txt:176-178 |
| **II-C-7** | `subtotal_no_vat / vat_total / grand_total` (totals) | الإرساليات.txt:208-214 |
| **II-C-8** | `journal` FK مباشرة (الآن من خلال payment) | الإرساليات.txt:173-175 |
| **II-C-9** | `editable` flag | الإرساليات.txt:196-198 |
| **II-C-10** | `clearance_lines` (جدول I-1) — مذكور أعلاه |

#### II-D. LogisticsDealItem — مفقود (خطير)

| # | الحقل | الـRef |
|---|------|--------|
| **II-D-1** | `seq` (مسلسل) | الإرساليات.txt:36 |
| **II-D-2** | `catalog_number` | الإرساليات.txt:40-42 |
| **II-D-3** | `name_snapshot` (لقطة الاسم لحظة الإدخال) | الإرساليات.txt:43-45 |
| **II-D-4** | `description_line` (بيان السطر، قابل للتعديل) | الإرساليات.txt:46-48 |
| **II-D-5** | `unit` FK (وحدة 1/2/3 من Product) | الإرساليات.txt:49-50 |
| **II-D-6** | `warehouse` FK | الإرساليات.txt:51-53 |
| **II-D-7** | `extra_qty` (الكمية الإضافية) | الإرساليات.txt:57-60 |
| **II-D-8** | `batch_number` / `manufacture_number` / `serial_number` | الإرساليات.txt:61-62 |
| **II-D-9** | `expiry_date` | الإرساليات.txt:63-65 |
| **II-D-10** | `unit_price` موجود — لكن مع `currency FK` + `exchange_rate` per-line (multi-currency line) | الإرساليات.txt:69-74 |
| **II-D-11** | `second_date` per-line | الإرساليات.txt:75-77 |
| **II-D-12** | `is_taxable` (yes/no) + `vat_percent` per-line | الإرساليات.txt:78-80 |
| **II-D-13** | `discount_percent / discount_amount` per-line | الفواتير.txt:62 (M2 added on Sale, لا on Deal) |

#### II-E. PurchaseInvoiceItem — مفقود

نفس قائمة II-D حرفياً + إضافة `landed_*` الموجودة بالفعل.

### الفئة III: خرق Multi-Tenancy (default=1)

I4-05 (Phase 4 من task2) أزال `default=1` من **accounting** فقط. **لا
يَزال موجوداً في logistics + tenants + بعض sales:**

| # | الموقع | الحالة |
|---|--------|--------|
| **III-1** | `logistics/models.py:19` `LogisticsDeal.tenant default=1` | يَجب يُحذَف، يَفشل loud إن tenant غير مُمرَّر |
| **III-2** | `logistics/models.py:261` `LogisticsShipment.tenant default=1` | نفس الشيء |
| **III-3** | `logistics/models.py:439` `LogisticsClearance.tenant default=1` | نفس الشيء |
| **III-4** | `logistics/models.py:465` `LogisticsClearancePayment.tenant default=1` | نفس الشيء |
| **III-5** | `logistics/models.py:513` `LogisticsExpense.tenant default=1` + `currency default=1` | نفس الشيء |
| **III-6** | `logistics/models.py:563` `LocalShipment.tenant default=1` + `currency default=1` | نفس الشيء |
| **III-7** | `logistics/models.py:729, 756` `PurchaseInvoice.tenant default=1` + `currency default=1` | نفس الشيء |
| **III-8** | `logistics/models.py:881` `PurchaseInvoiceFee.tenant default=1` | نفس الشيء |
| **III-9** | `LogisticsPayment` (راجع 170+) | نفس الشيء |

**الأثر:** أيّ كَود يَستدعي `Model.objects.create(...)` بدون `tenant`
سيُكتب لـtenant=1 بدلاً من 400 صريح. خَطر تَلوّث بيانات multi-tenant.

### الفئة IV: تَكدّس حقول الحالة (Status Bloat)

`LogisticsDeal` يَحوي **4 حقول حالة متداخلة**:

| الحقل | القيم | المُستخدِم الفعلي |
|------|-------|------------------|
| `status` | Open/Shipped/Cleared/Closed/Cancelled | legacy، يُستخدم في GL/AR queries |
| `order_status` | Open/Manufacturing/ReadyToShip/Shipping/Clearance/Delivered/Closed | UI dashboard fields |
| `payment_status` | Unpaid/Partially Paid/Fully Paid | يُحسَب من remaining_amount نظرياً، مُخزَّن واقعياً |
| `shipping_workflow_status` | sw_mfg_start → sw_released (7 stages) | state machine الحقيقي |

**النتيجة:** سَجِل واحد يُمكنه يَحمل قيم متناقضة (`status='Open'`،
`order_status='Delivered'`، `shipping_workflow_status='sw_released'`).
لا cross-validation. تَحديث واحد يَنسى الباقي.

**القرار المُقتَرح:** الإبقاء على `shipping_workflow_status` كمصدر حقيقة
وحيد للـlifecycle، احتساب `payment_status` من `remaining_amount`،
deprecation تَدريجي لـ`status` و `order_status` (الإبقاء كـcomputed
properties للـbackwards compat فقط).

### الفئة V: نمط Attachments السيِّئ

ملفات مَرفقة مُخزَّنة كـ`CharField(500)` URLs مُتفرّقة:

| الموقع | الحقل |
|--------|------|
| `LogisticsDeal:46` | `alibaba_link` |
| `LogisticsPayment:212-213` | `bank_swift_image`, `supplier_confirmation_image` |
| `LogisticsShipment:290, 293, 298` | `bill_of_lading_file`, `airway_bill_file`, `tracking_link` |
| `LogisticsExpense` لا حقل، لكن `invoice_doc` يُخزَّن في `LogisticsPayment:203` | `invoice_doc`, `claim_doc` |

**الأمراض:**
1. لا يُمكن رفع ملفات متعدّدة للحقل (URL واحدة لكل حقل).
2. لا metadata: filename, mime_type, size, uploaded_by, uploaded_at.
3. لا cascade على حذف الـowner.
4. orphan files في Cloudinary بَعد حذف السجل.

**الإصلاح المُقتَرَح:** model `Attachment` polymorphic
(GenericForeignKey أو content_type+object_id) مع كل الـmetadata
المذكورة. migration تُحوّل URLs الموجودة لـrows.

### الفئة VI: ضَعف منطق الدفعات والشيكات

| # | الموقع | الخلل |
|---|--------|------|
| **VI-1** | `LogisticsPayment` (170+) يَحوي `bank_swift_image`, `supplier_confirmation_image`, `confirmed_by_supplier`, `supplier_notes` — هذا workflow tracking لا payment | افصل إلى `DealConfirmationStep` model |
| **VI-2** | Cheque attached to `PurchaseInvoice` غير مدعومة بالكامل (موجودة في `SalesInvoice` M2-T3) | أَضِف نفس البنية لـPurchaseInvoice |
| **VI-3** | Disjoint payment models: Firestore deal payments vs SQL CustomerPayment + ClearancePayment + LocalShipment payment + PurchaseInvoice.local_payments_json — **5 مَصادر حقيقة منفصلة** | unification major refactor — موضوع mini-RFC منفصل |
| **VI-4** | `core/payments.py` foundation موجود (I4-09) لكن غير مَوصول | wiring في P-G (مذكور لاحقاً) |
| **VI-5** | Cheque state-machine في `transfer_cheque` يَسمح بـ`Bounced → Collected` (لم يُتحقَّق) | enforce VALID_TRANSITIONS dict |
| **VI-6** | Cheque idempotency: إن فشل ترحيل voucher بعد إنشاء cheques بـDraft، تَبقى يَتيمة | atomic + savepoint rollback |

### الفئة VII: الأخطاء الـRuntime من PDF + الـbrowser

(القائمة من النسخة السابقة — تَبقى لكن في Phase H):

| # | الموقع | الخلل |
|---|--------|------|
| **VII-1** | `AccountingJournalEntryPage.tsx:444` | useCallback بعد early return → hooks violation |
| **VII-2** | `autoDisableScheduler.ts` | 404 كل دقيقة على endpoint غير موجود |
| **VII-3** | `frontend_v2/public/site.webmanifest` | 404 على android-chrome-192x192.png |
| **VII-4** | `logistics/models.py:153, 367` | يَرفع Django ValidationError → DRF يَردّ 500 بدل 400 |
| **VII-5** | `DealForm.tsx:506-509` | error في console فقط، بلا UI feedback |
| **VII-6** | `/api/accounting/cost-centers/` 500 على tenant غير seed | يَحتاج seed command + tenant validation |

### الفئة VIII: ديون كَسلية (lazy code)

| # | الموقع | الخلل |
|---|--------|------|
| **VIII-1** | `ShipmentForm.tsx:50` `useState<any>(shipment ...)` — كل الـformData بـany | أنواع `Shipment` موجودة في types/، استخدمها |
| **VIII-2** | `AccountingJournalEntryPage.tsx:133` `journalsList: any[]` | type `JournalHeader[]` |
| **VIII-3** | 30+ `console.log` في `services/` و `components/` (autoDisableScheduler emojis ☑️/⚠️/❌) | احذف في P-H |
| **VIII-4** | `ShipmentForm.tsx:6` يَستورد `suppliersService` من `firestoreService.ts` | يَجب SQL fully |
| **VIII-5** | `PurchaseInvoice.firestore_id` (line 809-812) | orphan legacy flag — يَجب يُحذَف بـmigration |
| **VIII-6** | `LogisticsDeal` فيها 5 حقول pricing مَخزَّنة (`subtotal, discount_amount, tax_amount, total_amount, remaining_amount`) — كلّها قابلة للحساب من lines + payments | احذف الـ4 الأخيرة، حافظ على `subtotal` فقط، احسب الباقي في `@property` |
| **VIII-7** | TS errors = 39 ثابتة عبر N5-N9 | هدف ≤ 15 |
| **VIII-8** | لا ESLint `react-hooks/rules-of-hooks` (VII-1 ما كان ليَمرّ) | أَضِفه |
| **VIII-9** | `frontend_v2/` root فيها 10+ ملف orphan (`complete_dump.py`, `consolidate*.js`, `dump_code.js`, `extractor.js`, `final_*`, `LITERAL_COMPLETE_CODEBASE*.md`) | gitignore + git rm --cached |
| **VIII-10** | `frontend_v2/dist/` + `dist.zip` مُتعقَّبة | gitignore |
| **VIII-11** | `frontend/` (Next.js منفصل) + `smart-product-search-platform/` تَلوّث الجذر + port 3000 | doc README + قرار مالك |

---

## Pre-Planning Protocols (الـ5 إلزامية)

### 1. الوعي الزمني وموثوقية التبعيات
- التاريخ 2026-05. لا dependencies جديدة. لا libs.

### 2. التدفّق المنطقي ومنع زحف الميزات
- **0 ميزات جديدة.** كل ما هنا normalization + completion + hardening.
- عند الغموض: علِّق `[QUESTION] ...` في commit body. لا قرار صامت.

### 3. المعمارية الذكية (Surgical)
- كل migration تَخصّ تغيير واحد فقط — لا "كل تغييرات Phase".
- استَخدم helpers موجودة (`post_journal()`، `next_document_number()`،
  `get_exchange_rate()`)؛ لا اخترع.
- **Simplicity First:** تَفكيك JSON إلى جدول لا يَعني إعادة كتابة الـAPI
  — أَبقِ الـserializer surface backwards-compatible.

### 4. التتبّع (Safe Logging)
- استبدل كل `print` + `console.log` بـlogger أو حَذف. لا نظام جديد.

### 5. الذاكرة الخارجية (PROJECT_MAP.md)
- بعد كل Phase: حدّث `[ORPHANS & PENDING]` + بصمة الـPhase.

---

## Milestones P-A .. P-J

> **Total:** 10 phases · ~85 task · ~22 migration · 14+ test جديد ·
> **0 ميزة جديدة.** **التقدير:** 50-80 ساعة موديل أرخص + 8 ساعة مراجعة.

---

### P-A — Foundation: Baseline + Safety Net + Tooling (2 ساعة)

- [ ] **P-A-1 — Baseline metrics.** سَجِّل في `task6_baseline.md`:
  `tsc --noEmit` (39 expected)، `manage.py check` (0 expected)،
  `makemigrations --check` (no drift expected)، `vite build` (success)،
  عدد `console.log` في `services/` + `components/` (grep)، عدد `: any`
  في `*.tsx`.

- [ ] **P-A-2 — Branch + worktree.** `git checkout -b claude/task6`.
  كل تنفيذ commit-per-task.

- [ ] **P-A-3 — ESLint + react-hooks rule.** أَضِف
  `eslint-plugin-react-hooks` كـdevDependency. أَنشئ `.eslintrc.cjs`
  بسيط (plugin:react-hooks/recommended فقط). شغّل `npx eslint
  components/**/*.tsx` — سَجِّل العدد. **لا تُصلِح هنا**، الإصلاح في P-H.

- [ ] **P-A-4 — Reproduce all PDF errors live.** Django:8000 + Vite:3000،
  نَفِّذ السيناريوهات الستّة من PDF (VII-1..VII-6). سَجِّل screenshots
  مع timestamps.

---

### P-B — Critical Runtime Hotfixes (4 ساعات)

> **الهدف:** بعد P-B الـconsole يَكون **نظيفاً** والـ500 الناتجة عن
> ValidationError تَختفي. هذه أولوية قبل أي refactor.

- [ ] **P-B-1 — إصلاح hooks-order في AccountingJournalEntryPage** (VII-1).
  `frontend_v2/components/accounting/AccountingJournalEntryPage.tsx`:
  - انقل `showAccountBalance = useCallback(...)` من السطر 444 إلى ما
    قبل `if (loading) return ...` (السطر 434). الموقع الأمثل: بعد
    useEffects (~السطر 246).
  - audit بقية الملف بحثاً عن أيّ hook آخر بعد early return.
  - **Verify:** تَنقَّل بين قيود محاسبية live، console clean.

- [ ] **P-B-2 — DRF Exception Handler موحَّد** (VII-4).
  - أنشئ `core/exception_handler.py`:
    ```python
    from rest_framework.views import exception_handler as drf_handler
    from rest_framework.exceptions import ValidationError as DRFVE
    from django.core.exceptions import ValidationError as DjangoVE
    import logging
    logger = logging.getLogger(__name__)

    def custom_exception_handler(exc, context):
        if isinstance(exc, DjangoVE):
            if hasattr(exc, 'message_dict'):
                exc = DRFVE(detail=exc.message_dict)
            else:
                exc = DRFVE(detail=list(exc.messages) if hasattr(exc,'messages') else [str(exc)])
        response = drf_handler(exc, context)
        if response is None:
            logger.exception("Unhandled exception in view")
        return response
    ```
  - في `core/settings.py` `REST_FRAMEWORK` أَضِف
    `'EXCEPTION_HANDLER': 'core.exception_handler.custom_exception_handler'`.
  - **Verify:** PATCH `/api/logistics/deals/<id>/` بـworkflow غير
    صالح ⇒ 400 + رسالة عربية واضحة. اختبار في P-I.

- [ ] **P-B-3 — تَعطيل autoDisableScheduler** (VII-2).
  `frontend_v2/services/autoDisableScheduler.ts`:
  - استبدل جسم الـclass بـno-op (start/stop يَفعلان لا شيء، لكن public
    API يَبقى).
  - علِّق سَطراً واحداً يَشرح: «معطَّل — Firestore tail غير مَدعوم في
    backend الحالي. راجع P-G لإزالة كاملة».
  - **Verify:** console خالٍ من 404 لـ3 دقائق.

- [ ] **P-B-4 — PWA Manifest icon** (VII-3).
  `frontend_v2/public/site.webmanifest`:
  - الأبسط: احذف الإشارة لـ192. أَبقِ 512 مع `purpose: "any maskable"`.
  - **Verify:** F12 → Application → Manifest: لا warning.

- [ ] **P-B-5 — cost-centers 500 audit** (VII-6).
  - شغّل `curl '/api/accounting/cost-centers/'` على tenant جديد (seed
    الـDB من الصفر). اقرأ stack trace.
  - السبب الأرجح: tenant غير موجود (default=1 fallback). أَضِف
    `accounting/management/commands/seed_minimum_tenant.py` يُنشِئ:
    Tenant + Currency (ILS, USD) + Account-tree أساسي (1000 الأصول،
    2000 الالتزامات، 3000 حقوق الملكية، 4000 الإيرادات، 5000
    المصاريف) + FiscalPeriod للسنة الحالية. idempotent.
  - **Verify:** endpoint يُرجع 200 + `[]` على tenant جديد بعد الـseed.

- [ ] **P-B-6 — UI feedback على workflow patch errors** (VII-5).
  `DealForm.tsx:506-509` `handleShippingWorkflowChange`:
  - استبدل `console.error(...)` بـ`setError(message)` (state موجود) +
    اعرض في الـUI tooltip أحمر.
  - **Verify:** workflow غير صالح ⇒ رسالة عربية في الـUI، لا 500.

**Verifiable P-B:** console clean + 6 سيناريوهات PDF تَعمل + workflow
patch errors تُعرَض UI-side.

---

### P-C — Multi-Tenancy Hardening (3 ساعات)

> **الهدف:** إزالة `default=1` من كل الـlogistics + currency. كل create
> يَفشل loud عند tenant missing.

- [ ] **P-C-1 — Migration لإزالة `default=1` من logistics tenant fields.**
  `logistics/migrations/0026_remove_tenant_default.py`:
  - 9 موديل (III-1 .. III-9) — كل واحد `AlterField` يَحذف `default=1`.
  - الـmigration **لا تُغيِّر schema** (default على Python-level فقط).
  - أَضِف help_text يَشرح: «tenant مطلوب — لا fallback».

- [ ] **P-C-2 — Migration لإزالة `default=1` من currency fields.**
  - `LogisticsExpense.currency`, `LocalShipment.currency`,
    `PurchaseInvoice.currency`, إلخ. `migrations/0027_*`.

- [ ] **P-C-3 — ViewSets adoption لـ`BaseTenantViewSet`.**
  - تَأكَّد أن `LogisticsDealViewSet`, `LogisticsShipmentViewSet`,
    `LogisticsClearanceViewSet`, `LocalShipmentViewSet`,
    `PurchaseInvoiceViewSet` كلّها تَرث `BaseTenantViewSet`
    (`core/mixins.py` — I4-05).
  - تَأكَّد لا `serializer.save(tenant_id=1)` أو fallback في
    `logistics/views.py` — استبدل بـ400 loud.

- [ ] **P-C-4 — اختبار tenant-isolation.**
  `logistics/tests/test_tenant_isolation.py`:
  - أَنشِئ Tenant A و Tenant B، أَنشِئ Deal لكل واحد.
  - بـAPIClient كـA: GET `/api/logistics/deals/` ⇒ سَجَل A فقط.
  - POST `/api/logistics/deals/` بدون X-Tenant-Id ⇒ 400 (لا fallback).
  - GET `/api/logistics/deals/<B.id>/` كـA ⇒ 404.

**Verifiable P-C:** 9 migration · 0 `default=1` في logistics ·
tenant-isolation test ينجح.

---

### P-D — Data-Model Normalization Wave 1 (Clearance + PI Payments) (5 ساعات)

> **الهدف:** فكِّك أكبر JSONField + اَستخدم جدول منظَّم.

- [ ] **P-D-1 — `LogisticsClearanceLine` model جديد** (I-1).
  `logistics/models.py`:
  ```python
  class LogisticsClearanceLine(models.Model):
      LINE_TYPE_CHOICES = [
          ('vat', 'ضريبة القيمة المضافة'),
          ('declaration_fee', 'رسوم البيان الجمركي'),
          ('terminal', 'محطة الشحن'),
          ('permits', 'معالجة التصاريح'),
          ('broker_commission', 'عمولة المخلص'),
          ('customs_system', 'نظام الجمارك «الجيل الجديد»'),
          ('other', 'أخرى'),
      ]
      id = models.AutoField(primary_key=True)
      clearance = models.ForeignKey(LogisticsClearance, on_delete=CASCADE, related_name='lines')
      seq = models.PositiveSmallIntegerField()
      line_type = models.CharField(max_length=32, choices=LINE_TYPE_CHOICES, default='other')
      account = models.ForeignKey(Account, on_delete=PROTECT, null=True, blank=True)
      description = models.CharField(max_length=255)
      debit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
      credit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
      vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
      cost_center = models.ForeignKey(CostCenter, on_delete=SET_NULL, null=True, blank=True)
      class Meta: ordering = ['seq']
  ```
  Migration `logistics/0028_clearance_line.py`.

- [ ] **P-D-2 — Migration backfill `cost_lines` JSON → rows.**
  `logistics/migrations/0029_backfill_clearance_lines.py` (data migration):
  - لكل `LogisticsClearance`، اقرأ `cost_lines` JSON، حوّل كل
    `{label, amount}` إلى `LogisticsClearanceLine` row.
  - مَطابقة `label` العربي إلى `line_type` choice بـlookup table.
  - `amount > 0` ⇒ debit; `amount < 0` ⇒ credit (الأصيل: -100 = دائن).
  - idempotent: skip إذا الـclearance لها lines.
  - **لا تَحذف الـJSONField بعد** — في P-D-4.

- [ ] **P-D-3 — Update API: Serializer + ViewSet + Frontend.**
  - `logistics/serializers.py`: `LogisticsClearanceSerializer` يُعرِض
    `lines` (NestedSerializer) بدل `cost_lines`. أَبقِ `cost_lines`
    كـSerializerMethodField backwards-compat (يَحسبه من lines) — حتى
    لا تَكسر الـUI الحالي.
  - Frontend `CustomsClearanceManagement.tsx`:
    - استبدل `ClearanceCostLine[]` JSON بـtype `ClearanceLine` يَطابق
      الـmodel الجديد.
    - استبدل label-matching بـ`line_type` enum.
    - عَدِّل `notesMeanShippingPayment` (line 51) — احذف! استَخدم
      `payment_purpose` (سيُضاف في P-D-5).

- [ ] **P-D-4 — حذف `cost_lines` JSONField.**
  Migration `logistics/0030_drop_cost_lines_json.py`. **بعد** التَحقّق
  أن frontend لا يَستخدمه + كل البيانات في rows.

- [ ] **P-D-5 — `ClearancePayment.payment_purpose` field** (I-4).
  - أَضِف choice field: `'clearance_fee', 'shipping', 'broker_fee',
    'customs', 'vat', 'other'`.
  - Migration backfill: قَيِّم القيمة من `notes` بـregex:
    - `notes startsWith '[شحن]' or 'شحن'` ⇒ `shipping`.
    - `'[تخليص]'` ⇒ `clearance_fee`.
    - `'[مخلِّص]' or 'عمولة'` ⇒ `broker_fee`.
    - default ⇒ `other`.
  - حدِّث `CustomsClearanceManagement.tsx` ليَستخدم
    `payment.payment_purpose` بدل `notesMeanShippingPayment`.
  - احذف الـfunction `notesMeanShippingPayment` بعد القَطع.

- [ ] **P-D-6 — `PurchaseInvoicePayment` model جديد** (I-2).
  ```python
  class PurchaseInvoicePayment(models.Model):
      id = models.AutoField(primary_key=True)
      tenant = models.ForeignKey(Tenant, on_delete=CASCADE)
      invoice = models.ForeignKey(PurchaseInvoice, on_delete=CASCADE, related_name='payments')
      payment_date = models.DateField()
      amount = models.DecimalField(max_digits=18, decimal_places=2)
      currency = models.ForeignKey(Currency, on_delete=PROTECT)
      exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1)
      payment_method = models.CharField(max_length=32, choices=[...])
      cash_or_bank_account = models.ForeignKey(Account, on_delete=PROTECT)
      reference_number = models.CharField(max_length=100, blank=True, default='')
      is_posted = models.BooleanField(default=False)
      journal = models.ForeignKey(JournalHeader, on_delete=SET_NULL, null=True, blank=True)
      notes = models.TextField(blank=True, default='')
      created_at = models.DateTimeField(auto_now_add=True)
      created_by = models.ForeignKey(User, on_delete=SET_NULL, null=True)
  ```
  Migration `logistics/0031_pi_payment.py`.

- [ ] **P-D-7 — Migration backfill `local_payments_json` → rows.**
  لكل `PurchaseInvoice`، اقرأ `local_payments_json`، أَنشِئ
  `PurchaseInvoicePayment` rows. حافظ على الـJSONField للـrollback.

- [ ] **P-D-8 — حذف `local_payments_json`** + `conversion_metadata_json`
  (I-3). الأخير ⇐ `DocumentConversion` mini-model أو حقول صريحة على
  `PurchaseInvoice`:
  - `converted_from_shipment` (FK، nullable)
  - `converted_at` (DateTime)
  - `converted_by` (User FK)
  Migration `logistics/0032_drop_purchase_invoice_json.py`.

**Verifiable P-D:** clearance.lines جدول حقيقي · clearance UI يَعمل
بدون JSON-parse · `notesMeanShippingPayment` محذوف · PI payments جدول
حقيقي · 0 `local_payments_json` في الـDB.

---

### P-E — Data-Model Normalization Wave 2 (Line-Level Fields) (5-7 ساعات)

> **الهدف:** أَضِف الحقول المفقودة في II-D + II-E (DealItem +
> PurchaseInvoiceItem).

- [ ] **P-E-1 — DealItem enrichment migration** (II-D).
  `logistics/migrations/0033_deal_item_enrichment.py`:
  - أَضِف: `seq` (PositiveSmallIntegerField)، `catalog_number`،
    `name_snapshot`، `description_line`، `unit` (FK لـUnit إن موجود،
    وإلا CharField)، `warehouse` (FK لـWarehouse)،
    `extra_qty` (Decimal)، `batch_number`، `serial_number`،
    `manufacture_number`، `expiry_date`، `line_currency` (FK)،
    `line_exchange_rate` (Decimal)، `second_date`، `is_taxable`،
    `vat_percent`، `discount_percent`، `discount_amount`.
  - كلّها nullable/default سَلِسة — لا backfill إجباري.

- [ ] **P-E-2 — PurchaseInvoiceItem enrichment** (II-E). نفس الحقول
  (II-D-1 .. II-D-13). Migration `logistics/0034_pi_item_enrichment.py`.

- [ ] **P-E-3 — Backfill من notes إن وُجد pattern.**
  Data migration `logistics/0035_backfill_line_fields.py`:
  - لكل `DealItem`، اقرأ `notes`، حاول استخراج:
    - `batch:XXX` → `batch_number = XXX`
    - `expiry:YYYY-MM-DD` → `expiry_date`
    - `lot:XXX` → `manufacture_number`
  - بقيّة الـnotes تَبقى.
  - log كل تَحويل.

- [ ] **P-E-4 — Serializer + UI exposure (DealForm).**
  - `LogisticsDealSerializer` يَعرِض الحقول الجديدة.
  - `frontend_v2/components/procurement/deals/DealForm.tsx`: أَضِف
    أعمدة جديدة في الـAseelGrid items (batch / expiry / warehouse /
    extra_qty / discount% / vat%).
  - **لا تَكسر الـUI الحالي** — الأعمدة الجديدة hidden by default،
    تَظهر عبر «إظهار الأعمدة المتقدّمة» toggle (helper موجود في
    AseelDenseTable N9-T7).

- [ ] **P-E-5 — Serializer + UI exposure (InvoiceForm).** نفس P-E-4
  للـ`InvoiceForm.tsx`.

- [ ] **P-E-6 — per-line VAT enforcement.**
  - `logistics/views.py:PurchaseInvoiceViewSet.post_to_accounting`:
    عند ترحيل الـjournal، عوض VAT موحَّد (`header.vat_percent`)
    استخدم `sum(line.vat_percent * line.subtotal)` للـVAT line.
  - اختبار: PI بـ3 lines، VAT 17/0/8% → الـJournal يُرجع 3 VAT lines
    منفصلة (أو سَطر مُجمَّع بـcorrect total).

**Verifiable P-E:** DealItem + PIItem فيها 13 حقل جديد لكل واحد ·
per-line VAT يَعمل · UI advanced toggle موجود.

---

### P-F — Data-Model Normalization Wave 3 (Clearance Header + Status Unification) (4 ساعات)

- [ ] **P-F-1 — LogisticsClearance header enrichment** (II-C-1..II-C-9).
  Migration `logistics/0036_clearance_header_enrichment.py`:
  - `transaction_time` (TimeField)
  - `second_date` (DateField)
  - `licensed_dealer_no` (CharField100)
  - `settlement_invoice_number` (CharField100)
  - `currency` (FK Currency)
  - `exchange_rate` (Decimal)
  - `vat_statement` (FK VatStatement)
  - `subtotal_no_vat` (Decimal)
  - `vat_total` (Decimal)
  - `grand_total` (Decimal)
  - `journal` (FK JournalHeader, direct)
  - `editable` (Boolean default True)
  كل nullable + default sensible.

- [ ] **P-F-2 — Shipment header enrichment** (II-B). Migration
  `logistics/0037_shipment_header_enrichment.py`:
  - `transaction_time`, `transit_journal` FK, `editable` flag,
    `vat_statement` FK, `subtotal/vat_total/grand_total`.

- [ ] **P-F-3 — Deal header enrichment** (II-A). Migration
  `logistics/0038_deal_header_enrichment.py`:
  - `transaction_time`, `second_date`, `licensed_dealer_no`,
    `editable`.
  - book_number helper integration: تَأكَّد أن `LogisticsDeal.save()`
    يَستخدم `next_document_number(tenant, 'deal', book_number)` من
    accounting/services.py (N0-T3).

- [ ] **P-F-4 — Status field deprecation plan** (الفئة IV).
  - **القرار:** `shipping_workflow_status` يَبقى source of truth.
  - `LogisticsDeal.status` و `LogisticsDeal.order_status` يَصيرون
    `@property` computed:
    ```python
    @property
    def status(self):
        sw = self.shipping_workflow_status
        if sw is None or sw == 'sw_mfg_start': return 'Open'
        if sw == 'sw_released': return 'Closed'
        return 'Shipped'
    ```
  - `payment_status` يُحسَب من `remaining_amount` (computed).
  - أَزِل الأعمدة الفعلية في migration P-F-5 بعد التَحقّق أن لا
    queries تَستخدمها.
  - **هذا تَغيير API كبير — لكن read-only لا breaking.**

- [ ] **P-F-5 — Migration drop legacy status columns.** بعد P-F-4 +
  audit أن لا queries SQL خام تَستخدم `status`/`order_status`/
  `payment_status` كأعمدة. Migration حذف. **اختياري — قد يُؤجَّل
  لـtask7 إن وَجدنا قَلَقاً.**

- [ ] **P-F-6 — UI updates للـClearanceForm.**
  - أَضِف 11 حقل في header band: الساعة / تاريخ ثاني / مشتغل مرخص /
    رقم فاتورة المقاصة / العملة / سعر العملة / كشف الضريبة (read-only) /
    رقم القيد (read-only) / المجموع بدون الضريبة / مجموع الضريبة /
    مبلغ البيان الإجمالي.

**Verifiable P-F:** 3 migrations · `LogisticsClearanceForm` يَعرض كل
حقول الأصيل · status هو computed property.

---

### P-G — UI Density Redesign + Workflow Merge (الأهمّ — 20-30 ساعة)

> **الهدف:** نفس فلسفة الكَثافة على **كل شاشة في المشروع** (لا فقط
> الـimport flow). 14 sub-phase:
>
> - **G-1..G-6:** شاشة الاستيراد الموحَّدة `ImportDocumentScreen`
>   (شحنة + تخليص + نقل محلي + فاتورة شراء في tabs أفقية).
> - **G-7..G-11:** Density treatment لكل forms الأخرى (Sales،
>   Accounting، Procurement، Inventory، HR/Misc).
> - **G-12:** Universal Modal → SidePanel sweep.
> - **G-13:** Density audit script + CI guard.
> - **G-14:** `docs/ui_density_rules.md` كَدستور كَثافة دائم.
>
> **القاعدة:** على شاشة 1920×1080 يَجب كل form/list/report يَدخل
> viewport بدون scroll للـcontainer (الـtab content أو الـtable يَكون
> له scroll داخلي فقط).
>
> **المرجع البصري:** لقطات الأصيل + مراجع `docs/aseel_reference/full/
> الإرساليات.txt:1-214`. **القالب الذهبي:** `SalesInvoiceEditor.tsx`
> (M1) بَنياً، لكن مع توسيع الـtabs لتَحوي الـclearance + local.

#### P-G-1 — إنشاء `ImportDocumentScreen` (الشاشة الموحَّدة)

- [ ] **P-G-1-a — مكان الملف.**
  أنشئ `frontend_v2/components/import-flow/ImportDocumentScreen.tsx`.
  يَستقبل `shipmentId: string | null` (إن null = جديد).
  يَستخدم `AseelDocumentShell` + `AseelGrid` + `AseelIndexPicker`.

- [ ] **P-G-1-b — Header band مُكثَّف (4 صفوف × 6 أعمدة = 24 حقل
  مَرئي).**
  ```
  ┌────────────────────────────────────────────────────────────────────┐
  │ Row 1: رقم الإرسالية | دفتر | تاريخ | الساعة | تاريخ ثاني | الوكيل │
  │ Row 2: اسم الوكيل | المورد | الاسم | نوع الإرسالية | عملة | السعر  │
  │ Row 3: رقم البوليصة | الحاوية | المغادرة | الوصول | السفينة | الرحلة│
  │ Row 4: المخلِّص | رقم البيان | تاريخ التخليص | فاتورة المقاصة |    │
  │         كشف الضريبة | محرَّر                                       │
  └────────────────────────────────────────────────────────────────────┘
  ```
  - استَخدم CSS grid (`grid-template-columns: repeat(6, 1fr)`) داخل
    AseelDocumentShell `header` prop.
  - كل حقل بـ`aseel-input` class + `aseel-field-label` (compact).
  - ارتفاع الـheader band ≤ 180px.

- [ ] **P-G-1-c — Status timeline أفقي مُكثَّف (~32px).**
  استبدال `ShipmentStatusVisualizer` بـsingle-row chip:
  ```
  ●مستودع_الوكيل → ●جمارك_الصين → ◐البحر → ○الميناء → ○جمارك_إسرائيل → ○مفرج → ○محلي
  ```
  - `●` = مكتمل، `◐` = حالي، `○` = قادم.
  - ارتفاع ≤ 32px. خلفية `var(--aseel-bg-strip)`.
  - عند click على chip ⇒ يَتنقل لتلك المرحلة (ينقذ مرحلة workflow).

- [ ] **P-G-1-d — Main area بـtabs أفقية كَثيفة (لا CollapsibleSection).**
  - tabs: «الصفقات» / «بنود الإرسالية» / «التخليص (بنود)» / «النقل
    المحلي» / «الدفعات» / «الحسابات» / «المرفقات» / «ملاحظات».
  - كل tab يَفتح **في نفس الـcontent area** (لا modal، لا new route).
  - الـtab الافتراضي: «الصفقات» (لأنه أوّل ما يَفتحه المستخدم).
  - ارتفاع tab bar ≤ 36px.

- [ ] **P-G-1-e — Right-side dock (Totals + Status compact، ~300px width).**
  Side panel ثابت يَمين الـscreen يَعرض:
  ```
  الإجمالي:        100,000
  المدفوع:          40,000
  المتبقي:          60,000
  ─────────────
  تكلفة شحن:        5,000
  تكلفة تخليص:      3,200
  نقل محلي:         1,500
  ─────────────
  الحالة:          arrived
  السجل:            5/12
  ```
  - الـtotals تَتحدَّث live من كل tab.
  - يَختفي على شاشات أصغر < 1280px (يَنتقل لـbottom horizontal).

- [ ] **P-G-1-f — Bottom status bar (~32px).**
  المستخدم | رقم القيد | رقم الإرسالية | الوقت | اتصال — single line.

- [ ] **P-G-1-g — Viewport budget.**
  - Toolbar (~44px) + Header band (~180px) + Timeline (~32px) +
    Tabs (~36px) + Tab content (flexible) + Status bar (~32px) +
    Right dock (تأخذ من الـcontent، لا تُضاف للارتفاع).
  - الإجمالي fixed ≈ 324px → الـtab content يَأخذ
    `min(calc(100vh - 324px), 600px)`.
  - **شَرط القبول:** على شاشة 1080p (1920×1080) كل المحتوى يَجب
    يَكون مَرئياً بدون scroll للـcontainer (الـtab content وحده له
    scroll داخلي).

#### P-G-2 — Routing + Migration من الشاشات القديمة

- [ ] **P-G-2-a — App.tsx route.**
  أَضِف route `/import-flow/<shipmentId>` يُرَنْدِر `ImportDocumentScreen`.

- [ ] **P-G-2-b — Sidebar.**
  أَضِف «رحلة الاستيراد» تحت قائمة «المشتريات». اِجعلها الـdefault
  بدل «الشحنات» / «التخليص» / «النقل المحلي» (الثلاثة الأخيرة
  تَنتقل لـsubmenu «وصول مباشر للقوائم» للوصول المستقل إذا أراد).

- [ ] **P-G-2-c — backwards-compat redirects.**
  - `/shipments/<id>` ⇒ redirect لـ`/import-flow/<id>`.
  - `/clearance/<id>` ⇒ يَفتح `/import-flow/<shipment_id>?tab=clearance`.
  - `/local-shipments/<id>` ⇒ `/import-flow/<shipment_id>?tab=local`.
  - الـlist pages (ShipmentManagement / ClearanceManagement /
    LocalShippingPage) **تَبقى** كـbrowsing tools، لكن النقر على
    سَطَر يَفتح الـImportDocumentScreen.

#### P-G-3 — تَفكيك الشاشات القديمة

- [ ] **P-G-3-a — حذف `ShipmentForm.tsx`.**
  بعد التَأكَّد أن `ImportDocumentScreen` يُغطّي كل وظائفه + redirect
  P-G-2-c يَعمل. احذف الملف + الـsubcomponents
  (`ShipmentBasicInfo.tsx`, `ShipmentShippingDetails.tsx`,
  `ShipmentStatusVisualizer.tsx` — الأخير يَنتقل لـ`import-flow/
  CompactTimeline.tsx`).

- [ ] **P-G-3-b — حذف form-mode من `CustomsClearanceManagement.tsx`.**
  الـlist mode يَبقى (master). كل form-mode (header + lines + cost
  breakdown) يَنتقل لـ`ImportDocumentScreen` كـtab. الـlist row click
  يَفتح الـimport-flow بـtab=clearance.

- [ ] **P-G-3-c — `LocalShippingPage` نفس الشيء.**
  list-mode يَبقى. form-mode يَنتقل لـtab «النقل المحلي» في
  ImportDocumentScreen.

#### P-G-4 — نفس النمط لـ`DealForm` (0-7)

- [ ] **P-G-4-a — ضَغط `DealForm.tsx` لـsingle viewport.**
  - Header band 4×6 = 24 حقل.
  - استبدال CollapsibleSection بـtabs أفقية.
  - Right dock للـtotals.
  - **لا تُدمج مع ImportDocumentScreen** — Deal هو document مُستقل
    قبل الشحن. لكن طَبِّق نفس فلسفة الكَثافة.

- [ ] **P-G-4-b — زر «إنشاء/فتح شحنة» في DealForm.**
  إن الـdeal مَربوط بشحنة، زر يَفتح `ImportDocumentScreen` للشحنة
  المُرتَبطة. إن لا، زر «إنشاء شحنة من هذه الصفقة».

#### P-G-5 — نفس النمط لـ`InvoiceForm` purchase (0-8)

- [ ] **P-G-5-a — ضَغط `InvoiceForm.tsx`.**
  نفس النمط. لكن InvoiceForm **مُدمج جزئياً** في
  ImportDocumentScreen كـtab «فاتورة الشراء» — يَجب أن يَكون نفس
  الكَود بـmode=embedded أو mode=standalone.

#### P-G-6 — استبدال Modals بـSide Panels (0-10)

- [ ] **P-G-6-a — `AseelSidePanel` primitive جديد.**
  `frontend_v2/components/aseel/AseelSidePanel.tsx`:
  - يَنزلق من اليمين (RTL) بـwidth 380px.
  - يَأخذ `open`, `onClose`, `title`, `children`, `width?`.
  - **لا يَحجُب** الـform — الـform يَبقى تَفاعلياً (لكن `aria-busy`).

- [ ] **P-G-6-b — تَحويل Modals.**
  استبدِل:
  - `SupplierViewModal` ⇒ `AseelSidePanel`.
  - `ShipmentDealSelector` ⇒ `AseelSidePanel` بـsearchable list.
  - `AseelIndexPicker` (لكل الحسابات/الموردين/إلخ) — _ابقَه كما هو_
    (modal مَركَزي قَصد، لأنه decision point). فقط Side panels
    للـbrowse/view modals.

#### P-G-7 — Sales Forms Density (M1 golden + sales suite)

> **النطاق:** كل forms الـsales في `frontend_v2/components/sales/`.
> الـpattern نفسه (header band 4-6 أعمدة × 3-5 صفوف، tabs أفقية، right
> dock، status bar، viewport ≤ 1080p). لا CollapsibleSection. لا
> stacked sections.

- [ ] **P-G-7-a — `SalesInvoiceEditor.tsx` (M1، قالب ذهبي).**
  - راجع بـDevTools: هل كل المحتوى يَدخل في 1080p بدون scroll؟
  - إن لا: ضَغط tabs الـ«الحسابات» / «الدفعات» / «الملاحظات» —
    احذف أي `space-y-{4-9}` و `p-{4-9}` غير ضروري.
  - voucher modal (M2-T3 attached cheques) — تَحقّق أنه AseelSidePanel
    (P-G-6) لا modal مَركَزي.

- [ ] **P-G-7-b — `SalesCustomerPaymentsPage.tsx` (F9).**
  - header band 6 أعمدة × 3 صفوف = 18 حقل (دفتر / رقم السند /
    التاريخ / الساعة / تاريخ ثاني / العملة / السعر / العميل /
    الصندوق / نقدا / مجموع الشيكات / خصم مصدر % / خصم مصدر مبلغ /
    المجموع / مبلغ الحساب / المتبقي / رقم القيد / كشف الضريبة).
  - tabs: «الشيكات (AseelGrid)» / «الحسابات» / «الملاحظات» / «بيانات أخرى».
  - **احذف** أي CollapsibleSection للـcheques table — يَدخل tab.

- [ ] **P-G-7-c — `CreditDebitNotesPage.tsx` (F10).**
  - header 5 × 3 = 15 حقل (دفتر / رقم الإشعار / التاريخ / الساعة /
    تاريخ ثاني / رقم القيد / كشف الضريبة / الحساب + فهرس /
    رقم فاتورة المقاصة / حساب الإشعار / النوع / المبلغ /
    يشمل ض / المبلغ بدون ضريبة / مبلغ الضريبة الإجمالي).
  - tabs: «الحسابات» / «ملاحظات».

- [ ] **P-G-7-d — `SalesQuotationsPage.tsx` (F11).**
  - header 6 × 3 = 18 حقل + «فعّال حتى» + «فعّال» checkbox.
  - main: AseelGrid items.
  - tabs: «الحسابات / ملاحظات / المرفقات».

- [ ] **P-G-7-e — `SalesReturnEditor.tsx` + `PurchaseReturnEditor.tsx`
  (N-F2, N-F3).**
  - نفس بنية SalesInvoiceEditor قَبَلْ density.
  - **مَيزة خاصّة:** field `original_invoice` يَفتح AseelSidePanel
    يَعرض الفاتورة الأصلية read-only بجانب الـreturn — مَطلب الأصيل.

- [ ] **P-G-7-f — `SupplierPaymentsPage.tsx` (N-F4).**
  - مَرآة P-G-7-b للمورّدين.

- [ ] **P-G-7-g — `SalesInvoicesPage.tsx`, `SalesCustomersPage.tsx`
  (L7, L8).**
  - list pages: filter bar ≤ 64px، stats band ≤ 56px،
    AseelDenseTable يَملأ الباقي.
  - **احذف** أي `space-y-{4-9}` بين الـbands.

- [ ] **P-G-7-h — `SalesSettingsPage.tsx` (L9).**
  - 4 tabs بدل 4 sections مكدّسة (بيانات عامة / حسابات افتراضية /
    ضرائب / أرقام دفاتر — إن لم تَنتقل لـGroupConstants).

#### P-G-8 — Accounting Forms Density

- [ ] **P-G-8-a — `AccountingJournalEntryPage.tsx` (F7).**
  - header 6 × 2 = 12 حقل (رقم القيد / التاريخ / الساعة / تاريخ
    ثاني / البيان الإجمالي / المرجع / العملة / السعر / دفتر / حالة /
    المستخدم / مركز التكلفة الافتراضي).
  - main: AseelGrid journal lines (full-width).
  - dock يَمين: total Dr / total Cr / Difference / status.
  - **احذف** أي tooltip ضخم — استبدل بـside-panel على Space.

- [ ] **P-G-8-b — `AccountingJournalListPage.tsx` (L15).**
  - filter bar (من-إلى تاريخ + دفتر + حساب + مستخدم) في **سَطر واحد
    horizontal scrollable** ≤ 56px.

- [ ] **P-G-8-c — `AccountingCoaPage.tsx` (L16).**
  - شَجَرة الحسابات: يَجب تَملأ viewport. **احذف** أي header bands
    غير الـfilter (بحث + فلتر نوع الحساب).

- [ ] **P-G-8-d — `AccountingChequesPage.tsx` (L14).**
  - **دَمج**: list + transfer dialog في نفس الصفحة. النقر على شيك
    يَفتح AseelSidePanel بـtransfer form (لا modal مَركَزي).

- [ ] **P-G-8-e — `FiscalPeriodsPage.tsx`, `ExchangeRatesPage.tsx`,
  `AccountingLandedCostPage.tsx`, `AccountingVatReportPage.tsx`,
  `AccountingTrialBalancePage.tsx`, `AccountingGeneralLedgerPage.tsx`,
  `BalanceSheetPage.tsx`, `IncomeStatementPage.tsx`,
  `VatStatementsPage.tsx` (L17, L18, R1-R6, N-F5).**
  - كلّها: filter bar صَفّ واحد + AseelReportTable يَملأ الباقي.
  - **احذف** padding/spaces بين الـfilter + table.
  - export-CSV button في top-right (موجود من N9-T6) — لا تَأخذ سَطراً
    منفصلاً.

- [ ] **P-G-8-f — `YearEndClosePage.tsx` (new P-H-10).**
  - shell + 1 header band + form section + زر تَنفيذ — كل شيء في
    viewport واحد.

- [ ] **P-G-8-g — `GroupConstantsPage.tsx` (N0-T4).**
  - 4 tabs الموجودة (بيانات عامة / أرقام الدفاتر / حسابات افتراضية /
    ضرائب) — كل tab يَحوي header band مَكثَّف بدون
    CollapsibleSection داخلي.

#### P-G-9 — Procurement Forms Density (غير الـimport-flow)

- [ ] **P-G-9-a — `DealForm.tsx` — موسَّع.**
  مُذكور في P-G-4، لكن **تَفصيل:**
  - header 6 × 4 = 24 حقل (رقم الصفقة / دفتر / تاريخ / الساعة /
    تاريخ ثاني / تاريخ الاستحقاق / المورد + فهرس / الاسم / العنوان /
    مشتغل مرخص / طريقة شحن / Incoterms / وسيلة دفع / أيام إنتاج /
    أيام تسليم / CBM / وزن / شهادات / عملة / سعر / الحالة /
    workflow status / نوع ضريبة / محرَّر).
  - tabs: «بنود الصفقة» / «أقساط الدفع» / «الشحنة المُرتَبطة (link)» /
    «الحسابات» / «المرفقات» / «ملاحظات».
  - زر «فَتح شاشة الاستيراد» (`ImportDocumentScreen`) إن مَربوط
    بشحنة.

- [ ] **P-G-9-b — `PriceOfferForm.tsx` (F5).**
  - header 5 × 3 = 15 حقل + 4 offer types switch.
  - main: AseelGrid items.
  - tabs: «الحسابات / ملاحظات / المرفقات».

- [ ] **P-G-9-c — `PriceOfferManagement.tsx`,
  `DealManagement.tsx`, `ShipmentManagement.tsx`,
  `LocalShippingPage.tsx` (L1-L3, L10).**
  - list pages — راجع filter bar + stats band يَكونوا compact.

- [ ] **P-G-9-d — `SupplierManagement.tsx` (L5).**
  - filter bar + stats band compact.

#### P-G-10 — Inventory + Items Forms Density

- [ ] **P-G-10-a — `ItemFormAseel.tsx` (F6).**
  - 6 pages موجودة (بيانات عامة / الأرصدة / الأسعار 5+5 / المتاجرة /
    أخرى / معادلات).
  - **كل page** يَجب يَدخل viewport بدون scroll.
  - الـpages tabs أفقية (لا horizontal stepper sidebar).
  - **page الأسعار 5+5**: عرض tabular (5 sale rows × columns +
    5 purchase rows) — جدول واحد كَثيف، لا 10 cards.

- [ ] **P-G-10-b — `ItemsManagement.tsx` (L4).**
  - filter bar compact + AseelDenseTable.

- [ ] **P-G-10-c — `StockLevelsPage.tsx`, `StockMovementsPage.tsx`,
  `InventoryValuationPage.tsx` (L11, L12, N-F8).**
  - filter bar (مخزن / فئة / حالة) صَفّ واحد + جدول.

#### P-G-11 — HR/Misc/SQL/Dashboard Density

- [ ] **P-G-11-a — `Dashboard.tsx`.**
  - KPI cards صَفّ واحد horizontal (4-6 cards) + لا فجوات.
  - chart واحد فقط (الأهم) — لا تَكدُّس.

- [ ] **P-G-11-b — `TaskManagement.tsx`, `AttendanceManagement.tsx`,
  `EmployeePointsManagement.tsx`, `PointsHistoryPage.tsx`,
  `ResultsPage.tsx`.**
  - كلّها list pages: filter compact + AseelDenseTable.

- [ ] **P-G-11-c — `SettingsPage.tsx`.**
  - section واحد لكل tab، tabs أفقية.

- [ ] **P-G-11-d — SQL pages (`SqlDeals/Shipments/Clearances/
  PurchaseInvoices`).**
  - تَوحيد: filter compact + table. **اقتراح:** دَمج الـ4 في صفحة
    واحدة بـmaster tabs أعلى (مَلاحظة: يَعتمد على approval المالك).

- [ ] **P-G-11-e — `PropertyRentalPage.tsx`.**
  - نفس النمط (realestate خارج النطاق المحاسبي لكن يَنطبق عليه نفس
    الـdensity rules).

#### P-G-12 — Universal Modal → Side Panel sweep

- [ ] **P-G-12-a — Audit كل `Modal` / `Dialog` في المشروع.**
  ```
  grep -rEn "Modal|Dialog|isOpen=" frontend_v2/components | grep -v ".test.tsx"
  ```
  لكل modal:
  - **Decision modals** (pickers، confirmations): تَبقى modals
    (centered overlay).
  - **Browse/view modals** (SupplierViewModal، DealSelector،
    ShipmentDetailView، إلخ): استبدِل بـAseelSidePanel.

- [ ] **P-G-12-b — تَحديد الـside panels في primitives.**
  أَضِف `AseelSidePanel` بـtypes + tests + AseelKitStory demo.

#### P-G-13 — Density Audit script + CI guard (الـscript الأشمل)

- [ ] **P-G-13-a — `scripts/measure_form_density.ts`.**
  - يَفحَص كل `*Form.tsx`, `*Editor.tsx`, `*Page.tsx`:
    - عدد `CollapsibleSection` ≤ 1 (يُفضَّل 0).
    - عدد `space-y-[4-9]` ≤ 2.
    - عدد top-level `<section>` أو `<div>` كـconsecutive-flex-col
      مع padding ≤ 4.
    - وجود `AseelDocumentShell` (لكل form).
    - عدد `useState<any>` = 0.
  - يُنتج report `frontend_v2/density_report.json`.
  - يَفشل CI لو ملف يَتجاوز الحدود.

- [ ] **P-G-13-b — ESLint custom rule (اختياري لكن مُوصى).**
  `no-collapsible-section-in-form`: يَمنع import `CollapsibleSection`
  في ملفات تَنتهي بـ`Form.tsx` أو `Editor.tsx`.

#### P-G-14 — Universal Density Principles (ملف توثيق)

- [ ] **P-G-14-a — `docs/ui_density_rules.md`.**
  وَثيقة 1-pager تَنصّ على القواعد العامّة:
  1. **Header band:** 4-6 أعمدة × 3-5 صفوف. ≤ 200px ارتفاع.
  2. **No CollapsibleSection** في forms — استَخدم tabs أو
     AseelFormSection (بدون collapse).
  3. **No `space-y-{4-9}`** بين top-level sections.
  4. **No `p-{6-9}`** على containers رئيسية.
  5. **Status timeline** ≤ 32px (single row).
  6. **Tabs** أفقية ≤ 36px.
  7. **Right dock** للـtotals/status ≤ 320px width.
  8. **Bottom status bar** ≤ 32px.
  9. **Filter bar** على list pages: صَفّ واحد horizontal-scroll إن
     لزم.
  10. **Stats band** على list pages: ≤ 56px.
  11. **Modals** فقط للـdecisions؛ **side panels** للـbrowse.
  12. **Viewport budget:** على 1920×1080 لا scroll على
      الـcontainer الرئيسي. الـtab content فقط له scroll داخلي.
  هذه الوثيقة مَرجع لكل صفحة جديدة مستقبلاً.

**Verifiable P-G (شامل كل sub-phases G-1 .. G-14):**

1. **شاشة الاستيراد الموحَّدة:**
   `ImportDocumentScreen` على `/import-flow/<id>` · 8 مراحل
   timeline ≤ 32px · header band 24 حقل · tabs بدل CollapsibleSection ·
   viewport 1920×1080 بدون scroll للـcontainer (DevTools verify) ·
   ShipmentForm + Basic + ShippingDetails محذوفة.

2. **Sales forms (P-G-7):** SalesInvoiceEditor + CustomerPayments +
   CreditDebit + Quotations + Returns + SupplierPayments — كلّها
   single viewport بدون CollapsibleSection.

3. **Accounting forms (P-G-8):** JournalEntry + JournalList + CoA +
   Cheques + FiscalPeriods + ExchangeRates + GL + TB + VAT report +
   Landed + BalanceSheet + IncomeStatement + VatStatements + YearEnd
   + GroupConstants — كلّها compact.

4. **Procurement (P-G-9):** DealForm + PriceOfferForm + 4 list
   managements — single viewport.

5. **Inventory/Items (P-G-10):** ItemForm 6 pages كل page في viewport ·
   list pages compact.

6. **HR/Misc/SQL (P-G-11):** Dashboard + 5 HR pages + Settings + SQL
   pages — single viewport.

7. **Modals → Side Panels (P-G-12):** كل browse/view modals صارت
   `AseelSidePanel` (لا تَحجُب). Decision modals (pickers) باقية
   modals.

8. **Density script (P-G-13):** `scripts/measure_form_density.ts`
   ينجح على كل forms والـlist pages؛ CI يَفشل لو أي ملف تَجاوز الحدود.

9. **توثيق (P-G-14):** `docs/ui_density_rules.md` موجود ومَقروء.

---

### P-H — Business Logic Completion (5-6 ساعات)

- [ ] **P-H-1 — Cheque attached to PurchaseInvoice** (VI-2).
  مرآة `attach_payment_voucher` لـ`SalesInvoice` (M2-T3):
  - `accounting/models.py:Cheque` فيها FK لـPurchaseInvoice إن لم
    تَكن (راجع — `accounting/migrations/0017_add_cheque_invoice_links`
    أضافها فقط لـSalesInvoice). إن لا، migration
    `accounting/0019_cheque_pi_link.py`.
  - service `attach_pi_payment_voucher(invoice, cash, cash_account,
    cheques, user)` في `logistics/services.py` (إن غير موجود — أَنشِئه).
  - UI: في `InvoiceForm.tsx` (purchase) زر «سند مالي مرفق» يَفتح
    modal مَطابق لـSalesInvoice voucher modal.

- [ ] **P-H-2 — Sales/Purchase Return stock reconciliation** (مذكور
  سابقاً، يُؤكَّد هنا).
  - `sales/services.py:post_sales_invoice`: عند
    `invoice_kind in ('sale_return','purchase_return')`:
    - استدعِ `inventory.services.record_stock_movement` بـtype
      `RETURN_IN` (sale_return) / `RETURN_OUT` (purchase_return).
    - استخدم `original_invoice.line.unit_cost` بدل current WAC.
  - اختبار: بَيع 10@100، RETURN_IN لـ3 ⇒ WAC unchanged + stock=7.

- [ ] **P-H-3 — SupplierPayment AP fallback** (VI-2 mirror).
  `sales/services.py:post_supplier_payment` priority:
  1. `partner.linked_account`
  2. `partner.group.account_payable`
  3. `SalesSettings.default_ap_account` (أَضِف الحقل إن غير موجود)
  4. `Account.objects.get(code='2101')`
  5. raise ValidationError صريح إن لا شيء.

- [ ] **P-H-4 — Cheque state machine enforcement** (VI-5).
  `accounting/services.py:transfer_cheque`:
  ```python
  VALID_TRANSITIONS = {
      'Draft': ['Under_Collection', 'Cancelled'],
      'Under_Collection': ['Collected', 'Bounced', 'Returned'],
      'Collected': [],
      'Bounced': ['Under_Collection', 'Cancelled'],
      'Returned': ['Cancelled'],
      'Cancelled': [],
  }
  ```
  - raise ValidationError إن الـtransition غير مُمَلَّك.
  - اختبار في `accounting/tests/test_cheque_lifecycle.py`.

- [ ] **P-H-5 — Voucher atomicity** (VI-6).
  `sales/services.py:attach_payment_voucher` + `post_sales_invoice`:
  - استخدم `transaction.atomic()` يَلفّ cheque-creation + post.
  - savepoint — إن post فَشل، الـcheques يُلغَون.
  - اختبار: mock `post_journal` ليَرفع، تَأكَّد `Cheque.count==0`.

- [ ] **P-H-6 — VatStatement uniqueness + lock**.
  `sales/models.py:VatStatement`:
  - `UniqueConstraint(tenant, period_from, period_to,
    name='unique_vat_statement_period')`.
  - service `build_vat_statement`:
    - `SalesInvoice.objects.select_for_update().filter(
      vat_statement__isnull=True, transaction_date__range=...)`.
    - رفع ValidationError إن VatStatement موجود يُغطّي الفترة.
  - migration `sales/0015_vat_statement_unique.py`.

- [ ] **P-H-7 — Account overrides activation** (مذكور سابقاً).
  `sales/services.py:_resolve_*_account`:
  - priority: `line.product.account_*_override` (N8-T10) → SalesSettings
    → fallback القديم.
  - نفس الشيء في `logistics/views.py` للـpurchase.
  - اختبار: PI بـProduct بـpurchase_account_override=2001 ⇒ سَطر
    الـinventory يَستخدم 2001.

- [ ] **P-H-8 — Multi-currency FX per allocation**.
  `sales/services.py:post_customer_payment`:
  - الحساب الحالي: FX يُحسَب على dispatch واحد per payment. خاطئ
    إن payment يُغطّي فواتير بـعملات مختلفة.
  - الإصلاح: per-allocation FX gain/loss.
  - اختبار: payment USD 1000 ⇒ allocate لـinvoice EUR + invoice ILS
    ⇒ Journal فيه 2 FX line منفصلة.

- [ ] **P-H-9 — `core/payments.py` wiring** (VI-4).
  - استبدل validations في 3 ViewSets بـ`core.payments.validate_payment(ctx)`:
    - `sales/views.py:CustomerPaymentViewSet.create`
    - `logistics/views.py:LogisticsClearanceViewSet.pay_from_cashbox`
    - `logistics/views.py:LogisticsPaymentViewSet.create`
  - لا تَستبدل `post_*` services — فقط validation entry.

- [ ] **P-H-10 — Year-End Close UI page**.
  - أنشِئ `frontend_v2/components/accounting/YearEndClosePage.tsx`
    بـAseelDocumentShell. حقول: السنة المالية، تاريخ، حساب الأرباح
    المُحتجَزة، عرض الفترات.
  - يَستدعي `POST /api/accounting/fiscal-periods/year-end-close/`
    (موجود من I4-04).
  - App.tsx route + Sidebar.

- [ ] **P-H-11 — TenantBook race fix.**
  `accounting/services.py:next_document_number`:
  - استخدم `F('last_used_number') + 1` (لا instance assignment).
  - اختبار concurrent: 5 threads × 10 calls = 50 numbers فريدة.

**Verifiable P-H:** 11 سَلسلة backend hardening · cheque attached
لـPI live · Year-End UI live · core/payments موصول.

---

### P-I — Frontend Quality Sweep (4-6 ساعات)

- [ ] **P-H-1 — react-hooks/rules-of-hooks zero violations.**
  بعد P-A-3، شغّل `npx eslint --ext .tsx components/`. أَصلح كل
  انتهاك. تَوقَّع 20-50 موقع. **لا `eslint-disable`** إلا في حالة
  مُوثَّقة.

- [ ] **P-H-2 — TS errors من 39 إلى ≤ 15.**
  - استبدل `any[]` بـtypes صحيحة (`journalsList`, `ShipmentForm
    formData`, إلخ).
  - `as any` → narrow types.
  - missing return types على exported functions.

- [ ] **P-H-3 — console.log purge.**
  ```
  grep -rEn "console\.(log|error|warn|info)" frontend_v2/components frontend_v2/services
  ```
  - في `services/`: احذف أو خُذها في `if (import.meta.env.DEV)`.
  - في `components/`: احذف. الأخطاء تَذهب لـstate.
  - استَهدف 0.

- [ ] **P-H-4 — Firestore tail isolation** (VIII-4).
  - انقل `firestoreService.ts` + `firestoreService_append.ts` إلى
    `frontend_v2/services/legacy/`.
  - في كل ملف يَستوردهما، استبدل import واتركه يَستهلك من SQL أو
    عَلِّق سَببَ الاحتفاظ.

- [ ] **P-H-5 — DenseTable migration completeness audit.**
  grep لـ`DataGrid` import في components/ — يَفترض task5 استبدلها.
  أَكمل إن وُجد.

- [ ] **P-H-6 — N9-T1 color purge completeness.**
  ```
  grep -rEn '(from|to|bg|text|border)-(emerald|blue|red|amber|orange|teal|cyan|sky|violet|purple|fuchsia|pink|rose|lime|yellow)-[0-9]' frontend_v2/components/{sales,procurement,accounting,inventory,items,suppliers}
  ```
  يَجب 0. أَصلح المتبقّي.

- [ ] **P-H-7 — Sidebar dead-state cleanup.**
  - راجع `AccountingJournalEntryPage` + غيرها بحثاً عن state
    declared+set لكن غير مُستخدَم في render (مثال:
    `pickerTargetLine`). احذف.

**Verifiable P-H:** ESLint 0 hooks violations · TS errors ≤ 15 ·
console.log = 0 · DataGrid في components = 0.

---

### P-J — Tests + CI Foundation (3-5 ساعات)

- [ ] **P-I-1 — pytest-django setup.**
  - تَأكَّد `pytest-django` في requirements.txt.
  - `pytest.ini` بـ`DJANGO_SETTINGS_MODULE = core.settings`.

- [ ] **P-I-2 — Coverage baseline.**
  - `coverage` لـrequirements.
  - `coverage run -m pytest && coverage report` — سَجِّل في
    `task6_baseline.md`. لا هدف، رؤية فقط.

- [ ] **P-I-3 — Tests الإلزامية الجديدة.** (الحدّ الأدنى 14):
  1. `test_exception_handler.py` (P-B-2): Django VE → 400.
  2. `test_tenant_isolation.py` (P-C-4).
  3. `test_clearance_lines.py` (P-D-1): create / sum debit/credit /
     VAT calc.
  4. `test_pi_payment_migration.py` (P-D-7): JSON → rows idempotent.
  5. `test_deal_item_extra_fields.py` (P-E-1): batch/expiry/warehouse
     persistence.
  6. `test_pi_per_line_vat.py` (P-E-6).
  7. `test_clearance_header_fields.py` (P-F-1).
  8. `test_pi_cheque_voucher.py` (P-G-1).
  9. `test_sales_return_stock.py` (P-G-2).
  10. `test_supplier_payment_fallback.py` (P-G-3).
  11. `test_cheque_lifecycle.py` (P-G-4).
  12. `test_voucher_atomicity.py` (P-G-5).
  13. `test_vat_statement_unique.py` (P-G-6).
  14. `test_account_overrides_active.py` (P-G-7).
  15. `test_multi_currency_fx.py` (P-G-8).
  16. `test_tenant_book_concurrent.py` (P-G-11).

- [ ] **P-I-4 — GitHub Actions CI** (اختياري).
  `.github/workflows/ci.yml` بـjobs: backend (pytest) + frontend
  (tsc + vite + eslint).

**Verifiable P-I:** 14+ test pass · CI workflow ready.

---

### P-K — Documentation, Hygiene, Final Review, Push (2 ساعة)

- [ ] **P-J-1 — gitignore + root cleanup** (VIII-9, VIII-10).
  `.gitignore` بـpatterns anchored:
  ```
  /frontend_v2/dist/
  /frontend_v2/dist.zip
  /frontend_v2/complete_dump.py
  /frontend_v2/consolidate*.{js,py}
  /frontend_v2/dump_code.js
  /frontend_v2/extractor.js
  /frontend_v2/final_*.{js,py}
  /frontend_v2/FULL_LITERAL_CODEBASE*.md
  /frontend_v2/Full_Project_*.md
  /frontend_v2/LITERAL_COMPLETE_CODEBASE*.md
  /notes_extract.txt
  /task6_baseline.md
  ```
  + `git rm --cached` لكل ملف.

- [ ] **P-J-2 — orphan apps decision** (VIII-11).
  أَنشِئ `frontend/README.md` يَقول «not part of ERP — separate Next.js
  app». نفس الشيء لـ`smart-product-search-platform/`. اسأل المالك قبل
  حذف.

- [ ] **P-J-3 — `firestore_id` field removal** (VIII-5).
  Migration `logistics/0039_drop_firestore_id.py`. تَأكَّد أن لا code
  يَستخدمه.

- [ ] **P-J-4 — RFC Document لـpayment unification** (VI-3).
  أنشِئ `docs/decisions/payment_model_unification.md`:
  - الانفصال الحالي (5 مصادر).
  - 3 خيارات unification: (a) ترحيل deal Firestore لـSQL، (b) إبقاء
    disjoint مع reconciliation report، (c) status quo.
  - **لا تَنفِّذ.** قرار مالك مستقبلي.

- [ ] **P-J-5 — Attachments mini-RFC** (الفئة V).
  `docs/decisions/attachments_model.md`:
  - الحالة الحالية: 6 حقول URL مُتفرّقة في 3 موديل.
  - الخيار المُقتَرَح: `Attachment` polymorphic model.
  - **لا تَنفِّذ هنا** — تَغيير كبير يَستحقّ phase منفصلة.

- [ ] **P-J-6 — PROJECT_MAP.md update.**
  أَضِف قسم `[TASK6 — DONE 2026-MM-DD]` بـpiet لكل Phase. حدِّث
  `[ORPHANS & PENDING]`.

- [ ] **P-J-7 — Final live verification.**
  Django:8000 + Vite:3000:
  - دورة استيراد كاملة: Deal (مع batch/expiry على line) → Shipment
    (مع journal direct) → Clearance (مع 8 lines structured) →
    LocalShipment → PurchaseInvoice (مع cheque voucher).
  - دورة بيع كاملة: Quotation → Invoice → Payment + Cheques → VAT
    statement (uniqueness check).
  - دورة محاسبة: قيد يدوي → ترحيل → عَكس → Trial Balance → Year-End
    Close.
  - دورة شيكات: Draft → Under_Collection → Collected (state machine).
  - Console clean في كل ما سَبَق.

- [ ] **P-J-8 — Opus Review Gate.**
  أوقَف. انتظر مراجعة Opus. لا push على main قبل الموافقة.

- [ ] **P-J-9 — Push.**
  بعد موافقة Opus + المالك:
  ```
  git checkout main
  git merge --ff-only claude/task6
  git push origin main
  ```

**Verifiable P-J:** repo نظيف · PROJECT_MAP محدَّث · 2 RFCs مكتوبة ·
push.

---

## Verification Matrix

| Phase | Verifiable Goals |
|------|------------------|
| P-A | baseline metrics في task6_baseline.md · ESLint مُفعَّل · 6 سيناريوهات PDF مؤكَّدة |
| P-B | console clean · A1-A6 لا تَتكرّر · workflow patch ⇒ 400 |
| P-C | 9 migrations · `default=1` = 0 في logistics · tenant-isolation test passes |
| P-D | Clearance lines table · PI payments table · `notesMeanShippingPayment` محذوف · 0 JSONField للـpayments/lines |
| P-E | DealItem + PIItem فيهما 13 حقل جديد · per-line VAT في journal · UI advanced toggle |
| P-F | Clearance/Shipment/Deal فيها كل حقول Aseel · status هو @property |
| **P-G** | **`ImportDocumentScreen` موحَّد + density treatment لـ40+ شاشة (Sales 8 + Accounting 13 + Procurement 6 + Inventory 4 + HR 7 + SQL 4) · كل form يَدخل viewport 1080p · Modal→SidePanel universal · density script CI guard · `docs/ui_density_rules.md` دستور** |
| P-H | 11 سَلسلة backend hardening · cheque attached لـPI · Year-End UI · core/payments موصول |
| P-I | ESLint 0 hooks · TS errors ≤ 15 · console.log = 0 |
| P-J | 14+ tests pass · CI workflow (optional) |
| P-K | repo نظيف · PROJECT_MAP محدَّث · 2 RFCs · push |

---

## Execution Rules (صارمة جداً)

1. **اقرأ هذا الملف كاملاً قبل البدء — يَتضمَّن قسم «الاوديت الحقيقي»
   9 فئات (0..VIII). الفئة 0 هي الأهمّ ولا يَجوز اختصارها.**
2. اقرأ `PROJECT_MAP.md` (سجلّ الذاكرة) + الـreferences في
   `docs/aseel_reference/full/` (خاصةً `الإرساليات.txt` و `الفواتير.txt`
   و `المحاسبة.txt`).
3. **commit-per-task** بـرسالة `task6 P<X>-T<Y>: <description>`.
4. اعمل في `claude/task6` worktree، لا في main.
5. **بعد كل Phase**، أوقَف وانتظر مراجعة Opus.
6. **لا تَخترع APIs/models/services خارج ما نَصّ عليه التاسك.**
7. **0 ميزات جديدة. 0 dependencies جديدة.**
8. عند الغموض: `[QUESTION] ...` في commit body. لا قرار صامت.
9. قبل tests جديدة: شغّل tests موجودة وتَأكَّد passing.
10. **متصفّح حيّ بعد كل Phase.** Django:8000 + Vite:3000.
11. migrations sequential (0026_ → 0039_ بحسب الـapp). لا تَعارض.
12. **لا تَلمس `services/*Api.ts`** إلا بإضافة helpers جديدة.
13. **`tsc --noEmit` لا يَجب أن يَرتفع** بين أي commit وآخر.
14. **اقرأ M1 `SalesInvoiceEditor.tsx` قبل أي rebuild لـform** — قالب
    ذهبي.
15. لكل migration: backfill قبل الحذف. لا data loss.

---

## Aseel ↔ KTRA Mapping (محدَّث post-deep-audit)

| الموضوع | الحالة الحالية | الإصلاح في task6 |
|---------|----------------|-------------------|
| بنود التخليص | `cost_lines: JSONField` (label + amount) | جدول `LogisticsClearanceLine` بـ8 أعمدة (P-D-1) |
| دفعات الشراء | `local_payments_json: JSONField` | جدول `PurchaseInvoicePayment` (P-D-6) |
| نوع دفعة تخليص | `notes.startsWith('[شحن]')` regex | `payment_purpose` choice (P-D-5) |
| Deal item batch/expiry/warehouse | mashed في `notes (255)` | 13 عمود صريح (P-E-1) |
| PI item نفسه | mashed في `notes (500)` | 13 عمود صريح (P-E-2) |
| Clearance header | 8 حقول Aseel مفقودة | 11 حقل جديد (P-F-1) |
| Shipment header | 4 حقول Aseel مفقودة | 5 حقول جديدة (P-F-2) |
| Deal header | 4 حقول Aseel مفقودة | 4 حقول جديدة (P-F-3) |
| 4 status fields متداخلة | DB columns كلّها | source-of-truth واحد + computed (P-F-4) |
| Multi-tenancy في logistics | `default=1` × 9 موديل | إزالة كاملة + loud fail (P-C) |
| **شاشات منفصلة (Shipment/Clearance/Local)** | **3 routes × scroll عمودي** | **`ImportDocumentScreen` موحَّد بـtabs (P-G-1..G-3)** |
| **كَثافة الشاشة المنخفضة** | **8 sections عمودية + scroll مستمر** | **header 24 حقل + tabs + dock في viewport 1080p (P-G-1)** |
| **Modals تَحجُب الشاشة** | `SupplierViewModal` + dealSelector + ... كلّها overlay | `AseelSidePanel` لا يَحجُب (P-G-6) |
| Cheque على PI | غير مدعوم | mirror SalesInvoice voucher (P-H-1) |
| Sales/Purchase Return stock | UI فقط، لا StockMovement | RETURN_IN/OUT (P-H-2) |
| Cheque state machine | يَسمح Bounced→Collected | enforce (P-H-4) |
| Cheque idempotency | يَتيمة على failure | atomic + savepoint (P-H-5) |
| VAT per-line | header-level فقط | per-line في journal (P-E-6) |
| FX multi-currency | per-payment | per-allocation (P-H-8) |
| `core/payments.py` | foundation only | wired (P-H-9) |
| Year-End Close | endpoint بدون UI | UI page (P-H-10) |
| Hook rules | منتهَكة (PDF) | enforce + fix (P-A-3 + P-I-1) |
| DRF Django VE | 500 | 400 موحَّد (P-B-2) |
| Test coverage | ~0 | 14+ tests (P-J-3) |
| Repo hygiene | ~12 orphan files tracked | gitignore + remove (P-K-1) |
| Disjoint payments (5 sources) | unresolved | RFC doc (P-K-4) |
| Attachments (6 URL fields) | unresolved | RFC doc (P-K-5) |

---

## Status

> **Status:** `[ ]` P-A .. P-K pending owner approval · 2026-05-23
>
> **Total:** 11 Phases · ~130 task · ~22 migration · 14+ test · شاشة
> موحَّدة جديدة + density treatment لـ40+ شاشة موجودة · **0 ميزة جديدة.
> 0 dependency جديد.**
>
> **Estimated execution:** 80-130 ساعة موديل أرخص + ~12 ساعة مراجعة
> Opus = ~95-145 ساعة إجمالاً.
>
> **بعد الموافقة:** ابدأ بـP-A فقط. توقَّف بعد كل Phase. **لا تَقفز
> لـP-G قبل P-A..P-F** — الـheader band يَعتمد على الحقول الجديدة من
> P-F، والـtabs يَعتمدون على الـClearanceLine جدول من P-D.
>
> **P-G داخلياً مُرتَّب:** G-1..G-6 (import flow) → G-7..G-11 (بقية
> forms) → G-12 (modals) → G-13 (script + CI) → G-14 (docs). كل
> sub-phase له commit مستقل.
