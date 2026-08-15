/**
 * T-PERM (المرحلة 2، البند 1): ترشيح روابط التنقّل بالصلاحيات.
 *
 * الشريط الجانبي كان يقرّر بدور التطبيق القديم (`user.role === 'manager'`)، فلا
 * علاقة له بمصفوفة الصلاحيات. هنا القاعدة الوحيدة:
 *   - `perm` غير محدَّد ⇒ الرابط مفتوح للجميع (صالة الصور، من نحن…).
 *   - `perm` محدَّد ⇒ يظهر لمن يملكه فقط.
 *   - `roles` (الإرث) تبقى مُحترمة حيث لا مقابل لها في الكتالوج (الحضور، النقاط)،
 *     ومن يجمع الاثنين يلزمه استيفاؤهما معاً.
 * والمجموعة تظهر إن ظهر أحد أبنائها — كما في الأنظمة الاحترافية: القائمة مشتقّة
 * من الصلاحيات لا مكتوبة يدوياً.
 *
 * THA-110: هذه أيضاً **نقطة التركيب الوحيدة** لقناع «الوضع السهل». الوسيط
 * `uiMode` اختياري: حذفه يعني السلوك القائم حرفياً، وقيمته `'simple'` تُقلّم
 * القائمة إلى شاشات `SIMPLE_VIEWS` وحدها. الشرطان يجتمعان ولا يتبادلان —
 * **الصلاحية تحجب والوضع يُرتّب**: الرابط يظهر إن سمحت الصلاحية *و*(الوضع
 * متقدم *أو* الشاشة مُدرَجة). فلا يمنح الوضعُ ما منعته الصلاحية أبداً، ولا
 * يحجب مساراً — الرابط المباشر للشاشة المتقدمة يبقى يعمل.
 *
 * دالة صرفة (لا React) كي تُختبر وحدها — الإخفاء تجميل، والإنفاذ خادمي.
 */
// امتداد `.ts` صريح: هذا الملف يُشغَّل تحت `node --test` مباشرةً، ومحلّل ESM
// لا يُخمّن الامتداد (كما في ملفات الاختبار المجاورة).
import { viewVisibleInSimpleMode, type UiMode } from './uiMode.ts';

export type NavAccessLink = {
  key: string;
  /** مفتاح الصلاحية المطلوب لعرض الرابط (اختياري). */
  perm?: string;
  /** أدوار التطبيق القديمة (اختياري) — للشاشات خارج كتالوج الصلاحيات. */
  roles?: string[];
};

export function linkVisible<T extends NavAccessLink>(
  link: T,
  can: (key: string) => boolean,
  role?: string,
  uiMode?: UiMode,
): boolean {
  if (link.perm && !can(link.perm)) return false;
  if (link.roles && role !== undefined && !link.roles.includes(role)) return false;
  // القناع آخر شرطٍ يُفحص: لا يُستشار إلا بعد أن تكون الصلاحية سمحت أصلاً.
  if (uiMode === 'simple' && !viewVisibleInSimpleMode(link.key)) return false;
  return true;
}

export function visibleLinks<T extends NavAccessLink>(
  links: T[],
  can: (key: string) => boolean,
  role?: string,
  uiMode?: UiMode,
): T[] {
  return links.filter((l) => linkVisible(l, can, role, uiMode));
}

/** المجموعة تظهر ما دام فيها رابط واحد ظاهر. */
export function groupVisible<T extends NavAccessLink>(
  links: T[],
  can: (key: string) => boolean,
  role?: string,
  uiMode?: UiMode,
): boolean {
  return links.some((l) => linkVisible(l, can, role, uiMode));
}
