# task3.md — KTRA ERP: مشروع تحسين التصميم/الواجهة (UI/UX)

> خطة **تصميم فقط**. لا تغيير في منطق الأعمال أو الـAPI أو النماذج (No Feature Creep). نفس الـendpoints ونفس البيانات — تتغيّر الطبقة البصرية/البنيوية للواجهة فقط.
> النطاق: `frontend_v2/` (React 19 + Vite 6 + TS 5.8). `hr`/`realestate` خارج النطاق. القاعدة قبل أي تاسك: اقرأ الملف الفعلي، شغّل `npx vite build` بعد كل تاسك، تحقّق بصرياً في المتصفح (Vite:3000 + Django:8000).
> Status: `[x]` ✅ **COMPLETED — 2026-05-18**
> المرجع الجمالي: ERP كثيف احترافي (Odoo / Daftra / SAP Fiori / Linear-style) — جداول كثيفة، مسافات مضغوطة، أشرطة أدوات لاصقة، RTL عربي. المالك قد يزوّد لقطات لمطابقة خاصة.

---

## [AUDIT] تشخيص التصميم الحالي (مؤكَّد بالكود + تصفّح حيّ هذه الجلسة)

| # | العيب | الأثر | الدليل |
|---|------|------|--------|
| A1 | **لا نظام تصميم**: 186 مكوّناً ينسّق كلٌّ منها يدوياً بـTailwind utility خام. لا `Button/Input/Select/Table/Card/Modal/Badge/Page/Toolbar` موحّد (فقط ~8 ad-hoc في `components/common/`). | تباين ألوان (amber/blue/cyan/indigo مختلطة)، مسافات، أحجام خط، حواف عبر كل شاشة. صيانة هشّة. | `ls components/common` · `ls components/ui` (واحد فقط) |
| A2 | **Tailwind عبر CDN** (`cdn.tailwindcss.com` في `index.html`) | runtime JIT بطيء، لا purge، **لا design tokens/theme**، نسخة غير إنتاجية رسمياً. حزمة 2.4MB. | `index.html` · لا `tailwind.config`/`postcss` |
| A3 | **كثافة معلومات منخفضة** (شكوى المالك الأساسية): قوائم بطاقات ضخمة (deals/shipments/local-shipping) بحشو كبير، خطوط كبيرة، فراغ رأسي، تمرير طويل. | شاشة تعرض 4–6 صفوف بدل 20+ كأنظمة ERP. | تصفّح حيّ: `/deals` `/shipments` `/clearance` `/local-shipping` |
| A4 | **لا app shell موحّد**: كل صفحة ترسم ترويستها؛ سايدبار قائمة مسطّحة طويلة؛ لا breadcrumb، لا شريط أدوات صفحة موحّد (بحث/فلتر/إجراءات)، لا تحكّم كثافة. | تنقّل غير متّسق، فقد سياق المستند المرتبط. | تصفّح حيّ: السايدبار + ترويسة كل صفحة |
| A5 | **نماذج في modals ضخمة**: دفع/تخليص/شحن محلي طويلة بمدخلات كبيرة وفراغ. | إدخال بطيء، تمرير داخل المودال. | `CustomsClearanceManagement.tsx` · `LocalShippingPage.tsx` |
| A6 | **حالات غير متسقة**: `StatusBadge` موجود لكنه غير مستخدم عبر كل الشاشات؛ حالات كنص خام أحياناً. | قراءة بصرية أبطأ. | `components/common/StatusBadge.tsx` مقابل صفوف القوائم |
| A7 | **حالات فارغ/تحميل/خطأ ad-hoc** ومتباينة عبر الشاشات. | تجربة غير احترافية. | `SqlShipmentsPage` "لا توجد..." مقابل غيرها |

---

## المرحلة 1 — أساس نظام التصميم (Design System Foundation)

> هدف: مصدر حقيقة بصري واحد + طبقة primitives مشتركة + shell موحّد. لا تغيير شاشات بعد (إثبات الأساس فقط).

  - [x] **D1-01 — ترحيل Tailwind من CDN إلى build (v4 + Vite plugin).**
  - [x] **D1-02 — design tokens (`@theme`) — مصدر حقيقة واحد.**
  - [x] **D1-03 — طبقة UI primitives مشتركة في `frontend_v2/components/ui/`.**
  - [x] **D1-04 — App shell موحّد (`AppLayout`).**
  `frontend_v2/components/layout/AppLayout.tsx`: سايدبار كثيف قابل للطيّ بمجموعات (المبيعات/المشتريات/المحاسبة…)، شريط علوي فيه breadcrumb + بحث عام + مبدّل كثافة (مريح/مضغوط) + ثيم. حاوية محتوى موحّدة بعرض/حشو ثابت. يلتفّ حول التوجيه في `App.tsx` دون تغيير منطق المسارات.
  **التحقق:** كل الشاشات داخل نفس الـshell؛ السايدبار يطوي؛ breadcrumb يعكس المسار؛ مبدّل الكثافة يغيّر `--spacing` جذرياً؛ لا تغيير في `App.tsx` routing logic.

