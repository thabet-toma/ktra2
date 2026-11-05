# ملف التسليم

يُحدَّث قبل أي توقّف (CLAUDE.md — Workflow، الخطوة 8). من يستلم يبدأ من هنا.
**وبطلب المالك (2026-10-22): يُحدَّث بعد كل تذكرة، وبعد كل جولة تصليح، وقبل أي ضغطٍ للسياق** — هو ذاكرة
المنسّق بعد الـcompact. الإكمال حتى آخر تذكرة بلا توقّف.

**آخر تحديث:** 2026-11-05 ~00:50 (قبل compact رابع بطلب المالك؛ **لا عامل حيّ ولا job حيّ**)

## ⏩ نقطة الاستئناف — ابدأ من هنا (2026-11-05 00:50)

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
   - النشر: `deploy-277.sh` من `deploy-276.sh` (`before-277`). و`0007` فيها `CreateModel`/`AddField`/`AlterField`/`AddConstraint`/`AddIndex`/`RunPython` (بيانات v2 فلسطين) — **لا** `RemoveField`/`DeleteModel`/`RunSQL`. والإرسال: `($s -replace "","") | ssh -i ~/.ssh/hostenger2/id_ed25519 root@187.124.164.58 'bash -s'`؛ والبناء على الخادم بأمرٍ مستقلٍّ ينتهي بـ`echo done`.
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
