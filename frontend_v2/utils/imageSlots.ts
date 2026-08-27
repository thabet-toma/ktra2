/**
 * توزيع الصور الملصوقة على خانات صور ثابتة العدد (شاشة المنتج: ثلاث خانات).
 *
 * اللصق لا يعرف خانةً بعينها — القاعدة أن الصورة تذهب إلى **أول خانة فارغة**،
 * وعدّة صور تملأ الخانات الفارغة التالية بالترتيب، وما زاد يُهمَل ويُعاد عدده
 * كي تخبر الشاشة المستخدم بدل أن تبتلعه صامتة. دالة صرفة كي تُختبَر بلا متصفح.
 */

export type SlotAssignment<T> = { index: number; file: T };

export type SlotFillResult<T> = {
  /** الخانة المستهدَفة لكل ملف مقبول، بترتيب الملفات نفسه. */
  assignments: SlotAssignment<T>[];
  /** عدد الملفات التي لم تجد خانة فارغة. */
  dropped: number;
};

/** خانة فارغة = لا رابط فيها؛ والمسافات البيضاء ليست رابطاً. */
const isEmptySlot = (value: string | undefined | null): boolean => !value || value.trim() === "";

export function fillFirstEmptySlots<T>(
  slots: readonly (string | undefined | null)[],
  files: readonly T[],
): SlotFillResult<T> {
  const emptyIndexes: number[] = [];
  for (let i = 0; i < slots.length; i++) {
    if (isEmptySlot(slots[i])) emptyIndexes.push(i);
  }

  const assignments: SlotAssignment<T>[] = [];
  for (let i = 0; i < files.length && i < emptyIndexes.length; i++) {
    assignments.push({ index: emptyIndexes[i], file: files[i] });
  }

  return { assignments, dropped: files.length - assignments.length };
}
