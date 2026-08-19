/**
 * THA-121 — تفضيل «هل تعلم» **لكل مستخدم**: أيّ تلميحٍ أُخفي، وكم مرّةً عُرض.
 *
 * السابقة المتّبعة هي `importGuidePref.ts`: مفتاحٌ مُلحق بمعرّف المستخدم كي لا
 * يحرم صاحبُ المحل موظّفَه على الجهاز المشترك، ودوالّ صرفة بلا React ولا شبكة
 * تُختبر وحدها. الفارق الوحيد المقصود: **بلا معرّف مستخدم لا يُعرض شيء ولا
 * يُكتب شيء** — إخفاءٌ يُكتب باسم لا أحد يسري على الجميع، وهذا عكس المطلوب.
 *
 * التخزين محليّ لا خادميّ عن قصد: عدّاد «عُرض مرّتين ثم يُطوى» محلّيٌ بطبعه
 * (كتابة كل ظهورٍ للخادم ثرثرةٌ بلا مقابل)، ومعه يفقد التفضيل الخادميّ معظم
 * قيمته — فعلى جهازٍ ثانٍ يطوي التلميح نفسَه بعد ظهورَين على الأكثر. ثمنُه
 * المدفوع صراحةً: «لا تُظهر مجدداً» لا يتبع الحساب عبر الأجهزة. وهذا الملف هو
 * المقعد الوحيد للتبديل لاحقاً إلى حقلٍ على العضوية (على غرار `ui_mode`) بلا
 * مسّ المكوّن.
 *
 * وقاعدة المساحة (`hasRoomForTip`) هنا أيضاً لا في المكوّن: قاعدةٌ مدفونة في
 * JSX لا يحرسها شيء — `tsc` لا يفحص خصائص JSX في هذا المستودع.
 */
import type { PrefStore } from './importGuidePref.ts';
import { moduleAllowsView, permForView } from './viewPermissions.ts';
import { viewVisibleInSimpleMode, type UiMode } from './uiMode.ts';
import type { Tip } from '../constants/tips.ts';

export type { PrefStore };

/** سقف الظهور لكل تلميح: يُعرض مرّتين ثم يُطوى وحده بلا أن يُطلب منه. */
export const MAX_SHOWS = 2;

/** أقلّ ارتفاعٍ تحتاجه البطاقة كي تُعرض — دونه لا تُعرض أصلاً. */
export const CARD_MIN_PX = 120;

const BASE_KEY = 'ktra.didYouKnow';

/** حالة تلميحٍ واحد عند هذا المستخدم. */
export interface TipState {
  readonly hidden: boolean;
  readonly shown: number;
}

/** سجلّ المستخدم كلّه: مفتاح التلميح ← حالته. */
export type DidYouKnowState = Readonly<Record<string, TipState>>;

const EMPTY: DidYouKnowState = {};

/** مفتاح التخزين لهذا المستخدم، و`null` بلا معرّف — فلا نكتب باسم لا أحد. */
export function didYouKnowKey(userId: string | null | undefined): string | null {
  const id = String(userId ?? '').trim();
  return id ? `${BASE_KEY}:${id}` : null;
}

/** رقمٌ صحيح غير سالب، وأي شيءٍ آخر (سجلّ محرَّر بيدٍ، خادم أقدم) يعود صفراً. */
const asShown = (value: unknown): number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0
    ? Math.min(Math.floor(value), MAX_SHOWS)
    : 0;

/**
 * سجلّ المستخدم. **لا يرمي أبداً**: تخزينٌ محظور أو JSON فاسد أو شكلٌ غريب ⇒
 * سجلٌّ فارغ — يعود المستخدم يرى التلميحات، وهو أهون من شاشةٍ تنكسر.
 */
export function readDidYouKnowState(
  store: PrefStore,
  userId: string | null | undefined,
): DidYouKnowState {
  const key = didYouKnowKey(userId);
  if (!key) return EMPTY;
  let raw: string | null;
  try {
    raw = store.getItem(key);
  } catch {
    return EMPTY;
  }
  if (!raw) return EMPTY;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return EMPTY;
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return EMPTY;
  const out: Record<string, TipState> = {};
  for (const [tipKey, value] of Object.entries(parsed as Record<string, unknown>)) {
    if (!value || typeof value !== 'object') continue;
    const entry = value as { hidden?: unknown; shown?: unknown };
    out[tipKey] = { hidden: entry.hidden === true, shown: asShown(entry.shown) };
  }
  return out;
}

/** يحفظ السجلّ — وفشل الحفظ لا يمنع البطاقة من العمل في هذه الجلسة. */
function writeState(
  store: PrefStore,
  userId: string | null | undefined,
  state: DidYouKnowState,
): void {
  const key = didYouKnowKey(userId);
  if (!key) return;
  try {
    store.setItem(key, JSON.stringify(state));
  } catch {
    /* تخزين محظور (وضع خاص، حصّة ممتلئة) — الحالة في الذاكرة تكفي الآن */
  }
}

const entryFor = (state: DidYouKnowState, tipKey: string): TipState =>
  state[tipKey] ?? { hidden: false, shown: 0 };

