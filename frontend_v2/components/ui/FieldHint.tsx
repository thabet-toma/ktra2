/**
 * THA-110 — «علامة سؤال تشرح كل عنصر» (طلب المالك حرفياً).
 *
 * أيقونة «؟» صغيرة تُفتح بضغطة فتشرح العنصر بجوارها في سطرين. ثلاث قواعد
 * تحكمها، وكلها هنا في مكانٍ واحد كي لا تُنسى في موضع نداءٍ من ثمانية عشر:
 *
 * 1. **الوضع السهل وحده.** المكوّن يقرأ `uiMode` بنفسه ويختفي في المتقدّم —
 *    التلميحات ضجيجٌ على المحترف، والشرط لو تُرك لكل موضع نداءٍ لسقط في أحدها.
 * 2. **لا نصّ هنا.** كل حرفٍ يراه المستخدم يأتي من `constants/simpleHints.ts`
 *    وحده — الملف الواحد القابل للتحرير الذي طلبه المالك.
 * 3. **مفتاحٌ ناقص ⇒ لا أيقونة، لا انكسار.** لا شاشة تسقط لأن نصّاً لم يُكتب.
 *
 * بلا مكتبة خارجية وبلا أنماط مضمّنة: زرٌّ حقيقي (فيُبلَغ بالتاب ويُفتح
 * بالمسافة/الإدخال)، Escape يغلق، والنقر خارجه يغلق. و`preventDefault` مقصود:
 * الأيقونة قد تسكن داخل `<label>`، وبدونه تُبدّل ضغطتُها خانة الاختيار المجاورة.
 */
import React, { useEffect, useId, useRef, useState } from 'react';
import { HelpCircle } from 'lucide-react';
import { usePermissions } from '../../contexts/PermissionsContext';
import { simpleHintFor, type SimpleHintKey } from '../../constants/simpleHints';

interface FieldHintProps {
  /** مفتاح النصّ في `constants/simpleHints.ts`. */
  hint: SimpleHintKey;
  /**
   * جهة انفتاح الفقاعة — تُختار **بعيداً عن أقرب حافة**: `start` تنفتح نحو
   * داخل الصفحة (الافتراض، ويصلح لما كان قرب حافة الشاشة اليمنى)، و`end`
   * تنفتح نحو الجهة الأخرى ويلزم حيث يقصّ الأبُ ما يخرج عنه — كقائمة الشريط
   * الجانبي (`overflow-y-auto`). موضعٌ ثابت بلا قياسٍ وقت التشغيل.
   */
  align?: 'start' | 'end';
  className?: string;
}

export const FieldHint: React.FC<FieldHintProps> = ({ hint, align = 'start', className = '' }) => {
  const { uiMode } = usePermissions();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement>(null);
  const bubbleId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const text = simpleHintFor(hint);
  if (uiMode !== 'simple' || !text) return null;

  return (
    <span ref={wrapRef} className={`relative inline-flex shrink-0 ${className}`}>
      <button
        type="button"
        data-field-hint={hint}
        aria-label={text.title}
        aria-expanded={open}
        aria-controls={open ? bubbleId : undefined}
        title={text.title}
        onClick={(e) => {
          // الأيقونة قد تكون داخل `<label>` أو داخل زرّ تنقّل: لا تُبدّل خانةً
          // ولا تفتح شاشةً — تفتح شرحها وحده.
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-emerald-600 transition-colors hover:bg-emerald-100 hover:text-emerald-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:text-emerald-400 dark:hover:bg-emerald-950/50 dark:hover:text-emerald-200"
      >
        <HelpCircle className="h-3.5 w-3.5" />
      </button>
      {open && (
        <span
          id={bubbleId}
          role="tooltip"
          className={`absolute top-full z-50 mt-1 w-56 rounded-md border border-emerald-200 bg-white p-2 text-right text-[11px] leading-5 font-normal text-gray-700 shadow-lg dark:border-emerald-900 dark:bg-gray-800 dark:text-gray-200 ${align === 'end' ? 'end-0' : 'start-0'}`}
        >
          <span className="mb-0.5 block font-bold text-emerald-700 dark:text-emerald-300">{text.title}</span>
          {text.lines.map((line) => (
            <span key={line} className="block">{line}</span>
          ))}
        </span>
      )}
    </span>
  );
};

export default FieldHint;
