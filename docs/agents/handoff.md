# ملف التسليم

> **الخطة الكاملة المعتمدة لطرق تكلفة المبيعات وحالتها:** `docs/decisions/cogs_cost_methods.md` (أُنشئت 2026-11-18 بطلب المالك «اعملها بملف كاملة زي ما اتفقنا علبها بالبداية»؛ مصدرها نص الخطة المعتمد event 165). اقرأها قبل أي استئناف. **دقّقها المنسّق على الكود في 2026-11-18** بطلب «حللها وزبطها». أُضيف: قاعدة فرق المرتجع (§3.3، §4.2)، ورد AVCO النسبي (§3.5)، ونطاق الطريقة، وتوجيه التصحيحات اللاحقة للفروقات، وتذكرة M0، وإطلاق على دفعتين (AVCO = M5 أخيراً). **موجز M1B-1 السابق يُحدَّث بقواعد §3.3 قبل إعادة إرساله.**

## ▶ الآن بالضبط — 2026-11-18: تنفيذ خطة COGS كاملةً («يلا بلش الوورك فلو لتخلص الخطة كامله»)

> - ▶ **2026-11-22 الآن:** M5-2 ✅ **مودعة ومدفوعة `e633a400`** (البوّابة 8129 passed + الستة البيئية، الهجرات No changes)، وإيداع تثبيت الهاش يليها. قارئ M5-3 انتهى (`runs/M5-3-reader/final.txt`)، والمؤجَّل منه صار القضايا #296–#302. **الآن (`0fbf8794` إيداع الهاش مدفوع):** M5-3 منفّذ + تصليح 1 (F1–F8، Terra) في الشجرة غير مودَع؛ قُرئ فرق التصليح كاملاً وهو سليم. المراجعتان النهائيتان نظيفتان (`review/M5-3-*-r2.md`) والهجرات No changes. جولة تصليح 2 Terra انتهت وقُرئ فرقها كاملاً (G1–G3 سليمة). المراجعتان r3 (`review/M5-3-*-r3.md`): H1 should-fix (docstring `WarehouseTransfer`) + nits H2–H4، كلها مقبولة. البوّابة الكاملة على الحالة قبل التصليح 3: `6 failed (البيئية), 8139 passed`. جولة تصليح 3 (Sonnet high، H1–H4) انتهت وقُرئ فرقها كاملاً وهو سليم؛ تحقّقي: 107 passed والهجرات No changes. M5-3 ✅ **مودعة ومدفوعة `46f9d8d2`** وتثبيت الهاش يليها. **M5-4 (2026-11-22):** منفّذ Terra انتهى وقُرئ الفرق كاملاً (مطابق للموجز؛ sales+inventory 1333 passed، tsc 0، npm test 1451، build ok). المراجعتان r1 (`review/M5-4-*-r1.md`): قُبلت أربع (تعليق `salesApi.ts` القديم، كلمات بحث AVCO، `restore_defaults` يعامل avco كـfifo، تشديد e2e)، ورُفضت إعادة هيكلة `computeCogsExampleRows` (D3). تصليح 1 (F1–F4) وتصليح 2 (وثائق) Terra انتهيا وقُرئ فرقاهما كاملاً. المراجعتان النهائيتان على الحالة النهائية نظيفتان (`review/M5-4-*-final.md`). البوّابات على الحالة النهائية: الكاملة `6 failed (البيئية), 8140 passed`، tsc 0، npm test 1451، build ok، Playwright 1 passed، الهجرات No changes، sync_docs بلا تغيير. M5-4 ✅ **مودعة ومدفوعة `6d75402c`** وإيداع الهاش (CHANGELOG، سطر حالة الخطة، صف M5، §7) يليها. **الآن:** نشر الدفعة الثانية (`docs/agents/deploy.md`: CI أخضر، نسخة احتياطية قبل migrate 0057، rsync يستثني `dl`، ثم `sync_avg_cost_from_layers` معاينة ثم `--apply`). ✅ نُشرت الدفعة الثانية على الإنتاج 2026-11-22: دمج `origin/newktra` في `modern` (`916f51b1` ← `f539a933`) بلا تعارض، ونسخة احتياطية `/root/backups/backup-before-cogs-batch2-20261122-084840.sql` (29MB) قبل migrate، والهجرة `sales.0057` OK، وrsync يستثني `dl` (ملف واحد قبل وبعد)، والتحقّق أخضر (health محلي/عام والجذر 200، نقاط الوكيل الأربع 200، سجل gunicorn نظيف، NRestarts=0). ⏸ `sync_avg_cost_from_layers` معاينةً: synced=676 · unchanged=1391 · skipped_uncovered=7، لكن 657 منها يصير `avg_cost` لها صفراً، و631 منها بلا أي طبقة إطلاقاً (رصيدها ≤ 0)، فالتصفير يمحو آخر كلفة معروفة لها، وأول بيعٍ سالبٍ لها يُنشئ طبقة مؤقتة بكلفة صفر (`record_stock_movement`: `avg_before` > 0 وإلا `_last_layer_unit_cost` وإلا صفر). **`--apply` لم يُشغَّل، معلّق بقرار المالك** (الاقتراح: تذكرة صغيرة تجعل الأمر يتخطّى المنتج بلا أي طبقة حين يكون الهدف صفراً، ثم `--apply`). **قرار المالك 2026-11-22 (الخيار A، «اعمل الموصى»):** تذكرة **SYNC-NOLAYER**: المنتج بلا أي `StockLayer` إطلاقاً والهدف صفر يُتخطّى بحالة `skipped_no_layers` ويبقى `avg_cost`؛ ذو الطبقات المستهلكة كلها يبقى يُصفَّر (بديله `_last_layer_unit_cost`). **الآن:** المنفّذ Terra (high) أُطلق بموجز `briefs/SYNC-NOLAYER-impl.txt` إلى `runs/SYNC-NOLAYER-impl` (مهمة خلفية) ← قراءة الفرق ← مراجعتان Opus ← البوّابات ← إيداع ودفع ← CI ← نشر (دمج فقط، لا هجرة ولا واجهة) ← معاينة على الإنتاج (المتوقّع نحو synced=45 · skipped_no_layers=631 · skipped_uncovered=7) ← `--apply` ← تحقّق قراءةً (الـ631 تحتفظ بكلفتها، عدد القيود ثابت). **تقدّم SYNC-NOLAYER:** Terra انتهى (gpt-6.1-terra high، كل الاختبارات الأربعة رُئيت فاشلة للسبب ثم خضراء؛ inventory 648 passed). قرأتُ الفرق كاملاً: القاعدة بعد فحص غير المغطّى، والاستعلام مفلتر بالشركة، ولا كتابة عند التخطّي؛ nit واحد عندي: سطر فارغ زائد قبل البند الجديد في docstring الخدمة والأمر. المراجعتان Opus (Standards وSpec) تعملان ← `review/SYNC-NOLAYER-*-r1.md`.
> - ▶ **M5 (AVCO) 2026-11-21:** القارئ ✅ (`runs/M5-reader/final.md`). التقسيم: M5-1 المحرّك + أداء 200 طبقة (خامل) ← M5-2 الربط في `record_stock_movement` ← M5-3 التدفقات والسالب وlanded ← M5-4 رفع المنع API/واجهة. **M5-1 ✅** (Terra + تصليحان Terra + تصليح 3 Sonnet؛ مراجعتان نهائيتان بلا blocker؛ البوّابة والهجرات) — **مودع ومدفوع `7661ccb9`** (البوّابة 8127 passed + الستة البيئية، الهجرات No changes). **التالي:** M5-2 بقارئ Terra `--read-only` ثم موجز: ربط `consume(method=)` في `record_stock_movement` لكل صادر وكتابة `cogs_method` عليه، لقطة `avco` في `inventory/cogs_method.py` (`apply_sale_cogs_snapshot`)، المرتجعات المختلطة وM1B-R unpost/repost، وفرق التقريب 0.0004 بين قيمة الحركة q2 والطبقات. **قرار المالك 2026-11-21 («ساوي اقترحاتك بالسؤالين»):** حذف `SalesSettings.use_moving_average_cost` بهجرة RemoveField (`sales/0057`) وحذف الأدوات الأربع (#295) ← تذكرة **CLEANUP-COGS** (موجز `briefs/CLEANUP-impl.txt` جاهز) بعد إيداع M5-1 وقبل M5-2. موجز M5-2 جاهز `briefs/M5-2-impl.txt` (القرارات D1–D7 والاختبارات T1–T11)، يُملأ `<BASE>` فيه بهاش CLEANUP. **الترتيب:** CLEANUP (تنفيذ Terra انتهى في الشجرة غير مودَع: حذف الأوامر الأربعة و`reconcile_product_cogs` والحقل + `sales/0057` غير متتبَّعة؛ قرأتُ الفرق كاملاً، ملاحظاتي: docstring الحارس وجملتا `rebuild_fifo_layers.py`؛ المراجعتان ✅ بلا blocker ولا major؛ وثيقة الخطة محدّثة ✅؛ جولة تصليح Terra 1 ✅ (قُرئ الفرق)؛ الهجرات No changes ✅؛ sync_docs ✅؛ CHANGELOG بسطر `TBD` ✅؛ المراجعتان النهائيتان ✅ (nits فقط)؛ جولة تصليح Terra 2 ✅ (قُرئ الفرق)؛ الاختبارات المركّزة + test_docs_freshness ✅ (49 passed + فشل `test_production_code_has_one_source_of_today` البيئي المعروف من `.agents/worktrees`) و**البوّابة الكاملة جارية** ← قراءة فرق التصليح 2 + اختبارات الملفات الملموسة + test_docs_freshness ← البوّابة + الهجرات + sync_docs + CHANGELOG + الخطة ← **مودعة ومدفوعة `7ba297de`** (البوّابة 8119 passed + الستة البيئية + `test_shop_days_extension` قرب منتصف الليل #293، الهجرات No changes؛ #295 مغلقة)) ← **M5-2 جارٍ: المنفّذ انتهى (شجرة عمل غير مودَعة على `b902e88b`)، والمراجعتان Opus رجعتا بلا مانع؛ جولة التصليح 1 (Terra high) أُطلقت بموجز `briefs/M5-2-fix1.txt` (F1 ثوابت، F2 ميزانية الاستعلامات، F3 فحص D6، F4 إعادة كتابة اختبارَي المرتجع المختلط بسيناريو 6/3/4، F5 تنظيف، F6 وثائق) إلى `runs/M5-2-fix1`، فتوقّف صحيحاً عند خطأ حسابٍ في موجزي (الطبقات [3, 4] لا [4, 4])، فاستُكملت الجلسة نفسها بـ`briefs/M5-2-fix1b.txt` إلى `runs/M5-2-fix1b`؛ انتهت (red check `36.00 != 42`)، وقُرئ الفرق كاملاً ✅؛ الهجرات No changes ✅؛ المراجعتان النهائيتان: Spec CLEAN (2 nit)، Standards NEEDS-FIX (1 should-fix + 5 nit) — قُبلت كلها؛ جولة التصليح 2 (Terra) ✅ (قُرئ الفرق)؛ المراجعتان النهائيتان 2: NEEDS-FIX (S1–S3/S5/S6 وP1–P4، رُفضت S4)؛ جولة التصليح 3 (Sonnet high) ✅ (red check، 82 passed، قُرئ الفرق)؛ المراجعتان النهائيتان 3 (Opus) ✅ نظيفتان (رُفضت nit واحدة من كلٍّ منهما، وM1 يُصلحه `sync_docs`؛ لا جولة 4)؛ الهجرات No changes ✅؛ **التالي: sync_docs ← البوّابة الكاملة ← sync_docs ← CHANGELOG + الخطة §3.5 (D6 مقبول <0.01) ← إيداع ودفع** ← M5-3 ← M5-4 ← نشر الدفعة الثانية.
> - ▶ **M0 ✅ مودعة ومدفوعة `fb6094ad` (2026-11-21)** — البوّابة 8112 passed + الستة البيئية المعروفة، والهجرات No changes؛ الخطة وCHANGELOG محدّثان. لم تُنشر (تُنشر مع الدفعة الثانية بعد M5: نسخة احتياطية ثم `sync_avg_cost_from_layers` معاينة ثم `--apply`). **التالي:** قضيتا متابعة على GitHub (واجهة `InvoiceForm`/`ProductCostPage` على متوسط كل المشتريات؛ الأدوات القديمة الأربع — تحتاج قرار المالك لأنها تمسّ قيوداً مرحّلة)، وسؤال المالك عن حذف `SalesSettings.use_moving_average_cost`، ثم **M5 (AVCO)** بقارئ Terra (`gpt-6.1-terra` عبر codex-delegate، high).

> **حالة 2026-11-18 (بعد M1B-2 `1a06ee68`):** المنفّذ والقارئ الآن **Hydrogen عبر agy-delegate** (`gemini-4-hydrogen-high`، جهد high،
> `--dangerously-skip-permissions`؛ والقارئ `--read-only`). تصعيد جولات التصليح: 1–2 Hydrogen، 3 Sonnet high (`sonnet-implementer`)، 4 Opus high، ثم المالك.
> - ✅ **SEC-MANUAL-REF مودع محلياً `7a39d6e6`** (بلا push حتى M4). هاشه في CHANGELOG ما زال «_(غير مودع)_» ويُصحَّح مع إيداع M1B-3. `test_shop_days_extension` يفشل على الأصل أيضاً قرب منتصف الليل (تاريخ محلي/UTC) — بيئي.
> - 🔄 **M1B-3:** القارئان انتهيا (`runs/m1b3-reader/final.md` و`runs/m1b3-reader2/final.md`؛ الثاني فشل بمهلة 60 دقيقة لتعلّق `rg` واسع لكن
>   إجاباته كاملة). حقائق حاسمة: لا تقرير يفصل تكلفة المبيعات اليوم (مجمل الربح لـM1B-4)؛ تحويل `51` الورقة إلى أب يكسر
>   `resolve_default_account(allow_parent=False)` و`restore_defaults`. **قُسّم:** M1B-3a (إعدادات + تحقق + حساب افتراضي + سجلّ نشاط + `standard_cost`)
>   ثم M1B-3b (توجيه فرق الطبقة المؤقتة وحصة التكلفة الواصلة المباعة). موجز 3a: `briefs/M1B-3a.txt` (قراراته في progress.md 2026-11-19). ✅ M1B-3a نُفّذت (Hydrogen). المراجعتان Opus عادتا: lockout في `validate` (MAJOR)، حقلا الحساب غير مقيّدين بالشركة + مسار كتابة عابر للشركات عبر `default_cogs_account` (أمني)، فرع parent ميت، ازدواج منطق، `_resolved_tenant_id` ميت، T3/T4/T6/T11 ضعيفة. ⏸ **موقوفة مؤقتاً بطلب المالك («اعمل ايقاف وقف مؤقتا») 2026-11-19:** جولة التصليح 1 أُوقفت أثناء عملها، وتركت تعديلات **جزئية** في الشجرة (F2 حقل مقيّد، F4 `default_cost_variance_account_error`، F3 `parent = cogs_account.parent`، F5 حُذف `_resolved_tenant_id`؛ الباقي غير معروف). لا عملية agy باقية. عند الاستئناف: اقرأ `git diff 7a39d6e6 -- sales inventory docs` وقرّر: إكمال بموجز دلتا أو إعادة الجولة. ~~جولة تصليح 1 تعمل على Hydrogen~~ ← موجز `briefs/M1B-3a-fix1.txt` (F1–F7)، المخرَج `scratchpad/runs/m1b3a-fix1/` (مهمة خلفية؛ انتظر `result.json`). التالي: قراءة فرق التصليح ← مراجعتان نهائيتان على الحالة النهائية ← البوّابة المعزولة + الهجرات ← إيداع محلي مع تصحيح هاش SEC في CHANGELOG إلى `7a39d6e6`. ثم **SEC-SETTINGS-FK** (بلا سؤال): بقية حقول FK في `SalesSettingsSerializer` بـ`TenantScopedPrimaryKeyRelatedField` + `restore_defaults` بلا `require_perm("sales.settings.manage")` (وجده Standards؛ تحقّق قبل الموجز).
> - 🔄 **M1B-3b (بعد `22cd6579`، غير مودعة):** Hydrogen نفّذ (`scratchpad/runs/m1b3b/`، موجز `briefs/M1B-3b.txt`). الفرق مقروء كاملاً؛ ملاحظاتي F1–F6 في progress.md (أهمها: التقريب يعود لأصل كل موضع لأن D4 في موجزي كان خطأً). المراجعتان عادتا وقراراتي في progress.md. **الآن:** جولة تصليح 1 تعمل على Hydrogen (موجز `briefs/M1B-3b-fix1.txt`، المخرَج `runs/m1b3b-fix1/`، مهمة خلفية؛ انتظر `result.json`) ← قراءة الفرق ← مراجعة نهائية ← البوّابة المعزولة + الهجرات + `lint-imports` ← إيداع محلي (يملأ هاش M1B-3b في CHANGELOG لاحقاً) ← M1B-4.
> - 🔄 **2026-11-19 استؤنفت:** تعديلات جولة 1 (F1–F7) اكتملت كلها في الشجرة (71 passed). المراجعتان النهائيتان: Standards نظيف (MINOR: `restore_defaults` لا يعيد فحص حساب الفروقات بعد تعيين COGS ← يُضمّ لـSEC-SETTINGS-FK). Spec: **MAJOR** الواجهتان ترسلان `default_cogs_account` في كل حفظ فإصلاح F1 لا يحمي (تحقّقتُ: `frontend_v2/utils/salesSettingsPayload.ts` و`GroupConstantsPage.tsx`)؛ `avco` مقبول عبر API ويُرحَّل FIFO صامتاً (قراري: رفضه 400 حتى M5)؛ اختبار مسار «بلا حساب COGS»؛ T9 لا يفحص المستخدم. **جولة تصليح 2 تعمل على Hydrogen:** موجز `briefs/M1B-3a-fix2.txt` (G1 فحصٌ عند **تغيّر** حقل COGS فقط، G2 منع avco، G3، G4، G5 نيتس)، المخرَج `runs/m1b3a-fix2/`. بعدها: قراءة الفرق ← مراجعتان على الحالة النهائية ← البوّابة المعزولة (`gate.py`) + الهجرات ← إيداع محلي (تصحيح هاش SEC في CHANGELOG إلى `7a39d6e6`).
> - 🔄 **جولة 2 انتهت (Hydrogen):** G1–G5 في الشجرة، قرأتُ الفرق كاملاً وهو صحيح (75 passed؛ sales+inventory 1259 passed). بقي ثابت ميت `SalesSettingsSerializer._COGS_VALIDATION_FIELDS` ← يُضمّ لجولة 3 (Sonnet high حسب التصعيد). **مراجعتان Opus نهائيتان تعملان** على الحالة النهائية. بعدها: جولة 3 إن لزم ← البوّابة المعزولة + الهجرات ← إيداع محلي.
> - ✅ **M1B-3a مودعة محلياً `11d911b8`** (2026-11-19): مراجعتان نهائيتان نظيفتان، جولة 3 (Sonnet high) للنيتس، البوّابة المعزولة `1 failed (PaperAmountsPayloadTest، بيئي), 8065 passed`، الهجرات No changes. هاش SEC في CHANGELOG صُحّح إلى `7a39d6e6`؛ سطر M1B-3a في CHANGELOG ما زال «_(غير مودع)_» ← يُصحَّح إلى `11d911b8` في الإيداع التالي. لا push حتى M4. **التالي: SEC-SETTINGS-FK** (بلا سؤال): قارئ Hydrogen `--read-only` يتحقّق من حقول FK الباقية في `SalesSettingsSerializer` (`default_customer`، حسابات الإيراد/النقد/المخزون/الذمم، `default_vat_rate`، `vat_input_account`؛ العملة عامة فتُستثنى) و`restore_defaults` (صلاحية `sales.settings.manage` + إعادة فحص حساب الفروقات بعد تعيين COGS كي لا يتطابقا) ← موجز ← Hydrogen.
> - ✅ **SEC-SETTINGS-FK مودعة محلياً `22cd6579`** (2026-11-19): تنفيذ Hydrogen + جولتا تصليح Hydrogen + جولة 3 Sonnet high (اسم S7 وتعليقه). المراجعتان النهائيتان: Spec كل D1–D5 وS1–S8 مستوفاة؛ Standards بلا BLOCKER/MAJOR. البوّابة المعزولة `1 failed (PaperAmountsPayloadTest، بيئي), 8073 passed`، الهجرات No changes. هاش SEC في CHANGELOG صُحّح في الشجرة إلى `22cd6579` (غير مودع ← يُودَع مع M1B-3b). **مؤجّل لـM5:** قاعدة حساب الفروقات مكرّرة بين `SalesSettingsSerializer.validate/update` و`restore_defaults` ← توحيدها في helper بـ`sales/services/foundation.py` حين يدخل `avco`. لا push حتى M4.
> - 🔄 **M1B-3b يعمل على Hydrogen** (2026-11-19): قراراته D1–D5 في progress.md (التوجيه بلقطة كل حركة بيع؛ ثلاثة مواضع + المُعيدان؛ رفض صريح بلا حساب فروقات؛ عمود الواجهة مؤجّل لـM2). الموجز `scratchpad/briefs/M1B-3b.txt`، المخرَج `scratchpad/runs/m1b3b/` (مهمة خلفية؛ انتظر `result.json`). الأساس `22cd6579` ← الفرق `git diff 22cd6579 -- . ":!docs/agents/"`. بعدها: قراءة الفرق ← مراجعتان Opus ← جولات التصليح ← البوّابة المعزولة + الهجرات ← إيداع محلي (مع هاش SEC في CHANGELOG وسجلّات الإغلاق) ← تحديث §5 في الخطة.
> - 🔄 **M1B-3b جولة تصليح 1 انتهت (Hydrogen)** (2026-11-19): R1–R5 وF1–F11 وTF1–TF5 في الشجرة؛ قرأتُ الفرق كاملاً (الكود والاختبارات والوثائق) وهو مطابق. بوّابات المنفّذ: inventory 613، sales 666، logistics 823، accounting 456 passed؛ الهجرات No changes. **الآن:** مراجعتان Opus نهائيتان (Standards + Spec) على الحالة النهائية + البوّابة المعزولة `gate.py` تعمل بالخلفية ← جولة 2 (Hydrogen) إن لزم ← إيداع محلي.
> - 🔄 **M1B-3b جولة تصليح 2 تعمل (Hydrogen)** (2026-11-19): المراجعتان النهائيتان بلا blocker/major. المقبول: CHANGELOG ناقص (تخطّي reconcile_cogs + الباني العام)، صفّ `cogs_method.py` في inventory.md (الباني + عدد الأسطر 94)، جملة «فرقٌ صفريٌّ ⟵ لا قيد»، فرع اختبار ميت في `test_reconcile_syncs_only_fifo`، توحيد الثابت في الاختبارات، واختبار جديد TM1 لتقسيم S3 المختلط. المرفوض: نقل استيراد `_resolve_line_account` (قرار F5 محسوم). الموجز `briefs/M1B-3b-fix2.txt`. لا تغيير كود إنتاجي. ← قراءة الفرق ← مراجعة أخيرة ← إيداع محلي.
> - 🔄 **M1B-3b جولة تصليح 2 انتهت (Hydrogen، `runs/m1b3b-fix2b`؛ المحاولة الأولى فشلت بخطأ agy «empty conversation id» بلا أثر)** (2026-11-19): G1–G5 + TM1 في الشجرة، قرأتُ الفرق كاملاً: لا ملف إنتاجي تغيّر، وTM1 صحيح حسابياً (FIFO 60←72 +12، ثابت 52←48 −4 ← مدين ت.ب.م 12 / دائن الفروقات 4 / دائن المخزون 8) ورأيته أحمر مؤقتاً. الهجرات No changes؛ `.importlinter` فيه `inventory.cogs_method -> sales.models`. **الآن:** البوّابة المعزولة تعمل بالخلفية ← إيداع محلي `git add -u` ← M1B-4.
> - ✅ **M1B-3b مودع محلياً `2181947f`** (2026-11-19): البوّابة المعزولة 8086 passed / 1 failed بيئي معروف (`PaperAmountsPayloadTest`)، الهجرات No changes. بلا push حتى M4. **الآن:** M1B-4 — القارئ (Hydrogen `--read-only`، `briefs/M1B-4-reader.txt` ← `runs/m1b4-reader`) يعمل؛ بعده موجز التنفيذ. هاش M1B-3b في CHANGELOG مصحَّح في الشجرة ويدخل مع إيداع M1B-4.
> - **M1B-4 (2026-11-19):** القارئ انتهى (`runs/m1b4-reader.txt`)، والموجز كُتب (`briefs/M1B-4.txt`): (a) ربح `stock-by-dimension` على `cogs_cost` مع الرجوع لـ`total_cost`، (b) `account_period_net` جديد في `accounting/services.py` و`invoice_profits.totals` يكسب `cost_variance`/`gross_profit` (null مع فلتر العميل) + سطران في `InvoiceProfitsPage`، (c) حارس الخسارة على `method_unit_cost` لـstandard/last_purchase وإلا `avg_cost`. **الآن:** تنفيذ Hydrogen high في الخلفية (`runs/m1b4`). معاينة الخسارة في المحرّر نُقلت إلى M2.
> - **M1B-4 تنفيذ انتهى (2026-11-19):** Hydrogen high أنهى (a)(b)(c) + T1–T9 واختبار إضافي لـ`invoice_date=None` (اختار `localdate()`). قرأتُ الفرق كاملاً (14 ملفاً) ولا عائق. **الآن:** مراجعتا Standards/Spec (Opus) متوازيتان على `git diff 2181947f`، ثم التصليح إن لزم، ثم البوّابة والإيداع المحلي.
> - **M1B-4 مراجعة (2026-11-19):** Spec نظيف بلا عائق؛ Standards عائقٌ «major» واحد (معاينة الخسارة في `SalesInvoiceEditor.tsx`) رُفض لأنه قرارٌ محسوم نُقل إلى M2 ولا نشر قبل M4. قُبل: لوحة الفروقات بفئات `ktra-total-row` للوضع الداكن، اختبار عزل الشركة في `account_period_net` يسقط فعلاً + حدّ `date_from` + المسودّة بـ`_journal`، `Coalesce` في `_sale_movement_shares`، docstrings، `date=` لـ`_save_via_serializer`، نوع `int | None`، مرجع CHANGELOG. رُفض: N+1 (بنود قليلة)، فحوص زائدة غير ضارة. البوّابة الكاملة على حالة التنفيذ: 8096 نجح وفشل `PaperAmountsPayloadTest` البيئي وحده. **الآن:** جولة تصليح 1 (Hydrogen) في الخلفية (`runs/m1b4-fix1`).
> - **M1B-4 مراجعة نهائية (2026-11-19):** Spec مطابق بلا حاجب؛ Standards بلا حاجب، 4 minor + nits. المقبول (F8–F14): `mt-2 w-60 ms-auto` بدل الـstyle في `InvoiceProfitsPage`، تعليق `loss_invoice_policy` القديم، `effective_cogs_expression()` في `inventory/cogs_method.py` مصدراً واحداً، توقيع `account_period_net` في الوثيقة، حذف حارس مكرّر، رسالة الخسارة في الاختبارات + docstring T8، حالة بلا `SalesSettings`. **الآن:** جولة تصليح 2 Hydrogen (`runs/m1b4-fix2`، `briefs/M1B-4-fix2.txt`). **بعد M1B-4:** تذكرة LINT — عقد import-linter «inventory لا يستورد sales» مكسور بـ`inventory/tests/test_restore_origin_breakdown.py` (من 7cbb3704)، وCI يشغّل lint-imports، فيجب إصلاحه قبل push M4.
> - **M1B-4 ✅ `0ecc3eb3` (2026-11-19، محلي بلا push):** جولة تصليح 2 (Hydrogen high) طبّقت F8–F14؛ قرأتُ الفرق كاملاً. البوّابة المعزولة: 1 failed (PaperAmountsPayloadTest المعروف) + 8097 passed؛ الهجرات «No changes detected»؛ فحص مرئي (Playwright مؤقّت حُذف) بـ4 تركيبات skin×theme: الصندوق 240px على الحافّة اليسرى — رأيتُ الصور بعيني. **الآن:** تذكرة LINT-INV-SALES (`briefs/LINT-INV-SALES.txt`) قبل M3.
> - **LINT-INV-SALES (2026-11-19):** Hydrogen (المحاولة الأولى فشلت بخطأ backend «empty conversation id» قبل أي تعديل، والثانية نجحت). الاختبار نُقل بنصّه، و`lint-imports`: 3 kept. البوّابة المعزولة: PaperAmountsPayloadTest المعروف + `test_generated_blocks_are_current` (رقم inventory في ARCHITECTURE) ← شغّلتُ `sync_docs` فتغيّر رقمٌ واحد. **التالي:** M3.
> - **M3 أُرسل (2026-11-19):** موجز `briefs/M3.txt` إلى Hydrogen (out-dir `runs/m3-1`). القرارات: `SalesSettings.product_price_column` (5 خيارات، افتراض last_purchase)، حقلا المنتج `inventory_avg_cost` (طبقات مفتوحة مجمّعة) و`method_cost` (حسب طريقة الشركة، والسقوط إلى inventory_avg)، مساعدان في `inventory/cogs_method.py` بلا ignore جديد، قسم في `SalesSettingsPage`، و`utils/productPriceColumn.ts`، وtestids جديدة في e2e. **التالي:** قراءة الفرق ثم مراجعتان.
> - **M3 (2026-11-19):** تنفيذ Hydrogen (run m3-1) انتهى؛ قرأتُ الفرق كاملاً (`scratchpad/m3.diff` من `bb0ecc27`). **الآن:** مراجعتا Opus (Standards/Spec) تعملان ← تقاريرهما `scratchpad/review-m3-*.md`، ثم تصليح 1 (Hydrogen) ← بوّابة معزولة ← فحص مرئي ← commit محلي.
> - **M3 مراجعتان (2026-11-19):** Standards: قُبل F1/F3/F4/F5 جزئياً/F6/F7/F8/F9/F11 جزئياً، ورُفض F2/F10. Spec: قُبل F1 (تقريب المتوسّط ← `fifo.derived_avg_costs` مصدراً واحداً) وF2–F5، ورُفض F6. البوّابة المعزولة قبل التصليح: 1 failed معروف + 8105 passed. **الآن:** تصليح 1 (Hydrogen) بموجز `scratchpad/briefs/M3-fix1.txt` ← قراءة الفرق ← مراجعة نهائية ← بوّابة ← فحص مرئي ← commit محلي.
> - **M3 تصليح 1 (2026-11-19):** Hydrogen (run m3-fix1) طبّق البنود 1–7؛ قرأتُ الفرق كاملاً (`scratchpad/m3-fix1.diff`) ونظيف (ملاحظة صغيرة مقبولة: import محلي لـ`Q4` في `get_method_cost`). سطور `cogs_method.py` = 142 مطابقة. الهجرات «No changes detected»، و`lint-imports` 3 kept. **الآن:** مراجعتا Opus النهائيتان على `scratchpad/m3-final.diff` + البوّابة المعزولة في الخلفية ← فحص frontend/e2e ← فحص مرئي ← commit محلي.
> - **M3 مراجعة نهائية (2026-11-19):** Spec: 3 ملاحظات وثائق قديمة (فقرة الطباعة وبند `buildFamilyRow` في inventory.md، وحالة inventory_avg في frontend.md) قُبلت كلها. Standards: قُبل F1 (تأكيد موجب في اختبار unscoped) وF2 (Q4 إلى مستوى الوحدة) ورُفض F3؛ وقُبل تصحيح عدد سطور `inventory/serializers.py` في جدول inventory.md. **الآن:** تصليح 2 (Hydrogen، `briefs/M3-fix2.txt`، run m3-fix2) + البوّابة المعزولة جارية ← قراءة الفرق ← frontend/e2e ← فحص مرئي ← commit محلي.
> - **M3 تصليح 2 (2026-11-19):** Hydrogen (run m3-fix2) طبّق البنود 1–5؛ قرأتُ الفرق (`scratchpad/m3-fix2-delta.txt`) ونظيف: تأكيد "10.0000" وmethod_cost غير None (أحمر عند إرجاع tenant=None)، `Q4` إلى مستوى الوحدة، والوثائق الثلاث. الهجرات «No changes detected»، و`lint-imports` 3 kept. فشل docs-freshness المحلي سببه ملفات المالك في `.agents/worktrees` فقط (لا تُمسّ). **الآن:** البوّابة المعزولة + frontend جاريان ← Playwright ← فحص مرئي ← commit محلي.
> - **M3 مكتمل (2026-11-20):** البوّابة المعزولة 8107 passed (فشل `PaperAmounts` المعروف وحده)، الهجرات بلا تغيير، lint 3 kept، tsc OK وnpm test 1441 وbuild OK، Playwright `items-purchase-prices` 5 passed. الفحص المرئي (16 لقطة، modern/classic × light/dark): رأس «متوسط تكلفة المخزون» والرقم 32 والتفاصيل الأربعة، وقسم الإعداد بقيمة «التكلفة حسب الطريقة المختارة» — سليمة كلها. أُودع محلياً (بلا push حتى M4). **الآن:** M2 (واجهة الإعدادات) — الاستكشاف ثم الموجز.
> - **M2 بدأ (2026-11-20):** القارئ Hydrogen (`--read-only`) يعمل في الخلفية: الموجز `scratchpad/briefs/M2-reader.txt`، المخرَج `scratchpad/runs/m2-read/result.json`. **الآن:** انتظار القارئ ← موجز M2 (`briefs/M2.txt`) ← تنفيذ Hydrogen.
> - **M2 تنفيذ (2026-11-20):** القارئ انتهى (`scratchpad/runs/m2-reader.txt`). القرارات المحسومة في الموجز `scratchpad/briefs/M2.txt` (قسم `cogs-cost-method` بلا avco وجدول مثال §4 محسوب، حساب الفروقات بلا allowParents، تأكيد danger:false، صف الفروقات في خريطة القيد، `standard_cost` في ItemForm، حقل `cogs_method_unit_cost` في `ProductLookupSerializer` يطابق `_loss_lines` بلا fallback، و`expectedUnitCost`/`missingMethodCost` في salesInvoiceMath للحارس والمعاينة). Hydrogen يعمل: `scratchpad/runs/m2/result.json`. **الآن:** انتظار التنفيذ ← قراءة الفرق كاملاً ← مراجعتا Opus ← البوّابات ← فحص مرئي ← commit محلي.
> - **M2 نُفّذ (2026-11-20):** Hydrogen انتهى بمهلة 90د وهو ينتظر 4 اختبارات حراسة تمسح `.agents/worktrees` (بيئي معروف، لهذا `gate.py`). قرأتُ الفرق كله (`scratchpad/m2.diff`): ملاحظة واحدة مؤكّدة — inline style في `ItemForm.tsx` (تلميح السعر الثابت)، وتعليق قديم فوق `lossOffenders`. **الآن:** البوّابة المعزولة + مراجعتا Opus متوازيتان ← موجز تصليح جولة 1 (Hydrogen) يجمع الملاحظات.
> - **M2 مراجعة جولة 1 (2026-11-20):** Standards = CHANGES REQUESTED، Spec = PASS بملاحظات صغيرة (`scratchpad/reviews/M2-*-r1.md`). البوّابة المعزولة على حالة ما قبل التصليح: 8111 نجاح، فشل واحد معروف مسبقاً (`PaperAmountsPayloadTest`). المقبول (8): `ktra-hint` بدل inline في `ItemForm.tsx`، `ktra-row--sel` لصف المثال المختار، تعليقان قديمان، المرتجع يبقى بالمعاينة القديمة (`!isReturn`)، stub الـe2e يرفض avco ويُنشئ 5190 لـstandard/last_purchase فقط، اختبار سيناريو ثانٍ لـ`computeCogsExampleRows`، حذف `else` الميت، عنوان فقرة frontend.md. **الآن:** موجز `briefs/M2-fix1.txt` عند Hydrogen (`runs/m2-fix1`) ← قراءة الفرق ← مراجعتا Opus على الحالة النهائية ← البوّابات ← commit محلي.
> - **M2 تصليح 1 مكتمل ومقروء (2026-11-20):** الثمانية مطبّقة كما الموجز (`scratchpad/m2-final.diff`)؛ Hydrogen: product_api 65، frontend 1448، e2e 1 passed. الهجرات No changes، lint 3 kept. **الآن:** مراجعتا Opus نهائيتان (`reviews/M2-*-r2.md`) + البوّابة المعزولة + frontend ← e2e ← الفحص البصري ← commit.
> - **M2 مراجعة r2 (2026-11-20):** Spec PASS، Standards 6 minor/6 nit (`reviews/M2-*-r2.md`). المقبول: S1 (حساب الفروقات يظهر `#5190` بعد الإنشاء التلقائي — خطأ حقيقي) وS2–S11 وSpec F3/F6؛ المرفوض F1/F2/F4/F5. **الآن:** تصليح 2 بـHydrogen (`briefs/M2-fix2.txt`، `runs/m2-fix2`) ← قراءة الفرق ← مراجعتان على الحالة النهائية ← البوّابات ← البصري ← commit.
> - **M2 تصليح 2 مكتمل ومقروء (2026-11-20):** الـ11 مطبّقة كما الموجز (`scratchpad/m2-fix2-interdiff.diff`)؛ Hydrogen: product_api 65، frontend 1450، e2e 1 passed، والـe2e رُئي أحمر على `#5190` قبل الإصلاح. ملاحظتي: `COGS_METHOD_LAST_PURCHASE` صار import غير مستعمل في `inventory/serializers.py`. **الآن:** مراجعتا Opus r3 على الحالة النهائية (`reviews/M2-*-r3.md`) + البوّابة المعزولة ← تصليح 3 (Sonnet) إن لزم ← البصري ← commit.
> - **M2 مراجعة r3 (2026-11-20):** Spec PASS، Standards طلب تغييرات (`reviews/M2-*-r3.md`). البوّابة المعزولة على حالة تصليح 2: 8111 ناجحاً + الفشل القديم المعروف وحده. المقبول: M1 (`cogs_method_unit_cost` على المنتقي وحده فيضيع بعد حفظ المنتج من الفاتورة وفي المنتجات الموقوفة — القرار: نقله إلى `ProductSerializer`)، m1، m2، m3 (`lineExpectedUnitCost` واستعادة تكلفة الخدمات قبل M2)، m4/F3 (nature والرمز القصير في الـstub)، الاستيراد غير المستعمل، ونِتّات. المرفوض: F2 (تقدير مقصود)، F1 مؤجَّل كمتابعة (المنتقي يحسب آخر شراء بتاريخ اليوم لا تاريخ الفاتورة)، تكرار فحوص estimateInvoiceCogs. **الآن:** تصليح 3 بـSonnet high (`briefs/M2-fix3.txt`) ← قراءة الفرق ← مراجعتان على الحالة النهائية ← البوّابات ← البصري ← commit.
> - **M2 تصليح 3 (2026-11-20، Sonnet high):** انتهى؛ السبعة مطبَّقة وقرأتُ الفرق البيني (`m2-interdiff-r4.diff`) سطراً بسطر. ملاحظة صغيرة مؤجَّلة لجولة 4 إن وُجدت: رسالة البادئة في stub الـe2e تستعمل `cogsAcc.code.slice(0,2)` بدل `cogsCode.slice(0,2)`. **الآن:** مراجعتا Opus r4 على الحالة النهائية (`m2-full-r4.diff` → `reviews/M2-*-r4.md`) + البوّابة المعزولة ← e2e ← البصري ← commit.
> - **M2 مراجعة r4 (2026-11-20):** Spec نجاح (ملاحظات ترتيب المعاينة/سطر LOC/الشريط مرفوضة: الترتيب قرار الموجز والمبالغ متطابقة، وLOC مولَّد، والشريط يصحّ عند التسليم أيضاً). Standards طلب تغييرات كلها في stub الـe2e (المسار الافتراضي بلا 400، واسم الحساب المُنشأ يجب «فروقات أسعار البضاعة المباعة»، وشرط التخطّي، ورسالة pk مجهول، وفحص الطريقة، و`cogsCode`) + `?? 0` في `lineExpectedUnitCost` — كلها مقبولة. بوّابة: فشل docs-freshness كان `AUTO:apps_table` متقادماً في النسخة (عدّ أسطر inventory)؛ `sync_docs` أصلحه في المستودع و`--check` نظيف. tsc/npm 1451/build خضر. **الآن:** جولة 4 (Opus high، `briefs/M2-fix4.txt`) ← قراءة فرقها ← مراجعة r5 ← البوّابة ← e2e ← البصري ← commit.
> - **M2 جولة 4 (2026-11-20، Opus high):** stub الـPATCH صار مرآة `SalesSettingsSerializer` (`_cogs_settings_changed`، `validate`، `update`) و`foundation.py` (`cost_variance_account_error`، `_inspect_default_cost_variance_account`): مرحلة حقول (pk مجهول برسالة DRF العربية، `invalid_choice`، avco)، ثم التحقّق عند تغيّر إعدادات التكلفة فقط، والمسار الافتراضي بأخطائه الحقيقية، والحساب المُنشأ «فروقات أسعار البضاعة المباعة». `?? 0` في `lineExpectedUnitCost`. قرأتُ الفرق كاملاً مقابل الكود الحقيقي ورسائل DRF تحقّقتُ منها تشغيلاً. البوّابة المعزولة قبلها: 1 فشل معروف، 8112 نجاح. **الآن:** مراجعة r5 (Opus×2، `m2-full-r5.diff`) ← بوّابات الواجهة ← e2e ← البصري ← commit.
> - **M2 مراجعة r5 (2026-11-20، Opus×2):** كلاهما PASS بلا حاجب ولا major. Spec: minor منتقي حساب الفروقات لا يقصر الخيارات على مجموعة ت.ب.م (الخادم يرفض بـ400، لا ضرر دفتري) + nit `avco` مخزَّن خارج الـAPI يمنع الحفظ. Standards: minor الـstub يقبل pk مجهولاً لحسابات الإيراد/الذمم/النقد (401، 402، 101، 104، 102، 105 خارج `STUB_ACCOUNTS`) + nit رسائل NaN/null + nit تكرار قاعدة التكلفة في `estimateInvoiceCogs` (وقصّ `Math.max(0)`). الجولة 4 كانت الأخيرة المسموحة، فالقرار للمالك: جولة 5 أم تأجيلها متابعات. **الآن:** الفحص البصري (Hydrogen، `runs/M2-visual`) يعمل ← رؤية اللقطات ← سؤال المالك ← commit.
> - **M2 فحص بصري (2026-11-20، Hydrogen + عيني):** 4/4 Playwright، 28 لقطة (كلاسيك/حديث × فاتح/داكن). رأيتُ: بطاقة الإعدادات (المنتقي + 5190 + جدول المثال 112/110/160 بفروقات مدين 2/دائن 48)، تلميح السعر الثابت في المنتج، وقيد معاينة الفاتورة متوازن 99=99 بسطر فروقات 4 مدين، وتنبيه `cogs-method-missing-cost` في الداكن. لا خلل تخطيط ولا تباين. **الآن:** سؤال المالك: جولة 5 (Opus high) لثغرة الـstub، أم تأجيل الملاحظات متابعات ثم commit M2 محلياً.
> - **M2 جولة تصليح 5 (2026-11-20، بقرار المالك صراحةً، Opus high وكيل فرعي):** الموجز `briefs/M2-fix5.txt`: فحص وجود كل FK في PATCH stub (إضافة الحسابات 401/402/101/102/104/105) + رسائل DRF لـ`incorrect_type` و`null`. المؤجَّل متابعاتٍ: منتقي الفروقات لا يقصر على مجموعة ت.ب.م (Spec minor)، وتكرار قاعدة التكلفة في `estimateInvoiceCogs`، و`avco` المخزَّن. **انتهت الجولة 5** (tsc 0، npm 1451/0، e2e 1 passed؛ انحراف: حسابات أصل مجموعة 100/400، ومسارات currencies/partners/tax-rates تطابق `SalesSettingsPage.tsx`). قرأتُ الفرق. مراجعتا r6 على الحالة النهائية: Standards PASS وSpec PASS (0 blocker/major). أصلحتُ بنفسي Spec F3 (وثائق: `ProductSerializer` ومنه `ProductLookupSerializer`). متابعات مؤجَّلة تُضاف لما سبق: تلميح الإنشاء التلقائي في الإعدادات يَعِد بما قد يرفضه الخادم (Spec F1)، والـstub يردّد الجسم الخام ولا يفحص حقول الاختيار الأخرى (Standards minor)، و`round2`/سقوط avg_cost مكرّران، وحقل `standard_cost` بلا اختبار. البوّابات كلها خضراء: backend المعزولة 8112 passed + فشل `PaperAmountsPayloadTest` المعروف وحده، الهجرات No changes، lint 3 kept، tsc 0، npm 0 fail، build OK، e2e 1 passed، `sync_docs` OK.
> - ✅ **M2 مودع محلياً `c16446ad` (2026-11-20، بلا push حتى M4).** M4 (2026-11-20): e2e الجدول والإعدادات 6 passed؛ حدّثتُ حالةً قديمة في الخطة (M1A كانت «غير مودعة» وهي `4e9a4e38`، و§7)، و`sync_docs --check` طازج. وافق المالك على push + النشر.
> - ✅ **M4 منشور (2026-11-20):** push `d6e4feaa`؛ CI: frontend وpwa أخضران وbackend فشلٌ واحد سابق مرتبط بالتاريخ (`test_shop_days_extension`، يفشل على الأصل `ab92c5df`، القضية #293). الخادم: دمج في `modern` `916f51b1` (HEAD السابق في `/root/backups/pre-merge-head-20261120.txt`)، نسخة `ktra-before-cogs-batch1-20261120-211540.sql` (28.7MB)، الهجرات الخمس OK، collectstatic وbuild وrsync باستثناء `dl` (2 قبل/بعد)، `ktra.service` active وصحّة 200. تغييرات المالك غير المودعة على الخادم (`hr/auth_api.py`/`hr/urls.py` magic-login) لم تُلمس. القرص 97%.
> - **الآن:** M0 ← M5 (AVCO) ← نشر الدفعة الثانية. قارئ M0 انتهى (`runs/M0-reader/final.txt`، ادعاءاته متحقَّقة). **القرار (في progress.md):** حذف `apply_purchase_cost_model`/`set_avg_cost_from_purchases` ومواضعها التسعة، `avg_cost` = متوسط الطبقات المفتوحة وحده، قيد الجرد بتكلفة الحركة، أمر `sync_avg_cost_from_layers` بدل هجرة بيانات، والعلم `use_moving_average_cost` يبقى (حذفه بإذن المالك). القيود المرحَّلة لا تتغيّر. **يعمل الآن:** منفّذ Hydrogen في الخلفية (`briefs/M0-impl.txt` ← `runs/M0-impl/`) ← قراءة الفرق ← مراجعتا Opus ← البوّابات ← commit + push. **إن انقطع التشغيل (حدّ Hydrogen أو فشل agy):** الشجرة فيها تعديلاته الجزئية غير المودعة (~18 ملفاً: `inventory/services.py`، `logistics/*`، الاختبارات، الوثائق) — لا تُرمى. افحص `runs/M0-impl/result.json` و`agy.log`، ثم `git diff --stat`، ثم موجز استئناف مكمّل (`--resume-last` أو جلسة جديدة بـ«أكمل M0 من الشجرة الحالية» + الموجز نفسه). آخر حالة معروفة (2026-11-21 00:05 محلي): المنفّذ يشغّل البوّابة الكاملة، لا أخطاء حدّ في السجلّ. المالك: «اذا وصل الحد سجل وين وصلنا… وبنكمل بعدين».


**المالك طلب:** تحديث التسليم والتقدّم **بعد كل خطوة** (قبل أي كومباكت).

- **سير العمل:** `CLAUDE.md` الجديد (commit `492d68c9`): أنا المنسّق لا أكتب كوداً. بطاقة المشروع في رأس
  `docs/decisions/cogs_cost_methods.md`: القارئ والمنفّذ `gpt-6.1-terra` بجهد high عبر `codex-delegate`
  (relay: `node ~/.claude/skills/codex-delegate/scripts/relay.mjs --brief <f> --cd D:/Users/asus/Desktop/ktra
  --model gpt-6.1-terra --effort high`، والقارئ `--read-only`)، والمراجعان وكيلان فرعيان Opus بمهارة `code-review`.
- **ترتيب التذاكر:** M1A (إيداع) ← M1B-1 ← M1B-2 ← M1B-3 ← M1B-4 ← M3 ← M2 ← M4 (نشر الدفعة 1 **بإذن المالك
  ونسخة احتياطية**) ← M0 ← M5 (AVCO).
- **البوّابة الكاملة معزولة:** المستودع فيه 39 worktree متداخلة تحت `.agents/worktrees/` تُعلّق الحرّاس. السكربت
  `%TEMP%/claude/88386ed35da8e742/b7e464bd-fe83-4f20-9269-9e325458afe2/scratchpad/gate.py` ينسخ الشجرة (متتبَّع +
  غير متجاهَل، بلا `marketing/` وملفات المالك الشاردة) إلى `%TEMP%/ktra-gate-copy` ويشغّل `pytest -q -n auto` هناك؛
  السجلّ `gate-last.log` بجانبه. يُعاد إنشاؤه من هذا الوصف إن ضاع.
- **لا push:** الرفع يحمل `13da894b` (عرض أسعار الشراء) الذي اشترط المالك قبله نسخةً احتياطية وعرض التغييرات.
  كل الإيداعات محلية حتى M4.
- ✅ **M1A مودعة** `4e9a4e38` (محلياً). البوّابة المعزولة: 7982 passed، وفشل واحد `PaperAmountsPayloadTest`
  بيئيّ (execnet تحت xdist؛ يمرّ منفرداً 7 passed، ومثبت على HEAD سابقاً).
- ✅ **Codex CLI حُدِّث** إلى `0.170.0` بإذن المالك (كان 0.154.0 فرفض `gpt-6.1-terra` بـmodel_not_found، والتشغيل
  r1 فشل بلا أي تعديل).
- ⛔ **M1B-1 r2 فشل بلا أي تعديل:** `windows sandbox failed: helper_unknown_error: setup refresh had errors`. السبب
  (من `~/.codex/.sandbox/sandbox.2026-11-18.log`): الـCLI 0.170 يختار وضع `elevated` (من `[windows] sandbox =
  "elevated"` في `~/.codex/config.toml`) فيحاول إضافة ACE على مجلد المستودع ويُرفض (WRITE_DAC، Access denied).
  التطبيق المكتبي والـCLI القديم كانا يستعملان `mxc`. **مُجرَّب:** `codex exec -s workspace-write -c
  'windows.sandbox="mxc"'` يكتب في المستودع ويشغّل Python/Django. الحل المقترح على المالك: تغيير السطر إلى
  `sandbox = "mxc"` (الـrelay لا يمرّر `-c`). ✅ **المالك وافق وغُيّر السطر.**
- ✅ **M1B-1 r3 انتهى** (17 دقيقة، `threadId 01a1eded-28e6-7263-a216-0aa138cfd673` للتصليح بـ`--session`). عدّل
  `inventory/fifo.py` و`inventory/services.py` و`sales/services/{calc,flow,pricing}.py` والوثائق، وأضاف
  `sales/tests/test_cogs_variance_journal.py` و`inventory/tests/test_restore_origin_breakdown.py`. نتيجته:
  `sales+after_sales+cogs report` ← 1 failed / 1286 passed. الفشل الوحيد `test_telescoping_returns`: **خطأ حسابي
  في موجزي** (توقّعتُ 33.33/33.33/33.34، والمعادلة المحسومة تعطي 33.33/33.34/33.33). **القرار: المعادلة تغلب،
  يُصحَّح توقّع الاختبار.**
- 🔄 **قرأتُ الفرق كاملاً.** ملاحظاتي للتصليح: توقّع telescoping؛ استيرادان غير مستعملين في الاختبار (`fifo`،
  `SalesInvoiceLine`)؛ `lambda` مسندة وأسطر طويلة في كتلة `RETURN_IN` في `inventory/services.py`؛ `docs/modules/sales.md`
  حذف سبب «الوسيط إلزامي بلا احتياط إلى avg_cost» وذكر `create_standalone_delivery_note`.
- ✅ **المراجعتان انتهتا بلا مانع** (Spec تحقّقت بالتشغيل من قيود 52/44/8 و52/12/64 ومن تطابق القيد اليوم). المقبول كله في
  `scratchpad/briefs/M1B-1-fix1.txt`. أبرز قراراته: ثابت `FIXED_COGS_METHODS` ودالّة `_cumulative_cogs` بدل lambda، واستعلام
  مجمَّع واحد قبل الحلقة، وفرق التقريب من الأصول الثابتة وحدها، و`cogs_method` = الطريقة المشتركة فقط إن حملت كل الأصول لقطة
  ثابتة، و`StockMovement.effective_cogs`، وتحديث تعليق الموديل، واختبارات (fifo بلقطة 112، ومنتجان يتعادل فرقاهما، وفحص
  `cogs_by_product` في مسار التسليم بـ`patch(wraps=)`)، وإعادة سبب الوسيط الإلزامي إلى `sales.md`. أما `create_standalone_delivery_note`
  فيبقى عمداً على `total_cost` لأنه ينقل القيمة إلى حساب وسيط وليس قيد COGS. **⚠ يجب فحصه في M1B-2/M1B-3: هل الفاتورة اللاحقة
  تنقل من الحساب الوسيط إلى COGS بلقطة الطريقة؟**
- ✅ **M1B-1 fix1 انتهى** (27 دقيقة): 33 passed مركّزة، وsales+after_sales+cogs report ← 1291 passed. `inventory/tests -n auto` توقّف
  عند 97% عنده (بيئي محتمل، والبوّابة المعزولة تحكم). قرأتُ الفرق كاملاً وهو نظيف.
- ✅ **fix2 انتهى** (7 دقائق)، وقرأتُ الفرق وتحقّقتُ يدوياً من 54 و75 و1.50. المراجعتان النهائيتان على الحالة النهائية: **Spec ← PASS،
  Standards ← بلا مانع** (فقط تعليقات قديمة). البوّابة المعزولة بعد fix2: **7999 passed** + البيئي وحده. وmakemigrations ← No changes.
- ✅ **fix3 انتهى** (تعليقات وأسماء)، والبوّابة الأخيرة 7999 passed + البيئي وحده. **M1B-1 مودعة محلياً** (انظر `git log -1`). قرار: يبقى
  فحص حساب الفروقات لكل منتج (الأصرم).
- ▶ **التالي مباشرةً: M1B-R.** الموجز جاهز في `scratchpad/briefs/M1B-R.txt` (نموذج `StockLayerRestoration` وهجرة 0047، و`restore_partial(restored_by=)`،
  والعكس في `reverse_stock_movements` بحارس، والمرتجعات القديمة بلا أثر تبقى كاليوم، واختبارات a–g). الحقائق في `runs/R-M1B-R-facts/final.txt`.
  ✅ **M1B-R r1 انتهى** (8 دقائق، threadId `01a1ee3a-c1fe-7831-bd2a-16c81cb58c02`). أضاف `StockLayerRestoration` وهجرة `0047_stocklayerrestoration`،
  و`restore_partial(restored_by=)`، و`_undo_layer_restorations` الذي يُستدعى أول `reverse_stock_movements`، والاختبارات في
  `sales/tests/test_sale_return_unpost_layers.py` (a–g). النتائج: 35 passed مركّزة، و1293 passed للمبيعات، وmakemigrations بلا تغيير. قرأتُ الفرق،
  وملاحظتي الوحيدة: النموذج غير مدرج في جدول النماذج في `inventory.md`. ✅ البوّابة المعزولة: 8006 passed + البيئي وحده.
  ✅ **المراجعتان:** Standards ← major سباق (قراءة صفوف الاستعادة بلا قفل) وminors. Spec ← **FAIL** بـmajor: إلغاء مرتجعين بترتيب ترحيلهما
  يقلب ترتيب صفوف الاستهلاك (5@10/3@16/2@20، R1=2 ثم R2=3، إلغاء R1 ثم R2 ← إعادة ترحيل R1 = 32 بدل 40). **القرار:** حارس LIFO (لا يُلغى
  مرتجع وفوقه مرتجع لاحق أعاد من حركة الصرف نفسها)، وقفل الاستعادات أولاً بترتيب استعادات ← استهلاك ← طبقات، وجلب مسبق بلا استعلامات في الحلقة،
  واختبار h للسيناريو. الحارس القديم لكل طبقة دفاعٌ إضافي فقط لأن `find_stock_dependents` يسبقه. **متابعة مقترحة للمالك لاحقاً:** منع إلغاء فاتورة
  البيع الأصلية ومرتجعها قائم (CASCADE يمحو الأثر)، وهو عيب سابق.
  ✅ **fix1 (من 3) انتهى** (13 دقيقة، threadId `01a1eeca-e770-7201-8e06-5cb2158b9393`): حارس LIFO، وقفل استعادات ← استهلاك ← طبقات، وجلب مسبق،
  واختبارا h وi، وتشديد c/e/f، والوثائق. نتيجته: 37 passed مركّزة، و1295 passed لـsales+after_sales، وmakemigrations نظيف. قرأتُ الفرق كاملاً
  (الكود والاختبار) فوجدته مطابقاً للموجز.
  ✅ **بعد fix1:** البوّابة المعزولة 8008 passed + `PaperAmountsPayloadTest` البيئي، وmakemigrations نظيف. Standards ← لا blocker ولا major
  (minors: قفل Product عبر select_related، و`later` قراءة بلا قفل). Spec ← **MAJOR تحقّقتُ منه بالتشغيل:** حارس LIFO يطابق `origin_movement_id`
  وحده، وفاتورة بسطرين للمنتج نفسه تعطي حركتَي أصل فيُتجاوز (إعادة ترحيل R1 بـ32 بدل 40).
  🔄 **الآن: fix2 (الجولة 2 من 3) يعمل** بموجز `scratchpad/briefs/M1B-R-fix2.txt` ← `runs/M1B-R-fix2`: نطاق الحارس = مستند الأصل + المنتج
  (reference_type, reference_id, product_id)، وترتيب القفل products ← restorations ← consumptions ← layers، و`of=('self',)`، و`later` بقفل،
  واختبار j (أحمر أولاً) وk، وإعادة تسمية i، واستيرادات h، ولفّ FKs، والوثائق.
  ✅ **fix2 انتهى** (8 دقائق، threadId `01a1eee3-b66f-7c51-962c-4d42c02ec474`): j أحمر (`200 == 400`) ثم أخضر، وk أخضر قبل وبعد،
  و1297 passed لـsales+after_sales، وmakemigrations نظيف. SALE+STOCK_ISSUE لفاتورة واحدة ممكن على مستوى الخدمة (`issue_stock_from_invoice`)
  لكن لا مستدعي له، فلم يُوسَّع. قرأتُ الفرق كاملاً فوجدته مطابقاً. ملاحظة لي: `later` بـselect_for_update مع joins قد يقفل صفوف stock_movements.
  مراجعة Standards بعد fix2: **FAIL بـMAJOR واحد مقبول**: `later` يُقفَل بعد الطبقات وبلا `of=('self',)` فيقفل صفوف stock_movements
  المنضمّة ويقلب ترتيب الأقفال. وminor: الوثيقة لا تطابق الترتيب. وnit: label يُبنى لكل صفّ. ورفضتُ nit تسمية i لأنها قرار fix2.
  البوّابة المعزولة بعد fix2: 8010 passed + البيئي وحده. موجز fix3 جاهز: `scratchpad/briefs/M1B-R-fix3.txt`.
  مراجعة Spec بعد fix2: **PASS** (9 سيناريوهات إضافية خضراء)، وملاحظتها الوحيدة nit = نفس قفل `later` المشمول في fix3.
  ✅ **fix3 انتهى** (6 دقائق، threadId `01a1eef5-21f9-7e30-9fa8-c682dddfdb2b`): `later` نُقل بعد الاستعادات بـ`of=('self',)`
  والحارس قبل الاستهلاكات/الطبقات، وlabel عند الرفع فقط، والوثائق مطابقة. 39 + 1297 passed، makemigrations نظيف. قرأتُ الدالة كاملةً فوجدتها مطابقة.
  Standards النهائية بعد fix3: **PASS** (بلا blocker/major). تُسجَّل ولا تُكرَّر (بعد الجولة 2):
  minor1 قفل `later` يأخذ gap lock على مستوى الشركة فيؤخّر ترحيل مرتجعات أخرى حتى الإيداع (الترتيب مضمون أصلاً بقفل المنتج والفاتورة
  `_lock_invoices_with_linked_originals`)؛ minor2 ترتيب قفل المنتجات بين الترحيل والإلغاء مختلف (deadlock 1213 ممكن ويُكتشف، موجود أصلاً
  بين الترحيلات)؛ nits: CASCADE «متابعة لاحقة» بلا قضية، «أولاً» في docstring `reverse_stock_movements`، والوثيقة لا تسمّي قفل الفاتورة.
  Spec النهائية بعد fix3: **PASS** (nits: اختبار j لا يؤكّد عودة الطبقات للصفر، وتعليق النموذج يقول «حذف» لا «إلغاء ترحيل»).
  البوّابة المعزولة بعد fix3: 1 failed (البيئي `PaperAmountsPayloadTest` وحده)، **8010 passed**، 1080s؛ makemigrations: No changes detected.
  ✅ **M1B-R مودعة محلياً (بلا push)** — الالتزام `3cbbc396`. ▶ **M1B-2 جارية:** القارئ انتهى (`scratchpad/runs/R-M1B-2-facts/final.txt`). الموجز `briefs/M1B-2.txt` كُتب، التشغيل الأول (`runs/M1B-2/`) توقّف حذراً عند تأكيد `cogs_cost is None` في `sales/tests/test_cogs_cost_methods.py` — حركته MANUAL خارج النطاق فالتأكيد صحيح ويبقى؛ ترك اختبارات جزئية في `sales/tests/test_cogs_method_snapshot.py`. ▶ التشغيل الثاني بموجز `briefs/M1B-2b.txt` (توضيح + الموجز نفسه) ← `scratchpad/runs/M1B-2b/` (مهمة خلفية؛ انتظر `result.json`). قرارات الموجز: وحدة `inventory/cogs_method.py` (`method_unit_cost` للمعاينة + `apply_sale_cogs_snapshot`) تُستدعى داخل `record_stock_movement` لـ OUT بـ SALE/STOCK_ISSUE؛ مزامنة `cogs_cost` لحركات fifo عند إعادة كتابة `total_cost`؛ تنبيه الغياب `cogs_warnings` في ردّ ترحيل الفاتورة؛ معاينة الواجهة مؤجّلة لـ M1B-4. ✅ التشغيل الثاني اكتمل (13 ملفاً +69/−13 + وحدة واختبار جديدان؛ تقريره `runs/M1B-2b/final.txt`)، وقرأتُ الفرق كاملاً: ملاحظتي الذاتية سطر CHANGELOG فوق الكتلة لا صفّاً في الجدول. ▶ مراجعتان Opus (Standards/Spec) جاريتان على `3cbbc396`. فجوة معروفة: ردّ التسليم بلا `cogs_warnings`. ✅ المراجعتان رجعتا بلا blocker: Standards ← majorان (صفّ CHANGELOG، وفقرة ARCHITECTURE «M1A تخزينٌ فقط» صارت كاذبة) وminors؛ Spec ← minors/nits فقط. **الحكم:** قُبل كلّه في `briefs/M1B-2-fix1.txt` (F1–F10: الوثائق، دالّة `sync_fifo_snapshot` و`is_sale_issue` واحدة، `cogs_warnings` في ردود الإنشاء بالترحيل التلقائي والتسليم وحفظ الإرسالية والترحيل+التحصيل، dedupe وN+1، استيراد pricing، ROUND_HALF_UP، اختبار عزل الشركة بطبقة مزوّرة على المنتج نفسه، حدّ اليوم نفسه). **مؤجَّل بقرار:** توجيه فرق المُعيدين الثلاثة للّقطة الثابتة إلى حساب الفروقات ← M1B-3 («التصحيحات اللاحقة»)؛ `issue_stock_from_invoice` بلا view يبقى؛ **ثغرة**: نقطة الحركة اليدوية `inventory/views.py` تقبل أي `reference_type` من العميل (SALE/PURCHASE_INVOICE مزوّرة تلوّث اللقطة وآخر شراء) ← تذكرة أمنية مستقلة بعد إيداع M1B-2 (قائمة بيضاء). ▶ fix1 (الجولة 1 من 3) يعمل على Terra ← `scratchpad/runs/M1B-2-fix1/`. التالي: قراءة الفرق ← مراجعة الحالة النهائية ← البوّابة ← الإيداع. ✅ fix1 اكتمل (F1–F10 + تنبيه `DeliveryOrderViewSet.deliver`؛ 21 passed مركّزة، sales+inventory+logistics ← 2048 passed). قرأتُ الفرق كاملاً، وتحقّقتُ أن `_cogs_warnings` يُقرأ من الكائن نفسه الذي عدّله الـservice في المسارات الأربعة (التحصيل، وحفظ الإرسالية، و`deliver_delivery_order` ← `delivery.invoice`، والتسليم قبل `refresh_from_db`). `test_docs_freshness` يفشل محلياً على مسارات `.agents/worktrees` وحدها (بيئي)، وmakemigrations الحقيقي نظيف. ▶ مراجعتا الحالة النهائية Opus جاريتان + البوّابة المعزولة في الخلفية (`scratchpad/gate-last.log`). nits مسجّلة: الاستيراد الدالّي الزائد في `record_stock_movement`، ولا اختبار مخصّص لتنبيه التحصيل وحفظ الإرسالية.
- ✅ البوّابة المعزولة بعد fix1: 7996 passed + `PaperAmountsPayloadTest` البيئي وحده.
- ✅ المراجعتان النهائيتان: Spec ← PASS. Standards ← major واحد (اختبار التسليم لا يسقط إن مُرِّر `total_cost` لأن
  effective == total في الـfixture). **fix2 (الجولة 2 من 3) يعمل** بموجز `scratchpad/briefs/M1B-1-fix2.txt` (PropertyMock 18 مقابل 20
  وسطر فروقات 2، واختبارا الأصول المختلطة والفائض، واستخراج `_fixed_cogs_reversal`، والتقريب بخطوتين 4 ثم 2 خانات، وتصحيح
  الوثائق والتعليق). بعده: قراءة الفرق، ثم مراجعة نهائية، ثم البوّابة، ثم الإيداع.
- 🐞 **ثبت بالقراءة عيبٌ قديم من #137 (خارج M1B-1):** إلغاء ترحيل مرتجع البيع (`sales/views.py` `unpost_invoice` ← `accounting/services.py`
  `unpost_document` ← `inventory/services.py` `reverse_stock_movements`) يحذف RETURN_IN لكنه **لا يعيد استهلاك الطبقات** التي رفعها
  `restore_partial` ولا يعيد صفوف استهلاك البيعة. مثال: 8@10 و4@16، ثم بيع 10، ثم مرتجع 4، ثم إلغاؤه ← الطبقات 2+4 (=84) والرصيد 2.
  إعادة الترحيل تعكس 40 بدل 52. لا اختبار post←unpost للطبقات. **الإصلاح:** حفظ أثر الاستعادة لكل مرتجع وعكسه ذرّياً عند الإلغاء.
  التقرير في `runs/R-return-unpost/final.txt`. ✅ **المالك: «Yes, before M4»** ← أُضيف تذكرة **M1B-R** في §5 من الخطة، وتُنفَّذ
  **مباشرةً بعد إيداع M1B-1** (تلمس مسار المرتجع نفسه)، وM4 صار يعتمد عليها. **الترتيب الجديد:** M1B-1 ← M1B-R ← M1B-2 ← M1B-3 ← M1B-4
  ← M3 ← M2 ← M4 ← M0 ← M5.
- (سابقاً) مراجعتان نهائيتان + البوّابة بالتوازي.
  **سقف التصليح:** جولة جديدة فقط لمانع أو ملاحظة major، وبحد أقصى 3 جولات، ثم يُعرض الأمر على المالك. إن خلت المراجعتان
  من مانع والبوّابة خضراء (عدا `PaperAmountsPayloadTest` البيئي) يأتي الإيداع المحلي `feat(M1B-1-COGS): …` ثم runs.md.

## ⏸ توقف بطلب المالك — 2026-11-17، 19:59 Asia/Hebron

**آخر طلب:** «وقف حاليا حدث ملف التلسليم والتقدم». أُوقف العامل فوراً، والتحديث هنا مباشرة فقط؛ لا متابعة أو فحوص حتى إذن جديد. لا commit ولا push ولا نشر ولا نسخة إنتاج أو هجرات على قاعدة عمل. الفرع عند المطابقة `newktra`، HEAD `13da894b`؛ ملفات المالك غير المرتبطة محفوظة.

**المنجز فعلاً:** M1A غير مودعة، تخزين الحقول الخمسة والهجرتين والاختبار فقط، بلا محرك طرق أو API/UI أو تغيير حسابات. بعد تقرير العامل أعاد المنسق بنفسه `python -m pytest sales/tests/test_cogs_cost_methods.py sales/tests/test_settings_engine.py inventory/tests/test_fifo_engine.py inventory/tests/test_fifo_movements.py -q` ← `29 passed in 12.38s`؛ وفحص `makemigrations --check --dry-run --settings=core.test_settings` مع `KTRA_MIGRATIONS_DB` ← `No changes detected`، و`sync_docs --settings=core.test_settings` و`git diff --check` ← exit0. التحذير السابق `employee_ops.W001` باقٍ.

**فحص الهجرة حُسم استقلالياً، بحدّ أداة مسجّل:** `delegation_verify` قطع `python -u "$env:TEMP\ktra-cogs-m1a-migration-probe.py"` عند نحو121s أثناء بناء الرسم السابق بلا traceback، فسُجل FAILED. تحقّق المنسق من انتهاء العملية ثم نفّذ استدعاء Python نفسه عبر `pwsh` بخلفية مناسبة وجمع `pwsh-62a69e4de5674720`: **exit0 و`MIGRATION_ROUNDTRIP_PASS`، 845.6s**. السجل `%TEMP%/ktra-cogs-m1a-coordinator-final.log`: قاعدة SQLite فريدة ← المخطط السابق ← ثلاث شركات (إعدادان بعلمين مختلفين وشركة بلا إعدادات) ومنتجان وحركتان ← الهجرتان الجديدتان وحدهما ← تأكيد القيم وFIFO وNULL ← التراجع عنهما وحدهما مع بقاء الصفوف ← إعادة التطبيق. **لا تُعد بناء479 هجرة مرة أخرى لمجرد حد أداة التسجيل.** نتيجة الأداة القصيرة تبقى فاشلة في السجل رغم نجاح التشغيل المستقل. لا تحقق MySQL 8.4 ولا بوابة backend كاملة جديدة على M1A، والفحوص سبقت تحديث التوقف هذا.

**المراجعة:** `attempt-e2dbd44e-52c6-4eba-83e4-de4851ebc3ff` أُغلقت `reviewed-completion` بحدود الفحص أعلاه (ثلاثة ملفات توثيق فقط تغيّرت خلالها، وأداة تحقق TEMP). مراجعتا Standards `attempt-1ff2aafd-38d5-4185-b15f-9cbff8fc6b35` وSpec `attempt-08fb5fca-d5b0-4171-ba90-36cbda97655d` اكتملتا قراءةً فقط بلا مانع وبلا تعديل وبلا فحوص؛ قبلهما المنسق ساكناً. تنبيهات Standards: اختبار الاستقلال تخزيني لا اختبار محرك، و«لا backfill» دليلُه الهجرة لا إنشاء حركة جديدة؛ والفرق بين `total_cost` (قيمة المخزون) و`cogs_cost` (مصروف الطريقة) مقصود ويحتاج قيد فرق في M1B. افتراض FIFO محسوم؛ العلم القديم لا يبدّل محرّك الصرف القائم FIFO. السالب محروس بـvalidator لا CheckConstraint؛ لا قيود إضافية ضمن M1A.

**ما لم يُنفّذ:** أُرسل موجز `M1B-1-COST-JOURNAL-SEAM` إلى `attempt-2716e79b-cd6f-4d7f-9c69-859c76193528` / `delegation-25fa5a58ff6c47ac`: فصل خرائط قيمة المخزون وCOGS في `sales/services/calc.py` و`pricing.py` و`flow.py`، قيد فرق، و`Coalesce(cogs_cost,total_cost)` لكل حركة، واختبار `sales/tests/test_cogs_snapshot_journals.py`. أُوقف بطلب المالك؛ `delegation_review` **صفر تعديل مرصود ولا تقرير**، وconclude `needs-attention`. **لا كود مالي ولا اختبار جديد من هذه المحاولة؛ لا تعتبر الموجز تسليماً.** لا عامل أو فحص جارٍ بعد الجمع.

**عند استئناف صريح:** انتقل مباشرة لشريحة القيود/قراءة اللقطات المذكورة (اختبارات مركزة أولاً)، ثم الكاتب والطرق والمرتجعات وAVCO بقيمة طبقات نقدية صحيحة، وبعدها API/UI وإعداد سعر الجدول المستقل، فالبوابات النهائية والنسخة الاحتياطية قبل أي نشر بإذن منفصل. اشتكى المالك «حاسك فايت بلوب مطول ولا شو»؛ أُقرّ بالتأخير: لا تكرر قبول M1A ولا تنشئ أدوات تحقق معقدة بدل التنفيذ. الهدف الآلي بقي paused/disarmed؛ `resume` رفضته الأداة، ولا التفاف بهدف جديد.

## ✅ `TASK M1A-CLOSE` — 2026-11-17، بعد «كمل وقلي ككم ضايل» ثم «بعدك بالمرحلة الاولى .»

**آخر طلبين للمالك:** «كمل وقلي ككم ضايل» ثم «بعدك بالمرحلة الاولى .». حُسم فحصُ M1A الوحيد المفتوح (دورةُ الهجرة على صفوفٍ قديمة) ولم يبدأ المحرّكُ المالي ولا الواجهة.

**الحالة الدقيقة:** `newktra` / HEAD `13da894b`. M1A **ما زالت غير مودعة** وبياناتٍ فقط: `inventory/models.py` (`COGS_METHOD_CHOICES`، `Product.standard_cost` ‏`Decimal(18,4)` ≥0 قابلةٌ للفراغ، `StockMovement.cogs_cost` ‏`Decimal(18,2)` ≥0 و`cogs_method`)، و`sales/models.py` (`SalesSettings.cogs_cost_method` بافتراض `fifo`، و`cost_variance_account`)، وهجرتا `AddField` وحدهما `inventory/migrations/0046_cogs_cost_methods.py` و`sales/migrations/0054_cogs_cost_methods.py`، واختبار `sales/tests/test_cogs_cost_methods.py` (سبعة)، والوثائق. **لا service ولا API ولا UI ولا أيُّ محرّكِ طرق.**

**سببُ الصمت السابق:** السكربت لم يُخرج شيئاً قبل تطبيق الرسم السابق كاملاً (8–9 دقائق)، والقاعدتان المتروكتان تُثبتان 479 هجرة مطبَّقة مع الهجرتين الجديدتين وقيمَ صفوفٍ مطابقة — فالغائبُ كان الخرج لا التقدّم. أُصلحت الأداة خارج المستودع (تقدّمٌ لكل مرحلة، سجلٌّ يملكه السكربت، تقدّمٌ كل 25 هجرة) وحُذف منها ضبطُ SQLite بعد أن قِيس أسوأ (1296s مقابل ~488s).

**التحقق الفعلي:** `python -u %TEMP%\ktra-cogs-m1a-migration-probe.py` = exit 0 و`MIGRATION_ROUNDTRIP_PASS` (631.3s: الهجرتان وحدهما أماماً ثم تراجعاً ثم إعادةَ تطبيق، وصفوفٌ سليمة بعد إعادة بناء الجدول) · `29 passed in 13.79s` · `No changes detected` (بمتغيّر `KTRA_MIGRATIONS_DB`) · `sync_docs` exit 0 · `git diff --check` exit 0.

**حدود:** لا بوابةَ كاملة (`-n auto`) ولا قبولَ منسّق ولا commit/push/نشر ولا قاعدةَ إنتاج أو عمل. إثباتُ الهجرة على SQLite وحدها لا MySQL 8.4. **الباقي: M1B** (المحرّك/القيود/الفروقات/المرتجعات/لقطات AVCO) ثم M1C (اختيارٌ فعّال وواجهة)؛ لا يُدَّعى أيُّ تنفيذٍ للطرق.

## ⏸ توقف بطلب المالك للكومباكت — 2026-11-17، بعد انقطاع الجلسة واستئناف 18:06

**آخر طلب:** «وقف مؤقتا حدث ملف التسليم والتقدم دعمل كومباكت». توقف التنفيذ والفحوص؛ لا متابعة حتى طلب صريح جديد. حُدّث هذان الملفان مباشرة دون عامل توثيق جديد. لا push ولا نشر ولا نسخة إنتاج ولا تطبيق هجرات على قاعدة عمل.

**الحالة الفعلية عند آخر مطابقة:** `newktra` / HEAD `13da894b`، وهو إيداع عرض أسعار المنتجات محلياً فقط. شريحة `M1A` ما زالت **غير مودعة**: خمسة حقول نموذجية مشتركة الاختيارات، هجرتا `inventory/migrations/0046_cogs_cost_methods.py` و`sales/migrations/0054_cogs_cost_methods.py` (`AddField` فقط)، واختبار `sales/tests/test_cogs_cost_methods.py` ووثائقها (12 مساراً). لا محرك تكلفة بديلة ولا API/واجهة لاختيارها ولا كتابة لقطات ولا تعديل حسابات أو FIFO. ملفات المالك غير المرتبطة محفوظة.

**مراجعة المنسق بعد الانقطاع:** قرأ فرق الشريحة والهجرتين والاختبار والوثائق. أعاد عبر `delegation_verify` على `attempt-a4550937-60ed-4f32-81ec-93b6a9fd0ef3` الأوامر: `python -m pytest sales/tests/test_cogs_cost_methods.py sales/tests/test_settings_engine.py inventory/tests/test_fifo_engine.py inventory/tests/test_fifo_movements.py -q` → **29 passed in 11.89s**؛ فحص الهجرات مع `KTRA_MIGRATIONS_DB` → `No changes detected`؛ `python manage.py sync_docs --settings=core.test_settings` → exit0؛ `git diff --check` → exit0. التحذير القائم `employee_ops.W001`. صحّح المنسق مباشرة سطرين توثيقيين: موجز M1A من المنسق لا طلب حرفي من المالك، ونتيجة البوابة السابقة ليست دليلاً على الشريحة الحالية. **لا فحوص بعد طلب التوقف أو بعد تحديث التسليم هذا.**

**حدود القبول:** تقرير العامل عن `1176 passed` لتطبيقي المخزون والمبيعات ودورة هجرة من صفر هو تقريره، لا إعادة تحقق المنسق. فحص المنسق الإضافي لصفوف قديمة بهجرات حقيقية لم يكتمل: أداة التحقق أعادت exit1 بلا خرج للأمر `python "$env:TEMP\ktra-cogs-m1a-migration-probe.py"`؛ تشغيل تشخيصي محفوظ في `%TEMP%/ktra-cogs-m1a-migration-probe.log` بقي فارغاً وأُوقف بطلب المالك (`pwsh-a4713b0c527f4171`، جُمعت النتيجة killed). البرنامج خارج المستودع `%TEMP%/ktra-cogs-m1a-migration-probe.py` ينشئ SQLite فريدة، ولا توجد نتيجة تثبت تطبيق/تراجع ناجحاً من المنسق؛ افحص الحالة قبل إعادة أي محاولة، ولا تعِد تشغيله عمياناً. المراجعتان النهائيتان Standards `attempt-d6175695-25c5-4f89-90e7-2fd91746e2ea` وSpec `attempt-e675d94a-fdf2-415a-8e1a-944eff0e7d6c` أُوقفتا، بلا تقرير وبلا تعديل مرصود؛ **لا قبول مستقل للشريحة**. أصل التنفيذ لا يُعد مقبولاً نهائياً. لا بوابة backend كاملة جديدة على M1A.

**عند طلب متابعة جديد فقط:** احسم فحص الهجرة على بيانات قائمة والمراجعتين، ثم أكمل M1B (محرك الطرق/القيود/الفروق/الأرباح/المرتجعات وتصميم AVCO الدقيق) وبعده الواجهة وإعداد سعر الجدول المستقل. لا تعتبر وجود الحقول تنفيذ طرق التكلفة. لا تغيّر التاريخ ولا تعتمد اقتراح AVCO الأول المتناقض؛ المخزون والطبقات يجب أن يتطابقا نقدياً. نتائج العرض والتصميم السابقة أدناه تاريخية. كما ظهر تحذير `git gc` بعد الإيداع المحلي بعدم القدرة على حذف بيانات worktrees قديمة (`Permission denied`)؛ الإيداع نجح، ولم تُجرَ معالجة أو حذف يدوي.

## ⏩ متابعة 2026-11-17 — `M1A-COGS`: عقدُ البيانات جاهز، والمحرّك لم يبدأ

الفرع `newktra`، والـHEAD المحلي `13da894b` (إيداعُ `ITEM-PURCHASE-DISPLAY` محلياً). أُضيفت في هذه الجولة **حقولُ تخزينٍ فقط** لطرق تكلفة المبيعات: `SalesSettings.cogs_cost_method` (افتراض `fifo`) و`cost_variance_account`، و`Product.standard_cost` (`NULL` = «لم تُحدَّد»)، و`StockMovement.cogs_cost`/`cogs_method` (`NULL` = تاريخية، **بلا تعبئة تاريخية**). قائمةُ الاختيارات `COGS_METHOD_CHOICES` معرَّفةٌ مرّةً واحدة في `inventory/models.py`. الهجرتان `inventory/0046_cogs_cost_methods` و`sales/0054_cogs_cost_methods` (‏`AddField` فقط) دُوِّرتا كاملتين على قاعدة SQLite مؤقّتة **جديدة**: من صفر ← التراجع عن الهجرتين الجديدتين وحدهما ← إعادةُ تطبيقهما. `git diff --check` و`sync_docs` نُفّذا. **لا commit ولا push ولا نشر، ولم تُمَسّ أي قاعدة إنتاج.**

**ما لم يُنفَّذ ولا يُدَّعى:** لا محرّكَ يكتب اللقطات أو يقرأ الطريقة، ولا اختيارَ فعّالاً في الـAPI أو الواجهة (`SalesSettingsSerializer` بقائمة حقوله الصريحة لم يتغيّر)، ولا مساسَ بـ`total_cost`/FIFO/`avg_cost`/الأرباح/الترحيل/`use_moving_average_cost`. الاختبارُ `sales/tests/test_cogs_cost_methods.py` أُولِّيٌّ (٧ اختبارات: `7 passed`) بعد أن رُئي **أحمرَ لغياب الحقول** لا لخطأ تهيئة؛ والأمرُ المركّز `29 passed`؛ و`makemigrations --check --dry-run` = `No changes detected`. **البوابة الكاملة لم تُشغَّل على هذه الشريحة**؛ النتيجة السابقة على النسخة المعزولة (7975 passed، 6 skipped، وفشلُ `PaperAmountsPayloadTest` المثبت على HEAD) تخصّ الحالة قبل إضافة الحقول، وليست دليلاً جديداً على حالة M1A.

**الخطوة القادمة:** M1B — محرّكُ الطرق والقيود وفروقاتُ التكلفة والأرباح والمرتجعات، وتصميمُ لقطات AVCO (`remaining_value`/`consumed_value` مؤجّلة عمداً حتى يُثبت التقريب)؛ ثم M1C للاختيار الفعّال وواجهة العرض. **لا نشر** قبل مراجعة الفرق سطراً بسطر ونسخةٍ احتياطية وإذن المالك.

## ⏩ متابعة 2026-11-17 بعد طلب «كمل»: فحص العرض حُسم، والتنفيذ المالي تالٍ

طلب المالك المتابعة؛ لا توقف ساري الآن. الهدف الآلي ما زال paused/disarmed ورفض resume، لكن العمل العادي يتابع بطلبه. **لا push ولا نشر**؛ إذن المالك محلي فقط، ومراجعة التغييرات والنسخة الاحتياطية تسبقان أي نشر.

اكتملت البوابة على نسخة مطابقة خارج الشجرات المتداخلة `%TEMP%/ktra-ipd-audit-20261117-1450`: `python -m pytest -q -n auto` = **7975 passed، 6 skipped، وفشل واحد** في `PaperAmountsPayloadTest` بسبب xdist/execnet وتسلسل كائن User. أُعيد الفشل نفسه على HEAD غير المعدل في `%TEMP%/ktra-ipd-head-20261117-1515` (أرشيف zip صحيح، لا نسخة tar الجزئية القديمة). السجلان `%TEMP%/ktra-ipd-isolated-backend-20261117.log` و`ktra-ipd-head-xdist-20261117.log`. هذه بوابة مكتملة ذات عطل سابق مثبت، **وليست خضراء**.

نجحت typecheck واختبارات الواجهة والبناء، والهجرات بفحص فعلي، وsync_docs بلا تغيير. اختبار المنتجات أُعيد منفرداً بعد تعثر التنقل تحت الحمل: **4 passed**؛ وراجَع المنسق صورتَي الجدول والرأس. اختبار العروض يفشل قبل التسمية عند «اختر منتجاً…»، وثبت الموضع نفسه على HEAD؛ لا إصلاح خارج النطاق. السجلات `%TEMP%/ktra-ipd-{unit,build}-resume-20261117.log` و`ktra-ipd-e2e-products-only-20261117.log` و`ktra-ipd-head-quotation-20261117.log`. قرئ الفرق النهائي سطراً بسطر. الإيداع المحلي لعمل العرض مأذون، ولا يُضمّ ملف آخر من ملفات المالك غير المرتبطة.

M1–M4 لم تُنفذ بعد هذه المراجعة. مراجعة AVCO للقراءة فقط انتهت بتصحيح اقتراح خاطئ (طبقات32 مقابل مخزون24): الاتجاه الآن حفظ قيمة نقدية للطبقة والاستهلاك وإرجاع القيمة مع الكمية، لا تسعير الطبقات عمياناً ولا قيمة AVCO منفصلة عن الطبقات. التصميم الكامل ما زال يحتاج اختبارات التقريب وفك الوارد وlanded cost والسالب؛ لا تعتمد الصيغ الأولية المنسوخة كتطبيق مثبت. خطر سابق في `logistics/domain/landed_revaluation.py` (تغيير الاستهلاك/الحركة بعد إعادة التقييم وفارق محتمل بعد فك البيع) أُبلغ ولم يُصلح مستقلاً. المحاولتان `attempt-a898895f-2be5-401b-9800-7c2a346f9ff9` ثم `attempt-8aef9e8c-6e49-4484-bcee-5150ab3c917b`: صفر تعديلات، `git diff --check` ناجح، دليل ساكن فقط. الفقرات الأقدم أدناه تاريخ وليست الحالة الحالية.

## ⏸ نقطة الاستئناف — 2026-11-17، بعد استئناف 14:09: مراجعة العمل السابق فقط، ثم توقف للكومباكت

**آخر طلب للمالك:** «وقف شوي حدث ملف التسليم والتقدم دعمل كومباكت». يتوقف العمل بعد تحديث هذين الملفين مباشرة، بلا عامل توثيق جديد وبلا فحوص جديدة. لا استئناف إلا بطلب جديد. الهدف `goal-20f20f33-6099-479b-afeb-55d30b75624c` عند القراءة الحالية `paused` / `disarmed`، revision 3؛ محاولة `update_goal action=resume` رفضتها الأداة: `the model cannot resume a paused goal; the user must resume it`. المتابعة العادية ممكنة بطلب المالك؛ التشغيل التلقائي يحتاج تفعيل المالك من الواجهة.

**المطابقة الفعلية:** الفرع `newktra`، HEAD `ab92c5df710d25f02e3ca84b4224d73c5062e412`. لم يبدأ تنفيذ M1–M4، ولم يُعدَّل model أو migration أو منطق مالي في هذه الجولة؛ لا commit ولا push ولا نشر ولا نسخة إنتاج. الموجود ما زال `ITEM-PURCHASE-DISPLAY` غير مودع: 21 ملفا متتبعا معدلا (+787/−45 عند بدء المراجعة) و`frontend_v2/e2e/items-purchase-prices.spec.ts` غير متتبع. ملفات المالك غير المرتبطة لم تُمس. أعاد المنسق قراءة نص الخطة الأصلي من سجل الجلسة (event 165)، وقرأ فرق backend/frontend/tests/docs والاختبار الجديد. الخطة المعتمدة والأرقام الاختبارية هي نفسها في الفقرة التالية، وليست ميزة منفذة.

**مراجعتا القراءة فقط انتهتا:** Standards `attempt-f8756a22-53ab-49d0-b101-f8cced9b6415` وSpec `attempt-b052ed85-6c58-4a5d-90d9-00d6bb682529` على الفواعلي `max`؛ لا مانع مثبت داخل تذكرة العرض، ولا تعديل لوحظ من أي منهما. استُلمتا بـ`delegation_review` ثم شغّل المنسق `git diff --check` لكل محاولة: exit 0، ثم `reviewed-completion` لكلتيهما، بحدود **مراجعة ساكنة فقط** لا قبول البوابات. أهم ملاحظة تحقق منها المنسق: `last_purchase_prices_base_currency` يأخذ سعر المورد بعد حصته، بينما `_purchase_lowest_prices_base_currency` يأخذ السعر المحمل الخام؛ في الدولية الوحيدة قد يظهر آخر شراء 70 وأقل شراء 100. لم يتغير أي حساب أو تلميح بعد الملاحظة؛ اقتُرح توضيح الأساس في UI/docs لاحقا لا تغيير صيغة الأقل بصمت. يبقى احتساب مرتجع الشراء ضمن آخر سعر كما في المسترجع القديم، خارج إصلاح العرض. ملاحظات غير مانعة: لا اختبار نطاق مستقل لـ`set_active`، وتلميح الربح ما زال يقول «سعر التكلفة».

**الفحوص الجديدة التي رآها المنسق:** من `frontend_v2`، `npx tsc --noEmit` انتهى exit 0 (`pwsh-1bb39e51da6d4ddc`). `npm test` انتهى: 1434 pass، 0 fail، 0 skipped؛ خرجُه في `%TEMP%\ktra-ipd-unit-20261117.log`. أمره المتسلسل انتقل إلى `npm run build`، ثم أُوقف بطلب المالك (`pwsh-d742b806eff2462b`)؛ **لا نتيجة بناء نهائية**، والسجل `%TEMP%\ktra-ipd-build-20261117.log`. لم يُشغّل Playwright أو بوابة الهجرات أو sync_docs في هذه الجولة. لا فحص بعد تحديث ملفي التسليم والتقدم.

**سبب تعثر backend أصبح له شاهد جديد:** شُغّل `python -m pytest -q -n auto -o faulthandler_timeout=120` بسجل `%TEMP%\ktra-resume-baseline-20261117.log` (`pwsh-7e5395852fd04e93`). وصل 99% مع علامات F، وبقي بلا تقدم نهائي؛ أوقف المنسق شجرة عمليته وحدها بعد نحو نصف ساعة. الـtracebacks تُظهر حراس `test_terminology_guard` و`test_docs_freshness` و`platform_ops/tests/test_isolation_guard.py` داخل المسح/قراءة/AST لمسارات المستودع، وفيه عشرات worktrees قديمة متداخلة (`git worktree list`). **ليس دليلا على أسماء كل الفشل أو أنه سابق؛ لا خلاصة pytest ولا بوابة ناجحة. لا تكرر التشغيل نفسه بلا معالجة بيئة المسح.**

**محاولة عزل الفحص لم تنجح بعد:** أُنشئت أرشيفة HEAD ورقعة `git diff --binary` تحت `%TEMP%` بالبادئة `ktra-ipd-verify-20261117-1440`؛ استخراج `tar.exe` فشل exit 1 برسالة `Archive entry has empty or unreadable filename ... skipping`. المجلد `%TEMP%\ktra-ipd-verify-20261117-1440` **نسخة جزئية غير صالحة للفحص**؛ لم تُطبق الرقعة ولم يُنسخ الاختبار الجديد ولم تُشغّل pytest عليه. افحص الحالة قبل إعادة المحاولة؛ لا تعتمد هذه النسخة ولا تحذف/تنظف worktrees المالك لتسريع الاختبارات. كل وظائف هذه الجولة جُمعت، والبناء والبوابة أُوقفا؛ لا عامل جار.

**بعد طلب متابعة صريح:** احسم فحص العمل السابق ببيئة تحقق مطابقة بلا الشجرات المتداخلة (عالج استخراج الأرشيف أولا أو استخدم آلية موثوقة أخرى)، ولا تعتمد نجاحا قبل خرج نهائي. بعدها إيداع المسارات المأذونة فقط، ثم التنفيذ المفوض المرحلي. نقطة تصميم M1 غير المحسومة: تسطيح أسعار الطبقات للمتوسط قد يفصل قيمة الرد عن snapshots القديمة؛ لا تنفذ تغيير `unit_cost` عميانا. أي بديل (مثل استهلاك نسبي) يحتاج برهان التقريب والقيمة والرد وتبديل الطريقة، ولم يُعتمد أو يُنفذ هنا. لا push أو نشر قبل عرض التغييرات ونسخة احتياطية وإذن المالك كما طلب.

## ⏸ نقطة الاستئناف — 2026-11-17 14:04: خطة طرق التكلفة معتمدة، والتنفيذ لم يبدأ

المالك اعتمد البدء بخيارات تكلفة المبيعات: FIFO افتراضياً، متوسط مرجّح بالكمية، سعر ثابت لكل منتج، وآخر سعر شراء فعلي مرحّل شامل التكاليف المرسملة؛ مع حساب فروقات تكلفة منفصل للسعر الثابت وآخر شراء، وإعداد مستقل للرقم الأساسي المعروض بجدول المنتجات. التغيير للأمام دون إعادة كتابة القيود القديمة. سمح بإيداع عمل `ITEM-PURCHASE-DISPLAY` الموجود بعد مراجعته وفحصه، وشدّد على التحقق المالي وعلى نسخة احتياطية ومراجعة ما تغيّر قبل أي نشر. **لم يبدأ تنفيذ الميزة ولم يحصل commit أو push أو نشر في هذه الجولة.** قُرئت أجزاء من الفرق الحالي؛ لم تكتمل قراءة الفرق أو البوابات اللازمة للإيداع. العمل السابق وتغييرات المستخدم الأخرى محفوظة وغير مودعة.

بدأت بوابة `python -m pytest -q -n auto -p no:cacheprovider` بسجل `%TEMP%\ktra-gate-ipd-20261117.log` (العملية `pwsh-2d5fd07e06384c0f`)؛ طُلب إلغاؤها عند طلب الكومباكت، ولم تُجمع خلاصة تثبت نجاحها أو فشلها. أُوقف عامل التوثيق `attempt-7d314370-dcef-42f2-9525-e112c9ce4b58` بطلب المالك؛ مراجعته لم ترصد أي تعديل منه. حدّث المنسّق هذين الملفين مباشرةً فقط لتسجيل التسليم ثم توقف. الهدف `goal-20f20f33-6099-479b-afeb-55d30b75624c` غير مُسلّح عند آخر قراءة؛ لا استئناف تلقائي. عند طلب المالك المتابعة: اقرأ الحالة وفرق Git الحالي، وأعد تسليح الهدف بـ`update_goal action=resume`، ثم احسم فحوص العمل السابق قبل إيداع مساراته وحدها، وبعدها فوّض تنفيذ الخطة مع اختبارات المال أولاً. **لا نشر قبل نسخة احتياطية وعرض التغييرات على المالك وإذنه.** الفقرات الأقدم سجل تاريخي وليست حالة التنفيذ الجديدة.

## ⏩ الحالة الحالية — 2026-11-17: استكمال المراجعة والتصحيح محلياً

بطلب المالك «كمل» أُجريت مراجعتا Standards وSpec، ثم صحّح الفواعلي نطاق جلب `last_purchase_price` ليقتصر على صفوف الطلب (بعد إكمال العائلات، وفي القراءة والإنشاء والتعديل المفرد)، وأضاف أربعة اختبارات، وحدّث توقع التسمية وحده في `frontend_v2/e2e/quotation-document-discount.spec.ts`. المحاولة `attempt-9cc26f4d-d300-4b66-9555-b7107325ab65`؛ المراجعتان النهائيتان `attempt-0786570d-5fe2-4289-ba5e-0e59efc3ca21` و`attempt-b97b55ac-0187-46eb-a2e1-49a8b5ff863a` أعادتا «لا مانع» بالقراءة فقط. قرأ المنسّق الفرق وأعاد أمر الاختبارات المركزة المدوّن أدناه: `97 passed in 30.40s`؛ و`python manage.py sync_docs --settings=core.test_settings` نجح مع `employee_ops.W001`. نتائج الواجهة السابقة أدناه تاريخية؛ لم يتغير كود الواجهة في الاستكمال.

**الحدود الباقية:** المجموعة الكاملة `python -m pytest -q -n auto` أعادت exit 1 بمخرجات مبتورة عند نحو 15% وفيها `F`. تشغيل مستقل حفظ خرجه في `%TEMP%/ktra-item-purchase-backend-20261117.log` وصل 98% ثم لم يسجّل تقدماً لأكثر من خمس دقائق؛ أوقف المنسّق شجرة عمليته فقط. لا خلاصة كاملة ولا تشخيص لفشل الاختبار، فلا بوابة خضراء ولا إثبات أنه عطل سابق. اختبار العروض شغّله المنسّق قبل تعديل توقع التسمية: فشل عند زر «اختر منتجاً…» قبل الوصول للبطاقة؛ لم يُصلَح المسار أو يُعَد تشغيله بعد التعديل النصّي. لا تغيير FIFO أو أرباح أو مخزون أو ترحيل أو هجرات. لا commit ولا push ولا نشر؛ الملفات غير المرتبطة محفوظة. الأقسام التالية سجلّ تاريخي، وليست أمراً بإعادة التنفيذ أو الفحوص الطويلة تلقائياً.

## ⏩ نقطة الاستئناف الحالية — 2026-11-17: عرض أسعار المنتجات، توقّف بطلب المالك للكومباكت

**الحالة:** التغيير محليّ وغير مودَع؛ لا commit ولا push ولا نشر في هذه الجلسة. المالك طلب «حدث ملف التسليم والتقدم ووقف بدي اعمل كومباكت». يتوقف العمل بعد تحديث هذين الملفين؛ الاستئناف بطلب جديد منه. الأقسام الأقدم أدناه سجلّ تاريخي، وليست أوامر نشر سارية أو إثباتاً لحالة الإنتاج الحالية.

**المطلوب المنفّذ (`ITEM-PURCHASE-DISPLAY`):** جدول المنتجات وتقرير طباعته يعرضان «آخر سعر شراء» أساسياً؛ «أقلّ شراء (آخر ٥)» داخل «تفاصيل السعر» مغلقة في خلية الجدول. رأس الكرت، خارج التبويبات، يعرض آخر شراء وأقل شراء ضمن آخر خمس فواتير ومتوسط تكلفة المخزون. توحّدت تسمية المتوسط في النظرة العامة وتبويب الأسعار والمجاميع. لا تعديل على FIFO أو حساب الأرباح أو تحديث المخزون أو الترحيل أو السكيمة.

**خريطة التعديل:** `core/pricing.py` (`last_purchase_prices_base_currency`) قراءة دفعية بالعملة الأساسية، بلا سقوط إلى المتوسط، بنفس ترتيب ومحوّلات سعر المورد في المسترجع القائم؛ `inventory/serializers.py` (`_last_purchase_price_map`، `last_purchase_price`) و`inventory/services.py` (`product_profile`) يقرآن المصدر نفسه. الواجهة: `frontend_v2/components/items/ItemsManagement.tsx` و`ItemForm.tsx` و`ProductInsightTabs.tsx`، ونوع `SqlProduct`. صف العائلة يحتفظ بسعر البراند المرجعي القائم، مع توضيح صاحبه في التفاصيل؛ لم يُعَد تصميم التجميع. أُضيف `frontend_v2/e2e/items-purchase-prices.spec.ts`، وعُدّل محاكي `items-tree-stubs.ts` واختبارات الأسعار في `logistics/tests/` والكرت والقائمة في `inventory/tests/`. حُدّثت وثيقتا المخزون والواجهة وسطر CHANGELOG، وعدادات ARCHITECTURE المولّدة.

**التحقق الذي شغّله المنسّق بنفسه على الحالة المسلّمة:**
- `python -m pytest logistics/tests/test_purchase_price_resolver.py inventory/tests/test_product_api.py inventory/tests/test_product_profile.py logistics/tests/test_international_supplier_share.py -q` → `93 passed in 45.32s`.
- من `frontend_v2`: `npx tsc --noEmit` → exit 0 في آخر إعادة؛ `npm test` → 1434 نجاحاً، صفر فشل؛ `npm run build` → exit 0 مع تحذيرات تقسيم الحزم؛ `npx playwright test e2e/items-purchase-prices.spec.ts --reporter=line` → `4 passed (58.4s)`.
- `python manage.py sync_docs --settings=core.test_settings` → exit 0 مع التحذير `employee_ops.W001`؛ `git diff --check` → exit 0. قرأ المنسّق الفرق وفتح صور الجدول والتفاصيل ورأس الكرت؛ المتصفح يستخدم API stubs لا بيانات الإنتاج.
- **البوابة الكاملة غير مثبتة:** `python -m pytest -q -n auto` أعادت exit 1 من `delegation_verify` بعد تقدّم أولي بلا traceback لفشل اختبار؛ تشغيل العامل السابق أُوقف بعد نحو 32 دقيقة بلا نتيجة. لا يجوز وصف المجموعة بأنها ناجحة أو نسبة التعثّر للتغيير أو إثبات أنه عطل سابق. ظهرت أيضاً نتائج exit 1 صامتة لـTypeScript عبر الأداة، بينما التشخيص اليدوي اكتمل exit 0، ثم نجحت إعادة الأمر نفسه عبر الأداة. السجل الأقدم أدناه يذكر حدوداً مشابهة للأداة، لكنه ليس دليلاً على سبب هذه الجولة.

**التسليم المفوّض:** `attempt-e53a4e6c-07d9-451d-b155-e905bc8da73d` على الفواعلي، concluded `reviewed-completion` بحدود الفحص أعلاه؛ 17 مساراً لوحظ تغيّرها قبل تحديث ملفي التسليم والتقدم. لم تُنفّذ مراجعتان مستقلّتان؛ المراجعة والفحص البصري للمنسّق، فلا يُدّعى قبول مراجع مستقل.

**ملاحظة قائمة لم تُصلَح:** اختيار آخر شراء في `resolve_purchase_price` لا يستثني `is_return=True`؛ الخريطة الجديدة تحفظ دلالته الحالية. تُناقش مستقلاً إن طُلب، لا تُصلح تلقائياً ضمن تغيير العرض. ملفات المالك غير المتتبعة (`.agy-design-refs/` و`marketing/` و`package-lock.json` و`str` والاسم مشوّه الترميز) بقيت بلا مساس.

**عند الاستئناف:** اقرأ هذه الفقرة وفرق Git الحالي أولاً؛ لا تعِد التنفيذ ولا الفحوص الطويلة تلقائياً. إن طلب المالك اعتماداً أو نشراً، يلزم حسم بوابة الخادم الكاملة والمراجعة المطلوبة، وإذن نشر صريح. التأخير في هذه الجولة سببه توسيع الفحوص وتعثر التشغيل؛ المالك اعترض على طول تغيير عرض صغير، فلا يتكرر التوسع بلا داع.

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-13 02:35 — **مُنشورةٌ على الإنتاج:** التذاكرُ الأربع `PASS` مستقلّ، وCI أخضر، والإنتاجُ `d4ffde71`)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — **`paused`/`disarmed`**، و`update_goal action=resume` **مرفوضٌ من الجلسة** («the model cannot resume a paused goal; the user must resume it») — يفعّله المالك من الواجهة إن أراد استئنافاً آليًّا.