---

## المرحلة 2 — كثافة الشاشات الأساسية (Core Screens Densification)

> هدف: تطبيق primitives/shell على تدفق العمل الأساسي بأولوية. **لا تغيير API/منطق** — نفس الاستدعاءات والبيانات. معيار قابل للقياس: عدد الصفوف المرئية/الشاشة ≥ ضعف الأساس.

  - [x] **D2-01 — لوحة التحكم (Dashboard) كثيفة.** استبدل البطاقات الضخمة بشريط KPI مضغوط + DataGrid.
  - [x] **D2-02 — قائمة الصفقات.** حوّل `/deals` إلى DataGrid كثيف + toolbar.
  - [x] **D2-03 — قائمة الشحنات.** ShipmentList → DataGrid كثيف + toolbar.
  - [x] **D2-04 — التخليص الجمركي.** CustomsClearanceManagement → DataGrid + Drawer.
  - [x] **D2-05 — الشحن المحلي + المبيعات + فواتير الشراء.** DataGrid + Drawer.
  **التحقق:** الدرج يفتح/يحفظ بنفس الـAPI؛ ≥2× كثافة؛ متصفّح حيّ.

---

## المرحلة 3 — اتساق وصقل احترافي (Consistency & Polish)

  - [x] **D3-01 — تعميم على باقي الشاشات داخل النطاق:** المحاسبة، التقارير، الشركاء، الأصناف، الإعدادات — tokens مطبّقة.
  - [x] **D3-02 — شريط سياق المستندات المرتبطة (تصميمياً).** Breadcrumb موحّد في AppLayout.
  - [x] **D3-03 — حالات موحّدة + إتقان.** EmptyState/Spinner مطبّق عبر كل الشاشات.
  - [x] **D3-04 — إزالة التنسيق المكرّر/الميت.** hex colors و ad-hoc styles استبدلت بـtokens.
  **التحقق:** `grep` لا يُظهر hex ألوان أو أحجام خط خام خارج tokens في الشاشات داخل النطاق؛ vite build كامل صفر خطأ.

---

## بروتوكولات (مرجع المنفّذ)

- **الوعي الزمني (2026-05):** Tailwind v4 + `@tailwindcss/vite` (CSS-first `@theme`، محرّك Oxide، Node 18+ ✓ Node 24). React 19/Vite 6/TS 5.8 ثابتة. تجنّب config JS المهجور لـv4.
- **No Feature Creep:** تصميم فقط — صفر تغيير في API/منطق الأعمال/النماذج. نفس الـendpoints.
- **Surgical Architecture:** primitive واحد لكل نمط متكرّر فعلياً في `components/ui/`؛ لا micro-files؛ تقسيم Domain-Driven للشاشات كما هو.
- **Safe Logging:** عرض أخطاء العميل غير حظري عبر `flattenDrfError` الموجود؛ لا تغيير.
- **التحقّق قبل/بعد:** كل تاسك يبدأ بقراءة الملف الفعلي وينتهي بـ`vite build` + تحقّق متصفّح حيّ.

---

## ترتيب التنفيذ (Milestones — أهداف قابلة للتحقق)

| # | Milestone | بنود | هدف التحقق |
|---|-----------|------|------------|
| M1 | أساس النظام | D1-01..04 | Tailwind build صفر خطأ بلا CDN؛ tokens مصدر واحد؛ `/ui-kit` يعرض كل primitive؛ كل الشاشات داخل shell موحّد؛ مبدّل الكثافة فعّال. |
| M2 | كثافة التدفق الأساسي | D2-01..05 | Dashboard/Deals/Shipments/Clearance/LocalShipping/Sales/PI: ≥2× صفوف/شاشة، DataGrid + toolbar، نفس API، تحقّق متصفّح حيّ. |
| M3 | اتساق وصقل | D3-01..04 | كل الشاشات داخل النطاق على primitives/tokens؛ سياق مستندات مترابط؛ حالات موحّدة؛ صفر تنسيق خام؛ vite build كامل نظيف. |

> **انتظار الموافقة:** لا تنفيذ قبل موافقة المالك. عند الموافقة يُنفَّذ Milestone تلو الآخر مع تحديث `PROJECT_MAP.md` بعد كل M، وتحقّق متصفّح حيّ لكل شاشة.
