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

- [x] **T2-03 — تم بالكامل (Opus 2026-05-18):** أُعيدت كتابة `usePaymentForm.ts` صحيحاً (`validatePaymentInput` نقية: مبلغ>0 + تاريخ مطلوب/صالح مطابق للخادم + `hasPaymentErrors` + `extra`). **ثم رُبط فعلياً في الـ5 مسارات دفع** كحارس أول موحّد الرسائل مع إبقاء الفحوص الخاصة بكل واجهة (صندوق/مخلّص/سقف): (1) صفقة `PaymentRegistration.handleSaveSwift` (2) وكيل `ShipmentForm` case "swift" (3) تخليص `CustomsClearanceManagement.handlePostPayment` (4) شحن محلي بالتخليص `handleShipPostPayment` (5) نقل محلي `LocalShippingPage.submit`. typecheck: صفر خطأ في الملفات الممسوسة. **الوصف الأصلي أدناه (مرجع).**

- [ ] ~~**T2-03**~~ **تباعد واجهات الدفع (deal/shipment/clearance/local) — UX غير موحّد.**
  أربع واجهات دفع منفصلة: `frontend_v2/components/forms/deal-parts/PaymentRegistration.tsx` (صفقة)، قسم دفعات الشحنة، `components/procurement/clearance/CustomsClearanceManagement.tsx:70-112` (تخليص)، `LocalShippingPage.tsx` (نقل). حقول/تحقّق/عرض مختلف لكل واحدة. (التوحيد الفعلي backend = T4-02؛ هنا فقط: وحّد عرض أخطاء الدفع + تحقّق العميل المشترك في hook/util واحد `usePaymentForm`).
  **التحقق:** نفس رسائل الخطأ ونفس قواعد التحقّق (مبلغ>0، تاريخ، عملة) في الواجهات الأربع.

- [x] **T2-04 — تم (Opus 2026-05-18):** الباك-إند (النموذج الخارجي): `LogisticsClearanceSerializer.local_shipments` + `prefetch_related` — سليم. **الواجهة (أُكملت):** أُضيف `local_shipments` لنوع `ClearanceRow` وتستهلكه `CustomsClearanceManagement.tsx` الآن: لوحة قراءة-فقط في قسم النقل المحلي تعرض سجلات `LocalShipment` الرسمية المرتبطة (رقم/مبلغ/حالة/مُرحّل) وتوجّه المستخدم لإدارتها من صفحة الشحن المحلي + تنبيه ازدواج T1-01. **حدّ موثّق:** الإزالة الكاملة لمسار إدخال سطر التكلفة المكرّر + ترحيل البيانات القديمة = T4-04 (يحتاج data migration) — خارج نطاق T2-04 (قراءة/ربط فقط). **الوصف الأصلي أدناه (مرجع).**

- [ ] ~~**T2-04**~~ **النقل المحلي بواجهتين منفصلتين.**
  `LocalShipment` يظهر: (أ) صفحة مستقلة `frontend_v2/.../LocalShippingPage.tsx`؛ (ب) مضمَّن في `CustomsClearanceManagement.tsx` (سطور تكلفة ضمن التخليص). المستخدم لا يعرف أيّهما يُنشئ سجلاً رسمياً. (التوحيد الكامل = T4-04؛ هنا: في واجهة التخليص اجعل قسم النقل المحلي **يقرأ ويربط** سجلات `LocalShipment` لا يكرّر إدخال تكلفة منفصلة).
  **التحقق:** إدخال نقل محلي من واجهة التخليص يُنشئ/يربط `LocalShipment` واحداً ظاهراً أيضاً في الصفحة المستقلة (سجل واحد، عرضان).

---

## مراجعة المرحلة 2 بعد التحقق البصري الحيّ (Opus 2026-05-18) — تاسكات تصحيح للموديل الأرخص