**✅ نُشِر على الإنتاج 2026-11-13 02:35:** `git push origin newktra` (`4c22da02..9c63b736`) ← **CI أخضر على `9c63b736`** (`43334984170`: backend · frontend · pwa-audit) ← على الخادم دمجٌ بلا تعارض (`d4ffde71`) ← نسخةٌ `ktra-before-287-20261113-003215.sql` (27MB · 403 جدول) ← الهجرات الثلاث (`tenants.0038` · `accounting_office.0025` · `0026`) ← `npm run build` (304 مدخلاً بعد 296) ← `rsync` والـstatic ← `systemctl restart` ← `active` · `NRestarts=0` · ثلاث curls 200 · نقاط الوكيل الأربع 200 · `client-books`/`settings` 401 (حياةٌ لا 404) · لا خطأ في السجلّ. **و`#287` مغلقةٌ أصلاً على GitHub فلا إغلاق.**

**⚠️ ثغرةٌ في الخادم لم تُمَسّ وليست من النشر:** `hr/auth_api.py` (108 سطراً زائداً) و`hr/urls.py` (سطرا `magic_login_view`) **تعديلاتٌ غيرُ مودَعة** على `modern` بتاريخ 2026-11-12 16:27–16:32 من جلسات المالك — ظهرت في فحص الثابت `git diff origin/newktra --stat` وهي حيّةٌ الآن. **لم ألمسها ولم أضمّها إلى أيّ التزام** (تعديلاتُ المالك له). تبقى فارقاً دائماً في فحص الثابت حتى تُنقل إلى `newktra` بتذكرة أو تُلغى بقراره.

