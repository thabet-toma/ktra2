# CLAUDE.md — K.T.R.A Project

## قواعد السلوك (مُطبَّقة دائماً)

- نفّذ ما طُلب فقط — لا أقل ولا أكثر
- لا تنشئ ملفات إلا إذا كانت ضرورية تماماً
- افضّل دائماً تعديل ملف موجود على إنشاء ملف جديد
- لا تنشئ ملفات docs أو README تلقائياً إلا إذا طُلب صراحةً
- اقرأ الملف دائماً قبل تعديله
- لا تحفظ أسرار أو credentials أو ملفات .env في git

## التوازي — قاعدة أساسية

جميع العمليات غير المترابطة **يجب** تنفيذها بشكل متوازٍ في رسالة واحدة:

- دائماً اجمع ALL قراءات/كتابات الملفات في رسالة واحدة
- دائماً اجمع ALL أوامر terminal في رسالة واحدة
- استخدم `Task` tool لإطلاق Agents متوازية لأي مهمة معقدة

---

## قراءة السياق — ابدأ من هنا

قبل أي مهمة، اقرأ **هذين فقط**:

1. `ARCHITECTURE.md` — خريطة الـapps، مخطط الاعتماديات، القواعد العابرة للنظام، وجدول «أين أبدأ؟»
2. `docs/modules/<الموديول المعني>.md` — الملفات والـmodels والـservices والـendpoints وقواعد لا يجوز كسرها

المتاح: `sales` · `accounting` · `inventory` · `logistics` · `partners` · `tenants` · `hr` · `accountant_portal`

**لا تقرأ `docs/history/PROJECT_MAP.md` افتراضياً** — سجلّ تاريخي للمهام (8,104 سطر)، يُرجَع إليه فقط عند البحث عن سبب قرار قديم.

مراجع أخرى: `docs/decisions/` (قرارات معمارية) · `docs/REFACTOR_PROMPTS.md` (خطة الفصل وجاهزية التوسّع).

---

## إعدادات مشروع K.T.R.A

### Tech Stack
- **Backend:** Django 5.1.15 (requirements.txt), DRF 3.16, MySQL (prod) / SQLite (test)
  — لا تستعمل ميزةً حصريةً بـ6.0
- **Frontend:** React 19.2, TypeScript 5.8, Vite 6.2, Tailwind CSS 4.3
- **Tests:** `python manage.py test --settings=core.test_settings` — 1,025 اختباراً، يجب أن تبقى خضراء

### بنية المجلدات الرئيسية
13 Django app. الجدول الكامل بالمسؤوليات والأحجام في `ARCHITECTURE.md`. الأكبر:

| مجلد | الغرض |
|------|--------|
| `logistics/` | الاستيراد والمشتريات — صفقة، شحنة، تخليص، فاتورة دولية |
| `sales/` | المبيعات والعملاء |
| `core/` | طبقة مشتركة — عزل الشركة، الصلاحيات، التقارير |
| `accounting/` | محاسبة — قيود، شيكات، بنوك، فترات مالية |
| `inventory/` | المخزون والمنتجات |
| `partners/` | العملاء والموردين |
| `frontend_v2/` | React SPA (TypeScript) |

### قواعد Django
- استخدم `core.test_settings` في الاختبارات
- الـ migrations في مجلد `migrations/` داخل كل app
- الـ models والـ views والـ serializers والـ services في **جذر كل app** (`sales/views.py`) — لا مجلد `api/`
- الاختبارات في `<app>/tests/`
- **كل قيد محاسبي يمرّ عبر `accounting.services.post_journal`** — لا كتابة مباشرة لـ`JournalHeader`/`JournalLine`
- **كل تغيير مخزون يمرّ عبر `inventory.services.record_stock_movement`**
- كل model يحمل `tenant` FK، وكل ViewSet يفلتر عليه — `get_queryset` بلا فلتر شركة = تسريب بيانات

### قواعد Frontend
- الملفات في `frontend_v2/` مباشرةً (`components/`، `services/`، `utils/`) — لا وجود لـ`src/`
- استخدم `restApi.ts` كـ base client
- CSS عبر Tailwind فقط — لا inline styles
