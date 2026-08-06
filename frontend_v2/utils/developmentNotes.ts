/**
 * قواعد عرض ملاحظات التطوير المشتركة بين الشاشة والخادم.
 * الخادم يفرز المكتملة لآخر الورقة (`DevelopmentNoteViewSet`)، وهذه النسخة
 * تعيد الفرز نفسه محلياً فور تغيير الحالة بلا انتظار إعادة تحميل.
 */

type NoteLike = { status: string };

export const isNoteDone = (note: NoteLike): boolean => note.status === 'done';

/**
 * أسطر الوصف الظاهرة قبل «عرض المزيد».
 * أما *هل* قُصّ النص فعلاً فيُقاس من المتصفح (`scrollHeight > clientHeight`) لا
 * يُقدَّر بعدد الحروف: عرض الحرف العربي أضيق من اللاتيني فالتقدير يُظهر الزر
 * على نصوص غير مقصوصة أصلاً.
 */
export const COLLAPSED_DESCRIPTION_LINES = 3;

/** المكتملة أخيراً، وما عداها يبقى بترتيب الخادم (فرز ثابت لا يلمس الأصل). */
export const sortDevelopmentNotes = <T extends NoteLike>(notes: T[]): T[] =>
  notes
    .map((note, index) => ({ note, index }))
    .sort((a, b) => {
      const done = Number(isNoteDone(a.note)) - Number(isNoteDone(b.note));
      return done !== 0 ? done : a.index - b.index;
    })
    .map((row) => row.note);
