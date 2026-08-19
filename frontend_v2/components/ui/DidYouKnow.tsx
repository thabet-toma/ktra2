import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Lightbulb, ArrowLeft, X } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { usePermissions } from "../../contexts/PermissionsContext";
import { TIPS } from "../../constants/tips";
import {
  hasRoomForTip,
  hideTip,
  markTipShown,
  pickTip,
  readDidYouKnowState,
  type DidYouKnowState,
  type PrefStore,
} from "../../utils/didYouKnowPref";
import type { AppView } from "../../types/common";

/**
 * THA-121 — «هل تعلم»: بطاقةٌ واحدة تسكن الفراغ أسفل الشاشة الحالية وتشرح ميزةً
 * قائمة قليلة الاستعمال.
 *
 * ثلاث قواعد تحكمها، وكلها **خارج هذا الملف** قصداً (`utils/didYouKnowPref.ts`)
 * كي تُختبر بلا متصفح — `tsc` لا يفحص خصائص JSX هنا، فقاعدةٌ مدفونة في الشرط لا
 * يحرسها شيء:
 *  1. **سياقية**: تلميح الشيكات في شاشة الشيكات، لا في الرئيسية.
 *  2. **تُطوى وحدها** بعد ظهورَين، وزرّ «لا تُظهر هذا مجدداً» يُنهيها فوراً —
 *     لكل تلميح على حدة ولكل مستخدم على حدة.
 *  3. **لا تزاحم**: تُقاس المساحة الباقية أسفل المحتوى فعلياً، وبلا متّسع لا
 *     تُعرض أصلاً — لا تزيح عنصراً ولا تطفو فوق شيء.
 *
 * تُركَّب **مرّة واحدة** في `App.tsx` داخل `<main>`، لا في 97 صفحة.
 *
 * ولا حرف عربيّ من نصوص التلميحات هنا: كلها في `constants/tips.ts` وحده.
 */

interface Props {
  /** الشاشة المعروضة الآن — سياق التلميح. */
  view: AppView;
  /** فتح شاشة الوجهة، بنفس موجّه التطبيق. */
  onNavigate: (view: AppView) => void;
}

/** كم يهدأ الحجم قبل أن تُقاس المساحة — يبتلع نموّ المحتوى أثناء التحميل. */
const SETTLE_MS = 250;

/** `localStorage` خلف واجهةٍ ضيّقة — والدوال تحته لا ترمي مهما مُنع التخزين. */
const browserStore: PrefStore = {
  getItem: (key) => localStorage.getItem(key),
  setItem: (key, value) => localStorage.setItem(key, value),
};

