# قواعد كثافة واجهة المستخدم — UI Density Rules

> **المرجع:** P-G-14 من task6.  
> **الفلسفة:** الأصيل كان يعمل على شاشة 1024×768 بدون scroll.  
> **القاعدة الذهبية:** Information Density First; Whitespace Second.

---

## 1. Viewport Budget

على شاشة 1920×1080، يجب أن يدخل كل form/viewport في 1080px:

| العنصر | أقصى ارتفاع |
|--------|-------------|
| Toolbar (أزرار + nav) | 44px |
| Header band (حقول) | 180px |
| Status Timeline | 32px |
| Tab bar | 36px |
| **Subtotal fixed** | **292px** |
| Tab content | `calc(100vh - 324px)` — scroll داخلي فقط |
| Status bar | 32px |
| **Total** | **~324px fixed + flexible content** |

→ في viewport 1080px، الـtab content يأخذ 756px — يكفي لمعظم الجداول.

---

## 2. Header Band

- CSS grid: `grid-template-columns: repeat(6, 1fr)` (6 أعمدة على 1080px+)
- كل حقل = `<label className="aseel-field"><span className="aseel-field-label">الاسم</span><input className="aseel-input" .../></label>`
- ارتفاع الحقل = 22px (حجم `aseel-input`)
- مسافة بين الحقول: `gap: 2px 8px`
- عدد الحقول: 24 (4 صفوف × 6 أعمدة)

---

## 3. بدائل الأقسام المكدّسة

| القديم (ممنوع) | الجديد (إلزامي) |
|----------------|-----------------|
| `CollapsibleSection` مع padding كبير | `AseelDocumentShell` tabs أفقية |
| `space-y-6`, `space-y-4` بين الأقسام | tabs مع content واحد مرئي |
| أقسام عمودية مع `mb-*` | tab أفقي لا يزيد ارتفاعه عن 36px |
| `p-6`, `p-8` حول المحتوى | `padding: 4px 8px` في tab content |

---

## 4. Compact Timeline

- استبدال `ShipmentStatusVisualizer` (100px) بـ `CompactTimeline` (32px)
- سطر واحد: `●مكتمل → ◐حالي → ○قادم`
- CSS: `height: 32px, display: flex, gap: 4px, direction: ltr`
- خلفية: `var(--aseel-bg-strip, #f5f5f5)`

---

## 5. Totals / Side Dock

- على ≥1280px: side panel على اليمين (ثابت، ~280px عرض)
- على <1280px: أسفل المحتوى (row أفقي)
- كل total: `<div className="aseel-total-row"><span>label</span><span className="aseel-total-value">value</span></div>`

---

## 6. Modals

- ممنوع: fullscreen overlays أو centered modals تحجب الشاشة
- إلزامي: side-panel على اليمين بعرض 380px لا يخفي الـform
- استخدم `Drawer` من `@/components/ui/Drawer` إن وُجد

---

## 7. Audit

شغّل `node scripts/density-audit.js` دورياً.  
في CI: `node scripts/density-audit.js --ci` يَفشل إن وُجد:
- ملف > 400 سطر (دلالة على كثافة منخفضة)
- `CollapsibleSection` (يجب أن يكون tab)
- `p-6`/`p-8`/`space-y-4` (padding مبالغ فيه)
- `: any` (نوع غير مصرّح)

---

## 8. الاستثناءات

- شاشات الـlist (`AseelDenseTable`) لا تحتاج density treatment — هي أصلاً كثيفة.
- شاشات التقارير (PDF-preview) مستثناة.
- الـmodals التي تعرض صورة أو مستند بحجم كامل (مثل Viewer) مستثناة — لكن side-panel مفضّل.
