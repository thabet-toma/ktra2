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
