/**
 * «تثبيت على الصفحة» — دوالّ خالصة لشريط الملاحظات الأصفر أعلى الصفحة
 * (`components/layout/PinnedPageNotes.tsx`). تسكن هنا كي تُختبر بـ`node --test`
 * بلا تصيير مكوّن، ولأنّ مفتاح الطيّ وقراءته مع تعطّل `localStorage` قواعدُ تُنسى.
 */

export interface PageNoteLike {
  is_done: boolean;
  is_pinned?: boolean;
}

/** الملاحظات المفتوحة (غير المنجزة) لصفحة، ومنها المثبّتة التي يعرضها الشريط. */
export function splitPageNotes<T extends PageNoteLike>(notes: readonly T[]): {
  open: T[];
  pinned: T[];
} {
  const open = notes.filter((note) => !note.is_done);
  return { open, pinned: open.filter((note) => note.is_pinned === true) };
}

/** مفتاح تخزين حالة الطيّ: لكل مستخدم ولكل مسار صفحة. */
export function pinnedNotesCollapsedKey(userId: string | number, pathname: string): string {
  return `ktra.pinnedNotes.collapsed.${userId}.${pathname}`;
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

/** قراءة حالة الطيّ — أي عطب في التخزين (وضع خاص، منع) يعني «غير مطويّ». */
export function readPinnedNotesCollapsed(
  getStorage: () => StorageLike,
  userId: string | number,
  pathname: string,
): boolean {
  try {
    return getStorage().getItem(pinnedNotesCollapsedKey(userId, pathname)) === '1';
  } catch {
    return false;
  }
}

/** حفظ حالة الطيّ؛ الفتح يمسح المفتاح كي لا يتراكم تخزين لكل صفحة زارها المستخدم. */
export function writePinnedNotesCollapsed(
  getStorage: () => StorageLike,
  userId: string | number,
  pathname: string,
  collapsed: boolean,
): void {
  try {
    const key = pinnedNotesCollapsedKey(userId, pathname);
    if (collapsed) getStorage().setItem(key, '1');
    else getStorage().removeItem(key);
  } catch {
    // التخزين غير متاح: الطيّ يبقى لهذه الجلسة في الحالة فقط.
  }
}

/**
 * سطر الشريط المطويّ بصرف العدد العربي الصحيح. `formatted` هو العدد بعد
 * `formatNumber` (المصدر الوحيد لعرض الأرقام) — يُمرَّر لا يُحسب هنا.
 */
export function pinnedNotesSummary(count: number, formatted: string): string {
  if (count === 1) return 'ملاحظة مثبّتة على هذه الصفحة';
  if (count === 2) return 'ملاحظتان مثبّتتان على هذه الصفحة';
  if (count >= 3 && count <= 10) return `${formatted} ملاحظات مثبّتة على هذه الصفحة`;
  return `${formatted} ملاحظةً مثبّتة على هذه الصفحة`;
}

const BODY_CLAMP_CHARS = 220;
const BODY_CLAMP_LINES = 4;

/** نصٌّ طويل يُقصّ خلف «المزيد» كي لا يبتلع الشريط الصفحةَ. */
export function isLongNoteBody(body: string): boolean {
  return body.length > BODY_CLAMP_CHARS || body.split('\n').length > BODY_CLAMP_LINES;
}
