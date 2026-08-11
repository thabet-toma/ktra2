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
 * دالة صرفة (لا React) كي تُختبر وحدها — الإخفاء تجميل، والإنفاذ خادمي.
 */
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
): boolean {
  if (link.perm && !can(link.perm)) return false;
  if (link.roles && role !== undefined && !link.roles.includes(role)) return false;
  return true;
}

export function visibleLinks<T extends NavAccessLink>(
  links: T[],
  can: (key: string) => boolean,
  role?: string,
): T[] {
  return links.filter((l) => linkVisible(l, can, role));
}

/** المجموعة تظهر ما دام فيها رابط واحد ظاهر. */
export function groupVisible<T extends NavAccessLink>(
  links: T[],
  can: (key: string) => boolean,
  role?: string,
): boolean {
  return links.some((l) => linkVisible(l, can, role));
}