| التذكرة | الحال | الالتزامات |
|---|---|---|
| `#289` لوحة صاحب المكتب | ✅ PASS | `c5252c29` ← دمج |
| `#282` الأتعاب الورقية | ✅ PASS | `c470d1fc` ثم `b07018aa` ← دمج `26995c32` |
| `#288` دفتر الزبون ٣ | ✅ PASS | `b8b7da53` ثم `417b2052` ← دمج `19c6fc48` |
| `#287` دفتر الزبون ٢ | ✅ PASS | `bf4a71b6` ← `702d658c`، ثم `70c5af07` ← `f0ad883f` |

**ما جرى في هذه الجولة:** مراجعةُ تحقّقٍ على `#287` أعطت **NEEDS-FIX بمانعين جديدين** (زرّ «أكّد» يُفكّ بإعادة تحميلٍ تُفكّ المكوّن، وقسمةُ ضريبةٍ تتجمّد في القيد ويُعيد الإقرارُ حسابَها)، ثم جولةٌ ثانية على مصحح ٢ (`attempt-5185aeda`) أغلقتهما، ثم مراجعةُ تحقّقٍ ثالثة (`attempt-7d944242`) ⇒ **PASS**. التفصيلُ أعلى `docs/agents/progress.md` و`docs/agents/review-backlog.md` §٤.

