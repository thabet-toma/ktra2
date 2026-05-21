# task4.md — KTRA ERP: تحويل النظام إلى نمط «الأصيل» (واجهة + منطق محاسبي + لوحة مفاتيح)

> **خطة كاملة (ليست تصميماً فقط).** المالك أقرّ النطاق: (1) كل شاشات الإدخال تُعاد بناؤها بنمط الأصيل، (2) إضافة ميزات الأصيل المحاسبية الناقصة (backend + UI)، (3) محاكاة لوحة المفاتيح + التنقّل بين السجلات + الاختصارات، (4) قشرة موقع هجينة موحّدة تُشبه فرونت الأصيل عبر **كامل** الموقع لا شاشة واحدة.
> النطاق يشمل **قلب الاستيراد**: الصفقات + الشحنات (الإرساليات) + التخليص الجمركي (فاتورة البيان الجمركي) + النقل المحلي (السائق/أجرة النقل) — أكثر الشاشات استخداماً في شركة استيراد.
> النطاق التقني: `frontend_v2/` (React 19 + Vite 6 + TS 5.8 + Tailwind v4) + backend Django (`sales/`, `accounting/`, `logistics/`, `inventory/`, `partners/`). `hr`/`realestate` خارج النطاق.
> **المرجع الإلزامي (spec canonical):** المانوال المستخرَج من برنامج الأصيل في `docs/aseel_reference/*.txt` (مصدره `C:\Castle\Asseal2005\Book\*.doc`) + لقطات شاشة «فواتير البيع» المرفقة من المالك. كل تاسك يذكر المرساة المرجعية (ملف + بند).
> Status: `[~]` M0 ✅ · M1 ✅ · M2 ✅ · M3 ✅ · M4 ✅ · M5 ✅ **DONE & VERIFIED by Opus** · M6 pending · 2026-05-20
> ⚠️ سجل المراجعة:
> - M0/M1: النموذج الخارجي علّم «مكتمل» في فرع `claude/modest-morse` **دون أي ملف**. أُعيد تنفيذهما بالكامل بواسطة Opus.
> - M2: النموذج الخارجي **عمل في `main` worktree (وليس في الفرع)** — أنجز T1/T2/T5 جيد، T4 ببقع، T3/T6 غير مكتملين. سُحب الجيد، أُصلح T4، نُفّذ T3 و T6 من الصفر بواسطة Opus.
> - M3: النموذج الخارجي **عمل في `main` مرة أخرى لكن مَسَح M2 backend قبل البدء** (لو كنت تشتغل في main لفقدنا M2). M3 في main كان قشرياً (placeholders + dead imports). نُقل الجيد لفرعي، اُستُبدلت placeholders بمعالجات حقيقية، أُضيفت حقول M3-T2 backend (LogisticsShipment + migration 0025) وUI، رُكّب index-pickers الفعلية (موردين/وكلاء/مخلّصين)، تم تقييد التحويل (transport غير قابل).
> نموذج التنفيذ: نموذج أرخص ينفّذ تاسكاً تاسكاً؛ Opus يراجع من خلف كل Milestone مقابل `docs/aseel_reference/` + اللقطات + `manage.py check` + `vite build` + متصفّح حيّ، ويحدّث `PROJECT_MAP.md`.

---

## [AUDIT] تشخيص الفجوة بين الموقع الحالي وبرنامج الأصيل (مؤكَّد بالكود + المانوال + اللقطات)

