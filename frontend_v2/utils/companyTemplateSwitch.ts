/**
 * ISSUE #64 — تبديل قالب شركة قائمة: ماذا يختفي وماذا يظهر.
 *
 * دالّةٌ صِرفة فوق `TEMPLATE_HIDDEN_VIEWS` (`utils/viewPermissions.ts`) — نفس
 * السِجلّ الذي يقنِّع الشاشات اليوم عند الإنشاء، لا نسخة ثانية منه. القرار 4:
 * التبديل يرفع القناع ولا ينزع المزروع، فهذه الدالّة تصف **العرض** فقط —
 * لا أثر لها على أي حسابٍ أو دفتر، تلك مسؤولية الخادم
 * (`tenants.services.switch_company_template`).
 */
import { TEMPLATE_HIDDEN_VIEWS } from './viewPermissions.ts';

export type TemplateSwitchDiff = {
  /** شاشات كانت مخفيّة بالقالب الحالي وتصير ظاهرة بالقالب الجديد. */
  appearing: string[];
  /** شاشات كانت ظاهرة بالقالب الحالي وتصير مخفيّة بالقالب الجديد. */
  disappearing: string[];
};

/** غياب القالب أو مفتاحه غير المسجَّل = `general` (بلا إخفاء) — نفس تطبيع `templateHidesView`. */
const hiddenViewsOf = (templateKey?: string | null): Set<string> =>
  new Set(TEMPLATE_HIDDEN_VIEWS[templateKey ?? ''] ?? []);

/** الفرق بين قناعَي قالبين — لا يفترض اتجاهاً: يعمل من وإلى أي قالبين مسجَّلين. */
export function diffTemplateSwitch(
  fromTemplate: string | null | undefined,
  toTemplate: string | null | undefined,
): TemplateSwitchDiff {
  const before = hiddenViewsOf(fromTemplate);
  const after = hiddenViewsOf(toTemplate);
  return {
    // كانت مخفيّة (before) ولم تعد مخفيّة (after) ⇒ تظهر.
    appearing: [...before].filter((view) => !after.has(view)).sort(),
    // لم تكن مخفيّة ثم صارت مخفيّة ⇒ تختفي.
    disappearing: [...after].filter((view) => !before.has(view)).sort(),
  };
}