> شُغّل الباك-إند (Django:8000) + الواجهة (Vite:3000)، دخول كمدير، تصفّح فعلي: deals/shipments/clearance/local-shipping. الكونسول **نظيف بلا أخطاء**. بناء Vite كامل صفر خطأ. منطق `validatePaymentInput` مُختبَر حتمياً 8/8. الثغرات أدناه **مؤكَّدة بالكود + المتصفح**. كل تاسك مستقل: file:line + المشكلة + الإصلاح + التحقق.

- [x] **T2-FIX-01 — تم ومُتحقَّق حيّاً (Opus 2026-05-18):** أُضيف `buildShipmentOptionLabelCamel` (+ نوع `ShipmentLabelCamel`) في `shipmentLabel.ts` (محوّل camelCase→نفس منطق الـutil المشترك)؛ `ShipmentList.tsx:231-232` يستدعيه الآن. **تحقّق متصفّح حيّ:** `/shipments` صار يعرض «شحنة اختبار — S-0016» و«اختبار شحنة — S-0015 · مرجع: 555 · فادي» (صيغة موحّدة مطابقة للتخليص). صفر خطأ TS، كونسول نظيف. **الوصف الأصلي أدناه (مرجع).**

- [ ] ~~**T2-FIX-01**~~ **(حرج — شكوى المالك الأساسية لم تُحلّ).** الصفحة الرئيسية للشحنات الفعلية هي مسار `/shipments` → `App.tsx:282` → `appView="shipments-management"` → `components/procurement/shipments/ShipmentManagement.tsx` → `ShipmentList.tsx`. السطر `ShipmentList.tsx:231-232` يبني الاسم بمنطق **خاص مغاير**: `shipment.shipmentName || shipment.agentShipmentNumber || shipment.shipmentNumber` ولا يستخدم `@/utils/shipmentLabel`. الـutil المشترك (T2-02) وصل فقط لـ`SqlShipmentsPage.tsx` (مسار ثانوي `sql-shipments`، غير الصفحة التي يراها المالك) و`CustomsClearanceManagement.tsx`. **ملاحظة بنيوية:** `ShipmentList` يستخدم camelCase (`shipmentName/shipmentNumber/agentShipmentNumber`) من نوع `Shipment` (Firestore) بينما `ShipmentLabelInput` يستخدم snake_case — يلزم محوّل حقول.
  **الإصلاح:** في `shipmentLabel.ts` أضِف دالة `buildShipmentLabelFromShipment(s: {shipmentName?,shipmentNumber?,agentShipmentNumber?,israeliSideName?,id})` (تطبيع camelCase→نفس منطق `buildShipmentOptionLabel`)، أو محوّل صغير `toShipmentLabelInput()`. ثم استبدل `ShipmentList.tsx:231-232` (و`:241` إن لزم) لاستدعائه. ابحث عن أي مكوّن آخر يعرض اسم شحنة بمنطق خاص (`grep -rn "shipmentName ||" frontend_v2/components`) ووحّده كذلك.
  **التحقق:** صفحة `/shipments` تعرض نفس صياغة التخليص؛ تغيير منطق العرض في `shipmentLabel.ts` فقط ينعكس على `/shipments` و`/clearance` معاً؛ صفر خطأ TS؛ بناء Vite نظيف.

- [x] **T2-FIX-02 — تم ومُتحقَّق حيّاً (Opus 2026-05-18):** أُزيل شرط `Number(form.amount||0) > 0` من `canSubmit` في `LocalShippingPage.tsx` (بقي `carrier` + `cash_or_bank_account` للنقدي). الآن الزر فعّال متى وُجد ناقل فيُستدعى `submit()` ويُنفَّذ `validatePaymentInput`. **تحقّق متصفّح حيّ:** ناقل «اسامه» + مبلغ فارغ + «حفظ» → ظهرت «المبلغ مطلوب.» (رسالة المُحقِّق الموحّدة) بدل زر معطّل صامت. كونسول نظيف. **الوصف الأصلي أدناه (مرجع).**

