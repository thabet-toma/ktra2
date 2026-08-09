/**
 * قواعد عرض ملاحظات التطوير المشتركة بين الشاشة والخادم.
 * الخادم يرتّب المكتملة أخيراً ثم الأهمّ أولاً ثم الأقدم (`DevelopmentNoteViewSet`)،
 * وهذه النسخة تعيد الترتيب نفسه محلياً فور الإضافة أو تغيير الحالة بلا إعادة تحميل.
 */

type NoteLike = {
  id: number;
  status: string;
  priority?: string | null;
  created_at?: string | null;
};

export const isNoteDone = (note: NoteLike): boolean => note.status === 'done';

/** لحظة الإنشاء بالمللي — صفر لملاحظة لم يصلها ردّ الخادم بعد فتتبع الرقم. */
const createdAtMs = (note: NoteLike): number => {
  const parsed = Date.parse(note.created_at || '');
  return Number.isFinite(parsed) ? parsed : 0;
};

/**
 * رتبة الأولوية — مرآة `priority_rank` المحسوبة في الـviewset حرفياً:
 * high=0 · medium=1 · وكل ما عداهما (بما فيه `low`) = 2، فأي قيمة مستقبلية
 * غير معروفة تهبط لنفس المكان على الجانبين ولا تقفز الملاحظة عند الحفظ.
 */
const PRIORITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

const priorityRank = (note: NoteLike): number =>
  PRIORITY_RANK[note.priority || ''] ?? 2;

/**
 * المكتملة تنزل لآخر القائمة مهما كان تاريخها، ثم الأهمّ أولاً، ثم الأقدم
 * فالأحدث داخل الأولوية الواحدة. `created_at` مرساة لا يحرّكها تعديل — فلا
 * تقفز ملاحظة من مكانها عند حفظها.
 */
export const sortDevelopmentNotes = <T extends NoteLike>(notes: T[]): T[] =>
  [...notes].sort((a, b) => {
    const done = Number(isNoteDone(a)) - Number(isNoteDone(b));
    if (done !== 0) return done;
    const priority = priorityRank(a) - priorityRank(b);
    if (priority !== 0) return priority;
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
