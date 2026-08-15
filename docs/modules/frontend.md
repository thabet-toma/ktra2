# frontend — واجهة React (`frontend_v2/`)

## الغرض

الـSPA كاملةً: React 19 + TypeScript 5.8 + Vite 6 + Tailwind 4. تتحدّث مع Django
عبر `/api/` حصراً.

**الملفات مباشرةً تحت `frontend_v2/` — لا مجلد `src/`.**

## أهم الملفات

| المسار | الغرض |
|---|---|
| `frontend_v2/App.tsx` | الجذر: التوجيه، 97 صفحة lazy، تركيب السياقات |
| `frontend_v2/services/restApi.ts` | **الـbase client** — مهلة 30ث، إعادة محاولة GET، ترويسات الشركة/الفرع |
| `frontend_v2/services/` | 52 ملفاً — خدمة لكل دومين (`salesApi`, `accountingApi`, `inventoryApi`, `dealsService`…) |
| `frontend_v2/components/aseel/` | **غلاف المستندات المشترك**: `AseelDocumentShell`, `AseelDenseTable`, `AseelDocumentView`, `AseelAutocomplete` |
| `frontend_v2/contexts/` | 9 سياقات: `Auth`, `Company`, `Permissions`, `Appearance`, `SessionSettings`, `Theme`, `Toast`, `Confirm`, `PriceVisibility` |
| `frontend_v2/utils/navAccess.ts` | اشتقاق القائمة: الصلاحية + قناع «الوضع السهل» — **نقطة التركيب الوحيدة** |
| `frontend_v2/utils/uiMode.ts` | «الوضع السهل»: `SIMPLE_VIEWS` و`viewVisibleInSimpleMode` وcache بمفتاح الشركة |
| `frontend_v2/components/ui/FieldHint.tsx` · `frontend_v2/constants/simpleHints.ts` | أيقونة «؟» ونصوصها — **كل النصوص في الملف الثاني وحده** |
| `frontend_v2/utils/formatNumber.ts` | **كل عرض رقمي يمرّ من هنا** |
| `frontend_v2/utils/formatDate.ts` | التواريخ — لا `toLocaleDateString` بلغة عربية |
| `frontend_v2/services/tenantSettingsApi.ts` | مصدر مشترك لإعدادات الشركة (نافذة 60ث) |
| `frontend_v2/components/legacy/firestoreService.ts` | الجسر القديم — **يُستورَد ديناميكياً** لا ثابتاً |

## بنية المكوّنات

39 مجلداً فرعياً تحت `components/`، أهمّها بحسب الدومين: `sales/` · `accounting/` ·
`inventory/` · `logistics/` · `import-flow/` · `partners/` · `procurement/` ·
`finance/` · `hr/` · `reports/` · `settings/` · `superadmin/`.
والمشترك: `aseel/` (غلاف المستندات) · `common/` · `shared/` · `ui/` · `layout/`.

## العقود مع الخادم

| العقد | القاعدة |
|---|---|
| الشركة | كل طلب يحمل `X-Tenant-Id` (و`X-Branch-Id` عند اللزوم) — يضيفها `restApi.ts` |
| الترقيم | نقاط «الفئة أ» **ترقيمها إلزامي** — مرّر `?page=` وإلا قد يُردّ الطلب. الـautocomplete يبقى بلا ترقيم |
| المحدِّدات | أصناف المستندات عبر `listPickerProducts` (`?view=lookup`) لا العقد الكامل |
| الصلاحيات | `/api/permissions/me/` **للعرض فقط** — إخفاء زر ليس حماية |
| الوحدات المرخّصة | غير المفعّلة ترد **404** لا 403 — عالِج الحالتين |
| وضع العرض | `ui_mode` يصل ضمن حمولة `/api/permissions/me/` نفسها (بلا طلب إضافي)، ويُحفَظ بـ`POST /api/tenants/companies/set-ui-mode/` |

## «الوضع السهل» — قناعُ عرضٍ فوق نفس الواجهة

نسخة مبسّطة للتاجر المبتدئ: **قناع لا منتج ثانٍ ولا واجهة ثانية**. لا شاشة جديدة بُنيت،
ولا سطر خادميّ محاسبيّ تغيَّر.

- **عرضٌ لا صلاحية.** يقلّم ما يُعرَض أولاً ولا يحجب مساراً: الرابط المباشر لأي شاشة
  متقدمة يبقى يعمل في الوضع السهل («مخفيّ لا محذوف»)، والحارس الوحيد يبقى الصلاحيات.
  **الصلاحية تحجب والوضع يُرتّب** — والوضع لا يمنح أبداً ما منعته الصلاحية.