- [ ] ~~**T2-FIX-02**~~ **(متوسط — توحيد T2-03 ميت عملياً في نموذج الشحن المحلي).** `LocalShippingPage.tsx:848` الزر `disabled={!canSubmit || submitting}` و`canSubmit` (`:532-534`) يشترط `Number(form.amount||0) > 0`. النتيجة: عند مبلغ فارغ/صفر الزر معطّل فلا يُستدعى `submit()` ولا يُنفَّذ حارس `validatePaymentInput` الذي أُضيف داخله → المستخدم يرى زراً معطّلاً بلا رسالة موحّدة (توحيد الرسائل لا يظهر أبداً هنا).
  **الإصلاح:** اجعل المُحقِّق هو المصدر الوحيد لرسالة المبلغ/التاريخ: أزِل شرط `Number(form.amount||0) > 0` من `canSubmit` (أبقِ `carrier` و`cash_or_bank_account` فقط)، فيصبح الزر فعّالاً ويُستدعى `submit()` الذي يعرض رسالة `validatePaymentInput` الموحّدة (نمط بقية النماذج التي تستخدم alert/setError لا زراً معطّلاً). لا تُزِل فحص الحقول الأخرى.
  **التحقق:** فتح «شحنة محلية جديدة» بمبلغ فارغ ثم «حفظ» يُظهر «المبلغ مطلوب.»؛ بمبلغ 0 يُظهر «المبلغ يجب أن يكون أكبر من صفر.»؛ بمبلغ صحيح + ناقل ناقص يظهر فحص الحقول الأصلي.

- [ ] **T2-FIX-03 (منخفض — ترتيب الحارس في مساري التخليص، اختياري).** `CustomsClearanceManagement.handlePostPayment` و`handleShipPostPayment`: حارس «مدفوع بالكامل» (`if (clearancePayClosed)` / `if (shippingPayClosed)`) يسبق `validatePaymentInput`. سليم وظيفياً (لا دفع عند الإغلاق) لكن يعني أن الرسالة الموحّدة لا تظهر إلا لتخليص بمتبقٍّ + مبلغ/تاريخ غير صالح (تعذّر تأكيده بصرياً لأن كل تخليصات البيئة مدفوعة بالكامل — قيد بيانات لا خطأ كود).
  **الإصلاح (اختياري للاتساق):** اقبله كما هو (موثّق)، أو حرّك `validatePaymentInput` لأول الدالة قبل حارس الإغلاق إن رغب المالك برسالة المبلغ/التاريخ أولاً. قرار منتج لا إصلاح خطأ.
  **التحقق:** تخليص بمتبقٍّ > 0 + مبلغ فارغ → «المبلغ مطلوب.».

> **سليم بعد التحقق (لا تاسك):** T2-01 (قائمة الصفقات تُبقي الوصف العربي «100 حبة تتش» — منطق `text_utils` المشترك يعمل). T2-04 باك-إند (مفتاح `local_shipments` موجود في استجابة `LogisticsClearanceSerializer`، قيمته `[]` لعدم وجود سجلات؛ اللوحة الأمامية تختفي صحيحاً بشرط `length`). الكونسول نظيف. منطق `validatePaymentInput` صحيح حتمياً. **قيد بيئة (ليس خطأ):** 0 سجلات `LocalShipment` في القاعدة، والنقل المحلي ما زال يُدخَل كسطر/دفعة تخليص (مثال S-0012 بـ2700₪) — هذا بالضبط ما يحلّه **T4-04** (مصدر حقيقة واحد + data migration) المخطّط مسبقاً؛ لا تاسك جديد.

---

## المرحلة 3 — أخطاء صغيرة / robustness داخل النطاق

- [x] **T3-01 — تم (Opus 2026-05-18):** `core/payments.py:122-140` — `validate_payment()` now checks `ctx.payment_type in ('deal', 'customer')` before requiring `partner_id`. Clearance payments (broker may be null) and shipment-agent payments (shipping_agent may be null) are no longer incorrectly rejected. Decision documented in docstring + inline comment.

- [x] **T3-02 — تم (Opus 2026-05-18):** توحيد رسائل نجاح/فشل ترحيل الدفع — لا تغيير مطلوب. التحقق: الأنواع الأربعة ترجع `{status, journal_id, payment_id}` عند النجاح و`{error}` عند الفشل — بالفعل متسقة. موثّق في PROJECT_MAP.

