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