**ما بقي:**
1. **تعديلاتُ الخادم غيرُ المودَعة** (`hr/auth_api.py` + `hr/urls.py`، وفيهما `magic_login_view`): تُنقل إلى `newktra` بتذكرةٍ وموجزٍ مستقلّ يعمل عليه وكيل، أو تُلغى بأمر المالك. **ولا تُحذف ولا تُخزَّن ولا تُودَع من الخادم** (و«القاعدة الحديدية» تمنع الكتابة هناك).
2. **تنظيفُ الشجرات المدموجة:** `acct-282fix` · `acct-288fix` · `acct-289fix` · `acct-282fix2` · `acct-288fix2` · `acct-287fix` · `acct-287fix2`.
3. **الديونُ أدناه** — تُفتح تذاكر عند الطلب، وأهمّها أن حركات الإنتاج المولَّدة قبل `f0ad883f` تُقرأ بنسبة الحساب الحالية.

**البوّابات على `f0ad883f` (شغّلها المنسّق بنفسه):**
- backend: `python -m pytest -q -n auto` ⇒ **7953 نجاحاً، 6 فشل، 6 تخطٍّ** — نفسُ الستّة البيئية بالاسم، **ولا فشلَ جديد**.
- الواجهة: `npx tsc --noEmit` ⇒ 0 · `npm test` ⇒ **1434 / 0**.
- الهجرات: `No changes detected` (بمتغيّر `KTRA_MIGRATIONS_DB` إلزاماً) · `import-linter` 3 kept · `test_docs_freshness` 9/9.
- `sync_docs` بعد الدمج لم يغيّر شيئاً.

**عطلُ أداةٍ مُثبت:** `delegation_verify` يعطي **FAILED** للمجموعة الطويلة (`accounting_office/tests`) بينما تشغيلُ pwsh اليدويّ يعطي `1433 passed, 2 skipped` — يقصّ المخرجات. **المجموعةُ الطويلة تُشغَّل بيدي.**

**ديونٌ مسجَّلة (لم تُصلَح):**
- **حركاتُ الإنتاج المولَّدة قبل `f0ad883f` تبقى بلا نسبةٍ على سطرها** فتُقرأ بنسبة الحساب الحالية — التجميدُ يسري من التوليد التالي، ولا هجرةَ تملأ التاريخ.
- تعليقُ رأس `OfficeObligationActions` يقول «كلُّ فعلٍ ينجح يُنادي `onChanged`» و«احسب» صار استثناءً · تعليقُ `models.py:3592` يصف النسبة بإعدادٍ وسببٍ وحدها · `docs/modules/accounting_office.md:81` والـCHANGELOG «يرفض التوليد» والأدقّ «يرفض حين في الورقة ضريبةُ مدخلات» · `PaperRateIsDisplayOnlyTest` أضيق من اسمها.
- من الجولات السابقة: `share_receipt`/`share_statement` بلا حارس قناع · `readyToSendItemRowKey` قد يكرّر مفتاح React · «شيل لهذه المرة» بلا أثرٍ على بند الرابط · مفتاحُ `documents` المشترك مع الإشعار الدائن · `assert_period_open` خارج معاملة `create_entry` · `submit_obligation` يقفل في معاملةٍ ثانية · كلفةُ `depreciation_payload` · `locked_periods` غيرُ مقروءةٍ في الواجهة · ظهورُ «احسب» لغير ض.ق.م · سباقُ `reopen_period` · شرطُ `canReopen` في الواجهة دون الخادم.
- مفتوحٌ خارج التذاكر: حذفُ شركات التجربة التسع (`purge_legacy_offices` جاهزٌ بأمرٍ صريح فقط) · `#292` بديونها.

**القواعدُ التي لا تُخالَف:** `sync_docs` **بعد** الدمج وفي الـcommit نفسه · لا نشرَ قبل CI أخضرَ على **آخر** commit · **لا نشرَ بلا مراجعٍ مستقلّ** · والمراجعُ لا يُكلَّف كتابةً · وفي الجذر `git add -- <مسارات>` لا `-A`.

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-12 23:45 — **المراجعاتُ المؤجَّلة نُفِّذت وسلّمها التصليح؛ كلُّها محليّةٌ غيرُ مدفوعة**)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — **الحالُ عند الكتابة `paused`/`disarmed`** (أوقفه المالك قبل الجولة بطلب «توقّف هلق»). للاستئناف: `update_goal action=resume`.

**⚠️ كلُّ عمل هذه الجولة محليٌّ على `newktra` = `702d658c` — أربعةَ عشرَ التزاماً غير مدفوعة. لا push ولا نشر، والإنتاجُ ما زال `56e344a8` (قبل `#282` و`#288` و`#289` و`#287`).**

**ما جرى:** المالكُ طلب تنفيذَ المراجعاتِ المؤجَّلة الأربع بلا رفع، ثم قال «امشي بالفلو أوّلَ مرّةٍ على فواعلي» — فنُفِّذ سلّمُ التصليح (فواعلي ← مصحح ٢ ← المراجع) حتى قبول المراجع.

| التذكرة | حالتُها الآن | الالتزامات |
|---|---|---|
| `#289` لوحة صاحب المكتب | ✅ **PASS من المراجع** (جولة تصليحٍ واحدة) | `c5252c29` ← دمج |
| `#282` الأتعاب الورقية | ✅ **PASS من المراجع** (جولتان) | `c470d1fc` ثم `b07018aa` ← دمج `26995c32` |
| `#288` دفتر الزبون ٣ | ✅ **PASS من المراجع** (جولتان + واجهة) | `b8b7da53` ثم `417b2052` ← دمج `19c6fc48` |
| `#287` دفتر الزبون ٢ | 🟡 **جولة أولى مدموجة، والمراجعةُ المستقلة عليها لسا ما انطلقت** | `bf4a71b6` ← دمج `702d658c` |

**الحصيلةُ الموثَّقة:** سبعةَ عشرَ مانعاً في المراجعة الأولى، وثغرتان لبندين باقيين في `#282`، وثلاثةُ بنودٍ باقية في `#288` — كلُّها في `docs/agents/review-backlog.md` §٤ (يُقرأ قبل أيّ استئناف).

**أوّلُ عملٍ في الجلسة القادمة — بهذا الترتيب:**
1. **مراجعةٌ مستقلّةٌ على `#287`** على الحالة المدموجة `702d658c` (نموذجُ الموجز في المحاولة `attempt-bbc7c4aa`: البنود الستة بمواضعها، وفرقُ `b73277f8..702d658c`). إن خرجت `NEEDS-FIX` فالجولةُ الثانيةُ على مصحح ٢ (`lane-1a4fac83…`)، ثم تحقّقٌ جديد.
2. **بعد أخضرِ المراجع للتذاكر الأربع:** `git push origin newktra` ← **CI أخضر على آخر commit** ← نشرٌ بنسخةٍ احتياطية — **والنشرُ لا يقع قبل كلمة المالك** («بدون ما رفع شي» كانت آخرَ تعليمٍ صريحٍ بشأن النشر، ثم قال «امشي بالفلو» وهو يحتمل الرفع؛ **يُسأل سؤالاً واحداً صريحاً قبل الدفع**).
3. **هجرةُ `#287` تُراجَع قبل `migrate`:** `accounting_office/0026_remove_bookperiodlock_uniq_book_period_lock` — `RemoveConstraint` وحدها (لا تحذف صفّاً). وهي **إلزاميّةٌ** لأن القفلَ صار صفّاً جديداً بعد كل فتح، والقيدُ القديمُ يمنع ذلك؛ ومِن ثَمَّ لا قيدَ شرطياً لأن MySQL 8.4 لا يدعمه.
4. **بعد النشر:** إغلاقُ `#287` في GitHub، وسطرُ تشغيلٍ في `docs/agents/runs.md`، وتنظيفُ الشجرات المدموجة (`acct-282fix` · `acct-288fix` · `acct-289fix` · `acct-282fix2` · `acct-288fix2` · `acct-287fix`).

**البوّابات على `702d658c` (شغّلها المنسّق بنفسه):**
- backend: `python -m pytest -q -n auto` ⇒ **7940 نجاحاً، 6 فشل** — كلُّها بيئيّة، **ولا فشلاً جديداً** (المجموعةُ قبل جولتي التصحيح التانيتين أعطت نفس الستّة): `PaperAmountsPayloadTest…` (فليكٌ معروفٌ تحت `-n auto` وحدها، أُثبت على `1e3381eb`) · `test_docs_freshness::test_production_code_has_one_source_of_today` · `accountant_portal::test_no_source_references_the_deleted_models_or_surface` (يثبت فشلُه أنه يقرأ `.claude/worktrees/**` القديمةَ حيث `practice.py` ما زال موجوداً — مؤكَّدٌ من رسالته) · `employee_ops` و`platform_ops` isolation guards · `terminology_guard`. **الخمسةُ الأخيرةُ تتلوّث بالشجرات والملفات غير المتتبَّعة في الجذر، وتزول في نسخةٍ نظيفة (CI).**
- الواجهة: `cd frontend_v2 && npx tsc --noEmit` ⇒ 0 · `npm test` ⇒ **1434 نجاح / 0 فشل**.
- وحدة `accounting_office` على `#287` وحدها: **1428 passed, 2 skipped, 986 subtests**.

**أخطاء المنسّق في هذه الجولة (مسجَّلة كي لا تُكرَّر):** (أ) `git add -A` في **جذر** المستودع ضمّ ملفاتِ المالك غيرَ المتتبَّعة (`.agy-design-refs/` · `marketing/` · `package-lock.json` · `str` · ملفٌّ باسمٍ مشوّه) إلى التزام دمج؛ **صُحّح** بـ`git rm --cached` + `amend` فعادت غيرَ متتبَّعة كما كانت، والالتزامُ نظيف (`fee432d4`). **القاعدة: في الجذر `git add -- <مسارات>` صراحةً، و`-A` في شجرات العمل فقط.** (ب) `create_worktree` أُنشئ ثلاثَ مرّاتٍ داخل شجرة عملٍ لأن سياق الجلسة كان فيها — أُزيلت ونُظِّفت، والباقي منها مجلّدٌ فارغٌ تحت `acct-282fix2` أُزيل. **القاعدة: عُد إلى الجذر قبل كل `create_worktree`.**

**ديونٌ جديدةٌ سُجِّلت هذه الجولة ولم تُصلَح:** تسريبُ الرابط في سجلّ التذكيرات أُغلق، لكن **`share_receipt` و`share_statement` من `#283` بلا حارس قناع** (يحتاج تذكرةً بنمط إصلاح `#288`: 403 ونطاق `none()`) · `readyToSendItemRowKey` لا يميّز بند الرابط (مفتاحُ React مكرَّرٌ ممكن) · «شيل لهذه المرة» لا أثر له على بند الرابط · الإشعارُ الدائن يتقاسم مفتاح `documents` بلا فاصلٍ بالمعرّف · `assert_period_open` يُقرأ خارج معاملة `create_entry` · `submit_obligation` يحفظ الحالة ثم يقفل في معاملةٍ ثانية · `depreciation_payload` يدفع 3 استعلاماتٍ لكل حسابِ أصلٍ على كل `GET` · `locked_periods` غيرُ مقروءٍ في الواجهة.

**شجراتُ العمل الحيّة:** `acct-282fix` · `acct-288fix` · `acct-289fix` · `acct-282fix2` · `acct-288fix2` · `acct-287fix` (كلُّها مدموجة). لا محاولةَ جارية، ولا مهمةَ خلفية.

**القواعدُ التي لا تُخالَف:** `sync_docs` **بعد** الدمج وفي الـcommit نفسه · لا نشرَ قبل CI أخضرَ على **آخر** commit · **لا نشرَ بلا مراجعٍ مستقلّ** · والمراجعُ لا يُكلَّف كتابةً.

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-12 16:45 — **`#291` منشورة**: الطبقةُ القديمةُ أُزيلت والمكتب 22 محوَّل، وحذفُ شركات التجربة مؤجَّلٌ بطلب المالك)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — إن ظهر disarmed فـ`update_goal action=resume`.

**الإنتاج = `56e344a8`** (دمجُ `origin/newktra` = `580668a2`) · CI أخضر `43225561774` · نسخةٌ `ktra-before-291-20261112-133933.sql` (28MB · 409 جدول) · الهجرتان المطبَّقتان: `accountant_portal.0007_delete_legacy_office_models` و`partners.0019_remove_partner_engagement_and_more` · `active` · `NRestarts=0` · ثلاث curls 200 · 296 حزمة واجهة.

**المكتب 22:** `template=accounting_office` و`TenantModule(accounting_office)` — نُفِّذ بأمر `switch_office_to_new_module --tenant-id 22 --apply`.

**⚠️ المفتوحُ الوحيد في `#291`: حذفُ شركات التجربة — أوقفه المالك بعد أن رأى المعاينة.** الأمرُ جاهز: `venv/bin/python manage.py purge_legacy_offices --tenant-id 14 --tenant-id 15 --tenant-id 16 --tenant-id 17 --tenant-id 18 --tenant-id 19 --tenant-id 20 --tenant-id 21 --tenant-id 28 --apply --confirm PURGE --backup-file /root/backups/ktra-before-291-20261112-133933.sql`. **لا تنفّذه إلا بأمرٍ صريح منه.** المعاينة الحقيقية: ثمانٌ صفرُ قيود، و`21` فيها 4 قيود؛ والباقي لا يُمَسّ (`كترا` 395 قيداً · `الجرابعه` 3901 · `شركة النور` 1794). **وسؤالُه المحسوم:** ليست «كلُّ شركةٍ لها حسابات» — كلُّ شركةٍ تُزرع لها شجرة — بل شركاتُ الطبقة القديمة وحدها.

**المراجعاتُ المؤجَّلةُ الباقية (٤):** `#282` · `#288` · `#289` · `#287` — في `docs/agents/review-backlog.md`، تُطلب بطلب المالك. ولم تُطلب بعد.

**`#292` مفتوحة** بديونها المسجَّلة (شيكُ المكتب اليتيم، وكشفُ الحساب لا يعرض الإشعار/التكميلية كحركة، ولا فعلَ «عكس دفعة»…).

**شجراتُ العمل:** `acct-291ui` · `acct-291ui2` · `acct-291cmd` · `acct-291cmd2` · `acct-291rm` (كلُّها مدموجة — تُنظَّف عند الفراغ) · والباقي من الجولات السابقة مدموجٌ أيضاً.

**قاعدةٌ تُنفَّذ حرفياً:** `sync_docs` **بعد** الدمج لا قبله وفي الـcommit نفسه، ولا نشرَ قبل CI أخضرَ على **آخر** commit، و**لا نشرَ بلا مراجعٍ مستقلّ**.


## ⏩ سجلُّ المراجعات المؤجَّلة — `docs/agents/review-backlog.md`

**تسعُ تذاكرَ دُمجت بلا مراجعةٍ مستقلّةٍ في نافذة سقوط اشتراك Anthropic** (`#284` · `#283` · `#282` · `#288` · `#289` · `#287` منشورة، و`#286/ج-١` · `#286/ج-٢` · `#290` مدموجة). الملفُّ يعدّها بألتزاماتها وحالِ كلٍّ منها، وخطواتُ المراجعة المؤجَّلة فيه — **يُقرأ قبل أيّ طلبِ مراجعةٍ من المالك بعد `#291`**.

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-12 08:10 — `#283/ج` و`#287` منشورتان، ومحاولتان جاريتان)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — إن ظهر disarmed فـ`update_goal action=resume`.

**الإنتاج = `5a2caf79`** (نشر `#283/ج` + `#287`) · **`newktra` = `eec75d2e`** · CI أخضر `43161917000` · نسخةٌ `ktra-before-283c-287-20261112-055224.sql` (27MB) · الهجراتُ المطبَّقةُ على MySQL حتى `accounting_office.0022` و`docshare.0010` · ثلاثُ curls 200 · `NRestarts=0`. **`#287` مغلقة** (و`#283` كانت مغلقة).

**خطُّ المراجع ساقط — لا تُضِع محاولةً أخرى عليه قبل إصلاح الحساب:** هيئةُ الخطوط تقول `signed-out`، والإرسالُ الفعليّ رجع `403 oauth_not_allowed_for_organization` مرّتين، و`claude -p --model opus` يقول «payment is past due … or use an Anthropic API key». **الإصلاحُ بيد المالك:** `claude.ai/settings/billing` أو `ANTHROPIC_API_KEY`. حتى ذلك الحين المنسّق هو المراجع (يقرأ الفرق سطراً سطراً ويشغّل البوّابات بنفسه) — والحدُّ مُعلَنٌ: **ستُّ تذاكر دُمجت بلا مراجعٍ مستقلّ** (`#284` · `#282` · `#283` · `#288` · `#289` · `#287`).

**جارٍ الآن (لا تلمس أشجارهما):**
| التذكرة | الشجرة | المحاولة | الحال |
|---|---|---|---|
| `#286/ج` بنودُ الحركة من الورقة | `.agents/worktrees/acct-286c2` | `attempt-cb8ae8e4` | كتابةٌ في `views.py`/`models.py`/`serializers.py`/`client_books.py` + هجرة `0023_document_amounts` + `tests/test_book_entry_generation.py` |
| `#290` التصدير والالتزامات وإعدادات التشغيل | `.agents/worktrees/acct-290` | `attempt-d929261a` | كتابةٌ في `office_exports.py`/`self_obligations.py`/`docshare`/إعدادات/واجهة + هجرة `0023` و`docshare 0011` |

**قراراتٌ محسومة لهذه الجولة:** (أ) `#286/ج` — المبلغُ على الورقة **صافٍ قبل الضريبة**، والإجمالي = `amount + tax_amount`، والطرفُ على سطر الذمم، وخريطةُ الحسابات بحسب نوع الورقة (`1300`/`4100` بيع · `5200`/`2100` شراء · `5100`/`1100` مصروف · `1200`/`1100` بنك · `1100`/`4100` تقرير يومي)، والضريبة على `2200` بالطرف المقابل. (ب) `#290` — **سجلٌّ مستقلّ لالتزامات المكتب نفسه** (`OfficeSelfObligation`) لا «المكتب زبوناً عند نفسه»، بمصدرٍ «المنصة» وموعدٍ 31/3 من السنة اللاحقة لمكتب PS، والتصديرُ الكاملُ للمالك وحده (403 لغيره)، وإعدادان مقفلان (`official_invoicing` · `auto_send`).

**`#291` آخراً** بعد `#290` وحده (تنتظر 277، 279، 287، 289، 290).

**بعد التسليمين:** راجع الفرق سطراً سطراً (لا تقريرَ المنفّذ)، بوّاباتُ كلٍّ بنفسك، دمجٌ تذكرةً تذكرة مع **إعادة ترقيم هجرات `0023` المتعارضة** و`docshare 0011`، ثم `importlinter` + `npx tsc && npm run build` **بعد الدمج**، دفعٌ، CI، نشرٌ بنسخةٍ احتياطية، إغلاقٌ، وتحديثُ الوثائق.

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-12 07:35 — توقّفٌ آمن بطلب المالك للكومباكت)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — إن ظهر disarmed فـ`update_goal action=resume`.

**لا عاملَ حيّ، لا محاولةَ جارية، لا مهمةَ خلفية.** الشجرةُ نظيفةٌ إلا العناصرَ الخمسةَ المعروفة غيرَ المتتبَّعة (`.agy-design-refs/` · `marketing/` · `package-lock.json` · `str` · ملفٌّ باسمٍ مشوّه) — **لم تُمَسّ**.

**`newktra` = `8d793abb`** = `origin/newktra` (مدفوع).
**الإنتاجُ = `247fb7f5`** — أي أن `#283/ج` و`#287` **مدموجان ولم يُنشَرا بعد**.

**أوّلُ عملٍ في الجلسة القادمة — النشر (بالترتيب):**
1. `gh run list --branch newktra --limit 1` ⇒ إن كان على `8d793abb` أخضرُ فامضِ؛ وإن كان فاشلاً اقرأ `gh run view <id> --log-failed` وأصلح. (كان قيدَ التشغيل عند التوقّف: `43161730564`.)
2. على الخادم: `git fetch` ← `git merge origin/newktra` ← `git diff origin/newktra` **فارغ**.
3. `venv/bin/python manage.py check` و`makemigrations --check` ⇒ لا تغيير.
4. `showmigrations accounting_office` ⇒ المتوقَّع `[ ]` لـ`0021_officeclient_delivered_on` و`0022_book_rates_and_period_lock`. **وراجع `0022`**: فيها `RunPython(seed_rates, unseed_rates)` — `update_or_create` للائحة النسب والسقوف، وعكسُها يحذف صفوفَها وحدها. ليست `RemoveField`/`DeleteModel`/`RunSQL`، والبياناتُ منقولةٌ عن بحث `#269` حرفاً بحرف.
5. **نسخةٌ احتياطية أوّلاً** (`mysqldump` ببيانات `.env` إلى `/root/backups/`).
6. `migrate` ← `npm run build` + `rsync` (الواجهةُ تغيّرت: شارةُ نتيجة الفترة وتنبيهُ السقوف في تبويب الدفتر) ← `systemctl restart ktra.service` ← `is-active`/`NRestarts=0` ← ثلاثُ `curl` 200.
7. `gh issue close 287` بتعليق النشر · وتحديثُ `acct-office-build.md` و`progress.md`.

**ما في `8d793abb` ولم يُنشَر بعد:**
- **`#283/ج`:** تذكيرُ «اللي عليه» بعد الاستحقاق بدرجتَي **+3 و+7** بحدِّ **مرّتين** (السقفُ من السجلّ)، والدفعُ الجزئيّ لا يوقفه والنصُّ يذكر الباقي · **كشفٌ شهريّ يوم 1** مدموجٌ في بندٍ واحد مع رسالة الفاتورة (يُفضَّل بندُ «اللي عليه») · **حجبُ التسليم** بإعداد `delivery_hold_unpaid` (مطفأٌ افتراضاً، يُبقي الردَّ بايتاً ببايت) يُظهر «لم يُسلَّم بعد» ويردّ تعليمَ التسليم **400**، و`delivered_on` على الزبون. **العلامةُ في رأس ملفّ الزبون** لأن `OfficeClientAccount.tsx` لم يكن في شجرته.
- **`#287`:** لائحةُ نسب المنصّة لكل نظام (قيمة · مصدر · مستوى دليل · سريان · «راجع») وتعديلُ المكتب بسجلٍّ إلحاقيّ · نسبتا ض.ق.م والدخل على الحساب وعلى السطر (بسببٍ وإعدادِ سماح) · **الإهلاكُ بالقسط الثابت** (أثاث 10% PS / 6% IL) · **مبلغُ ض.ق.م من الدفتر** محسوباً ومعدَّلاً وبتأكيدٍ ثانٍ · **إقفالُ الفترة** عند «انقدّم» وفتحُها بسببٍ للمدير · **نتيجةُ الفترة** بألوان الإشعار (ربحٌ أخضر · خسارةٌ حمراء · رماديٌّ بحدّ الإشعارات) في ملفّ الزبون وإشعار الدفع · **تنبيهُ السقوف السنوية** تنبيهاً لا رفضاً. **سبعُ صفوفٍ بقيت «راجعاً» بقيمةٍ فارغة، وسبعُ طفراتٍ أثبتت أن الاختبارات تعضّ.**

**ما بقي على التذاكر المفتوحة:** `#287` تُغلق بعد النشر · **`#286/ج`** (توليدُ بنود الحركة من مبلغ الورقة وضريبتها وطرفها — **يحتاج قرار المالك**، وهي الوحيدةُ في الدفتر التي بلا قرار) · `#290` (تصديرُ بيانات المكتب وبيانُ الزباين) · `#291` **آخراً**. وما بقي غيرَ مبنيٍّ وأُعلِن: شاشاتُ استيراد/إعدادات/قيدٍ يدويّ لدفتر الزبون · محرّرُ لائحة النسب · محرّرُ نسب الحساب في شجرة الزبون · الإهلاكُ ونتيجةُ الفترة في Excel/الطباعة.

**دَينٌ تقنيّ مسجَّل (لا يُنسى):** `client_due` لا يرى الضريبة (**تذكرةٌ لازمة**) · التكميليةُ لا تُرحَّل · ورقةُ إجمالي صفرٍ بلا قيد · `Greatest(remaining,0)` يُخفي تخصيصاً زائداً · `Cheque` بلا فرادةٍ على `(tenant, cheque_number)` · «مصاريفُ معترف بها» في نتيجة الفترة فُهمت مصاريفَ الدفتر لا مصاريفَ مقبولةً ضريبياً (تحتاج عين المالك) · صفٌّ مكرَّرٌ في جدول «أهم الملفات» بـ`accounting_office.md` و`KIND_TEXT` معرَّفٌ مرّتين · `requirements.local.txt` يحتاج `openpyxl==3.1.5` · اختبارُ `after_sales/tests/test_shop_days_extension.py` هشٌّ بساعة الحائط · أربعةُ فشلٍ بيئيٍّ في المجموعة الكاملة تقرأ `.agents/worktrees/**`.


## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-12 06:50 — خمسُ تذاكرَ مغلقة، واثنتان في التنفيذ)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — إن ظهر disarmed فـ`update_goal action=resume`.

**الإنتاج (متحقَّق 06:50):** الخادم `247fb7f5` · كلُّ الهجرات مطبَّقة (`accounting_office` حتى `0020`، `docshare` حتى `0010`) · `ktra.service` active و`NRestarts=0` · ثلاثُ `curl` 200 · آخرُ نسخةٍ احتياطية `ktra-before-289-20261112-*` (27MB).
**`newktra` = `cd6780a7`** (مدفوع) · CI أخضر `43155045255`.

| التذكرة | الحالة |
|---|---|
| `#282` أتعاب/فاتورة ورقيّة | ✅ **مغلقة** (أ١ · أ٢/١ · أ٢/٢ · وقيودُ الدفاتر الأربعة) |
| `#283` الدفعات وكشف الحساب | ✅ **مغلقة** (أ · ب) |
| `#284` القيد التلقائي | ✅ **مغلقة** (أ منشور · ب نُقل إلى `#282` ونُفِّذ) |
| `#288` دفتر الزبون ٣ | ✅ **مغلقة** (أ · ب-١ · ب-٢) — **يبقى شاشاتُ الاستيراد/الإعدادات/القيد اليدوي** |
| `#289` لوحة صاحب المكتب | ✅ **مغلقة** |
| `#287` النسب والإهلاك والإقفال | 🔧 **في التنفيذ** — `.agents/worktrees/acct-287` (`attempt-842e2e21`) |
| `#283/ج` تذكير المتأخّر والكشف الشهري وحجب التسليم | 🔧 **في التنفيذ** — `.agents/worktrees/acct-283d` (`attempt-ed152b61`) |
| `#286/ج` بنودُ الحركة من الورقة | ⏸ **يحتاج قرار المالك** في التوليد |
| `#290` · `#291` | ⏸ تنتظر (`#291` آخراً) |

**أوّلُ عملٍ في الجلسة القادمة:** راجع `git -C .agents/worktrees/acct-287 status` و`acct-283d`، ثم بوّاباتُ كلٍّ منهما ⇒ دمجٌ ⇒ `importlinter` و`npx tsc && npm run build` **بعد الدمج** ⇒ دفعٌ ⇒ CI ⇒ نشرٌ (الهجراتُ الجديدةُ من `#287` ستكون `0021+`).

**قاعدتان دفعتهما هذه الجولة ثمناً:** (١) **لا `git add -A`** — ضمّ ملفات المالك مرّتين. (٢) **بعد كل دمجٍ يدويّ: `importlinter` للخلفيّ و`tsc`+`npm run build` للواجهة قبل الدفع** — CI كشف مرّتين ما لم يكشفه `npm test`.

**دَينٌ تقنيّ مسجَّل:** `client_due` لا يرى الضريبة (**تذكرةٌ لازمة**: «الضريبة في اللي عليه») · التكميليةُ لا تُرحَّل · ورقةُ إجمالي صفرٍ بلا قيد · `Greatest(remaining,0)` يُخفي تخصيصاً زائداً · نسبةُ الضريبة غيرُ مؤرَّخة (لائحةُ النسب في `#287` تعالجها لدفتر الزبون لا لدفتر الشركة) · `Cheque` بلا فرادةٍ على `(tenant, cheque_number)` · صفٌّ مكرَّرٌ في جدول «أهم الملفات» بـ`accounting_office.md` و`KIND_TEXT` معرَّفٌ مرّتين · `requirements.local.txt` يحتاج سطر `openpyxl==3.1.5` · اختبارُ `after_sales/tests/test_shop_days_extension.py` هشٌّ بساعة الحائط · أربعةُ فشلٍ بيئيٍّ في المجموعة الكاملة تقرأ `.agents/worktrees/**`.


## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-12 03:30 — أربعُ تذاكرَ مدموجة، النشرُ هو الخطوة)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — إن ظهر disarmed فـ`update_goal action=resume`.

**`newktra` = `09b6a43c`** (مدفوع). **الإنتاجُ لم يُنشَر بعد** — آخرُ منشورٍ هو `804afd5d` (`#285` + `#288/أ` + `#283/أ`).