export const DidYouKnow: React.FC<Props> = ({ view, onNavigate }) => {
  const { currentUser } = useAuth();
  const { can, modules, uiMode } = usePermissions();
  const userId = currentUser?.id ?? null;

  const [state, setState] = useState<DidYouKnowState>(() =>
    readDidYouKnowState(browserStore, userId),
  );
  const [hasRoom, setHasRoom] = useState(false);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const settleRef = useRef<number | null>(null);
  /** آخر ارتفاعٍ للمحتوى — به نعرف أنه ما زال ينمو فنؤجّل القياس. */
  const lastHeightRef = useRef<number>(-1);
  /** ما عُدّ ظهوره في هذا التحميل — كي لا يُحرق الظهوران في تنقّلٍ واحد. */
  const countedRef = useRef<Set<string>>(new Set());

  // تبديل المستخدم على الجهاز نفسه يعيد قراءة سجلّه هو، لا سجلّ من سبقه.
  useEffect(() => {
    setState(readDidYouKnowState(browserStore, userId));
    countedRef.current = new Set();
  }, [userId]);

  const tip = useMemo(
    () => (userId ? pickTip(TIPS, state, { view, can, modules, uiMode }) : null),
    [userId, state, view, can, modules, uiMode],
  );

  /**
   * القياس **مهدَّأ**: الشاشة تبدأ فارغة ثم تمتلئ ببياناتها، فقياسٌ فوريّ كان
   * يُظهر البطاقة لحظةً ثم يبتلعها حين يصل الجدول — ووميضٌ كهذا أسوأ من ألّا
   * تظهر أصلاً. لا تُقاس المساحة إلا بعد أن يهدأ الحجم.
   */
  const measure = useCallback(() => {
    if (settleRef.current !== null) window.clearTimeout(settleRef.current);
    settleRef.current = window.setTimeout(() => {
      settleRef.current = null;
      const el = sentinelRef.current;
      const container = el?.parentElement ?? null;
      if (!el || !container) {
        setHasRoom(false);
        return;
      }
      // ارتفاعٌ تغيّر منذ آخر دورة يعني أن المحتوى ما زال يصل: انتظر دورةً
      // أخرى بدل أن تُقاس مساحةٌ ستزول. الوميض هنا أسوأ من الغياب.
      const height = container.scrollHeight;
      if (height !== lastHeightRef.current) {
        lastHeightRef.current = height;
        measure();
        return;
      }
      setHasRoom(hasRoomForTip(el.getBoundingClientRect().top, window.innerHeight));
    }, SETTLE_MS);
  }, []);

  /**
   * يُعاد القياس عند تبديل الشاشة، وعند تغيّر حجم النافذة، وعند **نموّ المحتوى**
   * بعد وصول بياناته: شاشةٌ تبدأ فارغة ثم تمتلئ كانت ستُبقي بطاقةً لم يعد لها
   * مكان.
   */
  useEffect(() => {
    measure();
    const container = sentinelRef.current?.parentElement ?? null;
    window.addEventListener("resize", measure);
    const observer =
      container && typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => measure())
        : null;
    observer?.observe(container!);
    return () => {
      window.removeEventListener("resize", measure);
      observer?.disconnect();
      if (settleRef.current !== null) window.clearTimeout(settleRef.current);
    };
  }, [measure, view]);

  // لا يُعدّ ظهوراً إلا ما رآه المستخدم فعلاً — بطاقةٌ لم تُعرض لضيق المكان لا
  // تستهلك من رصيد التلميح شيئاً.
  useEffect(() => {
    if (!tip || !hasRoom || !userId) return;
    if (countedRef.current.has(tip.key)) return;
    countedRef.current.add(tip.key);
    setState(markTipShown(browserStore, userId, tip.key));
  }, [tip, hasRoom, userId]);

  const dismiss = useCallback(() => {
    if (!tip || !userId) return;
    setState(hideTip(browserStore, userId, tip.key));
  }, [tip, userId]);

  return (
    <>
      {/* حارسٌ صفريّ الارتفاع في نهاية التدفّق — منه تُقاس المساحة الباقية. */}
      <div ref={sentinelRef} aria-hidden="true" className="h-0" />
      {tip && hasRoom && (
        <aside
          data-testid="did-you-know"
          data-tip-key={tip.key}
          aria-label="هل تعلم"
          className="mt-6 flex items-start gap-3 rounded-xl border border-blue-200 bg-blue-50/60 p-3 text-[var(--color-text)] dark:border-blue-900/60 dark:bg-blue-950/20"
        >
          <Lightbulb className="mt-0.5 h-5 w-5 shrink-0 text-blue-600 dark:text-blue-300" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-bold text-blue-700 dark:text-blue-300">هل تعلم؟</p>
            <p className="mt-0.5 text-sm font-bold">{tip.title}</p>
            {tip.lines.map((line) => (
              <p key={line} className="mt-1 text-xs leading-6 text-[var(--color-text-muted)]">
                {line}
              </p>
            ))}
            <div className="mt-2 flex flex-wrap items-center gap-3">
              {tip.targetView && (
                <button
                  type="button"
                  onClick={() => onNavigate(tip.targetView!)}
                  className="flex items-center gap-1 rounded-lg border border-blue-300 bg-white px-2.5 py-1 text-[11px] font-bold text-blue-800 hover:bg-blue-50 dark:border-blue-800 dark:bg-slate-900 dark:text-blue-200 dark:hover:bg-slate-800"
                >
                  افتحها
                  <ArrowLeft className="h-3.5 w-3.5" />
                </button>
              )}
              <button
                type="button"
                onClick={dismiss}
                className="text-[11px] font-semibold text-[var(--color-text-muted)] underline-offset-4 hover:underline"
              >
                لا تُظهر هذا مجدداً
              </button>
            </div>
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="لا تُظهر هذا مجدداً"
            className="rounded p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-3)]"
          >
            <X className="h-4 w-4" />
          </button>
        </aside>
      )}
    </>
  );
};

export default DidYouKnow;
