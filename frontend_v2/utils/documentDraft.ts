/**
 * ISSUE #118 — وحدة القرار لمسودّات المستندات المحلّية (IndexedDB).
 *
 * دوالٌّ نقيّة فقط — **كل** منطق القرار هنا، والخطّاف (`hooks/useDocumentDraft.ts`)
 * غلافٌ رقيقٌ فوقها بلا قرار خاص به. هذا الملف هو المقعد الوحيد الذي يُشغَّل فيه
 * `node --test` لهذه الميزة (سابقة: `offlineTenantScope.ts` و`idleSession.ts`).
 *
 * القرارات المصدر: issue #109 §§٣–٩ (مواصفة)، issue #118 (تنفيذ ١/٤).
 */

import { tenantScopedOfflineKey } from "./offlineTenantScope.ts";

/* ─────────────────────────── هويّة المسودّة (§٧) ─────────────────────────── */

/**
 * مفتاح المسودّة: `(شركة، نوعُ المستند، معرّفُ المستندِ القائم أو معرّفُ التبويب)`.
 *
 * مستندٌ قائم (`docId` معروف) ⇒ المفتاح على معرّف المستند — كل من يفتحه يرى نفس
 * المسودّة. مستندٌ جديد (`docId` غائب) ⇒ المفتاح على معرّف **التبويب** — العطبُ
 * القائم في `SalesInvoiceEditor` كان مفتاحاً واحداً (`"new"`) لكل الفواتير
 * الجديدة، ففاتورتان جديدتان في تبويبين تتزاحمان.
 */
export function buildDocumentDraftKey(params: {
  tenantId: number;
  docType: string;
  docId: string | number | null | undefined;
  tabId: string;
}): string {
  const { tenantId, docType, docId, tabId } = params;
  const identity =
    docId != null && docId !== ""
      ? `${docType}:doc:${docId}`
      : `${docType}:tab:${tabId}`;
  return tenantScopedOfflineKey(tenantId, identity);
}

/* ──────────────────────── متى تُكتب — علامة «لُمِس» (§٤) ─────────────────── */

/**
 * قرارُ الكتابة الوحيد: **لُمِس أم لا** — لا حالة المستند (`status`) ولا وجود
 * بنود (`lines.length`). كلاهما سقط عمداً: مَن يعدّل مستنداً مرحَّلاً ويغادر لا
 * يجوز أن يفقد تعديله بلا سبب، ورأسٌ مكتوبٌ بلا بنود عملٌ حقيقيّ.
 *
 * علامة «لُمِس» نفسها مسؤوليّة المستدعي (`isTouched` تُرفَع عند أوّل تعديل
 * **مستخدم**، لا عند التعبئة البرمجية لحمولة محمَّلة من الخادم) — هذه الدالّة
 * تُطبّق القرار عليها فقط.
 */
export function shouldPersistDraft(isTouched: boolean): boolean {
  return isTouched === true;
}

/* ───────────────────────── أهليّة الاستعادة (§٩) ──────────────────────────── */

export type DraftRestoreEligibility = "restore" | "stale" | "posted";

export interface DraftRestoreInput {
  /** المستند المرحَّل لا يُكتب عليه إلا بمسار `unpost` — لا استعادة تلقائية إطلاقاً. */
  isPosted: boolean;
  /** ختم تعديل المستند كما كان لحظة فتحه (وقت بدء جلسة المسودّة)، أو `null` لمستند جديد. */
  draftDocUpdatedAt: string | null;
  /** ختم تعديل المستند الحالي القادم من الخادم عند العودة، أو `null` لمستند جديد. */
  currentDocUpdatedAt: string | null;
}

/**
 * ثلاثة أحكام لا أكثر:
 * - `posted`: اطّلاعٌ فقط — الشريط يُعرض ولا يُطبَّق شيء تلقائياً.
 * - `stale`: الختمان اختلفا (تغيّر المستند بعد المسودّة) — القرار للمستخدم.
 * - `restore`: مطابقان (أو مستندٌ جديد بلا ختمٍ من الأصل) — استعادةٌ تلقائية.
 */
export function evaluateDraftRestore(
  input: DraftRestoreInput,
): DraftRestoreEligibility {
  if (input.isPosted) return "posted";
  if (
    input.draftDocUpdatedAt != null &&
    input.currentDocUpdatedAt != null &&
    input.draftDocUpdatedAt !== input.currentDocUpdatedAt
  ) {
    return "stale";
  }
  return "restore";
}

/* ───────────────────────── اليتامى — مستندٌ جديد (§٧) ─────────────────────── */

export interface OrphanDraftCandidate {
  key: string;
  /** `null`/فارغ لمسودّة مستندٍ جديد (المفتاحُ على معرّف تبويب) — الأخرى تُستبعد. */
  docId: string | null;
  updatedAt: string;
}

/**
 * يتامى مستندٍ جديد لنفس الشركة والنوع (المستدعي يُقيِّد الاستعلام بالفعل عبر
 * الفهرس `[tenant_id+doc_type]`) — باستثناء مسودّة **هذا التبويب نفسه**
 * (`currentKey`)، الأحدث أوّلاً. مسودّاتٌ لمستندٍ **قائم** (`docId` معروف)
 * ليست يتيمة بهذا المعنى: مفتاحها على معرّف المستند لا التبويب، فمن يفتحه من
 * أيّ تبويب يرى نفس المسودّة — لا تزاحم.
 */