| التذكرة | الحالة | الشجرة/الالتزام |
|---|---|---|
| `#284/أ` القيدُ التلقائي | ✅ مدموجٌ (`ed7b738e`) — ينتظر النشر: هجرة `0015_office_client_partner` | `acct-284` على `f0c51c51` |
| `#282/أ٢-١` فاتورةُ الأتعاب الورقية | ✅ مدموجٌ (`c5aa2e2a`) — ينتظر النشر: `0016_fee_invoices` + `docshare.0008` | `acct-282b` على `e0c061a5` |
| `#283/ب` إشعارُ القبض وكشفُ الحساب | ✅ مدموجٌ (`b2c29bb2`) — ينتظر النشر: `0017_fee_statement` + `docshare.0009` | `acct-283b` على `a0c72850` |
| `#288/ب-١` مستخرجاتُ الدفتر | ✅ مدموجٌ (`54cfe3c6`) — ينتظر النشر: `0018_client_book_report` + `docshare.0010` + `openpyxl` | `acct-288b` على `d7d7e4b0` |
| `#282/أ٢-٢` شاشةُ المسودّات | ⏸ لم يبدأ | — |
| `#288/ب-٢` القيدُ اليدوي والافتتاحية والاستيراد وض.ق.م | ⏸ لم يبدأ | — |
| `#286/ج` بنودُ الحركة من الورقة | ⏸ لم يبدأ (قرارُ المالك في التوليد) | شجرةُ `acct-286c` جاهزة |
| `#283/ج` تذكيرُ «اللي عليه» والكشفُ الشهري وحجبُ التسليم | ⏸ لم يبدأ | — |
| `#287` · `#289` · `#290` · `#291` | ⏸ تنتظر | — |

**أوّلُ عملٍ — النشر (بإجراء المهارة، وCI أخضر على `09b6a43c` شرطٌ):**
1. `gh run list --branch newktra --limit 1` ⇒ أخضر (الفشلُ البيئيُّ المعروف وحده لا يوجد في CI لأنه لا يشغّل الماسحات على شجرات).
2. على الخادم: `git fetch` ← `git merge origin/newktra` ← `git diff origin/newktra` **فارغ**.
3. `venv/bin/pip install -r requirements.txt` (**`openpyxl` جديد**) ← `venv/bin/python manage.py check` و`makemigrations --check`.
4. `venv/bin/python manage.py showmigrations accounting_office docshare` ⇒ المتوقّع `[ ]` لـ`0015`–`0018` و`0008`–`0010`؛ ومراجعةُ الهجرات: **كلُّها `CreateModel`/`AddField`/`AlterField`** (لا `RemoveField` ولا `DeleteModel` ولا `RunSQL`).
5. **نسخةٌ احتياطية:** `mysqldump` ببيانات `.env` إلى `/root/backups/ktra-before-283b-<ts>.sql`.
6. `venv/bin/python manage.py migrate` ← `npm run build` ثم `rsync -a --delete --exclude "/s/" --exclude "/media/" dist/ /var/www/ktra-pro.tech/` (الواجهة تغيّرت: تبويبُ الأتعاب وشاشةُ التقارير).
7. `systemctl restart ktra.service` ← `is-active` و`NRestarts=0` ← ثلاثُ `curl` 200.
8. `gh issue close 284` · `gh issue close 283` (الجزءان أ وب) · تعليقُ حالةٍ على `#282` (بقي أ٢/٢) و`#288` (بقي ب-٢).
9. تحديثُ `acct-office-build.md` (نشرُ هذه الأربع) و`progress.md`.

**دَينٌ تقنيّ مسجَّل (لا يُنسى):** `Greatest(remaining,0)` يُخفي تخصيصاً زائداً · مجموعتا `ledger` تتشاركان `page` · نسبةُ الضريبة غيرُ مؤرَّخة · لا عملةَ على `FeeDraft` · `vat` يحتاج مصدرَ نسبة · `Cheque` بلا فرادةٍ على `(tenant, cheque_number)` (**قرارُ مالك**) · إشعارُ القبض ببندٍ واحدٍ لكل زبونٍ في اليوم (فدفعتان في يومٍ تُطوى في بندٍ يذكر رقمَي الإشعار) · عضوٌ مقنَّعٌ يُنشئ رابطَ تقريرٍ يفتحه الزبونُ بالمبالغ كاملة (سلوكُ `payment_notice` نفسِه) · `requirements.local.txt` يحتاج سطر `openpyxl==3.1.5` · اختبارُ `after_sales/tests/test_shop_days_extension.py` هشٌّ بساعة الحائط · **درسٌ مكرَّر: لا `git add -A` في هذا المستودع** (ضمّ ملفات المالك مرّتين).

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-12 00:25 — توقّفٌ بطلب المالك للكومباكت)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — إن ظهر disarmed فـ`update_goal action=resume`.

**لا عاملَ حيّ الآن:** أوقفتُ محاولةَ تصليح `#284/أ` في منتصفها (`attempt-ef49a678`) بطلب المالك.

**الإنتاج (متحقَّق):** الخادم `804afd5d` · `#285` + `#288/أ` + `#283/أ` منشورة · ثلاثُ `curl` 200 · `NRestarts=0` · آخرُ نسخةٍ احتياطية `ktra-before-283-20261111-205351.sql`.
**`newktra` = `bec704f8`** (مدفوع). CI على `4de1710f` (دمج 288/أ+283/أ) **أخضر**؛ وCI على `bec704f8` (وثائقٌ فقط) بقي في الطابور عند التوقّف.

**⚠️ عطلٌ بيئيّ حاسم: خطّا Anthropic ساقطان.** بعد ستّ محاولاتٍ بـ`429` جاء الرفضُ النهائي `403 permission_error — OAuth authentication is currently not allowed for this organization`. أي أنّ **`المراجع` (Opus) و`مصحح ٢` (Sonnet) غيرُ قابلَين للاستعمال الآن**، والمراجعاتُ المستقلّةُ متعذّرة. **قرارٌ للمالك:** إمّا إصلاحُ مصادقة المؤسّسة، أو الإذنُ بإجراء جولات المراجعة على الفواعلي (فقدانُ الاستقلال) أو بالاعتماد على قراءتي أنا + البوّابات. **لم أُبدّل الخطّ من تلقاء نفسي.**

**الشجرةُ الرئيسية نظيفة** إلا العناصرَ الخمسةَ المعروفة غيرَ المتتبَّعة (`.agy-design-refs/` · `marketing/` · `package-lock.json` · `str` · ملفٌّ باسمٍ مشوّه).

| التذكرة | الحالة الدقيقة | الشجرة/الالتزام |
|---|---|---|
| `#285` إشعار الدفع | ✅ **منشورة ومغلقة** | `1db4cbd5` (الخادم `31bd0dc6`) |
| `#288/أ` تقارير الدفتر | ✅ **مدموجٌ ومنشور** · بقي (ب): الشاشات والمستخرجُ والاستيراد · و`vat` مؤجَّلٌ بقرار | `acct-288a` → `30451077` |
| `#283/أ` الدفعات | ✅ **مدموجٌ ومنشور** · بقي (ب): إشعارُ القبض وكشفُ الحساب · (ج): التذكيرُ والكشفُ الشهري وحجبُ التسليم | `acct-283` → `4de1710f` |
| `#284/أ` القيد التلقائي | 🔧 **تنفيذٌ كاملٌ (`1783f721`) + تصليحٌ غيرُ مُلتزَم في الشجرة** — أوقفتُه منتصفَ تحقّق الطفرات | `.agents/worktrees/acct-284`، فرعُه `1783f721` + تعديلاتٌ غيرُ مُلتزَمة في 8 ملفات |
| `#282/أ٢-١` فاتورة الأتعاب | ⛔ **عالقٌ**: مراجعتُه الثانية أعادت **٩ موانع**، والتصليحُ لا يستطيع البدء (Anthropic ساقط) | `.agents/worktrees/acct-282b` على `5544963e` نظيف |

**أوّلُ عملٍ في الجلسة القادمة — بالترتيب:**
1. **قرارُ المالك في عطل Anthropic** (أعلاه) — يوقف كلَّ مراجعةٍ مستقلّة.
2. **`#284/أ`:** اقرأ `git -C .agents/worktrees/acct-284 status` و`diff`؛ التصليحُ المطلوبُ مكتوبٌ حرفياً في موجز `delegation_correct` على `attempt-060ec22a` (حسابُ الديون المعدومة `5290` يُنشأ عند الحاجة · حذفُ `"bank"` · ثلاثةُ نظافة). ثم بوّاباتٌ ⇒ مراجعةٌ ⇒ دمجٌ (`0015_office_client_partner`).
3. **`#282/أ٢-١`:** التسعةُ موانع في موجز الجولة الثانية (أخطرها: تعليقُ `{# #}` يُطبع على الورقة · ثلاثةُ اختباراتٍ تسقط بين منتصف الليل والثانية · مفتاحُ البند ليس لكل ورقة · إلغاءُ فاتورةٍ لها تصحيحٌ حيّ) ⇒ تنفيذٌ ⇒ مراجعةٌ ⇒ **دمجٌ مع إعادة ترقيم `0014_fee_invoices` إلى `0016`** (`dependencies` على `0015_office_client_partner`) ⇒ نشرٌ ثانٍ.
4. ثم **#286/ج** ∥ **#282/أ٢-٢** ∥ **#288/ب** ⇒ #287 · #289 · #290 · **#291 آخراً**.

**دَينٌ تقنيّ مسجَّل (لا يُنسى):** `Greatest(remaining,0)` يُخفي تخصيصاً زائداً (#283) · مجموعتا `ledger` تتشاركان `page` · نسبةُ الضريبة غيرُ مؤرَّخة · لا عملةَ على `FeeDraft` منذ أ١ · `vat` يحتاج مصدرَ نسبة · `Cheque` بلا فرادةٍ على `(tenant, cheque_number)` (**قرارُ مخططٍ للمالك**) · اختبارُ `after_sales/tests/test_shop_days_extension.py::test_start_is_the_earlier_…` **هشٌّ بساعة الحائط** (يسقط بين 23:00 و00:30 بتوقيت الخليج بسبب فرق التوقيت الصيفيّ) · ازدواجُ صفوفٍ في جدول ملفّات `accounting_office.md` وعمودُ «أسطر» قديمٌ في `accounting.md`.

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-11 22:40 — مدموجان بانتظار CI والنشر · `#282/أ٢-١` ينتظر خطّ Anthropic)

**`newktra` = `4de1710f`** (دمجُ `acct-288a` ثم `acct-283`). **الإنتاجُ ما زال `31bd0dc6`** (#285).
- **`#288/أ`** مدموجٌ (`30451077`، CI أخضر `43093824854`… **راجع أحدثه**) — تقاريرُ دفتر الزبون السبعة، بلا هجرة.
- **`#283/أ`** مدموجٌ (`4de1710f`) — دفترُ الدفعات و«اللي عليه»، هجرةُ `0014_fee_payments` (أربعةُ `CreateModel`).
- **CI على `4de1710f`** قيد التشغيل عند كتابة هذه النقطة.
- **`#282/أ٢-١`**: الالتزام `5544963e` في `.agents/worktrees/acct-282b`، مراجعتُه الثانية أعادت **تسعة موانع** (أخطرها: تعليقُ `{# #}` يُطبع على الورقة · ثلاثةُ اختباراتٍ تسقط كل ليلة · مفتاحُ البند ليس لكل ورقة · إلغاءُ فاتورةٍ لها تصحيحٌ حيّ)، والقراراتُ كلُّها مكتوبةٌ في موجز المحاولة. **خطّا Anthropic (Opus وSonnet) يردّان 429 الآن** — أعِد الإرسال بعد فاصل.

**الخطوة التالية بالترتيب:** (١) CI أخضر على `4de1710f` ⇒ نشرُ `#288/أ`+`#283/أ` بنسخةٍ احتياطية قبل `0014_fee_payments`، ثم `npm run build`+`rsync` إن تغيّرت الواجهة (لم تتغيّر: كلُّها خادم). (٢) إنهاءُ `#282/أ٢-١` (تصليح ٢ على Sonnet) ⇒ مراجعةٌ ثالثة ⇒ دمجٌ مع **إعادة ترقيم `0014_fee_invoices` إلى `0015`** (`dependencies` على `0014_fee_payments`) ⇒ نشرٌ ثانٍ. (٣) ثم #284 (يحتاج #283 ✅) ∥ #286/ج ∥ #282/أ٢-٢ ⇒ #288/ب · #287 · #289 · #290 · **#291 آخراً**.

**دَينٌ تقنيّ مسجَّل:** `Greatest(remaining,0)` يُخفي تخصيصاً زائداً · مجموعتا `ledger` تتشاركان `page` · نسبةُ الضريبة غيرُ مؤرَّخة (جدولٌ منصّيّ) · لا عملةَ على `FeeDraft` منذ أ١ · `vat` يحتاج مصدرَ نسبة · تعليقُ `.fi-foot-gap` لصفحةٍ واحدة.

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-11 20:20 — ثلاثُ محاولاتٍ جارية)

**الإنتاج:** `31bd0dc6` (= `#285` منشورة) · `newktra` = `9096a53a` · `#285` مغلقة، وتعليقا حالةٍ على `#282` و`#286`.

**الجارية (لا تلمسها):**
| التذكرة | المحاولة | الشجرة | الحالة |
|---|---|---|---|
| `#282/أ٢-١` فاتورة الأتعاب الورقية + `docshare` + الترقيم | `attempt-0dc8d27d…` | `.agents/worktrees/acct-282b` | تنفيذٌ أوّليّ (تجاوز الساعتين) |
| `#288/أ` تصليحُ ستّة موانع (الميزانية رصيدٌ تراكميّ · `cash` على الأصول · `receivables` بالطرف · قَصُّ فترة العهد البسيط · سطر `CHANGELOG` · اختبار الترخيص) | `attempt-da6d4d4d…` | `.agents/worktrees/acct-288a` | جولة تصليح ١ |
| `#283/أ` تصليحُ خمسة موانع (المرتجعات في سطر العلم · `state=unpaid` · اختبار العدّاد · اختبار «اعتمد الكل» · عدد النماذج) + قرارُ `allocations: []` + قفلُ صفّ الدفعة | `attempt-46688630…` | `.agents/worktrees/acct-283` | جولة تصليح ١ |

**التزامات الفرعين:** `acct-288a` = `d5c1868a` · `acct-283` = `97a62de4` · `acct-282b` = بلا التزامٍ بعد.

**بوّابات تحقّقتُ منها بنفسي:** `#288/أ` ⇒ 945 ناجح/2 متخطّى/659 مجموعة فرعية · `makemigrations` بلا تغيير · المجموعة الكاملة 7575 ناجح وفشلٌ واحد هو `test_throttle_guards` البيئيّ · `importlinter` 3 kept · `git diff --check` نظيف. **ولم أتحقّق من `#283/أ` بنفسي بعد** (قرأتُ الكود وحدَه) — البوّاباتُ تنتظر نهاية تصليحه.

**دَينٌ تقنيّ مسجَّل:** `next_receipt_number` قد يُجمِد نادراً عند أوّل ثلاثة إشعاراتٍ متزامنة في السنة (لا أرقامَ مكرّرة — `get_or_create` يلتقط التصادم) · `Greatest(remaining,0)` يُخفي تخصيصاً زائداً · مجموعتا `ledger` تتشاركان `page` · `report_payload` يستورد اسمين مخصّصين من `client_books`.

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-11 19:15 — **#285 منشورةٌ ومغلقة**)

**نُشر #285 على الإنتاج:** الخادم `31bd0dc6` · CI أخضر `43060894120` · نسخة `ktra-before-285-20261111-170904.sql` (27MB) · هجرة `docshare.0007` طُبِّقت · `NRestarts=0` · ثلاث `curl` 200. **التذكرة مغلقة**، وتحديثُ حالةٍ أُضيف على #282 و#286.

**محاولتان جاريتان الآن (لا تلمسهما):**
- `attempt-8ed23379-a8f1-477a-932e-d991b38f747b` = **#283/أ** (دفتر الدفعات + دالة «اللي عليه» + API) في شجرة `.agents/worktrees/acct-283` على الفرع `acct-283`.
- `attempt-0dc8d27d-1873-411d-80ba-7b900ff7c41f` = **#282/أ٢-١** (فاتورة الأتعاب الورقية + نوع `docshare` + الترقيم + الإشعار الدائن) في `.agents/worktrees/acct-282b` على `acct-282b`.

**توقّعات الدمج:** كلاهما يضيف هجرةً برقم `0014_*` (`0014_fee_payments` و`0014_fee_invoices`) — عند الدمج يبقى للفرع الأول رقمُه ويُعاد ترقيمُ الثاني إلى `0015` مع `dependencies` على الأول. وكلاهما يلمس `accounting_office/urls.py` و`views.py` ⇒ تعارضٌ نصّي متوقَّع يُحلّ بيد.

**بعد دمجهما:** #283/ب (إشعار القبض وكشف الحساب ورابطهما) · #283/ج (تذكير «اللي عليه» + كشف شهري + حجب التسليم) · #282/أ٢-٢ (شاشة «المسودّات» وتبويب «الحساب») · #286/ج.

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-11 19:00 — توقّفٌ للكومباكت بطلب المالك)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — إن ظهر disarmed فـ`update_goal action=resume`.

**لا عاملَ حيّ ولا محاولةَ جارية ولا مهمةَ خلفية.** الشجرةُ الرئيسية نظيفةٌ إلا العناصرَ الخمسةَ المعروفة غيرَ المتتبَّعة.

**الحالة الدقيقة:**
- `newktra` = **`1db4cbd5`** = `origin/newktra` (مدفوع).
- **الإنتاج ما زال على `944b8921`** (#282/أ١). **`#285` مدموجٌ في `newktra` ولم يُنشَر بعد.**
- CI على `1db4cbd5` لم يُراقَب (لم أبدأ مراقبتَه).

**أوّلُ عملٍ: نشرُ #285.** التسلسل على الخادم:
1. `gh run watch <run-id>` على `1db4cbd5` حتى الأخضر (‏`gh run list --branch newktra --limit 1`).
2. `git fetch` ← `git merge origin/newktra` ← `git diff origin/newktra` يجب أن يكون **فارغًا**.
3. `venv/bin/python manage.py showmigrations docshare` ⇒ المتوقَّع `[ ] 0007_payment_notice_doc_type`، ومراجعةُ الملف: **`AlterField` وحده**.
4. **نسخةٌ احتياطية:** `set -a ; . .env ; set +a ; mysqldump -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" > /root/backups/ktra-before-285-$(date +%Y%m%d-%H%M%S).sql`.
5. `venv/bin/python manage.py migrate`.
6. `cd frontend_v2 ; npm run build` ثم `rsync -a --delete --exclude "/s/" --exclude "/media/" dist/ /var/www/ktra-pro.tech/` (تغيّر `docShareApi.ts` و`accountingOffice.ts`).
7. `systemctl restart ktra.service` ← `is-active` و`NRestarts=0` ← ثلاثُ `curl` 200 ← `tail` سجلّ gunicorn.
8. `gh issue close 285` بتعليق النشر، ثم تحديثُ `acct-office-build.md`/`runs.md`/`handoff.md`.
**ملاحظة:** `python` غيرُ موجودٍ على الخادم — استعمل **`venv/bin/python`**. ولا `push` من الخادم.

**بعده:** **#283 الدفعات** (جاهزة: #282/أ١ منشور) ∥ **#286/ج** (توليدُ بنود الحركة من الورقة — قرار مالك) ∥ **#282/أ٢** — ثم #284 · #288 · #287 · #289 · #290 · **#291 وحدها آخراً**.

**ملاحظاتٌ مفتوحة من #285 (مسجّلة في `docs/modules/accounting_office.md` §قيود معروفة):** الإشعارُ عربيٌّ دائمًا ولو كانت لغةُ الجهة عبريّة (تذكرةٌ لاحقة) · رقمٌ مختلفان في رسالةٍ واحدة («مبلغ مستحقّ» #281 و«المجموع» #285) · لا كلمةَ عند `total == 0` · قيمةٌ احتياطية `.get(client_id, 0)` تخالف افتراضَ السجلّ (10) · `tax_file_number` في الحمولة ولا يظهر على الورقة · ثمنُ التمديد: رابطُ تاريخ 15/3 يعرض إشعار 15/4 بعد التمديد.

**أخطاءُ المنسّق في هذه الجولة (مسجّلة):** (أ) دمجُ `ARCHITECTURE.md` بحذف نطاقِ سطورٍ أخذ صفَّ `accounting` معه، و`sync_docs` أنشأ صفًّا فارغًا (`—`) بلا أن تكشفه بوّابة — أُصلح `1db4cbd5`. (ب) أمرُ فرقٍ بنقطتين بدل ثلاث في موجز مراجعة #285 — نبّه عليه المراجع.
## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-11 17:30 — توقّفٌ بطلب المالك للكومباكت)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — إن ظهر disarmed فـ`update_goal action=resume`.

**لا عاملَ حيّ ولا محاولةَ جارية ولا مهمةَ خلفية الآن.** الشجرةُ الرئيسية نظيفةٌ إلا العناصرَ الخمسةَ غيرَ المتتبَّعة المعروفة.

**الإنتاج (متحقَّق 17:15):** الخادم `944b8921` · `newktra` = `647cc36a` · `git diff origin/newktra` على الخادم فارغ · ثلاثُ `curl` 200 · `NRestarts=0`.
الهجراتُ المطبَّقة: `0011` ← `0013_appointments` ← `0012_fees` (بهذا الترتيب: `0012` تعتمد `0013` لأنها لحقتها).

**التذاكر:**
| التذكرة | الحالة | الالتزام |
|---|---|---|
| #280 · #286/أ · #286/ب · #281 · #282/أ١ | ✅ منشورة | آخرها `def37caa` (282) و`aa1ad5a7` (281) |
| #281 | **مغلقة** | — |
| #282 | منشورٌ أ١ · **أ٢ لم يبدأ** | `def37caa` |
| #286 | أ+ب منشوران · **ج لم يُبنَ** | `a2c91ef3` |
| **#285 إشعار الدفع** | 🔧 **منفَّذٌ ومُلتزَم، لم يُراجَع** | `2c684882` في `.agents/worktrees/acct-285` |
| #283 · #284 · #287 · #288 · #289 · #290 · #291 | لم تبدأ (283 صارت جاهزةً بنشر 282) | — |

**أوّلُ عملٍ في الجلسة القادمة — #285:**
1. `git -C .agents/worktrees/acct-285 log --oneline -1` ⇒ المتوقَّع `2c684882`، و`git status` نظيف.
2. البوّاباتُ بنفسي (لا أثق بتقرير المنفّذ): `pytest accounting_office/tests docshare/tests core/tests/test_shell_manifest.py -n auto` · `npm test` · `tsc` · `build` · `makemigrations --check` بـ`KTRA_MIGRATIONS_DB` · `test_docs_freshness` · `git diff --check`.
3. **مراجعة ١ على المراجع** (قراءةً فقط) على `git diff 647cc36a 2c684882`.
4. ثم جولةُ تصليحٍ إن لزمت ← دمجٌ ← CI ← نشر **بنسخةٍ احتياطية** (هجرة `docshare/0007` `AlterField`) ← إغلاق #285.

**بعدها:** #283 الدفعات (المسار الحرج) ∥ #286/ج (توليدُ بنود الحركة من الورقة — قرار مالك) ∥ #282/أ٢ — ثم #284 · #288 · #287 · #289 · #290 · **#291 وحدها آخراً**.

**ملاحظاتٌ مفتوحة أبلغ عنها العمال وتحتاج قراراً (مسجّلة كما هي):**
- **#285:** مبالغُ `items[].notice` غيرُ مقنَّعةٍ لغير من يرى المبالغ — استثناءٌ **ثانٍ** من قاعدة القناع بعد استثناء `body`؛ ويحتاج قراراً صريحاً. · إنشاءُ صفّ مشاركةٍ في مسار قراءةٍ محصورٌ الآن بمن يملك `office.clients.write` لكن بلا قيد فرادةٍ على `(tenant, doc_type, doc_id)`. · الإشعارُ عربيٌّ دائماً ولو كانت لغةُ الجهة عبريّة. · `paymentNoticeTone` بلا شاشةٍ تستهلكها.
- **#282/أ١:** الإيقافُ مقصورٌ على طريقة «اشتراك» (زبونُ `per_service` الموقوف قد تُولَّد له مسودةٌ فيها خدماتُه) · مساراتُ التفصيل بلا `retrieve` ⇒ `DELETE` عليها 404 لا 405 · `0012` تعتمد `0013` (رسمٌ صحيح، ترقيمٌ معكوس).
- **#281:** مبلغُ نصّ الرسالة يمرّ بلا قناع `office.amounts.view` (استثناءٌ موثَّقُ ومُختبَر).
## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-11 17:20)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — إن ظهر disarmed فـ`update_goal action=resume`.

**الإنتاج (متحقَّق 17:15):** الخادم `944b8921` · `newktra` = `def37caa` · `git diff origin/newktra` على الخادم **فارغ** · ثلاثُ `curl` 200 · `NRestarts=0`.
**منشورٌ ومُغلَق:** #271–#280 · **#281** (`aa1ad5a7`، هجرة `0013`، نسخة `ktra-before-281-…-144157.sql`).
**منشورٌ والتذكرةُ مفتوحة:** #286/أ+ب (`a2c91ef3`، بانتظار بندها «ج») · **#282/أ١** (`def37caa`، هجرة `0012`، نسخة `ktra-before-282-…-151434.sql`، وبقيت **أ٢**).
**الهجراتُ المطبَّقة على MySQL:** `0011` ← `0013_appointments` ← `0012_fees` (هكذا: `0012` تعتمد `0013` لأنها لحقتها).

**غيرُ مُلتزَم في `acct-285`:** إشعار الدفع — جلستُه انتهت بتنفيذٍ كاملٍ وبوّاباتٍ يدّعي المنفّذ خضرتَها، **ولم تُراجَع ولم أتحقّق منها**. أولُ عملٍ في الجلسة القادمة: `delegation_review` (أو قراءةُ `git status`/`git diff` في الشجرة) ← البوّاباتُ بنفسي ← **مراجعة ١ على المراجع** ← جولةُ تصليحٍ إن لزمت ← دمجٌ ونشر (هجرةٌ إضافيّة إن وُجدت + نسخةٌ احتياطية).

**الترتيبُ المقترح بعد ذلك:** **#283 الدفعات** (المسار الحرج: 282 ✅) ∥ **#286/ج** (توليدُ بنود الحركة من الورقة — قرار مالك) ∥ **#282/أ٢** (فاتورةُ الأتعاب الورقية) — ثم #284 · #288 · #287 · #289 · #290 · **#291 وحدها آخراً**.

**قواعدُ ثابتة تكرّرت هذه الجلسة:**
- `python` غيرُ موجودٍ على الخادم — **`venv/bin/python`**.
- بوابةُ الهجرات تحتاج `KTRA_MIGRATIONS_DB` وإلا فهي اسميّة.
- تعارضُ هجراتٍ عند الدمج: التذكرةُ اللاحقةُ تُوجّه `dependencies` هجرتَها إلى السابقة (لا ترقيمَ جديد).
- تعارضٌ نصّيّ «كلا الطرفين أضاف» في `docs/*` و`utils/*`: يُحلّ بيدٍ لا آليًّا — الجمعُ الأعمى كسر بنية TS في هذه الجلسة.
- خطُّ المراجع (Opus) قد يردّ `429`؛ أعد الإرسال بعد فاصل، ولا تُبدّل الخطّ بلا قرار المالك.
- نجاحُ `npm test` لا يعني أن الشاشة تعمل: `@types/react` غائبٌ و`tsc` لا يفحص JSX.

**لا عاملَ حيّ الآن ولا محاولةَ جارية بعد إنهاء `acct-285`.** الشجرةُ الرئيسية نظيفةٌ إلا العناصرَ الخمسةَ غيرَ المتتبَّعة المعروفة.

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-11 16:45)

**الهدف:** `goal-e8d8b3d1-9118-43c6-93e3-5f0c07502bee` — إن ظهر disarmed فـ`update_goal action=resume`.

**الإنتاج (متحقَّق):** `988326b6` مدموجٌ ومنشور · #281 **منشورة ومغلقة** (هجرة `0013` مطبَّقة، نسخة `ktra-before-281-20261111-144157.sql`) · #286/ب منشورة (`266e0033`) والتذكرةُ مفتوحة لبند «ج» · #280 و#286/أ منشورتان · ثلاثُ `curl` تردّ 200 · `NRestarts=0`.

**جارٍ الآن:** `#282/أ١` **تصليح ٢ على مصحح ٢** (`attempt-a3860476…`، `acct-282`) لمانعٍ واحد: `_covered_before` تُفوتر العائدَ بعد إنهاءٍ شهراً كاملاً (المطلوب: 220.00 لا 310.00). بعده: **مراجعة ٣** ← البوّابات ← دمج ← نشر (هجرة `0012_fees` تتطلّب نسخةً احتياطية).

**التالي بعد #282:** مراجعةُ #282/أ١ النهائية ⇒ نشر ⇒ **#283 الدفعات** (المسار الحرج) ∥ **#286/ج** (توليدُ بنود الحركة من الورقة — قرار مالك) ∥ **#285 إشعار الدفع** (ينتظر #281 ✅ فصار جاهزاً). ثم #284 · #288 · #287 · #289 · #290 · **#291 وحدها آخراً**.

**ملاحظاتٌ للجلسة القادمة:**
- `python` غيرُ موجودٍ على الخادم — استعمل **`venv/bin/python`**.
- بوّابة الهجرات تحتاج `KTRA_MIGRATIONS_DB` وإلا فهي اسميّة.
- تعارضُ هجراتٍ بين تذكرتين: التي تلحق تُوجّه `dependencies` إلى هجرة السابقة.
- خطُّ المراجع (Opus) قد يردّ `429` — أعد الإرسال بعد فاصل، ولا تُبدّل الخطّ بلا قرار المالك.
- شجرةُ العمل الرئيسية نظيفةٌ إلا خمسةَ عناصرَ غيرِ متتبَّعة معروفة (`.agy-design-refs/` · `marketing/` · `package-lock.json` · `str` · الملفُّ المشوَّه).

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-11 14:30)

**الهدف:** `goal-56dd73bf-15ed-45f9-9659-17758cea84d7` — إن ظهر disarmed فـ`update_goal action=resume`. (الهدف يُمحى تلقائياً عند تغيّر الجلسة/الضغط — أعِد إنشاءه من نصّه في `progress.md`.)

**الإنتاج (متحقَّق 2026-11-11):** `680f7333` مدموجٌ ومنشور. #280 **منشورة ومغلقة**. #286/أ (خادم) منشور و**التذكرة مفتوحة** بانتظار الجزء ب. آخر هجرات مطبَّقة: `0010` ثم `0011`. نسخ: `ktra-before-280-20261111-105404.sql` · `ktra-before-286-20261111-112625.sql`.

**غير منشور:** `a54cf3a4` — بطاقة قالب «مكتب محاسبة (الجديد)» في شاشة إنشاء الشركة (CI أخضر `43016516576`). **لا يحتاج هجرة**؛ نشره = على الخادم `git fetch` + `merge` + `npm run build` في `frontend_v2` + `rsync -a --delete` لـ`dist/` إلى `/var/www/ktra-pro.tech/` (مع `--exclude '/s/'` و`'/media/'`). المالك ينتظر رؤيتها.

**ثلاثة worktrees جاهزة، عملُها غير مُلتزم:**

| التذكرة | المسار | الحالة الدقيقة |
|---|---|---|
| **#286/ب** (شاشات الدفتر) | `.agents/worktrees/acct-286` فرع `ticket/286-client-books` | مُلتزَم حتى `fe70a233`؛ **جولة تصليح ١ مكتملة وغير مُلتزمة** (3 موانع + 8 Nit، البوّابات خضراء: tsc 0 · npm 1459 · build 0 · الوحدة 775). **التالي: التزامها ← مراجعة ٢** |
| **#281** (المواعيد) | `.agents/worktrees/acct-281` فرع `ticket/281-appointments` | منفَّذ وغير مُلتزَم (816 ناجح). **مراجعة ١ = FAIL بسبعة موانع** — التالي: **جولة تصليح ١ على الفواعلي** |
| **#282/أ١** (الأتعاب) | `.agents/worktrees/acct-282` فرع `ticket/282-fees` | منفَّذ وغير مُلتزَم (798 ناجح، هجرة `0012` تُطبَّق من صفر). **التالي: مراجعة ١** |

**موانع #281 السبعة (بنصّها للموجز):** (١) تأكيدُ الموعد يستهلك مفتاح التذكير فيمنع «قبله بيوم» — يُمرَّر `by_pair` بدل `counted_by_pair`؛ (٢) بندٌ لكل التزام بمفتاحٍ لكل فترة ⇒ مفتاح React مكرّر و«قبل 2» يسقط — بندٌ واحد لكل (زبون، فترة)؛ (٣) التوقيت بالعدّ وحده ⇒ «شيل» بلا أثر ورسالتان في يوم — النافذة الحالية = آخر (7،2) بلغه اليوم والبند مستحقٌّ إن لم يوجد صفٌّ مؤقَّت يومه ≥ بدايتها؛ (٤) `{amount}` فارغ في القالب المشحون فتخرج «منك ␣␣قبل ما نقدّم» — يُضاف `amount` إلى `ReminderCandidate` وتُصحَّح نصوص `REMINDER_DEADLINE`؛ (٥) `reminder_type` في `ready_to_send_payload` توقّف عن الفلترة؛ (٦) حجز التقويم بلا «ابعت تأكيد»؛ (٧) `sync_docs` قبل الـcommit.

**قرارات لازمة قبل المتابعة:**
- **#286 الجزء ج** يتبنى (بقرار المالك 2026-11-11): توليدُ بنود الحركة من مبلغ الورقة وضريبتها وطرفها — **سببُ الانحراف موجزي** (قسّمتُ التذكرة A/B ولم أكتب الشرط). القيد اليدوي يبقى للتعديل (تحتاجه #288).
- **#291** (آخر تذكرة): إزالةُ قالب «مكتب محاسبة» القديم ووضع الجديد مكانه، ونقلُ شركة **«مكتب الساعة للمحاسبة والاستشارات الضريبية»** (TenantID 22) إلى الموديول الجديد — بقرار المالك.
- **كل شركات الإنتاج بلا ترخيص `accounting_office`** ولا واحدة عندها الوحدة مفعّلة؛ وتجربة «محاسبة 1» تنتهي 13/11. سببُ القالبين المتشابهين: `accounting_firm` (القديم) لا يمنح الوحدة، `accounting_office` («مكتب محاسبة (الجديد)») يمنحها.

