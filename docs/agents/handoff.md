# ملف التسليم

يُحدَّث قبل أي توقّف (CLAUDE.md — Workflow، الخطوة 8). من يستلم يبدأ من هنا.
**وبطلب المالك (2026-10-22): يُحدَّث بعد كل تذكرة، وبعد كل جولة تصليح، وقبل أي ضغطٍ للسياق** — هو ذاكرة
المنسّق بعد الـcompact. الإكمال حتى آخر تذكرة بلا توقّف.

**آخر تحديث:** 2026-10-22

## الآن بالضبط

- **C2** مستلَمة: commit `07741f3f` (3 جولات تصليح؛ backend 6478 ✓ · tsc/npm test/build ✓ · e2e 30 ✓ · لقطات
  الشاشة رآها المنسّق)، ودُفعت `newktra` (`4deebda3`). **النشر الأوّل (`deploy9.log`) تراجع تلقائياً** قبل
  `migrate`: اختبار `platform_ops/tests/test_applicant_meetings.py::…test_editing_the_time_does_not_wipe_the_agenda`
  سقط على الخادم ومحلياً **وعلى `316c5e1c` المنشور** — عطبٌ قائم لا من C2: انتهاء التوقيت الصيفي في
  `Asia/Hebron` يوم 2026-10-24 (الساعة 01:00–02:00 تتكرّر)، و`_clean_meeting_window` يقارن `datetime`ين بنفس
  الـtzinfo فيقارن بالساعة الجدارية (`01:12+03:00` «يساوي» `01:12+02:00`) ⇒ 400 على تعديلٍ صحيح. يسقط فقط
  ما دام «الآن + يوم» داخل تلك الساعة (≈ حتى 23:00 UTC يوم 2026-10-21). **⇒ إعادة النشر `deploy10.log` بعد
  انقضاء النافذة.**
- **تذكرة DST1 (بعد C3):** المقارنة في `_clean_meeting_window` بالـUTC، واختبارٌ مثبَّت على ساعة التحوّل لا
  على «الآن»، ومسحٌ تقريريّ لمقارناتٍ مماثلة (تقريرٌ فقط).
- **C3**: التنفيذ انتهى (`C3run` انقطع ← استُؤنف `C3run2`؛ للاستئناف بـ`--variant` يلزم `--model` أيضاً). قرأ المنسّق
  الفرق كاملاً. جولة التصليح 1 انتهت (`C3fixrun`: Esc، مربّع «إزالة التصنيف»، تعليق، أشكال الأخطاء) وقرأها
  المنسّق. المراجعتان النهائيتان: لا عائق، ودقّةٌ استحقّت جولة 2 (`C3fix2run`) + تعليقين (`C3fix3run`) — قرأها المنسّق.
  **C3 مستلَمة: commit `32ca072e`** (بوّابات 6498 · 1294 · e2e 38 · لقطات رآها المنسّق) — دُفعت مع DST1.
- **DST1 مستلَمة: commit `44ea8200`، ودُفعت `newktra` مع C3** ← CI أخضر ✓ ← **C3+DST1 منشورتان على الإنتاج** (`deploy11.log`: الخادم على `82aade47`، active، NRestarts 0، الفحوص الثلاثة 200، نقاط الوكيل الأربع 200، صفر أخطاء gunicorn، لا هجرات؛ جذر الويب كلّه من `dist/`).
- **SEC1 انتهت** (`SEC1run`، $0.03): فلتر `tenant_id` في `_push_family_fields_to_siblings` + اختباران أُحمِرا؛ قرأ المنسّق الفرق. بوّابة كاملة + مراجعتا Standards/Spec (على DST1+SEC1) تعملان. مسح SEC1 يقترح **SEC2**: `sync_family_from_product`/`sync_families_from_products` تكتب صفّ الأب من براندٍ لشركةٍ أخرى بلا تحقّق تطابق `tenant_id`، و`add_brand_to_family` يقرأ `filter(family=family)` بلا شركة. بوّابة SEC1 الكاملة 6505 ✓. المراجعتان: لا عائق — دقّة صياغة ⇒ جولة تصليح (`SEC1fixrun`) قرأها المنسّق، بوّابة 6506 ✓ ⇒ **SEC1 مستلَمة ومدفوعة**. **SEC2 انتهت** (`SEC2run`، $0.05): حارس تطابق الشركة في `sync_family_from_product`/`sync_families_from_products` (تخطٍّ بتحذير)، و`add_brand_to_family` يرفض شركةً مخالفة ويقرأ بفلترها؛ 4 اختبارات أُحمِرت. قرأ المنسّق الفرق؛ المراجعة: لا عائق ⇒ جولة تصليح (`SEC2fixrun`: `assertNumQueries(0)` خارج `assertRaises` لأن عدّاد Django لا يفحص عند الاستثناء، اسم معامل، صياغة) قرأها المنسّق؛ بوّابة 6510 ✓ ⇒ **SEC2 مستلَمة ومدفوعة** ← CI أخضر ← **نشر SEC1+SEC2 معاً** (`deploy12.log`) ← K1 (`K1.txt` جاهز).
- **C2 منشورة على الإنتاج** (`deploy10.log`: الخادم على `c06fd274`، الفحوص الثلاثة 200، NRestarts 0).
- **النشر من الآن بإجراء مهارة الخادم `deploy-local-to-modern`** (طلب المالك 2026-10-22): push ← CI أخضر ← على الخادم
  بوّابات خفيفة + بناء فقط (لا pytest/tsc على الإنتاج) ← لا push من الخادم. السكربت `deploy2.sh` في الـscratchpad،
  والخطوات في CLAUDE.md الخطوة 7. CI على `4deebda3` أحمر بسبب اختبار DST وحده ⇒ **DST1 قبل نشر C3**.