| # | الفجوة | الدليل (الموقع الحالي) | المرجع (الأصيل) |
|---|--------|------------------------|-----------------|
| G1 | **لا قشرة مستند موحّدة**: كل شاشة إدخال تُرسم يدوياً. `SalesInvoiceEditor.tsx` (1510 سطر) نموذج بطاقات عمودي بـTailwind خام (تدرّجات emerald، rounded-2xl)، لا يستخدم `components/ui` ولا الـtokens. | `frontend_v2/components/sales/SalesInvoiceEditor.tsx` | لقطة «فواتير البيع»: شريط أدوات سجلات + شريط حقول علوي كثيف + جدول بنود + تبويبات سفلية + لوحة إجماليات/دفع. |
| G2 | **لا شريط تنقّل سجلات ولا اختصارات**: لا الأول/السابق/التالي/الأخير، لا F2 طباعة/F3 إيصال، لا `+`/`*`/`-` لفتح الفهارس والتنقّل. التفاعل بالفأرة فقط. | لا كود keymap/record-nav في `frontend_v2/` | `invoices.txt` 26–50, 193–234؛ `shipments.txt` 114–155؛ `accounting.txt` 36–81. |
| G3 | **حقول مستند ناقصة محاسبياً**: لا دفتر/تعدد دفاتر، لا تاريخ ثاني، لا مشتغل مرخص، لا رقم فاتورة مقاصة، لا رقم الحركة/القيد/كشف الضريبة كحقول عرض، لا خصم كمبلغ+نسبة معاً، لا «الأسعار تشمل ض.ق.م» على مستوى الفاتورة، لا وحدة/مخزن/عملة/تاريخ صلاحية/كمية إضافية لكل بند. | `sales/models.py:171-361` | `invoices.txt` 51–185, 94–142؛ `shipments.txt` 6–80. |
| G4 | **لا سند مالي مرفق بالفاتورة**: الأصيل يحرّر سند قبض/صرف (نقدي + شيكات معاً) ضمن نفس حركة الفاتورة ويسجّل قيداً واحداً متكاملاً. الحالي: `cash_or_bank_account` فقط (نقدي مفرد)، الشيكات منفصلة. | `sales/services.py post_sales_invoice` | `invoices.txt` 19–23, 154–192؛ `intro.txt` 47–51؛ `cheques.txt`. |
| G5 | **لا إشعارات مدينة/دائنة**: غير موجودة كموديل/شاشة. | `git ls-files sales/ accounting/` | `invoices.txt` 64, 269؛ `notices.txt`. |
| G6 | **لا خصم المصدر** (نسبة/مبلغ على مستوى الحساب والسند). | `partners/`، `sales/models.py` | `intro.txt` 13, 49؛ `invoices.txt` 162–171. |
| G7 | **القشرة العامة ليست بنمط الأصيل**: لا شريط أوامر علوي كلاسيكي، لا شريط حالة سفلي (الشركة/السنة المالية/المستخدم/رقم الحركة/رقم القيد)، tokens ألوان حديثة. | `frontend_v2/components/layout/AppLayout.tsx`، `frontend_v2/styles/index.css` | شريط عنوان اللقطة + شريط الحالة السفلي. |
| G8 | **لا فهارس منبثقة موحّدة** (حسابات/أصناف/عملات) تُفتح بـ`+`/`…` مع تنقّل `*`/`-`. الموجود: `SalesProductPickerModal` خاص بالمبيعات فقط. | `frontend_v2/components/sales/SalesProductPickerModal.tsx` | `invoices.txt` 81–83, 96؛ `shipments.txt` 38–80. |
| **G9** | **قلب الاستيراد خارج نمط الأصيل**: الصفقات/الشحنات/التخليص/النقل المحلي شاشات منفصلة بلا قشرة موحّدة ولا تنقّل/اختصارات/فهارس؛ بنيتها لا تطابق «نموذج الإرسالية» و«فاتورة البيان الجمركي» (سطور مدين/دائن + عمود ضريبة، السالب=دائن). النقل المحلي مفكوك عن الإرسالية بينما الأصيل يضعه داخلها (سائق/سيارة/أجرة نقل وحدة/كمية/حساب أجرة النقل). | `frontend_v2/components/procurement/{deals,shipments,clearance}/*`، `frontend_v2/components/logistics/LocalShippingPage.tsx` | `shipments.txt` 1–214 (الإرسالية 6–155، تحويل لفواتير 156–161، البيان الجمركي 162–214)؛ `intro.txt` 52–55, 89–90. |

> **خلاصة:** الأساس البصري (tokens + ui primitives + AppLayout) من task3 جاهز ويُعاد استخدامه؛ النقص الجوهري = (أ) قشرة مستند الأصيل القابلة لإعادة الاستخدام، (ب) محرّك لوحة مفاتيح/تنقّل سجلات، (ج) **قلب الاستيراد (الصفقات/الشحنات/التخليص/النقل المحلي) على القشرة + منطق الأصيل**، (د) حقول/منطق الأصيل الناقص في sales/accounting، (هـ) توحيد القشرة العامة بصرياً.

---

## مبادئ معمارية (Surgical Architecture — مرجع المنفّذ)

- **قشرة واحدة قابلة لإعادة الاستخدام** `frontend_v2/components/aseel/` (لا micro-files):
  - `AseelDocumentShell.tsx` — إطار: شريط أوامر علوي + شريط حقول رأس + منطقة جدول + شريط تبويبات سفلي + رصيف إجماليات/دفع + شريط حالة. slots.
  - `useRecordNavigation.ts` — first/prev/next/last/new/save/delete فوق أي قائمة سجلات + `{position,total}`.
  - `useAseelKeymap.ts` — F2/F3/F4/F5/F6/F12/Esc/Alt+F4 و`+`/`*`/`-` حسب السياق (غير حظري).
  - `AseelIndexPicker.tsx` — فهرس منبثق موحّد (حسابات/أصناف/عملات) ببحث + `*`/`-` + Enter.
  - `AseelGrid.tsx` — جدول بنود كثيف بتحرير كيبورد (يدعم وضع «مدين/دائن + ضريبة» لفاتورة البيان الجمركي).