**دروسٌ مسجّلة هذه الجلسة (لا تُنسى):**
- **بوابة الهجرات اسميّة بلا `KTRA_MIGRATIONS_DB`** — صُحّح الأمر في `CLAUDE.md` و`AGENTS.md`.
- **`@types/react` غائب ⇒ `tsc` لا يفحص خصائص JSX في المستودع كلّه** (أُثبت بمسحٍ في #281).
- **`import-linter` 2.16 يرفض وحداتٍ غير موجودة في العقود** — ثُبِّت الإصدار وحُذفت 12 وحدة غائبة.
- **صورة `ubuntu-latest` صارت 26.04** ⇒ Playwright بلا chromium ⇒ `runs-on: ubuntu-24.04` + `timeout-minutes: 15` على خطوة Playwright (كانت تُعلّق الوظيفة 30+ دقيقة).

**لا عاملَ حيّ ولا محاولةَ جارية ولا مهمةَ خلفية الآن.**


يُحدَّث قبل أي توقّف (CLAUDE.md — Workflow، الخطوة 8). من يستلم يبدأ من هنا.
**وبطلب المالك (2026-10-22): يُحدَّث بعد كل تذكرة، وبعد كل جولة تصليح، وقبل أي ضغطٍ للسياق** — هو ذاكرة
المنسّق بعد الـcompact. الإكمال حتى آخر تذكرة بلا توقّف.

**آخر تحديث:** 2026-11-11 ~09:50 (بعد انقطاع الجلسة؛ **لا عامل حيّ ولا job حيّ ولا محاولة جارية**)

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-11 09:50)

الـGoal `goal-0636beb0-0b93-478a-ba89-e889254ad804`: إن ظهر disarmed فـ`update_goal action=resume`.

**الحالة:**

- ✅ **#271–#279 منشورة ومغلقة على GitHub وعلى الإنتاج.** آخرها: #278 (`a438e4f9`، CI `41943538928`، هجرة `0008`)، و#279 (`b29dc25e`، CI `41956587105`، هجرة `0009`، نسخة `ktra-before-279-20261105-033359.sql`).
- 🚀 **#280 الجزء A (الخادم) مُلتزَم ومدفوع `aff3a4bc`، CI أخضر `41975920977` — ولم يُنشَر، و#280 ما زالت مفتوحة** (النشر يكون مرّةً واحدة بعد الجزء B).
- 🔧 **#280 الجزء B (الشاشات) منفَّذ وغير ملتزَم في الشجرة** — المحاولة `attempt-bfabf0fd-8fab-4078-8354-4a880f0f1fc9` (settled، **لم تُراجَع ولم تُختَم بـ`delegation_conclude`**):
  - جديد: `frontend_v2/components/accounting-office/OfficeReadyToSendScreen.tsx` · `OfficeReminderTemplatesSection.tsx` · `OfficeHolidaysSection.tsx`.
  - معدَّل (16): `App.tsx` · `Sidebar.tsx` · `layout/Breadcrumb.tsx` · `types/common.ts` · `utils/viewPermissions.ts` · `OfficeClientFile.tsx` · `OfficeSettingsScreen.tsx` · `services/accountingOfficeApi.ts` · `utils/accountingOffice.ts` + `.test.ts` · `core/shell_manifest.py` · `core/terminology.py` · `core/tests/test_shell_manifest.py` · `docs/modules/accounting_office.md` · `docs/CHANGELOG.md`.
  - **تحقّقتُ بنفسي:** `npx tsc --noEmit` ✓ · `npm test` **1446/0** ✓ · `npm run build` ✓ · `test_shell_manifest` **12 ✓** · `makemigrations --check` ✓ · `git diff HEAD --check` ✓.
  - **لم أشغّل بنفسي:** مجموعة الموديول كاملة والكاملة و`test_terminology_guard`. تقرير العامل: `695 passed` + فشلٌ بيئيّ واحد (`test_no_hardcoded_compound_terms_outside_allowlist`، 252 مخالفاً كلُّهم تحت `.agents/`، **ولا واحد من ملفاته**).
  - ⚠️ **نقصُ API أبلغ عنه العامل (لجولة التصليح):** `GET ready-to-send/` لا يحمل `tax_system` للزبون، فالشاشة تنادي `officeWhatsappLink(phone, null, …)`. الجوال (059/056/باقي 05) والدوليُّ يعملان، و**الأرضيُّ وحده** يُقفل زرَّه بـ«رقم غير صالح للواتساب». الحلّ: حقل `tax_system` في بند الرسالة أو في المستلِم داخل `_reminder_message`.
  - ⚠️ **الشاشات لم تُرَ بالعين** (لا متصفح في هذه البيئة) — تُراجَع بالقراءة الآن، وتُجرَّب في Playwright يدوياً.

**تغيّرت خطوط التفويض (fleet revision 2) — استعمل هذه، فالقديمة لم تعد موجودة:**

- تنفيذ وجولة تصحيح **1**: `lane-7587384e-b0bf-4913-8361-67a1a1b59325` (الخط الافتراضي).
- **المراجع** وجولة تصحيح **3**: `lane-efdd3b26-0a1d-40e1-bd8d-66235e21438a` (Opus 5.5 high).
- جولة تصحيح **2**: `lane-1a4fac83-55c5-49ee-8bf7-7c14aa880489` (Sonnet 5.5 high).

**بالترتيب عند الاستئناف:**

1. `delegation_review` للمحاولة `attempt-bfabf0fd…` ← اقرأ فرق الجزء B سطراً سطراً بنفسك ← `delegation_conclude`.
2. اكتب `%TEMP%\wf-acct\briefs\280b-review.md` (الموجز الأصلي `280b.md`) وأرسله **مراجعةً واحدة** إلى `lane-efdd3b26` (المراجع: `git diff` + مهارة `code-review`)، ويُذكر فيه نقص `tax_system` بنداً معلوماً.
3. **سير العمل الجديد (طلب المالك 2026-11-11 ~10:00، في `progress.md`)** — كل جولة تصليح فقط عند خلل حقيقي من المراجع: خلل 1 ⇒ الفواعلي `lane-7587384e` (يصلح + `code-review` ذاتياً) ← مراجعة 2 ← خلل 2 ⇒ المصحح 2 `lane-1a4fac83` (يصلح + `code-review` ذاتياً) ← مراجعة 3 ← خلل 3 ⇒ المراجع نفسه `lane-efdd3b26` يصلح ← مراجعة 4 في جلسة مستقلة. PASS ⇒ البوّابات مباشرة. يُضاف بندُ `tax_system` إلى أوّل موجز تصليح.
4. البوّابات كلها بنفسك (الموديول+البيان، makemigrations، migrate من الصفر حتى `0010`، lint، tsc/npm/build، sync_docs، diff --check، **والكاملة بالخلفية**).
5. الاستلام: commit للجزء B (+ `docs/agents/*`) ← `git push origin newktra` ← CI أخضر (`aff3a4bc` أخضر أصلاً؛ يلزم أخضرُ على الـcommit الجديد) ← نشرٌ **واحد** يغطّي A+B: على الخادم fetch/merge/`git diff origin/newktra` فارغ/`check`/`makemigrations`/مراجعة `0010` (لا `RemoveField`/`DeleteModel`/`RunSQL`)/build ثم `%TEMP%\wf-acct\deploy-280.sh` (انسخ `deploy-279.sh` واستبدل `before-279`→`before-280`) ← `gh issue close 280` بتعليق النشر ← تحديث `acct-office-build.md`/`runs.md`/`handoff.md`/`progress.md`.
6. **بالتوازي حتى 3 تذاكر** حسب «خطة التوازي» في `progress.md`: **#286 تبدأ الآن** في worktree مع 280؛ وبعد 280: 281 ∥ 282؛ وهكذا. الدمج للمنسّق تذكرةً تذكرة.

**ملاحظات ثابتة:** إرسال سكربتات الخادم: `$s | ssh … 'bash -s'` ينهي السطر الأخير بـ`\r` — اختم الأمر بـ` ;`. و`frontend_v2` بلا `@types/react` ⇒ `tsc` لا يمسك أسماء حقول حالة الـhooks (قديم، خارج التذاكر). و`pytest` لا `manage.py test`. وملفّاتٌ في الجذر لا تُمسّ: `.agy-design-refs/` · `marketing/` · `str` · `package-lock.json` · الملفّ ذو الاسم المشوَّه.

## (قديم) نقطة الاستئناف 2026-11-05 00:50

الـGoal `goal-0636beb0-0b93-478a-ba89-e889254ad804`: إن ظهر disarmed فـ`update_goal action=resume`.

- ✅ **#277 منشورة ومغلقة** (`32f6d156`، CI `41898122328`، نسخة `ktra-before-277-20261104-203648.sql`، `0007` OK، PS v2 على الإنتاج).
- 🔧 **#278 غير ملتزَمة في الشجرة — بانتظار جولة التصليح 1 (DeepSeek). الموجز جاهز ولم يُرسَل:** `%TEMP%\wf-acct\briefs\278-round1-deepseek.md` (8 بنود).
  - التنفيذ: `attempt-25551946…` (مُراجَع)؛ ادّعى 564 · الكاملة 4/7174. **عندي:** الموديول **564 ✓**، tsc ✓، npm **1430/0 ✓**. قرأتُ services/views/الهجرة/الواجهات بنفسي.
  - مراجعة Standards `attempt-a7afd0e3…` و Spec `attempt-b62bd9db…`: **NEEDS-FIX** (كلاهما concluded). المشكلات الحقيقية (تحقّقتُ من الثلاث الأولى في الكود):
    1. الرفع يُقرأ كاملاً في الذاكرة قبل سقف ١٠MB (`views.py` `OfficeDocumentViewSet.files`)؛
    2. `id` بنود المنصّة من جدولٍ آخر و`PATCH` يحلّه على `OfficeDocumentItem` (`_document_item_row_payload`)؛
    3. `document_progress` بلا حدّ فترة؛
    4. `_document_service_codes` يتجاهل `skip` (فترة «ليست علينا» تولّد أوراقاً)؛
    5. `uploadDocumentFile` بلا `tenantOpts()`؛
    + أصول بعيدة يتيمة إن فشل حفظ الصفّ، ومصدران لـ«ضمن» بند المكتب، ونِتّات (أوصاف أمر التحديث، `user` غير مستعمل، تأكيد لا يسقط، checkbox «مفعَّل»، رسالة «لا قائمة» مع وجود السنوية، دالّتان بلا مستدعٍ).
  - ⚠️ مراجعة Spec رأت **فشلين إضافيين** في الكاملة خارج التذكرة: `crm/tests/test_lead_contact_stats.py` (`11 != 12`) و`after_sales/tests/test_shop_days_extension.py` (`2027-03-11 != 2027-03-12`) — حساب تواريخ قرب منتصف الليل/DST على الأرجح. **قبل الاستلام:** شغّلهما وحدهما؛ وإن فشلا فأثبت أنهما يفشلان على `HEAD` (`git stash` ممنوع — استعمل `git worktree add` مؤقتاً على `HEAD` وشغّلهما فيه) وإلا فهما من #278.