- **نقطة التركيب واحدة**: `utils/navAccess.ts` (`linkVisible`) بوسيط `uiMode` اختياري،
  فوق قائمة الشاشات في `utils/uiMode.ts` (`SIMPLE_VIEWS`). حذف الوسيط = السلوك القديم
  حرفياً. **لا تُضِف آلية إخفاء ثانية** فوق القائمة — آليتان متنازعتان هما كيف تموت شاشة
  بصمت. `App.tsx` (التوجيه) لا يُمَسّ.
- **مصدر الحقيقة الخادم**، والـcache المحلي (`ktra_ui_mode::<tenantId>`) لتطبيقٍ فوري بلا
  وميض قبل رد `/permissions/me/`. أي قيمة غير معروفة — خادم أقدم، cache فاسد، حمولة ناقصة
  — تُطبَّع إلى `advanced` (`utils/uiMode.ts` — `normalizeUiMode`). الافتراضي هو التجربة
  الكاملة؛ التبسيط اختيارٌ صريح.
- **الحفظ تفاؤلي ولا يرتدّ تحت يد المستخدم**: الحالة والـcache فوراً ثم POST في الخلفية،
  وفشلُه يُبقي الوضع عاملاً في هذا المتصفح مع toast واحد بنبرة «معلومة» أن الحفظ عبر
  الأجهزة لم يتم — وهو مسار دور `viewer` المعروف (ممنوع من كل كتابة على المنصة).
- **زر التبديل ظاهر في الوضعين** في ذيل الشريط الجانبي (بجوار مبدّل «وضع المحاسب» الذي
  يختفي في السهل): طريق العودة يجب ألا يمرّ بشاشةٍ يخفيها القناع نفسه.
- **قاعدة السقوط للظهور — «يظهر رغم الوضع»**: عنصرٌ يشرح افتراضاً **مطلوباً لم يُحَلّ**
  يبقى ظاهراً في الوضع السهل. في `SalesInvoiceEditor.tsx` (`unresolvedRequiredDefault`):
  محدّد العملة يظهر ما لم تحسمه الإعدادات فعلاً، وتبويب «بيانات أخرى» يبقى ما دام تحذير
  إعدادٍ حيّاً. لا فشل صامت ولا حالة بلا مخرج — وهذه القاعدة فوق أي قائمة إخفاء.
- **العنصر المخفيّ يحتفظ بقيمته وحالته**، فحمولة الوضع السهل مطابقة لحمولة المتقدّم لمن
  ترك الافتراضيات ⇒ **نفس القيد المحاسبي بالضبط**. يسمّره خادمياً
  `sales/tests/test_simple_mode_journal_parity.py`.
- **طبقة «؟»**: `FieldHint` يقرأ الوضع بنفسه ويختفي في المتقدّم (فلا يُنسى الشرط في موضع
  نداءٍ من ثمانية عشر)، ولا يحمل نصاً — كل حرف في `constants/simpleHints.ts`، ومفتاحٌ
  بلا نصّ يعني لا أيقونة لا انكسار.
- **ترتيب المزوّدات مقصود**: `ToastProvider` **فوق** `PermissionsProvider` في
  `frontend_v2/index.tsx` — الأخير يحتاج `useToast` (وهو يرمي بلا مزوّد). لا تُعِد الترتيب.
- الرحلة كاملةً يحرسها `frontend_v2/e2e/simple-ui-mode.spec.ts`.

## قواعد لا يجوز كسرها

1. **`tsc` لا يفحص خصائص JSX** — لا `@types/react` في المشروع. مكوّن يستقبل prop
   لا يمرّره أحد يبقى ميتاً بلا شكوى. **تحقّق من المستدعي بالقراءة** بعد أي تغيير
   على واجهة مكوّن.
2. **كل رقم عبر `utils/formatNumber`** — لا `toFixed(2)` ولا `toLocaleString`
   للمبالغ (مصدر أصفار زائدة متكرّر).
3. **التواريخ عبر `utils/formatDate`** — `toLocaleDateString` بلغة عربية يعطي
   هجرياً/أرقاماً هندية حسب إعداد الجهاز.
4. **Tailwind فقط — لا inline styles.** وانتبه: قواعد `tbody td` خارج الطبقات في
   `index.css` تُبطل أصناف Tailwind على خلايا الجداول.
5. **الغلاف يتتبّع التبويب بالفهرس** — إضافة تبويب في المنتصف وقت التشغيل تقفز
   بالمستخدم؛ ألحِقه آخر القائمة.
6. **نوافذ الكاش تُفرَغ بعد نجاح الكتابة لا قبلها**، ومع عدّاد أجيال كي لا يعيد
   طلبٌ طائر ملأها بقيمة قديمة (`inventoryApi.ts`, `tenantSettingsApi.ts`).

## التحقق

```bash
cd frontend_v2
npx tsc --noEmit     # لا يفحص JSX props — انظر القاعدة 1
npm test             # اختبارات utils
npm run build
```

## الاعتماديات

**يعتمد على:** كل الـAPI تحت `/api/` — الفهرس الكامل في `docs/API_INDEX.md`.