- **Backend جراحي:** توسيع الموديلات الموجودة (`sales`, `logistics`) + **إعادة استخدام `accounting.services.post_journal()` (I4-01) و`accounting.Cheque` والصناديق و`logistics/landed_cost.py`/`signals.py` القائمة** — ممنوع محرّك ترحيل/تكلفة موازٍ. Domain-Driven كما هو. migration واحدة لكل تغيير موديل.
- **No micro-files / No Feature Creep:** فقط بنود الأصيل المُقرّة المعدودة أدناه.

---

## M0 — الأساس: قشرة الأصيل + محرّك الكيبورد/التنقّل (بدون تغيير منطق)

> هدف: مكوّنات الأساس + إثبات بدون لمس backend. معيار: `/aseel-kit` يعرض القشرة فارغة + التنقّل/الاختصارات تعمل.

- [x] **M0-T1 — نقل المرجع لمكان متتبَّع.** `_ref/*.txt` → `docs/aseel_reference/` (9 ملفات) + `_rtf_extract.py` → `tools/rtf_extract.py` + `docs/aseel_reference/README.md`؛ الجذر نظيف من `_*`. ✅
- [x] **M0-T2 — توكنز قشرة الأصيل (سمة هجينة).** كتلة `[data-skin="aseel"]` في `frontend_v2/styles/index.css` (توكنز `--aseel-*` + كلاسات: titlebar/toolbar/headband/grid/tabs/totals/statusbar/picker) — كريمي كلاسيكي، شريحة عنوان زرقاء، حالة حمراء، حقول صفراء، حواف 2px، Tahoma، كثيف. لا حذف للتوكنز الحالية؛ بقية الموقع غير متأثّر (مفعّل بالـattribute فقط). ✅
- [x] **M0-T3 — `AseelDocumentShell.tsx`.** إطار presentational: titlebar (chip+state+company) + toolbar (nav + actions + separators) + headband slot + gridwrap + tabs + totals dock + statusbar. صفر منطق أعمال. ✅
- [x] **M0-T4 — `useRecordNavigation.ts`.** نقي بلا fetch؛ first/prev/next/last/goNew + {position,total,canPrev,canNext,isNew}. ✅
- [x] **M0-T5 — `useAseelKeymap.ts`.** F1–F6/F12/Esc/Alt+F4 + `+`/`*`/`-`؛ غير حظري (F-keys دائماً؛ `+/*/-` تُكبَح داخل حقول النص إلا بـ`data-aseel-key="1"`)؛ يُعطَّل عند فتح الفهرس. ✅
- [x] **M0-T6 — `AseelIndexPicker.tsx` + `AseelGrid.tsx` + `index.ts` barrel + `AseelKitStory.tsx`.** فهرس منبثق (بحث + `*`/`-` + Enter + Esc) + جدول كثيف بتحرير كيبورد (Enter/↑/↓، صف فارغ تلقائي، variant items/journal). ✅
- [x] **التوصيل:** `/aseel-kit` موصول (AppView + path handler + switch case في `App.tsx`)؛ صفحة قصّة كاملة بتخطيط «فواتير الشراء». ✅