- **طابور ما بعد C3:** DST1 (`DST1.txt` جاهز) ← **SEC1**: `inventory/services.py` `_push_family_fields_to_siblings`
  يحدّث الإخوة بـ`family_id` بلا فلتر شركة (أبلغ عنه منفّذ C3؛ لا يصل إليه API اليوم — دفاعٌ في العمق، يُصلَح
  بلا سؤال بقاعدة الذاكرة) ← K1 ← K2 ← K3 ← K4. **موجزا `SEC1.txt` و`K1.txt` جاهزان** في الـscratchpad
  (K1: هجرة إضافية، `create_stocktake_from_scope` بمطابقة صريحة + `all`، upsert + `replace_lines`، أختام العادّ،
  ETag/412، `uncounted_as_zero`، قائمة مختصرة، وسطر `replace_lines: true` وحده في `StocktakePage.tsx`).
- الـscratchpad: `C:\Users\asus\AppData\Local\Temp\claude\D--Users-asus-Desktop-ktra\e50319dd-86ab-4bfd-8e17-8dad24be7397\scratchpad`
  (الموجزات `C2*.txt`، سكربت النشر `deploy.sh`، آخر سجلّ نشر `deploy8.log`).
- **كل تشغيلٍ للمنفّذ بـ`--variant max`** (قاعدة في CLAUDE.md منذ 2026-10-22).

## أين نحن

- الخطة: `docs/plans/2026-10-21-inventory-count-category-tree.md` (13 تذكرة في 6 مراحل).
- **S1** (قفل ترحيل الجرد + ترقيم `TenantBook`) و**S2** (قفل كتابات الكتالوج بـ`inventory.item.manage` وإخفاء
  منافذها في الواجهة): مستلَمتان على `newktra`.
- النشر: S1+S2 على الإنتاج (`ba8e05d0`، 2026-10-21) — نسخة احتياطية
  `/root/backups/ktra-20261021-114700-pre-ba8e05d0.sql.gz` ثم هجرة `tenants.0036`، والفحوص الثلاثة 200.
- **B1** (الكبسة اليمنى على منتج): مستلَمة ومنشورة (`ba77f00f`، الفحوص الثلاثة 200). **B2** (تعديل البراند):
  مستلَمة ومنشورة (`65941149`). **B3** (الشجرة افتراضياً): مستلَمة ومنشورة (`e6c1d54a`، الفحوص الثلاثة 200).
  **R1** (تقرير المبيعات حسب المنتج): مستلَمة ومنشورة (`e72d72df`، الفحوص الثلاثة 200). **C1** (منتقي شجرة التصنيفات): مستلَمة ومنشورة (`316c5e1c`). **C2** (منتقي التصنيف في كرت المنتج): مستلَمة (`07741f3f`).

## الخطوة التالية

C2 ← C3 ← K1 ← K2 ← K3 ← K4، كلٌّ بحلقة CLAUDE.md (موجز ← تنفيذ في جلسة جديدة ←
قراءة الفرق ← Standards+Spec ← تصليح في جلسة جديدة حتى النظافة ← بوّابة ← استلام ونشر).

## مفتوح

- قيد فرادة `(tenant, stocktake_number)` بعد فحص تكرارات قاعدة الإنتاج.
- من منفّذ SEC2 (لم يُصلَح، صفٌّ فاسدٌ فقط): `ProductViewSet.add_brand` يحسب `will_create`/حدّ الخطة من `Product.objects.filter(family=family)` بلا شركة؛ و`adopt_family_for_product` يقبل `tenant` مخالفاً لشركة المنتج (مستدعيه الوحيد آمن).
- مسح DST1 (تقريرٌ لم يُصلَح): مقارنات بنفس `tzinfo` قد تعبر الساعة المتكرّرة في `activate_subscription_policy`
  و`activate_performance_evaluation_policy` و`activate_employee_compensation_policy` و`activate_service_unit_catalog`
  (`platform_ops/services.py`)، و`hr/attendance.py` (`resolve_attendance_date`، `recompute_attendance_day`،
  و`scheduled_minutes` تطرح 60 بدل 120 لوردية تعبر التحوّل).
- قرص الخادم 94% (3.2G حرّة) — النسخ الاحتياطية في `/root/backups` و`/root/ktra/db/` تأكل المساحة.
- `modern` على الخادم و`origin/modern` متباعدان (632 مقابل 29 commit من دمجات `localAccount`) — الدفع تقديمٌ
  سريع فقط، فيُتخطّى حتى يقرّر المالك.
