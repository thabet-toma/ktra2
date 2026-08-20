/**
 * وعي التبويبات في الواجهة — قطعتان صغيرتان يستهلكهما `Breadcrumb`:
 *
 * - `TabOriginChip`: يظهر في التبويب **المفتوح حديثاً** وحده، يومض وميضةً
 *   واحدة (نصف ثانية) ثم يهدأ إلى شارةٍ صامتة تقول من أين جاء. بلا هذا الإعلان
 *   يجد المستخدم نفسه في تبويبٍ لا يعرف كيف وصل إليه — خصوصاً حين يفتحه
 *   المتصفّح في الخلفية فيراه بعد دقائق.
 * - `LinkedTabHint`: لمحةٌ واحدة عند ضغط «رجوع» تذكّر بأن الشغل مفتوحٌ أيضاً في
 *   تبويبٍ آخر مرتبط. مرّةً واحدة لكل تبويب — التكرار إزعاج — وقابلة للتجاهل،
 *   ولا تعترض الملاحة: الرجوع يقع فوراً والتلميح يرافقه لا يسبقه.
 *
 * لماذا لا زرّ «انتقل إلى ذلك التبويب»؟ المتصفّحات تمنع `window.focus()` من
 * تبويبٍ غير مُفعَّل، و`rel="noopener"` يقطع المقبض أصلاً. زرٌّ لا يعمل أسوأ من
 * غيابه، فالتلميح إخباريّ عمداً.
 *
 * الوميض عبر `.ktra-flash-once` في `styles/index.css`، وهي تحترم
 * `prefers-reduced-motion` فتُبقي الشارة وتُسقط الحركة — المعلومة ليست حركة.
 */
import React, { useEffect, useState } from 'react';
import { ExternalLink, Info, X } from 'lucide-react';
import { incomingHandoff } from '../../utils/tabLink';
import { useLinkedTabs } from '../../hooks/useLinkedTabs';

export const TabOriginChip: React.FC = () => {
  // المناولة تُستهلَك مرّة واحدة عند الإقلاع، فالقيمة ثابتة طوال عمر التبويب.
  const [handoff] = useState(() => incomingHandoff());
  const [dismissed, setDismissed] = useState(false);

  if (!handoff || dismissed) return null;

  const from = handoff.openerLabel?.trim();

  return (
    <span
      role="status"
      aria-live="polite"
      className="ktra-flash-once flex items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1 text-[var(--font-size-sm)] text-[var(--color-text-muted)]"
      title={from ? `هذا تبويب جديد فُتح من شاشة «${from}»` : 'هذا تبويب جديد فُتح من تبويب آخر'}
    >
      <ExternalLink className="h-3.5 w-3.5 text-[var(--color-primary-emphasis)]" aria-hidden="true" />
      <span className="font-semibold text-[var(--color-text)]">تبويب جديد</span>
      {from && <span className="hidden sm:inline">· من «{from}»</span>}
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="rounded p-0.5 hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
        title="إخفاء"
        aria-label="إخفاء مؤشّر التبويب الجديد"
      >
        <X className="h-3 w-3" aria-hidden="true" />
      </button>
    </span>
  );
};

/** مدّة بقاء اللمحة قبل أن تنسحب وحدها. */
const HINT_MS = 6000;

/** لمحةٌ واحدة لكل تبويب: العلَم على مستوى الوحدة لا الحالة، فلا يعود بإعادة الرسم. */
let hintShown = false;

export interface LinkedTabHintProps {
  /** يتغيّر مع كل ضغطة «رجوع» — الصفر يعني «لم يُضغط بعد». */
  trigger: number;
}

export const LinkedTabHint: React.FC<LinkedTabHintProps> = ({ trigger }) => {
  const linked = useLinkedTabs();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!trigger || hintShown || linked.length === 0) return;
    hintShown = true;
    setVisible(true);
    const timer = setTimeout(() => setVisible(false), HINT_MS);
    return () => clearTimeout(timer);
  }, [trigger, linked.length]);

  if (!visible || linked.length === 0) return null;

  const names = linked.map((t) => t.label).filter(Boolean);
  const text =
    names.length === 0
      ? `لديك أيضاً ${linked.length === 1 ? 'تبويب آخر مفتوح' : `${linked.length} تبويبات أخرى مفتوحة`}`
      : names.length === 1
      ? `لديك أيضاً «${names[0]}» مفتوحاً في تبويب آخر`
      : `لديك أيضاً ${names.length} تبويبات مفتوحة: ${names.map((n) => `«${n}»`).join(' · ')}`;

  return (
    <div
      role="status"
      aria-live="polite"
      className="ktra-flash-once absolute top-full right-0 z-40 mt-1 flex max-w-xs items-start gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-[var(--font-size-sm)] text-[var(--color-text)] shadow-lg"
    >
      <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-primary-emphasis)]" aria-hidden="true" />
      <span className="flex-1 leading-relaxed">{text}</span>
      <button
        type="button"
        onClick={() => setVisible(false)}
        className="rounded p-0.5 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text)]"
        title="تجاهل"
        aria-label="تجاهل التذكير"
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
};