/** «لا تُظهر هذا مجدداً» — يُخفي هذا التلميح وحده عند هذا المستخدم وحده. */
export function hideTip(
  store: PrefStore,
  userId: string | null | undefined,
  tipKey: string,
): DidYouKnowState {
  const state = readDidYouKnowState(store, userId);
  const next: DidYouKnowState = {
    ...state,
    [tipKey]: { ...entryFor(state, tipKey), hidden: true },
  };
  writeState(store, userId, next);
  return next;
}

/**
 * يعدّ ظهوراً واحداً. المكوّن يناديها **مرّةً واحدة لكل تحميل صفحة لكل تلميح**
 * كي لا يُحرق الظهوران في تنقّلٍ واحدٍ ذهاباً وإياباً.
 */
export function markTipShown(
  store: PrefStore,
  userId: string | null | undefined,
  tipKey: string,
): DidYouKnowState {
  const state = readDidYouKnowState(store, userId);
  const current = entryFor(state, tipKey);
  if (current.shown >= MAX_SHOWS) return state;
  const next: DidYouKnowState = {
    ...state,
    [tipKey]: { ...current, shown: current.shown + 1 },
  };
  writeState(store, userId, next);
  return next;
}

/** ما تحتاجه الأهلية من سياق الشاشة الحالية. */
export interface TipContext {
  /** الشاشة المعروضة الآن. */
  readonly view: string;
  readonly can: (permission: string) => boolean;
  readonly modules?: Record<string, boolean> | null;
  readonly uiMode: UiMode;
}

/**
 * هل يملك المستخدم هذه الشاشة أصلاً؟ الصلاحية والوحدة — مقروءتان من نفس خرائط
 * الشريط الجانبي لا من نسخةٍ ثانية.
 *
 * تُطبَّق على شاشة التلميح **نفسها** أيضاً لا على وجهته وحدها: `App.tsx` يسقط
 * على لوحة التحكم حين تُحجب الشاشة بينما تبقى `appView` على الشاشة المحجوبة،
 * فبلا هذا الحارس يظهر تلميح الشيكات فوق لوحةٍ لا شيكات فيها.
 */
function viewAllowed(view: string, ctx: TipContext): boolean {
  const permission = permForView(view);
  if (permission && !ctx.can(permission)) return false;
  return moduleAllowsView(view, ctx.modules);
}

/**
 * هل تُفتح شاشة الوجهة لهذا المستخدم؟ ما يملكه، **زائد** قناع الوضع السهل: لا
 * يُدعى المستخدم إلى شاشةٍ يخفيها وضعُه. القناع على الوجهة وحدها — شاشةٌ متقدّمة
 * فتحها بالرابط المباشر لا تُحرم من شرح ما فيها.
 */
function targetReachable(target: string, ctx: TipContext): boolean {
  if (!viewAllowed(target, ctx)) return false;
  return ctx.uiMode !== 'simple' || viewVisibleInSimpleMode(target);
}

/**
 * التلميح المعروض الآن، و`null` إن لم يبقَ مؤهَّل. المؤهَّل: شاشتُه هي الشاشة
 * الحالية · غير مخفيّ · لم يبلغ سقف الظهور · ووجهتُه — إن كانت له وجهة —
 * مفتوحةٌ له فعلاً؛ فلا يَعِد تلميحٌ بشاشةٍ تحجبها صلاحية.
 *
 * وعند التساوي يفوز **الأقلّ ظهوراً** ثم ترتيب التصريح: فتُعرَض التلميحات
 * بالتناوب بدل أن يستهلك واحدٌ ظهورَيه ثم يبدأ الذي يليه.
 */
export function pickTip(
  tips: readonly Tip[],
  state: DidYouKnowState,
  ctx: TipContext,
): Tip | null {
  let best: Tip | null = null;
  let bestShown = Number.POSITIVE_INFINITY;
  for (const tip of tips) {
    if (tip.view !== ctx.view) continue;
    const entry = entryFor(state, tip.key);
    if (entry.hidden || entry.shown >= MAX_SHOWS) continue;
    if (!viewAllowed(tip.view, ctx)) continue;
    if (tip.targetView && !targetReachable(tip.targetView, ctx)) continue;
    if (entry.shown < bestShown) {
      best = tip;
      bestShown = entry.shown;
    }
  }
  return best;
}

/**
 * هل في ذيل الشاشة متّسعٌ للبطاقة؟ يُقاس من أعلى حارسٍ صفريّ الارتفاع موضوعٍ
 * في نهاية التدفّق: إن لم يبقَ تحته `CARD_MIN_PX` داخل إطار العرض فلا بطاقة
 * أصلاً — **لا تزيح محتوى ولا تطفو فوقه**، تختفي وحسب.
 */
export function hasRoomForTip(
  sentinelTop: number,
  viewportHeight: number,
  cardMinPx: number = CARD_MIN_PX,
): boolean {
  if (!Number.isFinite(sentinelTop) || !Number.isFinite(viewportHeight)) return false;
  return sentinelTop + cardMinPx <= viewportHeight;
}