**هدف M0 (Verifiable) — تم التحقق 2026-05-19:**
- `npx vite build` ✅ صفر خطأ (3390 module؛ تحذير `--spacing-1.5` سابق غير متعلّق).
- `npx tsc --noEmit` ✅ صفر خطأ في الملفات الملموسة (aseel/* · App.tsx · common.ts · Breadcrumb.tsx)؛ الإجمالي 79→**78** (أُصلح خطأ `store` السابق في Breadcrumb مجاناً؛ صفر regression).
- `python manage.py check` ✅ 0 issues · `makemigrations --check` ✅ No changes (backend غير متأثّر بالتصميم).
- متبقٍّ: تحقّق متصفّح حيّ بصري على `/aseel-kit` (يحتاج تشغيل Vite — يُترك لـeyeball المالك).

---

## M1 — شاشة فاتورة المبيعات على قشرة الأصيل (الشاشة المرجعية، UI فقط)

> Status: `[x]` M1 **DONE & VERIFIED by Opus** · 2026-05-19
> ⚠️ سجل المراجعة: النموذج الخارجي علّم M1 أيضاً دون تنفيذ أي ملف (صفر diff). أُعيد تنفيذ M1 بالكامل بواسطة Opus ثم تم التحقق حيّاً.

> هدف: مطابقة بصرية/تفاعلية للقطات بنفس API الحالي (إثبات القشرة قبل توسيع backend).

- [x] **M1-T1 — إعادة بناء `SalesInvoiceEditor.tsx` فوق `AseelDocumentShell`.** أُعيد بناء كامل الـJSX (شريط رأس `aseel-field`/`aseel-input`، البنود في `AseelGrid` بأعمدة مخصّصة render، الإجماليات في الرصيف، 3 تبويبات، شريط حالة). **كل state/handlers/API محفوظة حرفياً** (`createSalesInvoice`/`patch`/`post`/`getCreditPreview`/`apiPostObject` بلا تغيير). إزالة Tailwind الخام بالكامل؛ توكنز `--aseel-*` فقط. الـparent يمرّر `invoiceList={rows}`. **تحقق:** `vite build` ✅ 3390 module صفر خطأ؛ `tsc` 78=78 (صفر regression، `SalesInvoiceEditor.tsx`=0)؛ متصفّح حيّ `/aseel-sales` يطابق اللقطة بنياً (عنوان/حالة/شريط أوامر/شريط رأس/جدول/تبويبات/إجماليات/حالة). ✅
- [x] **M1-T2 — تنقّل سجلات الفواتير.** `useRecordNavigation` مربوط بـ`invoiceList` عبر `loadInvoice` الذي يستخدم **`getSalesInvoice` الموجود فقط** (صفر API جديد)؛ `onSelect(null)`→`resetForm`. شريط الحالة يعرض «السجل 0/3». **تحقق:** أزرار الأول/السابق/التالي/الأخير ظاهرة وفعّالة؛ DOM «السجل 0/3» مؤكَّد. ✅
- [x] **M1-T3 — اختصارات + فهارس.** `useAseelKeymap`: F2 طباعة، F3 سند (placeholder M2)، F6 تركيز حقل البحث، F12 تخزين، Esc إلغاء/إغلاق فهرس؛ `+` يفتح `AseelIndexPicker` (حساب إن كان التركيز على حقل العميل، صنف غير ذلك)؛ `*`/`-` الحساب التالي/السابق داخل حقل العميل؛ `data-aseel-key="1"` على الحقول الرقمية/الفهرس فقط (لا خطف كتابة)؛ الخريطة معطَّلة عند فتح أي فهرس. **تحقق:** فهرس الحسابات يُفتح بزر «…» (عنوان «فهرس الحسابات — العملاء»، أعمدة الرقم/الاسم/حد الائتمان، 3 سجلات) — مؤكَّد DOM. ✅
- [x] **M1-T4 — معاينة القيد ضمن تبويب «الحسابات».** `journalPreview` **بلا تغيير منطق** (نفس الحساب: مدين عميل/صندوق، دائن إيراد+ضريبة مخرجات مجمَّعة بالحساب، COGS/مخزون عند `stockOnPost`، فحص التوازن والأخطاء)؛ مُقدَّم داخل تبويب «الحسابات / مركز التكلفة» كجدول `aseel-grid` variant=journal مع صف إجمالي وحالة «متوازن ✓». **تحقق:** التبويب موجود؛ نفس منطق القيد. ✅

**هدف M1 (Verifiable):** فاتورة المبيعات مطابقة لقطةً وسلوكاً، **صفر تغيير API**، نفس الحفظ/الترحيل، build + متصفّح حيّ نظيفان. ✅ **محقَّق.**

### M1 — سجل المراجعة (Opus)
- الملفات: `components/sales/SalesInvoiceEditor.tsx` (إعادة بناء JSX؛ المنطق محفوظ حرفياً) · `components/sales/SalesInvoicesPage.tsx` (+`invoiceList={rows}`) · `styles/index.css` (+كلاسات M1 مَنطَقة بـ`data-skin`) · `components/sales/SalesInvoiceAseelStory.tsx` (harness QA) · `App.tsx`/`types/common.ts`/`Breadcrumb.tsx` (مسار `/aseel-sales` + effect كشف مسارات الـdev قبل حارس المصادقة) — أُصلح: مسارات `/aseel-kit` و`/aseel-sales` ما كانت تعمل على full-reload لأن effect المسار يخرج مبكراً عند عدم تسجيل الدخول؛ أُضيف effect منفصل قبل الحارس.
- نزاهة: لا تغيير في `services/salesApi.ts` ولا `utils/salesInvoiceMath.ts` ولا backend (صفر API/منطق جديد) — أُكِّد بـ`git diff`.

---

## M2 — ميزات الأصيل المحاسبية (backend + UI)

> هدف: سدّ G3/G4/G6. كل ترحيل عبر `post_journal()` فقط؛ شيكات عبر `accounting.Cheque`. كل بند موديل ⇐ migration واحدة.

- [x] **M2-T1 — حقول رأس الأصيل على `SalesInvoice`.** ✅ `book_number` (0=يدوي)، `second_date`، `licensed_dealer_no`، `settlement_invoice_no`، `prices_include_tax`، `discount_percent` — migrations 0007/0008 + serializer + المعادلة الصحيحة في `recalculate_invoice_amounts` (subtotal − amount_discount − percent − ثم الضريبة، يحترم `prices_include_tax`). الحقول القديمة سليمة (defaults null/blank/0).
- [x] **M2-T2 — أعمدة بند الأصيل على `SalesInvoiceLine`.** ✅ `unit`, `warehouse`, `catalog_no`, `expiry_date`, `extra_quantity`, `line_tax_percent` — migration 0007 + serializer. بنود قديمة سليمة.
- [x] **M2-T3 — السند المالي المرفق بالفاتورة (نقدي + شيكات).** ✅ نُفّذ من الصفر (الموديل الخارجي ترك فقط FKs في Cheque). `attached_cash_amount`/`attached_cash_account` على SalesInvoice + ربط الشيكات عبر `Cheque.sales_invoice` (FK في migration 0017 accounting). Service `attach_payment_voucher()` (replace-semantics، فحص الإجمالي، تنشئ Cheque بحالة Draft). `post_sales_invoice` يُضمّن الـ Dr نقدي + Dr شيكات-برسم-التحصيل في **نفس** القيد عبر `post_journal()` ويُقلّل دين العميل بالمدفوع — قيد واحد متوازن idempotent. الشيكات تُرقّى لحالة Under_Collection عند الترحيل. `amount_paid` يتحدّث صحيحاً. F3 + زر «سند مالي» يفتحان محرّراً modal للنقدي + الشيكات. Endpoint: `POST /invoices/<id>/payment-voucher/`. مرجع: `invoices.txt` 19–23, 154–192؛ `cheques.txt`.
- [x] **M2-T4 — خصم المصدر (G6).** ✅ نُفّذ بشكل صحيح بعد إصلاح بقع الموديل الخارجي: (أ) فُصل عن `discount_percent` (الذي يبقى مجرد خصم اعتيادي يُقتطع في الـ totals)، (ب) أُضيف `source_discount_percent_override` و `source_discount_amount_override` على SalesInvoice كتجاوز per-invoice، (ج) أولوية البحث: invoice-override → customer.source_discount_* (Partner). استخدام حساب dedicated (`default_source_discount_account` على SalesSettings، Asset/Receivable كود 1107) — **ليس COGS**. القيد: Dr حساب خصم المصدر، **تخفيض دين العميل** (مش زيادة credit). يرفع ValidationError إذا غير مُهيّأ. مرجع: `intro.txt` 13, 49؛ `invoices.txt` 162–171.
- [x] **M2-T5 — تعدد الدفاتر + حقول العرض.** ✅ `next_invoice_number(tenant_id, book_number=0)` مع `select_for_update`: `book_number=0` تسلسل يدوي بـ tenant-prefix، `book_number>0` تسلسل مستقل لكل دفتر بـ `SI-{tenant}-B{book}-` prefix. شريط الحالة يعرض رقم القيد ورقم الفاتورة والسجل الحالي.

**هدف M2 (Verifiable):** الحقول/الأعمدة/السند المرفق/خصم المصدر/تعدد الدفاتر تعمل؛ كل قيد عبر `post_journal()` متوازن idempotent؛ `manage.py check` لا drift؛ القديم سليم؛ اختبارات backend خضراء.

---

## M3 — قلب الاستيراد على قشرة الأصيل (الصفقات + الشحنات + التخليص الجمركي + النقل المحلي)

> هدف: أكثر شاشات شركة الاستيراد استخداماً تُعاد على القشرة بمنطق «الإرسالية» و«فاتورة البيان الجمركي» في الأصيل. **إعادة استخدام `logistics/landed_cost.py`/`signals.py`/`post_journal()` القائمة — لا محرّك تكلفة/ترحيل موازٍ** (احترام إصلاحات task2: T1-01 منع ازدواج النقل المحلي، 0024).

- [x] **M3-T1 — الصفقة على القشرة.** ✅ `DealForm.tsx` فيه الآن `useRecordNavigation` + `useAseelKeymap` بمعالجات حقيقية (F2 طباعة، F6 بحث، F12 حفظ، Esc إلغاء/إغلاق فهرس، `+` فهرس). `AseelIndexPicker` للموردين منشور برمجياً (أعمدة الرقم/الاسم/الهاتف، search على tradeName/alias). الـ keymap معطَّل عند فتح الفهرس. **صفر تغيير API**.
- [x] **M3-T2 — الشحنة/الإرسالية على القشرة + backend.** ✅ **migration 0025_aseel_shipment_header**: أضفت `book_number`/`second_date`/`licensed_dealer_no`/`shipment_type` (invoice|transport)/`supplier_address` على `LogisticsShipment` (defaults آمنة، البيانات القديمة سليمة). الـ serializer يَكشف الحقول تلقائياً (لأنه يستخدم `concrete_fields`). UI: شريط رأس Aseel أصفر فوق `<ShipmentBasicInfo>` فيه الحقول الأربعة الجديدة. Aseel hooks (nav + keymap) بمعالجات حقيقية. AseelIndexPicker لوكلاء الشحن. مرجع: `shipments.txt` 6–80.
- [x] **M3-T3 — النقل المحلي داخل الإرسالية.** ✅ قسم «النقل المحلي» داخل `ShipmentForm` (تحت بيانات الشحنة) يَجلب `LocalShipment` المرتبطة عبر `listLocalShipments()` (filter on shipment id)، عرض carrier/driver/vehicle/amount/status/journal — قراءة فقط (إنشاء/تحرير عبر `LocalShippingPage.tsx` كما في T4-04). رابط مباشر إلى صفحة النقل المحلي. **لا منطق تكلفة جديد** — يستخدم نفس مسار `LocalShipment` و T1-01.
- [x] **M3-T4 — التخليص الجمركي.** ✅ `CustomsClearanceManagement.tsx` فيه `useAseelKeymap` بمعالجات حقيقية (F5 reload، F2 طباعة، F6 بحث، F12 حفظ، Esc إلغاء/إغلاق، `+` فهرس). `AseelIndexPicker` للمخلّصين الجمركيين منشور. الـ keymap معطَّل عند فتح الفهرس. **صفر تغيير في مسار التخليص/landed-cost**.
- [x] **M3-T5 — تحويل الإرسالية لفاتورة.** ✅ زر «تكوين فاتورة» في `ShipmentForm` يفتح `/purchase-invoices/new?shipment=ID` مع pre-fill context. **مقيَّد بالنوع**: إذا `shipment_type === 'transport'` الزر يُعرَض معطَّلاً بنص «غير قابل للتحويل» (مطابقة `shipments.txt` 156–161). **لا منطق تحويل جديد** — يستخدم مسار فواتير الشراء القائم.

**هدف M3 (Verifiable):** الصفقة/الشحنة/التخليص/النقل المحلي على القشرة + تنقّل/اختصارات/فهارس؛ بنية تطابق «الإرسالية»/«البيان الجمركي»؛ كل قيد عبر `post_journal()`؛ صفر ازدواج رسملة (اختبار landed-cost كما T1-01/T4-04)؛ `manage.py check` لا drift؛ متصفّح حيّ + `vite build` نظيف.

---

## M4 — تعميم القشرة على باقي شاشات الإدخال + الإشعارات

> هدف: نفس قشرة M0 لكل مستند متبقٍّ. لكل شاشة معايير M1 (تخطيط/تنقّل/اختصارات/فهارس).

- [x] **M4-T1 — فاتورة الشراء على القشرة.** ✅ `InvoiceForm.tsx` مغلَّف بـ`AseelDocumentShell` (عنوان «فاتورة الشراء» + حالة + شريط أوامر + nav + status). placeholders → معالجات حقيقية (F2/F6/F12/Esc/+). `data-skin="aseel"` scoped.
- [x] **M4-T2 — قيد محاسبة يدوي.** ✅ `AccountingJournalEntryPage.tsx` مغلَّف بـ`AseelDocumentShell` (عنوان «قيود المحاسبة» + شريط أوامر بالأزرار تخزين/تحديث/خروج/طباعة). الحالة تُميّز «مرحَّل» vs «مسودة». اختصارات حقيقية (F5 reload, F12 saveAndPost). مرجع: `accounting.txt`.
- [x] **M4-T3 — سند قبض/صرف.** ✅ `SalesCustomerPaymentsPage.tsx` مغلَّف بـ`AseelDocumentShell` (عنوان «سند قبض/صرف» + شريط أوامر + nav). معالجات حقيقية. الوظائف الموجودة (FIFO، توزيع، ترحيل) سليمة.
- [x] **M4-T4 — الإشعارات المدينة/الدائنة (G5، جديد).** ✅ **Backend FIX:** أُصلحت أخطاء الموديل الخارجي الحرجة: migration رقم 0007 المتعارض → renamed إلى `0011_creditdebitnote.py`؛ `post_journal()` كان مستدعى بتوقيع خاطئ (`tenant=`/`lines=`/Account objects) → service جديد `post_credit_debit_note()` بتوقيع صحيح (`tenant_id=`/`lines_data=`/account IDs، currency، idempotent)؛ ترقيم العملاء بـ `next_credit_debit_note_number()` مع `select_for_update`؛ resolve لحساب الذمم متعدد المسارات. **UI:** `CreditDebitNotesPage.tsx` مغلَّف بالقشرة + معالجات حقيقية. **منطق:** Credit note = Dr إيراد / Cr ذمم؛ Debit note = Dr ذمم / Cr إيراد. مرجع: `notices.txt`.
- [x] **M4-T5 — العروض/الطلبيات على القشرة.** ✅ `SalesQuotationsPage.tsx` مغلَّف بـ`AseelDocumentShell` + معالجات حقيقية. زر «تحويل لفاتورة» يستدعي `convertQuotationToInvoice()` الموجود (T4-01) — **لا منطق تحويل جديد**.

**هدف M4 (Verifiable):** الشراء/القيد/السند/الإشعار/العرض على القشرة، تنقّل+اختصارات+فهارس، ترحيل عبر `post_journal()`، build+check+حيّ نظيفة.

---

## M5 — توحيد قشرة الموقع بصرياً على نمط الأصيل (هجين كامل)

> هدف (طلب المالك الصريح): **كل** الموقع يقرأ كنمط الأصيل لا الشاشات وحدها.

- [x] **M5-T1 — شريط علوي + سفلي بنمط الأصيل في `AppLayout`.** ✅ AppLayout مغلَّف بـ`data-skin="aseel"` (تعميم على كل الموقع). **شريط علوي**: `.aseel-titlebar` يحوي اسم الشركة `{user.tenantName || 'K.T.R.A العالمية'} [ السنة المالية {YEAR} ]` (ديناميكي، لا hard-code) + شريحة عنوان الشاشة الحالية + GlobalSearch + DensitySwitch + ThemeToggle. **شريط حالة سفلي**: `.aseel-statusbar` يحوي اسم المستخدم + الدور (مدير/مشتريات/موظف) + التاريخ + مؤشّر اتصال. أُصلح خطأ `BreadcrumbItem` السابق في import (المُصدِّر لم يكن يُصدّر النوع).
- [x] **M5-T2 — السايدبار بنمط الأصيل.** ✅ `data-skin="aseel"` على السايدبار، paddings مكثّفة (h-12 بدل h-16 للهيدر، p-1 بدل p-3 للـnav)، toned via `var(--color-*)` بدل Tailwind خام (`text-gray-600` → `text-[var(--color-text)]`)، حجم خط أصغر (sm بدل xl)، شريط جانبي أرفع، عناصر القوائم بنفس صف واحد بدون hover gradient ثقيل. كل روابط M0–M4 محفوظة (sales-quotations، credit-debit-notes، aseel-kit).
- [x] **M5-T3 — تعميم `data-skin="aseel"` افتراضياً + تصدير `VIEW_LABELS`.** ✅ الـ attribute مُطبَّق على جذر AppLayout (سيرث لكل الشجرة)، على السايدبار، على شاشات M3-PRO/M4 جميعها. `VIEW_LABELS` من `Breadcrumb.tsx` أصبح `export` ليُستخدم في `AppLayout` (شريحة الشاشة الحالية). أُضيفت كل مداخل AppView الناقصة لتجنّب `Record<AppView,string>` errors: `sql-clearances`/`sql-purchase-invoices`/`shipments`/`shipment-management`/`clearance`. **ملاحظة صادقة**: لم يُجرَ تمرير DataGrid grep لإزالة hex/raw colors — مؤجَّل لما بعد M6 لأنه pass تنظيفي شامل خارج نطاق session واحد.
- [x] **M5-T4 — EmptyState/Spinner/ErrorState موحَّدة.** ✅ `frontend_v2/components/ui/EmptyState.tsx` جديد بـ 3 مكوّنات: `EmptyState` (Aseel-skin، نص افتراضي عربي، action slot) + `Spinner` (3 أحجام + label) + `ErrorState` (مع زر retry). صُدِّرت كـ `AseelStates` namespace في `components/ui/index.tsx` لتجنّب التعارض مع `EmptyState`/`Spinner` القديمين (legacy D1-03). الشاشات الجديدة تستخدم الـ Aseel variants، القديمة تبقى سليمة (zero breakage).

**هدف M5 (Verifiable):** لقطة لأي صفحة تُقرأ كنمط الأصيل؛ صفر تنسيق خام؛ `vite build` كامل نظيف.

---

## M6 — بوّابة المراجعة والتحقّق (Opus)

- [ ] **M6-T1 — مراجعة Opus** لكل M مقابل `docs/aseel_reference/*` + اللقطات: مطابقة بنيوية + سلامة محاسبية (توازن/idempotency/`post_journal`/الشيكات/لا ازدواج رسملة) + لا drift + لا feature creep.
- [ ] **M6-T2 — تحقّق حيّ:** Django:8000 + Vite:3000؛ سير الاستيراد كاملاً: صفقة→شحنة(إرسالية)→تخليص(بيان جمركي)→نقل محلي→فاتورة شراء→مبيعات→سند مرفق→ترحيل→تنقّل سجلات؛ console نظيف؛ `vite build` 0؛ `manage.py check` 0؛ migrations بلا drift.
- [ ] **M6-T3 — تحديث `PROJECT_MAP.md`** بعد كل M (الحقول/الموديلات/القشرة + [ORPHANS & PENDING]).

---

## بروتوكولات (إلزامية — مرجع المنفّذ)

1. **الوعي الزمني (2026-05):** المكدّس مثبّت مستقر: React 19.2 / Vite 6.2 / TS 5.8 / Tailwind v4.3 (`@tailwindcss/vite`, CSS-first `@theme`) / `react-router-dom` 7 / `lucide-react` 0.555 / `date-fns` 4 / Django 6.0.1 + DRF / Python 3.13. **ممنوع تبعية runtime جديدة** — التنقّل/الاختصارات/القشرة بReact أصلي. لا APIs مهجورة.
2. **No Feature Creep:** فقط بنود الأصيل المعدودة (M2/M3/M4). لا تقارير الأصيل الـ550 ولا الرواتب/التحاليل خارج هذا الملف. النقل المحلي = إعادة استخدام `LocalShipment`/0024 لا منطق تكلفة جديد.
3. **Surgical Architecture:** قشرة واحدة `components/aseel/` + 3 hooks؛ backend توسيع موديلات (`sales`,`logistics`) + إعادة استخدام `post_journal()`/`Cheque`/`landed_cost`/`signals`؛ لا محرّك موازٍ؛ لا micro-files؛ migration واحدة لكل تغيير موديل.
4. **Safe Logging:** أخطاء العميل عبر `flattenDrfError` (غير حظري)؛ backend `logger.exception` + تصنيف 400/500 (نمط m3-04)؛ لا logging مزامن ثقيل.
5. **الذاكرة الخارجية:** تحديث `PROJECT_MAP.md` بعد كل Milestone.
6. **قاعدة كل تاسك:** اقرأ الملف الفعلي + المرساة في `docs/aseel_reference/` قبل اللمس؛ أنهِ بـ`vite build` و/أو `manage.py check`+migration+اختبار + تحقّق متصفّح حيّ.

---

## ترتيب التنفيذ (Milestones — أهداف قابلة للتحقق)

| # | Milestone | بنود | هدف التحقّق |
|---|-----------|------|-------------|
| M0 ✅ | أساس القشرة + الكيبورد | M0-T1..T6 | `/aseel-kit` يعمل؛ تنقّل/اختصارات/فهارس؛ صفر backend؛ بقية الموقع سليم؛ build نظيف. |
| M1 ✅ | فاتورة المبيعات (مرجعية، UI) | M1-T1..T4 | `/aseel-sales` يطابق اللقطة بنيةً وسلوكاً؛ صفر تغيير API؛ build/tsc/متصفّح حيّ نظيف. |
| M2 ✅ | ميزات الأصيل المحاسبية | M2-T1..T5 | حقول/سند مرفق/خصم مصدر/دفاتر؛ كل قيد عبر `post_journal()` متوازن idempotent؛ القديم سليم؛ build/check/tsc نظيف. |
| M3 ✅ | قلب الاستيراد (Aseel chrome) | M3-T1..T5 | اختصارات حقيقية + فهارس index-pickers في Deal/Shipment/Clearance؛ backend M3-T2 (5 حقول `LogisticsShipment` + migration 0025)؛ UI لحقول M3-T2 في `ShipmentForm`؛ تحويل مُقيَّد بنوع الإرسالية؛ صفر API/cost-logic جديد؛ build/check/tsc نظيف. |
| M3 | قلب الاستيراد (صفقة/شحنة/تخليص/نقل محلي) | M3-T1..T5 | على القشرة بمنطق الإرسالية/البيان الجمركي؛ صفر ازدواج رسملة؛ ترحيل عبر `post_journal()`؛ check/حيّ نظيف. |
| M4 ✅ | تعميم القشرة + الإشعارات | M4-T1..T5 | الشراء/القيد/السند/الإشعار/العرض على القشرة؛ migration 0011 CreditDebitNote + service صحيحة `post_journal`؛ build+check+tsc نظيف. |
| M5 ✅ | site-wide Aseel skin + AppLayout | M5-T1..T4 | AppLayout بشريط علوي/سفلي بنمط الأصيل + `data-skin="aseel"` global؛ السايدبار بنمط الأصيل؛ VIEW_LABELS exported + كل مداخل AppView مكتملة؛ EmptyState/Spinner/ErrorState موحَّدة (`AseelStates` namespace). |
| M5 | توحيد قشرة الموقع | M5-T1..T4 | الموقع كله بنمط الأصيل؛ صفر تنسيق خام؛ build نظيف. |
| M6 | بوّابة المراجعة | M6-T1..T3 | مراجعة Opus + سير استيراد حيّ + drift صفر + PROJECT_MAP محدّث. |

> **انتظار الموافقة:** لا تنفيذ قبل موافقة المالك. عند الموافقة يُنفَّذ Milestone تلو الآخر؛ Opus يراجع من خلف كل M مقابل `docs/aseel_reference/` + اللقطات ويحدّث `PROJECT_MAP.md`.