**بالترتيب عند الاستئناف:**
1. أرسل جولة 1 لـ DeepSeek (خط `lane-7587384e…`): `delegate` بموجزٍ يشير إلى `278-round1-deepseek.md` (مع scopes كما في التنفيذ).
2. عند عودته: `delegation_review` ← اقرأ تعديلاته ← كل البوّابات بنفسك (الموديول، migrate من الصفر حتى `0008`، makemigrations، lint، tsc، npm test، build، sync_docs، diff --check، والكاملة بالخلفية) ← مراجعة نهائية للقراءة على الحالة النهائية. مشكلةٌ ثانية ⇒ **Sonnet 5.5 high** (relay claude-delegate)، وثالثة ⇒ **Opus 5.5 high**.
3. الاستلام: commit (ملفات #278 + `docs/agents/*`) ← push ← CI (`gh run watch` بالخلفية؛ الـfrontend/Playwright ≈ ساعة) ← على الخادم: fetch/merge/diff فارغ/check/makemigrations/مراجعة `0008`/build (أمرٌ مستقلّ) ← `deploy-278.sh` (انسخ `deploy-277.sh` واستبدل `before-277`→`before-278`) ← `gh issue close 278` بتعليق النشر ← حدّث `acct-office-build.md`/`runs.md`/`handoff.md`.
4. ثم #279 (الرواتب: سطور اللائحة + بندا «كشف رواتب الشهر»/«تغييرات الموظفين» فوق نموذج أوراق #278) فما بعد.
- ملاحظة للمالك (مفتوحة): `frontend_v2` بلا `@types/react` ⇒ `tsc` لا يمسك أسماء الحقول على حالة الـhooks في المكوّنات (قديم، خارج التذاكر).
- إرسال سكربتات الخادم: `$s | ssh … 'bash -s'` ينهي السطر الأخير بـ`\r` — اختم الأمر بـ` ;` كي يقع `\r` أمراً مستقلاً غير ضارّ.

---

## (قديم) نقطة الاستئناف 19:35

**لا job حيّ ولا محاولة جارية.** الـGoal `goal-0636beb0-0b93-478a-ba89-e889254ad804` نشط: إن ظهر disarmed فـ`update_goal action=resume`.

**الحالة:**
- ✅ **#271–#276 منشورة ومغلقة على GitHub.** وفي #270 تعليق جدول التقدّم (13:20)، يُحدَّث من حين لآخر.
  - #275: نسخة `ktra-before-275-20261104-123543.sql`، وcron يومي `30 5 * * *` UTC لـ`refresh_accounting_offices`.
  - #276: `a326e39b`، نسخة `ktra-before-276-20261104-151443.sql`، و`0006` OK.
- 🔧 **#277 غير ملتزَمة في الشجرة، بعد جولة تصليح 1 (DeepSeek).**
  - بوّاباتي على الحالة الحالية: الموديول **499 ✓**، والكاملة **4 بيئية / 7109 ✓**.
  - المراجعة النهائية وجدت **مشكلة ثانية** ⇒ **جولة 2 لـ Sonnet 5.5 high: الموجز جاهز ولم يُرسَل** (`%TEMP%\wf-acct\briefs\277-round2-sonnet.md`، 11 بنداً). أهمّها:
    - `RuleOverrideSerializer` يحدّ `rule_day` 1..31، فيرفض تعديل سطر الحدث (الخدمة تقبل 0..180)؛
    - التزام المكتب الجديد لا يظهر في «اليوم» قبل الغد؛
    - لوحة التحرير تتكرّر لسنوات الكود نفسه؛
    - ثلاثة نصوص ما زالت على `actual_deadline`.

**بالترتيب عند الاستئناف:**
1. **أرسل Sonnet** (بالخلفية):
   `node "C:\Users\asus\.agents\skills\claude-delegate\scripts\relay.mjs" --brief "$env:TEMP\wf-acct\briefs\277-round2-sonnet.md" --cd "D:\Users\asus\Desktop\ktra" --model sonnet --effort high --timeout 1h30m --out-dir "$env:TEMP\wf-acct\relay\277-r2"`
2. عند عودته:
   - تحقّق `effort: high` في `result.json`؛
   - اقرأ الفرق؛
   - شغّل البوّابات كلها بنفسك: الموديول، والكاملة، وmigrate من صفر `0007`، وmakemigrations، وlint، وtsc، و`npm test`، وbuild، وsync_docs، و`diff --check`؛
   - ثم مراجعة نهائية للقراءة على خط `lane-da7d75a7…`. مشكلةٌ ثالثة ⇒ **Opus 5.5 high** (موجزٌ في `briefs\277-round3-opus.md`)، ولا جولة رابعة.
3. **الاستلام:**
   - commit (ملفات #277 + `docs/agents/*`؛ لا الملفات المحرّمة) ← `git push origin newktra` ← CI أخضر (`gh run watch <id> --exit-status` بالخلفية).
   - النشر: `deploy-277.sh` من `deploy-276.sh` (`before-277`). و`0007` فيها `CreateModel`/`AddField`/`AlterField`/`AddConstraint`/`AddIndex`/`RunPython` (بيانات v2 فلسطين) — **لا** `RemoveField`/`DeleteModel`/`RunSQL`. والإرسال: `($s -replace "
","") | ssh -i ~/.ssh/hostenger2/id_ed25519 root@187.124.164.58 'bash -s'`؛ والبناء على الخادم بأمرٍ مستقلٍّ ينتهي بـ`echo done`.
   - `gh issue close 277` بتعليق النشر، ثم حدّث `acct-office-build.md` و`runs.md` و`handoff.md`.
4. **#278 فما بعد** بترتيب جدول `acct-office-build.md`، وكلٌّ يُغلق على GitHub بعد نشره.

**ملاحظات تشغيلية:**
- مراقبة CI بـ`gh run watch` بالخلفية، لا `gh run list` متكرّر.
- الموجز الكبير يُحفظ ملفاً في `%TEMP%\wf-acct\briefs\` ويُشار إليه في `delegate`.
- `delegation_verify` لا يقبل أمراً مركّباً بـ`if`.
- Sonnet/Opus موجزهما مكتفٍ بذاته بالإنجليزية.

### (السابق) نقطة الاستئناف 14:30 — تاريخيّ
#### 14:30

**لا job حيّ ولا محاولة جارية.**
**Goal:** `goal-0636beb0-0b93-478a-ba89-e889254ad804` (rev 4). إن ظهر disarmed بعد الاستئناف: `update_goal action=resume`.
**طلب المالك القائم:** كل تذكرة تُنشر تُغلق على GitHub بتعليق النشر. و#271–#274 مغلقة. وفي #275 و#270 تعليقا حالة (13:20).
**وقرار المالك لـ#275:** «استنى CI وبعدين ديبلوي وسكّر»، **و CI صار أخضر**.

**تحديث 17:45:** #277 نُفّذت (`attempt-37c93b4a…`، 487 ✓ عندي)، والمراجعتان وجدتا مشكلة ⇒ **جولة تصليح 1 عند DeepSeek** (`attempt-b25f2d53-7e59-4e4f-a201-c600d8a533f5`، البنود A–O، والهجرة `0007` تُعدَّل في مكانها لأنها لم تُنشر). عند عودتها: قراءة الفرق ← مراجعة نهائية ← مشكلةٌ ثانية ⇒ Sonnet ← ثالثة ⇒ Opus ← البوّابات ← commit ← push ← CI ← نشر `0007` (فيها `RunPython` لبيانات v2، و`AlterField` لـ`rule` null — لا `RemoveField`/`DeleteModel`/`RunSQL`) ← إغلاق #277.

**تحديث 17:15:** ✅ **#276 منشورة ومغلقة** (نسخة `ktra-before-276-20261104-151443.sql`، و`0006` OK، والفحوص 200). والجاري: #277 عند DeepSeek (`attempt-37c93b4a…`) في مرحلة البوّابات.

**تحديث 16:15:**
- ✅ **#276 مُلتزَمة `a326e39b` ومدفوعة**: البوّابات على الحالة النهائية 437 · الكاملة 4 بيئية / 7047 · migrate من صفر `0006` · lint · tsc/1414/build · sync_docs. وعلّقتُ على #276 بالحالة.
  التالي: CI `41844193203` أخضر ⇒ `deploy-276.sh` (من 275، و`before-276`) ← `0006` فيها `CreateModel` فقط ← `gh issue close 276`.
- 🔨 **#277 أُرسلت إلى DeepSeek**: `attempt-37c93b4a-26e3-405e-88ef-62ecdea43057`، والموجز الكامل في `%TEMP%\wf-acct\briefs\277.md` (هجرة `0007`، وتعديل المكتب للائحة، والتمديد، والتزامات المكتب، والأحداث، وv2 فلسطين). الشجرة الآن تحمل عمل #277 غير الملتزَم، فلا تلمسها؛ نشرُ #276 يجري من `origin/newktra` على الخادم.

**تحديث 16:00:** #276 التصليح 2 (Sonnet، `effort=high`، 1.08$) استُلم، وبوّاباته كلها خضراء عندي: 437 · الكاملة 4 بيئية / 7047 · migrate `0006` · lint · tsc/1415/build · sync_docs · diff --check. والمراجعة النهائية وجدت 4 صغيرة (تسمية وتعليقات) ⇒ **جولة 3 عند Opus 5.5 high**: job `pwsh-1430444454924cbf`، relay `%TEMP%\wf-acct\relay\276-r3`، والموجز `briefs\276-round3-opus.md`. بعدها لا جولة رابعة في القاعدة: تحقّق `effort`، واقرأ الفرق، ثم البوّابات (الكاملة أيضاً)، ثم commit ← push ← CI ← نشر `0006` (`deploy-276.sh` من 275) ← `gh issue close 276` ← #277.

**تحديث 15:25:** #276 التصليح 1 (DeepSeek) استُلم، والموديول عندي 435 ✓. والمراجعة النهائية وجدت مشكلة ثانية، أخطرها MySQL 1093 في `mark_all_alerts_seen` ⇒ **جولة 2 عند Sonnet 5.5 high**: job `pwsh-9b91501b257042e4`، relay `%TEMP%\wf-acct\relay\276-r2`، والموجز `%TEMP%\wf-acct\briefs\276-round2-sonnet.md` (7 بنود). عند عودتها: تحقّق `effort: high` في `result.json` ← اقرأ الفرق ← البوّابات كلها ← مراجعة نهائية؛ ومشكلةٌ ثالثة ⇒ Opus 5.5 high.

**تحديث 14:40:**
- ✅ **#275 منشورة ومغلقة**: نسخة `ktra-before-275-20261104-123543.sql`، و`0005` طُبّقت، والفحوص كلها 200، والـcron اليومي مضاف. البند 1 أدناه منتهٍ.
- 🔧 **#276 جولة تصليح 1 أُرسلت** إلى DeepSeek: `attempt-e781fb7b-da42-429d-ae63-5242f6f57935` (البنود A–L كما في الملف). عند عودتها: `delegation_review`، ثم قراءة الفرق، ثم مراجعة نهائية… كما في البند 2.

**بالترتيب عند الاستئناف:**
1. ~~**نشر #275**~~ (تمّ) (run `41818234949` على `8caccb16` = `completed success`).
   - السكربت جاهز: `%TEMP%\wf-acct\deploy-275.sh` (من 274، و`before-275`).
   - قبله على الخادم: `git fetch` ← `git merge --no-edit origin/newktra` ← `git diff origin/newktra --stat` فارغ ← pip ← `manage.py check` ← `makemigrations --check` ← المعلّق `accounting_office.0005` وحده ← `cd frontend_v2 && npm install && npm run build`.
   - ثم السكربت: `($s -replace "`r","") | ssh -i ~/.ssh/hostenger2/id_ed25519 root@187.124.164.58 'bash -s'`.
   - ثم **cron يومي**، وشغّله يدوياً مرّةً للتحقّق: `30 5 * * * cd /root/ktra && venv/bin/python manage.py refresh_accounting_offices >> logs/refresh_accounting_offices.log 2>&1`.
   - ثم `gh issue close 275 --comment "<النشر: النسخة الاحتياطية، الهجرة 0005، الفحوص 200، cron>"`، وحدّث صفّ 275 ✅ في `acct-office-build.md` و`runs.md`.
   - **شجرة العمل تحمل #276 غير ملتزَمة، فلا تلمسها**: النشر من `origin/newktra` على الخادم وحده.
2. **#276 — جولة تصليح 1 (DeepSeek):**
   - أرسل: `delegation_correct` على `attempt-7aee1230-16dd-4cc6-82a4-b328eeae7bad` (مسجَّلة `correction-required`). الـfeedback = **نصّ الملف `%TEMP%\wf-acct\briefs\276-round1-deepseek.md` حرفياً**: البنود A–L بقراراتها، وأوامر الفحص.
   - إن رُفض الإرسال (`already-corrected`/`no-worker`): `delegate` جديد على خط التنفيذ `lane-7587384e…`، وأوّل الموجز «حالة الشجرة: #276 منفَّذة وغير ملتزَمة، وهذه جولة تصليح عليها» ثم نصّ الملف.
   - **أخطر بند (A):** `week` عدّاداً وفلتراً = نافذة `0 <= actual_deadline - day <= 6`، مستقلّة عن الشارة الواحدة (الشارة تبقى بالأولوية أحمر ← أصفر ← قريب). البقية:
     - (B) `visible_clients` في `_visible_alerts`.
     - (C) `seen-all` على المعروض وحده.
     - (D) `effective_assignee`.
     - (E) `existing` بـ`ref_key__in`.
     - (F) اختبارا العزل بنفس المستخدم في المكتبين.
     - (G) اختبار المحسوم بلا شارة على `client_obligations_payload`.
     - (H) التمديد.
     - (I) `badge` من الخادم في `alert_row`، وحذف `alertBadgeKey`.
     - (J) `&task=` وإبراز الشغلة.
     - (K) `MANAGER_ROLE` في `core/access.py` و`CLIENT_TAB_KEYS as const`.
     - (L) docstrings/وثائق، والسطر الفارغ، وتسمية اختبارين.
   - بعدها الحلقة: قراءة الفرق ← مراجعة نهائية (Standards+Spec على خط القراءة `lane-da7d75a7…`) ← مشكلة ثانية ⇒ Sonnet 5.5 high (`claude-delegate`) ← ثالثة ⇒ Opus 5.5 high. **ولا جولة إن كانت نظيفة.**
   - ثم البوّابات كلها بنفسي: الموديول+البيان · `core/tests` · الكاملة · migrate من صفر (`0006`) · makemigrations · lint · tsc/npm test/build · sync_docs · `git diff HEAD --check`.
   - ثم commit (ملفات #276 + `docs/agents/*`) ← push ← CI أخضر ← نشر (`deploy-276.sh` من 275، و`before-276`، والهجرة `0006` فيها `CreateModel` فقط) ← `gh issue close 276` ← التحديث.
3. **#277–#291** بترتيب جدول `acct-office-build.md`، وكلٌّ يُغلق على GitHub بعد نشره، ويُحدَّث تعليق التقدّم في #270 من حين لآخر.

**ما يعرفه المنسّق عن #276 (قرأ الفرق كاملاً):**
- النموذج `OfficeAlert` وهجرة `0006_officealert.py` (`CreateModel` فقط، وفرادة غير مشروطة).
- الإعدادان في مجموعة `alerts`.
- `_generate_late_alerts` داخل `refresh_office`، و`alerts_payload`/`mark_alert_seen`/`mark_all_alerts_seen`، و`OfficeAlertsViewSet`.
- `OfficeAlertsBell.tsx` في `AppLayout`، و`?tab=` في `OfficeClientFile`.
- محاولتا المراجعة (`attempt-a637687d…` Standards، و`attempt-5cd4b7c3…` Spec) مسجَّلتان `reviewed-completion`.

### (السابق) نقطة الاستئناف 13:20 — تاريخيّ

**لا job حيّ.** الشجرة: #275 ملتزَمة ومدفوعة؛ لا تعديل كود غير ملتزَم (فقط `docs/agents/*` بيد المنسّق، والملفات المحرّمة غير المتتبَّعة).
**Goal:** `goal-0636beb0-0b93-478a-ba89-e889254ad804` (rev 3) — بعد الاستئناف: `update_goal action=resume` إن ظهر disarmed. الهدف ينصّ: جولة التصليح **فقط إن وُجدت مشكلة** (1 DeepSeek ← 2 Sonnet ← 3 Opus).

**بالترتيب عند «كمّل»:**
1. **#275 — النشر:** `gh run list --branch newktra --limit 1` (run `41818234949` على `8caccb16`، كان `in_progress`). أخضر ⇒
   - `%TEMP%\wf-acct\deploy-274.sh` ⇒ `deploy-275.sh` (`before-274`⇒`before-275`). الإرسال: `($s -replace "`r","") | ssh -i ~/.ssh/hostenger2/id_ed25519 root@187.124.164.58 'bash -s'` (استبدل `\r` كلياً، لا `\r\n` فقط؛ و`tail -n N` لا `tail -N` على الخادم).
   - قبله على الخادم: `git fetch` ← `git merge --no-edit origin/newktra` ← `git diff origin/newktra --stat` فارغ ← pip ← `manage.py check` ← `makemigrations --check` ← المعلّق `accounting_office.0005` وحده (فيها `AddField`/`CreateModel`/`AddIndex`/`AddConstraint` فقط — لا `RemoveField`/`DeleteModel`/`RunSQL`) ← `cd frontend_v2 && npm install && npm run build`.
   - ثم السكربت (نسخة احتياطية ← migrate ← static ← dist ← restart ← فحوص 200).
   - **cron يومي جديد** على الخادم (crontab root)، مثلاً `30 5 * * * cd /root/ktra && venv/bin/python manage.py refresh_accounting_offices >> logs/refresh_accounting_offices.log 2>&1`، وتشغيلٌ يدوي مرّةً للتحقّق.
   - `gh issue close 275` بتعليق النشر، وحدّث `acct-office-build.md` (صفّ 275 ✅) و`runs.md`.
2. **#276 — استئناف:** `delegation_correct` على `attempt-0fa33ba5-bac9-4316-9bbf-483fee7facb4` بـ«كمّل #276 من البداية بنفس الموجز حرفياً». (أو dispatch جديد على خط التنفيذ؛ الموجز كاملاً في الجلسة: ابحث «تذكرة #276 — مكتب المحاسبة ٦».) القرارات المحسومة فيه:
   - **درجتان مشتقّتان بلا تخزين، شارةٌ واحدة بالأولوية:** أحمر `late` (`pending` و`actual_deadline < day`) ← أصفر `late_internal` (`pending` و`task.internal_deadline < day`) ← `near` ← لا شيء. `near` يصير محايداً (slate) لئلا يلتبس بالأصفر.
   - **«اليوم»:** counters `{late, late_internal, week, all}` قبل الفلتر؛ فلتر `late_internal` جديد؛ عدّادات «متأخّر رسمي» (rose) · «متأخّر داخلي» (amber) · «قريب هالأسبوع» · «الكل».
   - **`OfficeAlert`** (هجرة `0006`): `tenant`, `recipient`, `kind` (`task_late_internal` / `obligation_late`، قابلة للإضافة)، `ref_key` (`task:<id>`/`obligation:<id>`)، `client`/`task`/`obligation` nullable، `message` بلا مبلغ، `day`, `seen_at`, `created_at`؛ فرادة غير مشروطة `(tenant, recipient, kind, ref_key)` ⇒ **مرّة لكل (مستلِم، نوع، مرجع)**.
   - **إعدادان بمستوى المكتب** `late_internal_alert_to` (افتراض `assignee`) و`late_official_alert_to` (افتراض `assignee_owner`)، اختيارات `assignee`/`assignee_owner`/`owner`؛ مسؤولٌ `None` ⇒ صاحب المكتب؛ بلا تكرار مستلِم.
   - **التوليد** داخل `refresh_office` بـ`bulk_create(ignore_conflicts=True)` بلا N+1، و`created_alerts` في المردود والأمر.
   - **الجرس:** `alerts_payload(tenant, *, user)` يستبعد المحسوم عند القراءة (التزامٌ لم يعد pending / شغلةٌ بلا pending) بـ`Exists`؛ `GET alerts/` · `POST alerts/<id>/seen/` (غيرك 404) · `POST alerts/seen-all/`. `OfficeAlertsBell.tsx` في `AppLayout.tsx` بجوار `NotificationCenter` (لا تمسّه) ويظهر لمكتب المحاسبة المرخّص وحده؛ النقر «شفته» ثم ملفّ الزبون `?tab=obligations` (`alertTargetPath`)؛ جلبٌ عند التركيب وكل 5 دقائق وعند التركيز.
   - **ثم الحلقة كاملة:** قراءة الفرق ← Standards+Spec ← تصليح (إن لزم) ← بوّابات ← مراجعة نهائية ← commit ← push ← CI ← نشر (`0006`) ← إغلاق.
3. **#277–#291** بترتيب جدول `acct-office-build.md`.

**ملاحظات تشغيلية من هذه الجلسة:**
- `delegation_verify` يُسقط أمراً مركّباً بـ`if (...) { exit 1 }` — شغّل `tsc`/`npm test`/`build` أوامرَ منفصلة.
- الكاملة تُشغَّل في `pwsh` بالخلفية (~6–7 د)؛ والأربعة البيئية تُثبَت بتشغيلها وحدها (`.agents`=2696، `accounting_office`=0).
- Sonnet/Opus: `node "C:\Users\asus\.agents\skills\claude-delegate\scripts\relay.mjs" --brief <ملف> --cd "D:\Users\asus\Desktop\ktra" --model sonnet|opus --effort high --timeout 1h30m --out-dir "%TEMP%\wf-acct\relay\<id>"` بالخلفية، وتحقّق `effort: high` في `result.json`.

**مفتوح للمالك:** لم تُرَ شاشتا «اليوم» وتبويب الالتزامات بالعين (لا بيئة متصفّح)؛ محدِّد الإسناد في التبويب لا يميّز «موروث» من «محوَّل صراحةً» (طفيف، لـ#277)؛ #209 مصباح الحضور؛ هل تُعلَّم الحرّاس الأربعة لتتخطّى `.agents`.

### السجلّ السابق لهذه الجلسة (تاريخيّ)

**الحالة عند 12:25:**
- **#274 منشورة ومغلقة** (CI أخضر `41796745266`، نسخة احتياطية `/root/backups/ktra-before-274-20261104-090409.sql`، `0004` طُبّقت، كل الفحوص 200). القسم أدناه عنها تاريخيّ.
- **#275 مُلتزَمة `8caccb16` ومدفوعة (2026-11-04 ~13:05)** — الخطوة التالية: `gh run list --branch newktra --limit 1` أخضر ← نشر بـ`deploy-275.sh` (من `deploy-274.sh`) ← cron يومي `refresh_accounting_offices` ← إغلاق #275 ← ثم #276. (ما يلي تاريخ الجولات.)
- **#275 كانت في جولة تصليح 3 عند Opus 5.5** (relay بالخلفية، `--out-dir %TEMP%\wf-acct\relay\275-r3`، الموجز `%TEMP%\wf-acct\briefs\275-round3-opus.md`، 3 بنود O1–O3). جولة Sonnet (S1–S6) استُلمت: قرأتُ فرقها وبوّاباتها كلها خضراء (391 · كاملة 4 بيئية/7001 · migrate · lint · tsc/1411/build · sync_docs). بعد Opus: تحقّق `effort=high`، اقرأ الفرق، البوّابات، ثم الاستلام (لا جولة رابعة في القاعدة — ما يبقى يُبلَّغ المالك). شجرة العمل تحمل كل #275 **غير ملتزَمة**:
  - التنفيذ (DeepSeek) ← قراءة الفرق كاملاً + Standards/Spec ← تصليح 1 (DeepSeek، 18 بنداً) ← بوّابات المنسّق كلها خضراء (389 · كاملة 4 بيئية/6999 · migrate من صفر `0005` · lint · tsc/1411/build · sync_docs) ← مراجعة نهائية وجدت 6 ⇒ Sonnet.
  - **بعد عودة Sonnet:** تحقّق `effort=high` في `result.json`، اقرأ الفرق الجديد، شغّل البوّابات كلها، ثم مراجعة نهائية للقراءة. مشكلةٌ ثالثة ⇒ Opus 5.5 `--effort high`.
  - **ثم الاستلام:** commit بملفات #275 وحدها (لا `docs/agents` المحرّمة على المنفّذ — هذه للمنسّق تُلتزم معها كالعادة، ولا الملفات المحرّمة غير المتتبَّعة) ← push ← CI ← نشر (`deploy-275.sh` من `deploy-274.sh`، و`0005` فيها `AddField`/`CreateModel`/`AddIndex`/`AddConstraint` فقط) ← **cron يومي** على الخادم: `python manage.py refresh_accounting_offices` صباحاً ← إغلاق #275.
  - مفتوح للمالك: لم تُرَ الشاشة بالعين (لا بيئة متصفّح)؛ محدِّد الإسناد في التبويب يُظهر المسؤول الفعليّ فلا يميّز «موروث» من «محوَّل صراحةً» (طفيف، لـ#277).

**الأسطول:** خطّا DeepSeek V4.1 Flash كلاهما بجهد **max**:
- التنفيذ: `lane-7587384e-b0bf-4913-8361-67a1a1b59325`.
- القراءة: `lane-da7d75a7-91f6-4032-ae4a-be40c4285cc8`.

**قاعدة التصعيد:**
- الجولة 1: DeepSeek max.
- الجولة 2: Sonnet 5.5، `--effort high`.
- الجولة 3: Opus 5.5، `--effort high`.
- Sonnet وOpus عبر `claude-delegate` (relay بالخلفية، وتحقّق `effort=high` في `result.json`).

### #274 — مُلتزَمة `1b9e51a3` ومدفوعة
- **البوّابات عند المنسّق كلها خضراء:**
  - الموديول + البيان: 330.
  - migrate من صفر: OK (`0004`).
  - الكاملة: 4 failed (البيئية، `.agents`=2696 سطراً، و`accounting_office`=0) / 6940 passed.
  - lint: 3 kept.
  - tsc، و`npm test` 1407، وbuild، وsync_docs.
- **CI:** run `41796745266` كان `in_progress` (بدأ 08:04Z).
- **الخطوة التالية:**
  1. `gh run list --branch newktra --limit 1` ⇒ أخضر.
  2. النشر:
     - انسخ `%TEMP%\wf-acct\deploy-273.sh` إلى `deploy-274.sh`، وغيّر `before-273` إلى `before-274`.
     - على الخادم: fetch، ثم merge، ثم `git diff origin/newktra --stat` فارغ، ثم pip، ثم check، ثم `makemigrations --check`. المعلّق يجب أن يكون `accounting_office.0004` وحده، و0004 فيها `AlterField` و`CreateModel` و`RunPython` فقط. ثم `npm install` و`npm run build`.
     - ثم شغّل السكربت.
  3. أغلق #274 بتعليق.
  4. حدّث `acct-office-build.md`.

### #275 — الالتزامات و«اليوم»: موقوفة مؤقتاً بطلب المالك
- **المحاولة:** `attempt-7b4941d0-5bb9-40e8-a3d2-b196d14558c5`، concluded `correction-required` (إيقاف).
  - كان يقرأ ولم يعدّل أي ملف.
- **الاستئناف:**
  - إمّا `delegation_correct` على المحاولة نفسها: «كمّل من حيث وقفت بنفس الموجز».
  - وإمّا dispatch جديد على خط التنفيذ بنفس الموجز كاملاً. ابحث في الجلسة عن «تذكرة #275 — مكتب المحاسبة ٥».
- **القرارات المحسومة في الموجز:**
  - **النماذج** (هجرة `0005`):
    - `PeriodTask`: خدمة × فترة، مع `assignee` nullable يرث `responsible`.
    - `Obligation`: 3 حالات، مبلغ `Decimal`، واتجاه `due`/`refund`، و`client_paid`، و`prior_to_office`، وفرادة (`client_service`, `rule_code`, `period_end`).
    - `ClientService.last_period_ours`.
    - `OfficeRefreshRun(tenant, day)`.
  - **دالة التحديث:** `refresh_office(tenant, *, day)` idempotent.
    - تحفظ ما `period_end < day`، أي ق.م كانون الثاني تظهر في 1/2.
    - الحدّ الأدنى `max(starts_on, responsible_from)` بلا سقف 24 شهراً.
    - **محرّكٌ واحد مع `client_deadlines`**.
    - لا تُحدِّث صفاً موجوداً.
  - **التشغيل:**
    - `ensure_office_refreshed` تُنادى من `GET today/`.
    - أمر إدارة `refresh_accounting_offices [--day]`.
    - **الـcron على الخادم خطوة نشرٍ للمنسّق.**
  - **الانتقالات:**
    - «انقدّم» لا يُتراجع عنه، ويقفل المبلغ.
    - «مش لازم» يُعاد.
    - `close_prior_obligations`.
    - `assign_task` بـ`office.clients.assign`.
    - `visible_clients` يتّسع لمن حُوّلت له شغلة.
  - **المشتقّ عند القراءة:** `near` (0..6 أيام) و`late` (`actual_deadline < day`)، وصفرٌ تخزين. الأصفر/الأحمر والجرس لـ#276.
  - **الـAPI:**
    - `today/?filter=mine|week|late`.
    - `obligations/<id>/{submit,not-required,reopen,amount,client-paid}/`.
    - `tasks/<id>/assign/`.
    - `clients/<pk>/obligations/` و`…/close-prior/`.
  - **الواجهة:**
    - `OfficeTodayScreen` على `/accounting-office/today`، الجوال أولاً، على نموذج `prototypes/acct-office-screens/01-today.html` (فرع `prototype/acct-office-screens`).
    - تبويب «الالتزامات والشغلات» في ملف الزبون.
- **عند الاستلام:**
  - راجِع الشاشة على قياس الجوال بعينك.
  - أضِف الـcron على الخادم عند النشر (أمرٌ يومي صباحاً).

### (السابق) 09:50

- **#273:** ✅ منشورة 2026-10-31 (نسخة `/root/backups/ktra-before-273-20261031-131345.sql`، هجرة `0003` OK، فحوص 200) ومغلقة.
- **#274 — جولة التصليح 2 عند Sonnet** (job `pwsh-952ea4abb5b643cf`، relay `%TEMP%\wf-acct\relay\274-r2`،
  الموجز `briefs\274-round2-sonnet.md`). تحقّق `effort=high` في `result.json` ثم راجِع الفرق كاملاً وشغّل البوابات بنفسك.
  - الجولة 1 (DeepSeek، `attempt-fbf8eae8…`): أصلحت 12 بنداً (الدوريات الثابتة بـ`periods_for`، حزمٌ محاذاة، N+1،
    `user` keyword-only، `parse_iso_date`…). 307 اختبار الموديول وtsc وnpm test 1407 أخضر عندي.
  - المراجعة النهائية وجدت (وأعدتُ إنتاجه بنفسي): `service_periods` تبتلع الأشهر عند تقصير الدورية
    (سنوي←شهري من شباط = فترةٌ سنوية واحدة). وأيامُ الإعداد من طول الفترة، وسياقٌ يُعيد None لزبونٍ خارجه،
    وعلمُ السقف التقديري مُهمَل، وفلترُ النوع لنظامٍ واحد، والفلترة في بايثون.
  - رُفض: حذف احتياط `periodLabel` (المواصفة تطلبه).
  - إن وُجدت مشكلةٌ ثالثة ⇒ **Opus 5.5** بالمهارة نفسها.

### (القديم) نقطة الاستئناف (2026-10-31 15:10)

**لا job حيّ.** المنفّذ أنهى #274 قبل الانقطاع، وتسليمه في الشجرة **لم يُراجَع بعد**.

### الحالة الآن
- **#271 و#272:** ✅ منشورتان ومغلقتان.
- **#273 الخدمات والباقات:** مُلتزَمة `d96f556b`، ومدفوعة. **CI أخضر** (run `41194086851`). **لم تُنشر ولم تُغلق.**
- **#274 اللائحة والتقويم:** المحاولة `attempt-a87b5853-822d-4ed7-83a2-7ca9faa922f7` (job `delegation-6`) **انتهت completed**، والعمل
  غير مُلتزَم في الشجرة. لم أقرأ الفرق ولم أشغّل الفحوص بعد.
  - **تقرير المنفّذ** (ادّعاء، يُقرأ كاملاً بـ`job_output delegation-6` أو `delegation_review`):
    - الموديول 286 passed، و`makemigrations` نظيف، وmigrate من صفر OK (`0004_deadline_schedules`).
    - `lint-imports` 3 kept، و`tsc` نظيف، و`npm test` 1405، و`npm run build` ناجح.
    - الكاملة: 4 failed (البيئية) / 6908 passed.
    - إثبات سقوطٍ لسبعة اختبارات.
  - **الملفات الجديدة:**
    - `accounting_office/deadlines.py` (المحرّك النقي)
    - `accounting_office/migrations/0004_deadline_schedules.py`
    - `accounting_office/tests/test_deadlines.py` (71 اختباراً)
    - `frontend_v2/components/accounting-office/OfficeCalendarScreen.tsx`
  - **المعدَّلة:**
    - الخادم: `accounting_office/{models,services,settings_registry,urls,views}.py`، و`tests/test_settings.py`.
    - **خارج الموديول:** `core/shell_manifest.py`، و`core/terminology.py`، و`core/tests/test_shell_manifest.py`.
    - الواجهة: `frontend_v2/App.tsx`، و`components/Sidebar.tsx`، و`components/layout/Breadcrumb.tsx`، و`types/common.ts`،
      و`utils/viewPermissions.ts`، و`OfficeSettingsScreen.tsx`، و`accountingOfficeApi.ts`، و`utils/accountingOffice.ts` واختباره.
    - الوثائق: `ARCHITECTURE.md`، و`docs/{API_INDEX,CHANGELOG}.md`، و`docs/modules/accounting_office.md`.
  - **انحرافات أعلنها، يجب الحكم عليها في المراجعة:**
    1. الدورية المتغيّرة في `cadence=service` لا تُحاذى للتقويم، بل تُنتج الفترة التالية من أول شهر غير مغطّى، لتفادي ثقبٍ عند التغيير.
    2. حدّ 7 أيام في حلقات زحزحة أيام الراحة.
    3. عُدّلت 3 اختبارات من #271 في `test_settings.py`، لأن السجلّ صار 8 مفاتيح ومجموعتين، و`item` مسموح.
    4. «التقويم» مجموعة مستقلّة في الشريط الجانبي.
    5. `ThresholdContext`، والبطاقة الغائبة تُقرأ بـ`getattr`.
  - **مفتوح عنده:** التقويم ≈7 استعلامات إعداد لكل زبون (لا تحسين جماعي). ورابط تأجيل شباط 2026 في `note` النسخة لا في السطر.

### الخطوات التالية بالترتيب
1. **انشر #273** (CI أخضر):
   - انسخ `%TEMP%\wf-acct\deploy-272.sh` إلى `deploy-273.sh`، وغيّر `before-272` إلى `before-273` (يبقى `migrate` كاملاً).
   - على الخادم أولاً: `git fetch`، ثم `git merge origin/newktra`، ثم `git diff origin/newktra --stat` (يجب أن يكون فارغاً)، ثم
     `pip install -r requirements.txt`، و`manage.py check`، و`makemigrations --check`، و`showmigrations` (المعلَّق
     `accounting_office.0003` وحده).
   - افحص عمليات الهجرة: `0003` فيها `CreateModel` ×5، و`AddConstraint`، و`AddIndex`، و`RunPython` (زرع السقوف). لا
     `RemoveField`/`DeleteModel`/`RunSQL`.
   - ثم `cd frontend_v2; npm install; npm run build`. ثم شغّل السكربت عبر `bash -s` بعد تحويل CRLF إلى LF.
   - أغلق #273 بتعليق، وحدّث صفّها في `docs/agents/acct-office-build.md` وسجلّها.
   - **تنبيه:** دمج الخادم يأخذ `origin/newktra` وحده، وعمل #274 غير المُلتزَم لا يصل إليه.
2. **راجع #274** بالحلقة:
   - `delegation_review` على `attempt-a87b5853…`، ثم اقرأ الفرق كاملاً بنفسي، بما فيه ملفات `core/` والواجهة خارج الموديول.
   - ثم مراجعتا Standards وSpec بالتوازي على خط القراءة.
   - ثم جولة التصليح 1 لـDeepSeek (`delegation_correct`)، والثانية لـSonnet، والثالثة لـOpus.
   - ثم الفحوص بنفسي، وcommit، وpush، وCI، ونشر (هجرة `0004` + نسخة احتياطية)، وإغلاق.
   - **تحقّق خاص:**
     - البيانات في `0004` مقابل جداول רשות המסים المنقولة في الموجز.
     - حارس `ast` على `deadlines.py`.
     - التقويم لا يكتب.
     - `visible_clients` في التقويم.
     - صحّة تعديل اختبارات #271.
3. **ثم #275** (الالتزامات و«اليوم»)، فالبقية بترتيب `acct-office-build.md`.

### ملاحظات تشغيل
- **`delegation_verify` يقطع الأوامر الطويلة** (migrate من صفر، والبوّابة الكاملة) ويسجّلها فاشلةً بلا مخرَج. شغّلهما في `pwsh` بالخلفية
  وانقل النتيجة في `delegation_conclude`.
- **تأكيد الحرّاس البيئيين:** شغّل الأربعة وحدها، وعُدّ الأسطر: `\.agents` > 0 و`accounting_office` = 0.
- **ملفات مؤقّتة عالقة** من قطع `delegation_verify`: `%TEMP%\ktra-mig-273-v2.sqlite3` و`-journal`. احذفها إن لم تعد مقفلة.
- **أسعار relay:** #273 الجولة 2 (Sonnet) كلّفت $0.61، وفي `result.json` `effort=high`.

## (للتاريخ) نقطة استئناف 09:50 — أُنجزت

**الجلسة انقطعت قرابة 05:50 والمنفّذ في منتصف #273.** (ما يلي حتى «قواعد ثابتة» تاريخٌ قديم؛ القواعد الثابتة تحته سارية.)

### الحالة الآن
- **#271 الأساس:** ✅ مُلتزَمة `392d7165`، ومنشورة (الدمج `a239776b` على `modern`)، ومغلقة.
- **#272 الأدوار:** ✅ نُشرت (الدمج `3004b083`، نسخة `/root/backups/ktra-before-272-20261031-075255.sql`) وأُغلقت.
- **تحديث 09:57:** المحاولة القديمة عالقة «not finished» بلا job فلا تُصحَّح؛ أُرسل موجز تكملة جديد لـDeepSeek:
  `attempt-de6b75ef-7421-4b26-8410-b144485c9771` (job `delegation-1`).
- **تحديث ~11:30:** التكملة سُلّمت وقُرئت كاملاً، ومعها مراجعتا Standards/Spec. **جولة التصليح 1 (DeepSeek max)** جارية:
  `attempt-45d1e5d3-6d99-4da0-b7f2-accf38fb091e` (job `delegation-4`)، 17 بنداً. أخطرها أن الحالة «موقوفة» تُشتقّ من وجود `ends_on` فتسمح
  بتداخل الفترات، واختبار قناع `suggested_price` الذي لا يسقط، وبيانات الهجرة غير المحروسة. **الجولة 2 لـSonnet والثالثة لـOpus** (`--effort high`).
- **تحديث 12:30:** الجولة 1 مستلَمة وفحوصها خضراء عندي: 214 من اختبارات الموديول، وmigrate من صفر `exit=0`، والكاملة 4 بيئية فقط
  (أثبتُّ أن مخالفيها كلهم `.agents`). **ملاحظة:** `delegation_verify` يقطع الأوامر الطويلة (migrate من صفر والبوّابة الكاملة)
  ويسجّلها فاشلة بلا مخرَج، فشغّلهما في `pwsh` بالخلفية. المراجعة النهائية وجدت 9 ملاحظات، قُبل منها 8.
  **الجولة 2 عند Sonnet** (job `pwsh-241`، relay `%TEMP%\wf-acct\relay\273-r2`، والموجز `briefs\273-round2-sonnet.md`).
- **تحديث 12:50:** **#273 مُلتزَمة `d96f556b` ومدفوعة**، وCI run `41194086851` جارٍ. بعده: النشر (هجرة `accounting_office.0003` + نسخة
  احتياطية؛ السكربت `%TEMP%\wf-acct\deploy-272.sh` مع تغيير الاسم إلى 273)، ثم إغلاق #273.
  **#274 بدأت:** DeepSeek `attempt-a87b5853-822d-4ed7-83a2-7ca9faa922f7` (job `delegation-6`). الموجز كاملاً في نداء `delegate` (ابحث
  «تذكرة #274 — مكتب المحاسبة ٤»)، وفيه:
  - نماذج `DeadlineSchedule`/`DeadlineRule` بيانات منصّة بنسخ، و`deadlines.py` دالّة نقية.
  - جداول רשות המסים 2026 (pa151025-2) و2027 (pa131026-1)، وتعديل شباط 2026 إلى 26.3 (sa050326-2).
  - تقويم محسوب لا محفوظ، و4 إعدادات جديدة في مجموعة «الضريبة ولائحة المواعيد».
- **#273 الخدمات والباقات:** **نصف منجزة، غير مُلتزَمة** في الشجرة. المحاولة `attempt-9b5ef424-c954-44cc-acba-0708cca8cc79`
  (DeepSeek، الـjob `delegation-34`) انقطعت أثناء الواجهة.
  - **حسب آخر نشاطه:** الخادم «أخضر»، والاختبارات أولاً، والواجهة بدأها (`utils` والاختبار)، وكان ينتقل إلى `accountingOfficeApi.ts`.
  - **الملفات المعدَّلة:**
    - الخادم: `accounting_office/{models,serializers,services,urls,views}.py`، و`tests/test_amounts_guard.py`، و`tests/test_module_gate.py`.
    - الواجهة: `OfficeClientFile.tsx` و`OfficeSettingsScreen.tsx` و`accountingOfficeApi.ts`، و`utils/accountingOffice.ts` واختباره.
  - **الجديدة:** `accounting_office/migrations/0003_services_packages_thresholds.py` و`accounting_office/tests/test_services.py`.
  - **لم تُحدَّث بعد:** الوثائق (`docs/modules/accounting_office.md`، و`CONTEXT.md`، و`CHANGELOG`).
  - **الموجز كاملاً** في نداء `delegate` بالجلسة (ابحث `تذكرة #273 — مكتب المحاسبة ٣`). قراراته المحسومة:
    - **الكتالوج:** `OfficeService` (كود، اسم، تفعيل، مضمَّنة، ترتيب)، يُزرع بـ`ensure_default_services` (idempotent) بالأكواد الخمسة
      `bookkeeping`/`vat`/`payroll`/`annual_accounts`/`consulting`.
    - **الباقة:** `ServicePackage`، وفيها `suggested_price` مبلغٌ مقنَّع يُسجَّل في `AMOUNT_KEYS`.
    - **خدمة الزبون:** `ClientService` (`starts_on`/`ends_on`/`responsible_from`، لا حذف) و`ClientServiceFrequency` (`effective_from`،
      و`frequency_on(day)` = أكبر تاريخ ≤ اليوم).
    - **السقف:** `TaxThreshold` بيانات منصّة بلا `tenant` (IL `vat_monthly_reporting` 2026=1,775,000 و2027=1,805,000،
      و`vat_exempt_dealer` 2026=122,833)، وعليه إعفاءٌ معلَن في حارس المبالغ.
    - **الاقتراح:** `suggest_frequency` (IL: المعفى سنوي، والمرخّص شهري إن تجاوز سقف سنته وإلا كل شهرين، وسنةٌ بلا سقف تأخذ آخر سقفٍ
      سابق «تقديري»؛ PS: المسجّل شهري، وغير المسجّل `None`؛ الرواتب ومسك الدفاتر شهري، والميزانية سنوي، والاستشارات `on_demand`).
      والسبب بلا أرقام مبالغ.
    - **تطبيق الباقة:** نسخ لا ربط.
    - **الصلاحيات:** كل شيء عبر `visible_clients`؛ الكتابة `office.clients.write`، والكتالوج والباقات `office.settings.manage`.

### (قديم، أُنجز) الخطوات التالية آنذاك
1. **نشر #272** (CI أخضر)، بنفس سكربت #271 (`%TEMP%\wf-acct\deploy-271.sh`، وغيّر اسم النسخة الاحتياطية). يُشغَّل بـ`bash -s` بعد
   تحويل CRLF إلى LF، وهو يأخذ النسخة الاحتياطية بنفسه. **قبله على الخادم:**
   - `git fetch`، ثم `git merge origin/newktra`، ثم `git diff origin/newktra --stat` (يجب أن يكون فارغاً).
   - `pip install`، و`npm install`، و`manage.py check`، و`makemigrations --check`، و`npm run build`.
   - **فيها هجرتان:** `tenants.0037` (AlterField لخيارات الدور، آمنة) و`accounting_office.0002` (AddField + AddIndex، آمنة).
     والسكربت يشغّل `migrate accounting_office` وحدها، **فغيّره إلى `migrate` كاملة** لتشمل `tenants.0037`.
   - ثم أغلق #272 بتعليق، وحدّث `docs/agents/acct-office-build.md`.
2. **أكمل #273:**
   - إمّا `delegation_correct` على `attempt-9b5ef424…` إن قبلها، وإمّا موجز تكملة جديد لـDeepSeek: «أكمل الواجهة والوثائق، ثم البوّابات».
   - اقرأ أولاً ما في الشجرة بنفسك (`git diff`، و`git status`).
   - ثم الحلقة كاملة: قراءة الفرق، ثم مراجعتا Standards وSpec على خط القراءة، ثم جولات التصليح (الأولى DeepSeek، والثانية Sonnet،
     والثالثة Opus)، ثم البوّابات بنفسي، ثم commit ونشر وإغلاق.
3. **بعدها #274** (اللائحة والتقويم، يحجبها 273) ثم البقية بترتيب جدول `acct-office-build.md`.

### قواعد ثابتة (من طلبات المالك)
- **التصعيد لكل تذكرة:**
  - التنفيذ والجولة الأولى: DeepSeek على خط التنفيذ بجهد **max** (`delegation_correct`). **`--effort high` لـSonnet/Opus وحدهما.**
  - الثانية: **Sonnet 5.5**، والثالثة: **Opus 5.5**، كلاهما عبر `/claude-delegate`:
    `node C:\Users\asus\.agents\skills\claude-delegate\scripts\relay.mjs --brief <ملف> --cd D:\Users\asus\Desktop\ktra --model sonnet|opus --effort high --timeout 1h30m --out-dir %TEMP%\wf-acct\relay\<id>`.
    شغّله بالخلفية، وتحقّق من `effort=high` في `result.json`.
  - الموجزات في `%TEMP%\wf-acct\briefs\`.
- **`claude` مسجَّل الدخول الآن.** إن ظهر «OAuth expired» فاطلب من المالك `/login`.
- **`lint-imports`:** `C:\Users\asus\AppData\Roaming\Python\Python313\Scripts\lint-imports.exe`.
- **البوّابة الكاملة محلياً تُسقط 4 حرّاس بيئياً** يمسحون `.agents/worktrees/`. أثبتُّ أنها بيئية: لا مخالِف خارج `.agents`. وCI
  أخضر هو الحكم.
- **migrate من صفر:** `$env:KTRA_MIGRATIONS_DB=<temp>.sqlite3; python manage.py migrate --settings=core.test_settings`.
  الاختبارات بـ`--nomigrations` لا ترى ترتيب الهجرات.

## الآن بالضبط — بناء موديول مكتب المحاسبة (#271–#291)

### الطلب والقواعد
- **طلب المالك 2026-10-30، وهو «نفّذ»:** «/implement كل التذاكر باستخدام وكيل تنفيذ … وبين كل تذكره وتذكره راجع انت
  باستخدام git diff ومهارة كود ريفيو … ما توقف لتخلص كل شي واعمل ملف تقدم كل تذكره بتخلص حدثو».
  - هناك هدف (goal) نشط بهذا المعنى.
- **ملف التقدّم:** `docs/agents/acct-office-build.md`. فيه جدول الـ21 تذكرة وسجلّ، ويُحدَّث بعد كل تذكرة تُستلَم.
- **التصعيد حسب جولة التصليح، لكل تذكرة:**
  - **المرّة الأولى:** `delegation_correct` للمنفّذ نفسه.
  - **المرّة الثانية:** Sonnet 5.5.
  - **المرّة الثالثة:** Opus 5.5.
  - Sonnet وOpus ليسا في الأسطول، فاستعمل `delegate_choose_model` عند الحاجة. يسأل المالك، ويُستهلك تأكيده مع أوّل إرسال.
- **الأسطول:**
  - **التنفيذ:** `lane-7587384e-b0bf-4913-8361-67a1a1b59325`، وهو DeepSeek V4.1 Flash بجهد **max**.
  - **القراءة:** `lane-da7d75a7-91f6-4032-ae4a-be40c4285cc8`، بجهد **high**.
  - **المراجعتان** (Standards وSpec، مهارة `code-review`) تُرسلان متوازيتين على خط القراءة، بموجز «قراءة فقط».
  - **سأل المالك:** لماذا المراجعة عبر وكيل؟ جوابي: أقرأ الفرق بنفسي أوّلاً، والوكيلان «عين ثانية» تطلبها المهارة.
  - **اقترحت:** نقل المراجعة إلى خط `max`. **لم يُجب بعد.**
- **الحلقة لكل تذكرة:**
  1. موجز مكتفٍ بذاته يبدأ بـ«شغّل `/engineering-protocol` أولاً».
  2. `delegate` على خط التنفيذ، ثم `delegation_wait`.
  3. `delegation_review`، وأقرأ كل ملف بنفسي.
  4. المراجعتان المتوازيتان. أتحقّق من كل ملاحظة، وأرفض ما يخالف قراراً محسوماً.
  5. موجز تصليح واحد يجمع الكل.
  6. بعد النظافة: البوّابات بنفسي.
  7. commit، ثم `git push origin newktra`، ثم CI أخضر، ثم النشر حسب `CLAUDE.md` (`deploy-local-to-modern`).
     - إن وُجدت هجرة: نسخة احتياطية أوّلاً.
  8. إغلاق التذكرة، وسطر في `docs/agents/runs.md`، وتحديث `acct-office-build.md`.
- **البوّابة الكاملة على هذا الجهاز تُسقط 8 اختبارات بيئياً، بقول المنفّذ إنها تسقط على HEAD نظيفاً:**
  - **أربعة تاريخية:** `after_sales/tests/test_shop_days_extension.py` (2) و`crm/tests/test_lead_contact_stats.py` (2).
  - **أربعة حرّاس مسحٍ** تقرأ `.agents/worktrees/` غير المتتبَّعة، ومنها worktree النموذج المرئي:
    - `employee_ops/tests/test_isolation_guard.py`
    - `platform_ops/tests/test_isolation_guard.py`
    - `core/tests/test_docs_freshness.py` (`test_production_code_has_one_source_of_today`)
    - `core/tests/test_terminology_guard.py`
  - **لم أتحقّق بنفسي على HEAD بعد.** للتحقّق: أنشئ worktree خارج المستودع على HEAD وشغّل الثمانية هناك. وCI النظيف هو الحكم.
  - **إصلاح مقترح، مفصول ولم يُبلَّغ للمالك بعد:** أن تُقلِّم الحرّاس الأربعة `.agents`.

### الحالة الآن — #271 «الأساس»
- **الأساس قبل البناء:** commit `bc52288a`، وفيه الوثائق وملف التقدّم.
- **التسليم الأوّل:** المحاولة `attempt-34e41843-9fe4-421d-8c08-b69e7b0f7728`. قرأته كاملاً واختُتم `correction-required`.
  - **ما بناه:**
    - app `accounting_office` بنماذجه السبعة.
    - `settings_registry.py` والمحلّل `resolve_setting`.
    - API تحت `/api/accounting-office/`.
    - قالب `accounting_office` يرخّص الوحدة عند الإنشاء.
    - الواجهة: `frontend_v2/components/accounting-office/` (القائمة، والملف، والإعدادات، وأول تشغيل).
    - `CONTEXT.md` و`docs/modules/accounting_office.md`.
  - **البوّابة الكاملة عندي:** 8 failed، وهي البيئية نفسها، و6697 passed.
- **المراجعتان مختتمتان** `reviewed-completion`:
  - Standards: `attempt-9744aeeb-…`
  - Spec: `attempt-1ddd127d-…`
  - **أخطر ما وجدتاه:** الهجرة `0001` تنشئ العمود المولَّد `primary_client_key` قبل حقل `client`، فلا تُطبَّق. والاختبارات بـ`--nomigrations` لا تراه.
- **جولة التصليح 1 (للمنفّذ نفسه) جارية:** المحاولة `attempt-f10ecdce-54e9-412b-9d3f-df7f2efaadf5`، الـjob `delegation-19`. فيها 26 بنداً محسوماً.
  - **الخادم:**
    - ترتيب الهجرة وإثبات `migrate` على SQLite فارغة.
    - تصنيفات البطاقة الرسمية:
      - **PS:** licensed / exempt / unregistered.
      - **IL:** authorized / exempt / nonprofit.
    - تفريغ تصنيفات البطاقة غير الصالحة عند تغيّر `tax_system`.
    - منع إنشاء زبون قبل أول تشغيل.
    - `save()` يرفض شركةً مخالفة.
    - N+1: `resolve_setting_for_clients`، وقائمةٌ بلا بطاقة، واختبار `assertNumQueries`.
    - المستلِمون باستعلامين.
    - `client_label` «يوم راحة الزبون».
    - رفض «ارجع للافتراضي» لإعدادٍ بلا افتراضي.
    - حذف جهة غير مربوطة فقط، وبحث `?q=` في الجهات.
    - تحقّق `annual_sales`.
    - `log_activity` للإنهاء والإعادة.
  - **الواجهة:**
    - لا استيراد من `components/accountant/office/`.
    - «الزبائن» في كل مكان.
    - تسميات الخادم بدل الثوابت المحلية.
    - رابط `?client=<id>` للملف.
    - لا مسح لتعديلات البطاقة غير المحفوظة.
    - `useConfirm` قبل «أنهِ».
    - منتقي جهات بالبحث.
    - رسائل `utils/drfError.ts`.
    - أول تشغيل بأزرار اختيار.
    - رسالة `ModuleLicenseGuard` ثابتاً واحداً.
    - ثوابت مجموعات `shell_manifest` المشتركة، وبيان `accounting_firm` مطابقاً حرفياً.
  - **الوثائق:**
    - `CONTEXT.md` بالمعجم كاملاً من `%TEMP%\wf-acct\spec\254-glossary.md`، وبلا قسم «ما بُني».
    - تصحيح وثيقة الموديول (`core` يُستورد، و«طلبٌ مجهول»).
- **تحديث 2026-10-31 00:25:** جولة التصليح 1 **انتهت** (`attempt-f10ecdce-54e9-412b-9d3f-df7f2efaadf5`، completed). نُودي
  `delegation_review` عليها، و**لم تُقرأ ملفاتها بعد ولم تُختتم**.
  - **تقرير المنفّذ (ادّعاء لا دليل):** البنود الـ26 كلها منجزة.
    - `accounting_office/tests`: 98 passed.
    - `migrate` على SQLite فارغة: OK.
    - `makemigrations --check`: نظيف.
    - `lint-imports`: 3 kept.
    - `tsc` وnpm test (1386) وbuild: خضراء.
    - البوّابة الكاملة: `4 failed, 6719 passed`. الأربعة حرّاس المسح على `.agents/worktrees/`، والأربعة التاريخية مرّت هذه المرّة.
  - **انحرافاته:**
    - `value_label` يأتي من الخادم (`setting_value_label`).
    - علم `can_reset` جديد.
    - `popstate` صناعيّ لفتح الملفّ من شاشة الإعدادات.
    - `OfficeUi.tsx` محليّ داخل `components/accounting-office/`.
- **تحديث 00:35 قبل الـcompact:** قرأتُ `services.py` النهائي وترتيب الهجرة، وهما سليمان.
  - **فحوصي:**
    - `accounting_office/tests` و`core/tests/test_shell_manifest.py` و`tenants/tests`: **311 passed** ✓.
    - `makemigrations --check`: No changes ✓.
    - `lint-imports` غير معروف في shell PowerShell، فيُشغَّل من بيئة المشروع: `python -m importlinter` أو مسار venv.
    - فحص الواجهة أُلغي قبل أن ينتهي، فأعِده.
  - **مراجعتا Standards/Spec على الحالة النهائية** (`attempt-0dda0691…` و`attempt-6b7c0c4c…`) **أوقفتُهما** لأجل الـcompact. **أعِد إرسالهما**: الموجز نفسه، على خط القراءة.
  - **بقي:** قراءة الواجهة النهائية، والمراجعتان، ثم البوّابة الكاملة، ثم الاستلام.
- **تحديث 2026-10-31 00:40:** فحصتُ بنفسي: الواجهة (tsc/1386/build) ✓، و`lint-imports` بمسار
  `C:\Users\asus\AppData\Roaming\Python\Python313\Scripts\lint-imports.exe` (3 kept) ✓. قرأتُ الواجهة والـviews/serializers/models
  كاملة. المراجعتان أُعيدتا واختُتمتا (`attempt-06959532…` Standards، و`attempt-aee4b903…` Spec).
  - **جولة التصليح 2 (27 بنداً) جارية:** `attempt-4bdef7d9-5b80-43ef-9236-ab8e5394c746` (job `delegation-24`)، تصحيحٌ
    لـ`attempt-f10ecdce…` على DeepSeek. Sonnet غير متاح، والمالك اختار «كمّل مع DeepSeek».
  - أهمّ البنود: `onMissing` يُعيد تحميل الملف (يمسح التعديلات)، و`useSearchParams` بدل `popstate`، و`**` حرفية، وN+1 في
    `_propagate_tax_system`، و`update` بلا معاملة، و`CONTEXT.md` بعمود العلاقات، واختبارات البيان والحارس.
  - **بعدها:** قراءة الفرق، ثم مراجعتان على الحالة النهائية. إن بقي شيء فهي الجولة 3 (Opus غير متاح، فـDeepSeek).
- **تحديث 2026-10-31 02:45:** الجولة 2 (`attempt-4bdef7d9…`) قُرئت وفحصتُ `makemigrations`/`lint-imports` ✓، واختُتمت
  `correction-required` بأربعة بنود: «جلبه جلبه» في `OfficeClientFile.tsx:84`؛ الجهة المحذوفة تبقى في `pickerContacts`؛
  `test_settings_guard` يكتب `_guard_probe_app/` في جذر المستودع (سباق xdist) → شجرة `tempfile`؛ اختبار البوّابة المرخَّصة
  بـ`resolve()` لا يثبت شيئاً → `OPTIONS` = 200 مرخّصاً و404 بلا ترخيص.
  - أُرسلت لـDeepSeek (`attempt-362f2b5f…`) ثم **أوقفتُها** بطلب المالك: الجولة 2 لـSonnet 5.5 والثالثة لـOpus 5.5 **عبر
    `/claude-delegate`** (`node C:\Users\asus\.agents\skills\claude-delegate\scripts\relay.mjs --brief … --cd … --model opus`).
  - **العائق:** `claude` بلا تسجيل دخول (OAuth منتهٍ). بعد `/login` من المالك: راجع ما تركه `attempt-362f2b5f` جزئياً، ثم
    أرسل البنود الأربعة لـOpus بالـrelay، ثم البوّابات كاملة والمراجعتان والاستلام.
- **تحديث 2026-10-31 03:00:** الجولة 3 أخذها **Sonnet 5.5** عبر `claude-delegate`. الـrelay موجود في
  `%TEMP%\wf-acct\relay\271-r3` و`271-r3b`، والجلسة `77197a6b-c997-4854-85eb-634bfdfcd667`.
  - **ما أنجزته:** شجرة `tempfile` للحارس، و`OPTIONS` للبوّابة. ووجدت 500 حقيقياً على `OPTIONS settings/<key>/`، فأُصلح بـ`OfficeSettingsViewSet.get_object`، ومعه اختبار انحدار.
  - **فحوصي بعدها:**
    - الموديول: 323 ✓.
    - الواجهة: tsc و1386 وbuild ✓.
    - البوّابة الكاملة: `4 failed, 6731 passed` (الحرّاس الأربعة البيئيون).
  - **المراجعتان النهائيتان** اختُتمتا: Standards `attempt-564cfb13…`، وSpec `attempt-3aa0e3f1…`.
  - **الجولة 4 لـOpus 5.5 بـ`--effort high` جارية:** الـjob `pwsh-697`، والـrelay في `%TEMP%\wf-acct\relay\271-r4`، والموجز في `%TEMP%\wf-acct\briefs\271-round4-opus.md`. فيها 11 بنداً:
    - `select_related` في `_propagate_tax_system` مع اختباره.
    - فحص المستوى في `reset_office_setting`.
    - رمزا الاختبارين.
    - `OFFICE_SETTINGS_PATH`.
    - debounce لبحث القائمة.
    - جلب الرأس المكرّر.
    - تحرير الاسم ورقم الملف.
    - إخفاء «مخصَّص عند N» للإعداد المكتبي.
    - سطر الوثيقة.
  - **بعدها:** أقرأ الفرق وأشغّل البوّابات. فإن كانت نظيفة: commit، ثم push، ثم CI، ثم النشر (بنسخة احتياطية، فالهجرة جديدة)، ثم إغلاق #271.
- **تحديث 2026-10-31 03:30:** **#271 مُلتزَمة `392d7165` ومدفوعة** إلى `newktra`. الـCI run هو `41155237663`، وبيأخذ نحو ساعة.
  - **النشر بعد CI أخضر:**
    - هجرة جديدة `accounting_office.0001`، فخذ نسخة احتياطية أولاً.
    - الخادم `modern`، والـrsync لـ`dist/` يستثني كل ما في جذر الويب وليس من `dist/`.
    - بعد النشر: أغلق #271.
  - **#272 جارية على DeepSeek:** المحاولة `attempt-9f04e474-63c5-46ca-9279-0d5fff61a358`، والـjob `delegation-28`.
    - **قرارات الموجز:**
      - **الأدوار:** مالك = `manager`، ومدير = `office_manager` جديد، ومحاسب = `accountant`، وقارئ = `viewer`.
      - **مفاتيح الصلاحيات:** `office.clients.write`/`all`/`assign`، و`office.amounts.view`، و`office.settings.manage`.
      - **الموظف المسؤول:** `responsible` FK بهجرة 0002، والتحويل عبر `POST assign/`.
      - **مصدرا الرؤية والمبالغ:** `visible_clients` للرؤية (زبون غيره ⇒ 404)، و`can_see_amounts`/`mask_amounts` مع حارسٍ للمبالغ.
      - **الواجهة:** الأدوار عبر الـAPI القائمة `members/change-role/` و`/api/permissions/member/`.
  - **#273 بعد #272، لا بالتوازي:** الاثنتان تلمسان `accounting_office` والهجرة.
- **تحديث 2026-10-31 05:20:** **#271 نُشرت وأُغلقت.**
  - **النشر:** دمج `a239776b` على `modern`، والنسخة الاحتياطية في `/root/backups/ktra-before-271-20261031-023401.sql`.
  - **سكربت النشر:** `%TEMP%\wf-acct\deploy-271.sh`، ويُشغَّل بـ`bash -s` بعد تحويل CRLF.
  - **#272، جولة التصليح 1 عند DeepSeek:** المحاولة `attempt-42431db4…`، وقرأتُها.
    - أنجزت 12 بنداً، منها `visible_contacts` و`register_document_history_guard` و`_assert_role_assignable` و`select_for_update`.
    - البوّابة الكاملة عندي: `4 failed` (البيئية) و`6773 passed`.
  - **المراجعتان النهائيتان لـ#272:** Standards `attempt-93f369f5…`، وSpec `attempt-3b4d01ae…`، وكلتاهما مختتمة.
  - **الجولة 2 جارية عند Sonnet 5.5** عبر `claude-delegate` بـ`--effort high`:
    - الـjob: `pwsh-920`.
    - الـrelay: `%TEMP%\wf-acct\relay\272-r2`.
    - الموجز: `%TEMP%\wf-acct\briefs\272-round2-sonnet.md`.
    - **البنود الأربعة:** قفل حقل المبلغ، وإنشاء الزبون لغير العضو، و`user` مطلوب، وتأكيد الحارس.
  - **بعدها:** أقرأ الفرق وأشغّل البوّابات، ثم commit ونشر. فيها هجرتان: `tenants.0037` و`accounting_office.0002`.
- **الخطوة التالية (القديمة):**
  1. ~~`delegation_wait`~~ — تمّ.
  2. `delegation_review` (مُنادى)، ثم قراءة الفرق كاملاً بنفسي.
  3. المراجعتان من جديد على الحالة النهائية.
  4. إن بقيت ملاحظات فهذه **المرّة الثانية**: تذهب إلى Sonnet 5.5 بـ`delegate_choose_model`.
  5. وإلا: البوّابات، ثم الاستلام والنشر. الهجرة جديدة، فخذ نسخة احتياطية قبلها.
  6. إغلاق #271 وتحديث ملف التقدّم، ثم #272 و#273. كلاهما يحجبه 271 وحده؛ أُرسلهما متوازيين إن لم تتقاطع الملفات.
- **مراجع الموجزات:**
  - التذاكر بـ`gh issue view N`، والمواصفة #270، وتعديلها `6532297968` (الانتقال مباشر).
  - قرارات الحسم في `%TEMP%\wf-acct\spec\*.md`.
  - البحوث على فروع `research/acct-*` (`git show research/acct-X:docs/research/accounting-office-X.md`).
  - النموذج المرئي: `.agents/worktrees/prototype/acct-office-screens/prototypes/acct-office-screens/*.html`.
- **ما زال معلّقاً عند المالك:**
  - #209 مصباح الحضور.
  - هل تُنقل المراجعة إلى خط `max`.

## سابقاً — wayfinder: موديول مكتب محاسبة احترافي من الصفر

- **الطلب (2026-10-30):** قالب/موديول «مكتب محاسبة» احترافي **من الصفر** — «لا تركن ولا تبني على الشغل الحالي
  بالمرة». المحاسب طلب: إشعارات للزباين، مواعيد، وإشعارات «باللي عليهم». مسجَّل في `progress.md`.
- **الخريطة:** [#247](https://github.com/thabet-toma/ktra2/issues/247) «خريطة: موديول مكتب محاسبة احترافي — من الصفر»
  (`wayfinder:map`). **الوجهة: مواصفة** لا تنفيذ (التنفيذ خريطة لاحقة حين يقول المالك «نفّذ»). كل قرارات التأطير
  في قسم Notes بالخريطة — **اقرأ جسم #247 أولاً** (`gh issue view 247`).
- **قرارات التأطير باختصار:** كل الخدمات تُصمَّم والمكتب يفعّل ما يقدّمه ويحدّد باقة لكل زبون؛ النظام الضريبي
  (فلسطيني/إسرائيلي) **يختاره المكتب**؛ **زبون المكتب خارجي — لا شركة على المنصة ولا ربط ولا دخول**؛ واتساب
  بكبسة الموظف؛ موظفون وكل زبون مُسنَد؛ أتعاب = اشتراك شهري + إضافات، مسودّة شهرية؛ دفتر داخل النظام فقط لمن
  باقته «مسك دفاتر»؛ قائمة مستندات مطلوبة لكل فترة يعلّمها الموظف «وصل»؛ تسعير الموديول خارج النطاق.
- **مغلق (بحث، 4/4)** — كلٌّ بتعليق حسم وسطر في Decisions-so-far، والتقارير على فروع مؤقتة مدفوعة:
  - #248 النظام الفلسطيني ← `research/acct-tax-ps` (`docs/research/accounting-office-tax-ps.md`)
  - #249 النظام الإسرائيلي ← `research/acct-tax-il` (`docs/research/accounting-office-tax-il.md`)
  - #250 واتساب ← `research/acct-whatsapp` (`docs/research/accounting-office-whatsapp.md`)
  - #251 برامج إدارة المكاتب ← `research/acct-practice-mgmt` (`docs/research/accounting-office-practice-management.md`)
  - الـworktrees السبعة موجودة محلياً تحت `.agents/worktrees/research/*` (مُلتزَمة ومدفوعة — آمن حذفها).
  - **TaxDome صار مقروءاً** (`help.taxdome.com/article/...`)، فما قاله #251 عن حجبه قديم.
- **أهمّ ما خرج من البحث:** يوم العطلة الذي يزيح الموعد الإسرائيلي **حسب دين الزبون** (حقل على الزبون)؛ لائحة
  المواعيد السنوية **بيانات تُستورد** لا معادلة؛ الفلسطيني **بلا قاعدة عطلة** (ينبّه لا يزيح) وبعض مواعيده **نسبية**
  (30 يوماً من الاقتطاع)؛ الضمان الاجتماعي الفلسطيني موقوف منذ 4/2019؛ «الفترة» كيان صريح والباقة تولّد نسخة عمل
  لكل فترة؛ واتساب v1 = `wa.me` + سجلّ إرسال، v2 = Cloud API برقم لكل مكتب؛ لا Evolution لرسائل الزباين.
- **الجبهة الآن (frontier):**
  - **#252 استبيان المحاسب — مُغلقة:** المالك أجاب بدله (حجم المكتب إعداد، نظام ضريبي واحد لكل مكتب، الخدمات
    المعتادة كلّها، رسائل افتراضية يعدّلها المكتب، والباقي بالبحث). الاستبيان لم يُرسَل.
  - **بحث مغلق (3/3)، كلٌّ مُلتزَم ومدفوع وبتعليق حسم وسطر في Decisions so far:**
    - #259 المواعيد والتذكير والرسائل ← `research/acct-reminders` (`docs/research/accounting-office-reminders.md`):
      «المواعيد» = استحقاق عمل + كيان «موعد» داخلي صغير بلا حجز ذاتي؛ 3 أيام/مرّة (TaxDome)؛ مسوّدات ar/he.
    - #260 المستندات ← `research/acct-documents` (`docs/research/accounting-office-documents.md`): قائمة 3 طبقات بجدولي
      PS/IL؛ الحفظ على الزبون (PS ٥، IL ٧/٦) والمدد بيانات؛ الملف والحالة كيانان، نسخة عمل والأصل عند الزبون.
    - #261 الأدوار والأتعاب ← `research/acct-roles-fees` (`docs/research/accounting-office-roles-fees.md`): 3 أدوار +
      مفتاحا «زباين غيره»/«المبالغ» مطفآن للمحاسب؛ الإسناد على الزبون؛ الضغط بالأعداد؛ مسودّة + إضافات عليها.
    - **تعارض مفتوح لتذكرتي الأتعاب/الإشعارات:** إيقاع تذكير الأتعاب (#259: T-3، +3، +7، سقف 3 ↔ #261: +3، +7،
      سقف 2)؛ ونافذة الإرسال «لا جمعة/سبت» يجب أن تتبع يوم راحة الزبون.
    - **ضباب جديد في الخريطة:** مكان استضافة البيانات والنسخ الاحتياطي (إسرائيل §25(ו)(2): داخل إسرائيل أو المنطقة).
  - **#253 مكاتب الإنتاج — مُغلقة (قراءة فقط، `READ ONLY` + `ROLLBACK`):** لا مكتب حقيقي. 7 `accounting_firm` + 1
    `client_book` تجريبية، وطبقة المكتب 5 زبائن + برنامج واحد من الحسابين 1 و2؛ الحذف آمن بلا ترحيل. مفتوح لـ#258:
    المكتب 22 (الحساب 10) وبوابة المحاسب (3 ارتباطات نشطة على 1/3/6). `last_login` لا يصلح مقياساً (فارغ للجميع).
  - **#254 المعجم — مُغلق** (grilling، اعتمد المالك س1–س17): 19 كلمة في تعليق الحسم (الزبون = منشأة بملف ضريبي؛
    جهة الاتصال = شخص؛ خدمات الزبون بتواريخ سريان؛ الالتزام ≠ شغلة الفترة ≠ الموعد؛ قائمة أوراق شهرية + سنوية
    بأربع حالات؛ تذكير للزبون / تنبيه داخلي؛ اشتراك شهري + خدمة إضافية + حساب الزبون؛ دفتر الزبون لمسك الدفاتر).
  - **قاعدة الإعدادات (طلب المالك، في Notes الخريطة):** ما يختلف بين المكاتب = إعداد افتراضه توصيتنا؛ ما يختلف بين
    الزباين = تخصيص لكل زبون. ثوابت: لا دخول للزبون · المواعيد الرسمية من اللائحة · التاريخ لا يُمحى. **كل تذكرة
    تسرد إعداداتها (المستوى + الافتراضي).** والنظام الضريبي صار إعداد مكتب قابلاً للتخصيص لكل زبون (يعدّل #252).
- **#255 محرّك الالتزامات مغلقة** (حسم issuecomment-6523937017): المنصة تكتب لائحة المواعيد **والمكتب يعدّلها على
  مسؤوليته** (عدّل ثابت المعجم؛ Notes الخريطة وتعليق على #254 محدَّثان)؛ بطاقة ضريبية × خدمات = التزامات؛ ثلاث حالات
  مخزَّنة و«قريب/ناقصه أوراق/متأخّر» مشتقّة؛ جدول 19 إعداداً بافتراضاتها.
- **#256 الإشعارات مغلقة** (حسم issuecomment-6524019994): أربعة أنواع؛ قائمة «جاهز للإرسال» بكبسة `wa.me` ورسالة
  واحدة لكل شخص يومياً؛ أتعاب +3/+7 بحد 2 (حسم التعارض)؛ موافقة/سحب/تأجيل؛ تصعيد وسجلّ؛ جدول 17 إعداداً.
- **#257 الأتعاب مغلقة** (حسم issuecomment-6524158255): **طريقة الأتعاب إعداد** (اشتراك + إضافات افتراضياً · سعر لكل
  خدمة · ساعة) يُخصَّص لكل زبون (طلب المالك)؛ مسودّة يوم 1 مقدّماً؛ الفاتورة المعتمدة ضريبية لا تُمحى؛ دفعات يدوية
  بسند قبض؛ قيد تلقائي في دفاتر المكتب؛ جدول 23 إعداداً.
- **#262 بحث فاتورة المكتب قانونياً مغلقة** (حسم issuecomment-6524389147؛ فرع `research/acct-invoice-legal` commit
  590045d2، مدفوع): IL رقم التخصيص فوق 5,000 ₪ قبل מע"מ من 1.6.2026، شرط لخصم المدخلات لا للإصدار، والمنصة تحتاج
  تسجيل بيت برمجيات + נספח ה' + token لكل مكتب؛ PS لا رقم، والحقول في تعليمات الوزير (لم تُقرأ). أُضيف للضباب:
  تسجيل المنصة لدى רשות המסים (قرار تشغيلي للمالك) وتعليمات الفواتير الفلسطينية.
- **#258 مصير الموجود مغلقة** (حسم issuecomment-6524637847): المكتب 22 **حقيقي** ويُنقل للجديد مع إبلاغه؛ بوابة
  المحاسب تبقى ميزة مستقلة وتُزال جسورها فقط؛ طبقة المكتب والقالبان تُحذف بلا ترحيل؛ الجديد بجانب القديم ولا حذف قبل
  أن يعمل. **طلب المالك:** دفتر الزبون وكل ما يمسّ «كيف بنينا نظام المحاسبة» جديد بالكامل (في Notes الخريطة). **وضّح
  المالك:** «لا قصدي مكتب المحاسبة بس» — محرّك القيود العام (`post_journal`) مسموح من الداخل لدفتر الزبون وقيد الأتعاب.
- **الضباب كله صار تذاكر:** #263 دفتر الزبون (grilling) · #264 الرواتب (grilling) · #265 تشغيل المنصة لمكاتب إسرائيل
  (grilling) · #266 حقول الفاتورة الفلسطينية (task — نسخة فاتورة حقيقية أو التعليمات) · #267 الشاشات (prototype، محجوبة
  بـ#263 و#264). «بوابة الزبون» نُقلت إلى Out of scope.
- **#268 بحث دفاتر الزباين مغلقة** (commit bc13dce6، مدفوع): الدارج دفتر مستقل لكل زبون؛ المبسّط قانوني للصغار؛ PS
  138/2005 م6(7) تشترط تسجيل النظام المحاسبي لدى المالية (أُضيف لـ#265).
- **#263 دفتر الزبون مغلقة** (حسم issuecomment-6525020682): **دفتر جديد داخل الموديول بلا المحرّك العام** (اختيار المالك،
  يعدّل توضيح المحرّك لدفتر الزبون وحده؛ قيد الأتعاب في دفاتر المكتب يبقى على المحرّك)، منفصل لكل زبون، بسيط أو مزدوج
  حسب الزبون؛ جدول 10 إعدادات. Notes الخريطة محدَّثة.
- **المالك فوّض حسم الباقي بالتوصيات** («اعمل كل التذاكر بتسكير حسب توصيتك»)، وقرّر: **النسخة الأولى غير رسمية بلا
  تسجيل**. حُسمت: #265 تشغيل المنصة (issuecomment-6525119411: «إشعار أتعاب» للعلم بدل الفاتورة الضريبية، الدفتر «نسخة
  عمل»، الفوترة الرسمية إعداد مقفل حتى التسجيل) · #264 الرواتب (متابعة استحقاق فقط) · #267 الشاشات (مواصفة نصّية
  لتسع شاشات؛ النموذج المرئي أوّل خطوة في التنفيذ) · #266 أُغلقت **خارج النطاق** (تعود مع خريطة التسجيل). تعليقات
  تعديل على #257 و#262 و#263. Out of scope + Notes الخريطة محدَّثة. (الإغلاق عبر `gh issue close` فشل بـGraphQL؛ أُغلقت
  عبر REST `PATCH .../issues/N state=closed`.)
- **تعديل المالك على الفاتورة:** «بدي شي زي الفاتورة الضريبية نفس الرسمية الفرق انو مش تكون رسمية» ⇒ فاتورة الأتعاب تطابق
  الفاتورة الضريبية حقولاً وترتيباً، بعنوان ثابت «فاتورة أتعاب — ليست فاتورة ضريبية». أُعيد فتح #266 وحُسمت
  (issuecomment-6525668553) من قرار الوزير 25/2025 م4 — بحث `research/acct-invoice-ps` commit 6f8db8c9، التقرير
  `docs/research/accounting-office-invoice-ps.md`؛ سطر الضريبة بإعداد «مشتغل مرخّص» (م.55). تعليقات تعديل على #257 و#265.
- **إشعار الدفع والنسب (طلب المالك، «اعتمد كل اشي»):** تعليقات تعديل على #256 (إشعار دفع قبل 15، ألوان)، #255 (مبلغ
  الالتزام من الدفتر أو يدوي)، #263 (نسبتا ض.ق.م وضريبة الدخل على حساب المصروفات). بحث #269 (`research/acct-expense-rates`
  commit af594c09، التقرير `docs/research/accounting-office-expense-rates.md`) حُسم وأُغلق (issuecomment-6526139853): مثال
  الأثاث = إهلاك ⇒ «فئة أصل ونسبة إهلاك» على حساب الأصل الثابت؛ لائحة افتراضية لكل نظام، و«راجع» لا يُملأ بصمت.
- **الحالة: كل تذاكر الخريطة #247 مغلقة** (22/22). المواصفة مكتملة في حسوم التذاكر وتعديلاتها.
- **النموذج المرئي جاهز (طلب المالك 2026-10-30):** `prototypes/acct-office-screens/` على فرع `prototype/acct-office-screens`
  (commit 2d4fb5e8، مدفوع) — ست شاشات + `shoot.mjs` يولّد الصور. **الصور للمحاسب** في
  `D:\Users\asus\Desktop\صور للمحاسب - مكتب المحاسبة` (سطح المكتب على `D:` لا `C:`) مع أسئلة `اقرا-اول.md`. المنسّق
  رآها بعينه، وأعاد محاولة واحدة (عمود وهمي في شبكة الأوراق · «اللي عليه» صار 1,682 شاملة الضريبة).
  **بانتظار ملاحظات المحاسب** ← تعديلات على تذاكرها ← `/to-spec` ← `/to-tickets`.
- **تنظيف التذاكر (طلب المالك):** أُغلقت 31 تذكرة مبنيّة ومنشورة لم تُغلق (الكفالة، الموظفون، #210، #160/#162/#167/#168)،
  و#184 «غير مخطَّط». **المفتوح الآن: #247 (خريطتنا) و#209 فقط.** #209 = مصباح الحضور الميّت؛ توصية: يُشال بمهمة منفصلة
  بعد `/to-spec` (لم يقرّر المالك بعد).
- **المالك قال «جاهزين ل تو سبيك»** — لا ننتظر ملاحظات المحاسب؛ تُضاف تعديلاتٍ إن وصلت.
- **المواصفة منشورة (`/to-spec`، 2026-10-30):** [#270](https://github.com/thabet-toma/ktra2/issues/270) بوسم `ready-for-agent`،
  تذكرة فرعية لـ#247 (وسطر «الحالة» في Notes الخريطة يشير إليها). نقطة الفحص التي اعتمدها المالك: طبقة الخدمات بتاريخ
  مُعطى («عقل» الموديول) + فحصان صغيران (API للصلاحيات والعزل · الورقة المصيَّرة). قراران من المنسّق يستحقّان عين المالك:
  غرامة التأخير والأتعاب بالساعة **خارج النسخة الأولى** (صيغتهما لم تُحسم)؛ والزبون **طرف ذمّة في دفاتر المكتب** يُنشأ
  تلقائياً للقيد. #209 ما زال مفتوحاً بلا قرار.
- **التذاكر منشورة (`/to-tickets`، 2026-10-30):** #271–#291 «مكتب المحاسبة ١…٢١»، فرعية لـ#270، بحوافّ `blocked_by` أصلية.
  الترتيب: ١ الأساس ← (٢ الأدوار ∥ ٣ الخدمات) ← ٤ اللائحة ← ٥ «اليوم» ← (٦ التأخير ∥ ٨ الأوراق) ← … ← ٢١ الانتقال (آخراً).
  تعديل المالك على #270: الانتقال مباشر، المكتب 22 بلا نقل بيانات القديم وبلا شرط إبلاغ. **التالي: التنفيذ حين يقول المالك
  «نفّذ»** — يبدأ بـ#271 بحلقة `CLAUDE.md` (موجز ← منفّذ ← قراءة الفرق ← مراجعتان ← فحص ← نشر).
- **ملف الانتقال الحالي:** `%TEMP%\handoff-acct-office-tospec.md` (يستبدل `handoff-acct-office-prototype.md`).
  عند «نفّذ»: `CONTEXT.md` من معجم #254.
- **التوجيه (fleet):** البحث في الإنترنت والكتابة ← lane «تنفيذ وكتابة الكود والبحث في الانترنت» (max)؛ lane
  «قراءة الكود» (high) للقراءة فقط.
- **أدوات مساعدة:** أجسام التذاكر وتعليقات الحسم مسوّدة في `%TEMP%\wf-acct\`. تحديث الخريطة: إدراج السطر بعد
  `<!-- the index: one line per closed ticket -->` في جسم #247 (`gh issue edit 247 --body-file`، UTF-8 بلا BOM).
- **المالك ليس مبرمجاً:** اسأله بالعامية وبمثال محسوس («أبو أحمد صاحب السوبرماركت»).

## الخطة السابقة (مكتملة ومنشورة)

`docs/plans/2026-10-21-inventory-count-category-tree.md` — 13 تذكرة (S1·S2·B1·B2·B3·R1·C1·C2·C3·DST1·SEC1·SEC2·K1–K4)
كلّها مستلَمة ومنشورة؛ آخرها K4 (`b453a41a` ← الخادم `6a411579`). نُشرت K2/K4 قبل CI بطلب المالك — **افحص CI لـ`b453a41a`**.
مفتوح منها: فحص ETag خارج القفل (K1)، `lint-imports` خارج البوّابات، `countInputVariance` يعرض الفرق عبر `Number`
(عرضٌ فقط)، لا اختبار لدور «مستعرض» في محاكي روابط العدّ.

## مفتوح

- قيد فرادة `(tenant, stocktake_number)` بعد فحص تكرارات قاعدة الإنتاج.
- من منفّذ SEC2 (لم يُصلَح، صفٌّ فاسدٌ فقط): `ProductViewSet.add_brand` يحسب `will_create`/حدّ الخطة من `Product.objects.filter(family=family)` بلا شركة؛ و`adopt_family_for_product` يقبل `tenant` مخالفاً لشركة المنتج (مستدعيه الوحيد آمن).
- مسح DST1 (تقريرٌ لم يُصلَح): مقارنات بنفس `tzinfo` قد تعبر الساعة المتكرّرة في `activate_subscription_policy`
  و`activate_performance_evaluation_policy` و`activate_employee_compensation_policy` و`activate_service_unit_catalog`
  (`platform_ops/services.py`)، و`hr/attendance.py` (`resolve_attendance_date`، `recompute_attendance_day`،
  و`scheduled_minutes` تطرح 60 بدل 120 لوردية تعبر التحوّل).
- قرص الخادم 94–97% — النسخ الاحتياطية في `/root/backups` و`/root/ktra/db/` تأكل المساحة.
- `modern` على الخادم و`origin/modern` متباعدان (632 مقابل 29 commit من دمجات `localAccount`) — الدفع تقديمٌ
  سريع فقط، فيُتخطّى حتى يقرّر المالك.
- البوّابة المعزولة قبل fix2: 1 فشل (البيئيّ المعروف PaperAmountsPayloadTest) و8031 نجاح. مراجعتا الحالة النهائية: لا blocker ولا major، ملاحظاتٌ minor (تعليقاتٌ قديمة، استيراداتٌ داخل الدالة، ثابتٌ مكرّر، product_display_name، اختباراتٌ ناقصة للتحصيل وإذن التسليم وSTOCK_ISSUE ومزامنة FIFO في المُعيدين).
- ✅ fix2 (الجولة 2) انتهى على Hydrogen (completed، exit 0؛ 28 passed للملف و2055 للمجموعات الثلاث، أحمر-قبل-أخضر للخمسة). قرأتُ الفرق كاملاً: سليم، وnit اثنان يُسجَّلان ولا يُكرَّران (تعليق G3 إنجليزي طويل في cogs_method.py، واستيراد client_for مكرّر داخل test_deliver_returns_warning).
- ✅ بعد fix2: البوّابة المعزولة 8038 passed + البيئي وحده، وmakemigrations ← No changes، والمراجعتان Opus ← Spec PASS وStandards PASS.
  لكن Standards وجدت تعليقين قديمين في `inventory/models.py` (فوق `COGS_METHOD_FIFO` وعلى `cogs_cost`) وCLAUDE.md يمنع إيداعهما، فـ:
- 🔄 **fix3 (الجولة 3) يعمل على Sonnet high** (وكيل `sonnet-implementer`) بموجز `scratchpad/briefs/M1B-2-fix3.txt`: H1–H2 تعليقا models.py،
  H3 docstring، H4 تعليقا cogs_method.py، H5 اختبار تقريب يفرّق HALF_UP عن HALF_EVEN (1×10.125←10.13) + حذف client_for المكرّر + اختبار avco،
  H6 `cogs_warnings` في `payment_voucher` مع post:true، H7 `tenant_id` في استعلام `_post_stock_out_for_invoice`، H8 صفّ cogs_method.py في inventory.md.
- ▶ التالي: قراءة فرق fix3 كاملاً (وأدلة الأحمر لـH5a/H5c/H6)، ثم مراجعتا الحالة النهائية Opus + gate.py + makemigrations متوازية، ثم commit محلي
  (ملفات M1B-2 + السجلّات + بطاقة الخطة + صفّ §5 ← منجز)، ثم runs.md (fix2 Hydrogen high agy 1.5.11؛ fix3 Sonnet high). جولة رابعة لمانع/major فقط ← Opus high.

- 2026-11-18: fix3 قُرئ فرقه كاملاً ونظيف. أُطلقت المراجعتان النهائيتان (Opus Standards + Spec على `m1b2-final.diff`، أساس `3cbbc396`) والبوّابة المعزولة بالخلفية. التالي: إن نظفت → commit محلي لـM1B-2 + السجلات، ثم تذكرة الأمان (allow-list لـ`reference_type` اليدوي في `inventory/views.py`) ثم M1B-3.

- 2026-11-18: **M1B-2 مُودَع محلياً `1a06ee68`** (مراجعتان PASS، البوّابة 8040 + البيئي، بلا هجرة). minors مُرحَّلة لموجز M1B-3 (مسجّلة في progress.md). أُطلقت تذكرة الأمان SEC-MANUAL-REF على Hydrogen (`runs/sec-manual-ref`، موجز `briefs/SEC-manual-ref.txt`): الحركة اليدوية تقبل `reference_type` MANUAL وحده (400 لغيره) عبر `StockMovement.MANUAL_REFERENCE_TYPES`. التالي: قراءة فرقها + مراجعتان، ثم M1B-3.
- 2026-11-18: أُطلق بالتوازي قارئ M1B-3 (Hydrogen `--read-only`، موجز `briefs/M1B-3-reader.txt` ← `runs/m1b3-reader/result.json` finalMessage): 11 سؤالاً عن حساب الفروقات الافتراضي وسجلّ التدقيق ومسارات كتابة `standard_cost` و`_post_provisional_reconciliation_diff` وإعادة تقييم landed cost. (تحذير `readOnlyViolation` قد يظهر كاذباً لأن منفّذ SEC يعدّل الشجرة في الوقت نفسه.)
- 2026-11-22: SYNC-NOLAYER: المراجعتان عادتا (الكود سليم). مقبول لجولة fix1 (Terra): docstring الخدمة والأمر، zero_qoh في فحص save، تنسيق سطر التحذير — موجز `briefs/SYNC-NOLAYER-fix1.txt`. مرفوض: `before > 0` (لا منتج سالب في الإنتاج)، N4، N5. ينتظر انتهاء البوّابة الكاملة bj8ygedga قبل الإطلاق (تصادم قواعد الاختبار). بعدها: قراءة الفرق، مراجعتان نهائيتان، بوّابات، commit/push، CI، نشر، لقطة قبل، معاينة، `--apply`، لقطة بعد (`scratchpad/prod/sync_snapshot.py`).
- 2026-11-22: البوّابة الكاملة على حالة SYNC-NOLAYER قبل fix1: 8142 passed و6 failed (الستّة البيئية المعروفة). أُطلق fix1 على Terra (`runs/SYNC-NOLAYER-fix1`). التالي: قراءة فرقه.
- 2026-11-22: SYNC-NOLAYER fix1 انتهى (Terra high) وقُرئ فرقه كاملاً، مطابق. الآن: مراجعتان Opus نهائيتان على الحالة النهائية ← `review/SYNC-NOLAYER-*-final.md`، ثم البوّابات والإيداع والنشر و`--apply`.

- 2026-11-22 SYNC-NOLAYER: المراجعتان النهائيتان: Spec نظيفة (nit مرفوض)؛ Standards: should-fix مقبول (الوصفان ينقصهما شرط before != 0)، والـnitان مرفوضان (نمط قائم). الآن: جولة تصليح 2 (Terra، وصفان فقط) ← runs/SYNC-NOLAYER-fix2. بعدها: قراءة الفرق، مراجعة نهائية، بوّابة كاملة، إيداع ونشر و--apply.
- 2026-11-22 SYNC-NOLAYER: fix2 مقروء ومطابق؛ المراجعتان النهائيتان CLEAN. الآن: البوّابة الكاملة تعمل، ثم إيداع ودفع وCI ونشر ثم لقطة before ومعاينة و--apply ولقطة after على الإنتاج.
- 2026-11-22 SYNC-NOLAYER: أُودِع `283a6f86` ورُفع (بوّابة: 8142 passed + 6 بيئية). الآن: CI ثم النشر ثم لقطة before ومعاينة و--apply ولقطة after.
