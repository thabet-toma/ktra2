# ملف التسليم

يُحدَّث قبل أي توقّف (CLAUDE.md — Workflow، الخطوة 8). من يستلم يبدأ من هنا.

**آخر تحديث:** 2026-10-21

## أين نحن

- الخطة: `docs/plans/2026-10-21-inventory-count-category-tree.md` (13 تذكرة في 6 مراحل).
- **S1** (قفل ترحيل الجرد + ترقيم `TenantBook`): نُفّذت وروجعت (Standards + Spec)، وجولة تصليحها الأولى
  جارية في جلسة OpenCode `ses_ea297c49dffeSbYkA8ZcrlXUX5`. تغييراتها **غير ملتزَمة** في الشجرة:
  `inventory/services.py`، `inventory/tests/test_inventory_documents.py`، `docs/modules/inventory.md`،
  `ARCHITECTURE.md`، `docs/CHANGELOG.md` (+ `tenants/models.py` وهجرة بعد التصليح).
- موجز التذكرة التالية **S2** جاهز (ثغرة صلاحيات الكتالوج).

## الخطوة التالية

1. اقرأ فرق تصليح S1 سطراً بسطر، وشغّل `code-review`، ثم البوّابة كاملة بنفسك.
2. نظيف ← commit + push + نشر. غير نظيف ← موجز تصليح في جلسة جديدة.
3. ثم S2 ← B1 ← B2 ← B3 ← R1 ← C1 ← C2 ← C3 ← K1 ← K2 ← K3 ← K4.

## مفتوح

- قيد فرادة `(tenant, stocktake_number)` بعد فحص تكرارات قاعدة الإنتاج.