export function selectOrphanDrafts<T extends OrphanDraftCandidate>(
  drafts: T[],
  currentKey: string,
): T[] {
  return drafts
    .filter((d) => (d.docId == null || d.docId === "") && d.key !== currentKey)
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
}

/**
 * سطر محتوى المسودّة الأوّل — تمييزٌ بصريّ بين يتيمين لا أكثر، لا استخلاصٌ
 * دلاليّ (الحمولة تختلف شكلاً بين نوع مستندٍ وآخر، ولا معرفة هنا بحقولها).
 * تمثيلٌ نصّيّ ثابتٌ للحمولة (`JSON.stringify` مضغوطاً بلا أسطر) مقصوصٌ بطول
 * أقصى — أوثق من تخمين حقلٍ بعينه («اسم المورّد»؟ «اسم العميل»؟) قد لا يوجد.
 */
export function draftPreviewLine(data: string, maxLen = 100): string {
  let text: string;
  try {
    text = JSON.stringify(JSON.parse(data));
  } catch {
    text = data;
  }
  const firstLine = (text.split("\n")[0] ?? "").trim();
  return firstLine.length > maxLen ? `${firstLine.slice(0, maxLen)}…` : firstLine;
}

/** نصّ شريط اليتامى بجمعٍ عربيّ صحيح — لا نصّ مثنّىً ثابت لعددٍ متغيّر. */
export function orphanDraftsBannerText(count: number): string {
  if (count <= 0) return "";
  if (count === 1) return "لديك مسودةٌ واحدة غير محفوظة";
  if (count === 2) return "لديك مسودتان غير محفوظتين";
  return `لديك ${count} مسودّات غير محفوظة`;
}

/* ──────────────────── نفس المستند في تبويبين — إنذارٌ مرّة (§٨) ────────────── */

export interface CrossTabWriteWarningInput {
  /** `tab_id` الصفّ الموجود قبل هذه الكتابة، أو `null` إن لم توجد مسودّة بعد. */
  previousTabId: string | null;
  /** معرّف هذا التبويب — الحاضر الآن، لا معرّف مسودّة المستند الجديد الثابت. */
  thisTabId: string;
  /** التبويب الآخر لا يزال حيّاً (وعي الحضور في `utils/tabLink.ts`)؟ */
  isOtherTabLive: boolean;
  /** أُطلق الإنذار لهذه الهويّة (مفتاح المسودّة) في هذه الجلسة من قبل؟ */
  alreadyWarnedForKey: boolean;
}

/**
 * القرار: تنبيهٌ صريحٌ **مرّةً واحدة** لكل هويّة مسودّة — لا في كل كتابة، ولا
 * لتبويبٍ أُغلق فعلاً (ختمه باقٍ في الصفّ لكنه لم يعد حيّاً). الكتابة نفسها لا
 * تتوقّف على هذا القرار — «ثمّ تمضي» (issue #119): لا دمج ولا منع، تنبيهٌ ثم
 * الكتابة تجري كما هي.
 */
export function shouldWarnCrossTabWrite(input: CrossTabWriteWarningInput): boolean {
  if (input.alreadyWarnedForKey) return false;
  if (input.previousTabId == null) return false;
  if (input.previousTabId === input.thisTabId) return false;
  return input.isOtherTabLive;
}

/* ─────────────── فتح يتيمٍ فوق عملٍ غير محفوظ — تحذيرٌ أولاً (issue #146) ────── */

export interface OrphanOpenGuardInput {
  /** يوجد تعديلٌ مستخدمٍ غير محفوظ على الشاشة الآن — نفس علامة «لُمِس»
   *  (`isTouched`) التي تقرر أصلاً هل تُكتب المسودّة الحالية. */
  isTouched: boolean;
}

/**
 * فتح مسودّةٍ يتيمة يستبدل حالة الشاشة كاملةً (`onRestore`) — فاستبدالها
 * فوق عملٍ لُمِس بلا تحذير يمحو ذلك العمل صامتاً، وهو بالضبط العطب الذي منعته
 * قواعد issue #118–#121 عن الإغلاق والحذف. القرار وحيدٌ هو «لُمِس أم لا»، بلا
 * فحص محتوى إضافي — نفس بساطة `shouldPersistDraft`.
 */
export function wouldOpeningOrphanClobberUnsavedWork(input: OrphanOpenGuardInput): boolean {
  return input.isTouched === true;
}

/* ───────────────────────── متى تُمحى — ٣٠ يوماً (§٥) ──────────────────────── */

export const DRAFT_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

/** طابعٌ تالف يُعامَل كمنتهٍ — لا مسودّة يُوثَق بعمرها بلا تاريخ مفهوم. */
export function isDraftExpired(
  updatedAt: string | number,
  now: number,
  maxAgeMs: number = DRAFT_MAX_AGE_MS,
): boolean {
  const t = typeof updatedAt === "number" ? updatedAt : Date.parse(updatedAt);
  if (!Number.isFinite(t)) return true;
  return now - t > maxAgeMs;
}

export interface SweepableDraft {
  key: string;
  updatedAt: string | number;
}

/** مفاتيح المسودّات الواجب كنسها — مكنسةٌ ٣٠ يوماً تمنع التراكم بلا سياسة. */
export function selectExpiredDraftKeys(
  drafts: SweepableDraft[],
  now: number,
  maxAgeMs: number = DRAFT_MAX_AGE_MS,
): string[] {
  return drafts
    .filter((d) => isDraftExpired(d.updatedAt, now, maxAgeMs))
    .map((d) => d.key);
}
