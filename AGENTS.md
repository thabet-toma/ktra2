# AGENTS.md — K.T.R.A Project

## Ruflo — أداة الـ Multi-Agent الافتراضية

**الأداة المستخدمة دائماً في البرمجة:** [Ruflo](https://github.com/ruvnet/ruflo) (نسخة محلية: `.clone/ruflo`)

> Ruflo هي أداة orchestration للـ multi-agent مبنية فوق Codex. تضيف swarms ذاتية التنظيم، ذاكرة دائمة، وتنسيق موزع بين الوكلاء.

### تشغيل Ruflo في هذا المشروع

```bash
# تهيئة Ruflo (مرة واحدة)
npx ruflo init

# أو من النسخة المحلية
node .clone/ruflo/bin/ruflo.js init
```

---

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

## إعدادات مشروع K.T.R.A

### Tech Stack
- **Backend:** Django 6.0.1, DRF 3.16, MySQL (prod) / SQLite (test)
- **Frontend:** React 19.2, TypeScript 5.8, Vite 6.2, Tailwind CSS 4.3
- **Tests:** pytest-django (70 tests) · `python manage.py test --settings=core.test_settings`

### بنية المجلدات الرئيسية
| مجلد | الغرض |
|------|--------|
| `accounting/` | محاسبة — قيود، فواتير، مدفوعات |
| `sales/` | المبيعات والعملاء |
| `inventory/` | المخزون والمنتجات |
| `partners/` | العملاء والموردين |
| `frontend_v2/` | React SPA (TypeScript) |
| `.clone/ruflo/` | Ruflo (نسخة محلية من الأداة) |

### قواعد Django
- استخدم `core.test_settings` في الاختبارات
- الـ migrations في مجلد `migrations/` داخل كل app
- الـ serializers والـ views في `api/` داخل كل app

### قواعد Frontend
- الملفات في `frontend_v2/src/`
- استخدم `restApi.ts` كـ base client
- CSS عبر Tailwind فقط — لا inline styles

---

## استخدام Ruflo في المهام المعقدة

### Swarm للمهام الكبيرة

```javascript
// تهيئة swarm هرمي للمهام المعقدة
mcp__ruv-swarm__swarm_init({
  topology: "hierarchical",
  maxAgents: 6,
  strategy: "specialized"
})
```

### توجيه المهام

| نوع المهمة | الأداة |
|------------|--------|
| تحويلات بنيوية بسيطة | Tier 1 (codemod — $0 لا LLM) |
| مهام بسيطة | Tier 2 (Haiku) |
| معالجة معقدة / أمان / بنية | Tier 3 (Sonnet/Opus) |

### Anti-Drift للـ Coding Swarms
- استخدم `hierarchical` topology دائماً
- حدّ أقصى 6-8 agents للتنسيق الجيد
- شغّل checkpoints عبر `post-task` hooks
- namespace مشترك لكل الـ agents في المهمة الواحدة

---

## تثبيت Ruflo بالكامل (اختياري)

```bash
# تثبيت كامل — يضيف 98 agent, 60+ أمر, MCP server, hooks
npx ruflo init

# فحص الصحة بعد التثبيت
npx ruflo doctor
```

> **النسخة المحلية** متاحة في `.clone/ruflo/` — يمكن استخدامها مباشرة بدون تثبيت.