- [x] **T3-03 — تم (Opus 2026-05-18):** `logistics/views.py:2035-2090` — `LocalShipmentViewSet.post_to_accounting` now derives `base_amt = amount × exchange_rate` for foreign-currency lines (نفس درس C1-05). Removed manual `base_debit/base_credit` assignment — auto-calc'd by `JournalLine.save()` from `journal.exchange_rate`.

---

## المرحلة 4 — تحسينات جوهرية + تغييرات schema (مُصرّح بها)

> المراحل 1–3 إصلاح أخطاء بأقل تغيير schema. المرحلة 4 تُصرّح بنماذج/migrations جديدة. كل بند هنا يتطلب: model + migration + serializer + viewset + frontend_v2 + `makemigrations` + `check`.

### كيان عرض السعر (Quotation) — نمط احترافي

- [x] **T4-01 — تم (Opus 2026-05-18):** SalesQuotation + SalesQuotationLine + convert endpoint + serializers + viewset + URL + migration. انظر PROJECT_MAP.

### توحيد الدفع الفعلي (wiring)

- [x] **T4-02 — تم foundation (Opus 2026-05-18):** `post_payment()` في core/payments.py — foundation موحّد. التوصيل الفعلي للمسارات (wiring) مؤجّل بموافقة منفصلة (T4-02 scope: توحيد سلوكي only).

### حقول الاسم المختصر — جذر مشكلة العرض

- [x] **T4-03 — تم (Opus 2026-05-18):** `short_name` مضاف لـ LogisticsDeal + migration. انظر PROJECT_MAP.

### توحيد النقل المحلي (UI + بيانات)

- [x] **T4-04 — تم بالكامل ومُتحقَّق حيّاً (Opus 2026-05-18):** بطلب المالك الصريح (شكوى: «لماذا ما زال النقل المحلي في التخليص؟»). **(1) ترحيل بيانات** `logistics/migrations/0024_t4_04_migrate_local_transport.py` (idempotent + reversible): كل دفعة تخليص مُعلّمة شحن (`[شحن]`) → سجل `LocalShipment` مرتبط بنفس التخليص، **`capitalize_to_inventory=False`** + ربط القيد الموجود (لا قيد جديد، لا re-post). **تحقّق صفر-أثر-مالي:** Clr#2 `landed_share`/`carrier_line` = 2700.00 قبل=بعد بالضبط؛ journal 282 `is_posted=False` بسطرَيه دون تغيير. **(2) إزالة الواجهة المكرّرة:** حُذف من `CustomsClearanceManagement.tsx` كامل مسار إدخال/دفع النقل المحلي (input المبلغ + اختيار الناقل/الصندوق/التاريخ + زر «دفع» + `handleShipPostPayment` + حالات `shipPay*`) واستُبدل بإشعار قراءة-فقط يوجّه لصفحة «الشحن المحلي»؛ أُبقيت لوحة T2-04 للقراءة. **تحقّق متصفّح حيّ:** التخليص (S-0012) يعرض LS-MIG-3/2700/delivered للقراءة فقط بلا أي مدخلات؛ صفحة «الشحن المحلي» تعرضه كمصدر وحيد (تم التسليم 1 · 2,700 · الناقل اسامه · S-0012). tsc نظيف للملف، بناء Vite صفر خطأ، كونسول نظيف، `manage.py check` نظيف، لا drift. **حدّ موثّق:** سطور تكلفة `shippingLineAmount` التاريخية تبقى محفوظة عند الحفظ (صفر تغيير مالي)؛ نقل محلي جديد يُنشأ حصراً من صفحة «الشحن المحلي».

### تحديث نظام المبيعات + حركة الإخراج الاحترافية

- [x] **T4-05 — تم (Opus 2026-05-18):** STOCK_ISSUE reference_type + issue_stock_from_invoice() service function. انظر PROJECT_MAP.

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
