# task2.md — KTRA ERP: خطة التوحيد والارتقاء الاحترافي

> خطة **مركّزة** (ليست إعادة تدقيق). `task.md` (المراحل 0–4: C1/M2/m3/I4) خط أساس **مُجمَّد** — لا يُعاد فتح ما أُصلح فيه.
> النطاق محصور بمخاوف المالك المعلَنة + أخطاء جديدة مكتشَفة **داخل هذه المناطق فقط**:
> توحيد الدفع · ازدواج النقل المحلي · تسمية الصفقات/الشحنات · تحديث المبيعات + عرض السعر · ارتقاء UI/منطق بمستوى احترافي.
> القاعدة قبل أي مهمة: اقرأ الملف الفعلي تحت `C:\Users\asus\Desktop\ktra\` (ليس worktree). تحقّق أن الخطأ ما زال قائماً قبل الإصلاح. شغّل `python manage.py check` بعد كل مهمة backend وبعد كل migration شغّل `makemigrations --check`.
> Status: `[ ]` pending · `[~]` in-progress · `[x]` done. Audited 2026-05-18.
> مرجع التصميم/المنطق: أفضل ممارسات ERP الاحترافية (نمط Daftra/Odoo: عرض سعر→فاتورة، أذون مخزن، دورة مستندات مترابطة). المالك قد يزوّد لاحقاً مادة "برنامج الأصيل" لمطابقة ميزة بعينها.

---

## المرحلة 1 — أخطاء كارثية (مالية خاطئة / فساد بيانات) داخل النطاق

### نقل محلي / Landed cost

- [x] **T1-01** **تم + مراجعة (Opus 2026-05-18):** حارس `clearance_local_transport_superseded_by_localshipment` في chokepoint واحد (`landed_cost.py:232`) سليم. صُحِّحت 3 اختبارات مُضلِّلة (كانت تختبر `exists→False` بأسماء سيناريوهات مختلفة دون فحص شروط الفلتر). 12/12 ناجحة. **(الوصف الأصلي للمهمة أدناه.)**

- [ ] ~~**T1-01**~~ **ازدواج تكلفة النقل المحلي → تضخيم تقييم المخزون.**
  `logistics/models.py:496` `LocalShipment` فيه `capitalize_to_inventory=True` (`:613`) فتُرسمل قيمته على Landed Cost. **وفي الوقت نفسه** `logistics/landed_cost.py:232` `sum_local_shipping_from_clearance_cost_lines_ils` يجمع بنود النقل المحلي من `LogisticsClearance.cost_lines` (JSON، `models.py:408`) ويضيفها لنفس الـ landed pool. إذا أدخل المستخدم النقل المحلي في **كلا** المسارين (سطر تكلفة في التخليص + سجل `LocalShipment` مربوط بنفس `clearance`) → نفس التكلفة تُرسمل مرّتين على المخزون → **مخزون مُقيَّم بأعلى + COGS مستقبلي خاطئ + ربح وهمي**.
  **الإصلاح:** مصدر حقيقة واحد. في `logistics/landed_cost.py` (دالة بناء الـ pool — تتبّع `clearance_local_lines_pool_ils` في `compute_deal_invoice_lines:469` و`recalculate_landed_for_shipment:1027`): استبعد بنود النقل المحلي من `clearance.cost_lines` متى وُجد `LocalShipment` مربوط بنفس `clearance_id` و`capitalize_to_inventory=True` و`is_posted=True` (أو العكس — اعتمد `LocalShipment` كمصدر وحيد عند وجوده). أضف helper `clearance_local_transport_superseded_by_localshipment(clearance) -> bool`.
  **التحقق:** صفقة بشحنة+تخليص فيه سطر نقل محلي 1000 + سجل `LocalShipment` 1000 مربوط ومرحّل → `sum(landed_line_total_ils)` يزيد 1000 **مرّة واحدة** لا 2000. أضف اختبار في `logistics/tests/test_landed_cost.py`.

- [x] **T1-02** **تم + تصحيح مراجعة (Opus 2026-05-18):** المسار يمرّ الآن بـ `post_journal`. **خطأ forex صحّحته:** النموذج الخارجي ثبّت `exchange_rate=Decimal("1")` رغم أن دفعة التخليص تدعم عملة أجنبية → كان سيُخزّن أساساً = المبلغ الاسمي ويُفسد ميزان المراجعة (صنف خطأ C1-05/m3-09). الآن يحلّ السعر الفعلي عبر `get_exchange_rate(...)`، fallback=1 فقط بالعملة الأساسية، وسعر مفقود يُرجع 400 نظيف. (ملاحظة: idempotency ضد الإرسال المزدوج محدود — `reference_id=pay.id` فريد لكل طلب؛ post_journal يمنع ترحيل نفس الدفعة مرّتين فقط، لا إنشاء دفعتين بضغط مزدوج — قيد موثّق، حلّه الكامل خارج نطاق T1-02). **(الوصف الأصلي أدناه.)**

- [ ] ~~**T1-02**~~ **مسار دفع التخليص لا يمرّ بـ `post_journal()` المركزية (تحقّق ثم أصلح).**
  `logistics/views.py:1014` `LogisticsClearanceViewSet` — أكشن دفع التخليص (`pay_from_cashbox` أو ما يماثله؛ ابحث عن `LogisticsClearancePayment.objects.create` داخل الكلاس). تحقّق: هل يُنشئ `JournalHeader/JournalLine` مباشرةً بدل استدعاء `accounting.services.post_journal()`؟ إن كان كذلك فهو **خارج** ضمانات I4-01 (فحص فترة مالية ذرّي + idempotency بـ `select_for_update` + توازن دقيق) → خطر ترحيل في فترة مغلقة أو دفعة مكررة عند ضغط مزدوج.
  **الإصلاح:** حوّل المسار لاستدعاء `post_journal(reference_type='CLEARANCE_PAYMENT', reference_id=<clearance_payment.id>, ...)` مثل بقية المسارات (راجع نمط `sales/services.py post_customer_payment`).
  **التحقق:** ترحيل دفعة تخليص في فترة مغلقة يُرفض 400؛ استدعاء الأكشن مرّتين بنفس الدفعة لا يُنشئ قيدين (idempotent).

- [x] **T1-03** **تم + تصحيح مراجعة (Opus 2026-05-18):** أُضيف `unpost_payment` للتخليص بنمط القيد العكسي (سليم). **صحّحت:** (1) كان يضبط `payment.journal=None` فيُتلف رابط التدقيق — أُبقي الرابط (حارس `is_posted=False` يكفي لمنع الإلغاء المزدوج). (2) `except Exception → 400 str(e)` يسرّب التفاصيل ويُخطئ تصنيف 500 — الآن Validation/Integrity→400، غير متوقّع→500 + `logger.exception` (يطابق m3-04). تحقّقت أن مسارات deal/PI/local-shipment تستخدم نمط القيد العكسي مسبقاً. **(الوصف الأصلي أدناه.)**

- [ ] ~~**T1-03**~~ **عدم اتساق إلغاء الترحيل (unpost) عبر مسارات الدفع الأربعة.**
  `task.md` C1-14/I4-02 ثبّتا نمط القيد العكسي لبعض المسارات. تحقّق أن **كل** مسارات إلغاء الترحيل (deal payment, agent/shipment payment, clearance payment, local shipment, customer payment) تستخدم **نفس** نمط القيد العكسي (`reference_type=*_UNPOST`) ولا أحدها يحذف `JournalLine` أو يقلب `is_posted` عبر `.save()` (يُحجَب بحارس I4-02). جرّد المواضع: `logistics/views.py` (clearance unpost, local-shipment unpost ~`:1810-2025`)، `sales/services.py` (customer payment unpost).
  **الإصلاح:** أي مسار يحذف/يقلب → حوّله لقيد عكسي عبر `post_journal(reference_type='..._UNPOST')` أو `.filter().update()` المعفى من الحارس (نمط I4-02).
  **التحقق:** إلغاء ترحيل كل نوع دفعة يُبقي القيد الأصلي ويُنشئ قيداً عكسياً متوازناً؛ لا حذف سجل تدقيق.

---

## المرحلة 2 — أخطاء متوسطة داخل النطاق

- [x] **T2-01 — تم + تصحيح مراجعة (Opus 2026-05-18):** النموذج الخارجي حسّن regex الـboilerplate لكنه جعل `serializers._english_payment_boilerplate` نسخة طبق الأصل من `landed_cost._is_english_payment_or_legal_boilerplate` (منطق هشّ مكرّر يجب أن يبقى متزامناً يدوياً؛ ونسخة serializers استخدمت regex عربي أضيق `[U+0600-U+06FF]` فتُخطئ presentation-forms). **التصحيح:** وحدة مشتركة `logistics/text_utils.py` (مصدر حقيقة واحد، regex أوسع)؛ serializers.py و landed_cost.py يستوردان منها — تحقّق: نفس كائن الدالة (`is`). check نظيف، 12/12. **الوصف الأصلي للمهمة أدناه (مرجع).**

- [ ] ~~**T2-01**~~ **منطق عرض اسم الصفقة هشّ وإجرائي.**
  `logistics/serializers.py:27-46` (`_deal_title_for_list_preview`) يبني العنوان من سلسلة أولويات (description→notes→original_offer→ref_number). لا حقل اسم مخصّص → الصفحة الرئيسية تُظهر `description` (نص حرّ/إنجليزي أحياناً) بدل اسم مختصر. (الحل الجذري حقل `short_name` = T4-03؛ هنا فقط: ثبّت السلوك المؤقت — إن كان `description` إنجليزياً boilerplate أظهِر `ref_number` بوضوح بدل نص مبهم).
  **التحقق:** صفقة وصفها "payment terms…" تُظهر `ref_number` لا النص الإنجليزي في قائمة الصفقات.

- [x] **T2-02 — تم + إكمال (Opus 2026-05-18):** النموذج الخارجي استخرج `buildShipmentOptionLabel` إلى `frontend_v2/utils/shipmentLabel.ts` وربطه بـ`CustomsClearanceManagement.tsx` فقط — لكن القائمة الرئيسية `SqlShipmentsPage.tsx:98` بقيت تعرض `shipment_number` خاماً (شكوى المالك نفسها). **الإكمال:** هاجرتُ `SqlShipmentsPage.tsx` (بطاقة القائمة + فلتر البحث + النوع) للـutil المشترك. typecheck: صفر خطأ في الملفات الممسوسة. **الوصف الأصلي أدناه (مرجع).**

- [ ] ~~**T2-02**~~ **عرض الشحنة برقم خام بدل اسم مختصر.**
  `frontend_v2` قائمة الشحنات (تتبّع `shipment_number` في مكوّنات `components/logistics/` و`components/procurement/clearance/CustomsClearanceManagement.tsx:43-52` `buildShipmentOptionLabel`). الشحنات تُعرض بـ `SH-XXXX`. (الجذر = حقل `short_name` T4-03؛ هنا: وحّد دالة بناء التسمية في util مشترك واحد بدل تكرارها في كل مكوّن).
  **التحقق:** كل قوائم الشحنات تستخدم نفس util التسمية؛ تغيير منطق العرض في مكان واحد ينعكس كلياً.

- [~] **T2-03 — جزئي + تصحيح صدق (Opus 2026-05-18):** النموذج الخارجي أنشأ `usePaymentForm.ts` لكنه ملف ميت (لا مكوّن يستورده — التوحيد لم يحدث)، وأعلن حقول خطأ لا يتحقق منها ويسمح بتاريخ فارغ بينما الخادم يرفضه. **التصحيح:** أُعيدت كتابة الـhook صحيحاً وغير مُضلِّل (`validatePaymentInput` نقية: مبلغ>0 + تاريخ مطلوب مطابق للخادم + `extra` للأخطاء الخاصة). **متبقٍّ صراحةً:** ربطه بواجهات الدفع الأربع = عمل UI لا يُتحقَّق منه دون تشغيل الواجهة — لم يُدّعَ اكتماله. **الوصف الأصلي أدناه (مرجع).**

- [ ] ~~**T2-03**~~ **تباعد واجهات الدفع (deal/shipment/clearance/local) — UX غير موحّد.**
  أربع واجهات دفع منفصلة: `frontend_v2/components/forms/deal-parts/PaymentRegistration.tsx` (صفقة)، قسم دفعات الشحنة، `components/procurement/clearance/CustomsClearanceManagement.tsx:70-112` (تخليص)، `LocalShippingPage.tsx` (نقل). حقول/تحقّق/عرض مختلف لكل واحدة. (التوحيد الفعلي backend = T4-02؛ هنا فقط: وحّد عرض أخطاء الدفع + تحقّق العميل المشترك في hook/util واحد `usePaymentForm`).
  **التحقق:** نفس رسائل الخطأ ونفس قواعد التحقّق (مبلغ>0، تاريخ، عملة) في الواجهات الأربع.

- [~] **T2-04 — جزئي (Opus 2026-05-18):** النموذج الخارجي أنجز الباك-إند فقط: `LogisticsClearanceSerializer.local_shipments` + `prefetch_related("local_shipments")` — سليم. **متبقٍّ صراحةً:** واجهة `CustomsClearanceManagement.tsx` لا تستهلك `clearance.local_shipments` بعد، ومسار الإدخال المكرّر للنقل المحلي ما زال قائماً → معيار التحقق غير محقّق. الإكمال = T4-04 (يحتاج migration بيانات). لم يُدّعَ اكتمال الواجهة. **الوصف الأصلي أدناه (مرجع).**

- [ ] ~~**T2-04**~~ **النقل المحلي بواجهتين منفصلتين.**
  `LocalShipment` يظهر: (أ) صفحة مستقلة `frontend_v2/.../LocalShippingPage.tsx`؛ (ب) مضمَّن في `CustomsClearanceManagement.tsx` (سطور تكلفة ضمن التخليص). المستخدم لا يعرف أيّهما يُنشئ سجلاً رسمياً. (التوحيد الكامل = T4-04؛ هنا: في واجهة التخليص اجعل قسم النقل المحلي **يقرأ ويربط** سجلات `LocalShipment` لا يكرّر إدخال تكلفة منفصلة).
  **التحقق:** إدخال نقل محلي من واجهة التخليص يُنشئ/يربط `LocalShipment` واحداً ظاهراً أيضاً في الصفحة المستقلة (سجل واحد، عرضان).

---

## المرحلة 3 — أخطاء صغيرة / robustness داخل النطاق

- [ ] **T3-01** `core/payments.py` — `validate_payment()` يرفض `partner_id=None` دائماً، لكن دفعات التخليص قد تكون بلا `customs_broker` ودفعات الوكيل بلا `shipping_agent` (الحقول `null=True`). راجع: هل المنع سلوك تجاري مقصود أم صرامة زائدة تكسر حالات صحيحة؟ وثّق القرار في docstring.
  **التحقق:** قرار موثّق + اختبار يثبّت السلوك المختار.
- [ ] **T3-02** توحيد رسائل نجاح/فشل ترحيل الدفع: حالياً كل أكشن يرجع شكل استجابة مختلف. وحّد عبر serializer/هيكل استجابة واحد `{ok, journal_id, error}`.
  **التحقق:** الأكشنات الأربعة ترجع نفس مفاتيح JSON.
- [ ] **T3-03** `LocalShipment.exchange_rate` (`models.py:587`) و`currency` default=1 — تأكد أن الترحيل يشتقّ الأساس من سعر الصرف لا default 1 (نفس درس C1-05). تحقّق دالة ترحيل LocalShipment.
  **التحقق:** local shipment بعملة أجنبية يُخزَّن أساسه = amount × rate لا = amount.

---

## المرحلة 4 — تحسينات جوهرية + تغييرات schema (مُصرّح بها)

> المراحل 1–3 إصلاح أخطاء بأقل تغيير schema. المرحلة 4 تُصرّح بنماذج/migrations جديدة. كل بند هنا يتطلب: model + migration + serializer + viewset + frontend_v2 + `makemigrations` + `check`.

### كيان عرض السعر (Quotation) — نمط احترافي

- [ ] **T4-01** **كيان `SalesQuotation` + تحويله لفاتورة.**
  لا يوجد كيان عرض سعر (الموجود: `LogisticsDeal.original_offer_number` نص حرّ فقط). أنشئ في `sales/`:
  - نموذج `SalesQuotation` + `SalesQuotationLine` (يحاكي `SalesInvoice`/`SalesInvoiceLine` `sales/models.py:170-312`): `customer, currency, quotation_date, valid_until, status, lines, subtotal, tax, grand_total, notes`.
  - آلة حالة: `draft → sent → accepted → converted → expired/rejected` (نمط I4-07: الفرض في `save()` لا `clean()` فقط).
  - دالة `convert_quotation_to_invoice(q, user)` في `sales/services.py` — تنشئ `SalesInvoice` من العرض دون إعادة إدخال، تضبط `quotation.status='converted'` و FK `invoice` (idempotent: عرض محوَّل لا يُحوَّل ثانية).
  - serializer + `SalesQuotationViewSet` (يمتد `BaseTenantViewSet` من `core/mixins.py`) + مسار `POST /api/sales/quotations/{id}/convert/`.
  - frontend_v2: شاشة قائمة + محرّر عرض سعر (أعد استخدام مكوّنات `SalesInvoiceEditor.tsx`) + زر "تحويل لفاتورة".
  - migration `sales/000X_salesquotation`.
  **التحقق:** إنشاء عرض → قبول → تحويل → فاتورة مطابقة البنود/الإجماليات؛ تحويل ثانٍ مرفوض؛ `check` نظيف؛ لا انجراف.

### توحيد الدفع الفعلي (wiring)

- [ ] **T4-02** **توحيد مسارات الدفع عبر `core/payments.py` + ترحيل مركزي.**
  حالياً `core/payments.py` طبقة أساس غير موصولة (I4-09). صِل المسارات الأربعة فعلياً:
  - أضف `post_payment(ctx: PaymentContext, *, resolve_accounts_fn, user)` في `core/payments.py` تبني `lines_data` وتستدعي `accounting.services.post_journal()` (مصدر ترحيل واحد).
  - أعِد توجيه: deal payment (`logistics/views.py post_payment`)، agent payment (`post_agent_payment`)، clearance payment (T1-02)، customer payment (`sales/services.py:653-810`) لتمرّ عبر `post_payment(ctx, ...)`. حافظ على منطق forex المثبت في customer payment (I4-03) — مرّره عبر `resolve_accounts_fn`.
  - لا تغيير في النماذج (توحيد سلوكي فقط)؛ إن لزم حقل ربط موحّد وثّقه.
  **التحقق:** الأنواع الأربعة تُنشئ قيداً عبر `post_journal` بنفس بنية المراجع؛ idempotency + فحص الفترة يعملان للأربعة؛ اختبارات end-to-end لكل نوع.

### حقول الاسم المختصر — جذر مشكلة العرض

- [ ] **T4-03** **حقل `short_name` للصفقة والشحنة + تغيير تسمية حقل الوصف.**
  - `LogisticsDeal`: أضف `short_name = CharField(max_length=120, blank=True)`؛ غيّر تسمية واجهة "وصف الصفقة" → "اسم الصفقة" (الحقل `description` يبقى DB-name، يتغيّر label فقط في serializer/frontend). عند الفراغ: fallback مُرتّب موثّق (T2-01).
  - `LogisticsShipment`: استخدم/فعّل `shipment_name` الموجود (`models.py:268`) كاسم مختصر رئيسي؛ اعرضه بدل `shipment_number` في القوائم.
  - serializers + frontend_v2 (قائمة الصفقات الرئيسية + قوائم الشحنات) تعرض `short_name || ref_number` و`shipment_name || shipment_number`.
  - migration `logistics/000X_add_short_name`.
  **التحقق:** الصفحة الرئيسية تعرض اسم الصفقة المختصر؛ القوائم تعرض اسم الشحنة؛ `check` + لا انجراف.

### توحيد النقل المحلي (UI + بيانات)

- [ ] **T4-04** **مصدر حقيقة واحد للنقل المحلي.**
  بناءً على T1-01/T2-04: اجعل `LocalShipment` المصدر الرسمي الوحيد. واجهة التخليص (`CustomsClearanceManagement.tsx`) تعرض/تنشئ سجلات `LocalShipment` المرتبطة (`clearance` FK، `models.py:529`) بدل سطور JSON في `cost_lines`. رحّل بنود النقل المحلي القديمة من `clearance.cost_lines` إلى سجلات `LocalShipment` (migration بيانات + سكربت). أزل مسار إدخال النقل المحلي المكرّر من واجهة التخليص (قراءة/ربط فقط).
  **التحقق:** لا مكان يُدخل النقل المحلي مرّتين؛ landed cost = T1-01 (مرّة واحدة)؛ بيانات قديمة مُرحّلة بلا فقد.

### تحديث نظام المبيعات + حركة الإخراج الاحترافية

- [ ] **T4-05** **إذن صرف مخزني صريح (Stock Issue Voucher) للمبيعات.**
  حالياً خصم المخزون ضمني داخل `post_sales_invoice`/`deliver_delivery_order` (`sales/services.py`). الاحترافي: مستند صريح. أضف نموذج `StockIssue` (أو فعّل `DeliveryOrder` `sales/models.py:362-395` كإذن صرف رسمي): يحمل البنود/الكميات/المستودع، يُنشئ `StockMovement(reference_type='STOCK_ISSUE')` + قيد COGS عبر `post_journal`، idempotent (نمط C1-17). وضّح في الواجهة دورة: عرض سعر → فاتورة → إذن صرف → تسليم.
  **التحقق:** ترحيل فاتورة + إصدار إذن صرف يخصم المخزون مرّة واحدة بقيد COGS واحد؛ مزدوج مرفوض؛ الدورة ظاهرة في الواجهة.

### اقتراحات UI/تصميم (احترافي — تُنفَّذ كتاسكات frontend_v2)

- [ ] **T4-06** **دورة مستندات مترابطة ظاهرة.** شريط حالة/تتبّع موحّد (Quotation→Invoice→StockIssue→Delivery؛ Deal→Shipment→Clearance→LocalShipment→PurchaseInvoice) في رأس كل شاشة، روابط تنقّل بين المستندات المرتبطة.
- [ ] **T4-07** **لوحة دفع موحّدة.** مكوّن `<PaymentPanel sourceType=… />` واحد يستبدل الواجهات الأربع المتباعدة (يستهلك T4-02)؛ نفس الحقول/التحقّق/العرض.
- [ ] **T4-08** **الصفحة الرئيسية للصفقات/الشحنات.** أعمدة: الاسم المختصر (T4-03) + المرجع + الحالة + الإجمالي + شريط التقدّم؛ إزالة عرض الـ `description` الخام.
- [ ] **T4-09** **شاشات المبيعات الناقصة.** عرض سعر (T4-01)، إذن صرف (T4-05)، تحويلات بين المستندات، طباعة/PDF موحّدة القالب.

---

## بروتوكولات إلزامية (مرجع للمنفّذ)

- **الوعي الزمني:** 2026-05. Stack مثبّت: Django 6.0.1 + DRF، React 18/TS (frontend_v2). تجنّب أي API مهجور؛ ثبّت الإصدارات في `[TECH_STACK]`.
- **No Feature Creep:** نفّذ بنود هذا الملف فقط. لا نماذج/شاشات خارج النطاق.
- **Surgical Architecture:** Shared/Core (`core/payments.py`, `core/mixins.py`) للمنطق المتكرر فعلياً فقط؛ لا micro-files؛ تقسيم Domain-Driven (accounting/sales/logistics).
- **Safe Logging:** استخدم `logging` القياسي بمستوى INFO/ERROR، غير حظري، بلا I/O متزامن في مسار الطلب؛ لا تُسجّل أسراراً/PII.
- **التحقّق قبل الإصلاح:** كل مهمة تبدأ بإثبات أن المشكلة قائمة في الملف الفعلي.

---

## ترتيب التنفيذ الموصى (Milestones — أهداف قابلة للتحقق)

| # | Milestone | بنود | هدف التحقق (Verifiable Goal) |
|---|-----------|------|------------------------------|
| M1 | إيقاف نزيف مالي | T1-01, T1-02, T1-03 | لا ازدواج landed cost؛ كل ترحيل دفع عبر `post_journal` (فترة+idempotency)؛ unpost = قيد عكسي للأنواع كلها. اختبارات خضراء. |
| M2 | اتساق متوسط | T2-01..T2-04 | تسمية موحّدة عبر util واحد؛ تحقّق/أخطاء دفع موحّدة؛ النقل المحلي يربط لا يكرّر. |
| M3 | تنظيف صغير | T3-01..T3-03 | استجابات دفع موحّدة الشكل؛ أساس عملة LocalShipment صحيح؛ قرارات موثّقة. |
| M4 | ارتقاء جوهري | T4-01..T4-09 | عرض سعر→فاتورة يعمل؛ الدفع موحّد فعلياً عبر `core/payments.py`؛ `short_name` ظاهر؛ نقل محلي مصدر واحد؛ إذن صرف صريح؛ شاشات احترافية. كل migration نظيف، لا انجراف، اختبارات end-to-end. |

> **انتظار الموافقة:** لا تنفيذ قبل موافقة المالك على هذه الخطة. عند الموافقة يُنفَّذ Milestone تلو الآخر مع تحديث `PROJECT_MAP.md [ORPHANS & PENDING]` بعد كل M.
