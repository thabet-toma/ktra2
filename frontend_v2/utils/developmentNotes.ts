/**
 * قواعد عرض ملاحظات التطوير المشتركة بين الشاشة والخادم.
 * الخادم يرتّب الأقدم أولاً والمكتملة أخيراً (`DevelopmentNoteViewSet`)، وهذه
 * النسخة تعيد الترتيب نفسه محلياً فور الإضافة أو تغيير الحالة بلا إعادة تحميل.
 */

type NoteLike = { id: number; status: string; created_at?: string | null };

export const isNoteDone = (note: NoteLike): boolean => note.status === 'done';

/** لحظة الإنشاء بالمللي — صفر لملاحظة لم يصلها ردّ الخادم بعد فتتبع الرقم. */
const createdAtMs = (note: NoteLike): number => {
  const parsed = Date.parse(note.created_at || '');
  return Number.isFinite(parsed) ? parsed : 0;
};

/**
 * الأقدم أولاً ثم الأحدث، والمكتملة تنزل لآخر القائمة مهما كان تاريخها.
 * `created_at` مرساة لا يحرّكها تعديل — فلا تقفز ملاحظة من مكانها عند حفظها.
 */
export const sortDevelopmentNotes = <T extends NoteLike>(notes: T[]): T[] =>
  [...notes].sort((a, b) => {
    const done = Number(isNoteDone(a)) - Number(isNoteDone(b));
    if (done !== 0) return done;
    const created = createdAtMs(a) - createdAtMs(b);
    return created !== 0 ? created : a.id - b.id;
  });

/** تسميات الحالة والأولوية — مصدر واحد للجدول وللنافذة معاً. */
export const NOTE_STATUS_LABELS: Record<string, string> = {
  todo: 'قيد الانتظار',
  in_progress: 'قيد التنفيذ',
  done: 'مكتملة',
};

export const NOTE_PRIORITY_LABELS: Record<string, string> = {
  low: 'منخفضة',
  medium: 'متوسطة',
  high: 'عالية',
};
