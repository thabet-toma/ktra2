/**
 * وجهة زرّ «رجوع» — القاعدة كلّها دالّةً صرفة.
 *
 * كان الزرّ `navigate(-1)` عمياء. في تبويبٍ فُتح على مستند مباشرةً لا يوجد ما
 * يُرجَع إليه أصلاً: الضغطة إمّا لا تفعل شيئاً (المستخدم يظنّ الزرّ معطوباً)
 * أو تقذفه خارج التطبيق كلّه. الموجّه نفسه يحمل الجواب: `react-router` يحفظ
 * `idx` في `history.state` — صفرٌ يعني «هذه أول صفحة في هذا التبويب».
 *
 * فحين لا سابقة، لا نترك المستخدم في طريق مسدود ولا نكذب عليه بزرٍّ لا يعمل:
 * ننقله إلى **قائمة شاشته** (`VIEW_PATHS[activeView]`) — لا جدولَ مساراتٍ ثانياً
 * هنا يتفرّع عن الأول ويكذب لاحقاً — ونكتب اسم الوجهة على الزرّ ليعرف أين
 * سيذهب قبل أن يضغط.
 */

export type BackKind = 'history' | 'fallback';

export interface BackTarget {
  kind: BackKind;
  /** مسار الانتقال حين `kind === 'fallback'`؛ فارغٌ مع `history`. */
  path: string;
  /** نصّ الزرّ. */
  label: string;
  /** شرحُ الوجهة في `title`/`aria-label` — الزرّ لا يخفي إلى أين يأخذ المستخدم.
   *  يبدأ دائماً بكلمة «رجوع» كي يبقى للزرّ اسمٌ ثابت يعرفه قارئ الشاشة
   *  والاختبار مهما تغيّرت الوجهة، ويحتوي النصّ المرئي (شرط WCAG 2.5.3). */
  hint: string;
}

const DASHBOARD_PATH = '/dashboard';
const DASHBOARD_LABEL = 'الرئيسية';

const normalize = (path: string): string => {
  const trimmed = (path || '/').replace(/\/+$/, '');
  return trimmed === '' ? '/' : trimmed;
};

/**
 * هل في هذا التبويب صفحةٌ سابقة **داخل التطبيق**؟
 * `react-router` يضع `{ usr, key, idx }` في `history.state`؛ `idx > 0` يعني
 * أننا دفعنا مُدخلاً واحداً على الأقل بأنفسنا، فالرجوع يبقى داخل التطبيق.
 */
export function historyCanGoBack(state: unknown): boolean {
  if (!state || typeof state !== 'object') return false;
  const idx = (state as { idx?: unknown }).idx;
  return typeof idx === 'number' && idx > 0;
}

export function resolveBackTarget(input: {
  canGoBack: boolean;
  currentPath: string;
  /** مسار قائمة الشاشة الحالية — `VIEW_PATHS[activeView]`. */
  listPath?: string | null;
  /** اسم الشاشة الحالية — `VIEW_LABELS[activeView]`. */
  listLabel?: string | null;
}): BackTarget {
  const { canGoBack, currentPath, listPath, listLabel } = input;

  if (canGoBack) {
    return { kind: 'history', path: '', label: 'رجوع', hint: 'رجوع للصفحة السابقة' };
  }

  const here = normalize(currentPath);
  if (listPath && normalize(listPath) !== here) {
    const label = listLabel || 'رجوع';
    return {
      kind: 'fallback',
      path: listPath,
      label,
      hint: `رجوع — لا توجد صفحة سابقة في هذا التبويب، الانتقال إلى «${label}»`,
    };
  }

  return {
    kind: 'fallback',
    path: DASHBOARD_PATH,
    label: DASHBOARD_LABEL,
    hint: `رجوع — لا توجد صفحة سابقة في هذا التبويب، الانتقال إلى «${DASHBOARD_LABEL}»`,
  };
}
