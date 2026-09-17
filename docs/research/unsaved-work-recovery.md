# حمايةُ العمل غير المحفوظ — بحثٌ في مصادرَ أوّلية

> قضية [#101](https://github.com/thabet-toma/ktra2/issues/101) ضمن خريطة [#100](https://github.com/thabet-toma/ktra2/issues/100).
> **بحثٌ فقط** — لا تعديل على كود المنصّة. كلُّ اقتباسٍ دون خمسَ عشرةَ كلمة، بين علامتَي اقتباس وبنسبتِه إلى مصدره.
> المصادر: توثيقُ المنتِج نفسِه، وكودُه المفتوح، وMDN، ومواصفاتُ WHATWG.

---

## القسم صفر — أين نحن اليوم (تُحُقِّق منه في الكود، لا يُفترَض)

| الواقع | الملف والرمز |
|---|---|
| الحفظُ التلقائي **الوحيد** في المستودع كلّه | `frontend_v2/components/sales/SalesInvoiceEditor.tsx` — `useEffect` يؤجّل ٢٠٠٠ms ثمّ `db.invoice_drafts.put(...)` |
| المخزن | `frontend_v2/services/offline/db.ts` — `db.version(2)`: `invoice_drafts: 'draft_id, tenant_id, updated_at'` (Dexie فوق IndexedDB) |
| شرطُ الكتابة | `dirtyRef.current && invoiceStatus === "draft"` |
| شرطُ **الاستعادة** | `if (draftToEditId != null || draftId != null) return;` — أي للفاتورة الجديدة وحدَها |
| حارسُ المغادرة | `beforeunload` في نفس الملفّ (`e.preventDefault(); e.returnValue = ""`)، وثانٍ في `frontend_v2/components/import-flow/ImportDocumentScreen.tsx` بلا حفظٍ تلقائيّ خلفَه |

**العطبُ الأوّل — كتابةٌ لا يقرأها أحد.** مفتاحُ المسودّة `tenantScopedOfflineKey(tenant, draftId ?? "new")`. فحين يحرّر المستخدم **مسودّةً محفوظةً** (`draftId != null`) يظلّ الحفظُ التلقائيّ يكتب صفّاً في IndexedDB، بينما حارسُ الاستعادة يخرج مبكّراً فلا يقرؤه أحدٌ أبداً. صفوفٌ ميّتة تتراكم، وصفرُ فائدةٍ في الحالة الأشيع.

**العطبُ الثاني — والأخطرُ على أيّ تصميمٍ قادم — الرقمُ يُحرَق عند إنشاء المسودّة لا عند الترحيل.**
`sales/serializers.py` (`SalesInvoiceSerializer.create`) يستدعي `next_invoice_number(...)` وقتَ الإنشاء، وهو يمرّ إلى `accounting.services.next_document_number` ثمّ `tenants.models.TenantBook.get_next_number` — وهذه تأخذ `select_for_update()` وتزيد `last_used_number` **ولا تتراجع**. فكلُّ مسودّةٍ خادمية = رقمٌ مستهلَك من السلسلة إلى الأبد. (وقد كُتب في نفس الملفّ حلقةُ تصادمٍ تتقدّم بالعدّاد خمسين مرّة عند `IntegrityError` — أي إنّ الفجوات معروفةٌ ومُحتمَلة أصلاً.)

يوجد بالفعل `preview_next_invoice_number` في `sales/services/numbering.py` يقرأ `last_used_number + 1` **بلا زيادة** — وهو المِفصلُ الذي سيلزمنا لو ذهبنا إلى مسودّةٍ خادمية.

**قيدٌ ثالث:** `create` يرفض بلا عميل («لم يتم تحديد عميل ولا يوجد عميل افتراضي») وبلا بنود («يجب إضافة بند واحد على الأقل»). فالمستندُ نصفُ المكتوب — وهو بالضبط ما نريد إنقاذه — **لا يُمكن أن يُحفَظ خادمياً اليوم أصلاً**. والمسارُ الآخر الوحيد للمسودّات (`/api/agent/invoices/draft/` في `sales/agent_api.py`) يمرّ عبر نفس المُسلسِل، فيرث القيدَ وحرقَ الرقم معاً.

---

## القسم الأوّل — ما تسمح به منصّةُ الويب فعلاً

هذا نصفُ الجواب، وهو النصفُ الذي لا يُتفاوَض عليه: أيُّ تصميمٍ يخالفه يفشل صامتاً.

### ١ — `beforeunload`: حارسٌ، لا آليةَ حفظ

MDN تعدّد ما **لا** يستطيعه هذا الحدث ([MDN — beforeunload](https://developer.mozilla.org/en-US/docs/Web/API/Window/beforeunload_event)):

- النصُّ المخصَّص مات: المتصفّحات «only show a generic browser-specified string in the displayed dialog». فرسالتُنا العربية لن تُعرَض أبداً — وكودُنا يمرّر `""` أصلاً، وهذا هو الصواب.
- يلزمه تفاعلٌ سابق: «require sticky activation for the dialog to be displayed» — فإن لم يلمس المستخدمُ الصفحةَ فلا حوارَ ولا تحذير.
- لا يُعوَّل عليه: «It is not reliably fired, especially on mobile platforms». والمثالُ الذي تسوقه MDN هو حالتُنا حرفياً — مستخدمٌ على الهاتف ينتقل إلى تطبيقٍ آخر ثمّ يُغلق المتصفّح من مدير التطبيقات: «the `beforeunload` event is not fired at all».
- وله ثمنُ أداء: «Firefox will not place pages in the bfcache if they have `beforeunload` listeners».
- وتوصيةُ MDN صريحة: «It is recommended to use the `visibilitychange` event as a more reliable signal».

**الخلاصة:** `beforeunload` يصلح سؤالاً للمستخدم «أمتأكّد؟» وحسب. **لا يصلح مكاناً للحفظ.**

### ٢ — `visibilitychange` و`pagehide`: الحدثان الموصى بهما

- `visibilitychange` إلى `hidden` هو الحدُّ الأخير المضمون: «the last event that's reliably observable by the page»، و«developers should treat it as the likely end of the user's session» ([MDN — visibilitychange](https://developer.mozilla.org/en-US/docs/Web/API/Document/visibilitychange_event)).
- `pagehide` هو البديلُ الثاني لا الأوّل: «The best event to use to signal the end of a user's session»، و«In browsers that don't support `visibilitychange` the `pagehide` event is the next-best alternative» ([MDN — pagehide](https://developer.mozilla.org/en-US/docs/Web/API/Window/pagehide_event)).
- وميزتُه على `unload`: «this event is compatible with the back/forward cache (bfcache)» (نفس المصدر) — أي لا يعاقِب الأداء.
- **لكنّه هو أيضاً غيرُ مضمون:** «this event is not reliably fired by browsers, especially on mobile» (نفس المصدر).
- و`unload` نفسُه محكومٌ عليه: «Developers should avoid using this event» ([MDN — unload](https://developer.mozilla.org/en-US/docs/Web/API/Window/unload_event)).

**الفرقُ على المحمول:** انتقالُ المستخدم إلى تطبيقٍ آخر يُطلق `visibilitychange` → `hidden` فوراً؛ أمّا قتلُ المتصفّح لاحقاً من مدير التطبيقات فقد لا يُطلق شيئاً على الإطلاق — لا `pagehide` ولا `beforeunload`. ولذلك القاعدة: **احفظ عند الإخفاء، لا عند الإغلاق.**

### ٣ — السؤال الذي يتوقّف عليه تصميمُنا: أتكتمل كتابةُ IndexedDB والصفحةُ تُغلَق؟

**الجواب: لا. ولا ضمانَ أصلاً — والمصدرُ قاطعٌ، فلا نبني عليه.**

MDN، في قسم «Warning about browser shutdown» من صفحة استعمال IndexedDB ([MDN — Using IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API/Using_IndexedDB)):

> «you should never tie database transactions to unload events»

> «any transactions created in the unload event handler will never complete»

> «there is no way to guarantee that IndexedDB transactions will complete»

والجملةُ الثالثة هي الأهمّ: النفيُ ليس عن الإغلاق القسريّ وحدَه — MDN تنفي الضمانَ «even with normal browser shutdown».

ويؤكّده توثيقُ Chrome لدورة حياة الصفحة: في الحالتين المجمَّدة والمنتهية «asynchronous and callback-based APIs cannot be reliably used»، وحالةُ الإسقاط (`discarded`) قد تُدخَل من `hidden` أو من `frozen` بلا إطلاقِ أيّ حدث — «(no events fired)» ([Chrome for Developers — Page Lifecycle API](https://developer.chrome.com/docs/web-platform/page-lifecycle-api)).

**ما الذي يُقلّل الضرر (ولا يُلغيه):**

1. **الكتابةُ مبكّراً** — عند `visibilitychange` → `hidden`، لا عند `beforeunload`. عندها لا تزال الصفحةُ حيّةً وطابورُ المهامّ يعمل.
2. **`IDBTransaction.commit()`** — يبدأ الإنهاءَ فوراً: «start the commit process without waiting for events from outstanding requests» ([MDN — IDBTransaction.commit](https://developer.mozilla.org/en-US/docs/Web/API/IDBTransaction/commit))، وتوثيقُ Chrome أعلاه يرشّحه بالاسم لهذا الغرض بالذات. **Dexie لا تكشفه افتراضياً** — نقطةُ انتباهٍ لنا.
3. **`durability: "strict"`** في `IDBDatabase.transaction()` — «successfully written to a persistent storage medium»، مقابل `"relaxed"` الذي يكتفي بتسليمها «to the operating system, without subsequent verification» ([MDN — IDBDatabase.transaction](https://developer.mozilla.org/en-US/docs/Web/API/IDBDatabase/transaction)). وهذا يحمي من انقطاع الكهرباء لا من إغلاق التبويب.

**النتيجةُ العملية علينا:** حفظُنا الحالي مؤجَّلٌ ثانيتين. من يكتب سطراً ثمّ يُغلق التبويبَ فوراً يخسره — والمهلةُ نفسُها هي المخاطرة، لا IndexedDB. والعلاجُ ليس «اكتب عند الإغلاق» (وهو مستحيل)، بل **قصِّر المهلة، واكتب أيضاً عند `hidden`، واقبل أنّ آخر ثانيةٍ قد تضيع**.

### ٤ — `navigator.sendBeacon`: الإرسالُ الوحيد الذي يصمد للإغلاق

MDN تصف المشكلةَ التي وُلد لحلّها: عند المغادرة «the browser may choose not to send asynchronous XMLHttpRequest requests»؛ أمّا `sendBeacon` فـ«transmitted asynchronously when the user agent has an opportunity to do so» ([MDN — sendBeacon](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/sendBeacon)).

الحدود، بنصّها:

- **الحجم:** «The total size of queued data is limited to 64 KiB (65,536 bytes)».
- **الطريقة:** «The data is sent as an HTTP POST request» — لا PUT ولا PATCH.
- **والقيمةُ المُعادة تكذب على من يُسيء فهمَها:** «Returns `true` if the user agent successfully queued the `data` for transfer» — أي **أُدرِج في الطابور**، لا وصَل. لا استجابةَ خادمٍ تُقرَأ، ولا وسيلةَ لمعرفة الفشل، ولا إعادةَ محاولة.
- **بديلٌ أوسع:** `fetch(..., { keepalive: true })` — «not abort the associated request if the page that initiated it is unloaded»، ويسمح بطرقٍ غير POST وبقراءة الاستجابة، غير أنّ «The body size for `keepalive` requests is limited to 64 kibibytes» ([MDN — RequestInit](https://developer.mozilla.org/en-US/docs/Web/API/RequestInit)).

**علينا:** حمولةُ `buildPayload()` لفاتورةٍ بعشرات البنود أصغرُ من ٦٤ كيلوبايت بمراحل، فالحدُّ ليس عائقاً. العائقُ أنّ الإرسالَ **بلا إيصالِ استلام**: لا نعرف أوصلت المسودّةُ أم لا، فلا يجوز أن نمسح النسخةَ المحلّية اتّكالاً عليه.

### ٥ — بقاءُ البيانات: `navigator.storage.persist()`

معيارُ WHATWG للتخزين يقسم السِّلال قسمين: «A local storage bucket has a mode, which is `"best-effort"` or `"persistent"`»، والمتصفّحُ تحت ضغط المساحة «should clear network state and local storage buckets whose mode is `"best-effort"`». والحمايةُ التي يمنحها الوضعُ المستمرّ: «cannot clear storage marked as persistent without involvement from the origin or user» ([WHATWG Storage Standard](https://storage.spec.whatwg.org/)).

و`persist()` يُعيد وعداً «resolves to `true` if permission is granted and bucket mode is persistent» ([MDN — StorageManager.persist](https://developer.mozilla.org/en-US/docs/Web/API/StorageManager/persist))؛ والفرقُ العملي بنصّ MDN: مستمرّ — «Storage will not be cleared except by explicit user action»؛ وافتراضيّ — «Storage may be cleared by the UA under storage pressure».

ومتى يُجلى المحتوى ([MDN — Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)):

- ضغطُ المساحة بسياسة الأقلّ استعمالاً: «The data from the least recently used origin is deleted».
- والأخطرُ علينا — Safari: بلا تفاعلٍ من المستخدم سبعةَ أيّام «its data created from script will be deleted».
- ولا جلاءَ جزئيّ: «all of its data, not parts of it, is deleted at the same time».

**علينا:** لا نطلب `persist()` اليوم. فمسودّاتُنا المحلّية في وضعِ «أفضل جهد»، وقابلةٌ للجلاء الكامل — ومستخدمُ Safari الذي لا يفتح النظام أسبوعاً يفقدها بلا إشعار. وحتّى مع `persist()` يبقى المسحُ اليدويّ وتنظيفُ الجهاز واردَين. **التخزينُ المحلّي ليس مستودعاً — هو شبكةُ أمانٍ لدقائقَ أو ساعات.**

---

## القسم الثاني — ماذا تفعل التطبيقاتُ المهنية

### ١ — Odoo: **الحفظُ متعجّل، والترقيمُ متمهّل**

أقربُها إلينا — مستنداتٌ محاسبيةٌ بحالة `draft`. والدرسُ منه واحدٌ حاسم: **Odoo يفصل بين شيئين نخلطهما نحن.**

**(أ) المغادرةُ داخل التطبيق = حفظٌ صامت، لا نافذةَ تحذير.** في `addons/web/static/src/views/form/form_controller.js` تحفظ `beforeLeave` إن كان السجلُّ متّسخاً بدل أن تسأل. فهي تقرأ `await this.model.root.isDirty()`، فإن كان متّسخاً استدعت `this.save({ reload: false })` — **حفظٌ، لا سؤال**.

فالمستندُ نصفُ المكتوب **يصير صفّاً في قاعدة البيانات**، ولا يُفقَد. والتجاهلُ لا يقع إلّا بضغطة «Discard» صريحة.

**(ب) إغلاقُ التبويب = `sendBeacon`، والحوارُ آخرُ الحيل لا أوّلها.** وفي نفس الملفّ: `beforeUnload(ev)` تنتظر `urgentSave()`؛ **وإن فشلت وحدَها** تستدعي `ev.preventDefault()` وتضع `ev.returnValue`.

أي: **حاوِلِ الحفظَ أوّلاً، ولا تُزعج المستخدمَ إلّا إن فشلت.** وتعليقُ Odoo في `addons/web/static/src/model/relational_model/record.js` يشرح اختيارَ الوسيلة بنصّه:

> «We instead use sendBeacon, which isn't cancellable»

> «it has limited payload (typically < 64k)»

> «if it doesn't work, we will prevent the page from unloading»

**(ج) وأثمنُ سطرٍ لنا في المستودع كلّه** — في نفس الملفّ، داخل فرع العمل بلا اتّصال:

> «Unfortunately, we can't save on IndexedDB before unload»

هذا اعترافٌ من كودِ منتَجٍ مهنيٍّ بعينِ ما قرّرته مواصفةُ المنصّة في القسم ١‑٣. وحين يتعذّر الحفظ لا يخترع Odoo ضماناً وهمياً — بل **يُخبر المستخدم** بلافتةٍ لاصقة: «Your recent changes cannot be saved automatically while you are offline».

**(د) ولا شيءَ من هذا يحرق رقماً.** توثيقُ Odoo:

> «On confirmation, Odoo assigns each invoice a unique number from a defined sequence»
> ([Odoo 17 — Customer invoices](https://www.odoo.com/documentation/17.0/applications/finance/accounting/customer_invoices.html))

> «When confirming an invoice, Odoo generates a unique invoice reference number»
> ([Odoo 18 — Invoice sequence](https://www.odoo.com/documentation/18.0/applications/finance/accounting/customer_invoices/sequence.html))

والآليةُ في `addons/account/models/account_move.py`: المسودّةُ تحمل `name = '/'` حتّى الترحيل، وتُعرَض «Draft Invoice» بمعرّفها الداخليّ لا برقمٍ من السلسلة، وتوثيقُ `_post()` يقول: «Posting the documents will give it a number».

واستثناءٌ واحدٌ موثَّق: أوّلُ مسودّةٍ في فترةِ تسلسلٍ جديدة **تنال اسماً وهي مسودّة** — وهو ما يسمح بتحرير صيغة التسلسل عندها. وOdoo يرصد الفجواتِ صراحةً: تظهر رسالةُ «Gaps in the sequence» في لوحة المحاسبة.

**(هـ) ولا يحفظ Odoo المسودّاتِ في تخزين المتصفّح إطلاقاً.** بحثٌ في `addons/web/static/src` يُظهر `localStorage` مستعمَلاً للتفضيلات وذاكرةِ القوائم فقط — لا لبيانات سجلٍّ غير محفوظ. جوابُ Odoo هو **رحلةٌ إلى الخادم**، لا مخزنٌ محلّيّ.

> **الخلاصة، وهي جوهرُ التوصية:** يستطيع Odoo أن يحفظ بجرأةٍ لأنّ الترقيمَ عنده **كسول**. ونحن نحفظ بجُبنٍ لأنّ ترقيمَنا **متعجّل**. فالمشكلةُ ليست في الحفظ، بل في موضع استدعاء العدّاد.

### ٢ — Google Docs: حفظٌ مستمرّ بلا زرّ حفظ

> «When you're online, Google automatically saves your changes as you type»

> «You don't need a save button»
> ([Google — autosave](https://support.google.com/docs/answer/49114))

وبلا اتّصال «changes will save to your device as you enter text» ثمّ «will save to Drive once reconnected» (نفس المصدر). وشبكةُ الأمان **تاريخُ النسخ** لا زرُّ الحفظ ([Google — نسخُ الملفّ](https://support.google.com/docs/answer/190843)).

**تنبيهٌ منهجيّ:** Google **لا توثّق** لماذا يجوز هذا هناك (لا OT/CRDT، ولا «لا ترقيم»، ولا «لا أثرَ ماليّاً»). هذا استنتاجُنا نحن — صحيحٌ لكن لا يُنسَب إلى Google. والفرقُ الجوهريّ بيّنٌ بذاته: مستندُ Google **لا رقمَ له ولا قيدَ ينشأ عنه**، فحفظُ نصفِ جملةٍ لا يكلّف شيئاً؛ أمّا فاتورتُنا فحفظُها يستهلك رقماً ويُنشئ صفّاً يُسأل عنه المدقّق. لذلك **نموذجُ Google غيرُ قابلٍ للنقل إلينا كما هو** — ما يُنقَل منه هو *العقد* («لا تسأل، احفظ») لا الآلية.

### ٣ — Salesforce: حوارُ تحذيرٍ يبنيه المطوّر، ولا استرجاعَ موثَّقاً

المكوّن `lightning:unsavedChanges` (Aura) يعرض حواراً عند فقدِ محتوىً غير محفوظ — «a dialog appears prompting them to save or discard it» ([Salesforce — Lightning Component Reference](https://developer.salesforce.com/docs/platform/lightning-component-reference/guide/aura-unsaved-changes.html)).

**تحفّظان يجب ذكرُهما:**

1. هذا الاقتباس مأخوذٌ من مقتطف الفهرس **لتلك الصفحة بعينها**، لأنّ `developer.salesforce.com` يردّ 403 على كلّ جلبٍ آليّ. عالي الثقة، **غيرُ متحقَّقٍ منه مباشرةً** — من أراد اليقين فليفتح الرابط بنفسه.
2. **لم نجد أيَّ توثيقٍ أوّليّ لحفظٍ تلقائيّ أو استرجاعِ مسودّةٍ في Salesforce.** نموذجُها حفظٌ صريح، وحمايتُها الوحيدة الموثَّقة هي هذا الحوار — **ويكتبه المطوّر، لا يأتي جاهزاً**. ولم نتحقّق من وجود نظيرٍ بصيغة LWC.

### ٤ — Dynamics 365: حفظٌ تلقائيّ افتراضيّ — **بعد أوّل حفظٍ يدويّ**

كلُّ ما يلي من [Microsoft Learn — Manage auto-save](https://learn.microsoft.com/en-us/power-apps/maker/model-driven-apps/manage-auto-save):

- مفعَّلٌ افتراضياً: «By default all main forms for Updated tables and classic tables have AutoSave enabled».
- والمهلةُ ثلاثون ثانية، **ولا تبدأ إلّا بعد وجود الصفّ**: «After a row is created (initially saved)»، ثمّ «any changes made to a form are automatically saved 30 seconds after the change».
- **والحفظُ الأوّل يدويّ:** «the save button only appears for the initial save of the row».
- وعند المغادرة: «saved whenever you navigate away from a row or close a separate window».
- والإطفاءُ **للبيئة كلّها لا لجدول**: «There's no setting to disable AutoSave for individual tables or forms».
- وله ثمنٌ موثَّق: الإضافاتُ وسيرُ العمل ونصوصُ النموذج تعمل مع **كلّ** حفظٍ تلقائيّ، والتدقيقُ يسجّل كلَّ حفظٍ تحديثاً مستقلّاً.

**درسٌ لنا مباشر:** Microsoft تفصل بالضبط الفصلَ الذي نحتاجه — **إنشاءُ الصفّ قرارٌ بشريّ صريح، وما بعده تلقائيّ**. هذا يحلّ اليتامى والترقيمَ معاً بلا ذكاء. ودرسٌ ثانٍ: الحفظُ المتكرّر يضاعف سجلَّ التدقيق — وعندنا `core.activity.log_activity`، فليُنتبَه.

### ٥ — Notion و Linear: المسودّةُ المحلّية والتزامن

- **Linear** ([Linear — Get the app](https://linear.app/docs/get-the-app)): «the app will store changes locally»، ثمّ يُعيد المحاولة عند عودة الاتّصال. وينبّه Linear بنفسه: «Offline mode is designed as a failsafe and not a full-fledged feature» — ولا يقارن الطوابعَ الزمنية، فالتحريرُ الطويل بلا اتّصال قد يدهس أحدثَ منه.
  *(بنيةُ محرّك المزامنة المحلّيّ عند Linear موصوفةٌ في كتاباتٍ خارجية لا في توثيقه — فلا تُنسَب إليه.)*
- **Notion** ([Notion — Use pages offline](https://www.notion.com/help/use-pages-offline)): «While offline, you can: Create new pages»، والمزامنةُ «automatically updated in the background»، مع توصيةٍ صريحة بالاتّصال كلّما أمكن. وشبكةُ الأمان تاريخُ النسخ ([Notion — Version history](https://www.notion.com/help/duplicate-delete-and-restore-content)): «recorded every 10 minutes as you actively edit it»، وبعد دقيقتين من آخر تحريرٍ تُسجَّل نسخةٌ أخرى.

**الدرس:** حتّى الأدواتُ «المحلّية أوّلاً» تعامل التخزينَ المحلّي **شبكةَ أمانٍ مؤقّتة** لا مستودعاً — الحقيقةُ عند الخادم، والتاريخُ المؤرشَف هو ما يُرجَع إليه فعلاً.

### جدولٌ جامع

| المنتَج | أيُنشئ صفّاً عند المغادرة؟ | مكانُ المسودّة | أيحرق رقماً؟ |
|---|---|---|---|
| **Odoo** | نعم — حفظٌ صامت | الخادم (`sendBeacon` عند الإغلاق) | **لا** — `/` حتّى الترحيل |
| **Google Docs** | نعم دائماً | الخادم (+ الجهاز بلا اتّصال) | لا رقمَ أصلاً |
| **Dynamics 365** | نعم — **بعد** الحفظ الأوّل اليدويّ | الخادم كلَّ ٣٠ث | خارجَ نطاق البحث |
| **Salesforce** | لا | لا مسودّة موثَّقة — حوارُ تحذيرٍ فقط | — |
| **Notion / Linear** | نعم | محلّيّ ثمّ يُرفَع | لا رقمَ أصلاً |
| **نحن اليوم** | لا | IndexedDB، شاشةٌ واحدة | **نعم** — لحظةَ الحفظ الأوّل |
---

## القسم الثالث — «ما يصلح لنا»

المقارنةُ ليست بين ثلاث تقنيات، بل بين ثلاثة عقودٍ مع المستخدم. وهذه مقاييسُها الثلاثة كما طلبتها القضية: **الترقيم**، و**الصفوف اليتيمة**، و**التزامن بين الأجهزة**.

### (أ) استرجاعٌ محلّيّ فقط — IndexedDB + لافتةُ استعادة

*وهو ما نفعله اليوم في شاشةٍ واحدة، وهو معطوب.*

| المقياس | الكلفة |
|---|---|
| **الترقيم** | **صفر.** لا رقمَ يُطلَب ولا عدّادَ يتحرّك حتى يضغط المستخدم «حفظ». هذه أعظمُ فضائل هذا النموذج ولا يُستهان بها. |
| **الصفوف اليتيمة** | صفرٌ في قاعدة البيانات. لكن يتامى **محلّيّون**: صفوفُ `invoice_drafts` تتراكم بلا سياسة تنظيف — وعندنا اليوم مسارُ كتابةٍ أعمى يكتب لمسودّاتٍ محفوظةٍ لا يقرؤها أحد. |
| **التزامن بين الأجهزة** | **صفر، وهو عيبٌ بنيويّ لا يُرقَّع.** المسودّة حبيسةُ هذا الجهاز وهذا المتصفّح وهذا الملفّ الشخصيّ. من كتب على الحاسوب ثم فتح الهاتف لا يرى شيئاً. وتُمحى مع بيانات الموقع، ومع تنظيف Safari بعد سبعة أيّامٍ بلا تفاعل (القسم ١‑٥). |

**الحكم:** رخيصٌ، وآمنٌ محاسبياً تماماً، ويشتري ٩٠٪ من قيمة «لا يضيع ما كتبت» بـ١٠٪ من الكلفة — **لكنّه يَعِد وعداً لا يفي به على جهازٍ ثانٍ**. صالحٌ أساساً، لا حلّاً كاملاً.

### (ب) مسودّةٌ خادمية حقيقية تُكتب تلقائياً

*وهو ما يفعله Odoo وDynamics 365 — أي إنّه النموذجُ المهنيّ السائد فعلاً. لكنّ كلَّاً منهما اشترى أمانَه بثمنٍ لا نملكه بعد: Odoo بترقيمٍ كسول (`/` حتّى الترحيل)، وMicrosoft بإبقاء **الحفظِ الأوّل قراراً بشرياً**.*

| المقياس | الكلفة |
|---|---|
| **الترقيم** | **الكلفةُ الأكبر، وهي عندنا اليوم قاتلة.** `next_invoice_number` يُستدعى داخل `create` ويزيد `TenantBook.last_used_number` بلا رجعة. فمستخدمٌ يفتح فاتورةً ويكتب حرفاً ويغادر = رقمٌ محروق. عشرُ مراتٍ في اليوم = فجواتٌ في دفترٍ محاسبيّ يُسأل عنها المدقّق. **لا يجوز اعتماد هذا النموذج قبل نقل استدعاء الترقيم من `create` إلى لحظة الترحيل** — وهو تعديلٌ يمسّ المُسلسِل وكلَّ مستدعيه (`sales/services/orders.py`، `sales/agent_api.py`، ونظائرَه في `logistics`). |
| **الصفوف اليتيمة** | **حقيقيةٌ وثقيلة.** كلُّ فتحِ شاشةٍ يُنتج صفّاً في `sales_invoices` (وأسطراً في `sales_invoice_lines`). تلوّثُ قوائمَ المسودّات، وتقاريرَ «الفواتير غير المرحّلة»، وعدّاداتِ حدود الخطط (`core/plans.py` + `TenantLimit`). يلزمها **سياسةُ عمرٍ ومكنسةٌ دورية** — وهي شيءٌ لا نملكه اليوم. |
| **التزامن بين الأجهزة** | **مجّاناً وكاملاً.** هذه فضيلتُه الوحيدة الكبرى: المسودّة تتبع المستخدم، ويراها زميلُه، وتنجو من مسح المتصفّح ومن موت الجهاز. |
| **عائقٌ إضافيّ** | `create` يرفض بلا عميلٍ وبلا بند. فالمستندُ نصفُ المكتوب — الحالةُ المقصودة بالذات — يحتاج إمّا مساراً خادمياً موازياً بلا تحقّق، أو تخفيفَ التحقّق في حالة `draft`. |

**الحكم:** هو الوجهةُ الصحيحة على المدى الطويل، لكنّه **مسدودٌ اليوم بحاجزَي الترقيم والتحقّق**، وكلاهما تعديلٌ خادميّ حقيقيّ لا تحسينُ واجهة.

### (ج) المزيج — محلّيٌّ فوريّ، ورفعٌ للخادم عند المغادرة/الخمول

| المقياس | الكلفة |
|---|---|
| **الترقيم** | **صفر — إن ورفعنا إلى سجلٍّ مستقلٍّ لا إلى `SalesInvoice`.** أي جدولُ «مسودّاتٍ» عامّ (`tenant` + `user` + `doc_type` + `payload` JSON + `updated_at`) لا يمسّ `TenantBook` أبداً. الرقمُ يُطلَب مرّةً واحدة، عند «حفظ» الحقيقيّ. أمّا لو رفعنا إلى المستند نفسه فنحن في النموذج (ب) بكلفته كاملة. |
| **الصفوف اليتيمة** | متوسّطة **ومعزولة**: صفوفٌ يتيمة في جدول المسودّات وحده — لا في `sales_invoices`، فلا تلوّث قائمةً ولا تقريراً ولا عدّاداً. وتنظيفُها سطرٌ واحد: احذف ما مضى عليه ثلاثون يوماً، واحذف صفّ المسودّة لحظةَ الحفظ الحقيقيّ (وهو ما نفعله محلّياً أصلاً في `clearLocalDraft`). |
| **التزامن بين الأجهزة** | **يعمل** — بتأخيرٍ لا بفوريّة. من كتب على الحاسوب وأخفى التبويب يجد عملَه على الهاتف. |
| **الثمنُ الحقيقيّ** | **التعقيد وتضاربُ النسختين.** محلّيٌّ وخادميٌّ قد يختلفان (كتبتَ على جهازين). ويلزمه حسمٌ صريح: `updated_at` الأحدث يفوز، ولا دمجَ حقلٍ بحقل — ولا نُظهر لافتتَي استعادةٍ متنافستين. |

**والرفعُ عند المغادرة تحديداً محدود بالمنصّة:** `sendBeacon` بلا إيصالِ استلام (القسم ١‑٤)، فلا يجوز أن نمسح النسخةَ المحلّية اتّكالاً عليه. والصواب هو **الرفع الدوريّ عند الخمول** (كلَّ ٣٠ ثانية مثلاً، أو عند `visibilitychange` → `hidden`)، ويبقى `sendBeacon` محاولةً أخيرةً لا أكثر.

---

## التوصية

**(ج) المزيج، منفَّذاً على مرحلتين، ومحلُّ الرفعِ سجلٌّ مستقلٌّ لا المستند.**

1. **المرحلة الأولى — أصلِح المحلّيّ وعمّمه.** هي وحدها تشتري معظمَ القيمة، وبلا مساسٍ بالمحاسبة:
   - أصلِح العيوب الثلاثة المرصودة في #100 (الاستعادةُ للمسودّة المحفوظة أيضاً؛ مفتاحٌ فريد لكلّ تبويب لا `"new"` واحدة؛ استعادةُ الرأس ولو بلا بنود).
   - أضِف كتابةً عند `visibilitychange` → `hidden` (لا `beforeunload`)، وقصِّر التأجيل من ٢٠٠٠ms إلى ~٥٠٠ms.
   - اسحب الآليةَ إلى خطّافٍ واحد مشترَك (`useDocumentDraft`) بدل نسخِها في كلّ شاشة، ثمّ طبّقه على العشر شاشات — بدءاً بفاتورة الشراء التي لا تحفظ اليوم شيئاً.
   - نظّف المسودّاتِ عند تسجيل الخروج وعند مهلة الخمول (بياناتُ عملاءٍ وأسعارٌ على جهازٍ مشترَك).
   - **لا تطلب `persist()`** بلا حاجةٍ مثبتة، ولا تَعِد المستخدمَ ببقاءٍ لا تملكه.
2. **المرحلة الثانية — أضِف الرفع.** جدولُ مسودّاتٍ عامّ في `core`، يُرفَع إليه عند الخمول وعند `hidden`، بسياسة «الأحدثُ يفوز» وعمرٍ ثلاثين يوماً. **لا يلمس `TenantBook` ولا `sales_invoices`.**

**وما لا نفعله الآن:** النموذج (ب) — لا لأنّه خاطئ، بل لأنّ بابَه مقفلٌ عندنا. فحرقُ الرقم عند إنشاء المسودّة قيدٌ خادميّ قائم، وتحريكُه — نقلُ استدعاء `next_invoice_number` من `create` إلى لحظة الترحيل، وهو حرفياً ما يفعله Odoo بـ`name = '/'` — **قضيّةٌ مستقلّةٌ تستحقّ تذكرتَها الخاصة**، ولا يجوز أن تكون شرطاً مسبقاً لإنقاذِ عملِ المستخدم اليوم. ومتى فُتح ذلك الباب صار الانتقالُ من (ج) إلى (ب) خطوةً قصيرة، لأنّ جدولَ المسودّات يكون قد حمل الحمولةَ ذاتها أصلاً.

**وأمرٌ يُستعار من Odoo فوراً وبلا كلفة:** ترتيبُ `beforeUnload` عنده — **حاوِلِ الحفظَ أوّلاً، ولا تعترض المغادرةَ إلّا إن فشل**. حارسُنا اليوم يعترض دائماً ولا يحاول شيئاً. وهذا انقلابٌ في العقد: من «أنتَ على وشك أن تفقد عملك» إلى «عملُك محفوظ».

**وأمرٌ يُستعار من Odoo أيضاً:** حين يتعذّر الحفظ، **قُل ذلك صراحةً**. لافتةُ Odoo اللاصقة تطلب من المستخدم أن يضغط الحفظَ بنفسه. الصمتُ عن فشلٍ نعرفه أسوأُ من التحذير.

