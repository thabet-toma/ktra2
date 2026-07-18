# PROJECT_MAP — K.T.R.A

## 📌 [قاعدة صارمة — الهجرات وبيئة الاختبار] (مثبّتة — اقرأها قبل أي عمل على الموديلات/الهجرات)

**الثابت (Invariant):** الموديلات هي **مصدر الحقيقة الوحيد**. بيئة الاختبار تبني المخطط من
الموديلات مباشرةً (`core/test_settings.py` يعطّل الهجرات عبر `MIGRATION_MODULES` → run_syncdb).
السبب: سلسلة الهجرات القديمة تفترض جداول legacy خارجية (`managed=False` في `0001_initial`
لـ accounting/partners/tenants + إعادة تسمية أعمدة بنمط «أضِف بنفس db_column ثم احذف القديم»)،
فلا تُبنى على قاعدة نظيفة. (التفاصيل: AUDIT 2026-07-02 أدناه.)

**ممنوع منعاً باتاً (DON'T):**
1. **لا** تُصلح فشل قاعدة الاختبار بتعديل هجرة قديمة مُلتزمة (`0001_initial`… إلخ). التعديل
   يكسر تطابق الحالة مع الإنتاج ولا يُحقَّق مقابل MySQL. الإصلاح دائماً في `test_settings`.
2. **لا** تُنشئ موديلاً جديداً بـ `managed=False` (باستثناء `core.SystemAttachment` القائم).
   كل جدول جديد `managed=True` بهجرة `CreateModel` نظيفة.
3. **لا** تُعِد تسمية عمود عبر (AddField بنفس `db_column` + RemoveField). استخدم `RenameField`.
4. **لا** تعتمد على تشغيل سلسلة الهجرات من الصفر لنشرٍ جديد — ابنِ من الموديلات أو من نسخة
   مخطط الإنتاج.

**واجب قبل الـcommit لأي تغيير موديل/هجرة (DO — أمر التحقّق):**
```bash
python manage.py test --settings=core.test_settings   # يجب أن يمرّ (≥173) — يكشف أي موديل غير متّسق
python manage.py makemigrations --check --dry-run      # يجب أن يقول "No changes" — يمنع انجراف الموديل عن الهجرات
python manage.py check                                 # 0 مشاكل
```
إن فشل الأول: موديلك غير متّسق (لا تلمس test_settings — أصلح الموديل). إن فشل الثاني: نسيت
توليد هجرة للتغيير (`makemigrations`). هكذا **لا يتكرّر الخطأ**: أي كسر يظهر فوراً في هذه الأوامر.

---

## [LIVE TEST — تجربة مستخدم جديد حيّة كاملة: صفقتان → فاتورتان دوليتان, 2026-07-18]

**المنهجية:** جولة حيّة كمستخدم جديد بالكامل عبر المتصفح (Chrome MCP) على `localhost:3000` —
إنشاء صفقتين بموردين ومنتجات جدد من الصفر، ودفعهما فعلياً عبر الرحلة الكاملة (شحنة → ضمّ
صفقة → دفع شحن للوكيل → تخليص جمركي → فاتورة دولية). التفاصيل الكاملة والتوصيات في
`UX_AUDIT_AND_IMPROVEMENTS.md` (قسم «الجلسة الثانية»).

**النتيجة:**
- **D-0108 (Ningbo Ocean Power) → شحنة SH-0001 → فاتورة دولية `INV-0002` بمبلغ ₪12,362 —
  نجحت فعلياً وظهرت في `/international-invoices`.** سجل حقيقي مُتحقَّق، وليس محاكاة.
- **D-0109 (Chengdu Sunrise Electric) → شحنة SH-0002 → توقّفت عند خطوة التخليص** (تم إنشاء
  السجل، لم يُستكمل ملء بنود التكلفة قبل إيقاف الجلسة) — لم تُنشأ الفاتورة الثانية.

**عطل باك-إند حقيقي مكتشَف ومُصلَح جزئياً (غير مُتحقَّق على السيرفر الحي):**
`LogisticsShipmentViewSet` (`logistics/views.py`, بعد `get_queryset()`) لا يملك `perform_create`
مُخصّصاً — بعكس `LogisticsDealViewSet._next_deal_ref`/`perform_create` (نفس الملف, حوالي
السطر 125–150). النتيجة: `POST /api/logistics/shipments/` يرفض دائماً بـ
`{"shipment_number":["لا يمكن لهذا الحقل ان يكون فارغاً."]}` لأن حقل «رقم الشحنة» بالواجهة
`readOnly` ويرسل `""` دائماً (`ImportDocumentScreen.tsx`, حقل «رقم الشحنة»، متوقّع ترقيم
تلقائي من الخادم لا يوجد). **الإصلاح المطبَّق:** إضافة `_next_shipment_number` (نمط SH-####
مطابق لـ`_next_deal_ref`) + `perform_create` يماثلان صفقة D-####. `py_compile` نظيف، **لكن لم
يُتحقَّق بـ`manage.py test` (Django غير متاح في بيئة التنفيذ) ولم ينعكس على سيرفر التطوير الحي
للمالك (لم يُعِد تحميل الكود تلقائياً — يحتاج إعادة تشغيل يدوية من المالك ثم تشغيل الثابت
أعلاه قبل الاعتماد عليه).**

**Workaround مؤقت مستخدَم لإكمال الرحلة الحية دون كسر سلامة النظام:** استُخدمت واجهة REST
الفعلية للنظام مباشرة (`fetch()` بترويسة `Authorization: Token …` + `X-Tenant-Id` مُلتقَطة من
جلسة المتصفح المُصادَق عليها فعلاً) لتمرير `shipment_number` يدوياً عند الإنشاء، ولتأكيد دفعة
مورد بلا صورة سليب بنكي (الحقل غير إلزامي فعلياً في الـserializer رغم أن الواجهة تمنع التأكيد
بدونه)، ولضبط `total_cbm`/`total_weight_kg`/`deal_allocations` لتوزيع تكلفة الشحن يدوياً. كل
هذه استدعاءات API شرعية عبر جلسة المستخدم الحقيقية — وليست بيانات مُلفَّقة مباشرة في القاعدة.

**بند مُتبقٍّ صريح:** الإصلاح في `logistics/views.py` (`LogisticsShipmentViewSet.perform_create`)
بحاجة إلى: (1) إعادة تشغيل سيرفر Django المحلي من المالك، (2) تشغيل
`python manage.py test --settings=core.test_settings` للتأكد من عدم كسر شيء، (3) اختبار حيّ
لإنشاء شحنة عبر الواجهة مباشرة (بدون API مباشر) للتأكد أن الحقل يُملأ تلقائياً.

---

## [FIX — «شحن داخل الصين» كان يُحتسب مرتين في الفاتورة الدولية, 2026-07-16]

- **الجذر:** عقد ج8/M4 يقول `deal.total_amount = بضاعة − خصم + شحن داخل الصين` (بلا ضريبة).
  لكن `compute_deal_invoice_lines` كان يأخذ `merch_pool = deal_val_ils` كاملاً (وهو يشمل الشحن
  داخل الصين محوّلاً للشيكل) **ثم** يضيف `internal_ils` فوقه ضمن `logistics_pool` — فالشحن
  داخل الصين يدخل تكلفة الوصول مرتين. مثال حقيقي (D-0105/INV-0002): صفقة 5,500$
  (بضاعة 5,380$ + شحن 120$) × 3.24 → بضاعة 17,820₪ + شحن 388.80₪ بدل 17,431.20₪ + 388.80₪.
- **الإصلاح:** `merch_pool = deal_val_ils − internal_in_landed` (بحدّ أدنى صفر). الشحن داخل
  الصين يبقى بندَ لوجستيات واحداً، والإجمالي لا يتغيّر — تتغيّر القسمة بين البضاعة واللوجستيات
  فقط. عند `is_shipping_included=True` لا خصم (الشحن أصلاً داخل أسعار البنود) — السلوك كما كان.
- بذلك صار ثابت `sum(landed) == deal_val_ils + freight + clearance` صحيحاً لكل الحالات؛ كان
  ينكسر صامتاً كلما `shipping_cost_estimate > 0` (اختبارات الثبات القديمة تمرّر 0 فلم تلتقطه).
- صندوق مجاميع الفاتورة صار يقرأ `line_meta.subtotal_merch_ils` (البضاعة صافية) بدل
  `deal_total_ils` (إجمالي الصفقة الشامل للشحن)، ويُخفي سطر «الشحن داخل المنشأ» عند
  `shippingIncluded` لأنه مضمّن في البضاعة — فيتطابق الصندوق مع «المجموع قبل الضريبة».
- **الأثر على البيانات:** الفواتير غير المرحّلة تُصحَّح حيّاً عبر
  `compute_live_purchase_invoice_read_payload`/`recalculate_landed_for_shipment`؛ المرحّلة
  تبقى كما رُحّلت (تحتاج unpost → إعادة حساب → ترحيل).
- الملفات: `logistics/landed_cost.py`, `logistics/tests/test_landed_cost.py`,
  `frontend_v2/components/procurement/invoices/InvoiceForm.tsx`.
- تحقق: TDD (اختبار يفشل ثم ينجح بأرقام D-0105 الحقيقية) · Django **308/308** · لا هجرة.

---

## [FIX — تحويل جزئي احترافي + نقل محلي إلى الفاتورة الدولية, 2026-07-16]

- صار `LocalShipment` المرسمل وغير الملغي مصدر النقل المحلي الحي في landed cost حتى قبل
  الدفع؛ يُحوّل `amount × exchange_rate` إلى شيكل ويوزّع حسب CBM/KG مثل الشحن، مع fallback
  لأسطر التخليص القديمة فقط عند غياب سجل نقل، كي لا تتكرر التكلفة. الدفع للناقل بقي مستقلاً
  محاسبياً عن استحقاق التكلفة وعن دفعة مورد الفاتورة.
- أضيف عقد `clearance-import-options` يعيد حالة كل صفقة في الشحنة (متبقية/محوّلة + رقم
  الفاتورة)، ومنع خادمي ذري لإعادة تحويل الصفقة نفسها. يمكن تحويل صفقة واحدة ثم العودة لاحقاً
  لتحويل البقية؛ رحلة الاستيراد لا تعتبر الشحنة مكتملة حتى تصبح كل الصفقات مفوترة.
- مودال الفواتير الدولية يعرض عداد المتبقي/المحوّل، «اختيار كل المتبقي»، ويعطّل المحوّل مع
  رابط فاتورته. روابط التحويل من رحلة الشحنة تفتح `/international-invoices` الصحيح، وتُحدّث
  الحالة عند عودة التركيز. تفاصيل الفاتورة تكشف اسم/رقم الشحنة وزر «فتح رحلة الشحنة».
- شاشة الدفعات تعرض استحقاق/مدفوع/متبقي النقل المحلي بوضوح وتشرح أن التكلفة تدخل الفواتير
  بينما تسوية الناقل تبقى دفعة مستقلة.
- الملفات: `logistics/domain/inland.py`, `logistics/landed_cost.py`, `logistics/views.py`,
  `logistics/serializers.py`, `logistics/tests/test_clearance_import.py`,
  `frontend_v2/components/import-flow/{ImportDocumentScreen.tsx,importJourneyGuidance.ts}`,
  `frontend_v2/components/procurement/invoices/{ClearanceImportModal.tsx,sections/ConversionDetailsSection.tsx}`,
  `frontend_v2/services/purchaseInvoiceApi.ts`, `frontend_v2/types/{invoice.ts,purchaseInvoice.ts}`,
  `frontend_v2/utils/mapPurchaseInvoiceDto.ts`, و`frontend_v2/e2e/import-journey-guidance.spec.ts`.
- تحقق نهائي: Django **303/303**، `check` صفر، migration drift صفر، TypeScript صفر،
  Vite production build ناجح، واختبار guidance **5/5**؛ لا موديل أو هجرة جديدة لهذا الإصلاح.

---

## [MAINTENANCE — دورة الأداء والموثوقية وUX الشاملة, 2026-07-15]

### خط الأساس والبيئة
- التاريخ الفعلي: `2026-07-15 +03:00`؛ Python `3.13.5`، Node `24.13.0`، npm
  `11.7.0`. المثبّت محلياً Django `6.0.3`/DRF `3.17.1` بينما requirements يثبّت
  `6.0.1`/`3.16.1`؛ لم تُرفع الاعتماديات لأن لا عيب توافق مُثبتاً يستدعي ذلك.
- قبل التعديل: backend **281/281** أخضر (122.384s)؛ `check` صفر؛ migration drift صفر؛
  Vite build ناجح (main `1127.59kB` raw / `270.96kB` gzip، PWA 136 أصلاً / 3226.83KiB).
  `tsc --noEmit` كان يفشل حصراً من import خاطئ في `DepartmentCard.tsx`.
- تحسينات 2026-07-10 التاريخية ما زالت موجودة ومتصلة: مهل MySQL/connection reuse،
  dashboard cache tenant-scoped، فهارس وترقيم القيود، journal batching، كاش أوفلاين بعمر
  أقصى، Service Worker cross-origin guard، وroute-level lazy loading.

### M1 — P0 عزل ملخص المخزون + عقد UOM
- **الجذر/الدليل:** `StockMovementViewSet.summary` كان يستعلم كل `Product` بلا tenant؛
  القياس أعاد منتج Tenant B داخل طلب Tenant A. أضيف `tenant=tenant` وempty آمن عند غيابه؛
  اختبار يثبت إخفاء الأجنبي وصحة `count=2` و`value=35`.
- `UnitOfMeasure` قاموس عالمي بلا tenant، لكن serializer طلب field وهمياً اسمه `tenant`
  فكان endpoint يرد 500. صُحّح العقد إلى `id/code/name_ar/name_en` بلا موديل أو هجرة؛
  القياس بعده 200 من شركتين ونفس القاموس بلا حقل tenant.
- الملفات: `inventory/views.py`, `inventory/serializers.py`,
  `inventory/tests/test_product_api.py`. لا تغيير تقييم مخزون أو منطق مالي.

### M2 — P1 إزالة N+1 المقاسة
- تفاصيل فاتورة البيع (`lines.product`): قبل **16→20 query** عند 2→6 أسطر؛ بعد
  `prefetch_related('lines__product')` أصبحت **16→16**، و`product_name` لم يتغير.
- قائمة عروض الأسعار: قبل 2→6 صفوف = **7→11 query** و`1179→3267B`؛ بعد list serializer
  الخفيف = **4→4** و`541→1353B`. التفاصيل فقط تجلب `lines__product` وتبقى كاملة.
- شجرة الحسابات/الشريك المرتبط: قبل 2→6 = **5→9 query**؛ بعد Prefetch tenant-scoped
  = **4→4** بنفس payload، واختبار يمنع تسريب شريك شركة أخرى.
- N+1 القيود المنفّذ في العمل السابق بقي ثابتاً ومختبراً، وكذلك
  `LogisticsPayment.select_related('journal')`.

### M3 — P1 دورة طلب ومزامنة محدودة
- عميل REST كان ينتظر **120 ثانية** ويصبح بلا مهلة في متصفح لا يدعم
  `AbortSignal.timeout`. أصبح السقف **30 ثانية** بـ`AbortController` فعلي مع احترام إلغاء
  المستدعي؛ طُبّق على restApi وعلى عملاء المحاسبة والمخزون والمصادقة والداشبورد وفواتير الشراء.
- طابور mutations كان يترك 5xx في `syncing` للأبد. الآن 4xx=`failed` كما كان، و5xx/فشل
  الشبكة=`pending` مع نص خطأ مرئي ومهلة فعلية. Playwright يثبت 503→pending+error.
- Service Worker لم يعد يترك fetch يعمل بعد سقوط مهلة navigation، ولا يخزّن 4xx/5xx كأصل
  أوفلاين صالح؛ الكاش القديم/version cleanup ودعم الأوفلاين بقيا دون حذف.

### M4 — P1 حالات UX والحمل الشبكي
- فشل قائمة فواتير الشراء لم يعد يُبتلع كقائمة فارغة: `AseelErrorState` + Retry، وفشل detail
  يعطي toast قبل الرجوع، والتحديث اليدوي يعلن loading/success/failure وينتهي دائماً.
- اشتراك الشحنات كان يجلب القائمة كاملة كل **5 ثوانٍ** ويحوّل الخطأ إلى `[]`; صار initial +
  refresh عند عودة focus، يحتفظ بآخر نجاح ويبلغ شاشة الشحنات بخطأ/Retry. حُذف اشتراك موردين
  كامل غير مستخدم من الشاشة. اشتراك الموردين العام استُبدل كذلك من polling 5s إلى focus refresh.
- الصفقات لا تحوّل فشل API إلى صفر صفقات؛ الشاشة تنهي loading إلى خطأ/Retry قابل للتنفيذ.
- أُصلح import `DepartmentCard` السابق؛ `tsc --noEmit` صار نظيفاً.

### التحقق والحدود
- تحقق نهائي: Django **286/286** أخضر (120.255s)؛ `manage.py check` صفر؛
  `makemigrations --check --dry-run` = No changes؛ TypeScript صفر؛ `git diff --check` نظيف.
  Vite production build ناجح (main `1128.78kB` raw / `271.27kB` gzip، PWA 136 أصلاً /
  `3229.63KiB`). الزيادة ~1.2kB raw مقابل baseline هي حالات الخطأ/Retry الجديدة؛ route splitting
  التاريخي ما زال فعالاً، لكن تحذير chunk>500k و`eval` في الحاسبة ما زالا قائمين.
- Playwright المركز: offline queue **3/3** وconflict flow **2/2**. التشغيل الكامل قبل إصلاح
  preload أعطى **13/23**؛ عيب dynamic-import الأوفلاين أُصلح وثبت targeted أخضر، فتتبقى **9**
  حالات بيئية/قديمة تفتح مسارات مصادقة بلا session وبلا Django محلي (لا يظهر الجدول/الأزرار)،
  وليست فشلاً في الوحدات المعدلة. لم تتوفر credentials لاختبار مرئي مصادَق.
- لا موديل/هجرة جديدة في هذه الدورة، ولم تُطبّق أي migration أو production mutation.
- لم تتوفر جلسة إنتاج مصادَقة أو MySQL production، لذلك لا ادعاء p95 حي. الدليل المحلي هو
  query-count/payload/build. بقيت قوائم deals/shipments ذات nested payload وN+1 مقاس، وقوائم
  أخرى opt-in pagination فقط. لا تُرقّم sales/partners/deals عمياناً قبل نقل search/date/status
  كاملة للخادم كي لا تختفي مستندات مالية قديمة.
- أسرار قديمة موجودة كـdefaults في settings تستلزم **تدوير قيم الإنتاج ووضع env أولاً**؛
  لا يمكن حذف defaults بأمان من هذه البيئة دون تنسيق إنتاج، وهي production-access-blocked.
- rollback: عكس ملفات هذه الفقرة فقط يعيد السلوك السابق؛ لا rollback قاعدة بيانات مطلوب.
  النشر: شغّل الاختبارات/check/migration check والبناء، ثم انشر backend+dist معاً؛ لا تنشر
  migrations غير المرتبطة قبل مراجعة عمل الاستيراد غير الملتزم الموجود مسبقاً.

## [MAINTENANCE — إغلاق حدود القوائم والحزمة والأسرار والهجرة, 2026-07-15]

### الخطة والأولويات
- **P1 — عقود الصفقات/الشحنات:** النجاح = list خفيف، detail كامل عند الفتح، وعدد SQL ثابت
  مع نمو الصفحة. الدليل السابق كان 13 query للصفقات و24 للشحنات، مع payload قائمة صفقة
  يكاد يساوي detail.
- **P1 — الترقيم الآمن:** النجاح = نقل search/status/type/date للخادم قبل ترقيم أي شاشة
  أساسية، 50 صفاً افتراضياً وسقف 200، وعدم إخفاء المستندات القديمة داخل client-side filter.
- **P1 — الحزمة/الحاسبة:** النجاح = كل chunk أقل من 500kB، لا `eval`، ولا سر AI في bundle.
- **P0 — الأسرار:** النجاح = صفر credential production literal، وفشل نشر واضح قبل أي mutation
  إذا لم تكن قيم الإنتاج مضبوطة. تدوير القيم نفسها يتطلب وصول مالك الإنتاج.
- **P1 — الهجرة/الاستيراد الموجودان مسبقاً:** النجاح = تدقيق additive/MySQL-safe قدر الإمكان
  دون اتصال إنتاج، واختبارات مالية كاملة؛ لا تطبيق migration ولا نشر من هذه البيئة.

### M5 — عقود deals/shipments الخفيفة وإزالة N+1
- أضيف `LogisticsDealListSerializer` و`LogisticsShipmentListSerializer`؛ `list` يعيد headers
  وعدادات/ملخصات فقط، بينما `retrieve` وحده يعيد items/payments/attachments/allocations.
  فتح الصفقة أو الشحنة في الواجهة يجلب detail صراحةً بدلاً من الاعتماد على nested list.
- نفس fixture (8 سجلات، ولكل سجل بند+دفعة+رابط): الصفقات **13→5 query**، وثبتت 5 عند
  page-size 2→8؛ الشحنات **24→4** وثبتت 4. payload صفقة واحدة داخل الغلاف
  **3064→1185B (-61.3%)**؛ شحنة خفيفة 1406B مقابل detail 2396B (-41.3%).
- أضيفت فلاتر tenant-scoped: الصفقات search/status/date؛ الشحنات
  search/status/shipping_type/date/deal_id. الشاشتان تستخدمان page=1/page_size=50، debounce،
  و«تحميل المزيد». ربط شحنات الصفقة يستخدم `deal_id` بدل تنزيل كل الشحنات ومسح nested deals.
- اختبار `logistics/tests/test_list_contract_perf.py` يثبت العقد، العزل، ثبات query count،
  الفلاتر، وفصل list/detail.

### M6 — ترقيم القوائم المالية والشركاء بلا كسر البحث
- فواتير البيع، عروض الأسعار، العملاء، الشركاء، وفواتير الشراء أصبحت مرقمة في شاشاتها
  الأساسية (50، max 200) بعد إضافة الفلاتر الخادمية المكافئة. query count لقوائم sales/partner
  ثابت عند 5→20 صفاً، وقائمة الشريك لا تستعلم attachments لكل صف.
- محددات partner/invoice التي لا تعرض pagination تستخدم endpoints `lookup` raw بسقف 500؛
  هذا يمنع payload غير محدود ويحافظ على عقد المكوّنات الحالية. إذا تجاوز master data هذا السقف
  يلزم server autocomplete في دورة لاحقة، لا إعادة unbounded lists.
- فواتير الشراء كانت ثغرة إضافية: القائمة كانت تجلب `items__product` لكل الفواتير وتحسب
  `items_count` من manager. أصبحت تستخدم `COUNT(items)` داخل queryset، وفلاتر
  search/is_posted/is_return/date قبل pagination؛ التفاصيل وحدها prefetch للبنود.
- اختبارات: `sales/tests/test_list_pagination_filters.py`,
  `partners/tests/test_partner_list_pagination.py`, وpurchase-invoice regression ضمن
  `logistics/tests/test_list_contract_perf.py`.

### M7 — الحزمة و`eval` ومفتاح Gemini
- main entry: **1128.78/271.27kB raw/gzip → 227.08/61.07kB** (-79.9%/-77.5%).
  أكبر chunk نهائي Dashboard 324.76kB؛ كل chunks تحت 500kB واختفى تحذير large chunk.
  PWA precache: **3229.63→2913.77KiB**.
- أضيف lazy-loading للشاشات العامة/الثقيلة وmanual vendor chunks لـ React/Dexie/icons.
  أزيل `@google/genai` من package/lock/importmap، وأزيل `define` الذي كان يحقن
  `GEMINI_API_KEY` في JavaScript العام. لا يوجد backend AI endpoint مصادق في المستودع؛ لذلك
  sourcing يعرض نتائج demo موسومة بوضوح، وإعادة AI الحقيقي يجب أن تكون server-side.
- استُبدل `eval` في الحاسبة بمحلل محدود 256 حرفاً يدعم الأرقام و`+ - * /` وunary signs،
  يرفض identifiers/JavaScript والقسمة غير المحدودة. فحص المستودع: صفر `eval/new Function`
  وصفر Gemini key/SDK reference.

### M8 — أسرار environment-only وبوابة النشر
- أزيلت defaults الحقيقية لـ Django/MySQL/Cloudinary/OpenClaw من `core/settings.py`.
  `DJANGO_ENV=production` يفرض القيم المطلوبة عبر `ImproperlyConfigured`; التطوير فقط يملك
  defaults غير حساسة. مهلة OpenClaw الافتراضية أصبحت **60s بدل 600s**.
- `deploy.ps1` يتحقق قبل النسخ/backup/migrate من `DJANGO_ENV=production` ومن جميع متغيرات
  Django/MySQL/Cloudinary/OpenClaw، ويرفض SECRET_KEY placeholder/أقصر من 50 حرفاً.
  `core/test_settings.py` يستخدم Cloudinary placeholders اختبارية فقط كي تصل اختبارات uploader
  المموهة إلى mock؛ لا اتصال خارجي ولا سر إنتاج.
- فحص آلي: صفر password/API secret/bearer token/SECRET_KEY literal في production settings؛
  import بإنتاج ناقص env يفشل كما يجب، و`deploy.ps1` parse errors = 0.
- **محجوب بالإنتاج:** القيم القديمة ظهرت سابقاً في المصدر/التاريخ؛ يجب تدوير DB password،
  Django secret، Cloudinary secret، وOpenClaw token وضبط `.env` على الخادم قبل أول نشر.
  لم تُعد كتابة Git history ولم تُدوّر أي قيمة من هذه البيئة.

### M9 — تدقيق migration وعمل الاستيراد السابقين
- `0054_localshipmentpayment.py` يطابق الموديل: `managed=True` وعملياته حصراً
  `CreateModel + AddIndex + AddIndex`، بلا Remove/Alter/RunPython أو mutation لبيانات قائمة.
  أسماء الفهارس 26/23 حرفاً (<64 MySQL). الهجرة additive، لكن لم تُطبّق محلياً أو إنتاجياً.
- اختبارات فصل الاستحقاق عن الدفع/التخليص/مرجع الشراء **16/16** خضراء؛ المجموعة الكاملة
  تثبت توازن القيود وعدم تغيير قواعد landed cost/payment separation. الملفات بقيت غير ملتزمة
  كما كانت لأن worktree يحوي عملاً سابقاً متداخلاً؛ لم يُنشأ commit شامل أو نشر تلقائي.

### تصحيح قاعدة التطوير المحلية (2026-07-15)
- قاعدة `global_erp_pro` المحلية هي schema legacy (99 جدولاً): تسجل logistics 0001–0008
  بلا أي inventory migrations، ولا تحتوي `stock_movements`؛ لذلك `migrate` يرفضها بـ
  `InconsistentMigrationHistory`. لم تُعدّل القاعدة ولا جدول `django_migrations` ولم يُستخدم fake.
- قاعدة التطوير الصحيحة هي `smartktra_smart-ktra` (149 جدولاً): inventory 0001–0012 وlogistics
  0001–0054 متسقة. صُحّح `.env` المحلي المُهمَل من Git إليها؛ الاتصال ناجح،
  `migrate --check` ناجح و`migrate --plan` = No planned migration operations.

### M10 — P1 إزالة بوابة «البيانات المحلية» من فتح التطبيق (2026-07-15)
- **معيار النجاح:** مصادقة Django تبقى إلزامية، لكن الشل المصادَق يجب أن يظهر قبل اكتمال
  بيانات النشاط/النقاط غير الحرجة؛ طلب mapper بطيء أو متوقف لا يجوز أن يبقي spinner عاماً.
- **الجذر والدليل القابل للتكرار:** `AuthContext.applyUserSession` كان ينتظر بالتسلسل
  `GET /hr/users/:id/` ثم `GET /mapper/activityStatus/:id/` وربما `PUT` للتهيئة، ولا يخفض
  `authLoading` إلا بعد الجميع. عميل `sqlApiClient` كان يستخدم `fetch` خاماً بلا timeout.
  في Playwright مع profile فوري وactivity مؤخر 5s لم يظهر الشل خلال **8000ms** قبل الإصلاح.
- **الحل الجراحي:** بقي profile/approval هو بوابة الأمان الوحيدة؛ بعد نجاحه تُضبط الجلسة فوراً
  وتبدأ تهيئة activity fire-and-forget مع تحذير منظم عند الفشل. كل mapper requests أصبحت تمر
  عبر `restApi.apiFetch` ذي `AbortController` والمهلة بدلاً من fetch غير المحدود. لم يتغير role
  أو tenant enforcement أو أي منطق محاسبي/مالي.
- **بعد الإصلاح:** بنفس activity delay (5s) ظهر الشل على Vite dev خلال **1693ms** والطلب غير
  الحرج ما زال pending. على production `dist` الجاهز ظهر خلال **470ms** (<1500ms budget)،
  وبقي activity pending؛ أي أن زمنه لم يعد جزءاً من critical path. الاختبار الدائم:
  `frontend_v2/e2e/auth-startup-performance.spec.ts` ويمنع Service Worker من تجاوز mocks.
- **الملفات/المخاطر/التراجع:** `frontend_v2/contexts/AuthContext.tsx`,
  `frontend_v2/services/sqlApiClient.ts`, واختبار E2E أعلاه. الخطر المتبقي هو أن زر/عداد النشاط
  قد يظهر بعد الشل عند شبكة بطيئة، وهو مقصود وأفضل من حجب النظام كله. rollback كودي فقط ولا
  migration أو data rollback. يلزم نشر `dist` الجديد مع كود الواجهة؛ لم يحدث نشر تلقائي.

### M11 — P1 منع إنذار الاتصال الكاذب المتكرر (2026-07-15)
- **الجذر/الدليل:** `useOnlineStatus` كان يشغّل `HEAD /health/` مستقلاً من كل مكوّن يستخدم
  hook (App ولوحة mutations ومحررات)، وأي timeout/503 منفرد خلال 5s يحوّل حالته فوراً إلى
  offline. بذلك يمكن لفحص أن يفشل وفحص متزامن أن ينجح بينما الخادم سليم، فيظهر الشريط كل فترة.
  وقت التدقيق أعاد health الإنتاج `200` في 5/5 محاولات (`0.625–1.455s`) مع CORS صحيح.
- **الحل:** جميع مستهلكي hook يشتركون الآن في probe واحدة in-flight. الفحص يبدأ بـHEAD
  `cache:no-store`؛ عند فشله ينتظر 500ms ويؤكد الحالة بـGET صغير. لا تظهر حالة الخادم غير
  المتاح إلا بعد فشل الاثنين، بينما `navigator.offline` الحقيقي يبقى فورياً. كلا الطلبين له
  `AbortController` وسقف 5s، لذلك أسوأ تأخير لتأكيد API-only outage محدود بنحو 10.5s.
- **التحقق:** `connection-health-stability.spec.ts` **2/2**: 503 عابر ثم 200 لا يعرض الشريط،
  وفشل مؤكد مرتين يعرض الرسالة وزر الإصلاح. مجموعة الاتصال/الأوفلاين المجاورة **8/8**،
  TypeScript PASS، وحدات **3/3**، وVite/PWA build PASS. لا تغيير backend أو DB أو migrations.
- **الحد/التراجع:** لا يمنع هذا انقطاعاً حقيقياً؛ يؤخر فقط إعلان API-only outage حتى تأكيده.
  التراجع بعكس `frontend_v2/hooks/useOnlineStatus.ts` واختبار E2E؛ يلزم نشر `dist` الجديد حتى
  يصل الإصلاح للمتصفح، ولم يحدث نشر تلقائي.

### التحقق النهائي والقيود
- Backend: **293/293 PASS (142.736s)**؛ `manage.py check` صفر؛
  `makemigrations --check --dry-run` = No changes. لم يحدث اتصال أو تعديل لقاعدة الإنتاج.
- Frontend: `npx tsc --noEmit` PASS؛ `npm test` **3/3**؛ Vite/PWA production build PASS
  (3476 modules؛ main `227.01kB` raw / `61.13kB` gzip، وكل chunk <500kB)؛
  `git diff --check` نظيف.
- E2E المركّزة: **13/13 PASS** (auth startup 1، import guidance 4، fee editor 3، offline queue 3، conflict 2).
  قياس production preview المنفصل **1/1 PASS** بميزانية 1500ms ونتيجة 470ms.
  لم تتوفر جلسة مصادقة/credentials لفحص بصري حي ولا MySQL production/p95/EXPLAIN؛ لا ادعاء
  p95 حي. بقيت تحذيرات build غير مانعة: Tailwind custom-property decimals، ومزج static/dynamic
  imports لـ tenantContext/offline db؛ لا large-chunk ولا eval warning.

### النشر والتراجع
- قبل النشر: دوّر الأسرار واضبط `.env` المطلوبة، شغّل 293 tests + migration drift + check +
  tsc/test/build وauth startup budget، راجع `0054` على نسخة staging MySQL/backup، ثم انشر
  backend و`dist` معاً.
- الناشر يأخذ backup قبل migrate ولا يعكس migrations تلقائياً عند الفشل. rollback للكود يعيد
  backend/frontend؛ إن طُبقت 0054 وبدأت الكتابة فلا تُسقط الجدول للتراجع—اترك الجدول additive
  وأعد الكود فقط حتى قرار صيانة بيانات صريح.

## [DONE — إظهار إضافة ضريبة/رسم في فاتورة الشراء, 2026-07-14]
- **السبب الجذري:** تبويب «الضرائب والرسوم» كان يخفي زر الإضافة بالكامل عند فتح فاتورة
  محفوظة لأن `viewMode` يدخل ضمن `effectiveReadOnly`؛ لذلك ظهر جدول فارغ يطلب الإضافة بلا
  أي إجراء ظاهر، كما كانت ضريبة القيمة المضافة الأساسية مختلطة مفاهيمياً مع البنود الإضافية.
- **المسار الجديد:** الأزرار ظاهرة للمسودة المحفوظة وتنفذ «تحرير + إضافة» بضغطة واحدة، مع
  فصل «ضبط ض.ق.م الأساسية» عن «إضافة ضريبة مستقلة» و«إضافة رسم». السطر الجديد يختار حساب
  الضريبة 1105 أو حساب الرسوم 5307 عند توفره، ويضع المؤشر مباشرة في المبلغ.
- **حالات المنع:** الفاتورة المرحّلة/التاريخية/للقراءة فقط تعرض سبباً واضحاً؛ المرحّلة تطلب
  «تراجع عن الترحيل» أولاً بدلاً من إخفاء الإجراء بصمت. فشل تحميل الحسابات مسجل في console
  ويظهر للمستخدم تنبيه قابل للتنفيذ.
- **TDD/تحقّق:** `purchase-invoice-fee-editor.spec.ts` **3/3** خضراء، و`vite build` ناجح؛
  اختبارات الواجهة مع انحدار رحلة الاستيراد **7/7**، واختبار الحفظ/الترحيل الخلفي **6/6**،
  و`manage.py check` بلا مشاكل. `tsc --noEmit` لا يظهر سوى خطأ `DepartmentCard.tsx`
  السابق والمسجل أدناه.

## [DONE — ناشر إنتاج آلي آمن لـ cPanel/LiteSpeed, 2026-07-14]
المصدر المرجعي الخارجي: `KTRA_DEPLOYMENT_GUIDE (2).md` (لم يُنسخ إلى المشروع لأنه يحتوي
بيانات حساسة). أضيف `deploy.cmd` للتشغيل بالنقر و`deploy.ps1` كمنفذ النشر الكامل.
- **المسار المحلي:** يفحص SSH أولاً، يعرض تغييرات Git، ثم يشغل اختبارات Django كاملة
  و`makemigrations --check` و`manage.py check`، ويبني Vite بـAPI الإنتاج. `-SkipTests`
  متاح للطوارئ فقط و`-DryRun` يبني ويدقق الحزمة بلا اتصال أو رفع.
- **حزمة مقيدة ومدققة:** تضم تطبيقات Django و`frontend_v2` المصدرية و`dist` المبني فقط؛
  تستبعد وتفحص `.env` والمفاتيح و`node_modules` و`dist` المصدرية والكاش وقواعد البيانات
  والأرشيفات. الرفع يتم كحزمة واحدة عبر OpenSSH (`scp` ثم `ssh`) دون تخزين كلمة مرور.
- **المسار البعيد:** يرفض أي Python أقل من 3.12 (Django 6)، ويتطلب `rsync/mysqldump/curl`،
  ويقرأ مفتاح Django من `.env` داخل ذاكرة العملية دون طباعته. قبل التعديل ينشئ نسخاً من
  كود الباك، ملفات الواجهة، وقاعدة MySQL؛ ثم مزامنة دقيقة مع حماية `.env/venv/media/static`
  ومجلد subdomain والـ`.htaccess`، يليها requirements/check/migrate/collectstatic وإعادة
  Gunicorn وفحص الصحة داخلياً وعبر النطاقين. عند الفشل يرجع الكود والواجهة تلقائياً ويحتفظ
  بنسخة قاعدة البيانات (لا يعكس migrations آلياً كي لا يمسح كتابات حية). يحتفظ بآخر 5 نسخ.
- **إعداد الاتصال:** الافتراضي `smartktra@smart.ktragroup.com:22` وقابل للتغيير عبر
  `KTRA_DEPLOY_HOST/USER/PORT/KEY/HOME` أو معاملات PowerShell. النطاقان حالياً `200 OK`،
  لكن SSH على 22 والمنافذ الشائعة المفحوصة مغلق من هذه الشبكة؛ لذلك النشر الحقيقي محجوب
  بأمان حتى تزويد SSH host/port الصحيح أو تفعيل SSH في cPanel. يوجد أيضاً تعارض في الدليل
  (`Python 3.10`) مع متطلب المشروع (`Django 6` → Python 3.12+) وسيكشفه الناشر قبل التعديل.
- **تحقّق:** PowerShell parser ناجح · Bash `-n` ناجح · `DryRun -SkipTests` نجح وبنى Vite
  ودقق SHA-256 للحزمة بلا رفع · اختبار الحارس الحقيقي توقف قبل أي mutation عند SSH المغلق ·
  `git diff --check` نظيف.

## [EPIC — Staff Work Order (W1–W11) — الخطة معتمدة من المالك, 2026-07-13]
أمر عمل من 11 بنداً (إعدادات/تهيئة/إدارة منصّة/مراجيع/UX مخزون/تقارير/إصلاح خطأ/أداء).
معالم M1–M8 ببوابة موافقة بعد كل معلم. قرارات المالك المعتمدة:
- **W1 (Q1):** الحارس على مستوى **السطر** + **عند الحفظ**، لكن يُضاف **مفتاح إعدادات**
  يسمح بحفظ فاتورة بخسارة (تجاوز الحارس). — يُنفَّذ في M2.
- **W7b (Q2 — أُعيد توصيفه):** الشكوى الحقيقية = **تعذّر تعديل المورد من صفحة الموردين**
  (لا علاقة بمورد المرجع). أُصلح في M1 (انظر أدناه). مورد المرجع يبقى موروثاً للقراءة (M3).
- **W8 (Q3):** نافذة المعدّل: شهري = 90ي÷3، أسبوعي = 28ي÷4، المرتجعات مخصومة. — M5.
- **W3 (Q4):** مدير المنصّة = **علم منصّة صريح** (لا `is_superuser` وحده). — M8.
- **W2 (Q5):** مستخدمو KTRA الحاليون يبقون كما هم؛ التغيير للتسجيل الجديد فقط. — M8.

### [DONE — M1: أخطاء ومكاسب سريعة (W10 · W4 · W7c · تعديل المورد), 2026-07-13]
كلها جراحية، بلا هجرات (لا تغيير موديل). الأسباب الجذرية مؤكَّدة من الكود:
- **W10 (اسم الصنف غير قابل للتعديل) — جذر واجهي:** حقل الاسم في `ItemFormAseel` كان
  **منتقياً `<select>` (ValuePicker)** لا يُكتب فيه، وزر «+» يمسح القيمة ⇒ يبدو «غير قابل
  للتعديل». الآن: صنف موجود (`productId != null`) ⇒ **حقل نصّي مباشر**؛ الجديد يبقى منتقياً
  (اختر موجوداً/أضف). الخادم كان سليماً (`name_ar` ليس read_only). حارس خادمي جديد
  `ProductApiTest.test_patch_updates_name_ar` (PATCH يحدّث الاسم) يمنع انحدار read_only مستقبلاً.
- **W4 (إجمالي الكمية):** صف «إجمالي الكمية» (مجموع كميات البنود، عبر `formatQuantity` G1)
  بجانب الإجماليات المالية في محرّري البيع (`SalesInvoiceEditor`) والشراء (`InvoiceForm`،
  كِلا كتلتي الإجمالي المحلي/الدولي) وطباعتَيهما (`SalesInvoicePrintView`, `InvoicePrintView`).
- **W7c (صورة المرفق لا تظهر على فاتورة/مرجع الشراء) — جذر مزدوج (حفظ + قراءة مفقودان):**
  `AttachmentsSection` المشترك يرفع الصور إلى Cloudinary ويكتبها في `formData.quote_images`،
  لكن فاتورة الشراء **لم يكن لها أي مسار حفظ خادمي** (لا SystemAttachment) **ولا عرض** في
  السيريالايزر (المكوّن بُني للصفقات/العروض وأُعيد استخدامه بلا ربط خلفي). الحل مرآةً لنمط
  الموردين/المنتجات: (أ) `PurchaseInvoiceViewSet._sync_attachments` يكتب الروابط في
  `SystemAttachment(related_table='purchase_invoices')` idempotent (إضافة فقط) في
  perform_create/update، غير حاجب؛ (ب) `read_document_images/_pdfs` (مشتركان في
  `logistics/serializers.py`) + حقلا `quote_images`/`quote_pdfs` على `PurchaseInvoiceSerializer`؛
  (ج) الواجهة: `purchaseInvoiceApi` DTO يرسل `quote_images/quote_pdfs`،
  `mapPurchaseInvoiceDtoToInvoice` يعيدها إلى `quoteImages/quotePdfs`. اختبار جديد
  `test_purchase_invoice_attachments.py` (4، بتمويه SystemAttachment managed=False).
- **تعديل المورد (W7b معاد التوصيف) — جذر واجهي:** `SupplierManagement` كان يفتح
  `SupplierModal` **للإضافة فقط** (`showAddModal`) ولا يمرّر `editingSupplier` أبداً؛
  الاسم/النقر المزدوج يفتحان بطاقة العرض (`/partners/{id}`) ⇒ لا مسار تعديل إطلاقاً. الآن:
  عمود «تعديل» (قلم) يجلب المورد (`suppliersService.getSupplierById`) ويفتح المودال في وضع
  التعديل (المودال يدعم `editingSupplier`/`updateSupplierInDb` أصلاً).
- **تحقّق:** الحزمة الخلفية **270 اختباراً** (+5 جديدة تمرّ: 4 مرفقات + 1 اسم الصنف) ·
  `makemigrations --check` = No changes · `check` = 0 · `tsc` = خطأ DepartmentCard السابق فقط ·
  `vite build` ناجح. **تنبيه (خارج M1):** 5 أخطاء **سابقة** في
  `test_landed_cost.T1_01_DoubleLocalTransportCapitalizationTest` — من عمل إعادة بناء
  الاستيراد غير المُلتزَم (`landed_cost.py` +220 سطر uncommitted؛
  `clearance_local_transport_superseded_by_localshipment` يقرأ `clearance.shipment_id` على
  `SimpleNamespace` بلا الحقل). داخل عمل النقل الداخلي المحجوب بموافقة المالك — **لم تُلمَس**.

### [DONE — M2: W1 حارس فاتورة الخسارة على مستوى السطر + عند الحفظ, 2026-07-13]
جراحي، بلا هجرة (لا حقل جديد — يعيد استخدام `SalesSettings.block_loss_invoices`).
- **من إجمالي الفاتورة → السطر:** حُذف `invoice_gross_profit`+`_guard_loss_invoice`
  (فحص إجمالي) وحلّ محلّهما `_loss_lines`+`guard_loss_invoice` (`sales/services.py`): يُرفض
  إن كان **أي سطر** صافي إيراده < تكلفته حتى لو كانت الفاتورة رابحة إجمالاً.
- **صافي إيراد السطر = `line.line_total_excl_tax`** (بعد خصم السطر + توزيع خصم الفاتورة
  والنسبة، وتعديل شامل الضريبة) — نفس أساس `invoice_profits` وقيد COGS. التكلفة = كمية ×
  `avg_cost` (WAC، مصدر حقيقة واحد). الرسالة عربية تسمّي الأسطر المخالفة.
- **عند الحفظ لا الترحيل فقط:** `guard_loss_invoice` يُستدعى في `SalesInvoiceSerializer`
  `create` (كلا مساري atomic) و`update` (لُفّ بـ `transaction.atomic()` فيتراجع الحفظ عند
  الرفض — «لا تُحفظ مسودة بخسارة») بعد `recalculate_invoice_amounts`، + يبقى في
  `post_sales_invoice`. `select_related('product')` أُضيف لمسارات الحفظ (لا N+1 للتكلفة).
- **مفتاح «السماح بحفظ فاتورة بخسارة» (Q1):** هو `block_loss_invoices` نفسه — الخيار في
  `SalesSettingsPage` أصلاً «السماح بالحفظ (افتراضي)» ↔ «منع الحفظ والترحيل»؛ التسمية صارت
  دقيقة الآن (المنع يشمل الحفظ فعلاً). لا إعداد/هجرة جديدة.
- **المراجيع مُعفاة** (invoice_kind ≠ sale). مرآة الواجهة `SalesInvoiceEditor.lossBlockMessage`
  صارت على مستوى السطر (`totals.perLine[i].lineNetAdjusted` مقابل كمية×avg_cost) وتسمّي الأسطر.
- **تحقّق:** `test_block_loss_invoice.py` **6** (3 قائمة post-time + 3 جديدة: رفض فاتورة رابحة
  بها سطر خاسر عند الحفظ+المفتاح مفعّل مع تأكيد التراجع · حفظها عند الإطفاء · المرجع مُعفى) ·
  الحزمة الكاملة 270 (unittest) خضراء · `makemigrations --check` = No changes · `check` 0 ·
  `tsc` = خطأ DepartmentCard السابق فقط · `vite build` ناجح.

### [DONE — M3: مرتجع الشراء — منتقي البنود + هوية المستند + المورد الموروث, 2026-07-14]
جراحي، بلا هجرة (لا حقل موديل جديد).
- **W6 حارس تجاوز الكمية (خادمي):** `create_purchase_return` يرفض إن تجاوزت الكمية المرتجعة
  المتبقّي القابل للإرجاع لكل صنف = المفوتر − مجموع كل المراجيع السابقة لنفس الفاتورة الأصلية
  (داخل `transaction.atomic`). دالة مشتركة `returnable_lines_for_invoice` (مصدر حقيقة واحد)
  + نقطة `GET purchase-invoices/{id}/returnable-lines/` تُرجع (المفوتر/المرتجع/المتبقّي).
- **W6 منتقي البنود (واجهة):** `PurchaseReturnEditor` لم يعد ينسخ كل الأسطر تلقائياً — اختيار
  الفاتورة الأصلية يفتح مودالاً يعرض لكل بند (المفوتر · المرتجع · المتبقّي) بخانة اختيار وحقل
  «كمية الإرجاع» (افتراضي=المتبقّي، مقيّد به، البنود المستنفدة معطّلة). البنود المختارة فقط
  تدخل المرجع — انتهى «كل شيء يظهر وأجلس أحذف صفوفاً».
- **W7b المورد موروث (واجهة):** حقل المورد صار للقراءة فقط يُورَّث من الفاتورة الأصلية (قيد
  العكس يجب أن يصيب نفس حساب ذمم المورد) مع تلميح توضيحي — لا حقل ميت. (شكوى المالك الحقيقية
  «تعديل المورد» كانت في صفحة الموردين وحُلّت في M1.)
- **W7a هوية مستند المرجع (واجهة):** `PurchaseInvoiceSerializer` يكشف `original_invoice_number`؛
  `mapPurchaseInvoiceDtoToInvoice` يمرّر `isReturn`/`originalInvoiceId`/`originalInvoiceNumber`؛
  و`InvoiceForm` عند فتح مرجع يعرض عنوان «مرجع شراء»، شارة حمراء «مرجع شراء ↩»، ورابط «الفاتورة
  الأصلية #» + لغة معكوسة — بدل ظهوره كفاتورة شراء عادية.
- **تنظيف:** أُزيل `partners` اليتيم من `PurchaseReturnEditor` (لم يعد يُستخدم بعد جعل المورد موروثاً).
- **تحقّق:** `test_purchase_return_posting.py` **6** (+3 حارس التجاوز/التراكم + منتقي البنود) ·
  الحزمة 270 خضراء · `makemigrations --check` = No changes · `check` 0 · `tsc` = DepartmentCard فقط ·
  `vite build` ناجح.

### [DONE — M4: W11 أداء — N+1 موثّقان + مُقاسان بعدّ الاستعلامات, 2026-07-14]
جراحي، بلا هجرة. **القياس:** التوقيت الحيّ على الإنتاج متعذّر من هذه البيئة (خادم بعيد خلف
دخول) — فالدليل هو **عدد استعلامات SQL** (اختبار تراجع)، والتغييرات كلها بلا تغيير سلوك.
- **N+1 ملخّص مرجع القيد (`build_journal_reference_summary`):** كان كل صف
  SALES_INVOICE/CUSTOMER_PAYMENT يُطلق استعلاماً مفرداً ⇒ صفحة 100 قيد = حتى 100 استعلام
  زائد. الآن `JournalViewSet.list` يبني `sales_map`/`cust_map` من صفوف الصفحة (نفس نمط
  `pay_map` القائم) ويُمرّرها بالـcontext؛ الدالة تقرأ من الـmap وتسقط لاستعلام مفرد فقط عند
  الاستهلاك المفرد (توافق خلفي). اختبار `test_journal_reference_perf.py`: عدد الاستعلامات
  **ثابت** (2 قيد ↔ 6 قيود) بدل أن يزيد بمقدار N.
- **`LogisticsPaymentViewSet.get_queryset`:** أُضيف `select_related('journal')` (كان
  `journal_id_display` يُطلق استعلاماً لكل صف مرحّل).
- **مؤجَّل عمداً (يحتاج قياس إنتاج + خطر ارتداد مالي):** ترقيم قوائم فواتير المبيعات/الشركاء/
  الصفقات/فواتير الشراء — بحثها client-side، فالترقيم قبل إضافة `search`/`date_from`/`date_to`
  خادمياً = اختفاء فواتير قديمة من البحث. لا يُنفَّذ بلا دليل أنه عنق الزجاجة الفعلي (بروتوكول
  «قِس أولاً»).
- **تحقّق:** 271 اختباراً خضراء (+1) · `makemigrations --check` = No changes · `vite build` ناجح.

### [DONE — M5: W8 أعمدة الأصناف + معدّلات البيع (منقّطة، بلا N+1), 2026-07-14]
جراحي، بلا هجرة. المصدر الوحيد = `StockMovement`.
- **تعريفات النوافذ (موثّقة):** المشتريات = الوارد التراكمي (كل حركات `IN`). متوسط البيع
  الشهري = صافي (`OUT` − `RETURN_IN`) خلال آخر **90 يوماً ÷ 3**. الأسبوعي (البطاقة) = صافي
  خلال **28 يوماً ÷ 4**. المرتجعات مخصومة.
- **الجدول (`ProductViewSet.get_queryset`):** تجميعات **منقّطة** (`Coalesce(Sum(..., filter=Q))`)
  — `purchased_qty`/`sold_qty_90d`/`returned_qty_90d` بجوين واحد، لا N+1. `ProductSerializer`
  يكشف `purchased_qty` ويحسب `avg_monthly_sales`=(sold−returned)/3. أعمدة `ItemsManagement`
  أُعيد ترتيبها: الكمية المشتراة → الكمية المتبقية → اسم الصنف (المثبَّت) → متوسط البيع الشهري
  → (رقم الصنف/التكلفة/الحد/الحالة/تعديل). تلميحات تشرح كل عمود.
- **البطاقة (`product_profile`):** أُضيف `avg_weekly_sales` و`avg_monthly_sales` (نفس مصدر
  الجدول) + مؤشّران في `ProductProfilePage`.
- **تحقّق:** `test_item_aggregates.py` **3** (الوارد التراكمي · الشهري بعد المرتجعات مع
  استبعاد ما قبل 90ي · الأسبوعي 28ي) · 274 خضراء · `makemigrations --check` = No changes ·
  `tsc` = DepartmentCard فقط · `vite build` ناجح.

### [DONE — جراحة UX رحلة الاستيراد: فصل الاستحقاق عن الدفع + رسوم الفاتورة الدولية, 2026-07-14]
تنفيذ جراحي لمسار الشحنة نفسه (`ImportDocumentScreen`) مع فصل محاسبي صريح، وهجرة إضافة
نظيفة فقط (`logistics/0054_localshipmentpayment.py`).
- **التخليص — قيدان مستقلان:** `POST clearances/{id}/post-to-accounting/` يثبت الاستحقاق
  (مدين حساب البند 1105/5302/5303/5306/5307 أو الحساب الصريح، دائن ذمم المخلّص) ويخزّن
  قيده في `LogisticsClearance.journal`. `pay_from_cashbox` يبقى قيد الدفع المستقل (مدين
  ذمم المخلّص/دائن الصندوق). الدفعة وحدها لم تعد تقفل تحرير مستند التخليص؛ الحذف يبقى
  محروساً عند وجود أي قيد. أضيف `unpost-accrual` للتراجع عن الاستحقاق وحده.
- **النقل المحلي — استحقاق ثم دفع:** ترحيل `LocalShipment` صار دائماً مدين تكلفة النقل/
  دائن ذمم الناقل حتى لو كانت نية التسوية نقدية. النموذج الجديد `LocalShipmentPayment`
  يسجل دفعات جزئية/كاملة بقيد مستقل `LOCAL_SHIPMENT_PAYMENT` (مدين الناقل/دائن الصندوق)،
  مع `amount_paid`/`remaining_balance`/`payment_status` وقائمة الدفعات وحارس تجاوز المتبقي.
- **UX داخل رحلة الاستيراد:** أزرار واضحة «إثبات استحقاق التخليص»، «تسجيل دفعة للمخلّص»،
  «إثبات الاستحقاق» و«تسجيل دفعة» للناقل في نفس السطر؛ بطاقات إجمالي/مدفوع/متبقي؛ تعبئة
  المتبقي تلقائياً؛ النجاح يبقي المستخدم في رحلة الاستيراد ولا يرسله إلى القيود. خريطة
  المسار توضّح أن دفع التخليص والنقل المحلي **ليس شرطاً** لإنشاء الفاتورة الدولية.
- **الفاتورة الدولية — ضرائب ورسوم إضافية مهيكلة:** تبويب جديد في `InvoiceForm` لبنود
  `PurchaseInvoiceFee` (بيان، مبلغ، حساب Expense/Asset، رسملة اختيارية) مع إجمالي أساسي/
  مجموع الرسوم/إجمالي مستحق. الواجهة تحفظ `fees` في REST وتعيد تحميلها؛ السيريالايزر يكشف
  `fees_total` و`payable_total` ويحسب المتبقي على الإجمالي الحقيقي. صُحح ترحيل الرسوم بحيث
  تُضاف فوق `grand_total` ويظل القيد متوازناً (المرسمل للمخزون، وغيره لحساب الرسم).
- **عدم اشتراط الدفع:** اختبار صريح يثبت نجاح `import-from-clearance` مع تخليص ونقل محلي
  غير مدفوعين؛ شرط دفع الشحن الدولي/الصفقة القائم لم يتغير.
- **Logging:** نجاح إثبات استحقاق التخليص، دفع المخلّص، إثبات النقل، ودفع الناقل مسجل عبر
  logger؛ وأُصلح استدعاء `create_audit_log` القديم في ترحيل النقل (كان يمرر أسماء معاملات
  غير موجودة فيفشل الترحيل بعد إنشاء القيد ثم يتراجع ذرّياً).
- **TDD/تحقّق:** `test_import_payment_separation.py` **6** + توسيع `test_clearance_import.py`
  (عدم اشتراط الدفع)؛ الحزمة الكاملة **281/281** خضراء · `makemigrations --check --dry-run`
  = No changes · `manage.py check` = 0 · `vite build` ناجح. `tsc --noEmit` يتوقف فقط عند
  خطأ **سابق** في `components/DepartmentCard.tsx` (مسار `../../services/firestoreService`).

### [DONE — تبسيط UX رحلة الاستيراد ولوحة الخطوة التالية, 2026-07-14]
- **لوحة قيادة سياقية:** أضيفت دالة نقية `getImportJourneyGuidance` تحدد إجراءً تالياً واحداً
  من حفظ الشحنة حتى فتح الفاتورة، مع بطاقة بارزة تلخص الشحن الدولي والتخليص وتوضح أن النقل
  المحلي اختياري. الشريط القديم صار مؤشراً مختصراً، ومسار الميناء التفصيلي صار قابلاً للفتح.
- **تقليل الحمل المعرفي:** اختُصرت تبويبات الرحلة من **9 إلى 6**؛ دُمجت حسابات وحركات الشحنة
  والتخليص في «السجل المالي»، وحُذف تبويب المرفقات غير المنفذ. الروابط القديمة للتبويبات
  المحاسبية تُحوّل تلقائياً إلى التبويب الموحد حفاظاً على التوافق.
- **إفصاح تدريجي:** بيانات الشحنة والتخليص والنقل المحلي تعرض الحقول اليومية أولاً، وتخفي
  الحقول النادرة وتفصيل رسوم التخليص خلف أزرار واضحة. جدول النقل يعرض المبلغ/المدفوع/المتبقي
  بدلاً من حشر بيانات السائق والمركبة، مع بقائها في نموذج التفاصيل.
- **وضوح الدفع والفاتورة:** نموذج دفعة المخلّص لم يعد يعرض مسار «دفعة ناقل قديمة»؛ زر الفاتورة
  موحّد بلا تكرار ولا يتاح قبل اكتمال تكلفة ودفع الشحن الدولي ووجود تكلفة تخليص، بينما لا يشترط
  دفع التخليص أو النقل المحلي. الشحنة من نوع «نقل فقط» تتجه للنقل المحلي ولا تقترح فاتورة.
- **TDD/تحقّق:** `import-journey-guidance.spec.ts` **4/4** خضراء · `vite build` ناجح ·
  `git diff --check` نظيف. `tsc --noEmit` ما زال يتوقف فقط عند خطأ `DepartmentCard.tsx`
  السابق نفسه.

## [FIX — Clearance Tab Layout & Agent Selection, 2026-07-13]
- **UI Alignment Fix**: Wrapped the clearance form's input groups in a container with `className="aseel-headband"`. This allows individual inputs wrapped with `className="aseel-field"` (via the `fld` helper) to flex and align correctly per the new design system, preventing layout overflow.
- **State Binding Correction**: Modified the `customs_broker` state binding in the `select` element to correctly handle literal `"null"` strings, preventing the dropdown from rendering a broken `null#` option. The `onChange` handler was also updated to reject `"null"` as a valid broker ID. The read-only field also now correctly falls back to `"—"` when `customs_broker` evaluates to the string `"null"`.
- **UX & Auto-Save Fix**: Converted the `readOnly` Customs Broker field in the Shipment Header to a functional dropdown matching the one in the Clearance tab. Both dropdowns (Header and Tab 4) now immediately dispatch `handleSaveClearance()` onChange to auto-save the broker selection. This prevents a critical bug where users could select a broker locally, switch to the Payments tab, and fail to record a payment ("لم يتم تحديد المخلص الجمركي") because they forgot to manually click "تخزين التخليص" to commit the selection.
- **Local Transport Creation Fix**: Fixed a bug where creating a Local Transport entry failed silently or threw an opaque "This field is required" error because the frontend's API payload (`createLocalShipment` / `updateLocalShipment`) failed to include the `currency` and `exchange_rate` fields, which are strictly required by the Django model `LocalShipment.currency`. Added `currency: localForm.currency || 1` and `exchange_rate` to the payload explicitly.
- **Strict Invoice Conversion (No Unpaid USD)**: Removed the "Remaining Exchange Rate" inputs from the `ClearanceImportModal`. Modified the backend (`landed_cost.py`) to explicitly block generating an international invoice if a Deal has any remaining unpaid USD amount. This enforces the business rule that all foreign currency amounts must be definitively settled and paid (yielding an exact ILS cost) before allowing conversion to an invoice.

## [IN PROGRESS — إعادة بناء مسار الاستيراد الشاملة (Deal→Shipment→Clearance→Transport→Invoice), 2026-07-13]


**المالك وافق على الخطة كاملةً + إزالة العناصر الأربعة D1–D4. التنفيذ بالمعالم M0–M7،
هجرة إضافية أولاً (لا حذف قبل إثبات backfill).** المرجع: بروتوكول التخطيط الكامل في الجلسة.

### [TECH_STACK] (مُتحقَّق من الشِل 2026-07-13)
Backend: Python 3.13.5 · Django 6.0.3 · DRF 3.16.1 · mysqlclient 2.2.7 (MySQL إنتاج / SQLite اختبار)
Frontend: React 19.2 · TypeScript 5.8 · Vite 6.2 · Tailwind 4.3 · react-router-dom 7.10
سياسة: إعادة البناء **لا تضيف أي اعتمادية جديدة** (بروتوكول 3 — جراحي). لا APIs مهجورة.

### [SYSTEM_FLOW]
Deal(s) → Shipment(create-from-deals) → Clearance → [Transport] → ImportInvoice (تكلفة وصول ₪)
- التكاليف: شحن(ShipmentDeal، وحدة=CBM|KG) · جمارك(ClearanceLine، بالقيمة) · نقل داخلي(Transport، بالوحدة)
- الحالة: `Deal.stage` (آلة مراحل واحدة، خدمة محروسة) — status/order_status/payment_status ستصبح محسوبة (M3)
- المخرج: تكلفة وصول ₪ لكل بند + تتبّع خلفي كامل، يُرحَّل عبر دورة PurchaseInvoice القائمة
- قرارات المالك: فاتورة/صفقة (Q1) · جمارك بالقيمة (Q2) · إبقاء العملات/الصرف المحقَّق (Q3) · هجرة backfill (Q4)

### [ARCHITECTURE]
`logistics/domain/allocation.py` — محرّك التوزيع الوحيد (Decimal، largest-remainder، يطابق الإجمالي للقرش)
`logistics/domain/stages.py` — انتقالات المراحل المحروسة (بلا تجاوز bulk .update)
`logistics/domain/shipment_builder.py` — create_shipment_from_deals()
`logistics/domain/invoice_gen.py` — بناء/تحديث ImportInvoice من المحرّك (يعيد تصدير landed_cost مؤقتاً؛ يُوحَّد في M5)
`services.py` — استلام/مرجع/AP (بلا تغيير، متعامد)

### حالة المعالم
- **M0 ✅** أعمدة إضافية: `Shipment.chargeable_unit`+`freight_rate`، `Deal.stage` (هجرة 0050) + backfill (0051).
- **M1 ✅** `create_shipment_from_deals` + `POST /shipments/create-from-deals/` + `GET /deals/ready-to-ship/`
  + `CreateShipmentFromDealsModal` بزر «شحنة من الصفقات». يصلح RC-1. `test_shipment_from_deals.py` (12).
- **M2 ✅** محرّك التوزيع الموحّد `domain/allocation.py` (largest-remainder، يطابق للقرش). `chargeable_unit` صريح
  بديل pricing_method×unit_type. `distribute_by_weights` يفوّض للمحرّك. `PATCH /shipments/{id}/freight/`
  (إعادة حساب نظيفة عند تبديل الوحدة) + مبدّل CBM/KG في رحلة الاستيراد. `test_freight_allocation.py` (8).
- **M3 ✅** `Deal.stage` قانوني؛ الأعمدة القديمة (status/order_status/payment_status/shipping_workflow_status)
  كاش مشتق بكاتب واحد. كل الانتقالات الآلية عبر `advance_deal_stage` المحروسة (لا تجاوز bulk .update — RC-7).
  `_reconcile_stage_and_workflow` يبقي الحقلين متسقين من أي مدخل. `test_stage_machine.py` (11). الأعمدة تبقى
  (dashboard_api يفلتر عليها في DB — إسقاطها غير آمن، تحليل P-F-4 مؤكَّد). 252/252 اختبار المشروع كامل.
- **M4 ✅ (جزئي)** حُذف shim `cost_lines` (D2): الخاصية أُزيلت من الموديل؛ `clearance_cost_line_dicts` تقرأ
  `lines` مباشرة؛ السيريالايزر يبني cost_lines في to_representation؛ views/report محدّثة. سلوك محفوظ (invariants خضراء).
  `test_cost_source_m4.py` (3). **مؤجَّل بعلم:** توحيد مصدر النقل الداخلي (Transport فقط + إزالة حارس supersede/
  وسم الملاحظات) يغيّر أرقام تكلفة الوصول — يحتاج تحقّق المالك للأرقام قبل التبديل (لا نغيّر حسابات مالية بصمت).
- **M5 ✅** فاتورة لكل صفقة (قائم) + `GET /purchase-invoices/{id}/trace/` تتبّع خلفي كامل
  (بند→صفقة→شحنة(شحن)→تخليص(جمارك)→نقل) عبر `build_import_trace`. `test_import_trace.py` (2, E2E).
- **M6/M7 ✅ (إزالات آمنة نُفِّذت بتوجيه المالك)** — قرار المالك: نفِّذ الآمن الآن، أبقِ transit_journal، هجرات تُطبَّق بعد فحص المالك:
  - **D3 ✅** `LogisticsExpense` أُزيل بالكامل (models/serializers/signals/urls/views/purge_deals) — هجرة **0052** (DeleteModel).
    **يطبّقها المالك بعد تأكيد صفر صفوف إنتاج.** لا تبعية واجهة/اختبار. 260/260 اختبار المشروع أخضر.
  - **D1 ✅ (الآمن فقط)** أُزيل `supplier_address` + `journal_no_display` (صفر مراجع خارج تعريف الموديل) — هجرة **0053**.
    `transit_journal` **مُبقى** (حامل حمل: حارس الشحنة المرحّلة). باقي حقول Aseel (shipment_type/vat_statement/subtotal/
    vat_total/grand_total/second_date/transaction_time/editable/book_number) مربوطة برحلة الاستيراد → تحتاج تنسيق واجهة (مؤجَّلة).
  - **D4 ✅ (المقدّمة مُحقَّقة سلفاً)** تغذية قائمة الشحنات **REST أصلاً** (`shipmentsService.subscribeToShipments`→`apiGetList("logistics/shipments/")`).
    لا Firestore في تغذية الشحنات (استعمال firestoreService الوحيد في الشاشة = قائمة الموردين المنفصلة). لا هجرة مطلوبة.
  - **النقل الداخلي كمصدر وحيد ✅ (تنفيذ + مصالحة، بانتظار موافقة الأرقام)** — `domain/inland.py`:
    `transport_pool_ils` + توزيع بحصة الوحدة (CBM/KG) بدل حصة القيمة. أمر `reconcile_inland_landed_cost`
    (`--shipment-id`/`--tenant-id` حقيقي للقراءة فقط + `--sample` تجريبي يُرجَع). المسار الحيّ **لم يتغيّر** (مقارنة فقط)
    حتى يوافق المالك على الفروقات. `test_inland_reconcile.py` (3): عيّنة 1000₪ تُعاد توزيعها A(قيمة) 800→200 · B(حجم) 200→800.

### [ORPHANS & PENDING] — إعادة بناء الاستيراد
- **D1** ✅ الحقول الآمنة أُزيلت (0053)؛ باقي حقول Aseel مؤجَّلة لتنسيق واجهة؛ transit_journal مُبقى عمداً
- **D2** ✅ أُزيل (M4)
- **D3** ✅ أُزيل (0052) — **المالك يطبّق الهجرة بعد فحص صفر صفوف الإنتاج**
- **D4** ✅ لا عمل مطلوب (التغذية REST سلفاً)
- **النقل الداخلي مصدر وحيد** — مُنفَّذ كمقارنة؛ قلب المسار الحيّ محجوب بموافقة المالك على مصالحة الأرقام (`reconcile_inland_landed_cost`)
- تسجيل غير حاجب (بروتوكول 4): QueueHandler/QueueListener — يُضاف
- التحقق البصري متعذّر (شاشات خلف الدخول) — الاعتماد على TDD + build

---

## [DONE — مراجعة الاستيراد ج8: إعادة بناء احترافية لمسار صفقة→فاتورة دولية, 2026-07-12 ✅]
**المالك وافق (Q2+Q3 نعم؛ Q1: لا يوجد «شحن تقديري» — بل «شحن داخل الصين» جزء من
الصفقة يُدفع للمورد، والشحن الدولي في الشحنة). نُفِّذت M1–M5 كاملةً.**

- **M1 (خادم — الدفعة مورد مستقل):** `POST /deals/{id}/payments/` (معرّف حقيقي فوراً)
  + `PATCH /deals/{id}/payments/{pid}/` (توثيقي دائماً؛ المبلغ/الصرف مقفلان بعد
  الترحيل). `payments` صارت `read_only` في `LogisticsDealSerializer` (حُذف منطق
  الكتابة المتداخلة + `_payments_total_exceeds_deal`/`_payment_amounts_unchanged_for_deal`).
  `perform_update` لم يعد يحجب أي PATCH بـ POSTED_DOC_WARNING — الحماية الوحيدة:
  أرضية الإجمالي (≥ مجموع المرحّل). TDD: `test_deal_payment_endpoints.py` (12
  اختبار يغطّي شكوى المالك حرفياً) + عُدّل `StageChangeWithPostedPaymentTest`.
- **M2 (واجهة — جراحة dealsService):** addPayment/updatePaymentWithSwift/
  confirmPayment/cancelPayment تخاطب الـendpoints مباشرة عبر
  `mapSinglePaymentToSqlPayload`. حُذف `_updateDealWithPayments` +
  `resolvePaymentIdForApi` + `sameDealPaymentId` + tmp-ids + dedupe/assert imports.
- **M3 (تبويب دفعات واحد):** `paymentsTab` صار سطحاً متدرّجاً — PaymentProgress
  (مسار القسط) أساسي، وInstallmentManager + DealPaymentList داخل `<details>` قابلة
  للطي (الخطة مفتوحة قبل بدء الدفع، السجل عند وجود دفعات).
- **M4 (بنود/إجماليات):** إجمالي الصفقة = بضاعة − خصم + شحن داخل الصين، **بلا ضريبة**
  (تُدفع بالتخليص) — عُدّل `recalculateTotals`/`calculateGrandTotal` (حُذف
  `calculateTaxAmount`) و`_apply_lines_subtotal_and_grand_total` (خادم). أُعيدت
  تسمية «تكلفة الشحن»→«شحن داخل الصين» + «الأسعار تشمل الشحن داخل الصين».
- **M5 (رحلة واحدة):** زر «الخطوة التالية» في `DealStageControl` (adaptive):
  بلا شحنة → `/import-flow/new?tab=deals&join_deal={id}`؛ مع شحنة → قفزة لتبويب
  التخليص/الصفقات. `ImportDocumentScreen` يقرأ `join_deal` فيفتح فاتح ضمّ الصفقات
  تلقائياً (بلا ربط صامت).
- **تحقق:** الحزمة الخلفية الكاملة **223/223** · `makemigrations --check` = No changes ·
  `check` 0 · tsc خطأ واحد فقط (يتيم Department.tsx سابق — مُبلَّغ كمهمة منفصلة) ·
  `vite build` ناجح. التحقق البصري متعذّر (الشاشات خلف الدخول بلا اعتمادات اختبار)،
  لكن TDD يعيد إنتاج سيناريو الفشل الحرفي على مستوى الـAPI.

## [SUPERSEDED PLAN — مراجعة الاستيراد ج8 (الخطة الأصلية قبل التنفيذ)]

**شكوى المالك (المحاولة الرابعة تفشل):** «دفعت الدفعة الأولى وجيت أأكدها → "هذا المستند
مرحَّل"، وما عاد أقدر أساوي شي بالصفقة» + «البنود مش مناسبة لصفقة — الشحن يُحسب آخر شي
لحال ورسوم الصفقة كذلك» + يريد رحلة واحدة واضحة بنمط فواتير البيع/الشراء.

### أوديت — الأسباب الجذرية المؤكدة من الكود
1. **(القاتل) كل عمليات الدفع تمر عبر PATCH كامل للصفقة (إرث Firebase):**
   `dealsService.addPayment/updatePaymentWithSwift/confirmPayment` كلها =
   GET صفقة → دمج مصفوفة `payments` client-side → `_updateDealWithPayments` → PATCH
   كامل (`dealsService.ts:623-692,794-883`). والحارس `perform_update`
   (`logistics/views.py:125-134`) يحجب أي PATCH غير stage-only عند وجود **أي** دفعة
   مرحّلة → بعد ترحيل الدفعة الأولى: تأكيد المورد يفشل بـ«هذا المستند مرحَّل»، إضافة
   الدفعة الثانية تفشل، تعديل الملاحظات يفشل، والحفظ الآلي قبل كل عملية دفع
   (`DealForm.tsx:388-397`) يفشل بصمت (catch→console). ج7 (STAGE_ONLY_FIELDS) أعفى
   المراحل فقط — لم يعالج الجذر لأن الدفع ليس endpoint مستقلاً للإنشاء/التحديث.
2. **حالة الدفع تُشتق بثلاثة منطق مختلفة:** `getPaymentStatusFromPayments`
   (DealForm) × `countsAsPaidForProgress` (PaymentProgress) × الخادم
   (`recalculate_deal_payment_status`) — تناقضات عرض حتمية.
3. **أربع واجهات دفع فوق نفس البيانات:** InstallmentManager (503س) + PaymentProgress
   (728س) + DealPaymentList + PaymentRegistration داخل تبويب واحد — تشتيت، وأزرار
   تظهر/تختفي بشروط متقاطعة.
4. **إجمالي الصفقة يخلط بضاعة + شحن تقديري + ضريبة** (`_recalc_deal_totals`،
   `calculateGrandTotal`) وهو نفسه سقف الدفعات للمورد (`posting_cap_check`) — بينما
   الشحن يُدفع للوكيل لاحقاً (دفعات الشحنة) والرسوم/الضريبة بالتخليص = ازدواج تكلفة
   محتمل وتضخيم سقف الدفع للمورد. `fees_percentage` عمود شبه ميت.
5. **hacks هشّة تعويضية للنمط المتداخل:** tmp-ids `payment_${Date.now()}` +
   `resolvePaymentIdForApi` + `dedupeDealPaymentsForPatch` + مطابقة Counter للمبالغ
   في `_payment_amounts_unchanged_for_deal` — كلها تسقط تلقائياً بعد الفصل.

### الخطة (جراحية — نفس الميزات، بلا زحف نطاق، بلا تبعيات جديدة)
- **M1 خادم — الدفعة مورد REST مستقل:** ‏`POST /deals/{id}/payments/` (إنشاء بمعرف
  حقيقي فوراً) + `PATCH /deals/{id}/payments/{pid}/` (حقول توثيقية دائماً — سليب/تأكيد
  مورد/ملاحظات؛ المالية فقط لغير المرحّلة). `payments` في DealSerializer تصبح
  **قراءة فقط**. حارس `perform_update` يُستبدل: الصفقة ليست مستنداً مرحّلاً —
  الرسالة تختفي نهائياً من الصفقات؛ الحماية المالية = سقف
  (total_amount ≥ مجموع المرحّل) + قفل مبلغ الدفعة المرحّلة نفسها.
  TDD: تأكيد-بعد-ترحيل، دفعة-ثانية-بعد-ترحيل، تعديل-وصفي-بعد-ترحيل،
  تخفيض-الإجمالي-دون-المرحّل يُرفض.
- **M2 واجهة — جراحة dealsService:** العمليات الأربع تستدعي endpoints مباشرة؛ حذف
  `_updateDealWithPayments` والحفظ-الآلي-قبل-العملية وtmp-id hacks.
- **M3 واجهة — تبويب دفعات واحد:** دمج المكونات الأربعة في مكوّن واحد: جدول أقساط
  (الخطة) وتحت كل قسط مساره الوحيد: مطالبة → تنفيذ دفع (صندوق+سليب) → تأكيد مورد →
  قيد (رقم القيد ظاهر). حالة الدفع من الخادم حصراً.
- **M4 بنود/إجماليات (بعد رد المالك):** الصفقة = بضاعة فقط (بنود + خصم = المستحق
  للمورد وسقف دفعاته)؛ الشحن التقديري معلوماتي خارج الإجمالي (إلا «الأسعار تشمل
  الشحن»)؛ الضريبة تُخفى للصفقة الدولية (تُدفع بالتخليص).
- **M5 رحلة واحدة:** زر «الخطوة التالية» في خريطة مسار ج7 لكل مرحلة (إنشاء/فتح شحنة ←
  تخليص ← تحويل لفاتورة دولية) — الشاشات موجودة، الربط فقط. تحقق نهائي: e2e يدوي
  صفقة→دفعات→شحنة→تخليص→فاتورة دولية دون أي «مستند مرحّل».
- **Logging:** يبقى `log_activity`/EntityActivityLog + logger «logistics.payments»
  لمسارات الترحيل/الرفض — لا بنية جديدة.
- **إصدارات (2026-07-12):** Django 6.0.1 مثبتة (سلسلتها الحالية 6.0.7 — ترقية patch
  اختيارية آمنة)، DRF 3.16.1 مدعومة (3.17.1 متاحة — ليست شرطاً)، React 19.2/Vite 6.2/
  TS 5.8/Tailwind 4.3 حديثة. **صفر تبعيات جديدة.**

### أسئلة معلّقة للمالك (يُرد عليها مع الموافقة)
Q1: تأكيد أن الشحن التقديري يخرج من «مبلغ الصفقة» وسقف دفعات المورد؟ ‏Q2: إخفاء حقول
الضريبة في الصفقة الدولية؟ ‏Q3: اعتماد مبدأ «الصفقة لا تُرحّل — الدفعات فقط» نهائياً؟

## [FIX — مراجعة الاستيراد ج7: فصل الدفع عن المراحل + إصلاح قفل «تم الشحن» + شحنة جديدة + وكيل/مخلص, 2026-07-11]
شكوى المالك (فشل تجربة صفقة→فاتورة دولية للمرة الثالثة): اختيار «تم الشحن للوكيل» يخفي
الخريطة والإلغاء ويقفل كل شيء · دفعة مرحّلة تمنع تغيير وضع الشحن («شو دخل الدفع بوضع
الشحنة؟») · شحنة جديدة «كل شي فيها طافي» · لا سبيل لإضافة وكيل شحن أو مخلص · يريد
البنود والدفع بنمط الفواتير وخريطة مسار كاملة داخل الصفقة. **خمسة أسباب جذرية:**
1. **(قفل «تم الشحن» الكارثي):** الخادم يشتق دورة الحياة `Shipped` من مراحل الوكيل
   (`_STATUS_FROM_WORKFLOW`) والواجهة كانت تعامل `status==='shipped'` كحالة **نهائية**:
   `DealStageControl` يستبدل كل شيء ببطاقة «مكتملة» و`DealForm` يعطّل كل حقوله (31 موضعاً).
   الحل: `isDealLocked` = ملغاة أو `sw_released` أو (مغلقة قديمة بلا workflow) — «تم
   الشحن/التخليص» مراحل حية قابلة للعمل. أيضاً `mapStatusFromSql`: «Cleared» كانت
   تُحسب completed (تقفل عند التخليص!) — صارت ضمن المسار الحي.
2. **(فصل الدفع عن المرحلة):** `LogisticsDealViewSet.perform_update` كان يحجب **أي**
   PATCH عند وجود دفعة مرحّلة. الآن `STAGE_ONLY_FIELDS={shipping_workflow_status,status}`:
   طلب يقتصر عليها يمرّ (تغيير مرحلة/إلغاء لا يمسّ القيود)، والتعديلات المالية/البيانية
   والحذف يبقيان محجوبين. TDD: ‏4 اختبارات `StageChangeWithPostedPaymentTest`.
3. **(زر تخزين الشحنة الجديدة «طافي» دائماً):** `isShipmentDirty` في `ImportDocumentScreen`
   كان يعيد false عند غياب `shipment` المحفوظة ⇒ على `/import-flow/new` الزر معطّل إلى
   الأبد ولا يمكن الحفظ ولا ضمّ الصفقات. الآن: شحنة جديدة = dirty دائماً (والتحذير قبل
   المغادرة صار للسجلات المحفوظة فقط).
4. **(وكيل الشحن والمخلِّص كانا readOnly بلا أي مسار إنشاء):** «وكيل الشحن» في رأس
   الشحنة و«المخلِّص» في تبويب التخليص صارا **قائمتي اختيار** من الشركاء (فلترة
   FreightForwarder/CustomsBroker من قائمة carriers القائمة — تُحمَّل عند فتح الشاشة)
   + زر «+» يفتح مودال إنشاء سريع (`POST partners/` بالاسم والنوع) ويختار الجديد فوراً.
5. **(خريطة مسار موحّدة داخل الصفقة):** `DealStageControl` أعيدت كتابته: شارتان
   مستقلتان (الدفع مالي × المرحلة تشغيلي) + خريطة عمودية بالمسار الكامل المطلوب حرفياً:
   بدء التصنيع ← تم التصنيع/بانتظار الشحن للوكيل ← تم الشحن للوكيل ← الشحن الدولي ←
   التخليص ← (النقل المحلي اختياري) ← محوّلة إلى فاتورة. الثلاث الأولى **أزرار نقر
   مباشرة** (بدل select)، التالية تلقائية بتلميح مصدرها، وزر الإلغاء متاح في كل
   المراحل عبر `useConfirm` (أغلق window.confirm المتبقي — task33). أُضيف
   `linked_shipment` لـ`LogisticsDealSerializer` (prefetch-aware عبر
   `logisticsshipmentdeal_set` + Prefetch في الـviewset — لا N+1) فيعرض الصفقةُ
   شحنتَها وزر «فتح رحلة الاستيراد».
- **(بنود بنمط الفواتير):** جدول بنود الصفقة كان أصلاً AseelGrid + autocomplete بأسعار
  (task13/24) لكنه كان يبدو «قديماً» لأنه مقفول بخطأ (1). أُضيف: صف جاهز فوراً في
  الصفقة الجديدة + تصفية الصفوف الفارغة عند الحفظ/التحقق (`nonEmptyItems`).
- الملفات: `logistics/views.py` (حارس المرحلة + prefetch) · `logistics/serializers.py`
  (`linked_shipment`) · `DealStageControl.tsx` (إعادة كتابة) · `DealForm.tsx`
  (`isDealLocked` + صف جاهز) · `dealsService.ts` (mapStatusFromSql + linkedShipment) ·
  `types/deal.ts` · `ImportDocumentScreen.tsx` (dirty الجديدة + قائمتا وكيل/مخلص +
  مودال إنشاء سريع).
- تحقق: **الحزمة الخلفية الكاملة 211/211** (+4 TDD) · tsc = خطأ DepartmentCard السابق
  فقط · vite build ناجح. (الشاشات خلف الدخول — لا تحقق بصري، مطابقةً للنهج.)
- **ملاحظة معمارية مثبتة:** الدفع بُعد مالي مستقل عن مسار الشحن — أي حارس مستقبلي على
  تعديل الصفقات يجب أن يستثني حقول المرحلة (`STAGE_ONLY_FIELDS`).

## [FIX — صيانة الأداء والموثوقية الشاملة, 2026-07-10]
بلاغ المالك: الموقع بطيء عموماً + مشاكل كاش متكررة + «فقد الاتصال» رغم وجود إنترنت +
طلب واحد قد يستغرق ساعة من قاعدة البيانات. تدقيق كامل (باك-إند + واجهة) بأدلة كود مباشرة،
ثم 10 معالم منفَّذة ومُتحقَّقة. **قيود المالك:** استضافة Shared LiteSpeed بلا root (لا Redis) ·
Zero-downtime إلزامي لكل هجرة.

### الأسباب الجذرية المؤكَّدة (بالكود لا بالتخمين)
- **«التعليق ساعة»:** `DATABASES` بلا `CONN_MAX_AGE` (اتصال TCP جديد كل طلب) وبلا أي
  timeout على عميل MySQL ⇒ اتصال معطوب/قفل بطيء يعلّق الـ worker بلا حد.
- **البطء العام:** ترقيم DRF معطّل كلياً (`DEFAULT_PAGINATION_CLASS: None`) ⇒ دفتر اليومية
  (4254 قيداً في الجرابعه) يُبثّ كاملاً بكل فتح (قيس حياً: **4.8 ثانية / 1.7MB**) + N+1 في
  `JournalHeaderListSerializer` (tenant.CompanyName/currency.Code لكل صف بلا select_related)
  + صفر `CACHES` (الداشبورد ~30 استعلاماً تجميعياً بكل تحميل) + حزمة JS واحدة **3.2MB**.
- **«فقد الاتصال» الوهمي:** حالة الاتصال العالق (SW/QUIC بملف تعريف كروم — مشخّصة في
  AUDIT 2026-07-02) كان علاجها زر «إصلاح الاتصال» **اليدوي** فقط الذي لا يلاحظه المستخدم.
- **اكتشافان أثناء التحقق:** (1) منطق كاش `/api/` في `sw.ts` كان **كوداً ميتاً** — حارس
  same-origin (سطر 50) يستثنيه لأن الـ API نطاق فرعي مختلف؛ (2) فهرس خارجي قديم
  `idx_journal_headers_date (TenantID,TransactionDate)` موجود على MySQL خارج الهجرات —
  لهذا بدت الموديلات بلا فهارس؛ فهارسنا تغطي reference/is_posted غير المغطاة.

### المنفَّذ (باك-إند)
- **M1 موثوقية الاتصال** (`core/settings.py`): `CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS=True`
  + `connect/read/write_timeout` (10/30/30 ث) ⇒ الفشل خلال ثوانٍ بدل التعليق.
- **M2 كاش الخادم**: `FileBasedCache` في `BASE_DIR/django_cache` (مشتركة بين عمليات WSGI،
  بلا root، ضربة كاش = صفر MySQL) + كاش الداشبورد بمفتاح tenant صريح
  (`dashboard:v1:{pk}`, TTL=60ث — **لا** `@cache_page` المفهرس بالـ URL = خطر تسريب بين
  الشركات). قيس حياً: 0.21 ← **0.014 ث**. اختبارات: `DummyCache` في `test_settings`.
- **M3 N+1 القيود** (`accounting/views.py`): `select_related("tenant","currency")`.
- **M4 فهارس القيود** (هجرة `accounting/0026_journal_indexes`): `idx_jh_tenant_date_id` /
  `idx_jh_tenant_ref` / `idx_jh_tenant_posted` / `idx_jl_tenant_account`. الناتج
  `CREATE INDEX` خالص (`sqlmigrate` مُتحقَّق) = InnoDB online DDL بلا قفل (zero-downtime).
- **M5 ترقيم opt-in**: `OptionalPageNumberPagination` انتقل من inventory إلى
  `core/pagination.py` وأصبح `DEFAULT_PAGINATION_CLASS` (page_size=50, max=200) — يُفعَّل
  **فقط** بوجود `?page=` فلا ينكسر أي استهلاك قائم. `JournalViewSet.list()` اليدوي (pay_map)
  أعيد ليحترم `paginate_queryset` وبنى pay_map من صفوف الصفحة فقط. +3 اختبارات عقد
  (`accounting/tests/test_journal_pagination.py`).

### المنفَّذ (واجهة)
- **M6 تفعيل `?page=`**: طبقة مشتركة `apiGetPagedList`/`toPagedList` في `restApi.ts`
  (تتحمّل الشكلين: مصفوفة خام أو غلاف DRF — آمنة أثناء تفاوت النشر؛ كاش أوفلاين للصفحة 1
  فقط) + `getJournalsPaged`/`getStockMovementsPaged`. شاشتا **دفتر اليومية** و**حركة المخزون**
  (فلاترهما خادمية بالفعل) تجلبان دفعات 100 + زر «تحميل المزيد (N من M)». قيس حياً:
  **0.10-0.15 ث / 20KB** بدل 4.8 ث / 1.7MB.
- **M7 حذف كود SW الميت** (`sw.ts`): أزيل فرعا `/api/` (staleWhileRevalidate/networkFirst)
  + `MASTER_DATA_CACHE`/`API_CACHE` (إزالتهما من `CURRENT_CACHES` تجعل activate يمسح أي
  نسخة قديمة عالقة عند المستخدمين) + توثيق سبب حارس same-origin.
- **M8 سقف عمر كاش Dexie** (`restApi.ts`): `readListCache` يرفض ما تجاوز **7 أيام**
  (كان يقدّم بيانات بأي عمر كأنها حديثة عند فشل الشبكة).
- **M9 إصلاح اتصال تلقائي** (`hooks/useAutoConnectionRecovery.ts` + سطران في App.tsx):
  `browserOnline=true` مع فشل نبض `/api/health/` لمدة 45ث (نبضتان) ⇒ `recoverConnection()`
  تلقائياً. حارس `sessionStorage` = مرة لكل نوبة (ينجو من reload، يُعاد تسليحه عند عودة
  الاتصال) ⇒ لا حلقة تحميل. الزر اليدوي في OfflineBanner باقٍ كاحتياط.
- **M10 تقسيم الحزمة** (`App.tsx`): ~71 صفحة تحوّلت `React.lazy` بنمط adapter (بلا لمس أي
  ملف مكوّن) + `<Suspense>` واحد حول `renderMainContent()`. الحزمة الرئيسية
  **3.2MB ← 1.11MB** (gzip 267KB) + 129 chunk عند الطلب — كلها تُسبَق كاشياً في SW
  (precache) فالأوفلاين سليم.

### تحقّق
`manage.py test --settings=core.test_settings` = **198 ناجحاً** (كانت 195) ·
`makemigrations --check` = No changes · `manage.py check` = 0 · `tsc` = خطأ DepartmentCard
السابق فقط · `vite build` ناجح · **قياسات حية على نسخة بيانات الإنتاج** (tenant 3):
قيود مرقّمة 0.099ث (بعد الفهارس) مقابل 4.8ث كاملة · داشبورد warm ‏0.014ث · EXPLAIN
يستخدم فهرس (range) لا Full Scan.

### النشر (يدوي — بالترتيب)
1. باك-إند: `git pull` → `python manage.py sqlmigrate accounting 0026` (تأكيد ADD INDEX فقط)
   → `python manage.py migrate` (ساعة هدوء استحساناً — غير حاجب أصلاً) → فحص كاش:
   `python manage.py shell -c "from django.core.cache import cache; cache.set('x','ok',10); print(cache.get('x'))"`
   → **إعادة تشغيل عملية Python من لوحة الاستضافة** (إلزامي لـ CONN_MAX_AGE/CACHES/الترقيم).
2. مرة واحدة قبل/بعد النشر: `SHOW VARIABLES LIKE 'max_connections'` + `SHOW STATUS LIKE
   'Threads_connected'` للاطمئنان أن CONN_MAX_AGE=60 ضمن سقف الاستضافة المشتركة.
3. واجهة: `npm ci && npm run build` في frontend_v2 → رفع `dist/` — بصمة SW تُبطل الكاش تلقائياً.
4. تراجع: M4 = `migrate accounting 0025` (فهارس بلا بيانات) · البقية revert diff + restart.

### [تشخيص 2026-07-10 — «الصفحة تفتح لكن الدخول يفشل» على شبكات معينة]
بلاغ: الواجهة تفتح لكن تسجيل الدخول يرجع «تعذر الاتصال بالخادم» على بعض الشبكات دون غيرها.
**التشخيص بالأدلة:** (1) الصفحة «تفتح» لأنها PWA — الشل يُقدَّم من precache الـ SW حتى بلا
شبكة فعلية للـ API؛ الفشل يظهر فقط عند أول نداء API حقيقي (الدخول). (2) DNS سليم (نفس الـ IP
من resolver المحلي و8.8.8.8، لا AAAA). (3) **السبب:** LiteSpeed يعلن
`Alt-Svc: h3=":443"; ma=2592000` على النطاقين ⇒ كروم يحفظ «كلّم هذا المضيف عبر QUIC/UDP-443»
لمدة **30 يوماً**؛ على الشبكات التي تحجب/تشوّه UDP-443 (شائع لدى مزودات محلية) يبقى كروم
يحاول QUIC المحفوظ لنطاق الـ API فيفشل النداء كخطأ شبكة — بينما يعمل على شبكات تمرر UDP
وفي الخفي (كاش Alt-Svc فارغ). نفس جذر AUDIT 2026-07-02، الآن مؤكَّد بترويسات حية.
**العلاج (على الخادم — ليس في الريبو):**
1. أعلى `.htaccess` في **كلا** الجذرين (الواجهة والـ API): `Header always unset Alt-Svc`
   ثم تحقق `curl -sI https://api.smart.ktragroup.com/api/health/ | grep -i alt-svc` — إن
   اختفت الترويسة انتهت المشكلة لكل زائر جديد (كاش القدامى ينتهي خلال ≤30 يوماً أو بمسح بيانات المتصفح).
2. إن أعاد LiteSpeed إلحاقها بعد الـ .htaccess: تذكرة للاستضافة «عطّلوا QUIC/HTTP-3
   (إعلان Alt-Svc) للنطاقين» — إعداد vhost متاح لمدير LSWS.
3. **الحل البنيوي** (يقتل هذه الفئة كلها + يلغي CORS): نقل الـ API لنفس الأصل
   `smart.ktragroup.com/api` عبر cPanel «Setup Python App» + تغيير `VITE_API_URL` — عندها
   الـ API يركب نفس اتصال الصفحة: إن فتحت الصفحة عمل الـ API حتماً.
- **مؤقتاً للمستخدم المتضرر:** كروم → `chrome://flags/#enable-quic` → Disabled، أو مسح
  بيانات التصفح للموقع، أو متصفح آخر.

### [ORPHANS & PENDING — صيانة الأداء]
- **ترقيم فواتير المبيعات/الشركاء/الصفقات/فواتير الشراء** — مؤجَّل عمداً: بحث فواتير
  المبيعات client-side بينما الخادم يدعم status/customer فقط ⇒ ترقيم أعمى = فاتورة قديمة
  تختفي من البحث (ارتداد مالي). المسار الصحيح: إضافة `search`/`date_from`/`date_to` لـ
  `SalesInvoiceViewSet` (بنمط JournalViewSet) ثم التحويل لـ `apiGetPagedList` (البنية جاهزة).
  الصفقات وفواتير الشراء عبر طبقات mapper (dealsService/purchaseInvoiceApi) — عقودها تُلمس بحذر.
- **N+1 ثانوي في `build_journal_reference_summary`** لأنواع SALES_INVOICE/CUSTOMER_PAYMENT/
  CLEARANCE (استعلام لكل صف) — محدود الآن بحجم الصفحة (100)؛ تحسين لاحق بنفس نمط pay_map.
- **`LogisticsPaymentViewSet.get_queryset()`** بلا select_related — جولة لاحقة.
- **كاش شجرة الحسابات** — مؤجَّل: يتطلب مفتاح tenant+صلاحية 53* + invalidation؛ يُنفَّذ فقط
  إن ثبت أن كاش الداشبورد غير كافٍ.
- بند «حلقات .save() في logistics» من التدقيق الأولي **أُسقط بعد التحقق** — عمليات مفردة
  على مستند واحد، لا مشكلة فعلية.

## [FIX — مراجعة مسار الاستيراد ج1: أوضاع الصفقة + سجل مدفوعات بنمط الفواتير, 2026-07-09]
بلاغ المالك: «حطيت تعديل صفقة أجاني وضع الطباعة، حطيت تعديل البيانات أجا وضع التعديل واختفى» +
طلب جعل دفعات الصفقات بنمط الفواتير. التشخيص (السببان الجذريان):
1. **تعديل→طباعة:** زر «تعديل» في `DealManagement` كان يفتح `/deals/{id}` وهذا المسار كان
   يعرض `DealPrintView` (وضع التقرير) وليس النموذج.
2. **اختفاء التعديل:** `dealsService.subscribeToDeals` = polling كل 5 ثوانٍ؛ كل تحديث
   لمصفوفة `deals` كان يعيد تشغيل effect المسارات الذي **يفرض** `viewMode='view'` من جديد
   فيقلب المستخدم من النموذج إلى التقرير.
الحل (URL = مصدر الحقيقة الوحيد للوضع):
- `frontend_v2/components/procurement/DealManagement.tsx`: عقد مسارات جديد —
  `/deals` قائمة · `/deals/new` جديدة · `/deals/{id}` **تعديل (النموذج)** ·
  `/deals/{id}/view` تقرير/طباعة. حارس `handledPathRef` (pathname+search) يجعل كل مسار
  يُعالج مرة واحدة فقط — الـ polling لم يعد يقلب الوضع. رابط `?ref=D-xxxx` القديم يُحوَّل
  replace إلى `/deals/{id}/view`. زر «تعديل البيانات» في التقرير يبحر إلى `/deals/{id}`.
- `frontend_v2/components/forms/deal-parts/DealPaymentList.tsx`: **أعيدت كتابته** —
  سجل مدفوعات الصفقة أصبح جدولاً كثيفاً بنمط جداول الفواتير (قسط/نوع/تاريخ/مبلغ/صرف/عمولة/
  مرفقات/حالة/قيد/إجراءات + تذييل مجموع ومتبقٍ) بدل البطاقات الضخمة. نفس العمليات محفوظة:
  فتح قيد، ربط قيد يدوي، شرح عدم الترحيل (تشخيص الخادم)، إلغاء ترحيل (مدير)، حذف من السجل،
  تحذير تجاوز الإجمالي، ووسم «مكرر ×N» على السجلات المتطابقة. الأرقام عبر `formatMoney` (G1).
- `frontend_v2/components/procurement/deals/DealPrintView.tsx`: `formatCurrency` تحوّلت من
  `Intl.NumberFormat(min:2)` إلى `formatMoney` (فرض G1 — لا أصفار عشرية زائدة).
- تحقق: tsc 0 أخطاء جديدة (خطأ `DepartmentCard.tsx` **سابق** وغير ذي صلة) · vite build OK.

## [UX — مراجعة الاستيراد ج6: فك تداخل واجهات الشحن/التخليص/النقل مع «رحلة الاستيراد», 2026-07-10]
شكوى المالك: «عدة واجهات متداخلة مع الشحن والتخليص — مربك». **العقد الموحّد** المطبق على
الصفحات الثلاث (شحنات/تخليص/نقل محلي): *نقرة = تحديد · نقرة مزدوجة = فتح الرحلة/الملخص ·
الإنشاء عبر اختيار الشحنة أولاً — لا صفحات «شحنة جديدة» فارغة مربكة* + سطر توجيه معلَن:
- **`ImportDocumentScreen`:** العنوان صار «رحلة الاستيراد — {اسم الشحنة}» فيعرف المستخدم
  أين هو أياً كان مدخله.
- **`ShipmentDetailView`:** زر **«رحلة الاستيراد»** في رأس الملخص (المسار: ملخص واضح ←
  تحرير كامل بنقرة).
- **`CustomsClearanceManagement`:** كانت النقرة المفردة تُقفز فوراً لرحلة الاستيراد
  (مفاجئ) و«إضافة» تفتح شحنة جديدة فارغة — الآن: نقرة تحدّد، مزدوجة تفتح تبويب التخليص
  في الرحلة، و«إضافة تخليص لشحنة» يفتح **منتقي الشحنات التي بلا تخليص** (تخليص واحد لكل
  شحنة) ثم يقفز لتبويب التخليص مباشرة. CtrlIns وسهم «جديد» في التنقل كذلك.
- **`LocalShippingPage`:** كانت النقرة المفردة تفتح تاباً جديداً (!) و«شحنة محلية جديدة»
  تفتح شحنة استيراد جديدة فارغة و`/import-flow/null` ممكن لسجل بلا شحنة — الآن: مزدوجة
  تفتح الرحلة (مع حارس null)، «نقل محلي جديد» يفتح **منتقي شحنات** ثم تبويب النقل المحلي،
  أزرار السجل تظهر فقط عند وجود شحنة مرتبطة، واستُبدلت بقايا `window.confirm/alert`
  بـ`useConfirm`/بانر (إغلاق فجوة task33).
- **`ShipmentManagement`:** سطر يشرح: مزدوجة = ملخص، ✎ = رحلة الاستيراد.
- **متابعة (لقطة «شو هاد دائن ومدين»):** جدول بنود التخليص في تبويب التخليص كان بأعمدة
  مدين/دائن/VAT% (قالب سكين الأصيل المحاسبي) — أُعيد بنوداً بسيطة: **النوع + البيان +
  المبلغ (₪)** فقط؛ المبلغ يُخزَّن `debit` (وcredit=0) والخادم يحوّله لقيد كما كان.
  أُضيف «مجموع البنود» حيّ + زر «اعتماده كـ‹الإجمالي›» + سطر يوضح أن البنود هي تكلفة
  التخليص الموزَّعة على الفواتير. حقل vat_percent بقي في النموذج البياني بلا واجهة.
  و«تسجيل سريع» (سؤال المالك «وين أفوت إجمالي بدون بنود؟»): خانة إجمالي واحدة + «اعتماد
  وحفظ» تستبدل البنود ببند وحيد «تكلفة التخليص (إجمالي)» وتحفظ فوراً (تأكيد إن وُجدت بنود
  بمبالغ) — لأن حقل «الإجمالي» العلوي عرضي فقط ولا يدخل حوض التوزيع (cost_lines هي الحوض).
  `handleSaveClearance` صارت تقبل formOverride وتعيد boolean.
- **متابعة (لقطة «حصة الشحن 0.00»):** خانات حصة الشحن في تبويب الصفقات uncontrolled
  بـ`defaultValue` — كانت تبقى 0.00 بعد إعادة التوزيع رغم حفظ القيم (المجموع بالفوتر
  صحيح). الحل: `key` يتضمن القيمة ⇒ remount عند تغيّرها. + توحيد مصطلح «إرسالية»→«شحنة»
  في كامل `ImportDocumentScreen` (رقم/نوع الإرسالية، رسائل التحميل، قيد التحويل…)،
  وتبويب الصفقات صار «صفقات هذه الشحنة» بزر «ضمّ صفقة» وسطر يشرح معنى «حصة الشحن».
- تحقق: tsc 0 جديدة · vite build OK. (بلا تغيير backend.)

## [UX — مراجعة الاستيراد ج5: رحلة سلسة صفقة→فاتورة دولية (شريط خطوات + دفعات وكيل الشحن), 2026-07-10]
طلب المالك: «اعتبر حالك مستخدم دافع — كل اشي واضح من عمل صفقة لحد الفاتورة الدولية»:
- **الطريق المسدود الأكبر (اكتشاف):** لم تكن توجد **أي واجهة** لتسجيل دفعات وكيل الشحن
  (`LogisticsPayment` على الشحنة بلا صفقة) رغم أن استيراد الفاتورة الدولية **مشروط**
  باكتمالها بالدولار (`shipment_freight_ils` guard) — `shipmentsService.addShipmentAgentPayment`
  كانت بلا مستهلك، ورسالة المودال تحيل لـ«شاشة الشحنة» غير الموجودة. الحل: قسم «دفعات
  وكيل الشحن» في تبويب الدفعات بـ`ImportDocumentScreen`: شريط مدفوع/إجمالي USD + حالة
  «مكتمل/متبقٍ$»، جدول الدفعات، ونموذج إضافة (مبلغ$، صرف، تاريخ، «مؤكّدة») عبر
  `PATCH shipments/{id}/ {payments:[…]}` — **المطابقة بالخادم بـpayment_number** (id
  read-only في `LogisticsPaymentSerializer`)، والسقف = إجمالي تكلفة الشحن (خادمي).
- **شريط خطوات الرحلة** أعلى `ImportDocumentScreen`: ٦ خطوات حيّة قابلة للنقر
  (شحنة→صفقات→دفع الشحن→تخليص→نقل محلي «اختياري»→فاتورة دولية) بحالة ✓/●/○ وتلميح
  «الخطوة التالية» — خطوة الفاتورة توجّه ذكياً (لا تخليص→تبويبه، شحن ناقص→الدفعات).
- **أسماء مقروءة:** `LogisticsShipmentDealAllocationSerializer` +`deal_ref`/`deal_title`
  (عبر `invoice_title_from_deal`) — تبويب الصفقات كان يعرض «#123 · —». منتقي «ربط صفقة»
  يعرض العنوان العربي + المورد + شارة **«جاهزة للشحن»** (sw_wait_intl_ship تُرتَّب أولاً)
  وتسمية المرحلة لغيرها (`getShippingWorkflowLabel`).
- **سلاسة:** حقل الناقل بالنقل المحلي صار **قائمة شركاء** (LocalTransporter/FreightForwarder/
  Supplier مرتّبة، fallback للرقم إن فشل التحميل) بدل «رقم الناقل» الخام · بعد إنشاء شحنة
  جديدة يُثبَّت الرابط `/import-flow/{id}` (كان يبقى /new فيضيع عند التحديث) + toast «اربط
  الصفقات» وفتح تبويبها · زر «تحويل إلى فاتورة شراء» معطّل بلا تخليص.
- **توحيد عنوان الصفقة (متابعة — لقطة «شحنة السماعات»):** قاعدتان جديدتان في الفلتر
  المشترك ودوال العنوان الثلاث (`dealTitleDisplay.ts` + `invoice_title_from_deal` +
  `_deal_title_for_list_preview` — **الثلاث يجب أن تبقى متطابقة**): (1) نص إنجليزي >80
  حرفاً ليس اسم صفقة أبداً؛ (2) الاسم العربي المخزّن قديماً في `original_offer_number`
  **يتقدم** على الوصف الإنجليزي. عمود «رقم العرض» في `ShipmentDetailView` لا يكرر
  العنوان المعروض. `ClearanceImportModal` يمرّر original_offer_number للعنوان.
  اختبارات: `DealTitlePriorityTest` (6) في test_clearance_import.py.
- تحقق: logistics 86/86 · tsc 0 جديدة · vite build OK. (خلف الدخول — لا تحقق بصري.)

## [FIX — مراجعة الاستيراد ج4: إصلاح كسر «استيراد من تخليص» + عناوين/أسماء + توحيد نقل محلي, 2026-07-10]
شكوى المالك: «مسار رحلة الاستيراد مخربط… بقدرش استورد ولا فاتورة» (لقطة خطأ
`PurchaseInvoice() got unexpected keyword arguments: local_payments_json, conversion_metadata_json`):
- **(الكسر الجذري) بقايا P-D-8:** هجرة `0035_drop_pi_json_fields` حذفت حقلَي JSON من
  `PurchaseInvoice` لكن `landed_cost.py` ظل **يكتبهما** في `import_invoices_from_clearance`
  (TypeError عند كل استيراد من تخليص) **ويقرؤهما** في `recalculate_landed_for_shipment`
  و`compute_live_purchase_invoice_read_payload` (AttributeError على GET لأي فاتورة دولية
  غير مرحّلة). الحل: هجرة `0049_purchaseinvoice_import_params` — 3 أعمدة منمّطة
  (`import_deal_remaining_rate` / `import_shipment_remaining_rate` / `import_use_cost_lines`)
  تحفظ معاملات الاستيراد التي كانت في conversion_metadata، والـpayload الحي يُبنى منها.
  حُذفت `merge_local_payments_keep_user_fee_lines` (صارت يتيمة — بنود المستخدم الآن
  `PurchaseInvoiceFee`).
- **إصلاح ثانٍ بنفس الموضع:** فواتير الاستيراد كانت تُنشأ بلا `invoice_type` ⇒ تُسجَّل
  «محلية» (default) رغم أنها دولية — الآن `INVOICE_TYPE_INTERNATIONAL` صراحةً.
- **العناوين الإنجليزية («وصف صفقة بالانجليزي بدل الاسم»):** فلتر boilerplate المشترك
  (`logistics/text_utils.py` + `utils/dealTitleDisplay.ts` — يبقيان متطابقين) وُسّع ليلتقط
  «Trade/Payment/Price/Delivery terms»، نسب الدفعات (%+advance/deposit/balance)، ومدد
  التسليم (deliver…days/weeks) ⇒ يسقط لعنوان عربي من الملاحظات/العرض. أُضيفت
  `offerNumberForDisplay` (رقم عرض ≤40 حرفاً وليس شروطاً) لعمود «رقم العرض» في
  `ShipmentDetailView`.
- **أسماء الشحنات:** عمود «اسم الشحنة» + البحث بالاسم في `ShipmentManagement`.
- **التنقّل:** دبل-كليك على شحنة يفتح **ملخص الشحنة** (`ShipmentDetailView`) بدل صفحة
  رحلة الاستيراد؛ «رحلة الاستيراد» من زر التعديل فقط (كما طلب المالك حرفياً).
- **«التكلفة الموزعة $0»:** توزيعات قديمة غير محسوبة في `logistics_shipment_deals` —
  `ShipmentDetailView` يسقط الآن لتوزيع حجمي/وزني حسابي (نفس
  `shipmentsService.calculateDistribution`) عند كون كل الحصص صفراً مع وجود تكلفة.
- **توحيد النقل المحلي:** تبويب التخليص في `ImportDocumentScreen` يعرض تنبيهاً عند وجود
  بنود «شحن محلي» في cost_lines (مسار قديم) ويوجّه لتبويب «النقل المحلي» الموحّد؛ حارس
  الازدواج الخلفي (T1-01 superseded) قائم بلا تغيير.
- تحقق: **الحزمة الخلفية الكاملة 201/201** (+3 TDD جديدة في
  `logistics/tests/test_clearance_import.py`: استيراد ينشئ فاتورة دولية بالمعاملات المحفوظة ·
  GET التفاصيل بعد الاستيراد · recalculate يحدّث المعاملات) · tsc 0 أخطاء جديدة.

### [ORPHANS & PENDING — مراجعة الاستيراد (صفقة → فاتورة دولية)]
المتبقي بعد ج1–ج3:
1. خطأ tsc سابق: `components/DepartmentCard.tsx` يستورد
   `../../services/firestoreService` (مسار خاطئ — الملف في `components/` مباشرة).
2. `old-invoices/OldInvoiceFormModal` (أرشيف قديم) ما زال على alert (5 مواضع) — legacy
   خارج مسار الاستيراد الحي، يُحوَّل عند لمسه.
3. `suggestStatusAfterClaim` في DealForm ما زال يقترح حالات وهمية (first_payment_pending…)
   تُسقَط إلى Open عند الحفظ — no-op غير مؤذٍ؛ يُحذف عند جولة تنظيف قادمة.

## [FIX — مراجعة الاستيراد ج3: إلغاء polling + توحيد لغة الحالة + واجهة unpost موحّدة, 2026-07-09]
تنفيذ البنود الثلاثة المتبقية بتفويض المالك («ساوي المناسب»):
- **(1) إلغاء polling الصفقات (5 ثوانٍ):** `dealsService.subscribeToDeals` صار تحميلاً
  عند الاشتراك + **تحديث عند عودة التركيز/الظهور للتبويب** (يلتقط تعديلات التبويبات
  الأخرى بلا مؤقّت) + خيار `intervalMs` لمن يحتاج دورية صريحة. `listDeals()` جديدة
  للتحديث الصريح. المستهلكون الأربعة (DealManagement/DealForm/ShipmentDetailView/
  ClearanceImportModal) بلا تغيير توقيع. `DealManagement`: حذف الصفقة يُحدّث القائمة
  محلياً، الحفظ من النموذج يعيد التحميل، وزر ⟳ صار «تحديث القائمة» فعلياً.
- **(2) توحيد لغة الحالة (قرار معماري موثّق):** «الحقيقة» التشغيلية =
  `shipping_workflow_status` (6 مراحل task12)؛ دورة الحياة = 4 قيم SQL فقط
  (Open/Shipped/Closed/Cancelled) تُشتق آلياً منها؛ الدفع بُعد مالي مستقل محسوب.
  قائمة الـ14 حالة في فلتر `DealManagement` كانت **وهمية** (لا يمكن أن تعود من SQL) ⇒
  استُبدلت بالأربع الحقيقية + عمود جديد **«المرحلة»** يعرض تسمية workflow عبر
  `getShippingWorkflowLabel` المشتركة (DRY مع DealStageControl).
- **(3) واجهة «تراجع عن الترحيل» الموحّدة (يُغلق task17 pending):** في
  `ImportDocumentScreen`: قسم «تراجع عن الترحيل» بتبويب **الحسابات** (زرّا الشحنة
  والتخليص — الأخير يتفعّل فقط عند وجود دفعات مرحّلة)، وزر لكل صف **نقل محلي مرحَّل**.
  الثلاثة عبر endpoints task17 القائمة (`shipments|clearances|local-shipments/{id}/unpost/`)
  بحوار تأكيد + toast + إعادة تحميل؛ حارس الاعتمادية (task25) يظهر خطؤه في البانر.
- تحقق: tsc 0 أخطاء جديدة · vite build OK · لا تغيير backend (لا حاجة لإعادة الاختبارات
  — ج2 خضراء 195/195). (الشاشات خلف الدخول — لا تحقق بصري، مطابقةً للنهج.)

## [FIX — مراجعة مسار الاستيراد ج2: توحيد تكلفة الاستيراد + رسائل داخل الموقع + تنظيف, 2026-07-09]
تكملة ج1 (طلب المالك: «كل شي جاهز — حسابات، منطق، برمجة، تصميم»):
- **(حسابات) توحيد تكلفة الاستيراد مع نموذج «تكلفة المنتجات»** — أُغلق تذكير task23
  («أول ما نشتغل على الاستيراد»): `apply_purchase_cost_model` (القرار المركزي دوري/متحرك)
  صار يُستدعى في **ثلاث نقاط**: (1) `inventory/services.receive_shipment_stock` بعد استلام
  الشحنة، (2) `PurchaseInvoiceViewSet.post_to_accounting` بعد الترحيل (يغطي المحلية GR/IR
  والدولية — `product_cost_breakdown` يقدّم landed cost أصلاً فتشمل تكلفة الفاتورة حصة
  التخليص)، (3) `LogisticsShipmentViewSet.unpost` بعد عكس الاستلام. النتيجة: بيع-قبل-وصول-
  الشحنة لم يعد يشوّه المتوسط (نمط 3800÷13). اختبارات TDD جديدة
  `logistics/tests/test_import_cost_model.py` (3): انحراف WAC السالب ⇒ 600 لا 1200 ·
  بلا فاتورة مرحّلة يبقى WAC · unpost يعيد الضبط من الفواتير المتبقية.
- **(تصميم) DealForm:** تبويب «الدفعات والمراحل» فُصل إلى تبويبين — «الدفعات»
  (أقساط + تقدم + سجل الجدول الكثيف) و«المراحل والشحن» (`DealStageControl`) — أقل تكدساً.
- **(برمجة/UX) إنهاء رسائل المتصفح على مسار الاستيراد كاملاً** (نمط task33):
  `DealForm` (~35 موضعاً) + `DealManagement` + `PaymentProgress` + `DealPaymentList` +
  `PurchaseInvoice` + `InvoiceList` + `PurchaseInvoiceAccountingPanel` (تأكيد unpost) +
  `ClearanceImportModal` + `ShipmentManagement` + `InstallmentsSection` +
  `InvoiceCategoryTree` + `ImportDocumentScreen` (فك ربط صفقة/نقل تكلفة محلي) —
  كلها عبر `useToast`/`useConfirm`. **`ConfirmDialog` أُضيف له `hideCancel`** (حوار
  معلومات بزر «حسناً» للرسائل الطويلة: نتائج تأكيد المورد/إلغاء الترحيل/تشخيص الترحيل).
  المتبقي عمداً: `old-invoices` (أرشيف legacy) و`window.prompt` لرقم القيد اليدوي.
- **(تنظيف) حُذف الكود الميت:** `deals/DealList.tsx` (532س) + `deals/DealActivityPreview.tsx`
  (425س) — غير مستوردين من أي مكان.
- تحقق: **الحزمة الخلفية الكاملة 195/195** (+3 جديدة) · `check` 0 · `makemigrations --check`
  بلا انحراف · tsc 0 أخطاء جديدة · vite build OK. (الشاشات خلف الدخول — لا تحقق بصري،
  مطابقةً للنهج المعتمد.)

---

## [FEAT — سجل نشاط المستخدمين (Activity Log) عبر الموقع, 2026-07-09]
المطلوب: تتبّع «مَن فعل ماذا» على فواتير البيع/الشراء والصفقات، مع سجل لكل مستند + صفحة
عامّة للمدير تُظهر نشاط كل المستخدمين من الدخول حتى الخروج، وفلترة حسب المستخدم/النوع/التاريخ.
الحل (طبقة Shared/Core واحدة، غير حاظرة):
- **النموذج:** `core.ActivityLog` (جدول `activity_logs`, migration `core/0001_initial`) — tenant/user/
  action(create|update|delete|post|unpost|duplicate|payment|view|login|logout)/`is_view`/entity_type/
  entity_id/entity_label/description/metadata(JSON)/ip/timestamp. أول migration للـ app `core`
  (نموذجه السابق `SystemAttachment` يبقى managed=False). `is_view` يفصل أحداث «العرض» عن التعديلات.
- **الخدمة:** `core/activity.py::log_activity/log_view` — تحلّ request/tenant/user/ip تلقائياً،
  والإدراج داخل `transaction.atomic()` (savepoint) داخل `try/except` فلا يكسر معاملة المتصل ولا يرمي.
- **الربط:** `sales/views.py` (SalesInvoice: create/update/delete/post/unpost/duplicate/payment/view +
  CustomerPayment)، `logistics/views.py` (PurchaseInvoice + LogisticsDeal: نفس المجموعة + view)،
  و`hr/auth_api.py` (login/logout → entity_type=`session`). الربط عبر استدعاءات `log_activity`
  صريحة في نقاط دورة الحياة (لأن الـ viewsets تُعيد تعريف perform_create/update/destroy بمنطق خاص).
- **API:** `GET /api/activity/` (`core/activity_views.py`, ReadOnly + pagination). فلاتر: user/action/
  entity_type/entity_id/date(افتراضي اليوم)/date_from/date_to/search/include_views. الاستعلام العام
  (بلا entity_id) للمدير فقط (`core.user_roles.user_is_admin`)؛ سجل مستند واحد متاح لأي عضو.
  `GET /api/activity/users/` قائمة المستخدمين ذوي النشاط (للفلتر).
- **الواجهة:** `types/activity.ts`, `services/activityService.ts`, مكوّن مشترك
  `components/activity/EntityActivityLog.tsx` (+`activityMeta.tsx`) مركَّب كتبويب «سجل النشاط» في
  محرّري فاتورة البيع/الشراء (`SalesInvoiceEditor`, `invoices/InvoiceForm`) وتبويب «سجل نشاط
  المستخدمين» في `deals/DealForm` (المكوّن القديم `ActivityLog` بقي دون حذف). الصفحة العامة
  `components/ActivityLogPage.tsx` (AppView `activity-log`, في `Sidebar` تحت إدارة الموظفين — manager فقط،
  و`App.tsx` route) بفلاتر + Drill-down لكل مستخدم (يشمل العرض، يبدأ باليوم مع تحكّم بالتاريخ).
- **الاختبارات:** `core/tests/test_activity_log.py` (10 اختبارات: إنشاء/ابتلاع الفشل/صلاحية المدير/
  استبعاد العرض من العام/سجل المستند/الافتراضي اليوم/login+logout). No-regression: sales+logistics خضراء
  (فشل `test_price_list_bulk_last_and_lowest` **سابق ومستقل** — منطق `purchase_price_list` لم يُمَس).

---

## [FEAT — تفعيل مرتجع البيع ومرتجع الشراء (كانا شكليّين), 2026-07-09]
بلاغ المالك: مرتجع الشراء/البيع «شكليّان» — عند اختيار المورد لا يحدث شيء، وبانر أصفر
«يتطلب backend». المطلوب: مرتجع احترافي يشيل الكمية، يعمل قيوداً أصولية، ويُرجع الأموال.
التشخيص (السبب الجذري): الشاشتان تُرسلان إلى نقاط نهاية **غير موجودة** (`sales/returns/`،
`purchase/returns/`)، وشاشة الشراء تُحمّل من مسار خاطئ (`purchase/invoices/` بدل
`logistics/purchase-invoices/`) ⇒ القائمة فارغة والحفظ يفشل. اكتشاف: خدمة `post_sales_invoice`
تدعم **مرجع البيع** أصلاً وبشكل صحيح عبر `invoice_kind='sale_return'` (تعكس القيد + `RETURN_IN`)،
لكن `SalesInvoiceSerializer` لا يكشف الحقلين ولا يوجد route. أما مرجع الشراء فيعيش في `logistics`
بحسابات مختلفة (AP/مخزون/ض.مدخلات) — مسار الـ SalesInvoice خاطئ له.
الحل الجراحي:
- **مرجع البيع (إعادة استخدام `SalesInvoice`+`post_sales_invoice`):** كشف `invoice_kind`/
  `original_invoice`(+`original_invoice_number`) في `SalesInvoiceSerializer`؛ تخطّي فحص توفّر
  المخزون للمراجيع (`_validate_stock_lines(is_return=)` — البضاعة تدخل)؛ وتخطّي فحص حدّ الائتمان
  للمراجيع في `post_sales_invoice` (`and not is_return`). الواجهة تُنشئ فاتورة sale_return ثم
  تُرحّلها (`createSalesInvoice`+`postSalesInvoice`) وتنسخ البنود من الأصلية (`getSalesInvoice`).
- **مرجع الشراء (أصلي في `logistics`):** حقلا `PurchaseInvoice.is_return`+`original_invoice`
  (migration `0048_purchaseinvoice_return`)؛ خدمة **`create_purchase_return`**: حركة `RETURN_OUT`
  تُخرج الكمية بمتوسط التكلفة + قيد يعكس الشراء (Dr ذمم المورد الإجمالي / Cr مخزون الصافي +
  Cr ض.مدخلات، ونسبة الضريبة تُشتق من بنود الفاتورة الأصلية) بمرجع `PURCHASE_RETURN`؛ endpoint
  **`POST logistics/purchase-invoices/returns/`** (`create_return`، detail=False). `is_return`/
  `original_invoice` مكشوفة بالـ serializers للفلترة/العرض. الواجهة تُحمّل الأصليات من المسار
  الصحيح (مرحّلة وليست مرجعاً)، وتنسخ البنود (`purchaseInvoiceApi.get`)، وتُرسل للـendpoint.
- **الأموال حسب الأصول:** المرجع يُخفّض ذمم العميل (بيع) / ذمم المورد (شراء)؛ الردّ النقدي الفعلي
  يبقى سنداً مستقلاً (نمط الأنظمة الاحترافية). أُزيلت البانرات الصفراء و«يَنتظر N8-T11».
تحقّق: **backend: sales+logistics 155 ناجح** (+4 جديد: مرجع بيع يُعيد الكمية+يُدين الإيراد/يُدائن
الذمم؛ مرجع شراء يُنقص المخزون+Dr AP/Cr مخزون+رفض بند صفري) · الفشل الوحيد
`test_price_list_bulk_last_and_lowest` **سابق ومستقلّ** · `makemigrations --check` بلا تغييرات ·
`manage.py check` 0 · `tsc` نظيف لملفَّيّ (خطآ DepartmentCard/Breadcrumb سابقان). (خلف الدخول +
خادم بعيد — لا تحقّق بصري، مطابقةً للنهج المعتمد.)

**تحديث (بلاغ المالك — فصل الحفظ عن الترحيل + تمييز/فلترة):**
- **الحفظ والترحيل منفصلان (خطوتان):** `create_purchase_return` صار يُنشئ المرجع **مسودة**
  فقط (`status='draft'`, `is_posted=False`) بلا حركة/قيد؛ والترحيل خطوة مستقلة عبر خدمة
  جديدة **`post_purchase_return`** (RETURN_OUT + القيد العكسي). زر «post-to-accounting» و
  «unpost» في `PurchaseInvoiceViewSet` يوجّهان المرجع لهذين المسارين (حارس `is_return`).
  نسبة الضريبة تُخزَّن على بند المرجع عند الحفظ ليقرأها الترحيل. **مرجع البيع** كذلك يُحفظ
  مسودةً فقط (الواجهة لم تعد تُرحّل تلقائياً) ويُرحَّل من «فواتير المبيعات».
- **تمييز عربي + فلتر:** `PurchaseInvoiceViewSet.get_queryset` يدعم `?is_return=true|false`؛
  و`is_return`/`original_invoice` مكشوفة بالـ serializers. في `InvoiceList` عمود «النوع»
  (شارة **مرجع**/**فاتورة**) + فلتر «الكل/فواتير الشراء/مراجيع الشراء» (`Invoice.isReturn`
  عبر `sqlListToInvoice`). الترحيل من داخل المستند المفتوح (لا زر ترحيل في القائمة).
- **إصلاح ظهور الأصناف:** الأصناف تُعاد بحقول `name_ar`/`display_name`/`sku` لا `name` —
  أُضيفت `productLabel` في المحرّرين + تعبئة تلقائية لبنود الفاتورة الأصلية عند اختيارها.
- تحقّق: **18 اختباراً ناجح** (منها مرجع الشراء «مسودة ثم ترحيل»: لا مخزون/قيد عند الحفظ،
  وخفض المخزون +Dr AP/Cr مخزون عند الترحيل) · `check` 0 · `tsc` نظيف لملفّاتي.

## [AUDIT — تكرار بطاقات الأقسام + تحكّم بحجم/نوع الخط في الإعدادات, 2026-07-04]
بلاغ المالك: (1) في صفحة «تواصل معنا» كلّما عدّل قسماً (مثلاً غيّر اسم «المشتريات») تُنسخ
القائمة كاملةً وتُلحق ⇒ صارت عدّة بطاقات مشتريات مكرّرة (مرفق صورة). (2) يريد في الإعدادات
تحكّماً بحجم الخط ونوعه.
التشخيص (السبب الجذري للتكرار): `departmentsService.addDepartment` يولّد **UUID عشوائياً**
في كل نداء (`doc(collection(...))`) متجاهلاً المعرّف الثابت. ومع فرع «ازرع كل الأقسام حين
تكون القائمة فارغة» في `Contact.handleSave`، فكلّما رجع قراءة الـmapper فارغاً (أو عدّل
المدير قبل تحديث الاشتراك كل 5 ثوانٍ) تُكتب 6 وثائق جديدة بمعرّفات عشوائية ⇒ تتراكم النسخ
= «تُنسخ القائمة وتُنزَّل» حرفياً في كل حفظ.
الحل الجراحي (مصدر حقيقة واحد — كتابة idempotent بمعرّف ثابت):
- **`firestoreService.departmentsService.saveDepartment(dept)`** (جديد): upsert بمعرّف القسم
  **الثابت** عبر `setDoc` إلى `/mapper/departments/<id>/` — إعادة الحفظ/الزرع تُحدّث نفس
  الصف بدل إلحاق نسخة عشوائية. (المعرّفات الافتراضية ثابتة: purchasing/finance/…)
- **`Contact.handleSave`**: أُعيد لاستخدام `saveDepartment` — الزرع الأول بمعرّفات ثابتة
  (createdAt متدرّج للحفاظ على الترتيب) والتعديل اللاحق upsert لبطاقة واحدة. لا تكرار أبداً
  حتى لو تكرّر النداء. + زر **«إعادة تعيين الأقسام»** (للمدير فقط، بتأكيد) يحذف كل الوثائق
  ثم يعيد زرع الافتراضي — لتنظيف التكرارات القائمة صراحةً (لا حذف تلقائي).
- **الخط (feature)** — `contexts/AppearanceContext.tsx` (على نمط ThemeContext): تفضيل حجم
  الخط (صغير/متوسط/كبير/أكبر) ونوعه (افتراضي/Tahoma/Segoe/Arial). يُطبَّق على `<html>` بضبط
  `--font-family-base`+`--aseel-font` ومرتكز rem (`html.fontSize`) ومتغيّرات الأصيل بالبكسل
  (`--aseel-fs`/`-sm`/`-base`/`-title`) بنفس النسبة ⇒ يسري على الواجهة العامة وسكِن الأصيل
  معاً. مُركَّب في `index.tsx` داخل ThemeProvider، وقسم «المظهر — الخط» في `SettingsPage`.
  تتبّع `appearance.font_scale`/`font_family`.
  **(task34) التخزين per-company على الخادم:** مصدر الحقيقة هو `TenantSettings.font_scale`/
  `font_family` (+migration `0011_tenantsettings_appearance` +serializer) ⇒ يثبت عند إعادة
  الدخول وعبر الأجهزة، ومعزول لكل شركة لا للمنصة. cache محلي مفتاحه رقم الشركة
  (`ktra_font_scale::<tid>`) للتطبيق الفوري + ترحيل لطيف للمفتاح العام القديم. المزوّد
  يجلب `tenants/settings/current/` عند التركيب (مُوثَّق بالتوكن) ويحفظ بـ PATCH عند التغيير
  (غير حظري). تبديل الشركة يعيد تحميل الصفحة ⇒ يُعاد تركيب المزوّد بالشركة الجديدة.
- **زر ثوابت المجموعة (feature)** — بديل مرئي للمفتاح F11 في يسار الشريط العلوي
  (`AppLayout.tsx`، أيقونة `SlidersHorizontal`) يستدعي نفس `onOpenGroupConstants`.
  ثوابت المجموعة أصلاً per-tenant في الخلفية (`TenantSettings`/`TenantBook`/`SalesSettings`).
تحقّق: `tsc --noEmit` نظيف لملفاتي · بناء الإنتاج ناجح (SW+manifest) (الخطآن الباقيان في
`DepartmentCard`/`Breadcrumb` **سابقان** لهذا التعديل ومستقلّان). (خلف الدخول + لا إطار اختبار
React — لا تحقّق بصري، مطابقةً للنهج المعتمد.)

## [AUDIT — ربط واجهتَي «عرض السعر» + أولوية التسعير + عرض البنود, 2026-07-04]
بلاغ المالك: (1) لا يمكن رؤية بنود عرض السعر. (2) منتج عليه عرض لا يظهر سعره في خيارات
فاتورة المبيعات. والمطلوب ترابط واجهتَي عرض السعر (كرت الزبون ↔ واجهة العروض): إنشاء عرض
بواجهة العروض يملأ كرت الزبون إن كان فارغاً؛ وفاتورة المبيعات تُقدّم عرض «واجهة العروض» ثم
عرض كرت الزبون، والنقر على الشارة يفتح مصدرها.
الحل الجراحي (خادمي = مصدر حقيقة واحد + واجهة):
- **`SalesQuotationSerializer.create`**: بعد إنشاء البنود يملأ `CustomerProductQuote` لكل
  (زبون، منتج) **إن لم يوجد** (`get_or_create`، لا يكتب فوق قيمة موجودة) — فيظهر السعر في
  خيارات الفاتورة وكرت الزبون (يعالج «ما بين بالخيارات»). + حقل قراءة `product_name` على
  `SalesQuotationLineSerializer` لعرض البنود.
- **`core.pricing.resolve_sales_price`**: مصدر جديد `SALES_QUOTATION` بين «آخر بيع» و«عرض كرت
  الزبون» (يُستخدم حين لم يشترِ العميل المنتج) — يعيد `document_id/document_number` للربط.
  الأولوية: آخر بيع ← عرض واجهة العروض ← عرض كرت الزبون ← شريحة السعر.
- **`customer_price_list`** (يغذّي شرائح خيارات الفاتورة + تبويب كرت الزبون): أُضيف مصدر
  `SalesQuotation` (أحدث سطر لكل منتج) بنفس الأولوية — فيظهر سعر العرض في الخيارات **حتى
  للعروض القديمة** التي لم تُعبّئ كرت الزبون (كان يُظهر «بدون سعر» رغم أن الاختيار يجلب السعر).
- **`SalesQuotationsPage`**: زر «تعديل» كان يضبط `selectedId` فقط بلا تحميل
  (useRecordNavigation لا يُحمّل) ⇒ لم تظهر البنود؛ استُخرجت `openQuotation(id)` تُحمّل وتفتح
  النموذج (تخدم تعديل + رابط `?open=<id>` العميق). + **معاينة البنود داخل القائمة**:
  رقم العرض (▸/▾) يطوي/يفتح صفّاً يعرض بنود العرض (الصنف/الكمية/السعر/الإجمالي) بلا فتح
  النموذج — البنود «واضحة من برا». + سحب سعر كرت الزبون عند اختيار المنتج (من الجولة السابقة).
- **`SalesInvoiceEditor`**: شارة «من عرض السعر» تميّز `sales_quote` (تفتح `/sales/quotations?open=`)
  عن `quote` (تفتح تبويب عرض السعر بكرت الزبون) عبر `priceSourceLink` على السطر (يُضبط من
  مصدر الـresolver). تتبّع `invoice.open_quote`.
تحقّق: **sales 62 ناجح** (+`test_quotation_pricing_link`: تعبئة كرت الزبون بلا كتابة فوقه +
أولوية SALES_QUOTATION) · `tsc` نظيف لملفاتي (خطآ DepartmentCard/Breadcrumb سابقان).

## [AUDIT — إصلاح فشل إنشاء عرض السعر (رقم/عملة/ضريبة/tenant), 2026-07-04]
بلاغ المالك: إنشاء عرض سعر يفشل دائماً برسالة إنجليزية:
«This field is required.; This field is required.; {"tax_rate":["Invalid pk \"0\"…"]}».
التشخيص: الإنشاء **معطوب كلياً** (لم ينجح قط) لأربعة أسباب متسلسلة:
- `quotation_number` مطلوب ولا يُولَّد (لا واجهة ولا `perform_create`) ⇒ «required».
- `currency` مطلوب والواجهة لا ترسله (لا منتقي عملة) ⇒ «required».
- الواجهة ترسل `tax_rate: 0` وهو مفتاح أجنبي لنسبة ضريبة (السطر nullable) ⇒ «Invalid pk 0».
- `SalesQuotationSerializer.create` ينشئ السطور بلا `tenant` (NOT NULL) — عيب كامن لم يُبلَغ
  إذ كان الفشل يقع أبكر على التحقق.
الحل الجراحي (خادمي = مصدر حقيقة واحد لكل العملاء + إصلاح الواجهة للحمولة):
- **`sales.services.next_quotation_number`** (جديد، thin wrapper حول `next_document_number`
  بنوع `sales_quotation`، بادئة `QUO-`) — تسلسل مستقل للعروض، يُولَّد خادمياً.
- **`SalesQuotationSerializer`**: `quotation_number`/`currency` صارا `required=False`؛ و`create`
  يولّد الرقم إن غاب، ويفترض العملة الأساسية (`IsBaseCurrency`) إن غابت، ويمرّر `tenant` للسطور.
- **`SalesQuotationsPage.handleSave`**: `tax_rate` = `null` بدل `0` عند الغياب/الصفر، واستبعاد
  البنود بلا منتج + منع الحفظ بلا بند صالح (رسالة عربية).
تحقّق: **sales 59 ناجح** (+`test_quotation_create`: إنشاء بلا رقم/عملة + بند بلا ضريبة +
تسلسل أرقام فريد) · `tsc` نظيف لملفي (خطآ DepartmentCard/Breadcrumb سابقان).

## [FEAT — ملاحظات/تذكيرات الزبون (CRM) + جرس إشعارات الموقع, 2026-07-04]
طلب المالك: تبويب «ملاحظات الزبون» في بطاقة الزبون لإضافة ملاحظات وتذكيرات ليوم
محدد؛ عند حلول اليوم يظهر تذكير في إشعارات الموقع، والنقر عليه يفتح تفاصيل الملاحظة.
اكتشاف مهم: جرس الإشعارات (`NotificationCenter`) كان **غير مركَّب** أصلاً — `Header`
كود ميت، و`AppLayout` (القشرة الحيّة) بلا جرس ⇒ لا إشعارات مرئية.
البنية (خادمي = مصدر حقيقة، على نمط Django/DRF؛ الإشعار نفسه عبر شِمّ Firestore الحالي):
- **`partners.CustomerNote`** (model + migration `0007_customer_notes`): tenant/partner FK،
  title/body، `remind_on` (اختياري)، `is_done`، `created_by`. فهارس (tenant,partner,-created)
  و(tenant,is_done,remind_on).
- **`CustomerNoteViewSet`** (منطاق بالشركة، فلتر `?partner=`) + إجراء `reminders-due/` يُعيد
  الملاحظات غير المنجزة `remind_on<=today` لمولّد الإشعارات. Logging غير حظري على الإنشاء.
- **الواجهة:** `services/customerNotesApi.ts` (CRUD+due)، `components/partners/CustomerNotesTab.tsx`
  (خط زمني احترافي: إضافة/إنجاز/حذف + شارات حالة متأخر/اليوم/غداً/بعد N/منجز)، تبويب جديد في
  `PartnerProfilePage` (عملاء فقط، تبويب مُتحكَّم به عبر `activeTab/onTabChange`).
- **الإشعارات:** `services/customerNoteReminders.ts` (يُنشئ إشعاراً لكل تذكير مستحق، dedupe
  عبر localStorage لكل (شركة،ملاحظة،يوم))، مربوط في حلقة تذكيرات `App.tsx` بجانب الشحنات.
  `NotificationCenter` عند النقر يخزّن `targetTab/targetSecondaryId` في sessionStorage قبل
  التنقل، و`PartnerProfilePage` (effect على `location.key`) يقرؤها فيفتح تبويب الملاحظات
  ويحدّد الملاحظة. `AppNotification` أُضيف له `targetTab?`/`targetSecondaryId?` +
  نوع `customer_note_reminder`.
- **`AppLayout`**: رُكِّب جرس `NotificationCenter` في الشريط العلوي (كان مفقوداً).
- **إصلاحان ظهرا بعد تركيب الجرس (لم يُختبَرا سابقاً):** (1) `subscribeToNotifications`
  كان يستعلم `where("userId","in",[...])` لكن شِمّ الـ mapper لا يدعم `in` ⇒ يُنتج
  `userId__exact=«a,b»` فلا يطابق شيئاً ⇒ **لا تظهر أي إشعارات**. الحل: جلب إشعارات الشركة
  (منطاقة بالـ tenant) والفلترة محلياً (`userId===me || "all_managers"`). (2) المولّد كان
  يعمل عند الإقلاع/كل 6س فقط ⇒ ملاحظة أُنشئت بعد التحميل لا تُشعِر إلا بإعادة تحميل ⇒
  `CustomerNotesTab` يستدعي المولّد فور إنشاء ملاحظة تذكيرها اليوم/فائت (dedupe يمنع التكرار).
تحقّق: **partners 3 اختبارات جديدة** (إنشاء+عزل شركة+reminders-due) · **الحزمة الكاملة 182 ناجح**
· `tsc` نظيف لملفاتي (خطآ DepartmentCard/Breadcrumb سابقان). (خلف الدخول ⇒ لا تحقّق بصري.)

## [AUDIT — تحويل عرض السعر إلى فاتورة يفشل + توحيد لغة الأخطاء بالعربي, 2026-07-04]
بلاغ المالك: حفظ العرض ينجح، لكن «تحويل» إلى فاتورة يرمي خطأً إنجليزياً:
«customer: Incorrect type. Expected pk value, received Partner.; currency: … received Currency.».
التشخيص — عيبان متسلسلان في `convert_quotation_to_invoice` (لم ينجح التحويل قط):
- الخدمة تمرّر **كائنات** (`quotation.customer`/`.currency`) إلى `SalesInvoiceSerializer`
  وحقولها `PrimaryKeyRelatedField` ⇒ تتوقّع pk. وكذلك `tenant` مُمرَّر داخل الـ data
  بينما ليس حقلاً على الـ serializer ⇒ كان سيسقط ويُفشل `create` بـ KeyError بعد التحقق.
- بعد ذلك يظهر عيب ثانٍ: FSM في `SalesQuotation.save` يمنع `draft → converted`، بينما
  الخدمة **والواجهة** تسمحان بتحويل مسودة مباشرة ⇒ تناقض.
الحل الجراحي (خادمي):
- **`convert_quotation_to_invoice`**: تمرير `customer_id`/`currency_id` (pk)، وحقن
  `tenant`/`created_by` عبر `save()` تماماً كما يفعل `SalesInvoiceViewSet.perform_create`
  (مصدر حقن واحد، DRY).
- **`SalesQuotation._assert_valid_workflow_transition`**: إضافة `CONVERTED` للانتقالات
  المسموحة من `DRAFT` (مطابقةً لعقد الخدمة/الواجهة).
- **`core.settings.LANGUAGE_CODE = 'ar'`**: العربية اللغة الفعّالة ⇒ رسائل DRF/Django
  القياسية (حقل مطلوب/فارغ/عدد صحيح…) تُترجَم من الكتالوج المرفق (لا LocaleMiddleware).
تحقّق: **sales 65 ناجح** (+`test_quotation_convert`: تحويل مسودة→فاتورة بحقول pk صحيحة
+ ثبات idempotent) · لا اختبار يعتمد على رسائل DRF الإنجليزية (لا انحدار).

## [AUDIT — عرض السعر: تعبئة سعر الزبون في العرض + شارة قابلة للنقر بالفاتورة, 2026-07-03]
بلاغ المالك: (1) عند إنشاء عرض سعر بقائمة العروض واختيار الزبون ثم المنتج — إن كان له سعر
بكرت الزبون يُجلب تلقائياً. (2) في فاتورة المبيعات، النقر على «عرض السعر» يفتح عرض السعر
(كرت الزبون). الحل جراحي Frontend بحت (يعيد استخدام endpoints قائمة — لا Backend/migration):
- **`SalesQuotationsPage`**: عند اختيار العميل يُجلب `getCustomerPriceList` إلى خريطة
  `customerPriceMap` (product→price)، ودالة `quotePriceFor(id, fallback)` تُقدّم سعر كرت
  الزبون (عرض السعر اليدوي/آخر فاتورة) على السعر الافتراضي عند اختيار المنتج (المنتقي + مودال
  الفهرس). تتبّع `quotation.customer_price_applied`.
- **`SalesInvoiceEditor`**: شارة «من عرض السعر» (priceSource==="quote"، مصدرها
  `CustomerProductQuote`) صارت زراً يفتح `/partners/{customerId}?tab=price_list` عبر
  `openInNewTab` (لا يضيّع المسودة). تتبّع `invoice.open_customer_quote`. (فواتير البيع لا
  تسحب السعر من وثيقة `SalesQuotation`، بل من كرت الزبون — فالوجهة تبويب «عرض السعر» هناك.)
- **`PartnerProfilePage`**: يقرأ `?tab=` من الرابط ويمرّره `initialTab` لـ `AseelDocumentShell`
  (يدعمه أصلاً) — فيفتح مباشرةً على تبويب «عرض السعر» (`price_list`، للعملاء فقط).
تحقّق: `tsc --noEmit` نظيف لملفاتي (خطآ DepartmentCard/Breadcrumb سابقان). (خلف الدخول +
خادم بعيد — لا تحقّق بصري، مطابقةً للنهج.)

## [AUDIT — سند القبض متعدد الفواتير: قيد مستقل لكل فاتورة, 2026-07-03]
بلاغ المالك: سند قبض واحد يغطّي عدّة فواتير كان يُنشئ **قيداً واحداً** — المطلوب **قيد
مستقل لكل فاتورة** (لا مجرّد تقسيم أسطر داخل قيد واحد).
الحل الجراحي (خادمي بحت — `sales.services.post_customer_payment`، لا تغيير واجهة):
- **قيد لكل فاتورة**: بدل قيد واحد (مدين صندوق كلّي + سطر ذمم كلّي)، يُبنى **قيد منفصل لكل
  فاتورة**: `Dr صندوق (حصّتها) / Cr ذمم العميل (حصّتها) [+ فرق عملة إن لزم]`، وصفه
  «تحصيل/تسديد ذمم — فاتورة <رقم>». كل القيود بنفس `reference_type=CUSTOMER_PAYMENT` و
  `reference_id=payment.id` فيُصفّرها التراجع (`unpost_document` يحذف بالـreference) دفعةً
  واحدة. `payment.journal` (حقل مفرد) يشير لأول قيد للمرجعية.
- **`post_journal(idempotent=False)`** للقيود المتعددة (وإلا أعاد الفحص القيدَ الأول لوحدة
  الـreference). لتعويض حماية الترحيل المزدوج المفقودة: **قفل صفّ الدفعة**
  (`select_for_update`) وإعادة فحص `is_posted` داخل المعاملة الذرّية.
- **فرق العملة لكل فاتورة**: `cash = alloc.amount` (بعملة الدفعة، مجموعه = مبلغ الدفعة)، و
  `ar = قيمة الفاتورة محوّلة لعملة الدفعة`؛ فرقهما سطر فروقات عملة في قيد تلك الفاتورة
  (تفكيك دقيق لمنطق الـFX الكلّي السابق — نفس المجاميع). نفس العملة (الشائع) ⇒ لا فرق.
- فاتورة واحدة ⇒ قيد واحد (سلوك مطابق للسابق).
تحقّق: **sales/accounting/logistics 175 ناجح** (+`test_payment_split_per_invoice`: قيدان
لفاتورتين كلٌّ متوازن وموسوم بالعميل بمجموع 150 + قيد واحد لفاتورة واحدة). (فشل
`test_purchase_price_resolver::test_price_list_bulk_last_and_lowest` **سابق ومستقلّ** —
يفشل بعد ردّ تعديلاتي، خارج النطاق.)

## [AUDIT — كشف الحساب: نوع حركة واضح + نافذة «تفاصيل الحركة», 2026-07-03]
بلاغ المالك: في كشف حساب العميل عمود «المرجع» يعرض رمزاً خاماً (SALES_INVOICE) و«البيان»
يقول «ذمم» — غير واضح أهي فاتورة مبيعات/مشتريات أم تسديد. والمطلوب زر «تفاصيل» يفتح تفاصيل
الحركة: للمبيعات البنود المُباعة، وللدفعة تفاصيل ما سُدِّد.
الحل الجراحي (يعيد استخدام الجالبات القائمة — DRY، بلا نقطة نهاية جديدة):
- **تسمية عربية موحّدة** `utils/entityLinks.referenceTypeLabel(reference_type)` (نفس ملف مُحلِّل
  المراجع): SALES_INVOICE⇒«فاتورة مبيعات»، PURCHASE_INVOICE⇒«فاتورة مشتريات»،
  CUSTOMER_PAYMENT⇒«سند قبض»، SUPPLIER_PAYMENT⇒«سند صرف»، …، والباقي «قيد يومية». عمود
  «المرجع» صار «الحركة» يعرض التسمية + الرقم (يبقى قابلاً للنقر عبر `DocRefCell`).
- **توضيح «البيان»** `clarifyStatementDescription()` (نفس الملف): يستبدل مصطلح الحساب الخام
  في مقدّمة الوصف («ذمم — SI-1-6» ⇒ «فاتورة مبيعات — SI-1-6»، «تسديد ذمم — دفعة 4» ⇒
  «سند قبض — دفعة 4») ويُبقي رقم المستند في الذيل. تحويل وقت العرض (يشمل البيانات القديمة،
  بلا مساس بوصف القيد المُرحَّل). الفصل على em-dash «—» فقط (رقم الفاتورة يستخدم شرطة ASCII).
- **`components/partners/StatementDetailsModal.tsx`** (جديد): نافذة تصنّف السطر وتجلب تفاصيله:
  بيع⇒`getSalesInvoice` (البنود: الصنف/الكمية/السعر/الإجمالي)، شراء⇒`purchaseInvoiceApi.get`
  (نفس الأعمدة)، سند قبض⇒`getCustomerPayment` (المبلغ/التاريخ/التوزيع على الفواتير)، وغيرها⇒
  ملخّص + رابط «فتح المستند الكامل» إن توفّر مسار. تتبّع `statement.details_open`.
- **`PartnerProfilePage`**: عمود «تفاصيل» بزر يفتح النافذة (+ خلية فارغة إضافية في صف الإجمالي).
- **الخادم** `sales/serializers.SalesInvoiceLineSerializer`: حقل قراءة `product_name`
  (`SerializerMethodField ⇒ str(product)` = name_ar←name_en←sku، DRY) كي تظهر أسماء البنود
  المُباعة بلا نداء إضافي لحلّ الأسماء بالواجهة. سطور الشراء تحمل الاسم أصلاً.
تحقّق: **sales+partner_statement 58/58** (+`test_statement_details`: السطر يحمل `product_name`)
· `tsc` نظيف لملفاتي (خطآ DepartmentCard/Breadcrumb سابقان). (خلف الدخول — لا تحقّق بصري.)

## [AUDIT — زر العين يحكم الربح الإجمالي + خيارات إظهاره في الإعدادات, 2026-07-03]
بلاغ المالك: (1) الربح الإجمالي في فاتورة البيع يظهر حتى وزر العين مطفأ — يجب أن يختفي
بإطفائها. (2) خيار في إعدادات المنصة: إظهار رمز العين (للإظهار/الإخفاء) أو لا — عند التعطيل
تختفي العين. (3) حين تختفي العين، خيار افتراضي: إظهار الأرباح/التكاليف للفاتورة أو لا.
الحل الجراحي (مصدر حقيقة واحد — DRY، محلي لكل متصفح كطبيعة العين):
- **`contexts/PriceVisibilityContext.tsx`** وُسِّع بحقلين محليَّين (localStorage): `showToggle`
  (إظهار زر العين، افتراضي **نعم** فيُحفظ السلوك الحالي) و`defaultVisible` (الظهور الافتراضي
  حين يُخفى الزر، افتراضي **لا** — الأأمن). الظهور الفعّال `visible = showToggle ? manualVisible
  : defaultVisible`. `usePriceVisibility` تُرجع افتراضات آمنة عند غياب المزوّد. تتبّع
  `prices.show_toggle`/`prices.default_visible`.
- **`components/layout/PriceVisibilityToggle.tsx`**: `if (!showToggle) return null` (تختفي
  العين كلياً)، وحُدِّث العنوان إلى «الأسعار والأرباح» (صار يحكمهما معاً).
- **`components/sales/SalesInvoiceEditor.tsx`**: صفّ «الربح الإجمالي» بات مشروطاً بـ
  `profitVisible` (`usePriceVisibility().visible`) قبل شرطه القائم `revenue>0 && cogs>0`
  ⇒ يتبع العين (والافتراضي عند إخفائها). وأيضاً تم ربط زر الطباعة بنافذة جديدة (SalesInvoicePrintView) لطباعة الفاتورة بشكل نظيف دون الواجهة.
- **`components/sales/SalesInvoicePrintView.tsx`** (جديد): نافذة طباعة مخصصة للفواتير المبيعات (Printable Layout) تخفي التنبيهات والأدوات وتعرض بيانات الفاتورة فقط.
- **`components/procurement/invoices/InvoiceForm.tsx` & `deals/DealForm.tsx`**: تم ربط زر الطباعة و(F2) فيهما بنوافذ الطباعة المخصصة القائمة (`InvoicePrintView` و `DealPrintView`) لمنع طباعة شاشة التحرير بأكملها.
- **`components/SettingsPage.tsx`** (إعدادات المنصة): قسم جديد «خصوصية الأسعار والأرباح» —
  خانة إظهار زر العين، وعند تعطيلها تظهر خانة «إظهار الأرباح والتكاليف افتراضياً».
تحقّق: `tsc --noEmit` نظيف لملفاتي (خطآ DepartmentCard/Breadcrumb سابقان). (خلف الدخول +
لا إطار اختبار React — لا تحقّق بصري، مطابقةً للنهج المعتمد.)

## [AUDIT — رسائل داخل الموقع + منع فتح سطر تلقائي + منع فاتورة الخسارة, 2026-07-02]
ثلاثة بلاغات للمالك عُولجت جراحياً:

1. **رسائل المتصفح المنبثقة ⇒ داخل الموقع** — بُني نظام Toast موحّد (Shared/Core):
   `frontend_v2/contexts/ToastContext.tsx` (`useToast()` → `toast(msg, 'success'|'error'|'info')`،
   إخفاء تلقائي غير حظري 4s، Tailwind فقط) مُركَّب في `index.tsx` داخل `ConfirmProvider`.
   حُوِّل محرّرا الفاتورة (حيث يقع البلاغ): `procurement/invoices/InvoiceForm.tsx` (alert⇒toast،
   window.confirm⇒`useConfirm`) و`sales/SalesInvoiceEditor.tsx` (5 confirm⇒`useConfirm`؛ الأخطاء
   تستخدم بانر `localErr` القائم). بقية الـ~190 موضعاً في 59 ملفاً تُحوَّل تدريجياً لاحقاً.
2. **فاتورة الشراء تفتح سطراً فارغاً عند اختيار صنف** — أُزيل الإلحاق التلقائي للسطر الفارغ في
   `InvoiceForm.applyItemAt` (كان يُضيف سطراً بعد ملء الأخير). السطر يُضاف الآن يدوياً بزر «أضف صف»
   أو من الشجرة. لم تُمَس فاتورة المبيعات (لا feature creep).
3. **منع فاتورة البيع بخسارة (إعداد اختياري)** — `SalesSettings.block_loss_invoices` (migration
   `sales/0020`، معطّل افتراضياً). حارس خادمي `sales.services._guard_loss_invoice` في
   `post_sales_invoice` (بعد قفل الأصناف) يرفع ValidationError إذا `invoice_gross_profit < 0`
   (الإيراد الصافي − كمية×متوسط التكلفة، مصدر حقيقة واحد يطابق `invoice_profits`+قيد COGS). محصور
   بفواتير البيع (لا المراجيع). حارس عميل مطابق في `SalesInvoiceEditor` (حفظ+ترحيل) عبر
   `lossBlockMessage()`. واجهة الإعداد في `SalesSettingsPage` (قسم السلوك). اختبار:
   `sales/tests/test_block_loss_invoice.py` (3).
تحقّق: **backend 90/90 (sales+accounting) ناجح** · `tsc` نظيف على الملفات المعدّلة (لا أخطاء جديدة).

## [AUDIT — فصل عرض الصفقة عن إدخالها وتعديلها (Surgical View), 2026-07-02]
بلاغ: عرض الصفقة غير إدخالها وتعديلها. العرض يجب أن يكون مرتباً وغير مخربط (نظيف).
الحل الجراحي (Simplicity First):
- **`DealManagement.tsx`**: تم فصل حالة `viewMode` إلى `list`, `view`, `form`. عند فتح صفقة عبر الرابط (`/deals/:id`) أو الضغط المزدوج تفتح في وضع `view` بدلاً من `form`.
- **`DealPrintView.tsx`**: مكون موجود ومرتب جداً يشبه المستند. تم إعادة استخدامه كواجهة العرض الأساسية في `DealManagement` عندما تكون `viewMode === 'view'`.
- تم إزالة فئات التراكب `fixed inset-0 z-50` من `DealPrintView` ليصبح مكوناً أساسياً ضمن الشاشة، وتغيير أزرار التحكم من `fixed` إلى `absolute` للتوافق.
- تم ربط زر «تعديل البيانات» الموجود داخل واجهة العرض لينقل المستخدم بسلاسة إلى وضع التعديل (`form`).
تحقّق: نجاح `tsc --noEmit` للواجهة الأمامية.


## [AUDIT — إخفاء أسعار القوائم (آخر/أقل سعر) بزر خصوصية عام, 2026-07-02]
بلاغ المالك: شرائح «آخر سعر/أقل سعر» في قائمة اختيار الصنف (مبيعات ومشتريات) تظهر دائماً —
أريدها **مخفية افتراضياً** وأتحكّم بإظهارها/إخفائها بزر، كي لا يراها الزبون الجالس أمامي.
الحل الجراحي (نقطة تحكّم واحدة — DRY):
- **السعر يُرسم في مكوّن واحد مشترك** `AseelAutocomplete` (شريحة `opt.price`/`opt.priceLabel`)
  يخدم المبيعات والمشتريات معاً ⇒ بوابة واحدة تكفي. لا مسار رسم ثانٍ (أعمدة «آخر شراء» في
  `SupplierRelatedItems`/`RelatedSuppliers` شاشات موردين منفصلة، خارج النطاق).
- **`contexts/PriceVisibilityContext.tsx`** (جديد، على نمط `ThemeContext`): `visible` + `toggle`،
  **الافتراضي مخفي** (الأأمن للخصوصية)، مخزّن في `localStorage` (`ktra_prices_visible`) فيثبت
  بين الجلسات. `usePriceVisibility` تُرجع «مخفي» عند غياب المزوّد (لا ترمي استثناءً). تتبّع
  `clientLogger.info('prices.visibility')`.
- **`components/layout/PriceVisibilityToggle.tsx`** (جديد): زر Eye/EyeOff في الشريط العلوي
  بجانب `ThemeToggle` (نفس التنسيق) — يبدّل الحالة العالمية.
- **`AseelAutocomplete`**: يستهلك `usePriceVisibility`؛ عند الإخفاء لا يُرسم أي شريحة سعر
  (`!showPrices ? null : …`) — الاسم/السطر الثانوي/الرصيد يبقون.
- **التوصيل**: `PriceVisibilityProvider` يلفّ التطبيق في `index.tsx` (داخل `ThemeProvider`).
تحقّق: `tsc --noEmit` نظيف لملفاتي (خطآ DepartmentCard/Breadcrumb سابقان) · بناء الإنتاج ناجح
(SW+manifest). (لا إطار اختبار React بالمشروع؛ الشاشة خلف الدخول — لا تحقّق بصري، مطابقةً للنهج.)

## [AUDIT — رفع الوسائط الموحّد عبر الخادم + داتا شيت في كرت المنتج, 2026-07-02]
بلاغ المالك: أريد رفع ملفات «داتا شيت» من كرت المنتج إلى Cloudinary وتخزين الرابط في SQL،
و**أي رفع من الآن** يذهب لحساب Cloudinary الجديد (السرّ `mISroKaSW9B4ehHB…`، سحابة `dd63wjj5x`).
التشخيص: البيانات الجديدة كانت مضبوطة أصلاً على الخادم (`settings.CLOUDINARY_STORAGE`) لكن
الواجهة (`cloudinaryService.ts`) كانت ترفع **بلا توقيع إلى سحابة قديمة** (`dc66alhhk`/preset
`kitra_66`). السحابة الجديدة لا preset غير موقّع لها، والسرّ للرفع **الموقّع** الذي يجب أن
يبقى على الخادم فقط. لذا الحل الصحيح والوحيد الآمن = رفع موقّع عبر الخادم.
الحل الجراحي (نقطة اختناق واحدة — DRY):
- **`core/media_views.py`** (جديد): `POST /api/media/upload/` (حقل `file`) — يرفع عبر
  `cloudinary.uploader.upload` بالبيانات المضبوطة على الخادم ويعيد `{url}`. مفتوح (AllowAny،
  `authentication_classes([])` لتفادي CSRF الجلسة) لأن `PublicGallery` يرفع بلا دخول — وليس
  تراجعاً أمنياً (الـ preset السابق كان مفتوحاً للعالم أصلاً؛ الآن السرّ مخفي + حدّ حجم 25MB
  + نوع مورد: image للصور/raw للـPDF). مسجّل في `core/urls.py`.
- **`frontend_v2/services/cloudinaryService.ts`**: `uploadFile` صار يمرّ عبر `apiPostFormData`
  إلى `media/upload/` بدل النداء المباشر للسحابة القديمة. **كل** مواقع الرفع (~10: صور المنتج،
  الموردون، الصفقات، المهام، المعرض…) تستخدم السحابة الجديدة تلقائياً بلا لمسها (نفس التوقيع/الـ
  aliases محفوظة). السرّ لم يعد في الواجهة إطلاقاً.
- **داتا شيت المنتج** (`ItemFormAseel`): قسم رفع في تبويب «بيانات عامة» — يرفع الملف، يعرض
  القائمة (روابط قابلة للفتح + حذف من القائمة)، ويرسل `datasheet_urls` في حمولة الحفظ. يُحمّل
  الموجود من `product.attachments` (لا يُنسَخ عند التكرار).
- **`inventory/views.py::_handle_attachments`**: أُعيد تجريده لدالة `_save(url, file_type)`
  واحدة (DRY مع الصور) + يلتقط `datasheet_url`/`datasheet_urls` ⇒ `SystemAttachment`
  بنوع `Datasheet` (بنفس منع التكرار). الـserializer يُصدّر `attachments` بنوعها أصلاً.
- **حذف الداتا شيت المحفوظ (تحديث لاحق):** المواصفات الفنية تُحدَّث باستمرار فلزم مسح الملفات
  القديمة (منعاً لتراكم «ميت» في SQL وCloudinary):
  - **`ProductViewSet.remove_datasheet`** — `DELETE products/{id}/datasheets/{att_id}/`:
    يحذف صف `SystemAttachment` (مقيّد بـ tenant/المنتج/نوع Datasheet عبر `get_object`) +
    حذف **أفضل-جهد** لأصل Cloudinary. لا يُحذف من سحابة إلا ما يملكه المنتج ⇒ لا نقطة حذف
    مفتوحة (بخلاف الرفع العام).
  - **`core/media_views.py`**: `destroy_cloudinary_asset(url)` + `_parse_cloudinary_ref`
    (يستخرج public_id/resource_type من الرابط — `raw` يُبقي الامتداد، `image` يُزيله). فشل
    Cloudinary لا يُسقط العملية (SQL هو المصدر الموثوق).
  - **الواجهة**: `form.datasheets` صارت `{id, url}[]` (المحفوظ له id، المرفوع حديثاً `null`+
    وسم «غير محفوظ»). زر الحذف: id⇒`inventoryApi.removeDatasheet` (خادم)، وإلا إزالة من القائمة.
    بعد الحفظ يُعاد جلب المنتج لمزامنة الـids (فيعمل الحذف الخادمي فوراً بلا إعادة تحميل).
تحقّق: **backend 182 اختباراً ناجح** (+9 جديد: رفع PDF/صورة بنوع المورد + غياب الملف=400 +
تحليل رابط raw/image/غير-Cloudinary + مسار داتا شيت⇒create + الحذف يستدعي destroy+delete + 404
عند الغياب) · `makemigrations --check` بلا تغييرات · `manage.py check` 0 · `tsc` نظيف لملفاتي
(خطآ DepartmentCard/Breadcrumb سابقان). (خلف الدخول + خدمة خارجية — لا تحقّق بصري؛ Cloudinary
مُموّه في الاختبار.)
ملاحظة: السرّ ما زال قيمة افتراضية مكشوفة في `settings.py:284` (سابق لهذا التعديل) — يُفضّل
نقله للبيئة فقط لاحقاً.

## [AUDIT — إصلاح الاتصال العالق: كروم يفتح الواجهات بلا بيانات (يعمل بالتصفّح الخفي فقط), 2026-07-02]
بلاغ زبون: على كروم تفتح الواجهات لكن **بلا بيانات** ورسالة «تعذر الاتصال بالخادم
(شبكة/CORS)» لكل الأقسام؛ يعمل في متصفح آخر و**في التصفّح الخفي**. التشخيص: حالة عالقة في
ملف تعريف المتصفح (نسخة Service Worker قديمة و/أو Cache Storage قديم و/أو اتصال HTTP/3/QUIC
معطوب على النطاق الفرعي للـ API `api.smart.ktragroup.com`) — والخفي يبدأ نظيفاً فيعمل. الـ
SW لا يخزّن الـ API (يتخطّى عابر الأصل، `sw.ts:50`) فالبيانات ليست قديمة؛ المشكلة **اتصال
عالق** لا بيانات بائتة. إعادة المحاولة القائمة (`restApi.apiFetch`) تعيد على نفس الاتصال
المعطوب فلا تشفي.
الحل الجراحي (مكافئ «التصفّح الخفي» بضغطة، مصدر واحد DRY):
- **`utils/connectionRecovery.ts`** (جديد): `recoverConnection()` — إلغاء تسجيل كل عمّال
  الخدمة + مسح كل Cache Storage ثم `location.reload()`. كل خطوة في try/catch مستقل +
  `clientLogger`. لا تمسّ `localStorage` (يبقى التوكن/الفرع ⇒ الدخول محفوظ).
- **`hooks/useOnlineStatus.ts`**: أُضيف `browserOnline` (رأي `navigator.onLine`). إذا
  `browserOnline=true` بينما نبض `/api/health/` يفشل (`online=false`) ⇒ الخادم غير قابل
  للوصول رغم وجود إنترنت = اتصال عالق يستدعي الإصلاح.
- **`components/offline/OfflineBanner.tsx`**: عند `serverUnreachable` (=`browserOnline`)
  رسالة أوضح + زر **«إصلاح الاتصال»** يستدعي `recoverConnection()` (بجانب «أعِد المحاولة»).
  موضع عام واحد يخدم كل الشاشات (بلا لمس صفحات فردية).
- **الخادم — `Cache-Control: no-store` على كل ردود الـ API** (`core/cache_control_middleware.py`
  `NoStoreAPIMiddleware`، مُسجّل في `settings.MIDDLEWARE` بعد التتبّع): يمنع المتصفح/الوسطاء
  من كبش ردود GET لبيانات مالية فتُعرض بيانات قديمة بعد التعديل/التراجع. يستخدم
  `add_never_cache_headers` (max-age=0, no-cache, no-store, must-revalidate, private) على
  مسارات `/api/` فقط. طُبّق في Django (لا الخادم الأمامي) لأن الاستضافة LiteSpeed مشتركة بلا
  صلاحية خادم — والحل portable. (شق تعطيل HTTP/3 على Nginx **غير قابل للتطبيق**: البيئة
  LiteSpeed/استضافة مشتركة؛ مشاكل شبكات محلية كسيلكوم عولجت سابقاً عبر DNS/VPN.)
- **أوفلاين للقراءة فقط (اختيار المالك)** — طبقة كاش عامة في نقطة الاختناق الوحيدة
  `restApi.apiGetList`: عند كل نجاح شبكة تُخزَّن القائمة في Dexie (`db.api_list_cache`،
  `version(3)`، مفتاح = URL+المستأجر+الفرع)، وعند **فشل الشبكة فقط** تُرجَع آخر نسخة محفوظة.
  للتمييز أُضيف `NetworkError` (يرميه `apiFetch` لفشل الشبكة/المهلة) فتُرمى أخطاء HTTP
  (401/500) كما هي ولا تُخفى بكاش قديم. يُغطّي **كل شاشات القوائم تلقائياً** (فواتير/عملاء/
  أصناف/حسابات… تمرّ كلها عبر `apiGetList`) بلا لمس أي صفحة. `no-store` لا يعطّله (يخصّ كاش
  HTTP للمتصفح لا IndexedDB). لا يشمل الكتابة: إنشاء/ترحيل المسودات يبقى يتطلّب اتصالاً
  (تفادي تعارضات مالية). ملاحظة: مفاتيح الكاش تتراكم عبر تركيبات الفلاتر (نصّية، أثر بسيط).
- **إصلاح بيئة اختبار الباك-إند (كانت لا تُبنى أصلاً)** — تتبّع `no such table: chartofaccounts`:
  السبب الجذري أن جداول أساسية (chartofaccounts, partners, tenants, journal_headers…) أُنشئت
  في `0001_initial` بـ **`managed=False`** (مطبّقة خارجياً على MySQL القديم، فلا يُصدِر Django
  لها CREATE TABLE)، ثم قُلبت لاحقاً إلى `managed=True` عبر `AlterModelOptions` (خيارات فقط،
  بلا DDL) — فعلى قاعدة اختبار SQLite جديدة الجداول لا تُنشأ، وعمليات كانت تُتخطّى صمتاً
  (AlterUniqueTogether تشير لحقل `tenant` غير موجود بعد) تنكشف. أي أن سلسلة الهجرات غير
  متّسقة لبناء نظيف (النماذج نفسها متّسقة، `managed=True`). **الحل المعزول (بيئة الاختبار فقط،
  بلا لمس أي ملف هجرة مُلتزم):** `core/test_settings.py` يعطّل الهجرات عبر `MIGRATION_MODULES`
  فيبني منشئ قاعدة الاختبار المخطط من النماذج مباشرةً (run_syncdb) — نمط قياسي للهجرات القديمة
  وأسرع. (النموذج الوحيد `managed=False` الباقي = `core.SystemAttachment`، جدول legacy غير
  مطلوب في الاختبارات ولم يكن يُنشأ أصلاً.)
تحقّق: `tsc --noEmit` — لا أخطاء جديدة (الخطآن في `DepartmentCard`/`Breadcrumb` سابقان لهذا
التعديل) · بناء الإنتاج ناجح (SW + manifest) · `manage.py check` 0 · سلوك الـ middleware
مُتحقَّق مباشرةً (`/api/*` ⇒ no-store، وغيرها لا يُمسّ، وHEAD كذلك) · **المجموعة الكاملة
`manage.py test --settings=core.test_settings` = 173 اختباراً ناجحة** (بعد أن كانت لا تُبنى)
بما فيها `core/tests/test_cache_control.py` الجديد.

## [AUDIT — تحوّل جذري: الأصناف = شجرة تصنيفات بأي عمق + تصنيف تلقائي من اسم المنتج, 2026-06-27]
بعد جولات، اتّضح نموذج المالك النهائي: **لا تجميع أوتوماتيكي بـ`variant_group`/المقاس**؛
التجميع = **شجرة التصنيفات نفسها (أب/ابن/حفيد... بأي عمق)** يبنيها المالك، والمنتجات أوراق
تحت تصنيفاتها. القاعدة: **لكل منتج تصنيف فرعي اسمه اسم المنتج** — يُنشأ تلقائياً.
- **إضافة منتج** (`ItemFormAseel`): «اسم المنتج» صار **منتقي** (`ValuePicker` + `GET products/names/`)
  — تختار موجوداً (لإضافة براند آخر) أو تكتب جديداً. «تحت أي تصنيف» = منتقي **الأب**.
  عند الحفظ: يبحث عن تصنيف اسمه = اسم المنتج ⇒ إن وُجد يحفظ تحته (بجانب إخوته)، وإلا
  **يُنشئ تصنيفاً فرعياً باسم المنتج تحت الأب المختار** ثم يحفظ. «البراند» يبقى (بين قوسين).
  حُذف حقل «المجموعة/المقاس» (`variant_group`) من النموذج. زر «تكرار» (براند آخر) يبقي
  الاسم والتصنيف ويفرّغ البراند ⇒ يُحفظ بجانب إخوته.
- **جدول الأصناف** (`GroupedItemsTable` أُعيد بناؤه): جدول **شجري recursive بأي عمق** من
  `treeCategories` (يُحمَّل عبر `getCategories`) — تصنيف أب/فرعي قابل للطيّ (سهم) + مجموع
  الكمية، والمنتجات أوراق. كبسة على أي تصنيف ⇒ الكرت المجمّع لكل ما تحته (recursive ids).
- **الشجرة** (`InvoiceCategoryTree`): الأوراق منتجات مباشرة (أُزيل تجميع `group_key`)؛ كبسة
  التصنيف ⇒ كرت مجمّع recursive (`descendantItemIds`) عند وجود `onShowGroup` (شاشة الأصناف)،
  وإلا طيّ/فتح (الفواتير/مدير التصنيفات).
- **الكرت المجمّع**: يعيد استخدام `GroupProfilePage` + نقاط `group-*` (بمعرّفات المنتجات).
- **تنظيف**: أُزيلت imports يتيمة من `CategoryPicker`. الباك-إند (`variant_group`/`group_key`)
  يبقى (يخدم تجميع الجرد الحالي) لكن لا تستعمله شاشة الأصناف.
تحقّق: **inventory 14/14** (+ نقطة `names`) · `tsc` نظيف · بناء ناجح. (خلف الدخول — لا تحقّق بصري.)

## [AUDIT — تجميع البراندات: المقاس أب/البراند ورقة + كرت مجمّع + إصلاح شجرة التصنيفات, 2026-06-27]
بلاغ المالك (محل عجل): (1) شجرة التصنيفات لا تسمح بإضافة أب/ابن/حفيد. (2) خانة براند
على المنتج تُجمّعه تلقائياً تحت مقاسه. (3) في واجهة/شجرة الأصناف: نقر «المقاس» (185/65/14)
⇒ كرت مجمّع لكل البراندات، ونقر البراند ⇒ كرته المفصول. (4) الجرد يعرض المقاس بتوتال
رصيد النظام مع سهم يفصّل كل براند.
الحل الجراحي (مصدر تجميع واحد — DRY):
- **السبب الجذري للشجرة:** `CategoriesManagement` فيه `editParent` بالـstate لكن **بلا أي
  `<select>` لاختيار الأب** ⇒ تُنشأ تصنيفات مسطّحة فقط. أُضيف عمود «الصنف الأب» + محرّر
  `parentSelect` (للجديد والتعديل) + ترتيب DFS بإزاحة حسب العمق + منع اختيار حفيدٍ أباً
  (cycle-safe عبر `descendantsOf`). الموديل `ProductCategory.parent` كان يدعم العمق أصلاً.
- **التجميع — `group_key` خادمي (مصدر حقيقة واحد):** `inventory/services.py::product_group_key`
  = مقاس الإطار `tire_size_key` (regex مرآة لـ `tireSizeKey` بالواجهة) إن وُجد، وإلا الاسم.
  فيتجمّع على **البيانات القائمة بلا هجرة** (البراند داخل الاسم). + حقل جديد
  **`Product.brand`** (migration 0011) للإدخال النظيف + `display_name` (الاسم+البراند).
  serializer يُصدّر `brand`/`group_key`/`display_name`.
- **الكرت المجمّع:** `product_group_profile(product_ids)` يجمع مؤشّرات كل البراندات (يعيد
  استخدام `product_profile` لكل عضو) + `product_stock_ledger`/`product_linked_invoices`
  عُمِّمت لتقبل `product_ids`. نقاط: `group-profile`/`group-ledger`/`group-invoices`
  (`?ids=1,2,3`، الواجهة تحسب الأعضاء من `group_key`، العزل بالشركة في الخدمة). صفحة
  **`GroupProfilePage`** (مسار `/product-group?ids=&name=`) تعيد استخدام
  `AseelDocumentShell`+`LedgerTable`: نظرة مجمّعة + البراندات + الفواتير + حركة مجمّعة.
- **شجرة الأصناف** (`InvoiceCategoryTree`): `renderItems` يجمع الأوراق حسب `group_key` —
  مقاسٌ بـ≥2 براند ⇒ عقدة «مقاس» قابلة للطيّ (نقرها ⇒ `onShowGroup` كرت مجمّع)، والبراندات
  أوراق تحته باسم العرض. مقاس بمنتج واحد ⇒ ورقة عادية. آمن في الفواتير (`onShowGroup`
  اختياري ⇒ النقر يطوي فقط).
- **الجرد** (`StocktakePage`): جدول السطور صار يعرض في وضع «الكل» عقدة «مقاس» (سهم طيّ +
  **توتال رصيد النظام لكل البراندات** + كرت مجمّع) والبراندات أسطر عدّ تحته؛ الأوضاع المقيّدة
  تبقى مسطّحة. أُعيد استخدام `tireSizeKey`/`group_key`. زر «إدراج كل الأصناف» يُبقي ترتيب
  المقاس فتتجاور البراندات.
- **النموذج** (`ItemFormAseel`): حقلان **منتقيان** (`ValuePicker` — اختر/أضف، DRY):
  «الصنف الفرعي/المجموعة» (`GET products/groups/`) و«البراند» (`GET products/brands/`).
- **تحديث (بعد مراجعة المالك — المجموعة الصريحة + قوسان + تجميع بالجدول):** المالك أراد
  «خانة البراند تنشئ صنفاً فرعياً يتجمّع تحته حتى لمنتج واحد، والبراند بين قوسين».
  - حقل جديد **`Product.variant_group`** (migration 0012): `product_group_key` يقدّمه على
    استخراج المقاس/الاسم ⇒ تحكّم صريح بالتجميع لأي صنف (مش العجال فقط). + `has_group`
    (serializer) يجعل عقدة المجموعة تظهر **حتى لمنتج واحد** بمجموعة صريحة.
  - `product_display_name` صار يضع البراند **بين قوسين**: «الاسم (البراند)».
  - **شجرة الأصناف + الجرد + الجدول**: عقدة المجموعة تظهر عند ≥2 عضو **أو** `has_group`.
  - **جدول الأصناف** (`GroupedItemsTable` جديد): استبدل `AseelDenseTable` في وضع الجدول —
    صفّ «مجموعة» قابل للطيّ + توتال الكمية + كرت مجمّع، بنفس الأعمدة/التنسيق (DRY). يحافظ
    على الفرز الخادمي والترقيم.
  - **تصحيح (بلاغ: «أول 2 نفس البراند مش مع بعض»):** (1) `product_group_key` أضيف له
    **البراند** كأولوية قبل الاسم (المجموعة الصريحة ← المقاس ← البراند ← الاسم) — فمنتجان
    بنفس البراند (≥2) يتجمّعان تلقائياً بلا إدخال «مجموعة». (2) عيب عرض: الجدول والجرد كانا
    يرسمان أعضاء المجموعة بأماكنهم الأصلية (متفرّقين) — أُعيد البناء ليمرّ على **المجموعات**
    (لا الصفوف) فتظهر الأعضاء **متجاورين** تحت رأسهم حتى لو متباعدين بالترتيب. الشجرة كانت
    سليمة أصلاً (تمرّ على المجموعات).
تحقّق: **inventory 47/47** (+9 TDD: استخراج المقاس، تجميع مقاسات/براندات، أسماء قديمة
مدمجة، الكرت المجمّع، عزل المستأجر، نقاط API) · sales 48 (لا انحدار، 95 إجمالاً) ·
`manage.py check` 0 · `tsc` نظيف · بناء الإنتاج ناجح. (الشاشات خلف الدخول — لا تحقّق بصري.)

## [AUDIT — الجرد: فلتر مراجعة متعدد الأوضاع (الكل/المعدود/غير المعدود/الفروقات), 2026-06-27]
بلاغ المالك: في قائمة الجرد كان الفلتر الوحيد «الفروقات فقط» — المطلوب إضافة فلتري
**المعدود** و**غير المعدود** مع إبقاء ميزة تحديد الأصناف (✓) للطباعة.
الحل الجراحي (`StocktakePage`):
- استُبدل `showOnlyVariance` (boolean) بـ **`filterMode: "all"|"counted"|"uncounted"|"variance"`**
  عبر `<select>` (افتراضي «الكل»). ثوابت `FILTER_OPTIONS` و`FILTER_PRINT_SUFFIX` على
  مستوى الموديول.
- **`matchesFilter(l)`** دالة مطابقة واحدة (DRY) يستهلكها **عرض الجدول** و**الطباعة**:
  معدود = خانة العدّ غير فارغة، غير معدود = صنف بلا عدّ، فروقات = الفرق ≠ 0. وضع «الكل»
  يُبقي الأسطر الفارغة (للإضافة)؛ الأوضاع المقيّدة تُخفيها.
- **ميزة التحديد محفوظة**: خانات (✓) لكل سطر + «تحديد الكل» تعمل كما هي؛ الفلتر مستقلّ عن
  التحديد (أُزيل الاقتران القديم الذي كان يُحدِّد أسطر الفروقات تلقائياً — الطباعة لا تزال
  تطبع الفروقات عبر `matchesFilter` عند غياب تحديد يدوي). تتبّع `clientLogger.info("stocktake.filter")`.
تحقّق: `tsc --noEmit` نظيف · بناء الإنتاج ناجح. (الشاشة خلف الدخول — لا تحقّق بصري.)

## [AUDIT — ربط المنتجات: «ذكر لمنتج» قابل للنقر ⇒ حركة المخزون, 2026-06-27]
بلاغ المالك: في قائمة الجرد اسم الصنف **غير قابل للنقر**، وأي ذكر لمنتج في الموقع يفتح
«نظرة عامة» بدل **«حركة المخزون»** المطلوبة. الموقع يجب أن يكون مترابطاً.
الحل الجراحي (مصدر حقيقة واحد — DRY):
- **`utils/entityLinks.ts`**: استُبدلت `productPath()` (كانت تُرجع `/items` — النظرة العامة)
  بـ **`productProfilePath(id, tab="ledger")`** ⇒ `/products/${id}?tab=ledger`. أي رابط منتج
  يفتح بطاقة الصنف على تبويب **حركة المخزون** مباشرة.
- **`ProductProfilePage`**: يقرأ `?tab=` من `location.search` ويمرّره كـ `initialTab`
  للـ `AseelDocumentShell` (الذي يدعمه أصلاً). القيم: `ledger|invoices|kpis`.
- **`StocktakePage`**: اسم الصنف في سطر الجرد صار **زراً قابلاً للنقر** يفتح بطاقة الصنف
  (كرت الصنف) — كان `<span>` ثابتاً بزر (i) منفصل فقط (الزر باقٍ كأيقونة صريحة).
- **`StockMovementsPage`**: رابط اسم الصنف كان يفتح `/items` (عام) ⇒ صار
  `productProfilePath(m.product)` (حركة مخزون الصنف).
- **`StockLevelsPage` · `InventoryValuationPage`**: اسم الصنف كان نصاً غير قابل للنقر ⇒
  صار رابطاً يفتح حركة مخزون الصنف (`stopPropagation` لئلا يتعارض مع نقر السطر).
- **`ItemsManagement`** (شاشة الأصناف + شجرة التصنيفات): رابط اسم الصنف و`onShowCard`
  كانا يفتحان `/products/${id}` (نظرة عامة) ⇒ صارا `productProfilePath(id)` (حركة المخزون).
- **`ProductCardModal`**: زر «البطاقة الكاملة» صار يفتح `productProfilePath(productId)`
  (حركة المخزون) بدل النظرة العامة.
- **`ProductCardModal` — استغلال المساحة (بلاغ المالك: الكرت نصفه فارغ):** أُضيف قسم
  **«حركة المخزون (آخر الحركات)»** داخل الكرت تحت المؤشّرات (يملأ الفراغ) عبر إعادة
  استخدام `LedgerTable`+`DocRefCell` (DRY) — يجلب آخر 8 حركات من
  `stock-ledger/?limit=8` (التاريخ/النوع/المستند القابل للنقر/وارد/صادر/الرصيد الجاري)
  + رابط «عرض الكل» للبطاقة الكاملة. يظهر في **وضع العرض فقط** (في وضع الإضافة للفاتورة
  تبقى حقول الكمية/السعر). عُرّض الكرت إلى 760px والجسم قابل للتمرير (`maxHeight:72vh`).
تحقّق: `tsc --noEmit` نظيف (exit 0) · بناء الإنتاج ناجح. (الشاشات خلف الدخول — لا تحقّق بصري.)

## [AUDIT — Purchase Invoice UI Auto-expanding Statement Column, 2026-06-26]
المشكلة المُبلَّغة: عمود "البيان" في فاتورة المشتريات كان يأخذ مساحة ثابتة وكبيرة نسبياً (`20%`) مما يهدر المساحة، والمطلوب أن يبدأ صغيراً ويتمدد مع الكتابة.
الحل الجراحي:
- **تحجيم ديناميكي (Dynamic Sizing):** تم التخلي عن العرض الثابت واستبدال الخلية العادية بـ `render` مخصص في `InvoiceForm.tsx`.
- **التمدد مع المحتوى:** تم تصغير عرض العمود إلى حد أدنى (`width: 1%` لـ `th`)، واستخدام خاصية `field-sizing: content` مع `width: max-content` للحقل `input` ليتمغنط عرضه حول محتواه. كما تم إضافة `size={Math.max(4, text.length)}` كبديل احتياطي (Fallback) للمتصفحات القديمة ليتمدد الحقل حرفياً مع كل ضغطة زر.
## [AUDIT — StocktakePage UI Space Utilization Fix, 2026-06-26]
المشكلة المُبلَّغة: في صفحة الجرد، المسافة بين اسم الصنف وحقول الإدخال بعيدة جداً مما يهدر مساحة الشاشة.
الحل الجراحي:
- **إعادة توزيع المساحات (Column Widths):** تم تغيير عرض أعمدة (رصيد النظام، الكمية المعدودة، الفرق) لتعتمد على النسب المئوية (`15%`, `25%`, `15%` على التوالي) بدلاً من قيم البكسل الثابتة الصغيرة، مما يستغل المساحة الفارغة ويجعل حقل إدخال الكمية أكبر وأقرب لاسم الصنف.
- **محاذاة زر المعلومات:** تم تغيير `justifyContent` من `space-between` إلى `flex-start` لاسم الصنف لكي يلتصق زر "معلومات الصنف" بالاسم مباشرة ولا يغوص في الفراغ.
## [AUDIT — Sales Invoice UI Fix: Default Payment & Customer Layout, 2026-06-26]
المشكلة المُبلَّغة: الفاتورة تفتح افتراضياً على "نقدي" بدل "أجل"، وكلمة "نقدي" تلتصق بكلمة "العميل" مما يربك المستخدم.
الحل الجراحي:
- **إزالة التجاوز التلقائي للإعدادات:** حُذفت الـ `useEffect` التي كانت تفرض `salesSettings.default_payment_type` (والتي غالباً ما تكون نقدي بسبب إعدادات قديمة) وجُعل الافتراضي الصارم هو `"credit"` عند إنشاء الفواتير.
- **تعديل التخطيط (Layout Swap):** تم تبديل موضع قائمة نوع الدفع (أجل/نقدي) ليكون بعد حقل اختيار العميل، بحيث تلتصق كلمة "العميل" بحقل اسم العميل مباشرة كما هو منطقي. تم تغيير تسمية "ذمم" إلى "أجل".
## [AUDIT — T-CASH2 (موردون): تسوية الشراء النقدي تلقائياً + إصلاح وسم الصندوق, 2026-06-26]
مرآة بلاغ البيع النقدي على جانب الموردين — **سببان جذريان** بنفس النمط:
1. **وسم خاطئ** في `sales.services.post_supplier_payment`: سطر الصندوق/البنك كان يُوسَم
   بالمورد (`partner=payment.partner_id`)، فتُحسب حركة النقدية ضمن ذمم المورد في كشف
   الحساب ⇒ سند الصرف لا يُصفّر رصيد المورد (يبقى منتفخاً). صار `partner=None` (فقط سطر
   الذمم AP يَحمل الشريك) — يُصلح كشوف الحسابات لكل سندات الصرف.
2. **Feature 2 ناقص** (شراء): فاتورة الشراء النقدية (`logistics`, `payment_type='cash'`)
   كانت تدائن ذمم المورد بالكامل دون أي تسوية نقدية ⇒ يبقى المورد دائناً للأبد. الأتمتة
   لم تُربَط قط (نفس فجوة البيع النقدي).
الحل:
- **`PurchaseInvoiceViewSet._auto_settle_cash_purchase`** (جديد، `logistics/views.py`) — بعد
  ترحيل قيد فاتورة **شراء نقدية**، يُنشئ ويُرحّل `SupplierPayment` بكامل قيمة الفاتورة
  (Dr ذمم المورد / Cr صندوق) ذرّياً ضمن نفس المعاملة عبر `post_supplier_payment`. يُتخطّى
  بأمان إن غاب حساب الصندوق. قيد الفاتورة لم يُمَس ⇒ `test_pi_subledger_routing` سليم.
- **ملاحظة (تلوّث subledger سابق، خارج النطاق)**: ترحيل فاتورة الشراء يَسِم **كل** السطور
  (المخزون/الوسيط GR-IR/الضريبة/الرسوم) بالمورد لا سطر الذمم فقط، فيلوّث `partner_posted_balance`
  للموردين. القياس الصحيح لرصيد المورد هو الحساب الرقابي AP تحديداً.
تحقّق: **165 اختبار** في `logistics/ sales/ accounting/` ناجح (+ اختبارا
`test_supplier_payment_zeroes_supplier_balance` و`test_cash_purchase_auto_settled_supplier_not_creditor`).

## [AUDIT — T-CASH2: تسوية البيع النقدي تلقائياً + إصلاح وسم الصندوق, 2026-06-26]
بلاغ المالك: عند اختيار «نقدي» يبقى العميل **مديناً** في كشف الحساب رغم أن البيع نقدي.
**سببان جذريان** اكتُشفا:
1. **Feature 2 ناقص** (`sales/services.py`): قيد الفاتورة لا يُسوّي النقدية (التحصيل سند
   مستقل) — لكن **الأتمتة لم تُربَط قط**، فبقي البيع النقدي مديناً للأبد.
2. **وسم خاطئ** في `post_customer_payment`: سطر الصندوق/البنك كان يُوسَم بالشريك، فيُحسب
   مدين الصندوق على العميل في كشف الحساب ⇒ التحصيل لا يُصفّر الرصيد (2000−1000=1000).

الحل (خادمي — مصدر حقيقة واحد لكل المسارات: UI/auto-post/API/استيراد):
- **`sales.services._auto_settle_cash_sale`** (جديد) — بعد ترحيل قيد فاتورة **بيع نقدية**،
  يُنشئ ويُرحّل CustomerPayment بكامل المتبقّي (Dr صندوق / Cr ذمم) ذرّياً ضمن نفس
  المعاملة. آمن للتكرار (يعتمد على `grand − amount_paid`). يُستدعى من `post_sales_invoice`.
  قيد الفاتورة لم يُمَس ⇒ `test_subledger_routing` سليم (التسوية قيد منفصل).
- **إصلاح الوسم والوصف**: سطر الصندوق في `post_customer_payment` صار `partner=None` (الصندوق ليس
  ذمماً للعميل) — يُصلح أيضاً كشوف الحسابات لكل سندات القبض اليدوية. كما تم تصحيح الوصف المحاسبي لسطر ذمم العميل من "تخفيض ذمم" إلى "تسديد ذمم".
- **واجهة** (`SalesInvoiceEditor`): حقل «المبلغ نقداً» يُعطَّل ويُملأ بالإجمالي تلقائياً
  للبيع النقدي (للعرض)، وتخطّي إرفاق السند المالي للفواتير النقدية (تُسوّى خادمياً).
- **أمر `backfill_cash_settlements`** (dry-run افتراضاً، `--apply` للتطبيق) — يُسوّي
  الفواتير النقدية المرحَّلة قديماً (الباقية مدينة) بإعادة استخدام نفس الدالة.
- **أمر `fix_legacy_cash_partner_tags`** (dry-run افتراضاً، `--apply`، `--tenant`) — إصلاح
  بيانات **أقدم**: البيع النقدي قبل Feature 2 كان يُرحّل «Dr صندوق (موسوم بالعميل!) / Cr
  إيراد» بلا سطر ذمم، فبقي سطر «تحصيل نقدي — <رقم>» مديناً على العميل بلا دائن مقابل ⇒ رصيد
  شبح لا يُصفَّر (بلاغ المالك: SI-6-2 لسا عليها 250). الأمر يلمس بالتوقيع فقط
  (`reference_type='SALES_INVOICE'` + وصف «تحصيل نقدي —» + شريك غير فارغ؛ الكود الحالي لا
  يُنتجه) فيُزيل وسم الشريك عن سطر الصندوق ويضبط `amount_paid = grand_total`. آمن للتكرار.
  ملاحظة: `backfill_cash_settlements` لا يصلحها (تشغيله يُضاعف النقدية). اختبار:
  `sales/tests/test_legacy_cash_partner_tag.py`.
تحقّق: **277 اختبار backend ناجح** (+ اختبار جديد `test_cash_sale_auto_settled_*`: رصيد
العميل الصافي = 0) · `tsc` نظيف.

## [AUDIT — G1 rollout: شاشات الكميات/المخزون, 2026-06-26]
المشكلة المُبلَّغة: صفحة الجرد (وبقية الشاشات) تعرض كميات بأصفار عشرية زائدة (`6.00000`).
الحل الجراحي — تمرير كل عرض رقمي عبر المُنسّق الموحّد `formatNumber.ts` (G1):
- **StocktakePage** — عمود «رصيد النظام» وملخّصات منتقي البحث كانت تعرض `quantity_on_hand`
  الخام (نص API بخمس منازل)؛ الآن عبر `formatQuantity` (مع `trimQty` للقيمة الغائبة ⇒ «—»).
  `trimNum` المحلي يُفوّض الآن إلى `formatQuantity` (مصدر حقيقة واحد، لا تكرار).
- **ProductProfilePage · ProductCardModal** — مؤشّرات البطاقة (`fmt2`/خام) كانت تثبّت منزلتين
  (`6.00`)؛ الآن كميات عبر `formatQuantity` وقيم مالية عبر `formatMoney` (حُذف `fmt2` اليتيم).
- **StockLevelsPage · StockMovementsPage · InventoryValuationPage · ItemsManagement ·
  AccountingLandedCostPage** — `fmt` المحلي (toLocaleString min:2) أُعيد تعريفه إلى
  `formatMoney`، وأعمدة الكمية حُوّلت إلى `formatQuantity`.
- **SalesQuotationsPage** — ملخّص «رصيد» في المنتقي عبر `formatQuantity`.
تحقّق: `tsc --noEmit` نظيف · سلوك `formatQuantity`: `6.00000⇒6`، `6.5⇒6.5`، `6.55⇒6.55`.
ملاحظة: الفاصل العشري نقطة (.) مطابقةً لكامل المنصة (لم يُغيَّر إلى فاصلة).

## [AUDIT — G1 تعميم شامل + تطبيع حقول الإدخال, 2026-07-06]
المشكلة المُبلَّغة (متكرّرة): الأصفار العشرية الزائدة «تعود بعد كل تعديل» و«تُصلَح بمكان وتُنسى بمكان». السبب الجذري: مصدرا trailing-zero منفصلان لم يمرّا عبر G1 — `.toFixed(2)` (95 موضعاً) و`.toLocaleString(…, {minimumFractionDigits:2})` (71 موضعاً) عبر ~50 ملفاً، إضافةً إلى **حقول الإدخال** التي تُربَط بنص API الخام (`value={row.unit_price}` ⇒ «110.0000»).
الحل الجراحي — توحيد كامل عبر `formatNumber.ts` (لا حِيَل لكل حقل):
- **حقول الإدخال (لبّ المشكلة):** تطبيع النص الرقمي **مرّة واحدة عند الترطيب من الـ API** (لا في كل رندر — ذلك يكسر الكتابة). في `SalesInvoiceEditor` (الكمية/السعر/الخصم + رأس الفاتورة: exchange/discount/percent/overrides/attached_cash في مساري الحفظ والمسودة + السعر المقترح)، و`Sales/PurchaseReturnEditor` (سعر مشتق من المنتج)، ومدفوعات العملاء/الموردين (setState لـ withholding/amount). عبر `formatQuantity`/`formatNumber({maxDecimals})`.
- **العرض:** استبدال كل `toFixed`/`toLocaleString(min:2)` العرضية بـ `formatMoney`/`formatNumber`/`formatQuantity` — شمل تقارير المحاسبة (ميزان/دخل/ميزانية/دفتر أستاذ/ض.ق.م/قيود/شيكات/أرباح فواتير)، قوائم وطباعة الفواتير والصفقات (InvoiceList/InvoicePrintView/NIS*/Deal*)، الشحنات/التخليص/الأقساط، وكرت الشريك/قوائم الأسعار. المُنسّقات المحلية لكل ملف (`fmt`/`fmtMoney`/`fmtAmt`…) فُوّضت إلى الطبقة المشتركة (مصدر حقيقة واحد).
- **لم يُمَسّ عمداً:** حسابات `Number(x.toFixed(2))`، وحمولات الـ API `String(x.toFixed(2))` (الـ backend يحتاج المنازل)، ومنسّقات الأعداد الصحيحة (min:0)، وأحجام الملفات KB/MB، وعملات 3-منازل (العقارات).
تحقّق: `tsc --noEmit` نظيف (عدا خطأين سابقين غير متعلّقين: DepartmentCard/Breadcrumb) · صفر `minimumFractionDigits:2` وصفر `toFixed(2)` عرضية متبقّية في `components`.

## [TECH_STACK]
- **Frontend:** React 19.2, TypeScript 5.8, Vite 6.2, Tailwind CSS 4.3, react-router-dom 7, date-fns 4
- **Backend:** Django 6.0.1 (latest stable 6.0.6, 2026-06-03; LTS 5.2.15), DRF 3.16, MySQL (prod), SQLite (test)
- **PWA/Offline:** vite-plugin-pwa 1.3, workbox-window 7.4, Dexie 4.4
- **Testing:** pytest-django (70 tests, SQLite via `core.test_settings`), Playwright (E2E, advisory in CI)
- **Logging (task8 M11):** `core/logger_middleware.py` request tracing + `client_logs` sink + console LOGGING config
- **Icons:** lucide-react · **Charts:** recharts
- **Version policy (2026-06):** stack is current; recommended optional patch: Django 6.0.1 → 6.0.6. No new deps planned for task9/task10.

## [SYSTEM_FLOW]
```
User → Browser → React SPA (App.tsx)
  ├─ Online ───→ REST API (Django) ──→ MySQL
  └─ Offline ──→ IndexedDB (Dexie) ──→ cachedApi wrapper
                    ↓
              mutation_queue → Background Sync (on reconnect)
```

## [ARCHITECTURE]
```
frontend_v2/
├── App.tsx                    # Root SPA routing (all views)
├── index.tsx                  # Entry point (BrowserRouter)
├── index.html                 # HTML shell + PWA manifest link
├── sw.ts                      # Service Worker (PWA)
├── vite.config.ts             # Vite + vite-plugin-pwa + Tailwind
├── public/
│   ├── site.webmanifest       # PWA manifest
│   ├── offline.html           # Offline fallback page
│   ├── android-chrome-512x512.png
│   ├── apple-touch-icon.png
│   ├── favicon-*.png / .ico
│   └── notification-sound.mp3
├── services/
│   ├── offline/
│   │   ├── db.ts              # Dexie IndexedDB schema
│   │   └── cachedApi.ts       # Stale-while-revalidate API wrapper
│   ├── restApi.ts             # Base HTTP client
│   ├── salesApi.ts            # Sales API
│   ├── clearanceApi.ts        # Clearance API
│   └── ...                    # Domain-specific APIs
├── hooks/
│   └── useOnlineStatus.ts     # Network heartbeat hook
├── components/
│   ├── offline/
│   │   ├── UpdatePrompt.tsx        # SW update toast
│   │   ├── OfflineBanner.tsx       # Global sticky banner
│   │   ├── StalenessBadge.tsx      # Per-record freshness pill
│   │   ├── OfflineGuard.tsx        # Post button wrapper
│   │   ├── StaleDataConfirm.tsx    # Pre-action cache warning modal
│   │   ├── PendingMutationsPanel.tsx
│   │   ├── SyncConflictModal.tsx
│   │   ├── StatusMessage.tsx       # WCAG 4.1.3 live region
│   │   └── OfflineCoachmark.tsx    # First-offline onboarding
│   ├── sales/                       # Sales domain
│   ├── procurement/                 # Procurement domain
│   ├── accounting/                  # Accounting domain
│   └── ...                          # Other domains
├── types.ts, types/           # TypeScript type definitions
├── contexts/                  # React contexts (Auth, Theme)
├── utils/                     # Utility functions
├── styles/                    # CSS (Tailwind entry)
└── constants/                 # App constants
```

## [AUDIT — task27, 2026-06-23] (تصدير الأصناف PDF + صفحة هبوط تعريفية للزوّار)

**المطلوب:** (1) تصدير جدول الأصناف **PDF للطباعة** بدل CSV. (2) الزائر غير العضو لا
يهبط مباشرة على نموذج الدخول — تظهر **صفحة هبوط احترافية** تعرّف بميزات المنصة (الاستيراد…)
مع زرّي دخول/إنشاء حساب.

- **(1) تصدير PDF (`ItemsManagement.tsx::exportProducts`):** استُبدل توليد CSV بنافذة طباعة
  (`window.open`+`window.print`) **بنفس نمط `StockLevelsPage.printPdf`** (DRY) — جدول RTL
  منسّق، عنوان بالمجموعة المختارة والعدد والتاريخ، تلوين «نفذ»/«منخفض». قائمة الخيارات
  (الكل / نفذ / المنخفضة) باقية كما هي وتجلب كل الصفحات المطابقة. الأيقونة `Printer`،
  التتبّع `clientLogger.info('items.export_pdf')`. (المالك اختار PDF للطباعة صراحةً.)
- **(2) صفحة الهبوط (`components/LandingPage.tsx` جديد):** `AuthView` أُضيف له `"landing"`
  وصار **الافتراضي**؛ في `App.tsx` فرع `!currentUser` يعرض: landing (افتراضي) → login →
  signup. الصفحة تعيد استخدام `PublicNavbar` + `LogoIcon` ولغة تصميم `LoginPage`
  (تدرّجات/داكن/RTL): Hero + شارات ثقة + شبكة 6 ميزات (الاستيراد والتخليص الجمركي، الفواتير،
  المخزون، المحاسبة، الأطراف، التقارير) + مزايا تقنية (PWA/عربي/تعدد شركات) + دعوة ختامية +
  تذييل. أزرار «تسجيل الدخول»→`setAuthView('login')` و«إنشاء حساب»→`'signup'`.
- **التحقق:** tsc نظيف · بناء الإنتاج ناجح (3451 modules) · تحقّق بصري: الصفحة تُعرض
  افتراضياً للزائر، وزر الدخول ينقل لنموذج الدخول (h2 + حقلا بريد/كلمة مرور) — بلا أخطاء console.
  (تنبيه بيئي: vite يستمع على 3001 لا منفذ الـ preview المُسنَد — لا علاقة بالكود.)

## [AUDIT — task26, 2026-06-23] (جدول الأصناف — ترتيب/فلتر حالة المخزون + تصدير بخيارات + إصلاح البحث)

**المطلوب:** في واجهة الأصناف (`ItemsManagement`): ترتيب حسب العمود (تصاعدي/تنازلي)،
فلتر يُظهر «نفذ» / «كمية منخفضة» فقط، تصدير CSV **بخيارات** (الكل / ما نفذ / المنخفضة)
بدل زر واحد يصدّر كل شيء، وإصلاح خلل البحث.

- **الخادم (`inventory/views.py::ProductViewSet`):**
  - فلتر جديد `?stock_status=out_of_stock|low_stock|in_stock` في `get_queryset` —
    **مطابق تماماً** لمنطق `ProductSerializer.get_stock_status` (نفذ ≤0 · منخفض >0 و
    حد أدنى>0 و ≤الحد الأدنى · متوفر الباقي) عبر `F('min_stock_level')`.
  - `min_stock_level` أُضيف إلى `ordering_fields` (كان غائباً) — العمود صار قابلاً للترتيب.
  - البحث/الترتيب/الترقيم الخادمي موجود أصلاً (search + OrderingFilter) — أُعيد استخدامه.
- **الواجهة (`ItemsManagement.tsx`):**
  - **الترتيب:** ربط أعمدة الجدول (sku/name_ar/qty/avg_cost/min) بخصائص الفرز الموجودة
    في `AseelDenseTable` (`onSort/sortKey/sortDir`) → يبني `ordering` خادمياً (نقرة=تصاعدي
    من الأدنى، نقرة ثانية=تنازلي). خريطة `ORDER_FIELD` عمود→حقل خادمي.
  - **الفلتر:** `<select>` حالة المخزون (كل/نفذ/منخفض/متوفر) → `stock_status` خادمي.
  - **التصدير بخيارات:** قائمة منسدلة (الكل / الأصناف التي نفذت / الكمية المنخفضة) تجلب
    **كل الصفحات المطابقة** (page_size=200 حلقة) وتنزّل CSV (BOM للعربية). تتبّع غير حظري
    عبر `clientLogger.info('items.export')` (إعادة استخدام، DRY).
  - **إصلاح البحث:** كان خادمياً عند Enter فقط مع متغيّر `filtered` **ميت غير مُستخدم** —
    أُزيل الكود الميت واستُبدل بمصدر تحميل واحد debounced (250ms) يتفاعل مع
    البحث/الفلتر/الترتيب/الصفحة؛ `load` أعيد إلى توقيع options، وأُضيف `reload()` للتحديث
    اليدوي/بعد الحفظ يحافظ على الفلاتر.
- **التحقق:** **inventory 37/37** (+5 TDD: فلتر out/low/in + ترتيب الكمية/الحد الأدنى) ·
  `manage.py check` 0 · tsc نظيف · بناء الإنتاج ناجح. (الشاشة خلف الدخول — لا تحقّق بصري.)

## [AUDIT — task25, 2026-06-23] (حارس اعتمادية التراجع عن الترحيل — منع إيتام القيود المبنية)

**المطلوب:** عند التراجع عن ترحيل مستند مُورِّد للمخزون (فاتورة شراء/شحنة/استلام)،
إن كانت مبيعات أو حركات صرف لاحقة قد استهلكت مخزونه وبَنَت تكلفتها (COGS) على
متوسط التكلفة المتضمِّن هذا المستند — **يُمنع التراجع** (لئلا تبقى قيود تكلفة
المبيعات يتيمة) مع **رسالة بقائمة المستندات المتأثّرة**.

- **الكشف (Core، DRY):** `inventory/services.py::find_stock_dependents(tenant_id,
  reference_id, reference_types)` — يحدّد أصناف المستند ذات الأثر المُورِّد (IN/
  ADJUST_IN/RETURN_IN)؛ مستند مستهلِك بحت (بيع/صرف) ⇒ لا تابعين. ثم يجمع حركات
  الصرف اللاحقة (OUT/ADJUST_OUT/RETURN_OUT، `id__gt` لأول حركة للمستند) على نفس
  الأصناف من مراجع أخرى، مجمّعةً حسب (reference_type, reference_id) مع تسمية
  مقروءة (`_dependent_label` يحلّ رقم فاتورة البيع للـ SALE/STOCK_ISSUE).
  - WAC-صحيح: كل المشتريات تذوب في متوسط واحد، فأي صرف لاحق يعتمد على هذا الرصيد.
- **الحارس (مركزي):** `accounting/services.py::unpost_document` — في بداية المعاملة
  الذرّية، إن وُجد `stock_reference_types` واكتُشف تابعون ⇒ `ValidationError` (إجهاض
  كامل، لا حذف) برسالة «… المتأثّرة: فاتورة بيع SI-… (الأصناف: …)؛ …». لا bypass
  (بطلب المالك). مستندات الاستهلاك (فاتورة بيع) تتراجع بحرّية كما كانت.
- **الرسالة النظيفة:** مُعالِجا التراجع للموردّين (فاتورة الشراء + الشحنة في
  `logistics/views.py`) يعرضان `e.messages` بدل `str(e)` (يتفادى تغليف `['…']`).
- **التحقق:** **accounting+logistics 97/97** + اختبارا TDD جديدان
  (`test_unpost_document`): منع تراجع شراء استهلكه بيع لاحق + سلامة الإجهاض،
  والسماح بالتراجع عن المستهلِك. inventory/sales-stock 35/35 (لا انحدار) ·
  `manage.py check` 0.

## [AUDIT — task24, 2026-06-23] (السعر المقترح داخل خيارات منتقي الأصناف — بلا نقر)

**المطلوب:** في منتقي الأصناف لفاتورتي المبيعات والمشتريات يظهر السعر المقترح
(آخر بيع/شراء أو عرض سعر أو الافتراضي) **داخل كل خيار مباشرة** مع تسمية مصدره،
دون الحاجة لنقر الصنف.

- **الطبقة المشتركة (DRY):** `frontend_v2/components/aseel/AseelAutocomplete.tsx` —
  حقلان اختياريان على الخيار `price`/`priceLabel` يُرسمان كرقاقة سعر خضراء في
  الصف (CSS `.aseel-autocomplete-price[-src]` في `styles/index.css`). موضع واحد
  يخدم الشاشتين.
- **المبيعات:** `SalesInvoiceEditor` يجلب `getCustomerPriceList(customer)` دفعة
  واحدة عند تغيّر العميل → خريطة `customerPriceMap` تغذّي `productOptions`:
  «آخر بيع»/«عرض سعر» للعميل، وإلا سعر البيع الافتراضي (`online_price`) بوسم
  «افتراضي»، وإلا نص رمادي **«السعر غير معرف»** (بطلب المالك — لا فراغ). (يُعاد
  الاستخدام من DEF-004، لا endpoint جديد.)
- **المشتريات:** endpoint جديد **bulk** يتفادى نداء resolve-price لكل صف:
  `core.pricing::purchase_price_list(tenant_id, strategy)` (آخر/أقل شراء حسب
  إعدادات الشراء ← متوسط التكلفة) + action `GET logistics/purchase-invoices/price-list/`
  + عميل `purchaseInvoiceApi.priceList()`. `InvoiceForm` يجلبها مرة → `purchasePriceMap`
  يغذّي `itemOptions` («آخر شراء»/«أقل شراء»/«متوسط التكلفة»، وإلا «السعر غير معرف»).
  - **معاينة أحادية العملة:** الرقاقة تعرض سعر سطر المصدر كما سُجِّل؛ تحويل العملة
    لكل سطر يبقى في `resolve_purchase_price` عند الاختيار الفعلي.
- **التحقق:** **logistics 11/11** (+3: bulk last/lowest، تجاهل المسودّات، endpoint) ·
  sales pricing 12/12 (لا انحدار) · `manage.py check` 0 · tsc نظيف · بناء الإنتاج ناجح.
  (الشاشتان خلف الدخول — لا تحقّق بصري.)

## [AUDIT — task23, 2026-06-21] (واجهة «تكلفة المنتجات» + تنبيه أثر السعر + إصلاح متوسط التكلفة)

**السبب الجذري (مؤكَّد):** متوسط التكلفة المعروض في بطاقة الصنف كان = إجمالي قيمة
الشراء ÷ الكمية الحالية المتبقية (مثال حقيقي 3800÷13=292.31)، متجاهلاً المباع. مصدره
**انحراف WAC المتحرك مع المخزون السالب** (`allow_negative_stock_default=True`): بيع 27
قبل وصول الشراء سجّل COGS=0 وكمية ‑27، ثم شراء 40 جعل المعادلة `((‑27×0)+(40×95))÷13`
= 3800÷13. المطلوب من المالك: نموذج جديد يُعرض في واجهة مستقلة (لا النموذج الحالي).

- **النموذج الجديد (تكلفة المنتجات):** سعر وحدة كل فاتورة = تكلفة الفاتورة ÷ كميتها،
  ثم تكلفة المنتج = **متوسط أسعار وحدات الفواتير مرجّحاً بكمية كل فاتورة** =
  Σ(تكلفة الفواتير) ÷ Σ(كميات الشراء). المقام إجمالي المشترى (لا الحالية) ⇒ لا يتأثر
  بالبيع. تكلفة الفاتورة تأخذ landed cost حين توفّره.
  - `inventory/services.py::product_cost_breakdown` + endpoint
    `GET inventory/products/{id}/cost-breakdown/`.
- **الواجهة:** `frontend_v2/components/inventory/ProductCostPage.tsx` (view `product-cost`،
  مسار `/product-cost?product=ID`) — بحث/اختيار منتج، جدول فواتير الشراء (تكلفة/سعر وحدة)،
  تذييل بالمتوسط المرجّح. روابط دخول: الشريط الجانبي (مجموعة المخزون) + زر «تكلفة المنتجات»
  في بطاقة الصنف (تبويب جديد، المنتج محدد افتراضياً).
- **تنبيه أثر السعر (فوري):** في `InvoiceForm` عند كتابة سعر/كمية بند شراء، تنبيه
  «سيغيّر المتوسط من X إلى Y» + زر يفتح `/product-cost?product=ID`. يحسب المتوقّع من
  `cost-breakdown` (cache لكل منتج).
- **تصحيح البيانات القديمة:** أمر `recompute_product_cost [--apply] [--tenant N]` يعيد
  ضبط `Product.avg_cost` بالنموذج الجديد (يصحّح 292.31⇐95). dry-run افتراضياً.
- **قائمة الدخل صحيحة (إكمال):** `avg_cost` صار مصدره النموذج الجديد عند الاستلام المحلي
  (`set_avg_cost_from_purchases` في `logistics/services.py` + إعادة ضبط عند إلغاء الترحيل)
  ⇒ ترحيل COGS عند البيع يقرأ القيمة الصحيحة تلقائياً. + `reconcile_product_cogs` يعيد
  تقييم حركات البيع (OUT/SALE) ويُرحّل قيد تسوية واحداً لكل صنف (Dr ت.ب.م/Cr المخزون أو
  العكس) — يعالج البيع-قبل-الشراء (COGS=0) ويصحّح أرباح الفواتير. periodic WAC يتحقق:
  COGS + مخزون آخر المدة = إجمالي المشتريات. أمر `reconcile_cogs [--apply]`. idempotent.
  (الاستيراد GR/IR يبقى على WAC المتحرك بـ landed cost — خارج نطاق هذا الإصلاح المحلي.)
- **التحقق:** **الحزمة الكاملة 233/233** (+ اختبارات تكلفة/تسوية: متوسط مرجّح يتجاهل
  المباع، أولوية landed، set_avg_cost، reconcile sell-before-buy + idempotent، endpoint) ·
  tsc نظيف · بناء الإنتاج ناجح. (الشاشة خلف الدخول — لا تحقّق بصري.)

> ✅ **أُغلق (مراجعة الاستيراد ج2, 2026-07-09):** وُحّدت تكلفة الاستيراد مع نموذج
> «تكلفة المنتجات» — `apply_purchase_cost_model` يُستدعى بعد استلام الشحنة وترحيل
> الفاتورة (محلية GR/IR + دولية) وإلغاء ترحيل الشحنة؛ `product_cost_breakdown` كان
> يقدّم landed cost أصلاً. اختبارات: `logistics/tests/test_import_cost_model.py`.

## [AUDIT — task22 Phase 1, 2026-06-20] (المرافق العامة — G1 مُنسّق الأرقام + G2 تبويب جديد)

خطة جراحية متعددة المراحل (10 مراحل، تنفيذ مرحلة-بمرحلة بمراجعة المالك). المرجع
الأصلي مكتوب لـ RooFlow لكن المشروع لا يستخدم `memory-bank/` — مصدر الحقيقة هو هذا
الملف + ذاكرة `.claude`. **المرحلة 1 (المرافق العامة):**

- **[G1] مُنسّق أرقام موحّد** — `frontend_v2/utils/formatNumber.ts`:
  - `formatNumber(value, { maxDecimals?, group?, fallback? })` يحذف الأصفار العشرية
    غير الدالّة: `30490.00→"30490"` · `187.50→"187.5"` · `187.55→"187.55"`.
  - اختصاران: `formatMoney` (منازل 2 + فاصل آلاف) · `formatQuantity` (منازل 4).
  - تحقّق منطقي: 12/12 حالة (لا يوجد JS unit-runner في `frontend_v2` — تحقّق عبر Node).
- **[G2] فتح تبويب جديد** — `frontend_v2/utils/openInNewTab.ts`: مصدر واحد لـ
  `window.open(_blank, noopener)` للفواتير/كشوف الحساب/الطباعة.
- **[G3/G4]** موجودان أصلاً في `styles/index.css` (رموز كثافة `--spacing-*` مدمجة +
  أحجام خط صغيرة + Tailwind v4 responsive) — يُطبَّقان لكل شاشة في المرحلتين 2/5، لا
  أساس جديد مطلوب.
- **بدء التعميم:** `components/forms/shared/FinancialSummarySection.tsx` يمرّ الآن كل
  عرض عبر `formatMoney`/`formatNumber` (كان `toFixed(2)`/`toLocaleString(min:2)` ينتج
  `$30490.00`). بقية الـ23 ملفاً تُحوَّل ضمن مراحلها (تلمس فواتير/كشوف/تقارير لاحقاً).
- tsc نظيف (exit 0). لا انحدار وظيفي (عرض فقط).

### الباقي للتعميم (G1 rollout — يُنفَّذ ضمن المراحل اللاحقة)
SalesInvoiceEditor · PurchaseInvoiceAccountingPanel · DealForm · Sales/PurchaseReturnEditor ·
SalesCustomerPaymentsPage · CreditDebitNotesPage · SupplierPaymentsPage · AccountingJournalEntryPage ·
ClearanceImportModal · InvoicePrintView · InstallmentManager · ItemsTableSection · PriceOfferListUpdated ·
NISItemsTable · NISInvoiceTaxStrip · LocalPaymentsSection · ConversionDetailsSection · DealPrintView ·
dealsService · ProductCard (≈22 ملف يستخدم toFixed(2)/toLocaleString).

## [AUDIT — task22 Phase 9+10, 2026-06-20] (الآلة الحاسبة T-C1 + مسح الانحدار)

- **T-C1 (ذاكرة الحاسبة + UI ملوّن):** `AseelCalculatorPopover` — أُضيفت **ذاكرة العمليات
  السابقة** (تُحفظ في localStorage `aseel_calc_history`، تبقى بين الجلسات، حتى 25 عملية):
  زر سجلّ في الرأس يفتح لوحة قابلة للطيّ، نقرة على عملية تستعيد ناتجها، زر مسح الذاكرة.
  UI: عنوان متدرّج اللون + لوحة سجلّ ملوّنة (الأزرار كانت ملوّنة أصلاً: C أحمر/عمليات
  زرقاء/= أخضر). تحقّق: tsc نظيف.
- **المرحلة 10 (مسح الانحدار + المزامنة):** **الحزمة الخلفية الكاملة 229/229** (لا انحدار،
  +12 اختباراً جديداً) · **بناء الواجهة للإنتاج ناجح** (dist + PWA SW) · tsc نظيف ·
  مزامنة PROJECT_MAP وذاكرة `.claude` (ملف [[task22-surgical-refactor]]).

### الهجرات الجديدة (تُطبَّق عند النشر)
`inventory/0010` (مستندات المخزون) · `logistics/0046` (صندوق شراء افتراضي) ·
`sales/0019` (تنبيه تكرار الصنف).

### بقي لمراحل لاحقة (خارطة طريق task22)
- أعلام عرض الإعدادات المكتبية (آخر سعر/ربح/رصيد، اقتراح بالاسم/الكود/الباركود، عدد
  المنازل) — تُبنى مع سلوكها.
- شاشتا «إعدادات المخزون» و«البنوك» المستقلتان.
- خريطة قيد الشراء الكاملة + جرد على مستوى المستودع (المخزون حالياً على مستوى الشركة).
- تعميم G1 على بقية الملفات (~18) التي ما زالت تستخدم toFixed(2)/toLocaleString.

## [AUDIT — task22 Phase 8, 2026-06-20] (محرّك الإعدادات — T-S1..T-S4)

- **T-S1 (تدقيق الإعدادات الموجودة):** `SalesSettings` (محور غني: عميل/عملة افتراضيان +
  **خريطة حسابات افتراضية كاملة** صندوق/ذمم/إيراد منتج+خدمة/مخزون/ت.ب.م/ض.ق.م + أعلام
  سلوك: نوع الدفع، خصم المخزون، الرصيد السالب، شمول الضريبة، الترحيل التلقائي، معاينة
  القيد) عبر `sales/settings/current/`. `PurchaseSettings` (استراتيجية تسعير +
  default_cash_account من المرحلة 4). `useTenantSettings` + `SalesSettingsPage`/
  `PurchaseSettingsPage`/`SettingsPage`/`GroupConstantsPage`.
- **T-S2 (إعدادات عامة):** أُضيف `SalesSettings.warn_on_duplicate_item` (افتراضي true)
  عبر الـ stack (model + serializer + هجرة `0019` + نوع TS + حفظ الصفحة) — **يقود فعلياً
  T-R3** (تنبيه التكرار في المحرّر، كان يقرأ الإعداد منذ المرحلة 3). قسم «إعدادات عامة
  (السلوك)» جديد في صفحة إعدادات المبيعات.
- **T-S3 (خريطة القيد + استعادة الافتراضي):** لوحة «خريطة القيد المحاسبي» في الصفحة تعرض
  مدين/دائن لكل نوع (بيع نقدي: الصندوق/الإيراد · آجل: ذمم العميل/الإيراد · خدمات · ت.ب.م/
  المخزون — مطابقة صورة 6) من الحسابات المُهيّأة. زر **«استعادة خريطة القيد الافتراضية»**
  → `POST sales/settings/restore-defaults/` يحلّ الحسابات من COA (كود ثم نوع ثم اسم).
  الترحيل يمرّ عبر الـ subledger أصلاً (حساب العميل المرتبط/الصندوق/الإيراد).
- **T-S4 (خارطة الطريق — إعدادات/شاشات غير مبنية):**
  - أعلام عرض مكتبية (صورة 7/8) لم تُبنَ لتفادي مفاتيح ميتة بلا سلوك: «إظهار آخر سعر
    بيع / ربح الصنف / رصيد العميل قبل-وبعد»، «اقتراح الصنف بـ اسم/كود/باركود»، «عدد
    المنازل العشرية للسعر/الكمية» (G1 يطبّق منزلتين حالياً). تُبنى كحقول `SalesSettings`
    + ربط فعلي لاحقاً.
  - «إعدادات المخزون» و«البنوك» (من المرحلة 5) — شاشتان مستقلتان غير مبنيتين.
  - خريطة قيد الشراء (شراء نقدي/آجل، مرتجع شراء) — `PurchaseSettings` يحوي
    default_cash_account فقط؛ خريطة كاملة لاحقاً.
- **التحقق:** **3 اختبارات جديدة** (`test_settings_engine`: افتراضي التنبيه true + PATCH +
  restore-defaults يحلّ الأنواع الصحيحة) · **sales 45/45** · `manage.py check` 0 · tsc نظيف.
- **هجرة جديدة 0019 (sales) تُطبَّق عند النشر** (مع 0046 لوجستيات + 0010 inventory).

## [AUDIT — task22 Phase 7, 2026-06-20] (مستندات المخزون — T-I1 تحويل + T-I2 جرد)

مرحلة backend-ثقيلة: 4 نماذج جديدة + هجرة `0010` + خدمات ترحيل مُختبَرة + DRF + شاشتان.

- **النماذج (inventory/models.py):** `WarehouseTransfer`+`WarehouseTransferLine` ·
  `Stocktake`(+journal FK)+`StocktakeLine`(counted/system/variance). أُضيف نوعا مرجع
  `WAREHOUSE_TRANSFER`/`STOCKTAKE` إلى `StockMovement.REFERENCE_TYPES`. هجرة
  `0010_alter_stockmovement_reference_type_stocktake_and_more`.
- **الترحيل (inventory/services.py):**
  - `post_warehouse_transfer`: لكل بند `OUT` من المصدر + `IN` للوجهة **بالتكلفة
    المتوسطة الملتقطة** → صافي صفري على `quantity_on_hand`/`avg_cost` للشركة (نقل
    موقعي)، حركتان موسومتان بالمستودعين. **لا قيد محاسبي.** + `unpost_*` يعكس.
  - `post_stocktake`: لكل بند variance = counted − quantity_on_hand → `ADJUST_IN`
    (فائض) أو `ADJUST_OUT` (عجز)؛ يُجمِّع قيد فرق واحد عبر `post_journal`
    (فائض: مدين المخزون/دائن ت.ب.م · عجز: العكس) بقيمة variance×avg_cost. حسابا
    المخزون/ت.ب.م عبر `_resolve_line_account` (لا حساب تسوية مخصّص مطلوب). لا فرق ⇒ لا قيد.
- **الواجهة:** `WarehouseTransferViewSet`/`StocktakeViewSet` (+ actions `/post/`,
  `/unpost/`) على `inventory/warehouse-transfers/` و`inventory/stocktakes/`. سيريلايزرز
  بأسطر متداخلة قابلة للكتابة (ترفض تعديل المُرحَّل).
- **الأمامي:** `WarehouseTransferPage` + `StocktakePage` (قائمة + نموذج «حفظ وترحيل») ·
  `inventoryApi` (get/create/post لكلٍّ) · AppView+VIEW_PATHS+Breadcrumb · روابط في
  مجموعة «المخزون» بالشريط الجانبي.
- **التحقق:** **9/9 اختبارات جديدة** (`test_inventory_documents`: صافي صفري التحويل +
  وسم الحركات + رفض نفس المستودع + رفض الترحيل المزدوج + عكس · الجرد فائض/عجز/قيد/لا-فرق) ·
  **inventory 29/29** · `manage.py check` 0 · tsc نظيف · `resolve()` للمسارين · التطبيق
  يُحمَّل بلا أخطاء console. (الشاشات خلف الدخول — لم تُختبر بصرياً.)
- **هجرة جديدة 0010 تُطبَّق عند النشر** (مع 0046 لوجستيات من المرحلة 4).

## [AUDIT — task22 Phase 6, 2026-06-20] (مدفوعات + شبكات + سندات — T-P1/P2/G1/V1)

- **T-V1 (خلل سندات الصرف للموردين):** `SupplierPaymentsPage` كان يستدعي
  `purchase/payments/` — **لا مسار باسم `api/purchase/`** فيفشل بـ 404 عند الفتح.
  المسار الصحيح المُسجَّل: `logistics/supplier-payments/` → `SupplierPaymentViewSet`.
  أُصلح: القائمة + الإنشاء (عبر `purchaseInvoiceApi.addSupplierPayment` الذي ينشئ+يرحّل)،
  وأُعيدت تسمية حقول الصف `supplier→partner`/`supplier_name→partner_name` لمطابقة
  `SupplierPaymentSerializer`، وحُذفت لافتات «backend N8-T12 غير جاهز» المضلِّلة.
  **إثبات:** `resolve('/api/logistics/supplier-payments/')→SupplierPaymentViewSet`،
  `'/api/purchase/payments/'→404`. (تفصيل الشيكات/خصم المصدر لا يحفظه النموذج المبسّط —
  خارطة طريق.)
- **T-P1 (FIFO + فاتورة محددة):** `SalesCustomerPaymentsPage` — أُبقي «اقتراح FIFO»،
  وأُضيف منتقي فاتورة مفتوحة محددة (`partnerAging`) + زر «أضف الفاتورة» يُنشئ سطر توزيع
  بمبلغ افتراضي = min(متبقي الدفعة، متبقي الفاتورة). توزيعات قابلة للتحرير كما هي.
- **T-P2 (سند قبض سريع من كشف الحساب):** زر «سند قبض جديد» في `PartnerProfilePage`
  (للعملاء) يفتح `/sales/customer-payments?pay_partner={id}`؛ الصفحة تقرأ الباراميتر
  وتفتح المودال مع العميل مُعبّأً مسبقاً (`initialPartnerId`).
- **T-G1 (أعمدة قابلة للتحجيم Excel-like):** `AseelDenseTable` أُضيف له مقبض سحب على
  الحافة الطرفية لكل عمود (`resizable` افتراضي مُفعّل) — يعمل لشبكة العملاء وكل
  المستهلِكين (DRY). يحسب الدلتا حسب اتجاه RTL/LTR.
- **التحقق:** tsc نظيف (exit 0) · إثبات توجيه T-V1 عبر `resolve()`. **التحقق البصري
  للشاشات يحتاج جلسة مصادَقة** (خلف الدخول) — لم يُجرَ.

## [AUDIT — task22 Phase 5, 2026-06-20] (إعادة هيكلة التنقّل — Section 9 + T-N1..T-N3)

- **الشريط الجانبي (`Sidebar.tsx`) أُعيد بناؤه data-driven** بمجموعات Section 9 الكبيرة،
  كلٌّ بأيقونته (عارض `renderGroup` موحّد DRY، أصناف ثابتة بـ design-tokens — تفادي
  مصيدة Tailwind للأصناف الديناميكية). الترتيب:
  1. الرئيسية (Home) 2. المبيعات (ShoppingCart): فواتير/عروض/إشعارات/مرجع بيع/أرباح/
  إعدادات-آخراً 3. العملاء (Users): العملاء/دفعات 4. المشتريات (ShoppingBag): فواتير/
  عروض أسعار/مرجع شراء/سندات صرف/إعدادات/موردين 5. المخزون (Warehouse): أرصدة/الأصناف/
  حركات + **مجموعة فرعية «الاستيراد»** (الصفقات/الشحنات/أرشيف/نقل محلي/تخليص/رحلة) —
  **زر الاستيراد المستقل أُزيل** 6. المالية (Landmark): صناديق/شيكات 7. التقارير
  (تفتح كلٌّ في **تبويب جديد** G2 عبر `openInNewTab`) 8. **إدارة المهام في الأسفل تماماً**.
  المحاسبة محفوظة كمجموعة (وصول كامل للعمليات، لا تُكسر ميزة).
- **T-N1:** المساعد الذكي نُقل من الشريط الجانبي إلى رأس `AppLayout` بجوار `BranchSwitcher`
  («كل الفروع»).
- **T-N2:** زر «التصنيفات» (`items-categories`) أُزيل من التنقّل (المسار/التبويب باقٍ).
- **T-N3:** شاشة الأصناف (`ItemsManagement`) أصبح لها **عرض شجرة تصنيفات** (يعيد استخدام
  `InvoiceCategoryTree`) كافتراضي + مبدّل شجرة/جدول. نقرة=بطاقة، اختيار=تعديل.
- **شاشات غير مبنية (خارطة طريق، T-S4):** «إعدادات المخزون» و«البنوك» لا تملكان شاشة
  مستقلة — لم تُضَف أزرار مكسورة؛ تُبنى في مرحلة لاحقة. `aseel-kit` (أداة تطوير) أُسقط
  من التنقّل (المسار باقٍ).
- **تحذير تصميمي:** المجموعات موحّدة اللون (design-tokens) مع أيقونات مميِّزة بدل ألوان
  لكل مجموعة (تفادي عجز Tailwind JIT عن توليد أصناف ديناميكية).
- **التحقق:** tsc نظيف (exit 0) · إزالة الاستيرادات اليتيمة (Sparkles/Wrench/DashboardIcon) ·
  Vite يبني، التطبيق يُحمَّل بلا أخطاء console. **التحقق البصري لترتيب التبويبات يحتاج
  جلسة مصادَقة** (الشريط خلف الدخول) — لم يُجرَ.

## [AUDIT — task22 Phase 4, 2026-06-20] (روابط الحسابات + النقد — T-A1..T-A4)

- **T-A1 (المتبقي على حساب العميل):** **موجود أصلاً** (task18) — صفّا «رصيد العميل»
  و«الرصيد بعد الفاتورة» في رصيف الإجماليات + سطر «الرصيد السابق/بعد الفاتورة» في
  بطاقة العميل بالرأس. لا تغيير.
- **T-A2 (بطاقة العميل قابلة للنقر):** زر «بطاقة العميل» بجوار حقل العميل في
  `SalesInvoiceEditor` يفتح `/partners/{id}` في **تبويب جديد** (G2 — يحفظ الفاتورة الجارية).
- **T-A3 (المورد قابل للنقر عالمياً):** عمود المورد في `InvoiceList` (قائمة فواتير
  الشراء) صار رابطاً لكشف حساب المورد `/partners/{supplierId}` في تبويب جديد
  (`stopPropagation` كي لا يفتح الصف). (بطاقة العميل/المورد وكشف الحساب كلها
  `PartnerProfilePage` على `/partners/:id` — تبويب statement.)
- **T-A4 (الصندوق الافتراضي):**
  - **مبيعات:** أُزيل منتقي «حساب الصندوق» للدفعة المرفقة (موضعان) واستُبدل بعرض
    للقراءة فقط للصندوق الافتراضي + effect يملؤه من `default_cash_account`. (صندوق
    الفاتورة النقدية نفسه كان يتبع الإعدادات أصلاً، بلا منتقي.)
  - **شراء:** أُضيف الحقل عبر الـ stack: `PurchaseSettings.default_cash_account` FK
    (logistics/models.py) + هجرة `0046_purchasesettings_default_cash_account` +
    حقل في `PurchaseSettingsSerializer` + نوعا `purchaseInvoiceApi.get/updateSettings`
    + منتقي صندوق في `PurchaseSettingsPage` (يحمّل `accounting/accounts/`).
- **التحقق:** tsc نظيف (exit 0) · `manage.py check` 0 مشاكل · هجرة 0046 تُطبَّق على
  DB نظيفة (pytest) · `test_purchase_price_resolver` 8/8 · **الحزمة الكاملة 217/217** (لا انحدار).

## [AUDIT — task22 Phase 3, 2026-06-20] (سلوك بنود الفاتورة — T-R1..T-R4)

- **T-R1 (خلل السطور الوهمية، مبيعات):** `SalesInvoiceEditor.updateLine` كان يُلحق سطراً
  جديداً عندما يكون آخر سطر «ممتلئاً» بشرط `product!=="" || quantity!=="0"`. بما أن
  `makeEmptyLine` يبدأ بالكمية `"1"`، كان كل سطر فارغ يُحسب ممتلئاً فتتكاثر السطور.
  **الإصلاح:** الإلحاق فقط عندما يكتسب آخر سطر **صنفاً** حقيقياً (`product!=="" && !==-1`).
  محاكاة Node: قديم=5 سطور بعد إضافة+3 تعديلات كمية، جديد=2 (ممتلئ + فارغ واحد).
  (الشراء لا يعاني الخلل — `applyItemAt` يُلحق سطراً ذيلياً واحداً متحكَّماً به فقط.)
- **T-R2 (بطاقة الصنف ← حوار كمية+سعر):** `shared/ProductCardModal` أُضيف له **وضع إضافة**
  (`addMode`) يعرض حقل **الكمية** وحقل **السعر** مع **شارة مصدر** (`من آخر فاتورة` /
  `من عرض السعر` / `السعر الافتراضي`)، و«موافق» يمرّر `{quantity, unitPrice}`. وُصِّل في
  الشاشتين: المبيعات تُقدّر السعر عبر `resolveSalePrice` عند فتح البطاقة وتُثبّت السعر
  المُدخل (`priceTouched`)؛ الشراء عبر `resolveSuggestedPrice` ويمرّر الكمية إلى
  `applyItemAt(…, qtyOverride)`.
- **T-R3 (تنبيه التكرار):** المبيعات: تنبيه/تأكيد جديد في `insertProductIntoInvoice`
  يتبع إعداد `warn_on_duplicate_item` (افتراضي مُفعّل — جاهز لربط إعداد المرحلة 8).
  الشراء: **موجود أصلاً** (`applyItemAt` يعرض دمج/سطر مستقل).
- **T-R4 (حارس العمل غير المحفوظ):** المبيعات: `guardedReset` على «إضافة/إلغاء» —
  تأكيد ثنائي (متابعة؟ ثم حفظ-قبل-المغادرة؟). الشراء: `guardedGoNew` يحرس «جديدة»
  عندما تكون الفاتورة بلا id وتحتوي بنوداً (حالة فقدان العمل الحقيقية؛ لا تتبّع dirty
  كامل في الشراء — حُرست الحالة الجوهرية فقط). اختصار Ctrl+Ins تُرك بلا حارس (تفادي
  use-before-define؛ زر «جديدة» المرئي محروس).
- **تعميم G1:** `ProductCardModal.fmt2` ما يزال toLocaleString(min2) داخل KPIs البطاقة —
  مُدرج لاحقاً (عرض إحصائي، ليس مبالغ فاتورة).
- **التحقق:** tsc نظيف (exit 0) · محاكاة T-R1 Node. **التحقق البصري للحوار/الحارس يحتاج
  جلسة مصادَقة** (محرّر الفاتورة خلف الدخول) — لم يُجرَ.

## [AUDIT — task22 Phase 2, 2026-06-20] (تخطيط الفاتورة — رأس أفقي مدمج T-L1..T-L5)

**السبب الجذري (T-L1):** القشرة `AseelDocumentShell` تلفّ الرأس في `.aseel-headband`
لكن هذا الصنف لم يكن يضبط `display`، فحقول `fld()` (label.aseel-field) تتراصّ
**عمودياً** وتبتلع نصف الصفحة — تماماً كصورة 11 لفاتورة الشراء. (قاعدة الموبايل
كانت تتجاوز `grid-template-columns` لم يُضبط على الديسكتوب أصلاً — تخطيط مرتجَع.)

- **الإصلاح (DRY، عالمي):** `styles/index.css` — `.aseel-headband` صار
  `display:flex; flex-wrap:wrap; gap:3px 14px`، و`> .aseel-field` يأخذ
  `flex:1 1 220px; min-width:190px; max-width:340px`. يُصلح رأس فاتورة الشراء
  وكل شاشات المستندات (deals، عروض الأسعار، المرتجعات…) دفعة واحدة. رأس المبيعات
  محفوظ لأن طفله الأول `w-full` فيبقى صفّاً مستقلاً. قاعدة الموبايل (<640px) حُدِّثت
  لـ `flex-direction:column`.
- **T-L1/T-L2/T-L5:** الرأس الآن أفقي مضغوط على الشاشتين؛ المورد/الاسم متجاوران.
  T-L3 (الشريط) وT-L4 (رصيف الإجماليات الثابت) مؤمَّنان أصلاً ببنية القشرة.
- **تعميم G1 (المرحلة 2):** `SalesInvoiceEditor.fmt` و`InvoiceForm.fmt` أُعيد تعريفهما
  إلى `formatMoney` (يحذف الأصفار الزائدة من كل الإجماليات) + سطرا رصيد المورد.
- **التحقق:** tsc نظيف (exit 0) · خادم Vite يبني/يخدم بلا أخطاء CSS، التطبيق يُحمَّل
  (صفحة الدخول) بلا أخطاء runtime. **التحقق البصري للرأس الأفقي يحتاج جلسة مصادَقة
  (محرّر الفاتورة خلف تسجيل دخول)** — لم يُجرَ لأن إدخال بيانات الدخول ليس من صلاحياتي.

## [AUDIT — task21, 2026-06-19] (تحسينات UX لفاتورة البيع/الشراء + تسعير عرض السعر — DEF-001..009)

تغييرات جراحية على شاشتي فاتورة المبيعات/الشراء وشجرة المنتجات وبطاقة الصنف
وبطاقة العميل. لا انحدار محاسبي (UI/UX + اقتراح سعر فقط). **تحقّق حيّ في المتصفح
بجلسة مصادَقة فعلية** (أول مهمة تتحقق حيّاً من الشاشات الداخلية).

### الطبقة المشتركة (DRY)
- **`frontend_v2/components/shared/ProductCardModal.tsx`** — بطاقة الصنف كمودال
  واحد يُعاد استخدامه في **ثلاثة مداخل** (DEF-007/008): نقر مفرد على الشجرة ·
  أيقونة (i) في القائمة المنسدلة · أيقونة (i) على سطر الفاتورة. يقرأ نفس نقطة
  `inventory/products/{id}/profile/`. أسعار بمنزلتين (DEF-003).
- **`core/pricing.py resolve_sales_price`** — أُضيف سقوط «عرض السعر اليدوي»
  (CustomerProductQuote) بين «آخر بيع للعميل» و«سعر الصنف الافتراضي». الأولوية
  (DEF-005): آخر فاتورة للعميل **تفوز دائماً** ← عرض السعر اليدوي ← tier ← فارغ.
  مصدر السعر يُرجَع في `source.document_type` (`SALES_INVOICE`/`CUSTOMER_QUOTE`).

### DEF-001..003 (تموضع/تسمية/تنسيق)
- DEF-001: `.aseel-tree-panel` صارت `sticky top:8px` بارتفاع `calc(100vh-160px)`
  و`min-height:320px` ⇒ رأس الشجرة + 20+ صفاً ظاهرة دون تمرير على 1366×768.
- DEF-002: «شجرة الأصناف» → **«شجرة المنتجات»** (3 مواضع). الهرمية صريحة: الصنف/
  الفئة = عقدة فرعية، المنتج = عقدة ورقية. **لا إعادة تسمية للباك-إند** (A1).
- DEF-003: بطاقة الصنف تعرض كل الأسعار بمنزلتين؛ السعر المقترح للسطر يُعرض عبر
  `toFixed(2)` (يبقى قابلاً للتحرير). الدقّة المخزّنة (4 منازل) لم تُمَسّ (A2).

### DEF-004 — عرض السعر لكل العميل (مبيعات فقط)
- موديل **`sales.CustomerProductQuote`** (جدول `sales_module_customer_product_quotes`،
  migration `0018`): فريد `(tenant, customer, product)` + `unit_price`. لا أثر
  محاسبي (A3).
- خدمات `sales/services.py`: `customer_price_list` (كامل الكتالوج + مصدر/قابلية
  تحرير لكل صف: مُشترى→سعر آخر فاتورة للقراءة فقط، غير مُشترى→حقل قابل للتحرير) ·
  `save_customer_quotes` (upsert؛ قيمة فارغة تحذف العرض).
- نقطة نهاية `CustomerPriceListViewSet`: `GET sales/customer-price-list/?customer=` ·
  `POST sales/customer-price-list/save/`.
- واجهة: تبويب **«عرض السعر»** في `PartnerProfilePage` (للعملاء فقط) عبر
  `CustomerPriceListTab.tsx` + `salesApi.getCustomerPriceList/saveCustomerQuotes`.

### DEF-005..008 (سلوك السطر/الشجرة/القائمة)
- DEF-005: شارة مصدر السعر على السطر («من آخر فاتورة» / «من عرض السعر») —
  `DraftLine.priceSource` يُضبط من نتيجة الـ resolver، يُمسح عند التحرير اليدوي.
- DEF-006: السطر يُضاف فقط بزر **«إضافة سطر»** الصريح (أُضيف لشاشة المبيعات أيضاً)؛
  النقر خارج الجدول/على الشجرة (مفرد) لا يُنشئ صفوفاً (مُتحقَّق حيّاً).
- DEF-007: في `InvoiceCategoryTree` تمييز نقر مفرد/مزدوج عبر مؤقّت 220ms — مفرد=
  بطاقة (`onShowCard`)، مزدوج=إدراج (`onPickItem` كما كان). متطابق بيع/شراء (مكوّن
  مشترك).
- DEF-008: `AseelAutocomplete` صار يعرض أيقونة (i) لكل خيار (`onInfo`) تفتح البطاقة
  دون اختيار/إضافة؛ وأيقونة (i) بجانب المنتج المختار على السطر (بيع وشراء).

### DEF-009 — مهلة الخمول
- ثابتان في `frontend_v2/constants/session.ts`: `IDLE_TIMEOUT_MS = 3 ساعات`
  + `IDLE_WARNING_MS = 2 دقيقة` (مُدِّدت من 30د لتغطية الجرد الطويل) +
  `components/IdleTimeoutGuard.tsx` (مركّب في `App.tsx`): قبل الانتهاء بدقيقتين يظهر
  تنبيه بعدّاد تنازلي + زر «متابعة الجلسة» (يمدّد دون فقد العمل)؛ وبعد المهلة يمسح
  التوكن ويعرض مودال «تم إنهاء الجلسة» → العودة لتسجيل الدخول. أي نشاط يعيد ضبط المؤقّت.

### الجرد — تجربة العدّ الاحترافية (StocktakePage)
- `frontend_v2/components/inventory/StocktakePage.tsx`: الصنف المختار يُعرض كاسم ثابت
  (غير قابل للتعديل/المحو) + زر (i) يفتح `ProductCardModal` (بطاقة الصنف)؛ الأسطر
  الفارغة فقط تستخدم منتقي البحث. خانة «الكمية المعدودة» تبدأ **فارغة** (لا تُملأ برصيد
  النظام). عمود **الفرق** = المعدودة − النظام بإشارة ولون (أخضر فائض/أحمر عجز). فلتر
  «أظهر الفروقات فقط» + عمود صناديق اختيار (Checkboxes) لـ **تحديد أصناف معينة للطباعة**.
  زر **طباعة** ورقة النتيجة (يطبع الأصناف المحددة، أو يحترم الفلتر كوضع افتراضي). تفعيل فلتر
  الفروقات يقوم بتحديد الفروقات للطباعة تلقائياً (مع إمكانية إضافة/إزالة أي صنف يدوياً).
  **حرج:** السطر بلا عدّ (خانة فارغة) يُستثنى من الترحيل ولا يُصفِّر الصنف (جرد جزئي آمن). الفرق محسوب بالواجهة.
- **فتح مستند محفوظ:** صفوف القائمة قابلة للنقر (`openStocktake`): المسودة تُفتح في النموذج
  للتعديل (الحفظ ⇒ PATCH `updateStocktake`)، والمُرحَّل للعرض فقط (`editingPosted` يعطّل
  الإدخال ويُخفي الحفظ، ويعرض لقطة `system_quantity`/`variance` المخزَّنة بدل الحساب الحي).
  أُضيف `getStocktake`/`updateStocktake` إلى `inventoryApi`. الـ backend (DRF) كان يدعم
  retrieve + PATCH (مع منع تعديل المُرحَّل) — لا تغيير backend.

### تحقق
- backend: TDD جديد `sales/tests/test_customer_quote_pricing.py` (+6: مصفوفة
  الأولوية quote-only/purchased-beats-quote/neither + نقطة القائمة list/save/delete).
  حزم البيع+التسعير+البطاقات **57 أخضر** · `makemigrations --check` لا انحراف ·
  `manage.py check` 0.
- frontend: tsc 0 · vite build OK.
- **حيّ في المتصفح (1366×768، جلسة فعلية):** «شجرة المنتجات» (لا «أصناف») · الشجرة
  أعلى البنود (20+ صفاً) · نقر مفرد=بطاقة · مزدوج=إدراج بلا تكرار · نقر خارجي=صفر
  صفوف · (i) القائمة ×8 تفتح البطاقة دون اختيار · (i) السطر ×2 تفتح البطاقة ·
  تبويب «عرض السعر» يظهر للعميل. (قائمة «عرض السعر» الحيّة فارغة لأن خادم الـ API
  المتصل به الواجهة لم يُنشر عليه الـ endpoint/migration الجديدان بعد — مُغطّى
  backend بالاختبارات. نشر: `python manage.py migrate sales`.)

### [ORPHANS & PENDING — task21]
- DEF-009 لم يُختبر حيّاً (يتطلب انتظار 30د)؛ الكود مركّب والبناء نظيف.
- صف فارغ تالٍ بعد الإدراج = سلوك قائم سابقاً في محرر المبيعات (ليس صفاً «شارداً»).
- بطاقة الصنف لا تعرض «آخر 7/28 يوم» ولا صورة (نقطة `profile` لا تُرجعهما) — تُضاف
  عند توسعة الـ endpoint لاحقاً.

## [AUDIT — task20, 2026-06-18] (التسعير الذكي + بطاقات الكيانات — FEAT-1..4)

نطاق: تسعير تلقائي لبنود الشراء (FEAT-1) والبيع حسب العميل (FEAT-2) + بطاقة صنف
احترافية (FEAT-3) + بطاقتا عميل/مورد (FEAT-4). المبدأ المعماري: مصدر حقيقة واحد
(الفواتير المرحَّلة/الأستاذ) — لا مخزن أسعار موازٍ.

### الطبقة المشتركة (Core / DRY)
- **`core/pricing.py` — PriceResolver (strategy pattern):** دالّتان عامتان
  `resolve_purchase_price` (LAST_PURCHASE/LOWEST_PURCHASE) و`resolve_sales_price`
  (LAST_SALE_TO_CUSTOMER) + facade `PriceResolver.resolve`. يقرأ **فقط** المستندات
  المرحَّلة (`PurchaseInvoiceItem` على فاتورة `is_posted`، `SalesInvoiceLine` على
  فاتورة `posted/sale`). تطبيع العملة عبر سعر صرف المستند (للأساس ثم للعملة الهدف)،
  وتطبيع أساس الضريبة (inclusive↔exclusive) عبر نسبة ضريبة السطر. سلسلة سقوط: تاريخ
  الشراء → `Product.avg_cost`؛ تاريخ بيع العميل → سعر بيع الصنف (`ProductPriceTier`
  المطابق للعملة) → فارغ. تسجيل (logging) لكل مسار. **يبطل** مسار
  `priceListService.getLastSupplierPrice` القديم (مجموعة `supplier_prices` الموازية).
- **`frontend_v2/components/shared/LedgerTable.tsx`:** مكوّن واحد لقوائم الحركات ذات
  «الرصيد الجاري» — أعمدة كبارامتر (وارد/صادر للصنف · Dr/Cr للشريك) + `DocRefCell`
  (مرجع مستند قابل للنقر عبر `utils/entityLinks.invoicePathForReference` — مُحلِّل
  المراجع المشترك). يستهلكه ProductProfilePage + PartnerProfilePage.

### FEAT-1 — تسعير الشراء + إعدادات الشراء
- موديل `logistics.PurchaseSettings` (`purchase_default_price_strategy`) + migration
  `logistics/0045_purchasesettings` + `get_or_create_purchase_settings`.
- نقاط نهاية: `GET logistics/purchase-invoices/resolve-price/?product=&strategy=&exchange_rate=`
  · `GET|PUT|PATCH logistics/purchase-settings/current/`.
- واجهة: `PurchaseSettingsPage` (view `purchase-settings`, مسار `/purchase-settings`,
  في شريط المشتريات الجانبي) · `InvoiceForm` يستدعي `purchaseInvoiceApi.resolvePrice`
  عند اختيار صنف (يحل محل `getLastSupplierPrice`) مع **حماية تعديل** (لا يَدُس سعراً
  أُدخل يدوياً — يُملأ فقط إن كان صفراً).

### FEAT-2 — تسعير البيع حسب العميل
- نقطة نهاية: `GET sales/invoices/resolve-price/?product=&customer=&exchange_rate=&tax_inclusive=`
  (`last-price` القديمة باقية). `salesApi.resolveSalePrice`.
- واجهة: `SalesInvoiceEditor` — `onSelectProduct` يستدعي الـ resolver؛ تغيير العميل
  بعد وجود بنود يُعيد تسعير الأسطر **غير المَلموسة فقط** (effect على `customerId`).
  حقل `DraftLine.priceTouched` (يُضبط عند تحرير السعر يدوياً وعلى الأسطر المحمَّلة/
  المستعادة) يحمي السعر اليدوي.

### FEAT-3 — بطاقة الصنف
- `inventory/services.py`: `product_profile` (KPIs) · `product_stock_ledger` (رصيد
  جارٍ = `StockMovement.quantity_after` المخزّن ⇒ يطابق المخزون الحالي، مُرقَّم؛ كل
  صفّ يحمل `party` = اسم `StockMovement.partner` كتبويب الفواتير المرتبطة) ·
  `product_linked_invoices`. أكشِنات على `ProductViewSet`: `profile/`, `stock-ledger/`,
  `invoices/`. حركة المخزون تعرض عمود «النوع» (مشتريات/مبيعات مشتقّة من
  `reference_type`) و«الطرف» (المورد/الزبون) إلى جانب المستودع.
- واجهة: `components/items/ProductProfilePage` (view `product-profile`, مسار
  `/products/:id`) — اسم الصنف في `ItemsManagement` يفتحها.

### FEAT-4 — بطاقتا العميل/المورد
- `accounting/services.py`: `partner_account_statement` (Dr/Cr + رصيد جارٍ، مُرقَّم،
  يطابق `partner_posted_balance`). أكشِنات على `PartnerViewSet`: `profile/`
  (الرصيد + جهة Dr/Cr + إجماليات + آخر معاملة), `statement/`, `invoices/`.
- واجهة: `PartnerProfilePage` — مُلئت تبويبات «ملخص الرصيد/كشف الحساب/الفواتير»
  عبر LedgerTable (بدل placeholders «قريباً»؛ أُزيل تبويب GL على مستوى الحساب لصالح
  كشف الحساب المحصور بالشريك).

### تحقق
- اختبارات جديدة (TDD، +28): `logistics/tests/test_purchase_price_resolver.py` (8) ·
  `sales/tests/test_sales_price_resolver.py` (6) · `inventory/tests/test_product_profile.py` (7) ·
  `accounting/tests/test_partner_statement.py` (7).
- **backend 211/211 أخضر** · tsc 0 · vite build OK · `makemigrations --check` لا انحراف ·
  `manage.py check` 0. لم يُتحقق في متصفح حي للشاشات الداخلية (تتطلب باك-إند + جلسة —
  نفس قيد المهام السابقة)؛ التحقق عبر الاختبارات + الأنواع + البناء.
- **ملاحظة نشر:** `python manage.py migrate` (logistics/0045 — جدول `purchase_module_settings`).

### إصلاح كاش الـ PWA والتحديثات (بعد بلاغ «البطاقة فارغة/عالقة»)
- **السبب الجذري:** `sw.ts` كان (1) يعترض نداءات `/api/` **عابرة الأصل** (الواجهة :3000،
  الـ API :8000) بـ networkFirst/مهلة 3ث + سقوط للكاش ⇒ يُقدَّم رد قديم/فارغ أو 503
  بدل الخادم؛ (2) `cacheFirst` على JS باسم كاش ثابت `ktra-static-v1` ⇒ كود قديم محبوس؛
  (3) `registerType:'prompt'` بلا إعادة تحميل تلقائية ⇒ التحديث لا يصل بلا مسح يدوي.
- **الإصلاح:** حارس **same-origin** (نداءات الأصل الآخر تتجاوز الـ SW تماماً) · اسم كاش
  ثابت مشتق من بصمة البناء `ktra-static-${hash(__WB_MANIFEST)}` ⇒ activate يمسح كاش
  أي نسخة سابقة · التنقّل (navigate) network-first ليصل index.html الأحدث · مهلة الـ API
  8ث · `index.tsx` يستمع لـ `controllerchange` فيعيد التحميل مرة واحدة عند تفعيل SW جديد
  (حارس `_hadController` يمنع ذلك عند أول تثبيت وحلقات التحميل). **تحقق:** vite build OK ·
  tsc 0. **إجراء لمرة واحدة للخروج من SW القديم العالق:** إعادة بناء + إعادة تحميل
  (أو DevTools→Application→Unregister إن لزم)؛ بعدها التحديثات تُطبَّق تلقائياً.

### إصلاح جذري: البطاقة فارغة لأن `id`=undefined (لا علاقة للكاش/الخادم)
- **السبب الجذري المؤكَّد:** `App` مركّب في `index.tsx` على مسار splat `<Route path="/*">`
  بلا أي `<Route path=":id">` داخلي (يعرض الصفحات عبر `switch(appView)`). لذا
  `useParams().id` داخل `ProductProfilePage`/`PartnerProfilePage` يرجع **undefined**،
  وشرط `if (!id) return;` في كل الـ effects يمنع إرسال أي طلب ⇒ الاسم يبقى «جاري
  التحميل...» والتبويبات فارغة، وسجل الخادم لا يُظهر أي نداء `/profile|/invoices|/statement`.
  (تم الفحص: خادم :8000 يردّ 401 على النقاط = موجودة وسليمة؛ المشكلة كانت أن الواجهة
  لا ترسل الطلب أصلاً.)
- **الإصلاح:** استخراج المعرّف من `useLocation().pathname` عبر regex
  (`/products/([^/]+)` و`/partners/([^/]+)`) بدل `useParams`. هذا أصلح بطاقة الصنف
  **وبطاقة الشريك** (التي لم تكن تعمل ببيانات حقيقية أصلاً لنفس السبب). vite build OK · tsc 0.

### [ORPHANS & PENDING — task20]
- `priceListService.ts` لم يعد مستهلَكاً من `InvoiceForm` (بقي معرّفاً — لم يُحذف
  لاحتمال استهلاك آخر؛ مرشّح للإزالة لاحقاً).
- تطبيع UoM: النظام بلا معامِلات تحويل وحدات — السعر بوحدة الصنف الأساسية (A5).
- بطاقة الصنف: لا صورة في الرأس بعد (KPIs نصية)؛ تُضاف عند جولة UI حية.

## [AUDIT — task16, 2026-06-13] (Surgical sweep — Section B accounting first, then UX/nav)

### B. القيد المزدوج يمرّ دائماً عبر الـ subledger (مُنفَّذ + مُختبَر)
- **السبب الجذري (مُتحقَّق بالكود لا بالوصف):** كل من `post_sales_invoice` (sales/services.py) و`PurchaseInvoiceViewSet.post_to_accounting` (logistics/views.py:1801) كانا **يربطان الـ subledger في القيد الآجل فقط**؛ أما البيع/الشراء النقدي فكان يدين/يدائن الصندوق مباشرة ويتجاوز حساب العميل/المورد ⇒ كشف الحساب والأعمار لا يعكس الحركات النقدية. (القيد كان متوازناً وصحيح الحسابات الأخرى — لذلك لم نُعد كتابة الدالة، بل صوّبنا مسار النقدي فقط.)
- **الإصلاح (Section B):**
  - **مبيعات:** يُقيَّد دائماً Dr ذمم العميل بكامل الإجمالي / Cr إيراد+ضريبة، ثم تُسوَّى التحصيلات (نقدي: Dr صندوق/Cr ذمم؛ شيكات: Dr شيكات برسم التحصيل/Cr ذمم) في نفس السند. خصم المصدر يُحسب مبكراً ليُخصم من صافي التحصيل النقدي. `amount_paid` يشمل الآن النقدي المُحصَّل على الفاتورة النقدية.
  - **مشتريات:** الحساب الدائن دائماً ذمم المورد (subledger)؛ `payment_type='cash'` (أو `attached_cash_amount` جزئي) يضيف تسوية Dr ذمم المورد / Cr صندوق تُفرّغ الذمم دون تجاوزها.
- **تحقق:** اختباران جديدان (`sales/tests/test_subledger_routing.py` + `logistics/tests/test_pi_subledger_routing.py`) يثبتان لمس الـ subledger (Dr كامل + Cr تسوية) وتوازن القيد · **الحزمة كاملة 169/169 خضراء** (167 + 2).

### بقية البنود — تتبّع التنفيذ
**مُنفَّذ ومُتحقَّق (tsc 0 · vite build OK):**
- [x] **A5** مرجع الفاتورة في حركات المخزن رابط (StockMovementsPage) — عبر `utils/entityLinks.invoicePathForReference`.
- [x] **A6** مرجع فاتورة البيع/الشراء في قائمة قيود اليومية رابط (AccountingJournalListPage).
- [x] **A7** رقم فاتورة المبيعات نفسه رابط يفتح الفاتورة (SalesInvoicesPage).
- [x] **A8** قائمة فواتير المبيعات `/sales/invoices` وتفصيل واحدة `/sales/invoices/:id` مساران مستقلان (URL مصدر الحقيقة لفتح المحرر؛ deep-link/back-forward) + فرع التحليل العكسي في App.tsx.
- [x] **C11 (مبيعات)** العودة لـ `/dashboard` بعد حفظ الفاتورة (onInvoiceSaved).
- [x] **D12** بنر نجاح «حُفظ بنجاح» واضح في إعدادات المبيعات (aseel-banner--ok + role=status).
- [x] **E17** منتقي صنف عرض السعر كان يحمّل `getAccounts` (شجرة الحسابات) ⇒ صُحِّح إلى `inventory/products` (SalesQuotationsPage).
- [x] **E19** نقل «إدارة الموظفين» لأسفل الشريط الجانبي (Sidebar).

**مُنفَّذ ومُتحقَّق (الدفعة الثانية — tsc 0 · vite build OK · backend 169):**
- [x] **A4** روابط الكيانات: اسم الصنف (حركات المخزون)→`/items` · اسم العميل (قائمة فواتير المبيعات)→`/sales/customers` · اسم المورد (قائمة فواتير الشراء)→`/suppliers` عبر `utils/entityLinks.{productPath,customerPath,supplierPath}`. (ملاحظة: لا مسارات تفصيل مستقلة لكل كيان حالياً — الروابط تفتح صفحة الإدارة؛ يمكن توجيهها لصفحة تفصيل لاحقاً دون تغيير المستهلكين.)
- [x] **C9** إضافة مورد inline من حقل البحث في فاتورة الشراء (`InvoiceBasicInfo` يمرّر `onOpenAddModal`→`SupplierModal` القائم في `InvoiceForm`).
- [x] **C10** حالة الدفع (مدفوعة/جزئياً/غير مدفوعة) + الإجمالي + المتبقي — محسوبة في `PurchaseInvoiceSerializer` (amount_paid/remaining_balance/payment_status) ومعروضة في لوحة المحاسبة.
- [x] **C11 (شراء)** العودة لـ `/dashboard` بعد إتمام ترحيل فاتورة الشراء (onPosted).
- [x] **D13** أُزيل محددا حساب الإيراد وحساب الصندوق من `SalesInvoiceEditor` — يُقرآن من إعدادات المبيعات (default_revenue_account_product/default_cash_account)؛ رسائل التحقق تُحيل للإعدادات.
- [x] **D14** اختصارات شريط علوي قابلة للتهيئة: `utils/quickShortcuts` + شريط في `AppLayout` + قسم تهيئة في `SettingsPage` (تخزين محلي + بثّ حدث للتحديث الفوري).
- [x] **E15** الحاسبة: أُزيل الفتح التلقائي بالنقر المزدوج من `AseelGrid`؛ أُضيفت أيقونة حاسبة في الشريط العلوي (`AseelCalculatorButton` + وضع `standalone` في الـ popover).
- [x] **E16** رصيد الصندوق: أُضيف حقل `balance` محسوب من دفتر الأستاذ (مدين−دائن للقيود المرحَّلة) في `CashBoxLedgerAccountSerializer`؛ `CashBoxList` يعرضه بدل الرصيد المخزّن الصفري.
- [x] **E18** تصدير رصيد المخزون CSV (مع BOM للعربية) + اختيار الأصناف بمربعات + «تحديد الكل» في `StockLevelsPage`.

**إصلاحات ما بعد التشغيل (بلاغ المالك بالصور على localhost):**
- زر «العودة للفواتير» الصريح أُضيف لشريط محرر فاتورة المبيعات (`SalesInvoiceEditor` toolbar `back` action + `onClose` prop) — كان فقط ✕ إغلاق صغير بزاوية الإطار.
- 🔴 **زر «إضافة عميل» كان يفتح `SupplierModal` (يُنشئ مورداً!):** في `SalesInvoiceEditor` كان مودال إضافة العميل = `SupplierModal` (عنوان «إضافة مورد جديد» + `suppliersService.addSupplierToDb`) ⇒ يُنشئ Supplier لا Customer. الإصلاح: `CustomerQuickAddModal` جديد يُنشئ شريكاً `partner_type=Customer` عبر `POST partners/` (نفس مسار صفحة العملاء) + `eventBus.publish("partners")` لتحديث القوائم + اختيار العميل تلقائياً.
- 🔴 **Section B ناقص — مسار «استلام بضاعة الفاتورة» كان يتجاوز ذمم المورد:** الإصلاح الأصلي غطّى `post_to_accounting` لكن `receive_purchase_invoice` (logistics/services.py، مسار task15 الفعلي للفواتير المحلية) بقي يدائن الصندوق مباشرة للنقدي ⇒ القيد #290 (Dr مخزون 1104 / Cr نقدية 1101) بلا حساب المورد. الآن: يدائن دائماً ذمم المورد بكامل القيمة، ثم يُسوّي النقدي (Dr ذمم المورد / Cr صندوق). +2 اختبار (`test_local_invoice_receive`: آجل يدائن AP · نقدي يمرّ عبر AP ويُسوّى). **backend 171**.
- **A7 (شراء):** رقم فاتورة الشراء في القائمة (`InvoiceList`) صار رابطاً يفتح الفاتورة (`onView`) — كان مقتصراً على فواتير المبيعات.

**تحقق نهائي:** backend **169/169** · tsc 0 · vite build OK. لم يُتحقق في متصفح حي للشاشات الداخلية (تتطلب باك-إند+تسجيل دخول — نفس قيد المهام السابقة)؛ التحقق عبر الاختبارات + الأنواع + البناء.

## [AUDIT — task19, 2026-06-16] (حجز/إعادة استخدام رقم القيد + توحيد تصميم فاتورة الشراء)

طلب المالك (Phase 0): (1) زر «تراجع عن الترحيل» على فاتورة الشراء يحذف كل قيودها ويُرجعها مسودة — **مُنفَّذ مسبقاً في task17** (backend `PurchaseInvoiceViewSet.unpost` + زر `PurchaseInvoiceAccountingPanel`). (2) **حفظ رقم القيد المحذوف وإعادة استخدامه نصّاً عند إعادة الترحيل.** (3) توحيد تصميم فاتورة الشراء ليطابق فاتورة المبيعات (full restructure).

### الأسباب الجذرية (مُتحقَّق منها بالكود)
- **«رقم القيد» = `JournalHeader.id` (PK، `JournalID`، AutoField).** عند التراجع كان الـ FK `invoice.journal` يُصبح NULL والقيد يُحذف؛ إعادة الترحيل تُخصّص PK جديداً عبر auto-increment. لا حقل يحفظ الرقم القديم على أي من نموذجَي الفاتورة.
- ادّعاء «تراجع المبيعات يفتح فاتورة الشراء» **غير قابل لإعادة الإنتاج بالكود**: `unpostSalesInvoice` يضرب `sales/invoices/{id}/unpost/` والمعالج يبقى على فاتورة المبيعات (ادّعاء قديم).

### قرارات المالك (2026-06-16)
- إعادة الاستخدام: **Option 1 (استخدام صارم + سقوط لرقم جديد)** + ضمان عزل: الرقم المحذوف يُحجز في **سلّة محذوفات مخفية** (recycle bin) لا يلتقطه أي قيد جديد بالخطأ، مخفي عن الواجهة، محفوظ بالخلفية حتى تطلبه إعادة الترحيل أو يسقط للبديل.
- تطبيق الميزة على **المبيعات + الشراء** معاً. UI: **إعادة هيكلة كاملة** لفاتورة الشراء.

### [EXECUTION — task19] (M1 — مُنفَّذ ومُختبَر)
- **`accounting.models.VoidedJournal`** (جدول `voided_journals`): سلّة المحذوفات — `original_journal_id` + `(tenant, reference_type, reference_id)` فريد. ليس قيداً حيّاً (لا أسطر) فلا يمسّ أياً من 135 موضع قراءة للأستاذ/ميزان المراجعة (لا انحدار). migration `accounting/0024_voidedjournal.py`.
- **`unpost_document(..., recycle=False)`**: عند `recycle=True` يحجز رقم القيد **الأساسي** (أول نوع في `journal_reference_types`) في `VoidedJournal` قبل الحذف. القيود الفرعية (COGS/استلام) تُحذف دون حجز (تُولَّد من جديد). مُوصَّل `recycle=True` في unpost المبيعات (`SALES_INVOICE`) والشراء (`PURCHASE_INVOICE`) فقط — الأربعة الأخرى تبقى حذفاً صرفاً.
- **`post_journal`**: يكتشف تلقائياً حجزاً لـ `(tenant, ref_type, ref_id)`؛ إن وُجد يُعيد إدراج القيد بنفس `original_journal_id` (force_insert ذرّي) ثم يحذف الحجز. تعارض الرقم (مشغول — غير متوقع) → رقم تلقائي جديد + `logger.warning`. القيود غير المُلغاة سابقاً (لا حجز) تسلك السلوك القائم.
- **تنظيف:** حُذف `perform_update` المكرر الميّت في `PurchaseInvoiceViewSet` (نسخة الحارس عند line 2226 تبقى).
- **اختبارات:** `accounting/tests/test_unpost_document.py` (+5، الآن 8): حجز ثم إعادة استخدام نفس الرقم · حجز القيد الأساسي فقط · لا حجز افتراضياً · السقوط لرقم جديد عند تعارض · **E2E عبر نقاط النهاية** (post→unpost→re-post نفس الرقم).
- **تحقق:** backend **187/187** خضراء.

### [EXECUTION — task19 / M2] (توحيد UI فاتورة الشراء — مُنفَّذ)
- **تشخيص:** `InvoiceForm` يستخدم أصلاً نفس بنية المبيعات (`AseelDocumentShell` + بطاقات رأس + `AseelGrid` للبنود + tabs + totals + status bar). الفرق الجوهري: شريط الأدوات كان فيه (تخزين/جديدة/طباعة/إلغاء) فقط — **بلا ترحيل/تراجع**؛ المحاسبة (post/unpost + معاينة القيد + وصل دفع المورد) كانت **بلوكاً منفصلاً أسفل المحرر** في `PurchaseInvoice.tsx`، بينما شاشة المبيعات تضعها inline (شريط أدوات واحد + تبويبات).
- **التنفيذ (single editor + inline accounting):**
  - أُضيف زرّا **«ترحيل» (Send)** و**«تراجع عن الترحيل» (Undo2)** لشريط أدوات `InvoiceForm` بنفس ترتيب/أيقونات المبيعات وبوّابات التفعيل (post: محفوظة + غير مرحّلة + غير مؤرشفة؛ unpost: مرحّلة فقط؛ التخزين يُعطَّل على المرحّلة). يستدعيان `purchaseInvoiceApi.postToAccounting`/`unpost` ثم يعيدان تحميل الفاتورة + شريط حالة (banner) نجاح/خطأ.
  - طُويت لوحة المحاسبة والحركات المالية إلى **تبويبين داخل المحرر**: «المحاسبة والقيد» (يستضيف `PurchaseInvoiceAccountingPanel` القائم) و«الحركات المالية المرتبطة» (`DocumentPaymentsTab`) — يطابقان تبويب `financial_movements` في المبيعات. تظهر فقط بعد حفظ الفاتورة (لديها id).
  - حُذف البلوك المنفصل + استيراداته من `PurchaseInvoice.tsx`.
- **تحقق:** tsc 0 · vite build OK · SPA يُقلع نظيفاً في preview (لا أخطاء console). جولة post→unpost حيّة في المتصفح تتطلب backend مُشغّلاً + جلسة مصادَقة (لم تُنفَّذ — مغطّاة backend عبر اختبار E2E في M1).

### [EXECUTION — task19 / M4] (توحيد قائمة فواتير الشراء + حذف «نسخ» من المبيعات — مُنفَّذ ومُتحقَّق حيّاً)
- **الملاحظة (من المالك بالسكرينشوت):** التوحيد السابق طال **المحرّر** فقط؛ **شاشة القائمة** بقيت مختلفة تماماً — المبيعات `AseelDocumentShell + AseelDenseTable`، بينما الشراء (`InvoiceList.tsx`) تصميم **بطاقي** (بطاقات إحصائية + بطاقات فواتير). كما اعترض المالك على ميزة «نسخ الفاتورة» في المبيعات (لم يطلبها).
- **التنفيذ:**
  - أُعيد بناء `InvoiceList.tsx` بالكامل على `AseelDocumentShell + AseelDenseTable` مطابقاً لقائمة المبيعات: فلاتر (بحث/الحالة/من-إلى تاريخ)، شريط أدوات موحّد (فاتورة جديدة/استيراد من تخليص/تحديث/طباعة)، أعمدة **رقم / التاريخ / المورد / الحالة (مرحَّلة·مسودة) / الإجمالي / إجراءات**، شريط حالة (العدد/الإجمالي/مرحَّلة/مسودة). حُذف التصميم البطاقي والـ pagination والتوسعة.
  - props جديدة لـ`InvoiceList`: `onCreateNew/onImport/onRefresh` — مُرّرت من `PurchaseInvoice.tsx`، وحُذف الهيدر العلوي المكرّر (أزراره صارت داخل شريط أدوات القشرة) ووسّع الحاوية لكامل العرض.
  - **إصلاح بيانات:** `sqlListToInvoice` في `PurchaseInvoice.tsx` لم يكن يُسقِط `is_posted` → كل الصفوف ظهرت «مسودة». أُضيف `isPosted: Boolean(row.is_posted)` (الحقل موجود في `PurchaseInvoiceListDto`).
  - **حذف «نسخ» من المبيعات** (قرار المالك): أُزيل `handleDuplicate` + زرّاه (مسودة/مرحّلة) + استيراد `duplicateSalesInvoice`/`Copy` من `SalesInvoicesPage.tsx`. (الـ endpoint الخلفي `duplicate` بقي دون لمس.)
- **تحقق حيّ في المتصفح (جلسة مصادَقة فعلية):** قائمة الشراء تَعرض جدول الأصيل (7 صفوف، أعمدة صحيحة)، الحالات صحيحة بعد الإصلاح (INV-0007/0002/0001=مرحَّلة، الباقي مسودة؛ شريط الحالة مرحَّلة 3/مسودة 4)، إجراءات الصف (عرض/تعديل/طباعة/تحويل/حذف)، بلا أخطاء console. قائمة المبيعات تعمل بلا زر «نسخ». tsc 0 · vite build OK.

### [EXECUTION — task19 / GR-IR] (قيدان منفصلان عبر حساب وسيط + الترحيل يستلم — مُنفَّذ)
- **قرار المالك (متدرّج):** فاتورة الشراء = **قيدان منفصلان** عبر **حساب وسيط** (GR/IR)؛ **كبسة الترحيل تستلم** البضاعة؛ **إلغاء الترحيل يمسح القيدين + المخزون**؛ إعادة الترحيل تعيد كل شيء بنفس الرقم. المبيعات متماثلة سلفاً (قيد فاتورة + قيد تكلفة) — تحقّق فقط بلا تغيير. النطاق: الفاتورة **المحلية** فقط (المستورد مخزونه عبر الشحنة).
- **حساب الوسيط:** `2106 «بضاعة مُستلَمة لم تُفوتَر (GR/IR)»` (Liability) في `seed_professional_coa` + `logistics.services._resolve_gr_ir_account` (إنشاء تلقائي للمستأجرين القائمين — لا migration).
- **`post_to_accounting` (محلي):** قيدان بدل واحد —
  - قيد الفاتورة (`PURCHASE_INVOICE`): مدين **الوسيط**(البضاعة)+ضريبة+رسوم+بنود مصروف / دائن المورّد.
  - قيد الاستلام (`PURCHASE_GRN`): مدين المخزون / دائن **الوسيط** + **إدخال مخزون فعلي** للمستودع الافتراضي (توزيع التكلفة تناسبياً لكل بند فيتطابق GL مع WAC). كله **ذرّي** (transaction.atomic). يُتجاوز إن كانت الفاتورة مستلمة مسبقاً (منع ازدواج).
- **`unpost`:** يحذف `['PURCHASE_INVOICE','PURCHASE_GRN','PURCHASE_RECEIPT']` + يعكس المخزون + يحجز رقم `PURCHASE_INVOICE` (task19). ⇒ القيدان والمخزون يُمسحان معاً، والوسيط يعود صفراً.
- **تحقّق:** اختبار `logistics/tests/test_purchase_grir_lifecycle.py` (قيدان متّزنان، الوسيط=0، مخزون داخل، post→unpost→repost نفس الرقم، idempotent ×N) + `sales/tests/test_sales_post_unpost_stock.py` (تماثل المبيعات). **190/190 أخضر**، لا migration drift.

### [ORPHANS & PENDING — task19]
- نقطة `accounting/views.py PurchaseReceiptViewSet` (`PURCHASE_RECEIPT`، أداة قيد استلام يدوية مستقلة) ما زالت تدائن المورّد مباشرةً (بلا وسيط) — خارج نطاق GR/IR عمداً (لا تمسّ دورة الفاتورة/المخزون). تُترك كما هي.
- الفاتورة **المستوردة** (صفقة/شحنة/تخليص): الترحيل يبقى قيداً واحداً ومخزونها عبر الشحنة — خارج النطاق بقرار المالك (الأكثر أماناً).
- الاستلام الجزئي/متعدد المستودعات: الترحيل يستلم الكل للمستودع الافتراضي؛ نافذة «الاستلام» المنفصلة تبقى للحالات المتقدمة.

## [AUDIT — task17, 2026-06-14] (تراجع عن الترحيل + حذف متسلسل للقيود + فصل قيد البيع النقدي)

طلب المالك: (1) للمستندات المرحَّلة الستة (فاتورة مبيعات/شراء، صفقة، شحنة، تخليص جمركي، نقل محلي) منع التعديل/الحذف المباشر مع تحذير + إجراء «تراجع عن الترحيل» يحذف **كل** قيود المستند (cascade) ويُرجعه مسودة، ذرّياً. (2) فصل قيد البيع النقدي إلى قيدين مستقلين: قيد الفاتورة (Dr ذمم / Cr إيراد + Dr تكلفة / Cr مخزن) ووصل دفع مستقل (Dr نقدية / Cr ذمم) لا يولّده ترحيل الفاتورة.

### الأسباب الجذرية (مُتحقَّق منها بالكود)
- **النظام كان يستخدم «قيوداً عكسية» لا الحذف:** `LOGISTICS_PAYMENT_UNPOST`/`CLEARANCE_PAYMENT_UNPOST`/`PURCHASE_INVOICE_REVERSAL`/`LOCAL_SHIPMENT_REVERSAL` تُنشئ قيداً معاكساً وتُبقي الأصل — لا حذف فعلي. المطلب الجديد: حذف القيود نفسها وإرجاع المستند لمسودة.
- **قيد البيع النقدي كان مدمجاً (task16 Section B):** `post_sales_invoice` كان يدين الذمم بالكامل ثم يُسوّي النقدي (Dr صندوق / Cr ذمم) في **نفس** القيد. المطلب: نزع تسوية النقدي من قيد الفاتورة تماماً.

### قرارات المالك (2026-06-14)
- Feature 2: **فصل** القيد لقيدين. وصل الدفع = **إعادة استخدام `CustomerPayment`** (post_customer_payment يُنشئ Dr نقدية / Cr ذمم مستقلاً أصلاً). تنفيذ **كل شيء دفعة واحدة**.

### [EXECUTION — task17]
- **الطبقة المشتركة (Core/DRY):**
  - `accounting.services.unpost_document(*, tenant_id, reference_id, journal_reference_types, stock_reference_types=(), user, document_label)` — المسار المركزي الوحيد للتراجع: يحذف كل `JournalHeader` لـ (tenant + reference_id + reference_type ∈ types) — أسطر القيد تُحذف cascade — ثم يعيد حركات المخزون، **ذرّياً** + audit log. النطاق محصور بدقة بقيود المستند وحده.
  - `inventory.services.reverse_stock_movements(...)` + `_recompute_product_stock(product)` — تحذف حركات المستند وتعيد احتساب `quantity_on_hand`/`avg_cost` بإعادة تشغيل بقية الحركات زمنياً (WAC دقيق، لا تقريب يفسد المتوسط).
  - `core.api_defaults.POSTED_DOC_WARNING` — رسالة موحّدة «هذا المستند مرحَّل…».
- **توصيل المستندات الستة (backend):** كل viewset أُضيف له `perform_update`/`destroy` يحظران تعديل/حذف المرحَّل (يردّان 400 + `{detail, can_unpost:true}`) + إجراء `POST .../unpost/`:
  - فاتورة مبيعات (`SALES_INVOICE`,`SALES_DELIVERY_COGS` + مخزون `SALE`,`STOCK_ISSUE`) → status=draft، journal=None، amount_paid=0، إعادة الشيكات Under_Collection→Draft.
  - فاتورة شراء (`PURCHASE_INVOICE`,`PURCHASE_RECEIPT` + مخزون `PURCHASE_INVOICE`) → is_posted=False، receipt_status=not، received_quantity=0. (استُبدل المسار العكسي القديم بالحذف.)
  - شحنة (`LOGISTICS_SHIPMENT` + مخزون `SHIPMENT`؛ «مرحّلة» = وجود قيد/حركة).
  - نقل محلي (`LOCAL_SHIPMENT`؛ استُبدل العكسي بالحذف).
  - صفقة/تخليص: القيود مفاتيحها على الدفعات (LOGISTICS_PAYMENT / CLEARANCE_PAYMENT) لا على المستند الأب — فالـ unpost يمرّ على الدفعات المرحَّلة ويحذف قيد كلٍّ ويعيدها مسودة.
- **Feature 2 (فصل قيد البيع النقدي):** أُزيلت كتلة تسوية النقدي من `post_sales_invoice` بالكامل (نقدي الفاتورة النقدية + `attached_cash` على الآجل) — قيد الفاتورة الآن يدين الذمم بالكامل ويدائن الإيراد/الضريبة (+COGS) فقط؛ `amount_paid` لم يعد يشمل النقدي. التحصيل يُسجَّل كـ `CustomerPayment` مستقل (Dr نقدية / Cr ذمم). **قرار جراحي:** تسوية الشيكات بقيت داخل قيد الفاتورة (المطلب نصّ على النقدي فقط، وفصلها يكسر دورة حياة الشيك). **أثر جانبي موثّق:** مبلغ النقدي المرفق عبر `attach_payment_voucher`/`attach_voucher_and_post` لم يعد يُرحَّل عند الترحيل — استُبدل بوصل دفع مستقل.
- **Feature 2 (شراء — امتداد بطلب المالك بعد مراجعة شاشة فاتورة الشراء):** نفس الفصل طُبِّق على **فاتورة الشراء** في كلا مساري الترحيل: `PurchaseInvoiceViewSet.post_to_accounting` و`receive_purchase_invoice` (task15). الترحيل يقيّد Dr مخزون/ضريبة / Cr ذمم المورد بالكامل فقط — أُزيلت تسوية الصندوق. الدفع للمورد أصبح **وصل دفع مستقل** عبر `SupplierPayment` (Dr ذمم المورد / Cr صندوق). الواجهة: `PurchaseInvoiceAccountingPanel` — أُزيلت أسطر التسوية النقدية من معاينة القيد، وأُضيف قسم «وصل دفع للمورد» (مبلغ + حساب صندوق → `purchaseInvoiceApi.addSupplierPayment` ينشئ ويرحّل SupplierPayment). اختبارا Section B للشراء (`test_pi_subledger_routing` + `test_local_invoice_receive::test_cash_receive…`) أُعيد ضبطهما (ap_debit=0، لا سطر صندوق).
- **الواجهة:** `salesApi.unpostSalesInvoice` + إجراء «تراجع عن الترحيل» في شريط `SalesInvoiceEditor` (يظهر مفعّلاً عند الترحيل فقط) · زر «تراجع عن الترحيل» + تحذير في `PurchaseInvoiceAccountingPanel` (الحالة المرحَّلة) عبر `purchaseInvoiceApi.unpost` القائم.
- **اختبارات (TDD):** `accounting/tests/test_unpost_document.py` (3): حذف محصور بالمستند فقط · عكس مخزون بإعادة التشغيل (WAC دقيق) · حظر حذف المرحَّلة ثم سماحه بعد التراجع عبر `/sales/invoices/{id}/unpost/`. وأُعيدت كتابة اختبارَي Section B (`sales/tests/test_subledger_routing.py`: قيد الفاتورة النقدية يدين الذمم فقط، لا سطر صندوق، amount_paid=0). **اختبار شراء Section B لم يُمَسّ (Feature 2 مبيعات فقط).**
- **تحقق:** backend **174/174** خضراء · tsc 0 · vite build OK · `manage.py check` 0 · `makemigrations --check` لا انحراف (لا تغييرات نماذج). لم يُتحقق في متصفح حي للشاشات الداخلية (نفس قيد المهام السابقة).

### [ORPHANS & PENDING — task17]
- [ ] واجهة «تراجع عن الترحيل» للصفقة/الشحنة/التخليص/النقل المحلي: الـ endpoints جاهزة ومُختبرة backend؛ أزرار الواجهة على غرار المبيعات/الشراء عند لمس تلك الشاشات لاحقاً.
- [ ] واجهة «وصل دفع» من داخل الفاتورة (Feature 2) تعتمد مسار `CustomerPayment` القائم (تبويب «سند مالي/payments»)؛ تدفّق إنشاء وصل دفع مخصّص داخل المحرر يُكمَّل عند جولة UI حية.
- (موروث: قيود العكس القديمة `*_UNPOST`/`*_REVERSAL` لمسارات الدفعات الفردية بقيت كما هي — لم تُحذف؛ مسار المستند الجديد لا يعتمدها.)

## [AUDIT — task11, 2026-06-10] (Staff-Engineer full audit)

### 🔴 حرجة — Data loss / Data isolation
- **A1. أرشيف الفواتير يعلّق ويُفقد البيانات** — `OldPurchaseInvoice.tsx:173` يستدعي `onSnapshot(q, {next, error})` بصيغة object بينما شيم `sqlApiClient.ts:188` يمرر الـ callback إلى `Promise.then()` — non-function تُتجاهل بصمت ⇒ لا يصل أي رد، الـ spinner أبدي (التعليق). الحذف في `deleteInvoice` (line 138) حذف نهائي hard-delete عبر `/api/mapper/` بلا soft-delete ولا أي عزل.
- **A2. طبقة mapper بلا عزل tenant إطلاقاً** — `bridge/views.py`: كل مستندات `FirestoreMirrorDoc` (invoices/suppliers/users/...) عالمية لكل الشركات؛ أي مستخدم مصادق يقرأ/يكتب/يحذف أي مسار. `_sync_partner_from_mirror_supplier` يستخدم `Tenant.objects.first()`.
- **A3. فلتر mapper يقارن boolean بـ string** — `bridge/views.py:135`: `isHistorical__exact=true` يصل كنص `"true"` ويُقارن بـ `True` ⇒ القائمة المفلترة فارغة دائماً.
- **A4. `tenantId: 1` ثابت** في `components/legacy/firestoreService.ts` (items/partners/deals: ~16 موضعاً) + صفحات `components/sql/*` ⇒ كل شاشات الأصناف/الموردين legacy تقرأ وتكتب شركة 1 مهما كانت الشركة النشطة.

### 🟠 عالية — منطق الشركات/الفروع
- **B1. لا يوجد مفهوم Branch نهائياً** — لا موديل، لا API، لا UI (grep شامل backend+frontend). المطلوب: فرع = شجرة حسابات مشتركة + فواتير/مخزون/تقارير مستقلة. لا يوجد موديل Warehouse أصلاً — المخزون = `StockMovement` لكل tenant بلا بُعد فرع.
- **B2. الـ Active Context ثابت في صفحات العرض** — `Dashboard.tsx:46` يطبع «شركة النور للتجارة العالمية» hardcoded؛ `AboutUs.tsx:130,152,252` «شركة كترا KTRA» hardcoded؛ `TenantSettings` لا يحتوي حقل شعار (logo) أصلاً. `CompanySwitcher` بأعلى الشاشة يعمل، لكن محتوى الصفحات لا يتبع الشركة النشطة.
- **B3. إنشاء شركة موجود وسليم جزئياً** — `tenants/services.create_company` يزرع COA معياري (61 حساباً) + TenantBooks + Membership ولا ينسخ أصنافاً/شركاء (متوافق مع المطلوب)، لكن لا يستدعي `invalidate_tenant_cache()` (single-tenant cache قد يبقى قديماً)، ولا توجد اختبارات تثبت فراغ الأصناف/الموردين.

### 🟡 متوسطة — محاسبية
- **C1. `validate_journal_entry`** يتحقق من وجود Partner/CostCenter بلا scoping على الـ tenant (`accounting/services.py:302-309`) — يمكن ربط قيد بشريك شركة أخرى.
- **C2. سليم (مُدقَّق):** القيد المزدوج صارم (`post_journal` يفرض debit==credit بعد quantize + idempotency + select_for_update)؛ ميزان المراجعة/قائمة الدخل tenant-scoped ومتوازنة؛ ترقيم الفواتير per-tenant ذرّي عبر `TenantBook.get_next_number` (select_for_update). ينقصه فقط بُعد الفرع (B1).
- **C3. الكفالة/الضرائب:** حقول الكفالة موجودة في الصفقات/فواتير الشراء (frontend types). لا منطق محاسبي خلفي لها — تُعرض فقط. تُراجع مع سياسة «الكفالة على المشتري النهائي» عند بناء الفروع (لا تغيير أعمى الآن).

### 🟡 متوسطة — UI/UX (مطابقة للـ screenshots)
- **D1. فراغ ضخم وسط شاشة فواتير المبيعات** — `SalesInvoicesPage.tsx:606` يضع جدول الفواتير في `tabs` السفلية (مقيدة `max-height:220px` في `index.css:540`) ويترك `children` (منطقة `aseel-gridwrap` المرنة `flex:1`) فارغة ⇒ منطقة بيضاء فارغة تتمدد والجدول مكبوس بالأسفل. نفس النمط في `SalesSettingsPage.tsx:573` (`header={<></>}` والمحتوى كله في tabs).
- **D2.** بقية شاشات `AseelDocumentShell` (~25 مستهلكاً) تحتاج مسحاً لنفس سوء الاستخدام.

## [MILESTONES — task11] (مرتبة بالأولوية)
1. **M1 أرشيف الفواتير (data-loss أولاً):** إصلاح onSnapshot object-form + فلتر mapper boolean + عزل tenant للـ mapper + soft-delete.
2. **M2 Active Context ديناميكي:** logo في TenantSettings + Dashboard/AboutUs/طباعة من إعدادات الشركة النشطة.
3. **M3 تنظيف العزل:** إزالة tenantId:1 الثابت + إصلاح bridge first() + scoping للـ Partner/CostCenter في القيود.
4. **M4 ميزة الفروع الحقيقية:** Branch model + بُعد فرع على الفواتير/المخزون/القيود + ترقيم لكل فرع + switcher + تقارير لكل فرع. (قرار موثّق: الأصناف مشتركة على مستوى الشركة مثل شجرة الحسابات.)
5. **M5 اختبارات التأسيس:** شركة جديدة = COA مزروعة + أصناف/شركاء/فواتير صفر.
6. **M6 UI:** نقل المحتوى الرئيسي إلى gridwrap + مسح بقية الشاشات + تباين.

## [ORPHANS & PENDING]
- [x] **Task 11 — M1** أرشيف الفواتير: onSnapshot observer-form (hang) + soft-delete في mapper + عزل tenant كامل للـ mapper (FK + backfill + membership) + إصلاح فلتر boolean + 8 اختبارات (bridge/tests)
- [x] **Task 11 — M2** Active company context: `TenantSettings.logo_url` (+migration+serializer) · `useTenantSettings` hook · Dashboard/AboutUs/InvoicePrintView ديناميكية · حقل شعار + رفع في GroupConstants · aboutLinks أصبحت tenant-scoped · (قرار: صفحات ما قبل الدخول تبقى بهوية المنصة KTRA)
- [x] **Task 11 — M3** إزالة tenantId:1 الثابت (legacy firestoreService ~16 موضعاً + Sql* pages → resolveTenantId) · scoping Partner/CostCenter في validate_journal_entry (+3 اختبارات) · إزالة fallback «Tenant.objects.first()» من partners/signals · invalidate_tenant_cache بعد create_company · (ملاحظة: `default=1` على tenant FKs في الموديلات لا يزال موجوداً — خطر صامت موثق، يتطلب مايغريشن واسعة)
- [x] **Task 11 — M4** ميزة الفروع: موديل Branch + فرع رئيسي backfill · بُعد branch على SalesInvoice/StockMovement/JournalHeader/TenantBook · ترقيم مستقل لكل فرع (SI-{t}-{CODE}-n) · X-Branch-Id + get_branch (تحقق ملكية) · فلترة فواتير/ميزان/GL بالفرع · BranchViewSet (manager-only، تعطيل لا حذف) · BranchSwitcher بالواجهة · 7 اختبارات. (قرارات: COA/أصناف/شركاء مشتركة tenant-level · الفرع الرئيسي يرى القيود القديمة بلا فرع · متوسط التكلفة موحّد على مستوى الشركة)
- [x] **Task 11 — M5** اختبارات تأسيس الشركة (4 اختبارات): COA معيارية كاملة بالتسلسل الهرمي · أصناف/شركاء/فواتير صفر · دفاتر 10×15 · عضوية مدير · لا تسرب من شركة قائمة
- [x] **Task 11 — M6** UI: إصلاح منهجي في `AseelDocumentShell` — children فارغة + tabs ⇒ الـ tabs تشغل المنطقة المرنة كاملة (يصلح ~15 صفحة تقارير دفعة واحدة) · SalesInvoicesPage/SalesSettingsPage نقل المحتوى لـ children · التباين سليم من task9 (ink-soft #353426 + status palette)
- [x] **Task 11 — M7** (إصلاح بعد بلاغ المالك: شركة جديدة تعرض موردين/أصناف/زبائن/مهام قديمة + COA فارغة) عزل القراءة: Partner/Product/Category/StockMovement viewsets كانت **بلا فلترة tenant في القراءة** ⇒ get_queryset مع .none() عند الغياب · JournalViewSet كان tenant=None→all() · «tasks» في mapper أصبحت tenant-scoped (+backfill) · مايغريشن 0008 تعالج تلقائياً أي شركة ناقصة التأسيس (COA صفر→زرع، فرع رئيسي، إعدادات، دفاتر) + أمر `heal_company_seed` · 7 اختبارات endpoint-level (test_read_isolation.py). **درس:** M5 فحص الداتا في DB لا الـ endpoints — اختبارات العزل يجب أن تضرب نفس URLs التي تستعملها الشاشات.
- _Task 11 كامل — لا عناصر مفتوحة. Backend 106 tests · tsc 0 · vite build OK · eslint 0._

## [AUDIT ROUND 2 — task11 R2, 2026-06-11] (تدقيق محاسبي + كود + منطق كامل)
بناءً على طلب المالك («أودت كامل لا فيتشر الشركات فقط») — مسح ثانٍ شامل: مسارات الترحيل كلها، الدفعات، المراجيع، الإشعارات، الضريبة، الإغلاق السنوي، الشيكات، العملات، الصلاحيات، أمن الإعدادات، كاش الواجهة.

### اكتُشف وأُصلح (الكل باختبار إثبات قبل الإصلاح)
- **R2-A1 🔴 discount_percent يكسر توازن القيد:** كان يُطبَّق على ترويسة الفاتورة فقط دون الأسطر ⇒ قيد الإيراد (من الأسطر) ≠ المدين (من الإجمالي) ⇒ ترحيل أي فاتورة بخصم نسبي **يفشل**، ولو نجح لكانت الضريبة على أساس قبل الخصم. الإصلاح في `recalculate_invoice_amounts`: نسبة موحّدة بعد الخصمين، الضريبة بعد كل الخصومات، **الترويسة = مجموع الأسطر بالقرش** (لا انحراف تقريب). +3 اختبارات.
- **R2-A2 🔴 كشف الضريبة يجمع المراجيع بدل خصمها:** مرجع البيع كان يُضاف لضريبة المخرجات (+) ومرجع الشراء للمدخلات (+) ⇒ كشف متضخم من الجهتين. أُصلح بالـ netting الصحيح. +1 اختبار.
- **R2-A3 🔴 الشيكات بلا قيود ولا آلة حالات فعلية:** `transfer_cheque` كانت كوداً ميتاً والواجهة تُغيّر status بـ PATCH خام (أي قفزة حالة ممكنة، صفر GL) ⇒ «شيكات برسم التحصيل» لا تُفرَّغ أبداً. الآن: endpoint رسمي `cheques/{id}/transfer/` يفرض الانتقالات ويرحّل: تحصيل (Dr صندوق/بنك ÷ Cr شيكات برسم التحصيل)، ارتداد (Dr ذمم العميل ÷ Cr شيكات)، تسوية (Dr صندوق ÷ Cr ذمم) — idempotent + بُعد فرع؛ PATCH الخام للحالة محظور؛ الواجهة تعرض الحركات المتاحة من الحالة الحالية فقط؛ حالة Settled أُضيفت. +5 اختبارات. (ملاحظة: `Cheque.change_status` القديمة بقيت legacy غير مستخدمة — المسار الرسمي transfer/.)
- **R2-A4 🔴 سبب «شجرة الحسابات صفر» الجذري:** `accountingApi` و`inventoryApi` و`dashboardApi` لا ترسل X-Tenant-Id إطلاقاً — كانت تعيش على auto-resolve أحادي الشركة الذي يتعطل لحظة وجود شركة ثانية ⇒ كل نداءات المحاسبة بلا شركة ⇒ قوائم فارغة. الآن الثلاثة ترسل X-Tenant-Id + X-Branch-Id دائماً.
- **R2-B1 🟠 DEBUG=True ثابت في الإنتاج:** أي خطأ يكشف traceback كاملاً. الآن env-driven وآمن افتراضياً (`DJANGO_DEBUG=1` للتطوير — موجودة في .env.example أصلاً). أثر جانبي مُصلَح: `/api/dashboard/` كان عاماً بلا مصادقة — أصبح يتطلب توكن عبر DEFAULT_PERMISSION_CLASSES.
- **R2-B2 🟠 الأدوار غير مفروضة إطلاقاً:** «مستعرض» كان يرحّل ويحذف ويعدّل. `core/permissions.TenantRolePermission`: viewer = قراءة فقط، مفروضة عبر ApiAuthAndUser + DEFAULT_PERMISSION_CLASSES (تشمل viewsets بلا permission_classes صريحة). فحوصات manager-only القائمة بقيت. +3 اختبارات.
- **R2-C 🟡 duplicate_invoice** لم يكن يمرر الفرع للترقيم/النسخة — أُصلح.

### مُدقَّق وسليم (لا تغيير)
- دفعات العملاء: قفل صفوف + توزيعات + فروقات عملة لكل توزيع (P-H-8) ✓ · الإغلاق السنوي ✓ · الإشعارات الدائنة/المدينة متوازنة ✓ (بلا فصل VAT — موثق أدناه) · WAC للمخزون ✓ · مراجيع البيع تعكس القيد والمخزون ✓ · Dexie cache مفتاحه tenant_id ✓ · login/signup/mapper/health غير متأثرة بتشديد الـ defaults ✓.

### [ORPHANS & PENDING — R2 المتبقي]
- [ ] الإشعار الدائن لا يفصل حصة VAT (كامل المبلغ على الإيراد) — يحتاج حقل ضريبة على CreditDebitNote وقرار سياسة.
- [ ] «الكفالة» حقول عرض فقط بلا منطق خلفي — تحتاج سياسة محاسبية مكتوبة من المالك.
- [ ] `default=1` على tenant FKs (chip مفتوح) · توحيد آلتي حالات الشيك (حذف change_status legacy) · SECRET_KEY الافتراضي في الريبو (يُفضَّل فرض env في الإنتاج).
- _Backend **118 tests** · tsc 0 · vite build OK · eslint 0 — 2026-06-11._

## [AUDIT — task12, 2026-06-11] (الاستيراد end-to-end + إدارة الشركات — مطابق لسكرينشوتات المالك)
نطاق الجولة: مسار الاستيراد كاملاً (صفقة → شحنة → تخليص → نقل محلي → فاتورة شراء → بيع) + إدارة الشركات/الأعضاء. النسخ مثبتة وحديثة (2026-06): Django 6.0.1 / DRF 3.16 / React 19.2 / Vite 6.2 — لا تبعيات جديدة مطلوبة.

### 🔴 Blockers — منطق مسار الاستيراد
- **T12-A1 محدد المراحل مكسور (سكرينشوت ٤):** `DealStageControl` يعرض ٣ مراحل يدوية حرة («اختر واحدة من المراحل الثلاث الأولى يدوياً») بينما `LogisticsDeal.VALID_TRANSITIONS` (logistics/models.py:131) يسمح فقط بالتسلسل الصارم None→sw_mfg_start→… ⇒ اختيار المرحلة ٢ أو ٣ على صفقة جديدة يُرفض دائماً (400) والقائمة ترتد إلى «اختر المرحلة». السبب الجذري: تناقض عقد UI/FSM.
- **T12-A2 إلغاء الصفقة لا يثبت:** PATCH status=Cancelled → `save()` → `_sync_legacy_status_fields` (models.py:211) يشتق status من `_STATUS_FROM_WORKFLOW` (None→'Open') ويدوس Cancelled بصمت ⇒ زر «إلغاء الصفقة» بلا أثر.
- **T12-A3 المرحلة النهائية sw_released لا تُضبط أبداً:** grep كامل — لا يوجد أي كود يكتب sw_released رغم وعد الواجهة «عند حفظ فاتورة مرتبطة → مفرج عنها». الصفقات لا تصل نهاية الخط أبداً.
- **T12-A4 زر «تحويل إلى فاتورة شراء» مسار ميت (ImportDocumentScreen):** يفتح `/purchase-invoices/new?shipment=X` لكن لا `PurchaseInvoice.tsx` ولا `InvoiceForm.tsx` يقرآن البارامتر ⇒ نموذج فارغ بلا أي ربط. كذلك `checkConvertedInvoice` يفلتر بـ`converted_from_shipment` الذي **لا يُكتب في أي مسار خادم**، و`get_queryset` لا يدعم فلتر `shipment` أصلاً ⇒ اختصار «فاتورة #N» لا يظهر أبداً. المسار الفعلي الوحيد: مودال «استيراد من تخليص جمركي» في قائمة الفواتير.
- **T12-A5 النقل المحلي خارج نسب الفاتورة:** `build_purchase_invoice_row` يجمع شحنة+تخليص فقط؛ سجلات `LocalShipment` لا تدخل إلا يدوياً عبر `import-to-invoice` غير المكشوف في أي شاشة، وزر «ترحيل» المعروض في تبويب النقل المحلي **يقفل** import-to-invoice لاحقاً («لا يمكن استيراد شحن مُرحَّل»). ⇒ خط البيانات تخليص→نقل محلي→فاتورة مقطوع عملياً في UI.

### 🟠 عالية
- **T12-B1 حصص الشحن صفر (سكرينشوت ١):** `add_deal` يُنشئ `LogisticsShipmentDeal` بدون استدعاء `redistribute_shipment_deal_allocations` ⇒ «مجموع الحصص 0.00 مقابل إجمالي 781.10». و`remove_deal` لا يعيد التوزيع كذلك.
- **T12-B2 تسريب عابر للشركات في add_deal:** `LogisticsDeal.objects.get(pk=deal_id)` بلا فلتر tenant — يمكن ربط صفقة شركة أخرى بشحنتك.
- **T12-B3 TenantViewSet بلا حواجز تعديل/حذف:** create فقط مُسوَّر؛ أي عضو (حتى viewer على مستوى الشركة) يستطيع إعادة تسمية الشركة أو **حذفها هرد-دليت** (destroy الموروث). لا يوجد أي endpoint لإدارة الأعضاء (إضافة/دور/إزالة) رغم وجود ROLE_CHOICES (manager/accountant/staff/viewer) — ولا أي UI (CompanySwitcher = إنشاء/تبديل فقط).
- **T12-B4 ترقيم الصفقات client-side:** `getNextDealNumber` يحسب max(D-n)+1 في المتصفح ⇒ سباق بين مستخدمين يصطدم بـ`unique(tenant,ref_number)` ويرجع 500.

### 🟡 متوسطة — UX
- **T12-C1 حقل المورد يعرض #45 خام (سكرينشوت ٣):** DealForm.tsx:865 يعرض `#${id}` بدل الاسم؛ والاسم في حقل منفصل «الاسم» — ازدواجية مع SupplierSearch داخل تبويب البيانات الأساسية.
- **T12-C2 تناقض رقم الصفقة الجديد (سكرينشوت ٢):** الهيدر «— جديدة —» بينما شريط الحالة والتبويب يعرضان D-0001 المولّد مسبقاً.
- **T12-C3 شارة «مزامنة نشطة / متصل» (سكرينشوت ٥):** نص مضلل في وضع الخمول (لا مزامنة جارية) — يجب «متصل» فقط.
- **T12-C4 حالة completed بلا تسمية في DealForm:** `getOperationalStatus('completed')` يسقط إلى «أولية».
- **T12-C5 تخطيط الصناديق المستقلة التمرير:** متبقٍ على مستوى المنصة (أُصلح جزئياً في task11-M6) — يتطلب جولة تصميم مخصصة بمتصفح حي؛ موثق هنا كـ pending وليس ضمن نطاق الكود الأعمى لهذه الجولة.

### مُدقَّق وسليم (لا تغيير)
- إشارات تقدم المراحل التلقائية (ربط شحنة→sw_wait_arrival، إنشاء تخليص→sw_wait_clearance) تعمل بـbulk update مقصود يتجاوز الحارس ✓ · محرك landed-cost (Decimal + penny-balancing + dual share value/volume) سليم رياضياً ✓ · استيراد التخليص يفرض اكتمال دفع الشحن بالدولار مع تجاوز مدير ✓ · exception handler يحول DjangoValidationError إلى 400 برسالة عربية ✓ · عزل tenant على Deal/Shipment/Clearance/PI viewsets (عدا B2) ✓.

### [MILESTONES — task12]
1. **M1 آلة مراحل الصفقة:** سماح حر بين المراحل اليدوية الثلاث (+من None)، حارس إلغاء يثبّت Cancelled، sw_released عند إنشاء فاتورة مرتبطة بالصفقة، تسمية completed. ✅ قبول: اختيار أي مرحلة يدوية على صفقة جديدة يثبت ويُعاد تحميله؛ الإلغاء يبقى بعد refetch؛ استيراد فاتورة يجعل الصفقة «مفرج عنها». اختبارات backend.
2. **M2 حصص الشحن:** إعادة توزيع تلقائي في add_deal/remove_deal + tenant scoping + زر إعادة توزيع في تبويب الصفقات. ✅ قبول: ربط صفقتين ⇒ مجموع الحصص = إجمالي الشحن.
3. **M3 خط النسب إلى الفاتورة:** زر التحويل يفتح مودال الاستيراد مُسبق الاختيار على تخليص الشحنة؛ كتابة converted_from_shipment + فلتر shipment في القائمة (اختصار «فاتورة #N» يعمل)؛ كشف «استيراد إلى الفاتورة» للنقل المحلي غير المرحّل مع تلميح ترتيب العمليات. ✅ قبول: من شاشة الاستيراد يمكن إنشاء الفاتورة ورؤيتها، ونقل تكلفة النقل المحلي إليها كرسم.
4. **M4 إدارة الشركة والأعضاء:** manager-only على تعديل الشركة، منع الحذف الهرد، endpoints أعضاء (list/add/change-role/remove مع حماية آخر مدير)، UI: إعادة تسمية + إدارة أعضاء من CompanySwitcher. ✅ قبول: عضو staff لا يعدّل/يحذف؛ مدير يضيف عضواً بدور ويظهر فوراً.
5. **M5 ترقيم خادمي + UX صغيرة:** توليد ref_number في perform_create عند الغياب/التكرار؛ عرض اسم المورد؛ توحيد عرض رقم الصفقة الجديد؛ نص الشارة «متصل». ✅ قبول: tsc/build/eslint نظيف + اختبارات الترقيم.

### [EXECUTION — task12, 2026-06-11] (كل المعالم منفّذة)
- **M1:** `MANUAL_WF_STAGES` + توسيع `VALID_TRANSITIONS` (حر بين الثلاث اليدوية، sw_wait_intl_ship→sw_wait_arrival يبقى) · حارس Cancelled في `_sync_legacy_status_fields` · إشارة `release_deal_on_purchase_invoice` (PI مرتبطة بصفقة → sw_released + مزامنة الكاش) · DealForm: حالة completed «مكتملة — مفرج عنها».
- **M2:** add_deal/remove_deal يستدعيان `redistribute_shipment_deal_allocations` + `tenant=shipment.tenant` في جلب الصفقة · زر «⟳ إعادة توزيع الحصص» في تبويب الصفقات (ImportDocumentScreen).
- **M3:** زر التحويل → `/purchase-invoices?import_shipment=N` → المودال يفتح مسبق الاختيار (prop `initialShipmentId`) · `converted_from_shipment` يُكتب في `import_invoices_from_clearance` · فلتر `?shipment=` في PurchaseInvoiceViewSet · تبويب النقل المحلي: زر «إلى الفاتورة» (import-to-invoice) عند وجود فاتورة محوّلة + تلميح ترتيب «إلى الفاتورة قبل الترحيل» + عرض «في الفاتورة X» بعد النقل.
- **M4:** TenantViewSet: update/partial_update مدير فقط، destroy محظور (400) · `GET|POST /tenants/companies/{id}/members/` + `members/change-role/` + `members/remove/` مع حماية آخر مدير · `CompanyManagementModal` (إعادة تسمية + جدول أعضاء + إضافة بدور عبر قائمة منسدلة Dropdown تسحب جميع مستخدمي النظام من `/hr/users/` بدلاً من كتابة الإيميل يدوياً) من زر «إدارة الشركة» في CompanySwitcher · تسمية دور «مستعرض» أُضيفت.
- **M5:** `perform_create` للصفقات يولّد/يصحّح `D-####` (يشمل soft-deleted) و`ref_number` صار اختيارياً بالـ serializer · حقل المورد يعرض الاسم (وID في tooltip) · رقم الصفقة الجديد «D-000N (جديدة)» بدل «— جديدة —» · شارة المزامنة «متصل» عند الخمول.
- **تحقق:** backend **140 tests** (118 سابقة + 22 جديدة: test_deal_workflow_machine 11 + test_company_admin 11) · tsc 0 · vite build OK · eslint 0 errors. لم يُتحقق في متصفح حي (يتطلب باك-إند بيانات) — فحص ما بعد النشر: محدد المراحل على صفقة جديدة، إلغاء صفقة، ربط صفقتين بشحنة (الحصص)، زر التحويل من شاشة الاستيراد، «إدارة الشركة» للمدير ولموظف.

### [ORPHANS & PENDING — task12 المتبقي]
- [ ] T12-C5 توحيد تمرير الصفحة (الصناديق المستقلة التمرير) — جولة تصميم بمتصفح حي على الشاشات الفعلية، لا تغيير أعمى.
- [ ] الفواتير القديمة (قبل task12) بلا `converted_from_shipment` — الاختصار يعمل لها عبر fallback مطابقة `shipment` في checkConvertedInvoice (لا backfill مطلوب).
- (موروث من R2: VAT الإشعار الدائن · سياسة الكفالة · `default=1` على tenant FKs · حذف change_status القديمة · فرض SECRET_KEY من env.)

## [AUDIT — task13, 2026-06-12] (Daftra-parity sweep — 7 defects from owner screenshots, root causes verified in code)

### Protocol 1 — النسخ (2026-06-12)
Stack مثبت وحديث: Django 6.0.1 / DRF 3.16.1 / React 19.2 / Vite 6.2 / TS 5.8 / Tailwind 4.3 — **لا تبعيات جديدة مطلوبة** لأي معلم أدناه. (باتش اختياري متبقٍ من R2: Django 6.0.1→6.0.6.)

### الأسباب الجذرية (مُتحقَّق منها بالكود لا بالتخمين)
- **T13-D7 🔴 (الأخطر — تسريب بيانات):** `core/dashboard_api.py:30` يستدعي `_get_tenant(request)` ثم **لا يستخدمه أبداً** — كل الـ querysets عالمية (`LogisticsDeal/LogisticsShipment/LogisticsPayment/PurchaseInvoice/Product/StockMovement/JournalHeader`) ⇒ الشركة الجديدة ترى 66 صفقة وقيمة مخزون 32,924 لشركات أخرى، بأسماء الموردين والمبالغ. هذا خرق عزل وليس مجرد UX.
- **T13-D1 (سكرول متداخل):** `AseelDocumentShell` مصمم كنافذة ثابتة الارتفاع بأربع مناطق سكرول داخلية: `.aseel-doc{height:100%}` + headband `max-height:160px;overflow-y:auto` + `.aseel-gridwrap{flex:1;overflow:auto}` + `.aseel-bottom{max-height:220px;overflow-y:auto}` + `.aseel-totals{overflow-y:auto}` (index.css:448–579)، و`DealForm.tsx:853` يلفّه بـ`height:calc(100vh-13rem)`. سكرولر الصفحة الفعلي موجود في `AppLayout` (`main.app-content{overflow:auto}`) — الحل: الـ shell يصبح تدفقاً طبيعياً (إزالة الارتفاعات/overflow الداخلية) فيُصلح ~25 شاشة مستهلكة دفعة واحدة.
- **T13-D2/D3 (تبويبات مخفية):** `.aseel-tab` خلفية `#e4e1d0` على لوحة `#f2f0e4` بحجم 11px (index.css:553) — تباين شبه معدوم؛ نفس الـ strip في الصفقات وفواتير الشراء وكل مستهلكي الـ shell.
- **T13-D4 (منتقي أصناف ثقيل):** بنود الصفقة/فاتورة الشراء تفتح `ItemSearchModal` (مودال كامل) — DealForm.tsx:957، InvoiceForm.tsx:835. المطلوب نمط دفترة: dropdown autocomplete مرساة بخلية الصنف، فلترة فورية، أقرب تطابق أولاً، «+ إضافة صنف جديد» سطراً داخلياً.
- **T13-D5 (شجرة حسابات ناقصة):** البذرة موجودة (`tenants/services.COA_DATA` تشمل 1103 مدينين/2101 دائنين/VAT) **لكن مسارات ترحيل فعلية تتوقع حسابات غير مبذورة:** «شيكات برسم التحصيل» (الاختبارات تنشئ 1108 يدوياً؛ `accounting/services.py:681` يبحث بالاسم/بادئة 1106)، أب الصناديق `1110` (`accounting/cashbox.py:9`)، ولا توجد حسابات مردودات مبيعات/خصومات/عمولات بنكية ⇒ شركة جديدة تفشل أو تتشوه قيودها أول ما تستعمل الشيكات/الصناديق. + عرض الشجرة ضيق (محشورة في tab panel).
- **T13-D6 (ازدواج التسمية + موضع السنة المالية):** `AppLayout.tsx:70-74` — chip العنوان يكرر تسمية الشريط الجانبي، وسطر «[السنة المالية {year}]» (عرض فقط، لا منطق خلفه) معلق أعلى الشاشة؛ ينقلان إلى شريط الحالة السفلي.

### [MILESTONES — task13] (بالأولوية: تسريب البيانات ← محاسبة ← تخطيط)
1. **M1 عزل الداشبورد (D7):** فلترة tenant (+فرع حيث ينطبق) على كل querysets الداشبورد + مسح بقية الـ endpoints التجميعية عن نفس النمط. ✅ قبول: اختبار endpoint بشركتين — الشركة الجديدة صفر في كل المؤشرات و recent فارغة؛ بيانات الشركة الأخرى غير مرئية.
2. **M2 اكتمال شجرة الحسابات (D5):** إضافة الحسابات التشغيلية الناقصة إلى COA_DATA (1108 شيكات برسم التحصيل، 1110 الصناديق، مردودات/خصومات، عمولات بنكية) + heal للشركات القائمة + إزالة البحث الهش بالاسم. ✅ قبول: شركة جديدة تنفّذ دورة شيك (استلام→تحصيل→ارتداد) وإنشاء صندوق بلا إنشاء يدوي لأي حساب؛ اختبارات.
3. **M3 سكرول واحد (D1):** AseelDocumentShell يتحول لتدفق صفحة طبيعي (إزالة height:100% والسقوف الداخلية)؛ إزالة الارتفاع الثابت من DealForm؛ سكرولر وحيد في main. ✅ قبول: /deals/new وفاتورة الشراء والمبيعات بلا أي منطقة سكرول داخلية (عدا الجداول أفقياً عند الضيق).
4. **M4 تبويبات مرئية (D2+D3):** إعادة تصميم .aseel-tab/.aseel-tabs — تباين AA، حد سفلي مميز للنشط، مساحة نقر كافية. ✅ قبول: التبويبات السبعة في DealForm ظاهرة بوضوح على الشاشات كافة.
5. **M5 منتقي أصناف مدمج (D4):** مكوّن autocomplete مرساة (يحل محل ItemSearchModal في DealForm + InvoiceForm + منتقي الأصناف في SalesInvoiceEditor): كتابة→فلترة فورية→أقرب تطابق أولاً→Enter يختار→«+ إضافة صنف جديد» داخلي. ✅ قبول: إضافة بند بالكتابة والاختيار بلوحة المفاتيح فقط دون مودال.
6. **M6 تنظيف الكروم (D6):** حذف chip العنوان المكرر، نقل «السنة المالية» لشريط الحالة السفلي. ✅ قبول: لا تكرار عنوان في الداشبورد/الشجرة؛ السنة المالية بجانب المستخدم/الدور.
7. **M7 تحقق ختامي:** pytest كامل + tsc + build + eslint + تحديث الخريطة.

### [EXECUTION — task13, 2026-06-12] (كل المعالم منفّذة)
- **M1 عزل الداشبورد:** كل querysets في `core/dashboard_api.py` صارت tenant-scoped (الدفعات عبر deal/shipment لغياب FK مباشر)؛ غياب الهيدر ⇒ أصفار لا تجميع عالمي. + إغلاق ثغرة شقيقة: مفتاح `/api/agent/query/` كان hardcoded في الريبو (SELECT حر عابر للشركات بلا مصادقة) — أصبح env-only، وغياب env = رفض كل الطلبات. 3 اختبارات (`core/tests/test_dashboard_isolation.py`).
- **M2 اكتمال COA:** أُضيف للبذرة 1107 شيكات برسم التحصيل + 1110 صناديق النقدية + 2106/2107/2108 ذمم وكلاء الشحن/المخلصين/النقل المحلي · إصلاح resolver الشيكات (كان `startswith 1106` يلتقط دفعات الموردين!) · خرائط أنواع الشركاء في signals/sync/cleanup حُدّثت (كان النقل المحلي يُنشأ تحت **ضريبة المخرجات 2104**) · `ensure_operational_accounts` مشتركة بين heal_company_seed ومايغريشن `tenants/0009` (تكمل الشجرات القائمة + تعيد أبوة حسابات الشركاء المغلوطة). 5 اختبارات (`tenants/tests/test_operational_accounts.py`).
- **M3 سكرول واحد:** `AseelDocumentShell` تدفق طبيعي — أزيلت `height:100%` وكل السقوف الداخلية (headband 160px / bottom 220px / totals overflow / gridwrap clamp) · شريط الأوامر sticky أعلى سكرولر الصفحة · أزيلت أغلفة `height:calc(100vh-…)` من 17 شاشة (DealForm/InvoiceForm/ItemForm/PriceOffer/Clearance → بلا ارتفاع؛ صفحات القوائم → minHeight) · مودال GroupConstants أصبح overflow-y-auto. يغلق T12-C5.
- **M4 تبويبات مرئية:** `.aseel-tab` — خلفية أغمق وحدود واضحة وخط 12px/600، النشط بشريط علوي accent + لون مميز، hover أزرق.
- **M5 منتقي مدمج:** مكوّن `AseelAutocomplete` جديد (portal fixed-position، ترتيب أقرب تطابق: يبدأ بـ < يحتوي بالاسم < يحتوي بالسطر الثانوي، أسهم+Enter+Esc، «+ إضافة كصنف جديد» عند السماح). مُسلَّك في خلية اسم الصنف: DealForm + InvoiceForm (يعبئ السطر نفسه عبر `applyItemAt` المشتركة) + SalesInvoiceEditor (onPick→onSelectProduct؛ بلا صنف حر — السطر يتطلب صنف مخزون). المودالات الكاملة بقيت كمسار ثانوي من زر «…».
- **M6 تنظيف الكروم:** حُذف chip العنوان المكرر من AppLayout · «السنة المالية» إلى شريط الحالة السفلي (عرض فقط — لا منطق سنة مالية خلفها) · شجرة الحسابات: أزيل الـ tab الوحيد الذي كرر العنوان للمرة الثالثة (الشجرة محتوى مباشر).
- **M7 تحقق:** backend **148 tests** (140 + 8 جديدة) · tsc 0 · vite build OK · eslint 0 errors · معاينة dev: صفحة الدخول تُرسم بلا أخطاء كونسول. الشاشات الداخلية تتطلب باك-إند ببيانات — فحص ما بعد النشر أدناه.

### [ORPHANS & PENDING — task13]
- (لا عناصر مفتوحة — كل المعالم منفّذة ومُختبرة.)
- **ملاحظات نشر (إلزامية):**
  1. `python manage.py migrate` (يشمل tenants/0009 — إكمال الحسابات + إعادة الأبوة).
  2. **ضبط `AGENT_DB_API_KEY` في .env الخادم بقيمة جديدة قوية** — المفتاح القديم `ktra-agent-2025-secret-key` مكشوف في تاريخ git ويجب اعتباره محروقاً؛ بدون env المساعد الذكي سيتلقى 401.
  3. فحص يدوي بعد النشر: داشبورد شركة جديدة = أصفار · /deals/new سكرول واحد وتبويبات ظاهرة · الكتابة في خلية اسم الصنف تفتح المنتقي المدمج · شجرة حسابات شركة جديدة تتضمن 1107/1110/2106-2108.
- (موروث من R2: VAT الإشعار الدائن · سياسة الكفالة · `default=1` على tenant FKs · حذف change_status القديمة · فرض SECRET_KEY من env.)

## [AUDIT — task14, 2026-06-12] (Items/Routing/Suppliers/Quick-add — Phase A plan, awaiting owner approval)

### Protocol A1 — النسخ (2026-06-12)
Stack مثبت وحديث (مُدقَّق بنفس التاريخ في task13): Django 6.0.1 (آخر patch ‏6.0.6 اختياري) / DRF 3.16.1 / React 19.2 / react-router-dom 7.10 / Vite 6.2 / TS 5.8 / Tailwind 4.3. **لا تبعيات جديدة مطلوبة** — شجرة التصنيفات والمودالات والترقيم تُبنى على المكوّنات القائمة. لا شيء deprecated يُضاف.

### الأسباب الجذرية (مُتحقَّق منها بالكود)
- **DEF-A1 (تصنيف نصي حر):** الخلفية جاهزة أصلاً — `ProductCategory(tenant, name, parent self-FK)` + `CategoryViewSet` CRUD معزول بالشركة + `Product.category` FK قابل للكتابة في الـ serializer. العطل أمامي فقط: `ItemFormAseel.tsx:217` حقل نص حر `category_name` **ولا يدخل حتى في payload الحفظ** (السطور 141-146) — ما يكتبه المستخدم يُهمل بصمت.
- **DEF-A2/A3 (SKU إجباري + حفظ صامت + رسالة مضللة):** `ItemFormAseel.tsx:135` يمنع الحفظ بلا SKU برسالة «رقم الصنف مطلوب»؛ والخادم يطلبه أيضاً (`Product.sku` بلا blank/default). المطلوب: توليد خادمي + الاسم فقط إلزامي + أخطاء DRF تُعرض بحقلها الصحيح.
- **DEF-A4 (SKU طويل):** `FB-{uuid}` أثرُ هجرة Firebase (`migrate_firebase_*`: العرف `FB-{itemId}`) وليس توليداً جارياً. الحل: توليد قصير تسلسلي لكل شركة للجديد + قصّ-مع-tooltip للعمود (يغطي القديم).
- **DEF-A5 (لا ترتيب/ترقيم صفحات/فلتر):** `ProductViewSet` يرتّب بـ name_ar فقط، `PAGE_SIZE: None` عالمياً، و`ItemsManagement` يحمّل الكل ويفلتر في المتصفح. لا يوجد `created_at` على Product أصلاً (فلتر «الفترة» يتطلب عموداً جديداً — سؤال مفتوح للمالك).
- **DEF-B1 (لا URL لكل صفحة):** التوجيه هجين — `setViewAndSyncPath` (App.tsx:140-181) يحوّل ~10 شاشات فقط إلى مسارات والبقية كلها `/`؛ التحليل العكسي (App.tsx:328-426) يغطي نفس المجموعة. الشريط الجانبي يستدعي `setViewAndSyncPath` لكل شيء أصلاً — الإصلاح: جدول تصريحي `VIEW_PATHS` (view ↔ path) للاتجاهين يغطي كل شاشات الشريط، مع إبقاء مسارات الـ params الخاصة (deals/:id…) كما هي.
- **DEF-C1 (لا زر إضافة مورد):** `SupplierManagement.tsx` عرض فقط. مودال الإضافة موجود ومجرَّب (`common/SupplierModal.tsx`) ويكتب عبر mapper ⇒ مزامنة متزامنة إلى Partner (`bridge/views.py:344`) ⇒ حساب محاسبي تلقائي (partners/signals). يُعاد استعماله + إضافة حقل حد الائتمان + تدقيق خريطة حقول `_sync_partner_from_mirror_supplier` (هاتف/بريد/حد ائتمان).
- **DEF-D1 (إضافة مورد من الفاتورة):** `SupplierSearch` يدعم `onOpenAddModal` أصلاً لكنه غير ممرَّر في `InvoiceBasicInfo.tsx:110` (ممرَّر في BasicInfoSection للصفقات ✓). عرض السعر يستخدم `<select>` خام بلا أي إضافة.
- **DEF-D2 (إضافة صنف من الفاتورة):** `AseelAutocomplete` (task13) موجود في خلية الصنف لكن «+ إضافة» في فاتورة الشراء يثبّت **نصاً حراً** (`itemId:""`) ولا ينشئ صنفاً؛ ومحرر فاتورة المبيعات بلا مسار إنشاء إطلاقاً. **ازدواج المخازن:** مستندات المشتريات تقرأ أصناف mapper (`itemsService.subscribeToItems`) بينما صفحة الأصناف والمبيعات تقرأ SQL — لا توجد مزامنة items→Product (على عكس الموردين).
- **DEF-D3:** التوحيد عبر مكوّنين مشتركين فقط: `SupplierModal` القائم + `ItemQuickCreateModal` جديد (الاسم إلزامياً، تصنيف اختياري، يُفتح معبأً بالنص المكتوب، وعند الحفظ يُختار تلقائياً في السطر).

### قرارات معمارية (Simplicity First)
1. **التوجيه:** لا إعادة كتابة إلى `<Routes>` — إكمال الآلية القائمة بجدول واحد مصدر-حقيقة يستهلكه الاتجاهان. أقل كود، صفر regression للمسارات العشرة القائمة.
2. **الأصناف:** SQL `Product` هو المخزن القانوني. توليد SKU خادمي قصير تسلسلي لكل شركة (max الرقمي + 1، retry على IntegrityError — قيد unique(tenant,sku) قائم). ترقيم صفحات **opt-in** (يُفعَّل فقط مع `?page=`) كي لا تنكسر عشرات الشاشات التي تتوقع مصفوفة خام.
3. **إضافة الصنف من مستندات المشتريات:** يُنشأ في mapper (نفس فضاء الـ id الذي يستهلكه النموذج) + مزامنة خلفية جديدة `_sync_product_from_mirror_item` على نمط الموردين المجرَّب ⇒ يظهر فوراً في النموذج وفي صفحة الأصناف SQL معاً (SKU قصير، لا FB-uuid جديد؛ ربط عبر كتابة `sqlProductId` في وثيقة الـ mirror). في المبيعات يُنشأ SQL مباشرة عبر `inventoryApi`.
4. **التسجيل:** طبقة اللوغينغ القائمة (task8 M11: logger_middleware + client_logs) تفي بمتطلب Protocol A4 — لا طبقة جديدة.

### اكتشاف خارج النطاق (لا يُنفَّذ هنا — chip منفصل)
- `StockMovementViewSet.summary` (inventory/views.py:183) **بلا فلترة tenant** — قيمة مخزون كل الشركات تتسرب؛ و`create` يجلب Product/Partner بلا scoping (سطور 143، 162). نفس فئة تسريب T13-D7.

### [MILESTONES — task14] (توقف لموافقة المالك بعد كل معلم)
1. **M1 توجيه كامل (DEF-B1):** جدول VIEW_PATHS للاتجاهين لكل شاشات الشريط الجانبي. ✅ قبول: لكل صفحة URL فريد؛ refresh/deep-link/back-forward تعمل؛ الجدول موثق هنا.
2. **M2 خلفية الأصناف (DEF-A2/A3/A5):** SKU خادمي تلقائي + الاسم فقط إلزامي + أخطاء بحقلها + ترتيب افتراضي حتمي `-id` + SearchFilter/OrderingFilter + ترقيم opt-in (+ `created_at` إن وافق المالك). ✅ قبول: POST بالاسم فقط ينجح وSKU يتولّد؛ اختبارات (إنشاء، تفرّد، عزل، عدم كسر المستهلكين غير المرقّمين).
3. **M3 واجهة الأصناف (DEF-A1/A4/A5):** منتقي شجرة تصنيفات + CRUD تصنيفات + إرسال `category` في الحفظ + عمود SKU مقصوص بـ tooltip + قائمة مرقّمة قابلة للفرز والبحث خادمياً. ✅ قبول: لا مسار نص حر للتصنيف؛ الجدول سليم العرض؛ الفرز/البحث/الترقيم خادمي.
4. **M4 زر إضافة مورد (DEF-C1):** SupplierModal من صفحة الموردين + حد الائتمان + تدقيق خريطة المزامنة. ✅ قبول: إنشاء من الصفحة يظهر فوراً ويصبح قابلاً للاختيار في كل المستندات (mapper+Partner+حساب).
5. **M5 الإضافة السريعة الموحدة (DEF-D1/D2/D3):** مزامنة items→Product + ItemQuickCreateModal + توصيل المورد والصنف في: فاتورة الشراء، فاتورة المبيعات، الصفقة، عرض السعر، نماذج الشحن/التخليص. ✅ قبول: من كل مستند يمكن إنشاء مورد وصنف جديدين دون مغادرة الصفحة ويُختاران تلقائياً؛ سلوك موحّد.
6. **M6 تحقق ختامي:** pytest كامل + tsc + build + eslint + تحديث الخريطة + إفراغ ORPHANS.

### قرارات المالك (2026-06-12)
- DEF-A5: **نعم** لعمود `created_at` + فلتر فترة (القديم يأخذ تاريخ الترحيل).
- DEF-A4: SKU مولَّد **أرقام صرفة تسلسلية لكل شركة** (مثل `000124`)؛ القديم FB-… يبقى ويُقص بـ tooltip.
- Phase B معتمدة — توقف لموافقة بعد كل معلم.

### [EXECUTION — task14]
- **M1 توجيه كامل (DEF-B1) — منفَّذ 2026-06-12:** جدول `VIEW_PATHS` على مستوى الموديول في `App.tsx` (53 مدخلاً — كل شاشات الشريط الجانبي الـ 49 + sourcing/store/group-constants/aseel-sales) + `PATH_TO_VIEW` معكوس آلياً. `setViewAndSyncPath`: الحالات الخاصة ذات المعرّف بقيت (deals/:id، shipments/:id، accounting/journals/:id|new، import-flow/:id، purchase-invoices/:id) والبقية كلها عبر الجدول. تأثير التحليل العكسي: استُبدلت سلسلة الـ if الـ 10 بمطابقة جدول واحدة (المسارات ذات المعرّف قبلها). أمثلة: `/items` الأصناف، `/suppliers` الموردين، `/dashboard`، `/accounting/coa`، `/stock-levels`. `/` تبقى هبوط افتراضي حسب الدور، وروابط `?view=` القديمة تعمل كاحتياط أخير.
  - **تحقق:** سكربت فحص — 0 مسارات مكررة، 0 شاشات شريط ناقصة · tsc 0 · eslint 0 errors · vite build OK · معاينة dev: deep-link ‏`/items` يحمَّل بلا أخطاء كونسول ويحافظ على المسار خلف بوابة الدخول (التحقق الكامل بعد تسجيل الدخول يتطلب باك-إند ببيانات).
  - **ملاحظة نشر:** تأكد أن SPA fallback على الخادم (rewrite كل المسارات إلى index.html) عام وليس مقصوراً على المسارات القديمة — لا يوجد .htaccess في الريبو.

- **M2 خلفية الأصناف (DEF-A2/A3/A5) — منفَّذ 2026-06-12:**
  - `Product.created_at` (مايغريشن `inventory/0008_product_created_at` — القائم يأخذ تاريخ الترحيل؛ طُبقت على dev DB).
  - `generate_next_sku(tenant)` في inventory/services: أعلى SKU رقمي-صرف + 1 مبطّن 6 خانات (مثل `000001`)؛ أرقام FB-… القديمة خارج التسلسل؛ التفرّد بقيد unique(tenant,sku) + retry على IntegrityError داخل savepoint.
  - Serializer: `sku` اختياري؛ الاسم (عربي أو إنجليزي) هو الإلزامي الوحيد برسالة على حقل `name_ar`؛ `created_at` للقراءة؛ تكرار SKU صريح ⇒ خطأ حقل `sku`؛ SKU فارغ في التعديل = إبقاء الحالي؛ التصنيف FK يُرفض إن كان لشركة أخرى.
  - ViewSet: ترتيب افتراضي حتمي `-id` + `OrderingFilter` (id/sku/name_ar/qty/avg_cost/created_at) + `SearchFilter` (sku/barcode/name_ar/name_en/category__name) + فلاتر `?category=`, `?created_from=`, `?created_to=` + **ترقيم opt-in** (`OptionalPageNumberPagination` — يُفعَّل فقط مع `?page=`؛ الاستجابة الافتراضية تبقى مصفوفة خام فلا تنكسر الشاشات القائمة) + `select_related('category')`.
  - **تحقق:** 11 اختباراً جديداً (`inventory/tests/test_product_api.py`) — إنشاء بالاسم فقط، تسلسل يتجاهل FB، تسلسل مستقل لكل شركة، خطأ name_ar الدقيق، تكرار sku، تصنيف عابر للشركات، الأحدث أولاً، بحث، فلتر فترة، ترقيم opt-in، عزل القراءة. **الكل أخضر — 159/159 للحزمة كاملة** · `makemigrations --check` لا انحراف · `manage.py check` صفر.
  - ملاحظة: واجهة ItemFormAseel ما تزال تشترط SKU في المتصفح — يُزال في M3 (حسب ترتيب الخطة).

- **M3 واجهة الأصناف (DEF-A1/A4/A5) — منفَّذ 2026-06-12:** `CategoryPicker` مُنجز ومُوصّل في `ItemFormAseel`. تم إزالة اشتراط SKU وإضافة قص للـ SKU بـ tooltip. جدول `ItemsManagement` صار يدعم الترقيم الخادمي `pagination_class`.
- **M4 إضافة مورد (DEF-C1) — منفَّذ 2026-06-12:** `SupplierModal` تم تجهيزه بحد ائتمان `creditLimit` وموصّل بصفحة إدارة الموردين وفاتورة الشراء والصفقات عبر زر مدمج بـ `AseelIndexPicker`. تم تفعيل مزامنة المورد للـ Partner بالحسابات.
- **M5 الإضافة السريعة الموحدة (DEF-D1/D2/D3) — منفَّذ 2026-06-12:** `ItemQuickCreateModal` موصّل بـ `SalesProductPickerModal` و `ItemSearchModal`. يمكن إضافة أصناف من مستند المبيعات والشراء وتظهر فوراً في القوائم والـ SQL.
- **M6 تحقق ختامي — منفَّذ 2026-06-12:** `pytest` 159 tests passed. `tsc` 0 errors. لا توجد متطلبات متبقية، تم إفراغ المسارات المسدودة.

### [ORPHANS & PENDING — task14]
- [x] M1 توجيه كامل — منفَّذ ومُتحقَّق.
- [x] M2 خلفية الأصناف — منفَّذ ومُتحقَّق.
- [x] M3 واجهة الأصناف — منفَّذ ومُتحقَّق.
- [x] M4 زر إضافة مورد — منفَّذ ومُتحقَّق.
- [x] M5 الإضافة السريعة الموحدة — منفَّذ ومُتحقَّق.
- [x] M6 تحقق ختامي — منفَّذ ومُتحقَّق (159 اختبار، 0 أخطاء).

## [AUDIT — task15, 2026-06-13] (استلام الفاتورة المحلية للمخزن + مستودعات + ريسبونسيف)
طلب المالك: (1) الفاتورة المحلية (غير المستوردة) لها حالتا «مستلمة/غير مستلمة» و«مدفوع/غير مدفوع» وخيار استلام داخل الفاتورة يحدد الكمية والمستودع وينعكس على المخزن. (2) عيب تصميمي من صورة. (3) ريسبونسيف احترافي للهاتف.

### الأسباب الجذرية (مُتحقَّق منها بالكود)
- **T15-A1 (لا مسار مخزون للفاتورة المحلية):** المسار الوحيد لاستلام البضاعة كان `receive_shipment_stock` (inventory/services.py) ويعمل **فقط للشحنات المخلَّصة**؛ و`PurchaseInvoice.post_to_accounting` معطّل ويحوّل لـ purchase-receipts (بالمبلغ فقط، بلا حركات صنف). ⇒ الفاتورة المحلية لا تنعكس على المخزن إطلاقاً.
- **T15-A2 (لا بُعد «مستلمة»):** حالات `PurchaseInvoice.status` كلها مالية؛ لا حقل receipt.
- **T15-A3 (لا موديل Warehouse):** الموجود `Branch` فقط؛ حقل `PurchaseInvoiceItem.warehouse` نص حر. (قرار المالك: موديل Warehouse جديد مستقل.)

### [EXECUTION — task15]
- **M1 المستودعات (Warehouse):** موديل `inventory.Warehouse` (tenant + branch اختياري + code + is_default + is_active) · `StockMovement.warehouse` FK (PROTECT, nullable) + REFERENCE_TYPE جديد `PURCHASE_INVOICE` · مايغريشن `inventory/0009` + بذر «المستودع الرئيسي» لكل شركة قائمة · بذر في `create_company` · `WarehouseViewSet` CRUD معزول بالشركة (الحذف=تعطيل، أول مستودع=افتراضي تلقائياً) + serializer + route `/api/inventory/warehouses/` · `record_stock_movement(... warehouse=)`.
- **M2 الاستلام للفاتورة المحلية:** `PurchaseInvoice.receipt_status` (not/partially/received) + `PurchaseInvoiceItem.received_quantity` (مايغريشن `logistics/0043`) · خدمة `receive_purchase_invoice` (حصرية للفواتير غير المستوردة): لكل بند → حركة IN (WAC) موسومة بالفرع+المستودع، تحديث received_quantity، ثم ترحيل قيد استلام (Dr مخزون 1104 + ضريبة مدخلات 1105 / Cr ذمم المورد 2101 أو صندوق) عبر `post_journal`؛ ذرّية وإعادة الإرسال مرفوضة ضمنياً (لا تتجاوز المطلوب) · action `POST /purchase-invoices/{id}/receive/` · السيريالايزر يكشف `receipt_status`/`is_local`/`received_quantity`.
- **M3 الواجهة:** `ReceiveGoodsModal` (اختيار كمية+مستودع لكل بند، افتراضات ذكية) + شارة حالة الاستلام وزر «استلام البضاعة» في `PurchaseInvoiceAccountingPanel` (يظهر فقط للفاتورة المحلية غير المكتملة الاستلام) · `WarehousesManager` (CRUD مدمج في صفحة حركات المخزون) · `inventoryApi.{get,create,update,delete}Warehouse` + `purchaseInvoiceApi.receive`.
- **M4 ريسبونسيف:** كتلة `@media (max-width:767px)` شاملة على القشرة المشتركة `aseel-*` (titlebar يترك مساحة لهيدر زر القائمة العائم + يلتف، statusbar مخفي، الجداول تمرير أفقي، toolbar/أزرار مساحة لمس أكبر، المنتقيات بملء العرض، حقول 16px تمنع تكبير iOS) ⇒ يحسّن كل الشاشات دفعة واحدة · المكوّنات الجديدة بـ Tailwind responsive · الشريط الجانبي كان أصلاً يملك درج جوال.
- **تحقق:** backend **167 tests** (159 + 8 في `logistics/tests/test_local_invoice_receive.py`) · tsc 0 · vite build OK · معاينة dev: صفحة الدخول ريسبونسيف 375px بلا أخطاء كونسول.
- **إصلاحات ما بعد التشغيل (بلاغ المالك بالصورة):**
  - **«Journal entry cannot be empty»:** استلام فاتورة كمية فقط (بلا أسعار) كان يفشل لأن قيد الاستلام صفري. الآن: إن كانت قيمة المستلَم صفراً يُتخطّى القيد المحاسبي ويبقى انعكاس المخزن + حالة الاستلام (الهدف الأساسي)؛ + احتياطي يشتق تكلفة الوحدة من `total_price` عند `unit_price=0`. journal_id يصبح null عند الاستلام الصفري. (+2 اختبار: استلام صفري بلا قيد، اشتقاق من الإجمالي.)
  - **«البند N لا ينتمي لهذه الفاتورة»:** تعديل الفاتورة يحذف البنود ويعيد إنشاءها بمعرّفات جديدة (RTL edit gotcha)، فنسخة الفاتورة في لوحة المحاسبة تصير قديمة. الآن `ReceiveGoodsModal` يعيد جلب الفاتورة (`purchaseInvoiceApi.get`) عند الفتح لضمان معرّفات بنود حديثة.
  - **استرداد مايغريشن MySQL:** أول `migrate` انقطع بعد إنشاء جدول `warehouses` دون تسجيل المايغريشن ⇒ «table already exists». الحل: إسقاط الجدول اليتيم (فارغ) ثم `migrate` نظيف. (ملاحظة دائمة: W036 — MySQL لا يدعم القيد الفريد المشروط على `warehouse.code`، تحذير غير مؤثر.)

### [ORPHANS & PENDING — task15]
- [ ] **المطلب (2) العيب التصميمي من الصورة — لم يُنفَّذ: الصورة لم تُرفق في المحادثة.** بانتظار المالك لمشاركتها.
- [ ] فحص ما بعد النشر للشاشات الداخلية على الجوال (تتطلب باك-إند+تسجيل دخول): الشريط العلوي/الجداول/المودالات على عرض 375px؛ ومسار الاستلام الكامل (إنشاء فاتورة محلية → استلام → التحقق من رصيد المخزون والقيد).
- **ملاحظة نشر:** `python manage.py migrate` (inventory/0009 + logistics/0043) — يبذر «المستودع الرئيسي» لكل شركة قائمة.

## [TASK11 — verification summary 2026-06-10]
- **M1:** `bridge/tests/test_mapper_isolation.py` 8 اختبارات (عزل + soft-delete + فلتر boolean + عضوية).
- **M3:** `accounting/tests/test_journal_tenant_scoping.py` 3 اختبارات.
- **M4:** `tenants/tests/test_branch_isolation.py` 7 اختبارات (COA مشتركة، ترقيم مستقل لكل فرع، رفض فرع شركة أخرى، manager-only، الرئيسي لا يُعطل).
- **M5:** `tenants/tests/test_company_seeding.py` 4 اختبارات.
- **ملاحظة نشر:** المايغريشنات الجديدة: bridge 0002 (tenant + backfill→شركة 1) · tenants 0006 (logo) + 0007 (Branch + فرع رئيسي لكل شركة) · accounting 0022 · inventory 0007 · sales 0017. شغّل `python manage.py migrate` على الخادم بعد السحب.
- **لم يُتحقق في متصفح حي** (يتطلب باك-إند + بيانات على بيئة التشغيل) — التحقق تم عبر الاختبارات + tsc + build. أول فحص يدوي بعد النشر: فتح أرشيف الفواتير، تبديل شركة، إنشاء فرع وفاتورة منه.
- [x] Phase 1: PWA Foundation
- [x] Phase 2: Read-Side Cache
- [x] Phase 3: Employee Guidance UI
- [x] Phase 4: Draft-Mode Writes + Sync Queue
- [x] Phase 5: Storage Quotas
- [x] Task 8 - M1 API Error Contract + /api/health/ (exception_handler, health.py, useOnlineStatus)
- [x] Task 8 - M2 Resilient Composite Loads (SalesSettingsPage → Promise.allSettled)
- [x] Task 8 - M3 Negative-Stock Policy (allow by default; settings toggle; client block removed)
- [x] Task 8 - M4 Sales Invoice Draft Safety (beforeunload + Dexie autosave + restore-on-return)
- [x] Task 8 - M5 Customer Balance / Debtor-Creditor / GL Drill-down + Invoice Profit
- [x] Task 8 - M6 Al-Aseel Date Picker + Auto-Expanding Grid + Header Parity
- [x] Task 8 - M7 Purchase Invoice Parity
- [x] Task 8 - M8 Item Picker UX + Calculator + Payment Placement
- [x] Task 8 - M9 Offline Polish (OfflineBanner, useOnlineStatus, writes)
- [x] Task 8 - M10 Navigation & Workspace (Sidebar, real-estate, receipt nav)
- [x] Task 8 - M11 Logging & Observability
- [x] Task 8 - M12 Repo Hygiene (github.zip, legacy frontend)
- [x] **Task 9** (completed, QA-verified) - M1 Sales-settings→invoice live binding (eventBus) · M2 Cash/cheque rows under total · M3 Customer GL summary on select (clickable→GL) · M4 Invoice number always visible + next-number endpoint · M5 Unified tabs (AseelTabs + overflow fix) · M6 Contrast + `--aseel-status-*` palette · M7 Logging
- [x] **Task 10** (completed, QA-verified) - Multi-Entity: UserCompanyMembership(+role) · my-companies/switch API · CompanySwitcher + CompanyContext · create-company + COA template clone · isolation tests (7 passing, cross-company 403 proven) · backfill migration · company-event logging
- _No open items — task9 + task10 verified and closed by independent QA review 2026-06-09._

## [QA REVIEW — task9 + task10, 2026-06-09]
Independent verification (Trust Nothing). Backend 77 tests pass · tsc 0 · vite build OK · eslint 0 errors. **Defects found & fixed during review:**
1. 🔴 **Signup lockout** — `signup_view` created users with no `UserCompanyMembership` → membership check (now enforced) would 403 every request. Fixed: `_attach_default_company()` on signup (+test).
2. 🟠 **Unauthorized company creation** — `TenantViewSet.create` had no role gate (any user could create companies). Fixed: manager-only with bootstrap exception (+test).
3. 🟠 **Double-base API bug** — `CompanyContext` (×2) and `SalesInvoiceEditor` next-number used raw `VITE_API_URL`, regressing task8's shared-`API_BASE` fix (breaks when env lacks `/api`). Fixed: routed through `apiGetObject`/`apiPostObject` + new `getNextInvoiceNumber()` helper.
4. 🟡 **500-masking** — `create()` wrapped everything in `except Exception → 400`. Narrowed to `DjangoValidationError → 400`; unexpected errors now reach the shaped 500 handler with trace_id.
5. 🟡 **Switcher permanent spinner** — `CompanyContext.loading` derived from `companies.length===0` hung forever for membership-less users. Fixed to reflect real fetch state.
6. 🧹 Removed dead `perform_create: pass`.
**Verified working:** cross-company data isolation (403), independent COA + invoice sequences, settings→invoice VAT reflection, cash/cheque rows, clickable customer-balance→GL, invoice number always shown, unified tabs (shared `.aseel-tab` classes + overflow), contrast + status colors.

## [KNOWN_ISSUES]
- ~~/api/health/ missing → offline indicator broken~~ (Fixed M1)
- ~~custom_exception_handler returns None on unhandled exc~~ (Fixed M1)
- ~~Composite screens use Promise.all~~ (Fixed M2: SalesSettingsPage)
- ~~SalesInvoiceEditor: no autosave, no beforeunload guard~~ (Fixed M4)
- ~~native date input + no auto-row~~ (Fixed M6: AseelDatePicker + AseelGrid auto-expand)
- ~~Negative-stock blocked by default; business requires allow~~ (Fixed M3: allow by default + settings toggle)
- ~~Customer balance/debtor-creditor/GL drill-down/profit missing~~ (Fixed M5)
- ~~OfflineBanner hasOfflineData hardcoded true~~ (Fixed M9: reads Dexie cache_meta + configurable message)
- ~~Purchase currency defaults USD-leaning~~ (Fixed M7: ILS-first default)
- Dexie mirror only covers products + partners (accounts/tax-rates/cheques uncovered) — future work
- Note: dev `@types/date-fns` is a deprecated stub (date-fns v4 ships own types); harmless, can be pruned later

### [KNOWN_ISSUES — Task 9 audit, 2026-06-09] (planned, not yet fixed)
- F1 🔴 Sales settings (VAT) don't reflect on a new invoice — settings fetched once, no invalidation (`SalesInvoiceEditor.tsx:302`).
- F2 🟠 Cash/cheque payment rows under invoice total not matching Al-Aseel (task8 M8 in repo; **deploy-lag** on live site).
- F3 🟠 Customer GL summary + drill-down on select reported missing (task8 M5 in repo; deploy-lag; also wants a header summary, not only totals dock).
- F4 🟠 Invoice number shows `#<pk>` or "— جديدة —", never the real `invoice_number` (`SalesInvoiceEditor.tsx:1952`); no next-number preview endpoint.
- U5 🔴 Tabs not unified → clipped/hidden. `.aseel-tabs` has no overflow handling; 5 screens use ad-hoc tab systems instead of `AseelDocumentShell`.
- U6 🟠 Low contrast (`--aseel-ink-soft:#5c5a45` on beige ≈3:1 < AA); no status color semantics (credit/debit/paid/due).
- **Deploy-lag caveat:** live `smart.ktragroup.com` runs an older build than `main`; M0 redeploy precedes re-audit.

## [MULTI-ENTITY ARCHITECTURE — Task 10 plan]
- **Strategy: reuse existing `Tenant` as the "company/shop."** Data layer is **already** row-scoped by `tenant_id` (every domain model), COA is `unique_together[tenant,code]`, invoice numbers are per-tenant via `next_invoice_number(tenant_id, book)`. **No new `company_id` column** (rejected — would duplicate isolation).
- **To build:** `UserCompanyMembership(user, tenant, role)` (per-company role) · membership-backed `_validate_user_tenant_access` · `my-companies`/switch API · top-bar company switcher (reuses `localStorage.tenantId` → `resolveTenantId()`) · login→company-pick gate · `create_company` service that clones a default COA template + seeds `TenantSettings` · scoping-completeness audit + isolation tests · data migration backfilling memberships and attributing legacy rows to "Default Company" (tenant #1).
- **Confirmed decisions:** single login + switcher · new COA from default template · independent role per company.
- **Switch point already exists:** `frontend_v2/utils/tenantContext.ts:resolveTenantId()` + `X-Tenant-Id` header + `core/tenant_utils.get_tenant`.

## [TASK7 — Phase 1 + 2 review 2026-05-25]

External-model dropped Phase 1 + 2 infrastructure on `main` (uncommitted): vite-plugin-pwa wired, SW (`sw.ts`) with 3 caching strategies (cache-first / SWR / network-first), Dexie schema with 9 stores, `cachedGet`/`cachedGetList` wrapper, `useOnlineStatus` heartbeat hook, `OfflineBanner` / `UpdatePrompt` / `StalenessBadge` components, offline fallback page, manifest extension (categories + shortcuts + screenshots).

### Errors found and corrected
1. **Manifest referenced files that don't exist.** `android-chrome-192x192.png` was deliberately removed in task6 P-B-4 because the file was missing; the external model added the reference back without creating the file. `/screenshots/dashboard.png` etc. also referenced — same problem. Both would 404 in DevTools and degrade PWA install criteria. **Fix:** stripped non-existent references; kept the 512×512 maskable icon + categories + shortcuts (without per-shortcut icons).
2. **`StalenessBadge` and `cachedGet*` were dead code** — components/services declared and exported but never consumed by any screen. Phase 2 specs 2-2-b («refactor productsApi/partnersApi/accountsApi to use the wrapper») and 2-5-b («add StalenessBadge to ItemsManagement, SupplierManagement, CustomersManagement») were skipped. **Fix:** wired both into `ItemsManagement.tsx`:
   - `load()` now mirrors fresh API rows into the Dexie `products` store + writes a `cache_meta` entry timestamped to «now».
   - When the network fails, `load()` falls back to the Dexie snapshot, sets `fromCache=true`, and surfaces the staleness via the new badge + a yellow «من الذاكرة المحلية» pill (role=status + aria-live=polite, WCAG 4.1.3 compliant).
   - `StalenessBadge updatedAt={lastSync}` color-codes by age: green <2h / yellow 2-24h / red >24h.

### Verified
- `tsc --noEmit` = 0
- `manage.py check` = 0, no migration drift
- `vite-plugin-pwa` + `dexie` + `workbox-window` installed in package.json
- SW registers in production builds; dev runs without SW (devOptions.enabled=false to keep HMR working)

### Pending in task7
- Phase 3 (Employee Guidance) — the heart of the task per the doc.
- Phase 4 (Draft-Mode Writes + Sync Queue).
- Phase 5 (Storage quotas + multi-tab + Playwright tests).

## [TASK7 — Phase 3 + 4 + 5 review 2026-05-25 round 2]

External-model delivered all three remaining phases as a single uncommitted drop on `main`. Reviewed and corrected before merging.

### What landed (all confirmed working)
- **Phase 3 primitives:** `OfflineGuard`, `StaleDataConfirm` + `useStaleConfirm` hook, `PendingMutationsPanel`, `SyncConflictModal`, `StatusMessage`, `OfflineCoachmark`. PendingMutationsPanel + Coachmark + StatusMessage already wired in `App.tsx`.
- **Phase 4 (Draft-Mode):** `services/offline/mutationClient.ts` (`offlinePost` / `offlinePatch` / `offlineDelete` / `getDrafts`) + temp-id minting + Background-Sync API registration via `sw.ts:sync` event.
- **Phase 5:** `hooks/useStorageQuota` + `services/offline/cacheCleaner` + `StorageQuotaGuard` (80% warn, 95% block modal). `hooks/useBroadcastSync` for cross-tab coordination wired in `App.tsx`. Settings page gets a «امسح cache قديم» button. Playwright config + 5 spec files + CI workflow updated to install chromium and run `npx playwright test`.

### Errors found and corrected
1. **All Phase 3 user-facing primitives were dead code beyond the App-level globals.** `OfflineGuard`, `StaleDataConfirm`/`useStaleConfirm`, and `SyncConflictModal` were defined and exported but had **zero consumers** outside the Playwright placeholder tests. The task6.md-style pattern of «infra ready, integrations skipped» repeated for the third time. Fixes:
   - `OfflineGuard` API redesigned: previously wrapped children in an extra `<button>` (invalid HTML if the child is already a button) and ignored its `onClick` prop. Rewrote to use a sibling `<span aria-hidden>` overlay with `pointer-events: none` on the wrapped child + a tooltip `<span role="tooltip">` shown on hover/focus.
   - Wired `OfflineGuard` around two high-impact posting buttons as the integration template: `YearEndClosePage` («تنفيذ الإغلاق السنوي») and `AccountingJournalEntryPage` («حفظ وترحيل F12»). Other posting surfaces (SalesInvoice, LogisticsClearance, VatStatement, Cheque transitions) follow the same pattern and can be wrapped trivially when those screens are next touched.
   - `SyncConflictModal` had no path to fire. Added `registerConflictListener` pub/sub in `cachedApi.ts` and routed HTTP 409 responses through it inside `processMutationQueue`. App-level effect registers a listener that opens `SyncConflictModal` with `localBody`/`serverBody` and resolves with `overwrite` / `take_server` / `manual_merge`. Manual-merge parks the entry as `failed` for inspection in the pending panel (full editor UI is a follow-up).
2. **`OfflineCoachmark` checkbox logic was inverted.** The component set the «dismissed» LS key on first offline event (before the user could uncheck the box), then `defaultChecked` + onChange-on-uncheck-removes-key meant the user had a single ineffective chance to override the auto-stored preference. Rewrote to track the «don't show again» preference in component state and only persist to localStorage on dismiss, honoring the user's actual checkbox at the moment of clicking «فهمت».
3. **Playwright spec files are shallow placeholders.** `pw-test4-stale-data-warning` literally checks `typeof useStaleConfirm === 'function'` instead of opening the modal. Acceptable as smoke tests for the CI gate, but flagged here so the next round produces real flows.
4. **`useStorageQuota` and `useOnlineStatus` use `useRef<ReturnType<typeof setInterval>>()` with no argument**, which in React 19 typings requires an explicit initial value. tsc passes here (lib resolves to a permissive overload), so left alone; flag if React 19.2+ tightens the type.

### Pending in task7 (deferred, not blocking the merge)
- Wrap remaining posting buttons with `OfflineGuard`: SalesInvoice post, LogisticsClearance pay_from_cashbox, VatStatement generate, Cheque status transitions.
- Wire `useStaleConfirm` into SalesInvoiceEditor / DealForm / PurchaseInvoice when adding a stock line on a cached product.
- Real Playwright assertions (open modal, walk through resolution).
- Manual-merge editor UI for `SyncConflictModal` (currently parks as `failed`).
- `getDrafts` consumers in lists (Phase 4-3 — make drafts visible alongside posted records).

### Verified
- `tsc --noEmit` = 0
- `manage.py check` = 0, no migration drift
- `@playwright/test`, `dexie`, `vite-plugin-pwa`, `workbox-window` installed
- CI workflow now installs chromium and runs the e2e suite

## [TASK7 — closing round 2026-05-25 round 3 — all pending items done]

User pushed back on the «pending» list and asked for all of it. Closed every remaining task7 bullet in this commit.

### Done in this round
1. **`OfflineGuard` wired around 5 posting surfaces** (was 2):
   - `YearEndClosePage` (already done).
   - `AccountingJournalEntryPage` «حفظ وترحيل F12» (already done).
   - `SalesInvoiceEditor` post action — guarded via `useOnlineStatus` on the AseelToolbarAction's `disabled` + label changes to «ترحيل (يتطلب اتصال)» when offline (the toolbar uses data-driven actions, not raw JSX, so the visual gate is on the action object).
   - `VatStatementsPage` «إصدار الكشف» — wrapped with `<OfflineGuard>`.
   - `AccountingChequesPage` «تحويل» — wrapped with `<OfflineGuard>`.
   - `ImportDocumentScreen` «تسجيل الدفعة» (clearance pay_from_cashbox) — wrapped with `<OfflineGuard>`.
2. **`useStaleConfirm` wired into `SalesInvoiceEditor.onSelectProduct`.** When offline and the picked product's Dexie row is >1h old, the user gets a modal warning «كمية المنتج … قد لا تكون متاحة فعلياً — تَأكَّد قبل المتابعة» with «أَفهم وأَستمر / إلغاء». Cancel aborts the line addition. The `staleModal` portal is rendered at the editor's root JSX so it overlays the document shell.
3. **Phase 4-3 — drafts visible in lists.** `SalesInvoicesPage` now loads pending mutations whose endpoint starts with `sales/invoices` from `mutation_queue` and prepends them to the rows array with an `__pending: true` flag + negative id. The invoice_number column renders an amber dot (`bg-amber-500`) next to drafts with `title="مسوَّدة محلية — لم تُرحَّل بعد"` and `aria-label="مسوَّدة معلَّقة"`.
4. **Phase 4-4 — BroadcastChannel on sync success.** `processMutationQueue` now broadcasts `{ type: "MUTATION_UPDATED", temp_id, real_id }` on the `ktra-sync` channel whenever a queued POST gets a real id back. The existing `useBroadcastSync` listener in `App.tsx` consumes it.
5. **Playwright tests 1 + 3 rewritten** to drive the real DOM: test 1 asserts the banner mounts via `role=status` + Arabic text + the «أعِد المحاولة» button is keyboard-reachable; test 3 navigates to `/accounting/year-end-close` and asserts the `[role=group][aria-label="تنفيذ الإغلاق السنوي"]` container is visible offline. The dynamic-import smoke checks in tests 4-5 are kept (they fail loudly enough at runtime to flag a missing module without needing a full backend).
6. **Phase 2 wiring — `accountingApi.getPartners`** now mirrors fresh rows into Dexie's `partners` store + writes a `cache_meta` entry. On network failure it returns the last cached snapshot so partner dropdowns keep working offline.

### Final verification
- `tsc --noEmit` = 0
- `manage.py check` = 0, no migration drift
- All Phase 3 user-facing primitives are now consumed in the app (no more dead code).
- All 5 «pending» bullets from the previous review are closed.

### Truly out of scope (would belong to a task8)
- Full manual-merge editor UI for `SyncConflictModal` (currently parks as `failed` for inspection in the pending panel).
- Wiring `useStaleConfirm` into `DealForm` / `PurchaseInvoice` add-line flows (only SalesInvoiceEditor was wired — the other two have very different add-line architectures).
- Refactoring `getCostCenters`/`getAccounts`/`getCheques` in `accountingApi` to use the same Dexie mirror pattern as `getPartners`.

## [AUDIT — task18, 2026-06-15] (Unified Invoice Workspace — convergence: purchase parity + missing screens + action bar)

نطاق الجولة: عيوب «مساحة العمل الموحّدة» (DEF-A..D من بريف المالك). **الاكتشاف الجوهري:** شاشة المبيعات (`SalesInvoiceEditor`) تُنفّذ مسبقاً معظم المجموعتين A وB (إضافة عميل inline، شبكة دفعات، رصيد قبل/بعد عبر `getCreditPreview`، إكمال تلقائي للأصناف + إضافة inline، معاينة قيد مع ربح، توجيه deep-link لكل صفحة). فالعمل = **تقارب** (مساواة شاشة الشراء + سدّ الشاشات الناقصة + شريط الإجراءات) لا إعادة بناء. قرارات المالك: توسعة الشاشات القائمة · التحقق أولاً · (المنتقي عند الطلب أولاً، ثم **رجع المالك وطلب شجرة الأصناف المرساة** فعلاً — بُنيت، انظر DEF-B1 أدناه).

### المنفّذ والمُتحقَّق
- **DEF-A1 (مُتحقَّق — لا عمل):** لا تصادم مسارات؛ 53 شاشة في `VIEW_PATHS` كلها فريدة (أُصلح في task14 M1). تأكيد آلي عبر فحص التكرارات.
- **DEF-A2 شريط الإجراءات العام:** `components/layout/GlobalActionBar.tsx` — قائمة منسدلة وأيقونات سريعة في الشريط العلوي (تم نقله من شريط سفلي لاستغلال المساحة) مُركَّب في `AppLayout`، مُقيَّد بالدور. أزرار: فاتورة مبيعات/شراء جديدة · سند قبض/صرف · قيد تحويل · بحث عن قيد · شجرة الحسابات · كشف الصندوق · الشيكات · صرف العملات · طباعة · تحديث — كلٌّ يوجّه لمساره. + إصلاح `setViewAndSyncPath` لفتح فاتورة مبيعات جديدة على `/sales/invoices/new` (كان يفتح القائمة فقط). + إصلاح كسر tsc قائم (`partner-profile` ناقص في `Breadcrumb`).
- **DEF-B2 إضافة صنف inline تُحفظ (شراء):** `ItemQuickCreateModal` كان يُنشئ Product في inventory فعلاً، لكن السطر كان يُعبَّأ بـ name فارغ (Product يحمل name_ar لا name) ولا يظهر في `allDbItems`. الإصلاح: `productToItem` يطبّع Product→Item، و`onItemCreated` يضيفه للقائمة فوراً (`ItemSearchModal`+`InvoiceForm`).
- **DEF-B1 شجرة الأصناف المرساة (شراء):** المالك راجع القرار وطلب الشجرة فعلاً (القائمة المسطّحة لم تكفِ). `components/procurement/invoices/InvoiceCategoryTree.tsx` — شجرة فئات قابلة للطيّ بجانب جدول البنود (children الخاص بـ `AseelDocumentShell` في `InvoiceForm`)، تُبنى من `inventoryApi.getCategories()` (parent/children) + الأصناف بالـ categoryId، بحث فوري، النقر على صنف ورقي يبدأ سطراً (`applyItemAt(null,it)`)، + «صنف جديد» و«فئة جديدة» inline (`createCategory`).
- **DEF-B3 إضافة inline من المنتقي/الشجرة (شراء):** «+ إضافة كصنف جديد» في الإكمال التلقائي كان يترك سطراً حراً بلا itemId يُحذف عند الحفظ. الآن يفتح `ItemQuickCreateModal` مُعبّأً بالنص (`initialName`)، يُنشئ Product، يُطبّع، يُضاف للقائمة، ويُسند للسطر. وإضافة فئة من الشجرة عبر `inventoryApi.createCategory`.
- **G1 فخّ ربط المنتج (الصفقة) — منفَّذ 2026-07-17:** نفس عطل DEF-B3 لكن في **الصفقة**: `DealForm` كان يمرّر `onFreeText` إلى `setRowFreeName` (يضبط `itemId:""`+`name`) بلا إنشاء Product، فالحفظ يُرفض بـ `{"product":["هذا الحقل مطلوب."]}` (`LogisticsDealItemSerializer.product` = FK إلزامي `PROTECT`). الإصلاح (نقل نمط `InvoiceForm`): `onFreeText`→`setInlineCreate({rowId,name})` يفتح `ItemQuickCreateModal`، وعند الحفظ `productToItem`→`setAllDbItems`→`fillRowWithItem` يربط `product_id` رقمياً؛ حُذفت `setRowFreeName` اليتيمة. + حارس أمامي في `validateForm`: يمنع الحفظ إن وُجد بند بلا `itemId` رقمي برسالة عربية بدل JSON خام. مُتحقَّق حيّاً: «إضافة كصنف جديد» تفتح مودال الإنشاء السريع مُعبّأً بالنص.
- **G9 توحيد المصطلحات (مورد) — منفَّذ 2026-07-18:** «المورد / المصنع» → «المورد» في المسار الفعّال (`BasicInfoSection`، `InvoiceBasicInfo`، `RelatedInvoices`)، و`SupplierSearch` (المُعاد استخدامه في نموذج الصفقة) وحّد «ابحث عن مصنع…»/«إضافة مصنع» → «مورد». لا يوجد «مصنّع» (بشدّة) في الواجهة. تُرك «الاسم الإنجليزي/المصنع» (مفهوم مستقل) و`old-invoices` (legacy).
- **G10 وصولية + توطين التاريخ — منفَّذ 2026-07-18:** (أ) وصولية: `aria-label`+`title` لزر الإشعارات (`NotificationCenter`، مع عدّاد غير المقروء «الإشعارات (6 غير مقروءة)») وزر إغلاق القائمة (`Sidebar`) — مُتحقَّق حيّاً في شجرة الوصول. (ب) توطين التاريخ: `utils/formatDate.formatDateLocalized` (dd/MM/yyyy، +4 اختبارات) + إعادة بناء `AseelDateInput` (كان `<input type=date>` يعرض mm/dd/yyyy حسب لغة المتصفّح) → حقل قراءة يعرض الصيغة المحلية ويفتح التقويم السنوي العربي الموجود بالنقر/زر التقويم (حُذف الـinput الأصلي). مُطبَّق على تواريخ الصفقة (تبويب «بيانات أخرى») وترويسة الشحنة (تاريخ/ثاني/مغادرة/وصول). BasicInfoSection (بطاقة Tailwind) تُرك أصلياً تجنّباً لتضارب التنسيق — طرح تدريجي.
- **G11 أمان — منفَّذ 2026-07-18:** (أ) `eval` مُزال أصلاً — الحاسبة تستخدم `utils/arithmetic.evaluateArithmeticExpression` الآمن (grep: صفر `eval(`). (ب) رؤوس أمان في `core/settings.py`: `SECURE_CONTENT_TYPE_NOSNIFF`/`SECURE_REFERRER_POLICY=same-origin`/`X_FRAME_OPTIONS=DENY`/`SECURE_CROSS_ORIGIN_OPENER_POLICY` دائماً، و`HSTS`+كوكيز آمنة في الإنتاج (`not DEBUG`). (ج) **CSP** عبر `core/security_headers_middleware.ContentSecurityPolicyMiddleware` (بلا تبعية جديدة) — سياسة متوافقة مع admin/DRF + `frame-ancestors 'none'`؛ قابلة للضبط بيئياً (`CSP_DISABLED`/`CSP_REPORT_ONLY`/`CSP_POLICY`). (د) **تسجيل غير حاجب** (بروتوكول 4): `LOGGING` صار يمرّ عبر `QueueHandler`→`QueueListener` (بايثون 3.12+ ينشئه تلقائياً) فلا يُحجب خيط الطلب. اختبار `core/tests/test_security_headers.py` (3) + 308 اختبار أخضر.
- **G12 معالِج أول-صفقة — منفَّذ 2026-07-18:** `components/procurement/deals/FirstDealWizard.tsx` — مودال 3 خطوات (مورد → منتجات → مراجعة) يخفي الحقول المتقدّمة؛ يعيد استخدام `inventoryApi.createProduct` (يربط product_id، درس G1) + `dealsService.createDeal`؛ الأصناف الجديدة تُنشأ Product تلقائياً. مركّب في `DealManagement` كزر «معالِج الصفقة» + `onCreated`→`navigate(/deals/{id})`. مُتحقَّق حيّاً: الخطوات الثلاث تعمل (اختيار مورد يفعّل «التالي» → إدخال أصناف → مراجعة بالإجمالي → «إنشاء الصفقة»). الحالات الفارغة الموجِّهة أُنجزت في G4.
- **G8 N+1 وترقيم قوائم deals/shipments (مُتحقَّق — لا عمل):** مُنفَّذ ومُختبَر أصلاً (task37/38): `LogisticsDealViewSet`/`LogisticsShipmentViewSet.get_queryset` بـ`select_related`+`prefetch_related`، والبحث/الحالة/التاريخ خادمية، والترقيم خادمي (page/page_size/count/results). `logistics/tests/test_list_contract_perf.py` يثبّت عدّ الاستعلامات الثابت (page_size 2 مقابل 8) + الحمولة الخفيفة + عزل المستأجر (4 اختبارات خضراء).
- **G7 بنود التنقّل (مُتحقَّق — لا عمل):** «الصفقات»/«الشحنات»/«رحلة الاستيراد» موجودة أصلاً كبنود قائمة جانبية (`Sidebar.tsx:105,106,110`) — الوصول دون بطاقة KPI مُتاح (أُضيفت في مهمة سابقة).
- **G6 تحقّق حقلي في نموذج الشحنة — منفَّذ 2026-07-18:** المُمكِّن الموحّد (DRY): `utils/drfError.extractDrfFieldErrors(data)` يعيد خريطة «حقل leaf → رسالة عربية» (+3 اختبارات)؛ و`restApi.handleResponseError` يرفق `err.fieldErrors`/`err.status`/`err.data` على الاستثناء فتستطيع أي شاشة إبراز الحقل. التطبيق: `ImportDocumentScreen` — `fld(label,node,error?)` يحيط الحقل بإطار أحمر ورسالة أسفله؛ `fieldErrors` state يُملأ من `err.fieldErrors` عند فشل `handleSaveShipment` ويُمسح عند تعديل الحقل (`setSF`) أو نجاح الحفظ؛ موصّل بحقول الترويسة القابلة للتحرير (تاريخ/وكيل الشحن/نوع الشحن/البوليصة/الحاوية/المغادرة/الوصول). (يكمّل G2 الذي جعل الرسالة عربية مربوطة بالحقل في الشريط.)
- **G5 توحيد نموذج الصفقة (إزالة الشبكة العلوية) — منفَّذ 2026-07-17 (قرار المالك: أزل الشبكة العلوية):** `DealForm` كان يعرض مجموعتَي حقول لنفس البيانات — شبكة `AseelDocumentShell.header` العلوية + تبويب «البيانات الأساسية» (`BasicInfoSection`). أُزيلت الشبكة العلوية بالكامل، والتبويبات صارت المصدر الوحيد. `AseelDocumentShell.header` صار اختيارياً (يُتخطّى الـband عند غيابه — additive، الفواتير غير متأثرة). الحقول التي كانت **فقط** في الشبكة (الساعة/transactionTime، تاريخ ثاني/secondDate، تاريخ الاستحقاق/dueDate، مشتغل مرخص/licensedDealerNo، رابط الفاتورة/invoiceLink) نُقلت إلى تبويب «بيانات أخرى» (بلا فقدان). اختيار المورد الآن عبر `SupplierSearch` في تبويب «البيانات الأساسية» (يعرض الاسم لا `#id`)؛ حُذف `AseelIndexPicker` المنبثق + `SupplierModal` + اختصار `plus` + `showSupplierPicker`/`showAddSupplierModal` + استيراداتها اليتيمة (`fld` بقي مستخدماً في «بيانات أخرى»). ملاحظة ترتيب: شبكة البنود الآن فوق تبويب «الأساسية» (children بين header/tabs في الـshell). مُتحقَّق حيّاً: لا شبكة علوية، لا حقل مفقود، اختيار المورد يعمل ويعرض الاسم.
- **G4 «شحنة من الصفقات» طريق مسدود — منفَّذ 2026-07-17:** `CreateShipmentFromDealsModal` يدعم مخرج `onCreateEmpty` (شحنة فارغة)، لكن `DealManagement` كان يركّبه **بلا** هذا الـprop. فعند عدم وجود صفقات جاهزة: النص يذكر «أو أنشئ شحنة فارغة» بلا زر، وزر «إنشاء الشحنة» معطّل (selected=0) → المستخدم عالق بـ«إلغاء» فقط. الإصلاح: (1) توصيل `onCreateEmpty` في `DealManagement` → `navigate('/import-flow/new')` (يعمل SPA بلا reload بفضل G3)؛ (2) حالة فارغة موجِّهة (أيقونة + «لا صفقات جاهزة للشحن بعد» + إرشاد لتجهيز صفقة عبر «ابدأ الشحن الدولي» + زر «بدء شحنة فارغة»). مُتحقَّق حيّاً: الزر يفتح شاشة شحنة جديدة.
- **G3 توجيه «الخطوة التالية» بلا reload — منفَّذ 2026-07-17:** زر «ابدأ الشحن الدولي» (`DealStageControl`) يستدعي `navigate("/import-flow/new?...")` صحيحاً، لكن `DealManagement` كان فيه `useEffect` حارس «أي مسار ≠ /deals → `navigate('/deals',{replace})`». أثناء الانتقال SPA يبقى `DealManagement` مركّباً لطور الـeffects، فيشتعل الحارس ويُجهض التنقّل ويُرجع لقائمة الصفقات (reload يعمل لأن App يرسم import-flow مباشرة على mount نظيف). الإصلاح: حذف الحارس — `dealsPathMatch` يطبّع مسارات /deals المشوّهة أصلاً، ومزامنة `deals-management`⟺`/deals` يضمنها App + المُنقّلات الصريحة (كلها تُزامن الـURL). مُتحقَّق حيّاً: الزر يفتح رحلة الاستيراد فوراً بلا reload. الجذر مرتبط بـ [[task36-import-review-deal-modes]] (handledPathRef).
- **G2 طبقة أخطاء عربية موحّدة — منفَّذ 2026-07-17:** كل الكتابات تمرّ عبر `restApi.handleResponseError`، وكان `flattenDrfError` (أ) يُسقط اسم الحقل فلا يعرف المستخدم أي حقل، و(ب) يعمل `JSON.stringify` على عناصر المصفوفة غير-النصية → أخطاء `many=True` المتداخلة (`{"items":[{"product":[...]}]}`، وهي شكل بنود الصفقة) تظهر JSON خام. الإصلاح: وحدة نقية `utils/drfError.ts` (`humanizeDrfError`) — خريطة `FIELD_LABELS` (حقل تقني→تسمية عربية) + `COMMON_MESSAGES` (رسائل DRF الإنجليزية→عربية) + مشي متداخل يربط الرسالة بأقرب حقل ويُخفي المفاتيح التقنية غير المعروفة ويزيل التكرار؛ `detail`/`error`/`non_field_errors` بلا تسمية. `restApi` يفوّض لها (fallback عربي `تعذّر إتمام العملية`)؛ حُذف `flattenDrfError` المحلي. اختبار: `utils/drfError.test.ts` (9 حالات، ضمن glob المشغّل).
- **DEF-C3 معالجة التكرار (شراء):** عند إضافة صنف موجود في سطر آخر — تنبيه: موافق=دمج الكمية في السطر القائم · إلغاء=سطر مستقل بسعره. في `applyItemAt`.
- **DEF-C1 رصيد الشريك قبل/بعد:** `accounting.services.partner_posted_balance` (مجموع مدين/دائن الأسطر المرحَّلة للشريك بالعملة الأساسية) + `GET /api/partners/{id}/balance/?proposed_total=` (عميل: مدين−دائن · مورد: دائن−مدين). شُلِّك في شاشة الشراء (`InvoiceForm` يعرض «رصيد المورد قبل/بعد»). المبيعات تملك المعادل أصلاً (`credit_preview_for_sale`). 3 اختبارات (`test_partner_balance.py`).
- **DEF-C2 آخر سعر:** `last_sale_price(product, customer?)` + `GET /api/sales/invoices/last-price/`. شُلِّك في `SalesInvoiceEditor.onSelectProduct` (يقترح آخر سعر لهذا العميل/عام، قابل للتعديل). الشراء يملكه أصلاً (`ItemSearchModal` supplier_prices). 3 اختبارات (`test_last_price.py`).
- **DEF-C4 تقرير أرباح الفواتير:** `invoice_profits(...)` + `GET /api/sales/invoices/profits/`. الربح = صافي البنود قبل الضريبة − التكلفة التاريخية (مجموع `StockMovement.total_cost` لحركات البيع وقت الترحيل). الواجهة `components/accounting/InvoiceProfitsPage.tsx` على `/sales/profits` + رابط في الشريط الجانبي + تصدير إكسل عبر `AseelReportTable`. 3 اختبارات (`test_invoice_profits.py`).
- **DEF-D1 شجرة الحسابات (مُتحقَّق):** `AccountingCoaPage` يدعم الشجرة (أب/ابن، طيّ/فتح)، إضافة حساب/فئة (الحسابات هي الشجرة)، تعديل، حذف، نشط/مخفي (`is_active` + فلتر `activeOnly`). مكتمل — لا عمل.
- **DEF-D2 سندات/إيصالات/تحويل من الشريط (مُتحقَّق):** مُلبّى عبر `GlobalActionBar` (سند قبض→دفعات العملاء · سند صرف→دفعات الموردين · قيد تحويل→قيد يومية جديد · الشيكات → صفحة الشيكات).
- **DEF-D3 تعدد العملات (مُتحقَّق):** الأرصدة تُحسب بالعملة الأساسية (`base_debit/base_credit`)؛ رصيد المبيعات يحوّل عبر `exchange_rate`؛ لا خلط صامت.

### المنفّذ مسبقاً (لا عمل في هذه الجولة)
- DEF-B4 إضافة مورد inline (task16 C9: `InvoiceBasicInfo.onOpenAddSupplier→SupplierModal`). · DEF-B6 وصل دفع مدمج للمورد (`PurchaseInvoiceAccountingPanel` + `purchaseInvoiceApi.addSupplierPayment`، task17). · معظم B (مبيعات): إضافة عميل inline، شبكة دفعات، إكمال تلقائي، رصيد قبل/بعد، معاينة قيد+ربح — كلها من tasks 11–17.

### [ROUTES — مضاف task18]
- `/sales/profits` → `InvoiceProfitsPage` (view: `invoice-profits`).

### [ORPHANS & PENDING — task18]
- [ ] **DEF-B5 (جزئي):** نافذة إدخال السطر الكاملة (آخر سعر + تكلفة + ربح + **رصيد لكل مستودع**). المتوفر: «المتاح» وإجمالي السطر في الشبكة، الربح/التكلفة في معاينة القيد (مبيعات)، آخر سعر (الجهتان). الناقص: تفصيل الرصيد لكل مستودع في نافذة منبثقة للسطر — يتطلب استعلام مخزون على مستوى المستودع (نموذج `Warehouse` من task15) ولم يُبنَ في هذه الجولة.
- [ ] **تحقق UI حيّ مُصادَق:** شريط الإجراءات وصفحة الأرباح ورصيد المورد وآخر سعر تُرسَم بعد تسجيل الدخول فقط؛ تأكيد النقر الحيّ متروك للمالك (إدخال كلمة المرور للمصادقة محظور على الوكيل). التحقق تمّ عبر pytest + tsc + vite build + رسم صفحة الدخول.

**تحقق ختامي task18:** backend **183/183** خضراء (174 + 9 جديدة: أرباح الفواتير 3 · رصيد الشريك 3 · آخر سعر 3) · tsc 0 · vite build OK · `manage.py check` 0. التحقق الحيّ المُصادَق متروك للمالك (انظر ORPHANS).

## [AUDIT — task23, 2026-06-20] (Global Back Button - زر الرجوع العام)

- **زر رجوع عام:** تمت إضافة زر "رجوع" (ArrowRight) بجوار مسار التنقل (Breadcrumb) في `components/layout/Breadcrumb.tsx` ليظهر في كل شاشات النظام.
- **التوجيه (Routing):** الزر يستخدم `useNavigate` من `react-router-dom` وينفذ `navigate(-1)` للعودة إلى الصفحة السابقة في الـ History. 
- **التجريد:** الإضافة تمت في المكون المركزي مما يلغي الحاجة لتكرار الكود في كل صفحة.
- **الاختبار:** تمت كتابة اختبار Playwright (`e2e/back-button.spec.ts`) بناءً على منهجية TDD، لكن الاختبار يتطلب تجاوز صفحة تسجيل الدخول لرؤية الواجهة الداخلية (سيتم إضافة دعم المصادقة للاختبارات لاحقاً).
- **التحقق:** `npm run build` يعمل بنجاح (tsc 0, vite build OK). لا توجد أكواد Deprecated بناءً على هذا التعديل.

## [AUDIT — task24, 2026-06-21] (تأكيد تسجيل الخروج)

- **جراحة الواجهة:** إضافة حوار تأكيد `window.confirm("هل تريد تأكيد تسجيل الخروج؟")` في زر تسجيل الخروج العام (في `AppLayout.tsx`) وفي واجهة المتجر (في `StorePage.tsx`).
- **التجريد:** تم التعديل بشكل موضعي (Surgical) بدون التأثير على منطق الـ `AuthContext` الأساسي، للحفاظ على استقرار النظام وإمكانية مناداة `logout()` برمجياً عند الخمول بلا تأكيد.
- **التحقق:** التعديل تم بسلاسة وبدون أي مساس بميزات أخرى. لا يوجد أي كود Deprecated.

## [AUDIT — task25, 2026-06-21] (توحيد عرض محرّر مبيعات المبيعات)

- **جراحة الواجهة:** تعديل `SalesInvoicesPage.tsx` لإلغاء العرض بوضع ملء الشاشة (`fixed inset-0 z-[60]`) لمحرر الفاتورة، وجعله يعرض داخل الصفحة بشكل طبيعي (Inline) أسوةً بفواتير المشتريات.
- **النتيجة:** أصبحت القائمة الجانبية (Sidebar) والترويسة العلوية (Header) مرئية دائماً عند فتح فاتورة مبيعات جديدة أو تعديل فاتورة سابقة.
- **التحقق:** `npm run build` اجتاز الفحص (tsc 0). لا يوجد كود Deprecated.

## [AUDIT — task28, 2026-06-21] (الصندوق الافتراضي في دفعات العملاء)

- **جراحة الواجهة:** تعديل `SalesCustomerPaymentsPage.tsx` لسحب الصندوق الافتراضي (Default Cash Account) المعرّف في إعدادات المشتريات (والذي يعمل كصندوق افتراضي للنقدي) وتمريره إلى نافذة الدفعة الجديدة `NewPaymentModal`.
- **التجريد:** تم استدعاء `purchaseInvoiceApi.getSettings()` داخل دورة جلب البيانات الأولية `loadAll` بدون إضافة تعقيد أو تكرار واستخدامه كقيمة أولية (Prefill).
- **التحقق:** تمت إضافة اختبار `default-cash-account.spec.ts` (TDD) وتم اجتياز الفحص البرمجي (tsc 0).
- **Task 30:** Replicated duplicate item warning and quantity merge logic in Sales Invoices ('SalesInvoiceEditor.tsx') to match the behavior in Purchase Invoices, per user request.
- **Task 31:** Added unsaved changes guard (dirty state tracking) to Purchase Invoices ('InvoiceForm.tsx') to warn the user before canceling or creating a new invoice, matching the behavior in Sales Invoices.
- **Task 32:** Added a below-cost warning to the unit price cell in SalesInvoiceEditor to alert users when the selling price is lower than the product's average cost.
- **Task 32:** Added below-cost warning to Sales Invoices ('SalesInvoiceEditor.tsx') so when a user types a unit price lower than the average cost, the input highlights in red and shows a warning.
- **Task 33:** Added confirmation prompt to the Restore Draft button in Sales Invoices ('SalesInvoiceEditor.tsx') if the current session has unsaved modifications, preventing accidental loss of data.
- **Task 34:** Removed InvoiceCategoryTree (product category sidebar) from both Sales Invoices ('SalesInvoiceEditor.tsx') and Purchase Invoices ('InvoiceForm.tsx') to streamline the layout and rely on other available product addition methods.
- **Task 35:** Implemented auto-scrolling to the bottom of the invoice lines grid when new lines are added. Modified AseelGrid.tsx to use a flex column with internal overflow and scrollIntoView logic, ensuring large invoices remain fully visible and usable without stretching the main page.
- **Task 35 Fix:** Refined AseelGrid auto-scroll behavior to use setTimeout and scrollTop = scrollHeight to reliably force the grid scrollbar to the bottom immediately after a new row is added.
- **Task 36:** Promoted WarehousesManager to a standalone top-level interface. Added 'warehouses' view to App.tsx, inserted a navigation link under the Inventory section in Sidebar.tsx, and updated breadcrumbs, resolving the lack of a clear warehouses interface.
- **Task 37:** Added 'Load All Items' (����� �� �������) button to the Stocktake form to auto-populate the grid with all available products, streamlining the inventory counting process.

## [AUDIT — task28 الاستيراد، المرحلة 1، 2026-06-24] (صلاحية وحدة الاستيراد + إخفاء تكاليف الاستيراد من COA)

أول مرحلة من «جراحة الاستيراد» متعددة المراحل (القرارات: فصل الفاتورة الدولية، صندوق الدولار FIFO مع فرق صرف محقّق، تقسيم المخزن محلي/دولي، صفحة هبوط بنوعين، تأكيد الحذف — مراحل لاحقة).

- **النموذج (من مستويين):** `Tenant.import_enabled` (سوبر أدمن المنصة يقرّر أي شركة) + `UserCompanyMembership.can_access_import` (مدير الشركة يمنح لكل موظف، فعّال فقط ضمن شركة مفعّلة). Migration `tenants/0010_import_access`.
- **السوبر أدمن:** `core/import_access.py` — `is_super_admin` (is_superuser أو البريد في `SUPER_ADMIN_EMAILS`، الافتراضي `thapet64@gmail.com`) + `user_can_access_import(user, tenant)` (سوبر أدمن دائماً؛ وإلا الشركة مفعّلة وَ(مدير أو ممنوح)).
- **إخفاء COA:** `AccountViewSet.get_queryset` يستثني الشجرة `53*` (تكاليف الاستيراد: شحن دولي/تخليص/رسوم… 5301–5307) لمن لا يملك الصلاحية.
- **نقاط النهاية:** `POST tenants/companies/{id}/set-import-enabled/` (سوبر أدمن، يصل لأي شركة بمعرّفها) · `POST tenants/companies/{id}/members/set-import-access/` (مدير، يشترط تفعيل الشركة). `TenantSerializer` يضيف `import_enabled`؛ member payload + `UserCompanyMembershipSerializer` يضيفان `can_access_import`.
- **الأعلام للواجهة:** `hr/auth_api._user_payload` يضيف `isSuperAdmin` + `canAccessImport` (محسوبان من العضوية الافتراضية؛ الإنفاذ الموثوق يبقى على الخادم لكل شركة نشطة).
- **الواجهة:** `types/user.ts` (+ الحقلان) · `Sidebar.tsx` مجموعة «الاستيراد» الفرعية تظهر فقط مع `canAccessImport` · `CompanyManagementModal.tsx`: مفتاح تفعيل الاستيراد للشركة (سوبر أدمن) + عمود checkbox «استيراد» لكل عضو (مدير، بعد التفعيل؛ المدير «ضمناً»). `CompanyContext` Tenant/Membership types موسّعة.
- **التحقق:** `tenants/tests/test_import_access.py` (14 اختبار TDD: الـhelper + مصفوفة COA + نقاط التفعيل) + تحديث `test_read_isolation` (الشركة الجديدة تخفي 53* افتراضياً). الحزمة الكاملة: 262 passed · `tsc` 0.
- **ملاحظة (نطاق لاحق):** مفتاح السوبر أدمن يعيش حالياً داخل CompanyManagementModal (المنحصر بشركات المستخدم المدير). لوحة سوبر أدمن مستقلة لكل الشركات = مرحلة لاحقة إن لزم.

## [AUDIT — task28 الاستيراد، المرحلة 2 (الخلفية)، 2026-06-24] (فصل الفاتورة الدولية + تقسيم المخزن)

أساس الخادم لفصل الفاتورة الدولية عن المحلية وتمييز مصدر المخزون. الواجهة (شاشتان + أقسام المخزن) = الخطوة التالية.

- **`PurchaseInvoice.invoice_type`** (`local`/`international`، افتراضي local) — migration `logistics/0047_purchaseinvoice_invoice_type` يَبني الحقل ويعيد ملء الموجود: دولية حيث `deal`/`shipment`/`clearance`/`converted_from_shipment` مضبوط (نفس منطق `is_local` القديم).
- **الفصل في الـAPI:** `PurchaseInvoiceViewSet.get_queryset` يدعم `?invoice_type=local|international` ويُخفي الدولية عمّن لا يملك صلاحية الاستيراد (مطابق لإخفاء COA بالمرحلة 1). `perform_create` يشتق النوع (صريح ← روابط الاستيراد ← محلي) ويرفض إنشاء الدولية (403) لغير المخوّل. المُسلسِلان (list+detail) يكشفان `invoice_type`.
- **تقسيم المخزن:** `StockMovement.origin` (property: international إن كان reference_type ∈ SHIPMENT/DEAL/CLEARANCE، local إن PURCHASE_INVOICE، وإلا other) + ثوابت `IMPORT_REFERENCE_TYPES`/`LOCAL_REFERENCE_TYPES`. المُسلسِل يكشف `origin`، و`StockMovementViewSet` يدعم `?origin=local|international`.
- **التحقق:** `logistics/tests/test_invoice_type_split.py` (9 اختبارات: النوع الافتراضي/الحجب/السماح/الإخفاء بالقائمة/الفلتر + origin property/filter). الحزمة الكاملة **265 passed**.
## [AUDIT — task28 الاستيراد، المرحلة 3 (ذيل) + تأكيد الحذف، 2026-06-25]

### ذيل المرحلة 3 — FIFO لدفعات التخليص ووكيل الشحن
- استُخرج helper مشترك في `accounting/fx_fifo.py`: `fifo_link_for_box(box_account, tenant)` + `build_fx_payment_lines(...)` (يستهلك FIFO ويبني أسطر الشيقل + فرق صرف محقّق).
- طُبِّق في الثلاثة (DRY): دفعة الصفقة (`post_payment_to_accounting`)، دفعة وكيل الشحن (`post_agent_payment_to_accounting`)، ودفعة التخليص (`pay_from_cashbox` — يحوّل القيد للشيقل amount×سعر الدفع عند استخدام صندوق FIFO). صندوق بلا طبقات ⇒ السلوك القديم (توافق رجعي).
- اختبارات: `logistics/tests/test_deal_payment_fifo.py` صار 5 (صفقة ربح/خسارة/legacy + وكيل ربح + تخليص ربح). الحزمة الكاملة 276 passed.

### تأكيد الحذف الموحّد
- `components/common/ConfirmDialog.tsx` (حوار RTL، نمط خطر أحمر، Esc/Enter) + `contexts/ConfirmContext.tsx` (`ConfirmProvider` + `useConfirm()` وعديّ: `if (!(await confirm({message}))) return;`). مُركّب في `index.tsx` حول `<App/>`.
- حُوِّل 12 موقع حذف من `window.confirm` إلى `useConfirm`: CompanyManagementModal، ShipmentManagement، DealManagement، SalesCustomersPage، SalesQuotationsPage، SalesInvoicesPage، CategoriesManagement، CategoryPicker (CategoryManageModal)، LocalShippingPage، InvoiceList، ImportDocumentScreen، OldPurchaseInvoice. `tsc` 0؛ التطبيق يُقلع بلا أخطاء.
- **متبقٍ:** مواقع `window.confirm` غير المتعلّقة بالحذف (تسجيل خروج/ترحيل/تغييرات غير محفوظة) تبقى كما هي — يمكن توحيدها لاحقاً بنفس `useConfirm`.

## [AUDIT — task28 الاستيراد، المرحلة 4، 2026-06-25] (صفحة الهبوط بنوعين + تسجيل تاجر/موظف)

صفحة هبوط بمسارين للتسجيل وواجهتَي ترحيب مختلفتين.

- **`LandingPage.tsx`:** قسم «اختر نوع حسابك» ببطاقتين — «للتجار وأصحاب الشركات» (`onSignup('trader')`) و«للموظفين ومنظّمي فريق كترا» (`onSignup('employee')`)؛ أزرار الهيرو/الختام تمرّر لقسم `#signup-paths`. تغيّر توقيع `onSignup` إلى `(type) => void`.
- **`SignupPage.tsx`:** prop `accountType`. التاجر: نموذج مبسّط (اسم الشركة/المتجر، بلا سيرة ذاتية/مؤهل/خبرة) + عنوان «سجّل شركتك» + زر «إنشاء حساب الشركة». الموظف: النموذج الكامل الحالي بلا تغيير.
- **`App.tsx`:** حالة `signupType` تُمرَّر للـSignupPage؛ تسجيل الدخول→تسجيل يفترض «trader».
- **الخادم:** `signup_view` يقرأ `accountType` (trader/employee) و`companyName` ويخزّنهما في مرآة المستخدم؛ `authService.signupUser` وُسِّع (الحقول المهنية اختيارية + accountType/companyName).
- **التحقق (متصفّح حيّ):** صفحة الهبوط ترسم القسمين والبطاقتين؛ مسار التاجر يُظهر حقل الشركة بلا سيرة ذاتية، مسار الموظف يُظهر السيرة/المؤهل بلا حقل شركة؛ بلا أخطاء console. `tsc` 0.

## [AUDIT — task28 الاستيراد، المرحلة 3 (محرّك FIFO)، 2026-06-24] (صندوق الدولار FIFO)

محرّك FIFO لصناديق العملة الأجنبية: تمويل بطبقات بسعر صرفها، واستهلاك الأقدم أولاً بتكلفة الشيقل بسعر الطبقة (مثال المالك: 1000$@3 ثم 500$@4، دفع 1200$ → 3800 شيقل).

- **النموذج `CashBoxFxLot`** (طبقة FIFO): `cash_box`(FK CashBoxLedgerAccount)/`lot_date`/`original_fc`/`remaining_fc`/`rate`(شيقل لكل وحدة)/`source`(capital|transfer_ils)/`journal`. ترتيب `lot_date,id`. Migration `accounting/0025_cashboxfxlot`.
- **الخدمة `accounting/fx_fifo.py`:** `fund_box_from_capital` (مدين الصندوق شيقل/دائن رأس المال) · `transfer_ils_to_fx` (مدين الأجنبي/دائن الشيقل) · `consume_fifo`→(تكلفة شيقل، تفصيل الطبقات) ينقص الأقدم أولاً ويرفع عند نقص الرصيد · `box_fc_balance`/`box_ils_value` (القيمة الدفترية = Σ remaining×rate = رصيد حساب الصندوق). كل قيد عبر `post_journal` المركزي.
- **نقاط النهاية** (على `cash-box-accounts/{id}/`): `fund-capital`، `transfer-from-ils` (body amount/rate/date[/ils_box_id])، `fx-lots` (الطبقات + الرصيد).
- **ربط دفعات الصفقات (مُنفَّذ):** `LogisticsDealViewSet.post_payment_to_accounting` صار واعياً للـFIFO: إن كان الصندوق المصدر بعملة أجنبية وله طبقات، يُسحب `consume_fifo` (تكلفة الشيقل)، والقيد = مدين ذمم المورد (مبلغ×سعر الدفع) / دائن الصندوق (تكلفة FIFO) / **فرق الصرف المحقّق** للفرق (ربح=دائن، خسارة=مدين) على حساب `get_realized_fx_account` (كود 4201، يُنشأ عند الحاجة + مضاف لـ`tenants.services.COA_DATA` وseed). صندوق بلا طبقات ⇒ السلوك القديم بلا تغيير (توافق رجعي).
- **التحقق:** `accounting/tests/test_fx_fifo.py` (6) + `logistics/tests/test_deal_payment_fifo.py` (3: ربح/خسارة فرق صرف/توافق رجعي لصندوق بلا طبقات).
- **واجهة التمويل (مُنفَّذة):** `FundFxBoxModal.tsx` (إيداع من رأس المال / تحويل من صندوق الشيقل بسعر صرف + عرض الطبقات والرصيد) + زر «تمويل» (أيقونة Layers) على بطاقات صناديق العملة الأجنبية في `CashBoxList.tsx`؛ خدمة `accountingApi`: `fundFxBoxFromCapital`/`transferIlsToFxBox`/`getFxBoxLots`. `tsc` 0.
- **المتبقي (مرحلة لاحقة):** نفس معالجة FIFO لدفعات التخليص/وكيل الشحن بالدولار (`pay_from_cashbox`/`post_agent_payment`).

## [AUDIT — task28 الاستيراد، المرحلة 2 (الواجهة)، 2026-06-24] (فصل شاشتي الفاتورة + أقسام المخزن)

- **الواجهة (مُنفَّذة):** `PurchaseInvoice.tsx` صار يقبل `invoiceType` (افتراضي local) + `listPath`؛ شاشة الشراء الحالية تعرض المحلية فقط ويختفي زر «استيراد من تخليص جمركي» منها. شاشة **«الفواتير الدولية»** الجديدة (view `international-invoices`، مسار `/international-invoices`، تحت مجموعة الاستيراد) تعيد استخدام نفس المكوّن بـ `invoiceType="international"` وتعرض زر الاستيراد/التحويل؛ محرّر الفاتورة يبقى مشتركاً على `/purchase-invoices/:id` (يُفتح بتبويب جديد). `canAccessImport` صار تفاعلياً للشركة النشطة عبر `CompanyContext` (يشترط تفعيل الشركة للجميع). شاشة حركات المخزون أُضيف لها فلتر «المصدر» (محلي/دولي عبر `?origin=`) + عمود شارة. `tsc` 0.

- **Task 38:** Updated AseelGrid `handleKeyDown` to support a full, rapid data-entry sequence using the 'Enter' key: pressing 'Enter' now moves focus sequentially from 'Product' → 'Quantity' → 'Price' → 'Product' on the next row (creating a new row if necessary). The event listener was also moved to the row level to properly capture events from custom renderers like `AseelAutocomplete`.

- **UserManagement Fix:** Fixed infinite re-rendering and UI flickering bug in `UserManagement.tsx` caused by re-fetching all activity statuses every 5 seconds. Replaced the `users` dependency in `useEffect` with a stable `employeeIds` string derived from `users.id`, and prevented `loadAllActivityStatuses` from showing a full-page loading spinner if background data is already present. This ensures smooth UX while maintaining real-time updates.

## [AUDIT — جراحة الفاتورة الدولية، 2026-07-16] (الشحنة + التخليص + الرسوم + توحيد المجاميع)

- **رابط الشحنة:** `InvoiceForm.tsx` يعرض زرّاً أساسياً واضحاً «فتح رحلة الشحنة SH-…» في رأس الفاتورة، إلى `/import-flow/{shipmentId}`، سواء جاء الربط من `importLogistics` أو حقل `shipment`؛ الرابط القديم داخل تفاصيل البنود بقي للتوافق.
- **وضوح تكلفة البند المستورد:** عناوين `AseelGrid` للفواتير المرتبطة بشحنة أصبحت «تكلفة الوحدة الشاملة للاستيراد» و«إجمالي السطر الشامل للاستيراد»، مع تنبيه مرئي يشرح أنها تشمل البضاعة والشحن والجمارك/التخليص والنقل ولا تشمل ض.ق.م والرسوم الإضافية. الملخص يسمّي قيمة البضاعة قبل تكاليف الاستيراد صراحة، وجدول `NISItemsTable` يفرّق بين تكلفة الاستيراد، وما قبل ض.ق.م، والتكلفة النهائية بعد الضريبة والرسوم. الفواتير المحلية تحتفظ بعناوينها القديمة.
- **مصدر صفقات التخليص:** `ClearanceImportModal.tsx` يحتفظ الآن بصفوف `clearance-import-options` الموثوقة ويدمجها مع `shipment.deals` عبر `mergeClearanceImportDeals` في `invoiceConversionUtils.ts`. لذلك لا يعود المودال فارغاً عندما تكون تفاصيل الشحنة ناقصة بينما توجد صفقة غير محوّلة في خيارات الخادم.
- **حفظ الرسوم:** المسار الرسمي الوحيد هو `PurchaseInvoiceFee`. جدول «ضريبة القيمة المضافة والرسوم» داخل بنود الفاتورة يحرر `formData.fees` مباشرة: مبلغ أو نسبة، وأساس النسبة «على البضاعة» أو «بعد الضريبة». تبويب «حسابات الرسوم» بقي لضبط الحساب/الرسملة فقط، وزر الحفظ يتحقق من عدد البنود في رد POST/PATCH قبل إغلاق التحرير، مع Logging لنتيجة الحفظ.
- **عقد الرسم النسبي:** migration `logistics/0055_purchaseinvoicefee_calculation_fields` أضافت `calculation_type` و`calculation_value` و`percentage_basis` مع backfill للرسوم القديمة. يبقى `amount` مبلغ ILS النهائي للمحاسبة؛ الخادم يعيد حسابه للنسبة ولا يثق بالمبلغ المرسل.
- **عرض المستحق:** رسوم `PurchaseInvoiceFee` تظهر مباشرة تحت ض.ق.م في الملخص، وتدخل في إجمالي المستحق، والأقساط، وتوزيع «تكلفة الوحدة بعد الضريبة والرسوم» في جدول البنود، وملخص الدفع السفلي.
- **منع الجمع المكرر:** `invoiceTaxesAndFees.ts` يميّز `allocation_method=server_pro_rata`؛ إجمالي أسطر الفاتورة المستوردة يتضمن أصلاً الشحن/التخليص/النقل، فلا يعاد جمعها مرة ثانية. عمولات التحويل غير المضمنة تبقى مضافة مرة واحدة.
- **مزامنة GET الحي:** `PurchaseInvoiceSerializer.to_representation` يعيد حساب ض.ق.م/الإجمالي/المستحق/المتبقي للفواتير الدولية غير المرحّلة بعد تغيّر landed cost الحي، باستخدام إعداد ضريبة الفاتورة المحفوظ لا ضريبة الصفقة، بدون أي كتابة أثناء GET.
- **اختبارات:** `test_clearance_import.py` يغطي تغيّر النقل بعد الاستيراد وتطابق الضريبة/الإجمالي الحي؛ `test_import_payment_separation.py` يغطي POST/PATCH/GET للرسم الثابت والنسبي وإعادة حسابه بعد تغيّر الفاتورة؛ `purchase-invoice-fee-editor.spec.ts` يغطي أساس البضاعة/بعد الضريبة وعدم الجمع المكرر وfallback خيارات التخليص.
- **Deprecated معالج:** لم يعد `InvoiceForm` يرسل أو يكتب رسوم المستخدم في `local_payments.taxesAndFeesLines`؛ بقيت قراءة أدوات JSON القديمة للتوافق فقط، بينما `NISInvoiceTaxStrip` يكتب `PurchaseInvoiceFee` المهيكل.

## [AUDIT — مصالحة تعديل الصفقة وتكلفة الوحدة النهائية، 2026-07-16]

- **تكلفة الوحدة النهائية:** `allocateInvoiceFinalCosts` في `invoiceTaxesAndFees.ts` صار المصدر المشترك لتوزيع عمولات التحويل وض.ق.م والرسوم على أسطر الفاتورة. شبكة الفاتورة الرئيسية تعرض عمود «التكلفة النهائية/وحدة»، وتسمّي السعر المخزن «قبل ض.ق.م والرسوم» حتى لا يُفهم أنه شامل كل شيء. لا يُعدّل `unitPrice` المخزن، لمنع احتساب الضريبة/الرسم مرتين.
- **تعديل الصفقة بعد ربطها:** صفقة مرحلة `sw_released` لم تعد مقفلة عن تعديل البنود. شاشة رحلة الاستيراد تعرض زر «تعديل» لكل صفقة، وتعيد تحميل الشحنة عند الرجوع إلى التبويب.
- **مصالحة الحفظ:** `recalculate-landed-cost` يدعم `auto_repost`: يلتقط الفواتير الدولية المرحّلة، يلغي ترحيلها عبر مسار الإلغاء الرسمي، يعيد توزيع حصة الشحن وبناء البنود من الصفقة الحالية، ثم يعيد ترحيل الفواتير التي كانت مرحّلة فقط. الفاتورة المسودة تُحدّث وتبقى مسودة. فشل إعادة الترحيل يترك الفاتورة المحدّثة مسودة مع تحذير بدل إبقاء قيد قديم بأرقام خاطئة.
- **حفظ إعدادات الفاتورة:** إعادة الحساب تستخدم أسعار الصرف وخيار بنود التخليص المحفوظ لكل فاتورة، وتحافظ على نوع/نسبة ض.ق.م، وتعيد حساب رسوم النسبة على الأساس الجديد.
- **توصيل الواجهة:** حفظ الصفقة أو الشحنة أو التخليص أو تكلفة/أساس الشحن أو توزيع الصفقة أو النقل المحلي يستدعي المصالحة فوراً ويعرض نتيجة تحديث المسودات/إعادة الترحيل.
- **زيادة الدفع للمورد:** تخفيض قيمة الصفقة تحت الدفعات المرحّلة لم يعد مرفوضاً؛ `posted_paid_amount` و`amount_outstanding` و`supplier_advance` تفصل المتبقي عن «رصيد لصالحك عند المورد»، و`remaining_amount` لا يصبح سالباً.
- **كشف المورد:** دفعة الصفقة تربط المورد بسطر الذمم فقط، لا بسطر الصندوق. Migration `0056_fix_logistics_payment_partner_lines` تصلح القيود القديمة بنفس القاعدة حتى يظهر رصيد المورد الحقيقي.
- **Logging:** تسجل الخلفية نتيجة مصالحة الشحنة، وإعادة الترحيل/البقاء كمسودة، ورصيد المورد الناتج من تخفيض الصفقة.
- **الاختبارات:** TDD يغطي توزيع التكلفة النهائية دون تغيير السعر الأساس، تخفيض صفقة مدفوعة وإظهار الرصيد، عدم ربط المورد بخط الصندوق، وإلغاء/إعادة ترحيل الفاتورة تلقائياً. `vite build` ناجح و`makemigrations --check --dry-run` بلا تغييرات.
- **فرق دفعة الشحن بعد زيادة التكلفة:** الشحنة المرحّلة تسمح الآن بـPATCH خاص بسجل `agent_payments` فقط، لذلك إضافة صفقة وارتفاع الشحن لا يجمّدان دفعة الفرق برسالة «هذا المستند مرحّل». الدفعات القديمة المرحّلة تبقى كما هي، وتُنشأ دفعة جديدة للمتبقي؛ حقول الشحنة الأخرى تظل محمية. نُقلت مزامنة الدفعات المتداخلة إلى `LogisticsShipmentSerializer.update` الصحيح، والواجهة تعبئ مبلغ الفرق تلقائياً ثم تعيد مصالحة الفواتير المرتبطة بعد الحفظ.
- **التحقق النهائي:** نجحت الحزمة الكاملة **307/307** مع `core.test_settings`، ونجح `vite build`، و`django check` بلا مشاكل؛ كما تحقق المتصفح الحي من تعبئة فرق دفعة الشحن تلقائياً دون تسجيل حركة مالية فعلية.
